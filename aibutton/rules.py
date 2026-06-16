"""Ambient mode resolution: (gesture, wall-clock time) -> action.

The button is always in some mode. Takeover modes (alarm, stopwatch,
counter) own the button while active and are handled by the scheduler +
main loop, not here; this module covers the *ambient* layer: the
`actions`-template modes that sit quietly and answer gestures.

Ambient modes are evaluated top-to-bottom in config order. A mode is a
candidate when its activation is in scope - `always` always, `window` when
the wall-clock is inside `between` (windows may cross midnight, e.g.
22:00-06:00) and the weekday is in `days` - and, if its actions behaviour
has `unless_logged_today`, that event hasn't already been logged today. The
first candidate that defines the gesture wins; candidates lacking it fall
through, so a time-scoped mode can override just one gesture while Default
keeps handling the rest. This is exactly v0.2's first-match-wins rule
resolution, filtered to ambient modes.

Pure module - no GPIO, no I/O. `logged_today` is injected (typically
EventStore.logged_today) rather than queried here, so this stays unit
testable without a database. Local wall-clock time is intentional:
"between 5 and 7 am" means the Pi's timezone (set it in SETUP.md section 2).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time

from .config import (
    Action,
    ActionsBehavior,
    AlwaysActivation,
    Mode,
    WindowActivation,
)


def _in_window(now: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # window crosses midnight, e.g. 22:00-06:00


def _activation_in_scope(activation, now: datetime) -> bool:
    if isinstance(activation, AlwaysActivation):
        return True
    if isinstance(activation, WindowActivation):
        if activation.between is not None and not _in_window(now.time(), *activation.between):
            return False
        if activation.days is not None and now.weekday() not in activation.days:
            return False
        return True
    return False  # takeover activations (schedule/manual) are not ambient


def resolve(
    modes: tuple[Mode, ...],
    trigger: str,
    now: datetime,
    logged_today: Callable[[str], bool] | None = None,
) -> tuple[Mode, Action] | None:
    """First ambient mode (in config order) whose activation is in scope and
    that defines `trigger`, returned with its action. Takeover modes (alarm,
    stopwatch, counter) are skipped here - alarms fire via the scheduler and
    stopwatch/counter are reached only via an enter_mode action, never by a
    gesture resolving to them directly."""
    for mode in modes:
        if not isinstance(mode.behavior, ActionsBehavior):
            continue  # only ambient actions modes answer gestures
        if not _activation_in_scope(mode.activation, now):
            continue
        unless = mode.behavior.unless_logged_today
        if unless is not None and logged_today is not None and logged_today(unless):
            continue
        action = mode.behavior.actions.get(trigger)
        if action is not None:
            return mode, action
    return None
