"""Stop lists - the "what happens next" light.

Everything here is a table over `plan_at`, which is pure: no clock, no
device, nothing async. main.py's `_drive_sequence` is the thin, untestable
(without asyncio) wrapper that sleeps for what this says and pushes what
this says to push - see test_main_takeover.py for that half.
"""

import pytest

from aibutton import sequencer
from aibutton.sequencer import Sequence, Stop

RED, GREEN, BLUE, BLACK = "#ff0000", "#00ff00", "#0000ff", "#000000"


# --- one-shot: plays once, says when it is done ----------------------------

def test_a_one_shot_holds_its_only_stop_then_finishes():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=False)
    assert sequencer.plan_at(seq, 0.0, 0.1) == (RED, 1.0)
    assert sequencer.plan_at(seq, 0.5, 0.1) == (RED, 0.5)
    assert sequencer.plan_at(seq, 0.999, 0.1)[0] == RED
    assert sequencer.plan_at(seq, 1.0, 0.1) == (None, None)
    assert sequencer.plan_at(seq, 5.0, 0.1) == (None, None)  # stays finished


def test_a_one_shot_walks_every_stop_in_order():
    seq = Sequence(
        stops=(Stop(RED, hold_s=1.0), Stop(GREEN, hold_s=1.0), Stop(BLUE, hold_s=1.0)),
        repeat=False,
    )
    assert sequencer.plan_at(seq, 0.0, 0.1)[0] == RED
    assert sequencer.plan_at(seq, 1.5, 0.1)[0] == GREEN
    assert sequencer.plan_at(seq, 2.5, 0.1)[0] == BLUE
    assert sequencer.plan_at(seq, 3.0, 0.1) == (None, None)


def test_a_one_shots_first_stop_fades_from_black():
    """Nothing plays before a one-shot starts, so there is nothing to fade
    from but black - the confirmation-flash case: it is arriving out of
    nothing."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    color, _ = sequencer.plan_at(seq, 0.0, 0.1)
    assert color == BLACK
    # And it has fully arrived at the exact instant the fade ends - the hold
    # branch, not an interpolated near-miss (see the exactness tests below).
    color, _ = sequencer.plan_at(seq, 1.0, 0.1)
    assert color == RED


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
    assert sequencer.plan_at(seq, elapsed, 0.1)[0] == expected


def test_a_repeat_never_reports_finished():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0),), repeat=True)
    for t in (0.0, 0.5, 1.0, 100.0, 1000.5):
        color, next_change = sequencer.plan_at(seq, t, 0.1)
        assert color is not None
        assert next_change is not None


def test_a_repeating_sequences_first_stop_fades_from_the_last_stops_colour():
    """Unlike a one-shot: there is always something behind a repeat's first
    stop - the cycle that just finished - so it never dips to black at the
    seam where it wraps."""
    seq = Sequence(
        stops=(Stop(RED, hold_s=1.0, fade_s=0.5), Stop(GREEN, hold_s=1.0, fade_s=0.5)),
        repeat=True,
    )
    color, _ = sequencer.plan_at(seq, 0.0, 0.1)
    assert color == GREEN  # the last stop's colour, not black
    # Confirm it holds on the second cycle too (t=3.0 is the same phase as 0.0).
    color, _ = sequencer.plan_at(seq, 3.0, 0.1)
    assert color == GREEN


def test_a_fully_degenerate_repeat_holds_rather_than_dividing_by_zero():
    """Every stop dwells zero: there is no timeline to walk. Rather than
    crash on `elapsed % 0`, it holds the last stop and reports a positive
    wait so a caller that sleeps for what it is told never busy-loops.
    config.sequence_safe keeps this from happening to anything that reaches
    main.set_led for real."""
    seq = Sequence(stops=(Stop(RED, 0, 0), Stop(GREEN, 0, 0)), repeat=True)
    color, wait = sequencer.plan_at(seq, 3.0, 0.1)
    assert color == GREEN
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
        color, _ = sequencer.plan_at(seq, t, 0.25)
        levels_seen.append(color)
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
    assert sequencer.plan_at(seq, 0.0, 0.5)[0] == BLACK
    assert sequencer.plan_at(seq, 0.04, 0.5)[0] == BLACK
    assert sequencer.plan_at(seq, 0.05, 0.5)[0] == RED


def test_min_step_s_of_zero_is_continuous_stepping_collapsed_to_one_step():
    """No floor at all is the coarsest floor there is (one step), not a
    division by zero."""
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=1.0),), repeat=False)
    assert sequencer.plan_at(seq, 0.5, 0.0)[0] == BLACK
    assert sequencer.plan_at(seq, 1.0, 0.0)[0] == RED


# --- interpolation endpoints are exact, not approximated --------------------

def test_a_fades_start_is_exactly_the_previous_colour():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=2.0),), repeat=False)
    assert sequencer.plan_at(seq, 0.0, 0.1)[0] == BLACK


def test_a_fades_end_is_exactly_the_target_colour_not_a_near_miss():
    """The hold branch returns `stop.color` directly - never a `mix()` at
    level 1.0, which floating point could round a channel or two away from
    the exact target."""
    seq = Sequence(stops=(Stop("#123456", hold_s=1.0, fade_s=0.3),), repeat=False)
    assert sequencer.plan_at(seq, 0.3, 0.1)[0] == "#123456"
    assert sequencer.plan_at(seq, 0.5, 0.1)[0] == "#123456"


def test_zero_fade_is_a_hard_cut_with_no_interpolation_at_all():
    seq = Sequence(stops=(Stop(RED, hold_s=1.0, fade_s=0.0),), repeat=False)
    assert sequencer.plan_at(seq, 0.0, 0.1)[0] == RED


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
