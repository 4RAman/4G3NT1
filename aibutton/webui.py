"""Web UI + REST API for the AI Button.

Runs inside the button service's own asyncio process - main.py starts
uvicorn as a task sharing the live ConfigManager, EventStore, and
ButtonDevice. No second service, no IPC. The page at / is a single
static file (web/index.html), no build step.

Endpoints (a future phone app should use these same routes):
    GET  /api/status              device state, uptime, last action
    GET  /api/config              {path, raw, effective, warnings}
    PUT  /api/config              validate, atomic-write, hot-reload
    POST /api/config/reload       re-read the file (after SSH edits)
    GET  /api/events?limit=50     recent log/timer events (newest first)
    POST /api/trigger/{trigger}   simulate a button press

Submitted configs go through the exact parser the service uses
(config.parse_config); anything invalid falls back per-key and the
fallback warnings are returned to the caller, so the editor can show
what was actually accepted.

No auth: this binds to the LAN like any homelab device. Front it with a
reverse proxy if it ever needs to face an untrusted network.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as time_of_day
from pathlib import Path

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .audio import ToneLibrary
from .config import TRIGGER_TYPES, ConfigManager, as_dict, parse_config
from .device import ButtonDevice, MockDevice, Sound, TriggerType
from .rules import resolve
from .store import EventStore

log = logging.getLogger(__name__)

# Windows' registry sometimes maps .js to text/plain, which browsers reject
# for <script type="module">. Pin it so the config-menu ES modules load.
mimetypes.add_type("text/javascript", ".js")

_WEB = Path(__file__).parent / "web"
_INDEX = _WEB / "index.html"
_STATIC = _WEB / "static"


@dataclass
class WebContext:
    # status and clock are main.DeviceStatus / main.Clock - duck-typed to
    # avoid an import cycle with main.
    cm: ConfigManager
    store: EventStore
    status: object
    device: ButtonDevice
    clock: object
    tones: ToneLibrary
    # Asks the run loop to shut down gracefully. None when nothing provided
    # one (tests, and anything embedding the app), in which case the stop
    # endpoint reports that it cannot oblige rather than pretending it did.
    on_stop: object = None


class _WarningCollector(logging.Handler):
    """Captures the config parser's WARNING+ records so the API can
    return them to the editor instead of burying them in the journal."""

    def __init__(self, sink: list[str]):
        super().__init__(level=logging.WARNING)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record.getMessage())


def _parse_with_warnings(raw: dict):
    warnings: list[str] = []
    config_log = logging.getLogger("aibutton.config")
    collector = _WarningCollector(warnings)
    config_log.addHandler(collector)
    try:
        cfg = parse_config(raw)
    finally:
        config_log.removeHandler(collector)
    return cfg, warnings


def _read_raw(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _active_modes(ctx: WebContext) -> dict[str, str | None]:
    """Which mode would answer each gesture if you pressed right now.

    Uses the loop's own `resolve()` rather than a second copy of the rules in
    JavaScript: which mode wins is a host decision, and the editor's "active
    now" mark is only allowed to report it. Takeover modes never appear here -
    they own the button through main.py, not through ambient resolution.
    """
    cfg = ctx.cm.config
    now = ctx.clock.now()
    resolved = {}
    for trigger in TRIGGER_TYPES:
        match = resolve(cfg.modes, trigger, now, ctx.store.logged_today)
        resolved[trigger] = match[0].name if match else None
    return resolved


def create_app(ctx: WebContext) -> FastAPI:
    app = FastAPI(title="AI Button", version=__version__)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_INDEX)

    @app.get("/api/status")
    async def status():
        s = ctx.status
        cfg = ctx.cm.config
        return {
            "state": s.state,
            "device_name": cfg.ble_device_name,
            "uptime_s": int(time.time() - s.started_at),
            "config_path": ctx.cm.path,
            "mode_count": len(cfg.modes),
            # Which mode would answer each gesture if you pressed right now.
            # Resolved with the loop's own resolve(), not a second copy of the
            # rules in JavaScript: "who handles this press" is a host decision,
            # and the editor only marks what the host reports.
            "active_modes": _active_modes(ctx),
            "last_trigger": s.last_trigger,
            "last_mode": s.last_mode,
            "last_ok": s.last_ok,
            "last_message": s.last_message,
            "version": __version__,
            # Drives the virtual device panel: with no real hardware behind
            # the seam, the browser *is* the LED and the buzzer.
            "mock": isinstance(ctx.device, MockDevice),
            # False while a real button is out of range or unplugged - the
            # app keeps running, so the UI has to say why nothing lights up.
            "device_connected": ctx.device.connected,
            # True when the event database could not be opened and history is
            # being kept in memory. The button still works, so the UI has to
            # say why the Events tab will be empty again after a restart.
            "store_degraded": ctx.store.degraded,
            "now": ctx.clock.now().isoformat(timespec="seconds"),
            "clock_override": ctx.clock.overridden,
            "led_state": s.led_state,
            "last_sound": s.last_sound,
            "sound_seq": s.sound_seq,
            # Small enough to ride along on the status poll, and doing so is
            # what keeps the virtual device honest: it renders the palette the
            # hardware was actually sent (ctx.device.palette), not the config
            # snapshot - the two briefly disagree while e.g. a metronome
            # session is pushing a live tempo override.
            "led_palette": {
                name: {
                    "style": e.style,
                    "color": e.color,
                    "color2": e.color2,
                    "period_s": e.period_s,
                }
                for name, e in ctx.device.palette.items()
            },
        }

    @app.get("/api/config")
    async def get_config():
        raw = _read_raw(ctx.cm.path)
        warnings: list[str] = []
        if isinstance(raw, dict):
            _, warnings = _parse_with_warnings(raw)
        return {
            "path": ctx.cm.path,
            "raw": raw,
            "effective": as_dict(ctx.cm.config),
            "warnings": warnings,
        }

    @app.put("/api/config")
    async def put_config(body: dict = Body(...)):
        _, warnings = _parse_with_warnings(body)
        path = Path(ctx.cm.path)
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            raise HTTPException(500, f"cannot write {path}: {exc}")
        ctx.cm.reload()
        return {
            "path": ctx.cm.path,
            "raw": body,
            "effective": as_dict(ctx.cm.config),
            "warnings": warnings,
        }

    @app.post("/api/service/stop")
    async def stop_service():
        """Shut the service down the way Ctrl+C would.

        This exists because Windows has no way for one process to ask
        another to stop politely: SIGTERM is never delivered across
        processes, and console control events need a console the tray
        control panel does not have. The alternative is `TerminateProcess`,
        which skips the run loop's cleanup - open timers left dangling and a
        ringing alarm left ringing on the device.

        No new exposure worth noting: this API already lets any caller
        rewrite the whole config (see this module's header - it is
        unauthenticated by design and expects a trusted network).
        """
        if ctx.on_stop is None:
            raise HTTPException(503, "this service was not started with a stop hook")
        ctx.on_stop()
        return {"stopping": True}

    @app.post("/api/config/validate")
    async def validate_config(body: dict = Body(...)):
        """Dry-run the parser without writing or reloading - the config
        menu calls this to preview what would be accepted (and which keys
        would fall back) before the user commits a Save."""
        cfg, warnings = _parse_with_warnings(body)
        return {"effective": as_dict(cfg), "warnings": warnings}

    @app.post("/api/config/reload")
    async def reload_config():
        ctx.cm.reload()
        return {"effective": as_dict(ctx.cm.config)}

    @app.get("/api/events")
    async def events(limit: int = 50):
        rows = ctx.store.recent(min(max(limit, 1), 500))
        return [
            {"ts": ts, "kind": kind, "name": name, "duration_s": duration, "mode": mode}
            for ts, kind, name, duration, mode in rows
        ]

    @app.post("/api/trigger/{trigger}")
    async def trigger(trigger: str):
        if trigger not in TRIGGER_TYPES:
            raise HTTPException(404, f"unknown trigger {trigger!r}")
        ctx.device.press(TriggerType(trigger))
        return {"queued": trigger}

    @app.post("/api/dev/clock")
    async def set_clock(body: dict = Body(...)):
        """Test clock: {"time": "06:30"} or {"time": "2026-06-15T06:30"}
        shifts rule-resolution time; {"clear": true} returns to real time.
        Never persists across restarts."""
        if body.get("clear"):
            ctx.clock.clear()
        else:
            raw = body.get("time")
            if not isinstance(raw, str):
                raise HTTPException(422, "body needs 'time' (HH:MM or ISO) or 'clear': true")
            try:
                target = datetime.fromisoformat(raw)
            except ValueError:
                try:
                    target = datetime.combine(date.today(), time_of_day.fromisoformat(raw))
                except ValueError:
                    raise HTTPException(422, f"cannot parse time {raw!r}")
            ctx.clock.set(target)
            log.info("test clock set to %s", ctx.clock.now().isoformat(timespec="seconds"))
        return {
            "now": ctx.clock.now().isoformat(timespec="seconds"),
            "clock_override": ctx.clock.overridden,
        }

    @app.get("/api/dev/sound/{name}")
    async def dev_sound(name: str):
        """The actual synthesized WAVs, so the browser plays exactly what
        the device buzzer would."""
        try:
            sound = Sound(name)
        except ValueError:
            raise HTTPException(404, f"unknown sound {name!r}")
        path = ctx.tones.path_for(sound)
        if path is None or not path.exists():
            raise HTTPException(404, "sound files unavailable")
        return FileResponse(path, media_type="audio/wav")

    # The config-menu ES modules (web/static/*.js) - index.html imports them.
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    return app


def make_server(app: FastAPI, host: str, port: int) -> uvicorn.Server:
    class _NoSignals(uvicorn.Server):
        def install_signal_handlers(self) -> None:
            pass  # main.py owns SIGTERM/SIGINT/SIGHUP

    return _NoSignals(uvicorn.Config(app, host=host, port=port, log_level="warning"))
