"""Where a readout gets its number, and how it draws it (TODO 118a).

**The seam the whole of 118 hangs on.** Before this, a Tally's two contributed
shortcuts were two unrelated actions that merely happened to agree: `count_up`
wrote the app's `docSlot` and `show_count` recounted a same-named event log.
They agreed only while nothing counted by more than one, and never past 99 -
the old renderer clamps there, silently. So `readout` grew a **source** (an
event's rows, or an app's declared slot) and a **scheme** (`readout.SCHEMES`,
TODO 91's uncapped compiler), and `config.counter_readout` became the one place
that decides which of each a Tally uses - for its own surface *and* for the
shortcut it lends out.

**The delicate half is that nothing already written may change appearance.**
Every `readout` in every config and scene carries an event and two colours and
no source and no scheme, and must still blink exactly what it blinked
yesterday. `test_the_old_renderer_is_not_the_new_one_generalised` is why that
is a preserved call rather than a claimed equivalence: `place_value` is the
same *idea* with one pair of dwells for every place, where the old renderer
gives the tens group its own slower pair - so the two agree on 0 and on
nothing else.

Three tiers, cheapest first, and deliberately: the parser and `readout_look`
are pure, so most of this costs nothing to run. Only what genuinely needs the
loop - "the press said 150, and the light showed it" - is driven through
`main.run` against a MockDevice, in the style of test_main_takeover.py. The
JavaScript half runs through node and **skips with a reason** where node is
absent, the split test_js_modules.py already draws.
"""

import asyncio
import json
import subprocess

import pytest

import aibutton.main as main
from aibutton import readout, sequencer
from aibutton.config import (
    READOUT_SOURCES,
    CounterBehavior,
    ReadoutAction,
    _action_to_dict,
    _mode_to_dict,
    counter_readout,
    parse_config,
    parse_with_warnings,
    readout_look,
)
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.documents import DocumentStore
from aibutton.store import EventStore

# The node harness's two constants, borrowed rather than re-derived: that file
# already knows to hand schema.js an absolute file:// URL and to decode node's
# UTF-8 on Windows, and a second copy of either would be a fixture waiting to
# drift.
from test_app_actions import SCHEMA_JS_PATH, needs_node, node


def _bound(action: dict) -> dict:
    """One ambient mode whose short press is `action`."""
    return {"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": action,
    }]}


# --- the parser: the new fields, and the old ones untouched -----------------


LEGACY = [
    (
        "the event and nothing else, which is every readout ever written",
        {"action": "readout", "event": "coffee"},
        ReadoutAction(event="coffee"),
    ),
    (
        "an event with both colours chosen",
        {"action": "readout", "event": "coffee",
         "tens_color": "#112233", "units_color": "#445566"},
        ReadoutAction(event="coffee", tens_color="#112233", units_color="#445566"),
    ),
    (
        "an explicit source of event, which is what absent already meant",
        {"action": "readout", "event": "coffee", "source": "event"},
        ReadoutAction(event="coffee"),
    ),
]


@pytest.mark.parametrize("scenario,raw,expected", LEGACY, ids=[s for s, _, _ in LEGACY])
def test_a_readout_written_before_this_parses_as_what_it_always_was(
    scenario, raw, expected,
):
    """The compatibility claim at the parser: the five new fields default to
    exactly the readout that existed before them, so an old binding is not a
    migration - it is the same object."""
    config, warnings = parse_with_warnings(_bound(raw))
    assert config.modes[0].behavior.actions["short_press"] == expected, scenario
    assert not warnings, scenario


