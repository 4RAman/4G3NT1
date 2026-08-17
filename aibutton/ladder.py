"""Subdivision ladders: telling time by which colour is flashing.

A ladder is a list of *rungs*, each an interval and a colour, plus a `base`
colour for the ticks that land on no rung at all. At any elapsed time, the
colour is the one on the **largest interval that divides that time**. That is
the whole idea, and the "largest wins" part is what makes it read like a clock
rather than like a list of rules:

    10s white   5s yellow   2s light blue   1s dark blue   base off

    t=0   every rung divides it            -> white   (the ten-second mark)
    t=1   only 1 does                      -> dark blue  (an odd second)
    t=2   2 and 1 do; 2 is larger          -> light blue (an even second)
    t=5   5 and 1 do; 5 is larger          -> yellow  (the five-second mark)
    t=0.5 nothing does                     -> base

So "even and odd seconds are different colours" needs no notion of parity: a
rung at 2s catches the even ones and a rung at 1s catches whatever is left.
Rungs compose by division, and the ladder is read top down.

**This is a third structure, not a variation on the other two**, and the
distinction is worth keeping:

    ramp.py     driven by progress 0->1     interpolates between colours
    a stop list driven by the clock         plays colours in order
    a ladder    driven by a counter         picks a colour by divisibility

A ramp answers "how far through are you"; a ladder answers "what time is it".
Neither can express the other - modular arithmetic is not interpolation - which
is why this is its own module rather than a mode on `ramp`.

Pure by construction: no clock, no device, no config. Nothing here knows what
is being timed, which is what lets a stopwatch, a countdown and a metronome
share it, and what lets the whole thing move onto the device in Stage 3
unchanged. Time arrives as a number of seconds someone else measured.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rungs are matched by division, and floating-point seconds do not divide
# exactly - 0.1 * 3 is not 0.30000000000000004's equal, and `2.0 % 0.5` can
# land on 0.4999999999999998. Everything is therefore compared in whole
# milliseconds, which is finer than any interval anyone would set and coarse
# enough that the arithmetic is exact.
_MS = 1000
# How far off a boundary a tick may be and still count as landing on it. One
# millisecond absorbs the rounding in converting a float number of seconds,
# and is far below anything the eye or the radio can resolve.
_SLOP_MS = 1


@dataclass(frozen=True)
class Rung:
    """One interval and the colour it wears."""

    every_s: float  # a colour change every this many seconds
    color: str      # "#rrggbb"


def color_at(rungs, elapsed_s: float, base: str = "#000000") -> str:
    """The colour at `elapsed_s`: the largest rung dividing it, else `base`.

    Total, like `ramp.color_at`. An empty ladder is `base`, negative time is
    treated as zero (a stopwatch has no time before it started), and a rung
    with a non-positive interval is skipped rather than dividing by zero -
    a hand-edited scene should cost you that rung, not the mode.

    Note that **t=0 matches every rung**, which is what you want: the moment a
    timer starts is a ten-second mark, and showing the top colour there is how
    you learn what the top colour means.
    """
    if elapsed_s < 0:
        elapsed_s = 0.0
    now_ms = round(elapsed_s * _MS)
    best: Rung | None = None
    for rung in rungs:
        interval_ms = round(rung.every_s * _MS)
        if interval_ms <= 0:
            continue
        offset = now_ms % interval_ms
        # Landing just *before* a boundary counts too, or a tick computed as
        # 1.9999s would miss the 2s rung it was scheduled for.
        if offset <= _SLOP_MS or interval_ms - offset <= _SLOP_MS:
            if best is None or interval_ms > round(best.every_s * _MS):
                best = rung
    return base if best is None else best.color


def tick_index(elapsed_s: float, tick_s: float) -> int:
    """Which tick `elapsed_s` falls in, at a cadence of `tick_s`.

    The caller's clock is not exact - a loop woken every 0.5s drifts - so a
    ladder is evaluated at the *tick's* nominal time (`index * tick_s`) rather
    than at the wall time it happened to wake up. Otherwise a tick scheduled
    for 2.000s that fires at 2.013s misses its rung and the second-marker
    colour silently never appears.
    """
    if tick_s <= 0 or elapsed_s <= 0:
        return 0
    return int(round(elapsed_s / tick_s))


def color_for_tick(rungs, index: int, tick_s: float, base: str = "#000000") -> str:
    """`color_at` for tick number `index` - the form a run loop wants.

    Evaluating at `index * tick_s` is what makes the ladder immune to the
    scheduler's jitter: the colours come out right even when the loop is late,
    which on a host that also talks to a radio it routinely is.
    """
    return color_at(rungs, index * tick_s, base)


def sorted_rungs(rungs) -> tuple[Rung, ...]:
    """Longest interval first - the order a ladder reads in, and the order the
    editor shows. Display only; `color_at` does not care."""
    return tuple(sorted(rungs, key=lambda rung: rung.every_s, reverse=True))
