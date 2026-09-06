"""The named-action pool (TODO 30a) and the standby action.

Two features that ship together because they are the two halves of the same
sentence someone wanted to write: "five taps turns it off, and the action that
does it is one I can point three gestures at."

The pool is `looks` again - `AppConfig.actions`, referenced from a gesture by
bare string - so these tests are mostly about the four properties that move was
made for: naming is optional, a dangling name warns rather than crashes, the
reference round-trips as the string it was, and resolution happens in one place.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import (
    LogAction,
    NamedAction,
    StandbyAction,
    WebhookAction,
    as_dict,
    parse_config,
    parse_with_warnings,
    resolve_action,
)
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

FLOOR = {"name": "Base", "template": "actions", "activation": {"type": "always"}}


def _cfg(**over):
    """A config with an ambient floor, so nothing here trips the seeded-Home
    warning `_ensure_ambient_always` adds to a config without one."""
    base = {**FLOOR, "short_press": {"action": "log", "event": "x"}}
    return {"modes": [base], **over}


# --- the pool ------------------------------------------------------------

def test_a_gesture_may_name_an_action_instead_of_holding_one():
    cfg, warnings = parse_with_warnings({
        "actions": {"smoke": {"action": "log", "event": "cig"}},
        "modes": [{**FLOOR, "short_press": "smoke"}],
    })
    binding = cfg.modes[0].behavior.actions["short_press"]
    assert binding == NamedAction(name="smoke")
    # The reference is not the action: resolving it is a separate step, and
    # that is what lets one edit reach every gesture naming it.
    assert resolve_action(cfg, binding) == LogAction(event="cig")
    assert not warnings


def test_naming_stays_optional_and_inline_actions_are_untouched():
    """The whole reason the pool is opt-in: most actions are used once."""
    cfg = parse_config(_cfg())
    assert cfg.actions == {}
    assert cfg.modes[0].behavior.actions["short_press"] == LogAction(event="x")


def test_a_name_with_nothing_behind_it_warns_and_keeps_the_binding():
    """Deleting a pool entry must leave an honest dangling name.

    Dropping the reference would silently change what the gesture does, which
    is strictly worse than a gesture that does nothing and says why - the same
    call `EnterModeAction` already makes about a missing target.
    """
    cfg, warnings = parse_with_warnings({
        "modes": [{**FLOOR, "short_press": "ghost"}],
    })
    assert cfg.modes[0].behavior.actions["short_press"] == NamedAction(name="ghost")
    assert resolve_action(cfg, NamedAction(name="ghost")) is None
    assert any("names action 'ghost'" in w for w in warnings), warnings


def test_a_mode_bound_only_by_name_survives_the_pool_being_empty():
    """A dangling name is not "no valid gesture actions" - losing the mode
    over one would be the rewrite the dangling name exists to prevent."""
    cfg = parse_config({"modes": [{**FLOOR, "short_press": "ghost"}]})
    assert [m.name for m in cfg.modes] == ["Base"]


def test_one_broken_pool_entry_costs_that_entry_and_not_the_pool():
    cfg, warnings = parse_with_warnings(_cfg(actions={
        "good": {"action": "log", "event": "ok"},
        "bad": {"action": "log"},             # no event
        "": {"action": "log", "event": "y"},  # unusable name
    }))
    assert set(cfg.actions) == {"good"}
    assert len(warnings) == 2, warnings


def test_a_pool_entry_may_not_itself_be_a_name():
    """One level, guaranteed by the parser rather than by a cycle check."""
    cfg, warnings = parse_with_warnings(_cfg(actions={
        "real": {"action": "log", "event": "ok"},
        "alias": "real",
    }))
    assert set(cfg.actions) == {"real"}
    assert any("cannot reference another one" in w for w in warnings), warnings


def test_a_pool_that_is_not_an_object_is_ignored_rather_than_fatal():
    cfg, warnings = parse_with_warnings(_cfg(actions=["log"]))
    assert cfg.actions == {}
    assert any("must be an object" in w for w in warnings), warnings


def test_an_empty_name_is_not_a_reference():
    cfg, warnings = parse_with_warnings({
        "modes": [{
            **FLOOR, "short_press": "   ", "double_tap": {"action": "log", "event": "x"},
        }],
    })
    assert set(cfg.modes[0].behavior.actions) == {"double_tap"}
    assert any("empty action name" in w for w in warnings), warnings


def test_a_reference_round_trips_as_the_string_it_was_written_as():
    raw = {
        "actions": {"smoke": {"action": "log", "event": "cig"}},
        "modes": [{**FLOOR, "short_press": "smoke", "double_tap": "ghost"}],
    }
    cfg = parse_config(raw)
    dumped = as_dict(cfg)
    assert dumped["actions"] == {"smoke": {"action": "log", "event": "cig"}}
    assert dumped["modes"][0]["short_press"] == "smoke"
    # The dangling one round-trips too, for the same reason it is kept at all.
    assert dumped["modes"][0]["double_tap"] == "ghost"
    assert parse_config(dumped) == cfg


def test_every_gesture_surface_can_name_one():
    """Ambient modes, control surfaces and signal positions are the three
    places an action is bound, and all three go through `_parse_action`."""
    cfg = parse_config({
        "actions": {"go": {"action": "log", "event": "go"}},
        "modes": [
            {**FLOOR, "short_press": "go"},
            {"name": "Desk", "template": "control", "activation": {"type": "manual"},
             "short_press": "go"},
            {"name": "Light", "template": "signal", "activation": {"type": "manual"},
             "states": [{"name": "Free", "color": "#00ff00", "action": "go"},
                        {"name": "Busy", "color": "#ff0000"}]},
        ],
    })
    by_name = {m.name: m for m in cfg.modes}
    assert by_name["Base"].behavior.actions["short_press"] == NamedAction(name="go")
    assert by_name["Desk"].behavior.actions["short_press"] == NamedAction(name="go")
    assert by_name["Light"].behavior.states[0].action == NamedAction(name="go")


def test_resolve_action_passes_an_inline_action_straight_through():
    cfg = parse_config(_cfg())
    inline = WebhookAction(url="https://example.test/hook")
    assert resolve_action(cfg, inline) is inline
    assert resolve_action(cfg, None) is None


# --- the standby action --------------------------------------------------

def test_standby_parses_and_round_trips():
    cfg = parse_config({"modes": [{**FLOOR, "short_press": {"action": "standby"}}]})
    assert cfg.modes[0].behavior.actions["short_press"] == StandbyAction()
    assert as_dict(cfg)["modes"][0]["short_press"] == {"action": "standby"}


def test_standby_can_be_pooled_like_any_other_action():
    cfg = parse_config({
        "actions": {"off": {"action": "standby"}},
        "modes": [{**FLOOR, "tap_5": "off"}],
    })
    bound = cfg.modes[0].behavior.actions["tap_5"]
    assert resolve_action(cfg, bound) == StandbyAction()


STANDBY_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "actions": {"nap": {"action": "standby"}},
    "modes": [
        {
            "name": "Default",
            "template": "actions",
            "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "ping"},
            "double_tap": "nap",
            "triple_tap": {"action": "enter_mode", "target": "Water"},
        },
        {
            "name": "Water", "template": "counter",
            "activation": {"type": "manual"}, "event": "water",
        },
    ],
}


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def _running(tmp_path, monkeypatch):
    """Start run() against a MockDevice, as test_main_takeover does."""
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(STANDBY_CONFIG, database_path=str(db_path))), encoding="utf-8"
    )
    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)  # let run() reach the main loop

    async def feed(trigger: TriggerType):
        device.press(trigger)
        await _drain(device.events)
        await asyncio.sleep(0.08)

    return device, task, feed, db_path


async def test_standby_silences_the_ambient_layer_and_lets_it_back(tmp_path, monkeypatch):
    """The whole behaviour in one script, because it is one behaviour: a
    gesture that turns the everyday layer off, a gesture ignored while it is
    off, and the same gesture turning it back on.

    Driven through `run()` rather than a unit of it, because what standby
    changes is what the *loop* does with the next press - there is no pure
    function underneath to test instead.
    """
    device, task, feed, db_path = await _running(tmp_path, monkeypatch)
    try:
        await feed(TriggerType.SHORT_PRESS)   # awake: logs
        await feed(TriggerType.DOUBLE_TAP)    # -> standby, via the named action
        await feed(TriggerType.SHORT_PRESS)   # asleep: ignored entirely
        await feed(TriggerType.TRIPLE_TAP)    # asleep: no takeover entered
        await feed(TriggerType.DOUBLE_TAP)    # -> awake
        await feed(TriggerType.SHORT_PRESS)   # awake again: logs
        await asyncio.sleep(0.1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
    finally:
        store.close()
    kinds_names = [(kind, name) for (_ts, kind, name, _d, _m, _v) in rows]

    # Two pings, not three: the press made while asleep logged nothing.
    assert kinds_names.count(("log", "ping")) == 2
    # And the triple tap that would have opened the counter did not.
    assert ("mode_enter", "Water") not in kinds_names


async def test_standby_darkens_idle_and_waking_puts_it_back(tmp_path, monkeypatch):
    """What "ambient-only" looks like: IDLE goes dark, and comes back.

    The dark is *arrived at* rather than snapped to (TODO 104), so this waits
    out the fade - shortened here, since what is being asserted is where the
    light lands and not how long it takes to get there.
    """
    monkeypatch.setattr(main, "_SLEEP_FADE_S", 0.1)
    device, task, feed, _db = await _running(tmp_path, monkeypatch)
    try:
        await feed(TriggerType.DOUBLE_TAP)  # -> standby
        await asyncio.sleep(0.25)           # the fade, and then some
        assert device.led_state is LEDState.IDLE
        assert device.led_effect is not None
        assert (device.led_effect.style, device.led_effect.color) == (
            "solid", main._STANDBY_COLOR,
        )

        await feed(TriggerType.DOUBLE_TAP)  # -> awake
        assert device.led_state is LEDState.IDLE
        # Back to whatever IDLE actually is - the palette entry, not the dim.
        assert (
            device.led_effect is None
            or device.led_effect.color != main._STANDBY_COLOR
        )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
