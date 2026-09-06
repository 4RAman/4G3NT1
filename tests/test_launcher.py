"""The app launcher, and the rule that lets a takeover start another one.

The rule is **replace, don't nest**: launching closes the launcher's session
before opening the app's, so a chain is a sequence rather than a stack. Most of
what is worth asserting here is that sequence — the event log is the honest
witness, because nested sessions and sequential ones look identical from the
LED and completely different in the log.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import LauncherBehavior, as_dict, parse_config, parse_with_warnings
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

APPS = [
    {"name": "Home", "template": "actions", "activation": {"type": "always"},
     "tap_4": {"action": "enter_mode", "target": "Menu"}},
    {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
     "log_as": "launched"},
    {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"},
     "log_as": "focus"},
    {"name": "Water", "template": "counter", "activation": {"type": "manual"},
     "event": "water"},
]


def _config(db, modes=None, **over):
    return {
        "sounds_enabled": False, "web_enabled": False, "database_path": str(db),
        "modes": modes if modes is not None else APPS, **over,
    }


async def _start(tmp_path, raw):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(raw), encoding="utf-8")
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)
    return task, device


async def _press(device, trigger):
    device.press(trigger)
    await asyncio.sleep(0.12)


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _rows(db):
    store = EventStore(str(db))
    try:
        return [(k, n) for (_ts, k, n, _d, _m, _v) in store.recent(100)][::-1]
    finally:
        store.close()


# --- reaching it -----------------------------------------------------------

async def test_a_gesture_opens_the_launcher(tmp_path):
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.TAP_4)
        assert device.led_state is LEDState.LISTENING
    finally:
        await _stop(task)


async def test_each_app_is_shown_in_its_own_colour(tmp_path):
    """The launcher answers 'which app', not 'which mode is running' - so
    cycling has to change the light without changing the state."""
    db = tmp_path / "events.db"
    modes = list(APPS)
    modes[2] = dict(modes[2], looks={"TIMING": "focus-look"})
    raw = _config(db, modes=modes, looks={
        "focus-look": {"style": "solid", "color": "#00ff88"},
    })
    task, device = await _start(tmp_path, raw)
    try:
        await _press(device, TriggerType.TAP_4)   # open the launcher
        first = device.led_effect
        await _press(device, TriggerType.SHORT_PRESS)  # next app
        second = device.led_effect
        assert device.led_state is LEDState.LISTENING
        assert first != second, "cycling apps did not change the light"
        assert "#00ff88" in (first.color, second.color)
    finally:
        await _stop(task)


# --- replace, don't nest ---------------------------------------------------

async def test_launching_closes_the_launcher_before_opening_the_app(tmp_path):
    """The whole rule, read off the log: the launcher's exit must land
    *before* the app's enter, not wrap around it."""
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.TAP_4)   # open launcher
        await _press(device, TriggerType.DOUBLE_TAP)   # launch the first app
        await asyncio.sleep(0.1)
    finally:
        await _stop(task)

    rows = _rows(db)
    order = [(k, n) for k, n in rows if k in ("mode_enter", "mode_exit")]
    assert order[:3] == [
        ("mode_enter", "Menu"),
        ("mode_exit", "Menu"),
        ("mode_enter", "Focus"),
    ], f"nested rather than sequential: {order}"


async def test_long_press_means_up_one_level_everywhere(tmp_path):
    """The rule the whole button leans on. Every takeover already exits on a
    long press; with `return_after` on by default that makes the gesture mean
    one distance rather than two - out of an app lands in the menu, out of the
    menu goes home. Two presses from anywhere, and nothing to learn. A third
    would put the button to sleep (TODO 104), which is the same rule arriving
    at the top of the ladder rather than an exception to it."""
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.TAP_4)  # four taps -> launcher
        await _press(device, TriggerType.DOUBLE_TAP)  # launch Focus (stopwatch)
        await asyncio.sleep(0.1)
        assert device.led_state is LEDState.TIMING, "the app did not start"

        await _press(device, TriggerType.LONG_PRESS)  # up: app -> launcher
        await asyncio.sleep(0.15)
        assert device.led_state is LEDState.LISTENING, "long press skipped the menu"

        await _press(device, TriggerType.LONG_PRESS)  # up again: launcher -> home
        await asyncio.sleep(0.15)
        assert device.led_state is LEDState.IDLE, "long press did not reach home"
    finally:
        await _stop(task)


