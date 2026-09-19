"""How far a notice is allowed to interrupt (TODO 105).

Four tiers as one ordered field, and the property under test is that it is a
*ladder*: each tier's permissions are a strict subset of the one above it. That
is checked as a table against the pure decision function - `main.notice_verdict`
- because a table is what a ladder is, and because the awaiting half is the run
loop's business and would only be re-tested here badly.

The rest is driven through `main.run` with a MockDevice and the web UI off, the
way test_reminders.py and test_sleep.py do, with the clock injected so "it is
07:00" and "six minutes have passed" are facts the test states rather than ones
it waits for.

**One column of the table has no run-loop test, and that is a fact about the
code rather than a gap in the tests.** "Interrupts a running app" cannot be
observed today: the run loop is what calls `scheduler.due_alarm`, and it is not
running while a takeover is - so a notice coming due during an app is never
seen at all, and `scheduler._FIRE_WINDOW` drops it a minute later. Catching
those up is the separately-filed offline/missed-window item. The ladder is
still written and checked over that axis, because it is what decides the
question the day the scheduler stops being blocked by the run loop.
"""

import asyncio
import json
from datetime import datetime, timedelta

import pytest

import aibutton.main as main
from aibutton.config import (
    DEFAULT_INTERRUPTS,
    INTERRUPT_TIERS,
    NoticeBehavior,
    as_dict,
    parse_with_warnings,
)
from aibutton.device import LEDState, MockDevice, Sound, TriggerType
from aibutton.main import NOTICE_MISS, NOTICE_SHOW, NOTICE_WAIT, notice_verdict
from aibutton.store import EventStore

AT = "07:00"
DUE = datetime(2026, 9, 10, 7, 0, 0)


# --- the ladder ------------------------------------------------------------

# tier -> (idle and awake, asleep, an app running). One script rather than
# twelve near-identical cases, because the thing worth asserting is the shape
# of the whole table: read any column downwards and it only ever gets weaker.
LADDER = {
    "always":      (NOTICE_SHOW, NOTICE_SHOW, NOTICE_SHOW),
    "while_awake": (NOTICE_SHOW, NOTICE_WAIT, NOTICE_SHOW),
    "when_free":   (NOTICE_SHOW, NOTICE_WAIT, NOTICE_WAIT),
    "never":       (NOTICE_MISS, NOTICE_MISS, NOTICE_MISS),
}


def _verdict(tier, *, asleep=False, busy=False, timeout=0.0, waited_min=0):
    return notice_verdict(
        NoticeBehavior(interrupts=tier, timeout_minutes=timeout),
        asleep=asleep, busy=busy,
        due_at=DUE, now=DUE + timedelta(minutes=waited_min),
    )


@pytest.mark.parametrize("tier", list(LADDER))
def test_each_tier_answers_both_conditions_as_the_table_says(tier):
    free, asleep, busy = LADDER[tier]
    assert _verdict(tier) is free
    assert _verdict(tier, asleep=True) is asleep
    assert _verdict(tier, busy=True) is busy


def test_the_tiers_are_ordered_and_every_one_is_weaker_than_the_last():
    """The property the single field exists to protect: no tier is allowed to
    be more permissive than the one above it in any column. Two checkboxes
    would offer sixteen combinations, twelve of which are not on this ladder at
    all - this is the assertion that says so."""
    rank = {NOTICE_SHOW: 2, NOTICE_WAIT: 1, NOTICE_MISS: 0}
    rows = [LADDER[tier] for tier in INTERRUPT_TIERS]
    for above, below in zip(rows, rows[1:]):
        assert all(rank[b] <= rank[a] for a, b in zip(above, below))


def test_always_is_the_tier_that_does_not_wait():
    """Stated precisely rather than implied: nothing blocks it, so no timeout
    of any length can turn it into a miss."""
    assert _verdict("always", asleep=True, busy=True, timeout=1, waited_min=99) is NOTICE_SHOW


def test_waiting_becomes_a_miss_on_the_notice_s_own_timeout():
    """Both middle tiers share one rule and one field - 84's
    `timeout_minutes`, not a second one invented for waiting."""
    assert _verdict("while_awake", asleep=True, timeout=5, waited_min=4) is NOTICE_WAIT
    assert _verdict("while_awake", asleep=True, timeout=5, waited_min=5) is NOTICE_MISS
    assert _verdict("when_free", busy=True, timeout=5, waited_min=6) is NOTICE_MISS


def test_with_no_timeout_a_blocked_notice_waits_indefinitely():
    """`timeout_minutes: 0` is 84's "waits until answered" and still is - a
    tier that cannot show yet must not quietly become a tier that gave up."""
    assert _verdict("when_free", busy=True, timeout=0, waited_min=10_000) is NOTICE_WAIT


