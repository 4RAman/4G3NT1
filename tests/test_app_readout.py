"""An app's page reads its own history back, and every claim it makes is a
mirror of something Python owns (TODO 51).

`readout` on a template descriptor says which rows in the event log belong to
that app and what the number on them means. Three separate things have to
agree for that to be true, and none of them is checked by anything else:

- the **event name** comes out of a config field, so `nameField` has to name a
  field that actually exists on that template's behaviour. A renamed field
  gives a readout that reads `undefined`, matches nothing, and shows an empty
  history - which is indistinguishable from "you have not used this app yet",
  and is therefore the drift least likely to be noticed by hand.
- the **kind** has to be a kind `store.py` actually writes, or the query
  returns nothing for the same silent reason.
- the **measure** decides how the number is rendered, and pooling unlike
  numbers is how you get a chart that is confidently meaningless (the trap
  TODO 53 names about `value`). A typo'd measure would fall through to the
  default branch and quietly draw the wrong one.

Read off the source with regex, the house style of the drift tests next door -
the alternative is running a JavaScript engine in the suite, and these are all
literal tables. Behaviour field names are taken from the **real parser**
rather than from a hand-written map, so a field renamed in config.py fails
here without anyone having to remember this file exists.
"""

import dataclasses
import logging
import re
from pathlib import Path

import pytest

from aibutton.config import _ALLOWED_ACTIVATIONS, parse_config

STATIC = Path(__file__).resolve().parents[1] / "aibutton/web/static"
SCHEMA_JS = (STATIC / "schema.js").read_text(encoding="utf-8")
STORE_PY = (Path(__file__).resolve().parents[1] / "aibutton/store.py").read_text(
    encoding="utf-8"
)

# The event names a template descriptor may point a readout at. Every one is an
# optional-or-required text field naming what the app writes to the log; if a
# template grows a *new* one, this list is what says the readout question was
# asked about it.
NAME_FIELDS = ("log_as", "event", "dismiss_event", "cleared_event")


# --- reading the descriptors off schema.js ---------------------------------


def _balanced(source: str, start: int) -> str:
    """The `{...}` beginning at `start`, brace-matched.

    Not a `[^}]*` pattern, because the alarm's readout nests a `states` map and
    a non-matching pattern would stop at its closing brace - reporting a
    descriptor that is not there rather than the one that is. A false alarm in
    a drift test is worse than no drift test: it teaches people to edit the
    test until it passes.
    """
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError("unbalanced braces reading a readout descriptor")


def _template_chunks() -> dict[str, str]:
    """{template type: its descriptor source}.

    Cut at every `type: '...'` line and keep the chunks that carry a `nature`,
    which is what distinguishes a template from an action or an activation -
    those use the same key and are declared in the same file.
    """
    marks = [(m.group(1), m.start()) for m in
             re.finditer(r"^\s*type: '(\w+)',$", SCHEMA_JS, re.M)]
    assert marks, "type: declarations are not one per line any more"
    chunks = {}
    for index, (name, start) in enumerate(marks):
        end = marks[index + 1][1] if index + 1 < len(marks) else len(SCHEMA_JS)
        chunk = SCHEMA_JS[start:end]
        if re.search(r"^\s*nature: '", chunk, re.M):
            chunks[name] = chunk
    return chunks


def _readouts() -> dict[str, dict]:
    """{template type: its parsed `readout`}, for the templates that declare one."""
    found = {}
    for template, chunk in _template_chunks().items():
        match = re.search(r"^\s*readout: \{", chunk, re.M)
        if not match:
            continue
        block = _balanced(chunk, chunk.index("{", match.start()))
        spec = {
            key: value for key, value in
            re.findall(r"\b(kind|nameField|measure|noun|unit): '([^']*)'", block)
        }
        better = re.search(r"\bbetter: (null|'low'|'high')", block)
        assert better, f"{template}'s readout does not state a `better`"
        spec["better"] = None if better.group(1) == "null" else better.group(1).strip("'")
        spec["states"] = bool(re.search(r"\bstates: \{", block))
        found[template] = spec
    return found


READOUTS = _readouts()
TEMPLATE_CHUNKS = _template_chunks()


def _measures() -> list[str]:
    match = re.search(r"export const READOUT_MEASURES = \[([^\]]*)\]", SCHEMA_JS)
    assert match, "READOUT_MEASURES is not a flat array literal any more"
    return re.findall(r"'(\w+)'", match.group(1))


def _store_kinds() -> set[str]:
    """Every `kind` store.py writes, read off its own INSERT statements rather
    than copied from the schema comment above them."""
    kinds = set(re.findall(r"VALUES \(\?, '(\w+)'", STORE_PY))
    assert len(kinds) >= 5, "the store's inserts no longer name their kind inline"
    return kinds


# --- the behaviour a template actually parses into -------------------------


