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
  for today's occurrence at the activation's `at` time, and
* that occurrence's stable key is not already in `fired`.

The 60-second window absorbs the loop's <=1s tick: the alarm still fires even
if the loop happens to wake a few hundred ms after the exact minute. The key
(`name@YYYY-MM-DDTHH:MM`) is per-occurrence, so each scheduled time fires
once; the caller records it in `fired` and prunes the set to today's keys.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    fires (in `fired`) and to prune the set to today's keys."""
    return f"{mode_name}@{occ.date().isoformat()}T{at.strftime('%H:%M')}"


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
    """
    for mode in modes:
        if not isinstance(mode.behavior, kinds):
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
