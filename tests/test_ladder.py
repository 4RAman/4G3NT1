"""Subdivision ladders - the "what time is it" light.

The scenarios are written against the default ladder from the request, because
that is the one someone has to be able to read across a room: white on the ten,
yellow on the five, light blue on even seconds, dark blue on odd.
"""

import pytest

from aibutton import ladder
from aibutton.ladder import Rung

WHITE, YELLOW, LIGHT, DARK, OFF = "#ffffff", "#ffff00", "#66ccff", "#0033aa", "#000000"

DEFAULT = (
    Rung(10.0, WHITE),
    Rung(5.0, YELLOW),
    Rung(2.0, LIGHT),
    Rung(1.0, DARK),
)


@pytest.mark.parametrize(
    "elapsed, expected",
    [
        (0.0, WHITE),    # the start is a ten-second mark, which is how you
                         # learn what white means
        (0.5, OFF),      # between seconds: no rung, so the base
        (1.0, DARK),     # odd second
        (1.5, OFF),
        (2.0, LIGHT),    # even second
        (3.0, DARK),
        (4.0, LIGHT),
        (5.0, YELLOW),   # 5 divides it and beats 1
        (6.0, LIGHT),
        (7.0, DARK),
        (8.0, LIGHT),
        (9.0, DARK),
        (10.0, WHITE),   # 10 beats 5, 2 and 1
        (15.0, YELLOW),
        (20.0, WHITE),
    ],
)
def test_the_default_ladder_reads_like_a_clock(elapsed, expected):
    assert ladder.color_at(DEFAULT, elapsed, OFF) == expected


def test_parity_falls_out_of_divisibility_rather_than_being_a_rule():
    """'Even and odd seconds differ' needs no notion of parity: 2s catches the
    even ones, 1s catches whatever is left."""
    evens = [ladder.color_at(DEFAULT, t, OFF) for t in (2, 4, 6, 8)]
    odds = [ladder.color_at(DEFAULT, t, OFF) for t in (1, 3, 7, 9)]
    assert set(evens) == {LIGHT}
    assert set(odds) == {DARK}


def test_the_largest_matching_rung_wins_whatever_order_they_are_listed_in():
    """Config order must not decide what a light means."""
    shuffled = (Rung(1.0, DARK), Rung(10.0, WHITE), Rung(2.0, LIGHT), Rung(5.0, YELLOW))
    for t in (0, 1, 2, 5, 10):
        assert ladder.color_at(shuffled, t, OFF) == ladder.color_at(DEFAULT, t, OFF)


# --- totality: a bad ladder costs a colour, never the mode ------------------

def test_an_empty_ladder_is_the_base_colour():
    assert ladder.color_at((), 3.0, OFF) == OFF


def test_a_rung_with_no_interval_is_skipped_not_divided_by():
    assert ladder.color_at((Rung(0.0, WHITE), Rung(1.0, DARK)), 3.0, OFF) == DARK
    assert ladder.color_at((Rung(-2.0, WHITE),), 3.0, OFF) == OFF


def test_time_before_the_start_is_the_start():
    assert ladder.color_at(DEFAULT, -5.0, OFF) == WHITE


# --- the arithmetic has to survive floats ----------------------------------

@pytest.mark.parametrize("t", [0.1, 0.2, 0.3, 0.7, 1.1, 2.2, 3.3])
def test_fractional_intervals_divide_exactly(t):
    """0.1 * 3 is not 0.3 in binary floating point, so the whole thing is done
    in whole milliseconds - a ladder that worked at 1s and failed at 0.1s
    would be the worst kind of intermittent."""
    fine = (Rung(0.1, WHITE),)
    assert ladder.color_at(fine, t, OFF) == WHITE


def test_a_tick_that_fires_slightly_late_still_lands_on_its_rung():
    """The loop is woken by a scheduler that also talks to a radio; 2.0s
    routinely arrives as 2.013s."""
    assert ladder.color_at(DEFAULT, 1.9999, OFF) == LIGHT
    assert ladder.color_at(DEFAULT, 2.0004, OFF) == LIGHT


def test_a_tick_that_is_genuinely_between_marks_is_not_snapped_to_one():
    """The slop absorbs jitter, not a real gap - or every colour would smear
    into its neighbours."""
    assert ladder.color_at(DEFAULT, 2.4, OFF) == OFF


# --- evaluating by tick rather than by wall time ---------------------------

def test_ticks_are_evaluated_at_their_nominal_time():
    """Immunity to drift is the whole reason color_for_tick exists: tick 4 at
    0.5s is 2.0s by definition, however late the loop actually woke."""
    assert ladder.color_for_tick(DEFAULT, 4, 0.5, OFF) == LIGHT
    assert ladder.color_for_tick(DEFAULT, 20, 0.5, OFF) == WHITE
    assert ladder.color_for_tick(DEFAULT, 1, 0.5, OFF) == OFF


def test_twenty_half_second_ticks_is_the_ten_second_mark():
    """The request, stated as a test: 'every 20 flashes at .5s'."""
    whites = [i for i in range(41) if ladder.color_for_tick(DEFAULT, i, 0.5, OFF) == WHITE]
    assert whites == [0, 20, 40]


def test_tick_index_rounds_to_the_nearest_tick():
    assert ladder.tick_index(2.03, 0.5) == 4
    assert ladder.tick_index(0.0, 0.5) == 0
    assert ladder.tick_index(5.0, 0.0) == 0  # a zero cadence has no ticks


def test_sorted_rungs_reads_top_down():
    assert [r.every_s for r in ladder.sorted_rungs(DEFAULT)] == [10.0, 5.0, 2.0, 1.0]
