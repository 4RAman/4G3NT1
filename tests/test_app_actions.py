"""What an app contributes, and what a Tally's own surface does (TODO 118).

Two halves of one idea, tested together because they are the same claim from
two sides: *an app is a thing you install, and installing it puts shortcuts in
your reach as well as a screen you can open.*

**118b - the shortcuts.** A template declares an `actions` list in
[schema.js](aibutton/web/static/schema.js) and every entry is a **pre-filled
instance of an action the button already has**. Nothing new reaches
`config.json`, so there is no migration and no round-trip to check; what there
*is* to check is the two things a table like that can quietly get wrong:

  * a body that the real Python parser does not accept (a `set_value` naming a
    slot no template declares, a `readout` missing a colour), which would
    produce a shortcut that silently becomes something else on Save; and
  * a shortcut offered somewhere its underlying action is not, which is the
    same failure the gesture sub-editor's `offered` filter has always existed
    to prevent.

Both need JavaScript, so they run through node and **skip with a reason where
node is absent** - the split [test_js_modules.py](tests/test_js_modules.py)
already draws, for the reason it gives.

**118c - the Tally's surface.** Five gestures with their own steps, a periodic
readout, and long press still leaving. Those are Python and are driven through
`main.run` against a `MockDevice`, in the house style of
[test_main_takeover.py](tests/test_main_takeover.py) - the only way to assert
that an old config *behaves* as it did rather than merely parsing as it did.
"""

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import aibutton.main as main
from aibutton.config import (
    HOOK_ACTIONS,
    POOL_ACTIONS,
    REFLEX_ACTIONS,
    SEQUENCE_ACTIONS,
    TRIGGER_TYPES,
    CounterBehavior,
    LogAction,
    SetValueAction,
    bound_triggers,
    _mode_to_dict,
    parse_config,
    parse_with_details,
)
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

# Borrowed rather than copied: `_wire_kind` is how a dataclass name becomes the
# string `action:` carries, and a second copy of that rule is a mirrored table
# with nothing testing it (CLAUDE.md). If it is ever renamed this import fails
# loudly, which is the failure worth having.
from test_schema_mirror import _wire_kind

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_JS_PATH = ROOT / "aibutton" / "web" / "static" / "schema.js"
SCHEMA_JS = SCHEMA_JS_PATH.read_text(encoding="utf-8")

node = shutil.which("node")
needs_node = pytest.mark.skipif(
    node is None,
    reason="node is not installed - the JavaScript half of this is optional, "
           "and nothing the service runs needs it",
)


# --- a config with one of everything ---------------------------------------
# Every template that declares `actions` needs an instance here, or the sweep
# below passes by testing nothing. The guard test right after it says so out
# loud rather than trusting the list to stay complete.

def _world() -> dict:
    """A config exercising every template that contributes a shortcut."""
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "modes": [
            {
                "name": "Home", "template": "actions",
                "activation": {"type": "always"},
                "short_press": {"action": "log", "event": "ping"},
            },
            {
                "name": "Water", "template": "counter",
                "activation": {"type": "manual"}, "event": "water",
            },
            {
                "name": "Smokes", "template": "counter",
                "activation": {"type": "manual"}, "event": "smokes",
                "durable": True,
            },
            {
                "name": "Mile", "template": "stopwatch",
                "activation": {"type": "manual"}, "log_as": "mile",
            },
            {
                "name": "Wake", "template": "notice",
                "activation": {"type": "schedule", "at": "07:00"},
                "log_as": "alarm",
            },
            {
                "name": "Apps", "template": "launcher",
                "activation": {"type": "manual"},
            },
            {
                "name": "Status", "template": "signal",
                "activation": {"type": "manual"},
                "states": [
                    {"name": "Free", "color": "#00ff00"},
                    {"name": "Busy", "color": "#ff0000"},
                ],
            },
            {
                "name": "DAW", "template": "control",
                "activation": {"type": "manual"},
                "short_press": {"action": "log", "event": "daw"},
                "positions": [{"name": "Recording"}],
            },
        ],
    }


