"""A reflex that goes and looks: a clock and a URL (TODO 99, shaped by 100).

Four layers, because they fail in four different ways, and the middle two are
the ones TODO 99 says will bite later.

The **reader** has to turn a body nobody controls into a flat payload the
one-field `when` test can read, and say clearly when it cannot. The **health**
state machine has to make a dead server quiet without making it invisible - no
fire, no spam, still findable - and it is pure, so all three are provable here
without a socket. The **parser** has to keep a half-typed reflex alive. And the
**run loop** has to dispatch a reading without pretending a button was pressed.

**No test here touches the network.** The poller takes an httpx transport the
way `actions.execute` takes one for a webhook, so a calendar is a string in
this file and a dead server is a handler that raises.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import aibutton.config as cfg
import aibutton.main as main
import aibutton.poll as poll
from aibutton.config import parse_with_warnings
from aibutton.device import MockDevice
from aibutton.store import EventStore

NOW = datetime(2026, 9, 9, 13, 0, 0)


def _ics(*events: str) -> str:
    """A calendar file, folded and CRLF'd the way a real export is."""
    body = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", *events, "END:VCALENDAR"])
    return body + "\r\n"


def _event(*lines: str) -> str:
    return "\r\n".join(["BEGIN:VEVENT", *lines, "END:VEVENT"])


# --- what a body means -----------------------------------------------------
# One table rather than a test per body: every row is "this arrived, and this
# is what `when` gets to read", which is the only question this half answers.

@pytest.mark.parametrize("scenario,reader,body,expected", [
    (
        "a JSON object is already a payload",
        "json", '{"moisture": 12, "battery": 91}',
        {"moisture": 12, "battery": 91},
    ),
    (
        "a bare list can only answer how many",
        "json", "[1, 2, 3]", {"count": 3},
    ),
    # These stamps carry no zone, so they are local wall time and the
    # expectations hold on any machine. The UTC form has its own test below,
    # because asserting a fixed number against one would only be asserting
    # what zone the machine running the suite is in.
    (
        "the next meeting is ten minutes away",
        "ics", _ics(_event("DTSTART:20260909T131000", "SUMMARY:Standup")),
        {"events": 1, "recurring": 0, "minutes": 10.0},
    ),
    (
        "a meeting that has already started is not the next one",
        "ics", _ics(
            _event("DTSTART:20260909T125500"),
            _event("DTSTART:20260909T140000"),
        ),
        {"events": 1, "recurring": 0, "minutes": 60.0},
    ),
    (
        "a cancelled event is not a meeting",
        "ics", _ics(_event("DTSTART:20260909T131000", "STATUS:CANCELLED")),
        {"events": 0, "recurring": 0},
    ),
    (
        "a repeating event is counted rather than pretended away",
        "ics", _ics(_event("DTSTART:20260909T131000", "RRULE:FREQ=WEEKLY;BYDAY=TU")),
        {"events": 0, "recurring": 1},
    ),
    (
        "an empty calendar is quiet, not broken",
        "ics", _ics(), {"events": 0, "recurring": 0},
    ),
    (
        "an all-day event starts at local midnight",
        "ics", _ics(_event("DTSTART;VALUE=DATE:20260910")),
        {"events": 1, "recurring": 0, "minutes": 660.0},
    ),
])
def test_a_fetched_body_becomes_a_payload(scenario, reader, body, expected):
    reading = poll.read_body(body, reader, NOW)
    assert reading.ok, f"{scenario}: {reading.error}"
    assert reading.payload == expected, scenario


def test_a_folded_line_is_read_as_one_property():
    """RFC 5545 breaks lines at 75 octets and every real export uses it. A
    folded DTSTART read a line at a time is two properties that are both
    nonsense, so this is the difference between reading the file and not.
    Folding is octet-based, so it can land mid-value - which is why the fold
    here is inside the timestamp rather than politely between fields."""
    body = _ics(_event(
        "DTSTART:2026090\r\n 9T131000",
        "SUMMARY:A title long enough to be fol\r\n ded in half",
    ))
    reading = poll.read_body(body, "ics", NOW)
    assert reading.ok, reading.error
    assert reading.payload == {"events": 1, "recurring": 0, "minutes": 10.0}


