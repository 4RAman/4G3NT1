"""Visual LED test — run ON the Pi:

    cd /home/pi/aibutton && .venv/bin/python device_tests/test_led.py

Expected sequence:
  IDLE      5 s   slow blue breathe (~3 s cycle)
  LISTENING 3 s   solid yellow
  THINKING  3 s   fast white pulse (~0.5 s cycle)
  SUCCESS   4 s   solid green 2 s, then back to blue breathe
  ERROR     4 s   three red flashes, then back to blue breathe
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from aibutton.led import LEDController, LEDState  # noqa: E402


async def main() -> None:
    led = LEDController()
    plan = [
        (LEDState.IDLE, 5),
        (LEDState.LISTENING, 3),
        (LEDState.THINKING, 3),
        (LEDState.SUCCESS, 4),
        (LEDState.ERROR, 4),
    ]
    for state, seconds in plan:
        print(f"{state.value} for {seconds}s")
        led.set_state(state)
        await asyncio.sleep(seconds)
    led.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
