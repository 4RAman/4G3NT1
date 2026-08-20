"""Stop lists: colours played in order, held for a while each.

[ladder.py](ladder.py) already names the shape this module fills in:

    ramp.py     driven by progress 0->1     interpolates between colours
    a stop list driven by the clock         plays colours in order
    a ladder    driven by a counter         picks a colour by divisibility

A ramp answers "how far through are you"; a ladder answers "what time is
it"; a stop list answers "what happens next" - it is a little playlist of
colours, each held for `hold_s` after arriving over `fade_s`. That third
question is genuinely different from the other two (nothing here is a
fraction of anything, and nothing here divides), which is why this is its
own module rather than a mode on `ramp` or `ladder`.

Pure by construction, like both of them: no clock, no device, no config.
`plan_at` is total over its declared domain and answers only "what colour
right now, and how long is that good for" - a caller supplies elapsed time
and gets back a colour to push and a number of seconds it may safely wait
before asking again. Nothing here knows *why* time is passing, which is
what will let this move onto the device unchanged (CLAUDE.md: "anything
pure survives the Stage-3 move").

**A sequence is not an effect.** `config.LedEffect` is one colour and a
style the *device* animates by itself (breathe, flash, rainbow...); a
`Sequence` is several colours the *host* walks through one at a time,
pushing each as a plain solid effect. That is why it cannot go in the
palette (CLAUDE.md: palette entries ship to the device, unattended - a
sequence is a schedule, not a byte the firmware can render alone) and why
driving one is main.py's job, not device.py's.

**Fades render stepped, not smooth.** Interpolating continuously would mean
a colour push every animation frame - fine on the device, dishonest over a
radio whose whole contract is fire-and-forget (see ble_device.py). Instead
a fade is cut into steps no shorter than `min_step_s`, each one landing on
a fresh `mix()` level; a fade shorter than one step degenerates to a single
hard cut from the previous colour, which is what asking for finer motion
than the caller is willing to spend on it should mean. Smooth belongs to
the device, once the device is the one drawing it (ROADMAP D5+).

Blending is the same straight per-channel RGB lerp as `ramp.mix` and
firmware/led.py's `_mix` - one *idea* of what a crossfade looks like, kept
as a second small implementation here rather than an import from ramp.py.
The two modules are siblings, not a hierarchy: each is a leaf a step in
CLAUDE.md's dependency graph could drop cleanly, and a four-line lerp is
cheap enough to duplicate that coupling two leaves together to save it
would cost more than it saves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .device import rgb_bytes


@dataclass(frozen=True)
class Stop:
    """One colour: arrive at it over `fade_s`, then hold for `hold_s`.

    Where the fade comes *from* is not this stop's business - it is always
    the previous stop's colour (or black, for a one-shot's very first stop;
    or the last stop's colour, for a repeating sequence's - see `Sequence`).
    That keeps a stop nameable and reorderable without carrying a pointer to
    whatever happens to precede it.
    """

    color: str          # "#rrggbb", the colour this stop arrives at
    hold_s: float = 0.5  # how long it stays, once arrived
    fade_s: float = 0.0  # how long arriving takes; 0 is a hard cut


@dataclass(frozen=True)
class Sequence:
    """An ordered stop list. `repeat=True` loops forever (until the next
    `set_led`); `repeat=False` plays once and is done.

    The two modes disagree about where the *first* stop fades from: a
    one-shot starts from black (there is nothing behind it to fade from -
    it is arriving out of nothing, the way a confirmation flash does), and a
    repeat starts from its own last stop (there is always something behind
    it - the cycle that just finished), so a repeating sequence never shows
    a black flicker at the seam where it wraps.
    """

    stops: tuple[Stop, ...]
    repeat: bool = True


def mix(first: str, second: str, level: float) -> str:
    """`level` 0..1 walks from `first` to `second`, component by component.

    Duplicated from `ramp.mix` rather than imported - see the module
    docstring. Kept byte-for-byte the same algorithm on purpose (it is what
    "a crossfade" means, here and in firmware/led.py's `_mix`), just not the
    same *symbol*.
    """
    start, end = rgb_bytes(first), rgb_bytes(second)
    return "#" + "".join(
        f"{round(a + (b - a) * level):02x}" for a, b in zip(start, end)
    )


def _fade_step(t_in_fade: float, fade_s: float, min_step_s: float) -> tuple[float, float]:
    """(interpolation level to show now, seconds until the next step) at
    `t_in_fade` seconds into a fade of length `fade_s`.

    The level shown for a step is the level *at its start*, held flat for
    the step's whole width - so the very first instant of a fade shows the
    untouched starting colour (level 0.0 exactly) and the fade only ever
    steps *toward* the target, never past it. The exact target colour
    appears the instant the fade ends, from the hold that follows - see
    `plan_at` - never as an interpolated near-miss.

    `min_step_s <= 0` collapses the fade to one step: a floor of zero is no
    floor, which degenerates to the coarsest possible stepping (one hard cut
    at the end) rather than to a division by it.
    """
    step_len = min_step_s if min_step_s > 0 else fade_s
    steps = max(1, math.ceil(fade_s / step_len - 1e-9))
    index = min(int(t_in_fade // step_len), steps - 1)
    level = min(1.0, index * step_len / fade_s)
    next_boundary = min((index + 1) * step_len, fade_s)
    return level, next_boundary - t_in_fade


@dataclass(frozen=True)
class _Span:
    """One stop's slice of the timeline: fade in [fade_at, fade_at+fade_s),
    then hold in [hold_at, hold_at+hold_s). Internal to `plan_at`."""

    fade_at: float
    fade_s: float
    hold_at: float
    hold_s: float
    from_color: str
    to_color: str


def _spans(seq: Sequence) -> tuple[tuple[_Span, ...], float]:
    """Lay `seq.stops` end to end on a timeline starting at 0. Returns the
    spans and the total length (one full cycle, for a repeat)."""
    prev = seq.stops[-1].color if seq.repeat else "#000000"
    spans = []
    t = 0.0
    for stop in seq.stops:
        fade_s = max(stop.fade_s, 0.0)
        hold_s = max(stop.hold_s, 0.0)
        hold_at = t + fade_s
        spans.append(_Span(t, fade_s, hold_at, hold_s, prev, stop.color))
        t = hold_at + hold_s
        prev = stop.color
    return tuple(spans), t


def plan_at(
    seq: Sequence, elapsed_s: float, min_step_s: float
) -> tuple[str | None, float | None]:
    """What to show `elapsed_s` into `seq`, and how long that is good for.

    Returns `(color, next_change_s)`:
      - `color` is the `'#rrggbb'` to push now, or `None` if a one-shot has
        already finished (`elapsed_s` at or past its total length).
      - `next_change_s` is how long the caller may wait before calling again
        - not necessarily until the colour visibly *changes* (a hold reports
        the time left in the hold, even though nothing moves during it), but
        long enough that nothing worth showing happens sooner. `None` only
        when `color` is `None`: a finished one-shot has nothing left to wait
        for.

    Total over its domain, like `ramp.color_at` and `ladder.color_at`:
    negative `elapsed_s` is clamped to 0, and an empty `seq.stops` reports
    `(None, None)` - there is no colour to show and nothing will ever
    change, which is what a one-shot with no stops means anyway.

    A repeating sequence whose stops all dwell zero (`hold_s == fade_s ==
    0` throughout) has no timeline to walk - every stop happens at the same
    instant. Rather than divide by that zero, it holds the last stop's
    colour and reports `min_step_s` (or 1.0 if that is also non-positive) as
    the wait, so a caller that sleeps for what it is told never busy-loops.
    In practice this never happens to a sequence that reached here through
    `main.set_led`: `config.sequence_safe` has already floored every stop
    that could repeat.
    """
    if elapsed_s < 0:
        elapsed_s = 0.0
    if not seq.stops:
        return None, None

    spans, total = _spans(seq)

    if seq.repeat:
        if total <= 0:
            return seq.stops[-1].color, (min_step_s if min_step_s > 0 else 1.0)
        t = elapsed_s % total
    else:
        if elapsed_s >= total:
            return None, None
        t = elapsed_s

    for span in spans:
        if t < span.fade_at + span.fade_s:
            level, remaining = _fade_step(t - span.fade_at, span.fade_s, min_step_s)
            return mix(span.from_color, span.to_color, level), remaining
        if t < span.hold_at + span.hold_s:
            return span.to_color, (span.hold_at + span.hold_s) - t

    # Floating-point can land `t` exactly on `total` (a repeat's modulo, or a
    # one-shot's last hold ending in a zero-width final stop) - the cycle
    # just completed. The last stop's colour is still the honest answer;
    # there is nothing more to wait for at *this* elapsed time; the next
    # call is what advances it.
    return spans[-1].to_color, 0.0
