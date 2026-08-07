# Gesture detection: short press, long press, double tap.
#
# A port of TriggerDetector from aibutton/button.py, which is the spec.
# The algorithm is unchanged line for line; only the Python dialect differs
# (no enum - events are the host's TriggerType *values*, the strings that
# protocol.GESTURE_CODES turns into wire bytes - and no type hints).
#
# tests/test_trigger_port.py drives this class and the host's through the
# same event scripts and requires identical output at every step. Fix a
# timing bug in one and you must fix it in the other, or that test fails.
#
# Timing rules
# ------------
# - long_press fires *while held*, as soon as the hold reaches 1.0 s
#   (better feedback than waiting for release); the release is consumed.
# - double_tap fires on the second press when two press-starts are
#   < 0.4 s apart.
# - short_press is press+release < 1.0 s. Emission is delayed until the
#   double-tap window (press start + 0.4 s) closes so a second tap can
#   upgrade it; if the press itself outlives the window, it emits
#   immediately on release. Worst-case added latency: 0.4 s.
#
# The caller owns debounce and the clock: main.py debounces the pin and
# feeds seconds that only ever increase (ticks_ms() wraps; a raw
# ticks_ms()/1000 would make the detector emit nonsense every ~12 days).

DEBOUNCE_S = 0.05
HOLD_S = 1.0
DOUBLE_WINDOW_S = 0.4
_EPSILON = 1e-6  # guards float jitter when a timer fires exactly on its deadline

SHORT_PRESS = "short_press"
LONG_PRESS = "long_press"
DOUBLE_TAP = "double_tap"


class TriggerDetector:
    """Pure state machine; every method takes a timestamp in seconds.

    The caller must invoke on_timeout(now) at (or after) the deadline
    returned by on_release(). Stale timeouts are harmless - they no-op
    once the pending press has been resolved.
    """

    def __init__(self):
        self._press_t = None
        self._ignore_current = False  # press already consumed by hold/double-tap
        self._pending_press_t = None  # short press awaiting its window

    def on_press(self, t):
        if (
            self._pending_press_t is not None
            and (t - self._pending_press_t) < DOUBLE_WINDOW_S
        ):
            self._pending_press_t = None
            self._press_t = t
            self._ignore_current = True  # second tap: its hold/release are spoken for
            return DOUBLE_TAP
        # A pending press older than the window has already been emitted by
        # the poll loop's on_timeout call.
        self._pending_press_t = None
        self._press_t = t
        self._ignore_current = False
        return None

    def on_hold(self, t):
        if self._ignore_current or self._press_t is None:
            return None
        self._ignore_current = True  # consume the upcoming release
        return LONG_PRESS

    def on_release(self, t):
        """Returns (event, timeout_deadline)."""
        press_t = self._press_t
        self._press_t = None
        if self._ignore_current:
            self._ignore_current = False
            return None, None
        if press_t is None:  # release without a recorded press (startup glitch)
            return None, None
        duration = t - press_t
        if duration >= HOLD_S:
            return LONG_PRESS, None  # safety net if the hold check was missed
        if duration >= DOUBLE_WINDOW_S:
            # No second press can start inside the window anymore - emit now.
            return SHORT_PRESS, None
        self._pending_press_t = press_t
        return None, press_t + DOUBLE_WINDOW_S

    def on_timeout(self, t):
        if self._pending_press_t is None:
            return None
        if (t - self._pending_press_t) >= DOUBLE_WINDOW_S - _EPSILON:
            self._pending_press_t = None
            return SHORT_PRESS
        return None
