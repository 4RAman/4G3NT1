"""Button trigger detection: short press, long press, double tap.

TriggerDetector is a pure, timestamp-driven state machine with no GPIO
dependencies (unit-testable off-device). ButtonListener wires it to a
gpiozero Button and emits TriggerType values on an asyncio.Queue - no
callbacks into business logic.

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
_EPSILON = 1e-6  # guards float jitter when a timer fires exactly on its deadline


class TriggerType(Enum):
    SHORT_PRESS = "short_press"
    LONG_PRESS = "long_press"
    DOUBLE_TAP = "double_tap"


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
