"""`SequenceAction` - a flat list of actions with delays (TODO 33).

The item's own words: **bounded by construction - no loops, no conditionals,
no nesting**, or it is a language the on-device runtime can never run. So most
of what is worth testing here is what the parser *refuses*, and the two edges
the item said to decide before writing any code: the limits live in the parser
rather than in the editor, and a sequence holds the button while it runs.

The worked example throughout is the one that made this item exist: Mackie
Control has no return-to-zero, so "stop and rewind" is Stop, a beat, Stop.
"""

import asyncio
import json
import time

import pytest

import aibutton.main as main
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

import aibutton.config as cfg
from aibutton.actions import execute
from aibutton.config import (
    LogAction,
    MidiAction,
    ReadoutAction,
    NamedAction,
    SequenceAction,
    SequenceStep,
    as_dict,
    parse_config,
    parse_with_warnings,
    resolve_action,
)

FLOOR = {"name": "Base", "template": "actions", "activation": {"type": "always"}}


def _cfg(binding, **over):
    """A config whose short press is `binding`, with an ambient floor so
    nothing here trips the seeded-Home warning."""
    return {"modes": [{**FLOOR, "short_press": binding}], **over}


def _bound(config):
    return config.modes[0].behavior.actions["short_press"]


STOP = {"action": "midi", "port": "4G3NT", "channel": 1,
        "kind": "note_on", "number": 93, "value": 127}

READOUT = {"action": "readout", "event": "Habit"}


# --- parsing ---------------------------------------------------------------

def test_a_sequence_is_a_list_of_actions_with_waits():
    config, warnings = parse_with_warnings(_cfg({
        "action": "sequence",
        "steps": [STOP, {**STOP, "wait_s": 0.15}],
    }))
    action = _bound(config)
    assert isinstance(action, SequenceAction)
    assert [step.wait_s for step in action.steps] == [0.0, 0.15]
    assert all(isinstance(step.action, MidiAction) for step in action.steps)
    assert not warnings


def test_a_step_may_name_a_pooled_action():
    config = parse_config(_cfg(
        {"action": "sequence", "steps": [STOP, "rewind"]},
        actions={"rewind": {"action": "midi", "port": "", "channel": 1,
                            "kind": "note_on", "number": 91, "value": 127}},
    ))
    assert _bound(config).steps[1].action == NamedAction(name="rewind")


def test_a_sequence_does_not_nest():
    """The one refusal that keeps this out of language territory."""
    config, warnings = parse_with_warnings(_cfg({
        "action": "sequence",
        "steps": [STOP, {"action": "sequence", "steps": [STOP]}],
    }))
    assert len(_bound(config).steps) == 1
    assert any("sequences do not nest" in w for w in warnings), warnings


@pytest.mark.parametrize("step", [
    {"action": "enter_mode", "target": "Focus"},
    {"action": "readout", "event": "coffee"},
    {"action": "standby"},
    {"action": "set_position", "name": "Recording"},
])
def test_a_step_that_changes_what_the_loop_does_next_is_refused(step):
    """A step does its job and hands the button back. The four that do not are
    the four the run loop keeps for itself."""
    config, warnings = parse_with_warnings(_cfg({
        "action": "sequence", "steps": [STOP, step],
    }))
    assert len(_bound(config).steps) == 1
    assert warnings


def test_a_sequence_with_no_usable_steps_is_dropped_entirely():
    # A second, valid gesture so the *mode* survives its binding being
    # dropped - a mode with no usable gesture at all is skipped, and then this
    # would be asserting against the seeded default config instead.
    config, warnings = parse_with_warnings({"modes": [{
        **FLOOR,
        "short_press": {"action": "sequence", "steps": [{"action": "nonsense"}]},
        "tap_4": {"action": "log", "event": "still here"},
    }]})
    assert "short_press" not in config.modes[0].behavior.actions
    assert "tap_4" in config.modes[0].behavior.actions
    assert warnings


@pytest.mark.parametrize("steps", ["not a list", [], None])
def test_a_sequence_needs_steps(steps):
    config, warnings = parse_with_warnings({"modes": [{
        **FLOOR,
        "short_press": {"action": "sequence", "steps": steps},
        "tap_4": {"action": "log", "event": "still here"},
    }]})
    assert "short_press" not in config.modes[0].behavior.actions
    assert warnings


def test_the_step_count_is_capped_by_the_parser_not_the_editor():
    """A config is a file people hand-edit; a bound only the UI knows is not a
    bound. Over the limit the list is truncated, not rejected - what was
    written up to that point still does what it says."""
    config, warnings = parse_with_warnings(_cfg({
        "action": "sequence", "steps": [STOP] * (cfg.MAX_SEQUENCE_STEPS + 3),
    }))
    assert len(_bound(config).steps) == cfg.MAX_SEQUENCE_STEPS
    assert any("more than" in w for w in warnings), warnings