_HARNESS = """
import {
  contributedActions, ACTION_BY_TYPE,
  POOL_ACTIONS, HOOK_ACTIONS, SEQUENCE_ACTIONS, REFLEX_ACTIONS,
} from %(schema)s;
import { readFileSync } from 'node:fs';

const modes = JSON.parse(readFileSync(%(modes)s, 'utf8'));
const lists = {
  gesture: null,  // a gesture takes anything that is not appOnly
  pool: POOL_ACTIONS,
  hook: HOOK_ACTIONS,
  sequence: SEQUENCE_ACTIONS,
  reflex: REFLEX_ACTIONS,
};
const out = { appOnly: [], offered: {} };
for (const [type, descriptor] of Object.entries(ACTION_BY_TYPE)) {
  if (descriptor.appOnly) out.appOnly.push(type);
}
for (const [where, allowed] of Object.entries(lists)) {
  out.offered[where] = contributedActions(modes, allowed);
}
console.log(JSON.stringify(out));
"""


def _contributed(tmp_path) -> dict:
    """What every binding surface would offer, for the config in `_world()`.

    The harness is written into `tmp_path` as an `.mjs` and given schema.js by
    absolute `file://` URL - a relative import out of a temp directory resolves
    against the wrong root on Windows, and a `.js` copy would be parsed as
    ambiguous rather than as ES (CLAUDE.md).
    """
    modes_path = tmp_path / "modes.json"
    modes_path.write_text(json.dumps(_world()["modes"]), encoding="utf-8")
    harness = tmp_path / "harness.mjs"
    harness.write_text(
        _HARNESS % {
            "schema": json.dumps(SCHEMA_JS_PATH.as_uri()),
            "modes": json.dumps(str(modes_path)),
        },
        encoding="utf-8",
    )
    # `encoding` spelled out, not left to `text=True`: node writes UTF-8 and
    # Windows decodes a pipe as cp1252 by default, so a label carrying a curly
    # quote - which several of these do - comes back as a UnicodeDecodeError in
    # a reader thread and an empty stdout here.
    result = subprocess.run(
        [node, str(harness)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=ROOT,
    )
    assert result.returncode == 0, f"harness failed:\n{result.stdout}\n{result.stderr}"
    return json.loads(result.stdout)


@needs_node
def test_every_template_that_declares_shortcuts_has_one_in_this_config(tmp_path):
    """The guard on everything below: a sweep over an empty list passes.

    Two halves, because either alone can be silently empty - the descriptors
    could stop being declared, or `_world()` could stop instantiating the
    templates that declare them.
    """
    region = SCHEMA_JS[SCHEMA_JS.index("export const TEMPLATES = ["):
                       SCHEMA_JS.index("export const TEMPLATE_BY_TYPE")]
    declaring = len(re.findall(r"\n\s*actions: \(mode\) =>", region))
    assert declaring >= 4, (
        "118b's claim is that this generalises, and the proof of it is more "
        "than one template declaring shortcuts"
    )
    offered = _contributed(tmp_path)["offered"]
    apps = {row["app"] for rows in offered.values() for row in rows}
    # Named rather than counted: a template that stops contributing should fail
    # here loudly instead of shrinking a number nobody reads.
    assert apps == {"Water", "Smokes", "Mile", "Wake", "Apps", "Status", "DAW"}


@needs_node
def test_a_contributed_shortcut_is_an_action_the_real_parser_accepts(tmp_path):
    """Every declared body, bound to a gesture, through `parse_with_details`.

    This is the test the feature actually needs. A shortcut is only worth
    offering if what it drops into the binding survives a Save - and the shapes
    it drops (`set_value`'s slot name, `readout`'s two colours, `enter_mode`'s
    target) are exactly the ones a hand-written table gets subtly wrong.
    """
    every = _contributed(tmp_path)["offered"]
    problems = []
    for where, rows in every.items():
        for row in rows:
            raw = _world()
            # `set_position` is answered by a running app, so it is bound to a
            # reaction rather than to a gesture - which is also the only place
            # the editor offers it.
            if row["body"]["action"] == "set_position":
                raw["reflexes"] = [{
                    "name": "from-the-daw", "then": row["body"],
                    "while": row["app"],
                }]
            else:
                raw["modes"][0]["triple_tap"] = row["body"]
            _, warnings = parse_with_details(raw)
            for warning in warnings:
                problems.append(f"{where}/{row['app']}·{row['label']}: {warning}")
    assert not problems, "\n".join(problems)


@needs_node
def test_a_shortcut_is_offered_exactly_where_its_action_already_is(tmp_path):
    """No allow-list is widened, and none is narrowed either.

    The whole design rests on this: a contributed action is a *pre-filled
    instance*, so the answer to "may this appear here" is already written down
    in `POOL_ACTIONS` / `HOOK_ACTIONS` / `SEQUENCE_ACTIONS` / `REFLEX_ACTIONS`
    and must not be answered a second time.
    """
    result = _contributed(tmp_path)
    lists = {
        "pool": POOL_ACTIONS,
        "hook": HOOK_ACTIONS,
        "sequence": SEQUENCE_ACTIONS,
        "reflex": REFLEX_ACTIONS,
    }
    for where, allowed in lists.items():
        # Checked against the **Python** allow-list rather than the JavaScript
        # one the filter itself used, which would be a tautology. The two are
        # pinned to each other next door in test_schema_mirror.py, so a wire
        # name that appears here and not there fails in one place or the other.
        names = {_wire_kind(cls) for cls in allowed}
        kinds = {row["body"]["action"] for row in result["offered"][where]}
        assert kinds <= names, f"{where} offers {kinds - names}"
    # A gesture is answered at the ambient layer, where no app is running to
    # have a position - so the one `appOnly` action must never reach one, no
    # matter how many apps declare positions.
    gestures = {row["body"]["action"] for row in result["offered"]["gesture"]}
    assert gestures.isdisjoint(result["appOnly"])
    # And the reverse, or this test would pass on a mechanism that offered
    # nothing anywhere: the positions *are* reachable, from a reaction.
    reflex = {row["body"]["action"] for row in result["offered"]["reflex"]}
    assert "set_position" in reflex


@needs_node
def test_a_tallys_count_up_follows_where_that_tally_keeps_its_number(tmp_path):
    """The one place a shortcut's body depends on how its app is configured,
    and the reason `actions` is a function of the mode.

    A running total lives in the document, so `set_value` moves it; a tally
    that starts again each day *is* its rows, so a row is what adds to it.
    Getting this backwards would produce a shortcut that appeared to work and
    moved a number nobody was looking at.
    """
    rows = {
        (row["app"], row["id"]): row["body"]
        for row in _contributed(tmp_path)["offered"]["gesture"]
    }
    assert rows[("Water", "counter:count_up")]["action"] == "log"
    assert rows[("Smokes", "counter:count_up")] == {
        "action": "set_value", "app": "Smokes", "slot": "count",
        "op": "add", "value": 1,
    }
    # Parsed, not just shaped - the pair the editor writes and the pair the
    # parser builds have to be the same objects.
    raw = _world()
    raw["modes"][0]["triple_tap"] = rows[("Water", "counter:count_up")]
    raw["modes"][0]["tap_4"] = rows[("Smokes", "counter:count_up")]
    config = parse_config(raw)
    home = config.modes[0].behavior
    assert home.actions["triple_tap"] == LogAction(event="water")
    assert home.actions["tap_4"] == SetValueAction(
        app="Smokes", slot="count", op="add", value=1,
    )


# --- the Tally's own surface (118c) ----------------------------------------


def _tally(**over) -> dict:
    """A config whose only takeover is a Tally reached by a double tap."""
    mode = {
        "name": "Water", "template": "counter",
        "activation": {"type": "manual"}, "event": "water",
    }
    mode.update(over)
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "modes": [
            {
                "name": "Home", "template": "actions",
                "activation": {"type": "always"},
                "double_tap": {"action": "enter_mode", "target": "Water"},
            },
            mode,
        ],
    }


