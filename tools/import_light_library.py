"""Turn a curated table of looks into the fetched light library (TODO 113).

    ./.venv/Scripts/python tools/import_light_library.py                  # seed from schema.js
    ./.venv/Scripts/python tools/import_light_library.py --source looks.csv
    ./.venv/Scripts/python tools/import_light_library.py --source a.json --source b.csv --seed
    ./.venv/Scripts/python tools/import_light_library.py --dry-run        # report only, write nothing

**This is an importer, not a generator.** The rows are curated elsewhere - by
hand, or by an LLM given `docs/light-library-format.md` - and handed here as
CSV or JSON. What this owns is the *contract*: what a row must be, what makes
one unfit to ship, and what the browser eventually fetches.

**Three things it refuses to do quietly.**

- **It never clamps.** A row the flash floor would rewrite is *rejected with a
  reason*, exactly as `appc.py`'s `_look_bytes` applies the floor where the
  bytes are made. CLAUDE.md's argument is that clamping a setting silently
  makes it a lie; clamping a *preset* is worse, because the swatch that sold
  it renders one thing and the button does another. Both floors apply -
  `config.flash_safe` for a strobing style, `config.sequence_safe` for a stop
  list's dwell, one-shot-of-three exemption included.
- **It never guesses at a key it does not know.** An unknown key inside a
  `look` is a rejection, because the parser would ignore `perod_s` in silence
  and ship a look nobody chose. There is no legacy to be kind to in a table
  written this week.
- **It ships the parser's own output.** Every accepted effect and stop list is
  re-serialised from what `config` parsed, so the bytes in the library are by
  construction the bytes the parser produces. (One exception, `morse`: see
  `_look_body`.)

**Dedupe is the point, not a tidy-up.** TODO 113: "a library of 8,000 looks
anybody can find in three keystrokes beats 40,000 nobody can tell apart." Two
rows within `--delta-e` in CIELAB, at rates within `--rate-ratio`, in the same
style class, are one row - and the survivor inherits the loser's tags, so the
search that would have found either still finds the one.

Curated rows (`curated: true`, and everything `--seed` produces) are exempt
from dedupe and kept whole: they are the overlay TODO 113 keeps on top of the
generated bank, and the one thing `tests/test_light_library.py` validates
entry by entry.

The emitted layout, and why, is `docs/light-library-format.md`. Read that
before changing anything here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aibutton import sequencer  # noqa: E402
from aibutton.config import (  # noqa: E402
    DRIVE_TEMPLATES,
    LedEffect,
    flash_safe,
    parse_look_with_warnings,
    sequence_safe,
)
from aibutton.device import (  # noqa: E402
    LED_STYLES,
    SAFE_MIN_PERIOD_S,
    STYLE_STROBES,
    STYLE_USES_COLOR2,
    STYLE_USES_SATURATION,
)

SCHEMA_JS = ROOT / "aibutton" / "web" / "static" / "schema.js"
OUT_DIR = ROOT / "aibutton" / "web" / "library"

# Bumped when the *shape* of index.json or a shard changes in a way a page
# written against the old one would misread. Adding a key nothing needs to
# read is not that; removing or re-meaning one is.
FORMAT_VERSION = 1

# What the page falls back to when the library is not fetchable at all - the
# offline `tools/build_editor.py` bundle being the case that matters. Written
# into the manifest so the contract is machine-visible rather than folklore.
FALLBACK_SOURCE = "aibutton/web/static/schema.js:LOOK_PRESETS"

# --- the two numbers that decide how big the library is -------------------
#
# CIE76 delta-E. A just-noticeable difference under laboratory conditions is
# ~2.3; this is deliberately looser, because the thing rendering these is one
# diffused RGB LED across the room, not a print proof. Raise it for a smaller,
# sharper library; lower it for a bigger one with more near-neighbours.
DELTA_E_DEFAULT = 5.0

# Rate is perceived logarithmically, so "the same speed" is a ratio, not a
# difference: two looks whose periods are within this factor are one rate.
# 1.25 means a 2 s breathe and a 2.4 s breathe are the same look - which they
# are, on a single pixel, at arm's length.
RATE_RATIO_DEFAULT = 1.25

# No single fetch should block the page. A group larger than this splits into
# numbered parts; the manifest names each part and its row count.
MAX_SHARD_ROWS_DEFAULT = 2000

# How many points a stop list is sampled at to get its dedupe signature. Two
# lists that agree at all of these, in the same drive and repeat mode, are the
# same look however differently they were written.
SEQUENCE_SAMPLES = 16

# --- the quiet facet: a preference, never a gate ---------------------------
#
# TODO 108's finding: the flash floor above is a *safety* threshold sized for
# a display filling the visual field, and it says nothing about whether a
# fast blink is pleasant to sit near. `is_quiet` below answers that second,
# separate question over rows that have already cleared the floor - it never
# rejects anything, it only labels what survived. A judgement call, stated as
# one: three times the flash floor's 0.333 s default, because a strobe or
# alternate style that clears the floor still reads as an alarm from across a
# room until its full cycle is about a second - "a deliberate blink," not a
# measured line. Retune it here and nowhere else.
QUIET_MIN_PERIOD_S = 1.0

# Morse is up to five symbols a digit and four a letter (aibutton/morse.py),
# so a message keeps costing real seconds per character with no ceiling of
# its own. Long enough for "SOS", "ON AIR" or "3 2 1"; short enough that
# nobody is asked to watch a paragraph blink past on one LED. A judgement
# call too - retune it here.
MAX_MORSE_MESSAGE_CHARS = 12

# --- vocabularies ---------------------------------------------------------
#
# `family` is a facet, so it is a closed set or it is not a facet: "red",
# "Red" and "reddish" make three chips for one colour. A row may state one
# from this list; a row that states nothing gets one derived from its
# brightest colour, which is reported so a curation pass can improve it.
FAMILIES = (
    "red", "orange", "yellow", "green", "teal", "cyan", "blue", "indigo",
    "violet", "magenta", "pink", "brown", "white", "grey", "black", "rainbow",
)

# Groups where a name is likely to be somebody's trademark. See the naming
# policy in docs/light-library-format.md: colour pairs are not protectable,
# club and franchise names are. Rows in these groups have their *name shape*
# checked - it must read "<generic label> - <Colour> & <Colour>" - and the
# trademarked name is expected to live in the tags instead.
#
# This is a list of GROUPS, deliberately not a list of trademarks. A blocklist
# of names would be endless, wrong, and stale the week after it was written.
# Add a group slug here when you add a bank of club, franchise or brand
# colours.
TRADEMARK_SENSITIVE_GROUPS = frozenset({
    "teams", "clubs", "franchises", "brands", "esports", "colleges",
    "universities", "sports",
})

# The whitelist the name-shape check runs against. Also not a trademark list:
# it is the set of words a *colour* may be called, and a name whose second
# half is made only of these cannot be naming a club.
COLOUR_WORDS = frozenset({
    *FAMILIES,
    "gray", "purple", "gold", "golden", "silver", "navy", "maroon", "crimson",
    "scarlet", "amber", "lime", "mint", "aqua", "turquoise", "cobalt", "royal",
    "sky", "cream", "ivory", "charcoal", "slate", "bronze", "copper", "rose",
    "lilac", "lavender", "plum", "olive", "forest", "sand", "tan", "peach",
    "coral", "ruby", "emerald", "sapphire", "jet", "snow", "ash", "steel",
    "blush", "wine", "burgundy", "fuchsia", "sable", "onyx", "pearl", "flame",
    "light", "dark", "deep", "pale", "bright", "hot", "neon", "electric",
    "off", "and", "&", "on",
})

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")
_TAG_SPLIT = re.compile(r"[|;,]")
_NAME_PAIR = re.compile(r"^(?P<label>.+?)\s+[-–—]\s+(?P<colours>.+)$")

# Every key each look shape may carry. Anything else is a rejection: the
# parser ignores what it does not know, so a typo would ship as a default.
_EFFECT_KEYS = frozenset({"style", "color", "color2", "period_s"})
_SEQUENCE_KEYS = frozenset({"stops", "repeat", "drive"})
_STOP_KEYS = frozenset({"color", "hold_s", "fade_s", "curve"})
_MORSE_KEYS = frozenset({"morse", "dpm", "color", "ramp"})
_ROW_KEYS = frozenset({
    "id", "name", "tags", "family", "group", "look", "curated",
    # Accepted aliases, so a schema.js-shaped table imports as-is.
    "label", "effect", "sequence",
})


class SourceError(Exception):
    """A source file this importer cannot read at all (as opposed to a row it
    can read and must reject). Loud, because there is nothing to report."""


# --- rows -----------------------------------------------------------------

@dataclass(frozen=True)
class Row:
    """One library entry as it arrives, before validation.

    `where` is only ever used in the rejection report - it is how somebody
    finds the offending line in a 30,000-row spreadsheet.
    """

    id: str
    name: str
    tags: tuple[str, ...]
    family: str
    group: str
    look: dict
    curated: bool = False
    where: str = ""
    # The group's display spelling, kept beside its slug because the manifest
    # needs both: "Countdown" heads the chip, `countdown.json` is the fetch.
    group_label: str = ""


@dataclass(frozen=True)
class Accepted:
    """A row that cleared every gate, carrying what the gates worked out.

    `parsed` is the parser's own answer and `body` is that answer
    re-serialised - the bytes actually written. `signature` is what dedupe
    compares. Keeping all three means nothing downstream has to re-derive
    them, and nothing can derive them differently.
    """

    row: Row
    parsed: LedEffect | sequencer.Sequence
    body: dict
    signature: "Signature"
    derived_family: bool = False
    quiet: bool = True


@dataclass(frozen=True)
class Rejection:
    id: str
    where: str
    kind: str      # 'row' | 'look' | 'parser' | 'floor' | 'duplicate'
    reason: str


# --- colour ---------------------------------------------------------------

_D65 = (0.95047, 1.0, 1.08883)


def _channels(hexcolor: str) -> tuple[float, float, float]:
    text = hexcolor.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lab(hexcolor: str) -> tuple[float, float, float]:
    """`#rrggbb` as CIELAB (D65, 2 degree observer).

    Pure and dependency-free on purpose - this is the whole reason the dedupe
    threshold can be a number anybody can reason about rather than a magic
    constant inside a library. sRGB -> linear -> XYZ -> Lab, the textbook
    chain; `delta_e` below is CIE76, which is a plain Euclidean distance in
    this space and quite good enough to answer "can anyone tell these apart on
    one LED".
    """
    r, g, b = (_linear(c) for c in _channels(hexcolor))
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = (f(v / w) for v, w in zip((x, y, z), _D65))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    """CIE76 distance between two Lab triples."""
    return math.dist(first, second)


def _hsv(hexcolor: str) -> tuple[float, float, float]:
    r, g, b = _channels(hexcolor)
    high, low = max(r, g, b), min(r, g, b)
    span = high - low
    if span == 0:
        hue = 0.0
    elif high == r:
        hue = (60 * ((g - b) / span)) % 360
    elif high == g:
        hue = 60 * ((b - r) / span) + 120
    else:
        hue = 60 * ((r - g) / span) + 240
    return (hue, 0.0 if high == 0 else span / high, high)


_HUE_BANDS = (
    (14, "red"), (40, "orange"), (68, "yellow"), (150, "green"),
    (182, "teal"), (200, "cyan"), (250, "blue"), (275, "indigo"),
    (300, "violet"), (330, "magenta"), (348, "pink"), (360, "red"),
)


def family_of_color(hexcolor: str) -> str:
    """The facet a single colour belongs to.

    Deliberately coarse and deliberately deterministic: a facet is a first
    cut, not a taxonomy, and the tags do the fine work. A row that states its
    own `family` always wins over this.
    """
    hue, sat, val = _hsv(hexcolor)
    if val < 0.08:
        return "black"
    if sat < 0.15:
        return "white" if val > 0.7 else "grey"
    if 14 <= hue < 45 and val < 0.6 and sat > 0.4:
        return "brown"
    for edge, name in _HUE_BANDS:
        if hue < edge:
            return name
    return "red"


def _brightest(colors: tuple[str, ...]) -> str:
    return max(colors, key=lambda c: _hsv(c)[2]) if colors else "#000000"


def derive_family(parsed: LedEffect | sequencer.Sequence) -> str:
    """The family a look falls into when the row did not say.

    A rainbow is every hue, so it is its own family. Everything else is judged
    by its *brightest* colour, which is the one the eye reports when it is
    asked what colour something was.
    """
    if isinstance(parsed, sequencer.Sequence):
        return family_of_color(_brightest(tuple(s.color for s in parsed.stops)))
    if parsed.style == "rainbow":
        return "rainbow"
    colors = (parsed.color,) + ((parsed.color2,) if parsed.style in STYLE_USES_COLOR2 else ())
    return family_of_color(_brightest(colors))


def is_quiet(parsed: LedEffect | sequencer.Sequence) -> bool:
    """Whether this look is calm enough for a shared space - an office, a
    classroom, a room with someone else whose peripheral vision catches it.

    **Not the flash floor, on purpose.** That is a hard safety gate: a row
    that fails it is rejected and never exists. This runs only on rows that
    already passed, and it never rejects anything - it is a preference a
    curator or a page can filter on, the honest answer to TODO 108's finding
    that the floor is a safety line, not a comfort line, and the two must
    never be blurred into one mechanism with two names.

    Non-strobing styles never hard-cut, so they are quiet by construction -
    the same set `device.STYLE_STROBES` names for the opposite reason. A
    strobing style is a matter of degree, judged against
    `QUIET_MIN_PERIOD_S`. A stop list has no `style` at all, so what matters
    is its *fastest transition*, not any single stop's dwell - one slow stop
    beside a rapid pair still reads as a strobe - with the same
    one-shot-of-three-or-fewer exemption `sequence_safe` already makes,
    because a handful of transitions played once cannot sustain anything
    either way.
    """
    if isinstance(parsed, sequencer.Sequence):
        if not (parsed.repeat or len(parsed.stops) > 3):
            return True
        fastest_dwell = min(s.hold_s + s.fade_s for s in parsed.stops)
        return 2 * fastest_dwell >= QUIET_MIN_PERIOD_S
    if parsed.style not in STYLE_STROBES:
        return True
    return parsed.period_s >= QUIET_MIN_PERIOD_S


# --- reading source tables ------------------------------------------------

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _tags(value) -> tuple[str, ...]:
    """Tags from a list, or from one cell.

    A cell may separate with `|`, `;` or `,` - all three, because no tag
    contains any of them and an LLM asked for a comma list inside a CSV will
    reach for whichever the quoting made easiest.
    """
    if isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        parts = _TAG_SPLIT.split(str(value or ""))
    seen: list[str] = []
    for part in parts:
        tag = part.strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return tuple(seen)


def _look_from_flat(raw: dict) -> dict:
    """A `look` assembled from flat CSV columns.

    Only reached when there is no `look` / `effect` / `sequence` column; the
    JSON-in-a-cell forms above are what a table of stop lists should use.
    """
    if raw.get("morse"):
        look: dict = {"morse": raw["morse"]}
        if raw.get("dpm"):
            look["dpm"] = float(raw["dpm"])
        if raw.get("color"):
            look["color"] = raw["color"]
        return look
    if raw.get("stops"):
        look = {"stops": json.loads(raw["stops"])}
        if raw.get("repeat") not in (None, ""):
            look["repeat"] = _truthy(raw["repeat"])
        if raw.get("drive"):
            look["drive"] = raw["drive"]
        return look
    look = {"style": raw.get("style") or "solid", "color": raw.get("color") or ""}
    if raw.get("color2"):
        look["color2"] = raw["color2"]
    if raw.get("period_s") not in (None, ""):
        look["period_s"] = float(raw["period_s"])
    return look


def normalise_keys(raw: dict) -> dict:
    """A source record's keys, lowercased and stripped of a stray BOM.

    A curated table's header row is whatever the person who wrote it typed -
    `Group`, ` id `, `Period_S` - and none of that should decide whether a row
    imports.
    """
    return {str(k).strip().lstrip("﻿").lower(): v for k, v in raw.items() if k}


def row_from_mapping(raw: dict, where: str) -> Row:
    """One source record - a CSV line or a JSON object - as a `Row`.

    Anything structurally impossible raises `ValueError`, which the caller
    turns into a rejection rather than a crash: one unreadable line must not
    cost the other 29,999.
    """
    raw = normalise_keys(raw)
    look = raw.get("look") or raw.get("effect") or raw.get("sequence")
    if isinstance(look, str):
        look = json.loads(look) if look.strip() else None
    if look is None:
        look = _look_from_flat(raw)
    if not isinstance(look, dict):
        raise ValueError("look must be an object")

    label = str(raw.get("group") or "").strip()
    return Row(
        id=str(raw.get("id") or "").strip().lower(),
        name=str(raw.get("name") or raw.get("label") or "").strip(),
        tags=_tags(raw.get("tags")),
        family=str(raw.get("family") or "").strip().lower(),
        group=slug(label),
        look=look,
        curated=_truthy(raw.get("curated")),
        where=where,
        group_label=label,
    )


def read_source(path: Path) -> list[tuple[dict, str]]:
    """`(mapping, where)` pairs out of a CSV or JSON table.

    Both, because the owner's curation pass could produce either and a format
    argument is one more thing to get wrong at 2 a.m.
    """
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SourceError(f"{path}: not valid JSON ({exc})") from exc
        rows = data.get("rows") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise SourceError(f"{path}: expected an array of rows, or an object with 'rows'")
        return [
            (r if isinstance(r, dict) else {}, f"{path.name}[{i}]")
            for i, r in enumerate(rows)
        ]
    if path.suffix.lower() == ".csv":
        reader = csv.DictReader(text.splitlines())
        return [(dict(r), f"{path.name}:{i + 2}") for i, r in enumerate(reader)]
    raise SourceError(f"{path}: expected a .csv or .json table")


# --- the seed -------------------------------------------------------------

_PRESETS_RE = re.compile(r"export const LOOK_PRESETS = (\[.*?\n\]);", re.S)


def seed_rows(schema_js: Path = SCHEMA_JS) -> list[tuple[dict, str]]:
    """Today's 142 `LOOK_PRESETS`, as source records.

    Sliced out of schema.js exactly the way `tests/test_look_presets.py` does
    it - the array is strict JSON precisely so nothing has to keep a second
    copy. These arrive `curated`, which is what makes them exempt from dedupe
    and what makes them the set the tests check entry by entry.

    Their tags are *derived* (group, style, family, and the words of the
    name), which is thin next to a hand-curated row. That is honest rather
    than ideal: it gives the page real content on day one and leaves the
    tagging pass something to improve.
    """
    source = schema_js.read_text(encoding="utf-8")
    match = _PRESETS_RE.search(source)
    if not match:
        raise SourceError(f"{schema_js}: LOOK_PRESETS must stay a single JSON array literal")
    records = []
    for index, preset in enumerate(json.loads(match.group(1))):
        body = preset.get("sequence") or preset.get("effect") or {}
        group = slug(preset.get("group", ""))
        words = [w for w in re.split(r"[^a-z0-9]+", preset.get("label", "").lower()) if w]
        tags = [group, *words]
        if isinstance(body, dict) and "stops" in body:
            tags.append("sequence")
        elif isinstance(body, dict) and body.get("style"):
            tags.append(body["style"])
        records.append((
            {
                "id": preset["id"],
                "name": preset["label"],
                # The display spelling, not the slug: `row_from_mapping`
                # slugifies, and the manifest keeps this as the group's label.
                "group": preset.get("group", ""),
                "tags": tags,
                "look": body,
                "curated": True,
            },
            f"schema.js:LOOK_PRESETS[{index}]",
        ))
    return records


# --- validation -----------------------------------------------------------

def _unknown_keys(look: dict) -> str:
    """Why this look's keys are wrong, or ''.

    The parser ignores keys it does not recognise, which is the right
    behaviour for a hand-edited config and the wrong one for a table we are
    about to ship: `perod_s` would sail through and render at 1 second.
    """
    if "morse" in look:
        extra = set(look) - _MORSE_KEYS
        return f"unknown key(s) in a morse look: {', '.join(sorted(extra))}" if extra else ""
    if "stops" in look:
        extra = set(look) - _SEQUENCE_KEYS
        if extra:
            return f"unknown key(s) in a stop list: {', '.join(sorted(extra))}"
        stops = look.get("stops")
        if not isinstance(stops, list) or not stops:
            return "stops must be a non-empty list"
        for index, stop in enumerate(stops):
            if isinstance(stop, str):
                continue
            if not isinstance(stop, dict):
                return f"stops[{index}] must be a colour or an object"
            extra = set(stop) - _STOP_KEYS
            if extra:
                # `style`/`period_s` on a stop are the TODO 36e leftovers the
                # parser forgives in a config it once wrote itself. A table
                # written this week has no such history, so they are a typo.
                return f"unknown key(s) in stops[{index}]: {', '.join(sorted(extra))}"
        return ""
    extra = set(look) - _EFFECT_KEYS
    if extra:
        return f"unknown key(s) in an effect: {', '.join(sorted(extra))}"
    if not look.get("style"):
        return "an effect look needs a style"
    if look["style"] not in LED_STYLES:
        return f"style must be one of {', '.join(LED_STYLES)}"
    if not look.get("color"):
        return "an effect look needs a color"
    return ""


def _row_problem(row: Row) -> str:
    """Why this row is unusable before its look is even looked at, or ''."""
    if not row.id:
        return "no id"
    if not _ID_RE.match(row.id):
        return f"id {row.id!r} must be a lowercase slug: a-z, 0-9 and hyphens"
    if not row.name:
        return "no name"
    if not row.group:
        return "no group"
    if not row.tags:
        return "no tags - a row nobody can search for is a row nobody will find"
    if row.family and row.family not in FAMILIES:
        return f"family {row.family!r} must be one of {', '.join(FAMILIES)}"
    if not isinstance(row.look, dict) or not row.look:
        return "no look"
    return ""


def _floor_problem(
    parsed: LedEffect | sequencer.Sequence, min_flash_period_s: float
) -> str:
    """Why the safety floor would rewrite this look, or ''.

    **A gate, never a clamp** - the whole reason this function returns a
    sentence instead of a fixed-up look. Both floors, applied through the same
    two functions `main.set_led` uses, so "safe" cannot come to mean two
    different things in two places.
    """
    if isinstance(parsed, LedEffect):
        if flash_safe(parsed, min_flash_period_s) == parsed:
            return ""
        return (
            f"{parsed.style} at {parsed.period_s:.3g}s is under the "
            f"{min_flash_period_s:.3g}s flash floor - slow it down, or use a "
            f"style outside {'/'.join(sorted(STYLE_STROBES))}"
        )
    floored = sequence_safe(parsed, min_flash_period_s)
    if floored == parsed:
        return ""
    dwell_floor = min_flash_period_s / 2
    culprits = [
        f"stops[{i}] dwells {s.hold_s + s.fade_s:.3g}s"
        for i, s in enumerate(parsed.stops)
        if s.hold_s + s.fade_s < dwell_floor
    ]
    return (
        f"under the {dwell_floor:.3g}s stop floor: {', '.join(culprits[:4])}"
        f"{' ...' if len(culprits) > 4 else ''}"
        " (a one-shot of three stops or fewer is exempt; this one is not)"
    )


def _morse_problem(look: dict) -> str:
    """Why this Morse look's message is unfit to ship, or ''.

    Checked on the *written* message, before the real parser ever expands it
    into a stop list - a message over the limit has already lost before a
    single dot plays, and there is no reason to build the two-hundred-stop
    sequence just to reject it. Only reached when `"morse" in look`; a
    non-Morse look has nothing here to check.
    """
    message = look.get("morse")
    if isinstance(message, str) and len(message) > MAX_MORSE_MESSAGE_CHARS:
        return (
            f"morse message is {len(message)} characters, over the "
            f"{MAX_MORSE_MESSAGE_CHARS}-character limit - a message that long "
            "is a light show nobody watches to the end"
        )
    return ""


def _sequence_problem(parsed: sequencer.Sequence) -> str:
    """Why this stop list is unfit to ship, or ''.

    The same three properties `test_look_presets.py` asserts over the curated
    library, moved to where they can reject a row instead of failing a build:
    a cycle with length, a drive something can actually supply, and - for a
    sampled drive - a look that says something different at different points.
    """
    if sequencer.span_total(parsed) <= 0:
        return "every stop is zero-width, so there is nothing to walk or sample"
    if parsed.drive != "clock" and parsed.drive not in DRIVE_TEMPLATES:
        return f"drive {parsed.drive!r} is one nothing can supply"
    if parsed.drive != "clock":
        seen = {sequencer.sample_at(parsed, i / 24).color for i in range(25)}
        if len(seen) < 2:
            return (
                f"a {parsed.drive}-driven look that never changes colour is a "
                "flat colour with extra steps"
            )
    return ""


def _round(value: float) -> float:
    """Seconds, at the precision a light can actually be told apart at.

    Also kills float noise that would otherwise make two identical looks
    differ in the emitted bytes.
    """
    rounded = round(float(value), 4)
    return int(rounded) if rounded == int(rounded) else rounded


def _look_body(parsed: LedEffect | sequencer.Sequence, original: dict) -> dict:
    """The bytes actually written for an accepted look.

    **The parser's own output, re-serialised**, so nothing in the library can
    render differently from what the parser said it was. Keys equal to the
    parser's defaults are dropped, which at 30,000 rows is real bytes and
    costs nothing: omitted means default, on both sides.

    **`morse` is the one exception and keeps its written form.** Expanding an
    "SOS" into its stop list is two hundred stops and ~8 KB per row, and the
    compact form is what `config.json` stores anyway - so the library ships
    the thing you would paste, not the thing it becomes.
    """
    if "morse" in original:
        return dict(original)
    if isinstance(parsed, sequencer.Sequence):
        stops = []
        for stop in parsed.stops:
            entry: dict = {"color": stop.color, "hold_s": _round(stop.hold_s)}
            if stop.fade_s:
                entry["fade_s"] = _round(stop.fade_s)
            if stop.curve != "linear":
                entry["curve"] = stop.curve
            stops.append(entry)
        body: dict = {"stops": stops}
        if not parsed.repeat:
            body["repeat"] = False
        if parsed.drive != "clock":
            body["drive"] = parsed.drive
        return body
    body = {"style": parsed.style, "color": parsed.color}
    # A second colour on a style that ignores it is invisible config - it
    # shows up in the saved look and in nothing else. Rainbow is the catch:
    # there `color2` is the cycle's saturation, not a second hue.
    if parsed.style in STYLE_USES_COLOR2 or parsed.style in STYLE_USES_SATURATION:
        body["color2"] = parsed.color2
    if parsed.style != "solid":
        body["period_s"] = _round(parsed.period_s)
    return body


def check(row: Row, min_flash_period_s: float) -> Accepted | Rejection:
    """One row, through every gate, in the order that gives the best reason.

    Structure first (so a missing id is not reported as a parser problem),
    then the keys, then the real parser, then the floor, then the stop-list
    properties. Anything that comes back is either shippable or says exactly
    why it is not.
    """
    problem = _row_problem(row)
    if problem:
        return Rejection(row.id or "?", row.where, "row", problem)

    problem = _unknown_keys(row.look)
    if problem:
        return Rejection(row.id, row.where, "look", problem)

    if "morse" in row.look:
        problem = _morse_problem(row.look)
        if problem:
            return Rejection(row.id, row.where, "look", problem)

    parsed, warnings = parse_look_with_warnings(
        row.look, f"library[{row.id}]", min_flash_period_s
    )
    if warnings:
        return Rejection(row.id, row.where, "parser", "; ".join(warnings))

    problem = _floor_problem(parsed, min_flash_period_s)
    if problem:
        return Rejection(row.id, row.where, "floor", problem)

    if isinstance(parsed, sequencer.Sequence):
        problem = _sequence_problem(parsed)
        if problem:
            return Rejection(row.id, row.where, "look", problem)

    derived = not row.family
    family = row.family or derive_family(parsed)
    return Accepted(
        row=replace(row, family=family),
        parsed=parsed,
        body=_look_body(parsed, row.look),
        signature=signature_of(parsed),
        derived_family=derived,
        quiet=is_quiet(parsed),
    )


def name_problem(row: Row) -> str:
    """Why this row's name is a trademark risk, or ''.

    **The policy, decided once, at import level** (TODO 113's open question):
    colour pairs are not protectable, club and franchise names are. So a row
    in a trademark-sensitive group must be *named* generically -
    "Green Bay - Green & Gold" - and carry the club's name in its **tags**,
    where search still finds it and no shipped string claims it.

    The check is on the name's *shape*, not on a list of trademarks: after the
    dash, every word must be a colour word. A blocklist of brands would be
    endless, wrong within a month, and would fail exactly the row somebody
    added last. This warns rather than rejects, for the same reason: it is a
    heuristic, and a heuristic that deletes content is a heuristic somebody
    switches off.
    """
    if row.group not in TRADEMARK_SENSITIVE_GROUPS:
        return ""
    match = _NAME_PAIR.match(row.name)
    if not match:
        return 'name must read "<Place or generic label> - <Colour> & <Colour>"'
    words = [w for w in re.split(r"[^A-Za-z&]+", match.group("colours")) if w]
    stray = [w for w in words if w.lower() not in COLOUR_WORDS]
    if stray:
        return f"not colour words after the dash: {', '.join(stray)}"
    return ""


# --- dedupe ---------------------------------------------------------------

@dataclass(frozen=True)
class Signature:
    """What dedupe compares: a style class, a rate, and a colour vector.

    Two signatures are the same look when the classes match exactly, the rates
    are within a *ratio*, and every corresponding colour is within delta-E.
    `extra` carries the scalars that are not colours at all - a rainbow's
    saturation - compared with a plain tolerance.

    `solid` has rate 1.0 whatever its `period_s` says, because a solid colour
    does not animate and two solids at different periods are the same look.
    """

    kind: tuple
    rate: float
    colors: tuple[tuple[float, float, float], ...]
    extra: tuple[float, ...] = ()

    @property
    def centre(self) -> tuple[float, float, float]:
        """The mean Lab of `colors` - the grid cell this signature files under.

        Sound as a bucket key by the triangle inequality: if every pair of
        colours is within delta-E, the means are too, so nothing that should
        match can fall outside the neighbour search below.
        """
        n = len(self.colors)
        return tuple(sum(c[i] for c in self.colors) / n for i in range(3))  # type: ignore[return-value]


def _level(hexcolor: str) -> float:
    """A rainbow reads `color` as brightness and `color2` as saturation, each
    off the brightest channel and each `0` meaning full - see INVARIANTS.md.
    """
    value = max(_channels(hexcolor))
    return 1.0 if value == 0 else value


def signature_of(parsed: LedEffect | sequencer.Sequence) -> Signature:
    if isinstance(parsed, sequencer.Sequence):
        colors = tuple(
            lab(sequencer.sample_at(parsed, i / SEQUENCE_SAMPLES).color)
            for i in range(SEQUENCE_SAMPLES)
        )
        return Signature(
            kind=("s", parsed.drive, parsed.repeat),
            rate=max(sequencer.span_total(parsed), 1e-6),
            colors=colors,
        )
    if parsed.style == "rainbow":
        level = _level(parsed.color)
        grey = "#" + f"{int(round(level * 255)):02x}" * 3
        return Signature(
            kind=("e", "rainbow"),
            rate=parsed.period_s,
            colors=(lab(grey),),
            extra=(_level(parsed.color2),),
        )
    colors = (lab(parsed.color),)
    if parsed.style in STYLE_USES_COLOR2:
        colors += (lab(parsed.color2),)
    rate = 1.0 if parsed.style == "solid" else parsed.period_s
    return Signature(kind=("e", parsed.style), rate=rate, colors=colors)


def same_look(
    first: Signature, second: Signature, delta: float, rate_ratio: float
) -> bool:
    """Whether two signatures are one look, at these thresholds."""
    if first.kind != second.kind or len(first.colors) != len(second.colors):
        return False
    lo, hi = sorted((first.rate, second.rate))
    if lo <= 0 or hi / lo > rate_ratio:
        return False
    if any(abs(a - b) > 0.1 for a, b in zip(first.extra, second.extra)):
        return False
    return all(delta_e(a, b) <= delta for a, b in zip(first.colors, second.colors))


def _cell(sig: Signature, delta: float, rate_ratio: float) -> tuple:
    centre = sig.centre
    return (
        sig.kind,
        int(math.floor(math.log(sig.rate) / math.log(rate_ratio))),
        *(int(math.floor(v / delta)) for v in centre),
    )


def _neighbours(cell: tuple):
    kind, rate, *grid = cell
    for drate in (-1, 0, 1):
        for dl in (-1, 0, 1):
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    yield (kind, rate + drate, grid[0] + dl, grid[1] + da, grid[2] + db)


def dedupe(
    accepted: list[Accepted], delta: float, rate_ratio: float
) -> tuple[list[Accepted], list[tuple[str, str]]]:
    """`(kept, [(dropped_id, kept_id), ...])`, tags merged into the survivors.

    **Merging the loser's tags into the winner is the point**, not a
    politeness. TODO 113's number that matters is "looks anybody can find in
    three keystrokes": collapsing "Rising Sun" and "Denmark Red" into one row
    is only an improvement if the survivor is still findable by both, so the
    row that stays inherits every word that would have found the row that
    went.

    **Curated rows never collapse.** They are the hand-written overlay; a
    generated row that happens to land on one is the one that goes. They are
    indexed first so that ordering holds regardless of input order.

    Linear, not quadratic: a signature files under one Lab/rate grid cell and
    is only compared against representatives in that cell and its neighbours.
    At 30,000 rows the difference is the tool finishing or not.
    """
    grid: dict[tuple, list[int]] = {}
    kept: list[Accepted] = []
    collapsed: list[tuple[str, str]] = []
    # Curated first, so a generated near-duplicate of a curated row loses to
    # it rather than the other way round.
    order = sorted(range(len(accepted)), key=lambda i: (not accepted[i].row.curated, i))

    for index in order:
        entry = accepted[index]
        cell = _cell(entry.signature, delta, rate_ratio)
        winner = None
        if not entry.row.curated:
            for neighbour in _neighbours(cell):
                for candidate in grid.get(neighbour, ()):
                    if same_look(entry.signature, kept[candidate].signature, delta, rate_ratio):
                        winner = candidate
                        break
                if winner is not None:
                    break
        if winner is not None:
            keeper = kept[winner]
            merged = tuple(dict.fromkeys(keeper.row.tags + entry.row.tags))
            kept[winner] = replace(keeper, row=replace(keeper.row, tags=merged))
            collapsed.append((entry.row.id, keeper.row.id))
            continue
        grid.setdefault(cell, []).append(len(kept))
        kept.append(entry)

    kept.sort(key=lambda e: (e.row.group, e.row.id))
    return kept, collapsed


# --- emitting -------------------------------------------------------------

def _emit_row(entry: Accepted) -> dict:
    row: dict = {
        "id": entry.row.id,
        "name": entry.row.name,
        "tags": list(entry.row.tags),
        "family": entry.row.family,
        "group": entry.row.group,
        "look": entry.body,
        # Always computed, never a curator's word for it - see `is_quiet`.
        # Carried on every row (not only in the facet counts) so a page can
        # filter an already-fetched shard without a second request.
        "quiet": entry.quiet,
    }
    if entry.row.curated:
        row["curated"] = True
    return row


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _stats(kept: list[Accepted], labels: dict[str, str]) -> dict:
    """The counts and facets, derived once.

    One function because `--dry-run` prints them without writing anything and
    a real run puts them in the manifest: two derivations of "how many blues
    are there" would be two answers waiting to differ.
    """
    groups: dict[str, int] = {}
    families: dict[str, int] = {}
    quiet_counts = {"quiet": 0, "busy": 0}
    for entry in kept:
        groups[entry.row.group] = groups.get(entry.row.group, 0) + 1
        families[entry.row.family] = families.get(entry.row.family, 0) + 1
        quiet_counts["quiet" if entry.quiet else "busy"] += 1
    return {
        "counts": {
            "total": len(kept),
            "curated": sum(1 for e in kept if e.row.curated),
            "generated": sum(1 for e in kept if not e.row.curated),
        },
        "facets": {
            "group": [
                {"id": g, "label": labels.get(g, g), "count": groups[g]}
                for g in sorted(groups)
            ],
            "family": [
                {"id": f, "count": families[f]}
                for f in sorted(families, key=lambda f: (-families[f], f))
            ],
            # A preference filter's counts, not the safety gate's - see
            # `is_quiet`. Two entries always, even at zero, so a chip never
            # has to guess whether "busy" is absent because none exist or
            # because nobody counted.
            "quiet": [
                {"id": "quiet", "count": quiet_counts["quiet"]},
                {"id": "busy", "count": quiet_counts["busy"]},
            ],
        },
    }


def write_library(
    kept: list[Accepted], out_dir: Path, *, settings: dict, labels: dict[str, str],
) -> dict:
    """Write `index.json` plus one shard per group, and return the manifest.

    The layout's argument is in docs/light-library-format.md; the short
    version is that the browse axis and the fetch axis should be the same
    axis, and that no single fetch may be the thing that blocks the page.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()

    by_group: dict[str, list[Accepted]] = {}
    for entry in kept:
        by_group.setdefault(entry.row.group, []).append(entry)

    max_rows = settings["max_shard_rows"]
    shards = []
    for group in sorted(by_group):
        entries = by_group[group]
        parts = [entries[i:i + max_rows] for i in range(0, len(entries), max_rows)] or [[]]
        for number, part in enumerate(parts, start=1):
            name = f"{group}.json" if number == 1 else f"{group}-{number}.json"
            payload = {
                "format_version": FORMAT_VERSION,
                "group": group,
                "label": labels.get(group, group),
                "part": number,
                "rows": [_emit_row(e) for e in part],
            }
            text = _dumps(payload)
            (out_dir / name).write_text(text, encoding="utf-8")
            shards.append({
                "file": name,
                "group": group,
                "label": labels.get(group, group),
                "part": number,
                "rows": len(part),
                "bytes": len(text.encode("utf-8")),
            })

    manifest = {
        "format_version": FORMAT_VERSION,
        "generated": date.today().isoformat(),
        "generator": "tools/import_light_library.py",
        # The page MUST fall back to this when the library is not fetchable -
        # the offline one-file editor build has no library to fetch. Named
        # here so that contract is data rather than folklore.
        "fallback": FALLBACK_SOURCE,
        "settings": settings,
        **_stats(kept, labels),
        "shards": shards,
    }
    (out_dir / "index.json").write_text(_dumps(manifest), encoding="utf-8")
    return manifest


# --- the report -----------------------------------------------------------

@dataclass
class Report:
    """What happened, in the form somebody can act on.

    A rejection nobody sees is a clamp with extra steps: the whole reason this
    tool refuses rather than fixes is that the misses have to be *findable* in
    a table the size of a phone book. So every rejection carries the row's id
    and where it came from, and the exit code is non-zero when anything is
    wrong.
    """

    read: int = 0
    rejections: list[Rejection] = field(default_factory=list)
    naming: list[tuple[str, str, str]] = field(default_factory=list)
    collapsed: list[tuple[str, str]] = field(default_factory=list)
    derived_families: int = 0
    duplicate_names: list[str] = field(default_factory=list)
    manifest: dict | None = None

    def render(self, limit: int = 25) -> str:
        lines = [
            "light library import",
            f"  read       : {self.read} rows",
            f"  rejected   : {len(self.rejections)}",
            f"  collapsed  : {len(self.collapsed)} near-duplicates merged into their keepers",
        ]
        if self.manifest:
            counts = self.manifest["counts"]
            shards = self.manifest["shards"]
            lines += [
                f"  accepted   : {counts['total']} "
                f"({counts['curated']} curated, {counts['generated']} generated)",
                f"  groups     : {len(self.manifest['facets']['group'])}",
                "  families   : " + ", ".join(
                    f"{f['id']} {f['count']}" for f in self.manifest["facets"]["family"][:10]
                ),
                "  quiet      : " + ", ".join(
                    f"{q['id']} {q['count']}" for q in self.manifest["facets"]["quiet"]
                ),
            ]
            lines.append(
                f"  written    : index.json + {len(shards)} shard(s), "
                f"{sum(s['bytes'] for s in shards) / 1024:.1f} KB"
                if shards else "  written    : nothing (--dry-run)"
            )
        if self.derived_families:
            lines.append(
                f"  note       : {self.derived_families} row(s) had no family and got a "
                "derived one - a curation pass should state it"
            )
        if self.duplicate_names:
            lines.append(
                f"  note       : {len(self.duplicate_names)} repeated display name(s), e.g. "
                + ", ".join(self.duplicate_names[:3])
            )

        if self.rejections:
            lines.append("")
            lines.append(f"REJECTED ({len(self.rejections)})")
            width = max(len(r.id) for r in self.rejections)
            for rejection in self.rejections[:limit]:
                lines.append(
                    f"  {rejection.id:<{width}}  {rejection.kind:<8} {rejection.reason}"
                    f"   [{rejection.where}]"
                )
            if len(self.rejections) > limit:
                lines.append(f"  ... and {len(self.rejections) - limit} more (see --report)")

        if self.naming:
            lines.append("")
            lines.append(
                f"NAMING ({len(self.naming)}) - a club or franchise name belongs in the "
                "tags, not the name"
            )
            for row_id, name, reason in self.naming[:limit]:
                lines.append(f"  {row_id}  {name!r}: {reason}")
            if len(self.naming) > limit:
                lines.append(f"  ... and {len(self.naming) - limit} more (see --report)")

        if self.collapsed:
            lines.append("")
            lines.append("COLLAPSED (first few)")
            for dropped, keeper in self.collapsed[:10]:
                lines.append(f"  {dropped} -> {keeper}")
        return "\n".join(lines)

    def as_json(self) -> dict:
        return {
            "read": self.read,
            "rejections": [
                {"id": r.id, "where": r.where, "kind": r.kind, "reason": r.reason}
                for r in self.rejections
            ],
            "naming": [
                {"id": i, "name": n, "reason": r} for i, n, r in self.naming
            ],
            "collapsed": [{"dropped": d, "kept": k} for d, k in self.collapsed],
            "derived_families": self.derived_families,
            "duplicate_names": self.duplicate_names,
            "manifest": self.manifest,
        }


# --- the run --------------------------------------------------------------

def build(
    records: list[tuple[dict, str]],
    *,
    min_flash_period_s: float = SAFE_MIN_PERIOD_S,
    delta: float = DELTA_E_DEFAULT,
    rate_ratio: float = RATE_RATIO_DEFAULT,
    max_shard_rows: int = MAX_SHARD_ROWS_DEFAULT,
) -> tuple[list[Accepted], Report, dict[str, str]]:
    """Everything except writing files - so a test can run the whole pipeline
    in memory and a `--dry-run` can report without touching the tree."""
    report = Report(read=len(records))
    accepted: list[Accepted] = []
    seen_ids: set[str] = set()
    seen_names: dict[str, str] = {}
    labels: dict[str, str] = {}

    for raw, where in records:
        try:
            row = row_from_mapping(raw, where)
        except (ValueError, TypeError, json.JSONDecodeError, AttributeError) as exc:
            row_id = str(normalise_keys(raw).get("id", "?")) if isinstance(raw, dict) else "?"
            report.rejections.append(
                Rejection(row_id, where, "row", f"unreadable ({exc})")
            )
            continue

        if row.id and row.id in seen_ids:
            report.rejections.append(
                Rejection(row.id, where, "duplicate", "id already used by an earlier row")
            )
            continue

        outcome = check(row, min_flash_period_s)
        if isinstance(outcome, Rejection):
            report.rejections.append(outcome)
            continue

        problem = name_problem(row)
        if problem:
            report.naming.append((row.id, row.name, problem))

        seen_ids.add(row.id)
        key = row.name.strip().lower()
        if key in seen_names:
            report.duplicate_names.append(row.name)
        else:
            seen_names[key] = row.id
        labels.setdefault(row.group, row.group_label or row.group)
        if outcome.derived_family:
            report.derived_families += 1
        accepted.append(outcome)

    kept, collapsed = dedupe(accepted, delta, rate_ratio)
    report.collapsed = collapsed
    # A provisional manifest, so `--dry-run` reports the same numbers a real
    # run would rather than a set of zeroes that reads like a failure. The
    # shard list is the one thing only `write_library` can fill in.
    report.manifest = {
        **_stats(kept, labels),
        "shards": [],
        "settings": {
            "delta_e": delta,
            "rate_ratio": rate_ratio,
            "min_flash_period_s": min_flash_period_s,
            "max_shard_rows": max_shard_rows,
        },
    }
    return kept, report, labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source", action="append", default=[],
        help="a .csv or .json table of rows; repeatable",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="include today's LOOK_PRESETS from schema.js as curated rows "
             "(the default when no --source is given)",
    )
    parser.add_argument("--out", default=str(OUT_DIR), help="output directory")
    parser.add_argument("--delta-e", type=float, default=DELTA_E_DEFAULT)
    parser.add_argument("--rate-ratio", type=float, default=RATE_RATIO_DEFAULT)
    parser.add_argument("--min-flash-period", type=float, default=SAFE_MIN_PERIOD_S)
    parser.add_argument("--max-shard-rows", type=int, default=MAX_SHARD_ROWS_DEFAULT)
    parser.add_argument(
        "--allow-names", action="store_true",
        help="report trademark-shaped names but do not fail on them",
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--report", help="also write the full report as JSON here")
    args = parser.parse_args(argv)

    records: list[tuple[dict, str]] = []
    try:
        if args.seed or not args.source:
            records += seed_rows()
        for source in args.source:
            records += read_source(Path(source))
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    kept, report, labels = build(
        records,
        min_flash_period_s=args.min_flash_period,
        delta=args.delta_e,
        rate_ratio=args.rate_ratio,
        max_shard_rows=args.max_shard_rows,
    )

    if not args.dry_run:
        report.manifest = write_library(
            kept, Path(args.out),
            settings=report.manifest["settings"], labels=labels,
        )

    print(report.render())
    if args.report:
        Path(args.report).write_text(
            json.dumps(report.as_json(), indent=2), encoding="utf-8"
        )

    if report.rejections:
        return 1
    if report.naming and not args.allow_names:
        return 1
    return 0


def sample(kept: list, seed: int, count: int) -> list:
    """A fixed, reproducible slice of a big library.

    Here rather than in the test because the *number* and the *seed* are
    properties of the library, not of one test file: TODO 113's rule is that
    the generator carries the gate and the test keeps its teeth over a seeded
    sample, and both halves should be reading the same definition of "the
    sample".
    """
    if len(kept) <= count:
        return list(kept)
    return random.Random(seed).sample(list(kept), count)


if __name__ == "__main__":
    raise SystemExit(main())
