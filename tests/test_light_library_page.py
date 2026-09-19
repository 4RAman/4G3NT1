"""The half of the light library the browser can reach (TODO 113).

`tests/test_light_library.py` checks what the *importer* writes.  This file
checks what the *service* hands out and what the page is entitled to assume
about it - the seam between the two, which is the only place a rename or a
moved key would go unnoticed by both sides.

Four claims, and each of them is something `lightLibrary.js` would break on:

  - the mount exists, and serves the manifest and a shard;
  - a shard row has the six fields docs/light-library-format.md promises, and
    a `look` whose shape can be sniffed from its keys;
  - `fallback` names something that is really there, because that field is how
    the offline page knows what it is falling back *to*;
  - a library that is absent does not stop the service, since that is a normal
    state and the page is built to survive it.

**What is not tested here, honestly.** Everything above is Python.  The page
itself is DOM code - the chips, the search, the lazy fetch, the "+" - and this
project verifies DOM code in a browser rather than in the suite
(CLAUDE.md's note on `tests/js/`).  What the suite *does* cover for free is
that the module parses as ES and that the offline bundler can still resolve
it: `test_js_modules.py::test_a_static_module_parses` and
`test_build_editor.py::test_the_real_modules_bundle`.
"""

import json
from pathlib import Path

import httpx
import pytest

from aibutton import webui
from aibutton.audio import ToneLibrary
from aibutton.config import ConfigManager
from aibutton.device import MockDevice
from aibutton.main import Clock, DeviceStatus
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aibutton/web/static"
LIBRARY_JS = STATIC / "lightLibrary.js"

# The three shapes a `look` may take, sniffed by key presence exactly as the
# page does (`stops` first, then `morse`, else a plain effect).
LOOK_KEYS = ("stops", "morse", "style")


@pytest.fixture
def ctx(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"ble_device_name": "TestBtn"}), encoding="utf-8")
    store = EventStore(str(tmp_path / "events.db"))
    tones = ToneLibrary()
    context = WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        device=MockDevice(),
        clock=Clock(),
        tones=tones,
    )
    yield context
    store.close()
    tones.close()


@pytest.fixture
async def client(ctx):
    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _library_present() -> bool:
    return (webui._LIBRARY / "index.json").exists()


needs_library = pytest.mark.skipif(
    not _library_present(),
    reason="no library has been imported into aibutton/web/library - which is "
           "itself a supported state, covered by the absent-file test below",
)


# --- the mount --------------------------------------------------------------


@needs_library
async def test_the_manifest_is_served(client):
    res = await client.get("/library/index.json")
    assert res.status_code == 200
    manifest = res.json()
    assert manifest["format_version"] == 1
    assert isinstance(manifest["counts"]["total"], int)
    assert manifest["shards"], "a manifest with no shards is a library with no rows"


@needs_library
async def test_the_manifest_describes_exactly_what_is_served(client):
    """The page says "N looks in the library" from `counts.total` and counts
    its own coverage from the shards' row counts.  Two numbers, one library:
    they have to be the same number or the page contradicts itself halfway
    down."""
    manifest = (await client.get("/library/index.json")).json()
    assert sum(s["rows"] for s in manifest["shards"]) == manifest["counts"]["total"]


@needs_library
async def test_a_shard_is_served_and_says_what_the_manifest_said(client):
    manifest = (await client.get("/library/index.json")).json()
    entry = manifest["shards"][0]
    res = await client.get(f"/library/{entry['file']}")
    assert res.status_code == 200
    shard = res.json()
    assert shard["format_version"] == 1
    assert shard["group"] == entry["group"]
    assert len(shard["rows"]) == entry["rows"]


@needs_library
async def test_a_row_carries_the_six_fields_the_page_reads(client):
    """docs/light-library-format.md section 1 and 7.  `lightLibrary.js` maps
    exactly these into its own record; a seventh field would be ignored and a
    missing one would be a row nobody can find or draw."""
    manifest = (await client.get("/library/index.json")).json()
    shard = (await client.get(f"/library/{manifest['shards'][0]['file']}")).json()
    for row in shard["rows"]:
        assert isinstance(row["id"], str) and row["id"]
        assert isinstance(row["name"], str) and row["name"]
        assert isinstance(row["tags"], list) and row["tags"], row["id"]
        assert all(isinstance(tag, str) for tag in row["tags"]), row["id"]
        assert isinstance(row["family"], str)
        assert row["group"] == shard["group"]
        assert any(key in row["look"] for key in LOOK_KEYS), row["id"]


