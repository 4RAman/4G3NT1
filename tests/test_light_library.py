"""The fetched light library, and the gate that decides what gets into it.

`test_look_presets.py` is the model and the ancestor: it feeds all 142 entries
of `LOOK_PRESETS` through the real Python parser, so no preset can ship a
colour the config rejects or a rate the flash floor would rewrite. TODO 113
keeps that property while the library grows two orders of magnitude, and the
only way both can be true is to split the work:

  - **the importer carries the gate** - every row, every run, no exceptions;
  - **this file keeps the teeth** - the curated overlay entry by entry, plus a
    fixed, seeded sample of whatever else got emitted.

Parsing 30,000 rows per test run is the thing that would quietly get this
file deleted, so it does not. What it asserts instead is that the gate is
real: a row the floor would clamp is *rejected with a reason* rather than
silently slowed down, which is the difference between a library and a lie.

The other half is the layout: a manifest that disagrees with its shards is a
page that renders a count nobody can click on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from aibutton import sequencer
from aibutton.config import (
    LedEffect,
    flash_safe,
    parse_look_with_warnings,
    sequence_safe,
)
from aibutton.device import SAFE_MIN_PERIOD_S

# tools/ is scripts, not a package - the same path insert test_build_editor.py
# makes, for the same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import import_light_library as lib  # noqa: E402

LIBRARY = Path(__file__).resolve().parents[1] / "aibutton" / "web" / "library"
INDEX = LIBRARY / "index.json"
MESSAGES_CSV = Path(__file__).resolve().parents[1] / "data" / "light-library" / "messages.csv"

# Fixed on purpose: a sample that moved every run would fail on a different
# row each time and could never be reproduced from the failure message.
SAMPLE_SEED = 113
SAMPLE_SIZE = 200


def row(**overrides) -> dict:
    """A minimal valid source record, for tests that vary one thing."""
    record = {
        "id": "probe",
        "name": "Probe",
        "tags": ["probe"],
        "group": "test",
        "look": {"style": "solid", "color": "#0044ff"},
    }
    record.update(overrides)
    return record


def build(*records, **kwargs):
    return lib.build([(r, f"probe[{i}]") for i, r in enumerate(records)], **kwargs)


def assert_shippable(look: dict, where: str, floor: float = SAFE_MIN_PERIOD_S) -> None:
    """The two properties `test_look_presets.py` asserts, over one row.

    Both floors, through the same functions `main.set_led` uses - "safe" must
    not come to mean one thing here and another at the point the light is
    actually pushed.
    """
    parsed, warnings = parse_look_with_warnings(look, where, floor)
    assert warnings == [], (where, warnings)
    if isinstance(parsed, sequencer.Sequence):
        assert parsed.stops, where
        assert sequencer.span_total(parsed) > 0, where
        assert sequence_safe(parsed, floor) == parsed, where
    else:
        assert isinstance(parsed, LedEffect), where
        assert flash_safe(parsed, floor) == parsed, where


# --- the curated overlay, whole ------------------------------------------

SEED = lib.build(lib.seed_rows())


def test_the_seed_imports_with_nothing_rejected():
    """The seed is today's shipped library. If the importer rejects one of
    those, either the importer is wrong or something got into schema.js that
    `test_look_presets.py` should already have caught - and either way it is
    not a thing to discover after generating 30,000 more rows."""
    kept, report, _ = SEED
    assert report.rejections == []
    assert len(kept) == report.read


def test_every_curated_row_survives_the_parser_and_both_floors():
    """The overlay entry by entry, which is the half TODO 113 refuses to
    sample: these are the looks a person chose, and one of them being
    unshippable is our mistake rather than a generator's."""
    kept, _, _ = SEED
    for entry in kept:
        assert entry.row.curated, entry.row.id
        assert_shippable(entry.body, entry.row.id)


def test_nothing_curated_is_ever_collapsed_by_dedupe():
    """Dedupe exists to thin a *generated* bank. A hand-written entry that
    vanished because a generator happened to land near it would be the
    library editing its own curation."""
    _, report, _ = SEED
    assert report.collapsed == []


