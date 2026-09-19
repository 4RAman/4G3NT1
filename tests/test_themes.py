"""Colour themes: one pool, one pointer, and a `load_theme` action (TODO 95).

A theme is the *only* thing in this config that changes colours somebody else
already chose, so what is worth testing is not that a dict merged - it is the
four decisions around the merge:

  - the theme's colours reach the **resolved** config, so nothing downstream
    of the parser has to know a theme was involved (the same property "scenes
    merge before the parser" buys, one layer in rather than one file out);
  - a pointer at a theme nobody has costs you the theme and not the button;
  - `as_dict` writes back the colours the *file* carries, because the editor
    edits that object and posts it back - emitting the themed palette would
    bake a theme into somebody's own colours on the very next Save, with no
    way back;
  - and the flash floor is not routed around, which for a theme is the whole
    of "it goes through `push_palette` like every other palette".

The four shipped themes are checked the way `LOOK_PRESETS` is: sliced out of
schema.js as strict JSON and fed through the real parser, because they are the
one place this app *ships* colour rather than accepting it.
"""

import json
import re
from pathlib import Path

import pytest

from aibutton import config as cfg
from aibutton.config import (
    BUILTIN_THEMES,
    FIRE_AND_FORGET_ACTIONS,
    HOOK_ACTIONS,
    POOL_ACTIONS,
    REFLEX_ACTIONS,
    SEQUENCE_ACTIONS,
    Colours,
    LedEffect,
    LoadThemeAction,
    apply_theme,
    as_dict,
    flash_safe,
    parse_config,
    parse_with_warnings,
    resolve_action,
    theme_for,
    themed,
)
from aibutton.device import SAFE_MIN_PERIOD_S, STYLE_STROBES, STYLE_USES_COLOR2

_SCHEMA_JS = Path(__file__).resolve().parents[1] / "aibutton/web/static/schema.js"


def _js_themes() -> list[dict]:
    source = _SCHEMA_JS.read_text(encoding="utf-8")
    match = re.search(r"export const THEMES = (\[.*?\n\]);", source, re.S)
    assert match, "THEMES must stay a single JSON array literal"
    return json.loads(match.group(1))


JS_THEMES = _js_themes()
JS_IDS = [t["id"] for t in JS_THEMES]

# Every LED state a theme is expected to answer for. Read off the parser rather
# than listed, so a state added tomorrow makes these fail loudly instead of
# leaving four themes quietly half-applied.
ALL_STATES = sorted(cfg.LED_STATE_NAMES)


def _themed_config(theme: str, **rest) -> cfg.AppConfig:
    return parse_config({"active_theme": theme, **rest})


# --- the shipped four ------------------------------------------------------

def test_the_four_themes_ship_on_both_sides_and_say_the_same_thing():
    """The one mirror in this feature. Both sides need the colours - the
    offline editor has no server to ask, and the service has to resolve
    `active_theme: "ember"` on a config nobody has opened in an editor - so
    they are written twice and compared here rather than trusted."""
    assert JS_IDS == [b["id"] for b in cfg._BUILTIN_THEME_BODIES]
    assert JS_THEMES == [dict(b) for b in cfg._BUILTIN_THEME_BODIES]


def test_the_four_asked_for_themes_are_the_four_that_shipped():
    assert JS_IDS == ["signal", "ember", "nocturne", "studio"]


@pytest.mark.parametrize("theme_id", JS_IDS)
def test_a_shipped_theme_parses_without_a_single_complaint(theme_id):
    """Shipped colour is our fault rather than a user's, so a warning here is
    a bug in the library and not a fallback doing its job."""
    _, warnings = parse_with_warnings({"active_theme": theme_id})
    assert warnings == [], (theme_id, warnings)


@pytest.mark.parametrize("theme_id", JS_IDS)
def test_a_shipped_theme_colours_every_state_the_button_can_be_in(theme_id):
    """A partial theme is legal - it leaves the states it does not name as you
    had them - but a *shipped* one leaving gaps would blend into whatever the
    reader already had and read as the theme half-working."""
    assert sorted(BUILTIN_THEMES[theme_id].palette) == ALL_STATES


