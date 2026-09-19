"""Turn a number into a stop list - the general form of `sequencer.readout`
(TODO 91), which only knows a tens digit and a units digit and only up to 99.

Four independent compilers, one per scheme - a caller picks exactly one to
configure, so this is one pure module with four functions rather than four
half-features:

    morse        the digits spoken as Morse - `morse.encode` unchanged
    place_value  a colour per decimal place, N pulses per place (the
                 existing tens/units idea, generalised past two places)
    binary       two colours, one per bit, most-significant first
    hour_colors  N pulses in one colour drawn from a wheel by the value
                 itself - "a colour per hour, 1-12" (TODO 106)

All four take a value of any size - `_READOUT_MAX` was `sequencer.readout`'s
cap, not a property of "reading a number as light", so there is none here -
and return a plain `tuple[sequencer.Stop, ...]`, the same shape
`morse.encode` already returns. Nothing downstream needs to know which
scheme produced it: it is played as the one-shot stop list it is, by the
same walker every other sequence uses, which is what lets it move onto the
device unchanged (CLAUDE.md: "anything pure survives the Stage-3 move").

This module intentionally does not touch TODO 91's other half - whether
counters become a top-level pool - that has been declined; this only builds
the compiler the "Done when" asks for.

Pure like `ramp.py`, `ladder.py` and `morse.py` beside it: no clock, no
device, no config. Importing `SAFE_MIN_PERIOD_S` from `device` is the one
exception, and it is `sequencer.py`'s own precedent (it imports `rgb_bytes`
from the same module) - a constant is not I/O, and every flash-floor
guarantee in this file is measured against that one number.
"""

from __future__ import annotations

from . import morse as _morse
from .device import SAFE_MIN_PERIOD_S
from .sequencer import Stop

_BLACK = "#000000"

# Half the WCAG floor - `sequencer.readout`'s own target, and for the same
# reason: a stop's dwell is on-time, not a period, and two dwells make one
# period. Every scheme below floors its own timing parameters against this
# directly, "by construction", rather than leaning on `config.sequence_safe`'s
# clamp - the same promise `sequencer.readout`'s docstring makes.
_FLOOR_S = SAFE_MIN_PERIOD_S / 2


def _nonneg(value: int) -> int:
    """Every scheme reads magnitude only. A bare "-" is not in `morse.ALPHABET`,
    so `morse.encode` would simply drop it - silently, per that module's own
    "unknown characters cost nothing" rule - and a negative value would read
    identically to its positive twin with nobody told. Deciding that once
    here, explicitly, beats three schemes independently inheriting it as an
    accident of what each one's alphabet happens to contain."""
    return abs(int(value))


# --- morse: reuses TODO 83's compiler outright ------------------------------

_DEFAULT_MORSE_COLOR = "#ff8800"


def morse(
    value: int,
    unit_s: float = 0.2,
    color: str = _DEFAULT_MORSE_COLOR,
    off: str = _BLACK,
) -> tuple[Stop, ...]:
    """`value`'s digits, spoken as Morse - `morse.encode` handles digits
    already (they are ordinary characters in `ALPHABET`), so there is no
    renderer to write here, only a number turned into the string it expects.

    (The module is imported as `_morse` at the top of this file for exactly
    the reason CLAUDE.md's "two defs of the same name" gotcha describes: this
    function is meant to be named `morse` too, and a `def morse` here would
    silently rebind the module name out from under its own body the moment
    Python finished defining it - the import shadowed rather than the other
    way around.)

    No `repeat`: a readout is a value at a moment, the one-shot rule
    `sequencer.readout` documents, and this passes it through un-looped.

    The flash floor is `unit_s`'s to keep, not this function's to add on
    top of: every Morse element - a dot, a dash, the shortest gap - is at
    least one unit, so flooring `unit_s` itself at `_FLOOR_S` guarantees
    every stop this produces clears it. That is a tighter floor than
    `config.py`'s own `_parse_morse_look` applies (it caps `dpm` against
    `min_flash_period_s`, a *setting* that may be taken below the WCAG
    default deliberately) - this function has no config in front of it, so
    it enforces the conservative default itself rather than trusting a caller
    to have done so.
    """
    unit_s = max(unit_s, _FLOOR_S)
    return _morse.encode(str(_nonneg(value)), unit_s, color, off=off)


# --- place_value: sequencer.readout's tens/units idea, generalised ---------