async def test_opting_out_makes_an_app_exit_straight_home(tmp_path):
    """`return_after: false` is still there for someone who wants the app to
    be the thing they are in - it just is not the default any more."""
    db = tmp_path / "events.db"
    modes = list(APPS)
    modes[1] = dict(modes[1], return_after=False)
    task, device = await _start(tmp_path, _config(db, modes=modes))
    try:
        await _press(device, TriggerType.TAP_4)  # launcher
        await _press(device, TriggerType.DOUBLE_TAP)  # launch Focus
        await _press(device, TriggerType.LONG_PRESS)  # stop it
        await asyncio.sleep(0.15)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


async def test_it_returns_to_the_launcher_once_not_forever(tmp_path):
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.TAP_4)  # launcher
        await _press(device, TriggerType.DOUBLE_TAP)  # launch Focus
        await _press(device, TriggerType.LONG_PRESS)  # stop it -> back to launcher
        await asyncio.sleep(0.15)
        assert device.led_state is LEDState.LISTENING, "did not return to the launcher"
        await _press(device, TriggerType.LONG_PRESS)  # and out
        await asyncio.sleep(0.15)
        assert device.led_state is LEDState.IDLE, "returned more than once"
    finally:
        await _stop(task)


async def test_long_press_backs_out_without_launching(tmp_path):
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.TAP_4)  # open
        await _press(device, TriggerType.LONG_PRESS)  # and straight back out
        await asyncio.sleep(0.1)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)

    names = [n for k, n in _rows(db) if k == "mode_enter"]
    assert "Focus" not in names and "Water" not in names


async def test_a_launch_is_logged_when_asked(tmp_path):
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.TAP_4)  # open
        await _press(device, TriggerType.DOUBLE_TAP)  # launch
        await asyncio.sleep(0.1)
    finally:
        await _stop(task)
    assert ("log", "launched") in _rows(db)


# --- what it offers --------------------------------------------------------

def test_an_empty_target_list_offers_every_app():
    cfg = parse_config({"modes": APPS})
    assert cfg.modes[1].behavior.targets == ()


def test_named_targets_choose_and_order_the_menu():
    modes = list(APPS)
    modes[1] = dict(modes[1], targets=["Water", "Focus"])
    cfg = parse_config({"modes": modes})
    assert cfg.modes[1].behavior.targets == ("Water", "Focus")


async def test_a_launcher_never_offers_another_launcher(tmp_path):
    """The one shape that could chain with nobody driving it.

    Asserted by counting rather than by looking: with two real apps, cycling
    twice must land back on the first. If a second launcher were in the menu
    the cycle would be three long, so the second short press would leave the
    selection on it and launching would enter the wrong mode - which the log
    shows.
    """
    db = tmp_path / "events.db"
    modes = APPS + [{"name": "Other menu", "template": "launcher",
                     "activation": {"type": "manual"}}]
    task, device = await _start(tmp_path, _config(db, modes=modes))
    try:
        await _press(device, TriggerType.TAP_4)   # open the launcher
        await _press(device, TriggerType.SHORT_PRESS)  # -> Water
        await _press(device, TriggerType.SHORT_PRESS)  # -> back to Focus
        await _press(device, TriggerType.DOUBLE_TAP)   # launch whatever shows
        await asyncio.sleep(0.1)
    finally:
        await _stop(task)

    entered = [n for k, n in _rows(db) if k == "mode_enter"]
    assert "Other menu" not in entered, f"a launcher offered itself a launcher: {entered}"
    assert entered[-1] == "Focus", f"cycle length wrong, landed on {entered[-1]!r}"


