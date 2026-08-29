"""Reflexes: a circumstance with an action attached (TODO 70/71).

Three layers, because they fail in three different ways. The parser has to
keep a half-finished reflex visible rather than dropping it; the endpoint has
to tell a script it typo'd; and the run loop has to dispatch one *without*
pretending a button was pressed.
"""

import asyncio
import json

import httpx
import pytest

import aibutton.config as cfg
import aibutton.main as main
from aibutton.audio import ToneLibrary
from aibutton.config import ConfigManager, parse_with_warnings
from aibutton.device import MockDevice, TriggerType
from aibutton.main import Clock, DeviceStatus
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app


# --- parsing ---------------------------------------------------------------

def test_a_reflex_holds_an_action_or_names_one():
    config = cfg.parse_config({
        "actions": {"celebrate": {"action": "log", "event": "party"}},
        "reflexes": [
            {"name": "moisture_low", "then": {"action": "log", "event": "dry"}},
            {"name": "deploy_done", "then": "celebrate"},
        ],
    })
    held, named = config.reflexes
    assert held.then == cfg.LogAction(event="dry")
    assert named.then == cfg.NamedAction(name="celebrate")
    # The fifth dispatch site resolves it the same way the other four do.
    assert cfg.resolve_action(config, named.then) == cfg.LogAction(event="party")


def test_a_dangling_name_is_kept_and_warned_about():
    config, warnings = parse_with_warnings({"reflexes": [{"name": "x", "then": "ghost"}]})
    assert config.reflexes[0].then == cfg.NamedAction(name="ghost")
    assert any("names action 'ghost'" in w for w in warnings), warnings
    # And it fails clearly at use time rather than doing something else.
    assert cfg.resolve_action(config, config.reflexes[0].then) is None


def test_a_scope_naming_no_app_warns_and_is_kept():
    config, warnings = parse_with_warnings({
        "reflexes": [{"name": "x", "then": {"action": "log", "event": "e"},
                      "while": "Ghost"}],
    })
    assert config.reflexes[0].while_app == "Ghost"
    assert any("no mode is named" in w for w in warnings), warnings


@pytest.mark.parametrize("entry", [
    "just a string",
    {"then": {"action": "log", "event": "e"}},           # no name
    {"name": "  ", "then": {"action": "log", "event": "e"}},
    {"name": "x"},                                        # no action
    {"name": "x", "then": {"action": "standby"}},         # not a reflex action
    {"name": "x", "then": {"action": "readout", "event": "e"}},
])
def test_an_unusable_reflex_is_dropped_and_the_rest_survive(entry):
    config = cfg.parse_config({
        "reflexes": [entry, {"name": "ok", "then": {"action": "log", "event": "e"}}],
    })
    assert [r.name for r in config.reflexes] == ["ok"]


def test_two_reflexes_cannot_share_a_name():
    config, warnings = parse_with_warnings({
        "reflexes": [
            {"name": "dup", "then": {"action": "log", "event": "first"}},
            {"name": "dup", "then": {"action": "log", "event": "second"}},
        ],
    })
    # The name is what a POST addresses, so the second could never be fired.
    assert [r.then.event for r in config.reflexes] == ["first"]
    assert any("two reflexes are named" in w for w in warnings), warnings


def test_a_broken_reflexes_key_never_breaks_the_config():
    config, warnings = parse_with_warnings({"reflexes": {"not": "a list"}, "web_port": 9999})
    assert config.reflexes == ()
    assert config.web_port == 9999  # every other key still landed
    assert any("must be a list" in w for w in warnings), warnings


def test_reflexes_round_trip_through_as_dict():
    raw = {
        "actions": {"celebrate": {"action": "log", "event": "party"}},
        "reflexes": [
            {"name": "a", "then": {"action": "enter_mode", "target": "Water me"}},
            {"name": "b", "then": "celebrate", "while": "Focus"},
        ],
        "modes": [{"name": "Focus", "template": "stopwatch",
                   "activation": {"type": "manual"}, "log_as": "focus"}],
    }
    once = cfg.parse_config(raw)
    written = cfg.as_dict(once)
    assert written["reflexes"] == raw["reflexes"]      # `then` stays a string
    assert cfg.parse_config(written).reflexes == once.reflexes


