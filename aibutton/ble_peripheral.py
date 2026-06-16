"""BLE GATT peripheral broadcasting device state and AI responses.

Uses bluez-peripheral (a D-Bus GATT server) so it cooperates with the
stock BlueZ/bluetoothd stack on Raspberry Pi OS - no exclusive HCI
access, no extra capabilities; the service just needs the `bluetooth`
group for D-Bus access (see SETUP.md).

Characteristics (read + notify, no pairing required):
- STATUS_CHAR:   current device state string (IDLE/THINKING/SUCCESS/ERROR)
- RESPONSE_CHAR: AI response text, chunked

Chunking: notification payloads are capped at ATT_MTU-3 bytes, so
512-byte chunks only survive when the central negotiates MTU >= 515.
We default to 180 bytes (safe for modern phones, which negotiate
MTU >= 185); raise CHUNK_SIZE if your centrals support it. Chunks never
split a UTF-8 character, and a single EOT byte (0x04) marks
end-of-message so the central knows when to reassemble.

The bluez-peripheral imports are guarded so this module stays importable
on dev machines without D-Bus (only chunk_utf8 is usable there).
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

SERVICE_UUID = "f3641400-00b0-4240-ba50-05ca45bf8abc"
STATUS_CHAR_UUID = "f3641401-00b0-4240-ba50-05ca45bf8abc"
RESPONSE_CHAR_UUID = "f3641402-00b0-4240-ba50-05ca45bf8abc"

CHUNK_SIZE = 180
CHUNK_DELAY_S = 0.05  # pace notifications so BlueZ/centrals don't drop them
EOT = b"\x04"  # end-of-message marker chunk


def chunk_utf8(text: str, size: int = CHUNK_SIZE) -> list[bytes]:
    """Split text into UTF-8 chunks of at most `size` bytes, never
    splitting a multibyte character."""
    data = text.encode("utf-8")
    chunks: list[bytes] = []
    i = 0
    while i < len(data):
        end = min(i + size, len(data))
        # Back off while the boundary lands on a continuation byte (0b10xxxxxx).
        while end < len(data) and end > i and (data[end] & 0xC0) == 0x80:
            end -= 1
        if end == i:  # size smaller than one character - split anyway
            end = min(i + size, len(data))
        chunks.append(data[i:end])
        i = end
    return chunks


try:
    from bluez_peripheral.advert import Advertisement
    from bluez_peripheral.agent import NoIoAgent
    from bluez_peripheral.util import Adapter, get_message_bus

    try:
        # Submodule paths (work on all known releases).
        from bluez_peripheral.gatt.characteristic import CharacteristicFlags as CharFlags
        from bluez_peripheral.gatt.characteristic import characteristic
        from bluez_peripheral.gatt.service import Service
    except ImportError:
        # Package-level re-exports (current README style).
        from bluez_peripheral.gatt import CharacteristicFlags as CharFlags
        from bluez_peripheral.gatt import Service, characteristic

    HAVE_BLUEZ = True
except ImportError:
    HAVE_BLUEZ = False


if HAVE_BLUEZ:

    class _AIButtonService(Service):
        def __init__(self):
            super().__init__(SERVICE_UUID, True)
            self._status_value = b"IDLE"

        @characteristic(STATUS_CHAR_UUID, CharFlags.READ | CharFlags.NOTIFY)
        def status_char(self, options):
            return self._status_value

        @characteristic(RESPONSE_CHAR_UUID, CharFlags.READ | CharFlags.NOTIFY)
        def response_char(self, options):
            return b""

        def notify_status(self, value: bytes) -> None:
            self._status_value = value
            self.status_char.changed(value)

        def notify_response(self, value: bytes) -> None:
            self.response_char.changed(value)


class BLEPeripheral:
    """start() registers the GATT service and advertisement; set_status()
    and send_response() notify subscribed centrals."""

    def __init__(self, device_name: str):
        if not HAVE_BLUEZ:
            raise RuntimeError(
                "bluez-peripheral is not available (Linux + BlueZ only)"
            )
        self._device_name = device_name
        self._service = _AIButtonService()
        self._bus = None

    async def start(self) -> None:
        self._bus = await get_message_bus()
        await self._service.register(self._bus)
        # Auto-accept if a central insists on pairing; plain read/notify
        # works without any pairing at all.
        agent = NoIoAgent()
        await agent.register(self._bus)
        adapter = await Adapter.get_first(self._bus)
        # timeout=0 -> advertise indefinitely. We only ever advertise
        # (no scanning), so contention with WiFi on the shared antenna
        # stays minimal even during Ollama calls.
        advert = Advertisement(self._device_name, [SERVICE_UUID], 0x0000, 0)
        await advert.register(self._bus, adapter)
        log.info("BLE advertising as %r", self._device_name)

    def set_status(self, status: str) -> None:
        self._service.notify_status(status.encode("utf-8"))

    async def send_response(self, text: str) -> None:
        for chunk in chunk_utf8(text, CHUNK_SIZE):
            self._service.notify_response(chunk)
            await asyncio.sleep(CHUNK_DELAY_S)
        self._service.notify_response(EOT)

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
