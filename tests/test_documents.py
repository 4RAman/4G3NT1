"""App documents: the durable named values an app owns (TODO 34, ROADMAP D9).

The event log can only append, so "what is it now" was a recount and "set this
to 3" was not expressible at all. What is worth testing is therefore not
storage - sqlite works - but the three decisions around it: what a slot may
hold, that the log stays separate from the number, and that an action naming
an app or a slot nobody has is reported rather than guessed at.
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

from aibutton import main
from aibutton.actions import execute
from aibutton.config import (
    DOC_SLOTS,
    SET_VALUE_OPS,
    CounterBehavior,
    SetValueAction,
    as_dict,
    parse_config,
    parse_with_warnings,
)
from aibutton.device import MockDevice, TriggerType
from aibutton.documents import MAX_SLOTS, DocumentStore
from aibutton.store import EventStore

SCHEMA_JS = (Path(__file__).resolve().parents[1]
             / "aibutton/web/static/schema.js").read_text(encoding="utf-8")


@pytest.fixture
def docs():
    store = DocumentStore(":memory:")
    yield store
    store.close()


# --- what a slot may hold --------------------------------------------------


def test_a_slot_reads_as_its_default_until_something_writes_it(docs):
    """What makes a document readable like a variable: no first-run branch,
    anywhere, ever."""
    assert docs.get("Habit", "count", 0.0) == 0.0
    assert docs.get("Habit", "count", 7) == 7


def test_adding_to_a_slot_that_has_never_been_written_starts_from_the_default(docs):
    assert docs.add("Habit", "count", 1) == 1.0
    assert docs.add("Habit", "count", 1) == 2.0


def test_a_flag_comes_back_a_flag(docs):
    """sqlite stores a bool as 1, so the declared default is the only thing
    that still knows which it was."""
    docs.set("Habit", "armed", True)
    assert docs.get("Habit", "armed", False) is True
    assert docs.get("Habit", "armed", 0.0) == 1


def test_anything_that_is_not_a_scalar_is_refused_rather_than_coerced(docs):
    """A dict silently stored as its repr is a value that reads back wrong
    forever - the same call summary.clean makes about the same three types."""
    assert docs.set("Habit", "count", {"nested": 1}) is None
    assert docs.set("Habit", "count", [1, 2]) is None
    assert docs.all("Habit") == {}


def test_text_cannot_be_added_to(docs):
    docs.set("Habit", "label", "cigs")
    assert docs.add("Habit", "label", 1) is None
    assert docs.get("Habit", "label", "") == "cigs"


def test_a_document_is_bounded_and_says_so(docs):
    """Bounded by construction is the line this whole design draws. The
    declared slots are the real bound; this is the backstop for a declaration
    that is wrong, and it must refuse rather than grow."""
    for n in range(MAX_SLOTS):
        assert docs.set("Habit", f"slot{n}", n) is not None
    assert docs.set("Habit", "one_too_many", 1) is None
    # ...and an existing slot is still writable, because it takes no new room.
    assert docs.set("Habit", "slot0", 99) == 99


def test_one_app_cannot_see_another_s_document(docs):
    docs.set("Habit", "count", 3)
    assert docs.get("Other", "count", 0.0) == 0.0
    assert docs.everything() == {"Habit": {"count": 3}}


def test_clearing_forgets_rather_than_writing_the_default_back(docs):
    """"Never set" and "set back to its default" stay the same state - there
    is nothing in this design that can tell them apart, and pretending
    otherwise would invent a distinction the device cannot carry."""
    docs.set("Habit", "count", 5)
    assert docs.clear("Habit", "count") == 1
    assert docs.all("Habit") == {}
    assert docs.get("Habit", "count", 0.0) == 0.0


def test_an_unwritable_database_degrades_to_memory(tmp_path):
    """The same trade store.py makes: a button that will not press because its
    notebook is unwritable is the wrong answer."""
    blocked = tmp_path / "nope"
    blocked.write_text("not a directory", encoding="utf-8")
    store = DocumentStore(str(blocked / "docs.db"))
    try:
        assert store.degraded
        assert store.add("Habit", "count", 1) == 1.0
    finally:
        store.close()


# --- the action ------------------------------------------------------------


def _config(**over) -> dict:
    body = {
        "modes": [
            {"name": "Home", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "set_value", "app": "Habit", "slot": "count"}},
            {"name": "Habit", "template": "counter", "activation": {"type": "manual"},
             "event": "cigs", "durable": True},
        ],
    }
    body.update(over)
    return body


def test_the_action_parses_with_its_defaults():
    config = parse_config(_config())
    assert config.modes[0].behavior.actions["short_press"] == SetValueAction(
        app="Habit", slot="count", op="add", value=1,
    )


def test_it_round_trips_through_the_editor():
    config = parse_config(_config())
    written = as_dict(config)["modes"][0]["short_press"]
    assert written == {
        "action": "set_value", "app": "Habit", "slot": "count",
        "op": "add", "value": 1,
    }
    assert parse_config(as_dict(config)).modes[0].behavior.actions == \
        config.modes[0].behavior.actions


@pytest.mark.parametrize("bad,why", [
    ({"action": "set_value", "slot": "count"}, "app"),
    ({"action": "set_value", "app": "Habit"}, "slot"),
    ({"action": "set_value", "app": "Habit", "slot": "count", "op": "multiply"}, "op"),
    ({"action": "set_value", "app": "Habit", "slot": "count", "value": {"a": 1}}, "value"),
])
def test_a_broken_set_value_is_dropped_with_a_reason(bad, why):
    config, warnings = parse_with_warnings(_config(modes=[
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "short_press": bad, "double_tap": {"action": "log", "event": "ok"}},
    ]))
    assert "short_press" not in config.modes[0].behavior.actions
    assert any(why in w for w in warnings)
    # ...and the rest of the mode survives, which is the fail-soft floor.
    assert "double_tap" in config.modes[0].behavior.actions


def test_adding_a_word_to_a_number_is_refused_at_parse_time():
    """Caught where the editor can say so, not when somebody presses the
    button - the same call the osc branch makes about a malformed address."""
    _, warnings = parse_with_warnings(_config(modes=[
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "set_value", "app": "H", "slot": "c",
                         "op": "add", "value": "five"}},
    ]))
    assert any("cannot add" in w for w in warnings)


def test_writing_to_an_app_nobody_has_is_reported_and_kept():
    """The dangling-reference rule: repointing it at some other app would be
    worse, and dropping it loses the number's owner."""
    config, warnings = parse_with_warnings(_config(modes=[
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "set_value", "app": "Ghost", "slot": "count"}},
    ]))
    assert config.modes[0].behavior.actions["short_press"].app == "Ghost"
    assert any("Ghost" in w for w in warnings)


