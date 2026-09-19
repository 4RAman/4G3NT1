"""Scheduled-alarm firing: which takeover mode is due *right now*.

The run loop wakes at least once a second (see main.py) and asks this pure
function whether any alarm mode's scheduled occurrence has arrived. Reading
time through the injected `now` (the device's Clock) means the web UI's test
clock drives schedules too - set 06:59 and a 07:00 alarm fires seconds
later - and keeps this unit-testable with no async, GPIO, or wall clock.

Not every takeover mode is scheduled. Stopwatch, counter, pomodoro, metronome
and countdown use `manual` activation and are reached only via an enter_mode
action - never auto-fired here.

**What makes a mode scheduled is its activation, not its behaviour.** So the
scan matches `ScheduleActivation` and lets the *parser* decide which templates
may carry one (`_ALLOWED_ACTIVATIONS` in config.py) - which is why a new
scheduled template costs nothing here, where a `due_<template>` per template
would have been the same twenty lines with one isinstance swapped. `due_alarm`
takes an optional filter for the one caller that cares which kind it got.

A scheduled mode is **due** when:

* `now`'s weekday is in the activation's `days` (or `days` is None - every
  day), and
* `now` falls in the half-open minute window [occurrence, occurrence + 60s)
  for the current occurrence of the activation, and
* that occurrence's clock time is inside the activation's `between` window (or
  there is no window), and
* that occurrence's stable key is not already in `fired`.

The 60-second window absorbs the loop's <=1s tick: the alarm still fires even
if the loop happens to wake a few hundred ms after the exact minute. The key
(`name@YYYY-MM-DDTHH:MM`) is per-occurrence, so each scheduled time fires
once; the caller records it in `fired` and prunes the set to today's keys.

**Recurrence and its window are one feature, and shipping either alone would
have been a mistake** (TODO 106). `every: 'hour'` turns the one daily
occurrence into twenty-four, and `between: ["08:00", "22:00"]` is what keeps
the other nine from happening at 3 AM. Both are optional and both default to
off, so an activation with neither behaves exactly as it did before they
existed - which is the property `test_hour_chime.py` pins first.

**This module still knows nothing about wall clocks or apps.** It is handed
`now` and answers a question about it, which is why the web UI's test clock
drives an hourly chime as readily as a 7 AM alarm, and why nothing here needs
a mock.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .config import Mode, NoticeBehavior, ScheduleActivation

# Behaviours a ScheduleActivation may fire. Kept as a tuple rather than
# "anything with a schedule" so a template that acquires a schedule by
# accident (a parser bug, a hand-edited scene) cannot be started by a clock
# without someone deciding it should be. One entry since TODO 84 merged
# AlarmBehavior/ReminderBehavior into NoticeBehavior.
SCHEDULED_BEHAVIORS = (NoticeBehavior,)

# How long after the scheduled minute an occurrence stays "due" if not yet
# fired - wide enough to survive the run loop's <=1s recompute tick.
_FIRE_WINDOW = timedelta(seconds=60)


def occurrence_key(mode_name: str, occ: datetime, at) -> str:
    """Stable per-occurrence id: `name@YYYY-MM-DDTHH:MM`. Used to dedupe
    fires (in `fired`) and to prune the set to today's keys.

    `at` is the occurrence's *own* clock time, not the activation's `at` - the
    two are the same thing for a once-a-day schedule and deliberately are not
    for an hourly one, where twenty-four occurrences share one `at` and each
    needs its own key or the day's first chime would suppress the rest.
    """
    return f"{mode_name}@{occ.date().isoformat()}T{at.strftime('%H:%M')}"


def _in_window(now: time, start: time, end: time) -> bool:
    """Is `now` inside [start, end)? A window whose end is not after its start
    crosses midnight - 22:00-06:00 is the evening and the small hours, not the
    empty set.

    Restated from `rules._in_window` rather than imported, the same call
    `readout._pulses` makes about `sequencer._digit_pulses`: that name is
    private to another pure module, and four lines is cheaper than reaching
    into someone else's underscore. The two are a mirrored table in CLAUDE.md's
    sense, so `test_hour_chime.py` pins the midnight-crossing case here as
    `test_rules.py` already does there.
    """
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def current_occurrence(activation: ScheduleActivation, now: datetime) -> datetime | None:
    """The one occurrence of `activation` that could possibly be due at `now`,
    or None if there is none.

    **There is only ever one candidate, and that is what keeps this cheap.**
    Occurrences are at least an hour apart and `_FIRE_WINDOW` is a minute, so
    at most one of them can contain `now` - no list to build, no scan.

    * with no `every`, it is today's occurrence at `at`, exactly as before;
    * with `every='hour'`, it is *this hour's*, at `at`'s minute past it. The
      hour in `at` is not used: an hourly schedule happens on every hour, and
      which hours are wanted is what `between` says. `config` warns when a
      config sets both in a way that suggests someone expected otherwise.

    None comes back when the candidate falls outside `between` - the window is
    tested on the occurrence's own clock time rather than on `now`, so a chime
    at 21:59 is inside a 08:00-22:00 window even if the loop asks about it at
    22:00:00 and change.
    """
    if activation.every == "hour":
        occ = now.replace(minute=activation.at.minute, second=0, microsecond=0)
    else:
        occ = now.replace(
            hour=activation.at.hour,
            minute=activation.at.minute,
            second=0,
            microsecond=0,
        )
    if activation.between is not None and not _in_window(
        occ.time(), *activation.between
    ):
        return None
    return occ


def due_alarm(
    modes: tuple[Mode, ...],
    now: datetime,
    fired: set[str],
    kinds: tuple[type, ...] = SCHEDULED_BEHAVIORS,
) -> tuple[Mode, str] | None:
    """First scheduled mode (config order) whose today's occurrence is due and
    not yet in `fired`, returned with its occurrence key. None if nothing is
    due. The caller records the key, runs it, and prunes `fired` to today.

    Config order decides, which means an alarm listed above a reminder wins a
    tie at the same minute. That is the right way round - the alarm is the one
    you cannot ignore - but it is a property of how the list is written, so say
    it out loud rather than leaving it to be discovered.

    An hourly schedule (TODO 106) is the same scan: `current_occurrence` hands
    back this hour's instead of today's, and everything downstream - the fire
    window, the key, the dedupe - is unchanged, because an hour chime is
    twenty-four ordinary occurrences rather than a second kind of schedule.
    """
    for mode in modes:
        if not isinstance(mode.behavior, kinds):
            continue
        if not isinstance(mode.activation, ScheduleActivation):
            continue
        activation = mode.activation
        if activation.days is not None and now.weekday() not in activation.days:
            continue
        occ = current_occurrence(activation, now)
        if occ is None:
            continue  # outside its `between` window
        if not (occ <= now < occ + _FIRE_WINDOW):
            continue
        # The occurrence's own time, not the activation's - see `occurrence_key`.
        key = occurrence_key(mode.name, occ, occ.time())
        if key in fired:
            continue
        return mode, key
    return None