def test_the_seed_is_long_enough_to_be_a_library():
    """Same argument as `test_look_presets.py`'s: a handful of entries reads
    as an oversight rather than a starting point, and this is what the page
    has on day one."""
    kept, _, _ = SEED
    assert len(kept) >= 100


def test_every_emitted_id_is_a_stable_slug():
    """An id is a URL fragment, a filename component and a thing that must
    never be reused. A space or a capital in one is a bug found much later."""
    kept, _, _ = SEED
    ids = [e.row.id for e in kept]
    assert len(set(ids)) == len(ids)
    for row_id in ids:
        assert lib._ID_RE.match(row_id), row_id


# --- what gets emitted is what the parser said ---------------------------

def test_an_accepted_look_is_the_parsers_own_output_re_serialised():
    """The library's central safety property. If the emitted bytes were the
    *source* bytes, a row could parse to something other than it reads as and
    nothing downstream would ever notice; because they are the parser's
    answer, re-parsing them is a fixed point."""
    kept, _, _ = SEED
    for entry in kept:
        parsed, warnings = parse_look_with_warnings(entry.body, entry.row.id)
        assert warnings == [], entry.row.id
        assert lib._look_body(parsed, entry.body) == entry.body, entry.row.id


def test_a_morse_look_keeps_its_written_form():
    """The one documented exception: expanding "SOS" into its stop list is a
    couple of hundred stops per row, and the compact form is what config.json
    stores anyway - so the library ships the thing you would paste."""
    kept, report, _ = build(
        row(id="sos", name="SOS - Red", look={"morse": "SOS", "dpm": 300, "color": "#ff0000"})
    )
    assert report.rejections == []
    assert kept[0].body == {"morse": "SOS", "dpm": 300, "color": "#ff0000"}
    # ...and it is still a stop list to everything downstream.
    assert isinstance(kept[0].parsed, sequencer.Sequence)


def test_a_colour_the_style_ignores_is_not_emitted():
    """A `color2` on a style that never renders it is invisible config: it
    survives into the saved look and into nothing else, and the next person
    to read it wonders what it was for. Dropping it cannot change what the
    light does, which is why this one normalisation is not a clamp."""
    kept, _, _ = build(
        row(look={"style": "breathe", "color": "#00ff00", "color2": "#ff0000", "period_s": 2})
    )
    assert "color2" not in kept[0].body


def test_a_rainbows_second_colour_is_kept_because_it_is_its_saturation():
    """The trap under the rule above: `color2` on a rainbow is not a second
    hue, it is how saturated the cycle is (INVARIANTS.md, "A rainbow's two
    colour fields"). Dropping it there would change what renders."""
    kept, _, _ = build(
        row(look={"style": "rainbow", "color": "#ffffff", "color2": "#808080", "period_s": 1.4})
    )
    assert kept[0].body["color2"] == "#808080"


# --- the floor is a gate, not a clamp ------------------------------------

def test_a_strobing_row_under_the_floor_is_rejected_rather_than_slowed_down():
    """The whole reason this tool refuses instead of fixing. A clamped preset
    renders differently from the swatch that sold it, so the library would be
    shipping a look nobody chose under a name somebody did."""
    kept, report, _ = build(
        row(id="too-fast", look={"style": "flash", "color": "#ff0000", "period_s": 0.2})
    )
    assert kept == []
    assert [(r.id, r.kind) for r in report.rejections] == [("too-fast", "floor")]
    assert "flash floor" in report.rejections[0].reason


def test_a_repeating_stop_list_under_the_dwell_floor_is_rejected():
    """`sequence_safe` is the second floor and it has to be gated too - a
    stop list has no period, so the floor is defined over its transitions."""
    kept, report, _ = build(
        row(id="strobe-seq", look={"stops": [
            {"color": "#ff0000", "hold_s": 0.05},
            {"color": "#000000", "hold_s": 0.05},
        ], "repeat": True})
    )
    assert kept == []
    assert report.rejections[0].kind == "floor"
    assert "stop floor" in report.rejections[0].reason


