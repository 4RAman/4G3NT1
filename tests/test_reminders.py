"""The reminders template: a scheduled nudge that is deliberately not an alarm.

Driven through `main.run` with a MockDevice and the web UI off, the same way
test_main_takeover.py does - the interesting behaviour is in the takeover loop,
and a unit test of the dataclass would assert nothing anyone cares about.

The clock is pushed to the scheduled minute rather than waiting for it, which
is what `Clock` exists for.

TODO 84 merged this template into `NoticeBehavior` (`urgent=False`), alongside
the old alarm template (`urgent=True`) - "reminders" still parses exactly as
before, so every behavioural assertion below still holds unchanged. Only the
dataclass name and the bare-default comparisons (a reminder's own defaults,
not `NoticeBehavior()`'s) needed updating.
"""

import asyncio
import json
from datetime import datetime

import pytest

import aibutton.main as main
from aibutton.config import NoticeBehavior, as_dict, parse_config, parse_with_warnings
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.scheduler import due_alarm
from aibutton.store import EventStore

AT = "07:00"


def _config(db_path, **overrides):
    reminder = {
        "name": "Stretch",
        "template": "reminders",
        "activation": {"type": "schedule", "at": AT},
        "message": "Stand up",
        "cleared_event": "stretched",
        "chime": False,
        "timeout_minutes": 0,
        **overrides,
    }
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "database_path": str(db_path),
        "modes": [reminder],
    }


async def _run_until_firing(tmp_path, monkeypatch, **overrides):
    """Start the service with the clock parked on the reminder's minute, and
    hand back the device once the reminder has taken the button."""
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(_config(db_path, **overrides)), encoding="utf-8")

    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    # The scheduler reads the injected clock, so "it is 07:00" is a fact the
    # test states rather than one it waits for.
    hour, minute = (int(part) for part in AT.split(":"))
    monkeypatch.setattr(
        main.Clock, "now",
        lambda self: datetime.now().replace(hour=hour, minute=minute, second=1,
                                            microsecond=0),
    )

    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    for _ in range(100):  # the loop scans once a second; give it room
        await asyncio.sleep(0.05)
        if device.led_state is LEDState.ALERT:
            break
    return task, device, db_path


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _rows(db_path):
    store = EventStore(str(db_path))
    try:
        return [(kind, name) for (_ts, kind, name, _d, _m, _v) in store.recent(100)]
    finally:
        store.close()


# --- what it does ----------------------------------------------------------

async def test_a_scheduled_reminder_takes_the_button_and_flashes(tmp_path, monkeypatch):
    task, device, _ = await _run_until_firing(tmp_path, monkeypatch)
    try:
        assert device.led_state is LEDState.ALERT
    finally:
        await _stop(task)


async def test_it_does_not_look_like_a_ringing_alarm(tmp_path, monkeypatch):
    """The one thing this template exists for. ALERT is shared with the alarm,
    so what has to differ is the look - and it has to differ by default,
    without anyone naming one."""
    task, device, _ = await _run_until_firing(tmp_path, monkeypatch)
    try:
        assert device.led_effect is not None, "a reminder must push its own look"
        assert device.led_effect.style == "breathe"
    finally:
        await _stop(task)


async def test_it_never_rings(tmp_path, monkeypatch):
    """No looping tone, which is the audible half of not being an alarm."""
    task, device, _ = await _run_until_firing(tmp_path, monkeypatch, chime=True)
    try:
        assert device.looping is None
    finally:
        await _stop(task)


async def test_any_press_clears_it_and_logs(tmp_path, monkeypatch):
    task, device, db_path = await _run_until_firing(tmp_path, monkeypatch)
    try:
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.3)
        assert ("log", "stretched") in _rows(db_path)
    finally:
        await _stop(task)


@pytest.mark.parametrize(
    "trigger",
    [TriggerType.SHORT_PRESS, TriggerType.LONG_PRESS, TriggerType.DOUBLE_TAP],
)
async def test_every_gesture_clears_it(tmp_path, monkeypatch, trigger):
    """A takeover mode must be escapable with a press, and a reminder makes
    that trivially true rather than nominating one gesture."""
    task, device, db_path = await _run_until_firing(tmp_path, monkeypatch)
    try:
        device.press(trigger)
        await asyncio.sleep(0.3)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


async def test_it_gives_up_on_its_own_and_logs_nothing(tmp_path, monkeypatch):
    """A timeout is not a clear - nobody saw it, so nothing happened."""
    task, device, db_path = await _run_until_firing(
        tmp_path, monkeypatch, timeout_minutes=1 / 120,  # half a second
    )
    try:
        await asyncio.sleep(1.0)
        assert ("log", "stretched") not in _rows(db_path)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


