"""Named looks: a mode's appearance, separate from the button's own.

The thing this exists to fix is stated as the first runtime test below - two
Pomodoros could not look different, because `WORKING` is one global palette
entry and every Pomodoro showed it. A look is a named effect in a pool that a
mode references per LED state, pushed as an ephemeral effect (ROADMAP D4), so
the *state* stays shared and only its appearance varies.

Fail-soft is the other half and is why so much of this file is about bad
input: a look is cosmetic, so a misspelled one must cost you a colour and
never a mode.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton import sequencer
from aibutton.config import (
    MODE_LED_STATES,
    SYSTEM_LED_STATES,
    LedEffect,
    as_dict,
    look_for,
    parse_config,
    parse_with_warnings,
)
from aibutton.device import LEDState, MockDevice, TriggerType

WARM = {"style": "breathe", "color": "#ff4400", "period_s": 5.0}
COOL = {"style": "breathe", "color": "#0044ff", "period_s": 4.0}


def _config(**over):
    base = {
        "sounds_enabled": False,
        "web_enabled": False,
        "looks": {"warm": dict(WARM), "cool": dict(COOL)},
        "modes": [
            {
                "name": "Default", "template": "actions",
                "activation": {"type": "always"},
                "short_press": {"action": "enter_mode", "target": "Deep"},
                "double_tap": {"action": "enter_mode", "target": "Shallow"},
            },
            {
                "name": "Deep", "template": "pomodoro",
                "activation": {"type": "manual"},
                "looks": {"WORKING": "warm"},
            },
            {
                "name": "Shallow", "template": "pomodoro",
                "activation": {"type": "manual"},
                "looks": {"WORKING": "cool"},
            },
        ],
    }
    base.update(over)
    return base


# --- the pool ----------------------------------------------------------

def test_looks_are_parsed_into_effects():
    cfg = parse_config(_config())
    assert cfg.looks["warm"] == LedEffect("breathe", "#ff4400", "#000000", 5.0)
    assert cfg.looks["cool"].color == "#0044ff"


def test_no_looks_key_is_an_empty_pool_not_an_error():
    """Every config written before looks existed has no `looks` key, and must
    keep behaving exactly as it did - every mode on the palette."""
    cfg = parse_config({"modes": []})
    assert cfg.looks == {}
    assert all(mode.looks == {} for mode in cfg.modes)


def test_one_broken_look_costs_only_that_look():
    cfg, warnings = parse_with_warnings(
        _config(looks={"warm": dict(WARM), "bad": {"style": "disco"}})
    )
    assert cfg.looks["warm"].color == "#ff4400"
    assert cfg.looks["bad"].style == "solid"  # per-field fallback, not dropped
    assert any("bad.style" in w for w in warnings)


def test_a_non_object_looks_key_is_ignored():
    cfg, warnings = parse_with_warnings(_config(looks=["warm"]))
    assert cfg.looks == {}
    assert any("'looks' must be an object" in w for w in warnings)


# --- a mode's references -----------------------------------------------

def test_a_mode_wears_the_look_it_names():
    cfg = parse_config(_config())
    deep = next(m for m in cfg.modes if m.name == "Deep")
    assert look_for(cfg, deep, LEDState.WORKING) == cfg.looks["warm"]


def test_a_state_the_mode_never_chose_falls_back_to_the_palette():
    """None, not the palette entry - None is what set_led already means by
    "no override", so an unchosen state costs no write at all."""
    cfg = parse_config(_config())
    deep = next(m for m in cfg.modes if m.name == "Deep")
    assert look_for(cfg, deep, LEDState.RESTING) is None
    assert look_for(cfg, None, LEDState.WORKING) is None


def test_a_dangling_look_reference_warns_and_keeps_the_mode():
    modes = _config()["modes"]
    modes[1] = dict(modes[1], looks={"WORKING": "nope"})
    cfg, warnings = parse_with_warnings(_config(modes=modes))

    deep = next(m for m in cfg.modes if m.name == "Deep")
    assert deep.looks == {}                       # dropped, not fatal
    assert look_for(cfg, deep, LEDState.WORKING) is None
    assert any("not in 'looks'" in w for w in warnings)


def test_a_mode_cannot_name_a_state_it_does_not_own():
    """A Pomodoro colouring ALERT would be editing the alarm's appearance from
    somewhere nobody would look for it."""
    modes = _config()["modes"]
    modes[1] = dict(modes[1], looks={"ALERT": "warm"})
    cfg, warnings = parse_with_warnings(_config(modes=modes))

    deep = next(m for m in cfg.modes if m.name == "Deep")
    assert deep.looks == {}
    assert any("does not own" in w for w in warnings)


def test_looks_round_trip_through_the_editor():
    cfg = parse_config(_config())
    again = parse_config(as_dict(cfg))
    assert again.looks == cfg.looks
    assert [m.looks for m in again.modes] == [m.looks for m in cfg.modes]


def test_a_mode_with_no_looks_stays_out_of_the_serialised_form():
    cfg = parse_config(_config())
    default = next(m for m in as_dict(cfg)["modes"] if m["name"] == "Default")
    assert "looks" not in default


# --- the state split ---------------------------------------------------

def test_every_led_state_is_owned_by_a_mode_or_by_the_button():
    """The split the Lights tab and the mode editor divide on: a state in
    neither list would be uneditable. LISTENING is the one deliberate dual
    citizen (TODO 26): the ambient layer wears it with no mode involved, so
    its global default stays editable, and a control page may also name a
    look that overrides it only while the page is open - two scopes, not two
    places that disagree."""
    owned = {state for states in MODE_LED_STATES.values() for state in states}
    assert owned | set(SYSTEM_LED_STATES) == {s.value for s in LEDState}
    assert owned & set(SYSTEM_LED_STATES) == {LEDState.LISTENING.value}


def test_every_template_declares_which_states_it_owns():
    from aibutton.config import _ALLOWED_ACTIVATIONS

    assert set(MODE_LED_STATES) == set(_ALLOWED_ACTIVATIONS)


# --- what the light actually does --------------------------------------

async def _run(tmp_path, raw, script):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(raw, database_path=str(tmp_path / "e.db"))), encoding="utf-8"
    )
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)
    try:
        await script(device)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return device


async def _enter(device, trigger):
    device.press(trigger)
    for _ in range(100):
        if device.events.empty():
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.15)


async def test_two_pomodoros_can_finally_look_different(tmp_path):
    """The whole point. Same template, same LEDState, different colour - and
    the shared palette entry is untouched by either."""
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.SHORT_PRESS)   # -> Deep
        seen["deep"] = device.led_effect
        seen["deep_state"] = device.led_state
        await _enter(device, TriggerType.LONG_PRESS)    # exit
        await _enter(device, TriggerType.DOUBLE_TAP)    # -> Shallow
        seen["shallow"] = device.led_effect
        seen["shallow_state"] = device.led_state

    device = await _run(tmp_path, _config(), script)

    assert seen["deep"].color == "#ff4400"
    assert seen["shallow"].color == "#0044ff"
    # Same state throughout: it is the appearance that differs, not what the
    # button reports it is doing.
    assert seen["deep_state"] is LEDState.WORKING
    assert seen["shallow_state"] is LEDState.WORKING
    assert device.palette["WORKING"].color == "#ff4400"  # the default, unedited


async def test_a_mode_without_a_look_pushes_no_effect_at_all(tmp_path):
    """Costing nothing is the point of falling back to None: an old device
    with no CAP_EFFECT behaves exactly as it always did."""
    modes = _config()["modes"]
    modes[1] = {k: v for k, v in modes[1].items() if k != "looks"}
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.SHORT_PRESS)
        seen["effect"] = device.led_effect
        seen["state"] = device.led_state

    await _run(tmp_path, _config(modes=modes), script)
    assert seen["state"] is LEDState.WORKING
    assert seen["effect"] is None


async def test_leaving_a_mode_drops_its_look(tmp_path):
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.SHORT_PRESS)
        await _enter(device, TriggerType.LONG_PRESS)  # exit
        seen["state"] = device.led_state
        seen["effect"] = device.led_effect

    await _run(tmp_path, _config(), script)
    assert seen["state"] is LEDState.IDLE
    assert seen["effect"] is None


async def test_a_countdown_walks_its_ramp_over_the_mode_look(tmp_path):
    """A live effect builds on the mode's look rather than on the palette, so
    choosing a look changes a countdown's style and speed while the ramp still
    owns its colour."""
    raw = {
        "sounds_enabled": False,
        "web_enabled": False,
        "looks": {"urgent": {"style": "flash", "color": "#ffffff", "period_s": 0.4}},
        "modes": [
            {
                "name": "Default", "template": "actions",
                "activation": {"type": "always"},
                "short_press": {"action": "enter_mode", "target": "Tea"},
            },
            {
                "name": "Tea", "template": "countdown",
                "activation": {"type": "manual"}, "minutes": 5,
                "ramp": ["#ff0000", "#0000ff"], "ring_on_finish": False,
                "looks": {"TIMING": "urgent"},
            },
        ],
    }
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.SHORT_PRESS)
        seen["effect"] = device.led_effect

    await _run(tmp_path, raw, script)
    # Style and period come from the look; the colour is the ramp's start.
    assert seen["effect"].style == "flash"
    assert seen["effect"].period_s == pytest.approx(0.4)
    assert seen["effect"].color == "#ff0000"


# --- control surfaces: a page's own look (TODO 26) ----------------------
#
# `control` used to own no LED state at all - it "spoke the button's
# vocabulary" and left it there. That was right for a remote (the interesting
# feedback is whether the *action* worked), but wrong for a menu: bind
# enter_mode and a control surface becomes a tree of pages, and knowing which
# page you are on is the entire job. LISTENING - the state the surface
# actually sits in between actions - is what got added to MODE_LED_STATES;
# SUCCESS/ERROR stay transient flashes, exactly as before.

def _pages_config(**over):
    base = {
        "sounds_enabled": False,
        "web_enabled": False,
        "looks": {"warm": dict(WARM), "cool": dict(COOL)},
        "modes": [
            {
                "name": "Home", "template": "actions",
                "activation": {"type": "always"},
                "long_press": {"action": "enter_mode", "target": "Menu"},
            },
            {
                "name": "Menu", "template": "control",
                "activation": {"type": "manual"},
                "short_press": {"action": "enter_mode", "target": "Mix"},
                "double_tap": {"action": "log", "event": "menu_thing"},
                "looks": {"LISTENING": "warm"},
            },
            {
                "name": "Mix", "template": "control",
                "activation": {"type": "manual"},
                "short_press": {"action": "log", "event": "mix_thing"},
                "looks": {"LISTENING": "cool"},
            },
        ],
    }
    base.update(over)
    return base


async def test_a_control_page_wears_the_look_it_names(tmp_path):
    """The light wears the page's look the whole time the page is open - the
    same machinery two Pomodoros use, one state along."""
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.LONG_PRESS)  # Home -> Menu
        seen["effect"] = device.led_effect
        seen["state"] = device.led_state

    await _run(tmp_path, _pages_config(), script)
    assert seen["state"] is LEDState.LISTENING
    assert seen["effect"].color == "#ff4400"


async def test_entering_a_sub_page_changes_the_pushed_look(tmp_path):
    """`enter_mode` from inside a control surface hands the button off exactly
    like the launcher does - `active_mode` changes, so the very next
    `set_led` resolves the child's own look rather than the parent's."""
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.LONG_PRESS)   # Home -> Menu
        seen["menu"] = device.led_effect
        await _enter(device, TriggerType.SHORT_PRESS)  # Menu -> Mix
        seen["mix"] = device.led_effect

    await _run(tmp_path, _pages_config(), script)
    assert seen["menu"].color == "#ff4400"
    assert seen["mix"].color == "#0044ff"


async def test_leaving_a_sub_page_restores_the_parents_look(tmp_path):
    """The `return_after` path: a long press out of Mix hands the button back
    to Menu, and Menu's own look comes back with it - not the palette's, and
    not Mix's left over from a moment ago."""
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.LONG_PRESS)   # Home -> Menu
        await _enter(device, TriggerType.SHORT_PRESS)  # Menu -> Mix
        await _enter(device, TriggerType.LONG_PRESS)   # leave Mix -> Menu
        seen["effect"] = device.led_effect
        seen["state"] = device.led_state

    await _run(tmp_path, _pages_config(), script)
    assert seen["state"] is LEDState.LISTENING
    assert seen["effect"].color == "#ff4400"


