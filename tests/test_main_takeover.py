"""End-to-end-ish driving of aibutton.main.run for the Phase 2 takeover
modes: a Default actions mode whose gestures enter_mode into a stopwatch and
into a counter, then drive those takeovers and assert the store side effects.

run() owns the button listener, so we patch ButtonListener with a fake that
exposes a queue we control. Presses are fed one at a time and we wait for each
to be consumed before feeding the next, so the run loop and the takeover
handlers (which read the same queue directly) see them in order without races.
The AI/BLE/web are all off (--mock --no-ble --no-web), sounds are disabled.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.button import TriggerType
from aibutton.store import EventStore


class _FakeListener:
    """Stands in for ButtonListener: just a queue + close()."""

    def __init__(self):
        self.events: asyncio.Queue = asyncio.Queue()

    def close(self):
        pass


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

    listener = _FakeListener()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)

    args = main._parse_args(["--mock", "--no-ble", "--no-web", "--config", str(cfg_path)])

    # Patch ButtonListener (imported inside run()) to our fake.
    import aibutton.button as button_mod
    monkeypatch.setattr(button_mod, "ButtonListener", lambda *a, **k: listener)

    run_task = asyncio.create_task(main.run(args))
    await asyncio.sleep(0.1)  # let run() reach the main loop

    async def feed(trigger: TriggerType):
        listener.events.put_nowait(trigger)
        await _drain(listener.events)
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

    kinds_names = [(kind, name) for (_ts, kind, name, _dur) in rows]

    # Stopwatch: exactly one timer_start + one timer_stop for "focus", plus a
    # lap log row.
    assert kinds_names.count(("timer_start", "focus")) == 1
    assert kinds_names.count(("timer_stop", "focus")) == 1
    assert kinds_names.count(("log", "focus_lap")) == 1

    # Counter: two "water" log rows (one per increment).
    assert kinds_names.count(("log", "water")) == 2