def test_a_config_that_predates_reflexes_still_loads():
    """No key, no reflexes, no complaint - and an empty list on the way out,
    which is what every other pool here writes when it holds nothing."""
    assert cfg.parse_config({}).reflexes == ()
    assert cfg.as_dict(cfg.parse_config({}))["reflexes"] == []


# --- the test it arrived with (TODO 72) ------------------------------------

def test_a_test_is_one_field_one_operator_one_number():
    config, warnings = parse_with_warnings({
        "reflexes": [{
            "name": "moisture_low", "then": {"action": "log", "event": "dry"},
            "when": {"field": "moisture", "op": "<", "value": 30},
        }],
    })
    assert config.reflexes[0].when == cfg.ReflexTest("moisture", "<", 30.0)
    assert not warnings


@pytest.mark.parametrize("op,value,fires", [
    ("<", 12, True), ("<", 42, False),
    ("<=", 30, True), (">", 42, True), (">=", 30, True),
    ("==", 30, True), ("!=", 30, False),
])
def test_every_operator_compares_the_way_it_reads(op, value, fires):
    reflex = cfg.Reflex(
        name="r", then=cfg.LogAction(event="e"),
        when=cfg.ReflexTest("moisture", op, 30.0),
    )
    assert cfg.reflex_matches(reflex, {"moisture": value}) == (fires, float(value))


def test_a_reading_is_returned_even_when_it_does_not_fire():
    """The event log wants the number either way - that is what turns a sensor
    into a chart rather than an alarm history."""
    reflex = cfg.Reflex(
        name="r", then=cfg.LogAction(event="e"),
        when=cfg.ReflexTest("moisture", "<", 30.0),
    )
    assert cfg.reflex_matches(reflex, {"moisture": 88}) == (False, 88.0)


@pytest.mark.parametrize("payload", [
    None, {}, {"other": 5}, {"moisture": "12"}, {"moisture": True}, "not a dict",
])
def test_a_missing_or_unusable_value_never_fires(payload):
    """A renamed sensor field must not become an alarm that goes off
    constantly - which is what firing-on-missing would do."""
    reflex = cfg.Reflex(
        name="r", then=cfg.LogAction(event="e"),
        when=cfg.ReflexTest("moisture", "<", 30.0),
    )
    assert cfg.reflex_matches(reflex, payload) == (False, None)


def test_a_reflex_with_no_test_fires_on_arrival():
    reflex = cfg.Reflex(name="r", then=cfg.LogAction(event="e"))
    assert cfg.reflex_matches(reflex, {"anything": 1}) == (True, None)


@pytest.mark.parametrize("when", [
    "moisture < 30",                                    # not an object
    {"op": "<", "value": 30},                           # no field
    {"field": "moisture", "value": 30},                 # no operator
    {"field": "moisture", "op": "~", "value": 30},      # not an operator
    {"field": "moisture", "op": "<", "value": "30"},    # not a number
    {"field": "moisture", "op": "<", "value": True},    # a bool is not a number
])
def test_a_broken_test_is_dropped_and_the_reflex_kept(when):
    """The reflex stays and fires unconditionally, which is visible. Silencing
    it would make a typo look like a sensor that stopped reporting."""
    config, warnings = parse_with_warnings({
        "reflexes": [{"name": "r", "then": {"action": "log", "event": "e"},
                      "when": when}],
    })
    assert [r.name for r in config.reflexes] == ["r"]
    assert config.reflexes[0].when is None
    assert warnings


def test_a_test_round_trips():
    raw = {"reflexes": [{
        "name": "r", "then": {"action": "log", "event": "e"},
        "when": {"field": "moisture", "op": ">=", "value": 30.5},
    }]}
    once = cfg.parse_config(raw)
    assert cfg.as_dict(once)["reflexes"] == raw["reflexes"]
    assert cfg.parse_config(cfg.as_dict(once)).reflexes == once.reflexes


# --- MIDI in as a source (TODO 73) -----------------------------------------

