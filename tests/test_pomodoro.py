"""The Pomodoro takeover, driven through aibutton.main.run.

Real durations are minutes, so every config here uses fractions of a minute
and the test presses the button rather than waiting. What is actually being
checked is the phase machine: that work blocks get logged and breaks do not,
that the long break lands on the right cycle, that `advance` decides who
starts the next block, and that the assignable gestures do what they say.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import parse_config
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

SECOND = 1 / 60  # one second, expressed in minutes


def config(**pomodoro):
    body = {
        "name": "Focus", "template": "pomodoro", "activation": {"type": "manual"},
        "work_minutes": 2 * SECOND, "break_minutes": SECOND,
        "long_break_minutes": 3 * SECOND, "blocks_before_long_break": 2,
        "extend_minutes": SECOND, "log_as": "pomodoro", "advance": "auto",
    }
    body.update(pomodoro)
    return {
        "sounds_enabled": False, "web_enabled": False,
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "Focus"}},
            body,
        ],
    }


async def _run(tmp_path, cfg, script, settle=0.15):
    """Start the app, enter the Pomodoro, run `script` (an async function
    given the device), then shut down and return the logged events."""
    db = tmp_path / "events.db"
    cfg = dict(cfg, database_path=str(db))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        device.press(TriggerType.SHORT_PRESS)  # enter_mode -> Focus
        await asyncio.sleep(settle)
        await script(device)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    store = EventStore(str(db))
    try:
        return [(kind, name) for (_ts, kind, name, _d, _mode, _val) in store.recent(100)]
    finally:
        store.close()


# --- entering ----------------------------------------------------------

async def test_entering_shows_the_working_light(tmp_path):
    seen = {}

    async def script(device):
        seen["led"] = device.led_state

    await _run(tmp_path, config(), script)
    assert seen["led"] is LEDState.WORKING


async def test_a_finished_work_block_is_logged(tmp_path):
    async def script(device):
        await asyncio.sleep(2.2)  # let the 2s work block elapse

    events = await _run(tmp_path, config(), script)
    assert ("log", "pomodoro") in events


async def test_a_break_is_not_logged(tmp_path):
    async def script(device):
        await asyncio.sleep(3.4)  # work (2s) + break (1s), and into work again

    events = await _run(tmp_path, config(), script)
    # One completed work block, and nothing logged for the break.
    assert [e for e in events if e[1] == "pomodoro"] == [("log", "pomodoro")]


async def test_work_and_break_show_different_lights(tmp_path):
    seen = {}

    async def script(device):
        seen["working"] = device.led_state
        await asyncio.sleep(2.3)  # into the break
        seen["resting"] = device.led_state

    await _run(tmp_path, config(), script)
    assert seen["working"] is LEDState.WORKING
    assert seen["resting"] is LEDState.RESTING


# --- the advance setting -----------------------------------------------

async def test_auto_advances_without_a_press(tmp_path):
    seen = {}

    async def script(device):
        await asyncio.sleep(2.3)
        seen["led"] = device.led_state

    await _run(tmp_path, config(advance="auto"), script)
    assert seen["led"] is LEDState.RESTING  # the break started on its own


async def test_manual_waits_for_a_press(tmp_path):
    seen = {}

    async def script(device):
        await asyncio.sleep(2.4)
        seen["waiting"] = device.led_state
        device.press(TriggerType.SHORT_PRESS)  # toggle: start the break
        await asyncio.sleep(0.2)
        seen["after_press"] = device.led_state

    await _run(tmp_path, config(advance="manual"), script)
    # Neither phase colour while waiting - the timer is not running.
    assert seen["waiting"] is LEDState.LISTENING
    assert seen["after_press"] is LEDState.RESTING


async def test_break_only_starts_breaks_but_waits_before_work(tmp_path):
    seen = {}

    async def script(device):
        await asyncio.sleep(2.3)
        seen["break"] = device.led_state       # break started itself
        await asyncio.sleep(1.1)
        seen["after_break"] = device.led_state  # ...but work waits

    await _run(tmp_path, config(advance="break_only"), script)
    assert seen["break"] is LEDState.RESTING
    assert seen["after_break"] is LEDState.LISTENING


# --- the long break ----------------------------------------------------

async def test_long_break_arrives_on_the_configured_cycle(tmp_path):
    # blocks_before_long_break=2, so the second break is the long one: with a
    # 3s long break still running when we look, we are past where a 1s short
    # break would have ended.
    seen = {}

    async def script(device):
        await asyncio.sleep(5.4)  # work, break, work -> into the second break
        seen["led"] = device.led_state
        await asyncio.sleep(1.4)  # a short break would be over by now
        seen["still_resting"] = device.led_state

    events = await _run(tmp_path, config(), script)
    assert seen["led"] is LEDState.RESTING
    assert seen["still_resting"] is LEDState.RESTING
    assert len([e for e in events if e[1] == "pomodoro"]) == 2


# --- gestures ----------------------------------------------------------

async def test_toggle_pauses_the_countdown(tmp_path):
    seen = {}

    async def script(device):
        device.press(TriggerType.SHORT_PRESS)  # pause almost immediately
        await asyncio.sleep(0.2)
        seen["paused"] = device.led_state
        await asyncio.sleep(2.5)  # longer than the whole work block
        seen["still_paused"] = device.led_state

    events = await _run(tmp_path, config(), script)
    assert seen["paused"] is LEDState.LISTENING
    assert seen["still_paused"] is LEDState.LISTENING
    assert not [e for e in events if e[1] == "pomodoro"]  # never completed


async def test_exit_leaves_the_mode(tmp_path):
    seen = {}

    async def script(device):
        device.press(TriggerType.LONG_PRESS)  # exit
        await asyncio.sleep(0.3)
        seen["led"] = device.led_state

    await _run(tmp_path, config(), script)
    assert seen["led"] is LEDState.IDLE  # back to the ambient layer


async def test_extend_delays_the_end_of_the_block(tmp_path):
    async def script(device):
        device.press(TriggerType.DOUBLE_TAP)  # +1s onto a 2s block
        await asyncio.sleep(2.4)  # the un-extended block would be done

    events = await _run(tmp_path, config(), script)
    assert not [e for e in events if e[1] == "pomodoro"]


async def test_skip_moves_on_without_earning_a_block(tmp_path):
    seen = {}

    async def script(device):
        device.press(TriggerType.SHORT_PRESS)  # skip (rebound below)
        await asyncio.sleep(0.25)
        seen["led"] = device.led_state

    events = await _run(tmp_path, config(short_press="skip"), script)
    assert seen["led"] is LEDState.RESTING       # jumped to the break
    assert not [e for e in events if e[1] == "pomodoro"]  # but did not count


async def test_gestures_are_assignable(tmp_path):
    seen = {}

    async def script(device):
        device.press(TriggerType.SHORT_PRESS)  # bound to exit here
        await asyncio.sleep(0.3)
        seen["led"] = device.led_state

    await _run(tmp_path, config(short_press="exit", long_press="toggle"), script)
    assert seen["led"] is LEDState.IDLE


async def test_an_unbound_gesture_does_nothing(tmp_path):
    seen = {}

    async def script(device):
        device.press(TriggerType.DOUBLE_TAP)  # explicitly unbound below
        await asyncio.sleep(0.2)
        seen["led"] = device.led_state

    await _run(tmp_path, config(double_tap=""), script)
    assert seen["led"] is LEDState.WORKING  # still working, nothing happened


# --- config parsing ----------------------------------------------------

def test_defaults_are_the_classic_pomodoro():
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"}},
    ]})
    behavior = cfg.modes[0].behavior
    assert (behavior.work_minutes, behavior.break_minutes) == (25, 5)
    assert behavior.long_break_minutes == 15
    assert behavior.blocks_before_long_break == 4
    assert behavior.advance == "auto"
    assert behavior.gestures == {
        "short_press": "toggle", "long_press": "exit", "double_tap": "extend",
    }


def test_bad_pomodoro_fields_fall_back_individually():
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"},
         "work_minutes": -5, "advance": "teleport", "blocks_before_long_break": 0,
         "short_press": "explode", "break_minutes": 7},
    ]})
    behavior = cfg.modes[0].behavior
    assert behavior.work_minutes == 25      # fell back
    assert behavior.advance == "auto"       # fell back
    assert behavior.blocks_before_long_break == 4
    assert behavior.gestures["short_press"] == "toggle"
    assert behavior.break_minutes == 7      # the one good value survived


def test_pomodoro_rejects_a_scheduled_activation():
    # Takeover modes are entered by a gesture, not by the clock.
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro",
         "activation": {"type": "schedule", "at": "09:00"}},
    ]})
    assert [m.name for m in cfg.modes] != ["P"]


def test_pomodoro_round_trips():
    from aibutton.config import as_dict

    raw = {"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"},
         "work_minutes": 50, "break_minutes": 10, "long_break_minutes": 30,
         "blocks_before_long_break": 2, "extend_minutes": 5, "advance": "manual",
         "log_as": "deep_work", "short_press": "toggle", "long_press": "exit",
         "double_tap": "skip"},
    ]}
    cfg = parse_config(raw)
    assert parse_config(as_dict(cfg)) == cfg
