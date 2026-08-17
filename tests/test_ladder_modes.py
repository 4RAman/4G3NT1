"""The subdivision ladder as a mode setting: parsing, and what it does to the
light on a running stopwatch and countdown.

The pure arithmetic lives in test_ladder.py. What is asserted here is the part
that only exists once a ladder is attached to something: that it is opt-in,
that a bad rung costs a rung, and that a running timer actually paints it.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import LadderSpec, as_dict, parse_config, parse_with_warnings
from aibutton.device import LEDState, MockDevice, TriggerType

LADDER = {
    "enabled": True,
    "tick_s": 0.5,
    "base": "#000000",
    "rungs": [
        {"every_s": 10, "color": "#ffffff"},
        {"every_s": 5, "color": "#ffff00"},
        {"every_s": 2, "color": "#66ccff"},
        {"every_s": 1, "color": "#0033aa"},
    ],
}


def _stopwatch(**ladder):
    return {"modes": [{
        "name": "Focus", "template": "stopwatch", "activation": {"type": "manual"},
        "log_as": "focus", "ladder": {**LADDER, **ladder},
    }]}


def _spec(raw):
    return parse_config(raw).modes[0].behavior.ladder


# --- it is a setting, and it is off unless asked for -----------------------

def test_a_timer_has_no_ladder_unless_you_turn_one_on():
    """It replaces the mode's look with a clock, which should never be a
    surprise the first time someone opens a stopwatch."""
    cfg = parse_config({"modes": [{
        "name": "Focus", "template": "stopwatch",
        "activation": {"type": "manual"}, "log_as": "focus",
    }]})
    assert cfg.modes[0].behavior.ladder.enabled is False


def test_the_default_rungs_are_the_readable_ones():
    """The defaults are the spec: white on the ten, yellow on the five,
    light/dark blue on even/odd seconds."""
    spec = LadderSpec()
    assert [(r.every_s, r.color) for r in spec.rungs] == [
        (10.0, "#ffffff"), (5.0, "#ffff00"), (2.0, "#66ccff"), (1.0, "#0033aa"),
    ]
    assert spec.tick_s == 0.5


@pytest.mark.parametrize("template,extra", [
    ("stopwatch", {"log_as": "focus"}),
    ("countdown", {"minutes": 1, "log_as": "cd"}),
    ("metronome", {"log_as": "metronome"}),
])
def test_both_time_based_templates_accept_one(template, extra):
    cfg = parse_config({"modes": [{
        "name": "T", "template": template, "activation": {"type": "manual"},
        "ladder": LADDER, **extra,
    }]})
    assert cfg.modes[0].behavior.ladder.enabled is True


# --- a bad ladder costs a colour, never the mode ---------------------------

def test_one_broken_rung_is_dropped_and_the_rest_survive():
    spec = _spec(_stopwatch(rungs=[
        {"every_s": 10, "color": "#ffffff"},
        {"every_s": 0, "color": "#ff0000"},      # no interval to divide by
        {"every_s": 2, "color": "not a colour"},  # unreadable
        {"every_s": 1, "color": "#0033aa"},
    ]))
    assert [(r.every_s, r.color) for r in spec.rungs] == [
        (10.0, "#ffffff"), (1.0, "#0033aa"),
    ]


def test_a_bad_tick_costs_the_tick_not_the_ladder():
    spec = _spec(_stopwatch(tick_s=-1))
    assert spec.tick_s == LadderSpec().tick_s
    assert spec.enabled is True


def test_an_enabled_ladder_with_no_usable_rungs_turns_itself_off():
    """One flat colour is not a time reference, and showing it while claiming
    to be one is worse than falling back to the mode's ordinary look."""
    cfg, warnings = parse_with_warnings(_stopwatch(rungs=[{"every_s": 0, "color": "#fff"}]))
    assert cfg.modes[0].behavior.ladder.enabled is False
    assert any("no usable rungs" in w for w in warnings)


def test_a_ladder_that_is_not_an_object_is_ignored():
    assert _spec(_stopwatch()) and parse_config({"modes": [{
        "name": "Focus", "template": "stopwatch", "activation": {"type": "manual"},
        "log_as": "focus", "ladder": "yes please",
    }]}).modes[0].behavior.ladder.enabled is False


def test_colours_are_normalised_by_the_parser_everyone_else_uses():
    """'#' optional, case-folded - one opinion about what a colour is."""
    spec = _spec(_stopwatch(base="FFAA00", rungs=[{"every_s": 1, "color": "#00FF00"}]))
    assert spec.base == "#ffaa00"
    assert spec.rungs[0].color == "#00ff00"


def test_it_round_trips_through_the_editor():
    once = parse_config(_stopwatch())
    assert parse_config(as_dict(once)).modes[0].behavior == once.modes[0].behavior


def test_the_serialised_ladder_reads_top_down():
    dumped = as_dict(parse_config(_stopwatch(rungs=[
        {"every_s": 1, "color": "#0033aa"},
        {"every_s": 10, "color": "#ffffff"},
    ])))
    assert [r["every_s"] for r in dumped["modes"][0]["ladder"]["rungs"]] == [10.0, 1.0]


# --- what a running timer actually shows -----------------------------------

CONFIG = {
    "sounds_enabled": False,
    "web_enabled": False,
    "modes": [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "Focus"}},
        {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"},
         "log_as": "focus", "ladder": LADDER},
    ],
}