def test_a_source_says_which_messages_reach_a_reflex():
    config, warnings = parse_with_warnings({
        "reflexes": [{
            "name": "rec_on",
            "from": {"midi": {"port": "Button", "note": 95, "channel": 1}},
            "when": {"field": "velocity", "op": "==", "value": 127},
            "then": {"action": "log", "event": "recording"},
        }],
    })
    assert config.reflexes[0].source == cfg.MidiSource(
        port="Button", kind="note", number=95, channel=1,
    )
    assert not warnings


@pytest.mark.parametrize("spec,reason", [
    ("a port", "not an object"),
    ({"port": "X"}, "neither note nor cc"),
    ({"note": 95, "cc": 7}, "both note and cc"),
    ({"note": 200}, "out of range"),
    ({"note": True}, "a bool is not a number"),
])
def test_a_broken_source_is_dropped_and_the_url_still_fires_it(spec, reason):
    """A reflex is addressable by name whatever else is wrong with it, so the
    half that broke is the half that goes - never the reflex."""
    config, warnings = parse_with_warnings({
        "reflexes": [{"name": "r", "from": {"midi": spec},
                      "then": {"action": "log", "event": "e"}}],
    })
    assert [r.name for r in config.reflexes] == ["r"], reason
    assert config.reflexes[0].source is None
    assert warnings


def test_a_channel_out_of_range_falls_back_to_any_channel():
    """The narrower failure: the source is usable, one field of it is not, and
    hearing every channel is what the field's absence already means."""
    config, warnings = parse_with_warnings({
        "reflexes": [{"name": "r", "from": {"midi": {"cc": 7, "channel": 99}},
                      "then": {"action": "log", "event": "e"}}],
    })
    assert config.reflexes[0].source == cfg.MidiSource(kind="cc", number=7)
    assert any("channel must be 1-16" in w for w in warnings), warnings


def test_a_source_nobody_has_heard_of_is_named_in_the_warning():
    config, warnings = parse_with_warnings({
        "reflexes": [{"name": "r", "from": {"osc": {"address": "/go"}},
                      "then": {"action": "log", "event": "e"}}],
    })
    assert config.reflexes[0].source is None
    assert any("'osc'" in w for w in warnings), warnings


def test_a_source_round_trips():
    raw = {"reflexes": [{
        "name": "r", "then": {"action": "log", "event": "e"},
        "from": {"midi": {"port": "Button", "cc": 7, "channel": 3}},
    }]}
    once = cfg.parse_config(raw)
    assert cfg.as_dict(once)["reflexes"] == raw["reflexes"]
    assert cfg.parse_config(cfg.as_dict(once)).reflexes == once.reflexes


@pytest.mark.parametrize("kind,number,channel,heard", [
    ("note", 95, 1, True),
    ("note", 95, 9, False),     # wrong channel
    ("note", 94, 1, False),     # wrong note
    ("cc", 95, 1, False),       # a CC is not a note, whatever the number
])
def test_a_source_hears_only_what_it_names(kind, number, channel, heard):
    reflex = cfg.Reflex(
        name="r", then=cfg.LogAction(event="e"),
        source=cfg.MidiSource(port="Button", kind="note", number=95, channel=1),
    )
    assert cfg.reflex_hears(reflex, kind, number, channel) is heard


def test_a_source_with_no_channel_hears_every_channel():
    reflex = cfg.Reflex(
        name="r", then=cfg.LogAction(event="e"),
        source=cfg.MidiSource(kind="cc", number=7),
    )
    assert all(cfg.reflex_hears(reflex, "cc", 7, ch) for ch in range(1, 17))


def test_an_http_only_reflex_hears_no_midi_at_all():
    reflex = cfg.Reflex(name="r", then=cfg.LogAction(event="e"))
    assert not cfg.reflex_hears(reflex, "note", 0, 1)


# --- the endpoint ----------------------------------------------------------

