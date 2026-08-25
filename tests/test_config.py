import json
from datetime import time

import pytest

from aibutton.config import (
    TRIGGER_TYPES,
    ActionsBehavior,
    AlarmBehavior,
    AlwaysActivation,
    AppConfig,
    ConfigManager,
    CounterBehavior,
    CountdownBehavior,
    EnterModeAction,
    LauncherBehavior,
    LedEffect,
    LogAction,
    ManualActivation,
    MetronomeBehavior,
    Mode,
    NamedAction,
    PomodoroBehavior,
    ReadoutAction,
    ScheduleActivation,
    StopwatchBehavior,
    TimerToggleAction,
    WebhookAction,
    WindowActivation,
    as_dict,
    bound_triggers,
    load_config,
    parse_config,
    parse_with_warnings,
)
from aibutton.sequencer import Sequence, Stop


def write(tmp_path, data) -> str:
    p = tmp_path / "config.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(p)


def test_missing_file_uses_defaults(tmp_path):
    cfg = load_config(str(tmp_path / "nope.json"))
    assert cfg == AppConfig()


def test_bad_json_uses_defaults(tmp_path):
    cfg = load_config(write(tmp_path, "{not json"))
    assert cfg == AppConfig()


def test_non_object_top_level_uses_defaults(tmp_path):
    cfg = load_config(write(tmp_path, "[1, 2]"))
    assert cfg == AppConfig()


def test_full_valid_v3_config(tmp_path):
    cfg = load_config(write(tmp_path, {
        "ble_device_name": "MyButton",
        "sounds_enabled": False,
        "database_path": "/var/lib/aibutton/events.db",
        "modes": [
            {
                "name": "Morning meds",
                "template": "actions",
                "activation": {"type": "window", "between": ["05:00", "07:00"],
                               "days": ["mon", "wed", "FRI"]},
                "double_tap": {"action": "log", "event": "meds_taken"},
            },
            {
                "name": "Workday",
                "template": "actions",
                "activation": {"type": "window", "between": ["09:00", "17:00"]},
                "short_press": {"action": "timer_toggle", "log_as": "deep_work"},
                "long_press": {"action": "webhook", "url": "https://hook.example/x",
                               "payload": {"note": "hi"}},
            },
            {
                "name": "Default",
                "template": "actions",
                "activation": {"type": "always"},
                "short_press": {"action": "enter_mode", "target": "Focus"},
            },
        ],
    }))
    assert cfg.ble_device_name == "MyButton"
    assert cfg.sounds_enabled is False
    assert cfg.database_path == "/var/lib/aibutton/events.db"

    meds, workday, default = cfg.modes
    assert meds.template == "actions"
    assert isinstance(meds.activation, WindowActivation)
    assert meds.activation.between == (time(5, 0), time(7, 0))
    assert meds.activation.days == frozenset({0, 2, 4})  # case-insensitive day names
    assert meds.behavior.actions["double_tap"] == LogAction(event="meds_taken")
    assert workday.behavior.actions["short_press"] == TimerToggleAction(log_as="deep_work")
    assert workday.behavior.actions["long_press"] == WebhookAction(
        url="https://hook.example/x", payload={"note": "hi"}
    )
    assert workday.activation.days is None
    assert isinstance(default.activation, AlwaysActivation)
    assert default.behavior.actions["short_press"] == EnterModeAction(target="Focus")


def test_default_modes_when_empty(tmp_path):
    cfg = load_config(write(tmp_path, {"ble_device_name": "x"}))
    assert cfg.modes == AppConfig().modes
    assert cfg.modes[0].name == "Home"
    assert isinstance(cfg.modes[0].activation, AlwaysActivation)


# --- the ambient floor is a structural guarantee, not a stored flag (TODO 5) --

def test_default_modes_shape_is_home_plus_three_apps():
    """_default_modes() seeds Home (the ambient floor) plus the three apps its
    own bindings promise to reach - a from-scratch config.json has to be able
    to keep that promise the moment it exists."""
    home, launcher, pomodoro, stopwatch = AppConfig().modes

    assert home.name == "Home"
    assert home.template == "actions"
    assert isinstance(home.activation, AlwaysActivation)
    assert home.behavior.actions["short_press"] == LogAction(event="button_press")
    assert home.behavior.actions["double_tap"] == EnterModeAction(target="Launcher")
    assert home.behavior.actions["long_press"] == EnterModeAction(target="Pomodoro")

    assert (launcher.name, launcher.template) == ("Launcher", "launcher")
    assert isinstance(launcher.activation, ManualActivation)
    assert launcher.behavior == LauncherBehavior()

    assert (pomodoro.name, pomodoro.template) == ("Pomodoro", "pomodoro")
    assert isinstance(pomodoro.activation, ManualActivation)
    assert pomodoro.behavior == PomodoroBehavior()

    assert (stopwatch.name, stopwatch.template) == ("Stopwatch", "stopwatch")
    assert isinstance(stopwatch.activation, ManualActivation)
    assert stopwatch.behavior == StopwatchBehavior()


def test_default_modes_enter_mode_targets_resolve():
    # Home's double_tap/long_press name Launcher/Pomodoro by string - the
    # forward references EnterModeAction leaves for the runtime to resolve
    # (see EnterModeAction's docstring). A fresh config has to actually ship
    # modes by those names, or Home's own bindings would point nowhere.
    cfg = AppConfig()
    names = {m.name for m in cfg.modes}
    targets = {
        action.target
        for action in cfg.modes[0].behavior.actions.values()
        if isinstance(action, EnterModeAction)
    }
    assert targets == {"Launcher", "Pomodoro"}
    assert targets <= names