@pytest.mark.parametrize("theme_id", JS_IDS)
def test_no_shipped_theme_is_touched_by_the_flash_floor(theme_id):
    """The floor is a floor, not a target: a theme that got clamped would
    render differently from the swatch that sold it, which is exactly the
    failure the floor exists to make visible."""
    for state, effect in BUILTIN_THEMES[theme_id].palette.items():
        assert flash_safe(effect, SAFE_MIN_PERIOD_S) == effect, (theme_id, state)


@pytest.mark.parametrize("theme_id", JS_IDS)
def test_a_shipped_theme_states_the_strobe_rule_directly(theme_id):
    """Belt and braces over the test above, so a change to `flash_safe` cannot
    quietly make the shipped library unsafe."""
    for state, effect in BUILTIN_THEMES[theme_id].palette.items():
        if effect.style in STYLE_STROBES:
            assert effect.period_s >= SAFE_MIN_PERIOD_S, (theme_id, state)


@pytest.mark.parametrize("theme_id", JS_IDS)
def test_a_second_colour_is_only_set_where_something_renders_it(theme_id):
    """A `color2` on a style that ignores it is invisible config: it shows up
    in the saved theme and nowhere else. `rainbow` is the exception and reads
    it as saturation (INVARIANTS.md), so it is allowed one."""
    for state, effect in BUILTIN_THEMES[theme_id].palette.items():
        if effect.style in STYLE_USES_COLOR2 or effect.style == "rainbow":
            continue
        assert effect.color2 == "#000000", (theme_id, state)


@pytest.mark.parametrize("theme_id", JS_IDS)
def test_a_shipped_theme_is_palette_only_so_it_survives_the_host_going_away(
    theme_id,
):
    """A palette entry ships to the device and renders with nothing attached;
    a named look is a schedule only the host can walk. The shipped four are
    palette-only on purpose, so a themed button stays themed with the PC
    off - the direction the whole product is travelling."""
    theme = BUILTIN_THEMES[theme_id]
    assert theme.looks == {}
    assert theme.state_looks == {}


def test_ember_moves_thinking_off_the_rainbow():
    """The finding Ember forced, pinned so it cannot regress. THINKING's
    default style is `rainbow` - by definition every hue at once - so a theme
    that could only carry *colours* could never put that state on the
    black-body curve. A theme entry is a whole LedEffect, style included, and
    this is the case that proves the format needs to be."""
    default = parse_config({})
    assert default.led_palette["THINKING"].style == "rainbow"
    ember = _themed_config("ember")
    assert ember.led_palette["THINKING"].style != "rainbow"


def test_ember_separates_its_two_pomodoro_states_without_using_hue():
    """The other half of the same finding: with one hue family, level and
    period are all that is left to tell two states apart, so both have to be
    themeable. WORKING and RESTING exist precisely so focus and break do not
    look alike."""
    ember = BUILTIN_THEMES["ember"].palette
    working, resting = ember["WORKING"], ember["RESTING"]
    assert working.color != resting.color
    brightness = lambda hexed: max(  # noqa: E731 - one expression, read once
        int(hexed[i:i + 2], 16) for i in (1, 3, 5)
    )
    channels = lambda hexed: tuple(  # noqa: E731
        int(hexed[i:i + 2], 16) for i in (1, 3, 5)
    )
    # Warm at both ends - red is the strongest channel in each, which is what
    # "on the black-body curve" means here - and told apart by level.
    assert channels(working)[0] == max(channels(working))
    assert channels(resting)[0] == max(channels(resting))
    assert brightness(resting) != brightness(working)


def test_nocturne_never_strobes_above_a_whisper():
    """A theme is allowed to be quieter than the floor requires. The one
    strobing state in Nocturne is near-black, which is the difference between
    a tick you can see at 3 AM and a torch."""
    nocturne = BUILTIN_THEMES["nocturne"].palette
    for state, effect in nocturne.items():
        if effect.style not in STYLE_STROBES:
            continue
        assert max(int(effect.color[i:i + 2], 16) for i in (1, 3, 5)) < 0x60, state


def test_studio_keeps_saturated_red_for_the_alarm_alone():
    """"Desaturated everywhere except record" is the whole argument for the
    theme, and it is a property of the numbers rather than of the prose."""
    studio = BUILTIN_THEMES["studio"].palette
    red, green, blue = (int(studio["ALERT"].color[i:i + 2], 16) for i in (1, 3, 5))
    assert (red, green, blue) == (0xFF, 0, 0)
    for state, effect in studio.items():
        if state == "ALERT":
            continue
        channels = [int(effect.color[i:i + 2], 16) for i in (1, 3, 5)]
        assert not (channels[0] == 0xFF and max(channels[1:]) < 0x30), state


