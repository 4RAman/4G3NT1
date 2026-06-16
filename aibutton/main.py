"""AI Button orchestrator.

On the Pi (normally via systemd):
    .venv/bin/python -m aibutton.main

Dev on any machine - mock GPIO pins + canned AI, web UI live at
http://localhost:8080 with simulated press buttons:
    python -m aibutton.main --mock --no-ble

One-shot smoke test (each trigger once, then exit):
    python -m aibutton.main --mock --demo --no-ble

The button is always in some mode. Per gesture: resolve the (trigger,
time-of-day) against the *ambient* modes (the actions-template ones,
first match wins), execute the matched action primitive (prompt / log /
timer_toggle / webhook), and surface the result on LED, sound, BLE, and
the web UI.

Alarms are *takeover* modes, not gesture-resolved: each loop iteration
asks scheduler.due_alarm() whether a scheduled alarm mode's occurrence
has arrived, and if so ring_alarm() owns the device (ALERT LED + looping
tone) until a press dismisses or snoozes it. The press-wait polls on a
<=1s timeout so the test clock stays responsive and an alarm added live
(web UI or SIGHUP) starts firing within a second.

Signals: SIGHUP reloads the config, SIGTERM/SIGINT shut down cleanly.
Heavy imports happen inside run() so startup stays lean on 1 GB RAM.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

log = logging.getLogger("aibutton")

# How long the ERROR flashes get to play before returning to IDLE.
_ERROR_DISPLAY_S = 1.5
# SUCCESS hold time, matching led.py's 2 s green window.
_SUCCESS_DISPLAY_S = 2.0
# Pomodoro countdown refresh: wake at least this often so the remaining time
# display and the work<->break transition stay within a second of accurate.
_POMODORO_TICK_S = 1.0


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
    """Live device state shared with the BLE STATUS_CHAR and the web UI."""

    state: str = "IDLE"
    last_trigger: str | None = None
    last_mode: str | None = None
    last_ok: bool | None = None
    last_message: str = ""
    asleep: bool = False  # device toggled off via 5-tap (ignores gestures)
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
        help="config path (default: $AIBUTTON_CONFIG or /etc/aibutton/config.json)",
    )
    p.add_argument("--no-ble", action="store_true", help="run without the BLE peripheral")
    p.add_argument("--no-web", action="store_true", help="run without the web UI")
    p.add_argument("--mock", action="store_true", help="mock GPIO pins and the AI client")
    p.add_argument(
        "--real-ai",
        action="store_true",
        help="with --mock: use the real Ollama backends instead of the canned AI",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="run one pass of every trigger, then exit (combine with --mock)",
    )
    return p.parse_args(argv)


class _MockAIClient:
    async def query(self, prompt: str) -> str:
        await asyncio.sleep(1.5)  # simulate inference latency
        return f"[mock] Answering {prompt!r}: all systems nominal."


async def run(args: argparse.Namespace) -> None:
    if args.mock:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin

        Device.pin_factory = MockFactory(pin_class=MockPWMPin)

    from .actions import ActionResult, _fmt_elapsed, execute
    from .ai_client import AIClient
    from .audio import Sound, SoundPlayer
    from .button import ButtonListener, TriggerType
    from .config import (
        AlarmBehavior,
        ConfigManager,
        CounterBehavior,
        EnterModeAction,
        PomodoroBehavior,
        StopwatchBehavior,
    )
    from .led import LEDController, LEDState
    from .rules import resolve
    from .scheduler import due_alarm
    from .store import EventStore

    cm = ConfigManager(args.config)
    status = DeviceStatus()
    clock = Clock()
    led = LEDController()
    sounds = SoundPlayer(enabled=cm.config.sounds_enabled)
    store = EventStore(cm.config.database_path)

    def set_led(state: LEDState) -> None:
        led.set_state(state)
        status.led_state = state.value

    def play_sound(sound: Sound) -> None:
        sounds.play(sound)
        status.last_sound = sound.value
        status.sound_seq += 1

    set_led(LEDState.IDLE)

    ble = None
    if not args.no_ble:
        try:
            from .ble_peripheral import BLEPeripheral

            ble = BLEPeripheral(cm.config.ble_device_name)
            await ble.start()
        except Exception as exc:
            log.error("BLE unavailable (%s) - continuing without it", exc)
            ble = None

    def set_status(state: str) -> None:
        status.state = state
        if ble is None:
            return
        try:
            ble.set_status(state)
        except Exception as exc:
            log.warning("BLE status notify failed: %s", exc)

    listener = ButtonListener()
    ai = _MockAIClient() if args.mock and not args.real_ai else AIClient(cm)

    web_server = None
    web_task = None
    if not args.no_web and cm.config.web_enabled:
        try:
            from .webui import WebContext, create_app, make_server

            ctx = WebContext(
                cm=cm,
                store=store,
                status=status,
                trigger_queue=listener.events,
                clock=clock,
                sounds=sounds,
                mock=args.mock,
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

    def settle() -> None:
        """Return the LED/status to the resting layer after an action: the
        dark OFF state when the device is asleep, otherwise IDLE."""
        if status.asleep:
            set_led(LEDState.OFF)
            set_status("OFF")
        else:
            set_led(LEDState.IDLE)
            set_status("IDLE")

    def go_to_sleep() -> None:
        """5-tap from the ambient layer: turn the device off. Gestures are
        ignored until a 5-tap wakes it; scheduled alarms still fire."""
        status.asleep = True
        log.info("device off (5-tap)")
        play_sound(Sound.SLEEP)
        status.last_message = "Off - 5-tap to wake"
        set_led(LEDState.OFF)
        set_status("OFF")

    def wake_up() -> None:
        """5-tap while off: turn the device back on, dropping to the ambient
        layer (Default)."""
        status.asleep = False
        log.info("device on (5-tap)")
        play_sound(Sound.WAKE)
        status.last_message = "On"
        set_led(LEDState.IDLE)
        set_status("IDLE")

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
            sounds.start_loop(Sound.ALARM)
            status.last_message = label
            set_status("ALARMING")
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            sounds.stop_loop()
            return ActionResult(True, f"{label} (demo: rings until dismissed)")
        while True:
            set_led(LEDState.ALERT)
            sounds.start_loop(Sound.ALARM)
            status.last_message = label
            set_status("ALARMING")
            trigger = await _wait_for_trigger(listener.events, stop)
            sounds.stop_loop()
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
                store.log_event(behavior.dismiss_event)
            return ActionResult(True, f"Dismissed: {label}")

    async def fire_alarm(mode_name: str, behavior: AlarmBehavior) -> None:
        """Run a scheduled alarm's ring loop and surface its result, then
        drop back to the ambient layer (IDLE)."""
        play_sound(Sound.ACK)
        status.last_trigger = None
        status.last_mode = mode_name
        log.info("scheduled alarm %r firing", mode_name)
        try:
            result = await ring_alarm(behavior, mode_name)
        except Exception as exc:  # an alarm bug must never kill the loop
            log.exception("alarm crashed")
            result = ActionResult(False, f"internal error: {exc}")
        status.last_ok = result.ok
        status.last_message = result.message
        if result.ok and ble is not None:
            try:
                await ble.send_response(result.message)
            except Exception as exc:
                log.warning("BLE response notify failed: %s", exc)
        settle()

    async def run_stopwatch(behavior: StopwatchBehavior, mode_name: str) -> ActionResult:
        """Takeover stopwatch: start a timer, then own the button - short_press
        or double_tap marks a lap (logs `<log_as>_lap`), long_press stops and
        exits (logs the elapsed time via toggle_timer, reusing the timer_toggle
        action's elapsed formatting). A None trigger (shutdown) stops the
        running timer so it isn't left open, then exits. The caller drops the
        LED/status back to IDLE."""
        log_as = behavior.log_as
        store.toggle_timer(log_as)  # returns ("started", None)
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
                _, elapsed = store.toggle_timer(log_as)
                return ActionResult(True, f"{log_as} (demo: ran {_fmt_elapsed(elapsed or 0)})")
            while True:
                trigger = await _wait_for_trigger(listener.events, stop)
                if trigger is None:  # shutting down mid-run - stop the open timer
                    running = False
                    store.toggle_timer(log_as)
                    return ActionResult(True, f"{log_as} stopped (shutdown)")
                # long_press stops & exits; the 5-tap escape does too.
                if trigger in (TriggerType.LONG_PRESS, TriggerType.QUINTUPLE_TAP):
                    running = False
                    _, elapsed = store.toggle_timer(log_as)
                    message = f"{log_as} stopped after {_fmt_elapsed(elapsed or 0)}"
                    total = store.total_today(log_as)
                    if total > (elapsed or 0):
                        message += f" ({_fmt_elapsed(total)} today)"
                    if laps:
                        message += f", {laps} lap(s)"
                    return ActionResult(True, message)
                # short_press / double_tap -> a lap
                store.log_event(f"{log_as}_lap")
                laps += 1
                play_sound(Sound.ACK)
                status.last_message = f"Lap {laps}"
        finally:
            if running:  # an exception left the timer open - close it
                store.toggle_timer(log_as)

    async def run_counter(behavior: CounterBehavior, mode_name: str) -> ActionResult:
        """Takeover counter: count starts at 0, then own the button - each
        gesture adds its configured increment (defaults short +1, long +10,
        double +20) and logs `event` by that amount (so count_today / streaks
        just work), while the 5-tap escape exits with a session summary. A None
        trigger (shutdown) just exits. The caller drops the LED/status back to
        the resting layer."""
        event = behavior.event
        increments = {
            TriggerType.SHORT_PRESS: behavior.tap_increment,
            TriggerType.LONG_PRESS: behavior.long_increment,
            TriggerType.DOUBLE_TAP: behavior.double_increment,
        }
        count = 0
        set_led(LEDState.COUNTING)
        set_status("COUNTING")
        status.last_mode = mode_name
        status.last_message = f"{event}: {count}"
        if args.demo:
            # --demo is unattended: apply one tap increment so the path is
            # exercised, then exit with a summary instead of hanging.
            if behavior.tap_increment:
                store.log_event(event, behavior.tap_increment)
            count += behavior.tap_increment
            play_sound(Sound.ACK)
            status.last_message = f"{event}: {count}"
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"{event}: {count} this session (demo)")
        while True:
            trigger = await _wait_for_trigger(listener.events, stop)
            if trigger is None:  # shutting down
                return ActionResult(True, f"{event}: {count} this session (shutdown)")
            if trigger is TriggerType.QUINTUPLE_TAP:  # the universal escape
                return ActionResult(True, f"{event}: {count} this session")
            inc = increments.get(trigger, 0)
            if inc:
                store.log_event(event, inc)
            count += inc
            play_sound(Sound.ACK)
            status.last_message = f"{event}: {count}"

    async def run_pomodoro(behavior: PomodoroBehavior, mode_name: str) -> ActionResult:
        """Takeover Pomodoro: a work/break countdown that auto-repeats until the
        5-tap escape exits. Each gesture runs its assigned command (start_pause /
        restart / extend; defaults short=start_pause, long=restart,
        double=extend). Each completed work block is logged as a `log_as` timer
        so total_today accumulates focus time. The caller drops the LED/status
        back to the resting layer."""
        loop = asyncio.get_running_loop()
        work_s = behavior.work_minutes * 60
        break_s = behavior.break_minutes * 60
        extend_s = behavior.extend_minutes * 60
        log_as = behavior.log_as
        phase = "work"  # "work" | "break"
        remaining = work_s
        running = True
        blocks = 0  # completed work blocks this session
        status.last_mode = mode_name

        def show() -> None:
            tag = "Work" if phase == "work" else "Break"
            paused = "" if running else " (paused)"
            status.last_message = f"{tag} {_fmt_elapsed(max(0, remaining))}{paused}"

        def enter_phase(new_phase: str) -> None:
            nonlocal phase, remaining
            phase = new_phase
            remaining = work_s if new_phase == "work" else break_s
            set_led(LEDState.POMODORO_WORK if new_phase == "work" else LEDState.POMODORO_BREAK)
            set_status("POMODORO_WORK" if new_phase == "work" else "POMODORO_BREAK")
            show()

        set_led(LEDState.POMODORO_WORK)
        set_status("POMODORO_WORK")
        show()
        if args.demo:
            # --demo is unattended: show the work phase briefly, then exit.
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(
                True,
                f"Pomodoro (demo: {behavior.work_minutes:g}/{behavior.break_minutes:g} min)",
            )

        def summary() -> ActionResult:
            message = f"Pomodoro ended: {blocks} work block(s)"
            total = store.total_today(log_as)
            if total:
                message += f", {_fmt_elapsed(total)} today"
            return ActionResult(True, message)

        while True:
            timeout = min(remaining, _POMODORO_TICK_S) if running else None
            start_t = loop.time()
            trigger = await _wait_for_trigger(listener.events, stop, timeout=timeout)
            if stop.is_set():  # shutting down
                return summary()
            if running:
                remaining = max(0.0, remaining - (loop.time() - start_t))

            if trigger is None:  # countdown tick
                if running and remaining <= 0:
                    if phase == "work":
                        store.log_duration(log_as, work_s)
                        blocks += 1
                        play_sound(Sound.SUCCESS)
                        enter_phase("break")
                    else:
                        play_sound(Sound.PHASE)
                        enter_phase("work")
                else:
                    show()
                continue

            if trigger is TriggerType.QUINTUPLE_TAP:  # the universal escape
                return summary()

            command = behavior.gestures.get(trigger.value)
            if command == "start_pause":
                running = not running
            elif command == "restart":
                remaining = work_s if phase == "work" else break_s
                running = True
            elif command == "extend":
                remaining += extend_s
            play_sound(Sound.ACK)
            show()

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
        try:
            if isinstance(mode.behavior, AlarmBehavior):
                result = await ring_alarm(mode.behavior, mode.name)
            elif isinstance(mode.behavior, StopwatchBehavior):
                result = await run_stopwatch(mode.behavior, mode.name)
            elif isinstance(mode.behavior, CounterBehavior):
                result = await run_counter(mode.behavior, mode.name)
            elif isinstance(mode.behavior, PomodoroBehavior):
                result = await run_pomodoro(mode.behavior, mode.name)
            else:
                result = ActionResult(False, f"mode {mode.name!r} is not a takeover mode")
        except Exception as exc:  # a takeover bug must never kill the loop
            log.exception("takeover %r crashed", mode.name)
            result = ActionResult(False, f"internal error: {exc}")
        status.last_ok = result.ok
        status.last_message = result.message
        if result.ok and ble is not None:
            try:
                await ble.send_response(result.message)
            except Exception as exc:
                log.warning("BLE response notify failed: %s", exc)
        settle()

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
                (AlarmBehavior, StopwatchBehavior, CounterBehavior, PomodoroBehavior),
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
                    action, trigger=trigger.value, mode_name=mode.name, ai=ai, store=store
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
                if ble is not None:
                    try:
                        await ble.send_response(result.message)
                    except Exception as exc:
                        log.warning("BLE response notify failed: %s", exc)
                await asyncio.sleep(_SUCCESS_DISPLAY_S)
            else:
                await fail(result.message)
        settle()

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

    try:
        if args.demo:
            # The 5-tap toggle is a global escape, not a mode gesture, so drive
            # the three mappable gestures through handle(), then exercise the
            # off/on toggle once.
            for trigger in (
                TriggerType.SHORT_PRESS, TriggerType.LONG_PRESS, TriggerType.DOUBLE_TAP
            ):
                log.info("--- demo: %s ---", trigger.value)
                await handle(trigger)
            log.info("--- demo: quintuple_tap (off / on) ---")
            go_to_sleep()
            await asyncio.sleep(_ERROR_DISPLAY_S)
            wake_up()
            return

        log.info(
            "AI Button ready (config: %s, %d mode(s))", cm.path, len(cm.config.modes)
        )
        while not stop.is_set():
            trigger = await _wait_for_trigger(
                listener.events, stop, timeout=_SCHEDULER_TICK_S
            )
            if stop.is_set():
                break
            if trigger is TriggerType.QUINTUPLE_TAP:
                # Contextual escape from the ambient layer: a 5-tap toggles the
                # device off/on. (A 5-tap during a takeover is consumed by that
                # takeover's handler as its exit, so it never reaches here.)
                wake_up() if status.asleep else go_to_sleep()
            elif trigger is not None and status.asleep:
                # Off: ignore every gesture but the 5-tap wake above.
                log.info("ignored %s - device is off", trigger.value)
            elif trigger is not None:
                await handle(trigger)
                # Single in-flight action: drop presses made while busy.
                discarded = 0
                while not listener.events.empty():
                    listener.events.get_nowait()
                    discarded += 1
                if discarded:
                    log.info("discarded %d press(es) made while busy", discarded)
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
        listener.close()
        led.close()
        sounds.close()
        store.close()
        if ble is not None:
            with contextlib.suppress(Exception):
                await ble.stop()


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
