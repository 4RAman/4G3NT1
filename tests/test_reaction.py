"""The reaction timer: false starts, honest milliseconds, and the wiring.

The interesting assertions are all in the pure half - a reaction timer is a
subtraction with two corrections in it, and the whole reason `reaction.step`
exists is that the subtraction can be checked with numbers rather than by
racing a real clock.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import (
    ReactionBehavior,
    as_dict,
    parse_config,
    parse_with_warnings,
)
from aibutton.button import DOUBLE_WINDOW_S as LATENCY
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.reaction import (
    GO,
    LEAVE,
    NEXT,
    PRESS,
    START,
    Arm,
    Game,
    Go,
    Leave,
    Result,
    Score,
    step,
    summary,
)
from aibutton.store import EventStore


def game(**kw) -> Game:
    # latency_s as a real button would report it - see the same helper in
    # test_hotcold.py. Zero is the dataclass default, for an injected press.
    return Game(**{"rounds": 0, "reveal_s": 0.05, "latency_s": LATENCY, **kw})


# --- the measurement -------------------------------------------------------


def test_the_time_is_measured_from_the_light_to_the_finger():
    """The press arrives a tap-window after the finger moved, so a 250 ms
    reaction reaches us 650 ms after the light. Reporting that would be
    reporting the radio, not the player."""
    lit = game(lit_at=100.0)
    _, effects = step(lit, PRESS, now=100.25 + LATENCY)
    score, result = effects
    assert score.ms == pytest.approx(250.0)
    assert result.ms == pytest.approx(250.0)
    assert not result.false_start


def test_pressing_before_the_light_is_a_false_start():
    lit = game(lit_at=100.0)
    after, (result,) = step(lit, PRESS, now=99.9 + LATENCY)
    assert result.false_start and result.ms is None
    assert after.false_starts == 1
    assert after.lit_at is None, "a false start has to re-arm, not stay live"


def test_a_press_made_before_the_light_but_arriving_after_it_is_still_early():
    """The case the correction exists for: physically pressed at 99.95 and
    delivered at 100.35, which without the correction looks like a heroic
    350 ms *after* the light."""
    lit = game(lit_at=100.0)
    _, (result,) = step(lit, PRESS, now=99.95 + LATENCY)
    assert result.false_start


def test_pressing_while_still_dark_is_a_false_start():
    _, (result,) = step(game(lit_at=None), PRESS, now=50.0)
    assert result.false_start


def test_scores_are_not_logged_for_false_starts():
    _, effects = step(game(lit_at=None), PRESS, now=50.0)
    assert not any(isinstance(e, Score) for e in effects)


# --- the session -----------------------------------------------------------


def test_entering_arms_the_first_attempt():
    _, effects = step(game(), START, now=1.0, next_delay=3.5)
    assert effects == (Arm(3.5),)


def test_the_go_signal_starts_the_clock():
    after, effects = step(game(), GO, now=42.0)
    assert effects == (Go(),)
    assert after.lit_at == 42.0


def test_arming_is_a_separate_step_from_showing_the_result():
    """Emitting both at once would blank the answer before it could be read."""
    lit = game(lit_at=0.0)
    _, effects = step(lit, PRESS, now=0.3 + LATENCY)
    assert not any(isinstance(e, Arm) for e in effects)
    after, rearm = step(game(), NEXT, now=9.0, next_delay=2.0)
    assert rearm == (Arm(2.0),)
    assert after.lit_at is None


def test_a_fixed_attempt_count_ends_the_session_itself():
    lit = game(rounds=1, lit_at=0.0)
    after, effects = step(lit, PRESS, now=0.3 + LATENCY)
    assert isinstance(effects[-1], Leave)
    assert after.over


def test_the_best_and_the_average_are_both_reported():
    playing = game(lit_at=0.0)
    playing, _ = step(playing, PRESS, now=0.4 + LATENCY)  # 400 ms
    playing, _ = step(playing, GO, now=10.0)
    playing, _ = step(playing, PRESS, now=10.2 + LATENCY)  # 200 ms
    assert summary(playing) == "reaction - best 200 ms, average 300 ms"


def test_false_starts_are_counted_in_the_summary():
    playing = game()
    playing, _ = step(playing, PRESS, now=1.0)  # dark: false start
    assert summary(playing) == "reaction - no times (1 false starts)"


def test_a_finished_game_is_inert():
    over = game(over=True)
    assert step(over, PRESS, now=99.0) == (over, ())


def test_leaving_reports_what_happened():
    after, (leave,) = step(game(), LEAVE, now=5.0)
    assert after.over and leave.message == "reaction - no times"


# --- the config surface ----------------------------------------------------


def test_a_broken_field_costs_that_field_and_not_the_mode():
    cfg, warnings = parse_with_warnings({
        "modes": [{
            "name": "Sharp", "template": "reaction", "activation": {"type": "manual"},
            "min_delay_s": 0, "rounds": -2, "log_as": "",
        }],
    })
    mode = next(m for m in cfg.modes if m.name == "Sharp")
    defaults = ReactionBehavior()
    assert mode.behavior.min_delay_s == defaults.min_delay_s
    assert mode.behavior.rounds == defaults.rounds
    assert mode.behavior.log_as == defaults.log_as
    assert len(warnings) == 3, warnings


def test_an_inverted_delay_range_is_swapped_rather_than_rejected():
    """A range with the ends the wrong way round is obviously meant as a
    range; refusing it would hang the first attempt with nothing to explain
    why."""
    cfg, warnings = parse_with_warnings({
        "modes": [{
            "name": "Sharp", "template": "reaction", "activation": {"type": "manual"},
            "min_delay_s": 8, "max_delay_s": 3,
        }],
    })
    behavior = next(m for m in cfg.modes if m.name == "Sharp").behavior
    assert (behavior.min_delay_s, behavior.max_delay_s) == (3.0, 8.0)
    assert warnings


def test_a_reaction_mode_round_trips_through_the_editor():
    raw = {"modes": [{
        "name": "Sharp", "template": "reaction", "activation": {"type": "manual"},
        "min_delay_s": 1, "max_delay_s": 2, "rounds": 3, "slowest_ms": 900,
        "reveal_s": 0.4, "log_as": "sharp",
    }]}
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


# --- the driver ------------------------------------------------------------

GAME = [
    {"name": "Home", "template": "actions", "activation": {"type": "always"},
     "long_press": {"action": "enter_mode", "target": "Sharp"}},
    {"name": "Sharp", "template": "reaction", "activation": {"type": "manual"},
     "log_as": "sharp", "min_delay_s": 0.2, "max_delay_s": 0.2,
     "reveal_s": 0.05, "rounds": 0},
]


async def _start(tmp_path, modes):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "sounds_enabled": False, "web_enabled": False,
        "database_path": str(tmp_path / "events.db"), "modes": modes,
    }), encoding="utf-8")
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)
    return task, device


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _values(db, name):
    store = EventStore(str(db))
    try:
        return [v for (_ts, _k, n, _d, _m, v) in store.recent(100) if n == name]
    finally:
        store.close()


async def test_it_goes_dark_then_lights_up_on_its_own(tmp_path):
    task, device = await _start(tmp_path, GAME)
    try:
        device.press(TriggerType.LONG_PRESS)  # enter
        await asyncio.sleep(0.1)  # inside the 0.2s armed wait
        assert device.led_effect.color == main._REACTION_DARK
        await asyncio.sleep(0.25)  # past it
        assert device.led_effect.color == "#ffffff"
        assert device.led_state is LEDState.LISTENING
    finally:
        await _stop(task)


async def test_an_attempt_logs_its_milliseconds(tmp_path):
    task, device = await _start(tmp_path, GAME)
    try:
        device.press(TriggerType.LONG_PRESS)
        await asyncio.sleep(0.35)  # let it light up
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.15)
        values = _values(tmp_path / "events.db", "sharp")
        assert len(values) == 1
        assert values[0] >= 0.0
    finally:
        await _stop(task)


async def test_a_false_start_logs_nothing(tmp_path):
    task, device = await _start(tmp_path, GAME)
    try:
        device.press(TriggerType.LONG_PRESS)
        await asyncio.sleep(0.05)  # still dark
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.15)
        assert _values(tmp_path / "events.db", "sharp") == []
    finally:
        await _stop(task)


async def test_long_press_leaves_the_game(tmp_path):
    task, device = await _start(tmp_path, GAME)
    try:
        device.press(TriggerType.LONG_PRESS)
        await asyncio.sleep(0.35)
        device.press(TriggerType.LONG_PRESS)
        await asyncio.sleep(0.15)
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)