# --- the pointer -----------------------------------------------------------

def test_a_themes_colours_reach_the_resolved_config():
    """The property everything else depends on: the theme is applied inside
    the one parser, so `led_palette` *is* the themed answer and nothing
    downstream has to ask."""
    config = _themed_config("ember")
    assert config.active_theme == "ember"
    for state, effect in BUILTIN_THEMES["ember"].palette.items():
        assert config.led_palette[state] == effect, state


def test_a_theme_reaches_the_states_a_mode_wears_too():
    """Not only the button's own vocabulary. A mode with no named look renders
    its state's palette entry, so a theme that stopped at SYSTEM_LED_STATES
    would recolour half the button and look broken on the half it missed."""
    config = _themed_config("nocturne")
    assert config.led_palette["WORKING"] == BUILTIN_THEMES["nocturne"].palette["WORKING"]
    assert config.led_palette["METRONOME"].color == "#14202e"


def test_an_unknown_active_theme_warns_and_leaves_your_colours_alone():
    """It does not crash, and it does not pick a different theme on your
    behalf - the same call the action pool's dangling rule makes."""
    config, warnings = parse_with_warnings({"active_theme": "sunburst"})
    assert config.active_theme is None
    assert config.led_palette["IDLE"] == parse_config({}).led_palette["IDLE"]
    assert any("sunburst" in w for w in warnings), warnings


def test_an_active_theme_that_is_not_even_a_name_falls_back_per_key():
    config, warnings = parse_with_warnings({"active_theme": 17, "sounds_enabled": False})
    assert config.active_theme is None
    assert config.sounds_enabled is False  # the rest of the config survived
    assert any("active_theme" in w for w in warnings), warnings


def test_a_theme_of_your_own_shadows_a_shipped_one_of_the_same_name():
    """What "users can edit and save their own" has to mean when the one they
    want to edit is Ember. The same relationship a named look has with a look
    preset."""
    config = parse_config({
        "themes": {"ember": {"label": "My Ember", "palette": {
            "IDLE": {"style": "solid", "color": "#010203"},
        }}},
        "active_theme": "ember",
    })
    assert theme_for(config, "ember").name == "My Ember"
    assert config.led_palette["IDLE"].color == "#010203"
    # And the states it left alone are still yours, not the shipped Ember's.
    assert config.led_palette["SUCCESS"] == parse_config({}).led_palette["SUCCESS"]


def test_only_your_own_themes_are_written_back_not_the_shipped_four():
    """Nobody's config file grows four themes they did not write - the look
    presets' rule, applied one level up."""
    written = as_dict(parse_config({"active_theme": "studio"}))
    assert written["themes"] == {}
    assert written["active_theme"] == "studio"


# --- what a theme owns, and what it does not -------------------------------

def test_a_themes_state_looks_replace_yours_rather_than_merging():
    """The one asymmetry in the format, and it is the rule that makes a theme
    visible at all: `look_for` checks `state_looks` *before* the palette, so a
    config naming a look for IDLE would otherwise hide the theme's IDLE
    completely."""
    own = Colours(
        led_palette={}, looks={"mine": LedEffect()}, state_looks={"IDLE": "mine"},
    )
    theme = cfg.Theme(name="T", looks={"theirs": LedEffect()},
                      state_looks={"SUCCESS": "theirs"})
    out = themed(own, theme)
    assert out.state_looks == {"SUCCESS": "theirs"}
    # The pool merges, though: a mode names a look, so dropping the pool would
    # break every mode that wears one.
    assert set(out.looks) == {"mine", "theirs"}


def test_a_theme_does_not_decide_which_look_a_mode_wears():
    """A theme recolours the button; it does not rearrange it. Which look each
    mode names is the mode's identity and stays on the mode."""
    config = parse_config({
        "looks": {"focus": {"style": "solid", "color": "#123456"}},
        "themes": {"warm": {"label": "Warm", "looks": {
            "focus": {"style": "solid", "color": "#ff8800"},
        }}},
        "active_theme": "warm",
        "modes": [{
            "name": "Pom", "template": "pomodoro",
            "activation": {"type": "manual"}, "looks": {"WORKING": "focus"},
        }],
    })
    assert config.modes[0].looks == {"WORKING": "focus"}   # unchanged
    assert config.looks["focus"].color == "#ff8800"        # recoloured