@pytest.fixture
def ctx(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "reflexes": [{"name": "water_me", "then": {"action": "log", "event": "dry"}}],
    }), encoding="utf-8")
    store = EventStore(str(tmp_path / "events.db"))
    tones = ToneLibrary()
    fired: list[str] = []
    context = WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        device=MockDevice(),
        clock=Clock(),
        tones=tones,
        fire_reflex=lambda name, payload=None: (fired.append((name, payload)), True)[1],
    )
    context.fired = fired  # type: ignore[attr-defined]
    yield context
    store.close()
    tones.close()


@pytest.fixture
async def client(ctx):
    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_posting_a_reflex_queues_it(client, ctx):
    res = await client.post("/api/reflex/water_me")
    assert res.status_code == 200
    assert res.json() == {"queued": "water_me"}
    assert ctx.fired == [("water_me", None)]


async def test_the_new_spelling_answers_too_and_the_old_one_never_stops(client, ctx):
    """TODO 103 renamed reflexes to *reactions* in the UI. The route did not
    follow, it gained a second name.

    This URL is the one thing in the project written down *outside* it - in a
    phone shortcut, a cron line, a sensor's firmware - so retiring the old
    spelling is a rename someone else pays for. Both paths, one handler, and
    the test says so in one place rather than being split across two files.
    """
    res = await client.post("/api/reaction/water_me", json={"moisture": 12})
    assert res.status_code == 200
    assert res.json() == {"queued": "water_me"}

    res = await client.post("/api/reflex/water_me", json={"moisture": 12})
    assert res.status_code == 200

    assert ctx.fired == [("water_me", {"moisture": 12})] * 2


async def test_an_unknown_name_says_so_on_either_spelling(client, ctx):
    for path in ("/api/reaction/watrer_me", "/api/reflex/watrer_me"):
        res = await client.post(path)
        assert res.status_code == 404, path
        assert "water_me" in res.json()["detail"]
    assert ctx.fired == []


async def test_a_body_is_carried_to_the_loop_untouched(client, ctx):
    """The endpoint never tests it (TODO 72): one place evaluates, so a later
    source cannot end up with a second answer."""
    res = await client.post("/api/reflex/water_me", json={"moisture": 12})
    assert res.status_code == 200
    assert ctx.fired == [("water_me", {"moisture": 12})]


async def test_an_unknown_name_says_so_and_lists_what_exists(client, ctx):
    res = await client.post("/api/reflex/watrer_me")
    assert res.status_code == 404
    assert "water_me" in res.json()["detail"]
    assert ctx.fired == []


async def test_a_full_queue_refuses_rather_than_waiting(client, ctx):
    ctx.fire_reflex = lambda name, payload=None: False
    res = await client.post("/api/reflex/water_me")
    assert res.status_code == 503


async def test_a_service_that_cannot_dispatch_says_so(client, ctx):
    ctx.fire_reflex = None
    res = await client.post("/api/reflex/water_me")
    assert res.status_code == 503


# --- the run loop ----------------------------------------------------------

RUN_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "actions": {"note": {"action": "log", "event": "noted"}},
    "modes": [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "log", "event": "ping"}},
        {"name": "Water", "template": "counter", "activation": {"type": "manual"},
         "event": "water"},
    ],
    "reflexes": [
        {"name": "dry", "then": {"action": "log", "event": "dry"}},
        {"name": "moisture_low", "then": {"action": "log", "event": "water_me"},
         "when": {"field": "moisture", "op": "<", "value": 30}},
        {"name": "by_name", "then": "note"},
        {"name": "start_water", "then": {"action": "enter_mode", "target": "Water"}},
        {"name": "scoped", "then": {"action": "log", "event": "scoped"},
         "while": "Water"},
        {"name": "nowhere", "then": {"action": "enter_mode", "target": "Ghost"}},
    ],
}


