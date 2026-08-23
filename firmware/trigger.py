# Gesture detection: N taps and a long press.
#
# A port of TriggerDetector from aibutton/button.py, which is the spec. The
# algorithm is unchanged line for line; only the Python dialect differs (no enum
# - events are the host's TriggerType *values*, the strings that
# protocol.gesture_payload turns into wire bytes - and no type hints).
#
# tests/test_trigger_port.py drives this class and the host's through the same
# event scripts and requires identical output at every step. Fix a timing bug in
# one and you must fix it in the other, or that test fails.
#
# Timing rules
# ------------
# - long_press fires *while held*, as soon as the hold reaches 1.0 s (better
#   feedback than waiting for release); the release is consumed.
# - a burst of taps is presses less than 0.4 s apart. It emits as soon as it
#   reaches `max_taps` - there is nothing longer to wait for - and otherwise
#   when the window closes with no further tap.
#
# What max_taps costs, and why the host sets it rather than a config. At 2, the
# default and what an unconfigured button does, this is the behaviour it has
# always had: a double tap fires the instant the second press lands, and only a
# single waits out the window to prove it is not a double (worst-case added
# latency 0.4 s). Counting to 3 means a double tap can no longer fire on contact
# either - it has to outlive the window to prove it is not the start of a
# triple. That is a real change in how the button feels, so it is paid only by a
# button that has a triple bound to something: the host derives max_taps from
# the config and writes it over GESTURE_CONFIG (ROADMAP D5).
#
# The caller owns debounce and the clock: main.py debounces the pin and feeds
# seconds that only ever increase (ticks_ms() wraps; a raw ticks_ms()/1000 would
# make the detector emit nonsense every ~12 days).

import protocol

DEBOUNCE_S = 0.05
HOLD_S = 1.0
DOUBLE_WINDOW_S = 0.4
_EPSILON = 1e-6  # guards float jitter when a timer fires exactly on its deadline

SHORT_PRESS = "short_press"
LONG_PRESS = "long_press"
DOUBLE_TAP = "double_tap"
TRIPLE_TAP = "triple_tap"


class TriggerDetector:
    """Pure state machine; every method takes a timestamp in seconds.

    The caller must invoke on_timeout(now) at (or after) the deadline
    returned by on_release(). Stale timeouts are harmless - they no-op
    once the pending press has been resolved.
    """

    def __init__(self, max_taps=protocol.DEFAULT_MAX_TAPS):
        self._press_t = None
        self._ignore_current = False  # press already consumed by hold/burst
        self._pending_press_t = None  # last tap of a burst awaiting its window
        self._taps = 0                # taps in the burst, the current one included
        self._max_taps = protocol.DEFAULT_MAX_TAPS
        self.set_max_taps(max_taps)

    def set_max_taps(self, count):
        """How long a tap burst to look for. Abandons any burst in progress:
        the answer to "how many taps was that" just changed, so counting one
        under the old setting and finishing it under the new one would emit a
        gesture neither setting describes."""
        if count < protocol.DEFAULT_MAX_TAPS:
            count = protocol.DEFAULT_MAX_TAPS
        elif count > protocol.MAX_TAPS_LIMIT:
            count = protocol.MAX_TAPS_LIMIT
        self._max_taps = count
        self._taps = 0
        self._pending_press_t = None

    def _burst(self):
        """Emit the burst so far and start a new one."""
        count = self._taps
        self._taps = 0
        return protocol.TAP_NAMES.get(count)

    def on_press(self, t):
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
        # the poll loop's on_timeout call.
        self._pending_press_t = None
        self._press_t = t
        self._taps = 1
        self._ignore_current = False
        return None

    def on_hold(self, t):
        if self._ignore_current or self._press_t is None:
            return None
        self._ignore_current = True  # consume the upcoming release
        self._taps = 0  # a hold ends the burst rather than counting in it
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
            self._taps = 0
            return LONG_PRESS, None  # safety net if the hold check was missed
        if duration >= DOUBLE_WINDOW_S:
            # The window opened at press start and has already closed, so no
            # further tap can join this burst - emit it now.
            return self._burst(), None
        self._pending_press_t = press_t
        return None, press_t + DOUBLE_WINDOW_S

    def on_timeout(self, t):
        if self._pending_press_t is None:
            return None
        if (t - self._pending_press_t) >= DOUBLE_WINDOW_S - _EPSILON:
            self._pending_press_t = None
            return self._burst()
        return None