def test_writing_a_slot_that_template_does_not_keep_is_reported():
    config, warnings = parse_with_warnings(_config(modes=[
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "set_value", "app": "Watch", "slot": "count"}},
        {"name": "Watch", "template": "stopwatch", "activation": {"type": "manual"},
         "log_as": "watch"},
    ]))
    assert any("no values of its own" in w for w in warnings)


async def test_executing_it_writes_the_document(docs):
    events = EventStore(":memory:")
    try:
        result = await execute(
            SetValueAction("Habit", "count", "add", 2),
            trigger="short_press", mode_name="Home", store=events, documents=docs,
        )
        assert result.ok
        assert docs.get("Habit", "count", 0.0) == 2.0
        # The message names what changed - a gesture that does nothing visible
        # still has to say what it did.
        assert "Habit.count" in result.message
    finally:
        events.close()


async def test_set_writes_an_absolute_and_add_writes_a_delta(docs):
    events = EventStore(":memory:")
    try:
        for action in (
            SetValueAction("Habit", "count", "add", 5),
            SetValueAction("Habit", "count", "add", 5),
            SetValueAction("Habit", "count", "set", 0),
        ):
            await execute(action, trigger="t", mode_name="Home",
                          store=events, documents=docs)
        assert docs.get("Habit", "count", 0.0) == 0
    finally:
        events.close()


async def test_with_nowhere_to_keep_values_it_fails_clearly(docs):
    """Silently doing nothing is the failure a counter would take weeks to
    notice."""
    events = EventStore(":memory:")
    try:
        result = await execute(
            SetValueAction("Habit", "count", "add", 1),
            trigger="t", mode_name="Home", store=events,
        )
        assert not result.ok and "app values" in result.message
    finally:
        events.close()


# --- the counter, both ways ------------------------------------------------


async def _run(tmp_path, modes, presses):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "sounds_enabled": False, "web_enabled": False,
        "database_path": str(tmp_path / "events.db"), "modes": modes,
    }), encoding="utf-8")
    device = MockDevice()
    args = main._parse_args(["--no-web", "--no-lock", "--config", str(cfg)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)
    try:
        for trigger in presses:
            device.press(trigger)
            await asyncio.sleep(0.12)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return DocumentStore(str(tmp_path / "events.db"))


def _counter_modes(durable: bool) -> list[dict]:
    return [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "Habit"}},
        {"name": "Habit", "template": "counter", "activation": {"type": "manual"},
         "event": "cigs", "durable": durable},
    ]


async def test_a_durable_counter_keeps_its_number_in_its_document(tmp_path):
    docs = await _run(tmp_path, _counter_modes(True), [
        TriggerType.LONG_PRESS,   # enter
        TriggerType.SHORT_PRESS,
        TriggerType.SHORT_PRESS,
    ])
    try:
        assert docs.get("Habit", "count", 0.0) == 2.0
    finally:
        docs.close()