def test_no_ambient_always_mode_seeds_home_with_a_warning():
    # Nothing but a manual-activation takeover mode: no ambient mode of any
    # kind, let alone an Always one. _ensure_ambient_always has to notice and
    # seed the floor back in, appended last so it never shadows a mode
    # someone actually configured.
    cfg, warnings = parse_with_warnings({
        "modes": [
            {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"}},
        ],
    })
    assert [m.name for m in cfg.modes] == ["Focus", "Home"]
    assert isinstance(cfg.modes[-1].activation, AlwaysActivation)
    assert cfg.modes[-1].template == "actions"
    assert any("no ambient mode has an Always activation" in w for w in warnings)


def test_only_always_mode_edited_to_manual_still_gets_a_floor():
    # Simulates a hand-edited config.json rather than the editor's refusal:
    # the floor mode's activation was changed to "manual" directly in the raw
    # dict. "actions" does not allow manual activation (_ALLOWED_ACTIVATIONS),
    # so the mode is dropped at parse time for the mismatch - and with the
    # other mode in this config being a manual takeover, nothing ambient is
    # left. The guarantee still holds: Home comes back.
    cfg, warnings = parse_with_warnings({
        "modes": [
            {"name": "Was Home", "template": "actions", "activation": {"type": "manual"},
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"}},
        ],
    })
    names = [m.name for m in cfg.modes]
    assert "Was Home" not in names  # skipped: actions can't be manual
    assert "Home" in names
    home = cfg.modes[names.index("Home")]
    assert isinstance(home.activation, AlwaysActivation)
    assert any("no ambient mode has an Always activation" in w for w in warnings)


# --- migration: legacy v0.2 "rules" -> modes ----------------------------

def test_legacy_rules_migrate_to_actions_modes(tmp_path):
    cfg = load_config(write(tmp_path, {
        "rules": [
            {
                "name": "Morning meds",
                "between": ["05:00", "07:00"],
                "days": ["mon", "wed", "fri"],
                "unless_logged_today": "meds_taken",
                "double_tap": {"action": "log", "event": "meds_taken"},
            },
            {
                "name": "Default",
                "short_press": {"action": "timer_toggle", "log_as": "focus"},
            },
        ],
    }))
    meds, default = cfg.modes
    assert meds.template == "actions"
    # had between/days -> window activation
    assert isinstance(meds.activation, WindowActivation)
    assert meds.activation.between == (time(5, 0), time(7, 0))
    assert meds.activation.days == frozenset({0, 2, 4})
    assert meds.behavior.unless_logged_today == "meds_taken"
    assert meds.behavior.actions["double_tap"] == LogAction(event="meds_taken")
    # no scope -> always activation
    assert isinstance(default.activation, AlwaysActivation)
    assert default.behavior.actions["short_press"] == TimerToggleAction(log_as="focus")


def test_legacy_rule_with_alarm_action_drops_gesture(tmp_path):
    # The removed v0.2 alarm action can't be migrated (no fire time); the
    # gesture is dropped. Remaining gestures still migrate.
    cfg = load_config(write(tmp_path, {
        "rules": [
            {
                "name": "Wake up",
                "short_press": {"action": "alarm", "message": "Wake up", "snooze_minutes": 9},
                "double_tap": {"action": "log", "event": "snoozed"},
            },
        ],
    }))
    mode = cfg.modes[0]
    assert mode.template == "actions"
    assert "short_press" not in mode.behavior.actions  # alarm action dropped
    assert mode.behavior.actions["double_tap"] == LogAction(event="snoozed")


def test_legacy_rule_only_alarm_action_skipped_falls_back(tmp_path):
    # A rule whose only gesture was an alarm action has nothing migratable
    # -> skipped; with no other rules we fall back to the default modes.
    cfg = load_config(write(tmp_path, {
        "rules": [
            {"name": "Wake up", "short_press": {"action": "alarm", "message": "Wake up"}},
        ],
    }))
    assert cfg.modes == AppConfig().modes


def test_mode_with_prompt_action_drops_the_gesture(tmp_path):
    # The prompt action went with the on-device AI. Like the removed alarm
    # action it is dropped, not silently mangled; other gestures survive.
    cfg = load_config(write(tmp_path, {
        "modes": [
            {
                "name": "Default",
                "template": "actions",
                "activation": {"type": "always"},
                "short_press": {"action": "prompt", "prompt": "tell me a fact"},
                "double_tap": {"action": "log", "event": "note"},
            },
        ],
    }))
    mode = cfg.modes[0]
    assert "short_press" not in mode.behavior.actions
    assert mode.behavior.actions == {"double_tap": LogAction(event="note")}


def test_legacy_commands_are_all_prompts_so_nothing_migrates(tmp_path):
    # v0.1 "commands" configs only ever held prompts, so with the AI gone
    # they migrate to nothing and the built-in defaults take over.
    cfg = load_config(write(tmp_path, {
        "commands": {
            "short_press": {"prompt": "p1", "label": "l1"},
            "double_tap": {"prompt": "p3", "label": "l3"},
        },
    }))
    assert cfg.modes == AppConfig().modes


def test_legacy_commands_with_current_actions_still_migrate(tmp_path):
    cfg = load_config(write(tmp_path, {
        "commands": {"short_press": {"action": "log", "event": "ping"}},
    }))
    assert len(cfg.modes) == 1
    mode = cfg.modes[0]
    assert mode.name == "Default"
    assert mode.template == "actions"
    assert isinstance(mode.activation, AlwaysActivation)
    assert mode.behavior.actions == {"short_press": LogAction(event="ping")}


def test_modes_take_precedence_over_legacy_rules(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "New", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "new"}},
        ],
        "rules": [
            {"name": "Old", "short_press": {"action": "log", "event": "old"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["New"]


# --- per-key fallback ---------------------------------------------------

def test_bad_key_falls_back_others_survive(tmp_path):
    cfg = load_config(write(tmp_path, {
        "sounds_enabled": "yes",   # wrong type -> default True
        "web_port": True,          # bool is not an int -> default
        "ble_device_name": "Kept",
    }))
    assert cfg.sounds_enabled is True
    assert cfg.web_port == 8080
    assert cfg.ble_device_name == "Kept"


def test_mode_with_bad_window_is_skipped_others_survive(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Broken", "template": "actions",
             "activation": {"type": "window", "between": ["5am", "7am"]},
             "double_tap": {"action": "log", "event": "x"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "x"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_mode_with_bad_days_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Broken", "template": "actions",
             "activation": {"type": "window", "days": ["monday"]},  # must be 3-letter
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_window_without_bounds_is_always(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Bare", "template": "actions", "activation": {"type": "window"},
             "short_press": {"action": "log", "event": "x"}},
        ],
    }))
    assert isinstance(cfg.modes[0].activation, AlwaysActivation)


def test_invalid_action_skipped_within_actions_mode(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {
                "name": "Mixed",
                "template": "actions",
                "activation": {"type": "always"},
                "short_press": {"action": "log", "event": "good"},
                "long_press": {"action": "webhook", "url": "ftp://nope"},   # bad scheme
                "double_tap": {"action": "teleport"},                       # unknown type
            },
        ],
    }))
    mode = cfg.modes[0]
    assert mode.behavior.actions == {"short_press": LogAction(event="good")}


