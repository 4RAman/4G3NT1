import asyncio
import json
from datetime import datetime, timedelta

import httpx
import pytest

from aibutton.audio import SoundPlayer
from aibutton.button import TriggerType
from aibutton.config import ConfigManager
from aibutton.main import Clock, DeviceStatus
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app


@pytest.fixture
def ctx(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"ble_device_name": "TestBtn"}), encoding="utf-8")
    store = EventStore(str(tmp_path / "events.db"))
    sounds = SoundPlayer(enabled=False)
    context = WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        trigger_queue=asyncio.Queue(),
        clock=Clock(),
        sounds=sounds,
        mock=True,
    )
    yield context
    store.close()
    sounds.close()


@pytest.fixture
async def client(ctx):
    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_index_serves_html(client):
    res = await client.get("/")
    assert res.status_code == 200
    assert "<title>AI Button</title>" in res.text


async def test_status_shape(client, ctx):
    ctx.status.state = "THINKING"
    ctx.status.last_trigger = "short_press"
    res = await client.get("/api/status")
    data = res.json()
    assert data["state"] == "THINKING"
    assert data["device_name"] == "TestBtn"
    assert data["mode_count"] == 5  # built-in default mode set
    assert data["last_trigger"] == "short_press"
    assert data["uptime_s"] >= 0


async def test_get_config_returns_raw_and_effective(client):
    data = (await client.get("/api/config")).json()
    assert data["raw"] == {"ble_device_name": "TestBtn"}
    assert data["effective"]["ble_device_name"] == "TestBtn"
    assert data["effective"]["prefer_remote"] is True  # default filled in
    assert data["warnings"] == []


async def test_put_config_applies_persists_and_reloads(client, ctx):
    body = {
        "ble_device_name": "Renamed",
        "modes": [
            {"name": "Only", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "ping"}},
        ],
    }
    res = await client.put("/api/config", json=body)
    assert res.status_code == 200
    data = res.json()
    assert data["warnings"] == []
    assert data["effective"]["ble_device_name"] == "Renamed"
    assert data["effective"]["modes"][0]["name"] == "Only"
    # live config hot-reloaded
    assert ctx.cm.config.ble_device_name == "Renamed"
    # and persisted to disk
    on_disk = json.loads(open(ctx.cm.path, encoding="utf-8").read())
    assert on_disk == body


async def test_put_legacy_rules_body_migrates_to_modes(client, ctx):
    # Legacy "rules" bodies are still accepted (written verbatim) but the
    # effective config the editor reads back is the migrated modes list.
    body = {
        "ble_device_name": "Legacy",
        "rules": [
            {"name": "Only", "short_press": {"action": "log", "event": "ping"}},
        ],
    }
    res = await client.put("/api/config", json=body)
    assert res.status_code == 200
    data = res.json()
    assert data["warnings"] == []
    assert data["effective"]["modes"][0]["name"] == "Only"
    assert data["effective"]["modes"][0]["template"] == "actions"
    assert "rules" not in data["effective"]
    on_disk = json.loads(open(ctx.cm.path, encoding="utf-8").read())
    assert on_disk == body  # raw body written verbatim


async def test_put_config_reports_fallback_warnings(client, ctx):
    res = await client.put("/api/config", json={"prefer_remote": "yes"})
    data = res.json()
    assert data["warnings"]  # wrong type -> warning returned to the editor
    assert ctx.cm.config.prefer_remote is True  # fell back to default


async def test_put_config_rejects_non_object(client):
    res = await client.put("/api/config", json=[1, 2, 3])
    assert res.status_code == 422


async def test_effective_config_roundtrips_cleanly(client):
    effective = (await client.get("/api/config")).json()["effective"]
    res = await client.put("/api/config", json=effective)
    data = res.json()
    assert data["warnings"] == []
    assert data["effective"] == effective


async def test_validate_endpoint_does_not_write(client, ctx):
    before = open(ctx.cm.path, encoding="utf-8").read()
    body = {
        "ble_device_name": "Preview",
        "modes": [{"name": "Only", "template": "actions", "activation": {"type": "always"},
                   "short_press": {"action": "log", "event": "ping"}}],
    }
    res = await client.post("/api/config/validate", json=body)
    assert res.status_code == 200
    data = res.json()
    assert data["warnings"] == []
    assert data["effective"]["ble_device_name"] == "Preview"
    # dry run: neither the live config nor the file changed
    assert ctx.cm.config.ble_device_name == "TestBtn"
    assert open(ctx.cm.path, encoding="utf-8").read() == before


async def test_validate_endpoint_reports_warnings(client, ctx):
    res = await client.post("/api/config/validate", json={"web_port": "nope"})
    data = res.json()
    assert data["warnings"]
    assert data["effective"]["web_port"] == 8080  # fell back to default


async def test_config_menu_assets_served_as_javascript(client):
    res = await client.get("/static/menu.js")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/javascript")
    assert "ConfigMenu" in res.text


async def test_config_reload_endpoint(client, ctx):
    with open(ctx.cm.path, "w", encoding="utf-8") as f:
        json.dump({"ble_device_name": "EditedViaSSH"}, f)
    res = await client.post("/api/config/reload")
    assert res.status_code == 200
    assert ctx.cm.config.ble_device_name == "EditedViaSSH"


async def test_trigger_queues_event(client, ctx):
    res = await client.post("/api/trigger/double_tap")
    assert res.status_code == 200
    assert ctx.trigger_queue.get_nowait() is TriggerType.DOUBLE_TAP


async def test_trigger_unknown_404(client, ctx):
    res = await client.post("/api/trigger/quadruple_tap")
    assert res.status_code == 404
    assert ctx.trigger_queue.empty()


async def test_events_endpoint(client, ctx):
    ctx.store.log_event("meds_taken")
    ctx.store.toggle_timer("focus")
    rows = (await client.get("/api/events")).json()
    assert [r["name"] for r in rows] == ["focus", "meds_taken"]  # newest first
    assert rows[1]["kind"] == "log"


async def test_status_includes_dev_fields(client, ctx):
    ctx.status.led_state = "THINKING"
    data = (await client.get("/api/status")).json()
    assert data["mock"] is True
    assert data["clock_override"] is False
    assert data["led_state"] == "THINKING"
    assert data["sound_seq"] == 0
    datetime.fromisoformat(data["now"])  # parseable


async def test_clock_set_hhmm_and_clear(client, ctx):
    res = await client.post("/api/dev/clock", json={"time": "06:30"})
    data = res.json()
    assert data["clock_override"] is True
    now = ctx.clock.now()
    assert (now.hour, now.minute) == (6, 30)

    res = await client.post("/api/dev/clock", json={"clear": True})
    assert res.json()["clock_override"] is False
    assert abs((ctx.clock.now() - datetime.now()).total_seconds()) < 1


async def test_clock_set_full_datetime(client, ctx):
    target = datetime.now() + timedelta(days=3)
    await client.post("/api/dev/clock", json={"time": target.isoformat(timespec="minutes")})
    assert abs((ctx.clock.now() - target).total_seconds()) < 60


async def test_clock_bad_input_422(client, ctx):
    assert (await client.post("/api/dev/clock", json={"time": "6:30pm"})).status_code == 422
    assert (await client.post("/api/dev/clock", json={})).status_code == 422
    assert ctx.clock.overridden is False


async def test_dev_sound_serves_wav(client):
    res = await client.get("/api/dev/sound/ack")
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"
    assert res.content[:4] == b"RIFF"


async def test_dev_sound_unknown_404(client):
    assert (await client.get("/api/dev/sound/kazoo")).status_code == 404