async def test_a_pages_look_survives_an_actions_success_flash(tmp_path):
    """A fired command still gets its own SUCCESS flash - `run_control`'s
    feedback is per action, not per app - but the light must not be left
    there. `resting()` re-pushes LISTENING once the flash's confirm delay
    passes, and now that LISTENING is ownable that repaint resolves the
    page's look again rather than losing it to two seconds of green."""
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.LONG_PRESS)   # Home -> Menu
        await _enter(device, TriggerType.DOUBLE_TAP)   # menu_thing, logged
        await asyncio.sleep(main._CONTROL_CONFIRM_S + 0.1)
        seen["effect"] = device.led_effect
        seen["state"] = device.led_state

    await _run(tmp_path, _pages_config(), script)
    assert seen["state"] is LEDState.LISTENING
    assert seen["effect"].color == "#ff4400"


async def test_a_page_naming_no_look_costs_no_wire_traffic(tmp_path):
    """The existing invariant, one state along: a control surface that
    chooses nothing for LISTENING still resolves to None - the palette entry,
    not a borrowed effect - exactly like every other mode that owns a state
    and leaves it uncoloured."""
    modes = _pages_config()["modes"]
    modes[1] = {k: v for k, v in modes[1].items() if k != "looks"}
    seen = {}

    async def script(device):
        await _enter(device, TriggerType.LONG_PRESS)  # Home -> Menu
        seen["effect"] = device.led_effect
        seen["state"] = device.led_state

    await _run(tmp_path, _pages_config(modes=modes), script)
    assert seen["state"] is LEDState.LISTENING
    assert seen["effect"] is None


