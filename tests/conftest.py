"""Makes the `firmware/` tree importable, so the ESP32 code is testable here.

Those modules ship to a device where every file sits flat at the filesystem
root and imports its neighbours by bare name (`import protocol`). To
exercise that code on the host it has to be importable the same way, so the
firmware directory goes on sys.path rather than becoming a package: adding
an __init__.py to satisfy pytest would change what runs on the device. It is
appended, not prepended, so nothing here can shadow a real dependency.

This runs at collection time (not as a fixture) so the test modules can use
plain top-level imports.

Only the hardware-free modules import cleanly on the host - that is
deliberate: led.py and buzzer.py keep their `machine` imports inside the
backend constructors precisely so the animation and tone logic can be
tested off-device. firmware/main.py needs `aioble` and is not imported
here; the bleak probe in tools/ is its acceptance test.
"""

import sys
from pathlib import Path

FIRMWARE = Path(__file__).resolve().parent.parent / "firmware"

if str(FIRMWARE) not in sys.path:
    sys.path.append(str(FIRMWARE))
