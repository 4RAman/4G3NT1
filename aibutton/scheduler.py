"""Scheduled-alarm firing: which takeover mode is due *right now*.

The run loop wakes at least once a second (see main.py) and asks this pure
function whether any alarm mode's scheduled occurrence has arrived. Reading
time through the injected `now` (the device's Clock) means the web UI's test
clock drives schedules too - set 06:59 and a 07:00 alarm fires seconds
later - and keeps this unit-testable with no async, GPIO, or wall clock.

Only alarm modes are scheduled. Stopwatch and counter are takeover modes too,
but they use `manual` activation and are reached only via an enter_mode action
- never auto-fired here - so this scan matches AlarmBehavior + ScheduleActivation
alone and ignores everything else.

An alarm mode (an AlarmBehavior paired with a ScheduleActivation) is **due**
when:

* `now`'s weekday is in the activation's `days` (or `days` is None - every
  day), and
* `now` falls in the half-open minute window [occurrence, occurrence + 60s)
  for today's occurrence at the activation's `at` time, and
* that occurrence's stable key is not already in `fired`.

The 60-second window absorbs the loop's <=1s tick: the alarm still fires even
if the loop happens to wake a few hundred ms after the exact minute. The key
(`name@YYYY-MM-DDTHH:MM`) is per-occurrence, so each scheduled time fires
once; the caller records it in `fired` and prunes the set to today's keys.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import AlarmBehavior, Mode, ScheduleActivation

# How long after the scheduled minute an occurrence stays "due" if not yet
# fired - wide enough to survive the run loop's <=1s recompute tick.
_FIRE_WINDOW = timedelta(seconds=60)


def occurrence_key(mode_name: str, occ: datetime, at) -> str:
    """Stable per-occurrence id: `name@YYYY-MM-DDTHH:MM`. Used to dedupe
    fires (in `fired`) and to prune the set to today's keys."""
    return f"{mode_name}@{occ.date().isoformat()}T{at.strftime('%H:%M')}"


def due_alarm(
    modes: tuple[Mode, ...],
    now: datetime,
    fired: set[str],
) -> tuple[Mode, str] | None:
    """First alarm mode (config order) whose today's occurrence is due and
    not yet in `fired`, returned with its occurrence key. None if nothing is
    due. The caller records the key, rings, and prunes `fired` to today."""
    for mode in modes:
        if not isinstance(mode.behavior, AlarmBehavior):
            continue
        if not isinstance(mode.activation, ScheduleActivation):
            continue
        activation = mode.activation
        if activation.days is not None and now.weekday() not in activation.days:
            continue
        occ = now.replace(
            hour=activation.at.hour,
            minute=activation.at.minute,
            second=0,
            microsecond=0,
        )
        if not (occ <= now < occ + _FIRE_WINDOW):
            continue
        key = occurrence_key(mode.name, occ, activation.at)
        if key in fired:
            continue
        return mode, key
    return None
