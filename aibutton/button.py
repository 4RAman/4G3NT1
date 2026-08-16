"""Button trigger detection: N taps and a long press.

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
- a burst of taps is presses less than 0.4 s apart. It emits as soon as it
  reaches `max_taps` - nothing longer is being listened for - and otherwise
  when the window closes with no further tap.
- so at max_taps=2, the default, this is what it has always been: a double
  tap fires the instant the second press lands, and a single tap waits out
  the window to prove it is not a double. Worst-case latency: 0.4 s.

`max_taps` is host state the device is told (`device.max_taps_for`), not a
preference: counting to three costs the double tap its instant response, so
it is paid only by a button that has a triple tap bound to something.

Debounce (50 ms) is the firmware's job, as is calling on_timeout() at the
deadline on_release() hands back.
"""

from __future__ import annotations

import logging

from .device import DEFAULT_MAX_TAPS, MAX_TAPS, TAP_TRIGGERS, TriggerType

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

    def __init__(self, max_taps: int = DEFAULT_MAX_TAPS) -> None:
        self._press_t: float | None = None
        self._ignore_current = False  # press already consumed by hold/burst
        self._pending_press_t: float | None = None  # last tap awaiting its window
        self._taps = 0  # taps in the burst, the current one included
        self._max_taps = DEFAULT_MAX_TAPS
        self.set_max_taps(max_taps)

    def set_max_taps(self, count: int) -> None:
        """How long a tap burst to look for. Abandons any burst in progress:
        the answer to "how many taps was that" just changed, so counting one
        under the old setting and finishing it under the new one would emit a
        gesture neither setting describes."""
        self._max_taps = max(DEFAULT_MAX_TAPS, min(count, MAX_TAPS))
        self._taps = 0
        self._pending_press_t = None

    def _burst(self) -> TriggerType | None:
        """Emit the burst so far and start a new one."""
        count, self._taps = self._taps, 0
        return TAP_TRIGGERS.get(count)

    def on_press(self, t: float) -> TriggerType | None:
        if (
            self._pending_press_t is not None
            and (t - self._pending_press_t) < DOUBLE_WINDOW_S
        ):
            self._pending_press_t = None
            self._press_t = t
            self._taps += 1
            if self._taps >= self._max_taps:
                # The longest burst anything is listening for. Waiting for the
                # window to close could only produce a gesture nothing binds.
                self._ignore_current = True  # its hold/release are spoken for
                return self._burst()
            self._ignore_current = False
            return None
        # A pending press older than the window has already been emitted by
        # the timer (timers fire before later button events on the loop).
        self._pending_press_t = None
        self._press_t = t
        self._taps = 1
        self._ignore_current = False
        return None

    def on_hold(self, t: float) -> TriggerType | None:
        if self._ignore_current or self._press_t is None:
            return None
        self._ignore_current = True  # consume the upcoming release
        self._taps = 0  # a hold ends the burst rather than counting in it
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
            self._taps = 0
            return TriggerType.LONG_PRESS, None  # safety net if the hold event was missed
        if duration >= DOUBLE_WINDOW_S:
            # The window opened at press start and has already closed, so no
            # further tap can join this burst - emit it now.
            return self._burst(), None
        self._pending_press_t = press_t
        return None, press_t + DOUBLE_WINDOW_S

    def on_timeout(self, t: float) -> TriggerType | None:
        if self._pending_press_t is None:
            return None
        if (t - self._pending_press_t) >= DOUBLE_WINDOW_S - _EPSILON:
            self._pending_press_t = None
            return self._burst()
        return None
