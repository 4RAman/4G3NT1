"""The scene library's header, its honest degradation, and its gallery index.

TODO **114**. Three things are asserted here and they are three different
promises:

  - **A scene can describe itself, and that description never reaches the
    parser.** The header sits in the same dict that is merged over config.json
    and handed to `parse_config`, so the one thing that can go wrong is a
    reserved key leaking through and warning on every load. `scenes.merge` is
    the single place it is removed, and the leak test below is what keeps it
    single.
  - **What a scene assumes is answered honestly.** Some of the vocabulary is
    genuinely checkable and most of it is not; the design is allowed to say
    "unchecked" and is not allowed to invent a verdict. A phrase nobody has
    ever written must degrade to shown-not-checked rather than raise.
  - **The gallery's index is 113's contract.** The owner settled on 2026-09-09
    that the scene gallery reuses the light library's manifest whole, so this
    file checks the emitted manifest against
    docs/light-library-format.md section 7 rather than against itself.

**Not covered here, and said plainly rather than left as a gap:** the gallery's
DOM. `sceneGallery.js` builds cards, chips and a search box, and none of that
is asserted anywhere - CLAUDE.md's split is that only pure JavaScript is tested
under `node --test` and anything touching the DOM is verified in a browser.
What *is* mechanically checked is that the module parses as an ES module
(tests/test_js_modules.py sweeps `web/static`) and that the offline bundle
still builds with it (tests/test_build_editor.py), which together catch the
two failures that take the whole editor down.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from aibutton import scenes
from aibutton.config import load_config_full, parse_with_warnings

# tools/ is scripts, not a package - the same path insert test_light_library.py
# and test_build_editor.py make, for the same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_scene_index as builder  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "scenes" / "library"


def library_files() -> list[Path]:
    return sorted(LIBRARY.glob("*.json"))


# --- the header ------------------------------------------------------------

def test_every_shipped_scene_describes_itself():
    """Read off the real files, not a fixture: a scene added to the library
    without a header is a gallery row nobody can pick, and this is the only
    thing that would notice."""
    files = library_files()
    assert files, "scenes/library/ is empty - the library is the point of TODO 114"
    for path in files:
        meta = scenes.parse_meta(json.loads(path.read_text(encoding="utf-8")))
        assert meta.title, f"{path.name} has no title"
        assert meta.blurb, f"{path.name} has no blurb"
        assert meta.audience, f"{path.name} does not say who it is for"
        assert all(isinstance(a, str) and a for a in meta.assumes), path.name
        assert meta.described


def test_a_real_library_scene_parses_its_header():
    """One file, by name, with its values asserted - the generic sweep above
    would pass on a library of seven empty headers if `parse_meta` returned
    the input unchanged."""
    path = LIBRARY / "home-studio.json"
    if not path.exists():  # pragma: no cover - the file is checked in
        pytest.skip("home-studio.json is not in this checkout")
    meta = scenes.parse_meta(json.loads(path.read_text(encoding="utf-8")))
    assert meta.title == "Home Studio"
    assert meta.blurb.endswith(".")
    assert "DAW" in meta.audience
    # `for` is a Python keyword, which is the whole reason the field is called
    # something else; the wire name is still `for`.
    assert meta.assumes == ("a DAW", "a loopMIDI port named 'Button'")


def test_a_header_falls_back_per_key():
    """A broken header costs you that key, not the scene - config.py's
    per-key fallback rule one level up."""
    meta = scenes.parse_meta({
        "title": "Fine", "blurb": 12, "for": None, "assumes": ["ok", "", 7],
    })
    assert meta.title == "Fine"
    assert meta.blurb == ""
    assert meta.audience == ""
    assert meta.assumes == ("ok",)


def test_a_scene_that_is_not_an_object_has_an_empty_header():
    assert scenes.parse_meta(None) == scenes.SceneMeta()
    assert scenes.parse_meta([1, 2]).described is False


# --- the leak, which is the seam most likely to be got wrong ---------------

def test_merge_strips_every_reserved_key():
    """`scenes.merge` is the one place the header is removed, and it is
    removed *before* the parser rather than tolerated by it."""
    scene = {
        "name": "N", "title": "T", "blurb": "B", "for": "F", "assumes": ["x"],
        "modes": [], "web_port": 9,
    }
    merged = scenes.merge({"web_port": 8080}, scene)
    assert not (set(merged) & set(scenes.META_KEYS))
    assert merged["modes"] == []
    assert merged["web_port"] == 9


def test_a_library_scene_loads_without_an_unknown_key_warning(tmp_path):
    """The failure this is really about: a header key reaching `parse_config`
    warns on every single load, and the editor shows four complaints about a
    scene that is perfectly fine."""
    files = library_files()
    assert files
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"scenes": {"dir": "scenes", "active": "probe"}}), encoding="utf-8")
    (tmp_path / "scenes").mkdir()

    for path in files:
        (tmp_path / "scenes" / "probe.json").write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8",
        )
        raw = json.loads(config.read_text(encoding="utf-8"))
        scene_raw = json.loads(path.read_text(encoding="utf-8"))
        _, warnings = parse_with_warnings(scenes.merge(raw, scene_raw))
        leaks = [w for w in warnings if "unknown key" in w]
        assert not leaks, f"{path.name} leaked a header key into the parser: {leaks}"

        loaded = load_config_full(str(config))
        assert loaded.scene_id == "probe"
        assert loaded.scene_error == ""


def test_config_body_is_the_merge_filter_without_a_base():
    raw = {"title": "T", "assumes": [], "scenes": {"active": "loop"}, "modes": [1]}
    body = scenes.config_body(raw)
    assert body == {"modes": [1]}


# --- a broken scene is reported, never fatal -------------------------------

def test_a_garbled_scene_is_reported_and_the_base_config_runs(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"web_port": 8123, "scenes": {"dir": "scenes", "active": "broken"}}),
        encoding="utf-8",
    )
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "broken.json").write_text("{ not json,", encoding="utf-8")

    loaded = load_config_full(str(config))
    assert loaded.scene_id is None
    assert "not a readable JSON object" in loaded.scene_error
    assert loaded.config.web_port == 8123  # the base config ran


def test_a_missing_scene_is_reported_and_the_base_config_runs(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"web_port": 8124, "scenes": {"dir": "scenes", "active": "gone"}}),
        encoding="utf-8",
    )
    loaded = load_config_full(str(config))
    assert loaded.scene_id is None
    assert "not found" in loaded.scene_error
    assert loaded.config.web_port == 8124


def test_an_unreadable_scene_is_still_listed_with_its_header_absent(tmp_path):
    directory = tmp_path / "scenes"
    directory.mkdir()
    (directory / "broken.json").write_text("{", encoding="utf-8")
    (directory / "fine.json").write_text(
        json.dumps({"title": "Fine One", "modes": []}), encoding="utf-8",
    )
    listed = {info.id: info for info in scenes.list_scenes(directory)}
    assert listed["broken"].error
    assert listed["broken"].meta == scenes.SceneMeta()
    # A library scene has a `title` and no `name`; the picker shows the title
    # rather than the filename.
    assert listed["fine"].name == "Fine One"
    assert listed["fine"].meta.title == "Fine One"


# --- honest degradation ----------------------------------------------------

def probe_saying(state: str, detail: str = ""):
    return lambda argument: (state, detail or f"about {argument!r}")


def test_a_real_check_that_fails_is_shown_as_a_warning():
    """The case TODO 114 names: a musician scene wanting a loopMIDI port this
    machine does not have lands with something the picker *shows*."""
    [status] = scenes.check_assumes(
        ["a loopMIDI port named 'Button'"],
        {"midi_port": probe_saying(scenes.UNMET, "no MIDI output port matching 'Button'")},
    )
    assert status.state == scenes.UNMET
    assert "loopMIDI" in status.text          # the scene's own words come back
    assert "no MIDI output port" in status.detail  # and a reason to show


def test_a_real_check_that_passes_says_so():
    [status] = scenes.check_assumes(
        ["a loopMIDI port named 'Button'"], {"midi_port": probe_saying(scenes.OK, "it is here")},
    )
    assert status.state == scenes.OK


def test_an_uncheckable_phrase_is_shown_not_checked_and_says_why():
    """"A DAW" is in the vocabulary and has no probe. It must not be hidden
    and must not be ticked - an unverifiable assumption is still something the
    person installing the scene needs told."""
    [status] = scenes.check_assumes(["a DAW"], {})
    assert status.state == scenes.UNCHECKED
    assert status.detail, "an unchecked phrase with no reason reads as 'fine'"


def test_an_unknown_phrase_degrades_rather_than_raising():
    """A sixth string is a table row - and until somebody adds the row, a
    scene using it still lists it, still installs, and nothing raises."""
    [status] = scenes.check_assumes(["a thing nobody has written a probe for"], {})
    assert status.state == scenes.UNCHECKED
    assert status.text == "a thing nobody has written a probe for"
    assert status.detail == ""


def test_a_probe_that_blows_up_cannot_fail_a_scene():
    def angry(_argument):
        raise RuntimeError("the DLL is on fire")

    [status] = scenes.check_assumes(
        ["a loopMIDI port named 'Button'"], {"midi_port": angry},
    )
    assert status.state == scenes.UNCHECKED
    assert "on fire" in status.detail


def test_a_probe_is_only_asked_about_phrases_that_name_it():
    asked = []
    scenes.check_assumes(
        ["a DAW", "a loopMIDI port named 'Button'"],
        {"midi_port": lambda arg: asked.append(arg) or (scenes.OK, "")},
    )
    assert asked == ["Button"]


def test_a_drifted_phrase_is_answered_as_the_one_it_means():
    """docs/scene-library.md predicted the drift before any code read these
    strings: two spellings of one requirement would be two chips and two
    verdicts. The alias table is where that is fixed, and a row still displays
    exactly what its own file says."""
    [status] = scenes.check_assumes(
        ["a voice-chat app with a global mute hotkey"], {},
    )
    assert status.text == "a voice-chat app with a global mute hotkey"
    assert status.canonical == "a voice-chat or conferencing app with a global mute hotkey"
    assert status.detail, "the canonical phrase's note should come back with it"


def test_no_probes_at_all_is_a_complete_unchecked_list():
    """The offline CLI's case: everything shown, nothing claimed."""
    statuses = scenes.check_assumes(list(scenes.ASSUMPTIONS), {})
    assert len(statuses) == len(scenes.ASSUMPTIONS)
    assert {s.state for s in statuses} == {scenes.UNCHECKED}