def test_never_gives_up_at_once_rather_than_waiting_out_a_timeout():
    """The tier most likely to become an accidental no-op. It can never become
    showable, so waiting for that would be a no-op with a timer on it - and
    with the default `timeout_minutes: 0` the timer never fires, which would
    make the whole tier do nothing."""
    assert _verdict("never", timeout=0) is NOTICE_MISS
    assert _verdict("never", timeout=999, waited_min=0) is NOTICE_MISS


# --- the config surface ----------------------------------------------------

def _notice(**fields):
    raw = {"modes": [dict(
        {"name": "Wake", "template": "notice",
         "activation": {"type": "schedule", "at": AT}},
        **fields,
    )]}
    cfg, warnings = parse_with_warnings(raw)
    return cfg.modes[0].behavior, warnings


def test_a_notice_written_before_this_field_lands_on_the_default():
    behavior, _ = _notice()
    assert behavior.interrupts == DEFAULT_INTERRUPTS == "when_free"


@pytest.mark.parametrize("template", ["alarm", "reminders"])
def test_the_migrated_templates_land_on_the_default_too(template):
    """No config anywhere has ever carried this key, so there is no legacy
    meaning to preserve - unlike `urgent`, which the migration fixes."""
    cfg, _ = parse_with_warnings({"modes": [{
        "name": "Wake", "template": template,
        "activation": {"type": "schedule", "at": AT},
    }]})
    assert cfg.modes[0].behavior.interrupts == "when_free"


@pytest.mark.parametrize("bad", ["sometimes", "", 5, None, ["always"]])
def test_an_unknown_tier_falls_back_and_says_so(bad):
    """A bad config never crashes the service, and never silently picks a tier
    either - the fallback is the one that would have applied anyway, and it is
    reported so the editor can show what was actually accepted."""
    behavior, warnings = _notice(interrupts=bad)
    assert behavior.interrupts == "when_free"
    assert any("interrupts" in w for w in warnings)


def test_a_silent_notice_with_nothing_bound_is_warned_about():
    """`never` shows nothing by definition, so with no action bound it is a
    scheduled log row - and "my 9 AM webhook never ran" is otherwise
    indistinguishable from the feature not working."""
    _, warnings = _notice(interrupts="never")
    assert any("never interrupts" in w for w in warnings)


def test_a_silent_notice_that_binds_an_action_is_not_warned_about():
    _, warnings = _notice(
        interrupts="never", on_missed={"action": "log", "event": "posted"},
    )
    assert not any("never interrupts" in w for w in warnings)


def test_the_timeout_warning_does_not_fire_for_a_tier_that_never_shows():
    """"sets on_missed but the timeout is 0, so it can never fire" stopped
    being true for `never`: that tier reaches the missed outcome straight
    away, whatever the timeout says."""
    _, warnings = _notice(
        interrupts="never", timeout_minutes=0,
        on_missed={"action": "log", "event": "posted"},
    )
    assert not any("on_missed" in w and "timeout_minutes is 0" in w for w in warnings)


def test_it_round_trips_through_the_editor():
    """The editor rewrites config.json wholesale, so a field that did not come
    back out would vanish on the first Save."""
    raw = {"modes": [{
        "name": "Wake", "template": "notice",
        "activation": {"type": "schedule", "at": AT},
        "interrupts": "always",
    }]}
    cfg, _ = parse_with_warnings(raw)
    written = as_dict(cfg)
    assert written["modes"][0]["interrupts"] == "always"
    again, _ = parse_with_warnings(written)
    assert again.modes[0].behavior.interrupts == "always"
    assert as_dict(again) == written  # idempotent, like every other field


# --- the run loop ----------------------------------------------------------

class _Recorder(MockDevice):
    """A MockDevice that remembers *that* it was told something, not only the
    last thing it was told - which is what "the light untouched" needs: the
    ember a sleeping button already wears is what an unwanted repaint would
    land on too, so the final state cannot tell the two apart."""

    def __init__(self) -> None:
        super().__init__()
        self.led_calls: list = []
        self.sounds: list = []

    def set_led(self, state: LEDState, effect=None) -> None:
        self.led_calls.append((state, effect))
        super().set_led(state, effect)

    def play_sound(self, sound: Sound) -> None:
        self.sounds.append(sound)
        super().play_sound(sound)

    def start_loop(self, sound: Sound) -> None:
        self.sounds.append(sound)
        super().start_loop(sound)


