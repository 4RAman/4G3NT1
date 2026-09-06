"""Long press at the root means sleep (TODO 104).

Two halves, and they are the same rule seen from either end. The parser half:
an everyday gesture map may no longer bind `long_press`, exactly as a control
surface may not, because "up one level" has to mean one thing everywhere. The
run-loop half: at the ambient layer there is no level above, so the gesture is
answered by the loop itself - the light goes down, the button stops answering,
and the same gesture brings it back.

Sleep here is *host-side quiet mode*, not the device deep sleep of item 29:
the service is awake and everything that does not need a finger keeps running.
That is the property the last test guards, because it is the one a later
change could take away without anything else noticing.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import AppConfig, parse_with_warnings
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

FLOOR = {"name": "Home", "template": "actions", "activation": {"type": "always"}}


# --- the parser half -------------------------------------------------------

def test_binding_the_long_press_is_dropped_with_a_warning():
    cfg, warnings = parse_with_warnings({
        "modes": [{
            **FLOOR,
            "short_press": {"action": "log", "event": "ping"},
            "long_press": {"action": "log", "event": "held"},
        }],
    })
    assert any("long_press" in w for w in warnings)
    assert "long_press" not in cfg.modes[0].behavior.actions


def test_dropping_it_does_not_cost_the_rest_of_the_menu():
    """Dropped, not refused: one stale binding must not take a menu with it."""
    cfg, _ = parse_with_warnings({
        "modes": [{
            **FLOOR,
            "short_press": {"action": "log", "event": "ping"},
            "long_press": {"action": "log", "event": "held"},
        }],
    })
    assert cfg.modes[0].name == "Home"
    assert cfg.modes[0].behavior.actions["short_press"].event == "ping"


def test_a_menu_bound_only_to_the_long_press_is_skipped():
    """Nothing left that can be answered, so the mode goes - and the config
    falls back to the shipped defaults, the same as any other empty menu."""
    cfg, warnings = parse_with_warnings({
        "modes": [{**FLOOR, "long_press": {"action": "log", "event": "held"}}],
    })
    assert cfg.modes == AppConfig().modes
    assert warnings


# --- the run-loop half -----------------------------------------------------

CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {
            "name": "Home", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "ping"},
            "tap_4": {"action": "enter_mode", "target": "Water"},
        },
        {
            "name": "Water", "template": "counter",
            "activation": {"type": "manual"}, "event": "water",
        },
    ],
    "reflexes": [
        {"name": "moisture_low", "then": {"action": "log", "event": "dry"}},
    ],
}


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def _running(tmp_path, monkeypatch, config=CONFIG):
    """run() against a MockDevice, with the queue a reflex arrives on."""
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(config, database_path=str(db_path))), encoding="utf-8"
    )
    device = MockDevice()
    inbound: asyncio.Queue = asyncio.Queue()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device, inbound=inbound))
    await asyncio.sleep(0.1)  # let run() reach the main loop

    async def feed(trigger: TriggerType):
        device.press(trigger)
        await _drain(device.events)
        await asyncio.sleep(0.08)

    return device, task, feed, inbound, db_path


def _rows(db_path):
    store = EventStore(str(db_path))
    try:
        return [(kind, name) for (_ts, kind, name, _d, _m, _v) in store.recent(100)]
    finally:
        store.close()


async def test_a_long_press_sleeps_and_another_one_wakes(tmp_path, monkeypatch):
    """The whole gesture in one script, because it is one gesture: down, then
    nothing answers, then back - and the press that woke it fires nothing."""
    device, task, feed, _inbound, db_path = await _running(tmp_path, monkeypatch)
    try:
        await feed(TriggerType.SHORT_PRESS)  # awake: logs
        await feed(TriggerType.LONG_PRESS)   # -> asleep
        await feed(TriggerType.SHORT_PRESS)  # asleep: ignored entirely
        await feed(TriggerType.TAP_4)        # asleep: no app opened
        await feed(TriggerType.LONG_PRESS)   # -> awake, firing nothing
        await feed(TriggerType.SHORT_PRESS)  # awake again: logs
        await asyncio.sleep(0.1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    rows = _rows(db_path)
    # Two pings, not three: the press made while asleep logged nothing.
    assert rows.count(("log", "ping")) == 2
    # And the four taps that would have opened the counter did not.
    assert ("mode_enter", "Water") not in rows


async def test_going_down_is_visible_and_lands_dark(tmp_path, monkeypatch):
    """Asleep is dark, and the *fade* is what says it was deliberate: a
    crashed button goes out instantly, so a button that goes out slowly has
    already told you which one it is."""
    monkeypatch.setattr(main, "_SLEEP_FADE_S", 0.5)
    device, task, feed, _inbound, _db = await _running(tmp_path, monkeypatch)
    try:
        await feed(TriggerType.LONG_PRESS)
        mid = device.led_effect                 # ~0.1s in: still falling
        assert mid is not None
        assert mid.color != main._STANDBY_COLOR, "the light snapped out"

        await asyncio.sleep(0.8)                # the rest of the fade, and then some
        assert device.led_state is LEDState.IDLE
        assert (device.led_effect.style, device.led_effect.color) == (
            "solid", main._STANDBY_COLOR,
        )

        await feed(TriggerType.LONG_PRESS)      # awake: back to the real IDLE
        assert device.led_state is LEDState.IDLE
        assert (
            device.led_effect is None
            or device.led_effect.color != main._STANDBY_COLOR
        )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_a_sleeping_button_still_answers_the_world(tmp_path, monkeypatch):
    """Quiet mode is the button not answering *you*. A reflex is something out
    there reporting a fact, and a plant that has gone dry has not stopped
    meaning it because nobody is at the desk (item 29 is the half that would
    actually cut power, and it is not this)."""
    device, task, feed, inbound, db_path = await _running(tmp_path, monkeypatch)
    try:
        await feed(TriggerType.LONG_PRESS)   # -> asleep
        inbound.put_nowait(("moisture_low", None))
        await asyncio.sleep(0.3)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert ("log", "dry") in _rows(db_path)
