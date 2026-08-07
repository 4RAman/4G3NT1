"""Talk to the ESP32 firmware by hand, without running the app.

    python tools/ble_probe.py            # connect, print gestures, take commands
    python tools/ble_probe.py --cycle    # connect, walk every LED state + tone, exit

Press the button and gestures print as they arrive; type a state or sound
name and the device shows it. The first thing to reach for when the button
is behaving oddly, since it isolates the firmware from everything else.

It deliberately imports the protocol tables from aibutton.device rather
than restating them: if this talks to the firmware, so does BLEDevice -
they encode through the same code path.

Needs `bleak` (in requirements-dev.txt) and a machine with BLE.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakClient, BleakScanner  # noqa: E402

from aibutton.device import (  # noqa: E402
    BUTTON_EVENT_UUID,
    GESTURE_BY_CODE,
    LED_CODES,
    LED_STATE_UUID,
    SOUND_CMD_UUID,
    SOUND_CODES,
    STOP_LOOP_CMD,
    LEDState,
    Sound,
    sound_command,
)

DEFAULT_NAME = "AIButton"
SCAN_TIMEOUT_S = 10.0

_LED_BY_NAME = {state.value.lower(): state for state in LEDState}
_SOUND_BY_NAME = {sound.value: sound for sound in Sound}


def _on_gesture(_sender, data: bytearray) -> None:
    if not data:
        print("  <- empty notification")
        return
    trigger = GESTURE_BY_CODE.get(data[0])
    if trigger is None:
        print(f"  <- unknown gesture code 0x{data[0]:02x}")
    else:
        print(f"  <- {trigger.value}")


async def _find(name: str):
    print(f"scanning for {name!r} ...")
    device = await BleakScanner.find_device_by_name(name, timeout=SCAN_TIMEOUT_S)
    if device is None:
        print(
            f"not found. Is it powered and advertising? "
            f"(the name comes from firmware/hardware.py's DEVICE_NAME)"
        )
    return device


async def _set_led(client: BleakClient, state: LEDState) -> None:
    await client.write_gatt_char(LED_STATE_UUID, bytes([LED_CODES[state]]), response=True)
    print(f"  -> LED {state.value}")


async def _play(client: BleakClient, sound: Sound, *, loop: bool = False) -> None:
    await client.write_gatt_char(SOUND_CMD_UUID, sound_command(sound, loop=loop), response=True)
    print(f"  -> {'loop' if loop else 'play'} {sound.value}")


async def _stop(client: BleakClient) -> None:
    await client.write_gatt_char(SOUND_CMD_UUID, bytes([STOP_LOOP_CMD]), response=True)
    print("  -> stop loop")


async def cycle(client: BleakClient) -> None:
    """Every LED state and every tone, slowly enough to watch and hear."""
    for state in LEDState:
        await _set_led(client, state)
        await asyncio.sleep(3)
    for sound in Sound:
        await _play(client, sound)
        await asyncio.sleep(2)
    await _play(client, Sound.ALARM, loop=True)
    print("  (alarm looping for 6s)")
    await asyncio.sleep(6)
    await _stop(client)
    await _set_led(client, LEDState.IDLE)


# `error` and `success` name both an LED state and a tone, so sounds need
# the `play`/`loop` verb rather than a bare word - otherwise one of the two
# meanings would be unreachable from here.
HELP = """
commands:
  {leds}
      set the LED state
  play <sound>   play a tone once      ({sounds})
  loop <sound>   repeat a tone until `stop` (default alarm)
  stop           silence a looping tone
  cycle          run through every state and tone
  quit           disconnect and exit
press the button at any time; gestures print as they arrive.
""".strip()


async def interactive(client: BleakClient) -> None:
    print(HELP.format(
        leds="  ".join(sorted(_LED_BY_NAME)), sounds="  ".join(sorted(_SOUND_BY_NAME))
    ))
    while True:
        # to_thread keeps the notification callbacks running while we block
        # on input - otherwise gestures would only print between commands.
        line = (await asyncio.to_thread(input, "> ")).strip().lower()
        if not line:
            continue
        command, _, argument = line.partition(" ")
        try:
            if command in ("quit", "exit", "q"):
                return
            if command in _LED_BY_NAME:
                await _set_led(client, _LED_BY_NAME[command])
            elif command in ("play", "loop"):
                name = argument.strip()
                sound = _SOUND_BY_NAME.get(name, Sound.ALARM if not name else None)
                if sound is None:
                    print(f"  ? unknown sound {name!r}")
                else:
                    await _play(client, sound, loop=command == "loop")
            elif command == "stop":
                await _stop(client)
            elif command == "cycle":
                await cycle(client)
            else:
                print(f"  ? unknown command {command!r}")
        except Exception as exc:  # noqa: BLE001 - keep the session alive
            print(f"  ! {type(exc).__name__}: {exc}")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poke the AI Button firmware over BLE")
    parser.add_argument("--name", default=DEFAULT_NAME, help="advertised device name")
    parser.add_argument(
        "--cycle", action="store_true", help="run every LED state and tone, then exit"
    )
    args = parser.parse_args(argv)

    device = await _find(args.name)
    if device is None:
        return 1

    print(f"connecting to {device.address} ...")
    async with BleakClient(device) as client:
        await client.start_notify(BUTTON_EVENT_UUID, _on_gesture)
        print("connected. Subscribed to gestures.")
        if args.cycle:
            await cycle(client)
        else:
            await interactive(client)
        await client.stop_notify(BUTTON_EVENT_UUID)
    print("disconnected.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