def test_a_one_shot_of_three_stops_clears_the_floor_untouched():
    """The confirmation-flash exemption, stated here so a future tightening
    of `sequence_safe` cannot quietly take the library's whole Confirm group
    with it. Three transitions played once sustain nothing."""
    kept, report, _ = build(
        row(id="tick", look={"stops": [
            {"color": "#ffffff", "hold_s": 0.05},
            {"color": "#000000", "hold_s": 0.05},
            {"color": "#ffffff", "hold_s": 0.05},
        ], "repeat": False})
    )
    assert report.rejections == []
    assert kept[0].body["stops"][0]["hold_s"] == 0.05  # not raised to the floor


def test_the_floor_follows_the_setting_rather_than_the_constant():
    """`min_flash_period_s` is a setting, so a library built for a config that
    moved it must be gated against *that* number. A gate hardcoded to the
    default would pass rows the running button then clamps."""
    fast = row(id="fast", look={"style": "flash", "color": "#ff0000", "period_s": 0.5})
    _, strict, _ = build(fast, min_flash_period_s=1.0)
    _, lax, _ = build(fast, min_flash_period_s=0.1)
    assert strict.rejections and strict.rejections[0].kind == "floor"
    assert lax.rejections == []


# --- the other gates ------------------------------------------------------

def test_a_misspelt_key_is_rejected_rather_than_ignored():
    """The parser ignores keys it does not know, which is right for a
    hand-edited config and wrong for a table about to be shipped: `perod_s`
    would sail through and render at one second under a name promising four."""
    _, report, _ = build(
        row(id="typo", look={"style": "breathe", "color": "#0000ff", "perod_s": 4})
    )
    assert report.rejections[0].kind == "look"
    assert "perod_s" in report.rejections[0].reason


def test_a_colour_the_parser_would_fall_back_on_is_rejected():
    """Per-field fallback is the right behaviour for a user's config and the
    wrong one for shipped content - a preset that silently became blue is a
    preset nobody wrote."""
    _, report, _ = build(row(id="bad", look={"style": "solid", "color": "blue"}))
    assert report.rejections[0].kind == "parser"


def test_a_sampled_look_that_never_moves_is_rejected():
    """A progress-driven look that says the same thing at every point parses,
    floors and renders perfectly while being useless."""
    _, report, _ = build(
        row(id="flat", look={"stops": [
            {"color": "#ff0000", "hold_s": 1}, {"color": "#ff0000", "hold_s": 1},
        ], "repeat": False, "drive": "progress"})
    )
    assert report.rejections[0].kind == "look"


def test_a_family_outside_the_vocabulary_is_rejected_with_the_vocabulary():
    """`family` is a facet, so it is a closed set or it is not a facet:
    "red", "Red" and "burgundy" make three chips for one colour."""
    _, report, _ = build(row(id="oops", family="burgundy"))
    assert report.rejections[0].kind == "row"
    assert "burgundy" in report.rejections[0].reason
    assert "red" in report.rejections[0].reason


def test_a_row_nobody_could_search_for_is_rejected():
    """Tags are the only thing standing between 30,000 rows and a wall."""
    _, report, _ = build(row(id="untagged", tags=[]))
    assert report.rejections[0].kind == "row"


def test_a_repeated_id_is_rejected_rather_than_overwriting_the_first():
    """An id is stable and never reused; two rows claiming one is a curation
    mistake that would otherwise resolve to whichever was read last."""
    kept, report, _ = build(row(id="dup"), row(id="dup", name="Other"))
    assert len(kept) == 1
    assert report.rejections[0].kind == "duplicate"


def test_one_unreadable_row_does_not_cost_the_others():
    """A 30,000-row table will contain a broken line, and the run that stops
    at it tells you about exactly one problem per run."""
    kept, report, _ = build(row(id="good"), {"id": "broken", "look": "not an object"})
    assert [e.row.id for e in kept] == ["good"]
    assert len(report.rejections) == 1


# --- dedupe ---------------------------------------------------------------

def test_two_looks_a_hair_apart_in_rate_become_one():
    """TODO 113's actual number: "a library of 8,000 looks anybody can find in
    three keystrokes beats 40,000 nobody can tell apart." Twenty milliseconds
    of period is not a look."""
    kept, report, _ = build(
        row(id="a", look={"style": "breathe", "color": "#0044ff", "period_s": 4.0}),
        row(id="b", look={"style": "breathe", "color": "#0044ff", "period_s": 4.02}),
    )
    assert [e.row.id for e in kept] == ["a"]
    assert report.collapsed == [("b", "a")]


