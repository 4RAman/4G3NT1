import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from aibutton.audio import ToneLibrary
from aibutton.config import ConfigManager
from aibutton.device import LED_STYLES, LEDState, MockDevice, TriggerType
from aibutton.main import Clock, DeviceStatus
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app


@pytest.fixture
def ctx(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"ble_device_name": "TestBtn"}), encoding="utf-8")
    store = EventStore(str(tmp_path / "events.db"))
    tones = ToneLibrary()
    context = WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        device=MockDevice(),
        clock=Clock(),
        tones=tones,
    )
    yield context
    store.close()
    tones.close()


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
    assert data["mode_count"] == 1  # defaults
    assert data["last_trigger"] == "short_press"
    assert data["uptime_s"] >= 0


async def test_get_config_returns_raw_and_effective(client):
    data = (await client.get("/api/config")).json()
    assert data["raw"] == {"ble_device_name": "TestBtn"}
    assert data["effective"]["ble_device_name"] == "TestBtn"
    assert data["effective"]["sounds_enabled"] is True  # default filled in
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
    res = await client.put("/api/config", json={"sounds_enabled": "yes"})
    data = res.json()
    assert data["warnings"]  # wrong type -> warning returned to the editor
    assert ctx.cm.config.sounds_enabled is True  # fell back to default


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


async def test_status_reports_which_mode_answers_each_gesture(client, ctx):
    # What the editor's "active now" mark reads. It has to be the real
    # resolution, so this asserts the case that makes resolution non-obvious:
    # a time-scoped mode overriding one gesture while Default keeps the rest.
    await client.put("/api/config", json={
        "modes": [
            {"name": "Morning", "template": "actions",
             "activation": {"type": "window", "between": ["05:00", "07:00"]},
             "short_press": {"action": "log", "event": "morning"}},
            {"name": "Default", "template": "actions",
             "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "ping"},
             "long_press": {"action": "log", "event": "held"}},
        ],
    })

    ctx.clock.set(datetime.now().replace(hour=6, minute=0))
    active = (await client.get("/api/status")).json()["active_modes"]
    assert active["short_press"] == "Morning"  # the window wins
    assert active["long_press"] == "Default"   # which it does not define
    assert active["double_tap"] is None        # nothing binds it

    ctx.clock.set(datetime.now().replace(hour=12, minute=0))
    active = (await client.get("/api/status")).json()["active_modes"]
    assert active["short_press"] == "Default"  # outside the window


# --- the editor's tables mirror the device's ---------------------------
#
# schema.js declares what the Lights editor offers, and there is no JS test
# runner here, so these read the source the way test_protocol.py reads the
# firmware: a state or style the device has but the editor never lists is
# silently uneditable, which is how the Pomodoro's WORKING and RESTING
# colours went missing for a release.

_SCHEMA_JS = Path(__file__).resolve().parents[1] / "aibutton/web/static/schema.js"


def _descriptor_values(name: str, field: str) -> set[str]:
    """The `field` of every object literal in `export const <name> = [...]`."""
    source = _SCHEMA_JS.read_text(encoding="utf-8")
    block = re.search(rf"export const {name} = \[(.*?)\n\];", source, re.S)
    assert block, f"{name} is not an exported array literal in schema.js"
    return set(re.findall(rf"\b{field}: '([^']+)'", block.group(1)))


def test_lights_editor_offers_every_led_state():
    assert _descriptor_values("LED_STATES", "key") == {s.value for s in LEDState}


def test_mode_editor_offers_every_gesture():
    """The other mirrored table TODO 28 is about: a TriggerType with no entry
    here is a gesture nothing in the editor could ever bind, the same failure
    mode as a missing LED state above."""
    assert _descriptor_values("GESTURES", "key") == {t.value for t in TriggerType}


def test_lights_editor_offers_every_led_style():
    assert _descriptor_values("LED_STYLES", "type") == set(LED_STYLES)


def test_every_template_claims_the_same_led_states_on_both_sides():
    """Which states a mode owns decides two things that must agree: which
    pickers the mode editor shows, and which references the Python parser will
    accept. Drift here means the editor offers a look the parser then drops."""
    from aibutton.config import MODE_LED_STATES

    source = _SCHEMA_JS.read_text(encoding="utf-8")
    pairs = re.findall(r"type: '(\w+)',\s*\n\s*ledStates: \[([^\]]*)\]", source)
    from_js = {
        name: tuple(re.findall(r"'([^']+)'", states)) for name, states in pairs
    }
    assert from_js == {name: tuple(v) for name, v in MODE_LED_STATES.items()}


