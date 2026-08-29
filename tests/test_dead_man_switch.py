"""An alarm that fires an action because it was *not* answered (TODO 44).

Driven through `aibutton.main.run` with the clock parked on the alarm's
minute, the way the reminder tests do it: the interesting behaviour is a
branch of the ring loop, and a branch of a loop is not something a dataclass
test can reach.
"""

import asyncio
import json
from datetime import datetime

import pytest

import aibutton.main as main
from aibutton import config
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

AT = "07:00"
GRACE_MIN = 0.05  # three seconds; long enough to answer, short enough to test


def _config(db_path, **overrides):
    alarm = {
        "name": "Check in",
        "template": "alarm",
        "activation": {"type": "schedule", "at": AT},
        "message": "Still there?",
        "dismiss_event": "checkin",
        "grace_minutes": GRACE_MIN,
        "on_timeout": {"action": "log", "event": "nobody_answered"},
    }
    alarm.update(overrides)
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "database_path": str(db_path),
        "modes": [alarm],
    }


async def _ring(tmp_path, monkeypatch, **overrides):
    """Start the service with the clock on the alarm's minute; return once it
    is ringing."""
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(_config(db_path, **overrides)), encoding="utf-8")

    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    hour, minute = (int(part) for part in AT.split(":"))
    monkeypatch.setattr(
        main.Clock, "now",
        lambda self: datetime.now().replace(hour=hour, minute=minute, second=1,
                                            microsecond=0),
    )
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if device.led_state is LEDState.ALERT:
            break
    return task, device, db_path


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _events(db_path):
    """(name, value) pairs, newest first. `recent` yields
    (ts, kind, name, duration_s, mode, value) tuples."""
    store = EventStore(str(db_path))
    try:
        return [(row[2], row[5]) for row in store.recent(20)]
    finally:
        store.close()


async def test_answering_in_time_runs_nothing(tmp_path, monkeypatch):
    """The switch is armed and stays unfired - the ordinary case, and the one
    that must not cry wolf."""
    task, device, db_path = await _ring(tmp_path, monkeypatch)
    device.press(TriggerType.SHORT_PRESS)
    await asyncio.sleep(0.4)
    await _stop(task)

    names = [name for name, _ in _events(db_path)]
    assert "nobody_answered" not in names
    assert ("checkin", 1.0) in _events(db_path), "an answered alarm logs a 1"


async def test_going_unanswered_fires_the_action(tmp_path, monkeypatch):
    """The whole point: nobody pressed, so something else has to happen."""
    task, device, db_path = await _ring(tmp_path, monkeypatch)
    await asyncio.sleep(GRACE_MIN * 60 + 0.6)  # let the grace period lapse
    await _stop(task)

    events = _events(db_path)
    names = [name for name, _ in events]
    assert "nobody_answered" in names, "the timeout action never ran"
    assert ("checkin", 0.0) in events, "an unanswered alarm logs a 0"


async def test_it_stops_ringing_once_it_has_given_up(tmp_path, monkeypatch):
    """An unanswered alarm that keeps ringing after raising the alert is noise
    on top of the thing it already did."""
    task, device, db_path = await _ring(tmp_path, monkeypatch)
    await asyncio.sleep(GRACE_MIN * 60 + 0.6)
    state = device.led_state
    await _stop(task)
    assert state is LEDState.IDLE


async def test_without_a_grace_period_it_rings_exactly_as_before(tmp_path, monkeypatch):
    """`grace_minutes: 0` is today's alarm, unchanged - the switch is opt-in."""
    task, device, db_path = await _ring(
        tmp_path, monkeypatch, grace_minutes=0, on_timeout=None,
    )
    await asyncio.sleep(0.6)  # far longer than any grace would have been
    still_ringing = device.led_state
    device.press(TriggerType.SHORT_PRESS)
    await asyncio.sleep(0.3)
    await _stop(task)

    assert still_ringing is LEDState.ALERT, "an alarm with no grace gave up"
    assert "nobody_answered" not in [name for name, _ in _events(db_path)]


def test_a_timeout_with_no_action_is_not_warned_about_any_more(caplog):
    """TODO 84 made outcome logging unconditional: a timeout with no
    `on_missed` action still logs a 0 under the mode's own name, so "nothing
    will happen if this alarm goes unanswered" stopped being true - it always
    logs *something* now, which is exactly the point of making it automatic."""
    config.parse_config({"modes": [{
        "name": "Armed but silent", "template": "alarm",
        "activation": {"type": "schedule", "at": AT}, "grace_minutes": 5,
    }]})
    assert not any("on_missed" in r.getMessage() or "on_timeout" in r.getMessage()
                   for r in caplog.records)


def test_an_action_with_no_timeout_is_still_warned_about(caplog):
    """The other half is still a real misconfiguration: an `on_missed` that
    can never fire, because the switch never gives up."""
    config.parse_config({"modes": [{
        "name": "Wired but never", "template": "alarm",
        "activation": {"type": "schedule", "at": AT},
        "on_timeout": {"action": "log", "event": "x"},
    }]})
    assert any("never fire" in r.getMessage() for r in caplog.records)


def test_the_switch_survives_the_serialiser():
    """What the editor saves has to parse back to what it saved."""
    original = config.parse_config(_config("x.db"))
    again = config.parse_config(config.as_dict(original))
    before = next(m for m in original.modes if m.name == "Check in").behavior
    after = next(m for m in again.modes if m.name == "Check in").behavior
    assert after == before