def test_the_survivor_inherits_the_tags_of_what_it_absorbed():
    """Collapsing is only an improvement if the search that would have found
    either still finds the one - "Rising Sun" and "Denmark Red" are one red,
    and both words have to keep working."""
    kept, _, _ = build(
        row(id="a", tags=["japan", "flag"]),
        row(id="b", tags=["denmark", "flag"]),
    )
    assert kept[0].row.tags == ("japan", "flag", "denmark")


def test_two_colours_anyone_can_tell_apart_are_kept_apart():
    """The other half of the threshold: dedupe that collapsed red into green
    would be a bug that looked like success in the summary line."""
    kept, _, _ = build(
        row(id="r", look={"style": "solid", "color": "#ff0000"}),
        row(id="g", look={"style": "solid", "color": "#00ff00"}),
    )
    assert len(kept) == 2


def test_a_generated_row_loses_to_the_curated_one_it_lands_on():
    """The overlay is the thing being kept, whatever order the input arrived
    in - so the curated row wins even when the generated one was read first."""
    kept, report, _ = build(
        row(id="generated", tags=["auto"]),
        row(id="handmade", tags=["chosen"], curated=True),
    )
    assert [e.row.id for e in kept] == ["handmade"]
    assert report.collapsed == [("generated", "handmade")]


def test_the_same_style_at_different_speeds_is_two_looks():
    """Rate is part of a look's identity, not noise around its colour: a 1 s
    breathe and a 6 s breathe are not the same thing at all."""
    kept, _, _ = build(
        row(id="fast", look={"style": "breathe", "color": "#0044ff", "period_s": 1}),
        row(id="slow", look={"style": "breathe", "color": "#0044ff", "period_s": 6}),
    )
    assert len(kept) == 2


def test_a_solid_colour_ignores_period_when_deciding_what_it_is():
    """`solid` does not animate, so two solids that differ only in a number
    nothing reads are one look - and shipping both would be the exact kind of
    padding the dedupe rule exists to stop."""
    kept, _, _ = build(
        row(id="a", look={"style": "solid", "color": "#ff8800", "period_s": 1}),
        row(id="b", look={"style": "solid", "color": "#ff8800", "period_s": 9}),
    )
    assert len(kept) == 1


def test_two_stop_lists_that_render_the_same_are_one_look():
    """A stop list's identity is what it *renders*, not how it was written -
    an extra stop that changes nothing must not buy a second library entry."""
    kept, _, _ = build(
        row(id="a", look={"stops": [
            {"color": "#ff0000", "hold_s": 1}, {"color": "#0000ff", "hold_s": 1},
        ]}),
        row(id="b", look={"stops": [
            {"color": "#ff0000", "hold_s": 0.5}, {"color": "#ff0000", "hold_s": 0.5},
            {"color": "#0000ff", "hold_s": 1},
        ]}),
    )
    assert len(kept) == 1


def test_a_looser_threshold_yields_a_smaller_library():
    """The threshold is the knob the advertised number comes out of, so it has
    to actually move the number - documented in docs/light-library-format.md
    for exactly that reason."""
    rows = [
        row(id=f"r{i}", look={"style": "solid", "color": f"#{i * 4:02x}0000"})
        for i in range(1, 40)
    ]
    tight, _, _ = lib.build([(r, "x") for r in rows], delta=1.0)
    loose, _, _ = lib.build([(r, "x") for r in rows], delta=20.0)
    assert len(loose) < len(tight)


# --- the naming policy ----------------------------------------------------

def test_a_club_name_in_a_sensitive_group_is_reported():
    """TODO 113's one question to answer before release. Colour pairs are not
    protectable; club and franchise names are - so the name stays generic and
    the trademark lives in the tags, where search still finds it and no
    shipped string claims it."""
    _, report, _ = build(
        row(id="gb", name="Green Bay Packers", group="teams",
            tags=["nfl", "green bay", "packers"],
            look={"style": "alternate", "color": "#203731", "color2": "#ffb612",
                  "period_s": 2})
    )
    assert [n[0] for n in report.naming] == ["gb"]


