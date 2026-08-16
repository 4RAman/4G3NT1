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
    neither list would be uneditable, and one in both would be editable in two
    places that disagree."""
    owned = {state for states in MODE_LED_STATES.values() for state in states}
    assert owned | set(SYSTEM_LED_STATES) == {s.value for s in LEDState}
    assert not owned & set(SYSTEM_LED_STATES)


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