def test_mode_with_no_valid_actions_skipped_and_empty_modes_fall_back(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [{"name": "Empty", "template": "actions",
                   "activation": {"type": "window", "between": ["05:00", "07:00"]}}],
    }))
    assert cfg.modes == AppConfig().modes  # defaults


def test_unknown_template_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Weird", "template": "stopwatch", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


# --- unless_logged_today ------------------------------------------------

def test_unless_logged_today_parsing(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {
                "name": "Reminder",
                "template": "actions",
                "activation": {"type": "always"},
                "unless_logged_today": "meds_taken",
                "short_press": {"action": "log", "event": "meds_taken"},
            },
        ],
    }))
    assert cfg.modes[0].behavior.unless_logged_today == "meds_taken"


def test_unless_logged_today_invalid_skips_mode(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Broken", "template": "actions", "activation": {"type": "always"},
             "unless_logged_today": "",
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


# --- alarm template -----------------------------------------------------

def test_alarm_mode_parses(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {
                "name": "Wake up",
                "template": "alarm",
                "activation": {"type": "schedule", "at": "07:00",
                               "days": ["mon", "tue", "wed", "thu", "fri"]},
                "message": "Good morning!",
                "label": "Wake up",
                "snooze_minutes": 9,
                "dismiss_event": "woke_up",
            },
        ],
    }))
    mode = cfg.modes[0]
    assert mode.template == "alarm"
    assert isinstance(mode.activation, ScheduleActivation)
    assert mode.activation.at == time(7, 0)
    assert mode.activation.days == frozenset({0, 1, 2, 3, 4})
    assert mode.behavior == AlarmBehavior(
        message="Good morning!", label="Wake up", snooze_minutes=9.0, dismiss_event="woke_up",
    )


def test_alarm_mode_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Bare", "template": "alarm", "activation": {"type": "schedule", "at": "06:00"}},
        ],
    }))
    mode = cfg.modes[0]
    assert mode.behavior == AlarmBehavior()
    assert mode.activation.days is None  # every day


def test_alarm_mode_bad_at_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Broken", "template": "alarm", "activation": {"type": "schedule", "at": "7am"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_alarm_invalid_snooze_falls_back_per_key(tmp_path):
    # Alarm fields fall back per-key (the mode survives) - unlike an actions
    # mode where a bad action is dropped from the gesture map.
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wake up", "template": "alarm",
             "activation": {"type": "schedule", "at": "07:00"},
             "snooze_minutes": -1, "message": "Up"},
        ],
    }))
    mode = cfg.modes[0]
    assert mode.behavior.snooze_minutes == 0  # default
    assert mode.behavior.message == "Up"      # kept


# --- template <-> activation mismatch -----------------------------------

def test_actions_with_schedule_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "actions",
             "activation": {"type": "schedule", "at": "07:00"},
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_alarm_with_always_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "alarm", "activation": {"type": "always"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_alarm_with_window_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "alarm",
             "activation": {"type": "window", "between": ["06:00", "07:00"]}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


# --- stopwatch + counter templates, manual activation -------------------

def test_stopwatch_mode_parses(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Focus", "template": "stopwatch",
             "activation": {"type": "manual"}, "log_as": "focus"},
        ],
    }))
    mode = cfg.modes[0]
    assert mode.template == "stopwatch"
    assert isinstance(mode.activation, ManualActivation)
    assert mode.behavior == StopwatchBehavior(log_as="focus")


def test_counter_mode_parses(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Water", "template": "counter",
             "activation": {"type": "manual"}, "event": "water"},
        ],
    }))
    mode = cfg.modes[0]
    assert mode.template == "counter"
    assert isinstance(mode.activation, ManualActivation)
    assert mode.behavior == CounterBehavior(event="water")


def test_stopwatch_counter_defaults_when_field_missing(tmp_path):
    # Both takeover modes are manual-activation, so an ambient Always mode is
    # added explicitly here - without one, _ensure_ambient_always would seed
    # "Home" as a third mode and this unpacking would fail on its own.
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"}},
            {"name": "Water", "template": "counter", "activation": {"type": "manual"}},
            {"name": "Base", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "x"}},
        ],
    }))
    sw, ct, _base = cfg.modes
    assert sw.behavior == StopwatchBehavior()  # log_as -> "stopwatch"
    assert ct.behavior == CounterBehavior()  # event -> "counter"


