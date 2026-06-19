"""Web UI + REST API for the AI Button.

Runs inside the button service's own asyncio process - main.py starts
uvicorn as a task sharing the live ConfigManager, EventStore, and the
button's trigger queue. No second service, no IPC. The page at / is a
single static file (web/index.html), no build step.

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

import asyncio
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
from .audio import Sound
from .config import ConfigManager, as_dict, parse_config
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
    # status, clock, sounds are main.DeviceStatus / main.Clock /
    # audio.SoundPlayer - duck-typed to avoid an import cycle with main.
    cm: ConfigManager
    store: EventStore
    status: object
    trigger_queue: asyncio.Queue
    clock: object
    sounds: object
    mock: bool = False


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
            "last_trigger": s.last_trigger,
            "last_mode": s.last_mode,
            "last_ok": s.last_ok,
            "last_message": s.last_message,
            "version": __version__,
            "mock": ctx.mock,
            "now": ctx.clock.now().isoformat(timespec="seconds"),
            "clock_override": ctx.clock.overridden,
            "led_state": s.led_state,
            "last_sound": s.last_sound,
            "sound_seq": s.sound_seq,
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
            raise HTTPException(500, f"cannot write {path}: {exc}") from exc
        ctx.cm.reload()
        return {
            "path": ctx.cm.path,
            "raw": body,
            "effective": as_dict(ctx.cm.config),
            "warnings": warnings,
        }

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
            {"ts": ts, "kind": kind, "name": name, "duration_s": duration}
            for ts, kind, name, duration in rows
        ]

    @app.post("/api/trigger/{trigger}")
    async def trigger(trigger: str):
        from .button import TriggerType  # deferred: pulls in gpiozero

        try:
            kind = TriggerType(trigger)  # accepts quintuple_tap (the 5-tap toggle) too
        except ValueError:
            raise HTTPException(404, f"unknown trigger {trigger!r}") from None
        ctx.trigger_queue.put_nowait(kind)
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
                    raise HTTPException(422, f"cannot parse time {raw!r}") from None
            ctx.clock.set(target)
            log.info("test clock set to %s", ctx.clock.now().isoformat(timespec="seconds"))
        return {
            "now": ctx.clock.now().isoformat(timespec="seconds"),
            "clock_override": ctx.clock.overridden,
        }

    @app.get("/api/dev/sound/{name}")
    async def dev_sound(name: str):
        """The actual synthesized WAVs, so the browser plays exactly what
        the device speaker would."""
        try:
            sound = Sound(name)
        except ValueError:
            raise HTTPException(404, f"unknown sound {name!r}") from None
        path = ctx.sounds.path_for(sound)
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
