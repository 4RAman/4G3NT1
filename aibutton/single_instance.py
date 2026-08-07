"""One button, one host process.

BLE allows a single central, so a second copy of the service does not
politely queue - it steals the connection, and the two ping-pong: the web
UI flickers between connected and offline, presses land in whichever
process won the last race, and both write the same event database. That is
miserable to diagnose from a log, which is why this refuses at startup
instead (ROADMAP.md's Stage 2 exit gate).

The lock is an **OS-level file lock**, not a PID file, on purpose: the
kernel drops it when the process dies, however it dies, so a crash or a
hard kill never leaves a stale lock for someone to clear by hand. The PID
written alongside it is informational only - it tells you what to kill, and
is never trusted to decide whether the lock is held.

Windows and POSIX take different syscalls for this and neither is in the
stdlib's portable half, so both backends live here behind one method.
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# The PID is written after the locked byte so that taking the lock and
# recording who holds it never touch the same region of the file.
_LOCK_BYTE = 1


class AlreadyRunning(RuntimeError):
    """Another copy of the service holds the lock."""


def _try_lock(fd: int) -> bool:
    """Take an exclusive, non-blocking lock on the first byte of `fd`.
    True if we got it, False if someone else holds it."""
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, _LOCK_BYTE)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_BYTE)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:  # already gone, or the file vanished - nothing to undo
        pass


class SingleInstance:
    """Holds the run lock for as long as this process runs.

    Usable as a context manager. `acquire()` raises `AlreadyRunning` if
    another process has it; everything else that can go wrong (an
    unwritable directory, a filesystem with no locking) is logged and
    allowed through - refusing to start because the *guard* broke would be
    a worse failure than the one it guards against.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    def _holder_pid(self) -> str:
        """Best-effort read of the PID recorded by whoever holds the lock.

        Reads from `_LOCK_BYTE` onward rather than slurping the file: Windows
        byte-range locks are enforced against *readers* on other handles too,
        so touching byte 0 here would fail on the very path that needs to
        report who to stop.
        """
        fd = None
        try:
            fd = os.open(self.path, os.O_RDONLY)
            os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
            pid = os.read(fd, 16).decode("ascii", "replace").strip()
        except OSError:
            return "unknown"
        finally:
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
        return pid or "unknown"

    def acquire(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Opened read/write and never truncated: truncating would drop the
            # very byte the lock is taken on.
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as exc:
            log.warning(
                "single-instance: cannot open %s (%s) - running unguarded",
                self.path, exc,
            )
            return

        if not _try_lock(fd):
            pid = self._holder_pid()
            os.close(fd)
            raise AlreadyRunning(
                f"another copy of the button service is already running "
                f"(pid {pid}, lock {self.path}). Only one may hold the BLE "
                f"connection - stop that one first."
            )

        self._fd = fd
        # Byte 0 is the lock; the PID goes after it, padded so a shorter PID
        # replacing a longer one cannot leave trailing digits behind.
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"\0" + f"{os.getpid()}".ljust(16).encode("ascii"))
        except OSError:  # the lock is what matters; the note is a nicety
            pass

    def release(self) -> None:
        if self._fd is None:
            return
        _unlock(self._fd)
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None
        # Deliberately not unlinking: another process may already be waiting
        # on this path, and removing it out from under them would let two
        # instances lock two different inodes and both believe they are alone.

    def __enter__(self) -> "SingleInstance":
        self.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self.release()
