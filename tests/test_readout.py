"""aibutton.readout: three number -> light compilers (TODO 91).

Tables of `(value, scheme) -> stops`, per 91's "Done when". Assertions are
mostly structural (which colours light, in what order, whether a dwell
clears the floor) rather than pinning every literal second this module's
defaults happen to pick - the contract is the shape, the same split
test_sequencer.py draws between its "27 is two slow pulses..." test (an
exact stop-by-stop pin, because that scheme is frozen) and this module's
schemes, which still take configurable timing.
"""

import pytest

from aibutton import morse, readout
from aibutton.device import SAFE_MIN_PERIOD_S
from aibutton.sequencer import Stop

BLACK = "#000000"
FLOOR = SAFE_MIN_PERIOD_S / 2


def _on_colors(stops: tuple[Stop, ...]) -> list[str]:
    """The colours actually lit, black gaps stripped - the sequence TODO
    91's own "1021 is yellow, cyan, cyan, blue" is written in."""
    return [s.color for s in stops if s.color != BLACK]


# --- place_value: sequencer.readout's tens/units idea, generalised ---------

def test_1021_matches_todo_91s_worked_example():
    """Highest place first: thousands=1, hundreds=0 (skipped), tens=2,
    units=1. Written out against the default table (1s blue/10s cyan/100s
    green/1000s yellow) rather than derived, so this would catch the same
    mistake the algorithm could make - and it is TODO.md's own example,
    verbatim: "1021 is yellow, cyan, cyan, blue"."""
    blue, cyan, _, yellow = readout.DEFAULT_PLACE_COLORS
    assert _on_colors(readout.place_value(1021)) == [yellow, cyan, cyan, blue]


def test_a_zero_digit_inside_a_larger_number_is_skipped_not_blinked():
    """20's units digit is zero and contributes nothing - two pulses of the
    tens colour and the sequence simply ends, the same "no trailing gap to
    nothing" rule `sequencer.readout` documents for its own units group."""
    _, cyan, _, _ = readout.DEFAULT_PLACE_COLORS
    stops = readout.place_value(20)
    assert _on_colors(stops) == [cyan, cyan]
    assert stops[-1].color == cyan  # ends on the pulse, no dangling gap


def test_the_whole_value_zero_is_one_dim_blink_not_zero_pulses():
    """Distinguishable from "nothing happened" - `sequencer.readout`'s own
    convention for value 0, restated here: one stop, in a colour that
    matches none of the configured places."""
    stops = readout.place_value(0)
    assert len(stops) == 1
    assert stops[0].color not in readout.DEFAULT_PLACE_COLORS
    assert stops[0].hold_s > 0


def test_a_colour_list_shorter_than_the_digit_count_wraps_rather_than_raising():
    """Two colours, three digits (321) - place_value must still answer for
    the hundreds place instead of raising an IndexError. It wraps back to
    `colors[0]`, so the hundreds and the units end up sharing a colour
    rather than the call failing."""
    stops = readout.place_value(321, colors=("A", "B"))
    assert _on_colors(stops) == ["A", "A", "A", "B", "B", "A"]


def test_a_five_digit_number_uses_every_place_no_99_cap():
    """`sequencer.readout` would have clamped this to 99; place_value has no
    such ceiling, and a value five digits long should still walk every
    place, wrapping the four-colour default table onto the fifth. Written
    out longhand: 20213 is 2 (ten-thousands), 0 (thousands, skipped), 2
    (hundreds), 1 (tens), 3 (units)."""
    blue, cyan, green, _ = readout.DEFAULT_PLACE_COLORS
    stops = readout.place_value(20213)
    assert _on_colors(stops) == [
        blue, blue,        # ten-thousands: place index 4 wraps to colours[0]
        green, green,      # hundreds: place index 2
        cyan,               # tens: place index 1
        blue, blue, blue,  # units: place index 0
    ]


@pytest.mark.parametrize("on_s,off_s,group_gap_s", [(0.0, 0.0, 0.0), (0.01, 0.01, 0.01)])
def test_place_value_dwell_clears_the_floor_even_with_degenerate_timing(on_s, off_s, group_gap_s):
    """A caller passing an unreasonably fast strobe still gets every dwell
    clamped up to `FLOOR` "by construction" - the same guarantee
    `sequencer.readout`'s fixed constants give for free, applied here to
    parameters that could otherwise violate it."""
    for value in (0, 5, 20, 1021, 20213):
        stops = readout.place_value(value, on_s=on_s, off_s=off_s, group_gap_s=group_gap_s)
        assert all(s.hold_s + s.fade_s >= FLOOR for s in stops)