# --- the four-step resolution order (TODO 36a) ------------------------------
#
# `set_led`'s explicit argument, then the active mode's look, then the global
# state look, then None (meaning the palette). The middle two are the ones with
# an order worth pinning: a mode that named a look for a state it owns is the
# more specific answer and has to win, or a global default would quietly
# override the per-mode colour that `looks` exists to make possible.

_SEQ_LOOK = {"repeat": False, "stops": [
    {"color": "#00ff2a", "hold_s": 0.2}, {"color": "#000000", "hold_s": 0.2},
    {"color": "#00ff2a", "hold_s": 0.4},
]}


def _cfg_with_state_looks(**over):
    raw = {
        "looks": {"three-blinks": _SEQ_LOOK, "amber": {"style": "solid", "color": "#ffb400"}},
        "modes": [{
            "name": "Base", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "x"},
        }],
    }
    raw.update(over)
    return parse_config(raw)


def test_a_system_state_may_name_a_look_the_palette_could_never_hold():
    """The point of the whole feature: a palette entry ships to the device and
    renders unattended, so it is one effect - a stop list is a schedule only
    the host can walk. Naming one is how SUCCESS becomes a pattern."""
    cfg = _cfg_with_state_looks(state_looks={"SUCCESS": "three-blinks"})
    look = look_for(cfg, None, LEDState.SUCCESS)
    assert isinstance(look, sequencer.Sequence)
    assert len(look.stops) == 3


