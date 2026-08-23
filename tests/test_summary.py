"""The session-summary contract, asserted rather than asked for.

TODO 32's rule is that a summary is flat, scalar and bounded, and that no app
is trusted to have honoured it - so what these test is the *gate*, with the
kinds of bad summary an app plausibly returns: a nested dict, a list of laps, a
None where a number was expected, a division nobody guarded, and one that
simply says too much. Every one of them costs its key and nothing else, because
the app has already ended by the time any of this runs.
"""

import math

import pytest

from aibutton import summary


def test_a_flat_bag_of_numbers_survives_intact():
    kept, complaints = summary.clean({"blocks": 4, "focused_s": 6000.0})
    assert kept == {"blocks": 4, "focused_s": 6000.0}
    assert complaints == ()


def test_nothing_reported_costs_nothing():
    """The common case: most apps have no numbers, and must not pay a warning,
    a key or a payload entry for it."""
    for nothing in (None, {}):
        assert summary.clean(nothing) == ({}, ())


def test_the_keys_come_out_in_name_order():
    """What makes the OSC argument order a function of the summary's contents
    rather than of the order the app's code happened to build the dict in."""
    kept, _ = summary.clean({"played": 3, "best_ms": 210.0, "average_ms": 260.0})
    assert list(kept) == ["average_ms", "best_ms", "played"]


@pytest.mark.parametrize("value,because", [
    ({"deep": 1}, "nested"),
    ([1, 2, 3], "a list of laps"),
    (None, "a number nobody set"),
    ((1, 2), "a tuple"),
    (object(), "something with no wire form at all"),
])
def test_a_value_that_is_not_a_scalar_loses_its_key_and_nothing_else(value, because):
    kept, complaints = summary.clean({"blocks": 4, "junk": value})
    assert kept == {"blocks": 4}, because
    assert len(complaints) == 1 and "'junk'" in complaints[0]


@pytest.mark.parametrize("value", [float("nan"), math.inf, -math.inf])
def test_a_number_with_no_json_form_is_dropped(value):
    """`inf` and `nan` are what a guard-free average returns on an empty
    session. Neither has a JSON spelling, so a receiver would reject the whole
    body over one bad key - which is the failure this stops."""
    kept, complaints = summary.clean({"played": 0, "average_ms": value})
    assert kept == {"played": 0}
    assert len(complaints) == 1 and "'average_ms'" in complaints[0]


@pytest.mark.parametrize("value", [True, 7, 1.5, "won"])
def test_every_scalar_the_carriers_can_express_is_allowed(value):
    """Bools and strings as much as numbers: both carriers have a form for
    them (JSON natively, OSC as T/F and a string argument)."""
    assert summary.clean({"k": value}) == ({"k": value}, ())


def test_a_key_that_is_not_a_name_is_dropped():
    kept, complaints = summary.clean({"blocks": 4, 7: 1, "": 2})
    assert kept == {"blocks": 4}
    assert len(complaints) == 2


def test_too_many_keys_are_truncated_rather_than_refused():
    """A chatty app loses its tail, not its summary - the numbers that did fit
    are still worth carrying, and the log line says which ones did not."""
    raw = {f"k{i:02d}": i for i in range(summary.MAX_KEYS + 3)}
    kept, complaints = summary.clean(raw)
    assert len(kept) == summary.MAX_KEYS
    assert list(kept) == sorted(raw)[:summary.MAX_KEYS]  # deterministic, by name
    assert len(complaints) == 1 and "at most" in complaints[0]


def test_something_that_is_not_a_dict_at_all_reports_nothing():
    kept, complaints = summary.clean("8 rounds")
    assert kept == {}
    assert len(complaints) == 1


def test_the_gate_never_raises_on_anything_an_app_can_hand_it():
    """Total by construction, the way `ramp.color_at` is: this runs while an
    app is ending, and an exception here would turn a bad key into a lost
    exit hook."""
    for hostile in ([("a", 1)], {"a": {"b": {"c": 1}}}, {1: 2, "b": None}, 42, b"x"):
        kept, _ = summary.clean(hostile)
        assert isinstance(kept, dict)


# --- what the carriers do with it ------------------------------------------


def test_a_webhook_payload_carries_the_numbers_flat():
    payload = summary.merge(
        {"trigger": "on_exit", "mode": "Focus"}, {"blocks": 4}
    )
    assert payload == {"trigger": "on_exit", "mode": "Focus", "blocks": 4}


def test_an_app_cannot_overwrite_what_identifies_the_event():
    """`mode` is who reported, not something an app gets to say. A receiver
    keying on it must not be lie-able-to by an app that counts something with
    the same name."""
    payload = summary.merge({"mode": "Focus"}, {"mode": "elsewhere", "blocks": 4})
    assert payload == {"mode": "Focus", "blocks": 4}


def test_osc_arguments_are_the_values_in_key_order():
    """Positional, so the order has to come from the key names - a receiver
    maps argument 0 to a meaning and cannot re-read our source when an app
    changes."""
    assert summary.as_args({"played": 3, "best_ms": 210.0}) == (210.0, 3)