def test_a_utc_stamp_is_read_as_an_instant_rather_than_as_wall_time():
    """`DTSTART:...Z` is the form Google writes, and reading its digits as
    local time is an alarm that is right in Greenwich and wrong everywhere
    else. Built from `now` rather than hard-coded, so the assertion is about
    the conversion and not about where the suite happens to be running."""
    as_utc = NOW.astimezone().astimezone(timezone.utc) + timedelta(minutes=10)
    body = _ics(_event("DTSTART:" + as_utc.strftime("%Y%m%dT%H%M%SZ")))
    assert poll.read_body(body, "ics", NOW).payload["minutes"] == 10.0


def test_a_zone_this_machine_cannot_name_is_read_as_local_wall_time():
    """A degradation with a reason: Windows ships no IANA time zone database,
    so `TZID=America/Denver` is unresolvable here unless `tzdata` happens to be
    installed. Refusing the event would silence a calendar reflex on the
    platform this project runs on, and local wall time is exactly right
    whenever the calendar is in the button's own zone."""
    assert poll.parse_dtstart(";TZID=Nowhere/Nowhere", "20260909T131000") == (
        datetime(2026, 9, 9, 13, 10)
    )


def test_no_next_meeting_leaves_the_field_out_rather_than_reporting_a_zero():
    """A missing field never fires (INVARIANTS.md), so "nothing in the diary"
    needs no special case anywhere downstream - which is why `minutes` is
    absent rather than 0 or -1, either of which would fire `minutes <= 10`."""
    reading = poll.read_body(_ics(), "ics", NOW)
    assert "minutes" not in reading.payload
    reflex = cfg.Reflex(
        name="meeting", then=cfg.LogAction(event="soon"),
        when=cfg.ReflexTest(field="minutes", op="<=", value=10),
    )
    assert cfg.reflex_matches(reflex, reading.payload) == (False, None)


@pytest.mark.parametrize("scenario,reader,body,expected", [
    ("the wrong reader says which one it wanted",
     "json", _ics(), "looks like iCalendar"),
    ("and the same the other way round",
     "ics", '{"moisture": 1}', "looks like JSON"),
    ("a JSON scalar is not a payload", "json", "42", "rather than an object"),
    ("nonsense is not JSON", "json", "<html>no</html>", "not JSON"),
])
def test_an_unreadable_body_fails_with_a_reason_a_person_can_act_on(
    scenario, reader, body, expected,
):
    """The likeliest cause of a body that will not parse is the wrong `read`,
    and a reflex that goes silent is a bad way to find that out. The failure
    goes through the same health machinery a dead server does, so it costs one
    log line and shows up in the same place."""
    reading = poll.read_body(body, reader, NOW)
    assert not reading.ok, scenario
    assert expected in reading.error, f"{scenario}: {reading.error}"


# --- quiet, and visible ----------------------------------------------------
# TODO 99's three requirements about failure. The first (no fire) is structural
# and is asserted in the run-loop section; these two are decisions, so they are
# made in one pure place and tested there.

def test_a_dead_endpoint_is_logged_once_per_reason_not_once_per_attempt():
    """Sixty refusals an hour are one line. A refusal that *becomes* a 404 is a
    second line, because the reason changing is news - the same rule
    `sync_midi_listeners` already applies to a port that will not open."""
    health = poll.Health(period_s=60.0)
    script = [
        # (what happened, is it worth a log line?)
        ("refused", True),    # the first failure always is
        ("refused", False),
        ("refused", False),
        ("refused", False),
        ("HTTP 404", True),   # a new reason is news
        ("HTTP 404", False),
    ]
    now = 0.0
    said = []
    for error, _expected in script:
        said.append(health.failed(now, error))
        now = health.next_at
    assert said == [expected for _error, expected in script]
    assert health.failures == len(script)


def test_recovery_is_said_once_too():
    health = poll.Health(period_s=60.0)
    health.failed(0.0, "refused")
    assert health.succeeded(60.0) is True     # back from the dead: worth saying
    assert health.succeeded(120.0) is False   # still fine: not news


