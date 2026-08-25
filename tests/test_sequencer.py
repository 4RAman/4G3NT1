"""Stop lists - the "what happens next" light.

Everything here is a table over `plan_at`, which is pure: no clock, no
device, nothing async. main.py's `_drive_sequence` is the thin, untestable
(without asyncio) wrapper that sleeps for what this says and pushes what
this says to push - see test_main_takeover.py for that half.
"""

import pytest

from aibutton import sequencer
from aibutton.device import SAFE_MIN_PERIOD_S
from aibutton.sequencer import Sequence, Stop

RED, GREEN, BLUE, BLACK = "#ff0000", "#00ff00", "#0000ff", "#000000"


def colour_at(seq, elapsed, min_step=0.1):
    """`plan_at`'s colour alone, or None when a one-shot has finished.

    `plan_at` answers with a `Frame` (colour plus the stop's own style) since
    TODO 36c. Most tables below ask only the colour question, so they go
    through here; the ones that care about style or wait unpack the frame
    themselves."""
    frame, _ = sequencer.plan_at(seq, elapsed, min_step)
    return frame.color if frame is not None else None


# --- one-shot: plays once, says when it is done ----------------------------

def test_a_one_shot_holds_its_only_stop_then_finishes():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=False)
    assert sequencer.plan_at(seq, 0.0, 0.1) == (sequencer.Frame(RED), 1.0)
    assert sequencer.plan_at(seq, 0.5, 0.1) == (sequencer.Frame(RED), 0.5)
    assert colour_at(seq, 0.999) == RED
    assert sequencer.plan_at(seq, 1.0, 0.1) == (None, None)
    assert sequencer.plan_at(seq, 5.0, 0.1) == (None, None)  # stays finished


def test_a_one_shot_walks_every_stop_in_order():
    seq = Sequence(
        stops=(Stop(RED, hold_s=1.0), Stop(GREEN, hold_s=1.0), Stop(BLUE, hold_s=1.0)),
        repeat=False,
    )
    assert colour_at(seq, 0.0) == RED
    assert colour_at(seq, 1.5) == GREEN
    assert colour_at(seq, 2.5) == BLUE
    assert sequencer.plan_at(seq, 3.0, 0.1) == (None, None)