def test_stopwatch_bad_field_falls_back_per_key(tmp_path):
    # Like alarm fields (not like actions): a bad flat field falls back to the
    # default and the mode survives.
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Focus", "template": "stopwatch",
             "activation": {"type": "manual"}, "log_as": 123},
        ],
    }))
    assert cfg.modes[0].behavior == StopwatchBehavior()  # log_as -> "stopwatch"


def test_stopwatch_with_window_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "stopwatch",
             "activation": {"type": "window", "between": ["06:00", "07:00"]},
             "log_as": "focus"},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_counter_with_schedule_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "counter",
             "activation": {"type": "schedule", "at": "07:00"}, "event": "water"},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_metronome_mode_parses(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"}},
        ],
    }))
    mode = cfg.modes[0]
    assert mode.template == "metronome"
    assert isinstance(mode.activation, ManualActivation)
    assert mode.behavior == MetronomeBehavior()


def test_metronome_with_schedule_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "metronome",
             "activation": {"type": "schedule", "at": "07:00"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_alarm_with_manual_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "alarm", "activation": {"type": "manual"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


def test_actions_with_manual_is_skipped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Wrong", "template": "actions", "activation": {"type": "manual"},
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Good", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "y"}},
        ],
    }))
    assert [m.name for m in cfg.modes] == ["Good"]


# --- enter_mode action --------------------------------------------------

def test_enter_mode_action_parses(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "long_press": {"action": "enter_mode", "target": "Focus"}},
            {"name": "Focus", "template": "stopwatch",
             "activation": {"type": "manual"}, "log_as": "focus"},
        ],
    }))
    default = cfg.modes[0]
    assert default.behavior.actions["long_press"] == EnterModeAction(target="Focus")


def test_enter_mode_empty_target_is_dropped(tmp_path):
    # An invalid action is dropped from the gesture map like any other; the
    # remaining valid gestures keep the mode alive.
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "long_press": {"action": "enter_mode", "target": ""},
             "short_press": {"action": "log", "event": "x"}},
        ],
    }))
    mode = cfg.modes[0]
    assert "long_press" not in mode.behavior.actions
    assert mode.behavior.actions["short_press"] == LogAction(event="x")


def test_enter_mode_missing_target_is_dropped(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "long_press": {"action": "enter_mode"},  # no target key
             "short_press": {"action": "log", "event": "x"}},
        ],
    }))
    assert "long_press" not in cfg.modes[0].behavior.actions


def test_enter_mode_target_not_validated_at_parse_time(tmp_path):
    # Forward / dangling references are allowed at parse time; the runtime
    # handles a missing/non-takeover target gracefully.
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "Nonexistent"}},
        ],
    }))
    assert cfg.modes[0].behavior.actions["short_press"] == EnterModeAction(target="Nonexistent")


# --- round-trip ---------------------------------------------------------

def test_as_dict_roundtrips_actions_and_alarm(tmp_path):
    cfg = load_config(write(tmp_path, {
        "ble_device_name": "RT",
        "modes": [
            {"name": "Scoped", "template": "actions",
             "activation": {"type": "window", "between": ["22:00", "06:00"],
                            "days": ["sat", "sun"]},
             "double_tap": {"action": "webhook", "url": "https://h.example/x",
                            "payload": {"k": "v"}},
             "short_press": {"action": "timer_toggle", "log_as": "focus"}},
            {"name": "Meds", "template": "actions", "activation": {"type": "always"},
             "unless_logged_today": "meds_taken",
             "long_press": {"action": "log", "event": "meds_taken"}},
            {"name": "Wake up", "template": "alarm",
             "activation": {"type": "schedule", "at": "07:00", "days": ["mon", "fri"]},
             "message": "Wake up", "label": "WU", "snooze_minutes": 9, "dismiss_event": "woke_up"},
        ],
    }))
    dumped = as_dict(cfg)
    assert dumped["modes"][0]["activation"]["between"] == ["22:00", "06:00"]
    assert dumped["modes"][0]["activation"]["days"] == ["sat", "sun"]
    assert dumped["modes"][1]["unless_logged_today"] == "meds_taken"
    assert dumped["modes"][2]["template"] == "alarm"
    assert dumped["modes"][2]["activation"]["at"] == "07:00"
    assert parse_config(dumped) == cfg  # exact round-trip


def test_default_config_roundtrips(tmp_path):
    cfg = AppConfig()
    assert parse_config(as_dict(cfg)) == cfg


def test_constructed_mode_roundtrips():
    cfg = AppConfig(modes=(
        Mode(
            name="Wake up",
            activation=ScheduleActivation(at=time(7, 0), days=frozenset({0, 1, 2, 3, 4})),
            behavior=AlarmBehavior(message="Wake up", snooze_minutes=9, dismiss_event="woke_up"),
        ),
        Mode(
            name="Default",
            activation=AlwaysActivation(),
            behavior=ActionsBehavior(actions={"short_press": LogAction(event="x")}),
        ),
    ))
    assert parse_config(as_dict(cfg)) == cfg