def _config(db_path, **overrides):
    notice = {
        "name": "Wake",
        "template": "notice",
        "activation": {"type": "schedule", "at": AT},
        "message": "Stand up",
        "log_as": "woke",
        "urgent": False,     # a gentle notice: one chime, no looping tone
        "chime": False,
        "timeout_minutes": 0,
        **overrides,
    }
    return {
        "sounds_enabled": True,  # so a stray ack would actually reach the device
        "web_enabled": False,
        "database_path": str(db_path),
        "modes": [
            {"name": "Home", "template": "actions",
             "activation": {"type": "always"},
             "short_press": {"action": "log", "event": "ping"}},
            notice,
        ],
    }


async def _running(tmp_path, monkeypatch, **overrides):
    """The service, a recording device, and a clock the test moves by hand.

    It starts a minute *before* the notice is due, so a test can arrange the
    button - asleep, awake - before the scheduler ever sees the occurrence.
    """
    db_path = tmp_path / "events.db"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(_config(db_path, **overrides)), encoding="utf-8",
    )
    clock = {"now": DUE - timedelta(minutes=1)}
    monkeypatch.setattr(main.Clock, "now", lambda self: clock["now"])
    monkeypatch.setattr(main, "_SUCCESS_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_ERROR_DISPLAY_S", 0.05)
    monkeypatch.setattr(main, "_SLEEP_FADE_S", 0.05)
    monkeypatch.setattr(main, "_SCHEDULER_TICK_S", 0.05)

    device = _Recorder()
    args = main._parse_args(["--no-web", "--config", str(cfg_path)])
    task = asyncio.create_task(main.run(args, device=device))
    await asyncio.sleep(0.15)  # let run() reach the main loop

    async def feed(trigger: TriggerType):
        device.press(trigger)
        for _ in range(60):
            await asyncio.sleep(0.02)
            if device.events.empty():
                break
        await asyncio.sleep(0.1)

    return device, task, feed, clock, db_path


async def _stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def _settle(seconds: float = 0.4):
    """Give the loop several ticks with nothing else to do."""
    await asyncio.sleep(seconds)


async def _until(predicate, timeout: float = 3.0) -> bool:
    waited = 0.0
    while waited < timeout:
        if predicate():
            return True
        await asyncio.sleep(0.02)
        waited += 0.02
    return False


def _rows(db_path):
    store = EventStore(str(db_path))
    try:
        return [(kind, name, value)
                for (_ts, kind, name, _d, _m, value) in store.recent(200)]
    finally:
        store.close()


async def test_an_always_notice_rings_through_sleep_and_leaves_it_asleep(
    tmp_path, monkeypatch,
):
    """The tier that does not wait, and the whole of what "wakes a sleeping
    button and puts it back" means: the light is the notice's while it is up,
    and the ambient layer is still asleep underneath when it is cleared."""
    device, task, feed, clock, db_path = await _running(
        tmp_path, monkeypatch, interrupts="always",
    )
    try:
        await feed(TriggerType.LONG_PRESS)          # -> asleep
        await _settle()
        clock["now"] = DUE + timedelta(seconds=1)   # -> due
        assert await _until(lambda: device.led_state is LEDState.ALERT), \
            "an always notice must ring through a sleeping button"

        device.press(TriggerType.SHORT_PRESS)       # clears it
        assert await _until(lambda: device.led_state is LEDState.IDLE)
        await _settle(0.2)
        # Still asleep: cleared means back to the dark, not back to the light.
        assert device.led_effect is not None
        assert device.led_effect.color == main._STANDBY_COLOR
    finally:
        await _stop(task)

    assert ("log", "woke", 1) in _rows(db_path)


async def test_a_while_awake_notice_waits_for_a_wake_instead_of_forcing_one(
    tmp_path, monkeypatch,
):
    """The rung that makes the fourth tier worth having: identical to `always`
    while the button is awake, and differs only in refusing to wake it. One
    script, because it is one story - held back, then released by the very
    gesture that wakes the button."""
    device, task, feed, clock, db_path = await _running(
        tmp_path, monkeypatch, interrupts="while_awake",
    )
    try:
        await feed(TriggerType.LONG_PRESS)          # -> asleep
        await _settle()
        clock["now"] = DUE + timedelta(seconds=1)   # -> due, but held back
        await _settle(0.5)
        assert device.led_state is not LEDState.ALERT, \
            "a while_awake notice must not wake a sleeping button"
        assert not any(name == "woke" for _kind, name, _v in _rows(db_path)), \
            "held back is not missed - nothing is logged while it waits"

        await feed(TriggerType.LONG_PRESS)          # -> awake, and it lands
        assert await _until(lambda: device.led_state is LEDState.ALERT), \
            "the notice waited for a wake and must ring once it comes"
        device.press(TriggerType.SHORT_PRESS)
        assert await _until(lambda: device.led_state is LEDState.IDLE)
    finally:
        await _stop(task)

    assert ("log", "woke", 1) in _rows(db_path)


