"""Turning MIDI clock pulses into a tempo. Pure arithmetic, no ports.

**What a DAW actually sends.** MIDI Clock is a single byte, `0xF8`, sent
**24 times per quarter note** - the tempo is never transmitted, only implied by
how fast the pulses arrive. `0xFA` starts, `0xFB` continues and `0xFC` stops.
Do not confuse this with MIDI Time Code, which carries SMPTE *position* and
says nothing about tempo; a DAW offering both will happily send the wrong one.

**Why the estimator is a median and not a mean.** These pulses arrive on a
driver thread through a USB or virtual cable, and one late delivery is normal:
Windows timer granularity, a garbage collection, the DAW's own buffer. A mean
lets a single 40 ms straggler drag the answer; a median over a beat's worth of
intervals ignores it entirely. The cost is that a *deliberate* tempo change
takes half a window to be believed, which is the right trade - a metronome that
lurched on every scheduling hiccup would be worse than one that settles in half
a beat.

**Everything here is a pure function over a list of timestamps**, which is the
shape CLAUDE.md asks for and the reason none of it needs a MIDI port to test:
jitter, tempo changes and dropouts are all just lists. It is also the half that
survives if any of this ever moves off the host.
"""

from __future__ import annotations

from statistics import median

# The MIDI spec's clock rate. Not a tunable - a device sending any other rate
# is not sending MIDI clock.
PULSES_PER_QUARTER = 24

# System real-time bytes this understands. They are single bytes and may appear
# *between* the bytes of another message, which is why a reader must check for
# them before anything else.
CLOCK = 0xF8
START = 0xFA
CONTINUE = 0xFB
STOP = 0xFC

# One beat of pulses. Long enough that a stray interval is outvoted, short
# enough that a tempo change lands within about half a beat.
DEFAULT_WINDOW = PULSES_PER_QUARTER

# Outside this, the answer is not a tempo - it is a dropout, a device sending
# something that is not clock, or the first pulse after a long silence. Bounds
# rather than clamps: a wrong number confidently reported is worse than none.
MIN_BPM = 20.0
MAX_BPM = 400.0


def bpm_from_intervals(intervals) -> float | None:
    """Tempo implied by the gaps between consecutive clock pulses.

    Returns None rather than a guess when there is nothing usable - too few
    intervals, or an answer outside what a tempo can be. Callers show the last
    good tempo instead, because a metronome that blanks on one dropped pulse is
    less useful than one that keeps time.
    """
    usable = [gap for gap in intervals if gap > 0]
    if not usable:
        return None
    typical = median(usable)
    bpm = 60.0 / (typical * PULSES_PER_QUARTER)
    return bpm if MIN_BPM <= bpm <= MAX_BPM else None


def bpm_from_pulses(timestamps, window: int = DEFAULT_WINDOW) -> float | None:
    """Tempo from the arrival times of recent clock pulses.

    `window` is counted in *pulses*, so the most recent `window` intervals are
    what decides the answer and everything older is already forgotten.
    """
    recent = list(timestamps)[-(window + 1):]
    if len(recent) < 2:
        return None
    return bpm_from_intervals(
        [b - a for a, b in zip(recent, recent[1:])]
    )


def is_stale(timestamps, now: float, beats: float = 2.0,
             bpm: float | None = None) -> bool:
    """Has the clock stopped without saying so?

    A DAW that is quit, disconnected or paused mid-stream sends no `0xFC` - the
    pulses simply stop. Silence longer than `beats` beats at the current tempo
    is the only way to notice, and it is deliberately generous: at 120 BPM two
    beats is a full second, far longer than any plausible gap between pulses
    that are meant to be 21 ms apart.
    """
    if not timestamps:
        return True
    tempo = bpm or 120.0
    return (now - timestamps[-1]) > (60.0 / tempo) * beats
