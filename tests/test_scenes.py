"""Scenes: the merge, the files, and the CLI.

The merge half is pure, so most of this is plain dict-in/dict-out. The rest
uses tmp_path because the point of the feature is files you can edit with
nothing running.
"""

from __future__ import annotations

import json

import pytest

from aibutton import scenes
from aibutton.config import ConfigManager, as_dict, load_config, load_config_full, parse_config


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def a_mode(name="From base", event="base_event"):
    return {
        "name": name,
        "template": "actions",
        "activation": {"type": "always"},
        "short_press": {"action": "log", "event": event},
    }


def a_config(tmp_path, active="focus", **extra):
    """A base config pointing at a scenes dir next to it."""
    payload = {
        "web_port": 8080,
        "database_path": "data/events.db",
        "modes": [a_mode()],
        "scenes": {"dir": "scenes", "active": active},
        **extra,
    }
    if active is None:
        payload["scenes"] = {"dir": "scenes"}
    return write(tmp_path / "config.json", payload)


# --- the merge is pure --------------------------------------------------

def test_scene_keys_win_and_unmentioned_keys_are_inherited():
    base = {"web_port": 8080, "modes": [a_mode()], "sounds_enabled": True}
    scene = {"modes": [a_mode("From scene", "scene_event")]}

    merged = scenes.merge(base, scene)

    assert merged["modes"][0]["name"] == "From scene"
    assert merged["web_port"] == 8080  # untouched by the scene
    assert merged["sounds_enabled"] is True


def test_merge_does_not_mutate_either_input():
    base = {"modes": [a_mode()]}
    scene = {"modes": []}

    scenes.merge(base, scene)

    assert base["modes"] and scene["modes"] == []


def test_a_scene_cannot_repoint_the_active_scene():
    """The one key that would let loading a scene change which scene loads."""
    base = {"scenes": {"dir": "scenes", "active": "focus"}}

    merged = scenes.merge(base, {"scenes": {"active": "something-else"}})

    assert merged["scenes"]["active"] == "focus"


def test_the_scenes_display_name_is_not_config():
    """`name` labels the picker; leaking it into the config would trip
    parse_config's unknown-key warning on every load."""
    merged = scenes.merge({}, {"name": "Focus", "web_port": 9000})

    assert "name" not in merged
    assert merged["web_port"] == 9000


# --- ids are containment, not style -------------------------------------

@pytest.mark.parametrize("bad", [
    "../secrets", "a/b", "a\\b", "C:evil", ".hidden", "", ".", "..", None, 7,
])
def test_unsafe_ids_are_refused(bad):
    assert not scenes.safe_id(bad)


@pytest.mark.parametrize("good", ["focus", "My Focus", "ab-test-b", "kitchen_2"])
def test_hand_named_scenes_are_usable(good):
    """A file someone made in Explorer is a valid scene; insisting on slugs
    would punish the offline editing this exists for."""
    assert scenes.safe_id(good)


def test_path_for_refuses_to_climb_out(tmp_path):
    settings = scenes.SceneSettings(dir="scenes", active="x")
    assert scenes.path_for(str(tmp_path / "config.json"), settings, "../../etc/passwd") is None


def test_scenes_dir_is_relative_to_the_config_not_the_cwd(tmp_path):
    settings = scenes.SceneSettings(dir="scenes")
    resolved = scenes.dir_for(str(tmp_path / "sub" / "config.json"), settings)
    assert resolved == (tmp_path / "sub" / "scenes").resolve()


@pytest.mark.parametrize("name,expected", [
    ("Deep Focus", "deep-focus"), ("A/B test!", "a-b-test"), ("", "scene"), ("   ", "scene"),
])
def test_slugify(name, expected):
    assert scenes.slugify(name) == expected


def test_unique_id_avoids_overwriting_a_scene():
    assert scenes.unique_id({"focus", "focus-2"}, "focus") == "focus-3"


# --- loading ------------------------------------------------------------

def test_the_active_scene_replaces_the_base_modes(tmp_path):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {
        "name": "Focus", "modes": [a_mode("Focus mode", "focus_event")],
    })

    loaded = load_config_full(str(config))

    assert [m.name for m in loaded.config.modes] == ["Focus mode"]
    assert loaded.scene_id == "focus"
    assert loaded.scene_error == ""
    assert loaded.config.web_port == 8080  # still the base's


def test_a_partial_scene_inherits_the_base_palette(tmp_path):
    """Changing behaviour while holding appearance constant - the A/B case."""
    config = a_config(tmp_path, led_palette={"IDLE": {"style": "solid", "color": "#123456"}})
    write(tmp_path / "scenes" / "focus.json", {"modes": [a_mode("Focus mode")]})

    cfg = load_config(str(config))

    assert cfg.led_palette["IDLE"].color == "#123456"


def test_no_scenes_block_is_todays_behaviour(tmp_path):
    config = write(tmp_path / "config.json", {"modes": [a_mode("Only mode")]})

    loaded = load_config_full(str(config))

    assert [m.name for m in loaded.config.modes] == ["Only mode"]
    assert loaded.scene_id is None
    assert loaded.config.scenes.active is None


def test_a_missing_scene_runs_the_base_config_and_says_so(tmp_path):
    config = a_config(tmp_path, active="gone")

    loaded = load_config_full(str(config))

    assert [m.name for m in loaded.config.modes] == ["From base"]
    assert loaded.scene_id is None
    assert "gone" in loaded.scene_error


def test_a_corrupt_scene_never_crashes_the_service(tmp_path):
    config = a_config(tmp_path)
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "focus.json").write_text("{ not json", encoding="utf-8")

    loaded = load_config_full(str(config))

    assert [m.name for m in loaded.config.modes] == ["From base"]
    assert loaded.scene_error