# --- morse: TODO 83's compiler, reused directly -----------------------------

def test_morse_of_a_value_is_exactly_morse_encode_of_its_digits():
    """No renderer written here - `readout.morse` is `morse.encode` handed a
    stringified number, so this must match calling that compiler directly
    (unit_s above the floor, so nothing here clamps it)."""
    color = "#ff0000"
    assert readout.morse(1234, unit_s=1.0, color=color) == morse.encode("1234", 1.0, color)


def test_morse_zero_is_five_dashes_not_silence():
    """"0" is `-----` in the international alphabet - a real, visible
    pattern, so a counted zero does not read as the button doing nothing
    (the same property place_value's zero needs a special case for; morse
    gets it for free from its own alphabet having no blank digit)."""
    color = "#ff0000"
    stops = readout.morse(0, unit_s=1.0, color=color)
    assert [s.color for s in stops if s.color != BLACK] == [color] * 5


def test_morse_of_a_large_number_matches_the_compiler_digit_for_digit():
    """No cap: a nine-digit value compiles exactly as if its digits were
    typed as a message, proving there is no ceiling hiding in this wrapper."""
    value = 123456789
    color = "#00ff00"
    assert readout.morse(value, unit_s=0.5, color=color) == morse.encode(
        str(value), 0.5, color
    )


def test_morse_floors_unit_s_at_half_the_flash_period():
    """Every Morse element is at least one unit long (a dot, or the shortest
    gap), so flooring `unit_s` itself guarantees every stop clears `FLOOR` -
    checked here with `unit_s=0` to prove the floor is applied rather than
    merely being true of some already-safe default."""
    color = "#123456"
    stops = readout.morse(2024, unit_s=0.0, color=color)
    assert all(s.hold_s + s.fade_s >= FLOOR for s in stops)
    # And it is exactly the floored unit that reaches the compiler:
    assert stops == morse.encode("2024", FLOOR, color)


# --- binary: two colours, most-significant bit first ------------------------

def test_5_is_one_zero_one_most_significant_bit_first():
    zero, one = "Z", "O"
    stops = readout.binary(5, zero_color=zero, one_color=one, on_s=1.0, off_s=0.5)
    assert [s.color for s in stops] == [one, BLACK, zero, BLACK, one]


def test_binary_zero_is_a_single_zero_coloured_pulse():
    """`bin(0)` is the single bit "0", which already reads as "something
    happened" the moment it lights `zero_color` - no special case needed,
    unlike the other two schemes."""
    stops = readout.binary(0, zero_color="Z", one_color="O", on_s=1.0, off_s=0.5)
    assert stops == (Stop("Z", hold_s=1.0),)


def test_binary_of_a_large_number_separates_every_run_of_the_same_bit():
    """255 is eight 1-bits in a row - without a gap between each one, that
    would render as one long flash indistinguishable from a single bit held
    eight times as long, so every bit gets its own gap even when its
    neighbour is the same colour."""
    stops = readout.binary(255, zero_color="Z", one_color="O")
    assert [s.color for s in stops] == ["O", BLACK] * 7 + ["O"]


@pytest.mark.parametrize("on_s,off_s", [(0.0, 0.0), (0.01, 0.01)])
def test_binary_dwell_clears_the_floor_even_with_degenerate_timing(on_s, off_s):
    for value in (0, 5, 255, 123456):
        stops = readout.binary(value, on_s=on_s, off_s=off_s)
        assert all(s.hold_s + s.fade_s >= FLOOR for s in stops)


# --- negative values: magnitude only, decided once ---------------------------

@pytest.mark.parametrize("scheme", readout.SCHEMES)
def test_a_negative_value_reads_the_same_as_its_magnitude(scheme):
    fn = getattr(readout, scheme)
    assert fn(-7) == fn(7)


# --- render(): the dispatcher ------------------------------------------------

@pytest.mark.parametrize("scheme", readout.SCHEMES)
def test_render_dispatches_to_the_function_named_in_schemes(scheme):
    fn = getattr(readout, scheme)
    assert readout.render(42, scheme) == fn(42)


def test_render_forwards_keyword_options_to_the_scheme():
    assert readout.render(5, "binary", zero_color="Z", one_color="O") == readout.binary(
        5, zero_color="Z", one_color="O"
    )


def test_render_rejects_a_scheme_nothing_dispatches():
    with pytest.raises(ValueError, match="bogus"):
        readout.render(5, "bogus")


def test_schemes_names_every_dispatchable_scheme():
    """The mirror a future parser/schema needs: every name in `SCHEMES`
    actually dispatches through `render`."""
    for scheme in readout.SCHEMES:
        readout.render(1, scheme)  # does not raise