# 1s blue, 10s cyan, 100s green, 1000s yellow - TODO 91's own defaults,
# extendable by passing a longer tuple. Index 0 is the *lowest* place (1s),
# matching how `divmod` peels digits off the bottom.
DEFAULT_PLACE_COLORS: tuple[str, ...] = ("#3399ff", "#00cccc", "#33cc33", "#ffcc00")

_PLACE_ON_S = 0.3
_PLACE_OFF_S = 0.22
_PLACE_GROUP_GAP_S = 0.6
_PLACE_ZERO_HOLD_S = 0.4
_PLACE_ZERO_COLOR = "#404040"  # dim neutral - matches sequencer.readout's own


def _pulses(count: int, color: str, on_s: float, off_s: float) -> list[Stop]:
    """`count` hard-cut pulses of `color`, separated by `off_s` of black, no
    trailing gap - `sequencer._digit_pulses` restated rather than imported:
    that name is private to `sequencer.py`, and four lines is cheaper than
    reaching into another module's underscore for them."""
    stops: list[Stop] = []
    for i in range(count):
        stops.append(Stop(color, hold_s=on_s))
        if i < count - 1:
            stops.append(Stop(_BLACK, hold_s=off_s))
    return stops


def place_value(
    value: int,
    colors: tuple[str, ...] = DEFAULT_PLACE_COLORS,
    on_s: float = _PLACE_ON_S,
    off_s: float = _PLACE_OFF_S,
    group_gap_s: float = _PLACE_GROUP_GAP_S,
) -> tuple[Stop, ...]:
    """`value`'s decimal digits, highest place first, each blinking
    `colors[place]` 1-9 times on a steady strobe - `sequencer.readout`'s
    tens/units idea with N configurable places instead of two fixed ones,
    and no cap. 1021 is thousands=1 (one pulse of `colors[3]`), hundreds=0
    (skipped, see below), tens=2 (two pulses of `colors[1]`), units=1 (one
    pulse of `colors[0]`) - four pulses on the light: high, low, low, low
    in colour terms, exactly TODO 91's worked example.

    **Zero reads two different ways, at two different scales - the same
    split `sequencer.readout` makes.** The *whole value* being zero is a
    single dim blink (`_PLACE_ZERO_COLOR`, matching none of `colors`),
    `sequencer.readout`'s own convention restated, so a counted zero still
    reads as "counted", not as the light doing nothing. A *digit* that is
    zero inside a larger number (the hundreds of 1021) contributes no pulses
    and no gap of its own - it is skipped exactly the way "20"'s units digit
    already is in `sequencer.readout`. A group gap appears only between two
    places that both produced pulses, so a skipped place never leaves a gap
    stranded next to nothing.

    `colors` shorter than the number of places needed **wraps** rather than
    raising or padding - `colors[place_index % len(colors)]` - so a counter
    configured with two colours still lights every place it reaches, at the
    cost of two distant places sharing a colour, which is a configuration
    choice to widen rather than a crash to avoid.

    `on_s`/`off_s`/`group_gap_s` are floored at `_FLOOR_S` here, the same "by
    construction" guarantee `sequencer.readout` documents for its own fixed
    constants - these are parameters instead of constants, so the floor has
    to be applied rather than simply being true of the literals.
    """
    on_s = max(on_s, _FLOOR_S)
    off_s = max(off_s, _FLOOR_S)
    group_gap_s = max(group_gap_s, _FLOOR_S)

    value = _nonneg(value)
    if value == 0:
        return (Stop(_PLACE_ZERO_COLOR, hold_s=_PLACE_ZERO_HOLD_S),)

    digits: list[int] = []
    v = value
    while v > 0:
        v, d = divmod(v, 10)
        digits.append(d)
    digits.reverse()  # highest place first
    place_count = len(digits)

    stops: list[Stop] = []
    for i, digit in enumerate(digits):
        if digit == 0:
            continue
        place_index = place_count - 1 - i  # 0 = 1s, counting up from the units end
        color = colors[place_index % len(colors)]
        if stops:
            stops.append(Stop(_BLACK, hold_s=group_gap_s))
        stops += _pulses(digit, color, on_s, off_s)
    return tuple(stops)


# --- binary: two colours, most-significant bit first ------------------------

