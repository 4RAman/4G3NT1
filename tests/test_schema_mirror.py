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
    STYLE_USES_SATURATION,
)

STATIC = Path(__file__).resolve().parents[1] / "aibutton/web/static"
SCHEMA_JS = (STATIC / "schema.js").read_text(encoding="utf-8")
WIDGETS_JS = (STATIC / "widgets.js").read_text(encoding="utf-8")


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
    ("saturation", STYLE_USES_SATURATION),
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


# --- a seeded mode has to pass the editor's own Check -----------------------
# Two things hand you a *whole* mode rather than a field: BUILTIN_MODES ("Add
# a ready-made mode") and the from-scratch scene seed, which is
# `as_dict(AppConfig())` shipped into the offline editor by
# tools/build_editor.py and dropped in whole by its "New scene" button. What
# nothing checked is that either one survives the validators the editor runs
# on Save/Check - and neither did (TODO 35): a seeded Pomodoro's `lead_in_s:
# 0` tripped a hard-coded "> 0" in the duration widget, and a seeded
# Stopwatch's empty `log_as` tripped `required: true`. "New scene" then
# "Check" rejected the config the editor had just written.
#
# This is the exact opposite case to the deleted "descriptor defaults must
# parse" test noted above, and the two rules coexist: `defaults()` is a blank
# form and *should* leave a required field empty for you to fill in, while a
# seeded mode claims to be finished and ready to run.
#
# The reader below is a real bracket walk rather than a pattern, because these
# tables carry brackets inside strings ("[1] usually means…") and URLs inside
# comments - either one defeats a bracket count that cannot tell code from
# text. It reads only the *scalars* at the top level of an object, which is
# every field a `required` or a `min` can be declared on.


def _past_string(text: str, start: int) -> int:
    """Index just past the quoted run starting at `text[start]`."""
    quote = text[start]
    i = start + 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return min(i + 1, len(text))


def _past(text: str, start: int) -> int:
    """Index just past the bracket opened at `text[start]`."""
    closers = {"{": "}", "[": "]", "(": ")"}
    stack = [closers[text[start]]]
    i = start + 1
    while i < len(text) and stack:
        ch = text[i]
        if ch in "'\"`":
            i = _past_string(text, i)
            continue
        if text[i:i + 2] == "//":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline
            continue
        if ch in closers:
            stack.append(closers[ch])
        elif ch == stack[-1]:
            stack.pop()
        i += 1
    assert not stack, f"unbalanced brackets from {text[start:start + 40]!r}"
    return i


def _inside(text: str, marker: str, at: int = 0) -> str:
    """What `marker` (ending in its own opening bracket) encloses."""
    opener = text.index(marker, at) + len(marker) - 1
    return text[opener + 1:_past(text, opener) - 1]


def _flat_comments(text: str) -> str:
    """`text` with its `//` comments blanked out, strings left alone - which is
    the whole reason this is a walk: a placeholder of 'https://…' is not a
    comment, and blanking from the slashes would eat its closing quote."""
    out, i = [], 0
    while i < len(text):
        if text[i] in "'\"`":
            end = _past_string(text, i)
            out.append(text[i:end])
        elif text[i:i + 2] == "//":
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            out.append(" " * (end - i))
        else:
            out.append(text[i])
            i += 1
            continue
        i = end
    return "".join(out)


def _flat(inside: str) -> str:
    """`inside` with its comments *and* its nested groups blanked out, so what
    is left is exactly the top-level keys of one object literal."""
    text = _flat_comments(inside)
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            end = _past_string(text, i)
            out.append(text[i:end])
        elif ch in "{[(":
            end = _past(text, i)
            out.append(" " * (end - i))
        else:
            out.append(ch)
            i += 1
            continue
        i = end
    return "".join(out)


# A product is spelled out where it reads better as one (`work_s: 25 * 60`),
# so a number here is a product of literals rather than a single one.
_SCALAR = re.compile(
    r"(\w+):\s*(?:'([^']*)'|\"([^\"]*)\"|(-?[\d.]+(?:\s*\*\s*-?[\d.]+)*)|(true|false))"
)


def _object(inside: str) -> dict:
    """The scalar key/value pairs at the top level of one object literal.

    A key whose value is a call, an array or another object is simply absent -
    `ladder: defaultLadder()` and `states: [...]` are not things a `required`
    or a `min` is ever declared on. Later keys win, which is what a spread
    followed by overrides means in JS.
    """
    found = {}
    for key, single, double, number, boolean in _SCALAR.findall(_flat(inside)):
        if number:
            product = 1.0
            for part in number.split("*"):
                product *= float(part)
            found[key] = product
        elif boolean:
            found[key] = boolean == "true"
        else:
            found[key] = single or double
    return found


