"""Morse code as a stop list.

A dot is on for one unit, a dash for three; the gap inside a letter is one
unit, between letters three, between words seven. Every one of those is a
`sequencer.Stop` with a `hold_s` and no fade - so this needs no runtime of its
own, only a pure compiler from text to `tuple[Stop, ...]` (TODO 83). Everything
downstream (the walker, the flash floor, the device, the editor's preview)
treats the result as the ordinary stop list it is, which is also what lets it
survive the move onto the device unchanged.

Pure by construction, like [ramp.py](ramp.py) and [ladder.py](ladder.py)
beside it: no clock, no device, no config, and in particular no notion of the
flash floor - a speed arrives already chosen, and it is `config.py`'s job to
cap it against `min_flash_period_s` and say so, the same way every other
safety floor in this project has one call site outside the pure core.

Unknown characters are dropped, silently here - `unknown_chars` is the
companion query a caller uses to warn about them before compiling, which
keeps this module answering only "what does this text sound like" and never
"what should I tell the user".

`encode`'s colour may be a ramp rather than a single colour - see its own
docstring for why that stays a callable rather than an import of `ramp.py`.
"""

from __future__ import annotations

from .sequencer import Stop

# The international Morse alphabet: letters and digits only. Punctuation is
# deliberately absent rather than guessed at - it is "unknown", the same as
# any other character nobody has taught this table.
ALPHABET: dict[str, str] = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".",
    "F": "..-.", "G": "--.", "H": "....", "I": "..", "J": ".---",
    "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---",
    "P": ".--.", "Q": "--.-", "R": ".-.", "S": "...", "T": "-",
    "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--",
    "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}

# Concrete rather than a wire-code convention (TODO 83's speed field used to
# be "words per minute", which needs the PARIS-standard "a word is 50 units"
# assumption before it means anything): `dpm` is directly "how many dot-units
# fit in a minute", so one unit is 60/dpm seconds - no hidden assumption.
# Exposed so config.py can invert it when capping speed against the flash
# floor, without either side re-deriving the constant.
UNIT_S_PER_DPM = 60.0

# The pause before a repeated message starts over - twice a word gap (7
# units), so the loop boundary reads as "the message just ended" rather than
# as one more word break inside it. Without this a beacon's last symbol sits
# flush against its own first symbol on every lap - reported 2026-09-05 as
# "the repeats are getting stuck together", which is exactly that seam.
_REPEAT_GAP_UNITS = 14


def unknown_chars(message: str) -> tuple[str, ...]:
    """Characters in `message` that `encode` will drop, first-seen order,
    space excluded (a space is a word gap, not an unknown character).

    What `config.py` warns about before compiling, so the drop is dropped
    "with a warning, not guessed" (TODO 83) rather than silently.
    """
    seen: list[str] = []
    for ch in message.upper():
        if ch != " " and ch not in ALPHABET and ch not in seen:
            seen.append(ch)
    return tuple(seen)


def _timeline(message: str) -> tuple[tuple[bool, float], ...]:
    """`(is_on, units)` pairs - the rhythm of `message`, with no colour
    opinion at all. A space is a word gap (7 units); any other unrecognised
    character is dropped and costs nothing - not even a gap - so two spaces
    or a stray unknown character do not stutter the rhythm. Adjacent gaps
    (an unknown letter sitting between two words, say) are merged into one,
    which is also what keeps this the one place "how long is this gap"
    is computed - `encode` never has to ask whether two entries touch.

    Every "on" entry is exactly one dot or dash: two are never adjacent
    (a gap always separates them by construction), so merging never
    coarsens a symbol the way it may a gap.
    """
    entries: list[list] = []  # [is_on, units], mutated in place to merge

    def emit(is_on: bool, units: float) -> None:
        if entries and entries[-1][0] == is_on:
            entries[-1][1] += units
        else:
            entries.append([is_on, units])

    for word_index, word in enumerate(message.upper().split(" ")):
        if word_index > 0:
            emit(False, 7)
        first_letter = True
        for ch in word:
            code = ALPHABET.get(ch)
            if code is None:
                continue
            if not first_letter:
                emit(False, 3)
            for symbol_index, symbol in enumerate(code):
                if symbol_index > 0:
                    emit(False, 1)
                emit(True, 3 if symbol == "-" else 1)
            first_letter = False

    return tuple((is_on, units) for is_on, units in entries)


def encode(
    message: str, unit_s: float, color, off: str = "#000000", repeat: bool = False,
) -> tuple[Stop, ...]:
    """`message` as a stop list: `color` for a dot/dash, `off` for the gaps.

    `color` is a plain colour, or a callable `(progress: float) -> str` - a
    ramp sampled once per symbol at how far *into the message* that symbol
    falls (0.0 at the first dot or dash, approaching 1.0 at the last). That
    is the whole mechanism for "the colour changes across the message": this
    module stays ignorant of what the callable does - a ramp, a lookup table,
    a solid colour in disguise - the same way a sort key does not need to
    know what it is sorting. `config.py` is the one place that knows about
    `ramp.py`; this file only ever calls what it is handed. `total_units` -
    and therefore every symbol's `progress` - is fixed before `repeat`'s gap
    is added, so a looping ramp still spans the message itself rather than
    being stretched thin across the silence after it.

    `repeat` is set by a caller that means to loop this as a beacon
    (`sequencer.Sequence.repeat`): it appends `_REPEAT_GAP_UNITS` of `off`
    after the last symbol, or the walker jumps straight from that symbol back
    to the first one with no pause at all - the message reads as if it never
    stopped. A one-shot has nothing after it to separate itself from, so it
    gets no such gap, and neither does an empty message.

    Empty in, empty out: a message that is all spaces or all unknown
    characters compiles to `()`, which is `config.py`'s cue to fall back to
    the default look exactly as an empty `stops` list already does.
    """
    timeline = _timeline(message)
    total_units = sum(units for _, units in timeline)
    if repeat and timeline:
        timeline = (*timeline, (False, _REPEAT_GAP_UNITS))
    stops: list[Stop] = []
    elapsed = 0.0
    for is_on, units in timeline:
        if is_on:
            progress = elapsed / total_units if total_units else 0.0
            stop_color = color(progress) if callable(color) else color
        else:
            stop_color = off
        stops.append(Stop(color=stop_color, hold_s=units * unit_s, fade_s=0.0))
        elapsed += units
    return tuple(stops)