def test_a_colour_pair_name_passes():
    _, report, _ = build(
        row(id="gb", name="Green Bay - Green & Gold", group="teams",
            tags=["nfl", "packers"],
            look={"style": "alternate", "color": "#203731", "color2": "#ffb612",
                  "period_s": 2})
    )
    assert report.naming == []


def test_groups_with_nothing_to_infringe_are_not_policed():
    """Flags, holidays, colour theory and Morse carry no trademark problem,
    and a check that fired on them would be a check somebody switched off."""
    _, report, _ = build(row(id="jp", name="Rising Sun", group="flags"))
    assert report.naming == []


def test_a_naming_flag_does_not_delete_the_row():
    """It is a heuristic on the *shape* of a name, not a finding of fact about
    a trademark - so it warns loudly and leaves the row, because a heuristic
    that deletes content is one nobody dares leave switched on."""
    kept, report, _ = build(
        row(id="gb", name="Green Bay Packers", group="teams",
            look={"style": "solid", "color": "#203731"})
    )
    assert report.naming and [e.row.id for e in kept] == ["gb"]


# --- reading both formats -------------------------------------------------

def test_csv_and_json_tables_produce_the_same_rows(tmp_path):
    """Both, because the owner's curation pass could produce either and a
    format flag is one more thing to get wrong."""
    (tmp_path / "t.csv").write_text(
        "id,name,tags,family,group,style,color,color2,period_s\n"
        "flag-jp,Rising Sun,flag|japan|red,red,flags,solid,#bc002d,,1\n",
        encoding="utf-8",
    )
    (tmp_path / "t.json").write_text(json.dumps({"rows": [{
        "id": "flag-jp", "name": "Rising Sun", "tags": ["flag", "japan", "red"],
        "family": "red", "group": "flags", "look": {"style": "solid", "color": "#bc002d"},
    }]}), encoding="utf-8")

    from_csv, _, _ = lib.build(lib.read_source(tmp_path / "t.csv"))
    from_json, _, _ = lib.build(lib.read_source(tmp_path / "t.json"))
    assert [lib._emit_row(e) for e in from_csv] == [lib._emit_row(e) for e in from_json]


def test_a_csv_cell_may_separate_tags_however_it_likes(tmp_path):
    """No tag contains a pipe, a semicolon or a comma, and an LLM asked for a
    list inside a CSV reaches for whichever the quoting made easiest."""
    (tmp_path / "t.csv").write_text(
        'id,name,tags,group,style,color\n'
        'a,A,"flag, japan; asia|red",flags,solid,#bc002d\n',
        encoding="utf-8",
    )
    kept, _, _ = lib.build(lib.read_source(tmp_path / "t.csv"))
    assert kept[0].row.tags == ("flag", "japan", "asia", "red")


def test_a_table_that_is_not_a_table_fails_loudly(tmp_path):
    """A source file nobody can read has nothing to report row by row, so it
    is an exception rather than a rejection."""
    (tmp_path / "t.json").write_text("[[[", encoding="utf-8")
    with pytest.raises(lib.SourceError):
        lib.read_source(tmp_path / "t.json")


# --- families -------------------------------------------------------------

def test_a_rainbow_is_its_own_family():
    """It is every hue, so filing it under one would be a lie in a chip."""
    parsed, _ = parse_look_with_warnings(
        {"style": "rainbow", "color": "#ffffff", "period_s": 1}, "x"
    )
    assert lib.derive_family(parsed) == "rainbow"


def test_a_look_is_filed_under_its_brightest_colour():
    """Which is the one the eye reports when it is asked what colour
    something was - a dark blue lead-in to a white flash is a white look."""
    parsed, _ = parse_look_with_warnings(
        {"stops": [{"color": "#000820", "hold_s": 1}, {"color": "#ff2200", "hold_s": 1}]}, "x"
    )
    assert lib.derive_family(parsed) == "red"