async def _running_stopwatch(tmp_path, monkeypatch, config=CONFIG):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(dict(config, database_path=str(tmp_path / "events.db"))),
        encoding="utf-8",
    )
    device = MockDevice()
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)
    device.press(TriggerType.LONG_PRESS)  # enter the stopwatch
    await asyncio.sleep(0.25)
    return task, device


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_running_stopwatch_paints_the_ladder(tmp_path, monkeypatch):
    task, device = await _running_stopwatch(tmp_path, monkeypatch)
    try:
        assert device.led_state is LEDState.TIMING
        seen = {device.led_effect.color}
        # Two seconds covers the 1s and 2s rungs at least once each, so the
        # light must have changed colour without anyone pressing anything.
        for _ in range(20):
            await asyncio.sleep(0.1)
            if device.led_effect is not None:
                seen.add(device.led_effect.color)
        assert len(seen) > 1, f"the ladder never changed colour: {seen}"
    finally:
        await _stop(task)


async def test_the_ladder_is_shown_as_a_solid_not_a_flash(tmp_path, monkeypatch):
    """The tick supplies the rhythm; asking the device to also flash inside
    each tick would be two clocks on one light."""
    task, device = await _running_stopwatch(tmp_path, monkeypatch)
    try:
        assert device.led_effect is not None
        assert device.led_effect.style == "solid"
    finally:
        await _stop(task)


async def test_a_stopwatch_without_a_ladder_does_not_wake_to_repaint(tmp_path, monkeypatch):
    """No ladder, no tick - it still blocks on the next press, so a plain
    stopwatch costs no radio traffic at all."""
    plain = dict(CONFIG, modes=[
        CONFIG["modes"][0],
        {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"},
         "log_as": "focus"},
    ])
    task, device = await _running_stopwatch(tmp_path, monkeypatch, plain)
    try:
        before = device.led_effect
        await asyncio.sleep(0.6)
        assert device.led_effect is before
    finally:
        await _stop(task)


async def test_the_stopwatch_still_exits_on_a_long_press(tmp_path, monkeypatch):
    """The tick must not eat presses - a takeover mode has to stay escapable."""
    task, device = await _running_stopwatch(tmp_path, monkeypatch)
    try:
        device.press(TriggerType.LONG_PRESS)
        await asyncio.sleep(0.4)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


async def test_the_metronome_colours_beats_without_being_tapped(tmp_path, monkeypatch):
    """Its ladder counts beats, and it runs from start_bpm before the first
    tap - the light should be keeping time the moment you enter."""
    beats = dict(CONFIG, modes=[
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "Beat"}},
        {"name": "Beat", "template": "metronome", "activation": {"type": "manual"},
         "log_as": "metronome", "start_bpm": 240, "sound_on_tap": False,
         "ladder": {"enabled": True, "base": "#000000", "rungs": [
             {"every_s": 4, "color": "#ffffff"},
             {"every_s": 2, "color": "#66ccff"},
             {"every_s": 1, "color": "#0033aa"},
         ]}},
    ])
    task, device = await _running_stopwatch(tmp_path, monkeypatch, beats)
    try:
        assert device.led_state is LEDState.METRONOME
        seen = set()
        for _ in range(24):
            await asyncio.sleep(0.1)
            if device.led_effect is not None:
                seen.add(device.led_effect.color)
        assert len(seen) > 1, f"the beat ladder never changed colour: {seen}"
    finally:
        await _stop(task)


async def test_a_metronome_without_a_ladder_still_pulses_at_the_tempo(tmp_path, monkeypatch):
    """The ladder replaces the device-rendered pulse; without one, the old
    behaviour has to be untouched."""
    plain = dict(CONFIG, modes=[
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "long_press": {"action": "enter_mode", "target": "Beat"}},
        {"name": "Beat", "template": "metronome", "activation": {"type": "manual"},
         "log_as": "metronome", "start_bpm": 120, "sound_on_tap": False},
    ])
    task, device = await _running_stopwatch(tmp_path, monkeypatch, plain)
    try:
        assert device.led_state is LEDState.METRONOME
        # 120 BPM is a 0.5s beat, and the device is asked to pulse at it.
        assert device.led_effect is not None
        assert device.led_effect.period_s == pytest.approx(0.5)
        assert device.led_effect.style != "solid"
    finally:
        await _stop(task)


async def test_the_tick_is_floored_for_flash_safety(tmp_path, monkeypatch):
    """A 0.05s tick is a 20 Hz colour change however sedate the style - the
    hole flash_safe cannot see, because it reads period_s and a solid never
    strobes by its own reckoning."""
    fast = dict(CONFIG, modes=[
        CONFIG["modes"][0],
        {"name": "Focus", "template": "stopwatch", "activation": {"type": "manual"},
         "log_as": "focus", "ladder": {**LADDER, "tick_s": 0.05}},
    ])
    task, device = await _running_stopwatch(tmp_path, monkeypatch, fast)
    try:
        changes = 0
        last = device.led_effect.color if device.led_effect else None
        for _ in range(20):
            await asyncio.sleep(0.05)
            now = device.led_effect.color if device.led_effect else None
            if now != last:
                changes += 1
                last = now
        # One second of wall time at the 3 Hz floor allows at most a handful of
        # changes; an unfloored 0.05s tick would allow twenty.
        assert changes <= 6, f"{changes} colour changes in ~1s - the floor did not apply"
    finally:
        await _stop(task)
