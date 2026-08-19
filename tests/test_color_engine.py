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


def test_system_and_mode_states_are_still_disjoint():
    assert not set(SYSTEM_LED_STATES) & _mode_owned_states()


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