def test_a_stated_family_beats_the_derived_one():
    """Derivation is a fallback for a table that skipped the column, never an
    override of a curator who filed something deliberately."""
    kept, _, _ = build(row(family="pink", look={"style": "solid", "color": "#ff0000"}))
    assert kept[0].row.family == "pink"
    assert not kept[0].derived_family


# --- the quiet facet: a preference, never a gate ---------------------------
#
# The honest counterpart to TODO 108: the flash floor above is a hard safety
# gate and a row that fails it never exists. `is_quiet` runs only on rows
# that already passed it, and it never rejects anything - these tests are
# here specifically to keep the two from drifting into one mechanism with
# two names, which is exactly the trap CLAUDE.md's "one call site each" rule
# warns about.

def test_a_non_strobing_style_is_quiet_by_construction():
    """Breathe and fade never hard-cut, so they are quiet whatever their
    period - the same reason `device.STYLE_STROBES` leaves them unfloored."""
    parsed, _ = parse_look_with_warnings(
        {"style": "breathe", "color": "#0000ff", "period_s": 0.4}, "x"
    )
    assert lib.is_quiet(parsed) is True


def test_a_slow_flash_clears_the_quiet_threshold():
    """A known quiet row: well clear of both the safety floor and the quiet
    threshold - a deliberate blink, not an alarm."""
    parsed, _ = parse_look_with_warnings(
        {"style": "flash", "color": "#ff0000", "period_s": 1.2}, "x"
    )
    assert lib.is_quiet(parsed) is True


def test_a_fast_flash_clears_the_floor_but_is_busy():
    """A known busy row, and the distinction that must not blur: 0.5s clears
    the 0.333s safety floor with room to spare, yet still reads as an alarm
    from across a room, which is exactly what the quiet facet is for."""
    parsed, _ = parse_look_with_warnings(
        {"style": "flash", "color": "#ff0000", "period_s": 0.5}, "x"
    )
    assert lib.is_quiet(parsed) is False


def test_a_fast_repeating_stop_list_is_busy():
    """A stop list has no style to check, so what is judged is its fastest
    transition, not any one stop's dwell."""
    parsed, _ = parse_look_with_warnings(
        {"stops": [
            {"color": "#ff0000", "hold_s": 0.2},
            {"color": "#000000", "hold_s": 0.2},
        ], "repeat": True}, "x",
    )
    assert lib.is_quiet(parsed) is False


def test_a_one_shot_of_three_or_fewer_stops_is_quiet_however_fast():
    """The same exemption `sequence_safe` makes for the safety floor: a
    handful of transitions played once cannot sustain anything, quiet or
    otherwise."""
    parsed, _ = parse_look_with_warnings(
        {"stops": [
            {"color": "#ffffff", "hold_s": 0.05},
            {"color": "#000000", "hold_s": 0.05},
            {"color": "#ffffff", "hold_s": 0.05},
        ], "repeat": False}, "x",
    )
    assert lib.is_quiet(parsed) is True


def test_the_quiet_facet_is_emitted_with_counts_and_on_every_row(tmp_path):
    """Like `group` and `family`: counts in the manifest so a chip can be
    drawn before any shard is fetched, and the same answer on every row so a
    fetched shard can be filtered without a second request."""
    kept, _, labels = build(
        row(id="calm", look={"style": "breathe", "color": "#00ff00", "period_s": 3}),
        row(id="loud", look={"style": "flash", "color": "#ff0000", "period_s": 0.4}),
    )
    manifest = lib.write_library(
        kept, tmp_path, settings={"max_shard_rows": 10}, labels=labels,
    )
    counts = {q["id"]: q["count"] for q in manifest["facets"]["quiet"]}
    assert counts == {"quiet": 1, "busy": 1}
    rows = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))["rows"]
    by_id = {r["id"]: r for r in rows}
    assert by_id["calm"]["quiet"] is True
    assert by_id["loud"]["quiet"] is False


# --- the emitted layout ---------------------------------------------------