def test_backing_off_turns_an_hour_of_attempts_into_a_handful():
    """The other half of "no spam": not just fewer log lines but fewer
    requests, because somebody else's server is on the end of this."""
    health = poll.Health(period_s=60.0)
    now, attempts = 0.0, 0
    while now < 3600.0:
        health.failed(now, "refused")
        attempts += 1
        now = health.next_at
    assert attempts <= 8, "an hour of a dead endpoint should not be 60 requests"
    # And it recovers within one period of the server coming back, rather than
    # staying backed off for half an hour after it does.
    assert health.succeeded(now) is True
    assert health.next_at == now + 60.0


def test_a_long_interval_never_gets_shorter_because_it_failed():
    """A cap that is *below* the configured period would turn an hourly poll
    into a half-hourly one the moment it started failing - backoff has to be
    monotone in the period, not just in the failure count."""
    assert all(poll.backoff_s(3600.0, n) >= 3600.0 for n in range(1, 10))


def test_the_health_of_every_url_is_askable_rather_than_only_loggable():
    """"Why did nothing happen?" must have an answer that is not "read the log
    from three hours ago"."""
    health = poll.Health(period_s=60.0)
    health.failed(0.0, "ConnectError: no route to host")
    snapshot = health.snapshot(300.0)
    assert snapshot["ok"] is False
    assert snapshot["failures"] == 1
    assert "no route to host" in snapshot["error"]
    assert snapshot["failing_for_s"] == 300.0
    assert "no route to host" in health.describe(300.0)
    # And "never tried" is a third state, not a healthy one.
    assert poll.Health(period_s=60.0).snapshot(0.0)["ok"] is None


# --- the parser ------------------------------------------------------------

def test_a_reflex_can_name_a_url_and_an_interval():
    config = cfg.parse_config({"reflexes": [{
        "name": "next_meeting",
        "then": {"action": "log", "event": "soon"},
        "from": {"url": {
            "url": "https://calendar.example/secret/basic.ics",
            "every_minutes": 5, "read": "ics",
        }},
        "when": {"field": "minutes", "op": "<=", "value": 10},
    }]})
    source = config.reflexes[0].source
    assert isinstance(source, cfg.UrlSource)
    assert source.url == "https://calendar.example/secret/basic.ics"
    assert (source.every_minutes, source.read) == (5.0, "ics")
    # And it round-trips, so saving from the editor does not lose it.
    assert cfg._reflex_to_dict(config.reflexes[0])["from"] == {"url": {
        "url": "https://calendar.example/secret/basic.ics",
        "every_minutes": 5.0, "read": "ics",
    }}


@pytest.mark.parametrize("scenario,spec,expect_source,complaint", [
    ("no interval is fifteen minutes",
     {"url": "https://x/f.ics"}, True, None),
    ("an interval below the floor is clamped and said so",
     {"url": "https://x/f.ics", "every_minutes": 0}, True, "below the"),
    ("a nonsense interval falls back to the default",
     {"url": "https://x/f.ics", "every_minutes": "soon"}, True, "must be a number"),
    ("an unknown reader falls back to JSON",
     {"url": "https://x/f.ics", "read": "calendar"}, True, "not one of"),
    ("no address is the one thing worth dropping the source over",
     {"every_minutes": 5}, False, "http(s) address"),
    ("nor is a bare string an address to fetch",
     {"url": "not a url"}, False, "http(s) address"),
    ("the source is an object, not a string",
     "https://x/f.ics", False, "must be an object"),
])
def test_a_malformed_url_source_falls_back_rather_than_raising(
    scenario, spec, expect_source, complaint,
):
    """A bad config never crashes the service, and the warnings reach the web
    API so the editor shows what was actually accepted. **The reflex always
    survives** - what is lost is at most one way in, and its own address still
    fires it."""
    config, warnings = parse_with_warnings({"reflexes": [{
        "name": "r", "then": {"action": "log", "event": "e"},
        "from": {"url": spec},
    }]})
    assert [r.name for r in config.reflexes] == ["r"], scenario
    assert isinstance(config.reflexes[0].source, cfg.UrlSource) is expect_source, scenario
    if complaint is None:
        assert not warnings, scenario
        assert config.reflexes[0].source.every_minutes == poll.DEFAULT_PERIOD_MINUTES
    else:
        assert any(complaint in w for w in warnings), (scenario, warnings)