async def test_an_ordinary_counter_writes_no_document(tmp_path):
    """Off is the template as it always was - today's rows, recounted - and it
    must cost nothing at all."""
    docs = await _run(tmp_path, _counter_modes(False), [
        TriggerType.LONG_PRESS, TriggerType.SHORT_PRESS,
    ])
    try:
        assert docs.everything() == {}
    finally:
        docs.close()


async def test_a_durable_counter_still_writes_every_row(tmp_path):
    """History and current value are different jobs, so a durable counter does
    both - otherwise switching the flag would silently empty the Events page
    for that app."""
    docs = await _run(tmp_path, _counter_modes(True), [
        TriggerType.LONG_PRESS, TriggerType.SHORT_PRESS, TriggerType.SHORT_PRESS,
    ])
    docs.close()
    events = EventStore(str(tmp_path / "events.db"))
    try:
        rows = [n for (_t, _k, n, _d, _m, _v) in events.recent(50) if n == "cigs"]
        assert len(rows) == 2
    finally:
        events.close()


async def test_a_gesture_can_add_to_a_counter_without_entering_it(tmp_path):
    """TODO 15's "Smoking +1", and the whole reason a document lives outside
    every app's run loop."""
    modes = _counter_modes(True)
    modes[0]["short_press"] = {
        "action": "set_value", "app": "Habit", "slot": "count", "value": 1,
    }
    docs = await _run(tmp_path, modes, [
        TriggerType.SHORT_PRESS, TriggerType.SHORT_PRESS, TriggerType.SHORT_PRESS,
    ])
    try:
        assert docs.get("Habit", "count", 0.0) == 3.0
    finally:
        docs.close()


async def test_the_counter_opens_on_what_a_gesture_left_there(tmp_path):
    """The two halves meeting: press it up from Home, then open the app and
    the number is the same one. Under `count_today` that agreed because they
    were the same rows; under a document it agrees because they are the same
    slot."""
    modes = _counter_modes(True)
    modes[0]["short_press"] = {
        "action": "set_value", "app": "Habit", "slot": "count", "value": 4,
    }
    docs = await _run(tmp_path, modes, [
        TriggerType.SHORT_PRESS,   # +4 from the ambient layer
        TriggerType.LONG_PRESS,    # enter the counter
        TriggerType.SHORT_PRESS,   # +1 inside it
    ])
    try:
        assert docs.get("Habit", "count", 0.0) == 5.0
    finally:
        docs.close()


# --- the tables are mirrored, not trusted ----------------------------------


def _js_doc_slots() -> dict[str, list[str]]:
    """`{template: [slot name, ...]}` as schema.js declares it."""
    out: dict[str, list[str]] = {}
    for match in re.finditer(r"type: '(\w+)',", SCHEMA_JS):
        # The descriptor's own block, up to the next template's `type:`.
        rest = SCHEMA_JS[match.end():]
        block = rest[:rest.index("type: '")] if "type: '" in rest else rest
        # `docSlots` is declared above `type`, so look behind as well - the
        # comment rule that keeps it adjacent is what makes this readable.
        before = SCHEMA_JS[:match.start()]
        window = before[-600:] + block[:600]
        found = re.search(r"docSlots: \[(.*?)\]", window, re.S)
        if found:
            out[match.group(1)] = re.findall(r"name: '([^']+)'", found.group(1))
    return out


def test_the_declared_slots_match_on_both_sides():
    """One template's document is declared twice - config.py for the parser,
    schema.js for the editor - and a slot the editor offers that the parser
    does not know is a binding that saves and then writes nothing."""
    js = _js_doc_slots()
    python = {
        template: [slot.name for slot in slots]
        for template, slots in DOC_SLOTS.items() if slots
    }
    assert js == python


def test_the_operators_match_on_both_sides():
    match = re.search(r"export const SET_VALUE_OPS = \[(.*?)\];", SCHEMA_JS, re.S)
    assert match, "SET_VALUE_OPS is not a flat array literal any more"
    assert re.findall(r"'([^']+)'", match.group(1)) == list(SET_VALUE_OPS)


def test_the_editor_offers_set_value_as_a_sequence_step():
    """It is fire-and-forget - no loop changed, no light owned - so it belongs
    in the same set as a log row and a MIDI note."""
    match = re.search(r"export const SEQUENCE_ACTIONS = \[(.*?)\];", SCHEMA_JS, re.S)
    assert match and "set_value" in match.group(1)


def test_the_counter_declares_the_slot_it_actually_writes():
    """`run_counter` writes "count" unguarded, so the declaration is what the
    parser's warning is checked against - and a rename on one side alone would
    make every binding warn while working perfectly."""
    assert [slot.name for slot in DOC_SLOTS["counter"]] == ["count"]
    assert CounterBehavior().durable is False