APP_SOURCED = [
    (
        "an app and a slot, the pair set_value already names",
        {"action": "readout", "source": "app", "app": "Smokes", "slot": "count"},
        ReadoutAction(source="app", app="Smokes", slot="count"),
    ),
    (
        "with a scheme, which is what lifts the ninety-nine cap",
        {"action": "readout", "source": "app", "app": "Smokes", "slot": "count",
         "scheme": "place_value"},
        ReadoutAction(source="app", app="Smokes", slot="count", scheme="place_value"),
    ),
    (
        "with that scheme's own colours",
        {"action": "readout", "source": "app", "app": "Smokes", "slot": "count",
         "scheme": "binary", "colors": ["#112233", "#445566"]},
        ReadoutAction(source="app", app="Smokes", slot="count", scheme="binary",
                      colors=("#112233", "#445566")),
    ),
    (
        "names are trimmed, as set_value's are",
        {"action": "readout", "source": "app", "app": " Smokes ", "slot": " count "},
        ReadoutAction(source="app", app="Smokes", slot="count"),
    ),
]


@pytest.mark.parametrize(
    "scenario,raw,expected", APP_SOURCED, ids=[s for s, _, _ in APP_SOURCED],
)
def test_a_readout_can_point_at_an_apps_own_value(scenario, raw, expected):
    config = parse_config({"modes": [
        {"name": "Desk", "template": "actions", "activation": {"type": "always"},
         "short_press": raw},
        {"name": "Smokes", "template": "counter", "activation": {"type": "manual"},
         "event": "smokes", "durable": True},
    ]})
    assert config.modes[0].behavior.actions["short_press"] == expected, scenario


PER_FIELD_FALLBACKS = [
    (
        "a scheme nobody compiled leaves the tens and units digits",
        {"event": "coffee", "scheme": "semaphore"},
        "scheme", "", "scheme",
    ),
    (
        "a source nobody has heard of counts the event log",
        {"event": "coffee", "source": "sideways"},
        "source", "event", "source",
    ),
    (
        "a colour that is not one is dropped and the rest of the list stands",
        {"event": "coffee", "scheme": "binary", "colors": ["#112233", "octarine"]},
        "colors", ("#112233",), "colors[1]",
    ),
    (
        "a colours field that is not a list at all leaves the scheme's own",
        {"event": "coffee", "scheme": "binary", "colors": "#112233"},
        "colors", (), "colors",
    ),
    (
        "and a bad colour still costs only the colour, as it always did",
        {"event": "coffee", "tens_color": "not-a-colour"},
        "tens_color", "#ff8800", "tens_color",
    ),
]


@pytest.mark.parametrize(
    "scenario,over,field,expected,complaint", PER_FIELD_FALLBACKS,
    ids=[s for s, _, _, _, _ in PER_FIELD_FALLBACKS],
)
def test_a_bad_field_costs_that_field_and_never_the_readout(
    scenario, over, field, expected, complaint,
):
    """`_parse_effect`'s shape applied to the new questions: a config that says
    something unreadable still has a working button, and the web API hands the
    editor the same complaint the log got."""
    config, warnings = parse_with_warnings(_bound({"action": "readout", **over}))
    action = config.modes[0].behavior.actions["short_press"]
    assert getattr(action, field) == expected, scenario
    assert action.event == "coffee", "the readout itself survived"
    assert any(complaint in warning for warning in warnings), warnings


NO_NUMBER = [
    ("no event under the event source", {"action": "readout"}),
    ("an app source with no app named",
     {"action": "readout", "source": "app", "slot": "count"}),
    ("an app source with no slot named",
     {"action": "readout", "source": "app", "app": "Smokes"}),
    ("an app source whose app is only whitespace",
     {"action": "readout", "source": "app", "app": "   ", "slot": "count"}),
]


@pytest.mark.parametrize("scenario,raw", NO_NUMBER, ids=[s for s, _ in NO_NUMBER])
def test_a_readout_with_no_number_to_read_is_not_a_valid_action(scenario, raw):
    """Unfinished, rather than dangling - there is nothing to keep. It falls
    through to the same "not a valid action" a readout with no event has always
    produced, which is the message the editor already knows how to show."""
    config, warnings = parse_with_warnings(_bound(raw))
    assert not any(mode.name == "Desk" for mode in config.modes), scenario
    assert any("not a valid action" in warning for warning in warnings), warnings


