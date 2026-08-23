"""A way for a second launch to say "show yourself" to the first.

Three situations used to look identical - already running, wedged, and running
but invisible - because the panel lives in the tray and Windows hides new tray
icons in an overflow flyout. **Never parent a dialog to a withdrawn Tk root**:
on Windows it renders with no taskbar button and no focus, so the second
process sat forever holding an invisible modal and the panel looked hung.

So: a running panel listens on a loopback socket and a second launch connects
to it. If it answers, it raises its own window and the newcomer exits quietly,
which is what every other single-instance desktop app does. **If it does not
answer, that is information too** - the holder is wedged rather than merely
already-running, and the caller says so and names the PID instead of insisting
everything is fine.

Loopback TCP rather than a named pipe or a window message: it is stdlib, it
works the same on both platforms, and the port file is self-cleaning in the
only way that matters - a stale one simply fails to connect, which is exactly
the signal we want. Nothing here is a network service: it binds 127.0.0.1 on
an ephemeral port, speaks four bytes, and would refuse anything else.
"""

from __future__ import annotations

import contextlib
import logging
import socket
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# Deliberately tiny and fixed-length. This is not a protocol anyone should
# grow: if the panel ever needs real IPC it should get a real one, and the
# smallness here is what stops this quietly becoming that.
_SHOW = b"show"
_OK = b"ok"

# Long enough to cross a loopback socket on a busy machine, short enough that
# a wedged holder does not make the newcomer look wedged too.
CONNECT_TIMEOUT_S = 1.5


def port_path(config: Path) -> Path:
    """Beside the lock and the prefs, for the same reason they are: this is
    the panel's own business and never goes in config.json."""
    return config.with_name("control-panel.port")


class Beacon:
    """Listens for "show" while the panel runs. Best-effort by construction.

    Every failure here is logged and swallowed: a panel that would not start
    because its convenience socket could not bind would be a worse bug than
    the one this exists to fix.
    """

    def __init__(self, config: Path, on_show) -> None:
        self._path = port_path(config)
        self._on_show = on_show
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sock.listen(4)
        except OSError as exc:
            log.warning("control panel: no show-me socket (%s) - carrying on", exc)
            return
        self._sock = sock
        port = sock.getsockname()[1]
        try:
            self._path.write_text(str(port), encoding="ascii")
        except OSError as exc:
            # Without the file nobody can find us, so this is the one failure
            # that makes the socket pointless - but still not fatal.
            log.warning("control panel: cannot record the port (%s)", exc)
        self._thread = threading.Thread(
            target=self._serve, daemon=True, name="panel-beacon"
        )
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                return  # closed from under us: that is how stop() works
            with conn:
                with contextlib.suppress(OSError):
                    conn.settimeout(CONNECT_TIMEOUT_S)
                    if conn.recv(len(_SHOW)) == _SHOW:
                        conn.sendall(_OK)
                        # Hand back to the GUI thread; Tk is not thread-safe
                        # and this runs on the accept thread.
                        with contextlib.suppress(Exception):
                            self._on_show()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
        # Removed on the way out so a *clean* exit leaves nothing to mislead
        # the next launch. A crash leaves it behind, which is harmless: the
        # connect fails and the caller learns the same thing.
        with contextlib.suppress(OSError):
            self._path.unlink()


def ask_to_show(config: Path, timeout_s: float = CONNECT_TIMEOUT_S) -> bool:
    """Tell a running panel to show its window. True if one answered.

    False covers every way this can fail - no port file, a stale port, a
    refused connection, a holder too wedged to accept - and they all mean the
    same thing to the caller, which is why they are not distinguished here.
    """
    path = port_path(config)
    try:
        port = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout_s) as conn:
            conn.sendall(_SHOW)
            return conn.recv(len(_OK)) == _OK
    except OSError:
        return False
