# AI Button firmware - the ESP32 half of the split.
#
# MicroPython runs this on boot. It does exactly three things:
#
#   1. debounce the button and turn edges into gestures (trigger.py),
#   2. notify each gesture to the connected host,
#   3. run the LED animation and buzzer tone the host writes back.
#
# Everything else - modes, schedules, the event log, the web UI - is the
# Python app on the PC (see ../DESIGN-ESP32.md). Gesture timing lives here
# because a 0.4 s double-tap window would not survive BLE notification
# jitter; the wire carries finished gestures, never raw edges.
#
# Flashing and testing: see README.md in this directory.

import asyncio

import aioble
import bluetooth
import hardware
import protocol
from buzzer import Buzzer
from clock import now_s
from led import LEDController
from trigger import DEBOUNCE_S, HOLD_S, TriggerDetector

# 10 ms is far finer than the 50 ms debounce and the 0.4 s window it feeds,
# and costs nothing on a 240 MHz MCU.
_POLL_S = 0.01
_ADV_INTERVAL_US = 250_000

_service = aioble.Service(bluetooth.UUID(protocol.SERVICE_UUID))
_button_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.BUTTON_EVENT_UUID), read=True, notify=True
)
_led_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.LED_STATE_UUID), write=True, capture=True
)
_sound_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.SOUND_CMD_UUID), write=True, capture=True
)
_palette_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.LED_PALETTE_UUID), write=True, capture=True
)
_effect_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.LED_EFFECT_UUID), write=True, capture=True
)
_gesture_config_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.GESTURE_CONFIG_UUID), write=True, capture=True
)
# Read-only, and filled in once the LED and buzzer are actually constructed -
# see ButtonPeripheral._publish_info.
_info_char = aioble.Characteristic(
    _service, bluetooth.UUID(protocol.DEVICE_INFO_UUID), read=True
)
aioble.register_services(_service)


async def _next_write(characteristic):
    """One write payload. aioble returns (connection, data) when the
    characteristic was declared with capture=True and just the connection
    on older builds - accept both rather than pinning an aioble version."""
    result = await characteristic.written()
    if isinstance(result, tuple):
        return result[1]
    return characteristic.read()


