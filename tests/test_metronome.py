"""The metronome takeover, driven through aibutton.main.run.

Real taps, real gaps: what's being checked is the tempo machine (BPM is a
rolling average of recent tap intervals, a long gap starts the average over,
the LED's live period is floored for flash safety and reverted to the
configured palette on exit) - not any habit-tracking, since a metronome
deliberately logs nothing of its own to the event store.
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


async def test_entering_shows_the_metronome_light(tmp_path):
    seen = {}

    async def script(device):
        seen["led"] = device.led_state

    await _run(tmp_path, script)
    assert seen["led"] is LEDState.METRONOME


async def test_default_tempo_before_any_taps(tmp_path):
    seen = {}

    async def script(device):
        seen["period"] = device.palette["METRONOME"].period_s

    await _run(tmp_path, script)
    assert seen["period"] == 0.5  # the configured default, untouched


async def test_two_taps_set_a_live_tempo(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.5)  # roughly 120 BPM
        await _tap(device)
        seen["period"] = device.palette["METRONOME"].period_s

    await _run(tmp_path, script)
    assert 0.4 < seen["period"] < 0.65  # ~0.5s period, some real-clock slack


async def test_fast_taps_are_floored_for_flash_safety(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.05)  # far faster than the safety floor allows
        await _tap(device)
        seen["period"] = device.palette["METRONOME"].period_s

    await _run(tmp_path, script)
    assert seen["period"] == pytest.approx(main._METRONOME_MIN_PERIOD_S)


async def test_a_long_gap_resets_the_average_instead_of_averaging_in_the_silence(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.5)
        await _tap(device)  # ~120 BPM established
        seen["first_tempo"] = device.palette["METRONOME"].period_s
        await asyncio.sleep(2.5)  # longer than the reset gap
        await _tap(device)  # starts a fresh average - only one tap so far
        seen["after_gap"] = device.palette["METRONOME"].period_s
        await asyncio.sleep(1.0)
        await _tap(device)  # second tap of the new average: ~60 BPM
        seen["new_tempo"] = device.palette["METRONOME"].period_s

    await _run(tmp_path, script)
    # Unchanged: a lone tap after the gap does not yet have a second tap to
    # average against, so the LED keeps showing the last established tempo.
    assert seen["after_gap"] == seen["first_tempo"]
    assert 0.85 < seen["new_tempo"] < 1.15  # ~60 BPM now, not averaged with the gap


async def test_exit_restores_the_configured_palette(tmp_path):
    seen = {}

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.3)
        await _tap(device)
        await _tap(device, TriggerType.LONG_PRESS)  # exit
        seen["led"] = device.led_state
        seen["period"] = device.palette["METRONOME"].period_s

    await _run(tmp_path, script)
    assert seen["led"] is LEDState.IDLE
    assert seen["period"] == 0.5  # reverted to the configured default


async def test_no_tempo_data_is_logged_only_lifecycle(tmp_path):
    db = tmp_path / "events.db"

    async def script(device):
        await _tap(device)
        await asyncio.sleep(0.3)
        await _tap(device)
        await _tap(device, TriggerType.LONG_PRESS)

    await _run(tmp_path, script)

    store = EventStore(str(db))
    try:
        rows = store.recent(100)
    finally:
        store.close()

    kinds = [kind for (_ts, kind, _name, _dur, _mode) in rows]
    # Entering/exiting is logged like any takeover mode, but the metronome
    # itself never calls store.log_event/toggle_timer - purely live, by design.
    assert set(kinds) == {"mode_enter", "mode_exit"}
    assert kinds.count("mode_enter") == 1
    assert kinds.count("mode_exit") == 1