def test_a_one_shots_first_stop_fades_from_black():
    """Nothing plays before a one-shot starts, so there is nothing to fade
    from but black - the confirmation-flash case: it is arriving out of
    nothing."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    assert colour_at(seq, 0.0) == BLACK
    # And it has fully arrived at the exact instant the fade ends - the hold
    # branch, not an interpolated near-miss (see the exactness tests below).
    assert colour_at(seq, 1.0) == RED


def test_an_empty_stop_list_is_finished_immediately():
    assert sequencer.plan_at(Sequence(stops=(), repeat=False), 0.0, 0.1) == (None, None)
    assert sequencer.plan_at(Sequence(stops=(), repeat=True), 0.0, 0.1) == (None, None)


# --- repeat: cycles forever, never finishes ---------------------------------

@pytest.mark.parametrize(
    "elapsed, expected",
    [
        (0.0, RED), (0.9, RED),
        (1.0, GREEN), (1.9, GREEN),
        (2.0, RED),      # wrapped
        (7.5, GREEN),    # a later cycle (7.5 % 2.0 == 1.5, inside GREEN's hold)
        (200.0, RED),    # many cycles in - still lands cleanly
    ],
)
def test_a_repeating_sequence_cycles(elapsed, expected):
    seq = Sequence(stops=(Stop(RED, hold_s=1.0), Stop(GREEN, hold_s=1.0)), repeat=True)
    assert colour_at(seq, elapsed) == expected


def test_a_repeat_never_reports_finished():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=True)
    for t in (0.0, 0.5, 1.0, 100.0, 1000.5):
        frame, next_change = sequencer.plan_at(seq, t, 0.1)
        assert frame is not None
        assert next_change is not None


def test_a_repeating_sequences_first_stop_fades_from_the_last_stops_colour():
    """Unlike a one-shot: there is always something behind a repeat's first
    stop - the cycle that just finished - so it never dips to black at the
    seam where it wraps."""
    seq = Sequence(
        stops=(Stop(RED, hold_s=1.0, fade_s=0.5), Stop(GREEN, hold_s=1.0, fade_s=0.5)),
        repeat=True,
    )
    assert colour_at(seq, 0.0) == GREEN  # the last stop's colour, not black
    # Confirm it holds on the second cycle too (t=3.0 is the same phase as 0.0).
    assert colour_at(seq, 3.0) == GREEN


def test_a_fully_degenerate_repeat_holds_rather_than_dividing_by_zero():
    """Every stop dwells zero: there is no timeline to walk. Rather than
    crash on `elapsed % 0`, it holds the last stop and reports a positive
    wait so a caller that sleeps for what it is told never busy-loops.
    config.sequence_safe keeps this from happening to anything that reaches
    main.set_led for real."""
    seq = Sequence(stops=(Stop(RED, 0, 0), Stop(GREEN, 0, 0)), repeat=True)
    frame, wait = sequencer.plan_at(seq, 3.0, 0.1)
    assert frame.color == GREEN
    assert wait == pytest.approx(0.1)
    # min_step_s <= 0 too: still a positive, finite wait.
    _, wait = sequencer.plan_at(seq, 3.0, 0.0)
    assert wait == pytest.approx(1.0)


# --- fades: stepped, not smooth ---------------------------------------------

def test_fade_steps_are_quantised_to_min_step_s():
    """A 1s fade sampled no finer than 0.25s shows exactly 4 distinct levels,
    each held for a whole step."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    levels_seen = []
    for t in (0.0, 0.1, 0.24, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.99):
        levels_seen.append(colour_at(seq, t, 0.25))
    # Exactly the four step colours, in step order, each repeated for its
    # whole 0.25s window.
    assert levels_seen == [
        sequencer.mix(BLACK, RED, 0.0), sequencer.mix(BLACK, RED, 0.0),
        sequencer.mix(BLACK, RED, 0.0),
        sequencer.mix(BLACK, RED, 0.25), sequencer.mix(BLACK, RED, 0.25),
        sequencer.mix(BLACK, RED, 0.5), sequencer.mix(BLACK, RED, 0.5),
        sequencer.mix(BLACK, RED, 0.75), sequencer.mix(BLACK, RED, 0.75),
        sequencer.mix(BLACK, RED, 0.75),
    ]


def test_next_change_is_the_time_left_in_the_current_step():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    _, wait = sequencer.plan_at(seq, 0.1, 0.25)
    assert wait == pytest.approx(0.15)  # 0.25 - 0.1, the first step's edge
    _, wait = sequencer.plan_at(seq, 0.6, 0.25)
    assert wait == pytest.approx(0.15)  # 0.75 - 0.6


def test_a_fade_shorter_than_one_step_is_a_hard_cut():
    """Asking for finer motion than the caller is willing to spend on it
    degenerates to the coarsest legal stepping: the old colour for the whole
    (short) fade, then the target the instant the hold begins."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=0.05),), repeat=False)
    assert colour_at(seq, 0.0, 0.5) == BLACK
    assert colour_at(seq, 0.04, 0.5) == BLACK
    assert colour_at(seq, 0.05, 0.5) == RED


def test_min_step_s_of_zero_is_continuous_stepping_collapsed_to_one_step():
    """No floor at all is the coarsest floor there is (one step), not a
    division by zero."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    assert colour_at(seq, 0.5, 0.0) == BLACK
    assert colour_at(seq, 1.0, 0.0) == RED


# --- interpolation endpoints are exact, not approximated --------------------

def test_a_fades_start_is_exactly_the_previous_colour():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=2.0),), repeat=False)
    assert colour_at(seq, 0.0) == BLACK


def test_a_fades_end_is_exactly_the_target_colour_not_a_near_miss():
    """The hold branch returns `stop.color` directly - never a `mix()` at
    level 1.0, which floating point could round a channel or two away from
    the exact target."""
    seq = Sequence(stops=(Stop("#123456", hold_s=1.0, fade_s=0.3),), repeat=False)
    assert colour_at(seq, 0.3) == "#123456"
    assert colour_at(seq, 0.5) == "#123456"