def test_a_readout_naming_an_app_nobody_has_is_kept_and_warned_about():
    """The dangling-reference rule, the same call `set_value` makes: a rename
    is a likelier explanation than a mistake, and quietly repointing the
    binding at some other app would be worse than leaving it broken."""
    config, warnings = parse_with_warnings(_bound({
        "action": "readout", "source": "app", "app": "Ghost", "slot": "count",
    }))
    action = config.modes[0].behavior.actions["short_press"]
    assert action.app == "Ghost", "the reference is kept"
    assert any("Ghost" in warning for warning in warnings), warnings


def test_a_readout_naming_a_slot_that_app_does_not_keep_is_reported():
    """The second half of the same pass, and the reason it is one pass: a
    stopwatch declares no slots at all, so pointing a readout at its `count`
    is the same mistake as pointing a `set_value` there."""
    config, warnings = parse_with_warnings({"modes": [
        {"name": "Desk", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "readout", "source": "app",
                         "app": "Mile", "slot": "count"}},
        {"name": "Mile", "template": "stopwatch", "activation": {"type": "manual"},
         "log_as": "mile"},
    ]})
    assert any("no values of its own" in warning for warning in warnings), warnings


def test_a_readout_round_trips_through_the_editor():
    """Parse, serialise, parse - the loop a Save makes. All five new keys are
    written every time, so an app-sourced readout does not quietly become an
    event-sourced one the first time somebody opens the page."""
    raw = _bound({
        "action": "readout", "source": "app", "app": "Smokes", "slot": "count",
        "scheme": "morse", "colors": ["#112233"],
    })
    raw["modes"].append({
        "name": "Smokes", "template": "counter", "activation": {"type": "manual"},
        "event": "smokes", "durable": True,
    })
    once = parse_config(raw)
    written = _mode_to_dict(once.modes[0])["short_press"]
    assert written["source"] == "app" and written["colors"] == ["#112233"]
    twice = parse_config({"modes": [_mode_to_dict(m) for m in once.modes]})
    assert twice.modes[0].behavior == once.modes[0].behavior


def test_the_two_sources_are_the_two_the_parser_names():
    """A guard on the tables above: they are written against the constant, so
    a third source added to `READOUT_SOURCES` and nowhere else fails here
    rather than passing untested."""
    assert READOUT_SOURCES == ("event", "app")


# --- the tally configures the scheme, not each binding ----------------------


def test_a_tally_written_before_schemes_existed_keeps_the_digits_it_had():
    config = parse_config({"modes": [
        {"name": "Water", "template": "counter", "activation": {"type": "manual"},
         "event": "water"},
    ]})
    behavior = config.modes[0].behavior
    assert behavior == CounterBehavior(event="water")
    assert behavior.readout_scheme == "" and behavior.readout_colors == ()


def test_a_tallys_scheme_falls_back_without_costing_the_tally():
    config, warnings = parse_with_warnings({"modes": [
        {"name": "Water", "template": "counter", "activation": {"type": "manual"},
         "event": "water", "readout_scheme": "semaphore"},
    ]})
    assert config.modes[0].behavior.readout_scheme == ""
    assert config.modes[0].behavior.event == "water"
    assert any("readout_scheme" in warning for warning in warnings), warnings


COUNTER_READOUTS = [
    (
        "a day counter is its rows, so its readout counts them",
        {"event": "water"},
        ReadoutAction(event="water"),
    ),
    (
        "a running total lives in the document, so its readout reads the slot",
        {"event": "smokes", "durable": True},
        ReadoutAction(event="smokes", source="app", app="Tally", slot="count"),
    ),
    (
        "the scheme and its colours come off the tally either way",
        {"event": "smokes", "durable": True, "readout_scheme": "place_value",
         "readout_colors": ["#112233", "#445566"]},
        ReadoutAction(event="smokes", source="app", app="Tally", slot="count",
                      scheme="place_value", colors=("#112233", "#445566")),
    ),
    (
        "and a day counter's scheme is configured in exactly the same place",
        {"event": "water", "readout_scheme": "morse"},
        ReadoutAction(event="water", scheme="morse"),
    ),
]