def test_a_scene_with_a_broken_mode_still_falls_back_per_key(tmp_path):
    """The scene goes through the same parser, so one bad mode is dropped
    rather than costing you the whole scene."""
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {
        "modes": [a_mode("Good"), {"name": "Bad", "template": "nonsense"}],
    })

    cfg = load_config(str(config))

    assert [m.name for m in cfg.modes] == ["Good"]


def test_scene_settings_round_trip_through_as_dict(tmp_path):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {"modes": [a_mode()]})

    cfg = load_config(str(config))
    again = parse_config(as_dict(cfg))

    assert again.scenes == cfg.scenes == scenes.SceneSettings(dir="scenes", active="focus")


def test_a_bad_active_pointer_costs_the_scene_not_the_config(tmp_path):
    config = write(tmp_path / "config.json", {
        "modes": [a_mode("Still here")], "scenes": {"active": "../escape"},
    })

    cfg = load_config(str(config))

    assert [m.name for m in cfg.modes] == ["Still here"]
    assert cfg.scenes.active is None


# --- listing and switching ----------------------------------------------

def test_listing_names_scenes_and_counts_their_modes(tmp_path):
    write(tmp_path / "scenes" / "focus.json", {"name": "Deep Focus", "modes": [a_mode(), a_mode()]})
    write(tmp_path / "scenes" / "kitchen.json", {"modes": []})

    entries = {i.id: i for i in scenes.list_scenes(tmp_path / "scenes")}

    assert entries["focus"].name == "Deep Focus"
    assert entries["focus"].mode_count == 2
    assert entries["kitchen"].name == "kitchen"  # falls back to the file stem
    assert entries["kitchen"].mode_count == 0


def test_a_broken_scene_is_listed_with_its_error_not_hidden(tmp_path):
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "typo.json").write_text("{,}", encoding="utf-8")

    [info] = scenes.list_scenes(tmp_path / "scenes")

    assert info.id == "typo" and info.error


def test_listing_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert scenes.list_scenes(tmp_path / "nope") == []


def test_switching_scenes_leaves_every_other_key_alone(tmp_path):
    config = a_config(tmp_path, active="focus", ble_device_name="Custom")
    write(tmp_path / "scenes" / "kitchen.json", {"modes": [a_mode("Kitchen")]})

    scenes.set_active(str(config), "kitchen")

    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw["scenes"]["active"] == "kitchen"
    assert raw["ble_device_name"] == "Custom"
    assert raw["web_port"] == 8080
    assert load_config(str(config)).modes[0].name == "Kitchen"


def test_switching_to_no_scene_runs_the_base_config(tmp_path):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {"modes": [a_mode("Focus mode")]})

    scenes.set_active(str(config), None)

    assert load_config(str(config)).modes[0].name == "From base"


def test_switching_refuses_to_overwrite_an_unreadable_config(tmp_path):
    """Replacing a config you can still fix by hand with a two-key stub is a
    worse outcome than refusing the switch."""
    config = tmp_path / "config.json"
    config.write_text("{ broken", encoding="utf-8")

    with pytest.raises(OSError):
        scenes.set_active(str(config), "focus")

    assert config.read_text(encoding="utf-8") == "{ broken"


def test_config_manager_reload_picks_up_a_switch(tmp_path):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {"modes": [a_mode("Focus mode")]})
    write(tmp_path / "scenes" / "kitchen.json", {"modes": [a_mode("Kitchen")]})
    cm = ConfigManager(str(config))
    assert cm.config.modes[0].name == "Focus mode"
    assert cm.write_path == str(tmp_path / "scenes" / "focus.json")

    scenes.set_active(str(config), "kitchen")
    cm.reload()

    assert cm.config.modes[0].name == "Kitchen"
    assert cm.loaded.scene_id == "kitchen"


def test_edits_go_to_the_scene_file_when_one_is_active(tmp_path):
    """The property that keeps two files from holding two copies of the same
    modes list: contents are written to the scene, the pointer to config.json."""
    config = a_config(tmp_path, active=None)
    cm = ConfigManager(str(config))

    assert cm.write_path == str(config)


# --- the offline CLI ----------------------------------------------------

def test_cli_check_validates_a_scene_with_nothing_running(tmp_path, capsys):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {"modes": [a_mode("Focus mode")]})

    code = scenes._cli(["--config", str(config), "check", "focus"])

    assert code == 0
    assert "ok" in capsys.readouterr().out


def test_cli_check_reports_the_real_parser_warnings(tmp_path, capsys):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {
        "modes": [a_mode("Good"), {"name": "Bad", "template": "nonsense"}],
    })

    code = scenes._cli(["--config", str(config), "check", "focus"])

    assert code == 1
    assert "nonsense" in capsys.readouterr().out


def test_cli_list_marks_the_active_scene(tmp_path, capsys):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "focus.json", {"name": "Deep Focus", "modes": [a_mode()]})
    write(tmp_path / "scenes" / "kitchen.json", {"modes": [a_mode()]})

    scenes._cli(["--config", str(config), "list"])

    out = capsys.readouterr().out
    assert "* focus" in out and "Deep Focus" in out
    assert "  kitchen" in out


def test_cli_activate_switches_and_refuses_a_missing_scene(tmp_path, capsys):
    config = a_config(tmp_path)
    write(tmp_path / "scenes" / "kitchen.json", {"modes": [a_mode("Kitchen")]})

    assert scenes._cli(["--config", str(config), "activate", "nope"]) == 2
    assert scenes._cli(["--config", str(config), "activate", "kitchen"]) == 0
    assert load_config(str(config)).modes[0].name == "Kitchen"