def test_a_tally_written_before_steps_existed_parses_as_the_pair_it_always_was():
    """The compatibility claim, made against the parser rather than assumed.

    None of the new keys is present, and the answer has to be the two gestures
    `run_counter`'s docstring named before any of this: short press and double
    tap, one each, and no readout on a timer.
    """
    config = parse_config(_tally())
    behavior = config.modes[1].behavior
    assert behavior.steps == {"short_press": 1, "double_tap": 1}
    assert behavior.show_every_s == 0.0
    assert behavior == CounterBehavior(event="water")


def test_an_old_tally_costs_the_button_nothing_it_did_not_cost_before():
    """`bound_triggers` reads any trigger-keyed dict on a behaviour, so the new
    `steps` field is now one of the things that decides how far the device
    counts - and counting further is what costs every shorter tap its instant
    response. An untouched tally must not spend one.
    """
    plain = parse_config(_tally())
    assert bound_triggers(plain.modes) >= {"short_press", "double_tap"}
    assert not bound_triggers(plain.modes) & {"triple_tap", "tap_4", "tap_5"}
    # Filling one in is what buys it, and only then.
    rich = parse_config(_tally(tap_5=10))
    assert "tap_5" in bound_triggers(rich.modes)


def test_a_step_of_zero_is_a_gesture_that_does_nothing():
    """Zero is how the editor says "unbound" - its number widget has no empty
    state - so it must not reach the map, or the button would count to five for
    a slot nobody filled in."""
    config = parse_config(_tally(triple_tap=0, tap_4=0, tap_5=0))
    assert config.modes[1].behavior.steps == {"short_press": 1, "double_tap": 1}
    assert not bound_triggers(config.modes) & {"triple_tap", "tap_4", "tap_5"}