def test_all_four_templates_and_enter_mode_roundtrip(tmp_path):
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "long_press": {"action": "enter_mode", "target": "Focus"},
             "double_tap": {"action": "enter_mode", "target": "Water"}},
            {"name": "Wake up", "template": "alarm",
             "activation": {"type": "schedule", "at": "07:00"},
             "message": "Up", "label": "", "snooze_minutes": 9, "dismiss_event": "woke_up"},
            {"name": "Focus", "template": "stopwatch",
             "activation": {"type": "manual"}, "log_as": "focus"},
            {"name": "Water", "template": "counter",
             "activation": {"type": "manual"}, "event": "water"},
        ],
    }))
    dumped = as_dict(cfg)
    assert dumped["modes"][0]["long_press"] == {"action": "enter_mode", "target": "Focus"}
    stopwatch = dumped["modes"][2]
    # The ladder is asserted separately from the rest: pinning the whole dict
    # made this test fail every time a template gained a field, which says
    # nothing about round-tripping (the assert below is what does).
    assert {k: v for k, v in stopwatch.items() if k != "ladder"} == {
        "name": "Focus", "template": "stopwatch",
        "activation": {"type": "manual"}, "log_as": "focus",
    }
    assert stopwatch["ladder"]["enabled"] is False  # opt-in, never by surprise
    assert dumped["modes"][3] == {
        "name": "Water", "template": "counter",
        "activation": {"type": "manual"}, "event": "water",
    }
    assert parse_config(dumped) == cfg  # exact round-trip


def test_metronome_roundtrips(tmp_path):
    """A metronome written with no fields comes back carrying all of them, so
    the editor has something to show rather than an empty form."""
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"}},
        ],
    }))
    dumped = as_dict(cfg)
    # The ladder is checked apart from the rest: pinning the whole dict made
    # this fail whenever the template gained a field, which says nothing about
    # round-tripping - the assert below is what does.
    assert {k: v for k, v in dumped["modes"][0].items() if k != "ladder"} == {
        "name": "Tempo", "template": "metronome", "activation": {"type": "manual"},
        "start_bpm": 120.0, "max_bpm": 300.0, "tap_history": 8,
        "reset_gap_s": 2.0, "sound_on_tap": True, "log_as": "metronome",
        "clock_port": "",  # tap-only, the tempo source this mode always had
    }
    assert dumped["modes"][0]["ladder"]["enabled"] is False  # opt-in
    assert parse_config(dumped) == cfg  # exact round-trip


def test_metronome_fields_fall_back_one_at_a_time(tmp_path):
    """A bad tempo costs you that tempo, not the whole mode - the same per-key
    rule the rest of the parser follows."""
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"},
             "start_bpm": "fast", "tap_history": 1, "reset_gap_s": -3,
             "sound_on_tap": "yes", "max_bpm": 240},
        ],
    }))
    behavior = cfg.modes[0].behavior
    assert behavior.start_bpm == 120.0    # not a number
    assert behavior.tap_history == 8      # below the two taps an average needs
    assert behavior.reset_gap_s == 2.0    # not positive
    assert behavior.sound_on_tap is True  # not a bool
    assert behavior.max_bpm == 240.0      # the one good value survives


def test_a_starting_tempo_above_the_ceiling_lifts_the_ceiling(tmp_path):
    """Both values parse; they just disagree. Keeping the tempo the user asked
    to start at beats silently starting them slower."""
    cfg = load_config(write(tmp_path, {
        "modes": [
            {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"},
             "start_bpm": 260, "max_bpm": 200},
        ],
    }))
    behavior = cfg.modes[0].behavior
    assert (behavior.start_bpm, behavior.max_bpm) == (260.0, 260.0)


def test_constructed_takeover_modes_roundtrip():
    cfg = AppConfig(modes=(
        Mode(name="Default", activation=AlwaysActivation(),
             behavior=ActionsBehavior(actions={
                 "short_press": EnterModeAction(target="Focus"),
             })),
        Mode(name="Focus", activation=ManualActivation(),
             behavior=StopwatchBehavior(log_as="focus")),
        Mode(name="Water", activation=ManualActivation(),
             behavior=CounterBehavior(event="water")),
    ))
    assert parse_config(as_dict(cfg)) == cfg


# --- web + manager ------------------------------------------------------

def test_web_keys(tmp_path):
    cfg = load_config(write(tmp_path, {
        "web_enabled": False,
        "web_host": "127.0.0.1",
        "web_port": 9090,
    }))
    assert cfg.web_enabled is False
    assert cfg.web_host == "127.0.0.1"
    assert cfg.web_port == 9090
    assert load_config(write(tmp_path, {"web_port": "9090"})).web_port == 8080  # bad type


def test_config_manager_reload(tmp_path):
    path = write(tmp_path, {"ble_device_name": "First"})
    cm = ConfigManager(path)
    assert cm.config.ble_device_name == "First"
    write(tmp_path, {"ble_device_name": "Second"})
    cm.reload()
    assert cm.config.ble_device_name == "Second"


def test_config_manager_env_path(tmp_path, monkeypatch):
    path = write(tmp_path, {"ble_device_name": "FromEnv"})
    monkeypatch.setenv("AIBUTTON_CONFIG", path)
    cm = ConfigManager()
    assert cm.path == path
    assert cm.config.ble_device_name == "FromEnv"


# --- which gestures are actually bound ---------------------------------

def test_the_gesture_vocabulary_matches_the_wire():
    """config.py and device.py must offer the same gestures, or a mode could
    bind one the button will never send (or the button could send one no mode
    can name)."""
    from aibutton.device import TriggerType

    assert TRIGGER_TYPES == tuple(t.value for t in TriggerType)


def test_bound_triggers_reads_the_everyday_template():
    config = parse_config({
        "modes": [{
            "name": "Default", "template": "actions",
            "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "ping"},
            "triple_tap": {"action": "log", "event": "note"},
        }],
    })
    assert bound_triggers(config.modes) == {"short_press", "triple_tap"}


