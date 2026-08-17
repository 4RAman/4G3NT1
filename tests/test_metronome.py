"""The metronome takeover, driven through aibutton.main.run.

Real taps, real gaps: what's being checked is the tempo machine (BPM is a
rolling average of recent tap intervals, a long gap starts the average over,
the LED's live period is floored for flash safety and gone on exit) - not any
habit-tracking, since a metronome deliberately logs nothing of its own to the
event store.
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
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Tempo"}},
        {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"}},
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


async def _run(tmp_path, script, settle=0.15):
    """Start the app, enter the metronome, run `script` (an async function
    given the device), then shut down and return the device."""
    db = tmp_path / "events.db"
    cfg = dict(CONFIG, database_path=str(db))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        device.press(TriggerType.SHORT_PRESS)  # enter_mode -> Tempo
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
    await asyncio.sleep(0.03)  # let the consumer act on it


def _period(device):
    """How fast the LED is actually blinking: the one-off look the metronome
    is pushing if there is one, and the palette entry for its state otherwise.

    Deliberately not `device.palette["METRONOME"]`. The tempo used to be
    rendered by rewriting that entry and is now pushed as an ephemeral effect
    (ROADMAP D4); asserting on what the light is doing rather than on which
    mechanism drives it is what makes these tests outlive the change.
    """
    effect = device.led_effect or device.palette[device.led_state.value]
    return effect.period_s


async def test_entering_shows_the_metronome_light(tmp_path):
    seen = {}

    async def script(device):
        seen["led"] = device.led_state

    await _run(tmp_path, script)
    assert seen["led"] is LEDState.METRONOME


async def test_default_tempo_before_any_taps(tmp_path):
    seen = {}

    async def script(device):
        seen["period"] = _period(device)

    await _run(tmp_path, script)
    # start_bpm's default of 120 - one beat every half second. The mode sets
    # this on entry, so the light keeps time before the first tap rather than
    # showing whatever period the global palette entry carries.
    assert seen["period"] == pytest.approx(0.5)


async def test_two_taps_set_a_live_tempo(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.5)  # roughly 120 BPM
        await _tap(device)
        seen["period"] = _period(device)

    await _run(tmp_path, script)
    assert 0.4 < seen["period"] < 0.65  # ~0.5s period, some real-clock slack


async def test_fast_taps_never_strobe_the_led_past_the_safety_floor(tmp_path):
    """The floor is a photosensitivity cap, not a preference: no tap sequence,
    however fast, may make the light blink more often than it allows."""
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.05)  # far faster than the safety floor allows
        await _tap(device)
        seen["period"] = _period(device)

    await _run(tmp_path, script)
    assert seen["period"] >= main.SAFE_MIN_PERIOD_S


async def test_a_long_gap_resets_the_average_instead_of_averaging_in_the_silence(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.5)
        await _tap(device)  # ~120 BPM established
        seen["first_tempo"] = _period(device)
        await asyncio.sleep(2.5)  # longer than the reset gap
        await _tap(device)  # starts a fresh average - only one tap so far
        seen["after_gap"] = _period(device)
        await asyncio.sleep(1.0)
        await _tap(device)  # second tap of the new average: ~60 BPM
        seen["new_tempo"] = _period(device)

    await _run(tmp_path, script)
    # Unchanged: a lone tap after the gap does not yet have a second tap to
    # average against, so the LED keeps showing the last established tempo.
    assert seen["after_gap"] == seen["first_tempo"]
    assert 0.85 < seen["new_tempo"] < 1.15  # ~60 BPM now, not averaged with the gap


async def test_the_live_tempo_never_touches_the_stored_palette(tmp_path):
    """A session's tempo must not outlive it, or the next metronome starts at
    whatever the last one settled on.

    It now cannot: the tempo is pushed as an ephemeral effect, so METRONOME's
    stored entry still reads as configured *during* the session and there is
    nothing to put back on the way out."""
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.3)
        await _tap(device)
        seen["shown_during"] = _period(device)
        seen["stored_during"] = device.palette["METRONOME"].period_s
        await _tap(device, TriggerType.LONG_PRESS)  # exit
        seen["led"] = device.led_state
        seen["effect_after"] = device.led_effect
        seen["stored_after"] = device.palette["METRONOME"].period_s

    await _run(tmp_path, script)
    assert 0.2 < seen["shown_during"] < 0.45   # the tapped tempo, on screen
    assert seen["stored_during"] == 0.5        # and not in the palette
    assert seen["led"] is LEDState.IDLE
    assert seen["effect_after"] is None
    assert seen["stored_after"] == 0.5


async def test_a_finished_session_logs_its_tempo(tmp_path):
    """One row per session carrying the BPM you settled on. Paired with the
    mode_enter/mode_exit duration, that makes "when did I practise, for how
    long, how fast" a query rather than a guess."""
    db = tmp_path / "events.db"

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.5)  # roughly 120 BPM
        await _tap(device)
        await _tap(device, TriggerType.LONG_PRESS)  # exit

    await _run(tmp_path, script)

    store = EventStore(str(db))
    try:
        rows = store.recent(100)
    finally:
        store.close()

    logged = [(name, value) for (_ts, kind, name, _dur, _mode, value) in rows
              if kind == "log"]
    assert len(logged) == 1
    name, value = logged[0]
    assert name == "metronome"
    assert 95 < value < 145  # ~120 BPM, with real-clock slack

    kinds = [kind for (_ts, kind, _name, _dur, _mode, _val) in rows]
    assert kinds.count("mode_enter") == 1
    assert kinds.count("mode_exit") == 1


