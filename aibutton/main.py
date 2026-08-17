"""AI Button orchestrator - the host half of the ESP32 split.

Run it (web UI live at http://localhost:8080, with simulated presses):
    python -m aibutton.main --config config.json

One-shot smoke test (each trigger once, then exit):
    python -m aibutton.main --demo --no-web

All hardware sits behind one ButtonDevice ([device.py](device.py)):
gestures arrive on its `events` queue, LED and sound go back out through
it. `--ble` puts the real ESP32 there; without it the device is MockDevice
and the "hardware" is the web UI's virtual device panel.

The button is always in some mode. Per gesture: resolve the (trigger,
time-of-day) against the *ambient* modes (the actions-template ones,
first match wins), execute the matched action primitive (log /
timer_toggle / webhook), and surface the result on the LED, the sound,
and the web UI.

Alarms are *takeover* modes, not gesture-resolved: each loop iteration
asks scheduler.due_alarm() whether a scheduled alarm mode's occurrence
has arrived, and if so ring_alarm() owns the device (ALERT LED + looping
tone) until a press dismisses or snoozes it. The press-wait polls on a
<=1s timeout so the test clock stays responsive and an alarm added live
(web UI or SIGHUP) starts firing within a second.

Signals: SIGHUP reloads the config, SIGTERM/SIGINT shut down cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import math
import signal
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from . import ladder, ramp
from .device import (
    SAFE_MIN_PERIOD_S,
    STYLE_USES_COLOR,
    ButtonDevice,
    LEDState,
    MockDevice,
    Sound,
    TriggerType,
    max_taps_for,
)
from .single_instance import AlreadyRunning, SingleInstance

log = logging.getLogger("aibutton")

# How long the ERROR flashes get to play before returning to IDLE.
_ERROR_DISPLAY_S = 1.5
# SUCCESS hold time; the device's green window matches it.
_SUCCESS_DISPLAY_S = 2.0
# The press wait wakes at least this often so a scheduled alarm is noticed
# within a second of its minute - crucial for the test clock (set 06:59 -> a
# 07:00 alarm rings ~1s later) and so an alarm added live via the web UI or
# SIGHUP starts firing without waiting for an unrelated press. Polling
# unconditionally (not only when an alarm exists *now*) is what lets a newly
# configured alarm engage immediately after a hot reload; the idle cost is one
# cheap scheduler scan per second. It also paces the loop's fault backoff.
_SCHEDULER_TICK_S = 1.0

# The shortest period the LED may flash at: roughly 3 times a second, per
# WCAG 2.3.1. It now lives in device.py as SAFE_MIN_PERIOD_S (config imports it
# too, and device.py is the module both may import) and it is the *default* for
# `min_flash_period_s` rather than a law - one button on one desk, and its
# owner may decide it can go faster. Everything here reads the config's
# effective value; this name is only the fallback for a pure function nobody
# handed one to.
#
# Two consumers, and they work around it differently because they mean
# different things: run_metronome marks every Nth beat (so raising max_bpm
# makes the button faster without making the light more dangerous), while
# run_countdown floors its configured period. When effects become stop lists
# the floor has to be defined over *transitions* rather than over a period.

# How often a running countdown re-evaluates its ramp. The colour is only
# actually pushed when it has visibly moved (ramp.differs), so this is a
# wake-up rate, not a write rate.
_COUNTDOWN_TICK_S = 1.0
# Per-channel difference before a new ramp colour is worth a palette write.
# ~1.5% of the range: below this it is not a colour change, it is traffic.
_COUNTDOWN_COLOR_STEP = 4

# How slowly a reminder breathes when it has no look of its own. Slow enough
# to be obviously not the alarm's flash, which is the whole distinction.
_REMINDER_PERIOD_S = 2.0


def metronome_flash(
    bpm: float, min_period_s: float = SAFE_MIN_PERIOD_S
) -> tuple[float, int]:
    """(LED period, how many beats each flash stands for) for a tempo of `bpm`.

    Module-level and pure on purpose. It is the one part of the metronome that
    is logic rather than I/O, and what it enforces is a safety property - so it
    is worth checking as a table rather than by tapping a mock device against a
    real clock, where the assertion ends up being about scheduler jitter.

    Tempo and flash rate are separate limits. Past roughly 180 BPM a beat is
    shorter than the light may legally blink, so instead of clamping the tempo
    (which would lie about it) or blinking through the floor (which would be a
    hazard), each flash marks the smallest whole number of beats that lands
    back inside the floor.
    """
    beat_s = 60.0 / bpm
    per_flash = max(1, math.ceil(min_period_s / beat_s))
    return beat_s * per_flash, per_flash


async def _wait_for_trigger(
    queue: asyncio.Queue, stop: asyncio.Event, timeout: float | None = None
):
    """Wait for the next button press, or None once `stop` fires (or the
    optional `timeout` elapses).

    Shared by the main loop and ring_alarm's dismiss/snooze wait, so a
    ringing or snoozing alarm never blocks graceful shutdown - without
    this, SIGTERM during a 9-minute snooze would hang for up to 9
    minutes.

    The main loop passes a short `timeout` so it wakes at least once a
    second to recompute scheduled alarm fires against the (possibly test-)
    clock; a None return then means "tick, nothing pressed" rather than
    "shutting down" - the caller distinguishes via stop.is_set().
    """
    get_task = asyncio.create_task(queue.get())
    stop_task = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {get_task, stop_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    if get_task in done:
        return get_task.result()
    get_task.cancel()
    return None


@dataclass
class DeviceStatus:
    """Live device state, as the web UI and the REST API see it."""

    state: str = "IDLE"
    last_trigger: str | None = None
    last_mode: str | None = None
    last_ok: bool | None = None
    last_message: str = ""
    started_at: float = field(default_factory=time.time)
    # Virtual-hardware mirror for the web UI's dev panel:
    led_state: str = "IDLE"
    # The ephemeral look overriding led_state's palette entry, if a mode is
    # pushing one. The virtual LED renders it in preference to the palette,
    # which is what keeps the browser showing what the real button shows.
    led_effect: object | None = None
    last_sound: str | None = None
    sound_seq: int = 0  # bumped per sound so the browser knows when to replay


@dataclass
class FaultTracker:
    """Counts main-loop faults and decides which ones get logged.

    Pure - it never logs, it only answers "is this one worth a traceback?",
    so the throttle is testable without a clock or a logger. The reason it
    exists: a fault that recurs every tick writes a traceback a second, and
    over the 24-hour soak in ROADMAP.md that is both a full disk and a log
    nobody can read. The first fault always logs; after that, one per
    `interval_s`.
    """

    interval_s: float = 60.0
    count: int = 0
    last_logged: float | None = None

    def record(self, now: float) -> bool:
        """Register a fault at monotonic time `now`. True if it should be
        logged now."""
        self.count += 1
        if self.last_logged is None or now - self.last_logged >= self.interval_s:
            self.last_logged = now
            return True
        return False


@dataclass
class Clock:
    """Wall clock with a settable offset - the web UI's "test clock".

    Ambient mode resolution and the alarm scheduler read time through
    this, so time-windowed modes and scheduled alarms can be tested
    without waiting for the right hour (set 06:59, watch a 07:00 alarm
    fire seconds later). The offset keeps ticking (set 06:30, a minute
    later it is 06:31), never persists across restarts, and does not
    affect event-log timestamps, which stay real UTC.
    """

    delta: timedelta = timedelta(0)

    def now(self) -> datetime:
        return datetime.now() + self.delta

    @property
    def overridden(self) -> bool:
        return self.delta != timedelta(0)

    def set(self, target: datetime) -> None:
        self.delta = target - datetime.now()

    def clear(self) -> None:
        self.delta = timedelta(0)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Button service")
    p.add_argument(
        "--config",
        default=None,
        help="config path (default: $AIBUTTON_CONFIG or ./config.json)",
    )
    p.add_argument(
        "--ble",
        action="store_true",
        help="drive the real ESP32 button over BLE (default: the in-memory MockDevice)",
    )
    p.add_argument("--no-web", action="store_true", help="run without the web UI")
    p.add_argument(
        "--demo",
        action="store_true",
        help="run one pass of every trigger, then exit",
    )
    p.add_argument(
        "--no-lock",
        action="store_true",
        help="skip the single-instance guard (two copies will fight over the button)",
    )
    return p.parse_args(argv)


async def run(args: argparse.Namespace, device: ButtonDevice | None = None) -> None:
    """Drive the button until `stop` fires. `device` is the hardware seam:
    --ble picks the real ESP32, otherwise the in-memory MockDevice, and
    tests inject their own. Nothing past this point knows the difference."""
    from .actions import ActionResult, _fmt_elapsed, execute
    from .audio import ToneLibrary
    from .config import (
        AlarmBehavior,
        ConfigManager,
        CountdownBehavior,
        CounterBehavior,
        EnterModeAction,
        MetronomeBehavior,
        PomodoroBehavior,
        ReminderBehavior,
        StopwatchBehavior,
        bound_triggers,
        flash_safe,
        look_for,
    )
    from .rules import resolve
    from .scheduler import due_alarm
    from .store import EventStore

    cm = ConfigManager(args.config)
    # One process per button. BLE allows a single central, and two copies also
    # share the event database and the web port. Tests inject `device` and get
    # no lock: they run many services in one session against temp databases,
    # and none of them touch real hardware.
    guard = None
    if device is None and not args.no_lock:
        guard = SingleInstance(Path(cm.config.database_path).with_suffix(".lock"))
        guard.acquire()  # raises AlreadyRunning; main() turns that into exit 1
    status = DeviceStatus()
    clock = Clock()
    if device is None:
        if args.ble:
            from .ble_device import BLEDevice  # deferred: pulls in bleak

            device = BLEDevice(cm.config.ble_device_name)
        else:
            device = MockDevice()
    # Connecting happens in the background: a button that is out of range or
    # unplugged must not stop the web UI and the scheduler from coming up.
    await device.start()

    def wanted_max_taps() -> int:
        """How far the device should count taps, given what the config binds.

        Derived rather than configured because it is not a preference: counting
        to three is what makes a double tap wait out its window, so a button
        pays that only once a triple tap is bound to something.
        """
        return max_taps_for(TriggerType(name) for name in bound_triggers(cm.config.modes))

    device.set_gesture_config(wanted_max_taps())
    tones = ToneLibrary()
    store = EventStore(cm.config.database_path)

    # The takeover mode that currently owns the button, if any. Kept here so
    # `set_led` can find the look it wears without every run_* loop having to
    # be handed its own Mode and pass it along on every call.
    active_mode = None

    def set_led(state: LEDState, effect=None) -> None:
        """Show `state`, optionally wearing a one-off `effect` instead of its
        palette entry - which is how a mode gets its own look without
        allocating a global LEDState (ROADMAP D4).

        With no explicit effect, the *active mode's* look for this state is
        used if it has chosen one. That is what makes two Pomodoros able to
        look different: the state stays `WORKING` for both, and only its
        appearance differs. A mode that has chosen nothing resolves to None and
        the device falls back to the palette, exactly as before looks existed.
        """
        if effect is None:
            effect = look_for(cm.config, active_mode, state)
        # The one gate every pushed look passes through, which is why the floor
        # is enforced here rather than in each run_* loop: a mode computing its
        # own effect (the metronome's period, the countdown's colour) cannot
        # route around it, and neither can a look someone hand-edited into a
        # scene file. The palette's own entries are floored where they are
        # pushed - the device renders those without asking.
        effect = flash_safe(effect, cm.config.min_flash_period_s)
        device.set_led(state, effect)
        status.led_state = state.value
        status.led_effect = effect

    def push_palette(palette: dict) -> None:
        """Send the stored palette, floored. Separate from `set_led` because
        the device renders these entries on its own when no effect overrides
        them, so a strobing palette entry would never pass through the gate
        above."""
        device.set_palette(
            {
                name: flash_safe(entry, cm.config.min_flash_period_s)
                for name, entry in palette.items()
            }
        )

    # Deferred until push_palette exists, rather than pushed raw at connect
    # time: the very first palette the button ever sees has to be inside the
    # floor too. Nothing between here and device.start() reads the palette.
    push_palette(cm.config.led_palette)

    def base_look(state: LEDState):
        """The look a mode should build its live effect on top of - its own if
        it has one, the palette entry otherwise. What `run_countdown` walks the
        colour of, and what `run_metronome` rewrites the period of."""
        return look_for(cm.config, active_mode, state) or cm.config.led_palette.get(
            state.value
        )

    def ladder_paint(spec, state: LEDState):
        """A `paint(seconds)` that shows `spec`'s colour for a moment in time.

        Returns `(paint, tick_s)` - the cadence comes back because the caller
        has to wake at it, and because it is not always the configured one.

        **The flash floor applies to the cadence, not to the effect's period.**
        A ladder changes colour every tick, so a 0.1s tick is a 10 Hz change
        rate however sedate the underlying style is - which is exactly the hole
        `flash_safe` cannot see, since it reads `period_s` and a `solid` never
        strobes by its own reckoning. Flooring the tick is the same safety
        property enforced over the axis that actually moves here.

        Colours are pushed only when they change, for the reason ramp.differs
        exists: a ladder is a couple of writes a second on a radio whose whole
        contract is fire-and-forget, and most ticks repeat the previous colour.
        """
        tick = max(spec.tick_s, cm.config.min_flash_period_s)
        shown: str | None = None

        def paint(seconds: float) -> None:
            nonlocal shown
            index = ladder.tick_index(seconds, tick)
            colour = ladder.color_for_tick(spec.rungs, index, tick, spec.base)
            if colour == shown:
                return
            base = base_look(state)
            if base is None:
                return
            shown = colour
            # `solid` because the ladder *is* the animation - the tick supplies
            # the rhythm, so asking the device to also flash inside each tick
            # would be two clocks on one light.
            set_led(state, replace(base, style="solid", color=colour))

        return paint, tick

    def play_sound(sound: Sound) -> None:
        """Feedback tone + the web UI's mirror of it. sounds_enabled is read
        per press, so muting the button takes effect on the next reload."""
        if not cm.config.sounds_enabled:
            return
        device.play_sound(sound)
        status.last_sound = sound.value
        status.sound_seq += 1

    def start_loop(sound: Sound) -> None:
        if not cm.config.sounds_enabled:
            return
        device.start_loop(sound)
        status.last_sound = sound.value
        status.sound_seq += 1

    def stop_loop() -> None:
        device.stop_loop()

    set_led(LEDState.IDLE)

    def set_status(state: str) -> None:
        status.state = state

    # Created before the web UI so the stop endpoint can be handed the same
    # event the signal handlers below set - one shutdown path, three ways in.
    stop = asyncio.Event()

    web_server = None
    web_task = None
    if not args.no_web and cm.config.web_enabled:
        try:
            from .webui import WebContext, create_app, make_server

            ctx = WebContext(
                cm=cm,
                store=store,
                status=status,
                device=device,
                clock=clock,
                tones=tones,
                # The endpoint runs on this loop, so setting the event
                # directly is safe and needs no thread hop.
                on_stop=stop.set,
                # Frozen here so the scene endpoints can tell the user which
                # of their changes are waiting on a restart: the store, the
                # lock, the web bind and the BLE name were all decided above.
                startup_config=cm.config,
            )
            web_server = make_server(
                create_app(ctx), cm.config.web_host, cm.config.web_port
            )
            web_task = asyncio.create_task(web_server.serve())
            web_task.add_done_callback(
                lambda t: not t.cancelled()
                and t.exception()
                and log.error("web UI stopped: %s", t.exception())
            )
            log.info(
                "web UI on http://%s:%d", cm.config.web_host, cm.config.web_port
            )
        except Exception as exc:
            log.error("web UI unavailable (%s) - continuing without it", exc)
            web_server = None

    loop = asyncio.get_running_loop()

    # SIGHUP is POSIX-only and reloads the config. SIGTERM/SIGINT exist
    # everywhere and are the graceful-shutdown hook - they used to sit behind
    # the same SIGHUP check, which meant Windows (the host this actually runs
    # on) had no graceful shutdown at all: Ctrl+C unwound as KeyboardInterrupt
    # straight through the takeover loops instead of letting them exit on
    # `stop` and stop their own timers and alarms.
    if hasattr(signal, "SIGHUP"):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signal.SIGHUP, cm.reload)

    def _fallback_handler(signum, _frame) -> None:
        # A second Ctrl+C restores the default handler, so an interrupt during
        # a wedged shutdown still kills the process instead of being swallowed.
        with contextlib.suppress(ValueError, OSError):
            signal.signal(signum, signal.SIG_DFL)
        loop.call_soon_threadsafe(stop.set)

    # SIGBREAK is Windows-only and is what a Ctrl+Break sent to our process
    # group arrives as - the control panel stops the service that way
    # precisely so this graceful path runs instead of a hard terminate.
    shutdown_signals = [signal.SIGTERM, signal.SIGINT]
    if hasattr(signal, "SIGBREAK"):
        shutdown_signals.append(signal.SIGBREAK)
    for sig in shutdown_signals:
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError, ValueError, RuntimeError):
            # Windows' ProactorEventLoop has no add_signal_handler; signal()
            # runs the handler on the main thread, so hop back onto the loop
            # before touching the Event.
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, _fallback_handler)

    async def fail(message: str) -> None:
        log.error("%s", message)
        status.last_ok = False
        status.last_message = message
        set_led(LEDState.ERROR)
        play_sound(Sound.ERROR)
        set_status("ERROR")
        await asyncio.sleep(_ERROR_DISPLAY_S)

    async def ring_alarm(behavior: AlarmBehavior, mode_name: str) -> ActionResult:
        """Ring (ALERT LED + looping ALARM tone) for a takeover alarm mode
        until the next press dismisses it, or - on long_press with
        snooze_minutes set - go quiet for that long and ring again. The
        snooze wait uses _wait_for_trigger so SIGTERM during a long snooze
        still shuts down promptly instead of waiting it out."""
        label = behavior.message or behavior.label or mode_name
        if args.demo:
            # --demo runs unattended: no press will ever arrive to dismiss
            # this, so show it briefly instead of hanging the smoke test.
            set_led(LEDState.ALERT)
            start_loop(Sound.ALARM)
            status.last_message = label
            set_status("ALARMING")
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            stop_loop()
            return ActionResult(True, f"{label} (demo: rings until dismissed)")
        while True:
            set_led(LEDState.ALERT)
            start_loop(Sound.ALARM)
            status.last_message = label
            set_status("ALARMING")
            trigger = await _wait_for_trigger(device.events, stop)
            stop_loop()
            if trigger is None:  # shutting down mid-ring
                set_led(LEDState.IDLE)
                return ActionResult(True, f"{label} (interrupted by shutdown)")
            if trigger is TriggerType.LONG_PRESS and behavior.snooze_minutes > 0:
                set_led(LEDState.IDLE)
                set_status("IDLE")
                message = f"{label} - snoozed {behavior.snooze_minutes:g} min"
                try:
                    await asyncio.wait_for(stop.wait(), timeout=behavior.snooze_minutes * 60)
                    return ActionResult(True, message)  # shutting down mid-snooze
                except asyncio.TimeoutError:
                    continue  # snooze elapsed; ring again
            if behavior.dismiss_event:
                store.log_event(behavior.dismiss_event, mode=mode_name)
            return ActionResult(True, f"Dismissed: {label}")

    def reminder_look(behavior: ReminderBehavior):
        """What a reminder shows on ALERT.

        A named look wins, exactly as everywhere else. With none chosen the
        fallback is *not* the bare ALERT palette entry, because that is the
        ringing-alarm look and a reminder that is indistinguishable from an
        alarm has failed at the one thing it is for. Breathing the same colour
        reads as "notice me" where the alarm's hard flash reads as "deal with
        me", and it costs no wire code: it is an ephemeral effect over the
        state the mode already owns.
        """
        chosen = look_for(cm.config, active_mode, LEDState.ALERT)
        if chosen is not None:
            return chosen
        base = cm.config.led_palette.get(LEDState.ALERT.value)
        return None if base is None else replace(
            base, style="breathe", period_s=max(base.period_s, _REMINDER_PERIOD_S)
        )

    async def run_reminder(behavior: ReminderBehavior, mode_name: str) -> ActionResult:
        """A scheduled nudge: flash until any press clears it, or until it
        gives up on its own.

        Three deliberate differences from `ring_alarm`, which is the template
        this parallels and does not touch:

        *Any* press clears it, rather than a nominated gesture. Requiring a
        specific one would make a reminder as demanding as an alarm, which is
        the thing it exists not to be - and it keeps the "escapable with a
        press" invariant trivially true.

        No snooze, and no loop. A reminder that could be postponed is an alarm
        with extra steps; if you want it again, schedule it again.

        It times out. `timeout_minutes` (0 = wait forever) is the other half of
        being ignorable - a reminder nobody was in the room for should not
        still be flashing at midnight. A timeout is not a clear: nothing is
        logged, because nobody saw it.
        """
        label = behavior.message or behavior.label or mode_name
        set_led(LEDState.ALERT, reminder_look(behavior))
        if behavior.chime:
            play_sound(Sound.ACK)  # once - the light is what persists
        status.last_message = label
        set_status("REMINDING")

        if args.demo:
            # --demo runs unattended: no press will ever arrive, so show it
            # briefly rather than hanging the smoke test.
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"{label} (demo: flashes until cleared)")

        timeout = behavior.timeout_minutes * 60 if behavior.timeout_minutes > 0 else None
        trigger = await _wait_for_trigger(device.events, stop, timeout)
        if trigger is None:
            if stop.is_set():
                return ActionResult(True, f"{label} (interrupted by shutdown)")
            return ActionResult(True, f"{label} - not cleared, gave up")
        if behavior.cleared_event:
            store.log_event(behavior.cleared_event, mode=mode_name)
        return ActionResult(True, f"Cleared: {label}")

    async def fire_alarm(mode) -> None:
        """Run a scheduled mode - an alarm's ring or a reminder's flash - and
        surface its result, then drop back to the ambient layer (IDLE)."""
        nonlocal active_mode
        play_sound(Sound.ACK)
        status.last_trigger = None
        status.last_mode = mode.name
        log.info("scheduled mode %r firing", mode.name)
        entered_at = store.log_mode_enter(mode.name)
        active_mode = mode  # so ALERT wears this mode's look, if it has one
        try:
            if isinstance(mode.behavior, ReminderBehavior):
                result = await run_reminder(mode.behavior, mode.name)
            else:
                result = await ring_alarm(mode.behavior, mode.name)
        except Exception as exc:  # a scheduled-mode bug must never kill the loop
            log.exception("scheduled mode crashed")
            result = ActionResult(False, f"internal error: {exc}")
        store.log_mode_exit(mode.name, entered_at)
        active_mode = None
        status.last_ok = result.ok
        status.last_message = result.message
        set_led(LEDState.IDLE)
        set_status("IDLE")

    async def run_stopwatch(behavior: StopwatchBehavior, mode_name: str) -> ActionResult:
        """Takeover stopwatch: start a timer, then own the button - short_press
        or double_tap marks a lap (logs `<log_as>_lap`), long_press stops and
        exits (logs the elapsed time via toggle_timer, reusing the timer_toggle
        action's elapsed formatting). A None trigger (shutdown) stops the
        running timer so it isn't left open, then exits. The caller drops the
        LED/status back to IDLE."""
        log_as = behavior.log_as
        store.toggle_timer(log_as, mode=mode_name)  # returns ("started", None)
        set_led(LEDState.TIMING)
        set_status("TIMING")
        status.last_mode = mode_name
        status.last_message = f"{log_as} timer started"
        laps = 0
        # The open timer. Every normal exit clears this *before* closing the
        # timer, so the finally only fires on an abnormal (exception) exit -
        # closing a dangling timer without double-toggling a normal stop.
        running = True
        try:
            if args.demo:
                # --demo is unattended: no press will arrive, so show it
                # briefly, stop the timer (don't leave it open), and exit.
                await asyncio.sleep(_SUCCESS_DISPLAY_S)
                running = False
                _, elapsed = store.toggle_timer(log_as, mode=mode_name)
                return ActionResult(True, f"{log_as} (demo: ran {_fmt_elapsed(elapsed or 0)})")
            # With a subdivision ladder on, the stopwatch grows a tick: the
            # light has to say what time it is, which means waking to change
            # it. Without one it still blocks indefinitely on the next press,
            # exactly as before - a stopwatch that woke twice a second to
            # repaint a colour nobody asked for would be pure radio traffic.
            ticking, tick_s = (
                ladder_paint(behavior.ladder, LEDState.TIMING)
                if behavior.ladder.enabled else (None, None)
            )
            started = asyncio.get_running_loop().time()
            while True:
                if ticking is not None:
                    ticking(asyncio.get_running_loop().time() - started)
                trigger = await _wait_for_trigger(device.events, stop, tick_s)
                if trigger is None and tick_s is not None and not stop.is_set():
                    continue  # a tick, not a press: repaint and keep waiting
                if trigger is None:  # shutting down mid-run - stop the open timer
                    running = False
                    store.toggle_timer(log_as, mode=mode_name)
                    return ActionResult(True, f"{log_as} stopped (shutdown)")
                if trigger is TriggerType.LONG_PRESS:
                    running = False
                    _, elapsed = store.toggle_timer(log_as, mode=mode_name)
                    message = f"{log_as} stopped after {_fmt_elapsed(elapsed or 0)}"
                    total = store.total_today(log_as)
                    if total > (elapsed or 0):
                        message += f" ({_fmt_elapsed(total)} today)"
                    if laps:
                        message += f", {laps} lap(s)"
                    return ActionResult(True, message)
                # short_press / double_tap -> a lap
                store.log_event(f"{log_as}_lap", mode=mode_name)
                laps += 1
                play_sound(Sound.ACK)
                status.last_message = f"Lap {laps}"
        finally:
            if running:  # an exception left the timer open - close it
                store.toggle_timer(log_as, mode=mode_name)

    async def run_counter(behavior: CounterBehavior, mode_name: str) -> ActionResult:
        """Takeover counter: count starts at 0, then own the button -
        short_press or double_tap logs `event` (so count_today / streaks just
        work) and bumps the live count, long_press exits with a session
        summary. A None trigger (shutdown) just exits. The caller drops the
        LED/status back to IDLE."""
        event = behavior.event
        count = 0
        set_led(LEDState.COUNTING)
        set_status("COUNTING")
        status.last_mode = mode_name
        status.last_message = f"{event}: {count}"
        if args.demo:
            # --demo is unattended: log one increment so the path is exercised,
            # then exit with a summary instead of hanging the smoke test.
            store.log_event(event, mode=mode_name)
            count += 1
            play_sound(Sound.ACK)
            status.last_message = f"{event}: {count}"
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"{event}: {count} this session (demo)")
        while True:
            trigger = await _wait_for_trigger(device.events, stop)
            if trigger is None:  # shutting down
                return ActionResult(True, f"{event}: {count} this session (shutdown)")
            if trigger is TriggerType.LONG_PRESS:
                return ActionResult(True, f"{event}: {count} this session")
            # short_press / double_tap -> +1
            store.log_event(event, mode=mode_name)
            count += 1
            play_sound(Sound.ACK)
            status.last_message = f"{event}: {count}"

    async def run_pomodoro(behavior: PomodoroBehavior, mode_name: str) -> ActionResult:
        """Takeover Pomodoro: alternating work and break blocks until you
        leave or the gestures say otherwise.

        Durations are measured against the event loop's monotonic clock, not
        the test clock: shifting the clock to try a time-windowed mode should
        not make a 25-minute block end instantly.

        Which gesture does what is configurable (behavior.gestures), and so is
        how transitions happen (behavior.advance) - the two things people
        disagree about most. What is *not* configurable is that a finished
        work block gets logged, so counts and streaks work on focus time the
        same way they work on everything else.
        """
        loop = asyncio.get_running_loop()
        completed = 0  # work blocks finished this session
        focused_s = 0.0
        working = True  # which half of the cycle we are in
        paused = False
        pending = False  # a block has ended and is waiting for a gesture
        remaining = behavior.work_minutes * 60
        deadline = loop.time() + remaining

        def phase_label() -> str:
            if pending:
                return "ready for the next block" if working else "ready for a break"
            return "focus" if working else "break"

        def show() -> None:
            if paused or pending:
                # A distinct "waiting on you" colour, rather than a phase
                # colour that would imply the timer is still running.
                set_led(LEDState.LISTENING)
            else:
                set_led(LEDState.WORKING if working else LEDState.RESTING)
            set_status("WORKING" if working else "RESTING")
            left = max(0.0, deadline - loop.time()) if not (paused or pending) else remaining
            status.last_message = (
                f"{mode_name}: {phase_label()}"
                + (f" - {_fmt_elapsed(left)} left" if not pending else "")
                + (f" ({completed} done)" if completed else "")
            )

        def start_phase(work: bool) -> None:
            nonlocal working, remaining, deadline, paused, pending
            working = work
            if work:
                minutes = behavior.work_minutes
            elif completed and completed % behavior.blocks_before_long_break == 0:
                minutes = behavior.long_break_minutes
            else:
                minutes = behavior.break_minutes
            remaining = minutes * 60
            deadline = loop.time() + remaining
            paused = pending = False

        def summary(suffix: str = "") -> ActionResult:
            text = f"{completed} block(s), {_fmt_elapsed(focused_s)} focused"
            return ActionResult(True, f"{mode_name}: {text}{suffix}")

        status.last_mode = mode_name
        show()

        if args.demo:
            # --demo is unattended: log one block so the path is exercised,
            # then leave rather than sitting here for 25 minutes.
            store.log_event(behavior.log_as, mode=mode_name)
            completed, focused_s = 1, behavior.work_minutes * 60
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return summary(" (demo)")

        while True:
            if paused or pending:
                timeout = None  # nothing is counting down; wait for a gesture
            else:
                timeout = max(0.05, deadline - loop.time())
            trigger = await _wait_for_trigger(device.events, stop, timeout=timeout)

            if stop.is_set():
                return summary(" (shutdown)")

            if trigger is None:
                # The block ran out.
                if working:
                    completed += 1
                    focused_s += behavior.work_minutes * 60
                    store.log_event(behavior.log_as, mode=mode_name)
                    play_sound(Sound.SUCCESS)
                else:
                    play_sound(Sound.ACK)
                next_is_work = not working
                auto = behavior.advance == "auto" or (
                    behavior.advance == "break_only" and not next_is_work
                )
                if auto:
                    start_phase(next_is_work)
                else:
                    pending, working = True, next_is_work
                    remaining = 0.0
                show()
                continue

            command = behavior.gestures.get(trigger.value)
            if command is None:
                play_sound(Sound.ERROR)  # that gesture does nothing here
                continue

            if command == "exit":
                return summary()
            if command == "toggle":
                if pending:
                    start_phase(working)  # the awaited block starts now
                elif paused:
                    deadline = loop.time() + remaining
                    paused = False
                else:
                    remaining = max(0.0, deadline - loop.time())
                    paused = True
                play_sound(Sound.ACK)
            elif command == "restart":
                completed_before = completed
                start_phase(True)
                completed = completed_before  # a restart is not a rewind
                play_sound(Sound.ACK)
            elif command == "extend":
                added = behavior.extend_minutes * 60
                if paused or pending:
                    remaining += added
                    if pending:  # extending a finished block resumes it
                        pending = False
                        paused = True
                else:
                    deadline += added
                play_sound(Sound.ACK)
            elif command == "skip":
                if working:  # skipping work does not earn a completed block
                    play_sound(Sound.ACK)
                start_phase(not working)
            show()

    async def run_metronome(behavior: MetronomeBehavior, mode_name: str) -> ActionResult:
        """Takeover metronome: short_press/double_tap mark a beat, long_press
        exits. BPM is the rolling average of the last `tap_history` intervals;
        a gap longer than `reset_gap_s` starts the average over. The LED
        pulses at the resulting tempo as an ephemeral effect, so the session
        never touches the stored palette and nothing has to be put back.

        How this goes fast. The tempo and the flash rate are different limits.
        `max_bpm` bounds the tempo and is yours to raise;
        _MIN_FLASH_PERIOD_S bounds how often the light may blink and is a
        photosensitivity floor, not a preference. Above roughly 180 BPM those
        two collide, so rather than clamp the tempo (a lie) or flash through
        the floor (a hazard), the light marks every Nth beat - the smallest N
        that keeps it inside the floor. The tempo stays honest and the LED
        stays safe.
        """
        loop = asyncio.get_running_loop()
        taps: list[float] = []  # loop.time() of recent beats, oldest first
        bpm: float | None = None
        beats = 0
        set_led(LEDState.METRONOME)
        set_status("METRONOME")
        status.last_mode = mode_name

        # A ladder here counts *beats*, not seconds - the tempo already decides
        # the timing, so what a colour adds is an accent ("every 4th beat"). It
        # also changes who drives the light: normally the device animates the
        # pulse and the host only sends a period, but a colour per beat has to
        # come from the host, so the loop grows a beat clock below.
        laddered = behavior.ladder.enabled
        shown_beat: str | None = None

        def paint_beat(beat: int) -> None:
            """Show the ladder's colour for beat number `beat`."""
            nonlocal shown_beat
            colour = ladder.color_at(behavior.ladder.rungs, beat, behavior.ladder.base)
            if colour == shown_beat:
                return
            base = base_look(LEDState.METRONOME)
            if base is None:
                return
            shown_beat = colour
            set_led(LEDState.METRONOME, replace(base, style="solid", color=colour))

        def push_tempo(tempo: float) -> int:
            """Show METRONOME beating at `tempo`. The mode's look (or the
            palette entry) supplies the colour and style; only the period is
            the session's business.

            With a ladder running, the period is *not* pushed: the beat clock
            is painting a colour per beat, and asking the device to also pulse
            underneath would be two clocks on one light. `per_flash` is still
            returned, because it is the number of beats the light may mark
            without crossing the flash floor - and the ladder obeys the same
            grouping rather than inventing a second safety rule.
            """
            base = base_look(LEDState.METRONOME)
            period, per_flash = metronome_flash(tempo, cm.config.min_flash_period_s)
            if base is not None and not laddered:
                set_led(LEDState.METRONOME, replace(base, period_s=period))
            return per_flash

        def describe(tempo: float, per_flash: int) -> str:
            grouped = f" (light marks every {per_flash} beats)" if per_flash > 1 else ""
            return f"{round(tempo)} BPM{grouped}"

        # The mode owns its starting tempo, so the light is already keeping
        # time before the first tap rather than sitting at whatever period the
        # global palette entry happens to carry.
        per_flash = push_tempo(behavior.start_bpm)
        status.last_message = f"tap to set the tempo (from {round(behavior.start_bpm)} BPM)"

        # The beat clock, which only exists when a ladder does. It runs from
        # `start_bpm` immediately, for the same reason push_tempo does: the
        # light should already be keeping time before the first tap lands.
        beat_no = 0
        beat_step = 60.0 / behavior.start_bpm * per_flash
        next_beat = loop.time() + beat_step if laddered else None
        if laddered:
            paint_beat(0)

        if args.demo:
            # --demo is unattended: no tap will ever arrive, so show it
            # briefly and exit instead of hanging the smoke test.
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, "metronome (demo: no taps)")
        while True:
            timeout = None
            if next_beat is not None:
                timeout = max(0.0, next_beat - loop.time())
            trigger = await _wait_for_trigger(device.events, stop, timeout)
            if trigger is None and next_beat is not None and not stop.is_set():
                # A beat, not a press. Advancing by `per_flash` keeps the beat
                # *number* honest at tempos where the light may only mark every
                # Nth one - the ladder is read in beats, not in flashes.
                beat_no += per_flash
                paint_beat(beat_no)
                next_beat += beat_step
                continue
            if trigger is None:  # shutting down mid-session
                return ActionResult(True, "metronome stopped (shutdown)")
            if trigger is TriggerType.LONG_PRESS:
                if bpm is None:
                    return ActionResult(True, "metronome (no tempo set)")
                # One row per session: the tempo you settled on. The
                # duration comes free from the mode_enter/mode_exit pair,
                # so "when did I practise, how long, how fast" is a query
                # rather than a guess.
                store.log_event(behavior.log_as, mode=mode_name, value=round(bpm, 1))
                _, per_flash = metronome_flash(bpm, cm.config.min_flash_period_s)
                return ActionResult(
                    True, f"{describe(bpm, per_flash)} over {beats} beats"
                )
            # any tap -> a beat
            now = loop.time()
            if taps and (now - taps[-1]) > behavior.reset_gap_s:
                taps.clear()
            taps.append(now)
            del taps[:-behavior.tap_history]
            beats += 1
            if behavior.sound_on_tap:
                play_sound(Sound.ACK)
            if len(taps) >= 2:
                intervals = [b - a for a, b in zip(taps, taps[1:])]
                bpm = min(behavior.max_bpm, 60.0 / (sum(intervals) / len(intervals)))
                per_flash = push_tempo(bpm)
                status.last_message = describe(bpm, per_flash)
                if next_beat is not None:
                    # Re-phase the beat clock onto the tap that just landed,
                    # rather than letting it keep the old tempo's grid. A
                    # metronome you retap should follow you immediately.
                    beat_step = 60.0 / bpm * per_flash
                    next_beat = now + beat_step
            else:
                status.last_message = "tap again to set the tempo"

    async def run_countdown(behavior: CountdownBehavior, mode_name: str) -> ActionResult:
        """Takeover countdown: a fixed run to zero with the LED's *colour*
        walking `behavior.ramp` as the time goes, then the alarm.

        Style and colour are driven separately, which is the whole point - the
        light flashes at a fixed period the entire time while the colour moves
        from one end of the ramp to the other, so "flash" and "fade over the
        timer" are not two settings fighting over the same light.

        Long press leaves early (a takeover mode must be escapable with a
        press); any other press acknowledges without stopping the clock, since
        the time left is already on the status line.

        **The ramp is still walked host-side, and knowingly so.** Each colour
        goes down as an *ephemeral effect* now (ROADMAP D4) rather than by
        rewriting the TIMING palette entry, so a countdown no longer edits
        state it does not own and nothing has to be put back afterwards - the
        look ends by itself at the next plain `set_led`. What it still costs is
        a radio write every few seconds and a host that is awake to send them;
        moving the ramp itself onto the device is what fixes that, and this is
        the shape it moves in.

        TIMING is still the state being shown, because a state is what the
        status line and the web UI report. Only its appearance is borrowed.
        """
        loop = asyncio.get_running_loop()
        total = behavior.minutes * 60
        deadline = loop.time() + total
        label = behavior.label or mode_name
        # Where the *shape* of the light comes from. A named look wins when the
        # mode has one - looks exist to be a mode's appearance, so having the
        # template's own fields quietly override one would make choosing a look
        # do nothing here. With no look these are the template's fields, which
        # is what a countdown has always used.
        look = look_for(cm.config, active_mode, LEDState.TIMING)
        style = look.style if look is not None else behavior.style
        # No floor applied here any more: every effect this loop pushes goes
        # through set_led, which is the one place that enforces it. Flooring
        # again would only make this the second place to keep in step.
        period = look.period_s if look is not None else behavior.period_s
        pushed: str | None = None

        # A ramp can only be seen through a style that renders `color`. A
        # rainbow is all the hues by definition and ignores it (see
        # STYLE_USES_COLOR), so walking a ramp underneath one is invisible *and*
        # costs a radio write every time it moves. Say so once and stop pushing,
        # rather than sending colour into a style that discards it.
        colour_shows = style in STYLE_USES_COLOR
        if not colour_shows:
            log.info(
                "countdown %r: a %r look ignores colour, so its ramp is not shown",
                mode_name, style,
            )

        def paint(progress: float) -> None:
            """Push the ramp's colour for `progress`, if it has visibly moved."""
            nonlocal pushed
            if not colour_shows:
                return
            colour = ramp.color_at(behavior.ramp, progress)
            if pushed is not None and not ramp.differs(
                pushed, colour, _COUNTDOWN_COLOR_STEP
            ):
                return
            base = base_look(LEDState.TIMING)
            if base is None:
                return
            pushed = colour
            set_led(
                LEDState.TIMING,
                replace(base, style=style, color=colour, period_s=period),
            )

        def left() -> float:
            return max(0.0, deadline - loop.time())

        # The ladder and the ramp both decide *which colour*, so they cannot
        # both run - and the ladder wins, because it is off by default and
        # turning it on is an explicit "make this light a clock". Driven by the
        # time *remaining*, which is what a countdown is about: the ten-second
        # colour lands on ten seconds left, not ten seconds in.
        ticking, tick_s = (
            ladder_paint(behavior.ladder, LEDState.TIMING)
            if behavior.ladder.enabled else (None, _COUNTDOWN_TICK_S)
        )

        set_led(LEDState.TIMING)
        set_status("TIMING")
        status.last_mode = mode_name

        if args.demo:
            # --demo is unattended: show the ramp's opening colour briefly
            # rather than sitting here for the whole countdown.
            paint(0.0)
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"{label} (demo: {behavior.minutes:g} min)")

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            if ticking is not None:
                ticking(remaining)
            else:
                paint(1.0 - remaining / total)
            status.last_message = f"{label} - {_fmt_elapsed(remaining)} left"
            trigger = await _wait_for_trigger(
                device.events, stop, timeout=min(remaining, tick_s)
            )
            if stop.is_set():
                return ActionResult(
                    True, f"{label} - {_fmt_elapsed(left())} left (shutdown)"
                )
            if trigger is TriggerType.LONG_PRESS:
                return ActionResult(
                    True, f"{label} - cancelled with {_fmt_elapsed(left())} left"
                )
            if trigger is not None:
                play_sound(Sound.ACK)

        # Ran out. Logged before the ring, so a countdown that is finished
        # but not yet dismissed still counts as finished.
        store.log_event(behavior.log_as, mode=mode_name, value=behavior.minutes)
        if not behavior.ring_on_finish:
            play_sound(Sound.SUCCESS)
            return ActionResult(True, f"{label} finished")
        # A finished countdown *is* an alarm going off, so it rings like
        # one rather than growing a second copy of that loop.
        return await ring_alarm(AlarmBehavior(message=f"{label} finished"), mode_name)

    async def enter_takeover(mode) -> None:
        """Enter a takeover mode (reached via a schedule fire or an enter_mode
        gesture) and surface its result, then drop back to the ambient layer
        (IDLE). Dispatches by behaviour type: alarm rings, stopwatch times,
        counter counts. Exception-guarded so a handler bug never kills the
        main loop (mirrors fire_alarm)."""
        nonlocal active_mode
        play_sound(Sound.ACK)
        status.last_trigger = None
        status.last_mode = mode.name
        log.info("entering takeover mode %r (%s)", mode.name, mode.template)
        entered_at = store.log_mode_enter(mode.name)
        # Set before dispatch so the first set_led inside the loop already
        # wears this mode's look, and cleared after so the ambient layer's
        # IDLE below is the palette's again.
        active_mode = mode
        try:
            if isinstance(mode.behavior, AlarmBehavior):
                result = await ring_alarm(mode.behavior, mode.name)
            elif isinstance(mode.behavior, StopwatchBehavior):
                result = await run_stopwatch(mode.behavior, mode.name)
            elif isinstance(mode.behavior, CounterBehavior):
                result = await run_counter(mode.behavior, mode.name)
            elif isinstance(mode.behavior, PomodoroBehavior):
                result = await run_pomodoro(mode.behavior, mode.name)
            elif isinstance(mode.behavior, MetronomeBehavior):
                result = await run_metronome(mode.behavior, mode.name)
            elif isinstance(mode.behavior, CountdownBehavior):
                result = await run_countdown(mode.behavior, mode.name)
            else:
                result = ActionResult(False, f"mode {mode.name!r} is not a takeover mode")
        except Exception as exc:  # a takeover bug must never kill the loop
            log.exception("takeover %r crashed", mode.name)
            result = ActionResult(False, f"internal error: {exc}")
        store.log_mode_exit(mode.name, entered_at)
        active_mode = None
        status.last_ok = result.ok
        status.last_message = result.message
        set_led(LEDState.IDLE)
        set_status("IDLE")

    async def handle(trigger: TriggerType) -> None:
        play_sound(Sound.ACK)
        set_led(LEDState.LISTENING)
        set_status("THINKING")
        status.last_trigger = trigger.value
        resolved = resolve(
            cm.config.modes, trigger.value, clock.now(), logged_today=store.logged_today
        )
        if resolved is None:
            status.last_mode = None
            await fail(f"no mode matches {trigger.value} right now")
        elif isinstance((action := resolved[1]), EnterModeAction):
            # A gesture starting a takeover: look the target up by name and,
            # if it is a takeover mode (alarm/stopwatch/counter), hand off to
            # enter_takeover (which owns the LED/sound/status and the IDLE drop
            # and its own BLE response). EnterModeAction is never passed to
            # execute(). A missing/non-takeover target fails clearly instead of
            # crashing - the parser deliberately does not pre-validate targets.
            mode = resolved[0]
            status.last_mode = mode.name
            target = next(
                (m for m in cm.config.modes if m.name == action.target), None
            )
            if target is not None and isinstance(
                target.behavior,
                (AlarmBehavior, StopwatchBehavior, CounterBehavior, PomodoroBehavior,
                 MetronomeBehavior, CountdownBehavior),
            ):
                await enter_takeover(target)
            else:
                await fail(f"enter_mode: no takeover mode named {action.target!r}")
            return
        else:
            mode, action = resolved
            status.last_mode = mode.name
            log.info(
                "trigger %s -> mode %r (%s)",
                trigger.value, mode.name, type(action).__name__,
            )
            set_led(LEDState.THINKING)
            try:
                result = await execute(
                    action, trigger=trigger.value, mode_name=mode.name, store=store
                )
            except Exception as exc:  # a primitive bug must never kill the loop
                log.exception("action crashed")
                result = ActionResult(False, f"internal error: {exc}")
            if result.ok:
                log.info("result (%d chars): %.120s", len(result.message), result.message)
                status.last_ok = True
                status.last_message = result.message
                set_led(LEDState.SUCCESS)
                play_sound(Sound.SUCCESS)
                set_status("SUCCESS")
                await asyncio.sleep(_SUCCESS_DISPLAY_S)
            else:
                await fail(result.message)
        set_led(LEDState.IDLE)
        set_status("IDLE")

    # Occurrence keys already rung today, so an alarm fires once per minute.
    fired: set[str] = set()
    # The palette last sent to the device. Editing colours in the web UI (or
    # a SIGHUP) replaces cm.config wholesale, so the tick below notices and
    # re-sends - which is why a colour picker updates the real LED live.
    pushed_palette = cm.config.led_palette
    # Nothing inside one iteration is allowed to end the service. handle() and
    # the takeover loops already guard their own bodies; this is the backstop
    # for the rest of an iteration - the store, the scheduler scan, the
    # palette push - because a button that dies on a locked database is worse
    # than one that misses a press.
    faults = FaultTracker()

    try:
        if args.demo:
            for trigger in TriggerType:
                log.info("--- demo: %s ---", trigger.value)
                await handle(trigger)
            return

        log.info(
            "AI Button ready (config: %s, %d mode(s))", cm.path, len(cm.config.modes)
        )
        while not stop.is_set():
            try:
                trigger = await _wait_for_trigger(
                    device.events, stop, timeout=_SCHEDULER_TICK_S
                )
                if stop.is_set():
                    break
                if trigger is not None:
                    await handle(trigger)
                    # Single in-flight action: drop presses made while busy.
                    discarded = 0
                    while not device.events.empty():
                        device.events.get_nowait()
                        discarded += 1
                    if discarded:
                        log.info("discarded %d press(es) made while busy", discarded)
                if cm.config.led_palette != pushed_palette:
                    pushed_palette = cm.config.led_palette
                    push_palette(pushed_palette)
                    log.info("LED palette changed - pushed to the device")
                # Binding (or unbinding) a long tap changes how far the device
                # counts, so this rides the same hot-reload path the palette
                # does rather than waiting for a restart.
                if (max_taps := wanted_max_taps()) != device.max_taps:
                    device.set_gesture_config(max_taps)
                    log.info("gestures changed - device now counts %d taps", max_taps)
                # After every wait (press or tick), check whether a scheduled
                # alarm is due now and ring it; an alarm preempts the ambient
                # layer. Prune `fired` to today's keys so it never grows without
                # bound across days.
                now = clock.now()
                today_prefix = now.date().isoformat()
                # Match the trailing "@<date>T<HH:MM>" structurally so a mode
                # name that happens to embed a date can't keep a stale key
                # alive.
                fired = {
                    k for k in fired
                    if k.rsplit("@", 1)[-1].startswith(f"{today_prefix}T")
                }
                due = due_alarm(cm.config.modes, now, fired)
                if due is not None:
                    mode, key = due
                    fired.add(key)
                    await fire_alarm(mode)
            except asyncio.CancelledError:
                raise  # shutdown, not a fault
            except Exception as exc:
                if faults.record(loop.time()):
                    log.exception("main loop fault #%d - continuing", faults.count)
                status.last_ok = False
                status.last_message = f"internal error: {exc}"
                # A fault part-way through handle() leaves the LED on
                # LISTENING or THINKING forever; drop back to IDLE so the
                # button looks alive again rather than hung.
                with contextlib.suppress(Exception):
                    set_led(LEDState.IDLE)
                set_status("IDLE")
                # A fault that recurs every tick would otherwise spin as fast
                # as it can raise; hold at tick rate, and stay interruptible.
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=_SCHEDULER_TICK_S)
        log.info("shutting down")
    finally:
        if web_server is not None:
            web_server.should_exit = True
            # uvicorn raises SystemExit (a BaseException) if it never bound its
            # port; suppress it here too so a failed *optional* web UI can't
            # turn shutdown into a process crash.
            with contextlib.suppress(Exception, SystemExit):
                await asyncio.wait_for(web_task, timeout=5)
        with contextlib.suppress(Exception):
            await device.close()
        tones.close()
        store.close()
        if guard is not None:
            guard.release()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,  # journald captures stdout
    )
    try:
        asyncio.run(run(args))
    except AlreadyRunning as exc:
        # Expected operator error, not a bug: say what to do, without a
        # traceback that makes it look like a crash.
        log.error("%s", exc)
        raise SystemExit(1)
    except KeyboardInterrupt:
        pass  # Windows fallback where SIGINT handlers aren't wired


if __name__ == "__main__":
    main()