def test_the_total_duration_is_capped_too():
    """Eight steps is not a bound on time - eight steps each waiting a minute
    would hold the button for eight minutes."""
    config, warnings = parse_with_warnings(_cfg({
        "action": "sequence",
        "steps": [{**STOP, "wait_s": 6}, {**STOP, "wait_s": 6}, STOP],
    }))
    action = _bound(config)
    assert sum(step.wait_s for step in action.steps) <= cfg.MAX_SEQUENCE_S
    assert len(action.steps) < 3
    assert warnings


@pytest.mark.parametrize("wait", [-1, "soon", True])
def test_an_unusable_wait_falls_back_to_no_wait(wait):
    config, warnings = parse_with_warnings(_cfg({
        "action": "sequence", "steps": [{**STOP, "wait_s": wait}],
    }))
    assert _bound(config).steps[0].wait_s == 0.0
    assert warnings


def test_a_sequence_round_trips():
    raw = _cfg({"action": "sequence", "steps": [STOP, {**STOP, "wait_s": 0.15}, "rewind"]},
               actions={"rewind": {"action": "log", "event": "rewound"}})
    once = parse_config(raw)
    written = as_dict(once)
    assert written["modes"][0]["short_press"] == raw["modes"][0]["short_press"]
    assert _bound(parse_config(written)) == _bound(once)


# --- resolving -------------------------------------------------------------

def test_a_named_step_is_resolved_where_every_other_binding_is():
    """Through `resolve_action`, which is why every dispatch site got
    sequences without growing a resolver of its own."""
    config = parse_config(_cfg(
        {"action": "sequence", "steps": ["rewind"]},
        actions={"rewind": {"action": "log", "event": "rewound"}},
    ))
    resolved = resolve_action(config, _bound(config))
    assert resolved.steps[0].action == LogAction(event="rewound")


def test_a_dangling_step_is_skipped_and_the_rest_still_run():
    config = parse_config(_cfg({"action": "sequence", "steps": [STOP, "ghost"]}))
    resolved = resolve_action(config, _bound(config))
    assert len(resolved.steps) == 1
    assert isinstance(resolved.steps[0].action, MidiAction)


def test_a_step_naming_a_pooled_sequence_is_the_nesting_the_parser_cannot_see():
    """The parser refuses an inline sequence inside a sequence; this is the
    same rule for the shape it cannot check, and it is enforced at the one
    place a name becomes an action."""
    config = parse_config(_cfg(
        {"action": "sequence", "steps": [STOP, "chain"]},
        actions={"chain": {"action": "sequence", "steps": [STOP]}},
    ))
    resolved = resolve_action(config, _bound(config))
    assert len(resolved.steps) == 1


def test_a_step_naming_a_loop_changing_action_is_skipped_not_run():
    """The other half of what a named step can hide. `readout`, `standby` and
    `enter_mode` are answered by `main.handle` *instead of* `execute()`, so
    one reaching a sequence used to fail the whole press with "unknown action
    type" - the count went in, the light went red. Same call the nesting case
    gets: drop the step, run the rest, say why."""
    for entry in ({"action": "standby"}, {"action": "enter_mode", "target": "Water"}):
        config = parse_config(_cfg(
            {"action": "sequence", "steps": [STOP, "after"]},
            actions={"after": entry},
        ))
        resolved = resolve_action(config, _bound(config))
        assert len(resolved.steps) == 1, entry
        assert isinstance(resolved.steps[0].action, MidiAction), entry


def test_a_readout_may_end_a_sequence_where_something_holds_the_light():
    """TODO 117: "count it, then show me the count" on one press. `tail_ok` is
    the caller saying it can render one - only `main.handle` can."""
    for last in (READOUT, "show"):
        config = parse_config(_cfg(
            {"action": "sequence", "steps": [STOP, last]},
            actions={"show": READOUT},
        ))
        resolved = resolve_action(config, _bound(config), tail_ok=True)
        assert [type(s.action) for s in resolved.steps] == [MidiAction, ReadoutAction], last


def test_a_readout_is_dropped_where_nothing_can_render_it():
    """Every dispatch site but `handle` hands its actions to `execute()`,
    which has a store and no LED - so the default is off, and a hook firing
    this sequence loses the readout rather than failing the whole thing."""
    config = parse_config(_cfg({"action": "sequence", "steps": [STOP, READOUT]}))
    resolved = resolve_action(config, _bound(config))
    assert [type(s.action) for s in resolved.steps] == [MidiAction]