_BINARY_ON_S = 0.3
_BINARY_OFF_S = 0.2
_DEFAULT_BINARY_ZERO_COLOR = "#3399ff"
_DEFAULT_BINARY_ONE_COLOR = "#ff3300"


def binary(
    value: int,
    zero_color: str = _DEFAULT_BINARY_ZERO_COLOR,
    one_color: str = _DEFAULT_BINARY_ONE_COLOR,
    on_s: float = _BINARY_ON_S,
    off_s: float = _BINARY_OFF_S,
) -> tuple[Stop, ...]:
    """`value` as its binary digits, most-significant bit first, one colour
    for a 0 bit and another for a 1 bit - the cheapest of the three schemes,
    and the one with nothing special to decide about zero: `bin(0)` is
    already the single bit "0", which lights `zero_color` once and so already
    reads as "something happened" - the property the other two schemes need
    an explicit special case to get, this one gets for free from its own
    alphabet having no empty digit.

    Every bit gets its own gap, unlike `place_value`'s digit groups: two
    consecutive `1` bits with nothing black between them would be one long
    flash, indistinguishable from a single bit held twice as long, and
    counting runs correctly is the entire point of reading a number in
    binary. So the gap is per-bit here, not per-place.

    `on_s`/`off_s` floored at `_FLOOR_S`, the same "by construction"
    guarantee the other two schemes make.
    """
    on_s = max(on_s, _FLOOR_S)
    off_s = max(off_s, _FLOOR_S)

    bits = bin(_nonneg(value))[2:]  # "0b101" -> "101"; bin(0) -> "0b0" -> "0"

    stops: list[Stop] = []
    for i, bit in enumerate(bits):
        stops.append(Stop(one_color if bit == "1" else zero_color, hold_s=on_s))
        if i < len(bits) - 1:
            stops.append(Stop(_BLACK, hold_s=off_s))
    return tuple(stops)


# --- hour_colors: count in a colour the value itself picks ------------------

# A twelve-step hue wheel, one entry per hour on a clock face. Index 0 is *one*
# o'clock, not zero - see `hour_colors` for why the wheel is indexed from 1.
#
# **Twelve hues is more than one pixel can really say, and that is worth
# knowing before choosing this scheme.** Adjacent entries here (amber/yellow,
# azure/blue) are two steps apart on a wheel a WS2812 renders with a measured
# colour cast, through a diffuser, in a room with its own light in it. What
# this scheme reliably gives you is the *count* - twelve pulses is noon - with
# the colour as a second, softer cue that says roughly which quarter of the
# clock you are in. Pass a shorter `colors` (four seasons of three hours, say)
# if you want the colour to carry real information.
DEFAULT_HOUR_COLORS: tuple[str, ...] = (
    "#ff0000", "#ff5500", "#ff9900", "#ffdd00",   # 1-4    red -> yellow
    "#aaff00", "#00ff00", "#00ffaa", "#00ffff",   # 5-8    lime -> cyan
    "#0088ff", "#2200ff", "#aa00ff", "#ff00aa",   # 9-12   azure -> magenta
)

# Deliberately `place_value`'s own constants rather than tighter ones: the two
# schemes are the same mechanism (count the pulses) and someone comparing them
# in the editor should be reading a difference in *length*, not in cadence.
_HOUR_ON_S = _PLACE_ON_S
_HOUR_OFF_S = _PLACE_OFF_S
_HOUR_ZERO_HOLD_S = _PLACE_ZERO_HOLD_S
_HOUR_ZERO_COLOR = _PLACE_ZERO_COLOR


