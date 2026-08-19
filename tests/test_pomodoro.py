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

def config(**pomodoro):
    # Written in seconds because the fields are seconds now. These used to be
    # `2 * (1/60)` minutes, which is what a config format that could only say
    # "minutes" does to anyone wanting a two-second block - the same pressure
    # that made a 20-second Tabata interval unexpressible (TODO 20).
    body = {
        "name": "Focus", "template": "pomodoro", "activation": {"type": "manual"},
        "work_s": 2, "break_s": 1,
        "long_break_s": 3, "blocks_before_long_break": 2,
        "extend_s": 1, "log_as": "pomodoro", "advance": "auto",
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
        seen["waiting_state"] = device.led_state
        seen["waiting_style"] = device.led_effect.style
        device.press(TriggerType.SHORT_PRESS)  # toggle: start the break
        await asyncio.sleep(0.2)
        seen["after_press"] = device.led_state

    await _run(tmp_path, config(advance="manual"), script)
    # The *next* phase's colour (a break is coming up), frozen solid rather
    # than counting down - not the global LISTENING state.
    assert seen["waiting_state"] is LEDState.RESTING
    assert seen["waiting_style"] == "solid"
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
    assert seen["after_break"] is LEDState.WORKING  # work is next, and waiting


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
        seen["paused_style"] = device.led_effect.style
        await asyncio.sleep(2.5)  # longer than the whole work block
        seen["still_paused"] = device.led_state

    events = await _run(tmp_path, config(), script)
    # Work's own colour, frozen solid - not the global LISTENING state.
    assert seen["paused"] is LEDState.WORKING
    assert seen["paused_style"] == "solid"
    assert seen["still_paused"] is LEDState.WORKING
    assert not [e for e in events if e[1] == "pomodoro"]  # never completed


async def test_waiting_style_is_configurable(tmp_path):
    seen = {}

    async def script(device):
        device.press(TriggerType.SHORT_PRESS)  # pause almost immediately
        await asyncio.sleep(0.2)
        seen["style"] = device.led_effect.style

    await _run(tmp_path, config(waiting_style="flash"), script)
    assert seen["style"] == "flash"


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


# --- rounds and the lead-in, which is what makes this an interval timer ----

async def test_a_counted_session_ends_itself(tmp_path):
    """A Pomodoro runs until you leave; a workout stops after eight. The light
    going back to IDLE with nobody pressing anything is the difference."""
    seen = {}

    async def script(device):
        await asyncio.sleep(2.4)  # one 2s work block, then it should be over
        seen["led"] = device.led_state

    events = await _run(tmp_path, config(rounds=1), script)
    assert seen["led"] is LEDState.IDLE
    assert ("log", "pomodoro") in events, "the last round still counts"


async def test_an_uncounted_session_keeps_going(tmp_path):
    """rounds: 0 is the default and must behave exactly as it always did."""
    seen = {}

    async def script(device):
        await asyncio.sleep(2.4)
        seen["led"] = device.led_state

    await _run(tmp_path, config(rounds=0), script)
    assert seen["led"] is not LEDState.IDLE


async def test_the_lead_in_delays_the_first_block_without_crediting_it(tmp_path):
    """The get-ready pause is not a work block: nothing is logged for it, and
    the block it precedes still runs its full length afterwards."""
    async def script(device):
        await asyncio.sleep(1.0)  # inside a 2s lead-in
        assert device.led_state is LEDState.WORKING  # wearing work's colour

    events = await _run(tmp_path, config(lead_in_s=2), script)
    assert ("log", "pomodoro") not in events


# --- config parsing ----------------------------------------------------

def test_defaults_are_the_classic_pomodoro():
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"}},
    ]})
    behavior = cfg.modes[0].behavior
    assert (behavior.work_s, behavior.break_s) == (25 * 60, 5 * 60)
    assert behavior.long_break_s == 15 * 60
    assert behavior.blocks_before_long_break == 4
    assert behavior.advance == "auto"
    # The two fields the interval merge added, defaulting to exactly what a
    # Pomodoro always did: no end, and no countdown before it starts.
    assert (behavior.rounds, behavior.lead_in_s) == (0, 0.0)
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
    assert behavior.work_s == 25 * 60       # fell back
    assert behavior.advance == "auto"       # fell back
    assert behavior.blocks_before_long_break == 4
    assert behavior.gestures["short_press"] == "toggle"
    assert behavior.break_s == 7 * 60       # the one good value survived


# --- seconds are canonical, minutes still parse ----------------------------
# TODO 20: the same field has to say "25 minutes" and "20 seconds", and
# `work_minutes: 0.333` is not a way to write the second one.


def test_a_config_written_in_minutes_still_parses():
    """Nobody's config breaks. This is the whole compatibility story."""
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"},
         "work_minutes": 50, "break_minutes": 10, "long_break_minutes": 30,
         "extend_minutes": 5},
    ]})
    behavior = cfg.modes[0].behavior
    assert (behavior.work_s, behavior.break_s) == (3000, 600)
    assert (behavior.long_break_s, behavior.extend_s) == (1800, 300)


def test_seconds_win_when_a_config_carries_both():
    """A hand-edit mid-migration must not resolve to whichever name the parser
    happens to try second."""
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"},
         "work_s": 40, "work_minutes": 25},
    ]})
    assert cfg.modes[0].behavior.work_s == 40


def test_short_intervals_are_expressible_at_all():
    """The reason for the change: Tabata is 20 on, 10 off."""
    cfg = parse_config({"modes": [
        {"name": "T", "template": "pomodoro", "activation": {"type": "manual"},
         "work_s": 20, "break_s": 10, "rounds": 8, "lead_in_s": 10},
    ]})
    behavior = cfg.modes[0].behavior
    assert (behavior.work_s, behavior.break_s) == (20, 10)
    assert (behavior.rounds, behavior.lead_in_s) == (8, 10.0)


def test_a_minutes_config_is_rewritten_as_seconds_when_saved():
    """One format in, one format out - the migration completes itself the
    first time the editor saves."""
    from aibutton.config import as_dict

    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"},
         "work_minutes": 25},
    ]})
    entry = as_dict(cfg)["modes"][0]
    assert entry["work_s"] == 1500
    assert "work_minutes" not in entry


@pytest.mark.parametrize("rounds", [-1, 2.5, "eight", True])
def test_a_nonsense_round_count_falls_back(rounds):
    cfg = parse_config({"modes": [
        {"name": "P", "template": "pomodoro", "activation": {"type": "manual"},
         "rounds": rounds},
    ]})
    assert cfg.modes[0].behavior.rounds == 0


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
