"""Non-blocking RGB LED state animations.

Every state is an asyncio coroutine driven at ~20 fps; set_state()
cancels the previous animation task and starts the new one, returning
immediately. gpiozero's RGBLED provides software PWM via the lgpio pin
factory on Bookworm - no RPi.GPIO needed.

Wiring assumption: common-cathode LED (common leg to GND, 330R per
channel). For a common-anode LED pass active_high=False.
"""

from __future__ import annotations

import asyncio
import colorsys
import logging
import math
from enum import Enum

from gpiozero import RGBLED

log = logging.getLogger(__name__)

_FRAME_S = 0.05  # 20 fps - smooth fades, negligible CPU on a Pi 3B+


def _hsv_to_rgb(hue: float, sat: float, val: float) -> tuple[float, float, float]:
    """HSV (each 0..1) -> RGB (each 0..1) for the THINKING rainbow fade."""
    return colorsys.hsv_to_rgb(hue, sat, val)


class LEDState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    ALERT = "ALERT"
    TIMING = "TIMING"
    COUNTING = "COUNTING"


def _log_task_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("LED animation %s crashed: %s", task.get_name(), exc)


class LEDController:
    """Public surface: set_state() (+ close() for shutdown)."""

    def __init__(self, red: int = 18, green: int = 23, blue: int = 24,
                 active_high: bool = True):
        self._led = RGBLED(red=red, green=green, blue=blue, active_high=active_high)
        self._task: asyncio.Task | None = None
        self._animations = {
            LEDState.IDLE: self._idle,
            LEDState.LISTENING: self._listening,
            LEDState.THINKING: self._thinking,
            LEDState.SUCCESS: self._success,
            LEDState.ERROR: self._error,
            LEDState.ALERT: self._alert,
            LEDState.TIMING: self._timing,
            LEDState.COUNTING: self._counting,
        }

    def set_state(self, state: LEDState) -> None:
        """Switch animations. Non-blocking; call from the event loop thread."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.get_running_loop().create_task(
            self._animations[state](), name=f"led-{state.value}"
        )
        self._task.add_done_callback(_log_task_failure)

    def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._led.off()
        self._led.close()

    async def _breathe(self, color: tuple[float, float, float], period_s: float):
        """Sine-fade `color` between off and full, forever."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        r, g, b = color
        while True:
            phase = ((loop.time() - start) % period_s) / period_s
            level = (1 - math.cos(2 * math.pi * phase)) / 2
            self._led.color = (r * level, g * level, b * level)
            await asyncio.sleep(_FRAME_S)

    async def _idle(self):
        await self._breathe((0, 0, 1), period_s=3.0)  # slow blue breathe

    async def _listening(self):
        self._led.color = (1, 1, 0)  # solid yellow
        await asyncio.Event().wait()  # hold until cancelled

    async def _thinking(self):
        """Fast rainbow fade - hue rotates a full turn each cycle while an
        action runs (e.g. asking the AI). At full saturation/value the wheel
        always shows a vivid colour, so "working" reads at a glance."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        period_s = 1.0  # one full hue rotation per second
        while True:
            hue = ((loop.time() - start) % period_s) / period_s
            self._led.color = _hsv_to_rgb(hue, 1.0, 1.0)
            await asyncio.sleep(_FRAME_S)

    async def _success(self):
        self._led.color = (0, 1, 0)
        await asyncio.sleep(2)
        await self._idle()  # auto-return to IDLE

    async def _error(self):
        for _ in range(3):
            self._led.color = (1, 0, 0)
            await asyncio.sleep(0.2)
            self._led.off()
            await asyncio.sleep(0.2)
        await self._idle()

    async def _alert(self):
        """Urgent red/white flash, forever - a ringing alarm mode. Unlike
        _error this never auto-returns to idle; only set_state() (the
        next press dismissing or snoozing it) ends it."""
        while True:
            self._led.color = (1, 0, 0)
            await asyncio.sleep(0.2)
            self._led.color = (1, 1, 1)
            await asyncio.sleep(0.2)

    async def _timing(self):
        """A running stopwatch: a steady teal/cyan pulse, forever. Distinct
        from the slow blue IDLE breathe (it adds the green channel and pulses
        faster) so "a timer is running" reads at a glance. Held until the
        stopwatch stops and set_state() returns the LED to IDLE."""
        await self._breathe((0, 1, 1), period_s=1.6)  # cyan, brisk pulse

    async def _counting(self):
        """An open counter: a magenta breathe, forever. Distinct from the
        IDLE blue and the TIMING cyan (red + blue, no green). Held until the
        counter exits and set_state() returns the LED to IDLE."""
        await self._breathe((1, 0, 1), period_s=2.2)  # magenta breathe
