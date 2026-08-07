"""Button trigger detection: short press, long press, double tap.

**This is the firmware spec, not host runtime code.** Gesture timing runs
on the ESP32 - a 0.4 s double-tap window would not survive BLE notification
jitter - so the host receives finished gestures on a ButtonDevice
([device.py](device.py)) and never sees raw edges. TriggerDetector stays
here as the reference implementation the MicroPython port follows, with
[test_trigger_detector.py](../tests/test_trigger_detector.py) as its spec
vectors: it is pure and timestamp-driven, so both sides can be checked
against the same cases.

Timing rules
------------
- long_press fires *while held*, as soon as the hold reaches 1.0 s
  (better feedback than waiting for release); the release is consumed.
- double_tap fires on the second press when two press-starts are
  < 0.4 s apart.
- short_press is press+release < 1.0 s. Emission is delayed until the
  double-tap window (press start + 0.4 s) closes so a second tap can
  upgrade it; if the press itself outlives the window, it emits
  immediately on release. Worst-case added latency: 0.4 s.

Debounce (50 ms) is the firmware's job, as is calling on_timeout() at the
deadline on_release() hands back.
"""

from __future__ import annotations

import logging

from .device import TriggerType

log = logging.getLogger(__name__)

DEBOUNCE_S = 0.05
HOLD_S = 1.0
DOUBLE_WINDOW_S = 0.4
_EPSILON = 1e-6  # guards float jitter when a timer fires exactly on its deadline


class TriggerDetector:
    """Pure state machine; every method takes a monotonic timestamp.

    The caller must invoke on_timeout(now) at (or after) the deadline
    returned by on_release(). Stale timeouts are harmless - they no-op
    once the pending press has been resolved.
    """

    def __init__(self) -> None:
        self._press_t: float | None = None
        self._ignore_current = False  # press already consumed by hold/double-tap
        self._pending_press_t: float | None = None  # short press awaiting its window

    def on_press(self, t: float) -> TriggerType | None:
        if (
            self._pending_press_t is not None
            and (t - self._pending_press_t) < DOUBLE_WINDOW_S
        ):
            self._pending_press_t = None
            self._press_t = t
            self._ignore_current = True  # second tap: its hold/release are spoken for
            return TriggerType.DOUBLE_TAP
        # A pending press older than the window has already been emitted by
        # the timer (timers fire before later button events on the loop).
        self._pending_press_t = None
        self._press_t = t
        self._ignore_current = False
        return None

    def on_hold(self, t: float) -> TriggerType | None:
        if self._ignore_current or self._press_t is None:
            return None
        self._ignore_current = True  # consume the upcoming release
        return TriggerType.LONG_PRESS

    def on_release(self, t: float) -> tuple[TriggerType | None, float | None]:
        """Returns (event, timeout_deadline)."""
        press_t, self._press_t = self._press_t, None
        if self._ignore_current:
            self._ignore_current = False
            return None, None
        if press_t is None:  # release without a recorded press (startup glitch)
            return None, None
        duration = t - press_t
        if duration >= HOLD_S:
            return TriggerType.LONG_PRESS, None  # safety net if the hold event was missed
        if duration >= DOUBLE_WINDOW_S:
            # No second press can start inside the window anymore - emit now.
            return TriggerType.SHORT_PRESS, None
        self._pending_press_t = press_t
        return None, press_t + DOUBLE_WINDOW_S

    def on_timeout(self, t: float) -> TriggerType | None:
        if self._pending_press_t is None:
            return None
        if (t - self._pending_press_t) >= DOUBLE_WINDOW_S - _EPSILON:
            self._pending_press_t = None
            return TriggerType.SHORT_PRESS
        return None
