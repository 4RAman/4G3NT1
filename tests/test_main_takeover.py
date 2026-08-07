"""End-to-end-ish driving of aibutton.main.run for the takeover modes: a
Default actions mode whose gestures enter_mode into a stopwatch and into a
counter, then drive those takeovers and assert the store side effects.

run() takes the ButtonDevice, so the test injects a MockDevice and presses
it. Presses are fed one at a time and we wait for each to be consumed before
feeding the next, so the run loop and the takeover handlers (which read the
same queue directly) see them in order without races. The web UI is off
(--no-web) and sounds are disabled.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.device import MockDevice, TriggerType
from aibutton.store import EventStore

CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {
            "name": "Default",
            "template": "actions",
            "activation": {"type": "always"},
            "long_press": {"action": "enter_mode", "target": "Focus"},
            "double_tap": {"action": "enter_mode", "target": "Water"},
            "short_press": {"action": "log", "event": "ping"},
        },
        {
            "name": "Focus",
            "template": "stopwatch",
            "activation": {"type": "manual"},
            "log_as": "focus",
        },
        {
            "name": "Water",
            "template": "counter",
            "activation": {"type": "manual"},
            "event": "water",
        },
    ],
}


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    """Wait until the queue has been emptied (consumed) by the runtime."""
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def test_run_enter_mode_stopwatch_then_counter(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    db_path = tmp_path / "events.db"
    CONFIG_DB = dict(CONFIG, database_path=str(db_path))
    cfg_path.write_text(json.dumps(CONFIG_DB), encoding="utf-8")

    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)

    args = main._parse_args(["--no-web", "--config", str(cfg_path)])

    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)  # let run() reach the main loop

    async def feed(trigger: TriggerType):
        device.press(trigger)
        await _drain(device.events)
        await asyncio.sleep(0.05)  # let the consumer act on it

    try:
        # Stopwatch: long_press enters Focus (starts a timer), short_press is a
        # lap, long_press stops & exits.
        await feed(TriggerType.LONG_PRESS)   # enter_mode -> Focus (timer_start)
        await feed(TriggerType.SHORT_PRESS)  # lap -> log focus_lap
        await feed(TriggerType.LONG_PRESS)   # stop -> timer_stop, exit
        await asyncio.sleep(0.1)

        # Counter: double_tap enters Water, two increments, long_press exits.
        await feed(TriggerType.DOUBLE_TAP)   # enter_mode -> Water
        await feed(TriggerType.SHORT_PRESS)  # +1 -> log water
        await feed(TriggerType.DOUBLE_TAP)   # +1 -> log water
        await feed(TriggerType.LONG_PRESS)   # exit
        await asyncio.sleep(0.1)
    finally:
        # Stop the run loop: SIGTERM isn't wired on Windows, so cancel the task.
        run_task.cancel()
        with pytest.raises((asyncio.CancelledError,)):
            await run_task

    # Inspect the store side effects on the same DB file.
    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
    finally:
        store.close()

    kinds_names = [(kind, name) for (_ts, kind, name, _dur, _mode) in rows]

    # Stopwatch: exactly one timer_start + one timer_stop for "focus", plus a
    # lap log row.
    assert kinds_names.count(("timer_start", "focus")) == 1
    assert kinds_names.count(("timer_stop", "focus")) == 1
    assert kinds_names.count(("log", "focus_lap")) == 1

    # Counter: two "water" log rows (one per increment).
    assert kinds_names.count(("log", "water")) == 2

    # Every row fired while a takeover mode owned the button is attributed to
    # that mode, not left blank.
    modes_by_name = {name: mode for (_ts, _kind, name, _dur, mode) in rows}
    assert modes_by_name["focus"] == "Focus"
    assert modes_by_name["focus_lap"] == "Focus"
    assert modes_by_name["water"] == "Water"

    # Each takeover session logs its own enter/exit lifecycle.
    assert kinds_names.count(("mode_enter", "Focus")) == 1
    assert kinds_names.count(("mode_exit", "Focus")) == 1
    assert kinds_names.count(("mode_enter", "Water")) == 1
    assert kinds_names.count(("mode_exit", "Water")) == 1
