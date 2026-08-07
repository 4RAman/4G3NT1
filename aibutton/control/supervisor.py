"""Owns the button service as a child process, and asks it how it is doing.

The two halves the tray needs and Tk should never do inline:

**Lifecycle.** `start()` spawns `python -m aibutton.main`, `stop()` asks it
to leave the way it would on Ctrl+C so its takeover loops close their own
timers. Only then does it escalate. Every line the child prints is kept in a
bounded buffer for the log window.

**Health.** `poll()` reads the service's own `/api/status` over HTTP rather
than guessing from the process table, so a service someone started from a
terminal shows up exactly like one the tray started.

Command building is kept pure (`service_command`, `flash_command`) so what
actually gets run is assertable without spawning anything.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

import httpx

from ..config import load_config
from .status import Health, from_payload

log = logging.getLogger(__name__)

# Lines of child output kept for the log window. Enough to cover a flash and
# a startup; not enough to grow without bound over a long session.
LOG_LINES = 500
POLL_TIMEOUT_S = 1.5
# How long the child gets to leave politely at each escalation step.
_GRACE_S = 6.0
_TERMINATE_S = 3.0

_IS_WINDOWS = os.name == "nt"


def service_command(python: str, config: Path, *, ble: bool = True) -> list[str]:
    """The argv that starts the service. `-u` because the log window reads
    the child's stdout as it goes: block buffering would hold whole startup
    messages back until something else filled the buffer.

    `--ble` is the default here even though it is opt-in on the command
    line: someone running the control panel has a button, and a panel whose
    Start button silently launches a simulated one is worse than useless.
    dev.ps1 remains the no-hardware path.
    """
    argv = [python, "-u", "-m", "aibutton.main"]
    if ble:
        argv.append("--ble")
    argv += ["--config", str(config)]
    return argv


def prefs_path(config: Path) -> Path:
    """The panel's own settings, beside the config it drives. Deliberately
    not *in* config.json: that file is the service's, is hot-reloaded, and
    is rewritten wholesale by the web UI's editor."""
    return config.with_name("control-panel.json")