def test_a_clamped_interval_is_honoured_and_complained_about_not_clamped_quietly():
    """Silently clamping a setting makes it a lie - `min_flash_period_s`'s rule,
    one subsystem over."""
    config, warnings = parse_with_warnings({"reflexes": [{
        "name": "r", "then": {"action": "log", "event": "e"},
        "from": {"url": {"url": "https://x/f.ics", "every_minutes": 0.01}},
    }]})
    assert config.reflexes[0].source.every_minutes == poll.MIN_PERIOD_MINUTES
    assert any("every_minutes" in w for w in warnings), warnings


def test_a_reflex_hears_from_one_source_not_two():
    """Two sources would leave `when` judging a different payload depending on
    which way in fired. The answer to wanting both is two reflexes."""
    config, warnings = parse_with_warnings({"reflexes": [{
        "name": "r", "then": {"action": "log", "event": "e"},
        "from": {"url": {"url": "https://x/f.ics"}, "midi": {"note": 95}},
    }]})
    assert config.reflexes[0].source is None
    assert any("one source" in w for w in warnings), warnings


def test_a_polled_reflex_is_not_asked_about_midi_notes():
    """`source` is a union now, and a polled one has no note number. The
    question is asked once, in `reflex_hears`, rather than at each caller."""
    config = cfg.parse_config({"reflexes": [{
        "name": "r", "then": {"action": "log", "event": "e"},
        "from": {"url": {"url": "https://x/f.ics"}},
    }]})
    assert cfg.reflex_hears(config.reflexes[0], "note", 95, 1) is False


def test_a_url_source_carries_no_credential():
    """TODO 100's decision, made structural: the keyless endpoints ship first
    because a token in `config.json` is a credential leak by construction -
    that file is served in full by an unauthenticated API and is now in git.
    A field for one here would be that leak, so there is not one (TODO 96a)."""
    assert set(f.name for f in cfg.UrlSource.__dataclass_fields__.values()) == {
        "url", "every_minutes", "read",
    }


# --- the run loop ----------------------------------------------------------

RUN_CONFIG = {
    "web_enabled": False,
    "modes": [{"name": "Home", "template": "actions", "activation": {"type": "always"},
               "short_press": {"action": "log", "event": "ping"}}],
    "reflexes": [{
        "name": "next_meeting",
        "then": {"action": "log", "event": "meeting_soon"},
        "from": {"url": {"url": "https://calendar.example/basic.ics",
                         "every_minutes": 1, "read": "ics"}},
        "when": {"field": "minutes", "op": "<=", "value": 10},
    }],
}