@pytest.mark.parametrize(
    "scenario,over,expected", COUNTER_READOUTS,
    ids=[s for s, _, _ in COUNTER_READOUTS],
)
def test_a_tallys_own_readout_follows_where_it_keeps_its_number(
    scenario, over, expected,
):
    """TODO 91's "Done when" as a table: the source, the scheme and its colours
    are all facts about the tally, so `counter_readout` is the only thing that
    has to know them and everything showing the number asks it."""
    config = parse_config({"modes": [
        dict({"name": "Tally", "template": "counter",
              "activation": {"type": "manual"}}, **over),
    ]})
    mode = config.modes[0]
    assert counter_readout(mode.behavior, mode.name) == expected, scenario


# --- the renderers: the old one preserved, the new ones uncapped ------------


def test_the_old_renderer_is_not_the_new_one_generalised():
    """**The measurement behind keeping the legacy call**, rather than a claim
    that `place_value` with two colours is the same thing.

    It is the same *idea* - a colour per decimal place, the digit blinked that
    many times - and not the same rendering: the old one gives the tens group
    its own slower pair of dwells (0.5s on, 0.35s off) where `place_value` uses
    one pair for every place (0.3s / 0.22s), and the group gap differs too. So
    swapping the default would have changed the appearance of every readout
    ever written, in the one thing a readout promises - that the same number
    always looks the same.
    """
    same = [
        value for value in range(100)
        if tuple(sequencer.readout(value, "#ff8800", "#3399ff").stops)
        == readout.place_value(value, colors=("#3399ff", "#ff8800"))
    ]
    # Zero, and only zero: both render it as the one dim blink that says
    # "counted nothing" rather than "nothing happened".
    assert same == [0]


@pytest.mark.parametrize("value", [0, 1, 7, 20, 27, 99, 150])
def test_a_readout_with_no_scheme_renders_exactly_what_it_always_did(value):
    """The compatibility claim where it is cheapest to make, and strongest:
    `readout_look` on a legacy action is `sequencer.readout`, stop for stop,
    including the 99 clamp that 150 runs into."""
    action = ReadoutAction(event="coffee")
    assert readout_look(action, value) == sequencer.readout(
        value, action.tens_color, action.units_color,
    )


UNCAPPED = [
    ("morse", "150 is three characters of Morse, not two"),
    ("place_value", "150 is one flash, a gap, then five - the zero is skipped"),
    ("binary", "150 is eight bits"),
    ("hour_colors", "150 is a hundred and fifty pulses - absurd, but honest"),
]


@pytest.mark.parametrize("scheme,scenario", UNCAPPED, ids=[s for s, _ in UNCAPPED])
def test_every_scheme_reads_a_number_past_the_old_cap(scheme, scenario):
    """The old renderer clamps at 99 and says nothing about it, which is why a
    tally in the hundreds needed a scheme at all. None of the four clamps."""
    action = ReadoutAction(event="x", scheme=scheme)
    assert readout_look(action, 150) != readout_look(action, 99), scenario
    assert readout_look(action, 150) != readout_look(action, 50), scenario
    # And the clamp really is the thing being escaped: the default renderer
    # cannot tell 150 from 99 at all.
    plain = ReadoutAction(event="x")
    assert readout_look(plain, 150) == readout_look(plain, 99)


