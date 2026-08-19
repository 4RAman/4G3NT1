"""The built-in look library, checked against the parser that will receive it.

These presets are the one place the app *ships* colour rather than accepting
it, so they are the one place a bad value would be our fault rather than a
user's. Two properties matter and neither is about taste:

  - every preset survives `_parse_effect` unchanged, so picking one can never
    produce a warning or a silently different look;
  - no preset is touched by `flash_safe` at the default floor, so the library
    cannot ship a seizure risk (CLAUDE.md's flash-floor invariant).

The array in schema.js is strict JSON precisely so this file can read it
rather than re-declaring it - a second copy would be a mirrored table with
nothing testing the mirror.
"""

import json
import re
from pathlib import Path

import pytest

from aibutton.config import LedEffect, flash_safe, parse_effect_with_warnings
from aibutton.device import SAFE_MIN_PERIOD_S, STYLE_STROBES, STYLE_USES_COLOR2

_SCHEMA_JS = Path(__file__).resolve().parents[1] / "aibutton/web/static/schema.js"


def _presets() -> list[dict]:
    source = _SCHEMA_JS.read_text(encoding="utf-8")
    match = re.search(
        r"export const LOOK_PRESETS = (\[.*?\n\]);", source, re.S
    )
    assert match, "LOOK_PRESETS must stay a single JSON array literal"
    return json.loads(match.group(1))


PRESETS = _presets()
IDS = [p["id"] for p in PRESETS]


def test_the_library_is_actually_long():
    """The ask was for a long list, and a handful of presets is a worse
    default than none - it reads as an oversight rather than a library."""
    assert len(PRESETS) >= 30


def test_ids_and_labels_are_unique():
    assert len(set(IDS)) == len(IDS)
    labels = [p["label"] for p in PRESETS]
    assert len(set(labels)) == len(labels)


def test_every_preset_is_grouped():
    """Grouping is the useful axis: nobody wants "all the blues", they want
    the one that means resting."""
    for preset in PRESETS:
        assert preset.get("group"), preset["id"]


@pytest.mark.parametrize("preset", PRESETS, ids=IDS)
def test_a_preset_parses_to_exactly_itself(preset):
    """No warnings, and nothing quietly altered on the way in."""
    effect, warnings = parse_effect_with_warnings(preset["effect"])
    assert warnings == [], (preset["id"], warnings)
    assert effect == LedEffect(**preset["effect"])


@pytest.mark.parametrize("preset", PRESETS, ids=IDS)
def test_no_preset_is_clamped_by_the_flash_floor(preset):
    """The library must not ship anything the safety gate has to rewrite. A
    preset that got clamped would render differently from the swatch that sold
    it, which is the failure mode the floor exists to make visible."""
    effect = LedEffect(**preset["effect"])
    assert flash_safe(effect, SAFE_MIN_PERIOD_S) == effect, preset["id"]


@pytest.mark.parametrize("preset", PRESETS, ids=IDS)
def test_strobing_presets_stay_the_safe_side_of_the_floor(preset):
    """Belt and braces over the test above: state the rule directly, so a
    change to `flash_safe` cannot quietly make this library unsafe."""
    effect = preset["effect"]
    if effect["style"] in STYLE_STROBES:
        assert effect["period_s"] >= SAFE_MIN_PERIOD_S, preset["id"]


@pytest.mark.parametrize("preset", PRESETS, ids=IDS)
def test_a_second_colour_is_only_set_where_it_is_rendered(preset):
    """A colour2 on a style that ignores it is invisible config: it shows up
    in the saved look and in nothing else, and the next person to read it
    wonders what it was for."""
    effect = preset["effect"]
    if effect["style"] not in STYLE_USES_COLOR2:
        assert effect["color2"] == "#000000", preset["id"]
