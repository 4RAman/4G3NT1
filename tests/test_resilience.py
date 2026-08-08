"""The service survives things that used to end it.

Three separate guarantees, all of them about staying up rather than about
being correct: the run loop outlives a component that raises, the event log
degrades to memory instead of refusing to start, and a second copy of the
service is refused rather than left to fight the first one over the radio.
"""

import asyncio
import json

import pytest

import aibutton.main as main
import aibutton.scheduler as scheduler
import aibutton.store as store_mod
from aibutton.device import MockDevice, TriggerType
from aibutton.main import FaultTracker
from aibutton.single_instance import AlreadyRunning, SingleInstance
from aibutton.store import EventStore

CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {
            "name": "Default",
            "template": "actions",
            "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "ping"},
        }
    ],
}


# --- the fault throttle ------------------------------------------------
#
# Pure, so it is exercised directly rather than through a running loop.


def test_first_fault_logs_and_the_flood_behind_it_does_not():
    tracker = FaultTracker(interval_s=60.0)
    assert tracker.record(1000.0) is True
    assert [tracker.record(1000.0 + n) for n in (0.1, 1, 30, 59)] == [False] * 4
    assert tracker.record(1060.0) is True
    # Every fault is still counted, even the ones that were not logged.
    assert tracker.count == 6


def test_a_fault_after_a_long_quiet_period_logs_again():
    tracker = FaultTracker(interval_s=10.0)
    tracker.record(0.0)
    assert tracker.record(9.9) is False
    assert tracker.record(10.0) is True


# --- the run loop ------------------------------------------------------


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def test_a_scheduler_that_raises_does_not_take_the_service_down(
    tmp_path, monkeypatch
):
    """due_alarm() runs every tick outside handle()'s own guard, so before the
    backstop existed one raise there ended the process. The button has to keep
    answering presses across the failure and after it clears."""
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(CONFIG, database_path=str(db_path))), encoding="utf-8"
    )

    calls = {"n": 0}
    real_due_alarm = scheduler.due_alarm

    def exploding_due_alarm(modes, now, fired):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("scheduler blew up")
        return real_due_alarm(modes, now, fired)

    monkeypatch.setattr(scheduler, "due_alarm", exploding_due_alarm)
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    # Ticks (and so the post-fault backoff) run fast enough to test.
    monkeypatch.setattr(main, "_SCHEDULER_TICK_S", 0.02)

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    try:
        # Long enough for every exploding tick to have been survived.
        await asyncio.sleep(0.5)
        assert not run_task.done(), "the run loop died on a scheduler fault"
        assert calls["n"] > 3, "the faults never cleared"

        device.press(TriggerType.SHORT_PRESS)
        await _drain(device.events)
        await asyncio.sleep(0.2)
        assert not run_task.done()
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    # The press was handled despite the faults around it.
    store = EventStore(str(db_path))
    try:
        names = [name for (_ts, _kind, name, _dur, _mode, _val) in store.recent(100)]
    finally:
        store.close()
    assert "ping" in names


# --- the event log -----------------------------------------------------


def test_an_unopenable_database_degrades_to_memory_instead_of_refusing_to_start(
    tmp_path, monkeypatch
):
    """Pressing the button still has to do something when the disk does not.
    History is lost, the button is not."""
    real_connect = store_mod._connect

    def refuse_disk(path):
        if path != store_mod._MEMORY:
            raise OSError("disk is on fire")
        return real_connect(path)

    monkeypatch.setattr(store_mod, "_connect", refuse_disk)

    store = EventStore(str(tmp_path / "events.db"))
    try:
        assert store.degraded is True
        store.log_event("ping")
        assert store.count_today("ping") == 1
    finally:
        store.close()


def test_a_healthy_database_is_not_reported_as_degraded(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    try:
        assert store.degraded is False
    finally:
        store.close()


# The web UI's view of a degraded log is asserted in test_webui.py, next to
# the rest of the /api/status contract and its fixtures.


# --- one process per button --------------------------------------------


def test_a_second_instance_is_refused_while_the_first_holds_the_lock(tmp_path):
    lock = tmp_path / "events.lock"
    first = SingleInstance(lock)
    first.acquire()
    try:
        with pytest.raises(AlreadyRunning):
            SingleInstance(lock).acquire()
    finally:
        first.release()


def test_the_lock_is_available_again_once_the_holder_releases_it(tmp_path):
    lock = tmp_path / "events.lock"
    with SingleInstance(lock):
        pass
    second = SingleInstance(lock)
    second.acquire()  # must not raise
    second.release()


def test_the_refusal_names_the_process_to_stop(tmp_path):
    import os

    lock = tmp_path / "events.lock"
    first = SingleInstance(lock)
    first.acquire()
    try:
        with pytest.raises(AlreadyRunning, match=str(os.getpid())):
            SingleInstance(lock).acquire()
    finally:
        first.release()


def test_a_broken_lock_path_runs_unguarded_rather_than_blocking_startup(tmp_path):
    """The guard protecting against a rare operator error must never be the
    reason the button will not start."""
    # A path whose parent is a file, so neither mkdir nor open can succeed.
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    guard = SingleInstance(blocker / "events.lock")
    guard.acquire()  # logs a warning, does not raise
    guard.release()
