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
from datetime import datetime, timedelta

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

        # Counter: double_tap enters Water, gestures add their increments,
        # quintuple_tap (the 5-tap escape) exits.
        await feed(TriggerType.DOUBLE_TAP)     # enter_mode -> Water
        await feed(TriggerType.SHORT_PRESS)    # +1  -> log water (count 1)
        await feed(TriggerType.LONG_PRESS)     # +10 -> log water (count 10)
        await feed(TriggerType.QUINTUPLE_TAP)  # exit
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

    # Counter: two "water" log rows (one per increment gesture: +1 and +10).
    assert kinds_names.count(("log", "water")) == 2
    # The +1 and +10 are summed by the count column, not by row inflation.
    store2 = EventStore(str(db_path))
    try:
        assert store2.count_today("water") == 11
    finally:
        store2.close()


POMO_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Pomo"}},
        # A tiny work interval so the work->break transition (and its logged
        # work block) happens within the test instead of in 25 minutes.
        {"name": "Pomo", "template": "pomodoro", "activation": {"type": "manual"},
         "work_minutes": 0.002, "break_minutes": 9, "log_as": "pomo"},
    ],
}


async def _start_run(cfg, tmp_path, monkeypatch):
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(dict(cfg, database_path=str(db_path))), encoding="utf-8")
    listener = _FakeListener()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    import aibutton.button as button_mod
    monkeypatch.setattr(button_mod, "ButtonListener", lambda *a, **k: listener)
    args = main._parse_args(["--mock", "--no-ble", "--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args))
    await asyncio.sleep(0.1)
    return run_task, listener, db_path


async def test_run_pomodoro_logs_work_block_and_exits(tmp_path, monkeypatch):
    run_task, listener, db_path = await _start_run(POMO_CONFIG, tmp_path, monkeypatch)

    async def feed(trigger):
        listener.events.put_nowait(trigger)
        await _drain(listener.events)
        await asyncio.sleep(0.05)

    try:
        await feed(TriggerType.SHORT_PRESS)   # enter Pomo (work countdown starts)
        await asyncio.sleep(0.3)              # let the ~0.12 s work block elapse
        await feed(TriggerType.QUINTUPLE_TAP)  # the 5-tap escape exits
        await asyncio.sleep(0.1)
    finally:
        run_task.cancel()
        with pytest.raises((asyncio.CancelledError,)):
            await run_task

    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
        # one completed work block logged as a timer_stop for "pomo"
        assert sum(1 for (_t, k, n, _d) in rows if k == "timer_stop" and n == "pomo") >= 1
    finally:
        store.close()


PAUSE_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Pomo"}},
        # short_press = start_pause so the same gesture that enters can pause.
        {"name": "Pomo", "template": "pomodoro", "activation": {"type": "manual"},
         "work_minutes": 0.01, "break_minutes": 9, "log_as": "pomo",
         "short_press": "start_pause"},
    ],
}


async def test_pomodoro_pause_freezes_the_countdown(tmp_path, monkeypatch):
    run_task, listener, db_path = await _start_run(PAUSE_CONFIG, tmp_path, monkeypatch)

    async def feed(trigger):
        listener.events.put_nowait(trigger)
        await _drain(listener.events)
        await asyncio.sleep(0.05)

    try:
        await feed(TriggerType.SHORT_PRESS)   # enter Pomo (work countdown runs)
        await feed(TriggerType.SHORT_PRESS)   # start_pause -> pause (freezes)
        await asyncio.sleep(0.8)              # > the 0.6 s work block, but paused
        await feed(TriggerType.QUINTUPLE_TAP)  # exit
        await asyncio.sleep(0.1)
    finally:
        run_task.cancel()
        with pytest.raises((asyncio.CancelledError,)):
            await run_task

    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
        # paused the whole time -> the work block never completed, nothing logged
        assert not any(k == "timer_stop" and n == "pomo" for (_t, k, n, _d) in rows)
    finally:
        store.close()


SLEEP_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "log", "event": "ping"}},
    ],
}


async def test_quintuple_toggles_device_off_and_on(tmp_path, monkeypatch):
    run_task, listener, db_path = await _start_run(SLEEP_CONFIG, tmp_path, monkeypatch)

    async def feed(trigger):
        listener.events.put_nowait(trigger)
        await _drain(listener.events)
        await asyncio.sleep(0.05)

    try:
        await feed(TriggerType.QUINTUPLE_TAP)  # off
        await feed(TriggerType.SHORT_PRESS)    # ignored while off -> no ping
        await feed(TriggerType.QUINTUPLE_TAP)  # on
        await feed(TriggerType.SHORT_PRESS)    # logs ping
        await asyncio.sleep(0.1)
    finally:
        run_task.cancel()
        with pytest.raises((asyncio.CancelledError,)):
            await run_task

    store = EventStore(str(db_path))
    try:
        pings = sum(1 for (_t, k, n, _d) in store.recent(100) if k == "log" and n == "ping")
        assert pings == 1  # only the press made while the device was on
    finally:
        store.close()


async def test_scheduled_alarm_fires_while_off_then_returns_off(tmp_path, monkeypatch):
    """The deliberate choice: turning the device off does NOT silence a
    scheduled alarm (it must still wake you); after dismissal the device
    returns to off, so a following gesture is still ignored."""
    base = datetime.now().replace(second=0, microsecond=0)
    alarm_at = (base + timedelta(minutes=5)).strftime("%H:%M")

    class _FixedClock:
        def __init__(self):
            self._now = base + timedelta(minutes=4)  # a minute before the alarm

        def now(self):
            return self._now

        @property
        def overridden(self):
            return True

        def set(self, target):
            self._now = target

        def clear(self):
            self._now = datetime.now()

    clk = _FixedClock()
    monkeypatch.setattr(main, "Clock", lambda: clk)

    cfg = {
        "sounds_enabled": False,
        "web_enabled": False,
        "modes": [
            {"name": "Wake", "template": "alarm",
             "activation": {"type": "schedule", "at": alarm_at},
             "message": "Wake up", "dismiss_event": "woke_up"},
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "ping"}},
        ],
    }
    run_task, listener, db_path = await _start_run(cfg, tmp_path, monkeypatch)

    async def feed(trigger):
        listener.events.put_nowait(trigger)
        await _drain(listener.events)
        await asyncio.sleep(0.05)

    try:
        await feed(TriggerType.QUINTUPLE_TAP)       # turn the device off
        clk.set(base + timedelta(minutes=5))        # advance to the alarm minute
        await asyncio.sleep(1.4)                     # scheduler tick fires the alarm
        await feed(TriggerType.SHORT_PRESS)         # dismiss -> logs woke_up, back to off
        await feed(TriggerType.SHORT_PRESS)         # ignored: still off -> no ping
        await feed(TriggerType.QUINTUPLE_TAP)       # wake
        await feed(TriggerType.SHORT_PRESS)         # logs ping
        await asyncio.sleep(0.1)
    finally:
        run_task.cancel()
        with pytest.raises((asyncio.CancelledError,)):
            await run_task

    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
        woke = sum(1 for (_t, k, n, _d) in rows if k == "log" and n == "woke_up")
        pings = sum(1 for (_t, k, n, _d) in rows if k == "log" and n == "ping")
        assert woke >= 1   # the alarm rang and was dismissed even though off
        assert pings == 1  # the press right after dismissal was ignored (still off)
    finally:
        store.close()