def test_bound_triggers_reads_a_takeover_template_too():
    """Pomodoro keeps its gesture map under a different field name. Reading
    the dataclass's dict-shaped fields rather than asking each template what
    it binds is what makes that work without a branch per template - including
    for a template nobody has written yet."""
    config = parse_config({
        "modes": [{
            "name": "Pom", "template": "pomodoro",
            "activation": {"type": "manual"},
            "short_press": "toggle", "long_press": "exit", "double_tap": "extend",
        }],
    })
    assert {"short_press", "long_press", "double_tap"} <= bound_triggers(config.modes)


def test_nothing_bound_is_an_empty_set_not_an_error():
    # bound_triggers is pure and works on any Mode tuple - constructed
    # directly here rather than through parse_config, whose invariant
    # guarantee (_ensure_ambient_always) would otherwise seed a "Home" mode
    # and put gestures back into the set this test means to find empty.
    mode = Mode(
        name="Tea", activation=ManualActivation(),
        behavior=CountdownBehavior(minutes=3),
    )
    assert bound_triggers((mode,)) == set()


# --- stop-list looks (sequences) -----------------------------------------

def test_a_look_pool_may_mix_plain_effects_and_sequences():
    cfg = parse_config({
        "looks": {
            "warm": {"style": "breathe", "color": "#ff8800", "period_s": 4.0},
            "pulse": {"stops": ["#ff0000", "#0000ff"]},
        },
    })
    assert isinstance(cfg.looks["warm"], LedEffect)
    assert isinstance(cfg.looks["pulse"], Sequence)


def test_a_stops_key_is_what_selects_the_sequence_shape():
    """The dispatch is the key's presence, not a "type" field - an object
    with no `stops` still parses as a plain effect exactly as before."""
    cfg = parse_config({"looks": {"plain": {"style": "solid", "color": "#00ff00"}}})
    assert cfg.looks["plain"] == LedEffect(style="solid", color="#00ff00")


def test_bare_colours_and_objects_both_work_as_stops():
    cfg = parse_config({
        "looks": {"pulse": {"stops": [
            "#ff0000",                                            # bare shorthand
            {"color": "#00ff00", "hold_s": 1.0, "fade_s": 0.2},    # full form
        ]}},
    })
    seq = cfg.looks["pulse"]
    assert seq.stops == (
        Stop("#ff0000", hold_s=0.5, fade_s=0.0),  # Stop's own defaults
        Stop("#00ff00", hold_s=1.0, fade_s=0.2),
    )
    assert seq.repeat is True  # the default


def test_repeat_false_is_a_one_shot():
    cfg = parse_config({
        "looks": {"once": {"stops": ["#ff0000", "#00ff00"], "repeat": False}},
    })
    assert cfg.looks["once"].repeat is False


def test_a_non_bool_repeat_falls_back_to_true():
    cfg, warnings = parse_with_warnings({
        "looks": {"a": {"stops": ["#ff0000"], "repeat": "yes"}},
    })
    assert cfg.looks["a"].repeat is True
    assert any("repeat" in w for w in warnings)


def test_a_structurally_wrong_stop_is_dropped_others_survive():
    """One bad stop costs that stop, not the sequence - the same rule
    _parse_ramp follows for a ramp stop of the wrong shape."""
    cfg, warnings = parse_with_warnings({
        "looks": {"mix": {"stops": [
            {"color": "#ff0000"},
            123,        # wrong shape entirely - dropped
            {"color": "#00ff00"},
        ]}},
    })
    seq = cfg.looks["mix"]
    assert [s.color for s in seq.stops] == ["#ff0000", "#00ff00"]
    assert any("stops[1]" in w for w in warnings)


def test_a_bad_field_inside_a_stop_falls_back_per_field_the_stop_survives():
    cfg, warnings = parse_with_warnings({
        "looks": {"a": {"stops": [
            {"color": "not-a-colour", "hold_s": -1, "fade_s": "nope"},
        ]}},
    })
    stop = cfg.looks["a"].stops[0]
    assert stop.color == "#000000"   # bad colour -> black, not dropped
    assert stop.hold_s == 0.5
    assert stop.fade_s == 0.0
    assert any("a.stops[0].color" in w for w in warnings)
    assert any("a.stops[0].hold_s" in w for w in warnings)
    assert any("a.stops[0].fade_s" in w for w in warnings)


def test_an_empty_stops_list_falls_back_to_the_default_effect():
    cfg, warnings = parse_with_warnings({"looks": {"broken": {"stops": []}}})
    assert cfg.looks["broken"] == LedEffect()
    assert any("broken.stops" in w for w in warnings)


def test_stops_not_a_list_falls_back_to_the_default_effect():
    cfg = parse_config({"looks": {"broken": {"stops": "nope"}}})
    assert cfg.looks["broken"] == LedEffect()


def test_every_stop_unusable_falls_back_to_the_default_effect():
    """Structurally wrong entries all the way down: nothing survives, so the
    whole look reverts - the same "empty/invalid" rule as an empty list."""
    cfg = parse_config({"looks": {"broken": {"stops": [None, 42, []]}}})
    assert cfg.looks["broken"] == LedEffect()


def test_a_sequence_look_round_trips_through_as_dict():
    cfg = parse_config({
        "looks": {"pulse": {
            "stops": [
                {"color": "#ff0000", "hold_s": 0.3, "fade_s": 0.1},
                {"color": "#00ff00", "hold_s": 0.6, "fade_s": 0.2},
            ],
            "repeat": False,
        }},
    })
    again = parse_config(as_dict(cfg))
    assert again.looks["pulse"] == cfg.looks["pulse"]
    assert isinstance(again.looks["pulse"], Sequence)


def test_a_mixed_pool_round_trips_through_as_dict():
    cfg = parse_config({
        "looks": {
            "warm": {"style": "breathe", "color": "#ff8800", "period_s": 4.0},
            "pulse": {"stops": ["#ff0000", "#0000ff"]},
        },
    })
    again = parse_config(as_dict(cfg))
    assert again.looks == cfg.looks