def test_a_theme_cannot_move_the_flash_floor():
    """A safety setting is not an aesthetic. `min_flash_period_s` is not a
    theme key, so a theme naming one is an unknown key inside the theme rather
    than a floor somebody lowered by picking a colour scheme."""
    config = parse_config({
        "themes": {"fast": {"label": "Fast", "min_flash_period_s": 0.01}},
        "active_theme": "fast",
    })
    assert config.min_flash_period_s == SAFE_MIN_PERIOD_S


def test_a_theme_under_the_floor_is_floored_where_every_palette_is():
    """No fourth path to the light and no second clamp: a theme lands in
    `led_palette`, and `main.push_palette` is the one place a palette is
    floored. Stated here over the same function that call site uses."""
    config = parse_config({
        "themes": {"fast": {"label": "Fast", "palette": {
            "ERROR": {"style": "flash", "color": "#ff0000", "period_s": 0.05},
        }}},
        "active_theme": "fast",
    })
    themed_error = config.led_palette["ERROR"]
    assert themed_error.period_s == 0.05  # honoured in the config, as a setting is
    floored = flash_safe(themed_error, config.min_flash_period_s)
    assert floored.period_s == pytest.approx(config.min_flash_period_s)


def test_the_palette_push_is_still_the_only_place_a_palette_is_floored():
    """Guards the rule rather than one instance of it: three paths to the
    light, one call site each (CLAUDE.md). A theme must not have added a
    fourth."""
    source = (Path(cfg.__file__).resolve().parents[0] / "main.py").read_text(
        encoding="utf-8"
    )
    assert source.count("flash_safe(entry") == 1
    assert source.count("sequence_safe(effect") == 1


# --- saving, and not saving ------------------------------------------------

def test_saving_a_themed_config_writes_back_your_colours_not_the_themes():
    """The editor edits `as_dict`'s output and posts it back, so emitting the
    themed palette here would bake Ember into somebody's own colours on the
    next Save with no way back."""
    base = {"led_palette": {"IDLE": {
        "style": "solid", "color": "#00ff00", "color2": "#000000", "period_s": 1,
    }}}
    config = parse_config({**base, "active_theme": "ember"})
    assert config.led_palette["IDLE"].color == "#4a1200"      # what the button shows
    written = as_dict(config)
    assert written["led_palette"]["IDLE"]["color"] == "#00ff00"  # what the file keeps


def test_a_themed_config_round_trips_exactly():
    config = parse_config({
        "active_theme": "signal",
        "looks": {"mine": {"style": "solid", "color": "#0a0b0c"}},
        "state_looks": {"SUCCESS": "mine"},
    })
    assert parse_config(as_dict(config)) == config


def test_clearing_a_theme_brings_your_own_colours_back_exactly():
    config = parse_config({"active_theme": "studio"})
    assert apply_theme(config, None).led_palette == parse_config({}).led_palette


def test_switching_themes_never_compounds_one_over_the_other():
    """Always laid over your own colours, never over the theme already on -
    otherwise the states the new theme happens not to name would keep wearing
    the old one's."""
    straight = _themed_config("nocturne")
    via_ember = apply_theme(_themed_config("ember"), "nocturne")
    assert via_ember.led_palette == straight.led_palette
    assert via_ember.state_looks == straight.state_looks


# --- the action ------------------------------------------------------------

def test_load_theme_is_offered_everywhere_an_ordinary_primitive_is():
    """One placement in `FIRE_AND_FORGET_ACTIONS` puts it on a gesture, a
    hook, a reflex, the pool and a sequence step at once. The reflex is the
    case that earns it: at sunset, load Nocturne."""
    for allowed in (FIRE_AND_FORGET_ACTIONS, SEQUENCE_ACTIONS, HOOK_ACTIONS,
                    POOL_ACTIONS, REFLEX_ACTIONS):
        assert LoadThemeAction in allowed