async def test_leaving_without_a_tempo_logs_nothing(tmp_path):
    """A session you backed straight out of has no tempo to record, and a row
    with no value would pollute the count of sessions actually practised."""
    db = tmp_path / "events.db"

    async def script(device):
        await _tap(device, TriggerType.LONG_PRESS)  # straight back out

    await _run(tmp_path, script)

    store = EventStore(str(db))
    try:
        kinds = [kind for (_ts, kind, _n, _d, _m, _v) in store.recent(100)]
    finally:
        store.close()

    assert "log" not in kinds
    assert set(kinds) == {"mode_enter", "mode_exit"}


@pytest.mark.parametrize(
    "bpm, period, per_flash",
    [
        (60, 1.0, 1),      # slow: a flash a beat
        (120, 0.5, 1),
        (180, 1 / 3, 1),   # exactly on the floor, still a flash a beat
        (240, 0.5, 2),     # past it: every 2nd beat rather than a faster blink
        (300, 0.4, 2),
        (400, 0.45, 3),    # every 3rd
    ],
)
def test_a_tempo_past_the_floor_marks_every_nth_beat(bpm, period, per_flash):
    """Tempo and flash rate are separate limits: the reported BPM stays honest
    while the light groups beats to stay inside the safety floor."""
    assert main.metronome_flash(bpm) == (pytest.approx(period), per_flash)


@pytest.mark.parametrize("bpm", [1, 45, 179, 180, 181, 240, 600, 3000])
def test_no_tempo_can_make_the_light_blink_past_the_floor(bpm):
    """The property that actually matters, over the whole range rather than
    the handful of tempos above."""
    period, _ = main.metronome_flash(bpm)
    assert period >= main.SAFE_MIN_PERIOD_S


async def test_max_bpm_bounds_what_a_bounced_press_can_register(tmp_path):
    """Two edges milliseconds apart imply an absurd tempo; without a ceiling
    one bad press throws the average away."""
    seen = {}
    db = tmp_path / "events.db"
    cfg = dict(CONFIG, database_path=str(db))
    cfg["modes"] = [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Tempo"}},
        {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"},
         "max_bpm": 200},
    ]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        device.press(TriggerType.SHORT_PRESS)
        await _drain(device.events)
        await asyncio.sleep(0.15)
        await _tap(device)
        await asyncio.sleep(0.02)  # ~3000 BPM if taken at face value
        await _tap(device)
        seen["period"] = _period(device)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Once the cap bites the result stops depending on the clock at all: any
    # interval implying more than 200 BPM lands on exactly 200's grouping,
    # never on the ~3000 BPM the raw 0.02s gap suggested.
    assert seen["period"] == pytest.approx(main.metronome_flash(200)[0])


async def test_the_light_keeps_time_at_the_configured_starting_tempo(tmp_path):
    """The mode owns its starting tempo, so the light is already keeping time
    before the first tap rather than sitting at the global palette's period."""
    seen = {}
    db = tmp_path / "events.db"
    cfg = dict(CONFIG, database_path=str(db))
    cfg["modes"] = [
        {"name": "Default", "template": "actions", "activation": {"type": "always"},
         "short_press": {"action": "enter_mode", "target": "Tempo"}},
        {"name": "Tempo", "template": "metronome", "activation": {"type": "manual"},
         "start_bpm": 60},
    ]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        device.press(TriggerType.SHORT_PRESS)
        await _drain(device.events)
        await asyncio.sleep(0.15)
        seen["period"] = _period(device)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert seen["period"] == pytest.approx(1.0)  # 60 BPM = one beat a second
