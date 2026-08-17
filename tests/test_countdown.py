"""The countdown takeover, driven through aibutton.main.run.

The ramp maths itself lives in test_ramp.py, where it can be a table over a
pure function. What is checked here is the wiring: that the colour actually
moves as the clock runs, that style and period stay put while it does, that
the light is handed back on the way out, and that a finished run is recorded.

Durations are kept to fractions of a minute so the suite stays quick; the
loop measures against the event loop's clock, so nothing here waits on a
wall-clock minute.
"""

import asyncio
import json

import pytest

import aibutton.main as main
from aibutton.device import LEDState, MockDevice, TriggerType
from aibutton.ramp import Stop
from aibutton.store import EventStore

RED, GREEN, BLUE = "#ff0000", "#00ff00", "#0000ff"


@pytest.fixture(autouse=True)
def _fast_tick(monkeypatch):
    """Shorten how often a running countdown re-evaluates its ramp.

    The tick is a wake-up rate, not behaviour: the colour is pushed when it has
    moved, whatever the rate. Left at its one-second default, a countdown short
    enough for a test would evaluate once and the ramp would never appear to
    move - which is a property of the test, not of the loop.
    """
    monkeypatch.setattr(main, "_COUNTDOWN_TICK_S", 0.05)


def _config(db, **countdown):
    """A Default mode whose short press enters a countdown called Tea."""
    return {
        "sounds_enabled": False,
        "web_enabled": False,
        "database_path": str(db),
        "modes": [
            {"name": "Default", "template": "actions", "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "Tea"}},
            {"name": "Tea", "template": "countdown", "activation": {"type": "manual"},
             **countdown},
        ],
    }


async def _drain(queue, timeout=2.0):
    waited = 0.0
    while not queue.empty():
        await asyncio.sleep(0.02)
        waited += 0.02
        if waited > timeout:
            raise AssertionError("press was not consumed in time")


async def _run(tmp_path, script, settle=0.15, **countdown):
    db = tmp_path / "events.db"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_config(db, **countdown)), encoding="utf-8")

    device = MockDevice()
    args = main._parse_args(["--no-web", "--config", str(path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.1)
    try:
        device.press(TriggerType.SHORT_PRESS)  # enter_mode -> Tea
        await _drain(device.events)
        await asyncio.sleep(settle)
        await script(device)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return device


def _timing(device):
    """What the LED is actually showing: the one-off look the countdown is
    pushing if there is one, and the palette entry for its state otherwise.

    Deliberately *not* `device.palette["TIMING"]`. A countdown used to walk its
    colour by rewriting that entry; it now pushes an ephemeral effect and
    leaves the stored palette alone (ROADMAP D4). Asserting on what is on
    screen rather than on which mechanism put it there is what let these tests
    survive that change unedited below the helper.
    """
    return device.led_effect or device.palette[device.led_state.value]


# --- the ramp actually moves ----------------------------------------------

async def test_the_colour_walks_the_ramp_as_the_clock_runs(tmp_path):
    """The whole point: same light, same flash, colour travelling from one end
    of the ramp to the other."""
    seen = {}

    async def script(device):
        seen["start"] = _timing(device).color
        await asyncio.sleep(0.5)   # half of a 1-second countdown
        seen["middle"] = _timing(device).color
        await asyncio.sleep(0.45)
        seen["late"] = _timing(device).color

    await _run(tmp_path, script, settle=0.02,
               minutes=1 / 60, ramp=[RED, GREEN, BLUE], ring_on_finish=False)

    assert seen["start"] == RED
    assert seen["middle"] not in (RED, BLUE)   # somewhere in the blend
    assert seen["late"] != seen["start"]


async def test_style_and_period_hold_still_while_the_colour_moves(tmp_path):
    """A countdown flashes at a steady rate the whole way through - the ramp
    drives colour only. If the period moved too, the light would speed up as
    well as change, which is a different (and unasked-for) effect."""
    seen = {}

    async def script(device):
        seen["first"] = (_timing(device).style, _timing(device).period_s, _timing(device).color)
        await asyncio.sleep(0.6)
        seen["later"] = (_timing(device).style, _timing(device).period_s, _timing(device).color)

    await _run(tmp_path, script, settle=0.02,
               minutes=1 / 60, style="flash", period_s=0.5,
               ramp=[RED, BLUE], ring_on_finish=False)

    assert seen["first"][:2] == ("flash", 0.5)
    assert seen["later"][:2] == ("flash", 0.5)
    assert seen["first"][2] != seen["later"][2]


async def test_a_countdown_borrows_the_timing_light(tmp_path):
    """No new wire code was allocated for this: it shows TIMING wearing a
    pushed look (ROADMAP D4). The state still means something - it is what the
    status line and the web UI report - and only its appearance is borrowed."""
    seen = {}

    async def script(device):
        seen["led"] = device.led_state

    await _run(tmp_path, script, minutes=1, ring_on_finish=False)
    assert seen["led"] is LEDState.TIMING


async def test_the_configured_period_is_floored_for_flash_safety(tmp_path):
    """The floor applies to anything that flashes, not just the metronome."""
    seen = {}

    async def script(device):
        seen["period"] = _timing(device).period_s

    await _run(tmp_path, script, minutes=1, period_s=0.02, ring_on_finish=False)
    assert seen["period"] == pytest.approx(main.SAFE_MIN_PERIOD_S)


# --- leaving ---------------------------------------------------------------

async def test_long_press_cancels_early(tmp_path):
    """Every takeover mode must be escapable with a press - a five-minute
    countdown you cannot get out of owns the button for five minutes."""
    async def script(device):
        await _drain_after(device, TriggerType.LONG_PRESS)

    device = await _run(tmp_path, script, minutes=5, ring_on_finish=False)
    assert device.led_state is LEDState.IDLE


async def _drain_after(device, trigger):
    device.press(trigger)
    await _drain(device.events)
    await asyncio.sleep(0.1)


async def test_the_ramp_never_touches_the_stored_palette(tmp_path):
    """The override must never outlive the session, or every later stopwatch
    inherits a countdown's colour.

    It now cannot, and that is the point of the change rather than a detail of
    it: the look is pushed as an ephemeral effect, so TIMING's stored entry
    still reads as configured *while the countdown is running*. Nothing has to
    remember to put anything back."""
    seen = {}

    async def script(device):
        seen["during"] = _timing(device).color
        seen["stored_during"] = device.palette["TIMING"].color
        await _drain_after(device, TriggerType.LONG_PRESS)
        seen["effect_after"] = device.led_effect
        seen["stored_after"] = (
            device.palette["TIMING"].color, device.palette["TIMING"].style
        )

    await _run(tmp_path, script, minutes=5, style="flash",
               ramp=[RED, BLUE], ring_on_finish=False)

    assert seen["during"] == RED                       # the ramp is on screen
    assert seen["stored_during"] == "#00ffff"          # and not in the palette
    assert seen["effect_after"] is None                # gone on the way out
    assert seen["stored_after"] == ("#00ffff", "breathe")


async def test_a_cancelled_countdown_logs_nothing(tmp_path):
    """Only a run that reached zero counts as a countdown done."""
    db = tmp_path / "events.db"

    async def script(device):
        await _drain_after(device, TriggerType.LONG_PRESS)

    await _run(tmp_path, script, minutes=5, ring_on_finish=False)

    store = EventStore(str(db))
    try:
        kinds = [kind for (_ts, kind, _n, _d, _m, _v) in store.recent(100)]
    finally:
        store.close()
    assert "log" not in kinds


# --- finishing -------------------------------------------------------------

async def test_finishing_logs_the_length_it_ran_for(tmp_path):
    db = tmp_path / "events.db"

    async def script(device):
        await asyncio.sleep(1.2)  # outlive a 1-second countdown

    await _run(tmp_path, script, settle=0.02,
               minutes=1 / 60, ring_on_finish=False, log_as="tea")

    store = EventStore(str(db))
    try:
        logged = [(name, value) for (_ts, kind, name, _d, _m, value)
                  in store.recent(100) if kind == "log"]
    finally:
        store.close()

    assert len(logged) == 1
    name, value = logged[0]
    assert name == "tea"
    assert value == pytest.approx(1 / 60)


async def test_finishing_rings_until_dismissed(tmp_path):
    """A finished countdown *is* an alarm going off, so it reuses that loop
    rather than growing a second copy of it."""
    seen = {}

    async def script(device):
        await asyncio.sleep(1.2)
        seen["ringing"] = device.led_state
        await _drain_after(device, TriggerType.SHORT_PRESS)  # dismiss
        seen["after"] = device.led_state

    await _run(tmp_path, script, settle=0.02, minutes=1 / 60, ring_on_finish=True)

    assert seen["ringing"] is LEDState.ALERT
    assert seen["after"] is LEDState.IDLE


async def test_a_silent_countdown_does_not_ring(tmp_path):
    seen = {}

    async def script(device):
        await asyncio.sleep(1.2)
        seen["led"] = device.led_state

    await _run(tmp_path, script, settle=0.02, minutes=1 / 60, ring_on_finish=False)
    assert seen["led"] is not LEDState.ALERT


# --- traffic ---------------------------------------------------------------

async def test_the_colour_is_only_pushed_when_it_visibly_moves(tmp_path):
    """A ramp evaluated every second over a long countdown must not push a
    write every second - the radio's contract is fire-and-forget, and the
    queue is the thing that suffers."""
    pushes = []

    async def script(device):
        original = device.set_led

        def counting(state, effect=None):
            if effect is not None:
                pushes.append(effect.color)
            original(state, effect)

        device.set_led = counting
        await asyncio.sleep(1.0)

    await _run(tmp_path, script, settle=0.02,
               minutes=10, ramp=[RED, BLUE], ring_on_finish=False)

    # Ten minutes of ramp seen for one second: the colour has barely moved, so
    # the ticks should almost all be silent.
    assert len(pushes) <= 2