# --- the drive and a stop's own shape, head-on (TODO 36b/c/d) --------------
#
# The two round-trips above cover `stops`/`repeat`. The four keys TODO 36
# added - a sequence's `drive`, and a stop's `curve`, `style` and `period_s` -
# were only ever carried incidentally by tests that happened to set one, which
# is a round-trip nobody is actually asserting.
#
# The serialiser's convention is that a look is written out **in full**:
# `_look_to_dict` names every key the way `_effect_to_dict` does and the way a
# countdown's ramp positions are, so a stop that took the defaults still says
# so on the way out. "The round-trip has to be exact, not merely equivalent" -
# so that is what is pinned below, rather than a tidier-looking output that
# omitted whatever happened to match a default.

_SEQUENCE_LOOKS = {
    "plain": {"stops": ["#ff0000", "#0000ff"]},
    "curved": {"stops": [
        {"color": "#ff0000", "hold_s": 0.25, "fade_s": 0.75, "curve": "ease_in_out"},
        {"color": "#0000ff", "hold_s": 0.5, "fade_s": 0.5, "curve": "exponential"},
    ]},
    "animated": {"stops": [
        {"color": "#00ff00", "hold_s": 2.0, "style": "flash", "period_s": 0.45},
        {"color": "#000000", "hold_s": 1.0, "style": "breathe", "period_s": 3.0},
    ]},
    "sampled": {"drive": "progress", "repeat": False, "stops": [
        {"color": "#ff0000", "hold_s": 1.0, "fade_s": 1.0, "curve": "ease_out"},
        {"color": "#00ff00", "hold_s": 1.0},
    ]},
    "beaten": {"drive": "beats", "stops": [
        {"color": "#ffffff", "hold_s": 1.0, "style": "flash", "period_s": 0.5},
        {"color": "#333333", "hold_s": 3.0},
    ]},
}


@pytest.mark.parametrize("name", sorted(_SEQUENCE_LOOKS))
def test_a_sequences_drive_and_stop_shape_survive_the_editor(name):
    """Serialise, parse, serialise: the second dump has to equal the first, or
    a look would drift a little every time the editor saved it."""
    cfg = parse_config({"looks": dict(_SEQUENCE_LOOKS)})
    dumped = as_dict(cfg)
    again = parse_config(dumped)
    assert again.looks[name] == cfg.looks[name]
    assert as_dict(again)["looks"][name] == dumped["looks"][name]


def test_drive_and_curve_are_carried_rather_than_defaulted_away():
    """The failure a round-trip alone cannot see: a serialiser that dropped
    `drive` or `curve` would still round-trip *something* - just not the look
    that was asked for."""
    cfg = parse_config({"looks": {"arc": {
        "drive": "progress", "repeat": False,
        "stops": [{"color": "#ff0000", "hold_s": 0.25, "fade_s": 0.75,
                   "curve": "ease_in"}],
    }}})
    assert cfg.looks["arc"] == Sequence(
        stops=(Stop("#ff0000", hold_s=0.25, fade_s=0.75, curve="ease_in"),),
        repeat=False, drive="progress",
    )
    assert as_dict(cfg)["looks"]["arc"] == {
        "stops": [{"color": "#ff0000", "hold_s": 0.25, "fade_s": 0.75,
                   "curve": "ease_in"}],
        "repeat": False,
        "drive": "progress",
    }


def test_a_stop_that_still_carries_a_style_loses_it_without_complaint():
    """`style`/`period_s` on a stop were ours to write and ours to drop
    (TODO 36e), so a config that still has them parses to the flat colour it
    now means - silently. Warning about a key we put there ourselves would be
    scolding somebody for our own change of mind."""
    cfg, warnings = parse_with_warnings({"looks": {"old": {
        "stops": [{"color": "#ff0000", "hold_s": 1.0,
                   "style": "flash", "period_s": 0.45}],
    }}})
    assert cfg.looks["old"] == Sequence(stops=(Stop("#ff0000", hold_s=1.0),))
    assert warnings == []


def test_a_stop_that_took_every_default_is_still_written_out_in_full():
    """The convention, stated once: every key, every time. A stop written as a
    bare colour comes back as the object form, and `clock` is named rather than
    left to be inferred - a reader should not have to know the defaults to see
    what a look does."""
    cfg = parse_config({"looks": {"pulse": {"stops": ["#ff0000"]}}})
    assert as_dict(cfg)["looks"]["pulse"] == {
        "stops": [{
            "color": "#ff0000", "hold_s": 0.5, "fade_s": 0.0, "curve": "linear",
        }],
        "repeat": True,
        "drive": "clock",
    }


# --- the readout action (TODO 15/17) --------------------------------------

def _mode_with(action: dict) -> dict:
    return {"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": action,
    }]}


def test_a_readout_action_parses_with_its_defaults():
    cfg = parse_config(_mode_with({"action": "readout", "event": "coffee"}))
    action = cfg.modes[0].behavior.actions["short_press"]
    assert action == ReadoutAction(event="coffee")
    assert action.tens_color != action.units_color  # clearly different, by design


def test_a_readout_action_carries_its_own_colours():
    cfg = parse_config(_mode_with({
        "action": "readout", "event": "coffee",
        "tens_color": "#112233", "units_color": "#445566",
    }))
    action = cfg.modes[0].behavior.actions["short_press"]
    assert action == ReadoutAction(
        event="coffee", tens_color="#112233", units_color="#445566"
    )


