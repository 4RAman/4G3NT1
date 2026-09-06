"""The Signal template - the first app whose point is to persist.

Two presets ride on one machine (a status light and an OSC footswitch), so
most of what is worth asserting is that the machine does not care which: it
cycles positions, holds the one it is on, and fires whatever `Action` that
position happens to carry.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import (
    OscAction,
    SignalBehavior,
    WebhookAction,
    as_dict,
    parse_config,
    parse_with_warnings,
)
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore


def _modes(states, **over):
    return [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "tap_4": {"action": "enter_mode", "target": "Sign"}},
        {"name": "Sign", "template": "signal", "activation": {"type": "manual"},
         "states": states, **over},
    ]


THREE = [
    {"name": "Free", "color": "#00ff00"},
    {"name": "Heads-down", "color": "#ff8800"},
    {"name": "On air", "color": "#ff0000", "style": "breathe"},
]


# --- parsing ---------------------------------------------------------------


def test_a_position_may_carry_any_action_primitive():
    """The reason this template is cheap: it does not know what a webhook or
    an OSC message is, and the next primitive works here for free."""
    cfg = parse_config({"modes": _modes([
        {"name": "A", "color": "#ffffff",
         "action": {"action": "webhook", "url": "https://example.test/x"}},
        {"name": "B", "color": "#000000",
         "action": {"action": "osc", "host": "127.0.0.1", "port": 9000,
                    "address": "/b"}},
    ])})
    states = next(m for m in cfg.modes if m.name == "Sign").behavior.states
    assert isinstance(states[0].action, WebhookAction)
    assert isinstance(states[1].action, OscAction)


def test_a_position_with_no_action_is_a_light_and_nothing_else():
    cfg = parse_config({"modes": _modes(THREE)})
    states = next(m for m in cfg.modes if m.name == "Sign").behavior.states
    assert [s.action for s in states] == [None, None, None]


def test_a_broken_message_costs_the_message_not_the_position():
    """A status light whose webhook has a typo should still light up."""
    cfg, warnings = parse_with_warnings({"modes": _modes([
        {"name": "A", "color": "#ffffff", "action": {"action": "webhook", "url": "nope"}},
    ])})
    states = next(m for m in cfg.modes if m.name == "Sign").behavior.states
    assert len(states) == 1 and states[0].name == "A"
    assert states[0].action is None
    assert warnings


def test_a_nameless_position_is_skipped_and_the_rest_survive():
    cfg, warnings = parse_with_warnings({"modes": _modes([
        {"name": "A", "color": "#ffffff"},
        {"color": "#00ff00"},
        {"name": "C", "color": "#0000ff"},
    ])})
    states = next(m for m in cfg.modes if m.name == "Sign").behavior.states
    assert [s.name for s in states] == ["A", "C"]
    assert warnings


def test_a_signal_with_nothing_usable_falls_back_rather_than_vanishing():
    """The one shape that would take over the button and then do nothing."""
    cfg, warnings = parse_with_warnings({"modes": _modes([{"color": "#ffffff"}])})
    behavior = next(m for m in cfg.modes if m.name == "Sign").behavior
    assert behavior.states == SignalBehavior().states
    assert warnings


def test_an_out_of_range_start_falls_back_to_the_first_position():
    cfg, warnings = parse_with_warnings({"modes": _modes(THREE, start_at=9)})
    assert next(m for m in cfg.modes if m.name == "Sign").behavior.start_at == 0
    assert warnings


def test_a_signal_round_trips_through_the_editor():
    raw = {"modes": _modes([
        {"name": "Stop", "color": "#ff0000", "style": "solid"},
        {"name": "Play", "color": "#00ff00", "style": "breathe",
         "action": {"action": "osc", "host": "10.0.0.2", "port": 9000,
                    "address": "/play", "args": [1]}},
    ], start_at=1, log_as="deck")}
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


# --- the driver ------------------------------------------------------------


async def _start(tmp_path, modes):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "sounds_enabled": False, "web_enabled": False,
        "database_path": str(tmp_path / "events.db"), "modes": modes,
    }), encoding="utf-8")
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


async def test_it_opens_on_a_position_without_announcing_it(tmp_path):
    """Walking up to your own desk should not send anything."""
    task, device = await _start(tmp_path, _modes(THREE, log_as="status"))
    try:
        await _press(device, TriggerType.TAP_4)  # enter
        assert device.led_effect.color == "#00ff00"
        store = EventStore(str(tmp_path / "events.db"))
        try:
            assert not [
                n for (_t, _k, n, _d, _m, _v) in store.recent(50) if n == "status"
            ]
        finally:
            store.close()
    finally:
        await _stop(task)


async def test_a_press_moves_on_and_stays_there(tmp_path):
    task, device = await _start(tmp_path, _modes(THREE))
    try:
        await _press(device, TriggerType.TAP_4)   # enter -> Free
        await _press(device, TriggerType.SHORT_PRESS)  # -> Heads-down
        assert device.led_effect.color == "#ff8800"
        await asyncio.sleep(0.3)  # and it is still there a moment later
        assert device.led_effect.color == "#ff8800"
        assert device.led_state is LEDState.LISTENING
    finally:
        await _stop(task)


async def test_the_positions_wrap_around(tmp_path):
    task, device = await _start(tmp_path, _modes(THREE))
    try:
        await _press(device, TriggerType.TAP_4)
        for _ in range(3):
            await _press(device, TriggerType.SHORT_PRESS)
        assert device.led_effect.color == "#00ff00"
    finally:
        await _stop(task)


async def test_a_position_carries_its_own_style(tmp_path):
    task, device = await _start(tmp_path, _modes(THREE))
    try:
        await _press(device, TriggerType.TAP_4)
        await _press(device, TriggerType.SHORT_PRESS)
        await _press(device, TriggerType.SHORT_PRESS)  # On air, breathing
        assert device.led_effect.style == "breathe"
    finally:
        await _stop(task)


async def test_each_change_can_be_logged_with_its_position(tmp_path):
    task, device = await _start(tmp_path, _modes(THREE, log_as="status"))
    try:
        await _press(device, TriggerType.TAP_4)
        await _press(device, TriggerType.SHORT_PRESS)
        await _press(device, TriggerType.SHORT_PRESS)
        store = EventStore(str(tmp_path / "events.db"))
        try:
            values = [
                v for (_t, _k, n, _d, _m, v) in store.recent(50) if n == "status"
            ]
        finally:
            store.close()
        assert sorted(values) == [1.0, 2.0]
    finally:
        await _stop(task)


async def test_long_press_releases_the_button(tmp_path):
    """The escape from an app that otherwise holds the foreground forever."""
    task, device = await _start(tmp_path, _modes(THREE))
    try:
        await _press(device, TriggerType.TAP_4)
        await _press(device, TriggerType.LONG_PRESS)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


async def test_a_double_tap_resends_without_moving(tmp_path):
    task, device = await _start(tmp_path, _modes(THREE, log_as="status"))
    try:
        await _press(device, TriggerType.TAP_4)
        await _press(device, TriggerType.SHORT_PRESS)  # -> Heads-down, logged
        await _press(device, TriggerType.DOUBLE_TAP)   # same place, sent again
        assert device.led_effect.color == "#ff8800"
        store = EventStore(str(tmp_path / "events.db"))
        try:
            values = [
                v for (_t, _k, n, _d, _m, v) in store.recent(50) if n == "status"
            ]
        finally:
            store.close()
        # A re-send is not a change, so it does not write a second row.
        assert values == [1.0]
    finally:
        await _stop(task)
