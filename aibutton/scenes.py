"""Scenes - swappable, offline-editable button configs.

A scene is a JSON file in `scenes/` holding as much of a config as you like.
`config.json` says which one is active, and the active scene is layered over
it *as raw JSON* before the parser ever runs:

    config.json                     scenes/focus.json
    { "web_port": 8080,             { "name": "Focus",
      "scenes": {                     "modes": [ ... ] }
        "dir": "scenes",
        "active": "focus" },
      "modes": [ ... ] }            -> modes come from the scene,
                                       web_port from the base

That the merge happens on raw dicts is the whole trick: `parse_config` still
sees one dict, so every per-key fallback, every warning and the web API's
validate endpoint apply to scene files with no second parser anywhere. Which
is also why this module imports nothing from the package - `config` imports
*it*, not the reverse, exactly like [device.py](device.py).

Scenes are meant to be edited with nothing running: they are plain files,
`python -m aibutton.scenes check <file>` validates one against the real
parser with the service stopped, and a file that fails to parse is still
listed (with its error) rather than quietly vanishing from the picker.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DIR = "scenes"
SUFFIX = ".json"

# Scene-file keys that are not config. `name` labels the scene in the picker,
# so renaming one doesn't mean moving a file and an exported scene keeps its
# label; it is dropped on merge because parse_config would flag it as unknown.
_META_KEYS = ("name",)

# A scene never repoints the active scene: that is the one key which would let
# loading a scene change which scene loads. Dropping it kills the loop, and
# stops an imported file from taking the pointer over on first load.
_FORBIDDEN_KEYS = ("scenes",)

# Rejected anywhere in a scene id. Ids are filenames *and* they arrive off the
# wire in a URL path, so this is a containment check, not a style one.
_UNSAFE_CHARS = set('/\\:*?"<>|')


# --- settings -----------------------------------------------------------

@dataclass(frozen=True)
class SceneSettings:
    """The `scenes` block of config.json: where scenes live and which one is
    active. `active` is None when scenes are switched off, which is what every
    config that predates this feature parses to."""

    dir: str = DEFAULT_DIR
    active: str | None = None


def parse_settings(raw) -> SceneSettings:
    """Parse the `scenes` block, falling back per key - a bad `active` costs
    you the scene, not the whole config (config.py's `_parse_effect` shape)."""
    defaults = SceneSettings()
    if raw is None:
        return defaults
    if not isinstance(raw, dict):
        log.error("config: 'scenes' must be an object - ignoring it")
        return defaults

    directory = raw.get("dir", defaults.dir)
    if not (isinstance(directory, str) and directory.strip()):
        log.error("config: scenes.dir must be a non-empty string - using %r", defaults.dir)
        directory = defaults.dir

    active = raw.get("active", defaults.active)
    if active in (None, ""):
        active = None
    elif not (isinstance(active, str) and safe_id(active)):
        log.error(
            'config: scenes.active must name a scene file like "focus" - '
            "running without a scene",
        )
        active = None

    return SceneSettings(dir=directory, active=active)


def settings_to_dict(settings: SceneSettings) -> dict:
    """JSON-ready view; round-trips through parse_settings."""
    return {"dir": settings.dir, "active": settings.active}


# --- the merge (pure) ---------------------------------------------------

def merge(base: dict, scene: dict) -> dict:
    """Layer a scene's raw JSON over the base config's raw JSON.

    Shallow and key-by-key on purpose. A scene that defines `modes` replaces
    the list wholesale - half of one modes list spliced into half of another
    is nobody's intent - while a scene that says nothing about `led_palette`
    inherits the base's, which is exactly what testing two arrangements of the
    same modes against one set of colours needs.

    Pure: the caller does the reading, and the result is raw JSON rather than
    an AppConfig, so the single parser downstream stays the only validator.
    """
    merged = dict(base)
    for key, value in scene.items():
        if key in _META_KEYS:
            continue
        if key in _FORBIDDEN_KEYS:
            log.warning("scene: %r is not allowed inside a scene file - ignored", key)
            continue
        merged[key] = value
    return merged


# --- ids and paths (pure) -----------------------------------------------

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """A display name -> a file stem, for scenes *created* through the UI.
    Hand-made files keep whatever you named them (see `safe_id`); this only
    decides what "Save as: Deep Focus" writes to disk."""
    slug = _SLUG_STRIP.sub("-", (name or "").strip().lower()).strip("-")
    return slug[:64] or "scene"


def safe_id(scene_id) -> bool:
    """True when `scene_id` can only name a file directly inside the scenes
    directory.

    Ids come off the wire, so this is a containment check: anything with a
    separator, a drive letter or a leading dot could reach outside. It
    deliberately does *not* insist on slug-shaped names - `My Focus.json` is a
    perfectly good hand-made scene, and hiding it from the picker because of
    the space would punish exactly the offline editing this exists for.
    """
    if not isinstance(scene_id, str) or not scene_id or scene_id in (".", ".."):
        return False
    if scene_id.startswith("."):
        return False
    return not (set(scene_id) & _UNSAFE_CHARS)


def unique_id(taken, wanted: str) -> str:
    """`focus` -> `focus-2` when `focus` is taken. Ids are filenames, so a
    collision would silently overwrite somebody's scene."""
    existing = set(taken)
    if wanted not in existing:
        return wanted
    n = 2
    while f"{wanted}-{n}" in existing:
        n += 1
    return f"{wanted}-{n}"


def dir_for(config_path: str, settings: SceneSettings) -> Path:
    """Where the scenes live, resolved relative to the *config file* rather
    than the working directory: `--config /elsewhere/config.json` should find
    `/elsewhere/scenes/`. (`database_path` is cwd-relative because it is a
    service path; this one is a sibling of the file being edited.)"""
    directory = Path(settings.dir)
    if directory.is_absolute():
        return directory
    return Path(config_path).expanduser().resolve().parent / directory


def path_for(config_path: str, settings: SceneSettings, scene_id: str) -> Path | None:
    """The file a scene id names, or None when the id is not safe."""
    if not safe_id(scene_id):
        log.error("scenes: %r is not a usable scene name - ignored", scene_id)
        return None
    return dir_for(config_path, settings) / f"{scene_id}{SUFFIX}"


# --- files --------------------------------------------------------------

def read_json(path: Path) -> dict | None:
    """A JSON object from `path`, or None (logged) for anything else. Missing
    is not logged here - the callers all have a better sentence for it."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        log.error("scenes: cannot read %s (%s)", path, exc)
        return None
    if not isinstance(data, dict):
        log.error("scenes: top level of %s is not an object", path)
        return None
    return data


def write_json(path: Path, payload: dict) -> None:
    """Write atomically - tmp file then `os.replace`, the same dance the
    config API does. A half-written scene file is a config that vanished."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class SceneInfo:
    """One entry in the picker. `mode_count` is None and `error` is set when
    the file could not be read - counted straight off the raw list rather than
    parsed, because a picker does not need a parser."""

    id: str
    name: str
    path: Path
    mode_count: int | None = None
    error: str = ""


def _info(path: Path) -> SceneInfo:
    scene_id = path.stem
    raw = read_json(path)
    if raw is None:
        return SceneInfo(
            id=scene_id, name=scene_id, path=path,
            error="not a readable JSON object",
        )
    name = raw.get("name")
    modes = raw.get("modes")
    return SceneInfo(
        id=scene_id,
        name=name if isinstance(name, str) and name.strip() else scene_id,
        path=path,
        mode_count=len(modes) if isinstance(modes, list) else None,
    )


def list_scenes(directory: Path) -> list[SceneInfo]:
    """Every scene file in `directory`, readable or not.

    A broken file is listed *with* its error rather than hidden: these are
    meant to be hand-edited, and a scene silently disappearing from the picker
    after a stray comma is the worst possible way to learn about the comma.
    """
    try:
        paths = sorted(p for p in directory.glob(f"*{SUFFIX}") if p.is_file())
    except OSError as exc:
        log.error("scenes: cannot list %s (%s)", directory, exc)
        return []
    return [_info(p) for p in paths]


def set_active(config_path: str, scene_id: str | None) -> None:
    """Point config.json at a scene, leaving every other key alone.

    Rewrites the raw file rather than serialising an AppConfig, so key order
    and any keys this version doesn't know about survive a switch. Refuses to
    write when the existing file can't be read: replacing an unreadable config
    with a two-key stub would destroy a file you can still fix by hand.
    """
    path = Path(config_path)
    raw = read_json(path)
    if raw is None:
        raise OSError(f"cannot read {path} - refusing to overwrite it")
    block = raw.get("scenes")
    block = dict(block) if isinstance(block, dict) else {}
    if scene_id is None:
        block.pop("active", None)
    else:
        if not safe_id(scene_id):
            raise ValueError(f"{scene_id!r} is not a usable scene name")
        block["active"] = scene_id
    raw["scenes"] = block
    write_json(path, raw)


# --- CLI ----------------------------------------------------------------
#
# `python -m aibutton.scenes ...` - the offline half of this feature. It runs
# the real parser, which is the reason there is no second validator in the
# editor's JavaScript.

def _cli(argv: list[str] | None = None) -> int:
    import argparse

    # Deferred exactly like main.py's: config imports *this* module, so
    # importing it at module scope would be a cycle.
    from .config import DEFAULT_CONFIG_PATH, load_config_full, parse_with_warnings

    parser = argparse.ArgumentParser(
        prog="python -m aibutton.scenes",
        description="List, validate and switch button scenes - works with the service stopped.",
    )
    parser.add_argument(
        "--config", default=os.environ.get("AIBUTTON_CONFIG", DEFAULT_CONFIG_PATH),
        help="config path (default: $AIBUTTON_CONFIG or ./config.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show every scene and which one is active")
    check = sub.add_parser("check", help="validate a scene against the real parser")
    check.add_argument("scene", nargs="?", help="a scene id or a path to a file (default: the active scene)")
    activate = sub.add_parser("activate", help="make a scene the active one")
    activate.add_argument("scene", help="a scene id, or 'none' to run the base config alone")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
    loaded = load_config_full(args.config)
    settings = loaded.config.scenes
    directory = dir_for(args.config, settings)

    if args.command == "list":
        entries = list_scenes(directory)
        print(f"{directory}  (active: {settings.active or 'none'})")
        if not entries:
            print("  no scenes yet")
        for info in entries:
            mark = "*" if info.id == settings.active else " "
            detail = info.error or (
                f"{info.mode_count} mode(s)" if info.mode_count is not None else "no modes of its own"
            )
            print(f" {mark} {info.id:<24} {info.name:<24} {detail}")
        if loaded.scene_error:
            print(f"\n! {loaded.scene_error}")
        return 1 if loaded.scene_error else 0

    if args.command == "check":
        target = args.scene or settings.active
        if not target:
            print("no scene given and none is active")
            return 2
        path = Path(target) if (os.sep in target or target.endswith(SUFFIX)) else path_for(
            args.config, settings, target
        )
        if path is None or not path.exists():
            print(f"no such scene: {target}")
            return 2
        try:
            # Parsed here rather than through read_json so the line and column
            # land on stdout with everything else - that detail is the whole
            # point of running `check` on a file you are editing by hand.
            with open(path, encoding="utf-8") as f:
                scene_raw = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: {exc}")
            return 1
        if not isinstance(scene_raw, dict):
            print(f"{path}: top level is not an object")
            return 1
        base_raw = read_json(Path(args.config)) or {}
        _, warnings = parse_with_warnings(merge(base_raw, scene_raw))
        if warnings:
            print(f"{path}: would load with {len(warnings)} warning(s):")
            for line in warnings:
                print(f"  - {line}")
            return 1
        print(f"{path}: ok")
        return 0

    if args.command == "activate":
        target = None if args.scene.lower() in ("none", "-") else args.scene
        if target is not None:
            path = path_for(args.config, settings, target)
            if path is None or not path.exists():
                print(f"no such scene: {target}")
                return 2
        try:
            set_active(args.config, target)
        except (OSError, ValueError) as exc:
            print(f"could not switch: {exc}")
            return 1
        print(f"active scene: {target or 'none'}")
        # The running service (if any) picks this up on SIGHUP or a reload;
        # say so rather than implying the button already changed.
        print("restart the service or POST /api/config/reload to apply it")
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via _cli in tests
    raise SystemExit(_cli())
