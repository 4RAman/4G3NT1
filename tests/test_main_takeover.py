"""End-to-end-ish driving of aibutton.main.run for the takeover modes: a
Default actions mode whose gestures enter_mode into a stopwatch and into a
counter, then drive those takeovers and assert the store side effects.

run() takes the ButtonDevice, so the test injects a MockDevice and presses
it. Presses are fed one at a time and we wait for each to be consumed before
feeding the next, so the run loop and the takeover handlers (which read the
same queue directly) see them in order without races. The web UI is off
(--no-web) and sounds are disabled.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore

CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {
            "name": "Default",
            "template": "actions",
            "activation": {"type": "always"},
            "long_press": {"action": "enter_mode", "target": "Focus"},
            "double_tap": {"action": "enter_mode", "target": "Water"},
            "short_press": {"action": "log", "event": "ping"},
        },
        {
            "name": "Focus",
            "template": "stopwatch",
            "activation": {"type": "manual"},
            "log_as": "focus",
        },
        {
            "name": "Water",
            "template": "counter",
            "activation": {"type": "manual"},
            "event": "water",
        },
    ],
}


async def _drain(queue: asyncio.Queue, timeout: float = 2.0):
    """Wait until the queue has been emptied (consumed) by the runtime."""
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def test_run_enter_mode_stopwatch_then_counter(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    db_path = tmp_path / "events.db"
    CONFIG_DB = dict(CONFIG, database_path=str(db_path))
    cfg_path.write_text(json.dumps(CONFIG_DB), encoding="utf-8")

    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)

    args = main._parse_args(["--no-web", "--config", str(cfg_path)])

    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)  # let run() reach the main loop

    async def feed(trigger: TriggerType):
        device.press(trigger)
        await _drain(device.events)
        await asyncio.sleep(0.05)  # let the consumer act on it

    try:
        # Stopwatch: long_press enters Focus (starts a timer), short_press is a
        # lap, long_press stops & exits.
        await feed(TriggerType.LONG_PRESS)   # enter_mode -> Focus (timer_start)
        await feed(TriggerType.SHORT_PRESS)  # lap -> log focus_lap
        await feed(TriggerType.LONG_PRESS)   # stop -> timer_stop, exit
        await asyncio.sleep(0.1)

        # Counter: double_tap enters Water, two increments, long_press exits.
        await feed(TriggerType.DOUBLE_TAP)   # enter_mode -> Water
        await feed(TriggerType.SHORT_PRESS)  # +1 -> log water
        await feed(TriggerType.DOUBLE_TAP)   # +1 -> log water
        await feed(TriggerType.LONG_PRESS)   # exit
        await asyncio.sleep(0.1)
    finally:
        # Stop the run loop: SIGTERM isn't wired on Windows, so cancel the task.
        run_task.cancel()
        with pytest.raises((asyncio.CancelledError,)):
            await run_task

    # Inspect the store side effects on the same DB file.
    store = EventStore(str(db_path))
    try:
        rows = store.recent(100)
    finally:
        store.close()

    kinds_names = [(kind, name) for (_ts, kind, name, _dur, _mode, _val) in rows]

    # Stopwatch: exactly one timer_start + one timer_stop for "focus", plus a
    # lap log row.
    assert kinds_names.count(("timer_start", "focus")) == 1
    assert kinds_names.count(("timer_stop", "focus")) == 1
    assert kinds_names.count(("log", "focus_lap")) == 1

    # Counter: two "water" log rows (one per increment).
    assert kinds_names.count(("log", "water")) == 2

    # Every row fired while a takeover mode owned the button is attributed to
    # that mode, not left blank.
    modes_by_name = {name: mode for (_ts, _kind, name, _dur, mode, _val) in rows}
    assert modes_by_name["focus"] == "Focus"
    assert modes_by_name["focus_lap"] == "Focus"
    assert modes_by_name["water"] == "Water"

    # Each takeover session logs its own enter/exit lifecycle.
    assert kinds_names.count(("mode_enter", "Focus")) == 1
    assert kinds_names.count(("mode_exit", "Focus")) == 1
    assert kinds_names.count(("mode_enter", "Water")) == 1
    assert kinds_names.count(("mode_exit", "Water")) == 1


@pytest.mark.parametrize(
    "extra_binding,expected",
    [
        (None, 2),
        ({"triple_tap": {"action": "log", "event": "note"}}, 3),
        ({"tap_4": {"action": "log", "event": "note"}}, 4),
    ],
    ids=[
        "nothing longer than a double is bound",
        "a triple tap is bound",
        "four taps is bound",
    ],
)
async def test_the_device_is_told_how_far_to_count_taps(
    tmp_path, extra_binding, expected
):
    """Binding a triple tap is what makes the button count that far. The
    number is derived from the config rather than set by hand, because it is
    not a preference: counting to three is what delays a double tap, so a
    button pays that only once something is listening for one.
    """
    modes = [dict(m) for m in CONFIG["modes"]]
    if extra_binding:
        modes[0] = dict(modes[0], **extra_binding)
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(CONFIG, modes=modes, database_path=str(tmp_path / "e.db"))),
        encoding="utf-8",
    )

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    try:
        await asyncio.sleep(0.1)
        assert device.max_taps == expected
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task


# --- stop-list ("sequence") looks: the async half of set_led ---------------
#
# sequencer.plan_at is tested on its own (test_sequencer.py) as a pure table;
# what only an event loop can prove is that main.set_led actually walks it,
# cancels it on the next state change, and falls back to the palette when a
# one-shot finishes. Stops are 0.05s so a few real asyncio.sleep()s cover
# several full cycles without the test taking long.

SEQUENCE_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "looks": {
        "pulse": {
            "stops": [
                {"color": "#ff0000", "hold_s": 0.05},
                {"color": "#00ff00", "hold_s": 0.05},
            ],
            "repeat": True,
        },
        "once": {
            "stops": [
                {"color": "#ff0000", "hold_s": 0.05},
                {"color": "#00ff00", "hold_s": 0.05},
            ],
            "repeat": False,
        },
    },
    "modes": [
        {
            "name": "Default", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "enter_mode", "target": "Pulse"},
            "double_tap": {"action": "enter_mode", "target": "Once"},
        },
        {
            "name": "Pulse", "template": "pomodoro", "activation": {"type": "manual"},
            "looks": {"WORKING": "pulse"},
        },
        {
            "name": "Once", "template": "pomodoro", "activation": {"type": "manual"},
            "looks": {"WORKING": "once"},
        },
    ],
}

COUNTDOWN_SEQUENCE_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "looks": {
        "pulse": {
            "stops": [{"color": "#ff0000", "hold_s": 0.05}, {"color": "#00ff00", "hold_s": 0.05}],
        },
    },
    "modes": [
        {
            "name": "Default", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "enter_mode", "target": "Tea"},
        },
        {
            "name": "Tea", "template": "countdown", "activation": {"type": "manual"},
            "minutes": 10, "ring_on_finish": False,
            "looks": {"TIMING": "pulse"},
        },
    ],
}


async def _run_sequence(tmp_path, raw, script):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(raw, database_path=str(tmp_path / "e.db"))), encoding="utf-8"
    )
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        await script(device, task)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return device


async def _press(device, trigger):
    device.press(trigger)
    await _drain(device.events)
    await asyncio.sleep(0.1)  # let the consumer (and any mode transition) settle


async def test_a_repeating_sequence_look_cycles_colours(tmp_path):
    seen = []

    async def script(device, task):
        await _press(device, TriggerType.SHORT_PRESS)  # -> Pulse (WORKING)
        for _ in range(6):
            if device.led_effect is not None:
                seen.append(device.led_effect.color)
            await asyncio.sleep(0.05)

    await _run_sequence(tmp_path, SEQUENCE_CONFIG, script)
    assert "#ff0000" in seen
    assert "#00ff00" in seen


async def test_a_one_shot_sequence_finishes_and_falls_back_to_the_palette(tmp_path):
    """`device.set_led(state, None)`, not a re-resolved look - None is what
    set_led already means by "no override", and re-resolving would just find
    the same look and restart the one-shot forever."""

    async def script(device, task):
        await _press(device, TriggerType.DOUBLE_TAP)  # -> Once (WORKING)
        await asyncio.sleep(0.3)  # well past the 0.1s one-shot
        assert device.led_effect is None
        assert device.led_state is LEDState.WORKING  # state unchanged

    await _run_sequence(tmp_path, SEQUENCE_CONFIG, script)


async def test_leaving_the_mode_cancels_the_running_sequence(tmp_path):
    async def script(device, task):
        await _press(device, TriggerType.SHORT_PRESS)  # -> Pulse, sequence running
        await asyncio.sleep(0.12)
        await _press(device, TriggerType.LONG_PRESS)   # exit -> IDLE
        assert device.led_state is LEDState.IDLE
        assert device.led_effect is None
        # If the old task were still running, it would overwrite this with a
        # stop's colour within one more hold (0.05s) - give it several and
        # confirm IDLE sticks rather than flickering back.
        await asyncio.sleep(0.2)
        assert device.led_state is LEDState.IDLE
        assert device.led_effect is None

    await _run_sequence(tmp_path, SEQUENCE_CONFIG, script)


async def test_a_sequence_look_on_a_ramp_driven_state_does_not_crash(tmp_path):
    """TIMING is walked by the countdown's own ramp, which needs a style and
    a period to modify - config.py's mode-looks validation only checks that
    a named look *exists*, not that it is the right *kind*, so a stop-list
    look assigned to a ramp-driven state must degrade to the template's own
    style (base_look, and run_countdown's own guard) rather than raising out
    of the run loop entirely."""

    async def script(device, task):
        await _press(device, TriggerType.SHORT_PRESS)  # -> Tea (TIMING)
        await asyncio.sleep(0.1)
        assert not task.done()
        assert device.led_state is LEDState.TIMING

    await _run_sequence(tmp_path, COUNTDOWN_SEQUENCE_CONFIG, script)
