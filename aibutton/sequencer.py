"""Stop lists: colours played in order, held for a while each.

Three questions, three sibling modules, one light:

    ramp.py     driven by progress 0->1   "how far through are you"
    a stop list driven by the clock       "what happens next"
    a ladder    driven by a counter       "what time is it"

A stop list is a little playlist of colours, each held for `hold_s` after
arriving over `fade_s`. Nothing in it is a fraction of anything and nothing
divides, which is why it is not a mode on `ramp` or `ladder`.

Pure like both of them: no clock, no device, no config. A caller supplies
elapsed time and gets back a colour to push and how long that is good for;
nothing here knows *why* time is passing, which is what lets it move onto the
device unchanged (CLAUDE.md: "anything pure survives the Stage-3 move").

**A sequence is not an effect.** `config.LedEffect` is one colour plus a style
the *device* animates by itself; a `Sequence` is several colours the *host*
walks through one at a time, pushing each as a plain solid. Hence it cannot go
in the palette (a palette entry ships to the device and renders unattended - a
sequence is a schedule) and driving one is main.py's job, not device.py's.

**Fades render stepped, not smooth.** Interpolating continuously would mean a
colour push every animation frame - fine on the device, dishonest over a radio
whose whole contract is fire-and-forget (see ble_device.py). A fade is cut into
steps no shorter than `min_step_s`, and one shorter than a single step
degenerates to a hard cut from the previous colour. Smooth belongs to the
device once the device is drawing it (ROADMAP D5+); `sample_at` is the one
deliberate exception, and says why.

Blending is the same per-channel RGB lerp as `ramp.mix` and firmware/led.py's
`_mix`, kept as a second small implementation rather than an import: these are
sibling leaves in CLAUDE.md's dependency graph, and coupling two of them to
save a four-line lerp would cost more than it saves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .device import rgb_bytes


# How a fade is shaped between its two colours (TODO 36b). Each maps 0..1 to
# 0..1 monotonically with f(0)=0 and f(1)=1, which is what keeps `_fade_step`'s
# "never step past the target" guarantee true whichever one is chosen.
#
# Asymmetric *periodic* motion - a breathe whose peak is narrower than its
# valley - is deliberately not here: that is a property of a device-rendered
# style, and approximating it as a stop list is the whole reason this table
# exists instead of a protocol change (TODO 36).
CURVES = ("linear", "ease_in", "ease_out", "ease_in_out", "exponential")

# How sharply `exponential` bends. 4.0 is about the steepest that still reads
# as a fade rather than a cut at the 50 ms step floor a radio-driven fade is
# quantised to (see the module docstring).
_EXP_K = 4.0


def shape(curve: str, level: float) -> float:
    """`level` 0..1 through `curve`. An unknown curve is linear rather than an
    error: this is reached from parsed config, and a look that renders in the
    plainest possible way beats one that raises."""
    if level <= 0.0:
        return 0.0
    if level >= 1.0:
        return 1.0
    if curve == "ease_in":
        return level * level
    if curve == "ease_out":
        return 1.0 - (1.0 - level) ** 2
    if curve == "ease_in_out":
        return 2 * level * level if level < 0.5 else 1.0 - 2 * (1.0 - level) ** 2
    if curve == "exponential":
        # Normalised so f(1) is exactly 1 - an un-normalised expm1 curve would
        # stop short of the target colour, which `_fade_step` is written to
        # guarantee never happens.
        return math.expm1(_EXP_K * level) / math.expm1(_EXP_K)
    return level


@dataclass(frozen=True)
class Stop:
    """One colour: arrive at it over `fade_s`, then hold for `hold_s`.

    Where the fade comes *from* is the previous stop's colour (or black for a
    one-shot's first stop, or the last stop's colour for a repeat - see
    `Sequence`), which keeps a stop nameable and reorderable without carrying
    a pointer to whatever happens to precede it.

    **A stop is one flat colour, and a hold does not move** (TODO 36e). A stop
    briefly carried a `style`/`period_s` of its own, so that one node of a list
    could be "flashing yellow"; it was removed because a list that both walks
    colours *and* animates inside them is two clocks on one light and nobody
    could say from the editor which one they were setting. Everything it
    expressed is expressible as more stops - a flash is on, off, on - and that
    form is the one the editor can show you honestly.
    """

    color: str           # "#rrggbb", the colour this stop arrives at
    hold_s: float = 0.5  # how long it stays, once arrived
    fade_s: float = 0.0  # how long arriving takes; 0 is a hard cut
    curve: str = "linear"   # how the fade is shaped - see CURVES


# What moves a sequence along (TODO 36d):
#
#   clock      seconds; walked by `plan_at`, which returns a wait
#   progress   0..1; sampled by `sample_at` from whatever the app is doing
#   beats      a count; sampled by `sample_at` from a tempo
#
# **Walked versus sampled is the real distinction**, not the unit. A
# clock-driven sequence owns its own position and a caller only has to keep
# asking; the other two are *parameterised from outside themselves* - a
# countdown owns its progress, a metronome its beat - so nothing can render one
# without an app underneath supplying the number. That is why a progress-driven
# look is meaningless on IDLE, and why `config` rather than this module decides
# where each drive may be bound.
#
# For `progress` and `beats` a stop's `hold_s`/`fade_s` are read as *weights* in
# that unit rather than as seconds; the names keep the `_s` because renaming
# them would be a config break for the one drive that has always been seconds.
DRIVES = ("clock", "progress", "beats")


@dataclass(frozen=True)
class Sequence:
    """An ordered stop list. `repeat=True` loops until the next `set_led`;
    `repeat=False` plays once and is done.

    The two disagree about where the *first* stop fades from: a one-shot starts
    from black (it is arriving out of nothing, the way a confirmation flash
    does) and a repeat starts from its own last stop - the cycle that just
    finished - so a repeat never shows a black flicker at the seam where it
    wraps.
    """

    stops: tuple[Stop, ...]
    repeat: bool = True
    drive: str = "clock"  # what moves it along - see DRIVES


def mix(first: str, second: str, level: float) -> str:
    """`level` 0..1 walks from `first` to `second`, component by component.

    Duplicated from `ramp.mix` rather than imported - see the module docstring.
    Deliberately the same algorithm, just not the same *symbol*.
    """
    start, end = rgb_bytes(first), rgb_bytes(second)
    return "#" + "".join(
        f"{round(a + (b - a) * level):02x}" for a, b in zip(start, end)
    )


def _fade_step(t_in_fade: float, fade_s: float, min_step_s: float) -> tuple[float, float]:
    """(interpolation level to show now, seconds until the next step) at
    `t_in_fade` seconds into a fade of length `fade_s`.

    A step shows the level *at its start*, held flat for its whole width - so
    the first instant of a fade shows the untouched starting colour (level 0.0
    exactly) and the fade only ever steps *toward* the target, never past it.
    The exact target appears the instant the fade ends, from the hold that
    follows (see `plan_at`), never as an interpolated near-miss.

    `min_step_s <= 0` collapses the fade to one step: a floor of zero is no
    floor, which degenerates to the coarsest possible stepping rather than to a
    division by it.
    """
    step_len = min_step_s if min_step_s > 0 else fade_s
    steps = max(1, math.ceil(fade_s / step_len - 1e-9))
    index = min(int(t_in_fade // step_len), steps - 1)
    level = min(1.0, index * step_len / fade_s)
    next_boundary = min((index + 1) * step_len, fade_s)
    return level, next_boundary - t_in_fade


@dataclass(frozen=True)
class Frame:
    """What to show at one instant: a colour, held.

    A one-field dataclass rather than a bare string, and deliberately kept as
    one: it is the return type of both `plan_at` and `sample_at`, and the
    callers that pattern-match on it should not have to change shape the day a
    frame carries something besides a colour again. `None` still means "there
    is nothing to show", which a bare string could only have said as `""`.
    """

    color: str


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
    curve: str


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
        spans.append(_Span(t, fade_s, hold_at, hold_s, prev, stop.color, stop.curve))
        t = hold_at + hold_s
        prev = stop.color
    return tuple(spans), t


def plan_at(
    seq: Sequence, elapsed_s: float, min_step_s: float
) -> tuple[Frame | None, float | None]:
    """What to show `elapsed_s` into `seq`, and how long that is good for.

    Returns `(frame, next_change_s)`:
      - `frame` is what to push now, or `None` if a one-shot has already
        finished. One flat colour either way: the interpolated one mid-fade,
        the stop's own during its hold (see `Stop`).
      - `next_change_s` is how long the caller may wait before calling again -
        not necessarily until the colour visibly *changes* (a hold reports the
        time left in it, even though nothing moves), but long enough that
        nothing worth showing happens sooner. `None` only when `frame` is.

    Total over its domain, like `ramp.color_at` and `ladder.color_at`: negative
    `elapsed_s` clamps to 0, and an empty `seq.stops` reports `(None, None)`.

    A repeating sequence whose stops all dwell zero has no timeline to walk -
    every stop happens at the same instant. Rather than divide by that zero it
    holds the last stop's colour and reports `min_step_s` (or 1.0 if that is
    also non-positive) as the wait, so a caller that sleeps for what it is told
    never busy-loops. Anything that arrived here through `main.set_led` has
    already been floored by `config.sequence_safe`.
    """
    if elapsed_s < 0:
        elapsed_s = 0.0
    if not seq.stops:
        return None, None

    spans, total = _spans(seq)

    if seq.repeat:
        if total <= 0:
            return (
                Frame(seq.stops[-1].color),
                (min_step_s if min_step_s > 0 else 1.0),
            )
        t = elapsed_s % total
    else:
        if elapsed_s >= total:
            return None, None
        t = elapsed_s

    for span in spans:
        if t < span.fade_at + span.fade_s:
            level, remaining = _fade_step(t - span.fade_at, span.fade_s, min_step_s)
            # The curve shapes *which* colour this step lands on; nothing about
            # a fade is periodic, so there is one colour to report and no rate.
            return (
                Frame(mix(span.from_color, span.to_color, shape(span.curve, level))),
                remaining,
            )
        if t < span.hold_at + span.hold_s:
            return Frame(span.to_color), (span.hold_at + span.hold_s) - t

    # Floating-point can land `t` exactly on `total` (a repeat's modulo, or a
    # one-shot's last hold ending in a zero-width final stop). The last stop's
    # colour is still the honest answer, nothing is left to wait for at *this*
    # elapsed time, and the next call is what advances it.
    return Frame(spans[-1].to_color), 0.0


def span_total(seq: Sequence) -> float:
    """One cycle's length in the sequence's own unit - seconds for `clock`,
    fractions for `progress`, beats for `beats`.

    Exposed because a *sampled* sequence needs it and a walked one does not:
    `sample_at` has to turn "40% through" into a position on a timeline whose
    length only this module knows.
    """
    return _spans(seq)[1]


def sample_at(seq: Sequence, position: float) -> Frame | None:
    """The frame at `position`, a *fraction* 0..1 rather than an elapsed time.
    The sampled counterpart of `plan_at` (TODO 36d).

    `plan_at` answers "what now, and how long may I sleep" - the question a
    caller with a clock asks. This answers only "what at this point", which is
    what a caller with a *progress bar* asks: a countdown 40% through already
    has its own tick and simply wants the colour that belongs to 40%. That is
    also why no wait comes back - when the next frame is due depends on how
    fast the app's own number moves, which is the app's business.

    **Fades interpolate continuously here, and that is the one place this
    disagrees with `plan_at` on purpose.** The 50 ms stepping exists because a
    walked sequence pushes every frame over a radio, so promising motion finer
    than the radio can carry would be dishonest. A sampled sequence pushes only
    when the app ticks - the app's rate *is* the rate - and the caller decides
    whether a frame is worth sending (`main.sampled_paint` drops one that has
    not visibly moved). Quantising on top of that would lose gradient for
    nothing: a 1 s countdown tick against a 0.05 s step is already twenty times
    coarser than the floor it would be obeying.

    Out-of-range positions are handled rather than rejected, and how depends on
    `repeat`: a repeating sequence wraps (which is what makes `beats` useful -
    a four-beat pattern over an eight-beat bar), a one-shot clamps to its ends.
    Clamping rather than returning `None` is the other difference from
    `plan_at`: a progress bar that reaches 1.0 should show the last stop, not
    go dark, because "finished" is a state a countdown *holds*.
    """
    if not seq.stops:
        return None
    spans, total = _spans(seq)
    if total <= 0:
        return Frame(seq.stops[-1].color)

    position = position % 1.0 if seq.repeat else min(max(position, 0.0), 1.0)
    t = position * total

    for span in spans:
        if span.fade_s > 0 and t < span.fade_at + span.fade_s:
            level = shape(span.curve, (t - span.fade_at) / span.fade_s)
            return Frame(mix(span.from_color, span.to_color, level))
        if t < span.hold_at + span.hold_s:
            return Frame(span.to_color)

    return Frame(spans[-1].to_color)


# --- readout: a value played as blinks (TODO 15 and 17) --------------------
#
# TODO 17's finding is why this looks the way it does: one LED has three
# channels, and only count/rhythm is good at *exact* integers - hue is good at
# proportion, not digits. So a readout is blinks, not colours, which is what
# lets it survive this build's measured ring colour cast, a warm room, and a
# colourblind reader (see hardware gotchas in CLAUDE.md).

_READOUT_TENS_ON_S = 0.5
_READOUT_TENS_OFF_S = 0.35
_READOUT_GROUP_GAP_S = 0.7
_READOUT_UNITS_ON_S = 0.18
_READOUT_UNITS_OFF_S = 0.18
_READOUT_ZERO_HOLD_S = 0.4
_READOUT_ZERO_COLOR = "#404040"  # dim neutral - not either digit's colour
_READOUT_MAX = 99
_BLACK = "#000000"


def _digit_pulses(count: int, color: str, on_s: float, off_s: float) -> list[Stop]:
    """`count` hard-cut pulses of `color`, `on_s` each, separated by `off_s` of
    black - no trailing gap after the last pulse, so whatever comes next (the
    group gap, or the end of the sequence) decides what follows."""
    stops: list[Stop] = []
    for i in range(count):
        stops.append(Stop(color, hold_s=on_s))
        if i < count - 1:
            stops.append(Stop(_BLACK, hold_s=off_s))
    return stops


def readout(
    value: int, tens_color: str = "#ff8800", units_color: str = "#3399ff"
) -> Sequence:
    """`value` as blinks: the tens digit as slow pulses in `tens_color`, the
    units digit as quick ones in `units_color` - 27 is two slow, then seven
    quick, reading like an abacus with no legend needed.

    `value` is clamped to 0..99. 0 is a special case: a single dim neutral blink
    (`_READOUT_ZERO_COLOR`, matching neither digit's colour) rather than zero
    pulses, so "counted zero" reads differently from "nothing happened".

    A zero *digit* contributes no pulses, and the group gap appears only when
    both groups have a pulse to separate - so "7" starts straight into the quick
    pulses with no leading pause, and "20" ends after the slow ones with no
    trailing gap to nothing.

    One-shot, always: a readout is a value at a moment, not something to loop.
    Every stop's dwell clears `SAFE_MIN_PERIOD_S / 2` (~0.167s) by construction,
    so it never leans on `config.sequence_safe`'s floor - which still runs
    centrally in `main.set_led`.
    """
    value = max(0, min(_READOUT_MAX, value))
    if value == 0:
        return Sequence(
            stops=(Stop(_READOUT_ZERO_COLOR, hold_s=_READOUT_ZERO_HOLD_S),),
            repeat=False,
        )

    tens, units = divmod(value, 10)
    stops: list[Stop] = []
    if tens:
        stops += _digit_pulses(
            tens, tens_color, _READOUT_TENS_ON_S, _READOUT_TENS_OFF_S
        )
    if tens and units:
        stops.append(Stop(_BLACK, hold_s=_READOUT_GROUP_GAP_S))
    if units:
        stops += _digit_pulses(
            units, units_color, _READOUT_UNITS_ON_S, _READOUT_UNITS_OFF_S
        )
    return Sequence(stops=tuple(stops), repeat=False)
