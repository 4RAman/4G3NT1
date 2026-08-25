"""Where colour is chosen, and where it is no longer chosen.

Three structural claims, all of which were true by accident before and are now
true on purpose:

  - the Lights tab holds the *button's* vocabulary and nothing a mode owns;
  - the mode-owned palette entries still exist in config as the invisible
    fallback, because deleting them would leave a mode with nothing to show;
  - the colour control works with no device attached, so the offline editor
    keeps working.

These are read off the source rather than a DOM, for the same reason the
existing schema drift tests are: the alternative is a browser in the suite.
"""

import re
from pathlib import Path

from aibutton.config import AppConfig, MODE_LED_STATES, SYSTEM_LED_STATES

STATIC = Path(__file__).resolve().parents[1] / "aibutton/web/static"
MENU_JS = STATIC / "menu.js"
ENGINE_JS = STATIC / "colorEngine.js"
MODE_EDITOR_JS = STATIC / "modeEditor.js"
SHELL = Path(__file__).resolve().parents[1] / "tools/editor_shell.html"


# --- the Lights tab is the button's own vocabulary -------------------------


def test_the_lights_tab_does_not_edit_mode_colours():
    """TODO 19d, and the reason is modularity: editing a Pomodoro in one tab
    and its colour in another is what stops a mode being a single thing."""
    source = MENU_JS.read_text(encoding="utf-8")
    assert "SYSTEM_LED_STATES" in source
    assert "MODE_LED_STATES" not in source, (
        "mode-owned states are edited on the mode page now"
    )


def test_the_mode_page_is_where_a_mode_s_colour_is_edited():
    source = MODE_EDITOR_JS.read_text(encoding="utf-8")
    assert "createLookEditor" in source, "the mode page must be able to edit, not just pick"
    assert "LOOK_PRESETS" in source, "and to make a look without leaving the page"


def test_the_test_bench_is_gone_and_its_power_is_in_the_engine():
    """Scrapped as a place, kept as a capability - a look you can push at the
    hardware belonged next to every colour picker, not on its own at the
    bottom of one tab."""
    menu = MENU_JS.read_text(encoding="utf-8")
    assert "_renderTestBench" not in menu
    assert "showLook" not in menu, "live preview belongs to the engine now"
    assert "showLook" in ENGINE_JS.read_text(encoding="utf-8")


# --- the fallback the editor no longer shows -------------------------------


def _mode_owned_states() -> set[str]:
    """config.MODE_LED_STATES is keyed by *template*, so the states are the
    values. (schema.js exports a same-named list of state descriptors, which
    is a different shape for a different job - the editor's, not the parser's.)
    """
    return {state for states in MODE_LED_STATES.values() for state in states}


def test_mode_owned_states_still_have_palette_entries():
    """The editor group went away; the entries did not. They are what a mode
    that has named no look renders, and `base_look` reads them - removing them
    would leave such a mode with nothing at all."""
    palette = AppConfig().led_palette
    owned = _mode_owned_states()
    assert owned, "the split is meaningless if no template owns a state"
    for state in owned:
        assert state in palette, state


def test_system_and_mode_states_overlap_only_on_listening():
    """Disjoint, with one deliberate exception (TODO 26): LISTENING is worn
    by the ambient layer with no mode involved, so its global default must
    stay on the Lights tab - and a control page may also name a look for it,
    overriding the global colour only while that page is open."""
    assert set(SYSTEM_LED_STATES) & _mode_owned_states() == {"LISTENING"}


# --- the engine works with nothing plugged in ------------------------------


