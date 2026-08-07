"""What the control panel believes about the service, and how that reads.

Pure, on purpose. A `Health` is assembled from a `/api/status` payload (or
from the absence of one), and everything the tray renders - icon colour,
menu labels, the window's summary - is derived from it by plain functions.
So the interesting decisions here are testable without a tray, a network or
a child process, the same way rules.py is testable without hardware.

Nothing in this module imports pystray, Pillow, Tk or httpx.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Level(Enum):
    """Coarse health. The tray icon is a dot in this colour, so the whole
    point is that there are few of these and they are unambiguous."""

    STOPPED = "stopped"    # nothing running
    STARTING = "starting"  # process is up, its API has not answered yet
    WAITING = "waiting"    # service up, no button on the other end
    READY = "ready"        # service up, button connected
    FAULT = "fault"        # it was running and stopped being


# RGB, chosen to survive both light and dark Windows taskbars.
COLOURS: dict[Level, tuple[int, int, int]] = {
    Level.STOPPED: (128, 128, 134),
    Level.STARTING: (232, 168, 48),
    Level.WAITING: (232, 168, 48),
    Level.READY: (46, 190, 96),
    Level.FAULT: (222, 62, 62),
}

_LEVEL_TEXT: dict[Level, str] = {
    Level.STOPPED: "Stopped",
    Level.STARTING: "Starting...",
    Level.WAITING: "Waiting for the button",
    Level.READY: "Ready",
    Level.FAULT: "Stopped unexpectedly",
}


@dataclass(frozen=True)
class Health:
    """One snapshot. `process_alive` is what the supervisor knows about a
    child it started; `responding` is whether the service's own API answered.
    They are separate because either can be true without the other: a service
    started from a terminal responds without being our child, and a child that
    has just been spawned is alive well before it can answer."""

    process_alive: bool = False
    responding: bool = False
    pid: int | None = None
    # Everything below is only meaningful when `responding` is True.
    connected: bool = False
    mock: bool = False
    state: str = ""
    mode: str | None = None
    message: str = ""
    degraded: bool = False
    # Set when a child we started has exited on its own.
    exit_code: int | None = None

    @property
    def running(self) -> bool:
        return self.process_alive or self.responding

    @property
    def level(self) -> Level:
        if not self.running:
            # A non-zero exit is a crash; a clean one is someone pressing Stop.
            return Level.FAULT if self.exit_code not in (None, 0) else Level.STOPPED
        if not self.responding:
            return Level.STARTING
        # A MockDevice has no radio to be disconnected from - treating it as
        # "waiting" would leave the icon amber forever in the offline dev setup.
        return Level.READY if (self.connected or self.mock) else Level.WAITING


def headline(health: Health) -> str:
    """The one line that says what is going on."""
    text = _LEVEL_TEXT[health.level]
    if health.level is Level.FAULT and health.exit_code is not None:
        return f"{text} (exit {health.exit_code})"
    if health.level is Level.READY and health.mock:
        return f"{text} (simulated button)"
    return text


def summary_lines(health: Health) -> list[str]:
    """The status block, as the tray menu and the window both show it.

    Only facts that are actually known: fields behind `responding` are left
    out entirely when the service is not answering, rather than rendered as
    stale or as a confident-looking blank.
    """
    lines = [f"Service: {headline(health)}"]
    if health.pid is not None and health.running:
        lines[0] += f"  (pid {health.pid})"
    if not health.responding:
        return lines

    lines.append(f"Button: {'connected' if health.connected else 'not connected'}"
                 + (" - simulated" if health.mock else ""))
    if health.state:
        lines.append(f"State: {health.state}")
    if health.mode:
        lines.append(f"Mode: {health.mode}")
    if health.message:
        lines.append(f"Last: {health.message}")
    if health.degraded:
        # Loud, because an empty Events tab otherwise looks like a quiet day.
        lines.append("! Event log degraded - history is in memory only")
    return lines


def from_payload(
    payload: dict | None,
    *,
    process_alive: bool = False,
    pid: int | None = None,
    exit_code: int | None = None,
) -> Health:
    """Build a Health from a `/api/status` body, or from None when the poll
    failed. Unknown/odd payload shapes degrade to defaults rather than raise -
    the control panel must not be the thing that breaks."""
    if payload is None:
        return Health(
            process_alive=process_alive, responding=False, pid=pid, exit_code=exit_code
        )
    return Health(
        process_alive=process_alive,
        responding=True,
        pid=pid,
        connected=bool(payload.get("device_connected")),
        mock=bool(payload.get("mock")),
        state=str(payload.get("state") or ""),
        mode=payload.get("last_mode") or None,
        message=str(payload.get("last_message") or ""),
        degraded=bool(payload.get("store_degraded")),
        exit_code=exit_code,
    )