def test_a_big_group_splits_into_numbered_shards(tmp_path):
    """No single fetch may be the thing that blocks the page, which is the
    whole argument for sharding rather than one file."""
    rows = [
        row(id=f"r{i:04d}", name=f"R {i}", group="bulk",
            look={"style": "solid", "color": f"#{i % 256:02x}{(i * 7) % 256:02x}80"})
        for i in range(60)
    ]
    kept, _, labels = lib.build([(r, "x") for r in rows], delta=0.1)
    manifest = lib.write_library(
        kept, tmp_path,
        settings={"max_shard_rows": 25}, labels=labels,
    )
    assert len(manifest["shards"]) >= 3
    assert all(s["rows"] <= 25 for s in manifest["shards"])
    assert {s["file"] for s in manifest["shards"]} >= {"bulk.json", "bulk-2.json"}


def test_writing_the_library_clears_what_was_there_before(tmp_path):
    """A shard from a previous run that no longer appears in the manifest is
    a file the page can still fetch and must never see."""
    (tmp_path / "ghost.json").write_text("{}", encoding="utf-8")
    kept, _, labels = lib.build([(row(), "x")])
    lib.write_library(kept, tmp_path, settings={"max_shard_rows": 100}, labels=labels)
    assert not (tmp_path / "ghost.json").exists()


def test_the_manifest_names_the_offline_fallback(tmp_path):
    """`tools/build_editor.py` inlines schema.js into one HTML file with no
    server to fetch a library from, so the page MUST degrade to the curated
    presets when the library is absent. Naming the fallback in the manifest
    makes that contract data rather than folklore."""
    kept, _, labels = lib.build([(row(), "x")])
    manifest = lib.write_library(
        kept, tmp_path, settings={"max_shard_rows": 10}, labels=labels,
    )
    assert manifest["fallback"] == "aibutton/web/static/schema.js:LOOK_PRESETS"
    assert manifest["format_version"] == lib.FORMAT_VERSION


# --- the library actually on disk ----------------------------------------
#
# Skipped rather than failed when it is absent: TODO 113's degrade rule says
# the page works without the library at all, so a checkout that has not built
# one is legal. The seeded-sample rule lives here - the curated rows whole,
# and a fixed sample of everything else.

def _emitted() -> tuple[dict, list[dict]]:
    manifest = json.loads(INDEX.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for shard in manifest["shards"]:
        payload = json.loads((LIBRARY / shard["file"]).read_text(encoding="utf-8"))
        rows.extend(payload["rows"])
    return manifest, rows


needs_library = pytest.mark.skipif(
    not INDEX.exists(),
    reason="no built library - ./.venv/Scripts/python tools/import_light_library.py",
)


@needs_library
def test_the_manifest_agrees_with_its_shards():
    """A count in a facet chip that does not match the rows behind it is a
    page that renders a number nobody can click on."""
    manifest, rows = _emitted()
    assert manifest["counts"]["total"] == len(rows)
    assert sum(s["rows"] for s in manifest["shards"]) == len(rows)
    assert sum(f["count"] for f in manifest["facets"]["group"]) == len(rows)
    assert sum(f["count"] for f in manifest["facets"]["family"]) == len(rows)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids)


@needs_library
def test_every_shard_holds_only_rows_of_its_own_group():
    """The browse axis and the fetch axis are the same axis - a row filed in
    the wrong shard is a row the group chip cannot find."""
    manifest, _ = _emitted()
    for shard in manifest["shards"]:
        payload = json.loads((LIBRARY / shard["file"]).read_text(encoding="utf-8"))
        assert {r["group"] for r in payload["rows"]} <= {shard["group"]}


@needs_library
def test_every_curated_row_on_disk_is_shippable():
    """The overlay, whole. This is the half that is never sampled."""
    _, rows = _emitted()
    curated = [r for r in rows if r.get("curated")]
    assert curated, "the library should carry the curated overlay"
    for entry in curated:
        assert_shippable(entry["look"], entry["id"])


@needs_library
def test_a_seeded_sample_of_the_generated_rows_is_shippable():
    """TODO 113's compromise, and the reason this file survives the library
    growing two orders of magnitude: the importer carries the gate on every
    row, and this keeps teeth over a fixed, reproducible slice."""
    _, rows = _emitted()
    generated = [r for r in rows if not r.get("curated")]
    if not generated:
        pytest.skip("nothing generated yet - the curated test above covers this library")
    for entry in lib.sample(generated, SAMPLE_SEED, SAMPLE_SIZE):
        assert_shippable(entry["look"], entry["id"])


