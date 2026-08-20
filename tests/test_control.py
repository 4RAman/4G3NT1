"""The control-surface template: an app whose gestures fire actions.

The template exists because neither shape that could already fire arbitrary
actions worked as a remote - an ambient actions mode cannot be reached from a
launcher, and a Signal light cycles rather than binding one gesture per
command. So the tests worth writing are the ones about *those* two properties
and about the exit, not about action dispatch, which `execute` already owns.
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

from aibutton import config as cfg, main
from aibutton.config import (
    ControlBehavior,
    ManualActivation,
    as_dict,
    parse_config,
    parse_with_warnings,
)
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

SCHEMA_JS = (Path(__file__).resolve().parents[1]
             / "aibutton/web/static/schema.js").read_text(encoding="utf-8")


def _mode(**overrides) -> dict:
    mode = {
        "name": "DAW", "template": "control", "activation": {"type": "manual"},
        "short_press": {"action": "log", "event": "play"},
        "log_as": "",
    }
    mode.update(overrides)
    return {"modes": [mode]}


# --- the shape -------------------------------------------------------------


def test_a_control_surface_maps_each_gesture_to_its_own_action():
    """The whole point, and the thing a Signal light cannot do: three gestures,
    three different commands, no cycling between them."""
    config = parse_config(_mode(
        short_press={"action": "log", "event": "play"},
        double_tap={"action": "log", "event": "record"},
        triple_tap={"action": "log", "event": "stop"},
    ))
    behavior = config.modes[0].behavior
    assert isinstance(behavior, ControlBehavior)
    assert {t: a.event for t, a in behavior.actions.items()} == {
        "short_press": "play", "double_tap": "record", "triple_tap": "stop",
    }


def test_it_is_a_takeover_a_launcher_can_offer():
    """An ambient actions mode is not reachable from a launcher, which is why
    this template exists at all."""
    config = parse_config(_mode())
    mode = config.modes[0]
    assert isinstance(mode.activation, ManualActivation)
    assert cfg._ALLOWED_ACTIVATIONS["control"] == (ManualActivation,)


def test_a_control_surface_may_not_be_always_on():
    """An always-on control surface is an actions mode, which already exists.
    Offering both would be two ways to say one thing."""
    _, warnings = parse_with_warnings(_mode(activation={"type": "always"}))
    assert warnings


def test_a_mode_with_nothing_bound_is_skipped():
    config, warnings = parse_with_warnings({"modes": [{
        "name": "Empty", "template": "control", "activation": {"type": "manual"},
    }]})
    assert warnings
    assert not any(m.name == "Empty" for m in config.modes)


def test_it_round_trips_through_the_editor():
    once = parse_config(_mode(
        double_tap={"action": "midi", "port": "Button", "kind": "note_on",
                    "channel": 1, "number": 95, "value": 127},
        log_as="daw",
    ))
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


# --- the exit --------------------------------------------------------------


def test_binding_the_long_press_is_refused_with_a_warning():
    """Long press means "up one level" everywhere. A control surface is where
    breaking that would be most tempting - four gestures feels tight and there
    is a fifth right there - so the parser takes the choice away."""
    config, warnings = parse_with_warnings(_mode(
        long_press={"action": "log", "event": "marker"},
    ))
    assert any("long_press" in w for w in warnings)
    assert "long_press" not in config.modes[0].behavior.actions


def test_refusing_the_long_press_does_not_cost_the_rest_of_the_mode():
    """Dropped individually, like any bad action - a mode is not thrown away
    over one binding the parser will not take."""
    config, _ = parse_with_warnings(_mode(
        short_press={"action": "log", "event": "play"},
        long_press={"action": "log", "event": "marker"},
    ))
    assert config.modes[0].behavior.actions["short_press"].event == "play"


def test_a_mode_bound_only_to_long_press_is_skipped_rather_than_stranding_you():
    """Nothing left after the refusal, so there is no surface to open."""
    config, warnings = parse_with_warnings({"modes": [{
        "name": "Trap", "template": "control", "activation": {"type": "manual"},
        "long_press": {"action": "log", "event": "marker"},
    }]})
    assert warnings
    assert not any(m.name == "Trap" for m in config.modes)


# --- the editor agrees -----------------------------------------------------


def _control_descriptor() -> str:
    block = SCHEMA_JS[SCHEMA_JS.index("  type: 'control',"):]
    return block[:block.index("\n});")]


def test_the_editor_offers_exactly_the_gestures_the_parser_accepts():
    """Drift here is the worst kind for this template: an editor offering the
    long press would let someone bind their own exit away and watch it vanish
    on save."""
    offered = re.search(r"gestures: \[([^\]]*)\]", _control_descriptor())
    assert offered
    keys = set(re.findall(r"'([^']+)'", offered.group(1)))
    assert keys == {"short_press", "double_tap", "triple_tap", "tap_5"}
    assert "long_press" not in keys


def test_the_editor_calls_it_a_takeover_started_by_a_gesture():
    descriptor = _control_descriptor()
    assert "nature: 'takeover'" in descriptor
    assert "startedBy: 'gesture'" in descriptor
    assert "allowedActivations: ['manual']" in descriptor
    assert "'control'" in SCHEMA_JS[SCHEMA_JS.index("const TAKEOVER_TEMPLATES"):
                                    SCHEMA_JS.index("]);")]


def test_the_editor_default_parses():
    """"Add a control surface" has to produce something the parser keeps."""
    body = _control_descriptor()
    body = body[body.index("defaults: () => ({"):body.index("startedBy:")]
    event = re.search(r"event: '([^']+)'", body)
    assert event
    config = parse_config(_mode(short_press={"action": "log", "event": event.group(1)}))
    assert config.modes[0].behavior.actions


@pytest.mark.parametrize("gesture,note", [
    ("short_press", 94),   # Play
    ("double_tap", 95),    # Record
    ("triple_tap", 93),    # Stop
    ("tap_5", 84),         # Marker
])
def test_the_daw_preset_binds_the_transport_where_it_says(gesture, note):
    """Record must not be the easiest gesture to fire by accident, and the
    marker must not be on the long press - that is the way out."""
    block = SCHEMA_JS[SCHEMA_JS.index("id: 'daw_transport'"):]
    block = block[:block.index("id: 'footswitch_midi'")]
    assert "template: 'control'" in block
    found = re.search(rf"{gesture}: \{{[^}}]*number: (\d+)", block, re.S)
    assert found and int(found.group(1)) == note
    assert "long_press" not in block


# --- the driver ------------------------------------------------------------


def _modes(**gestures) -> list[dict]:
    surface = {
        "name": "DAW", "template": "control", "activation": {"type": "manual"},
        "log_as": "daw",
    }
    surface.update(gestures)
    return [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "DAW"}},
        surface,
    ]


async def _start(tmp_path, modes):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "sounds_enabled": False, "web_enabled": False,
        "database_path": str(tmp_path / "events.db"), "modes": modes,
    }), encoding="utf-8")
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(config)])
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


def _logged(tmp_path, name):
    store = EventStore(str(tmp_path / "events.db"))
    try:
        return [n for (_t, _k, n, _d, _m, _v) in store.recent(50) if n == name]
    finally:
        store.close()


THREE = {
    "short_press": {"action": "log", "event": "play"},
    "double_tap": {"action": "log", "event": "record"},
    "triple_tap": {"action": "log", "event": "stop"},
}


async def test_it_stays_open_across_several_commands(tmp_path):
    """The difference between this and an ambient actions mode: you opened it
    to send several things, so it does not drop back after the first."""
    task, device = await _start(tmp_path, _modes(**THREE))
    try:
        await _press(device, TriggerType.LONG_PRESS)    # enter
        await _press(device, TriggerType.SHORT_PRESS)   # play
        await _press(device, TriggerType.DOUBLE_TAP)    # record
        await _press(device, TriggerType.TRIPLE_TAP)    # stop
        # Pressed faster than the confirmation flash, which is the realistic
        # case for a transport control. Nothing may be lost - the presses queue
        # and the loop works through them - so this waits for the queue rather
        # than pacing the presses to suit the animation.
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 4)
        assert _logged(tmp_path, "play") and _logged(tmp_path, "record")
        assert _logged(tmp_path, "stop")
    finally:
        await _stop(task)


async def test_commands_pressed_faster_than_the_flash_are_not_lost(tmp_path):
    """The property the test above leans on, said out loud: the confirmation
    is a latency choice, not a lockout. Ten presses, all of them counted."""
    task, device = await _start(tmp_path, _modes(
        short_press={"action": "log", "event": "play"},
    ))
    try:
        await _press(device, TriggerType.LONG_PRESS)
        for _ in range(10):
            device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 12)
        assert len(_logged(tmp_path, "play")) == 10
    finally:
        await _stop(task)


async def test_each_gesture_fires_its_own_command(tmp_path):
    task, device = await _start(tmp_path, _modes(**THREE))
    try:
        await _press(device, TriggerType.LONG_PRESS)
        await _press(device, TriggerType.DOUBLE_TAP)
        assert _logged(tmp_path, "record")
        assert not _logged(tmp_path, "play")   # and nothing else came along
    finally:
        await _stop(task)


async def test_a_long_press_leaves(tmp_path):
    """The invariant, driven rather than asserted about the parser."""
    task, device = await _start(tmp_path, _modes(**THREE))
    try:
        await _press(device, TriggerType.LONG_PRESS)   # enter
        await _press(device, TriggerType.LONG_PRESS)   # leave
        assert device.led_state is LEDState.IDLE
        # ...and the ambient layer has the button back, so long press re-enters.
        await _press(device, TriggerType.SHORT_PRESS)
        assert not _logged(tmp_path, "play")
    finally:
        await _stop(task)


async def test_an_unbound_gesture_keeps_the_surface_open(tmp_path):
    """Mistiming a tap must not throw you out of the app - the one thing worse
    than the command not firing is having to walk back in."""
    task, device = await _start(tmp_path, _modes(
        short_press={"action": "log", "event": "play"},
    ))
    try:
        await _press(device, TriggerType.LONG_PRESS)   # enter
        await _press(device, TriggerType.TRIPLE_TAP)   # nothing bound here
        await _press(device, TriggerType.SHORT_PRESS)  # still open
        assert _logged(tmp_path, "play")
    finally:
        await _stop(task)


# --- branching ------------------------------------------------------------
# Four gestures per page is tight; four gestures per page and a branch on any
# of them is a tree. This is what makes a menu of menus cost no new template.


def _tree(return_after=True) -> list[dict]:
    return [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "Menu"}},
        {"name": "Menu", "template": "control", "activation": {"type": "manual"},
         "short_press": {"action": "enter_mode", "target": "Mix"},
         "double_tap": {"action": "log", "event": "menu_thing"},
         "return_after": return_after},
        {"name": "Mix", "template": "control", "activation": {"type": "manual"},
         "short_press": {"action": "log", "event": "mix_thing"}},
    ]


async def test_a_gesture_can_open_another_control_surface(tmp_path):
    """`enter_mode` is not something `execute()` can do - it has no idea what a
    mode is - so the loop has to intercept it the way handle() does."""
    task, device = await _start(tmp_path, _tree())
    try:
        await _press(device, TriggerType.LONG_PRESS)   # Home -> Menu
        await _press(device, TriggerType.SHORT_PRESS)  # Menu -> Mix
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        await _press(device, TriggerType.SHORT_PRESS)  # fires inside Mix
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        assert _logged(tmp_path, "mix_thing")
    finally:
        await _stop(task)


async def test_leaving_a_branch_returns_to_the_page_that_opened_it(tmp_path):
    """The reason `return_after` exists: without it a long press out of a
    sub-page would drop you all the way home, so the gesture would mean "up one
    level" or "up two" depending how deep you had gone."""
    task, device = await _start(tmp_path, _tree(return_after=True))
    try:
        await _press(device, TriggerType.LONG_PRESS)   # Home -> Menu
        await _press(device, TriggerType.SHORT_PRESS)  # Menu -> Mix
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        await _press(device, TriggerType.LONG_PRESS)   # leave Mix
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        # Back on Menu, so Menu's own binding answers again.
        await _press(device, TriggerType.DOUBLE_TAP)
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        assert _logged(tmp_path, "menu_thing")
    finally:
        await _stop(task)