def test_a_gesture_can_hold_one_and_a_reflex_can_name_one():
    config = parse_config({
        "actions": {"night": {"action": "load_theme", "theme": "nocturne"}},
        "reflexes": [{"name": "sunset", "then": "night"}],
        "modes": [{
            "name": "Home", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "load_theme", "theme": "ember"},
        }],
    })
    assert config.modes[0].behavior.actions["short_press"] == LoadThemeAction("ember")
    assert resolve_action(config, config.reflexes[0].then) == LoadThemeAction("nocturne")


def test_an_empty_theme_name_means_back_to_your_own_colours():
    """The other half of a gesture that loads one, and the reason the parser
    checks the type rather than emptiness: everywhere else here, blank means
    the binding was never finished."""
    action = parse_config({"modes": [{
        "name": "Home", "template": "actions", "activation": {"type": "always"},
        "short_press": {"action": "load_theme", "theme": ""},
    }]}).modes[0].behavior.actions["short_press"]
    assert action == LoadThemeAction(theme="")


def test_loading_a_theme_nobody_has_warns_at_load_and_keeps_the_binding():
    """Dangling on purpose, like every other named reference here: quietly
    repointing it at some other theme would be worse, and a rename is the
    likelier explanation."""
    config, warnings = parse_with_warnings({"modes": [{
        "name": "Home", "template": "actions", "activation": {"type": "always"},
        "short_press": {"action": "load_theme", "theme": "sunburst"},
    }]})
    assert config.modes[0].behavior.actions["short_press"] == LoadThemeAction("sunburst")
    assert any("sunburst" in w for w in warnings), warnings


def test_a_dangling_load_theme_fails_clearly_when_it_is_pressed():
    """The same fact at the moment it costs you something. `set_active_theme`
    refuses and says which name, rather than doing nothing."""
    manager = _FakeManager(parse_config({}))
    assert manager.set_active_theme("sunburst") == "no theme named 'sunburst'"
    assert manager.config.active_theme is None


def test_running_load_theme_swaps_the_live_config_without_touching_the_disk(
    tmp_path,
):
    """The design decision in TODO 95, pinned. It is reached from `execute()`
    on the press that fired it, so a disk write here is the thing
    fire-and-forget exists to keep out of a press - and `write_path` sends
    edits to the *active scene*, so persisting would mean a sunset reaction
    rewriting a scene file every evening."""
    import asyncio

    from aibutton.actions import execute

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"database_path": str(tmp_path / "e.db")}), "utf-8")
    manager = cfg.ConfigManager(str(path))
    before = path.read_text(encoding="utf-8")

    result = asyncio.run(execute(
        LoadThemeAction(theme="ember"), trigger="short_press", mode_name="Home",
        store=None, set_theme=manager.set_active_theme,
    ))

    assert result.ok, result.message
    assert manager.config.active_theme == "ember"
    assert manager.config.led_palette["IDLE"].color == "#4a1200"
    assert path.read_text(encoding="utf-8") == before  # nothing was written


def test_a_reloaded_config_is_back_on_the_theme_the_file_names(tmp_path):
    """The other half of not persisting, said out loud: a theme a gesture
    loaded lasts until the config is reloaded, exactly like standby."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "database_path": str(tmp_path / "e.db"), "active_theme": "signal",
    }), "utf-8")
    manager = cfg.ConfigManager(str(path))
    manager.set_active_theme("nocturne")
    assert manager.config.active_theme == "nocturne"
    manager.reload()
    assert manager.config.active_theme == "signal"


def test_load_theme_says_so_where_nothing_can_change_the_theme():
    """A silent no-op is the failure a counter takes weeks to notice - the
    call `set_value` already makes about a missing document store."""
    import asyncio

    from aibutton.actions import execute

    result = asyncio.run(execute(
        LoadThemeAction(theme="ember"), trigger="short_press", mode_name="Home",
        store=None,
    ))
    assert not result.ok
    assert "theme" in result.message


class _FakeManager:
    """A ConfigManager with no file behind it - `set_active_theme` touches
    neither, which is the whole point of this feature and makes this honest
    rather than a shortcut."""

    def __init__(self, config: cfg.AppConfig) -> None:
        self._loaded = cfg.LoadedConfig(config=config)

    @property
    def config(self) -> cfg.AppConfig:
        return self._loaded.config

    set_active_theme = cfg.ConfigManager.set_active_theme