def test_a_state_with_no_named_look_still_resolves_to_none():
    """None is what `set_led` already means by "use the palette", so a state
    nobody has named must cost no wire traffic at all."""
    cfg = _cfg_with_state_looks(state_looks={"SUCCESS": "three-blinks"})
    assert look_for(cfg, None, LEDState.ERROR) is None


def test_a_modes_own_look_beats_the_global_state_look():
    """The specific answer wins. LISTENING is the state where this is
    reachable: a control page may name a look for it (MODE_LED_STATES) while
    the button's own default for it lives on the Lights tab."""
    cfg = parse_config({
        "looks": {"amber": {"style": "solid", "color": "#ffb400"},
                  "cyan": {"style": "solid", "color": "#00e5ff"}},
        "state_looks": {"LISTENING": "amber"},
        "modes": [
            {"name": "Base", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "x"}},
            {"name": "Desk", "template": "control", "activation": {"type": "manual"},
             "short_press": {"action": "log", "event": "y"},
             "looks": {"LISTENING": "cyan"}},
        ],
    })
    desk = next(m for m in cfg.modes if m.name == "Desk")
    # The page's own look while it is open...
    assert look_for(cfg, desk, LEDState.LISTENING).color == "#00e5ff"
    # ...and the global one everywhere else.
    assert look_for(cfg, None, LEDState.LISTENING).color == "#ffb400"


def test_a_state_look_naming_something_absent_falls_back_and_warns():
    cfg, warnings = parse_with_warnings({
        "looks": {"amber": {"style": "solid", "color": "#ffb400"}},
        "state_looks": {"SUCCESS": "ghost"},
        "modes": [{"name": "Base", "template": "actions",
                   "activation": {"type": "always"},
                   "short_press": {"action": "log", "event": "x"}}],
    })
    assert cfg.state_looks == {}
    assert look_for(cfg, None, LEDState.SUCCESS) is None
    assert any("not in 'looks'" in w for w in warnings), warnings


def test_a_mode_owned_state_cannot_be_named_globally():
    """ALERT belongs to the alarm, so naming it on the Lights tab would be
    editing a mode's colour in the wrong place - the split CLAUDE.md draws."""
    cfg, warnings = parse_with_warnings({
        "looks": {"amber": {"style": "solid", "color": "#ffb400"}},
        "state_looks": {"ALERT": "amber"},
        "modes": [{"name": "Base", "template": "actions",
                   "activation": {"type": "always"},
                   "short_press": {"action": "log", "event": "x"}}],
    })
    assert cfg.state_looks == {}
    assert any("not one of the button's own states" in w for w in warnings), warnings


def test_state_looks_round_trip():
    cfg = _cfg_with_state_looks(state_looks={"SUCCESS": "three-blinks", "IDLE": "amber"})
    assert parse_config(as_dict(cfg)) == cfg
    assert as_dict(cfg)["state_looks"] == {"SUCCESS": "three-blinks", "IDLE": "amber"}