def _template_chunks() -> dict[str, str]:
    """{template type: the source of its descriptor}."""
    region = SCHEMA_JS[SCHEMA_JS.index("export const TEMPLATES = ["):
                       SCHEMA_JS.index("export const TEMPLATE_BY_TYPE")]
    parts = re.split(r"\n\s*type: '(\w+)',", region)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def _field_specs(block: str) -> list[dict]:
    """Every field descriptor in one `fields: [...]` block, including the ones
    referenced by name (LADDER_FIELD) rather than written inline."""
    # Blanked first: the comments between entries name the very constants a
    # by-name reference looks like (LED_STYLES is discussed twice), and a
    # reader that could not tell the two apart went looking for a descriptor
    # that is a prose mention.
    block = _flat_comments(block)
    specs, i = [], 0
    while i < len(block):
        if block[i] == "{":
            end = _past(block, i)
            specs.append(_object(block[i + 1:end - 1]))
            i = end
            continue
        shared = re.match(r"[A-Z][A-Z_0-9]+", block[i:])
        if shared:
            specs.append(_object(_inside(SCHEMA_JS, f"const {shared.group(0)} = {{")))
            i += shared.end()
            continue
        i += 1
    return specs


def _fields_by_template() -> dict[str, list[dict]]:
    fields = {}
    for name, chunk in _template_chunks().items():
        fields[name] = _field_specs(_inside(chunk, "fields: [")) if "fields: [" in chunk else []
    return fields


def _fields_by_action() -> dict[str, list[dict]]:
    block = _js_actions_block()
    fields = {}
    for match in re.finditer(r"^    type: '([^']*)',$", block, re.M):
        fields[match.group(1)] = _field_specs(_inside(block, "fields: [", match.end()))
    return fields


def _builtin_seeds() -> list[tuple[str, dict]]:
    """[(preset id, the mode object it writes), ...], spreads resolved.

    Flat scalars only, so a preset's *nested* action objects (the DAW
    transport's MIDI messages) are out of reach here - those are covered by
    the parser tests. Every `required` and `min` in the file is on a flat
    field, which is what this has to see.
    """
    chunks = _template_chunks()
    block = SCHEMA_JS[SCHEMA_JS.index("export const BUILTIN_MODES = ["):]
    block = block[:block.index("\n];")]
    seeds = []
    for match in re.finditer(r"id: '([^']+)'", block):
        body = _inside(block, "mode: () => ({", match.end())
        for template in re.findall(r"\.\.\.TEMPLATE_BY_TYPE\.(\w+)\.defaults\(\)", body):
            body = body.replace(
                f"...TEMPLATE_BY_TYPE.{template}.defaults()",
                _inside(chunks[template], "defaults: () => ({"),
            )
        seeds.append((match.group(1), _object(body)))
    return seeds


def _widget_errors(obj: dict, specs: list[dict]) -> list[str]:
    """What widgets.js would reject `obj` for, given `specs`.

    Only the kinds that can reject a filled-in value are modelled: `required`
    is checked by the text/textarea/select widgets, and `min`/`max` by
    duration/number/range. A bound declared as a *function* of the live config
    (the flash floor, in SETTINGS rather than in any template) reads as absent
    here, which is the right answer - a seeded mode cannot be judged against a
    number that depends on the config it is being added to.
    """
    errors = []
    for spec in specs:
        key, kind = spec.get("key"), spec.get("kind", "text")
        label = spec.get("label", key)
        value = obj.get(key)
        if kind in ("text", "textarea", "select"):
            if spec.get("required") and not str("" if value is None else value).strip():
                errors.append(f"{label} is required")
            continue
        if kind not in ("duration", "number", "range"):
            continue
        floor = spec.get("min")
        if kind == "duration":  # the widget reads `Number(obj[key] ?? 0)`
            value = 0 if value in (None, "") else value
            floor = 0 if floor is None else floor
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number")
            continue
        if floor is not None and number < floor:
            errors.append(f"{label} must be at least {floor}")
        if spec.get("max") is not None and number > spec["max"]:
            errors.append(f"{label} must be at most {spec['max']}")
    return errors