def test_zero_fade_is_a_hard_cut_with_no_interpolation_at_all():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=0.0),), repeat=False)
    assert colour_at(seq, 0.0) == RED


# --- totality: negative time, and the domain edges --------------------------

def test_negative_elapsed_is_clamped_to_the_start():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=False)
    assert sequencer.plan_at(seq, -3.0, 0.1) == sequencer.plan_at(seq, 0.0, 0.1)


# --- mix(): the same idea as ramp.mix, kept as its own copy ------------------

@pytest.mark.parametrize(
    "level, expected", [(0.0, BLACK), (0.5, "#808080"), (1.0, "#ffffff")]
)
def test_mix_walks_component_by_component(level, expected):
    assert sequencer.mix(BLACK, "#ffffff", level) == expected


# --- defaults, for the config parser to build on -----------------------------

def test_stop_defaults_match_the_documented_ones():
    stop = Stop(RED)
    assert stop.hold_s == pytest.approx(0.5)
    assert stop.fade_s == pytest.approx(0.0)


def test_sequence_defaults_to_repeating():
    assert Sequence(stops=(Stop(RED),)).repeat is True


# --- readout(): a value played as blinks (TODO 15/17) -----------------------

TENS, UNITS = "#ff8800", "#3399ff"


def test_27_is_two_slow_pulses_then_a_gap_then_seven_quick_pulses():
    seq = sequencer.readout(27, tens_color=TENS, units_color=UNITS)
    assert seq.repeat is False
    assert [s.color for s in seq.stops] == [
        TENS, BLACK, TENS, BLACK,
        UNITS, BLACK, UNITS, BLACK, UNITS, BLACK, UNITS, BLACK,
        UNITS, BLACK, UNITS, BLACK, UNITS,
    ]
    # "slow" and "quick" named exactly: the tens dwell, the units dwell, and
    # the one gap standing apart from both between the two digit groups.
    assert seq.stops[0].hold_s == pytest.approx(0.5)   # tens: colour ~0.5s
    assert seq.stops[1].hold_s == pytest.approx(0.35)  # tens: black gap ~0.35s
    assert seq.stops[3].hold_s == pytest.approx(0.7)   # the group gap
    assert seq.stops[4].hold_s == pytest.approx(0.18)  # units: colour ~0.18s
    assert seq.stops[5].hold_s == pytest.approx(0.18)  # units: black ~0.18s


def test_0_is_a_single_dim_neutral_blink_not_zero_pulses():
    """Distinguishable from "nothing happened" - a button that just sat
    there dark - rather than looking like the digit code simply had nothing
    to show."""
    seq = sequencer.readout(0, tens_color=TENS, units_color=UNITS)
    assert seq.repeat is False
    assert len(seq.stops) == 1
    stop = seq.stops[0]
    assert stop.color not in (TENS, UNITS, BLACK)
    assert stop.hold_s > 0


def test_7_is_no_slow_pulses_no_group_gap_seven_quick_pulses():
    seq = sequencer.readout(7, tens_color=TENS, units_color=UNITS)
    assert [s.color for s in seq.stops] == [
        UNITS, BLACK, UNITS, BLACK, UNITS, BLACK, UNITS,
        BLACK, UNITS, BLACK, UNITS, BLACK, UNITS,
    ]


def test_a_zero_units_digit_ends_after_the_tens_group_no_trailing_gap():
    """The mirror of the zero-tens case: "20" is two slow pulses and then
    nothing, not a gap left dangling with no units group to separate."""
    seq = sequencer.readout(20, tens_color=TENS, units_color=UNITS)
    assert [s.color for s in seq.stops] == [TENS, BLACK, TENS]


def test_values_above_99_clamp_to_99():
    assert sequencer.readout(100) == sequencer.readout(99)
    assert sequencer.readout(1000) == sequencer.readout(99)