async def _drive(tmp_path, monkeypatch, arrivals, after=0.3):
    """Run the service with an injected inbound queue, post each of
    `arrivals` - a name, or a `(name, payload)` pair - and hand back the rows
    the store ended up with."""
    cfg_path = tmp_path / "config.json"
    db_path = tmp_path / "events.db"
    cfg_path.write_text(
        json.dumps(dict(RUN_CONFIG, database_path=str(db_path))), encoding="utf-8"
    )
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    inbound: asyncio.Queue = asyncio.Queue()
    args = main._parse_args(["--no-web", "--no-lock", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=MockDevice(), inbound=inbound))
    await asyncio.sleep(0.1)  # let run() reach the main loop
    try:
        for arrival in arrivals:
            inbound.put_nowait(
                arrival if isinstance(arrival, tuple) else (arrival, None)
            )
            await asyncio.sleep(after)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    store = EventStore(str(db_path))
    try:
        return store.recent(100)
    finally:
        store.close()


async def test_a_posted_reflex_runs_its_action(tmp_path, monkeypatch):
    rows = await _drive(tmp_path, monkeypatch, ["dry", "by_name"])
    names = [name for (_ts, _kind, name, _dur, _mode, _val) in rows]
    assert "dry" in names        # the inline action
    assert "noted" in names      # the one that names a pool entry


async def test_a_reflex_can_start_an_app(tmp_path, monkeypatch):
    """The plant alarm, in one line: nobody pressed anything and the button is
    now in an app."""
    rows = await _drive(tmp_path, monkeypatch, ["start_water"])
    kinds = [(kind, name) for (_ts, kind, name, _dur, _mode, _val) in rows]
    assert ("mode_enter", "Water") in kinds


async def test_a_reflex_is_not_logged_as_a_press(tmp_path, monkeypatch):
    """An app that cannot tell a press from the world lies in its log: the row
    a reflex writes is attributed to no mode, because none was running."""
    rows = await _drive(tmp_path, monkeypatch, ["dry"])
    modes = [mode for (_ts, _kind, name, _dur, mode, _val) in rows if name == "dry"]
    assert modes == [None]


async def test_a_scoped_reflex_does_not_fire_when_its_app_is_not_running(
    tmp_path, monkeypatch,
):
    rows = await _drive(tmp_path, monkeypatch, ["scoped"])
    assert "scoped" not in [name for (_ts, _kind, name, _dur, _mode, _val) in rows]


async def test_a_reflex_pointing_at_nothing_fails_without_killing_the_loop(
    tmp_path, monkeypatch,
):
    rows = await _drive(tmp_path, monkeypatch, ["nowhere", "dry"])
    # The dangling one did nothing; the next one still worked, which is the
    # property that matters - the loop survived it.
    assert "dry" in [name for (_ts, _kind, name, _dur, _mode, _val) in rows]


async def test_a_value_that_matches_fires_and_one_that_does_not_only_logs(
    tmp_path, monkeypatch,
):
    """Both halves of TODO 72 in one run: the threshold decides whether the
    action happens, and the reading is recorded either way."""
    rows = await _drive(tmp_path, monkeypatch, [
        ("moisture_low", {"moisture": 12}),
        ("moisture_low", {"moisture": 88}),
    ])
    named = [(name, value) for (_ts, _kind, name, _dur, _mode, value) in rows]
    # One firing: the action ran once, for the reading below the threshold.
    assert named.count(("water_me", None)) == 1
    # Both readings landed in `value`, under the reflex's own name - which is
    # what gives the Events page a chart of the sensor rather than of alarms.
    assert sorted(v for (n, v) in named if n == "moisture_low") == [12.0, 88.0]


async def test_a_reflex_with_no_test_logs_no_reading(tmp_path, monkeypatch):
    """Nothing to report costs nothing: no test means no number, so the only
    row is the one the action itself writes - not a second one named after
    the reflex carrying NULL."""
    rows = await _drive(tmp_path, monkeypatch, [("dry", {"moisture": 12})])
    assert [(name, value) for (_ts, _kind, name, _d, _m, value) in rows] == [("dry", None)]


# --- reaching a running app (TODO 74) --------------------------------------

