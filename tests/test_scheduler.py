from datetime import datetime, time

from aibutton.config import (
    ActionsBehavior,
    AlwaysActivation,
    LogAction,
    Mode,
    NoticeBehavior,
    ScheduleActivation,
)
from aibutton.scheduler import due_alarm, occurrence_key


def alarm(name, at_, days=None, **fields):
    return Mode(
        name=name,
        activation=ScheduleActivation(at=at_, days=days),
        behavior=NoticeBehavior(**fields),
    )


def at(hour, minute=0, second=0, day=15):  # 2026-06-15 is a Monday
    return datetime(2026, 6, day, hour, minute, second)


WAKE = alarm("Wake up", time(7, 0), message="Wake up")


def test_fires_at_the_occurrence_minute():
    result = due_alarm((WAKE,), at(7, 0), set())
    assert result is not None
    mode, key = result
    assert mode.name == "Wake up"
    assert key == "Wake up@2026-06-15T07:00"


def test_fires_within_the_60s_window():
    # The half-open minute window absorbs the loop's <=1s tick.
    assert due_alarm((WAKE,), at(7, 0, 0), set()) is not None
    assert due_alarm((WAKE,), at(7, 0, 59), set()) is not None


def test_not_due_before_the_minute():
    assert due_alarm((WAKE,), at(6, 59, 59), set()) is None


def test_not_due_after_the_window():
    assert due_alarm((WAKE,), at(7, 1, 0), set()) is None


def test_does_not_refire_when_key_already_fired():
    fired = {occurrence_key("Wake up", at(7, 0), time(7, 0))}
    assert due_alarm((WAKE,), at(7, 0, 30), fired) is None


def test_respects_days():
    weekday_alarm = alarm("Weekday", time(7, 0), days=frozenset({0, 1, 2, 3, 4}))
    # 2026-06-15 is Monday (in days), 2026-06-20 is Saturday (not).
    assert due_alarm((weekday_alarm,), at(7, 0, day=15), set()) is not None
    assert due_alarm((weekday_alarm,), at(7, 0, day=20), set()) is None


def test_days_none_fires_every_day():
    assert due_alarm((WAKE,), at(7, 0, day=20), set()) is not None  # Saturday


def test_ignores_non_alarm_and_non_schedule_modes():
    ambient = Mode(
        name="Ambient",
        activation=AlwaysActivation(),
        behavior=ActionsBehavior(actions={"short_press": LogAction(event="x")}),
    )
    assert due_alarm((ambient,), at(7, 0), set()) is None


def test_first_due_alarm_wins_in_config_order():
    a = alarm("A", time(7, 0))
    b = alarm("B", time(7, 0))
    mode, _ = due_alarm((a, b), at(7, 0), set())
    assert mode.name == "A"


def test_distinct_keys_per_day():
    k1 = occurrence_key("Wake up", at(7, 0, day=15), time(7, 0))
    k2 = occurrence_key("Wake up", at(7, 0, day=16), time(7, 0))
    assert k1 != k2
    # Yesterday's fire doesn't block today's occurrence.
    assert due_alarm((WAKE,), at(7, 0, day=16), {k1}) is not None