COLOR_ROLES = [
    ("morse takes one colour", "morse", ("#112233",), {"color": "#112233"}),
    ("binary takes zero then one", "binary", ("#112233", "#445566"),
     {"zero_color": "#112233", "one_color": "#445566"}),
    ("place value takes the whole wheel", "place_value", ("#112233", "#445566"),
     {"colors": ("#112233", "#445566")}),
    ("hour colours takes the whole wheel too", "hour_colors", ("#112233",),
     {"colors": ("#112233",)}),
    ("and an empty list leaves every scheme its own", "binary", (), {}),
]


@pytest.mark.parametrize(
    "scenario,scheme,colors,expected", COLOR_ROLES,
    ids=[s for s, _, _, _ in COLOR_ROLES],
)
def test_one_flat_colour_list_reaches_each_schemes_own_arguments(
    scenario, scheme, colors, expected,
):
    """One field in the config, four spellings in the compiler. The table is
    what keeps a caller from having to know which is which - and what makes a
    fifth scheme a row rather than a branch."""
    assert readout.scheme_opts(scheme, colors) == expected, scenario
    # Every configured colour actually reaches the light. 21 rather than a
    # single digit on purpose: "colour per digit" only reaches its second
    # colour once there is a second place to put it in.
    stops = readout_look(ReadoutAction(scheme=scheme, colors=colors), 21).stops
    for color in colors:
        assert any(stop.color == color for stop in stops), scenario


def test_every_scheme_clears_the_flash_floor_by_construction():
    """`readout.py` promises this rather than leaning on `config.sequence_safe`,
    and the promise is what lets a compiled package carry one (CLAUDE.md's
    three paths to the light). Checked over a spread of sizes, because the
    schemes differ in *which* dwell is shortest."""
    from aibutton.device import SAFE_MIN_PERIOD_S
    floor = SAFE_MIN_PERIOD_S / 2
    for scheme in readout.SCHEMES:
        for value in (0, 1, 9, 27, 99, 150, 1021):
            for stop in readout_look(ReadoutAction(scheme=scheme), value).stops:
                assert stop.hold_s + stop.fade_s >= floor, (scheme, value)


def test_the_surface_and_the_shortcut_render_the_identical_stop_list():
    """The claim 118a exists for, at the level it is actually decided.

    `run_counter`'s periodic flash and the "show the count" shortcut are the
    same `ReadoutAction` (`counter_readout`) put through the same renderer
    (`readout_look`), so a tally cannot say one thing on its own page and
    another from a menu. Asserted here rather than only end-to-end because
    this is where it would break - the loop below merely uses it.
    """
    config = parse_config({"modes": [
        {"name": "Tally", "template": "counter", "activation": {"type": "manual"},
         "event": "smokes", "durable": True, "readout_scheme": "place_value",
         "readout_colors": ["#112233", "#445566"]},
    ]})
    mode = config.modes[0]
    own = counter_readout(mode.behavior, mode.name)
    # The shortcut is the same action after a trip through the file it would
    # be saved into - which is the only way a binding ever reaches the button.
    shortcut = parse_config(
        _bound(_action_to_dict(own)),
    ).modes[0].behavior.actions["short_press"]
    assert shortcut == own
    assert readout_look(shortcut, 150) == readout_look(own, 150)
    assert readout_look(own, 150) == sequencer.Sequence(
        stops=readout.render(150, "place_value", colors=("#112233", "#445566")),
        repeat=False,
    )


# --- driving it: the value, and the failure ---------------------------------
# What genuinely needs the loop: which number a press finds, and what the light
# does when there is not one. The *rendering* is pinned above, purely, so
# nothing here has to wait for a hundred and fifty pulses to finish.


class _RecordingDevice(MockDevice):
    """A MockDevice keeping every push rather than only the last state.

    A readout is a sequence, so what proves one ran is the frames that went
    past - `MockDevice` holds current state, which is the right shape for every
    other test and the wrong one for this.
    """

    def __init__(self) -> None:
        super().__init__()
        self.pushes: list[tuple] = []

    def set_led(self, state, effect=None) -> None:
        super().set_led(state, effect)
        self.pushes.append((state, getattr(effect, "color", None)))