APP_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Transport"}},
        {"name": "Transport", "template": "signal", "activation": {"type": "manual"},
         "log_as": "transport",
         "states": [
             {"name": "Stopped", "color": "#000080", "style": "solid"},
             {"name": "Recording", "color": "#ff0000", "style": "breathe"},
         ]},
    ],
    "reflexes": [
        {"name": "rec_on", "while": "Transport",
         "when": {"field": "velocity", "op": "==", "value": 127},
         "then": {"action": "set_position", "name": "Recording"}},
        {"name": "nowhere", "while": "Transport",
         "then": {"action": "set_position", "name": "Nowhere"}},
        {"name": "elsewhere", "then": {"action": "log", "event": "system_wide"}},
        {"name": "homeless", "then": {"action": "set_position", "name": "Recording"}},
    ],
}


async def _in_app(tmp_path, monkeypatch, arrivals):
    """Open the Transport app with a press, deliver `arrivals`, then leave,
    and hand back the rows the store ended up with."""
    cfg_path, db_path = tmp_path / "config.json", tmp_path / "events.db"
    cfg_path.write_text(
        json.dumps(dict(APP_CONFIG, database_path=str(db_path))), encoding="utf-8"
    )
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    device = MockDevice()
    inbound: asyncio.Queue = asyncio.Queue()
    args = main._parse_args(["--no-web", "--no-lock", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device, inbound=inbound))
    await asyncio.sleep(0.15)
    try:
        device.press(TriggerType.SHORT_PRESS)  # -> Transport
        await asyncio.sleep(0.3)
        for arrival in arrivals:
            inbound.put_nowait(
                arrival if isinstance(arrival, tuple) else (arrival, None)
            )
            await asyncio.sleep(0.3)
        device.press(TriggerType.LONG_PRESS)   # leave
        await asyncio.sleep(0.4)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    store = EventStore(str(db_path))
    try:
        return store.recent(100)
    finally:
        store.close()


async def test_a_reflex_naming_a_running_app_moves_it(tmp_path, monkeypatch):
    """The DAW says it is recording and the app follows - with nobody pressing
    anything, and without a synthetic press in the log to lie about it."""
    rows = await _in_app(tmp_path, monkeypatch, [("rec_on", {"velocity": 127})])
    named = [(name, value, mode) for (_ts, _k, name, _d, mode, value) in rows]
    # The app moved to position 1 (Recording) and logged it the way a pressed
    # change is logged - the light was there, and how it got there does not
    # change what the log is for.
    assert ("transport", 1.0, "Transport") in named
    # The reading is attributed to the app that was running, which is the only
    # place that fact can still be recorded.
    assert ("rec_on", 127.0, "Transport") in named


async def test_a_delivered_reflex_that_fails_its_test_still_records_the_reading(
    tmp_path, monkeypatch,
):
    rows = await _in_app(tmp_path, monkeypatch, [("rec_on", {"velocity": 64})])
    named = [(name, value, mode) for (_ts, _k, name, _d, mode, value) in rows]
    assert ("rec_on", 64.0, "Transport") in named
    # ... and the app did not move: no position row at all.
    assert not any(name == "transport" for (name, _v, _m) in named)


async def test_a_reflex_for_nobody_waits_until_the_app_hands_the_button_back(
    tmp_path, monkeypatch,
):
    """An unscoped reflex is about the button and the world, not about the app
    it interrupted - so it is held, not acted on, and not dropped either."""
    rows = await _in_app(tmp_path, monkeypatch, ["elsewhere"])
    order = [(kind, name) for (_ts, kind, name, _d, _m, _v) in rows]
    # Newest first: the system-wide action ran *after* the app's exit row.
    assert order.index(("log", "system_wide")) < order.index(("mode_exit", "Transport"))


async def test_a_position_that_does_not_exist_is_reported_not_guessed(
    tmp_path, monkeypatch,
):
    """The app says so and stays where it is; nothing crashes and the session
    still closes cleanly."""
    rows = await _in_app(tmp_path, monkeypatch, ["nowhere"])
    kinds = [(kind, name) for (_ts, kind, name, _d, _m, _v) in rows]
    assert ("mode_exit", "Transport") in kinds
    assert not any(name == "transport" for (_k, name) in kinds)