def _behaviour_fields() -> dict[str, set[str]]:
    """{template: the field names on the behaviour it parses into}.

    Through the real parser, deliberately. A hand-written template -> class map
    would be a third copy of the same fact, and the thing this test exists to
    catch is exactly a copy going stale.
    """
    activation_for = {
        "ScheduleActivation": {"type": "schedule", "at": "07:00"},
        "ManualActivation": {"type": "manual"},
        "AlwaysActivation": {"type": "always"},
    }
    # Enough of a body for every template to parse: a control surface is
    # skipped with no gesture bound, and a light show with no cues.
    seed = {"short_press": {"action": "log", "event": "x"}, "cues": "ember"}
    fields = {}
    # The parser logs an error per fallback and this deliberately feeds it
    # partial modes; the assertions below are what report a problem.
    logging.disable(logging.CRITICAL)
    try:
        for template, allowed in _ALLOWED_ACTIVATIONS.items():
            config = parse_config({
                "looks": {"ember": {"style": "solid", "color": "#ff0000"}},
                "modes": [{
                    "name": "probe", "template": template,
                    "activation": activation_for[allowed[0].__name__], **seed,
                }],
            })
            mode = next((m for m in config.modes if m.name == "probe"), None)
            assert mode is not None, (
                f"a minimal {template!r} mode no longer parses, so this file "
                "cannot see its fields - fix the seed above"
            )
            fields[template] = {f.name for f in dataclasses.fields(mode.behavior)}
    finally:
        logging.disable(logging.NOTSET)
    return fields


BEHAVIOUR_FIELDS = _behaviour_fields()


# --- the tests -------------------------------------------------------------


def test_the_readouts_are_still_extractable():
    """The guard on every assertion below: if this file stops finding them,
    the rest of the tests pass by vacuously checking nothing."""
    assert len(READOUTS) >= 13, "readout descriptors stopped being extractable"


@pytest.mark.parametrize("template", sorted(READOUTS))
def test_a_readout_names_a_field_its_behaviour_actually_has(template):
    """The drift that hides best: a readout pointing at a renamed field reads
    `undefined`, matches no rows, and renders as "you have not used this yet"."""
    field = READOUTS[template]["nameField"]
    assert field in BEHAVIOUR_FIELDS[template], (
        f"{template}'s readout reads {field!r}, which {template} does not have"
    )


@pytest.mark.parametrize("template", sorted(READOUTS))
def test_a_readout_asks_for_a_kind_the_store_writes(template):
    assert READOUTS[template]["kind"] in _store_kinds()


@pytest.mark.parametrize("template", sorted(READOUTS))
def test_a_readout_uses_a_declared_measure(template):
    """A typo'd measure falls through to the default branch and silently
    renders the wrong one, which is why this is checked rather than trusted."""
    assert READOUTS[template]["measure"] in _measures()


@pytest.mark.parametrize("template", sorted(READOUTS))
def test_better_is_only_ever_an_end_of_the_range(template):
    assert READOUTS[template]["better"] in (None, "low", "high")


@pytest.mark.parametrize("template", sorted(READOUTS))
def test_a_readout_says_what_one_row_is_called(template):
    """The noun is written into four sentences on the page ("12 runs",
    "No guesses logged yet"), so an empty one is four broken strings."""
    assert READOUTS[template].get("noun")


def test_only_an_outcome_carries_a_state_map_and_it_must():
    """`states` is what turns 0 and 1 into "answered" and "no answer". On any
    other measure it would be an unread key; on this one its absence would put
    a bare 0 on screen where a word belongs."""
    for template, spec in READOUTS.items():
        assert spec["states"] == (spec["measure"] == "outcome"), template


def test_every_app_that_logs_says_how_to_read_it_back():
    """The forgetting this catches: a new app ships with a `log_as` field, so
    it writes history, and its own page never shows any - which reads as the
    log being broken rather than as a missing four-line descriptor.

    Ambient templates are exempt: a reflex has no page of its own to put a
    history on, and its gestures' `log` actions are not the mode's own rows.
    """
    owed = {
        template for template, chunk in TEMPLATE_CHUNKS.items()
        if "nature: 'takeover'" in chunk
        and any(re.search(rf"key: '{field}'", chunk) for field in NAME_FIELDS)
    }
    assert owed, "no takeover template declares a loggable name field any more"
    assert owed <= set(READOUTS), (
        f"these apps log but do not say how to read it back: {sorted(owed - set(READOUTS))}"
    )


def test_a_measure_is_backed_by_a_column_that_carries_it():
    """duration reads `duration_s`, everything else reads `value` - and the
    store only sets `duration_s` on timer_stop and mode_exit rows. A duration
    readout over `log` rows would draw a chart of nulls."""
    for template, spec in READOUTS.items():
        if spec["measure"] == "duration":
            assert spec["kind"] in ("timer_stop", "mode_exit"), (
                f"{template} measures a duration off {spec['kind']!r} rows, "
                "which carry no duration_s"
            )
