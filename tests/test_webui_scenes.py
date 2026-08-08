"""The scene endpoints, over the real app.

Only the config/scene routes are exercised, so the device, store, clock and
tone library are left as None: none of these routes touch them, and building
real ones would make this a test of the whole service instead of the routes.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from aibutton.config import AppConfig, ConfigManager
from aibutton.webui import WebContext, create_app


def a_mode(name, event="an_event"):
    return {
        "name": name,
        "template": "actions",
        "activation": {"type": "always"},
        "short_press": {"action": "log", "event": event},
    }


@pytest.fixture
def client(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "web_port": 8080,
        "modes": [a_mode("Base mode", "base_event")],
        "scenes": {"dir": "scenes", "active": "focus"},
    }), encoding="utf-8")
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir()
    (scenes_dir / "focus.json").write_text(json.dumps({
        "name": "Deep Focus", "modes": [a_mode("Focus mode", "focus_event")],
    }), encoding="utf-8")
    (scenes_dir / "kitchen.json").write_text(json.dumps({
        "name": "Kitchen", "modes": [a_mode("Kitchen mode", "kitchen_event")],
    }), encoding="utf-8")

    cm = ConfigManager(str(config))
    ctx = WebContext(
        cm=cm, store=None, status=None, device=None, clock=None, tones=None,
        startup_config=cm.config,
    )
    with TestClient(create_app(ctx)) as c:
        c.config_path = config
        c.scenes_dir = scenes_dir
        c.ctx = ctx
        yield c


def test_listing_reports_the_active_scene_and_its_siblings(client):
    body = client.get("/api/scenes").json()

    assert body["active"] == "focus"
    assert {s["id"] for s in body["scenes"]} == {"focus", "kitchen"}
    assert next(s for s in body["scenes"] if s["id"] == "focus")["name"] == "Deep Focus"
    assert body["needs_restart"] == []


def test_activating_switches_the_running_config(client):
    body = client.post("/api/scenes/kitchen/activate").json()

    assert body["active"] == "kitchen"
    assert [m["name"] for m in body["effective"]["modes"]] == ["Kitchen mode"]
    assert client.ctx.cm.config.modes[0].name == "Kitchen mode"


def test_activating_none_runs_the_base_config(client):
    body = client.post("/api/scenes/none/activate").json()

    assert body["active"] is None
    assert [m["name"] for m in body["effective"]["modes"]] == ["Base mode"]


def test_activating_a_missing_scene_is_a_404_and_changes_nothing(client):
    assert client.post("/api/scenes/ghost/activate").status_code == 404
    assert client.ctx.cm.config.modes[0].name == "Focus mode"


def test_a_scene_id_cannot_climb_out_of_the_scenes_directory(client):
    assert client.post("/api/scenes/..%2F..%2Fevil/activate").status_code in (400, 404)
    assert client.delete("/api/scenes/..%2F..%2Fconfig").status_code in (400, 404)


def test_saving_the_config_writes_the_scene_not_config_json(client):
    """The property the whole design turns on: config.json keeps the pointer,
    the scene keeps the modes, and nobody holds two copies."""
    edited = client.get("/api/config").json()["effective"]
    edited["modes"] = [a_mode("Edited in the scene")]

    body = client.put("/api/config", json=edited).json()

    assert body["write_path"].endswith("focus.json")
    scene = json.loads((client.scenes_dir / "focus.json").read_text(encoding="utf-8"))
    assert [m["name"] for m in scene["modes"]] == ["Edited in the scene"]
    assert scene["name"] == "Deep Focus"  # the label survives an edit
    assert "scenes" not in scene  # a scene never carries the pointer
    base = json.loads(client.config_path.read_text(encoding="utf-8"))
    assert [m["name"] for m in base["modes"]] == ["Base mode"]


def test_edits_survive_switching_away_and_back(client):
    edited = client.get("/api/config").json()["effective"]
    edited["modes"] = [a_mode("Edited in the scene")]
    client.put("/api/config", json=edited)

    client.post("/api/scenes/kitchen/activate")
    body = client.post("/api/scenes/focus/activate").json()

    assert [m["name"] for m in body["effective"]["modes"]] == ["Edited in the scene"]


def test_saving_with_no_scene_active_writes_config_json(client):
    client.post("/api/scenes/none/activate")
    edited = client.get("/api/config").json()["effective"]
    edited["modes"] = [a_mode("Straight to the base")]

    body = client.put("/api/config", json=edited).json()

    assert body["write_path"] == str(client.config_path)
    base = json.loads(client.config_path.read_text(encoding="utf-8"))
    assert [m["name"] for m in base["modes"]] == ["Straight to the base"]


def test_creating_a_scene_snapshots_the_current_config_and_switches_to_it(client):
    body = client.post("/api/scenes", json={"name": "A/B test B"}).json()

    assert body["id"] == "a-b-test-b"
    assert body["active"] == "a-b-test-b"
    saved = json.loads((client.scenes_dir / "a-b-test-b.json").read_text(encoding="utf-8"))
    assert saved["name"] == "A/B test B"
    assert [m["name"] for m in saved["modes"]] == ["Focus mode"]  # what was running


def test_creating_a_scene_never_overwrites_one(client):
    """`focus.json` is already there, so two more "Focus" scenes have to land
    somewhere else - ids are filenames, and a collision would eat a scene."""
    first = client.post("/api/scenes", json={"name": "Focus", "activate": False}).json()
    second = client.post("/api/scenes", json={"name": "Focus", "activate": False}).json()

    assert [first["id"], second["id"]] == ["focus-2", "focus-3"]
    original = json.loads((client.scenes_dir / "focus.json").read_text(encoding="utf-8"))
    assert original["name"] == "Deep Focus"


def test_creating_without_activating_leaves_the_button_alone(client):
    client.post("/api/scenes", json={"name": "Later", "activate": False})

    assert client.ctx.cm.loaded.scene_id == "focus"


def test_a_scene_needs_a_name(client):
    assert client.post("/api/scenes", json={}).status_code == 422


def test_editing_an_inactive_scene_does_not_disturb_the_active_one(client):
    client.put("/api/scenes/kitchen", json={"config": {"modes": [a_mode("Rewritten")]}})

    assert client.ctx.cm.config.modes[0].name == "Focus mode"
    saved = json.loads((client.scenes_dir / "kitchen.json").read_text(encoding="utf-8"))
    assert [m["name"] for m in saved["modes"]] == ["Rewritten"]
    assert saved["name"] == "Kitchen"  # not clobbered by a config-only body


def test_deleting_the_active_scene_is_refused(client):
    response = client.delete("/api/scenes/focus")

    assert response.status_code == 409
    assert (client.scenes_dir / "focus.json").exists()


def test_deleting_an_inactive_scene_works(client):
    body = client.delete("/api/scenes/kitchen").json()

    assert not (client.scenes_dir / "kitchen.json").exists()
    assert {s["id"] for s in body["scenes"]} == {"focus"}


def test_a_scene_changing_a_startup_only_key_says_a_restart_is_needed(client):
    """The honest half of whole-config scenes: this reloads cleanly and then
    does nothing until the service restarts, so the API has to say so."""
    (client.scenes_dir / "kitchen.json").write_text(json.dumps({
        "name": "Kitchen", "web_port": 9999, "modes": [a_mode("Kitchen mode")],
    }), encoding="utf-8")

    body = client.post("/api/scenes/kitchen/activate").json()

    assert body["needs_restart"] == ["web_port"]


def test_a_scene_that_changes_nothing_startup_shaped_needs_no_restart(client):
    body = client.post("/api/scenes/kitchen/activate").json()

    assert body["needs_restart"] == []


def test_a_broken_scene_is_listed_and_the_base_config_runs(client):
    (client.scenes_dir / "focus.json").write_text("{ oops", encoding="utf-8")
    client.ctx.cm.reload()

    body = client.get("/api/scenes").json()

    assert body["configured"] == "focus"  # what config.json asks for
    assert body["active"] is None  # what is actually running
    assert body["error"]
    assert [m["name"] for m in body["effective"]["modes"]] == ["Base mode"]


def test_warnings_from_a_scene_reach_the_editor(client):
    body = client.put("/api/scenes/focus", json={
        "config": {"modes": [a_mode("Good"), {"name": "Bad", "template": "nonsense"}]},
    }).json()

    assert any("nonsense" in w for w in body["warnings"])


def test_needs_restart_is_empty_without_a_startup_snapshot(tmp_path):
    """Embedded callers and tests pass no snapshot; the answer is "nothing to
    compare", not a spurious restart prompt."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"modes": [a_mode("Only")]}), encoding="utf-8")
    ctx = WebContext(
        cm=ConfigManager(str(config)), store=None, status=None,
        device=None, clock=None, tones=None,
    )
    with TestClient(create_app(ctx)) as c:
        assert c.get("/api/scenes").json()["needs_restart"] == []
