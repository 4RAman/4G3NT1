"""The light show takeover, driven through aibutton.main.run.

What is being checked is the thing no other template can do - **advancing on
its own** - plus the two rules that make it safe to leave running: a dwell
floor the flash gate cannot see, and a cue naming a look that is gone being
reported rather than silently skipped.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton import config
from aibutton.device import LEDState, MockDevice, TriggerType

LOOKS = {
    "Ember": {"style": "solid", "color": "#ff5500"},
    "Frost": {"style": "solid", "color": "#00ccff"},
}

CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "looks": LOOKS,
    "modes": [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Show"}},
        {"name": "Show", "template": "lightshow", "activation": {"type": "manual"},
         "cues": ["Ember", "Frost"], "dwell_s": 1.0},
    ],
}


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def _run(tmp_path, script, settle=0.15, overrides=None):
    """Start the app, enter the show, run `script`, shut down, return device."""
    cfg = dict(CONFIG, database_path=str(tmp_path / "events.db"))
    if overrides:
        cfg = dict(cfg, modes=[CONFIG["modes"][0], dict(CONFIG["modes"][1], **overrides)])
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        device.press(TriggerType.SHORT_PRESS)  # enter_mode -> Show
        await _drain(device.events)
        await asyncio.sleep(settle)
        await script(device)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return device


async def _tap(device, trigger: TriggerType = TriggerType.SHORT_PRESS):
    device.press(trigger)
    await _drain(device.events)
    await asyncio.sleep(0.05)


def _shown(device) -> str | None:
    """The colour the show is actually putting on the light."""
    effect = device.led_effect
    return None if effect is None else effect.color


async def test_entering_shows_the_first_cue(tmp_path):
    seen = {}

    async def script(device):
        seen["led"] = device.led_state
        seen["color"] = _shown(device)

    await _run(tmp_path, script)
    # A cue is pushed as an ephemeral look over LISTENING, exactly as a Signal
    # position is - the show owns no LED state of its own.
    assert seen["led"] is LEDState.LISTENING
    assert seen["color"] == "#ff5500"


async def test_a_short_press_moves_to_the_next_cue(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        seen["color"] = _shown(device)

    await _run(tmp_path, script)
    assert seen["color"] == "#00ccff"


async def test_it_advances_on_its_own(tmp_path):
    """The reason this is a template and not a preset."""
    seen = {}

    async def script(device):
        seen["first"] = _shown(device)
        await asyncio.sleep(1.2)  # longer than the 1.0s dwell, no press
        seen["later"] = _shown(device)

    await _run(tmp_path, script)
    assert seen["first"] == "#ff5500"
    assert seen["later"] == "#00ccff", "the show did not advance on the clock"


async def test_a_double_tap_holds_it_where_it_is(tmp_path):
    """Held stops the clock, so the same cue is still up a dwell later."""
    seen = {}

    async def script(device):
        await _tap(device, TriggerType.DOUBLE_TAP)
        seen["at_hold"] = _shown(device)
        await asyncio.sleep(1.3)  # would have advanced twice if unheld
        seen["later"] = _shown(device)

    await _run(tmp_path, script)
    assert seen["later"] == seen["at_hold"], "a held show advanced anyway"


async def test_long_press_leaves_and_the_light_goes_back_to_idle(tmp_path):
    """The house rule every takeover obeys."""
    seen = {}

    async def script(device):
        await _tap(device, TriggerType.LONG_PRESS)
        await asyncio.sleep(0.1)
        seen["led"] = device.led_state

    await _run(tmp_path, script)
    assert seen["led"] is LEDState.IDLE


async def test_a_show_with_no_cues_says_so_instead_of_spinning(tmp_path):
    seen = {}

    async def script(device):
        seen["led"] = device.led_state

    await _run(tmp_path, script, overrides={"cues": []})
    assert seen["led"] is LEDState.ERROR


def test_a_cue_naming_a_missing_look_is_kept_and_warned_about(caplog):
    """Dropping it would make the show quietly shorter than the list you see -
    the same dangling-reference rule `enter_mode` targets follow."""
    cfg = config.parse_config({
        "looks": LOOKS,
        "modes": [dict(CONFIG["modes"][1], cues=["Ember", "Ghost"])],
    })
    mode = next(m for m in cfg.modes if m.name == "Show")
    assert [cue.look for cue in mode.behavior.cues] == ["Ember", "Ghost"]
    assert any("Ghost" in r.getMessage() for r in caplog.records)


def test_the_dwell_has_a_floor_of_its_own(caplog):
    """`sequence_safe` floors a look's own rate; nothing floors how fast the
    show swaps between looks, so this axis needs its own gate."""
    cfg = config.parse_config({"modes": [dict(CONFIG["modes"][1], dwell_s=0.01)]})
    mode = next(m for m in cfg.modes if m.name == "Show")
    assert mode.behavior.dwell_s == pytest.approx(1.0)
    assert any("floor" in r.getMessage() for r in caplog.records)


def test_a_show_survives_the_serialiser():
    """What the editor saves has to parse back to what it saved."""
    original = config.parse_config({
        "looks": LOOKS,
        "modes": [dict(CONFIG["modes"][1],
                       cues=["Ember", {"look": "Frost", "hold_s": 3}], auto=False)],
    })
    again = config.parse_config(config.as_dict(original))
    before = next(m for m in original.modes if m.name == "Show").behavior
    after = next(m for m in again.modes if m.name == "Show").behavior
    assert after == before
