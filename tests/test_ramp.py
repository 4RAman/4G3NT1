"""Colour ramps - the pure half of "show me how far through this is".

Everything here is a table over a side-effect-free function, which is the
point of ramp.py being its own module: the countdown loop that uses it needs
asyncio and a clock, and none of the maths below does.
"""

import pytest

from aibutton import ramp
from aibutton.ramp import Stop

RED, GREEN, BLUE, BLACK, WHITE = "#ff0000", "#00ff00", "#0000ff", "#000000", "#ffffff"


# --- spacing --------------------------------------------------------------

def test_a_list_of_colours_spreads_from_end_to_end():
    assert ramp.even([RED, GREEN, BLUE]) == (
        Stop(0.0, RED), Stop(0.5, GREEN), Stop(1.0, BLUE),
    )


def test_one_colour_is_a_constant_ramp_not_a_division_by_zero():
    stops = ramp.even([RED])
    assert stops == (Stop(0.0, RED),)
    assert ramp.color_at(stops, 0.0) == RED
    assert ramp.color_at(stops, 1.0) == RED


def test_no_colours_is_empty_rather_than_an_error():
    assert ramp.even([]) == ()


# --- reading a colour off a ramp -----------------------------------------

@pytest.mark.parametrize(
    "progress, expected",
    [
        (0.0, RED),
        (0.25, "#808000"),  # halfway red -> green
        (0.5, GREEN),
        (0.75, "#008080"),  # halfway green -> blue
        (1.0, BLUE),
    ],
)
def test_colour_is_blended_between_the_stops_either_side(progress, expected):
    assert ramp.color_at(ramp.even([RED, GREEN, BLUE]), progress) == expected


@pytest.mark.parametrize("progress", [-5.0, -0.001, 1.001, 99.0])
def test_progress_outside_zero_to_one_is_clamped_not_wrapped(progress):
    """A countdown that overshoots its deadline by a tick must not flip back
    to the starting colour."""
    stops = ramp.even([RED, BLUE])
    assert ramp.color_at(stops, progress) in (RED, BLUE)


def test_an_empty_ramp_is_black_rather_than_an_exception():
    assert ramp.color_at((), 0.5) == BLACK


def test_stops_are_sorted_rather_than_assumed_sorted():
    """Config can hand over hand-written stops in any order; an unsorted ramp
    should render the same as a sorted one, not silently wrongly."""
    scrambled = (Stop(1.0, BLUE), Stop(0.0, RED), Stop(0.5, GREEN))
    assert ramp.color_at(scrambled, 0.5) == GREEN
    assert ramp.color_at(scrambled, 0.0) == RED
    assert ramp.color_at(scrambled, 1.0) == BLUE


def test_two_stops_at_the_same_position_are_a_hard_edge():
    """Expressible on purpose - "green until 80%, then red" with no blend."""
    stops = (Stop(0.0, GREEN), Stop(0.8, GREEN), Stop(0.8, RED), Stop(1.0, RED))
    assert ramp.color_at(stops, 0.79) == GREEN
    assert ramp.color_at(stops, 0.81) == RED


def test_a_ramp_need_not_start_at_zero_or_end_at_one():
    """Positions outside the stops' range hold the nearest stop rather than
    fading to black."""
    stops = (Stop(0.25, RED), Stop(0.75, BLUE))
    assert ramp.color_at(stops, 0.0) == RED
    assert ramp.color_at(stops, 1.0) == BLUE


# --- blending -------------------------------------------------------------

@pytest.mark.parametrize(
    "level, expected",
    [(0.0, BLACK), (0.5, "#808080"), (1.0, WHITE)],
)
def test_mix_walks_component_by_component(level, expected):
    assert ramp.mix(BLACK, WHITE, level) == expected


def test_mix_matches_the_firmwares_crossfade():
    """firmware/led.py's _fade blends the same way. If these disagree, a ramp
    on the host and a `fade` on the device mean different things."""
    from led import _mix, _norm  # firmware, on sys.path via conftest

    host = ramp.mix(RED, BLUE, 0.25)
    device = _mix(_norm((255, 0, 0)), _norm((0, 0, 255)), 0.25)
    assert host == "#" + "".join(f"{round(channel * 255):02x}" for channel in device)


# --- change detection -----------------------------------------------------

def test_differs_ignores_a_change_too_small_to_see():
    assert not ramp.differs("#404040", "#414141", 4)


def test_differs_notices_a_change_on_any_single_channel():
    assert ramp.differs("#404040", "#404440", 4)


def test_differs_is_what_bounds_the_writes_over_a_long_sweep():
    """The property that matters: walking a full ramp one step at a time
    pushes a few hundred updates, not one per evaluation."""
    stops = ramp.even([RED, GREEN, BLUE])
    pushed, last = 0, None
    for step in range(3601):  # a one-hour countdown evaluated every second
        colour = ramp.color_at(stops, step / 3600)
        if last is None or ramp.differs(last, colour, 4):
            pushed += 1
            last = colour
    assert pushed < 300