async def _drive(tmp_path, monkeypatch, handler, *, config=None, seconds=0.6,
                 tick=0.02, floor=0.0):
    """Run the service with a faked transport and hand back (rows, device).

    `floor` lowers `MIN_PERIOD_MINUTES` so a test can watch several attempts go
    by in under a second; the production floor exists to be kind to somebody
    else's calendar server, and a MockTransport is not one.
    """
    cfg_path = tmp_path / "config.json"
    db_path = tmp_path / "events.db"
    cfg_path.write_text(
        json.dumps(dict(config or RUN_CONFIG, database_path=str(db_path))),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "_POLL_TICK_S", tick)
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(poll, "MIN_PERIOD_MINUTES", floor)
    device = MockDevice()
    args = main._parse_args(["--no-web", "--no-lock", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(
        args, device=device, poll_transport=httpx.MockTransport(handler),
    ))
    try:
        await asyncio.sleep(seconds)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    store = EventStore(str(db_path))
    try:
        return store.recent(100), device
    finally:
        store.close()


def _calendar_in(minutes: float):
    """A handler answering with one meeting `minutes` from the real now, so
    the run-loop tests need no clock injection to be deterministic."""
    def handler(request: httpx.Request) -> httpx.Response:
        starts = datetime.now() + timedelta(minutes=minutes)
        return httpx.Response(200, text=_ics(
            _event(f"DTSTART:{starts.strftime('%Y%m%dT%H%M%S')}", "SUMMARY:Standup"),
        ))
    return handler


async def test_a_fetched_reading_reaches_the_ordinary_when_test(tmp_path, monkeypatch):
    """TODO 99 and 100 in one line: the button fetched a calendar nobody
    authorised it to read and did something ten minutes before a meeting."""
    rows, _device = await _drive(tmp_path, monkeypatch, _calendar_in(7))
    names = [name for (_ts, _kind, name, _dur, _mode, _val) in rows]
    assert "meeting_soon" in names


async def test_a_reading_that_does_not_cross_the_line_does_not_fire(
    tmp_path, monkeypatch,
):
    """Same fetch, a meeting an hour out. The comparison language is the one
    that already existed - the source added no operator of its own."""
    rows, _device = await _drive(tmp_path, monkeypatch, _calendar_in(60))
    names = [name for (_ts, _kind, name, _dur, _mode, _val) in rows]
    assert "meeting_soon" not in names
    # But the reading is still logged under the reflex's own name, exactly as a
    # posted one is - a number that arrived is logged whether or not it fired,
    # which is what makes the Events page a chart of the sensor.
    readings = [
        value for (_ts, _kind, name, _dur, _mode, value) in rows
        if name == "next_meeting"
    ]
    assert readings and 55 <= readings[0] <= 60


async def test_a_poll_arrives_on_the_inbound_queue_and_never_as_a_press(
    tmp_path, monkeypatch,
):
    """A synthetic gesture would work and would make every log a lie - a
    session summary would record a press nobody made."""
    rows, device = await _drive(tmp_path, monkeypatch, _calendar_in(7))
    assert device.events.empty(), "the poller pushed a gesture at the device"
    # The row the reflex wrote is attributed to no mode and no trigger, which
    # is what a circumstance looks like; a press would have logged "ping".
    modes = [
        mode for (_ts, _kind, name, _dur, mode, _val) in rows
        if name == "meeting_soon"
    ]
    assert modes == [None]
    assert "ping" not in [name for (_ts, _kind, name, _dur, _mode, _val) in rows]


async def test_a_dead_endpoint_fires_nothing_and_says_so_once(
    tmp_path, monkeypatch, caplog,
):
    """All three of TODO 99's failure requirements, end to end: several
    attempts go by, none of them fires the reflex, and the log has one line
    rather than one per attempt."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("no route to host")

    # A tenth-of-a-second period, so several attempts fit in the window and
    # "one line, not one per attempt" is a claim the test can actually check.
    dead = {**RUN_CONFIG, "reflexes": [{
        **RUN_CONFIG["reflexes"][0],
        "from": {"url": {"url": "https://calendar.example/basic.ics",
                         "every_minutes": 0.002, "read": "ics"}},
    }]}
    with caplog.at_level(logging.WARNING, logger="aibutton"):
        rows, _device = await _drive(
            tmp_path, monkeypatch, handler, config=dead, seconds=1.0,
        )
    assert attempts >= 3, f"only {attempts} attempts - the test proved nothing"
    names = [name for (_ts, _kind, name, _dur, _mode, _val) in rows]
    assert "meeting_soon" not in names, "a dead server fired the reflex"
    # And no reading row either: those are named after the reflex and hold its
    # numbers, so a row meaning "the server was down" would poison the chart.
    assert "next_meeting" not in names
    complaints = [r for r in caplog.records if "next_meeting" in r.getMessage()]
    assert len(complaints) == 1, [r.getMessage() for r in complaints]
    assert "no route to host" in complaints[0].getMessage()


async def test_an_http_error_is_a_failure_not_an_empty_calendar(
    tmp_path, monkeypatch, caplog,
):
    """A 404 answering with an error page must not read as "no meetings" - that
    would be a reflex that goes quiet and looks like it is working."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<html>not found</html>")

    with caplog.at_level(logging.WARNING, logger="aibutton"):
        rows, _device = await _drive(tmp_path, monkeypatch, handler)
    assert not [
        name for (_ts, _kind, name, _dur, _mode, _val) in rows
        if name in ("meeting_soon", "next_meeting")
    ]
    assert any("HTTP 404" in r.getMessage() for r in caplog.records)
