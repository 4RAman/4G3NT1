"""`SequenceAction` - a flat list of actions with delays (TODO 33).

The item's own words: **bounded by construction - no loops, no conditionals,
no nesting**, or it is a language the on-device runtime can never run. So most
of what is worth testing here is what the parser *refuses*, and the two edges
the item said to decide before writing any code: the limits live in the parser
rather than in the editor, and a sequence holds the button while it runs.

The worked example throughout is the one that made this item exist: Mackie
Control has no return-to-zero, so "stop and rewind" is Stop, a beat, Stop.
"""

import time

import pytest

import aibutton.config as cfg
from aibutton.actions import execute
from aibutton.config import (
    LogAction,
    MidiAction,
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