async def test_config_reload_endpoint(client, ctx):
    with open(ctx.cm.path, "w", encoding="utf-8") as f:
        json.dump({"ble_device_name": "EditedViaSSH"}, f)
    res = await client.post("/api/config/reload")
    assert res.status_code == 200
    assert ctx.cm.config.ble_device_name == "EditedViaSSH"


async def test_trigger_presses_the_device(client, ctx):
    res = await client.post("/api/trigger/double_tap")
    assert res.status_code == 200
    assert ctx.device.events.get_nowait() is TriggerType.DOUBLE_TAP


async def test_trigger_unknown_404(client, ctx):
    res = await client.post("/api/trigger/quadruple_tap")
    assert res.status_code == 404
    assert ctx.device.events.empty()


async def test_events_endpoint(client, ctx):
    ctx.store.log_event("meds_taken", mode="Default")
    ctx.store.toggle_timer("focus")
    rows = (await client.get("/api/events")).json()
    assert [r["name"] for r in rows] == ["focus", "meds_taken"]  # newest first
    assert rows[1]["kind"] == "log"
    assert rows[1]["mode"] == "Default"
    assert rows[0]["mode"] is None


async def test_status_includes_dev_fields(client, ctx):
    ctx.status.led_state = "THINKING"
    data = (await client.get("/api/status")).json()
    assert data["mock"] is True  # a MockDevice is behind the seam
    assert data["clock_override"] is False
    assert data["led_state"] == "THINKING"
    assert data["sound_seq"] == 0
    datetime.fromisoformat(data["now"])  # parseable


async def test_test_bench_shows_a_look_without_saving_it(client, ctx):
    # The Lights tab's test bench. Its whole value is that it asserts a look
    # on the hardware and changes nothing else, so the config on disk and the
    # config in memory both have to come through untouched.
    before = json.loads(Path(ctx.cm.path).read_text(encoding="utf-8"))
    res = await client.post("/api/dev/led", json={
        "style": "solid", "color": "#ff0000", "state": "IDLE",
    })
    assert res.status_code == 200
    assert res.json()["effect"]["color"] == "#ff0000"
    assert ctx.device.led_effect.color == "#ff0000"
    assert ctx.device.led_state is LEDState.IDLE
    assert ctx.status.led_state == "IDLE"  # the dashboard renders from this
    assert json.loads(Path(ctx.cm.path).read_text(encoding="utf-8")) == before
    assert ctx.cm.config.led_palette["IDLE"].color != "#ff0000"  # nor in memory


async def test_test_bench_clear_drops_back_to_the_palette(client, ctx):
    # "Stop" has to remove the override rather than push a look that happens
    # to match the config - an effect left asserted would survive the next
    # palette edit and quietly misreport what the button is doing.
    await client.post("/api/dev/led", json={"style": "solid", "color": "#ff0000"})
    res = await client.post("/api/dev/led", json={"clear": True})
    assert res.status_code == 200
    assert res.json()["effect"] is None
    assert ctx.device.led_effect is None
    assert ctx.status.led_effect is None


async def test_test_bench_validates_like_the_config_does(client, ctx):
    # One parser: a colour the editor would reject on Save is rejected the
    # same way here, and the caller is told what it actually got. A bench
    # that silently showed something else would be untrustworthy exactly when
    # it matters.
    res = await client.post("/api/dev/led", json={"style": "solid", "color": "not-a-colour"})
    assert res.status_code == 200
    assert res.json()["warnings"]
    assert res.json()["effect"]["color"] != "not-a-colour"


async def test_test_bench_rejects_an_unknown_state(client):
    res = await client.post("/api/dev/led", json={"state": "NONSENSE"})
    assert res.status_code == 422


async def test_stop_endpoint_asks_the_run_loop_to_shut_down(client, ctx):
    # The control panel's only polite way to stop the service on Windows:
    # SIGTERM is never delivered between processes there, and a console
    # control event needs a console a tray app does not have.
    asked = []
    ctx.on_stop = lambda: asked.append(True)
    res = await client.post("/api/service/stop")
    assert res.status_code == 200
    assert res.json() == {"stopping": True}
    assert asked == [True]


