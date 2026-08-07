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
import signal
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from .device import ButtonDevice, LEDState, MockDevice, Sound, TriggerType

log = logging.getLogger("aibutton")

# How long the ERROR flashes get to play before returning to IDLE.
_ERROR_DISPLAY_S = 1.5
# SUCCESS hold time; the device's green window matches it.
_SUCCESS_DISPLAY_S = 2.0

# Metronome: how many recent taps the rolling BPM average is computed over.
_METRONOME_TAP_HISTORY = 8
# A gap this long (seconds) between taps starts the average over, so picking
# the button back up after a pause does not average in the silence.
_METRONOME_RESET_GAP_S = 2.0
# The LED's period is floored here regardless of tapped tempo - a WCAG-style
# flash-rate safety cap (item 4 in TODO.md will formalize the exact number
# for the palette editor generally; this is a conservative stand-in so a fast
# tap tempo can't strobe the LED faster than roughly 3 times a second).
_METRONOME_MIN_PERIOD_S = 1 / 3


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
    last_sound: str | None = None
    sound_seq: int = 0  # bumped per sound so the browser knows when to replay


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
        CounterBehavior,
        EnterModeAction,
        MetronomeBehavior,
        PomodoroBehavior,
        StopwatchBehavior,
    )
    from .rules import resolve
    from .scheduler import due_alarm
    from .store import EventStore

    cm = ConfigManager(args.config)
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
    device.set_palette(cm.config.led_palette)
    tones = ToneLibrary()
    store = EventStore(cm.config.database_path)

    def set_led(state: LEDState) -> None:
        device.set_led(state)
        status.led_state = state.value

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
    stop = asyncio.Event()
    if hasattr(signal, "SIGHUP"):  # POSIX only
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signal.SIGHUP, cm.reload)
            loop.add_signal_handler(signal.SIGTERM, stop.set)
            loop.add_signal_handler(signal.SIGINT, stop.set)

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

    async def fire_alarm(mode_name: str, behavior: AlarmBehavior) -> None:
        """Run a scheduled alarm's ring loop and surface its result, then
        drop back to the ambient layer (IDLE)."""
        play_sound(Sound.ACK)
        status.last_trigger = None
        status.last_mode = mode_name
        log.info("scheduled alarm %r firing", mode_name)
        entered_at = store.log_mode_enter(mode_name)
        try:
            result = await ring_alarm(behavior, mode_name)
        except Exception as exc:  # an alarm bug must never kill the loop
            log.exception("alarm crashed")
            result = ActionResult(False, f"internal error: {exc}")
        store.log_mode_exit(mode_name, entered_at)
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
            while True:
                trigger = await _wait_for_trigger(device.events, stop)
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

    async def run_metronome(mode_name: str) -> ActionResult:
        """Takeover metronome: short_press/double_tap mark a beat, long_press
        exits. BPM is the rolling average of the last _METRONOME_TAP_HISTORY
        tap intervals; a gap longer than _METRONOME_RESET_GAP_S starts the
        average over. The LED pulses at the resulting tempo via a live
        palette override (its period floored for flash safety); the finally
        block restores the configured palette so the override never outlives
        the session."""
        loop = asyncio.get_running_loop()
        taps: list[float] = []  # loop.time() of recent beats, oldest first
        bpm: float | None = None
        set_led(LEDState.METRONOME)
        set_status("METRONOME")
        status.last_mode = mode_name
        status.last_message = "tap to set the tempo"

        def push_tempo() -> None:
            base = cm.config.led_palette.get(LEDState.METRONOME.value)
            if base is None or bpm is None:
                return
            period = max(_METRONOME_MIN_PERIOD_S, 60.0 / bpm)
            device.set_palette({
                **cm.config.led_palette,
                LEDState.METRONOME.value: replace(base, period_s=period),
            })

        try:
            if args.demo:
                # --demo is unattended: no tap will ever arrive, so show it
                # briefly and exit instead of hanging the smoke test.
                await asyncio.sleep(_SUCCESS_DISPLAY_S)
                return ActionResult(True, "metronome (demo: no taps)")
            while True:
                trigger = await _wait_for_trigger(device.events, stop)
                if trigger is None:  # shutting down mid-session
                    return ActionResult(True, "metronome stopped (shutdown)")
                if trigger is TriggerType.LONG_PRESS:
                    message = f"{round(bpm)} BPM" if bpm else "metronome (no tempo set)"
                    return ActionResult(True, message)
                # short_press / double_tap -> a beat
                now = loop.time()
                if taps and (now - taps[-1]) > _METRONOME_RESET_GAP_S:
                    taps.clear()
                taps.append(now)
                del taps[:-_METRONOME_TAP_HISTORY]
                play_sound(Sound.ACK)
                if len(taps) >= 2:
                    intervals = [b - a for a, b in zip(taps, taps[1:])]
                    bpm = 60.0 / (sum(intervals) / len(intervals))
                    status.last_message = f"{round(bpm)} BPM"
                    push_tempo()
                else:
                    status.last_message = "tap again to set the tempo"
        finally:
            device.set_palette(cm.config.led_palette)  # drop the live tempo override

    async def enter_takeover(mode) -> None:
        """Enter a takeover mode (reached via a schedule fire or an enter_mode
        gesture) and surface its result, then drop back to the ambient layer
        (IDLE). Dispatches by behaviour type: alarm rings, stopwatch times,
        counter counts. Exception-guarded so a handler bug never kills the
        main loop (mirrors fire_alarm)."""
        play_sound(Sound.ACK)
        status.last_trigger = None
        status.last_mode = mode.name
        log.info("entering takeover mode %r (%s)", mode.name, mode.template)
        entered_at = store.log_mode_enter(mode.name)
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
                result = await run_metronome(mode.name)
            else:
                result = ActionResult(False, f"mode {mode.name!r} is not a takeover mode")
        except Exception as exc:  # a takeover bug must never kill the loop
            log.exception("takeover %r crashed", mode.name)
            result = ActionResult(False, f"internal error: {exc}")
        store.log_mode_exit(mode.name, entered_at)
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
                 MetronomeBehavior),
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

    # The press wait wakes at least this often so a scheduled alarm is noticed
    # within a second of its minute - crucial for the test clock (set 06:59 ->
    # a 07:00 alarm rings ~1s later) and so an alarm added live via the web UI
    # or SIGHUP starts firing without waiting for an unrelated press. Polling
    # unconditionally (not only when an alarm exists *now*) is what lets a
    # newly configured alarm engage immediately after a hot reload; the idle
    # cost is one cheap scheduler scan per second.
    _SCHEDULER_TICK_S = 1.0
    # Occurrence keys already rung today, so an alarm fires once per minute.
    fired: set[str] = set()
    # The palette last sent to the device. Editing colours in the web UI (or
    # a SIGHUP) replaces cm.config wholesale, so the tick below notices and
    # re-sends - which is why a colour picker updates the real LED live.
    pushed_palette = cm.config.led_palette

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
                device.set_palette(pushed_palette)
                log.info("LED palette changed - pushed to the device")
            # After every wait (press or tick), check whether a scheduled
            # alarm is due now and ring it; an alarm preempts the ambient
            # layer. Prune `fired` to today's keys so it never grows without
            # bound across days.
            now = clock.now()
            today_prefix = now.date().isoformat()
            # Match the trailing "@<date>T<HH:MM>" structurally so a mode name
            # that happens to embed a date can't keep a stale key alive.
            fired = {
                k for k in fired
                if k.rsplit("@", 1)[-1].startswith(f"{today_prefix}T")
            }
            due = due_alarm(cm.config.modes, now, fired)
            if due is not None:
                mode, key = due
                fired.add(key)
                await fire_alarm(mode.name, mode.behavior)
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


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,  # journald captures stdout
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass  # Windows fallback where SIGINT handlers aren't wired


if __name__ == "__main__":
    main()
