"""BLEDevice - the host as BLE central, talking to the ESP32 firmware.

The other half of [device.py](device.py)'s seam: gestures arrive as
notifications and become presses on the queue; LED and sound go out as writes.
Everything above it is unchanged and unaware. Two things shape the design:

**Writes must not block.** The mode machine cannot wait on a radio, so writes
go into an outbox and return. A pump drains it while connected and drops it
while not - feedback that arrives seconds late is worse than none.

**The link will drop.** The connection is a loop, not an event - scan, connect,
serve, wait, scan again, until close(). Each reconnect re-asserts the palette
and the current LED state, so the device never sits showing something the host
has moved on from.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from bleak import BleakClient, BleakScanner

from .button import DOUBLE_WINDOW_S
from .device import (
    ASSUMED_INFO,
    BUTTON_EVENT_UUID,
    CAP_BUZZER,
    CAP_EFFECT,
    CAP_GESTURE_PARAMS,
    CAP_LED,
    DEVICE_INFO_UUID,
    GESTURE_CONFIG_UUID,
    LED_CODES,
    LED_EFFECT_UUID,
    LED_PALETTE_UUID,
    LED_STATE_UUID,
    SOUND_CMD_UUID,
    STOP_LOOP_CMD,
    ButtonDevice,
    LEDState,
    Sound,
    decode_device_info,
    decode_gesture,
    effect_payload,
    gesture_config_payload,
    palette_payload,
    sound_command,
)

log = logging.getLogger(__name__)

SCAN_TIMEOUT_S = 10.0
RETRY_S = 3.0
# A press produces at most a handful of writes; anything beyond this means
# the link is stalled and the backlog is stale by definition.
OUTBOX_MAX = 32


class BLEDevice(ButtonDevice):
    def __init__(
        self,
        name: str = "AIButton",
        *,
        scan_timeout_s: float = SCAN_TIMEOUT_S,
        retry_s: float = RETRY_S,
    ) -> None:
        super().__init__()
        # The detector in firmware/trigger.py holds a single press back until
        # the multi-tap window closes. See ButtonDevice.press_latency_s.
        self.press_latency_s = DOUBLE_WINDOW_S
        self._name = name
        self._scan_timeout_s = scan_timeout_s
        self._retry_s = retry_s
        self._outbox: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._led_state = LEDState.IDLE
        self._led_effect = None  # the ephemeral look showing, if any
        # States whose palette entry on the device is currently holding an
        # ephemeral look, on a device too old to render one properly. Emptied
        # by putting the real entries back - see set_led.
        self._clobbered: set[LEDState] = set()
        self._client: BleakClient | None = None
        self._connected = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._maintain(), name="ble-connect")

    async def close(self) -> None:
        """Silence the device, then stop reconnecting.

        The stop goes out as a *direct* write rather than through the outbox:
        the pump is about to be cancelled, and leaving a ringing alarm behind
        because a queued byte never drained is exactly the failure the
        ButtonDevice contract calls out.
        """
        self._stop.set()
        client = self._client
        if client is not None and self._connected:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    client.write_gatt_char(
                        SOUND_CMD_UUID, bytes([STOP_LOOP_CMD]), response=True
                    ),
                    timeout=2.0,
                )
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    # --- feedback out -------------------------------------------------

    def set_led(self, state: LEDState, effect=None) -> None:
        # Remembered even while disconnected, so the next connection starts
        # showing what the host currently believes.
        self._led_state, previous = state, self._led_state
        self._led_effect = effect
        # Re-asserting the same state with a fresh look must not re-send the
        # state: the device restarts the animation on every LED_STATE write,
        # and a countdown pushes a colour every few seconds.
        if state is not previous or effect is None:
            self._send(LED_STATE_UUID, bytes([LED_CODES[state]]))
        if effect is None:
            self._restore_clobbered()
        elif self.info.has(CAP_EFFECT):
            self._send(LED_EFFECT_UUID, effect_payload(effect))
        else:
            # A device that predates ephemeral effects can still show the look,
            # by borrowing the state's palette entry. The borrowing lives here
            # rather than in the run loops so a mode never has to know which
            # kind of device it is talking to, and so it is undone
            # automatically rather than by a `finally` remembering.
            self._clobbered.add(state)
            self._send(LED_PALETTE_UUID, palette_payload(state, effect))

    def _restore_clobbered(self) -> None:
        """Put back any palette entry the fallback above borrowed."""
        while self._clobbered:
            state = self._clobbered.pop()
            effect = self.palette.get(state.value)
            if effect is not None:
                self._send(LED_PALETTE_UUID, palette_payload(state, effect))

    def play_sound(self, sound: Sound) -> None:
        if not self.info.has(CAP_BUZZER):
            return  # nothing to hear it; see _adopt_info
        self._send(SOUND_CMD_UUID, sound_command(sound))

    def start_loop(self, sound: Sound) -> None:
        if not self.info.has(CAP_BUZZER):
            return
        self._send(SOUND_CMD_UUID, sound_command(sound, loop=True))

    def stop_loop(self) -> None:
        # Never gated. Silencing is the safety path, it costs one byte, and a
        # device that gained a buzzer between connections must not be left
        # ringing because we decided in advance it had none.
        self._send(SOUND_CMD_UUID, bytes([STOP_LOOP_CMD]))

    def set_palette(self, palette: dict) -> None:
        """Send the whole palette, one write per state. Remembered too, so a
        reconnect re-sends it: the device's own defaults are only ever a
        stand-in for a host that hasn't spoken yet."""
        super().set_palette(palette)
        for state, effect in self._palette_entries():
            self._send(LED_PALETTE_UUID, palette_payload(state, effect))

    def set_gesture_config(self, max_taps: int) -> None:
        """Tell the device how long a tap burst to watch for.

        Gated, because a device that predates parameterised gestures counts to
        two and cannot be told otherwise: writing to a characteristic it does
        not have would only log a failure, and behaving exactly as it always has
        is the right answer for a button nobody has reflashed.
        """
        super().set_gesture_config(max_taps)
        if self.info.has(CAP_GESTURE_PARAMS):
            self._send(GESTURE_CONFIG_UUID, gesture_config_payload(self.max_taps))

    def _palette_entries(self):
        if not self.info.has(CAP_LED):
            return  # no LED came up; colours are a dozen pointless writes
        for state in LEDState:
            effect = self.palette.get(state.value)
            if effect is not None:
                yield state, effect

    async def _adopt_info(self, client: BleakClient) -> None:
        """Ask the device what it is, before sending it anything.

        A device with no DEVICE_INFO characteristic falls back to ASSUMED_INFO
        rather than to nothing, so that learning to ask cannot silence a button
        nobody has reflashed.
        """
        raw = None
        try:
            raw = await client.read_gatt_char(DEVICE_INFO_UUID)
        except Exception as exc:  # no such characteristic, or an unreadable one
            log.info("BLE: no device info (%s) - assuming a pre-v1 button", exc)
        info = decode_device_info(raw)
        if raw is not None and info is None:
            log.warning("BLE: device info was too short to trust - assuming a pre-v1 button")
        self.info = info or ASSUMED_INFO
        log.info(
            "BLE: protocol v%d, firmware %s, capabilities: %s",
            self.info.protocol_version,
            self.info.firmware,
            ", ".join(self.info.names) or "none reported",
        )

    def _send(self, uuid: str, payload: bytes) -> None:
        if not self._connected:
            return  # nothing on the other end; feedback is not worth queueing
        if self._outbox.qsize() >= OUTBOX_MAX:
            log.warning("BLE outbox full - dropping write to %s", uuid[:8])
            return
        self._outbox.put_nowait((uuid, payload))

    # --- gestures in --------------------------------------------------

    def _on_notify(self, _sender, data: bytearray) -> None:
        if not data:
            return
        trigger = decode_gesture(data)
        if trigger is None:
            log.warning("unknown gesture %s - ignored", bytes(data).hex())
            return
        self.press(trigger)

    # --- the connection loop ------------------------------------------

    async def _maintain(self) -> None:
        while not self._stop.is_set():
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # scan/connect/notify all fail this way
                log.warning("BLE: %s: %s", type(exc).__name__, exc)
            finally:
                self._connected = False
                self._client = None
            if not self._stop.is_set():
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self._retry_s)

    async def _connect_once(self) -> None:
        device = await BleakScanner.find_device_by_name(
            self._name, timeout=self._scan_timeout_s
        )
        if device is None:
            log.info("BLE: no %r in range - retrying", self._name)
            return

        disconnected = asyncio.Event()
        async with BleakClient(
            device, disconnected_callback=lambda _c: disconnected.set()
        ) as client:
            self._client = client
            await client.start_notify(BUTTON_EVENT_UUID, self._on_notify)
            self._connected = True
            log.info("BLE: connected to %s (%s)", self._name, device.address)
            # Ask first: everything below is gated on what it says it can do,
            # and re-asked every reconnect because the thing on the other end
            # may have been reflashed since.
            await self._adopt_info(client)
            # A fresh device holds its own palette, so nothing is borrowed yet
            # however this connection ended last time.
            self._clobbered.clear()
            if self.info.has(CAP_GESTURE_PARAMS):
                await client.write_gatt_char(
                    GESTURE_CONFIG_UUID,
                    gesture_config_payload(self.max_taps),
                    response=True,
                )
            # The palette first, then the state - so the state that lights up
            # is already wearing the user's colours rather than the device's
            # built-in defaults for a frame.
            for state, effect in self._palette_entries():
                await client.write_gatt_char(
                    LED_PALETTE_UUID, palette_payload(state, effect), response=True
                )
            # Whatever the host thinks the LED should be, right now - including
            # a look a takeover mode is part-way through showing, which would
            # otherwise wait for its next change to reappear.
            await client.write_gatt_char(
                LED_STATE_UUID, bytes([LED_CODES[self._led_state]]), response=True
            )
            if self._led_effect is not None:
                self.set_led(self._led_state, self._led_effect)
            await self._pump(client, disconnected)
        self._connected = False
        log.info("BLE: disconnected from %s", self._name)

    async def _pump(self, client: BleakClient, disconnected: asyncio.Event) -> None:
        """Drain the outbox until the link drops or we are shutting down."""
        while not disconnected.is_set() and not self._stop.is_set():
            get = asyncio.create_task(self._outbox.get())
            dropped = asyncio.create_task(disconnected.wait())
            stopping = asyncio.create_task(self._stop.wait())
            done, pending = await asyncio.wait(
                {get, dropped, stopping}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if get not in done:  # disconnected, or shutting down
                return
            uuid, payload = get.result()
            try:
                await client.write_gatt_char(uuid, payload, response=True)
            except Exception as exc:  # the link died mid-write
                log.warning("BLE write failed: %s", exc)
                return
