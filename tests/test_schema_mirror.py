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


# --- the action list -------------------------------------------------------
# The oldest mirror in the file and the last to get a test. Every action exists
# as a `type:` in schema.js's ACTIONS and as a branch in `_parse_action`, and
# the failure mode is asymmetric in an instructive way: an action the editor
# offers and the parser drops silently loses a person's binding on Save, while
# one the parser takes and the editor cannot show is merely unreachable.


def _js_actions_block() -> str:
    block = SCHEMA_JS[SCHEMA_JS.index("export const ACTIONS = ["):]
    return block[:block.index("\nexport const ACTION_BY_TYPE")]


def _js_action_types() -> list[str]:
    return re.findall(r"^    type: '([^']*)',$", _js_actions_block(), re.M)


def _py_action_kinds() -> set[str]:
    """The `kind == "..."` branches `_parse_action` actually accepts.

    Read off the source rather than off the union type, because the union says
    what can be *represented* and this test is about what can be *parsed* -
    the removed 'alarm' and 'prompt' branches exist to reject, and an editor
    offering either would be a bug the union could not see.
    """
    source = Path(cfg.__file__).read_text(encoding="utf-8")
    body = source[source.index("def _parse_action("):]
    body = body[:body.index("\ndef ", 1)]
    rejected = {"alarm", "prompt"}
    return set(re.findall(r'kind == "([^"]*)"', body)) - rejected


def test_every_action_the_editor_offers_is_one_the_parser_accepts():
    assert set(_js_action_types()) <= _py_action_kinds()


def test_every_action_the_parser_accepts_can_be_built_in_the_editor():
    assert _py_action_kinds() <= set(_js_action_types())


# A "descriptor defaults must parse" test was tried here and deleted: they
# deliberately do not. `defaults()` is what "Add an action" drops into an empty
# form, so a required field starts blank and the editor's own `required: true`
# is what stops it being saved. Where a default carries real values - MIDI's
# three numeric ranges - the check belongs beside that action, in test_midi.py.


# --- the built-in modes ----------------------------------------------------
# "Add a ready-made mode" is the one editor path that writes a whole mode
# rather than a field, so a preset whose template and activation disagree does
# not fail visibly - it saves, the parser skips it with a warning, and the mode
# you just added is simply not there. This was a real bug: the DAW transport
# preset shipped as `actions` + `manual`, which is not an allowed pair.


def _builtin_modes() -> list[tuple[str, str, str]]:
    block = SCHEMA_JS[SCHEMA_JS.index("export const BUILTIN_MODES = ["):]
    block = block[:block.index("\n];")]
    found = []
    for part in re.split(r"\n  \{\n", block)[1:]:
        entry = re.search(r"id: '([^']+)'", part)
        template = re.search(r"template: '([^']+)'", part)
        # The activation object is one line for most and several for a
        # schedule, so take the first `type:` after the word `activation`.
        activation = re.search(r"activation: \{[^}]*?type: '([^']+)'", part, re.S)
        assert entry and template and activation, part[:200]
        found.append((entry.group(1), template.group(1), activation.group(1)))
    return found


_ACTIVATION_JS_TO_PY = {
    "always": cfg.AlwaysActivation,
    "window": cfg.WindowActivation,
    "schedule": cfg.ScheduleActivation,
    "manual": cfg.ManualActivation,
}


def test_every_built_in_mode_uses_an_activation_its_template_allows():
    builtins = _builtin_modes()
    assert len(builtins) >= 14, "entries stopped being extractable"
    for entry, template, activation in builtins:
        allowed = cfg._ALLOWED_ACTIVATIONS.get(template)
        assert allowed, f"{entry}: unknown template {template!r}"
        assert _ACTIVATION_JS_TO_PY[activation] in allowed, (
            f"{entry}: {template} modes may not be {activation} - "
            f"the parser would skip this preset on save"
        )


def test_built_in_mode_ids_are_unique():
    ids = [entry for entry, _, _ in _builtin_modes()]
    assert len(set(ids)) == len(ids)


# --- the Signal template's default positions -------------------------------


def test_signal_default_positions_match_on_both_sides():
    """A template's `defaults()` has to parse to the dataclass defaults, or
    "add a Signal" produces something the parser immediately rewrites."""
    block = SCHEMA_JS[SCHEMA_JS.index("type: 'signal',"):]
    block = block[:block.index("startedBy:")]
    states = re.findall(r"\{ name: '([^']*)', color: '([^']*)', style: '([^']*)' \}", block)
    assert [(s.name, s.color, s.style) for s in cfg._default_signal_states()] == states