# --- the emitted index, against 113's contract -----------------------------

@pytest.fixture
def built(tmp_path):
    """The real library through the real builder, into a temp directory."""
    rows, rejected = builder.build(LIBRARY, {})
    manifest = builder.write_index(rows, tmp_path, source=LIBRARY)
    return manifest, tmp_path, rows, rejected


def test_the_shipped_library_builds_clean(built):
    _, _, rows, rejected = built
    assert not rejected, f"scenes/library/ has rejected files: {rejected}"
    assert rows


def test_the_manifest_has_the_documented_keys(built):
    """docs/light-library-format.md section 7 - the manifest, key for key.
    The scene gallery reuses that contract rather than inventing one, so
    anything missing here is a gallery that has quietly forked."""
    manifest, _, rows, _ = built
    for key in (
        "format_version", "generated", "generator", "fallback",
        "settings", "counts", "facets", "shards",
    ):
        assert key in manifest, key
    assert manifest["format_version"] == 1
    assert manifest["counts"]["total"] == len(rows)
    # No inlined fallback for scenes, and null rather than absent so a reader
    # can tell "no fallback" from "an older manifest that never said".
    assert manifest["fallback"] is None


def test_every_facet_value_carries_an_id_and_a_count(built):
    manifest, _, _, _ = built
    assert manifest["facets"], "a gallery with no facets has no chips to draw"
    for key, values in manifest["facets"].items():
        assert values, key
        for value in values:
            assert isinstance(value["id"], str) and value["id"]
            assert isinstance(value["count"], int) and value["count"] > 0