@needs_library
def test_every_row_on_disk_carries_the_whole_contract():
    """Cheap over the full library because it is a key check, not a parse:
    a row missing its tags or its family is one the page cannot file."""
    _, rows = _emitted()
    for entry in rows:
        assert set(entry) <= {
            "id", "name", "tags", "family", "group", "look", "curated", "quiet",
        }
        assert entry["id"] and entry["name"] and entry["group"]
        assert entry["tags"], entry["id"]
        assert entry["family"] in lib.FAMILIES, entry["id"]
        assert entry["quiet"] in (True, False), entry["id"]


# --- the messages group: Morse as pure curation ---------------------------
#
# aibutton/morse.py (TODO 83) already emits stop lists for arbitrary text, so
# a Morse category is curation with no new code beyond the length gate: every
# row still goes through the same parser, the same dwell floor and the same
# dedupe as anything else - no special path.

def test_an_overlong_morse_message_is_rejected_with_a_reason():
    """Length is the enemy: Morse is up to five symbols a digit and four a
    letter, so a long message is a light show nobody watches to the end.
    Checked before the real parser ever expands it into two hundred stops.
    `dpm` is stated explicitly so the rejection is unambiguously about
    length - the default `dpm` (400) is faster than the flash floor allows
    at 300 dots/min and would otherwise be rejected for the wrong reason."""
    message = "S" * (lib.MAX_MORSE_MESSAGE_CHARS + 1)
    _, report, _ = build(
        row(id="too-long", look={"morse": message, "dpm": 300, "color": "#ff0000"})
    )
    assert report.rejections[0].kind == "look"
    assert "character" in report.rejections[0].reason


def test_a_message_at_the_limit_is_not_rejected():
    """The gate is a maximum, not a discouragement - a message that exactly
    fits must not be punished for coming close."""
    message = "S" * lib.MAX_MORSE_MESSAGE_CHARS
    _, report, _ = build(
        row(id="fits", look={"morse": message, "dpm": 300, "color": "#ff0000"})
    )
    assert report.rejections == []


def test_the_curated_messages_table_reads_and_imports_cleanly():
    """The checked-in table ([data/light-library/messages.csv](
    ../data/light-library/messages.csv)) is data, not a hardcoded list in the
    tool - this is what keeps curation something a spreadsheet can hold."""
    kept, report, _ = lib.build(lib.read_source(MESSAGES_CSV))
    assert report.rejections == []
    assert len(kept) == report.read, "no shipped message should collapse or reject"
    assert all(e.row.group == "messages" for e in kept)


def test_a_curated_morse_rows_tags_carry_its_plaintext():
    """`tags` carry the plaintext so typing S-O-S finds the row; `name` reads
    as the message itself, not as dots and dashes."""
    kept, _, _ = lib.build(lib.read_source(MESSAGES_CSV))
    sos = next(e for e in kept if e.row.id == "msg-sos")
    assert sos.row.name == "SOS"
    assert "sos" in sos.row.tags
    on_air = next(e for e in kept if e.row.id == "msg-on-air")
    assert on_air.row.name == "ON AIR"
    assert "on air" in on_air.row.tags


def test_every_shipped_messages_row_clears_the_parser_and_the_dwell_floor():
    """Every row goes through the same gates as any other: the real parser,
    `sequence_safe`'s dwell floor, and (checked at build time above) dedupe.
    No special path for Morse."""
    kept, report, _ = lib.build(lib.read_source(MESSAGES_CSV))
    assert report.rejections == []
    for entry in kept:
        assert isinstance(entry.parsed, sequencer.Sequence), entry.row.id
        assert_shippable(entry.body, entry.row.id)


def test_every_shipped_message_is_at_or_under_the_length_limit():
    kept, _, _ = lib.build(lib.read_source(MESSAGES_CSV))
    for entry in kept:
        assert len(entry.body["morse"]) <= lib.MAX_MORSE_MESSAGE_CHARS, entry.row.id
