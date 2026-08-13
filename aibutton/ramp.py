"""Colour ramps: what colour something is when it is part-way through.

A ramp is a list of *stops*, each a colour pinned at a position from 0.0 (the
start) to 1.0 (the end). `color_at` blends between the two stops either side of
a progress value. That is the whole idea.

Pure by construction - no clock, no device, no config, and nothing here knows
what is progressing. That is deliberate, because the same object answers four
different questions:

    a countdown        how much time is left
    a Pomodoro block   how far through this block you are
    a held button      which hold level you are in (ROADMAP D5)
    a stopwatch        how close to a target you are

Only the first has a consumer today. The rest are why this is its own module
rather than a corner of [config.py](config.py), and why nothing below mentions
seconds.

**A ramp is not an effect.** An effect (`config.LedEffect`) says *how* the
light moves - a style, a period, one or two colours. A ramp says *which*
colour, given a fraction. They compose: a countdown flashes at a fixed period
while the ramp walks its colour from red to violet. Keeping them separate is
what stops "flash" and "fade slowly across the whole timer" from being two
settings that fight.

Blending is a straight per-channel RGB lerp, matching
[firmware/led.py](../firmware/led.py)'s `_mix` - one definition of what a
crossfade between two colours looks like, so a ramp rendered on the host and a
`fade` rendered on the device agree. It is not perceptually uniform, and a lerp
between opposite hues passes through something muddy; the answer is to put a
stop in the middle, which is exactly what the default countdown ramp does.

Positions, not durations, and hence no bounds on how long anything takes: a
ramp over a two-minute egg timer and a ramp over a two-hour deadline are the
same object.
"""

from __future__ import annotations

from dataclasses import dataclass

from .device import rgb_bytes

# rgb_bytes is imported rather than re-derived because device.py already owns
# "what does '#rrggbb' mean in bytes", imports nothing from this package, and
# is the module the wire encoding uses. A third hex parser would be a mirrored
# table with nothing testing the mirror.


@dataclass(frozen=True)
class Stop:
    """One colour, pinned somewhere along the ramp."""

    at: float   # 0.0 = the start, 1.0 = the end
    color: str  # "#rrggbb"


def even(colors) -> tuple[Stop, ...]:
    """Spread `colors` evenly from 0 to 1 - what a bare list of colours means.

    One colour is a constant ramp rather than a degenerate one: it holds that
    colour throughout, which is a reasonable thing to ask for and would
    otherwise be a division by zero.
    """
    colors = tuple(colors)
    if not colors:
        return ()
    if len(colors) == 1:
        return (Stop(0.0, colors[0]),)
    last = len(colors) - 1
    return tuple(Stop(i / last, color) for i, color in enumerate(colors))


def color_at(stops, progress: float) -> str:
    """The colour `progress` of the way along `stops`.

    Total: `progress` is clamped to 0..1, an empty ramp is black, and stops are
    sorted here rather than assumed sorted. Sorting on every call is a
    non-issue - a ramp is a handful of stops and this runs a few times a minute
    - and the alternative is a precondition that fails silently and looks like
    a colour bug.
    """
    ordered = sorted(stops, key=lambda stop: stop.at)
    if not ordered:
        return "#000000"
    fraction = 0.0 if progress < 0.0 else (1.0 if progress > 1.0 else progress)
    if fraction <= ordered[0].at:
        return ordered[0].color
    for low, high in zip(ordered, ordered[1:]):
        if fraction <= high.at:
            span = high.at - low.at
            # Two stops pinned at the same position: the later one wins rather
            # than dividing by zero, which makes a hard edge expressible.
            level = 1.0 if span <= 0 else (fraction - low.at) / span
            return mix(low.color, high.color, level)
    return ordered[-1].color


def mix(first: str, second: str, level: float) -> str:
    """`level` 0..1 walks from `first` to `second`, component by component."""
    start, end = rgb_bytes(first), rgb_bytes(second)
    return "#" + "".join(
        f"{round(a + (b - a) * level):02x}" for a, b in zip(start, end)
    )


def differs(first: str, second: str, minimum: int) -> bool:
    """Whether two colours are at least `minimum` apart on any channel.

    The point is not aesthetics but traffic: a ramp evaluated every second over
    a one-hour countdown would push 3600 palette writes down a radio whose
    whole contract is fire-and-forget. Pushing only on a visible change bounds
    that to a couple of hundred for the entire sweep, whatever the duration.
    """
    return any(
        abs(a - b) >= minimum for a, b in zip(rgb_bytes(first), rgb_bytes(second))
    )