async def test_stop_endpoint_refuses_when_nothing_can_act_on_it(client):
    # Embedded/test setups pass no hook; saying so beats reporting a
    # shutdown that was never going to happen.
    assert (await client.post("/api/service/stop")).status_code == 503


async def test_status_reports_a_degraded_event_log(client, ctx):
    # An empty Events tab has two very different causes - nothing logged yet,
    # and a log that isn't being kept because the database wouldn't open. The
    # button keeps working either way, so the UI has to be able to tell them
    # apart rather than show an innocent-looking empty table.
    assert (await client.get("/api/status")).json()["store_degraded"] is False
    ctx.store.degraded = True
    assert (await client.get("/api/status")).json()["store_degraded"] is True


async def test_status_led_palette_reflects_the_device_not_the_config(client, ctx):
    # A takeover mode (the metronome) can push a live palette override that
    # briefly disagrees with cfg.led_palette; the virtual device panel has to
    # render what the device was actually sent, or it lies about the LED.
    from dataclasses import replace

    live = dict(ctx.cm.config.led_palette)
    live["IDLE"] = replace(live["IDLE"], period_s=0.123)
    ctx.device.set_palette(live)

    data = (await client.get("/api/status")).json()
    assert data["led_palette"]["IDLE"]["period_s"] == 0.123
    assert ctx.cm.config.led_palette["IDLE"].period_s != 0.123  # config untouched


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


# --- the browser's own sound, and the integrations catalogue ----------------

_INDEX_HTML = Path(__file__).resolve().parents[1] / "aibutton/web/index.html"


def test_every_sound_preview_button_names_a_real_sound():
    """The preview row is a mirrored table like any other: a button naming a
    tone that does not exist would 404 silently, since playback deliberately
    swallows its own errors."""
    from aibutton.device import Sound

    names = set(re.findall(r"data-sound=\"([^\"]+)\"", _INDEX_HTML.read_text(encoding="utf-8")))
    assert names == {s.value for s in Sound}


def test_the_page_plays_sound_outside_the_mock_only_branch():
    """The point of the change: hearing what the buzzer just played is most
    useful when the buzzer is real and in another room. If playSound() ends up
    back inside `if (d.mock)`, this is the test that says so."""
    source = _INDEX_HTML.read_text(encoding="utf-8")
    mock_branch = source.index("virtual device panel (mock mode only)")
    play_call = source.index("playSound(d.last_sound)")
    closing = source.index("soundSeq = d.sound_seq;")
    assert mock_branch < play_call < closing
    # ...and the call sits after the mock block has been closed off.
    assert "if (d.last_sound) $('#vsound')" in source[mock_branch:play_call]


def test_every_integration_is_a_usable_webhook_template():
    source = _SCHEMA_JS.read_text(encoding="utf-8")
    start = source.index("export const INTEGRATIONS")
    block = source[start:source.index("\n];", start)]
    entries = re.findall(r"\bid: '([^']+)'", block)
    urls = re.findall(r"\burl: '([^']+)'", block)
    labels = re.findall(r"\blabel: '([^']+)'", block)
    assert len(entries) == len(urls) == len(labels) >= 6
    assert len(set(entries)) == len(entries), "integration ids must be unique"
    for url in urls:
        assert url.startswith(("http://", "https://")), url
        # Every template must be obviously unfinished: one that looked like a
        # working URL would be pasted into a mode and quietly POST nowhere.
        assert "YOUR_" in url or "EVENT_NAME" in url or "REGION" in url, url


def test_the_integration_picker_is_an_inserter_not_a_stored_field():
    """`integration` is deliberately unknown to the parser, so it is dropped on
    save. If it ever becomes a real config key, this test should be the thing
    that makes someone argue for it."""
    from aibutton.config import WebhookAction, parse_config

    cfg = parse_config({"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": {"action": "webhook", "url": "https://example.test/x",
                        "integration": "slack"},
    }]})
    action = next(m for m in cfg.modes if m.name == "Desk").behavior.actions["short_press"]
    assert isinstance(action, WebhookAction)
    assert not hasattr(action, "integration")