def hour_colors(
    value: int,
    colors: tuple[str, ...] = DEFAULT_HOUR_COLORS,
    on_s: float = _HOUR_ON_S,
    off_s: float = _HOUR_OFF_S,
) -> tuple[Stop, ...]:
    """`value` pulses, all in one colour, and the colour is chosen by `value`
    itself - the owner's "1-12 flashes colour-coded per hour" (TODO 106).

    Twelve pulses of magenta is noon; three pulses of amber is three o'clock.
    The count is the number and the colour is a redundant second reading of the
    same number, which is the point: miscounting eleven pulses as twelve is
    easy, and the two look nothing alike.

    **It is a wheel, not a clock.** Nothing here knows what an hour is - the
    colour is `colors[(value - 1) % len(colors)]`, so any `colors` length gives
    a scheme that counts in a colour repeating with that period. Twelve is only
    the default because a clock face is what asked for it. Indexing from
    `value - 1` is what puts hour 1 on the first entry and hour 12 on the last,
    which is how anyone reading `DEFAULT_HOUR_COLORS` will expect to line it up.

    **Folding 13:00 to 1 is the caller's job, not this function's.** A readout
    that quietly rendered 13 as 1 would be lying about every value outside
    1..12, and this module's whole contract is "a number in, that number as
    light". `main`'s chime folds to a twelve-hour clock *before* calling any
    scheme, uniformly, so noon is 12 in binary and Morse too.

    Zero is the same single dim blink `place_value` gives it, and for the same
    reason - a counted zero must not read as the light doing nothing. It also
    has no place on the wheel: `(0 - 1) % 12` is 11, which would have made
    midnight look like noon.

    `on_s`/`off_s` floored at `_FLOOR_S`, the "by construction" guarantee all
    four schemes make.
    """
    on_s = max(on_s, _FLOOR_S)
    off_s = max(off_s, _FLOOR_S)

    value = _nonneg(value)
    if value == 0 or not colors:
        return (Stop(_HOUR_ZERO_COLOR, hold_s=_HOUR_ZERO_HOLD_S),)
    return tuple(_pulses(value, colors[(value - 1) % len(colors)], on_s, off_s))


# --- dispatch ----------------------------------------------------------------

# Named so a parser or `schema.js` can mirror the set without knowing the
# four function names - the same role `sequencer.CURVES` and `sequencer.DRIVES`
# play for their own tables. Mirrored in `schema.js`'s notice template and
# checked by tests/test_hour_chime.py, per CLAUDE.md's "mirrored tables are
# tested, not trusted".
SCHEMES = ("morse", "place_value", "binary", "hour_colors")

_SCHEME_FUNCS = {
    "morse": morse,
    "place_value": place_value,
    "binary": binary,
    "hour_colors": hour_colors,
}

# How one flat list of colours maps onto each scheme's own keyword arguments.
# `None` means "the whole list, as `colors`" - the two counting schemes take a
# wheel of any length and wrap around it, while the other two take a fixed
# number of named colours and ignore anything past them.
#
# A table rather than four branches, for the reason `SCHEMES` is one: a caller
# holding a configured list of colours should not have to know which scheme
# spells them `color`, `zero_color`/`one_color` or `colors`. A fifth scheme
# adds a row here and nothing else changes.
SCHEME_COLOR_ROLES: dict[str, tuple[str, ...] | None] = {
    "morse": ("color",),
    "place_value": None,
    "binary": ("zero_color", "one_color"),
    "hour_colors": None,
}


def scheme_opts(scheme: str, colors) -> dict:
    """`colors` as the keyword arguments `scheme` actually takes.

    An empty list - or one whose entries were all dropped upstream - is an
    empty dict, which leaves every scheme on its own documented defaults.
    That is the point of returning options rather than a colour: "not
    configured" and "configured black" must not be the same thing.

    A list longer than the scheme has roles for is trimmed by `zip`, and a
    shorter one leaves the remaining roles at their defaults. Neither is worth
    an error: the two variadic schemes genuinely take any length, so a length
    rule would belong to two of the four and would have to be stated twice.
    """
    chosen = tuple(color for color in colors if color)
    if not chosen:
        return {}
    roles = SCHEME_COLOR_ROLES.get(scheme, ())
    if roles is None:
        return {"colors": chosen}
    return dict(zip(roles, chosen))


def render(value: int, scheme: str, **opts) -> tuple[Stop, ...]:
    """Look `scheme` up in `SCHEMES` and call it with `value` and `opts` - the
    one seam a future config/schema package needs, rather than three.

    An unrecognised `scheme` raises, unlike `sequencer.shape`'s fallback to
    `linear` on an unknown curve: a curve reaches that function already
    validated by `config.py`'s allow-list, but nothing validates `scheme`
    before it reaches this one - this module has no config in front of it at
    all yet. Rendering the wrong scheme silently would read as "the colours
    are wrong" instead of "the config is wrong", so the next package
    (config/main/schema) is expected to check against `SCHEMES` before ever
    calling this, the way every other allow-list in `config.py` already does
    for its own field.
    """
    try:
        fn = _SCHEME_FUNCS[scheme]
    except KeyError:
        raise ValueError(f"unknown readout scheme {scheme!r}; want one of {SCHEMES}")
    return fn(value, **opts)
