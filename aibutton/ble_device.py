"""BLEDevice - the host as BLE central, talking to the ESP32 firmware.

The other half of [device.py](device.py)'s seam: gestures arrive as
notifications and become presses on the queue; LED and sound go out as
one-byte writes. Everything above it is unchanged and unaware.

Two things shape the design:

**Writes must not block.** The mode machine cannot wait on a radio, so
writes go into an outbox and return. A pump drains it while connected and
drops it while not: feedback that arrives seconds late is worse than
feedback that never arrives.

**The link will drop.** The connection is a loop, not an event - scan,
connect, serve, wait, scan again, until close(). Each reconnect re-asserts
the palette and the current LED state, so the device never sits showing
something the host has moved on from.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from bleak import BleakClient, BleakScanner

from .device import (
    BUTTON_EVENT_UUID,
    GESTURE_BY_CODE,
    LED_CODES,
    LED_PALETTE_UUID,
    LED_STATE_UUID,
    SOUND_CMD_UUID,
    STOP_LOOP_CMD,
    ButtonDevice,
    LEDState,
    Sound,
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
        self._name = name
        self._scan_timeout_s = scan_timeout_s
        self._retry_s = retry_s
        self._outbox: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._led_state = LEDState.IDLE
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

    def set_led(self, state: LEDState) -> None:
        # Remembered even while disconnected, so the next connection starts
        # showing what the host currently believes.
        self._led_state = state
        self._send(LED_STATE_UUID, bytes([LED_CODES[state]]))

    def play_sound(self, sound: Sound) -> None:
        self._send(SOUND_CMD_UUID, sound_command(sound))

    def start_loop(self, sound: Sound) -> None:
        self._send(SOUND_CMD_UUID, sound_command(sound, loop=True))

    def stop_loop(self) -> None:
        self._send(SOUND_CMD_UUID, bytes([STOP_LOOP_CMD]))

    def set_palette(self, palette: dict) -> None:
        """Send the whole palette, one write per state. Remembered too, so a
        reconnect re-sends it: the device's own defaults are only ever a
        stand-in for a host that hasn't spoken yet."""
        super().set_palette(palette)
        for state, effect in self._palette_entries():
            self._send(LED_PALETTE_UUID, palette_payload(state, effect))

    def _palette_entries(self):
        for state in LEDState:
            effect = self.palette.get(state.value)
            if effect is not None:
                yield state, effect

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
        trigger = GESTURE_BY_CODE.get(data[0])
        if trigger is None:
            log.warning("unknown gesture code 0x%02x - ignored", data[0])
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
            # The palette first, then the state - so the state that lights up
            # is already wearing the user's colours rather than the device's
            # built-in defaults for a frame.
            for state, effect in self._palette_entries():
                await client.write_gatt_char(
                    LED_PALETTE_UUID, palette_payload(state, effect), response=True
                )
            # Whatever the host thinks the LED should be, right now.
            await client.write_gatt_char(
                LED_STATE_UUID, bytes([LED_CODES[self._led_state]]), response=True
            )
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
