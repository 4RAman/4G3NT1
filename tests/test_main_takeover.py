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


# --- named look > ladder > ramp: who owns the colour (TODO 36d) ------------
#
# Three things can decide TIMING's colour and two can decide METRONOME's, and
# only one of each may run. The order is the general rule CLAUDE.md states -
# the more explicit thing wins: a ramp is the template's own default and every
# countdown has one, a ladder is a checkbox you tick, and a driven stop list is
# something you had to build, name and then point this mode at.
#
# It has to be asserted through the run loop rather than through config: the
# precedence lives in `run_countdown` and `run_metronome`, which await a device
# and so exist only inside an event loop. The three sources are given disjoint
# palettes below, so *which* colour arrives is the whole answer - a membership
# check rather than an exact frame, because a ladder deliberately changes
# colour while it runs and a ramp deliberately does not.

_SEQ_COLORS = {"#0000ff", "#ffffff"}
# A ten-minute countdown is a fraction of a percent through after a second, so
# a progress-sampled list has to still be sitting on its *first* stop. Pinning
# that rather than the whole palette is what separates "sampled on progress"
# from "walked on the clock", which would have moved on within one hold.
_SEQ_START = {"#0000ff"}
_LADDER_COLORS = {"#00ff00", "#004400"}
_RAMP_COLORS = {"#ff0000"}
# What the METRONOME palette entry ships as: the colour that survives when
# nothing at all claims the beat, and the light is just the tempo.
_TEMPO_COLORS = {"#ffaa00"}

_COUNTDOWN_LADDER = {
    "enabled": True, "tick_s": 0.5, "base": "#004400",
    "rungs": [{"every_s": 1, "color": "#00ff00"}],
}


def _countdown_config(*, named_look: bool, ladder: bool) -> dict:
    """A ten-minute countdown that always has a ramp, optionally a ladder, and
    optionally a progress-driven look pointed at TIMING."""
    tea = {
        "name": "Tea", "template": "countdown", "activation": {"type": "manual"},
        "minutes": 10, "ring_on_finish": False, "ramp": ["#ff0000", "#ffff00"],
    }
    if ladder:
        tea["ladder"] = dict(_COUNTDOWN_LADDER)
    if named_look:
        tea["looks"] = {"TIMING": "arc"}
    return {
        "sounds_enabled": False, "web_enabled": False,
        "looks": {"arc": {
            "drive": "progress", "repeat": False,
            "stops": [{"color": "#0000ff", "hold_s": 1.0},
                      {"color": "#ffffff", "hold_s": 1.0}],
        }},
        "modes": [
            {"name": "Home", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "Tea"}},
            tea,
        ],
    }


def _metronome_config(*, named_look: bool, ladder: bool) -> dict:
    beat = {
        "name": "Beat", "template": "metronome", "activation": {"type": "manual"},
        "start_bpm": 120, "sound_on_tap": False,
    }
    if ladder:
        beat["ladder"] = {"enabled": True, "base": "#004400",
                          "rungs": [{"every_s": 2, "color": "#00ff00"}]}
    if named_look:
        beat["looks"] = {"METRONOME": "accent"}
    return {
        "sounds_enabled": False, "web_enabled": False,
        "looks": {"accent": {
            "drive": "beats", "repeat": True,
            "stops": [{"color": "#0000ff", "hold_s": 1.0},
                      {"color": "#ffffff", "hold_s": 1.0}],
        }},
        "modes": [
            {"name": "Home", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "Beat"}},
            beat,
        ],
    }


async def _colors_while(tmp_path, raw, state, frames=8):
    """Every colour the light wears while `state` owns it, over ~`frames`
    tenths of a second."""
    seen = set()

    async def script(device, task):
        await _press(device, TriggerType.SHORT_PRESS)  # Home -> the takeover
        for _ in range(frames):
            if device.led_state is state and device.led_effect is not None:
                seen.add(device.led_effect.color)
            await asyncio.sleep(0.1)

    await _run_sequence(tmp_path, raw, script)
    return seen


@pytest.mark.parametrize(
    "named_look, ladder, owner",
    [
        (True, True, _SEQ_START),
        (False, True, _LADDER_COLORS),
        (False, False, _RAMP_COLORS),
    ],
    ids=[
        "a named progress list beats the ladder and the ramp",
        "a ladder beats the ramp",
        "the ramp paints when nothing more explicit claims TIMING",
    ],
)
async def test_a_countdown_hands_timing_to_the_most_deliberate_colour_source(
    tmp_path, named_look, ladder, owner
):
    seen = await _colors_while(
        tmp_path, _countdown_config(named_look=named_look, ladder=ladder),
        LEDState.TIMING,
    )
    assert seen, "the countdown never coloured TIMING at all"
    assert seen <= owner, seen