def test_live_preview_is_optional_so_the_offline_editor_still_works():
    """The offline editor swaps in a FileApi with no showLook, so the engine
    must treat previewing as a capability it may not have. A colour control
    that required a running service would be the wrong thing to build the
    whole app's colour picking on."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    assert "typeof o.api.showLook === 'function'" in engine
    assert "canPreview" in engine
    # The other half of the claim: the offline API really does lack it.
    assert "showLook" not in SHELL.read_text(encoding="utf-8")


def test_the_diagnostic_colours_survived_the_bench():
    """README's byte-order diagnosis depends on pushing *known* colours, and
    on which ones: red, green, cyan and magenta reveal a channel swap, while
    blue, yellow and white are fixed points of an R/G swap."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    block = engine[engine.index("const DIAGNOSTIC"):engine.index("const FALLBACK_FLOOR")]
    colors = set(re.findall(r"#([0-9a-f]{6})", block))
    assert {"ff0000", "00ff00", "00ffff", "ff00ff"} <= colors


def test_a_preview_reports_the_state_it_is_editing():
    """The bench used to make you pick the reported LED state from a dropdown.
    Whoever mounts the control already knows which state it edits, so it is
    passed in - and `/api/dev/led`'s `state` parameter stops being an argument
    with no caller."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    assert "previewState" in engine
    # Clearing carries no state: it means "put back whatever the config says".
    assert "body.clear || !o.previewState ? body" in engine

    menu = MENU_JS.read_text(encoding="utf-8")
    assert "previewState: state.key" in menu, "the Lights tab knows its state"
    mode = MODE_EDITOR_JS.read_text(encoding="utf-8")
    assert "previewState: key" in mode, "a mode page knows its state too"


# --- one control answers one question (TODO 36f) ---------------------------
#
# "What does this state look like?" was asked twice on the Lights tab: once by
# the Style dropdown and once by a separate named-look select underneath. Two
# controls for one question is why a named look read as broken - the row went
# on describing and previewing the palette entry while the button wore the
# look. It is one dropdown now, and the look picker appears only inside it.


def test_a_named_look_is_an_option_in_the_style_dropdown():
    engine = ENGINE_JS.read_text(encoding="utf-8")
    assert "NAMED_STYLE" in engine
    # Never written into the effect: `__look__` is not a style, and a config
    # carrying one would be a look nothing can render.
    assert "const scratch = { style: wantNamed ? NAMED_STYLE : effect().style };" in engine


def test_the_lights_tab_has_no_second_look_picker():
    menu = MENU_JS.read_text(encoding="utf-8")
    assert "_renderStateLookRow" not in menu, "the picker lives in the style dropdown now"
    assert "_stateLookHandle" in menu, "and the tab supplies it as a handle"


def test_the_head_describes_the_look_that_will_run():
    """The swatch and the summary follow the named look, not the fallback
    underneath it. Reporting the other layer is the whole bug this replaced."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    assert "const shownLook = () =>" in engine
    assert "show(shownLook())" in engine, "and so does the preview button"


def test_a_pool_look_cannot_name_another_pool_look():
    """One level only, guaranteed the way `resolve_action`'s is: by nobody
    offering the option. The Lights tab passes `namedLook` for a *state* row
    and not for a pool row."""
    menu = MENU_JS.read_text(encoding="utf-8")
    pool = menu[menu.index("_renderLookEntry(name)"):menu.index("_looksUsedBy(name)")]
    assert "namedLook" not in pool


# --- a stop is a flat colour, and the fade is between two of them ----------


def test_a_stop_has_no_movement_of_its_own():
    """TODO 36e. A list that walks colours and animates inside them is two
    clocks on one light; what the style expressed is expressible as stops."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    block = engine[engine.index("const STOP_FIELDS"):engine.index("const FADE_FIELDS")]
    assert "'style'" not in block
    assert "period_s" not in block


def test_the_fade_is_edited_in_the_gap_it_crosses():
    """`fade_s` still lives on the stop being arrived at - that is the data -
    but a field called Fade inside one stop's row cannot say which two colours
    it joins. The gap can, and names both ends."""
    engine = ENGINE_JS.read_text(encoding="utf-8")
    assert "const gap = (index)" in engine
    assert "FADE_FIELDS" in engine
    assert "sequence-gap" in engine
