"""Hot/Cold's pure core: where the wheel is, how wrong you were, what happens next.

No device, no clock, no asyncio - the point of `hotcold.step` being a step
function is that a whole session is a list of calls with numbers in it.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.config import (
    HotColdBehavior,
    as_dict,
    parse_config,
    parse_with_warnings,
)
from aibutton.button import DOUBLE_WINDOW_S as LATENCY
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.store import EventStore
from aibutton.hotcold import (
    snap,
    GUESS,
    LEAVE,
    NEXT,
    START,
    Game,
    Leave,
    Reveal,
    Score,
    Spin,
    closeness,
    distance,
    phase_at,
    step,
    tally,
)


def game(**kw) -> Game:
    # latency_s as a real button would report it: these tests are about the
    # case where a gesture arrives after the finger moved. It defaults to 0 on
    # the dataclass because an injected press has no such delay.
    base = dict(
        sweep_s=4.0, rounds=0, tolerance=0.08, reveal_s=1.5, latency_s=LATENCY,
    )
    return Game(**{**base, **kw})


# --- where the wheel is ----------------------------------------------------


def test_a_press_is_dated_back_to_when_the_finger_went_down():
    """The scenario the whole compensation exists for: the player stops the
    wheel at the half-way mark, and the gesture only reaches us a tap-window
    later. Without the correction they would be scored on where the wheel had
    got to by then, which is a different colour entirely."""
    aimed_at = 2.0  # half of a 4 s sweep
    arrived_at = aimed_at + LATENCY
    assert phase_at(0.0, arrived_at, 4.0, LATENCY) == pytest.approx(0.5)


def test_an_instant_press_needs_no_correction():
    """The other half of the same rule: a gesture injected by the web UI or a
    test arrives when it was made, so correcting it would move the answer."""
    assert phase_at(0.0, 2.0, 4.0, 0.0) == pytest.approx(0.5)


def test_a_press_already_in_flight_wraps_backwards_rather_than_going_negative():
    """Pressing as the round begins dates the press before the spin. A wheel
    has no negative positions, so it reads as just short of a full turn."""
    assert phase_at(0.0, 0.0, 4.0, LATENCY) == pytest.approx(0.9)


def test_a_wheel_that_never_moves_is_not_a_division_by_zero():
    assert phase_at(0.0, 10.0, 0.0, LATENCY) == 0.0


@pytest.mark.parametrize(
    "first,second,expected",
    [
        (0.5, 0.5, 0.0),  # dead on
        (0.25, 0.5, 0.5),  # a quarter turn apart
        (0.0, 0.5, 1.0),  # half a turn - as far as a circle allows
        (0.95, 0.05, 0.2),  # across the wrap, the short way round
        (0.05, 0.95, 0.2),  # and the same from the other side
    ],
)
def test_distance_is_measured_the_short_way_round(first, second, expected):
    assert distance(first, second) == pytest.approx(expected)


def test_closeness_is_the_other_end_of_distance():
    assert closeness(0.5, 0.5) == pytest.approx(1.0)
    assert closeness(0.0, 0.5) == pytest.approx(0.0)


# --- the session -----------------------------------------------------------


def test_entering_spins_the_wheel_and_hides_a_target():
    after, effects = step(game(), START, now=10.0, next_target=0.3)
    assert effects == (Spin(4.0),)
    assert (after.target, after.spun_at) == (0.3, 10.0)


def test_a_perfect_guess_scores_and_counts_as_a_hit():
    playing = game(target=0.5, spun_at=0.0)
    after, effects = step(playing, GUESS, now=2.0 + LATENCY)
    score, reveal = effects
    assert score == Score(pytest.approx(1.0))
    assert reveal.hit and reveal.closeness == pytest.approx(1.0)
    assert (after.played, after.hits) == (1, 1)


def test_a_guess_outside_the_tolerance_still_scores_but_is_not_a_hit():
    playing = game(target=0.5, spun_at=0.0)
    # A quarter turn late: closeness 0.5, well outside a 0.08 tolerance.
    after, effects = step(playing, GUESS, now=3.0 + LATENCY)
    _, reveal = effects
    assert not reveal.hit
    assert reveal.closeness == pytest.approx(0.5)
    assert (after.played, after.hits) == (1, 0)


def test_the_best_guess_of_the_session_is_kept():
    playing = game(target=0.5, spun_at=0.0)
    playing, _ = step(playing, GUESS, now=3.0 + LATENCY)  # 0.5
    playing, _ = step(playing, GUESS, now=2.0 + LATENCY)  # 1.0
    assert playing.best == pytest.approx(1.0)


def test_a_fixed_number_of_rounds_ends_the_session_itself():
    playing = game(rounds=1, target=0.5, spun_at=0.0)
    after, effects = step(playing, GUESS, now=2.0 + LATENCY)
    assert isinstance(effects[-1], Leave)
    assert after.over


def test_zero_rounds_plays_until_you_leave():
    playing = game(rounds=0, target=0.5, spun_at=0.0)
    after, effects = step(playing, GUESS, now=2.0 + LATENCY)
    assert not any(isinstance(e, Leave) for e in effects)
    assert not after.over


def test_the_reveal_being_over_deals_another_round():
    after, effects = step(game(played=1), NEXT, now=20.0, next_target=0.8)
    assert effects == (Spin(4.0),)
    assert (after.target, after.spun_at) == (0.8, 20.0)


def test_leaving_reports_what_happened():
    playing = game(played=3, hits=2, best=0.91)
    after, (leave,) = step(playing, LEAVE, now=30.0)
    assert after.over
    assert leave.message == "hot/cold - 2/3 on target, best 91%"


def test_leaving_without_playing_says_so():
    _, (leave,) = step(game(), LEAVE, now=1.0)
    assert leave.message == "hot/cold - no guesses"


def test_a_finished_game_is_inert():
    """Totality: a late press arriving after the session ended must not deal a
    round nobody is watching."""
    over = game(over=True)
    assert step(over, GUESS, now=99.0) == (over, ())


def test_an_event_the_game_does_not_know_changes_nothing():
    playing = game()
    assert step(playing, "sneeze", now=1.0) == (playing, ())


# --- the config surface ----------------------------------------------------


def test_a_broken_field_costs_that_field_and_not_the_mode():
    """The standing rule: a bad config never crashes the service, and every
    key falls back on its own."""
    # The ambient Always mode is here only to keep the count honest: without
    # one, _ensure_ambient_always seeds "Home" and adds a warning of its own,
    # which says nothing about whether a broken field cost the mode.
    cfg, warnings = parse_with_warnings({
        "modes": [{
            "name": "Game", "template": "hotcold", "activation": {"type": "manual"},
            "sweep_s": -3, "rounds": "lots", "tolerance": 9, "log_as": "",
        }, {
            "name": "Base", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "log", "event": "x"},
        }],
    })
    mode = next(m for m in cfg.modes if m.name == "Game")
    defaults = HotColdBehavior()
    assert mode.behavior.sweep_s == defaults.sweep_s
    assert mode.behavior.rounds == defaults.rounds
    assert mode.behavior.tolerance == defaults.tolerance
    assert mode.behavior.log_as == defaults.log_as
    assert len(warnings) == 4, warnings


def test_a_hotcold_mode_round_trips_through_the_editor():
    raw = {"modes": [{
        "name": "Game", "template": "hotcold", "activation": {"type": "manual"},
        "sweep_s": 2.5, "rounds": 3, "tolerance": 0.2, "reveal_s": 0.5,
        "log_as": "wheel",
    }]}
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


def test_a_game_may_not_be_started_by_a_schedule():
    """A game that started itself would be a game interrupting you."""
    cfg, warnings = parse_with_warnings({
        "modes": [{"name": "Game", "template": "hotcold",
                   "activation": {"type": "schedule", "at": "09:00"}}],
    })
    assert not any(m.name == "Game" for m in cfg.modes)
    assert warnings


# --- the driver ------------------------------------------------------------
# Scoring is settled above with numbers; what is worth driving a real loop for
# is the wiring - that the wheel goes out as one effect, that a guess writes a
# row, and that long press leaves. Asserting an exact score here would only be
# asserting the test's own timing.

GAME = [
    {"name": "Home", "template": "actions", "activation": {"type": "always"},
     "long_press": {"action": "enter_mode", "target": "Game"}},
    {"name": "Game", "template": "hotcold", "activation": {"type": "manual"},
     "log_as": "wheel", "sweep_s": 4, "reveal_s": 0.05, "rounds": 0},
]


def _config(db, modes=None, **over):
    return {
        "sounds_enabled": False, "web_enabled": False, "database_path": str(db),
        "modes": modes if modes is not None else GAME, **over,
    }


async def _start(tmp_path, raw):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(raw), encoding="utf-8")
    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(cfg)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)
    return task, device


async def _press(device, trigger, settle=0.12):
    device.press(trigger)
    await asyncio.sleep(settle)


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _rows(db, name):
    store = EventStore(str(db))
    try:
        return [
            (n, v) for (_ts, _k, n, _d, _m, v) in store.recent(100) if n == name
        ]
    finally:
        store.close()


async def test_the_wheel_goes_out_as_one_rainbow_effect(tmp_path):
    """One write per round is the whole reason this game is playable over a
    fire-and-forget link - the host works out the phase rather than streaming
    a colour per frame."""
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.LONG_PRESS)  # enter the game
        assert device.led_state is LEDState.LISTENING
        assert device.led_effect.style == "rainbow"
        assert device.led_effect.period_s == 4
    finally:
        await _stop(task)


async def test_a_guess_logs_how_close_it_was(tmp_path):
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.LONG_PRESS)   # enter
        await _press(device, TriggerType.SHORT_PRESS)  # stop the wheel
        rows = _rows(db, "wheel")
        assert len(rows) == 1
        (_name, value), = rows
        assert 0.0 <= value <= 100.0
    finally:
        await _stop(task)


async def test_a_guess_shows_a_solid_colour_off_the_ramp(tmp_path):
    """The reveal has to be readable as a colour, which means it stops
    spinning - a rainbow answer would be no answer at all."""
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.LONG_PRESS)
        device.press(TriggerType.SHORT_PRESS)
        await asyncio.sleep(0.02)  # inside the reveal window
        assert device.led_effect.style == "solid"
    finally:
        await _stop(task)


async def test_long_press_leaves_the_game(tmp_path):
    """Long press means 'up one level' everywhere, games included."""
    db = tmp_path / "events.db"
    task, device = await _start(tmp_path, _config(db))
    try:
        await _press(device, TriggerType.LONG_PRESS)  # enter
        await _press(device, TriggerType.LONG_PRESS)  # and out again
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


async def test_a_fixed_round_count_ends_the_session_without_a_press(tmp_path):
    db = tmp_path / "events.db"
    modes = [GAME[0], dict(GAME[1], rounds=1)]
    task, device = await _start(tmp_path, _config(db, modes=modes))
    try:
        await _press(device, TriggerType.LONG_PRESS)   # enter
        await _press(device, TriggerType.SHORT_PRESS)  # the only round
        await asyncio.sleep(0.1)  # the reveal, then it closes itself
        assert device.led_state is LEDState.IDLE
    finally:
        await _stop(task)


# --- quantising the wheel --------------------------------------------------
# A continuous wheel is far harder than it reads: a press is accurate to a few
# tens of milliseconds against a four-second sweep, so the honest target is
# about one percent of a turn.


@pytest.mark.parametrize("phase,expected", [
    (0.00, 1 / 24),          # start of the first place -> its centre
    (1 / 24, 1 / 24),        # already the centre -> unchanged
    (0.083, 1 / 24),         # just short of the boundary -> still the first
    (1 / 12, 3 / 24),        # over it -> the second place
    (0.999, 23 / 24),        # the last place, not wrapped to the first
])
def test_snapping_lands_on_the_centre_of_a_place(phase, expected):
    assert snap(phase, 12) == pytest.approx(expected)


def test_a_continuous_wheel_snaps_to_nothing():
    assert snap(0.37, 0) == 0.37


def test_anywhere_in_the_right_place_scores_the_same():
    """The whole point: two presses that landed in the same place must score
    identically, however far apart they were inside it.

    Twelve places put a boundary exactly on 0.5, so the target here is 0.55 -
    comfortably inside place 6, which spans 0.5 to 0.583."""
    playing = game(segments=12, target=0.55, spun_at=0.0)
    early, _ = step(playing, GUESS, now=0.51 * 4.0 + LATENCY)
    late, _ = step(playing, GUESS, now=0.57 * 4.0 + LATENCY)
    assert early.best == late.best == pytest.approx(1.0)
    assert early.hits == late.hits == 1


def test_a_boundary_is_a_boundary_and_the_grid_does_not_hide_that():
    """Quantising moves where the edges are; it does not remove them. Two
    presses 0.06 of a turn apart across a boundary are still different
    answers, and pretending otherwise would just be a bigger tolerance."""
    playing = game(segments=12, target=0.55, spun_at=0.0)
    inside, _ = step(playing, GUESS, now=0.51 * 4.0 + LATENCY)
    outside, _ = step(playing, GUESS, now=0.49 * 4.0 + LATENCY)
    assert inside.hits == 1
    assert outside.hits == 0


def test_the_neighbouring_place_is_still_a_miss_at_the_default_tolerance():
    """Quantising must not make the game free - one place either side is
    0.167 apart normalised, comfortably outside a 0.08 tolerance."""
    playing = game(segments=12, target=0.5, spun_at=0.0)
    after, effects = step(playing, GUESS, now=(0.5 + 1 / 12) * 4.0 + LATENCY)
    _, reveal = effects
    assert not reveal.hit
    assert after.hits == 0


def test_a_smooth_wheel_still_behaves_exactly_as_it_did():
    """segments: 0 is the old game, unchanged - this is the regression guard
    for everyone who liked it hard."""
    playing = game(segments=0, target=0.5, spun_at=0.0)
    _, effects = step(playing, GUESS, now=2.0 + LATENCY)
    score, reveal = effects
    assert score == Score(pytest.approx(1.0))
    assert reveal.hit


# --- what it reports on the way out (TODO 32) ------------------------------


def test_the_session_reports_the_numbers_it_actually_holds():
    played = game(played=4, hits=3, best=0.87)
    assert tally(played) == {"played": 4, "hits": 3, "best_pct": 87.0}


def test_a_game_nobody_played_reports_zeros_rather_than_gaps():
    """The key set is the same on every exit, because one of the carriers is
    positional - a `best_pct` that appeared only after a guess would shift
    every OSC argument after it. `played: 0` is what says the rest is empty."""
    assert set(tally(game())) == set(tally(game(played=4, hits=3, best=0.87)))
    assert tally(game())["best_pct"] == 0.0
