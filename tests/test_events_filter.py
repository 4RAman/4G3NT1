"""Filtering and exporting the event log.

Against a real EventStore rather than a mock, per test_webui.py's rule: the
filters are SQL, and a mock would assert that the right arguments were passed
rather than that the right rows came back.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from aibutton.audio import ToneLibrary
from aibutton.config import ConfigManager
from aibutton.device import MockDevice
from aibutton.main import Clock, DeviceStatus
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app


@pytest.fixture
def store(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    yield store
    store.close()


@pytest.fixture
def ctx(tmp_path, store):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"ble_device_name": "TestBtn"}), encoding="utf-8")
    tones = ToneLibrary()
    yield WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        device=MockDevice(),
        clock=Clock(),
        tones=tones,
    )
    tones.close()


@pytest.fixture
async def client(ctx):
    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def logged(store):
    """A small log with something to tell apart on every axis."""
    store.log_event("coffee", mode="Home")
    store.log_event("coffee", mode="Home")
    store.log_event("note", mode="Focus")
    store.toggle_timer("focus", mode="Focus")
    store.log_event("metronome", mode="Practice", value=128.0)
    return store


def names(rows):
    return [row[2] for row in rows]


# --- the filters -----------------------------------------------------------

def test_no_filters_is_the_whole_log_newest_first(logged):
    assert names(logged.recent()) == ["metronome", "focus", "note", "coffee", "coffee"]


def test_kind_is_exact(logged):
    assert names(logged.recent(kind="timer_start")) == ["focus"]


def test_name_is_a_substring_search(logged):
    """You search a log for 'coff' and expect to find 'coffee'."""
    assert names(logged.recent(name="coff")) == ["coffee", "coffee"]


def test_name_search_is_not_case_sensitive(logged):
    assert names(logged.recent(name="COFF")) == ["coffee", "coffee"]


def test_a_percent_in_the_search_is_text_not_a_wildcard(logged):
    """LIKE's own wildcards have to be neutralised, or searching for '%'
    quietly matches everything - which reads as "the filter is broken"."""
    assert logged.recent(name="%") == []
    assert logged.recent(name="_") == []


def test_mode_is_exact(logged):
    assert names(logged.recent(mode="Focus")) == ["focus", "note"]


def test_filters_combine_with_and(logged):
    assert names(logged.recent(kind="log", mode="Focus")) == ["note"]


def test_limit_still_applies_on_top_of_the_filters(logged):
    assert names(logged.recent(limit=1, name="coffee")) == ["coffee"]


def test_a_time_window_selects_by_instant(store):
    """ts is UTC ISO-8601, where lexical order is chronological order - that
    is what makes a text column usable as a timeline."""
    store.log_event("old")
    boundary = datetime.now(timezone.utc).isoformat()
    store.log_event("new")
    assert names(store.recent(since=boundary)) == ["new"]
    assert names(store.recent(until=boundary)) == ["old"]


def test_a_window_with_nothing_in_it_is_empty_not_everything(store):
    store.log_event("coffee")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert store.recent(since=future) == []


def test_kinds_lists_what_is_actually_in_the_log(logged):
    assert logged.kinds() == ["log", "timer_start"]


# --- the API ---------------------------------------------------------------

async def test_the_endpoint_passes_filters_through(client, logged):
    res = await client.get("/api/events", params={"name": "coffee"})
    assert [row["name"] for row in res.json()] == ["coffee", "coffee"]


async def test_the_kinds_endpoint_backs_the_picker(client, logged):
    assert (await client.get("/api/events/kinds")).json() == {
        "kinds": ["log", "timer_start"]
    }


async def test_the_summary_totals_the_whole_log_not_a_window(client, store, logged):
    """The nav's live line (TODO 101), and the reason it is its own endpoint.

    `/api/events` is a feed with a limit; this is a total. A "12 runs" that
    quietly meant "12 of the last 500 rows" would look right for months, so the
    two are separate queries rather than one with a flag.
    """
    for _ in range(3):
        store.log_event("coffee", mode="Home")

    rows = (await client.get("/api/events/summary")).json()["rows"]
    by = {(r["kind"], r["name"]): r for r in rows}

    assert by[("log", "coffee")]["count"] == 5  # 2 from `logged`, 3 more here
    assert by[("log", "coffee")]["last"]
    # One row per (kind, name), not one per event.
    assert len(rows) == len({(r["kind"], r["name"]) for r in rows})


async def test_the_summary_reports_the_extremes_of_both_number_columns(client, store):
    """`duration_s` and `value` are different questions asked of one table -
    how long it took, and what number it carried - and a row usually has
    exactly one of them. Summarising them together would make a reaction
    timer's 214 ms and a stopwatch's 214 seconds the same fact."""
    store.log_event("tempo", value=90.0)
    store.log_event("tempo", value=160.0)
    started = store.log_mode_enter("Focus")
    store.log_mode_exit("Focus", started)

    by = {(r["kind"], r["name"]): r
          for r in (await client.get("/api/events/summary")).json()["rows"]}

    tempo = by[("log", "tempo")]
    assert (tempo["value_min"], tempo["value_max"]) == (90.0, 160.0)
    assert tempo["duration_min"] is None

    exited = by[("mode_exit", "Focus")]
    assert exited["duration_min"] is not None
    assert exited["value_min"] is None


async def test_an_empty_log_summarises_to_nothing(client):
    """What a fresh install answers, and the shape the editor has to survive:
    no rows means every nav line keeps the half it computed from the config."""
    assert (await client.get("/api/events/summary")).json() == {"rows": []}


async def test_an_unfiltered_request_is_unchanged(client, logged):
    """The filters are all optional, and the call the page made before they
    existed has to keep working."""
    res = await client.get("/api/events", params={"limit": 50})
    assert len(res.json()) == 5


# --- the export ------------------------------------------------------------

async def test_csv_export_carries_every_column(client, logged):
    res = await client.get("/api/events/export", params={"format": "csv"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert [row["name"] for row in rows] == [
        "metronome", "focus", "note", "coffee", "coffee"
    ]
    assert rows[0]["value"] == "128.0"
    assert rows[0]["mode"] == "Practice"


async def test_the_export_is_the_table_you_were_looking_at(client, logged):
    """The whole point of sharing one query: a downloaded file that disagrees
    with the filtered table is worse than no export."""
    params = {"kind": "log", "mode": "Focus"}
    shown = (await client.get("/api/events", params=params)).json()
    exported = list(csv.DictReader(io.StringIO(
        (await client.get("/api/events/export", params={**params, "format": "csv"})).text
    )))
    assert [row["name"] for row in exported] == [row["name"] for row in shown]


async def test_json_export_is_a_download_not_a_page(client, logged):
    res = await client.get("/api/events/export", params={"format": "json"})
    assert res.headers["content-type"].startswith("application/json")
    assert "attachment" in res.headers["content-disposition"]
    assert [row["name"] for row in res.json()] == [
        "metronome", "focus", "note", "coffee", "coffee"
    ]


async def test_an_export_defaults_to_the_whole_log_not_one_page(client, store):
    """An export asking for the log and quietly getting the most recent 50
    rows is the kind of wrong answer only noticed later, in a spreadsheet."""
    for i in range(120):
        store.log_event(f"event-{i}")
    res = await client.get("/api/events/export", params={"format": "csv"})
    assert len(list(csv.DictReader(io.StringIO(res.text)))) == 120


async def test_an_unknown_export_format_is_refused(client, logged):
    assert (await client.get("/api/events/export", params={"format": "pdf"})).status_code == 422