def load_prefs(config: Path) -> dict:
    """Never raises - a corrupt or missing prefs file means defaults."""
    try:
        with open(prefs_path(config), encoding="utf-8") as f:
            prefs = json.load(f)
        return prefs if isinstance(prefs, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_prefs(config: Path, prefs: dict) -> None:
    """Best effort. Losing a preference is not worth an error dialog."""
    try:
        prefs_path(config).write_text(json.dumps(prefs, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("could not save control panel prefs: %s", exc)


def flash_command(python: str, root: Path) -> list[str]:
    """The argv that copies the firmware onto the board and resets it.

    Modules are listed explicitly rather than passed as a glob: the shell is
    not involved here, so `firmware/*.py` would arrive at mpremote as a
    literal. Sorted so the command is stable enough to assert on.
    """
    modules = sorted(p.name for p in (root / "firmware").glob("*.py"))
    paths = [f"firmware/{name}" for name in modules]
    return [python, "-m", "mpremote", "cp", *paths, ":", "+", "reset"]


def status_url(config: Path) -> str | None:
    """Where the service's API will be, per its config. None when the web UI
    is switched off - the tray then has to fall back to process liveness."""
    cfg = load_config(str(config))  # never raises; falls back per key
    if not cfg.web_enabled:
        return None
    # 0.0.0.0 means "listen on everything", which is not an address to dial.
    host = "127.0.0.1" if cfg.web_host in ("0.0.0.0", "::", "") else cfg.web_host
    return f"http://{host}:{cfg.web_port}/api/status"


def web_url(config: Path) -> str | None:
    url = status_url(config)
    return url[: -len("/api/status")] + "/" if url else None


class Supervisor:
    """One service child, plus whatever the tray needs to know about it."""

    def __init__(self, root: Path, config: Path, python: str | None = None) -> None:
        self.root = root
        self.config = config
        self.python = python or sys.executable
        self._proc: subprocess.Popen | None = None
        self._task: subprocess.Popen | None = None  # a flash, while it runs
        self._log: deque[str] = deque(maxlen=LOG_LINES)
        self._lock = threading.Lock()
        self._client = httpx.Client(timeout=POLL_TIMEOUT_S)
        self._exit_code: int | None = None
        # Whether Start launches the real button or a simulated one. Sticky
        # across restarts, because it is a property of this desk, not of a
        # session.
        self.use_ble: bool = bool(load_prefs(config).get("use_ble", True))

    def set_use_ble(self, value: bool) -> None:
        self.use_ble = value
        prefs = load_prefs(self.config)
        prefs["use_ble"] = value
        save_prefs(self.config, prefs)

    # --- log ----------------------------------------------------------

    def note(self, line: str) -> None:
        """Add a line of the control panel's own commentary to the log."""
        with self._lock:
            self._log.append(line)

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self._log)

    def _drain(self, proc: subprocess.Popen, label: str) -> None:
        """Pump a child's output into the buffer until it closes. Runs on its
        own thread; a blocking readline here would otherwise freeze the UI."""
        assert proc.stdout is not None
        for line in proc.stdout:
            with self._lock:
                self._log.append(line.rstrip())
        code = proc.wait()
        with self._lock:
            self._log.append(f"--- {label} exited with {code} ---")

    def _spawn(self, argv: list[str], label: str) -> subprocess.Popen:
        flags = 0
        if _IS_WINDOWS:
            # NEW_PROCESS_GROUP so stop() can send this child a Ctrl+Break
            # without also hitting the tray; NO_WINDOW so nothing flashes a
            # console at a user who launched us from an icon.
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            argv,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
        )
        threading.Thread(
            target=self._drain, args=(proc, label), daemon=True, name=f"drain-{label}"
        ).start()
        return proc

    # --- lifecycle ----------------------------------------------------

    @property
    def owns_process(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        """Spawn the service. Safe to call when one is already running - the
        service's own single-instance lock is the real guard, and it will
        refuse with a clear message that lands in this log."""
        if self.owns_process:
            self.note("--- already running ---")
            return
        self._exit_code = None
        argv = service_command(self.python, self.config, ble=self.use_ble)
        self.note(f"--- starting: {' '.join(argv[1:])} ---")
        try:
            self._proc = self._spawn(argv, "service")
        except OSError as exc:
            self.note(f"--- could not start: {exc} ---")
            self._proc = None

    def _ask_to_stop(self) -> bool:
        """Ask over HTTP. True if the service accepted.

        This is the *only* polite option on Windows for a tray app: SIGTERM
        is never delivered between processes there, and CTRL_BREAK_EVENT
        needs a console, which a child spawned with CREATE_NO_WINDOW (by a
        parent that is itself consoleless) does not have. Signals below are
        kept for POSIX and for a service started from a terminal.
        """
        url = status_url(self.config)
        if url is None:
            return False
        try:
            res = self._client.post(url.replace("/api/status", "/api/service/stop"))
        except Exception:
            return False
        return res.status_code == 200

    def stop(self) -> None:
        """Ask the service to shut down the way Ctrl+C would, so its takeover
        loops close open timers and silence a ringing alarm, then escalate.

        The politeness is worth the wait but is not worth hanging on: each
        step has its own deadline and the last one always succeeds. A hard
        kill is survivable by design - the single-instance lock is released
        by the OS and the event store commits per write - it just skips the
        device's goodbye.
        """
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        self.note("--- stopping ---")
        if not self._ask_to_stop():
            with contextlib.suppress(Exception):
                if _IS_WINDOWS:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=_GRACE_S)
        except subprocess.TimeoutExpired:
            self.note("--- did not stop; terminating ---")
            with contextlib.suppress(Exception):
                proc.terminate()
            try:
                proc.wait(timeout=_TERMINATE_S)
            except subprocess.TimeoutExpired:
                self.note("--- terminate ignored; killing ---")
                with contextlib.suppress(Exception):
                    proc.kill()
        self._exit_code = proc.returncode

    def flash(self) -> bool:
        """Copy the firmware onto the board and reset it. Returns False if a
        flash is already in flight - two mpremotes would fight over the port."""
        if self._task is not None and self._task.poll() is None:
            self.note("--- a firmware update is already running ---")
            return False
        argv = flash_command(self.python, self.root)
        self.note("--- updating the button's firmware ---")
        try:
            self._task = self._spawn(argv, "firmware update")
        except OSError as exc:
            self.note(f"--- could not run mpremote: {exc} ---")
            return False
        return True

    @property
    def flashing(self) -> bool:
        return self._task is not None and self._task.poll() is None

    # --- health -------------------------------------------------------

    def poll(self) -> Health:
        """One health snapshot. Never raises: an unreachable service is a
        state to render, not an error to handle."""
        proc = self._proc
        alive = proc is not None and proc.poll() is None
        if proc is not None and not alive and self._exit_code is None:
            self._exit_code = proc.returncode  # it left on its own

        url = status_url(self.config)
        payload = None
        if url is not None:
            try:
                res = self._client.get(url)
                if res.status_code == 200:
                    payload = res.json()
            except Exception:
                payload = None  # not up yet, or not up any more

        # A service someone else started answers the API without being our
        # child, so report *its* pid when it tells us and ours otherwise.
        pid = proc.pid if alive and proc is not None else None
        return from_payload(
            payload, process_alive=alive, pid=pid, exit_code=self._exit_code
        )

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()
