"""Everything declared twice, checked once.

CLAUDE.md's rule is that mirrored tables are tested rather than trusted, and it
was being kept for the protocol and the LED states and quietly not for anything
else. These are the pairs that had no test: three default ramps, the Pomodoro
command set, the style table's `uses`/`strobes` flags, and the Signal
template's default positions. Each one is a place where changing the Python and
forgetting the JavaScript produces an editor that offers something the parser
drops - the exact failure the drift tests elsewhere exist to prevent.

Read off the source with regex, matching the house style of the `ledStates`
drift test next door: the alternative is running a JavaScript engine in the
suite, and these are all plain literal tables.

**If a mirror here becomes hard to extract, that is a signal to delete one
side, not to loosen the test.** `STYLE_USES_PERIOD` was removed for exactly
that reason - it had no reader and no test, so it was a copy waiting to drift.
"""

import re
from pathlib import Path

import pytest

from aibutton import config as cfg
from aibutton.device import (
    LED_STYLES,
    STYLE_STROBES,
    STYLE_USES_COLOR,
    STYLE_USES_COLOR2,
    STYLE_USES_LEVEL,
)

SCHEMA_JS = (Path(__file__).resolve().parents[1]
             / "aibutton/web/static/schema.js").read_text(encoding="utf-8")


def _hex_list(name: str) -> list[str]:
    """The colours in `const NAME = [ '#..', ... ];`."""
    match = re.search(rf"const {name} = \[(.*?)\];", SCHEMA_JS, re.S)
    assert match, f"{name} is not a flat array literal any more"
    return re.findall(r"'(#[0-9a-fA-F]{6})'", match.group(1))


# --- the default ramps -----------------------------------------------------
# A ramp is written out as colours in JS and as ramp.Stop objects in Python.
# Positions are implied by even spacing on both sides (ramp.even), so comparing
# the colours in order compares the whole thing.

@pytest.mark.parametrize("js_name,py_factory", [
    ("COUNTDOWN_RAMP", cfg._default_countdown_ramp),
    ("HOTCOLD_RAMP", cfg._default_hotcold_ramp),
    ("REACTION_RAMP", cfg._default_reaction_ramp),
])
def test_default_ramps_match_on_both_sides(js_name, py_factory):
    assert _hex_list(js_name) == [stop.color for stop in py_factory()]


def test_the_ramps_are_evenly_spaced_so_colours_alone_settle_it():
    """The assumption the test above rests on, stated rather than assumed: if
    a default ramp ever pins its own positions, comparing colours stops being
    enough and this is what says so."""
    for factory in (cfg._default_countdown_ramp, cfg._default_hotcold_ramp,
                    cfg._default_reaction_ramp):
        stops = factory()
        last = len(stops) - 1
        assert [s.at for s in stops] == [i / last for i in range(len(stops))]


# --- the Pomodoro command set ----------------------------------------------


def test_pomodoro_commands_match_on_both_sides():
    """A command the editor offers but the parser rejects is a gesture that
    silently does nothing."""
    block = re.search(r"const POMODORO_COMMANDS = \[(.*?)\];", SCHEMA_JS, re.S)
    assert block, "POMODORO_COMMANDS is not a literal array any more"
    values = re.findall(r"value: '([^']*)'", block.group(1))
    # '' is the editor's "do nothing" entry and is deliberately not a command:
    # the parser reads it as unbinding the gesture.
    assert [v for v in values if v] == list(cfg.POMODORO_COMMANDS)


# --- the style table -------------------------------------------------------


def _js_styles() -> dict[str, dict]:
    """Split the table into whole entries before reading each one.

    Deliberately not one regex over the lot: `strobes: true` sits on a
    continuation line for `alternate` and inline for `flash`, and a pattern
    that assumed either would report drift that is not there. A false alarm in
    a drift test is worse than no drift test, because it teaches people to
    edit the test until it passes.
    """
    block = SCHEMA_JS[SCHEMA_JS.index("export const LED_STYLES = ["):]
    block = block[:block.index("\n];")]
    styles = {}
    entries = re.split(r"\n  (?=\{ type: ')", block)[1:]
    for entry in entries:
        name = re.search(r"type: '(\w+)'", entry).group(1)
        uses = re.search(r"uses: \[([^\]]*)\]", entry).group(1)
        styles[name] = {
            "uses": set(re.findall(r"'(\w+)'", uses)),
            "strobes": bool(re.search(r"\bstrobes: true\b", entry)),
        }
    return styles


def test_every_style_exists_on_both_sides():
    assert set(_js_styles()) == set(LED_STYLES)


def test_which_styles_strobe_matches():
    """The flash floor is enforced in Python and *explained* in the editor by
    this flag. Drift means a slider that offers a rate the parser will clamp."""
    js = _js_styles()
    assert {name for name, s in js.items() if s["strobes"]} == set(STYLE_STROBES)


@pytest.mark.parametrize("reading,expected", [
    ("color", STYLE_USES_COLOR),
    ("color2", STYLE_USES_COLOR2),
    ("level", STYLE_USES_LEVEL),
])
def test_which_styles_use_each_field_matches(reading, expected):
    """Drift here hides a field that does something, or offers one that does
    nothing - the reason the two `color` readings are split at all."""
    js = _js_styles()
    assert {name for name, s in js.items() if reading in s["uses"]} == set(expected)


# --- the Signal template's default positions -------------------------------


def test_signal_default_positions_match_on_both_sides():
    """A template's `defaults()` has to parse to the dataclass defaults, or
    "add a Signal" produces something the parser immediately rewrites."""
    block = SCHEMA_JS[SCHEMA_JS.index("type: 'signal',"):]
    block = block[:block.index("startedBy:")]
    states = re.findall(r"\{ name: '([^']*)', color: '([^']*)', style: '([^']*)' \}", block)
    assert [(s.name, s.color, s.style) for s in cfg._default_signal_states()] == states