async def test_a_launcher_with_nothing_to_offer_fails_clearly(tmp_path):
    db = tmp_path / "events.db"
    modes = [APPS[0], APPS[1]]  # a launcher and nothing to launch
    task, device = await _start(tmp_path, _config(db, modes=modes))
    try:
        await _press(device, TriggerType.TAP_4)
        await asyncio.sleep(0.2)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


def test_a_target_that_does_not_exist_is_not_a_parse_error():
    """Config order is not dependency order - a launcher listed above its apps
    is the normal way to write one, so a missing name is a run-time warning."""
    modes = list(APPS)
    modes[1] = dict(modes[1], targets=["Nope"])
    cfg, warnings = parse_with_warnings({"modes": modes})
    assert cfg.modes[1].behavior.targets == ("Nope",)
    assert not [w for w in warnings if "Nope" in w]


# --- config surface --------------------------------------------------------

def test_it_may_only_be_started_by_a_gesture():
    _, warnings = parse_with_warnings({"modes": [
        {"name": "Menu", "template": "launcher",
         "activation": {"type": "schedule", "at": "07:00"}},
    ]})
    assert any("Menu" in w for w in warnings)


def test_every_field_falls_back_on_its_own():
    # `targets` is a number rather than a string here on purpose: a *string* is
    # a legitimate shape now (see below), so it is no longer an example of
    # something the parser should reject.
    cfg = parse_config({"modes": [
        {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
         "targets": 7, "return_after": "yes", "log_as": 7},
    ]})
    assert cfg.modes[0].behavior == LauncherBehavior()


def test_a_typed_out_menu_survives_being_saved_from_the_web_ui():
    """The bug this pins: the editor's field for `targets` is a textarea, so it
    writes one name per line as a plain string. Accepting only a list meant
    that opening a launcher in the web UI and pressing Save silently turned a
    curated menu into "offer every app" - an error in the log, and nothing at
    all on screen. `cues` had taken both shapes since 52a."""
    cfg = parse_config({"modes": [
        {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
         "targets": "Water\nFocus"},
    ]})
    assert cfg.modes[0].behavior.targets == ("Water", "Focus")


def test_a_typed_menu_ignores_blank_lines_and_stray_spacing():
    cfg = parse_config({"modes": [
        {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
         "targets": "  Water  \n\n\n  Focus\n"},
    ]})
    assert cfg.modes[0].behavior.targets == ("Water", "Focus")


def test_an_emptied_box_means_every_app_which_is_what_the_field_promises():
    """Blank offers everything - the field's own hint says so, and an
    all-whitespace box has to mean the same thing as an empty one."""
    for typed in ("", "   ", "\n  \n"):
        cfg = parse_config({"modes": [
            {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
             "targets": typed},
        ]})
        assert cfg.modes[0].behavior.targets == (), typed


def test_bad_entries_are_dropped_without_losing_the_good_ones():
    cfg = parse_config({"modes": [
        {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
         "targets": ["Focus", 3, "", "Water"]},
    ]})
    assert cfg.modes[0].behavior.targets == ("Focus", "Water")


def test_it_round_trips_through_the_editor():
    raw = {"modes": [
        {"name": "Menu", "template": "launcher", "activation": {"type": "manual"},
         "targets": ["Focus"], "return_after": True, "log_as": "launched"},
    ]}
    once = parse_config(raw)
    assert parse_config(as_dict(once)).modes[0].behavior == once.modes[0].behavior


def test_it_owns_no_led_state():
    """It wears the target's colour; a look of its own would only hide that."""
    from aibutton.config import MODE_LED_STATES
    assert MODE_LED_STATES["launcher"] == ()
