# Stop lists, walked on the device.
#
# The rendering half of the host's aibutton/sequencer.py, ported rather than
# reimplemented: same span layout, same stepped fade, same "a hold reports the
# time left in it" contract. CLAUDE.md's mirrored-table rule applies - the two
# are kept honest by tests/test_apppkg.py, which samples both and compares.
#
# **Two differences from the host's copy, both deliberate.**
#
#   * Colours are (r, g, b) tuples, never "#rrggbb". The device has no reason
#     to own a hex parser: the package already carries raw bytes, so a string
#     would be a conversion in the one place with the least memory to spend.
#   * There is no Sequence object. A stop list is a tuple of stops and a repeat
#     flag, passed as two arguments, because building a span table per frame is
#     exactly the allocation ARCHITECTURE.md's "bounded by construction" rule
#     forbids. `plan_at` walks the stops accumulating time inline and allocates
#     nothing but the colour it returns.
#
# A stop is a 4-tuple: ((r, g, b), hold_s, fade_s, curve).
#
# Pure - no machine, no asyncio, no clock. That is what lets the host suite
# import and drive it, the same way it already does trigger.py.

import math

# Mirrors sequencer.CURVES *by index*, which is the wire encoding: the compiler
# writes the index and this reads it, so adding a curve means appending here
# and there in the same commit. test_apppkg.py fails on drift.
CURVE_LINEAR = 0
CURVE_EASE_IN = 1
CURVE_EASE_OUT = 2
CURVE_EASE_IN_OUT = 3
CURVE_EXPONENTIAL = 4

# How sharply `exponential` bends - sequencer._EXP_K, and it must stay equal.
_EXP_K = 4.0
# expm1(_EXP_K) on the host. Computed once here because MicroPython's math has
# exp everywhere and expm1 only on some ports, and a curve that raises on a
# board is worse than one that is a floating-point ulp different from the host.
_EXP_DEN = math.exp(_EXP_K) - 1.0


def shape(curve, level):
    """`level` 0..1 through `curve`. An unknown curve is linear rather than an
    error - this comes out of a decoded package, and a look that renders in the
    plainest possible way beats one that stops the button."""
    if level <= 0.0:
        return 0.0
    if level >= 1.0:
        return 1.0
    if curve == CURVE_EASE_IN:
        return level * level
    if curve == CURVE_EASE_OUT:
        return 1.0 - (1.0 - level) ** 2
    if curve == CURVE_EASE_IN_OUT:
        if level < 0.5:
            return 2 * level * level
        return 1.0 - 2 * (1.0 - level) ** 2
    if curve == CURVE_EXPONENTIAL:
        return (math.exp(_EXP_K * level) - 1.0) / _EXP_DEN
    return level


def mix(first, second, level):
    """Per-channel lerp between two (r, g, b) tuples."""
    return (
        int(round(first[0] + (second[0] - first[0]) * level)),
        int(round(first[1] + (second[1] - first[1]) * level)),
        int(round(first[2] + (second[2] - first[2]) * level)),
    )


def _fade_step(t_in_fade, fade_s, min_step_s):
    """(level to show now, seconds until the next step) - sequencer._fade_step.

    A step shows the level at its *start*, held flat for its whole width, so a
    fade only ever steps toward its target and never past it.
    """
    step_len = min_step_s if min_step_s > 0 else fade_s
    steps = max(1, int(math.ceil(fade_s / step_len - 1e-9)))
    index = min(int(t_in_fade // step_len), steps - 1)
    level = min(1.0, index * step_len / fade_s)
    next_boundary = min((index + 1) * step_len, fade_s)
    return level, next_boundary - t_in_fade


def total_s(stops):
    """One cycle's length. Zero for an empty list, which is what makes the
    divide in `plan_at` safe without a second check.

    **Accumulated in the host's exact order** - `(at + fade) + hold` per stop,
    never `at + (fade + hold)`. Those differ by one ulp, and one ulp is not a
    rounding difference here: it is the modulo at the seam landing at the *end*
    of the previous cycle instead of the start of the next one, which shows up
    as the wrong colour for one frame every time a show loops. Found by
    test_apppkg.py's conformance sweep, which is the entire reason it samples
    past a single cycle.
    """
    at = 0.0
    for stop in stops:
        at = at + (stop[2] if stop[2] > 0 else 0.0)
        at = at + (stop[1] if stop[1] > 0 else 0.0)
    return at


def plan_at(stops, repeat, elapsed_s, min_step_s):
    """What to show `elapsed_s` into the list, and how long that is good for.

    Returns `(rgb, wait_s)`, or `(None, None)` once a one-shot has finished -
    the same two-value contract as sequencer.plan_at, with a tuple where the
    host has a Frame. A repeat whose stops all dwell zero holds the last colour
    and reports `min_step_s`, so a caller that sleeps for what it is told can
    never busy-loop.
    """
    if not stops:
        return None, None
    if elapsed_s < 0:
        elapsed_s = 0.0

    total = total_s(stops)
    if repeat:
        if total <= 0:
            return stops[-1][0], (min_step_s if min_step_s > 0 else 1.0)
        t = elapsed_s % total
    else:
        if elapsed_s >= total:
            return None, None
        t = elapsed_s

    # A one-shot arrives out of nothing; a repeat arrives out of the cycle that
    # just finished, so it shows no black flicker at the seam.
    prev = stops[-1][0] if repeat else (0, 0, 0)
    at = 0.0
    for stop in stops:
        color = stop[0]
        hold_s = stop[1] if stop[1] > 0 else 0.0
        fade_s = stop[2] if stop[2] > 0 else 0.0
        hold_at = at + fade_s
        if t < hold_at:
            level, remaining = _fade_step(t - at, fade_s, min_step_s)
            return mix(prev, color, shape(stop[3], level)), remaining
        if t < hold_at + hold_s:
            return color, (hold_at + hold_s) - t
        at = hold_at + hold_s
        prev = color

    # Floating point can land t exactly on the total. The last colour is still
    # the honest answer; the next call is what advances it.
    return stops[-1][0], 0.0