async def test_return_after_off_drops_straight_out(tmp_path):
    task, device = await _start(tmp_path, _tree(return_after=False))
    try:
        await _press(device, TriggerType.LONG_PRESS)   # Home -> Menu
        await _press(device, TriggerType.SHORT_PRESS)  # Menu -> Mix
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        await _press(device, TriggerType.LONG_PRESS)   # leave Mix -> home
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        assert device.led_state is LEDState.IDLE
        # Menu's binding must NOT answer - we are on the ambient layer now.
        await _press(device, TriggerType.DOUBLE_TAP)
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        assert not _logged(tmp_path, "menu_thing")
    finally:
        await _stop(task)


async def test_a_branch_to_a_mode_that_is_not_there_keeps_the_page_open(tmp_path):
    """Targets are resolved at runtime on purpose (config order is not
    dependency order), so a typo must not strand you on a dead page."""
    task, device = await _start(tmp_path, [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "Menu"}},
        {"name": "Menu", "template": "control", "activation": {"type": "manual"},
         "short_press": {"action": "enter_mode", "target": "Nope"},
         "double_tap": {"action": "log", "event": "menu_thing"}},
    ])
    try:
        await _press(device, TriggerType.LONG_PRESS)   # Home -> Menu
        await _press(device, TriggerType.SHORT_PRESS)  # branch to nothing
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        await _press(device, TriggerType.DOUBLE_TAP)   # still on Menu
        await asyncio.sleep(main._CONTROL_CONFIRM_S * 2)
        assert _logged(tmp_path, "menu_thing")
    finally:
        await _stop(task)


def test_return_after_defaults_to_on_and_round_trips():
    config = parse_config(_mode())
    assert config.modes[0].behavior.return_after is True
    off = parse_config(_mode(return_after=False))
    assert off.modes[0].behavior.return_after is False
    assert as_dict(off)["modes"][0]["return_after"] is False


async def test_only_commands_that_were_sent_are_counted(tmp_path):
    """`log_as` writes one row per command that actually went, so an unbound
    gesture does not inflate the count."""
    task, device = await _start(tmp_path, _modes(
        short_press={"action": "log", "event": "play"},
    ))
    try:
        await _press(device, TriggerType.LONG_PRESS)
        await _press(device, TriggerType.SHORT_PRESS)
        await _press(device, TriggerType.TRIPLE_TAP)  # unbound
        assert len(_logged(tmp_path, "daw")) == 1
    finally:
        await _stop(task)