def _world(short_press: dict, **tally) -> dict:
    """Home with a readout on its short press, and one Tally to point it at."""
    mode = {
        "name": "Tally", "template": "counter", "activation": {"type": "manual"},
        "event": "smokes", "durable": True,
    }
    mode.update(tally)
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "modes": [
            {"name": "Home", "template": "actions",
             "activation": {"type": "always"},
             "short_press": short_press,
             "double_tap": {"action": "enter_mode", "target": "Tally"}},
            mode,
        ],
    }


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def _run(tmp_path, monkeypatch, config, script, doc=None, rows=0, settle=0.6):
    """Seed the stores, write `config`, play `script`, and hand back the frames
    that reached the light and the lines the status bar was given."""
    db_path = tmp_path / "e.db"
    if doc is not None:
        docs = DocumentStore(str(db_path))
        try:
            docs.set("Tally", "count", doc)
        finally:
            docs.close()
    if rows:
        events = EventStore(str(db_path))
        try:
            for _ in range(rows):
                events.log_event("coffee")
        finally:
            events.close()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(config, database_path=str(db_path))), encoding="utf-8",
    )
    said: list[tuple] = []

    class _RecordingStatus(main.DeviceStatus):
        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == "last_message":
                # `last_ok` is set before the message at every site that sets
                # both, and `getattr` covers construction, where neither is.
                said.append((getattr(self, "last_ok", None), value))

    monkeypatch.setattr(main, "DeviceStatus", _RecordingStatus)
    device = _RecordingDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.2)
    # Startup's own pushes are not what any of these tests is about, and one of
    # them compares the *set* of colours that reached the light against what a
    # scheme can produce - so the resting frames before the first press would
    # be noise that looks like a failure.
    device.pushes.clear()
    try:
        for trigger in script:
            device.press(trigger)
            await _drain(device.events)
            await asyncio.sleep(settle)
        pushed = list(device.pushes)
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    return pushed, said


async def test_an_old_readout_still_counts_the_log_and_says_so(
    tmp_path, monkeypatch,
):
    """The compatibility claim through the loop: an untouched binding finds the
    same number in the same place, and both of its colours show."""
    pushed, said = await _run(
        tmp_path, monkeypatch,
        _world({"action": "readout", "event": "coffee",
                "tens_color": "#ff8800", "units_color": "#3399ff"}),
        [TriggerType.SHORT_PRESS],
        rows=27, settle=1.2,
    )
    assert (True, "coffee: 27 today") in said, said
    colors = {color for _state, color in pushed if color}
    assert "#ff8800" in colors, "the tens digit never showed"
    assert LEDState.ERROR not in [state for state, _ in pushed]


@pytest.mark.parametrize("scheme", readout.SCHEMES)
async def test_a_readout_reads_a_durable_tallys_slot_past_ninety_nine(
    tmp_path, monkeypatch, scheme,
):
    """The feature, end to end: the number is the app's own 150 - not the event
    log's zero, and not the 99 the old renderer would have clamped it to - and
    the light wears the colours the chosen scheme uses for it."""
    pushed, said = await _run(
        tmp_path, monkeypatch,
        _world({"action": "readout", "source": "app", "app": "Tally",
                "slot": "count", "scheme": scheme}),
        [TriggerType.SHORT_PRESS],
        doc=150,
    )
    assert (True, "Tally.count: 150") in said, said
    expected = {
        stop.color
        for stop in readout_look(ReadoutAction(scheme=scheme), 150).stops
    }
    shown = {color for _state, color in pushed if color}
    assert shown, "nothing reached the light at all"
    assert shown <= expected, sorted(shown - expected)


