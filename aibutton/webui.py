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
    GET  /api/scenes              the saved scenes and which is active
    POST /api/scenes              create one (from the current config, or blank)
    PUT  /api/scenes/{id}         overwrite one
    POST /api/scenes/{id}/activate  switch to it, hot
    DELETE /api/scenes/{id}       delete one (never the active one)
    GET  /api/events?limit=50     recent events, newest first; filter with
                                  kind/name/mode/since/until
    GET  /api/events/kinds        the kinds actually present in the log
    GET  /api/events/export       the same rows, as a csv or json download
    GET  /api/midi/ports          MIDI ports this machine can reach (out/in)
    POST /api/trigger/{trigger}   simulate a button press
    POST /api/reflex/{name}       fire a configured reflex (TODO 71)
    POST /api/dev/led             show one look now, saving nothing

Submitted configs go through the exact parser the service uses
(config.parse_config); anything invalid falls back per-key and the
fallback warnings are returned to the caller, so the editor can show
what was actually accepted.

With a scene active, `PUT /api/config` writes the *scene* file rather than
config.json (`ConfigManager.write_path`). Anything a scene changes that is only
read at startup comes back as `needs_restart`, because a switch that reloads
cleanly and then quietly does nothing is the worst answer available.

No auth: this binds to the LAN like any homelab device. Front it with a
reverse proxy if it ever needs to face an untrusted network.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import mimetypes
import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as time_of_day
from pathlib import Path

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, midi_io, scenes, sequencer
from .audio import ToneLibrary
from .config import (
    TRIGGER_TYPES,
    AppConfig,
    ConfigManager,
    LedEffect,
    as_dict,
    flash_safe,
    look_to_dict,
    parse_look_with_warnings,
    parse_with_warnings,
)
from .device import ButtonDevice, LEDState, MockDevice, Sound, TriggerType
from .rules import resolve
from .store import EventStore

log = logging.getLogger(__name__)

# Config keys the service only reads once, at startup: the store and its lock
# are opened, the web server bound and the BLE name scanned for before any of
# this can change. A scene that changes one reloads perfectly and then appears
# to do nothing, so every scene response says which ones differ from what the
# process actually started with.
_STARTUP_ONLY = ("ble_device_name", "database_path", "web_enabled", "web_host", "web_port")

# One row's columns, in the order the export writes them. Mirrors what
# EventStore.recent selects; the CSV header is generated from this rather than
# typed out, so a new column cannot appear in the JSON and go missing from the
# spreadsheet.
_EVENT_FIELDS = ("ts", "kind", "name", "duration_s", "mode", "value")
# The most rows any single request will return. A ceiling rather than
# pagination because this log is a few rows a day: it exists so a hand-made
# query cannot ask the service to build a 200 MB string.
_EVENT_EXPORT_MAX = 10000

# Windows' registry sometimes maps .js to text/plain, which browsers reject
# for <script type="module">. Pin it so the config-menu ES modules load.
mimetypes.add_type("text/javascript", ".js")

_WEB = Path(__file__).parent / "web"
_INDEX = _WEB / "index.html"
_STATIC = _WEB / "static"

# See the mount below: no build step means no cache-busting filenames, so the
# only safe answer for this page's own assets is not to cache them.
_NO_STORE = {"Cache-Control": "no-store, must-revalidate"}


class _NoStoreStatic(StaticFiles):
    """StaticFiles that never lets a browser hold on to a module."""

    def file_response(self, *args, **kwargs) -> Response:  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers.update(_NO_STORE)
        return response


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
    # Shows one look on the LED now and answers with what actually went out -
    # main.show_look. None when nothing provided one (tests, and anything
    # embedding the app), in which case the preview endpoint pushes a plain
    # effect straight at the device and says so for a sequence: driving a
    # schedule needs the cancellable task and the safety gate main owns, and a
    # second copy of either here is exactly the drift CLAUDE.md warns about.
    show_look: object = None
    # Queues an inbound reflex for the run loop to dispatch - main.fire_reflex.
    # None when nothing provided one (tests, and anything embedding the app),
    # in which case the endpoint says it cannot oblige rather than accepting a
    # circumstance nothing will ever act on.
    fire_reflex: object = None
    # The config as it was when this process started, kept only to answer
    # "does switching to that scene need a restart?" - see _STARTUP_ONLY.
    startup_config: AppConfig | None = None