def test_the_field_descriptors_are_still_readable():
    """The guard on everything below: an extraction that quietly found nothing
    would pass every check it makes."""
    fields = _fields_by_template()
    assert len(fields) >= 13, "templates stopped being extractable"
    assert fields["stopwatch"] and fields["pomodoro"] and fields["countdown"]
    # The two failures TODO 35 was about have to be visible from here, or this
    # is checking modes against nothing.
    assert any(f.get("key") == "log_as" and f.get("required") for f in fields["stopwatch"])
    assert any(f.get("key") == "lead_in_s" and f.get("min") == 0 for f in fields["pomodoro"])
    assert _fields_by_action()["log"][0]["required"] is True


def test_a_from_scratch_scene_passes_the_editors_own_check():
    """"New scene" then "Check" has to come back clean. The seed is
    `as_dict(AppConfig())` (tools/build_editor.py hands it to the editor), so
    what is really being asserted is that the parser's defaults and the
    editor's validators agree about what a finished mode looks like."""
    fields = _fields_by_template()
    actions = _fields_by_action()
    problems = []
    for mode in cfg.as_dict(cfg.AppConfig())["modes"]:
        for error in _widget_errors(mode, fields[mode["template"]]):
            problems.append(f"{mode['name']}: {error}")
        # An actions/control body validates each bound action too, exactly as
        # the mode editor does. A bare string is a pool reference, not an
        # action - see resolve_action.
        for trigger in cfg.TRIGGER_TYPES:
            bound = mode.get(trigger)
            if isinstance(bound, dict) and bound.get("action") in actions:
                for error in _widget_errors(bound, actions[bound["action"]]):
                    problems.append(f"{mode['name']} / {trigger}: {error}")
    assert not problems


def test_every_built_in_mode_passes_the_editors_own_check():
    """"Add a ready-made mode" writes a whole mode, so a preset that leaves a
    required field blank is a mode the editor refuses to save the moment it
    has been added."""
    fields = _fields_by_template()
    seeds = _builtin_seeds()
    assert len(seeds) >= 14, "entries stopped being extractable"
    problems = []
    for entry, mode in seeds:
        for error in _widget_errors(mode, fields[mode["template"]]):
            problems.append(f"{entry}: {error}")
    assert not problems


# --- a bound is declared once, in the descriptor ----------------------------
# The pair of tests above judge a seeded mode against what schema.js *says*.
# That is only worth anything while the widget agrees, and the second half of
# TODO 35 was exactly the case where it did not: the descriptor said `min: 0`
# and the widget rejected zero anyway.


def test_every_duration_field_declares_its_own_floor():
    """A duration is not automatically positive. Zero is a real value for
    `lead_in_s` ("0 = starts immediately") and nonsense for a work block, so
    which one a field means is written on the field rather than inherited."""
    specs = [
        spec
        for group in (*_fields_by_template().values(), *_fields_by_action().values())
        for spec in group
    ]
    durations = [spec for spec in specs if spec.get("kind") == "duration"]
    assert len(durations) == SCHEMA_JS.count("kind: 'duration'"), (
        "a duration field lives somewhere this test does not read"
    )
    missing = [spec.get("key") for spec in durations if spec.get("min") is None]
    assert not missing, f"no floor declared, so the widget has to guess one: {missing}"


def test_the_duration_widget_floors_where_the_descriptor_says():
    """Read off the source, the way test_color_engine.py reads its claims: the
    alternative is a JavaScript engine in the suite.

    A number written into this comparison is a *second* declaration of a bound
    schema.js already makes - which is the drift this whole file exists to
    catch, in the one place it was hiding as ordinary-looking validation."""
    body = _inside(WIDGETS_JS, "duration(spec, obj, onInput, ctx) {")
    check = _flat_comments(_inside(body, "validate() {"))
    assert re.search(r"[<>]=?\s*(floor|min)\b", check), (
        "the duration widget no longer compares against the declared bound"
    )
    literal = re.search(r"seconds\s*[<>]=?\s*-?\d|-?\d\s*[<>]=?\s*seconds", check)
    assert not literal, (
        f"the duration widget floors at a literal ({literal.group(0)!r}) instead "
        "of at spec.min - a field declaring min: 0 cannot then hold zero"
    )


# --- the lifecycle hooks (TODO 31) -----------------------------------------
# `on_enter`/`on_exit` are a mode-level pair rather than a template field, so
# they are declared once on each side: MODE_HOOKS in config.py and in
# schema.js. The allow-list beside them is the interesting mirror - an action
# the editor offers on a hook and the parser refuses is a binding lost on Save,
# which is the asymmetric failure the action-list tests above are about.