def test_the_manifest_counts_agree_with_the_shards(built):
    """A manifest that disagrees with its shards is a page that renders a
    count nobody can click on."""
    manifest, out, rows, _ = built
    assert sum(s["rows"] for s in manifest["shards"]) == len(rows)
    for shard in manifest["shards"]:
        body = json.loads((out / shard["file"]).read_text(encoding="utf-8"))
        assert body["format_version"] == manifest["format_version"]
        assert body["group"] == shard["group"]
        assert body["part"] == shard["part"]
        assert len(body["rows"]) == shard["rows"]
        assert shard["bytes"] == len((out / shard["file"]).read_text(encoding="utf-8").encode("utf-8"))


def test_a_shard_is_partitioned_by_a_facet_the_manifest_declares(built):
    """What lets the page turn "pick a chip" into one bounded fetch: every
    shard carries the value of a facet the manifest lists, so the browser can
    derive the shard axis instead of being told it."""
    manifest, _, _, _ = built
    keys = [
        key for key in manifest["facets"]
        if all(shard.get(key) is not None for shard in manifest["shards"])
    ]
    assert keys, "no facet partitions the shards - the gallery loses its shortcut"
    for key in keys:
        declared = {v["id"] for v in manifest["facets"][key]}
        assert {shard[key] for shard in manifest["shards"]} <= declared


