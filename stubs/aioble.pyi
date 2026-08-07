"""Type stub for aioble - editor support only, never imported at runtime.

aioble ships with micropython-lib rather than the firmware, so unlike
`machine` and `bluetooth` it has no published stub package; without this,
firmware/main.py is a wall of unresolved-import squiggles.

Deliberately not exhaustive: this covers exactly the API surface the
firmware uses, which makes it a useful second job - the list below is the
dependency on aioble, so if a future version moves something, this file
says what has to still exist.
"""

from typing import Any, Awaitable, Iterable

class UUID:
    def __init__(self, value: str | int) -> None: ...

class Characteristic:
    def __init__(
        self,
        service: Service,
        uuid: Any,
        read: bool = False,
        write: bool = False,
        notify: bool = False,
        indicate: bool = False,
        capture: bool = False,
        **kwargs: Any,
    ) -> None: ...
    def read(self) -> bytes: ...
    def write(self, data: bytes, send_update: bool = False) -> None: ...
    def notify(self, connection: DeviceConnection, data: bytes | None = None) -> None: ...
    # With capture=True this resolves to (connection, data); without it, just
    # the connection - firmware/main.py accepts both.
    def written(self, timeout_ms: int | None = None) -> Awaitable[Any]: ...

class Service:
    def __init__(self, uuid: Any) -> None: ...

class Device:
    addr_hex: str

class DeviceConnection:
    device: Device
    def disconnected(self, timeout_ms: int | None = None) -> Awaitable[None]: ...
    def disconnect(self, timeout_ms: int | None = None) -> Awaitable[None]: ...

def register_services(*services: Service) -> None: ...
def advertise(
    interval_us: int,
    name: str | None = None,
    services: Iterable[Any] | None = None,
    appearance: int = 0,
    manufacturer: tuple[int, bytes] | None = None,
    timeout_ms: int | None = None,
) -> Awaitable[DeviceConnection]: ...