async def test_a_position_with_no_app_running_fails_clearly(tmp_path, monkeypatch):
    """`set_position` outside an app is not "unknown action" - it is an app
    action with no app, and the loop survives it."""
    cfg_path, db_path = tmp_path / "config.json", tmp_path / "events.db"
    cfg_path.write_text(
        json.dumps(dict(APP_CONFIG, database_path=str(db_path))), encoding="utf-8"
    )
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    inbound: asyncio.Queue = asyncio.Queue()
    args = main._parse_args(["--no-web", "--no-lock", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=MockDevice(), inbound=inbound))
    await asyncio.sleep(0.15)
    try:
        inbound.put_nowait(("homeless", None))
        await asyncio.sleep(0.3)
        # Still alive, and still dispatching: the next reflex works.
        inbound.put_nowait(("elsewhere", None))
        await asyncio.sleep(0.3)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    store = EventStore(str(db_path))
    try:
        names = [name for (_ts, _k, name, _d, _m, _v) in store.recent(50)]
    finally:
        store.close()
    assert "system_wide" in names


# --- MIDI in, through the running service ----------------------------------

class _FakeMidi:
    """Stands in for winmm/rtmidi, like test_midi_clock's - it hands back the
    callback the listener registered so a test can play messages into it."""

    name = "fake"

    def __init__(self, names=("Button 3",)):
        self.names = list(names)
        self.on_message = None
        self.closed = False

    def in_ports(self):
        return list(self.names)

    def listen(self, index, on_message):
        self.on_message = on_message
        self.index = index

        def close():
            self.closed = True

        return close

    def play(self, status, data1, data2):
        assert self.on_message is not None, "nothing opened the port"
        self.on_message(status, data1, data2)


MIDI_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "log", "event": "ping"}},
    ],
    "reflexes": [
        {"name": "rec_on",
         "from": {"midi": {"port": "Button", "note": 95}},
         "when": {"field": "velocity", "op": "==", "value": 127},
         "then": {"action": "log", "event": "recording"}},
        {"name": "rec_off",
         "from": {"midi": {"port": "Button", "note": 95}},
         "when": {"field": "velocity", "op": "==", "value": 0},
         "then": {"action": "log", "event": "stopped"}},
    ],
}


async def _drive_midi(tmp_path, monkeypatch, messages):
    """Run the service with a fake MIDI backend, play `messages` into the port
    it opens, and hand back the rows the store ended up with."""
    from aibutton import midi_io

    backend = _FakeMidi()
    monkeypatch.setattr(midi_io, "_BACKEND", backend)
    cfg_path = tmp_path / "config.json"
    db_path = tmp_path / "events.db"
    cfg_path.write_text(
        json.dumps(dict(MIDI_CONFIG, database_path=str(db_path))), encoding="utf-8"
    )
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    args = main._parse_args(["--no-web", "--no-lock", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=MockDevice()))
    # The listeners are opened by the same tick that hot-reloads the palette,
    # so this waits for one rather than for a second startup path.
    await asyncio.sleep(1.4)
    try:
        assert backend.on_message is not None, "the service never opened the port"
        for message in messages:
            backend.play(*message)
            await asyncio.sleep(0.3)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert backend.closed, "the listener outlived the service"
    store = EventStore(str(db_path))
    try:
        return [name for (_ts, _kind, name, _d, _m, _v) in store.recent(50)]
    finally:
        store.close()


async def test_the_same_note_means_two_things_and_the_velocity_decides(
    tmp_path, monkeypatch,
):
    """MCU lights a lamp with note 95 velocity 127 and darkens it with the
    same note at 0. A reflex ignoring the velocity would fire on both - which
    is exactly why the test in TODO 72 exists."""
    names = await _drive_midi(tmp_path, monkeypatch, [
        (0x90, 95, 127),   # recording
        (0x90, 95, 0),     # stopped
    ])
    assert "recording" in names
    assert "stopped" in names


async def test_a_message_no_reflex_names_does_nothing(tmp_path, monkeypatch):
    names = await _drive_midi(tmp_path, monkeypatch, [
        (0x90, 94, 127),   # a note nobody asked for
        (0xB0, 95, 127),   # a CC with a note's number
        (0xF8, 0, 0),      # clock
    ])
    assert names == []