def _effect_dict(effect):
    """A LedEffect as JSON, or None. One definition, because the palette and
    the ephemeral effect are the same nine bytes on the wire and the browser
    paints them with the same function."""
    if effect is None:
        return None
    return {
        "style": effect.style,
        "color": effect.color,
        "color2": effect.color2,
        "period_s": effect.period_s,
    }


def _read_raw(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _needs_restart(ctx: WebContext) -> list[str]:
    """Which startup-only keys the live config now disagrees with the running
    process about. Empty is the normal answer; anything in here is a thing the
    user changed that will not take effect until the service is restarted."""
    started = ctx.startup_config
    if started is None:  # embedded or under test - nothing to compare against
        return []
    return [
        key for key in _STARTUP_ONLY
        if getattr(started, key) != getattr(ctx.cm.config, key)
    ]


def _scene_settings(ctx: WebContext):
    return ctx.cm.config.scenes


def _scene_path(ctx: WebContext, scene_id: str) -> Path:
    """The file a scene id names, or a 400 - `path_for` refuses anything that
    could reach outside the scenes directory, and ids arrive in a URL."""
    path = scenes.path_for(ctx.cm.path, _scene_settings(ctx), scene_id)
    if path is None:
        raise HTTPException(400, f"{scene_id!r} is not a usable scene name")
    return path


def _scene_state(ctx: WebContext, warnings: list[str] | None = None) -> dict:
    """The standard scene response: every endpoint here returns the same
    shape, so the editor re-renders from one payload however it got there."""
    loaded = ctx.cm.loaded
    settings = _scene_settings(ctx)
    return {
        "dir": str(scenes.dir_for(ctx.cm.path, settings)),
        "active": loaded.scene_id,
        # What config.json *asks* for, which differs from `active` when the
        # named scene is missing or broken - `error` then says why.
        "configured": settings.active,
        "error": loaded.scene_error,
        "write_path": ctx.cm.write_path,
        "scenes": [
            {
                "id": info.id,
                "name": info.name,
                "path": str(info.path),
                "mode_count": info.mode_count,
                "error": info.error,
                "active": info.id == loaded.scene_id,
            }
            for info in scenes.list_scenes(scenes.dir_for(ctx.cm.path, settings))
        ],
        "effective": as_dict(ctx.cm.config),
        "warnings": warnings or [],
        "needs_restart": _needs_restart(ctx),
    }


def _scene_file_body(body: dict, name: str | None) -> dict:
    """What actually gets written to a scene file.

    The editor posts the effective config, which carries a `scenes` block; that
    block belongs to config.json alone (a scene repointing the active scene is
    a loop - see scenes.merge), so it is dropped here rather than written and
    then ignored on every load. `name` leads because humans read these files.
    """
    payload = {key: value for key, value in body.items() if key != "scenes"}
    return {"name": name, **payload} if name else payload


def _write_scene(ctx: WebContext, path: Path, payload: dict) -> list[str]:
    """Write a scene and return the warnings it would load with. Validation is
    against the *merged* result, since that is what the service will run."""
    base = _read_raw(ctx.cm.path) or {}
    _, warnings = parse_with_warnings(scenes.merge(base, payload))
    try:
        scenes.write_json(path, payload)
    except OSError as exc:
        raise HTTPException(500, f"cannot write {path}: {exc}")
    return warnings


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
        return FileResponse(_INDEX, headers=_NO_STORE)

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
            # What the button said it is when we last connected - the two
            # questions a silent button raises: which firmware is on it, and
            # does it even have the part you are waiting to see or hear.
            # protocol_version 0 means it predates DEVICE_INFO, so these are
            # assumptions rather than answers.
            "device_info": {
                "protocol_version": ctx.device.info.protocol_version,
                "firmware": ctx.device.info.firmware,
                "capabilities": ctx.device.info.names,
                "capabilities_absent": ctx.device.info.names_absent,
            },
            # True when the event database could not be opened and history is
            # being kept in memory. The button still works, so the UI has to
            # say why the Events tab will be empty again after a restart.
            "store_degraded": ctx.store.degraded,
            "now": ctx.clock.now().isoformat(timespec="seconds"),
            "clock_override": ctx.clock.overridden,
            "led_state": s.led_state,
            # The one-off look a takeover mode is pushing, if any (a metronome's
            # live tempo, a countdown's ramp colour). Separate from the palette
            # because that is what it is on the wire: something shown, not
            # something stored. Null otherwise, and the virtual device falls
            # back to the palette.
            "led_effect": _effect_dict(s.led_effect),
            "last_sound": s.last_sound,
            "sound_seq": s.sound_seq,
            # Rides along on the status poll, which is what keeps the virtual
            # device honest: it renders the palette the hardware was actually
            # sent (ctx.device.palette), not the config snapshot.
            "led_palette": {
                name: _effect_dict(e) for name, e in ctx.device.palette.items()
            },
        }

    @app.get("/api/config")
    async def get_config():
        raw = _read_raw(ctx.cm.path)
        warnings: list[str] = []
        if isinstance(raw, dict):
            _, warnings = parse_with_warnings(raw)
        return {
            "path": ctx.cm.path,
            # Where a Save actually lands - the active scene's file, when
            # there is one. The editor shows it so "saved" is never ambiguous
            # about which of two files just changed.
            "write_path": ctx.cm.write_path,
            "scene": ctx.cm.loaded.scene_id,
            "raw": raw,
            "effective": as_dict(ctx.cm.config),
            "warnings": warnings,
        }

    @app.put("/api/config")
    async def put_config(body: dict = Body(...)):
        """Save the edited config. With a scene active this writes the scene
        file, not config.json - the pointer stays behind in config.json, so
        editing a scene and switching away and back keeps your edits."""
        scene_id = ctx.cm.loaded.scene_id
        path = Path(ctx.cm.write_path)
        if scene_id is not None:
            existing = scenes.read_json(path) or {}
            payload = _scene_file_body(body, existing.get("name"))
            warnings = _write_scene(ctx, path, payload)
        else:
            _, warnings = parse_with_warnings(body)
            payload = body
            try:
                scenes.write_json(path, payload)
            except OSError as exc:
                raise HTTPException(500, f"cannot write {path}: {exc}")
        ctx.cm.reload()
        return {
            "path": ctx.cm.path,
            "write_path": ctx.cm.write_path,
            "scene": ctx.cm.loaded.scene_id,
            "raw": payload,
            "effective": as_dict(ctx.cm.config),
            "warnings": warnings,
            "needs_restart": _needs_restart(ctx),
        }

    # --- scenes ---------------------------------------------------------

    @app.get("/api/scenes")
    async def list_scenes_route():
        return _scene_state(ctx)

    @app.get("/api/scenes/{scene_id}")
    async def get_scene(scene_id: str):
        """The scene file as it sits on disk. The editor's Export button is
        this plus a download; the standalone editor reads the same shape."""
        path = _scene_path(ctx, scene_id)
        raw = scenes.read_json(path)
        if raw is None:
            raise HTTPException(404, f"no readable scene named {scene_id!r}")
        return {"id": scene_id, "path": str(path), "raw": raw}

    @app.post("/api/scenes")
    async def create_scene(body: dict = Body(...)):
        """Create a scene. `config` defaults to whatever is running now, which
        is what "save this setup as a scene" means; `activate` defaults to
        true, because a Save-as that leaves you editing the old thing is a
        trap every other editor has learned not to set."""
        name = body.get("name")
        if not (isinstance(name, str) and name.strip()):
            raise HTTPException(422, "a scene needs a name")
        name = name.strip()
        source = body.get("config")
        if source is None:
            source = as_dict(ctx.cm.config)
        if not isinstance(source, dict):
            raise HTTPException(422, "'config' must be an object")

        settings = _scene_settings(ctx)
        directory = scenes.dir_for(ctx.cm.path, settings)
        taken = {info.id for info in scenes.list_scenes(directory)}
        scene_id = scenes.unique_id(taken, scenes.slugify(name))
        path = directory / f"{scene_id}{scenes.SUFFIX}"

        warnings = _write_scene(ctx, path, _scene_file_body(source, name))
        if body.get("activate", True):
            try:
                scenes.set_active(ctx.cm.path, scene_id)
            except (OSError, ValueError) as exc:
                raise HTTPException(500, f"saved {scene_id!r} but could not switch to it: {exc}")
        ctx.cm.reload()
        return {"id": scene_id, **_scene_state(ctx, warnings)}

    @app.put("/api/scenes/{scene_id}")
    async def put_scene(scene_id: str, body: dict = Body(...)):
        """Overwrite a scene - including one that isn't active, so the editor
        can fix a scene without switching to it first."""
        path = _scene_path(ctx, scene_id)
        source = body.get("config", body)
        if not isinstance(source, dict):
            raise HTTPException(422, "'config' must be an object")
        name = body.get("name")
        if not (isinstance(name, str) and name.strip()):
            existing = scenes.read_json(path) or {}
            name = existing.get("name")
        warnings = _write_scene(ctx, path, _scene_file_body(source, name))
        if ctx.cm.loaded.scene_id == scene_id:
            ctx.cm.reload()
        return {"id": scene_id, **_scene_state(ctx, warnings)}

    @app.post("/api/scenes/{scene_id}/activate")
    async def activate_scene(scene_id: str):
        """Switch scenes, hot. `null` is a legitimate destination: it runs the
        base config on its own, which is what a config with no scenes does."""
        if scene_id != "none":
            path = _scene_path(ctx, scene_id)
            if not path.exists():
                raise HTTPException(404, f"no scene named {scene_id!r}")
        try:
            scenes.set_active(ctx.cm.path, None if scene_id == "none" else scene_id)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"cannot switch scene: {exc}")
        ctx.cm.reload()
        loaded = ctx.cm.loaded
        # The palette is pushed by the main loop's tick when it changes, so
        # nothing to do here; the LED follows within a second of the switch.
        log.info("scene switched to %r", loaded.scene_id or "none")
        _, warnings = parse_with_warnings(_read_raw(ctx.cm.write_path) or {})
        return _scene_state(ctx, warnings if loaded.scene_id is None else [])

    @app.delete("/api/scenes/{scene_id}")
    async def delete_scene(scene_id: str):
        """Refuses the active one. Deleting what the button is currently
        running would leave the service on a config whose file is gone - the
        user switches away first, deliberately."""
        path = _scene_path(ctx, scene_id)
        if not path.exists():
            raise HTTPException(404, f"no scene named {scene_id!r}")
        if ctx.cm.loaded.scene_id == scene_id:
            raise HTTPException(409, "that scene is active - switch to another one first")
        try:
            path.unlink()
        except OSError as exc:
            raise HTTPException(500, f"cannot delete {path}: {exc}")
        return _scene_state(ctx)

    @app.post("/api/service/stop")
    async def stop_service():
        """Shut the service down the way Ctrl+C would.

        The polite stop on Windows, which has no way for one process to ask
        another to stop (CLAUDE.md). The alternative is `TerminateProcess`,
        which skips the run loop's cleanup - open timers left dangling and a
        ringing alarm left ringing on the device. No new exposure: this API
        can already rewrite the whole config (see the header).
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
        cfg, warnings = parse_with_warnings(body)
        return {"effective": as_dict(cfg), "warnings": warnings}

    @app.post("/api/config/reload")
    async def reload_config():
        ctx.cm.reload()
        return {"effective": as_dict(ctx.cm.config)}

    @app.get("/api/midi/ports")
    async def midi_ports():
        """What `midi_io.ports()`/`in_ports()` can see on this machine - the
        same answer the midi action's `send()` and the metronome's
        `ClockListener.start()` would resolve a typed name against.

        `out` is what the midi action sends to, `in` what the metronome's clock
        listens on: two separately-indexed lists, exactly as midi_io keeps them
        (a machine commonly has different counts of each).

        Optional by construction, the same rule as colorEngine.js's showLook:
        both midi_io backends can be absent (no rtmidi, not Windows), which is
        a normal state rather than an error - so this never 500s, it answers
        with empty lists and a note the port field can show.
        """
        try:
            return {"available": True, "out": midi_io.ports(), "in": midi_io.in_ports(), "note": None}
        except midi_io.MidiUnavailable as exc:
            return {"available": False, "out": [], "in": [], "note": str(exc)}

    def _events(limit: int, kind, name, mode, since, until) -> list[dict]:
        """The filtered log as dicts. Shared by the JSON endpoint and the export
        so the file you download is by construction the table you were looking
        at, rather than a second filter implementation's answer."""
        rows = ctx.store.recent(
            limit=min(max(limit, 1), _EVENT_EXPORT_MAX),
            kind=kind, name=name, mode=mode, since=since, until=until,
        )
        return [
            {"ts": ts, "kind": kind_, "name": name_, "duration_s": duration,
             "mode": mode_, "value": value}
            for ts, kind_, name_, duration, mode_, value in rows
        ]

    @app.get("/api/events")
    async def events(
        limit: int = 50,
        kind: str | None = None,
        name: str | None = None,
        mode: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ):
        return _events(limit, kind, name, mode, since, until)

    @app.get("/api/events/kinds")
    async def event_kinds():
        """What the filter's kind picker should offer - read off the log
        rather than hard-coded, so a new event kind appears on its own."""
        return {"kinds": ctx.store.kinds()}

    @app.get("/api/events/export")
    async def export_events(
        format: str = "csv",
        limit: int = _EVENT_EXPORT_MAX,
        kind: str | None = None,
        name: str | None = None,
        mode: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ):
        """The same rows as /api/events, as a download.

        The default limit is the ceiling rather than 50: an export asks for the
        log, and silently handing back its most recent page is the kind of
        quiet wrong answer only noticed much later, in a spreadsheet.
        """
        if format not in ("csv", "json"):
            raise HTTPException(422, f"unknown format {format!r} - csv or json")
        rows = _events(limit, kind, name, mode, since, until)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if format == "json":
            return Response(
                content=json.dumps(rows, indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition":
                        f'attachment; filename="button-events-{stamp}.json"'
                },
            )
        buffer = io.StringIO()
        # newline="" is csv's documented requirement; StringIO honours it and
        # skipping it puts stray blank lines in the file on Windows.
        writer = csv.DictWriter(buffer, fieldnames=_EVENT_FIELDS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    f'attachment; filename="button-events-{stamp}.csv"'
            },
        )

    @app.post("/api/trigger/{trigger}")
    async def trigger(trigger: str):
        if trigger not in TRIGGER_TYPES:
            raise HTTPException(404, f"unknown trigger {trigger!r}")
        ctx.device.press(TriggerType(trigger))
        return {"queued": trigger}

    @app.post("/api/reflex/{name}")
    async def reflex(name: str, body: dict | None = Body(None)):
        """Fire a configured reflex: the one hole every other source arrives
        through (TODO 70/71).

        Anything that can make a request can drive the button - a sensor, a
        cron job, Home Assistant, an iPhone Shortcut, `curl` - which is why
        this is the first source built and why MQTT is not a dependency.

        Answering **404 for an unknown name** is most of what makes this
        usable from a script: a typo says so at the moment it is made rather
        than silently doing nothing. The queue is the run loop's, so this
        returns as soon as the circumstance is *accepted*, never when it has
        been acted on - the button may be busy, and a reflex that blocked the
        thing reporting it would be worse than a late one.

        **The body is carried, not read here** (TODO 72). A reflex may test one
        field of it - `moisture < 30` - and that test is applied by the run
        loop, in the one place `reflex_matches` is called, so this stays a
        queue and a later source (MIDI in) cannot end up with a second answer.
        The reply says the circumstance was *accepted*, never that it matched.
        """
        reflex = next(
            (r for r in ctx.cm.config.reflexes if r.name == name), None
        )
        if reflex is None:
            known = ", ".join(r.name for r in ctx.cm.config.reflexes) or "none"
            raise HTTPException(404, f"unknown reflex {name!r} (configured: {known})")
        if ctx.fire_reflex is None:
            raise HTTPException(503, "this service cannot dispatch reflexes")
        if not ctx.fire_reflex(name, body):
            raise HTTPException(503, f"too many reflexes waiting - {name!r} dropped")
        return {"queued": name}

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

    @app.post("/api/dev/led")
    async def dev_led(body: dict = Body(...)):
        """Show one look on the real LED right now, without saving it.

        What every colour picker's live preview posts to (colorEngine.js). It
        needs no new device method: "show this look" is already what an
        ephemeral effect means - the same call `run_metronome` makes - so this
        is the seam being used, not widened.

        Nothing is written and nothing is remembered: the next press, mode
        change or palette edit repaints from the config, which is what makes
        this safe to poke at while a real button is in use. `{"clear": true}`
        drops straight back to the palette without waiting for that.

        `state` picks which LED_STATE byte rides along, because that is what a
        device too old for effects falls back to rendering - and what the
        status line reports either way. IDLE is the harmless default.

        A `stops` body parses through `parse_look_with_warnings`, shared with
        the named-look pool, so a broken sequence is rejected here exactly as
        it would be on save - and **it animates**, because the push goes
        through `ctx.show_look`, which is main's own `set_led` and owns both
        the cancellable task and the `sequence_safe` gate. Previewing a stop
        list as its first colour was the honest thing this endpoint could do
        alone, and it is not a preview of a stop list; asking main for the
        driver it already has costs one callable rather than a second gate.
        With no driver attached (tests, embedded) it falls back to that first
        colour and says so in the warnings.
        """
        raw_state = body.get("state", LEDState.IDLE.value)
        try:
            state = LEDState(raw_state)
        except ValueError:
            raise HTTPException(422, f"unknown LED state {raw_state!r}")

        if body.get("clear"):
            look, warnings = None, []
        else:
            look, warnings = parse_look_with_warnings(body, "look")

        if ctx.show_look is not None:
            # One gate, and it is main's: `set_led` floors a plain effect with
            # `flash_safe` and a stop list with `sequence_safe`, then reports
            # what it actually pushed. A preview that could strobe past the
            # configured limit would be a hole in the flash floor rather than a
            # way to check it, and answering with the floored look is what
            # keeps this page describing the light and not the request.
            shown = ctx.show_look(state, look)
        else:
            if isinstance(look, sequencer.Sequence):
                warnings = warnings + [
                    "nothing is attached to drive a sequence here, so this "
                    "previews as its first stop's colour, not the animation"
                ]
                look = LedEffect(style="solid", color=look.stops[0].color)
            shown = flash_safe(look, ctx.cm.config.min_flash_period_s)
            ctx.device.set_led(state, shown)
            # Mirrors the tail of main.set_led rather than calling it - in this
            # configuration there is nothing to call. These fields are what the
            # dashboard and the virtual device render from.
            ctx.status.led_state = state.value
            ctx.status.led_effect = shown

        return {
            "state": state.value,
            # Either shape: a sequence is a look too, and the picker summarises
            # what came back rather than what it sent.
            "effect": None if shown is None else look_to_dict(shown),
            "warnings": warnings,
            "connected": ctx.device.connected,
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
    #
    # Served no-store, which for a page like this is the honest setting rather
    # than a debugging convenience. There is no build step and no hashed
    # filenames, so an edited module keeps its URL; a browser that caches it
    # then runs *last* week's editor against this week's service, and an ES
    # module graph is cached per URL - a reload will not shift it, which makes
    # the failure look like the edit not having happened. The whole page is a
    # few hundred KB off localhost, so there is nothing to win by caching it.
    app.mount("/static", _NoStoreStatic(directory=_STATIC), name="static")

    return app


def make_server(app: FastAPI, host: str, port: int) -> uvicorn.Server:
    class _NoSignals(uvicorn.Server):
        def install_signal_handlers(self) -> None:
            pass  # main.py owns SIGTERM/SIGINT/SIGHUP

    return _NoSignals(uvicorn.Config(app, host=host, port=port, log_level="warning"))