async def test_a_readout_naming_an_app_nobody_has_fails_where_it_is_pressed(
    tmp_path, monkeypatch,
):
    """The other half of the dangling rule. The parser kept the reference and
    said so; this is the press, and it must not blink the document store's
    default zero as though it were somebody's count - a wrong number is worse
    than an error, because nothing about it looks wrong."""
    pushed, said = await _run(
        tmp_path, monkeypatch,
        _world({"action": "readout", "source": "app", "app": "Ghost",
                "slot": "count"}),
        [TriggerType.SHORT_PRESS],
    )
    assert any(ok is False and "Ghost" in text for ok, text in said), said
    assert LEDState.ERROR in [state for state, _ in pushed]


async def test_the_tally_shows_the_number_its_shortcut_would_show(
    tmp_path, monkeypatch,
):
    """One run, both paths. The Tally is opened and says 150 - its document,
    not its rows - and the shortcut bound in Home says 150 too. Two readings of
    one number, which is the whole of 118a in a sentence.
    """
    tally = dict(readout_scheme="place_value", show_every_s=0.4)
    # The shortcut is derived from the tally as parsed, not hand-written here:
    # a copy of the body would be the drift this whole item is about.
    parsed = parse_config(_world({"action": "log", "event": "x"}, **tally))
    behavior = next(m for m in parsed.modes if m.name == "Tally").behavior
    shortcut = _action_to_dict(counter_readout(behavior, "Tally"))
    pushed, said = await _run(
        tmp_path, monkeypatch,
        _world(shortcut, **tally),
        [TriggerType.SHORT_PRESS, TriggerType.DOUBLE_TAP],
        doc=150, settle=1.2,
    )
    assert (True, "Tally.count: 150") in said, said
    assert any(text == "smokes: 150" for _ok, text in said), said
    # The tally's own flash borrows COUNTING and hands it straight back, so the
    # surface is showing that number rather than the app merely being open.
    assert any(
        state is LEDState.COUNTING and color for state, color in pushed
    ), pushed


# --- the mirrored half: what the editor contributes -------------------------

_HARNESS = """
import { contributedActions } from %(schema)s;
import { readFileSync } from 'node:fs';
const modes = JSON.parse(readFileSync(%(modes)s, 'utf8'));
const out = {};
for (const row of contributedActions(modes)) {
  if (row.id === 'counter:show_count') out[row.app] = row.body;
}
console.log(JSON.stringify(out));
"""


@needs_node
def test_the_tallys_contributed_shortcut_is_the_readout_it_shows_itself(tmp_path):
    """The mirror, checked rather than trusted (CLAUDE.md).

    schema.js decides what the action picker pre-fills and `counter_readout`
    decides what the app's own surface shows, and 118a's whole point is that
    those are one decision. A table in JavaScript cannot import the Python one,
    so what is asserted is that the two parse to the same action - for a day
    counter *and* a running total, which is exactly where they differ.
    """
    config = parse_config({"modes": [
        {"name": "Water", "template": "counter", "activation": {"type": "manual"},
         "event": "water"},
        {"name": "Smokes", "template": "counter", "activation": {"type": "manual"},
         "event": "smokes", "durable": True, "readout_scheme": "place_value",
         "readout_colors": ["#112233", "#445566"]},
    ]})
    modes_path = tmp_path / "modes.json"
    modes_path.write_text(
        json.dumps([_mode_to_dict(mode) for mode in config.modes]), encoding="utf-8",
    )
    harness = tmp_path / "harness.mjs"
    harness.write_text(
        _HARNESS % {
            "schema": json.dumps(SCHEMA_JS_PATH.as_uri()),
            "modes": json.dumps(str(modes_path)),
        },
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, str(harness)], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    bodies = json.loads(result.stdout)
    assert set(bodies) == {"Water", "Smokes"}, bodies
    for mode in config.modes:
        offered = parse_config(_bound(bodies[mode.name])).modes[0]
        assert offered.behavior.actions["short_press"] == counter_readout(
            mode.behavior, mode.name,
        ), mode.name
