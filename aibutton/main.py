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

Takeover modes own the button instead of resolving per gesture, and are
reached two ways. A *clock* starts the scheduled ones (scheduler.due_alarm(),
asked once per tick); a *gesture* starts the rest via an enter_mode action -
including the launcher, which then hands over to the app you pick.
enter_takeover runs them in sequence rather than nesting them; see its
docstring for why. Long press means "up one level" in every one of them
(CLAUDE.md's invariants).

`--demo` runs unattended, so no press will ever arrive: every takeover below
shows itself for _SUCCESS_DISPLAY_S and returns rather than hanging the smoke
test, logging one row first where that is the path worth exercising.

Signals: SIGHUP reloads the config, SIGTERM/SIGINT shut down cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import math
import random
import signal
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from . import hotcold, ladder, ramp, reaction, sequencer
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

# What IDLE looks like while the ambient layer is asleep (config.StandbyAction).
# Dim rather than off, and solid rather than animated: "asleep" and "unplugged"
# have to be different things to look at, and a light that is not moving is the
# least attention this build can ask for while still answering the only
# question standby raises - is it still on?
_STANDBY_COLOR = "#101010"

# How long a control surface holds its per-command confirmation. Much shorter
# than _SUCCESS_DISPLAY_S on purpose: that one ends with a drop back to IDLE,
# while a control surface stays open and is meant to be played - two seconds of
# "yes, that went" between Play and Record would make the app feel broken.
# Presses during it are queued rather than lost, so this is a latency choice
# and not a dropped-input one.
_CONTROL_CONFIRM_S = 0.3

# How often a clocked metronome re-reads the DAW's tempo. The pulses are being
# timestamped continuously on a driver thread whatever this is set to; this
# only decides how often the loop *asks*. Five times a second is well inside
# what anyone notices in a tempo change and costs nothing.
_CLOCK_POLL_S = 0.2

# How far the clock's estimate must move before the light is re-pushed. The
# estimate wanders by a fraction of a BPM even on a rock-steady project, and
# without a threshold that would be a radio write several times a second for a
# change nobody can see.
_CLOCK_BPM_EPSILON = 0.5
# The press wait wakes at least this often so a scheduled alarm is noticed
# within a second of its minute - crucial for the test clock (set 06:59 -> a
# 07:00 alarm rings ~1s later) and so an alarm added live via the web UI or
# SIGHUP starts firing without waiting for an unrelated press. Polling
# unconditionally (not only when an alarm exists *now*) is what lets a newly
# configured alarm engage immediately after a hot reload; the idle cost is one
# cheap scheduler scan per second. It also paces the loop's fault backoff.
_SCHEDULER_TICK_S = 1.0

# The flash floor (device.SAFE_MIN_PERIOD_S, ~3 Hz per WCAG 2.3.1) is the
# *default* for config.min_flash_period_s rather than a law - one button on one
# desk, and its owner may decide it can go faster. Everything here reads the
# config's effective value; the imported constant is only the fallback for a
# pure function nobody handed one to. `set_led` is the single gate that
# enforces it (CLAUDE.md).

# How often a stop-list fade is re-sampled while it plays - the floor on how
# "smooth" a host-driven fade may claim to be. Small enough to look like
# motion, large enough that it stays honest about being pushed over a radio
# whose contract is fire-and-forget (ble_device.py) rather than promising the
# device's own smooth styles (breathe, fade) can't.
_SEQUENCE_MIN_STEP_S = 0.05

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

# The reaction timer's two non-ramp colours. Dark is deliberately not *off*: a
# black button is indistinguishable from a crashed one, and the whole game is
# spent staring at it. The false-start red is bright enough to read as a
# verdict rather than as the go signal arriving.
_REACTION_DARK = "#050515"
_REACTION_FALSE_START = "#ff0033"


def metronome_flash(
    bpm: float, min_period_s: float = SAFE_MIN_PERIOD_S
) -> tuple[float, int]:
    """(LED period, how many beats each flash stands for) for a tempo of `bpm`.

    Tempo and flash rate are separate limits. Past roughly 180 BPM a beat is
    shorter than the light may legally blink, so instead of clamping the tempo
    (which would lie about it) or blinking through the floor (which would be a
    hazard), each flash marks the smallest whole number of beats that lands
    back inside the floor. Pure and module-level so that safety property can be
    checked as a table rather than against a real clock's jitter.
    """
    beat_s = 60.0 / bpm
    per_flash = max(1, math.ceil(min_period_s / beat_s))
    return beat_s * per_flash, per_flash


async def _wait_for_trigger(
    queue: asyncio.Queue, stop: asyncio.Event, timeout: float | None = None
):
    """Wait for the next button press, or None once `stop` fires (or the
    optional `timeout` elapses).

    Waiting on `stop` too is what keeps a ringing or snoozing alarm from
    blocking graceful shutdown - without it, SIGTERM during a 9-minute snooze
    would hang for up to 9 minutes.

    With a `timeout`, a None return means "tick, nothing pressed" rather than
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
    """Counts main-loop faults and decides which ones get logged: the first
    always, then one per `interval_s`.

    A fault that recurs every tick would otherwise write a traceback a second,
    which over ROADMAP.md's 24-hour soak is both a full disk and a log nobody
    can read. Pure - it never logs, only answers "worth a traceback?" - so the
    throttle is testable without a clock or a logger.
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

    Ambient mode resolution and the alarm scheduler read time through this, so
    time-windowed modes and scheduled alarms can be tried without waiting for
    the right hour. The offset keeps ticking, never persists across restarts,
    and does not affect event-log timestamps, which stay real UTC.
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
    from . import midi_io
    from .actions import ActionResult, _fmt_elapsed, execute
    from .audio import ToneLibrary
    from .config import (
        MODE_LED_STATES,
        AlarmBehavior,
        ConfigManager,
        ControlBehavior,
        CountdownBehavior,
        CounterBehavior,
        EnterModeAction,
        HotColdBehavior,
        LauncherBehavior,
        LedEffect,
        MetronomeBehavior,
        PomodoroBehavior,
        ReactionBehavior,
        ReadoutAction,
        ReminderBehavior,
        SignalBehavior,
        StandbyAction,
        StopwatchBehavior,
        bound_triggers,
        flash_safe,
        look_for,
        resolve_action,
        sequence_safe,
    )
    from .rules import resolve
    from .scheduler import due_alarm
    from .store import EventStore
    from .summary import clean as clean_summary

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

    # Whether the ambient layer is asleep (config.StandbyAction). Session
    # state on purpose and therefore a local: an "off" that outlived a restart
    # would be a button that comes back dead with nothing on it to say why.
    standby = False

    # The task walking a Sequence look's planner, if one is running - see
    # `_drive_sequence`. Cancelled by `set_led` before it does anything else,
    # which is what makes a sequence last "until the next state change" exactly
    # like an ephemeral effect: nothing downstream has to know one was involved.
    sequence_task: asyncio.Task | None = None

    async def _drive_sequence(state: LEDState, seq: sequencer.Sequence) -> None:
        """Walk `seq`'s planner, pushing each frame as a plain solid
        `LedEffect` - never a Sequence itself, since `device.set_led`
        duck-types its `effect` on `.style`/`.color`/`.color2`/`.period_s`
        (device.py). Solid is the only thing a frame can be: a stop is a flat
        colour, and the movement is the walk between them.

        Pushes go straight through `device.set_led`, *not* through the
        `set_led` closure above: that closure cancels this very task on every
        call, so calling it from inside its own task would cancel itself one
        step in. `flash_safe` is skipped for the same reason a second clamp is
        always wrong (CLAUDE.md): `sequence_safe` already floored both of this
        sequence's axes before the task started.

        **Assumes the host is awake and connected**, like every run_* loop in
        this file (CLAUDE.md) - the sleeps are wall-clock, so a host that is
        asleep stops advancing the sequence rather than catching up.
        """
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            frame, wait = sequencer.plan_at(seq, loop.time() - start, _SEQUENCE_MIN_STEP_S)
            if frame is None:
                # A one-shot finished. `None` is what `set_led` (and the
                # device) already mean by "no override" - falling back to the
                # palette entry, not to whatever `active_mode` still names for
                # this state, which would just restart the same sequence.
                device.set_led(state, None)
                status.led_state = state.value
                status.led_effect = None
                return
            effect = LedEffect(style="solid", color=frame.color)
            device.set_led(state, effect)
            status.led_state = state.value
            status.led_effect = effect
            await asyncio.sleep(wait if wait and wait > 0 else _SEQUENCE_MIN_STEP_S)

    def set_led(state: LEDState, effect=None):
        """Show `state`, optionally wearing a one-off `effect` instead of its
        palette entry - which is how a mode gets its own look without
        allocating a global LEDState (ROADMAP D4).

        With no explicit effect, the *active mode's* look for this state is
        used if it has chosen one; that is what lets two Pomodoros look
        different while both stay in `WORKING`. A mode that chose nothing
        resolves to None and the device falls back to the palette.

        A look that is a stop list (`sequencer.Sequence`) is handed to
        `_drive_sequence` rather than pushed - the device understands one
        effect at a time, not a schedule. Every call here first cancels
        whatever sequence task is running, whatever `state`/`effect` turn out
        to be: a sequence lasts until the next state change exactly like an
        ephemeral effect, and that includes this call wanting another one.

        Returns what actually went out - the look after the safety floor, or
        None for "the device's own palette entry". Callers may ignore it; the
        one that does not is `show_look` below, which has to *report* what the
        light is doing and must not re-derive it from the floor a second time.
        """
        nonlocal sequence_task
        if sequence_task is not None:
            sequence_task.cancel()
            sequence_task = None

        if effect is None:
            effect = look_for(cm.config, active_mode, state)
        if standby and state is LEDState.IDLE:
            # Standby dims the *resting* light and only that: it is the ambient
            # layer that is asleep, and an alarm ringing through a standby must
            # still look like an alarm. Substituted here, where a mode's own
            # look is, rather than at each of the several places that drop back
            # to IDLE - those would drift. It wins over whatever IDLE would
            # otherwise wear, a named look included (TODO 36a): "asleep" is the
            # one thing this light has to say, and a configured IDLE look is
            # exactly what would hide it. Nothing reachable pushes an explicit
            # IDLE effect while asleep - the readout is ambient, so `handle`'s
            # gate turned it away already.
            effect = LedEffect(style="solid", color=_STANDBY_COLOR)

        if isinstance(effect, sequencer.Sequence):
            # THE ONE GATE for a sequence's floor, mirroring flash_safe just
            # below for a plain effect - see config.sequence_safe. Nothing
            # else may call sequence_safe; a second call site is a second
            # floor with its own chance to drift from this one.
            floored = sequence_safe(effect, cm.config.min_flash_period_s)
            sequence_task = asyncio.create_task(_drive_sequence(state, floored))
            # The task pushes its first frame on the next loop iteration, not
            # synchronously - set_led stays non-blocking either way. The state
            # is already known, though, so the status line need not wait.
            status.led_state = state.value
            return floored

        # The one gate every pushed look passes through, which is why the floor
        # lives here rather than in each run_* loop: a mode computing its own
        # effect (the metronome's period, the countdown's colour) cannot route
        # around it, and neither can a look hand-edited into a scene file. The
        # palette's own entries are floored in push_palette instead.
        effect = flash_safe(effect, cm.config.min_flash_period_s)
        device.set_led(state, effect)
        status.led_state = state.value
        status.led_effect = effect
        return effect

    def show_look(state: LEDState, look):
        """Show one look now on behalf of the web UI's colour pickers, and
        answer with what actually went out.

        A thin wrapper rather than the endpoint calling `device.set_led`
        itself, and the thinness is the point: a stop list is a *schedule*, so
        previewing one needs the cancellable task and the `sequence_safe` gate
        that only this closure owns. The endpoint used to have neither, which
        is why "Show on the button" could only ever flash a sequence's first
        colour - the one thing about a sequence that is not the sequence.

        `look=None` means "back to the configured colours", which is already
        what `set_led` does with no effect: it re-resolves the state's own
        look, cancelling any preview still playing.

        **Assumes the host is awake and connected**, like everything else that
        drives the light from here (CLAUDE.md).
        """
        return set_led(state, look)

    def push_palette(palette: dict) -> None:
        """Send the stored palette, floored. Separate from `set_led` because
        the device renders these entries unasked when no effect overrides them,
        so a strobing palette entry would never pass that gate."""
        device.set_palette(
            {
                name: flash_safe(entry, cm.config.min_flash_period_s)
                for name, entry in palette.items()
            }
        )

    # Deferred until push_palette exists rather than pushed raw at connect
    # time: the very first palette the button sees has to be inside the floor
    # too. Nothing between here and device.start() reads the palette.
    push_palette(cm.config.led_palette)

    def base_look(state: LEDState):
        """The look a mode should build its live effect on top of - its own if
        it has one, the palette entry otherwise. What `run_countdown` walks the
        colour of, and what `run_metronome` rewrites the period of.

        A stop-list look falls back to the palette entry, exactly like a mode
        that named nothing: the *derived, host-animated* effects this function
        feeds (a ramp, a beat pulse, a ladder tick) need a style and a period
        to modify, which a schedule is not. `set_led` still renders a sequence
        directly wherever a mode's look is used as-is.
        """
        look = look_for(cm.config, active_mode, state)
        if isinstance(look, sequencer.Sequence):
            look = None
        return look or cm.config.led_palette.get(state.value)

    def driven_look(state: LEDState, drive: str):
        """The active mode's look for `state`, if it is a stop list this app
        can drive (TODO 36d). None otherwise, including for a plain effect.

        The counterpart of `base_look`: that one asks "what do I animate on top
        of", this one "did someone hand me a schedule to sample". A run loop
        that owns a number - a countdown's progress, a metronome's beat - asks
        this first and falls back to its own ramp or ladder.
        """
        look = look_for(cm.config, active_mode, state)
        if isinstance(look, sequencer.Sequence) and look.drive == drive:
            return look
        return None

    def sampled_paint(state: LEDState, seq: sequencer.Sequence):
        """A `paint(fraction)` that shows `seq` sampled at 0..1.

        The sampled twin of `ladder_paint`, making the same two moves for the
        same reasons: pushes go through the central `set_led`, and a frame
        identical to the last is not pushed at all (`ramp.differs` - a
        fire-and-forget radio should not carry a colour that has not moved).

        `sequence_safe` is deliberately *not* applied here: its dwell floor
        asks how fast one stop follows another, which for a sampled sequence is
        decided by how fast the app's number moves and not by the stops at all
        - a countdown steps once a second whatever its stop list says.
        """
        shown: sequencer.Frame | None = None

        def paint(fraction: float) -> None:
            nonlocal shown
            frame = sequencer.sample_at(seq, fraction)
            if frame is None:
                return
            if shown is not None and not ramp.differs(
                shown.color, frame.color, _COUNTDOWN_COLOR_STEP
            ):
                return
            shown = frame
            set_led(state, LedEffect(style="solid", color=frame.color))

        return paint

    def ladder_paint(spec, state: LEDState):
        """A `paint(seconds)` that shows `spec`'s colour for a moment in time.

        Returns `(paint, tick_s)` - the cadence comes back because the caller
        has to wake at it, and because it is not always the configured one.

        **The flash floor applies to the cadence, not to the effect's period.**
        A ladder changes colour every tick, so a 0.1s tick is a 10 Hz change
        rate however sedate the underlying style is - the hole `flash_safe`
        cannot see, since it reads `period_s` and a `solid` never strobes by
        its own reckoning. Colours are pushed only when they change: most ticks
        repeat the previous colour, and the radio is fire-and-forget.
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
                # The one way in to the light from the web UI. Handed over as
                # a callable so webui never imports main (dependency
                # inversion) and never becomes a second flash-floor gate.
                show_look=show_look,
                # Frozen here so the scene endpoints can say which changes are
                # waiting on a restart: the store, the lock, the web bind and
                # the BLE name were all decided above.
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
            log.info("web UI on http://%s:%d", cm.config.web_host, cm.config.web_port)
        except Exception as exc:
            log.error("web UI unavailable (%s) - continuing without it", exc)
            web_server = None

    loop = asyncio.get_running_loop()

    # SIGHUP is POSIX-only and reloads the config. SIGTERM/SIGINT exist
    # everywhere and are wired *outside* that check, because Windows (the host
    # this actually runs on) would otherwise have no graceful shutdown at all:
    # Ctrl+C unwinds as KeyboardInterrupt straight through the takeover loops
    # instead of letting them exit on `stop` and stop their timers and alarms.
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
        snooze_minutes set - go quiet for that long and ring again. Both waits
        watch `stop`, so SIGTERM during a long snooze shuts down promptly
        instead of waiting it out."""
        label = behavior.message or behavior.label or mode_name
        if args.demo:
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

        A named look wins, as everywhere else. With none chosen the fallback is
        *not* the bare ALERT palette entry - that is the ringing-alarm look,
        and a reminder indistinguishable from an alarm has failed at the one
        thing it is for. Breathing the same colour reads as "notice me" where
        the alarm's hard flash reads as "deal with me", and costs no wire code.
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

        Three deliberate differences from `ring_alarm`, which this parallels
        and does not touch. *Any* press clears it, because requiring a
        nominated gesture would make a reminder as demanding as an alarm. No
        snooze and no loop - a reminder you could postpone is an alarm with
        extra steps; schedule it again instead. And it times out
        (`timeout_minutes`, 0 = wait forever), because a reminder nobody was in
        the room for should not still be flashing at midnight. A timeout is not
        a clear: nothing is logged, because nobody saw it.
        """
        label = behavior.message or behavior.label or mode_name
        set_led(LEDState.ALERT, reminder_look(behavior))
        if behavior.chime:
            play_sound(Sound.ACK)  # once - the light is what persists
        status.last_message = label
        set_status("REMINDING")

        if args.demo:
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

    async def fire_hook(mode, which: str, session=None) -> None:
        """Run a mode's `on_enter` / `on_exit` action, if it has one.

        `session` is what the app just reported about itself - a flat dict of
        numbers, or None from an app with nothing to say and from every
        `on_enter`. It is checked against the contract *here*, at the one place
        a summary leaves the machine, rather than at each app's return
        statement: one gate, for the reason the flash floor has one.

        **A hook can never stop a mode starting or ending.** Everything below
        that can go wrong - a missing pool entry, a webhook that 404s, a MIDI
        port that has gone away, a bug in a primitive - ends as a log line and
        nothing else, because an app you cannot leave while a server across the
        room is down is the worse failure. `on_exit` is awaited (nothing is
        kept waiting by it, and a launcher's chain needs each app's exit to
        land before the next app's entry); `on_enter` is not - see `spawn_hook`.

        Deliberately silent in `status` and on the light: the app's own result
        is what the status line is reporting, and a THINKING flash around
        something nobody pressed for would be the plumbing showing through.
        """
        bound = getattr(mode, which)
        if bound is None:
            return  # the overwhelmingly common case, and it costs one getattr
        # The fourth place an action is dispatched, so the fourth place a bare
        # name has to be turned back into an action (CLAUDE.md).
        action = resolve_action(cm.config, bound)
        if action is None:
            log.warning("mode %r %s: no action named %r", mode.name, which, bound.name)
            return
        # Cleaned after the early returns above, so an app that reports
        # something into a mode with no hook - or with a dangling one - pays
        # nothing for it. A rejected key is a log line and a missing number,
        # never a failed hook: the app has already ended either way.
        carried, complaints = clean_summary(session)
        for complaint in complaints:
            log.warning("mode %r %s summary: %s", mode.name, which, complaint)
        try:
            result = await execute(
                action, trigger=which, mode_name=mode.name, store=store,
                session=carried,
            )
        except Exception:  # a hook bug must never cost you the mode
            log.exception("mode %r %s hook crashed", mode.name, which)
            return
        log.log(
            logging.INFO if result.ok else logging.WARNING,
            "mode %r %s: %s", mode.name, which, result.message,
        )

    _pending_hooks: set[asyncio.Task] = set()

    def spawn_hook(mode, which: str) -> None:
        """Fire an entry hook without waiting for it.

        A hook is fire-and-forget *like all feedback* (TODO 31), and here that
        phrase is load-bearing: awaiting `on_enter` would put up to
        `actions.WEBHOOK_TIMEOUT_S` between your press and the app opening, and
        a five-second pause before a Pomodoro starts reads as a broken button,
        not as a slow server.

        The set is not bookkeeping: `asyncio` holds only a weak reference to a
        running task, so a hook nobody is holding can be collected mid-flight
        and simply not happen. Same trap as the ctypes callback in midi_io.py,
        different library.
        """
        if getattr(mode, which) is None:
            return  # the common case, and it allocates nothing
        task = asyncio.create_task(fire_hook(mode, which))
        _pending_hooks.add(task)
        task.add_done_callback(_pending_hooks.discard)

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
        # The other place a mode is entered and left, and hooks fire from both:
        # an alarm the clock started is the same session as one you started by
        # hand.
        spawn_hook(mode, "on_enter")
        try:
            if isinstance(mode.behavior, ReminderBehavior):
                result = await run_reminder(mode.behavior, mode.name)
            else:
                result = await ring_alarm(mode.behavior, mode.name)
        except Exception as exc:  # a scheduled-mode bug must never kill the loop
            log.exception("scheduled mode crashed")
            result = ActionResult(False, f"internal error: {exc}")
        store.log_mode_exit(mode.name, entered_at)
        await fire_hook(mode, "on_exit", result.summary)
        active_mode = None
        status.last_ok = result.ok
        status.last_message = result.message
        set_led(LEDState.IDLE)
        set_status("IDLE")

    async def run_stopwatch(behavior: StopwatchBehavior, mode_name: str) -> ActionResult:
        """Takeover stopwatch: start a timer, then own the button - short_press
        or double_tap marks a lap (logs `<log_as>_lap`), long_press stops and
        exits (logs the elapsed time via toggle_timer). A None trigger
        (shutdown) stops the running timer so it isn't left open, then exits.
        The caller drops the LED/status back to IDLE.

        Reports `elapsed_s` and `laps` on the way out (summary.py) - the two
        numbers a stopwatch is, and both already here."""
        log_as = behavior.log_as
        store.toggle_timer(log_as, mode=mode_name)  # returns ("started", None)
        set_led(LEDState.TIMING)
        set_status("TIMING")
        status.last_mode = mode_name
        status.last_message = f"{log_as} timer started"
        laps = 0

        def tally(elapsed) -> dict:
            """The same two keys on every exit, shutdown included - a summary
            whose shape depends on how the session ended renumbers an OSC
            receiver's arguments (summary.py)."""
            return {"elapsed_s": round(elapsed or 0.0, 1), "laps": laps}

        # The open timer. Every normal exit clears this *before* closing the
        # timer, so the finally only fires on an abnormal (exception) exit -
        # closing a dangling timer without double-toggling a normal stop.
        running = True
        try:
            if args.demo:
                await asyncio.sleep(_SUCCESS_DISPLAY_S)  # then close the timer
                running = False
                _, elapsed = store.toggle_timer(log_as, mode=mode_name)
                return ActionResult(
                    True, f"{log_as} (demo: ran {_fmt_elapsed(elapsed or 0)})",
                    tally(elapsed),
                )
            # With a subdivision ladder on, the stopwatch grows a tick: the
            # light has to say what time it is, which means waking to change
            # it. Without one it blocks indefinitely on the next press - waking
            # twice a second to repaint a colour nobody asked for would be
            # pure radio traffic.
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
                    # A session cut short by a shutdown is still a session, and
                    # reports the same two numbers.
                    _, elapsed = store.toggle_timer(log_as, mode=mode_name)
                    return ActionResult(
                        True, f"{log_as} stopped (shutdown)", tally(elapsed)
                    )
                if trigger is TriggerType.LONG_PRESS:
                    running = False
                    _, elapsed = store.toggle_timer(log_as, mode=mode_name)
                    message = f"{log_as} stopped after {_fmt_elapsed(elapsed or 0)}"
                    total = store.total_today(log_as)
                    if total > (elapsed or 0):
                        message += f" ({_fmt_elapsed(total)} today)"
                    if laps:
                        message += f", {laps} lap(s)"
                    return ActionResult(True, message, tally(elapsed))
                # short_press / double_tap -> a lap
                store.log_event(f"{log_as}_lap", mode=mode_name)
                laps += 1
                play_sound(Sound.ACK)
                status.last_message = f"Lap {laps}"
        finally:
            if running:  # an exception left the timer open - close it
                store.toggle_timer(log_as, mode=mode_name)

    async def run_counter(behavior: CounterBehavior, mode_name: str) -> ActionResult:
        """Takeover counter: count starts at today's `count_today(event)`
        rather than 0, then owns the button - short_press or double_tap logs
        `event` (so count_today / streaks just work) and bumps the live
        count, long_press exits with a session summary. A None trigger
        (shutdown) just exits. The caller drops the LED/status back to IDLE.

        Starting from the store rather than a local zero is TODO 15's "one line
        of state": an ambient `log`/`readout` binding and this takeover log the
        same event name, so counting from Home and then entering the Counter to
        continue agrees by construction - they were already the same rows.

        Reports both numbers it holds (summary.py): `count`, the day's total,
        and `added`, this session's share of it. A receiver that only ever got
        the first could not tell a busy session from an idle one."""
        event = behavior.event
        count = store.count_today(event)
        opened_at = count  # what the day already held, so `added` can be told
        set_led(LEDState.COUNTING)
        set_status("COUNTING")
        status.last_mode = mode_name
        status.last_message = f"{event}: {count}"

        def tally() -> dict:
            return {"count": count, "added": count - opened_at}

        if args.demo:
            store.log_event(event, mode=mode_name)  # one increment, then out
            count += 1
            play_sound(Sound.ACK)
            status.last_message = f"{event}: {count}"
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"{event}: {count} this session (demo)", tally())
        while True:
            trigger = await _wait_for_trigger(device.events, stop)
            if trigger is None:  # shutting down
                return ActionResult(
                    True, f"{event}: {count} this session (shutdown)", tally()
                )
            if trigger is TriggerType.LONG_PRESS:
                return ActionResult(True, f"{event}: {count} this session", tally())
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

        Which gesture does what (behavior.gestures) and how transitions happen
        (behavior.advance) are configurable - the two things people disagree
        about most. What is *not* is that a finished work block gets logged, so
        counts and streaks work on focus time like they do on everything else.
        """
        loop = asyncio.get_running_loop()
        completed = 0  # work blocks finished this session
        focused_s = 0.0
        working = True  # which half of the cycle we are in
        paused = False
        pending = False  # a block has ended and is waiting for a gesture
        # A "get ready" pause before the first block. It counts down like a
        # phase but is not one - nothing is logged and no block is credited,
        # which is why it is a flag rather than a third value of `working`.
        leading = behavior.lead_in_s > 0
        remaining = behavior.lead_in_s if leading else behavior.work_s
        deadline = loop.time() + remaining

        def phase_label() -> str:
            if leading:
                return "get ready"
            if pending:
                return "ready for the next block" if working else "ready for a break"
            return "focus" if working else "break"

        def show() -> None:
            state = LEDState.WORKING if working else LEDState.RESTING
            if leading:
                # The work phase's colour, frozen: the lead-in is about the
                # block that is coming, so wearing its colour says which one.
                base = base_look(state)
                set_led(state, replace(base, style=behavior.waiting_style)
                        if base is not None else None)
                set_status("WORKING")
                status.last_message = (
                    f"{mode_name}: get ready - "
                    f"{_fmt_elapsed(max(0.0, deadline - loop.time()))}"
                )
                return
            if paused or pending:
                # The same phase's colour, frozen into waiting_style instead of
                # its usual animation. Not LISTENING: that is the button's
                # global "your press registered" state, edited once in the
                # Lights tab, and a Pomodoro does not own it (MODE_LED_STATES).
                base = base_look(state)
                effect = (
                    replace(base, style=behavior.waiting_style)
                    if base is not None else None
                )
                set_led(state, effect)
            else:
                set_led(state)
            set_status("WORKING" if working else "RESTING")
            left = max(0.0, deadline - loop.time()) if not (paused or pending) else remaining
            status.last_message = (
                f"{mode_name}: {phase_label()}"
                + (f" - {_fmt_elapsed(left)} left" if not pending else "")
                + (f" ({completed} done)" if completed else "")
            )

        def start_phase(work: bool) -> None:
            nonlocal working, remaining, deadline, paused, pending, leading
            working = work
            if work:
                seconds = behavior.work_s
            elif completed and completed % behavior.blocks_before_long_break == 0:
                seconds = behavior.long_break_s
            else:
                seconds = behavior.break_s
            remaining = seconds
            deadline = loop.time() + remaining
            paused = pending = leading = False

        def summary(suffix: str = "") -> ActionResult:
            text = f"{completed} block(s), {_fmt_elapsed(focused_s)} focused"
            # Every exit comes through here, so the session's numbers ride out
            # of one place rather than seven (summary.py). Rounded because
            # focused_s is a sum of floats and no exit hook wants
            # 1500.0000000000002 seconds.
            return ActionResult(
                True, f"{mode_name}: {text}{suffix}",
                {"blocks": completed, "focused_s": round(focused_s, 1)},
            )

        status.last_mode = mode_name
        show()

        if args.demo:
            store.log_event(behavior.log_as, mode=mode_name)  # one block, then out
            completed, focused_s = 1, behavior.work_s
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
                if leading:
                    # The lead-in ran out: nothing is credited, the first block
                    # just begins.
                    play_sound(Sound.ACK)
                    start_phase(True)
                    show()
                    continue
                # The block ran out.
                if working:
                    completed += 1
                    focused_s += behavior.work_s
                    store.log_event(behavior.log_as, mode=mode_name)
                    play_sound(Sound.SUCCESS)
                    if behavior.rounds and completed >= behavior.rounds:
                        # Checked after the block is logged, so the last round
                        # counts exactly like the ones before it.
                        return summary(" - session complete")
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
                added = behavior.extend_s
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

        Fast tempos stay honest: `max_bpm` is yours to raise, and where it
        collides with the flash floor the light marks every Nth beat rather
        than the tempo being clamped - see `metronome_flash`.
        """
        loop = asyncio.get_running_loop()
        taps: list[float] = []  # loop.time() of recent beats, oldest first
        bpm: float | None = None
        beats = 0
        set_led(LEDState.METRONOME)
        set_status("METRONOME")
        status.last_mode = mode_name

        # Two ways to put a colour on a beat, in the precedence CLAUDE.md sets
        # out: **a named beats-driven stop list wins over a ladder** (TODO 36d).
        #
        # Both count *beats*, not seconds - the tempo already decides the
        # timing, so what a colour adds is an accent ("every 4th beat"), and a
        # seconds-based version would drift the moment you tapped a new tempo.
        # Both also change who drives the light: normally the device animates
        # the pulse and the host only sends a period, but a colour per beat has
        # to come from the host, so the loop grows a beat clock below whenever
        # either is in play.
        beat_seq = driven_look(LEDState.METRONOME, "beats")
        beat_cycle = sequencer.span_total(beat_seq) if beat_seq is not None else 0.0
        if beat_seq is not None and beat_cycle <= 0:
            # Every stop zero-width: there is no cycle to spread over beats, so
            # there is nothing to sample. Fall through to the ladder (or to
            # nothing) rather than dividing by it.
            log.warning(
                "metronome %r: its beats look has no length - ignoring it", mode_name,
            )
            beat_seq = None
        sampling_beats = sampled_paint(LEDState.METRONOME, beat_seq) if beat_seq else None
        laddered = behavior.ladder.enabled and sampling_beats is None
        beat_driven = laddered or sampling_beats is not None
        shown_beat: str | None = None

        def paint_beat(beat: int) -> None:
            """Show whatever owns the colour of beat number `beat`."""
            nonlocal shown_beat
            if sampling_beats is not None:
                # `sample_at` wraps a repeating sequence itself, so the beat
                # number goes in unreduced and a four-beat pattern lands the
                # same way on beat 4, 8 and 12.
                sampling_beats(beat / beat_cycle)
                return
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

            With anything painting per beat - a ladder or a beats-driven stop
            list - the period is *not* pushed: the beat clock already owns the
            light, and pulsing underneath it would be two clocks on one light.
            `per_flash` still comes back, because it is how many beats the
            light may mark without crossing the flash floor and both painters
            obey that same grouping rather than inventing a second rule.
            """
            base = base_look(LEDState.METRONOME)
            period, per_flash = metronome_flash(tempo, cm.config.min_flash_period_s)
            if base is not None and not beat_driven:
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

        # Following a DAW's clock, if this mode is configured to. A port that
        # is not there costs the sync and nothing else - a practice tool that
        # refuses to run because a DAW is shut is the wrong trade.
        #
        # **This is host-side forever**, not one of the "assumes the host is
        # awake" compromises to find and remove later - the DAW is on the host
        # by definition (ARCHITECTURE.md's split).
        clock = None
        if behavior.clock_port:
            try:
                clock = midi_io.ClockListener(behavior.clock_port)
                where = clock.start()
                status.last_message = f"waiting for MIDI clock on {where}"
                log.info("metronome %r following MIDI clock on %s", mode_name, where)
            except Exception as exc:  # noqa: BLE001 - any failure means tap-only
                log.warning("metronome %r: no MIDI clock (%s)", mode_name, exc)
                status.last_message = f"no MIDI clock ({exc}) - tap to set the tempo"
                clock = None

        # The beat clock, which only exists when something paints per beat. It
        # runs from `start_bpm` immediately, for the same reason push_tempo
        # does: the light should keep time before the first tap lands.
        beat_no = 0
        beat_step = 60.0 / behavior.start_bpm * per_flash
        next_beat = loop.time() + beat_step if beat_driven else None
        if beat_driven:
            paint_beat(0)

        def take_tempo(tempo: float, now: float) -> None:
            """Adopt `tempo` - from a tap or from the clock - and re-phase."""
            nonlocal bpm, per_flash, beat_step, next_beat
            bpm = min(behavior.max_bpm, tempo)
            per_flash = push_tempo(bpm)
            if next_beat is not None:
                # Re-phase the beat clock onto now rather than letting it keep
                # the old tempo's grid. A metronome you retap - or a project
                # whose tempo you change - should follow you immediately.
                beat_step = 60.0 / bpm * per_flash
                next_beat = now + beat_step

        def poll_clock(now: float) -> None:
            """Read the DAW's tempo, if it is still talking."""
            fresh = clock.bpm()
            if fresh is None:
                return
            if clock.stale(bpm):
                # The pulses stopped without a `0xFC` - the DAW was quit,
                # unplugged or paused mid-stream. Freeze at the last tempo and
                # say so: a metronome that blanks the moment a cable twitches
                # is less useful than one that keeps time on its own.
                if bpm is not None:
                    status.last_message = f"{describe(bpm, per_flash)} (clock stopped)"
                return
            # A threshold, not equality - see _CLOCK_BPM_EPSILON.
            if bpm is None or abs(fresh - bpm) >= _CLOCK_BPM_EPSILON:
                take_tempo(fresh, now)
            status.last_message = (
                f"{describe(bpm, per_flash)} from {clock.port_name}"
                + ("" if clock.rolling else " (stopped)")
            )

        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            if clock is not None:
                clock.stop()
            return ActionResult(True, "metronome (demo: no taps)")
        next_poll = loop.time() + _CLOCK_POLL_S if clock is not None else None
        try:
            while True:
                # Two clocks want waking: the beat and the tempo poll.
                # Whichever is sooner sets the timeout, and both are checked on
                # arrival, so neither can starve the other.
                deadlines = [d for d in (next_beat, next_poll) if d is not None]
                timeout = (
                    max(0.0, min(deadlines) - loop.time()) if deadlines else None
                )
                trigger = await _wait_for_trigger(device.events, stop, timeout)
                if trigger is None and deadlines and not stop.is_set():
                    now = loop.time()
                    if next_poll is not None and now >= next_poll:
                        next_poll = now + _CLOCK_POLL_S
                        poll_clock(now)
                    if next_beat is not None and now >= next_beat:
                        # A beat, not a press. Advancing by `per_flash` keeps
                        # the beat *number* honest at tempos where the light
                        # marks only every Nth one - a painter reads beats, not
                        # flashes.
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
                beats += 1
                if behavior.sound_on_tap:
                    play_sound(Sound.ACK)
                if clock is not None:
                    # Clocked: the DAW owns the tempo, so a tap marks a beat
                    # and nothing more. Two things steering one number is how
                    # you get a metronome that argues with the session.
                    continue
                if taps and (now - taps[-1]) > behavior.reset_gap_s:
                    taps.clear()
                taps.append(now)
                del taps[:-behavior.tap_history]
                if len(taps) >= 2:
                    intervals = [b - a for a, b in zip(taps, taps[1:])]
                    take_tempo(60.0 / (sum(intervals) / len(intervals)), now)
                    status.last_message = describe(bpm, per_flash)
                else:
                    status.last_message = "tap again to set the tempo"
        finally:
            if clock is not None:
                clock.stop()

    async def run_countdown(behavior: CountdownBehavior, mode_name: str) -> ActionResult:
        """Takeover countdown: a fixed run to zero with the LED's *colour*
        walking `behavior.ramp` as the time goes, then the alarm.

        Style and colour are driven separately, which is the whole point - the
        light flashes at a fixed period the entire time while the colour moves
        from one end of the ramp to the other, so "flash" and "fade over the
        timer" are not two settings fighting over the same light.

        Long press leaves early; any other press acknowledges without stopping
        the clock, since the time left is already on the status line.

        **The ramp is walked host-side, and knowingly so**: each colour goes
        down as an ephemeral effect (ROADMAP D4), which costs a radio write
        every few seconds and a host awake to send them. Moving the ramp onto
        the device is what fixes that, and this is the shape it moves in.
        TIMING stays the state being shown - that is what the status line and
        the web UI report - and only its appearance is borrowed.
        """
        loop = asyncio.get_running_loop()
        total = behavior.minutes * 60
        deadline = loop.time() + total
        label = behavior.label or mode_name
        # Where the *shape* of the light comes from. A named look wins when the
        # mode has one - looks exist to be a mode's appearance, so letting the
        # template's own fields override one would make choosing a look do
        # nothing here. A stop-list look has no style or period to take: same
        # fallback as base_look, warned about here because this runs once per
        # countdown rather than every tick.
        look = look_for(cm.config, active_mode, LEDState.TIMING)
        if isinstance(look, sequencer.Sequence):
            log.warning(
                "countdown %r: TIMING's look is a stop list, which has no "
                "style or period for the ramp to borrow - using the mode's "
                "own %r/%.2fs", mode_name, behavior.style, behavior.period_s,
            )
            look = None
        style = look.style if look is not None else behavior.style
        # Unfloored: every effect this loop pushes goes through set_led, the
        # one place that enforces it.
        period = look.period_s if look is not None else behavior.period_s
        pushed: str | None = None

        # A ramp can only be seen through a style that renders `color`. A
        # rainbow is all the hues by definition and ignores it
        # (STYLE_USES_COLOR), so walking a ramp underneath one is invisible
        # *and* costs a radio write every time it moves. Say so once, then stop
        # pushing colour into a style that discards it.
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

        # Three things can decide TIMING's colour and only one may run:
        # **named stop list > ladder > ramp**, the ordering CLAUDE.md sets out
        # (TODO 36d).
        #
        # All three are driven by the same number, and it is *remaining* time
        # rather than elapsed - which is what a countdown is about: the
        # ten-second colour lands on ten seconds left, not ten seconds in.
        progress_seq = driven_look(LEDState.TIMING, "progress")
        sampling = sampled_paint(LEDState.TIMING, progress_seq) if progress_seq else None
        ticking, tick_s = (
            ladder_paint(behavior.ladder, LEDState.TIMING)
            if behavior.ladder.enabled and sampling is None
            else (None, _COUNTDOWN_TICK_S)
        )

        set_led(LEDState.TIMING)
        set_status("TIMING")
        status.last_mode = mode_name

        if args.demo:
            (sampling or paint)(0.0)  # the opening colour, then out
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"{label} (demo: {behavior.minutes:g} min)")

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            if sampling is not None:
                sampling(1.0 - remaining / total)
            elif ticking is not None:
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

    async def run_hotcold(behavior: HotColdBehavior, mode_name: str) -> ActionResult:
        """Hot/Cold: a hue wheel spins, a press stops it, the light says how
        close you got to a target only the button knows.

        **This loop deliberately holds no game state.** What a press means
        lives in [hotcold.py](hotcold.py) as a pure step function; what is left
        here is the part that cannot be pure - a clock, a queue, a radio, a die
        roll and a database. A loop shaped like this survives the Stage-3 move
        onto the device; one that reasons about the game does not.

        One radio write per round, not per frame: the wheel is a single
        `rainbow` effect and the host works out where it has got to
        arithmetically (hotcold.phase_at), which is the only reason a
        stop-the-spinner game is possible over a fire-and-forget link.
        """
        loop = asyncio.get_running_loop()
        game = hotcold.Game(
            sweep_s=behavior.sweep_s,
            rounds=behavior.rounds,
            tolerance=behavior.tolerance,
            segments=behavior.segments,
            reveal_s=behavior.reveal_s,
            # Asked, not assumed: a real button's gestures arrive a tap-window
            # late and an injected one arrives instantly, and scoring the
            # second as if it were the first puts every guess 0.4 s of wheel
            # away from where the player aimed.
            latency_s=device.press_latency_s,
        )
        # LISTENING is the state byte and it is honest - the button is waiting
        # for you to press - but every look below is pushed explicitly, so the
        # palette's LISTENING never shows. Same bargain the launcher makes: the
        # state is for the status line and for a device too old for effects.
        base = base_look(LEDState.LISTENING)

        def render(effects, state: hotcold.Game) -> str | None:
            """Turn what the game asked for into light, sound and rows.

            Returns the closing message if the session ended, else None.
            """
            leaving = None
            for effect in effects:
                if isinstance(effect, hotcold.Spin):
                    if base is not None:
                        # White rather than the palette's colour: `rainbow`
                        # reads its brightest channel as brightness, so
                        # borrowing LISTENING's entry would let an unrelated
                        # setting quietly dim the game.
                        set_led(LEDState.LISTENING, replace(
                            base, style="rainbow", color="#ffffff",
                            period_s=effect.period_s,
                        ))
                    round_no = state.played + 1
                    of = f"/{state.rounds}" if state.rounds else ""
                    status.last_message = f"round {round_no}{of} - stop the wheel"
                elif isinstance(effect, hotcold.Reveal):
                    if base is not None:
                        set_led(LEDState.LISTENING, replace(
                            base, style="solid",
                            color=ramp.color_at(behavior.ramp, effect.closeness),
                        ))
                    play_sound(Sound.SUCCESS if effect.hit else Sound.ACK)
                    got = round(effect.closeness * 100)
                    status.last_message = (
                        f"{got}% - on target!" if effect.hit else f"{got}%"
                    )
                elif isinstance(effect, hotcold.Score):
                    # The closeness goes in the value column, so a run of
                    # games is something /api/events can actually plot.
                    store.log_event(
                        behavior.log_as, mode=mode_name,
                        value=round(effect.closeness * 100, 1),
                    )
                elif isinstance(effect, hotcold.Leave):
                    leaving = effect.message
            return leaving

        set_status("HOTCOLD")
        status.last_mode = mode_name
        game, effects = hotcold.step(
            game, hotcold.START, loop.time(), random.random()
        )
        render(effects, game)

        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(
                True, f"hot/cold (demo: {behavior.sweep_s:g}s wheel)",
                hotcold.tally(game),
            )

        while True:
            trigger = await _wait_for_trigger(device.events, stop)
            if trigger is None or trigger is TriggerType.LONG_PRESS:
                game, effects = hotcold.step(game, hotcold.LEAVE, loop.time())
                message = render(effects, game) or hotcold.summary(game)
                return ActionResult(
                    True, message + ("" if trigger else " (shutdown)"),
                    hotcold.tally(game),
                )

            # short press / double tap - the wheel stops here
            game, effects = hotcold.step(game, hotcold.GUESS, loop.time())
            ended = render(effects, game)

            # Hold the answer up long enough to read it, discarding presses
            # aimed at a wheel that had already stopped - the long press
            # excepted, because "up one level" has to work from anywhere.
            until = loop.time() + behavior.reveal_s
            leaving = False
            while (left := until - loop.time()) > 0:
                during = await _wait_for_trigger(device.events, stop, timeout=left)
                if stop.is_set():
                    return ActionResult(
                        True, f"{hotcold.summary(game)} (shutdown)",
                        hotcold.tally(game),
                    )
                if during is TriggerType.LONG_PRESS:
                    leaving = True
                    break

            if ended is not None:
                return ActionResult(True, ended, hotcold.tally(game))
            if leaving:
                game, effects = hotcold.step(game, hotcold.LEAVE, loop.time())
                return ActionResult(
                    True, render(effects, game) or hotcold.summary(game),
                    hotcold.tally(game),
                )

            game, effects = hotcold.step(
                game, hotcold.NEXT, loop.time(), random.random()
            )
            render(effects, game)

    async def run_reaction(behavior: ReactionBehavior, mode_name: str) -> ActionResult:
        """Reaction timer: the light goes out, comes back without warning, and
        the time until you press is logged.

        Same split as run_hotcold - the rules are pure in
        [reaction.py](reaction.py). Read that module before believing a number:
        the multi-tap window is corrected for and the radio's one-way latency
        is not, so these times compare with each other rather than with a
        stopwatch.
        """
        loop = asyncio.get_running_loop()
        game = reaction.Game(
            rounds=behavior.rounds,
            reveal_s=behavior.reveal_s,
            # See run_hotcold: without this a simulated press reads as having
            # happened before the light did, and every attempt is a false start.
            latency_s=device.press_latency_s,
        )
        base = base_look(LEDState.LISTENING)
        # None once the light is on: it doubles as "how long until the go
        # signal" and "are we still waiting", the only state this driver holds.
        armed_for: float | None = None

        def delay() -> float:
            return random.uniform(behavior.min_delay_s, behavior.max_delay_s)

        def show(color: str) -> None:
            if base is not None:
                set_led(LEDState.LISTENING, replace(base, style="solid", color=color))

        def render(effects, state: reaction.Game) -> str | None:
            nonlocal armed_for
            leaving = None
            for effect in effects:
                if isinstance(effect, reaction.Arm):
                    armed_for = effect.delay_s
                    show(_REACTION_DARK)
                    status.last_message = "wait for it..."
                elif isinstance(effect, reaction.Go):
                    armed_for = None
                    # A brightness jump rather than a hue change: it is the
                    # fastest thing an eye picks up, and the point of the
                    # signal is to be seen, not to be identified.
                    show("#ffffff")
                    status.last_message = "press!"
                elif isinstance(effect, reaction.Result):
                    if effect.false_start:
                        show(_REACTION_FALSE_START)
                        play_sound(Sound.ERROR)
                        status.last_message = "too early"
                    else:
                        ms = effect.ms or 0.0
                        # Walked by how well you did, so the good end of the
                        # ramp is the far end. Anything slower than slowest_ms
                        # is still logged honestly, it just pins the colour.
                        good = 1.0 - min(1.0, ms / behavior.slowest_ms)
                        show(ramp.color_at(behavior.ramp, good))
                        play_sound(Sound.SUCCESS)
                        # `state` is the game *after* the step, so best_ms is
                        # already this attempt if it was the best; the played>1
                        # guard stops the first one crowing.
                        beat_it = state.played > 1 and ms <= (state.best_ms or ms)
                        status.last_message = f"{round(ms)} ms{' - best yet' if beat_it else ''}"
                elif isinstance(effect, reaction.Score):
                    store.log_event(
                        behavior.log_as, mode=mode_name, value=round(effect.ms, 1)
                    )
                elif isinstance(effect, reaction.Leave):
                    leaving = effect.message
            return leaving

        set_status("REACTION")
        status.last_mode = mode_name
        game, effects = reaction.step(game, reaction.START, loop.time(), delay())
        render(effects, game)

        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(
                True, "reaction (demo: no attempts)", reaction.tally(game)
            )

        while True:
            trigger = await _wait_for_trigger(device.events, stop, timeout=armed_for)
            if stop.is_set():
                return ActionResult(
                    True, f"{reaction.summary(game)} (shutdown)", reaction.tally(game)
                )
            if trigger is None:
                if armed_for is None:  # not a timeout - we are shutting down
                    return ActionResult(
                        True, f"{reaction.summary(game)} (shutdown)",
                        reaction.tally(game),
                    )
                # The wait elapsed with nothing pressed: light up, clock starts.
                game, effects = reaction.step(game, reaction.GO, loop.time())
                render(effects, game)
                continue

            if trigger is TriggerType.LONG_PRESS:
                game, effects = reaction.step(game, reaction.LEAVE, loop.time())
                return ActionResult(
                    True, render(effects, game) or reaction.summary(game),
                    reaction.tally(game),
                )

            game, effects = reaction.step(game, reaction.PRESS, loop.time())
            ended = render(effects, game)

            # Hold the result up long enough to read, discarding presses aimed
            # at it - the long press excepted, because "up one level" has to
            # work from anywhere.
            until = loop.time() + behavior.reveal_s
            leaving = False
            while (left := until - loop.time()) > 0:
                during = await _wait_for_trigger(device.events, stop, timeout=left)
                if stop.is_set():
                    return ActionResult(
                        True, f"{reaction.summary(game)} (shutdown)",
                        reaction.tally(game),
                    )
                if during is TriggerType.LONG_PRESS:
                    leaving = True
                    break

            if ended is not None:
                return ActionResult(True, ended, reaction.tally(game))
            if leaving:
                game, effects = reaction.step(game, reaction.LEAVE, loop.time())
                return ActionResult(
                    True, render(effects, game) or reaction.summary(game),
                    reaction.tally(game),
                )

            game, effects = reaction.step(game, reaction.NEXT, loop.time(), delay())
            render(effects, game)

    async def run_signal(behavior: SignalBehavior, mode_name: str) -> ActionResult:
        """A signal light: short press moves to the next position and stays
        there, long press leaves, double tap re-sends where it already is.

        **Entering is not a change.** It shows `start_at` without firing that
        position's message, because walking up to your own desk should not
        announce anything - the first *press* is the first announcement. The
        re-send on double tap covers what follows from that: the receiving end
        missed one, or was not running yet.

        This loop holds the button for as long as it is showing - the "one
        foreground app" decision (TODO 15) made visible.
        """
        states = behavior.states
        index = min(behavior.start_at, len(states) - 1)

        async def announce(state) -> str:
            """Light the position, and send whatever it carries."""
            look = LedEffect(style=state.style, color=state.color)
            set_led(LEDState.LISTENING, look)
            status.last_message = f"{state.name} ({index + 1}/{len(states)})"
            if state.action is None:
                return state.name
            # A position may name a pooled action instead of carrying one
            # (config.NamedAction); resolve_action is the one place that is
            # undone, here as in handle() and run_control().
            action = resolve_action(cm.config, state.action)
            if action is None:
                log.warning(
                    "signal %r: %s names no action that exists", mode_name, state.name
                )
                status.last_message = f"{state.name} - no action named {state.action.name!r}"
                return state.name
            # Reusing execute() is the whole reason this template is cheap:
            # webhook, OSC and log all already work here, and so will the next
            # primitive anyone adds.
            result = await execute(
                action, trigger="signal", mode_name=mode_name, store=store,
            )
            if not result.ok:
                # A failed send must not strand the light on the old colour -
                # the button has moved, and saying so is more honest than
                # pretending the position did not change.
                log.warning("signal %r: %s", mode_name, result.message)
                status.last_message = f"{state.name} - {result.message}"
            return state.name

        set_status("SIGNAL")
        status.last_mode = mode_name
        current = states[index]
        set_led(LEDState.LISTENING, LedEffect(
            style=current.style, color=current.color,
        ))
        status.last_message = f"{current.name} ({index + 1}/{len(states)})"

        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"signal (demo: on {current.name})")

        while True:
            trigger = await _wait_for_trigger(device.events, stop)
            if trigger is None:
                return ActionResult(True, f"signal left on {states[index].name} (shutdown)")
            if trigger is TriggerType.LONG_PRESS:
                return ActionResult(True, f"signal left on {states[index].name}")
            if trigger is TriggerType.DOUBLE_TAP:
                await announce(states[index])  # same position, sent again
                continue
            index = (index + 1) % len(states)
            name = await announce(states[index])
            if behavior.log_as:
                store.log_event(behavior.log_as, mode=mode_name, value=index)
            status.last_ok = True
            log.info("signal %r -> %s", mode_name, name)

    async def run_control(behavior: ControlBehavior, mode_name: str):
        """A control surface: gestures fire actions until a long press leaves.

        The same dispatch `handle()` does for the ambient layer, held open. It
        stays a loop rather than becoming one-shot because that is the whole
        difference between this and an actions mode: you opened it to send
        several things, and returning to IDLE after each would make every
        command past the first cost a trip through the launcher.

        **Feedback is per action, not per app.** SUCCESS or ERROR flashes and
        then the surface's resting light comes back, which is why this template
        needs no LED state of its own.

        Long press is not checked against the bindings because it cannot be
        bound - `_parse_control_body` drops it, keeping the escape gesture a
        property of the parser rather than of this loop's memory.

        **Returns `(result, chosen)` like `run_launcher`**, and for the same
        reason: an `enter_mode` binding makes this a menu page, so it has to be
        able to name what runs next. `execute()` cannot - it has no idea what a
        mode is, which is why `handle()` intercepts that action at the ambient
        layer too. Four gestures per page and a branch on any of them is what
        makes a tree of menus cost no new template.
        """
        set_status("CONTROL")
        status.last_mode = mode_name
        fired = 0

        def resting() -> None:
            set_led(LEDState.LISTENING)
            status.last_message = (
                f"{mode_name}: {len(behavior.actions)} controls, long press to leave"
            )

        resting()
        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"control (demo: {mode_name})"), None

        while True:
            trigger = await _wait_for_trigger(device.events, stop)
            if trigger is None:
                return ActionResult(
                    True, f"{mode_name} left ({fired} sent, shutdown)"
                ), None
            if trigger is TriggerType.LONG_PRESS:
                return ActionResult(True, f"{mode_name} left ({fired} sent)"), None
            bound = behavior.actions.get(trigger.value)
            if bound is None:
                # Nothing bound. Say so and stay open - dropping out of the app
                # because you mistimed a tap would be the opposite of useful.
                status.last_message = f"{mode_name}: nothing on {trigger.value}"
                play_sound(Sound.ERROR)
                continue
            # A binding may be a name rather than an action - see
            # resolve_action. A name with nothing behind it is treated exactly
            # like nothing bound, for the same reason: the page stays open.
            action = resolve_action(cm.config, bound)
            if action is None:
                status.last_message = f"{mode_name}: no action named {bound.name!r}"
                play_sound(Sound.ERROR)
                continue
            if isinstance(action, EnterModeAction):
                # A branch to another page, resolved here rather than in
                # execute() because a mode is not a thing an action primitive
                # knows about. Handing the target back lets enter_takeover
                # close this page before opening the next, so a menu tree is a
                # sequence of pages and never a stack that can grow.
                target = next(
                    (m for m in cm.config.modes if m.name == action.target), None
                )
                if target is not None and isinstance(
                    target.behavior, TAKEOVER_BEHAVIORS
                ):
                    return ActionResult(
                        True, f"{mode_name} -> {target.name}"
                    ), target
                status.last_ok = False
                status.last_message = (
                    f"enter_mode: no takeover mode named {action.target!r}"
                )
                set_led(LEDState.ERROR)
                play_sound(Sound.ERROR)
                await asyncio.sleep(_CONTROL_CONFIRM_S)
                resting()
                continue
            set_led(LEDState.THINKING)
            try:
                result = await execute(
                    action, trigger=trigger.value, mode_name=mode_name, store=store
                )
            except Exception as exc:  # a primitive bug must never close the app
                log.exception("control action crashed")
                result = ActionResult(False, f"internal error: {exc}")
            if result.ok:
                fired += 1
                if behavior.log_as:
                    store.log_event(behavior.log_as, mode=mode_name)
                status.last_ok = True
                status.last_message = result.message
                set_led(LEDState.SUCCESS)
                play_sound(Sound.SUCCESS)
            else:
                status.last_ok = False
                status.last_message = result.message
                set_led(LEDState.ERROR)
                play_sound(Sound.ERROR)
            log.info("control %r %s -> %s", mode_name, trigger.value, result.message)
            await asyncio.sleep(_CONTROL_CONFIRM_S)
            resting()

    # Every takeover behaviour, for the two places that ask "is this a mode a
    # gesture can start". One tuple rather than two lists that drift apart -
    # the launcher both *is* a takeover and *chooses* one, which made that real.
    TAKEOVER_BEHAVIORS = (
        AlarmBehavior, StopwatchBehavior, CounterBehavior, PomodoroBehavior,
        MetronomeBehavior, CountdownBehavior, LauncherBehavior, HotColdBehavior,
        ReactionBehavior, SignalBehavior, ControlBehavior,
    )

    def app_look(target):
        """The colour `target` should be shown in while a launcher offers it:
        its own named look for the state it owns, else that state's palette
        entry, else None. It needs no new config, because a mode already knows
        what it looks like."""
        states = MODE_LED_STATES.get(target.template, ())
        if not states:
            return None
        state = LEDState(states[0])
        return look_for(cm.config, target, state) or cm.config.led_palette.get(
            state.value
        )

    def launcher_targets(behavior) -> list:
        """The apps a launcher offers, in the order it offers them.

        An empty `targets` means every takeover mode in config order, so a
        newly added app shows up without anyone editing a list. Launchers are
        never offered: a launcher that can launch itself is the one shape that
        turns "replace, don't nest" back into a loop with no user in it. A
        named target that does not exist is warned about *here* rather than at
        parse time - config order is not dependency order, and a launcher
        listed above its apps is the normal way to write one.
        """
        apps = [
            m for m in cm.config.modes
            if isinstance(m.behavior, TAKEOVER_BEHAVIORS)
            and not isinstance(m.behavior, LauncherBehavior)
        ]
        if not behavior.targets:
            return apps
        by_name = {m.name: m for m in apps}
        chosen = []
        for name in behavior.targets:
            target = by_name.get(name)
            if target is None:
                log.warning("launcher: no app named %r - skipped", name)
            else:
                chosen.append(target)
        return chosen

    async def run_launcher(behavior, mode_name: str):
        """Cycle the installed apps and hand one over.

        Returns `(result, chosen)` because it is the one run_* whose job is to
        name what runs next. The caller closes this session *before* opening
        the chosen app's - the "replace, don't nest" rule.

        Short press cycles, **double tap launches, long press leaves**. Fixed
        rather than configurable: this is the one mode whose controls someone
        has to be able to guess. Long press is *out*, never *in* - a launcher
        that launched on the universal escape gesture would be the one place it
        committed you to something instead (CLAUDE.md).
        """
        apps = launcher_targets(behavior)
        if not apps:
            return ActionResult(False, "launcher: no apps to offer"), None

        index = 0

        def show() -> None:
            target = apps[index]
            # LISTENING is honest - the button is waiting for you to choose -
            # and the app's own look is pushed over it, so the state only
            # matters to the status line and to a device too old for effects.
            set_led(LEDState.LISTENING, app_look(target))
            status.last_message = f"{target.name} ({index + 1}/{len(apps)})"

        show()
        set_status("LAUNCHER")
        status.last_mode = mode_name

        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"launcher (demo: {len(apps)} apps)"), None

        while True:
            trigger = await _wait_for_trigger(device.events, stop)
            if trigger is None:  # shutting down mid-choice
                return ActionResult(True, "launcher closed (shutdown)"), None
            if trigger is TriggerType.DOUBLE_TAP:
                chosen = apps[index]
                if behavior.log_as:
                    store.log_event(behavior.log_as, mode=mode_name)
                return ActionResult(True, f"launching {chosen.name}"), chosen
            if trigger is TriggerType.LONG_PRESS:
                return ActionResult(True, "launcher closed"), None
            index = (index + 1) % len(apps)
            show()

    async def enter_takeover(mode) -> None:
        """Run a takeover mode, then drop back to the ambient layer (IDLE).

        **Replace, don't nest** (TODO 0a). A launcher names the app that runs
        next and this loop closes the launcher's session before opening the
        app's, so a takeover starting another takeover is a *sequence*, never a
        stack. That beats a depth guard: no stack means no depth to overflow,
        the event log gets one clean mode_enter/mode_exit pair per app, and
        leaving an app returns you to where you actually are rather than to a
        menu you had forgotten was underneath it.

        No hop limit, deliberately: every handoff costs a press, so no chain
        runs without someone driving it - and the one shape that *could* spin
        unattended, a launcher offering itself, is excluded in
        `launcher_targets` instead.

        Exception-guarded so a handler bug never kills the main loop.
        """
        nonlocal active_mode
        play_sound(Sound.ACK)
        status.last_trigger = None
        # Set when a launcher hands off and wants the button back afterwards.
        # Cleared as soon as it is used, so "return to the launcher" happens
        # once rather than becoming a trap you have to escape twice.
        return_to = None

        while mode is not None:
            status.last_mode = mode.name
            log.info("entering takeover mode %r (%s)", mode.name, mode.template)
            entered_at = store.log_mode_enter(mode.name)
            # Set before dispatch so the first set_led inside the loop already
            # wears this mode's look, and cleared after so the ambient layer's
            # IDLE below is the palette's again.
            active_mode = mode
            # Before the loop starts, after the mode_enter row exists: a hook
            # that posts "I am in focus mode" must not be able to arrive ahead
            # of the row that says so.
            spawn_hook(mode, "on_enter")
            chosen = None
            try:
                if isinstance(mode.behavior, LauncherBehavior):
                    result, chosen = await run_launcher(mode.behavior, mode.name)
                elif isinstance(mode.behavior, AlarmBehavior):
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
                elif isinstance(mode.behavior, HotColdBehavior):
                    result = await run_hotcold(mode.behavior, mode.name)
                elif isinstance(mode.behavior, ReactionBehavior):
                    result = await run_reaction(mode.behavior, mode.name)
                elif isinstance(mode.behavior, ControlBehavior):
                    result, chosen = await run_control(mode.behavior, mode.name)
                elif isinstance(mode.behavior, SignalBehavior):
                    result = await run_signal(mode.behavior, mode.name)
                else:
                    result = ActionResult(
                        False, f"mode {mode.name!r} is not a takeover mode"
                    )
            except Exception as exc:  # a takeover bug must never kill the loop
                log.exception("takeover %r crashed", mode.name)
                result = ActionResult(False, f"internal error: {exc}")
                chosen = None
            store.log_mode_exit(mode.name, entered_at)
            # After the session row is closed and before the handoff below, so
            # a launcher's chain fires each app's exit hook before the next
            # app's enter hook, in the order they actually happened. The app's
            # own numbers ride out with it (summary.py); an app with nothing to
            # report passes None.
            await fire_hook(mode, "on_exit", result.summary)
            active_mode = None
            status.last_ok = result.ok
            status.last_message = result.message

            if chosen is not None:
                if mode.behavior.return_after:
                    return_to = mode
                mode = chosen
            else:
                mode, return_to = return_to, None

        set_led(LEDState.IDLE)
        set_status("IDLE")

    async def handle(trigger: TriggerType) -> None:
        nonlocal standby
        resolved = resolve(
            cm.config.modes, trigger.value, clock.now(), logged_today=store.logged_today
        )
        # A binding may name a pooled action rather than hold one
        # (config.NamedAction). Undone here, once, before anything below asks
        # what kind of action it is.
        action = resolve_action(cm.config, resolved[1]) if resolved is not None else None

        if standby and not isinstance(action, StandbyAction):
            # Asleep: the ambient layer answers nothing and does not let on
            # that it was asked - no ack, no light, no event, no status line
            # moving. The one gesture that still lands is the one that can undo
            # this, because a standby only a restart could leave would be a
            # button that looks broken.
            log.debug("standby: %s ignored", trigger.value)
            return

        play_sound(Sound.ACK)
        set_led(LEDState.LISTENING)
        set_status("THINKING")
        status.last_trigger = trigger.value
        if resolved is None:
            status.last_mode = None
            await fail(f"no mode matches {trigger.value} right now")
        elif action is None:
            # A binding naming a pool entry that is not there. The parser
            # warned at load; this is the same fact at the moment it costs you
            # something, failing the way a missing enter_mode target does.
            status.last_mode = resolved[0].name
            await fail(f"no action named {resolved[1].name!r}")
        elif isinstance(action, StandbyAction):
            # Handled here rather than in execute() for the reason enter_mode
            # and readout are: it changes what the *loop* does with the next
            # gesture, and that is state only the loop owns.
            standby = not standby
            status.last_mode = resolved[0].name
            status.last_ok = True
            status.last_message = (
                "standby - the ambient layer is asleep"
                if standby else "awake - the ambient layer is answering again"
            )
            log.info("standby %s", "on" if standby else "off")
            # No explicit look either way: set_led already knows what IDLE
            # means while asleep, so the same call dims it and undims it.
            set_led(LEDState.IDLE)
            set_status("STANDBY" if standby else "IDLE")
            return
        elif isinstance(action, EnterModeAction):
            # A gesture starting a takeover: look the target up by name and
            # hand off to enter_takeover, which owns the LED/sound/status and
            # the IDLE drop. EnterModeAction is never passed to execute(). A
            # missing or non-takeover target fails clearly instead of crashing
            # - the parser deliberately does not pre-validate targets.
            mode = resolved[0]
            status.last_mode = mode.name
            target = next(
                (m for m in cm.config.modes if m.name == action.target), None
            )
            if target is not None and isinstance(
                target.behavior, TAKEOVER_BEHAVIORS
            ):
                await enter_takeover(target)
            else:
                await fail(f"enter_mode: no takeover mode named {action.target!r}")
            return
        elif isinstance(action, ReadoutAction):
            # A readout's light *is* its feedback (TODO 15/17), so it must not
            # be wrapped in the SUCCESS flash the generic branch below plays:
            # `set_led` cancels the running sequence on every call, so a
            # SUCCESS push after this would cut the readout off mid-count.
            # Hence never handed to execute(), and an immediate return rather
            # than falling into the shared SUCCESS/IDLE tail.
            mode = resolved[0]
            status.last_mode = mode.name
            count = store.count_today(action.event)
            set_led(
                LEDState.IDLE,
                sequencer.readout(count, action.tens_color, action.units_color),
            )
            status.last_ok = True
            status.last_message = f"{action.event}: {count} today"
            set_status("IDLE")
            log.info("readout %s -> %d today", action.event, count)
            return
        else:
            mode = resolved[0]
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
    # The palette last sent to the device. Editing colours in the web UI (or a
    # SIGHUP) replaces cm.config wholesale, so the tick below notices and
    # re-sends - which is why a colour picker updates the real LED live.
    pushed_palette = cm.config.led_palette
    # The look IDLE was last *shown* wearing, for the same reason and the layer
    # above it: a state may name a look now (TODO 36a), and a named look is
    # resolved when it is asserted rather than pushed like the palette. Without
    # this, editing IDLE's look and saving changed nothing anybody could see
    # until the next press - which is indistinguishable from the feature not
    # working, and was reported as exactly that.
    #
    # IDLE alone, deliberately. It is the only state the ambient layer *rests*
    # in, so it is the only one an edit can sit in front of; the rest are
    # transient and get repainted by the very next press. Reaching this line
    # also means no takeover owns the button - a takeover is awaited inside
    # `handle` and this loop is not running while one is.
    shown_idle_look = look_for(cm.config, None, LEDState.IDLE)
    # Nothing inside one iteration may end the service. handle() and the
    # takeover loops guard their own bodies; this is the backstop for the rest
    # of an iteration - the store, the scheduler scan, the palette push -
    # because a button that dies on a locked database is worse than one that
    # misses a press.
    faults = FaultTracker()

    try:
        if args.demo:
            for trigger in TriggerType:
                log.info("--- demo: %s ---", trigger.value)
                await handle(trigger)
            return

        log.info("AI Button ready (config: %s, %d mode(s))", cm.path, len(cm.config.modes))
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
                # The layer above the palette, hot-reloaded the same way: an
                # asserted look has to be re-asserted, since nothing on the
                # device is holding a copy of it to re-render.
                if (idle_look := look_for(cm.config, None, LEDState.IDLE)) != shown_idle_look:
                    shown_idle_look = idle_look
                    if status.led_state == LEDState.IDLE.value:
                        set_led(LEDState.IDLE)
                        log.info("the idle look changed - shown now")
                # Binding (or unbinding) a long tap changes how far the device
                # counts, so this rides the same hot-reload path the palette
                # does rather than waiting for a restart.
                if (max_taps := wanted_max_taps()) != device.max_taps:
                    device.set_gesture_config(max_taps)
                    log.info("gestures changed - device now counts %d taps", max_taps)
                # After every wait (press or tick), ring whatever is due now;
                # an alarm preempts the ambient layer. `fired` is pruned to
                # today's keys so it never grows without bound across days,
                # matching the trailing "@<date>T<HH:MM>" structurally so a
                # mode name that embeds a date can't keep a stale key alive.
                now = clock.now()
                today_prefix = now.date().isoformat()
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
        if sequence_task is not None:
            # Not another `set_led` - shutting down never repaints the light,
            # it just stops walking whatever sequence was mid-flight so the
            # task does not outlive `run()` and trip a loop-closed warning.
            sequence_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sequence_task
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