class ButtonPeripheral:
    def __init__(self):
        self.led = LEDController()
        self.buzzer = Buzzer()
        self._detector = TriggerDetector()
        self._connection = None
        self._publish_info()

    def _publish_info(self):
        """Fill in DEVICE_INFO from what actually came up.

        Asked *after* the LED and buzzer are built, not read off hardware.py:
        both degrade to a Null backend when their pin is wrong or the driver
        refuses, and a bit claiming a buzzer nobody can hear is worse than none.
        """
        # Palette rendering and gesture parameters are pure firmware, so this
        # build always has them whatever came up on the pins. CAP_EFFECT is not:
        # an ephemeral look is something you can only be shown.
        capabilities = protocol.CAP_PALETTE | protocol.CAP_GESTURE_PARAMS
        if self.led.usable:
            # Rainbow brightness rides with the LED: it is how this build's
            # renderer reads an effect, so a working LED is the whole condition.
            capabilities |= (
                protocol.CAP_LED | protocol.CAP_EFFECT | protocol.CAP_RAINBOW_LEVEL
            )
        if self.buzzer.usable:
            capabilities |= protocol.CAP_BUZZER
        _info_char.write(protocol.device_info_payload(capabilities))
        # Unpacked into names rather than starred into the format tuple: `%`
        # with `(a, *b, c)` is valid CPython and a SyntaxError on the device, so
        # the host tests cannot catch it and the board silently fails to boot.
        # Keep firmware syntax boring.
        major, minor, patch = protocol.FIRMWARE_VERSION
        print(
            "device: protocol v%d, firmware %d.%d.%d, capabilities 0x%04x"
            % (protocol.PROTOCOL_VERSION, major, minor, patch, capabilities)
        )

    # --- BLE ----------------------------------------------------------

    async def advertise_forever(self):
        """Accept one central at a time, forever. Power-cycling the host (or
        the ESP32) recovers on its own: the connection ends, we re-advertise,
        and the host's BLEDevice reconnects."""
        while True:
            try:
                connection = await aioble.advertise(
                    _ADV_INTERVAL_US,
                    name=hardware.DEVICE_NAME,
                    services=[bluetooth.UUID(protocol.SERVICE_UUID)],
                )
                print("connected:", connection.device)
                self._connection = connection
                await connection.disconnected()
                print("disconnected")
            except Exception as exc:  # noqa: BLE001 - keep trying to be findable
                print("advertise failed:", exc)
                await asyncio.sleep(1)
            finally:
                self._connection = None
                # Nobody is listening for a press now, so nothing can dismiss a
                # ringing alarm: go quiet rather than buzz until the battery dies.
                self.buzzer.stop()
                self.led.set_state(protocol.LED_IDLE)

    async def serve_led(self):
        while True:
            try:
                data = await _next_write(_led_char)
                if data:
                    self.led.set_state(data[0])
            except Exception as exc:  # noqa: BLE001 - one bad write must not end the task
                print("led write failed:", exc)

    async def serve_sound(self):
        while True:
            try:
                data = await _next_write(_sound_char)
                if data:
                    self.buzzer.play(data[0])
            except Exception as exc:  # noqa: BLE001
                print("sound write failed:", exc)

    async def serve_palette(self):
        """One write per LED state: what that state should look like. The host
        sends all of them on connect and re-sends one when you edit it."""
        while True:
            try:
                entry = protocol.decode_palette_entry(await _next_write(_palette_char))
                if entry is None:
                    print("palette: short write - ignored")
                    continue
                self.led.set_effect(*entry)
            except Exception as exc:  # noqa: BLE001
                print("palette write failed:", exc)

    async def serve_effect(self):
        """A look to render right now, belonging to no state. Not stored:
        the next LED_STATE write ends it."""
        while True:
            try:
                effect = protocol.decode_effect(await _next_write(_effect_char))
                if effect is None:
                    print("effect: short write - ignored")
                    continue
                self.led.show_effect(*effect)
            except Exception as exc:  # noqa: BLE001
                print("effect write failed:", exc)

    async def serve_gesture_config(self):
        """How long a tap burst to look for. The host derives it from what it
        binds, so a button with nothing past a double tap keeps the instant
        double tap it has always had."""
        while True:
            try:
                max_taps = protocol.decode_gesture_config(
                    await _next_write(_gesture_config_char)
                )
                if max_taps is None:
                    print("gesture config: empty write - ignored")
                    continue
                self._detector.set_max_taps(max_taps)
                print("gesture config: counting up to", max_taps, "taps")
            except Exception as exc:  # noqa: BLE001
                print("gesture config write failed:", exc)

    def _emit(self, event):
        if event is None:
            return
        payload = protocol.gesture_payload(event)
        if payload is None:  # a gesture with no wire encoding - a bug, not a press
            print("no code for gesture", event)
            return
        print("button:", event)
        if self._connection is None:
            # Presses while disconnected are dropped, not buffered: replaying
            # them later would fire modes against the wrong time of day, and
            # buffering needs a time sync the device does not have.
            return
        try:
            _button_char.notify(self._connection, payload)
        except Exception as exc:  # noqa: BLE001 - e.g. the central vanished mid-notify
            print("notify failed:", exc)

    # --- button -------------------------------------------------------

    async def read_button_forever(self):
        """Debounce the pin, feed the detector, emit what comes out.

        Debounce is "the raw level has to hold for DEBOUNCE_S before it counts",
        which rejects contact bounce. on_timeout() is called every tick rather
        than on a scheduled timer - the detector no-ops until the double-tap
        window closes, so polling is both simpler and exactly as accurate.

        **A press is dated at the edge, not at the confirmation.** Waiting for
        the level to hold is how we decide a press was real, not when it
        happened; stamping the confirmation instead put DEBOUNCE_S (50 ms) of
        systematic error into every timestamp the host sees, uncorrectable
        because the host cannot know it is there. It showed up as a reaction
        timer reading ~50 ms slow for everybody.

        With contact chatter the edge we date to is the *last* bounce before the
        level settled, because nothing can tell us which bounce was the finger.
        A clean press has exactly one edge and dates exactly right.
        """
        from machine import Pin

        pull = Pin.PULL_UP if hardware.BUTTON_PULL_UP else None
        pin = Pin(hardware.BUTTON_PIN, Pin.IN, pull)

        def is_pressed():
            return (pin.value() == 0) if hardware.BUTTON_ACTIVE_LOW else bool(pin.value())

        stable = is_pressed()
        candidate = stable
        candidate_since = now_s()
        press_t = None
        hold_fired = False

        while True:
            now = now_s()
            raw = is_pressed()

            if raw != candidate:
                candidate = raw
                candidate_since = now
            elif raw != stable and (now - candidate_since) >= DEBOUNCE_S:
                stable = raw
                # `candidate_since`, not `now`: the edge is when it happened,
                # the hold is only how we know it was real. See the docstring.
                edge = candidate_since
                if stable:
                    press_t = edge
                    hold_fired = False
                    self._emit(self._detector.on_press(edge))
                else:
                    press_t = None
                    event, _deadline = self._detector.on_release(edge)
                    self._emit(event)

            # Long press fires while still held, not on release.
            if stable and not hold_fired and press_t is not None:
                if (now - press_t) >= HOLD_S:
                    hold_fired = True
                    self._emit(self._detector.on_hold(now))

            self._emit(self._detector.on_timeout(now))
            await asyncio.sleep(_POLL_S)


async def main():
    peripheral = ButtonPeripheral()
    peripheral.led.set_state(protocol.LED_IDLE)
    print("AI Button firmware ready - advertising as", hardware.DEVICE_NAME)
    # One task per characteristic; the button poll is the one we stay in. (Not
    # gather(): its coverage across MicroPython builds is patchier than
    # create_task, and there is nothing here to collect results from.)
    asyncio.create_task(peripheral.advertise_forever())
    asyncio.create_task(peripheral.serve_led())
    asyncio.create_task(peripheral.serve_sound())
    asyncio.create_task(peripheral.serve_palette())
    asyncio.create_task(peripheral.serve_effect())
    asyncio.create_task(peripheral.serve_gesture_config())
    await peripheral.read_button_forever()


if __name__ == "__main__":
    asyncio.run(main())
