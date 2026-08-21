"""The built-in look library, checked against the parser that will receive it.

These presets are the one place the app *ships* colour rather than accepting
it, so they are the one place a bad value would be our fault rather than a
user's. Two properties matter and neither is about taste:

  - every preset survives the parser unchanged, so picking one can never
    produce a warning or a silently different look;
  - no preset is touched by the safety floor at the default setting, so the
    library cannot ship a seizure risk (CLAUDE.md's flash-floor invariant).

**A preset carries an `effect` or a `sequence`, never both** (TODO 36a), and
the two shapes are checked separately below because almost nothing about them
is the same: an effect has one style and one period and is floored by
`flash_safe`, while a sequence has stops, a drive, and is floored by
`sequence_safe` over *two* axes. The handful of properties they do share -
unique ids, a group, exactly one body - are checked over the whole library.

The array in schema.js is strict JSON precisely so this file can read it
rather than re-declaring it - a second copy would be a mirrored table with
nothing testing the mirror.
"""

import json
import re
from pathlib import Path

import pytest

from aibutton import sequencer
from aibutton.config import (
    DRIVE_TEMPLATES,
    LedEffect,
    flash_safe,
    parse_effect_with_warnings,
    parse_look_with_warnings,
    sequence_safe,
)
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

EFFECTS = [p for p in PRESETS if "effect" in p]
EFFECT_IDS = [p["id"] for p in EFFECTS]
SEQUENCES = [p for p in PRESETS if "sequence" in p]
SEQUENCE_IDS = [p["id"] for p in SEQUENCES]


# --- the whole library ----------------------------------------------------

def test_the_library_is_actually_long():
    """The ask was for a long list, and a handful of presets is a worse
    default than none - it reads as an oversight rather than a library."""
    assert len(PRESETS) >= 30


def test_both_shapes_are_actually_represented():
    """Guards the split below: if either list emptied, every test
    parametrised over it would pass by vacuously running zero cases."""
    assert len(EFFECTS) >= 20
    assert len(SEQUENCES) >= 20


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
def test_a_preset_carries_exactly_one_body(preset):
    """`presetIsSequence` keys off `sequence` alone, so one carrying both
    would be applied as a sequence with an effect's keys left in it - the
    stale-key bug the drawer already had once."""
    assert ("effect" in preset) != ("sequence" in preset), preset["id"]


# --- effect presets -------------------------------------------------------

@pytest.mark.parametrize("preset", EFFECTS, ids=EFFECT_IDS)
def test_an_effect_preset_parses_to_exactly_itself(preset):
    """No warnings, and nothing quietly altered on the way in."""
    effect, warnings = parse_effect_with_warnings(preset["effect"])
    assert warnings == [], (preset["id"], warnings)
    assert effect == LedEffect(**preset["effect"])


@pytest.mark.parametrize("preset", EFFECTS, ids=EFFECT_IDS)
def test_no_effect_preset_is_clamped_by_the_flash_floor(preset):
    """The library must not ship anything the safety gate has to rewrite. A
    preset that got clamped would render differently from the swatch that sold
    it, which is the failure mode the floor exists to make visible."""
    effect = LedEffect(**preset["effect"])
    assert flash_safe(effect, SAFE_MIN_PERIOD_S) == effect, preset["id"]


@pytest.mark.parametrize("preset", EFFECTS, ids=EFFECT_IDS)
def test_strobing_presets_stay_the_safe_side_of_the_floor(preset):
    """Belt and braces over the test above: state the rule directly, so a
    change to `flash_safe` cannot quietly make this library unsafe."""
    effect = preset["effect"]
    if effect["style"] in STYLE_STROBES:
        assert effect["period_s"] >= SAFE_MIN_PERIOD_S, preset["id"]


@pytest.mark.parametrize("preset", EFFECTS, ids=EFFECT_IDS)
def test_a_second_colour_is_only_set_where_it_is_rendered(preset):
    """A colour2 on a style that ignores it is invisible config: it shows up
    in the saved look and in nothing else, and the next person to read it
    wonders what it was for."""
    effect = preset["effect"]
    if effect["style"] not in STYLE_USES_COLOR2:
        assert effect["color2"] == "#000000", preset["id"]


# --- sequence presets -----------------------------------------------------

@pytest.mark.parametrize("preset", SEQUENCES, ids=SEQUENCE_IDS)
def test_a_sequence_preset_parses_to_a_sequence_without_complaint(preset):
    look, warnings = parse_look_with_warnings(preset["sequence"])
    assert warnings == [], (preset["id"], warnings)
    assert isinstance(look, sequencer.Sequence), preset["id"]
    assert look.stops, preset["id"]


@pytest.mark.parametrize("preset", SEQUENCES, ids=SEQUENCE_IDS)
def test_no_sequence_preset_is_clamped_by_either_floor(preset):
    """`sequence_safe` floors two axes - each stop's dwell, and each stop's
    own strobing style - and the library must clear both. The dwell half has
    a trap worth stating: the exemption is for a one-shot of **three stops or
    fewer**, so a five-stop one-shot is floored exactly like a repeat. Two
    presets were caught by this before they shipped."""
    look, _ = parse_look_with_warnings(preset["sequence"])
    assert sequence_safe(look, SAFE_MIN_PERIOD_S) == look, preset["id"]


@pytest.mark.parametrize("preset", SEQUENCES, ids=SEQUENCE_IDS)
def test_a_sequence_preset_has_a_cycle_with_length(preset):
    """Every stop zero-width means nothing to walk and nothing to sample -
    `plan_at` degenerates and `sample_at` cannot divide by it."""
    look, _ = parse_look_with_warnings(preset["sequence"])
    assert sequencer.span_total(look) > 0, preset["id"]


@pytest.mark.parametrize("preset", SEQUENCES, ids=SEQUENCE_IDS)
def test_a_sequence_preset_names_a_drive_something_can_supply(preset):
    """A preset is shipped colour, so it does not get to be the one thing in
    the config that names a drive nothing can drive - that fail-soft is for
    hand-written files."""
    look, _ = parse_look_with_warnings(preset["sequence"])
    assert look.drive == "clock" or look.drive in DRIVE_TEMPLATES, preset["id"]


@pytest.mark.parametrize(
    "preset",
    [p for p in SEQUENCES if p["sequence"].get("drive", "clock") != "clock"],
    ids=[p["id"] for p in SEQUENCES if p["sequence"].get("drive", "clock") != "clock"],
)
def test_a_sampled_preset_actually_moves_across_its_range(preset):
    """The whole point of a progress- or beats-driven preset is that it says
    something different at different points. One flat colour end to end would
    parse, floor and render perfectly while being useless, which no other
    test here would notice."""
    look, _ = parse_look_with_warnings(preset["sequence"])
    seen = {sequencer.sample_at(look, i / 24).color for i in range(25)}
    assert len(seen) > 1, preset["id"]