def test_long_press_cannot_be_bound_away_from_leaving():
    """The escape gesture is not a thing a config gets to spend (CLAUDE.md).
    Refused by the parser rather than left to the editor, which is what makes
    it a constraint instead of a suggestion - a hand-edited file walks straight
    past a UI rule."""
    config, warnings = parse_with_details(_tally(long_press=5))
    assert "long_press" not in config.modes[1].behavior.steps
    assert any("long_press" in str(warning) for warning in warnings)


def test_the_tally_offers_a_step_for_every_gesture_but_the_long_press():
    """The mirror: schema.js's five step fields against the wire's six gestures.

    Written out in the editor rather than derived from GESTURES (the field
    extractor next door in test_schema_mirror.py cannot evaluate a `.map()`),
    so the derivation's guarantee lives here as an assertion instead - which is
    CLAUDE.md's rule about mirrored tables applied to a table of five.
    """
    block = SCHEMA_JS[SCHEMA_JS.index("type: 'counter',"):]
    block = block[:block.index("readout: {")]
    offered = [
        key for key in re.findall(r"\{ key: '(\w+)', label: '[^']*counts'", block)
    ]
    assert offered == [t for t in TRIGGER_TYPES if t != "long_press"]


def test_a_tally_round_trips_through_the_editor():
    """Parse, serialise, parse - the loop a Save makes. Every slot is written,
    zeroes included, because a key that vanished on Save reads as the field
    having been ignored."""
    config = parse_config(_tally(double_tap=5, tap_5=-1, show_every_s=30))
    written = _mode_to_dict(config.modes[1])
    assert written["triple_tap"] == 0  # a slot nobody filled, still written
    assert "long_press" not in written
    again, warnings = parse_with_details({"modes": [
        _mode_to_dict(mode) for mode in config.modes
    ]})
    assert not warnings
    assert again.modes[1].behavior == config.modes[1].behavior


# --- driving the surface ---------------------------------------------------
# Parsing is half the claim; the other half is that the loop does what the map
# says. Driven through main.run against a MockDevice, in the style of
# test_main_takeover.py - see that file's module docstring on why presses are
# fed one at a time.


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def _press(device: MockDevice, *triggers: TriggerType):
    for trigger in triggers:
        device.press(trigger)
        await _drain(device.events)
        await asyncio.sleep(0.1)


async def _run_tally(tmp_path, monkeypatch, script, **over):
    """Open the Tally, play `script`, and answer with the store and the
    messages the status line was given."""
    db_path = tmp_path / "e.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(_tally(**over), database_path=str(db_path))),
        encoding="utf-8",
    )
    messages: list[str] = []

    class _RecordingStatus(main.DeviceStatus):
        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == "last_message":
                messages.append(value)

    monkeypatch.setattr(main, "DeviceStatus", _RecordingStatus)
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        await _press(device, TriggerType.DOUBLE_TAP)  # enter_mode -> Water
        await _press(device, *script)
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    return db_path, messages


async def test_an_old_tally_still_counts_one_per_press(tmp_path, monkeypatch):
    """The behaviour half of the compatibility claim: short press and double
    tap each add one, long press leaves, and every press is a row."""
    db_path, messages = await _run_tally(
        tmp_path, monkeypatch,
        [TriggerType.SHORT_PRESS, TriggerType.DOUBLE_TAP, TriggerType.LONG_PRESS],
    )
    assert "water: 1" in messages
    assert "water: 2" in messages
    store = EventStore(str(db_path))
    try:
        assert store.count_today("water") == 2
    finally:
        store.close()