def _js_action_list(name: str) -> list[str]:
    """One of schema.js's action allow-lists, with any `...OTHER` spread
    expanded in place.

    They are built from each other now - a hook is the sequence set plus
    `sequence`, a reflex is the hook set plus two - which is the same
    derivation config.py makes, and reading it literally is what keeps the two
    sides comparable without writing the same six names in four places.
    """
    match = re.search(rf"export const {name} = \[(.*?)\];", SCHEMA_JS, re.S)
    assert match, f"{name} is not a flat array literal any more"
    out: list[str] = []
    for spread, literal in re.findall(r"\.\.\.(\w+)|'(\w+)'", match.group(1)):
        out.extend(_js_action_list(spread) if spread else [literal])
    return out


def _js_hook_actions() -> list[str]:
    return _js_action_list("HOOK_ACTIONS")


def _wire_kind(cls: type) -> str:
    """`LogAction` -> 'log', `TimerToggleAction` -> 'timer_toggle' - the name
    `_parse_action` branches on and the editor writes into `action:`."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__.removesuffix("Action")).lower()


def test_the_two_lifecycle_hooks_are_the_same_two_on_both_sides():
    keys = re.findall(
        r"key: '(\w+)'", _inside(SCHEMA_JS, "export const MODE_HOOKS = [")
    )
    assert tuple(keys) == cfg.MODE_HOOKS


def test_which_actions_a_hook_may_run_matches_on_both_sides():
    assert _js_hook_actions() == [_wire_kind(c) for c in cfg.HOOK_ACTIONS]


def test_the_operators_a_reflex_may_test_with_match_on_both_sides():
    """One field, one operator, one number (TODO 72) - and the operator list
    is the whole language, so an editor offering one the parser refuses is a
    reflex that silently always fires."""
    match = re.search(r"export const REFLEX_OPS = \[(.*?)\];", SCHEMA_JS, re.S)
    assert match, "REFLEX_OPS is not a flat array literal any more"
    assert sorted(re.findall(r"'([^']+)'", match.group(1))) == sorted(cfg.REFLEX_OPS)


def test_every_menu_template_is_a_real_template():
    """TODO 75's grouping is UI-only - `MENU_TEMPLATES` is not mirrored in
    Python and does not have to be - but a heading that lists a template name
    nothing answers to would silently show one group short."""
    match = re.search(r"export const MENU_TEMPLATES = \[(.*?)\];", SCHEMA_JS, re.S)
    assert match, "MENU_TEMPLATES is not a flat array literal any more"
    named = re.findall(r"'(\w+)'", match.group(1))
    assert named, "MENU_TEMPLATES is empty - the Menus group would be too"
    assert set(named) <= set(_template_chunks())


def test_which_actions_a_sequence_step_may_be_match_on_both_sides():
    """A step the editor offers and the parser refuses is a step lost on Save;
    a `sequence` in this list on either side is the nesting TODO 33 exists to
    make impossible."""
    listed = _js_action_list("SEQUENCE_ACTIONS")
    assert listed == [_wire_kind(c) for c in cfg.SEQUENCE_ACTIONS]
    assert "sequence" not in listed


def test_a_sequences_limits_are_the_same_number_on_both_sides():
    """The editor stops you where the parser would. One of them knowing a
    different number means either a save that loses steps or a bound a
    hand-edited file walks past."""
    for name, value in [
        ("MAX_SEQUENCE_STEPS", cfg.MAX_SEQUENCE_STEPS),
        ("MAX_SEQUENCE_S", cfg.MAX_SEQUENCE_S),
    ]:
        match = re.search(rf"export const {name} = (\d+(?:\.\d+)?);", SCHEMA_JS)
        assert match, f"{name} is not a plain number in schema.js"
        assert float(match.group(1)) == float(value), name


def test_which_actions_a_reflex_may_run_matches_on_both_sides():
    """The hook set plus `enter_mode` - a reflex is dispatched *by* the run
    loop, so starting an app is exactly what it is for (TODO 71)."""
    js = _js_action_list("REFLEX_ACTIONS")
    assert js == [_wire_kind(c) for c in cfg.REFLEX_ACTIONS]


def test_a_hooks_allow_list_only_names_actions_that_exist():
    """A subset of the action table, never a place a new name is invented - the
    three left out are excluded on purpose, not by omission."""
    assert set(_js_hook_actions()) < _py_action_kinds()