async def test_a_wait_that_runs_out_is_a_miss_and_fires_on_missed(
    tmp_path, monkeypatch,
):
    """Waiting turns into a miss on the notice's own `timeout_minutes` - the
    same field, the same logged 0, the same `on_missed` as a notice nobody
    answered. The clock is moved rather than waited on."""
    device, task, feed, clock, db_path = await _running(
        tmp_path, monkeypatch, interrupts="while_awake", timeout_minutes=5,
        on_missed={"action": "log", "event": "gave_up"},
    )
    try:
        await feed(TriggerType.LONG_PRESS)          # -> asleep
        await _settle()
        clock["now"] = DUE + timedelta(seconds=1)   # -> due, held back
        await _settle(0.3)
        assert device.led_state is not LEDState.ALERT

        clock["now"] = DUE + timedelta(minutes=6)   # the wait runs out
        assert await _until(
            lambda: any(name == "gave_up" for _k, name, _v in _rows(db_path))
        ), "on_missed must fire when the wait outlives timeout_minutes"
        assert device.led_state is not LEDState.ALERT, \
            "it was never allowed to show - giving up must not show it either"
    finally:
        await _stop(task)

    rows = _rows(db_path)
    assert ("log", "woke", 0) in rows, "a miss logs 0, always"
    assert ("log", "woke", 1) not in rows


async def test_a_never_notice_fires_its_action_with_the_light_untouched(
    tmp_path, monkeypatch,
):
    """The gap 105 fills: "at 9 AM, POST this webhook, no light". Not a
    degenerate tier - it is the only way a schedule can do something without an
    app taking the button over, and the failure mode to guard is it quietly
    doing nothing at all."""
    device, task, _feed, clock, db_path = await _running(
        tmp_path, monkeypatch, interrupts="never",
        on_missed={"action": "log", "event": "posted"},
        on_enter={"action": "log", "event": "entered"},
    )
    try:
        await _settle()
        before_led = len(device.led_calls)
        before_sound = len(device.sounds)
        clock["now"] = DUE + timedelta(seconds=1)
        assert await _until(
            lambda: any(name == "posted" for _k, name, _v in _rows(db_path))
        ), "a never notice must still fire its action"
        await _settle(0.3)

        # The point of the tier: nothing was pushed to the light or the buzzer.
        assert device.led_calls[before_led:] == []
        assert device.sounds[before_sound:] == []
        assert device.led_state is not LEDState.ALERT
    finally:
        await _stop(task)

    rows = _rows(db_path)
    assert ("log", "woke", 0) in rows
    # It is still a session that happened, so the hooks a config already binds
    # keep working rather than silently stopping the day it is made silent.
    assert ("log", "entered", None) in rows
    assert any(kind == "mode_enter" and name == "Wake" for kind, name, _v in rows)


async def test_an_ordinary_notice_on_an_awake_button_is_unchanged(
    tmp_path, monkeypatch,
):
    """The regression guard for every notice written before this existed: no
    `interrupts` key, the default tier, an awake and idle button - and it rings
    exactly as it always has."""
    device, task, _feed, clock, db_path = await _running(tmp_path, monkeypatch)
    try:
        await _settle()
        clock["now"] = DUE + timedelta(seconds=1)
        assert await _until(lambda: device.led_state is LEDState.ALERT), \
            "the default tier must not hold back a notice on an idle button"
        device.press(TriggerType.SHORT_PRESS)
        assert await _until(lambda: device.led_state is LEDState.IDLE)
    finally:
        await _stop(task)

    assert ("log", "woke", 1) in _rows(db_path)


async def test_the_legacy_alarm_template_still_rings_on_an_awake_button(
    tmp_path, monkeypatch,
):
    """The same guard one migration back: a config written before TODO 84,
    let alone 105, still behaves like an alarm."""
    device, task, _feed, clock, db_path = await _running(
        tmp_path, monkeypatch, template="alarm", dismiss_event="woke",
    )
    try:
        await _settle()
        clock["now"] = DUE + timedelta(seconds=1)
        assert await _until(lambda: device.led_state is LEDState.ALERT)
        device.press(TriggerType.SHORT_PRESS)
        assert await _until(lambda: device.led_state is LEDState.IDLE)
    finally:
        await _stop(task)

    assert ("log", "woke", 1) in _rows(db_path)