@needs_library
async def test_the_facets_are_readable_without_knowing_their_names(client):
    """The chips are drawn from this and nothing else - a facet the page has
    never heard of has to arrive with a label and a count or it cannot be
    offered.  Asserted over *whatever* keys are there, deliberately: naming
    `group` and `family` here would be the same hard-coding the page is
    forbidden."""
    manifest = (await client.get("/library/index.json")).json()
    total = manifest["counts"]["total"]
    assert manifest["facets"], "no facets means no way to browse"
    for key, values in manifest["facets"].items():
        assert isinstance(key, str) and key, "a facet key names a field on a row"
        assert values, f"facet {key!r} offers nothing to click"
        for value in values:
            assert isinstance(value["id"], str) and value["id"], key
            assert isinstance(value["count"], int)
            # A facet may cover only part of the table (a "safe in a
            # strobe-sensitive room" one would), so this is a ceiling and not
            # an equality - but no value can name more rows than exist.
            assert 0 <= value["count"] <= total, (key, value["id"])


@needs_library
async def test_the_fallback_field_names_a_real_thing(client):
    """The manifest carries the name of what the page falls back to when there
    is no manifest, which sounds circular and is not: it is what makes the
    contract *data* rather than folklore, and it is checkable from here."""
    manifest = (await client.get("/library/index.json")).json()
    path, _, symbol = manifest["fallback"].partition(":")
    source = ROOT / path
    assert source.exists(), manifest["fallback"]
    assert f"export const {symbol} = [" in source.read_text(encoding="utf-8")


# --- cache policy -----------------------------------------------------------


@needs_library
async def test_the_library_is_cached_and_the_editor_modules_are_not(client):
    """Two mounts, two policies, on purpose.  A module in /static is code
    being edited, where a cached copy runs last week's editor; a shard is
    versioned data that only changes when the importer runs.  Revalidation
    rather than a long max-age, because a shard keeps its filename across a
    re-import and there is no hash to bust."""
    module = await client.get("/static/lightLibrary.js")
    assert "no-store" in module.headers["cache-control"]

    shard = await client.get("/library/index.json")
    assert "no-store" not in shard.headers.get("cache-control", "")
    assert "etag" in shard.headers or "last-modified" in shard.headers


# --- and none of it is required --------------------------------------------


async def test_a_missing_library_does_not_stop_the_service(ctx, tmp_path, monkeypatch):
    """The whole reason the page has a fallback: a checkout that has never run
    the importer, or one where the directory was deleted, still starts and
    still serves the editor.  A 404 is the answer the page is written for."""
    monkeypatch.setattr(webui, "_LIBRARY", tmp_path / "never-imported")
    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/library/index.json")).status_code == 404
        # The thing that actually matters: the page itself is unaffected.
        assert (await c.get("/")).status_code == 200


# --- the page's half of the contract, read off the source -------------------
# Same technique as test_color_engine.py, and for the same reason: the
# alternative is a browser in the suite.


def test_the_page_reads_its_facets_generically():
    """CLAUDE.md's Open/Closed rule, applied to a data file instead of
    schema.js.  A "quiet" facet added by a later importer run has to appear
    with no edit here, so the facet list is iterated, never named."""
    source = LIBRARY_JS.read_text(encoding="utf-8")
    assert "Object.entries(manifest.facets" in source
    assert "'family'" not in source, (
        "a facet named in the page is a facet that stops being data"
    )


def test_the_page_falls_back_to_the_inlined_presets():
    """The fallback is the module's own import, not a fetch that happens to
    fail into one - which is what makes it work in the offline bundle, where
    there is no server to fail against."""
    source = LIBRARY_JS.read_text(encoding="utf-8")
    assert "LOOK_PRESETS" in source
    assert "location.protocol === 'file:'" in source, (
        "a file: page must not be asked to fetch - the console noise is the "
        "only thing the attempt would produce"
    )


def test_the_group_dropdown_is_gone_from_the_look_editor():
    """113's actual ask: a searchable page in place of a group-scoped list."""
    engine = (STATIC / "colorEngine.js").read_text(encoding="utf-8")
    assert "LOOK_PRESET_GROUPS" not in engine
    assert "createLibraryBrowser" in engine