@pytest.mark.parametrize(
    "value", [0, 1, 5, 7, 9, 10, 19, 20, 27, 40, 55, 90, 99, 100]
)
def test_every_stops_dwell_clears_the_default_flash_floor(value):
    """Chosen so `config.sequence_safe` never has to touch it - every dwell
    clears `SAFE_MIN_PERIOD_S / 2` (~0.167s) by construction, which is the
    property the sequencer.readout docstring promises."""
    seq = sequencer.readout(value)
    floor = SAFE_MIN_PERIOD_S / 2
    assert all(stop.hold_s + stop.fade_s >= floor for stop in seq.stops)


def test_readout_is_always_a_one_shot():
    for value in (0, 5, 27, 99):
        assert sequencer.readout(value).repeat is False


# --- curves: how a fade is shaped (TODO 36b) --------------------------------

@pytest.mark.parametrize("curve", sequencer.CURVES)
def test_every_curve_pins_both_ends_and_stays_inside_them(curve):
    """The property `_fade_step`'s "never step past the target" guarantee
    rests on: each curve maps 0..1 onto 0..1 with f(0)=0 and f(1)=1. A curve
    that overshot would produce a colour outside the two it is interpolating
    between - and `mix` would happily render it."""
    assert sequencer.shape(curve, 0.0) == 0.0
    assert sequencer.shape(curve, 1.0) == 1.0
    for i in range(1, 20):
        assert 0.0 <= sequencer.shape(curve, i / 20) <= 1.0


@pytest.mark.parametrize("curve", sequencer.CURVES)
def test_every_curve_only_ever_moves_forward(curve):
    """Monotonic, so a fade never doubles back on itself half way through."""
    levels = [sequencer.shape(curve, i / 20) for i in range(21)]
    assert levels == sorted(levels), curve


def test_the_curves_actually_differ_from_each_other_and_from_linear():
    """Otherwise the whole table is decoration.

    Compared over the *whole* range rather than at the midpoint, because
    `ease_in_out` passes through exactly 0.5 there - it is symmetric, so the
    one point where the other four are furthest apart is the one point where
    it is indistinguishable from linear.
    """
    profiles = {
        curve: tuple(round(sequencer.shape(curve, i / 20), 4) for i in range(21))
        for curve in sequencer.CURVES
    }
    assert len(set(profiles.values())) == len(sequencer.CURVES)

    mid = {curve: sequencer.shape(curve, 0.5) for curve in sequencer.CURVES}
    assert mid["linear"] == pytest.approx(0.5)
    assert mid["ease_in_out"] == pytest.approx(0.5)  # symmetric, by definition
    assert mid["ease_in"] < mid["linear"] < mid["ease_out"]
    # The steepest one: barely moved at half way, which is the whole point of
    # offering it - "hold, then rush" is the shape people ask for by name.
    assert mid["exponential"] < mid["ease_in"]


def test_an_unknown_curve_renders_linear_rather_than_raising():
    """Reached from parsed config, where a look that renders plainly beats one
    that throws - the same fail-soft rule every other key follows."""
    assert sequencer.shape("no-such-curve", 0.4) == pytest.approx(0.4)


def test_a_curve_shapes_the_fade_it_is_on():
    """End to end rather than through `shape` alone: the curve has to reach
    `plan_at`, and only the fade - the hold either side is untouched."""
    straight = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    bent = Sequence(
        stops=(Stop(RED, hold_s=1.0, fade_s=1.0, curve="exponential"),), repeat=False
    )
    # Half way through the fade, the exponential one has barely left black.
    assert colour_at(bent, 0.5, 0.05) != colour_at(straight, 0.5, 0.05)
    # Both ends stay exact whatever the curve.
    assert colour_at(bent, 0.0, 0.05) == BLACK
    assert colour_at(bent, 1.0, 0.05) == RED


# --- a stop is a flat colour (TODO 36e) ------------------------------------
#
# A stop briefly carried a style and a period of its own, so one node of a list
# could be "flashing yellow". It went because a list that walks colours *and*
# animates inside them is two clocks on one light, and nothing in the editor
# could say which one you were setting. What it expressed is still expressible,
# and these two tests are the argument: a flash is on, off, on.