def test_a_readout_anywhere_but_last_is_refused_at_parse_time():
    """Nothing may follow one: the next `set_led` cancels the running sequence
    and would cut the count off mid-digit."""
    config, warnings = parse_with_warnings(
        _cfg({"action": "sequence", "steps": [READOUT, STOP]})
    )
    assert [type(s.action) for s in _bound(config).steps] == [MidiAction]
    assert any("only be the last step" in w for w in warnings), warnings


def test_a_step_naming_an_ordinary_pooled_action_still_resolves():
    """The check is a type test, not a blanket refusal of named steps."""
    config = parse_config(_cfg(
        {"action": "sequence", "steps": [STOP, "note"]},
        actions={"note": {"action": "log", "event": "Habit"}},
    ))
    resolved = resolve_action(config, _bound(config))
    assert [type(s.action) for s in resolved.steps] == [MidiAction, LogAction]


def test_a_gesture_may_name_a_pooled_sequence():
    """One level *is* allowed: what a name may not point at is another name."""
    config = parse_config(_cfg(
        "stop_stop",
        actions={"stop_stop": {"action": "sequence", "steps": [STOP, {**STOP, "wait_s": 0.05}]}},
    ))
    resolved = resolve_action(config, _bound(config))
    assert isinstance(resolved, SequenceAction)
    assert len(resolved.steps) == 2


# --- running ---------------------------------------------------------------

class _Store:
    """The two methods a LogAction touches."""

    def __init__(self):
        self.events = []

    def log_event(self, name, mode=None, value=None):
        from datetime import datetime, timezone
        self.events.append(name)
        return datetime.now(timezone.utc)

    def count_today(self, name):
        return 1

    def current_streak(self, name):
        return 1


async def _run(action, store=None):
    return await execute(
        action, trigger="short_press", mode_name="Desk", store=store or _Store(),
    )


async def test_the_steps_run_in_order_and_the_waits_are_real():
    store = _Store()
    action = SequenceAction(steps=(
        SequenceStep(action=LogAction(event="stop")),
        SequenceStep(action=LogAction(event="stop_again"), wait_s=0.1),
    ))
    started = time.perf_counter()
    result = await _run(action, store)
    assert store.events == ["stop", "stop_again"]
    assert time.perf_counter() - started >= 0.1
    assert result.ok and result.message == "Sent 2 steps"


async def test_a_failed_step_does_not_stop_the_rest():
    """A sequence is a script, not a transaction: if the webhook is down, the
    MIDI note that was going to follow it is still what was asked for."""
    store = _Store()
    action = SequenceAction(steps=(
        SequenceStep(action=cfg.WebhookAction(url="", payload={})),
        SequenceStep(action=LogAction(event="after")),
    ))
    result = await _run(action, store)
    assert store.events == ["after"]
    assert not result.ok
    assert "step 1" in result.message


async def test_one_step_reads_as_one_step():
    result = await _run(SequenceAction(steps=(SequenceStep(action=LogAction(event="a")),)))
    assert result.message == "Sent 1 step"


# --- through the run loop --------------------------------------------------

class _Recording(MockDevice):
    """A mock that keeps every push, because a readout is a *sequence* of them
    and `led_effect` only ever holds the frame showing right now."""

    def __init__(self):
        super().__init__()
        self.pushed = []

    def set_led(self, state, effect=None):
        self.pushed.append((state, effect))
        super().set_led(state, effect)


async def test_a_press_can_count_and_then_show_the_count(tmp_path, monkeypatch):
    """The whole of TODO 117 in one press, driven through `run()` because what
    it changes is what the *loop* does - there is no pure function underneath.

    The bug it closes: this exact config used to log the count and then go red,
    because `execute()` has no branch for a readout and answered "unknown
    action type". What proves it fixed is not the absence of the error but the
    count arriving on the light - one blue pulse, then two.
    """
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "sounds_enabled": False,
        "web_enabled": False,
        "database_path": str(db_path),
        "modes": [{**FLOOR, "short_press": {
            "action": "sequence",
            "steps": [{"action": "log", "event": "Habit"}, READOUT],
        }}],
    }), encoding="utf-8")
    device = _Recording()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))

    units = lambda: sum(  # noqa: E731 - the units digit's colour, counted
        1 for _state, effect in device.pushed
        if effect is not None and effect.color == ReadoutAction(event="x").units_color
    )
    try:
        await asyncio.sleep(0.4)  # let run() reach the main loop
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.8)
        assert units() == 1, device.pushed
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.8)
        # Two more, because it is the second one today - a readout that ran
        # before the log step, or ignored it, would say one again.
        assert units() == 3, device.pushed
        # And never the error the whole item is about.
        assert LEDState.ERROR not in [state for state, _effect in device.pushed]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
    finally:
        store.close()
    assert [name for (_ts, kind, name, *_rest) in rows if kind == "log"] == [
        "Habit", "Habit",
    ]