@pytest.mark.parametrize(
    "named_look, ladder, owner",
    [
        (True, True, _SEQ_COLORS),
        (False, True, _LADDER_COLORS),
        (False, False, _TEMPO_COLORS),
    ],
    ids=[
        "a named beats list beats the ladder and the plain pulse",
        "a ladder beats the plain pulse",
        "the tempo pulse paints when nothing claims the beat",
    ],
)
async def test_a_metronome_hands_the_beat_to_the_most_deliberate_colour_source(
    tmp_path, named_look, ladder, owner
):
    """The same ordering one app along. The third tier is not a ramp here - a
    metronome has none - it is the device-rendered pulse the mode has always
    had, wearing the palette's own METRONOME colour."""
    seen = await _colors_while(
        tmp_path, _metronome_config(named_look=named_look, ladder=ladder),
        LEDState.METRONOME, frames=14,  # 120 BPM: ~1.4s covers several beats
    )
    assert seen, "the metronome never coloured METRONOME at all"
    assert seen <= owner, seen


# --- the readout action, and the Counter agreeing with the store -----------
#
# TODO 15/17: a `readout` action's display is its own feedback, so it must
# never be followed (or preceded) by the ambient dispatch's usual SUCCESS
# flash, and the Counter takeover must start counting from the same rows an
# ambient `log` already wrote rather than from a local zero. Both need the
# real run loop (readout drives an async sequence task; the Counter reads the
# store at takeover-entry time), so they live here rather than in
# test_config.py/test_sequencer.py, which only exercise the pure halves.

READOUT_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {
            "name": "Default", "template": "actions", "activation": {"type": "always"},
            "short_press": {
                "action": "readout", "event": "coffee",
                "tens_color": "#ff8800", "units_color": "#3399ff",
            },
        },
    ],
}


async def test_readout_action_shows_the_count_and_never_flashes_success(tmp_path):
    db_path = tmp_path / "e.db"
    seed = EventStore(str(db_path))
    for _ in range(3):  # tens=0, units=3 -> three quick blue pulses
        seed.log_event("coffee")
    seed.close()

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(READOUT_CONFIG, database_path=str(db_path))),
        encoding="utf-8",
    )

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)

    seen_states, seen_colors = [], []
    try:
        device.press(TriggerType.SHORT_PRESS)
        await _drain(device.events)
        # Watch for longer than the three-pulse readout (3*0.18 + 2*0.18 =
        # 0.9s) so the whole thing plays out and a stray SUCCESS has time to
        # show up if it were going to.
        for _ in range(24):
            seen_states.append(device.led_state)
            if device.led_effect is not None:
                seen_colors.append(device.led_effect.color)
            await asyncio.sleep(0.05)
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    assert LEDState.SUCCESS not in seen_states
    assert "#3399ff" in seen_colors  # the units pulses for a count of 3

    # Read-only: a readout must never write the row it is reporting on.
    store = EventStore(str(db_path))
    try:
        assert store.count_today("coffee") == 3
    finally:
        store.close()


COUNTER_AGREEMENT_CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {
            "name": "Default", "template": "actions", "activation": {"type": "always"},
            "double_tap": {"action": "enter_mode", "target": "Water"},
        },
        {
            "name": "Water", "template": "counter", "activation": {"type": "manual"},
            "event": "water",
        },
    ],
}


async def test_counter_starts_from_the_stores_count_not_zero(tmp_path, monkeypatch):
    """Counting from Home (an ambient `log`, or a readout) and then entering
    the Counter to continue must agree by construction (TODO 15's "one line
    of state") - this presses no gesture inside Home at all, so the only way
    the Counter can show anything but 0 on entry is reading the store."""
    db_path = tmp_path / "e.db"
    seed = EventStore(str(db_path))
    seed.log_event("water")
    seed.log_event("water")
    seed.close()

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(COUNTER_AGREEMENT_CONFIG, database_path=str(db_path))),
        encoding="utf-8",
    )

    # No route to the status line without the web UI (off here, like every
    # other test in this file) - a DeviceStatus that remembers every
    # `last_message` it was given is the plain substitute.
    messages: list[str] = []

    class _RecordingStatus(main.DeviceStatus):
        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == "last_message":
                messages.append(value)

    monkeypatch.setattr(main, "DeviceStatus", _RecordingStatus)

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)

    try:
        device.press(TriggerType.DOUBLE_TAP)  # enter_mode -> Water
        await _drain(device.events)
        await asyncio.sleep(0.1)

        # Continue the same tally from inside the Counter, then leave.
        device.press(TriggerType.SHORT_PRESS)  # +1
        await _drain(device.events)
        await asyncio.sleep(0.1)
        device.press(TriggerType.LONG_PRESS)  # exit
        await _drain(device.events)
        await asyncio.sleep(0.1)
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    # The very first count the Counter ever showed already said 2, not 0.
    assert "water: 2" in messages
    assert "water: 0" not in messages

    store = EventStore(str(db_path))
    try:
        assert store.count_today("water") == 3  # 2 seeded + 1 counter press
    finally:
        store.close()