def test_a_row_carries_its_header_its_facet_values_and_its_config(built):
    manifest, out, _, _ = built
    shard = json.loads((out / manifest["shards"][0]["file"]).read_text(encoding="utf-8"))
    for row in shard["rows"]:
        for key in ("id", "title", "blurb", "for", "assumes", "facets", "config"):
            assert key in row, key
        assert isinstance(row["config"], dict)
        # The header is the *row*; it must never be inside the config half, or
        # installing the scene would put it back on the parser's plate.
        assert not (set(row["config"]) & set(scenes.META_KEYS))
        assert row["modes"] == len(row["config"].get("modes") or [])


def test_a_row_facet_value_matches_the_manifests_ids(built):
    """The chip and the row are slugged by the same line of Python; this is
    what would catch them drifting apart."""
    manifest, out, _, _ = built
    declared = {key: {v["id"] for v in values} for key, values in manifest["facets"].items()}
    counted = {key: dict.fromkeys(ids, 0) for key, ids in declared.items()}
    for shard in manifest["shards"]:
        body = json.loads((out / shard["file"]).read_text(encoding="utf-8"))
        for row in body["rows"]:
            for key, value in row["facets"].items():
                for one in (value if isinstance(value, list) else [value]):
                    assert one in declared[key], f"{row['id']} has {key}={one!r}"
                    counted[key][one] += 1
    for key, values in manifest["facets"].items():
        for value in values:
            assert counted[key][value["id"]] == value["count"], f"{key}/{value['id']}"


def test_a_scene_with_no_assumptions_still_lands_in_a_facet_bucket(built):
    """"Needs nothing but the button" is the most useful thing to filter
    *for*, and an absence has no chip."""
    manifest, out, _, _ = built
    ids = {v["id"] for v in manifest["facets"]["assumes"]}
    assert builder._slug(builder.NO_ASSUMPTIONS) in ids


def test_a_scene_with_no_header_is_rejected_rather_than_shipped(tmp_path):
    (tmp_path / "anon.json").write_text(json.dumps({"modes": []}), encoding="utf-8")
    rows, rejected = builder.build(tmp_path, {})
    assert not rows
    assert [r.kind for r in rejected] == ["header"]


def test_an_unreadable_scene_is_rejected_rather_than_fatal(tmp_path):
    (tmp_path / "bad.json").write_text("{ nope", encoding="utf-8")
    (tmp_path / "good.json").write_text(
        json.dumps({"title": "T", "blurb": "B", "for": "F", "modes": []}), encoding="utf-8",
    )
    rows, rejected = builder.build(tmp_path, {})
    assert [r.id for r in rows] == ["good"]
    assert [(r.id, r.kind) for r in rejected] == [("bad", "file")]


def test_the_builder_exits_non_zero_only_when_something_was_rejected(tmp_path, capsys):
    (tmp_path / "good.json").write_text(
        json.dumps({"title": "T", "blurb": "B", "for": "F", "modes": []}), encoding="utf-8",
    )
    out = tmp_path / "out"
    assert builder.main(["--source", str(tmp_path), "--out", str(out), "--config", str(tmp_path / "none.json")]) == 0
    (tmp_path / "bad.json").write_text("{ nope", encoding="utf-8")
    assert builder.main(["--source", str(tmp_path), "--out", str(out), "--config", str(tmp_path / "none.json")]) == 1
    assert "REJECTED" in capsys.readouterr().out


def test_a_scene_that_would_warn_still_ships_with_its_warnings_attached(tmp_path):
    """A parser warning is the per-key fallback doing its job; the scene still
    runs, so hiding it from the gallery would be a worse answer than printing
    the sentence."""
    (tmp_path / "noisy.json").write_text(json.dumps({
        "title": "Noisy", "blurb": "B", "for": "F",
        "modes": [{"name": "Home", "template": "actions",
                   "activation": {"type": "always"},
                   "short_press": {"action": "log", "event": "x"}}],
        "web_port": "not a number",
    }), encoding="utf-8")
    rows, rejected = builder.build(tmp_path, {})
    assert not rejected
    assert rows[0].warnings
    assert rows[0].emit()["warnings"] == rows[0].warnings


# --- the built index that is checked in ------------------------------------

def test_the_checked_in_index_is_readable_if_it_exists():
    """It is a build artefact, so a checkout that has never run the builder is
    a normal state (the page treats a 404 as "no gallery here"). What is not
    normal is one that exists and cannot be read."""
    index = ROOT / "aibutton" / "web" / "scene-library" / "index.json"
    if not index.exists():
        pytest.skip("no built scene index in this checkout")
    manifest = json.loads(index.read_text(encoding="utf-8"))
    assert manifest["generator"] == "tools/build_scene_index.py"
    for shard in manifest["shards"]:
        assert (index.parent / shard["file"]).exists(), shard["file"]