async def test_the_session_is_recorded_like_any_other_takeover(tmp_path, monkeypatch):
    task, device, db_path = await _run_until_firing(tmp_path, monkeypatch)
    try:
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.3)
        rows = _rows(db_path)
        assert ("mode_enter", "Stretch") in rows
        assert ("mode_exit", "Stretch") in rows
    finally:
        await _stop(task)


# --- the scheduler ---------------------------------------------------------

def test_the_scheduler_fires_reminders_as_well_as_alarms():
    """Generalised rather than duplicated: what makes a mode scheduled is its
    activation, and the parser already decides which templates may have one."""
    cfg = parse_config({"modes": [{
        "name": "Stretch", "template": "reminders",
        "activation": {"type": "schedule", "at": AT},
    }]})
    now = datetime.now().replace(hour=7, minute=0, second=10, microsecond=0)
    due = due_alarm(cfg.modes, now, set())
    assert due is not None and due[0].name == "Stretch"


def test_a_fired_reminder_does_not_fire_again_that_minute():
    cfg = parse_config({"modes": [{
        "name": "Stretch", "template": "reminders",
        "activation": {"type": "schedule", "at": AT},
    }]})
    now = datetime.now().replace(hour=7, minute=0, second=10, microsecond=0)
    _, key = due_alarm(cfg.modes, now, set())
    assert due_alarm(cfg.modes, now, {key}) is None


# --- the config surface ----------------------------------------------------

def test_a_reminder_may_only_be_scheduled():
    """It has no gesture that reaches it, so a manual one would be a mode you
    could never start."""
    _, warnings = parse_with_warnings({"modes": [{
        "name": "Stretch", "template": "reminders",
        "activation": {"type": "manual"},
    }]})
    assert any("Stretch" in w for w in warnings)


def test_every_field_falls_back_on_its_own():
    """A bad key costs you that key, never the mode."""
    cfg = parse_config({"modes": [{
        "name": "Stretch", "template": "reminders",
        "activation": {"type": "schedule", "at": AT},
        "message": 12, "chime": "yes", "timeout_minutes": -4,
        "cleared_event": "stretched",
    }]})
    behavior = cfg.modes[0].behavior
    assert isinstance(behavior, NoticeBehavior)
    assert behavior.message == ""
    assert behavior.chime is True
    # A reminder's own default (5 minutes), not NoticeBehavior()'s bare
    # default (0, "waits forever") - the two templates disagree here on
    # purpose, which is exactly what the per-template branch in
    # `_parse_notice_body` exists to preserve.
    assert behavior.timeout_minutes == 5.0
    assert behavior.log_as == "stretched"  # the good key survives, under the new name


def test_it_round_trips_through_the_editor():
    raw = {"modes": [{
        "name": "Stretch", "template": "reminders",
        "activation": {"type": "schedule", "at": AT},
        "message": "Stand up", "chime": False, "timeout_minutes": 3.0,
        "cleared_event": "stretched",
    }]}
    once = parse_config(raw)
    assert parse_config(as_dict(once)).modes[0].behavior == once.modes[0].behavior


def test_a_reminder_may_name_a_look_for_the_state_it_owns():
    # A schedule activation is not an ambient Always one, so the config needs
    # its own floor mode for "no warnings" to mean "the look parsed clean".
    cfg, warnings = parse_with_warnings({
        "looks": {"soft-amber": {"style": "breathe", "color": "#ffaa00"}},
        "modes": [{
            "name": "Stretch", "template": "reminders",
            "activation": {"type": "schedule", "at": AT},
            "looks": {"ALERT": "soft-amber"},
        }, {
            "name": "Base", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "x"},
        }],
    })
    assert cfg.modes[0].looks == {"ALERT": "soft-amber"}
    assert not warnings


def test_the_alarm_template_still_behaves_like_an_alarm():
    """Item 11's original instruction was to keep the real alarm clock exactly
    as it was while adding reminders beside it; TODO 84 later merged the two
    into one `NoticeBehavior`, so what has to survive now is alarm's own
    *behaviour* (urgent rendering, snooze) rather than its own class name."""
    cfg = parse_config({"modes": [{
        "name": "Wake", "template": "alarm",
        "activation": {"type": "schedule", "at": "05:00"},
        "snooze_minutes": 9, "dismiss_event": "woke",
    }]})
    behavior = cfg.modes[0].behavior
    assert behavior.template == "notice"  # migrated - the canonical name out
    assert behavior.snooze_minutes == 9
    assert behavior.urgent is True  # an alarm always rings, never breathes
    assert behavior.log_as == "woke"
