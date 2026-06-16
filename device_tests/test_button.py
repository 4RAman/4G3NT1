"""Button trigger test — run ON the Pi:

    cd /home/pi/aibutton && .venv/bin/python device_tests/test_button.py

Try each pattern and watch the printed trigger:
  - quick tap            -> short_press   (arrives ~0.4 s after the tap)
  - hold >= 1 s          -> long_press    (fires while still holding)
  - two quick taps       -> double_tap
Ctrl+C to exit.
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from aibutton.button import ButtonListener  # noqa: E402


async def main() -> None:
    listener = ButtonListener()
    print("listening on GPIO17 — press away (Ctrl+C to exit)")
    try:
        while True:
            event = await listener.events.get()
            print(f"trigger: {event.value}")
    finally:
        listener.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