def test_a_hold_shows_one_flat_colour():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=False)
    frame, _ = sequencer.plan_at(seq, 0.5, 0.1)
    assert frame == sequencer.Frame(RED)


def test_a_flash_is_three_stops_and_reads_as_one():
    """The replacement for a flashing hold, and it says the same thing in the
    one vocabulary the editor can show: colours, in order, each held."""
    seq = Sequence(
        stops=(Stop(RED, hold_s=0.25), Stop(BLACK, hold_s=0.25), Stop(RED, hold_s=0.25)),
        repeat=False,
    )
    seen = [sequencer.plan_at(seq, t, 0.05)[0].color for t in (0.1, 0.35, 0.6)]
    assert seen == [RED, BLACK, RED]


def test_a_stop_defaults_to_a_plain_solid():
    """Every stop written before TODO 36 means exactly this, so the default is
    what keeps those looks rendering identically."""
    assert Stop(RED).curve == "linear"


# --- sample_at: the same list, driven from outside (TODO 36d) ---------------

def test_sampling_spreads_the_list_across_nought_to_one():
    seq = Sequence(
        stops=(Stop(RED, hold_s=1.0), Stop(GREEN, hold_s=1.0), Stop(BLUE, hold_s=2.0)),
        repeat=False, drive="progress",
    )
    assert sequencer.span_total(seq) == pytest.approx(4.0)
    assert sequencer.sample_at(seq, 0.0).color == RED
    assert sequencer.sample_at(seq, 0.2).color == RED       # t = 0.8
    assert sequencer.sample_at(seq, 0.3).color == GREEN     # t = 1.2
    assert sequencer.sample_at(seq, 0.9).color == BLUE      # t = 3.6


def test_a_sampled_one_shot_clamps_rather_than_finishing():
    """`plan_at` reports None past the end; sampling must not. A progress bar
    at 1.0 should show the last stop - "finished" is a state a countdown
    *holds*, not one it passes through."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=False, drive="progress")
    assert sequencer.sample_at(seq, 1.0).color == RED
    assert sequencer.sample_at(seq, 4.2).color == RED
    assert sequencer.sample_at(seq, -3.0).color == RED


def test_a_sampled_repeat_wraps_so_a_short_pattern_covers_a_long_run():
    """What makes `beats` useful: a four-beat accent over an eight-beat bar."""
    seq = Sequence(
        stops=(Stop(RED, hold_s=1.0), Stop(GREEN, hold_s=1.0)),
        repeat=True, drive="beats",
    )
    assert sequencer.sample_at(seq, 0.1).color == RED
    assert sequencer.sample_at(seq, 1.1).color == RED   # wrapped past 1.0
    assert sequencer.sample_at(seq, 5.6).color == GREEN


def test_sampled_fades_are_continuous_not_quantised():
    """The one place sampling disagrees with walking, deliberately. The 50 ms
    stepping models what a radio carries when the *host* pushes every frame,
    and nothing is pushing a sampled one - quantising here would lose the
    gradient for nothing. This is the bug that shipped first: `min_step_s = 0`
    collapses a fade to a single hard cut, so a sampled list showed no
    gradient at all."""
    seq = Sequence(
        stops=(Stop(RED, hold_s=0.0, fade_s=1.0),), repeat=False, drive="progress"
    )
    seen = {sequencer.sample_at(seq, i / 20).color for i in range(21)}
    assert len(seen) > 10, seen


def test_sampling_an_empty_list_is_none_rather_than_a_crash():
    assert sequencer.sample_at(Sequence(stops=(), repeat=False), 0.5) is None


def test_a_fully_degenerate_sample_holds_rather_than_dividing_by_zero():
    seq = Sequence(stops=(Stop(RED, 0, 0), Stop(GREEN, 0, 0)), repeat=True)
    assert sequencer.sample_at(seq, 0.5).color == GREEN


def test_a_sequence_defaults_to_the_clock_drive():
    """Every stop list written before TODO 36d is a clock one, and has to keep
    parsing as exactly that."""
    assert Sequence(stops=(Stop(RED),)).drive == "clock"
