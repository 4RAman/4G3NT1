"""BLE central-side test — run on this Windows PC (or any laptop/phone-adjacent
machine with Bluetooth) while the AI Button service runs on the Pi:

    pip install bleak
    python central_test/ble_central.py            # finds "AIButton"
    python central_test/ble_central.py MyButton   # custom device name

Subscribes to STATUS and RESPONSE characteristics. STATUS prints on every
state change; RESPONSE chunks are reassembled until the EOT (0x04) marker,
then printed as the full AI answer. Press the physical button and watch.
Ctrl+C to exit.
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner

STATUS_CHAR_UUID = "f3641401-00b0-4240-ba50-05ca45bf8abc"
RESPONSE_CHAR_UUID = "f3641402-00b0-4240-ba50-05ca45bf8abc"
EOT = 0x04


async def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "AIButton"
    print(f"scanning for {name!r} ...")
    device = await BleakScanner.find_device_by_name(name, timeout=15.0)
    if device is None:
        print("not found — is the service running and advertising?")
        sys.exit(1)
    print(f"found {device.address}, connecting ...")

    response_buf = bytearray()

    def on_status(_, data: bytearray) -> None:
        print(f"[STATUS] {data.decode('utf-8', errors='replace')}")

    def on_response(_, data: bytearray) -> None:
        if len(data) == 1 and data[0] == EOT:
            print(f"[RESPONSE] {response_buf.decode('utf-8', errors='replace')}")
            response_buf.clear()
        else:
            response_buf.extend(data)

    async with BleakClient(device) as client:
        await client.start_notify(STATUS_CHAR_UUID, on_status)
        await client.start_notify(RESPONSE_CHAR_UUID, on_response)
        print("subscribed — press the button on the Pi (Ctrl+C to exit)")
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