# --- lifecycle hooks (TODO 31) ---------------------------------------------
# The hooks live on `Mode` and fire from `enter_takeover`, so what has to be
# driven through run() is the *ordering* - a hook is only worth anything if
# "started" arrives before the app draws and "ended" after its session row is
# closed. Nothing below touches the Counter's own code, which is the point:
# zero per-template code means the same two lines serve every takeover.


def _hooked(db_path, **hooks) -> dict:
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "database_path": str(db_path),
        "actions": {"bell": {"action": "log", "event": "bell"}},
        "modes": [
            {
                "name": "Default", "template": "actions",
                "activation": {"type": "always"},
                "long_press": {"action": "enter_mode", "target": "Water"},
            },
            dict({
                "name": "Water", "template": "counter",
                "activation": {"type": "manual"}, "event": "water",
            }, **hooks),
        ],
    }


async def _session(tmp_path, monkeypatch, config) -> list[tuple[str, str]]:
    """Enter Water, count once, leave - and return the log in the order it was
    actually written (`recent` is newest-first over an autoincrementing id)."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    run_task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)

    async def feed(trigger):
        device.press(trigger)
        await _drain(device.events)
        await asyncio.sleep(0.08)

    try:
        await feed(TriggerType.LONG_PRESS)   # enter_mode -> Water
        await feed(TriggerType.SHORT_PRESS)  # +1 -> log water
        await feed(TriggerType.LONG_PRESS)   # exit
        await asyncio.sleep(0.1)
    finally:
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    store = EventStore(config["database_path"])
    try:
        rows = store.recent(100)
    finally:
        store.close()
    return [(kind, name) for (_ts, kind, name, _d, _m, _v) in reversed(rows)]


async def test_hooks_fire_around_the_session_in_the_order_it_happened(tmp_path, monkeypatch):
    """Enter hook after the mode_enter row; exit hook after the mode_exit row
    that closes the session. The row order *is* the assertion - a hook that
    posted "focus started" before the row saying so would be reporting a
    session the log does not have yet.

    The enter hook is spawned rather than awaited, so what is guaranteed is
    that it is *scheduled* before the app runs; it lands at the app's first
    suspension, which for every takeover here is waiting on a press. That is
    why it still sorts ahead of the app's own rows, and it is the ordering a
    non-blocking entry hook can actually promise."""
    order = await _session(tmp_path, monkeypatch, _hooked(
        tmp_path / "events.db",
        on_enter={"action": "log", "event": "water_open"},
        on_exit={"action": "log", "event": "water_shut"},
    ))
    assert order == [
        ("mode_enter", "Water"),
        ("log", "water_open"),
        ("log", "water"),
        ("mode_exit", "Water"),
        ("log", "water_shut"),
    ]


async def test_a_hook_can_name_an_action_from_the_pool(tmp_path, monkeypatch):
    """The fourth place an action is dispatched, so the fourth place a bare
    string has to be resolved (CLAUDE.md). Without `resolve_action` here this
    hook would simply do nothing, silently."""
    order = await _session(tmp_path, monkeypatch, _hooked(
        tmp_path / "events.db", on_exit="bell",
    ))
    assert ("log", "bell") in order
    assert order[-1] == ("log", "bell")  # after the session closed, like any exit hook


async def test_a_failing_hook_costs_the_hook_and_not_the_app(tmp_path, monkeypatch):
    """A MIDI port nobody has - the cheapest real failure there is, and the
    same shape as a webhook that 404s. The app must still open, still count,
    still close, and the *other* hook must still fire."""
    order = await _session(tmp_path, monkeypatch, _hooked(
        tmp_path / "events.db",
        on_enter={"action": "midi", "port": "no-such-port-zzz", "channel": 1,
                  "kind": "note_on", "number": 60, "value": 127},
        on_exit={"action": "log", "event": "water_shut"},
    ))
    assert order == [
        ("mode_enter", "Water"),
        ("log", "water"),
        ("mode_exit", "Water"),
        ("log", "water_shut"),
    ]


async def test_a_hook_naming_nothing_leaves_the_app_untouched(tmp_path, monkeypatch):
    """A dangling name fails the way `handle()` already fails on one: loudly in
    the log, and only for that hook."""
    order = await _session(tmp_path, monkeypatch, _hooked(
        tmp_path / "events.db", on_enter="gone", on_exit="bell",
    ))
    assert order == [
        ("mode_enter", "Water"),
        ("log", "water"),
        ("mode_exit", "Water"),
        ("log", "bell"),
    ]
