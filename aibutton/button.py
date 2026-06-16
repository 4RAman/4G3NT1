"""Button trigger detection: short press, long press, double tap.

TriggerDetector is a pure, timestamp-driven state machine with no GPIO
dependencies (unit-testable off-device). ButtonListener wires it to a
gpiozero Button and emits TriggerType values on an asyncio.Queue - no
callbacks into business logic.

Timing rules
------------
- long_press fires *while held*, as soon as the hold reaches 1.0 s
  (better feedback than waiting for release); the release is consumed.
- Taps are counted into a "chord": consecutive quick presses whose
  starts are each < 0.4 s apart. The chord resolves once the window
  after the last tap closes (or, for a single tap that outlives the
  window, immediately on release):
    1 tap  -> short_press
    2 taps -> double_tap
    5 taps -> quintuple_tap (the global on/off + takeover-escape gesture),
              emitted immediately on the 5th press so it feels instant
    3 or 4 taps -> nothing (an ambiguous partial chord)
  Worst-case added latency for short/double: 0.4 s.

Debounce (50 ms) is handled by gpiozero's bounce_time.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from gpiozero import Button

log = logging.getLogger(__name__)

DEBOUNCE_S = 0.05
HOLD_S = 1.0
DOUBLE_WINDOW_S = 0.4
QUINTUPLE_TAPS = 5  # taps in a chord that mean "global toggle / escape"
_EPSILON = 1e-6  # guards float jitter when a timer fires exactly on its deadline


class TriggerType(Enum):
    SHORT_PRESS = "short_press"
    LONG_PRESS = "long_press"
    DOUBLE_TAP = "double_tap"
    QUINTUPLE_TAP = "quintuple_tap"


class TriggerDetector:
    """Pure state machine; every method takes a monotonic timestamp.

    Quick presses accumulate into a tap chord (`_count`); the chord resolves
    on on_timeout(now), which the caller must invoke at (or after) the
    deadline returned by on_release(). Stale timeouts are harmless - they
    no-op once the chord has been resolved or superseded.
    """

    def __init__(self) -> None:
        self._press_t: float | None = None  # current press, for duration calc
        self._ignore_current = False  # this press's hold/release already spoken for
        self._count = 0  # taps in the open chord (0 = none pending)
        self._last_press_t = 0.0  # start of the most recent tap in the chord

    def _resolve(self) -> TriggerType | None:
        """Close the chord and map its tap count to a gesture."""
        count, self._count = self._count, 0
        if count == 1:
            return TriggerType.SHORT_PRESS
        if count == 2:
            return TriggerType.DOUBLE_TAP
        if count >= QUINTUPLE_TAPS:
            return TriggerType.QUINTUPLE_TAP  # normally already emitted on press
        return None  # 3 or 4: ambiguous partial chord

    def on_press(self, t: float) -> TriggerType | None:
        if self._count > 0 and (t - self._last_press_t) < DOUBLE_WINDOW_S:
            self._count += 1  # continues the open chord
        else:
            self._count = 1  # starts a fresh chord
        self._last_press_t = t
        self._press_t = t
        self._ignore_current = False
        if self._count >= QUINTUPLE_TAPS:
            # Fire the moment the fifth tap lands; swallow its hold/release and
            # close the chord so the trailing timeouts no-op.
            self._count = 0
            self._ignore_current = True
            return TriggerType.QUINTUPLE_TAP
        return None

    def on_hold(self, t: float) -> TriggerType | None:
        # Only a single sustained press is a long press; a hold after taps is
        # ignored. Consume the upcoming release.
        if self._ignore_current or self._count != 1:
            return None
        self._count = 0
        self._ignore_current = True
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
            self._count = 0
            return TriggerType.LONG_PRESS, None  # safety net if the hold event was missed
        if duration >= DOUBLE_WINDOW_S:
            # This press outlived the inter-tap window, so no later tap can join
            # the chord - resolve it now.
            return self._resolve(), None
        # A quick tap: wait for the window after it to close before resolving.
        return None, self._last_press_t + DOUBLE_WINDOW_S

    def on_timeout(self, t: float) -> TriggerType | None:
        if self._count == 0:
            return None
        if (t - self._last_press_t) >= DOUBLE_WINDOW_S - _EPSILON:
            return self._resolve()
        return None


class ButtonListener:
    """Owns the GPIO button; emits TriggerType values on `.events`.

    Must be constructed inside a running event loop. gpiozero callbacks
    arrive on a background thread and are hopped onto the loop with
    call_soon_threadsafe, so the detector only ever runs on the loop.
    """

    def __init__(self, pin: int = 17):
        self._loop = asyncio.get_running_loop()
        self.events: asyncio.Queue[TriggerType] = asyncio.Queue()
        self._detector = TriggerDetector()
        self._button = Button(
            pin, pull_up=True, bounce_time=DEBOUNCE_S, hold_time=HOLD_S
        )
        self._button.when_pressed = lambda: self._loop.call_soon_threadsafe(self._on_press)
        self._button.when_released = lambda: self._loop.call_soon_threadsafe(self._on_release)
        self._button.when_held = lambda: self._loop.call_soon_threadsafe(self._on_hold)

    def close(self) -> None:
        self._button.close()

    def _emit(self, event: TriggerType | None) -> None:
        if event is not None:
            log.info("button: %s", event.value)
            self.events.put_nowait(event)

    def _on_press(self) -> None:
        self._emit(self._detector.on_press(self._loop.time()))

    def _on_hold(self) -> None:
        self._emit(self._detector.on_hold(self._loop.time()))

    def _on_release(self) -> None:
        now = self._loop.time()
        event, deadline = self._detector.on_release(now)
        self._emit(event)
        if deadline is not None:
            self._loop.call_later(max(0.0, deadline - now), self._on_timeout)

    def _on_timeout(self) -> None:
        self._emit(self._detector.on_timeout(self._loop.time()))