async def test_each_gesture_counts_by_its_own_step(tmp_path, monkeypatch):
    """The feature: five presses, five amounts. A triple tap worth five and a
    four-tap worth minus one is a tally you can correct without leaving it."""
    db_path, messages = await _run_tally(
        tmp_path, monkeypatch,
        [TriggerType.TRIPLE_TAP, TriggerType.TAP_4, TriggerType.LONG_PRESS],
        triple_tap=5, tap_4=-1,
    )
    assert "water: 5" in messages
    assert "water: 4" in messages
    store = EventStore(str(db_path))
    try:
        # One row per press either way - the amount rides on the row rather
        # than multiplying it, so history and streaks are untouched.
        assert store.count_today("water") == 2
    finally:
        store.close()


async def test_a_gesture_with_no_step_does_nothing(tmp_path, monkeypatch):
    """An unbound gesture is unbound, here as everywhere else - it must not
    fall through to the +1 the loop used to give every non-long press."""
    db_path, messages = await _run_tally(
        tmp_path, monkeypatch,
        [TriggerType.TAP_5, TriggerType.SHORT_PRESS, TriggerType.LONG_PRESS],
        tap_5=0,
    )
    assert "water: 1" in messages
    assert "water: 2" not in messages
    store = EventStore(str(db_path))
    try:
        assert store.count_today("water") == 1
    finally:
        store.close()


class _RecordingDevice(MockDevice):
    """A MockDevice that keeps every push rather than only the last one.

    The periodic readout is a *sequence*, so what proves it ran is the frames
    that went past - and `MockDevice` holds current state, which is the right
    shape for every other test and the wrong one for this.
    """

    def __init__(self) -> None:
        super().__init__()
        self.pushes: list[tuple] = []

    def set_led(self, state, effect=None) -> None:
        super().set_led(state, effect)
        self.pushes.append((state, getattr(effect, "color", None)))


async def test_the_tally_says_its_number_on_a_timer_and_then_gives_the_light_back(
    tmp_path, monkeypatch,
):
    """The app's own surface (TODO 118c): nobody presses anything and the count
    still shows, in the colours this tally was given.

    The second half is the one worth pinning. A one-shot sequence lands on the
    state's *palette* entry when it finishes (`_drive_sequence`), not on
    whatever the app names for it - so a tally that flashed its count and never
    re-asserted COUNTING would quietly lose its own look after the first
    readout and never get it back.
    """
    db_path = tmp_path / "e.db"
    seed = EventStore(str(db_path))
    seed.log_event("water")  # one press today: one quick pulse, ~0.36s of it
    seed.close()

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(
            _tally(show_every_s=0.3, units_color="#00ff00"),
            database_path=str(db_path),
        )),
        encoding="utf-8",
    )
    device = _RecordingDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        await _press(device, TriggerType.DOUBLE_TAP)  # enter_mode -> Water
        device.pushes.clear()
        await asyncio.sleep(1.0)  # long enough for a tick, the digits, and rest
        pushed = list(device.pushes)
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    states = {state for state, _ in pushed}
    assert states == {LEDState.COUNTING}, "the readout borrows COUNTING, never a state of its own"
    assert any(color == "#00ff00" for _, color in pushed), (
        "the units digit never showed in the colour this tally was given"
    )
    # Back on the app's own look afterwards - a bare COUNTING with no effect is
    # what "the palette or whatever this mode names" is spelled as.
    assert pushed[-1] == (LEDState.COUNTING, None)


async def test_the_running_total_moves_by_the_step_and_survives_the_session(
    tmp_path, monkeypatch,
):
    """A step other than 1 only means what it says past midnight in a *durable*
    tally, because `count_today` counts rows and always will. So the document
    is where the arithmetic has to land."""
    db_path, messages = await _run_tally(
        tmp_path, monkeypatch,
        [TriggerType.DOUBLE_TAP, TriggerType.DOUBLE_TAP, TriggerType.LONG_PRESS],
        durable=True, double_tap=5,
    )
    assert "water: 10" in messages
    from aibutton.documents import DocumentStore
    docs = DocumentStore(str(db_path))
    try:
        assert docs.get("Water", "count", 0) == 10
    finally:
        docs.close()