def test_a_readout_with_no_event_is_not_a_valid_action():
    cfg, warnings = parse_with_warnings(_mode_with({"action": "readout"}))
    # The mode is seeded with the default Home actions instead (same
    # fail-soft rule _ensure_ambient_always applies whenever an ambient mode
    # is left with no usable gesture actions).
    mode = next((m for m in cfg.modes if m.name == "Desk"), None)
    assert mode is None
    assert any("not a valid action" in w for w in warnings)


def test_a_readout_actions_bad_colour_costs_the_colour_not_the_action():
    """Per-field fallback, like `_parse_effect` - a typo in a colour must not
    take the whole binding down with it."""
    cfg, warnings = parse_with_warnings(_mode_with({
        "action": "readout", "event": "coffee", "tens_color": "not-a-colour",
    }))
    action = cfg.modes[0].behavior.actions["short_press"]
    assert action == ReadoutAction(event="coffee")  # default tens_color, event kept
    assert any("tens_color" in w for w in warnings)


def test_a_readout_action_round_trips_through_the_editor():
    raw = _mode_with({
        "action": "readout", "event": "coffee",
        "tens_color": "#ff8800", "units_color": "#3399ff",
    })
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


# --- lifecycle hooks (TODO 31) ---------------------------------------------
# Two optional actions on the *mode*, not on each behaviour, so every takeover
# gets them for nothing. What is worth testing here is the fail-soft half: a
# hook is something a mode does around itself, so a broken one must cost you
# the hook and never the app.


def _takeover_with(**hooks) -> dict:
    return {"modes": [dict({
        "name": "Focus", "template": "stopwatch",
        "activation": {"type": "manual"}, "log_as": "focus",
    }, **hooks)]}


def test_a_mode_can_carry_an_action_on_each_edge():
    cfg = parse_config(_takeover_with(
        on_enter={"action": "webhook", "url": "https://example.test/start"},
        on_exit={"action": "log", "event": "focus_done"},
    ))
    mode = cfg.modes[0]
    assert mode.on_enter == WebhookAction(url="https://example.test/start")
    assert mode.on_exit == LogAction(event="focus_done")


def test_a_mode_with_no_hooks_has_none_and_writes_none():
    """The default has to be indistinguishable from before hooks existed, or
    every config ever written stops round-tripping byte for byte."""
    cfg = parse_config(_takeover_with())
    assert (cfg.modes[0].on_enter, cfg.modes[0].on_exit) == (None, None)
    written = as_dict(cfg)["modes"][0]
    assert "on_enter" not in written and "on_exit" not in written


def test_a_hook_may_name_a_pooled_action():
    """A hook is the fourth place an action is dispatched, so it has to be able
    to hold a name like the other three - resolved at use time, never here."""
    cfg = parse_config({
        "actions": {"desk-lamp": {"action": "osc", "address": "/lamp", "port": 9000}},
        **_takeover_with(on_enter="desk-lamp"),
    })
    assert cfg.modes[0].on_enter == NamedAction(name="desk-lamp")


def test_a_hook_naming_nothing_is_warned_about_but_kept():
    """Same rule a gesture's dangling name follows: repointing it at something
    nobody chose would be worse than leaving it visibly broken."""
    cfg, warnings = parse_with_warnings(_takeover_with(on_exit="gone"))
    assert cfg.modes[0].on_exit == NamedAction(name="gone")
    assert any("gone" in w for w in warnings)


def test_a_broken_hook_is_dropped_and_the_mode_survives():
    """The whole fail-soft claim in one case: the webhook has no URL, so there
    is nothing to fire - and losing a stopwatch over it would be absurd."""
    cfg, warnings = parse_with_warnings(_takeover_with(
        on_enter={"action": "webhook"},
        on_exit={"action": "log", "event": "focus_done"},
    ))
    mode = cfg.modes[0]
    assert mode.name == "Focus"
    assert mode.behavior == StopwatchBehavior(log_as="focus", ladder=mode.behavior.ladder)
    assert mode.on_enter is None            # dropped
    assert mode.on_exit == LogAction(event="focus_done")  # the other one is untouched
    assert any("on_enter" in w and "not a valid action" in w for w in warnings)


@pytest.mark.parametrize("action", [
    {"action": "enter_mode", "target": "Water"},
    {"action": "readout", "event": "coffee"},
    {"action": "standby"},
])
def test_the_three_loop_actions_are_refused_as_hooks(action):
    """These change what the run *loop* does next rather than the world outside
    it, and a hook fires beside the loop. An `enter_mode` hook is the one that
    would actually break something - a takeover starting a takeover from inside
    the moment the first one begins."""
    cfg, warnings = parse_with_warnings(_takeover_with(on_enter=action))
    assert cfg.modes[0].on_enter is None
    assert any("on_enter" in w for w in warnings)


def test_a_hook_on_an_everyday_mode_is_kept_and_complained_about():
    """An ambient mode is never entered or left, so nothing will ever fire
    this. Kept rather than deleted - the fix is to change the template, not to
    lose what was written - but a hook that silently does nothing is exactly
    what a load-time warning is for."""
    cfg, warnings = parse_with_warnings({"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": {"action": "log", "event": "ping"},
        "on_enter": {"action": "log", "event": "never"},
    }]})
    desk = next(m for m in cfg.modes if m.name == "Desk")
    assert desk.on_enter == LogAction(event="never")
    assert any("never fire" in w for w in warnings)


def test_hooks_round_trip_through_the_editor():
    raw = {
        "actions": {"desk-lamp": {"action": "log", "event": "lamp"}},
        **_takeover_with(
            on_enter={"action": "midi", "port": "Button", "channel": 1,
                      "kind": "note_on", "number": 60, "value": 127},
            on_exit="desk-lamp",
        ),
    }
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]
    # And a named hook stays the bare string it was written as.
    assert as_dict(once)["modes"][0]["on_exit"] == "desk-lamp"
