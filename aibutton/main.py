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
import functools
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

# What IDLE looks like while the ambient layer is asleep (config.StandbyAction,
# and the long press at the root - TODO 104). **Off, not dimmed.** A dim ember
# was tried first, on the argument that "asleep" and "unplugged" have to look
# different; the owner's answer is that sleep means dark, and the difference is
# carried by _SLEEP_FADE_S below instead - you *watch* it go out, which nothing
# broken does. Solid black rather than no effect at all, because "no effect"
# means the palette's own IDLE entry and that is the light being asked for.
_STANDBY_COLOR = "#000000"
# How long the light takes to go down. Going to sleep is *watched* - it is a
# deliberate gesture and the thing it does is make the button stop answering,
# so a snap to dark would be indistinguishable from the crash it most resembles
# (ROADMAP 29: off must be distinguishable from broken). Coming back is a cut,
# not a fade: a wake should feel like an answer, not an entrance.
_SLEEP_FADE_S = 1.0

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

# How many inbound reflexes may be waiting at once (TODO 71). Bounded because
# the thing filling this queue is an HTTP handler that must never block on the
# run loop, and because a reflex arriving while an app owns the button waits
# for it - a script in a loop could otherwise queue an hour of them. Full means
# the newest is dropped and said so, which is the same answer the radio gives.
_INBOUND_MAX = 16

# How long before a MIDI input port that would not open is tried again. The
# ports here are virtual cables owned by other software, so "not there" is a
# normal state that ends when a DAW or loopMIDI starts - but a retry per tick
# would be a warning a second, so this paces it.
_MIDI_RETRY_S = 15.0

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
# The same wake-up rate for a running Pomodoro block (TODO 19c). Shared value,
# separate name: they are the same *decision* - "about once a second is enough
# for a colour that walks over minutes" - reached for two different loops, and
# a Pomodoro that wanted a different cadence should be able to have one without
# editing the countdown's.
_POMODORO_TICK_S = 1.0
# The floor on a block's span when it is used as a denominator. A zero-length
# block is not configurable (`duration` refuses <= 0) but `restart` and demo
# mode can both land here, and a fraction is not worth a ZeroDivisionError.
_POMODORO_MIN_SPAN_S = 0.05

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


async def _wait_for_press_or_reflex(
    presses: asyncio.Queue, inbound: asyncio.Queue, stop: asyncio.Event,
    timeout: float | None = None,
):
    """The main loop's wait: the next press, the next inbound reflex, a tick,
    or shutdown.

    **Two queues rather than one**, and a reflex is never injected into the
    press queue: an app that cannot tell a press from the world is an app that
    will lie in its log (TODO 71). `wait_in_app` is the same wait made from
    inside a takeover (TODO 74), which is how a reflex reaches a running app.

    Returns `("press", TriggerType)`, `("reflex", name)`, or None for a tick or
    a shutdown, which the caller tells apart via `stop.is_set()` - the same
    contract `_wait_for_trigger` has.
    """
    press = asyncio.create_task(presses.get())
    reflex = asyncio.create_task(inbound.get())
    stop_task = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {press, reflex, stop_task}, timeout=timeout,
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    # A press wins a tie, because someone is standing there. Whichever getter
    # also finished has already taken its item off its queue, so it is put back
    # rather than dropped - cancelling a task that is already done does not
    # undo the get.
    if press in done:
        if reflex in done:
            inbound.put_nowait(reflex.result())  # room: we just took one out
        return "press", press.result()
    if reflex in done:
        return "reflex", reflex.result()
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


async def run(
    args: argparse.Namespace,
    device: ButtonDevice | None = None,
    inbound: asyncio.Queue | None = None,
) -> None:
    """Drive the button until `stop` fires. `device` is the hardware seam:
    --ble picks the real ESP32, otherwise the in-memory MockDevice, and
    tests inject their own. Nothing past this point knows the difference.

    `inbound` is the same seam for circumstances rather than presses (TODO
    71): the web endpoint fills the one made here, and a test hands in its own
    so it can post a reflex without standing up a web server."""
    from . import midi, midi_io
    from .actions import ActionResult, _fmt_elapsed, execute
    from .audio import ToneLibrary
    from .config import (
        MODE_LED_STATES,
        ConfigManager,
        ControlBehavior,
        CountdownBehavior,
        CounterBehavior,
        EnterModeAction,
        HotColdBehavior,
        LauncherBehavior,
        LedEffect,
        LightShowBehavior,
        MetronomeBehavior,
        NoticeBehavior,
        SetPositionAction,
        PomodoroBehavior,
        ReactionBehavior,
        ReadoutAction,
        SignalBehavior,
        StandbyAction,
        StopwatchBehavior,
        blank_midi_ports,
        bound_triggers,
        flash_safe,
        look_for,
        position_reporters,
        reflex_hears,
        reflex_matches,
        resolve_action,
        sequence_safe,
    )
    from .rules import resolve
    from .scheduler import due_alarm
    from .documents import DocumentStore
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
    # An app's durable named values, in the same file as the log and a table
    # of its own (TODO 34). History and current value are different jobs, so
    # they are different tables rather than one clever query.
    documents = DocumentStore(cm.config.database_path)

    # Every action runs through this rather than through `execute` directly.
    # The two stores an action may write are bound **once**, here, because
    # there are seven dispatch sites and the eighth is the one that would
    # forget `documents` and then silently do nothing - the same reasoning
    # `resolve_action` uses for being one function rather than seven inlines.
    run_action = functools.partial(execute, store=store, documents=documents)

    # A `midi` action with no port goes to output 0, which on Windows is the
    # built-in synth - so the DAW hears nothing and nothing has failed. The
    # editor's half of this shipped as a basic-tier field with a hint; this is
    # the half that reaches a file somebody edited by hand. At load, once,
    # because that is when a config becomes the thing the button is running.
    try:
        blanks = blank_midi_ports(cm.config, midi_io.ports())
    except Exception as exc:  # noqa: BLE001 - no backend, no question to answer
        log.debug("cannot list MIDI outputs to check for blank ports (%s)", exc)
    else:
        for where in blanks:
            log.warning(
                "%s sends MIDI with no port set - that means the first output "
                "on this machine, which is rarely the one you meant", where,
            )

    class Lighting:
        """Owns the button's light and sound: `set_led` and everything built
        on it. Used to be a dozen closures here sharing `active_mode`/
        `standby`/`sequence_task` by `nonlocal`; now one object, so the
        run_* loops below share an instance instead of forty closures. A
        medium-term SRP pass on `run()` (an owner audit found this the one
        real violation in the file) - the run_* loops themselves are
        unchanged and stay exactly where CLAUDE.md says they belong."""

        def __init__(self, device: ButtonDevice, cm: ConfigManager, status: DeviceStatus):
            self.device = device
            self.cm = cm
            self.status = status
            # The takeover mode that currently owns the button, if any. Kept
            # here so `set_led` can find the look it wears without every
            # run_* loop having to be handed its own Mode and pass it along
            # on every call. Set from outside (fire_alarm, enter_takeover)
            # via this attribute now, in place of the old `nonlocal`.
            self.active_mode = None
            # Whether the ambient layer is asleep (config.StandbyAction).
            # Session state on purpose: an "off" that outlived a restart
            # would be a button that comes back dead with nothing on it to
            # say why. Toggled from `handle()` via this attribute.
            self.standby = False
            # The task walking a Sequence look's planner, if one is running -
            # see `_drive_sequence`. Cancelled by `set_led` before it does
            # anything else, which is what makes a sequence last "until the
            # next state change" exactly like an ephemeral effect: nothing
            # downstream has to know one was involved.
            self.sequence_task: asyncio.Task | None = None

        def standby_look(self, state: LEDState):
            """The dark IDLE wears while the ambient layer is asleep, or None
            for "whatever this state normally wears".

            One definition with two callers - `set_led` substitutes it and
            `_drive_sequence` lands a finished one-shot on it - because "what
            does asleep look like" answered in two places is the drift CLAUDE.md
            names about floors, one layer up.
            """
            if self.standby and state is LEDState.IDLE:
                return LedEffect(style="solid", color=_STANDBY_COLOR)
            return None

        def set_standby(self, asleep: bool) -> None:
            """Put the ambient layer to sleep, or wake it, and show the change
            (TODO 104).

            **Going down is visible**: a one-shot fade from whatever IDLE is
            wearing to black. A one-shot fades from black by construction
            (`sequencer.Sequence`), so the first stop is a hard cut to where the
            light already is and the second is the movement - two stops, which
            is inside `sequence_safe`'s one-shot exemption, so the fade is not
            floored into a jump.

            **The flag flips after the push, and that is load-bearing**:
            `set_led` substitutes the dark for anything IDLE wears while
            `standby` is true, so setting it first would replace this fade with
            the very colour it is fading to. Nothing can arrive in between -
            there is no await here - and `_drive_sequence` reads the flag when
            the fade *ends*, which is when it should be true.
            """
            if not asleep:
                self.standby = False
                self.set_led(LEDState.IDLE)
                self.set_status("IDLE")
                return
            base = self.base_look(LEDState.IDLE)
            self.set_led(LEDState.IDLE, sequencer.Sequence(
                stops=(
                    sequencer.Stop(
                        color=getattr(base, "color", None) or _STANDBY_COLOR,
                        hold_s=0.0, fade_s=0.0,
                    ),
                    sequencer.Stop(
                        color=_STANDBY_COLOR, hold_s=0.0,
                        fade_s=_SLEEP_FADE_S, curve="ease_in",
                    ),
                ),
                repeat=False,
            ))
            self.standby = True
            self.set_status("STANDBY")

        async def _drive_sequence(self, state: LEDState, seq: sequencer.Sequence) -> None:
            """Walk `seq`'s planner, pushing each frame as a plain solid
            `LedEffect` - never a Sequence itself, since `device.set_led`
            duck-types its `effect` on `.style`/`.color`/`.color2`/`.period_s`
            (device.py). Solid is the only thing a frame can be: a stop is a flat
            colour, and the movement is the walk between them.

            Pushes go straight through `self.device.set_led`, *not* through
            `self.set_led`: that method cancels this very task on every
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
                    # Unless the layer is asleep, where the palette's IDLE is the
                    # bright light this one-shot has just faded out of (TODO 104):
                    # dark is what IDLE *means* then, so landing anywhere else
                    # would undo the fade at the moment it finished.
                    resting = self.standby_look(state)
                    self.device.set_led(state, resting)
                    self.status.led_state = state.value
                    self.status.led_effect = resting
                    return
                effect = LedEffect(style="solid", color=frame.color)
                self.device.set_led(state, effect)
                self.status.led_state = state.value
                self.status.led_effect = effect
                await asyncio.sleep(wait if wait and wait > 0 else _SEQUENCE_MIN_STEP_S)

        def set_led(self, state: LEDState, effect=None):
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
            if self.sequence_task is not None:
                self.sequence_task.cancel()
                self.sequence_task = None

            if effect is None:
                effect = look_for(self.cm.config, self.active_mode, state)
            if (dozing := self.standby_look(state)) is not None:
                # Standby dims the *resting* light and only that: it is the ambient
                # layer that is asleep, and an alarm ringing through a standby must
                # still look like an alarm. Substituted here, where a mode's own
                # look is, rather than at each of the several places that drop back
                # to IDLE - those would drift. It wins over whatever IDLE would
                # otherwise wear, a named look included (TODO 36a): "asleep" is the
                # one thing this light has to say, and a configured IDLE look is
                # exactly what would hide it. Nothing reachable pushes an explicit
                # IDLE effect while asleep - the readout is ambient, so `handle`'s
                # gate turned it away already, and `set_standby` starts its fade
                # while the flag is still down for exactly this reason.
                effect = dozing

            if isinstance(effect, sequencer.Sequence):
                # THE ONE GATE for a sequence's floor, mirroring flash_safe just
                # below for a plain effect - see config.sequence_safe. Nothing
                # else may call sequence_safe; a second call site is a second
                # floor with its own chance to drift from this one.
                floored = sequence_safe(effect, self.cm.config.min_flash_period_s)
                self.sequence_task = asyncio.create_task(self._drive_sequence(state, floored))
                # The task pushes its first frame on the next loop iteration, not
                # synchronously - set_led stays non-blocking either way. The state
                # is already known, though, so the status line need not wait.
                self.status.led_state = state.value
                return floored

            # The one gate every pushed look passes through, which is why the floor
            # lives here rather than in each run_* loop: a mode computing its own
            # effect (the metronome's period, the countdown's colour) cannot route
            # around it, and neither can a look hand-edited into a scene file. The
            # palette's own entries are floored in push_palette instead.
            effect = flash_safe(effect, self.cm.config.min_flash_period_s)
            self.device.set_led(state, effect)
            self.status.led_state = state.value
            self.status.led_effect = effect
            return effect

        def show_look(self, state: LEDState, look):
            """Show one look now on behalf of the web UI's colour pickers, and
            answer with what actually went out.

            A thin wrapper rather than the endpoint calling `device.set_led`
            itself, and the thinness is the point: a stop list is a *schedule*, so
            previewing one needs the cancellable task and the `sequence_safe` gate
            that only this method owns. The endpoint used to have neither, which
            is why "Show on the button" could only ever flash a sequence's first
            colour - the one thing about a sequence that is not the sequence.

            `look=None` means "back to the configured colours", which is already
            what `set_led` does with no effect: it re-resolves the state's own
            look, cancelling any preview still playing.

            **Assumes the host is awake and connected**, like everything else that
            drives the light from here (CLAUDE.md).
            """
            return self.set_led(state, look)

        def push_palette(self, palette: dict) -> None:
            """Send the stored palette, floored. Separate from `set_led` because
            the device renders these entries unasked when no effect overrides them,
            so a strobing palette entry would never pass that gate."""
            self.device.set_palette(
                {
                    name: flash_safe(entry, self.cm.config.min_flash_period_s)
                    for name, entry in palette.items()
                }
            )

        def base_look(self, state: LEDState):
            """The look a mode should build its live effect on top of - its own if
            it has one, the palette entry otherwise. What `run_countdown` walks the
            colour of, and what `run_metronome` rewrites the period of.

            A stop-list look falls back to the palette entry, exactly like a mode
            that named nothing: the *derived, host-animated* effects this function
            feeds (a ramp, a beat pulse, a ladder tick) need a style and a period
            to modify, which a schedule is not. `set_led` still renders a sequence
            directly wherever a mode's look is used as-is.
            """
            look = look_for(self.cm.config, self.active_mode, state)
            if isinstance(look, sequencer.Sequence):
                look = None
            return look or self.cm.config.led_palette.get(state.value)

        def driven_look(self, state: LEDState, drive: str):
            """The active mode's look for `state`, if it is a stop list this app
            can drive (TODO 36d). None otherwise, including for a plain effect.

            The counterpart of `base_look`: that one asks "what do I animate on top
            of", this one "did someone hand me a schedule to sample". A run loop
            that owns a number - a countdown's progress, a metronome's beat - asks
            this first and falls back to its own ramp or ladder.
            """
            look = look_for(self.cm.config, self.active_mode, state)
            if isinstance(look, sequencer.Sequence) and look.drive == drive:
                return look
            return None

        def sampled_paint(self, state: LEDState, seq: sequencer.Sequence):
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
                self.set_led(state, LedEffect(style="solid", color=frame.color))

            return paint

        def ladder_paint(self, spec, state: LEDState):
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
            tick = max(spec.tick_s, self.cm.config.min_flash_period_s)
            shown: str | None = None

            def paint(seconds: float) -> None:
                nonlocal shown
                index = ladder.tick_index(seconds, tick)
                colour = ladder.color_for_tick(spec.rungs, index, tick, spec.base)
                if colour == shown:
                    return
                base = self.base_look(state)
                if base is None:
                    return
                shown = colour
                # `solid` because the ladder *is* the animation - the tick supplies
                # the rhythm, so asking the device to also flash inside each tick
                # would be two clocks on one light.
                self.set_led(state, replace(base, style="solid", color=colour))

            return paint, tick

        def play_sound(self, sound: Sound) -> None:
            """Feedback tone + the web UI's mirror of it. sounds_enabled is read
            per press, so muting the button takes effect on the next reload."""
            if not self.cm.config.sounds_enabled:
                return
            self.device.play_sound(sound)
            self.status.last_sound = sound.value
            self.status.sound_seq += 1

        def start_loop(self, sound: Sound) -> None:
            if not self.cm.config.sounds_enabled:
                return
            self.device.start_loop(sound)
            self.status.last_sound = sound.value
            self.status.sound_seq += 1

        def stop_loop(self) -> None:
            self.device.stop_loop()

        def set_status(self, state: str) -> None:
            self.status.state = state

    lighting = Lighting(device, cm, status)
    # Aliased to the bare names every run_* loop below already calls, rather
    # than rewriting ~150 call sites to `lighting.set_led(...)` etc. - this
    # extraction is about giving the state one owner, not about how it reads
    # at each call site. Touch a call site for another reason and either
    # spelling is fine; both mean the same bound method.
    push_palette = lighting.push_palette
    set_led = lighting.set_led
    show_look = lighting.show_look
    base_look = lighting.base_look
    driven_look = lighting.driven_look
    sampled_paint = lighting.sampled_paint
    ladder_paint = lighting.ladder_paint
    play_sound = lighting.play_sound
    start_loop = lighting.start_loop
    stop_loop = lighting.stop_loop
    set_status = lighting.set_status

    # Deferred until push_palette exists rather than pushed raw at connect
    # time: the very first palette the button sees has to be inside the floor
    # too. Nothing between here and device.start() reads the palette.
    push_palette(cm.config.led_palette)

    set_led(LEDState.IDLE)

    # Created before the web UI so the stop endpoint can be handed the same
    # event the signal handlers below set - one shutdown path, three ways in.
    stop = asyncio.Event()

    # Inbound circumstances waiting to be dispatched (TODO 71). Filled by
    # anything that can reach the service - today `POST /api/reflex/{name}` -
    # and drained by the run loop beside the device's presses.
    if inbound is None:
        inbound = asyncio.Queue(maxsize=_INBOUND_MAX)

    def fire_reflex(name: str, payload=None) -> bool:
        """Queue a reflex for the run loop; False if there was no room.

        Synchronous and non-blocking, for the reason `set_led` is: the caller
        is a web handler on this same loop, and a circumstance that waits on
        the button is a circumstance that can hang the thing reporting it.

        `payload` is whatever arrived with it - the posted JSON body - carried
        untouched so the *loop* decides whether it matches (TODO 72). The
        endpoint queues; one place evaluates.
        """
        try:
            inbound.put_nowait((name, payload))
        except asyncio.QueueFull:
            log.warning(
                "reflex %r dropped: %d already waiting", name, inbound.qsize()
            )
            return False
        return True

    class MidiIn:
        """Owns MIDI-in listener lifecycle and turns an arriving message into
        a reflex (TODO 73). Used to be three closures here sharing
        `midi_listeners`/`midi_failed`/`midi_retry_at` by `nonlocal`; now one
        object, for the same reason `Lighting` above is one. `_on_midi` still
        runs on the driver's thread and does nothing but hop onto the event
        loop; `_dispatch_midi` is where every decision is made, exactly as
        before."""

        def __init__(self, cm: ConfigManager, fire_reflex):
            self.cm = cm
            self.fire_reflex = fire_reflex
            # MIDI in, the second source of circumstances (TODO 73). One
            # listener per distinct port any reflex names; the set is
            # re-checked on the tick, so a port that only exists once
            # loopMIDI or the DAW has started is picked up without a
            # restart, and a port that stops being named is closed.
            self.midi_listeners: dict[str, object] = {}
            self.midi_failed: dict[str, str] = {}
            self.midi_retry_at = 0.0

        def _on_midi(self, port: str, status: int, data1: int, data2: int) -> None:
            """One MIDI message, **on the driver's thread**.

            The only safe thing to do here is hand it to the event loop:
            `asyncio.Queue.put_nowait` is not thread-safe and neither is reading
            the live config, so the whole body is the hop. Everything that decides
            anything happens in `_dispatch_midi`, which runs on the loop.
            """
            loop.call_soon_threadsafe(self._dispatch_midi, port, status, data1, data2)

        def _dispatch_midi(self, port: str, status: int, data1: int, data2: int) -> None:
            """What an arriving message means, on the event loop.

            The message becomes a **payload**, and from there a MIDI reflex is an
            ordinary one: the source decided it reached this reflex, and `when`
            decides whether it fires. That is why 73 needed no second comparison
            language - `note 95 velocity 127` is a source plus a test, and note 95
            velocity 0 is the same source and the opposite test (TODO 72).

            `velocity` and `value` are the same number under two names, because a
            DAW's own UI says velocity for a note and value for a CC, and a config
            should be able to say whichever it means.
            """
            decoded = midi.decode(status, data1, data2)
            if decoded is None:
                return  # clock, sysex, active sensing - not ours
            kind, number, value, channel = decoded
            family = "cc" if kind == midi.CONTROL_CHANGE else "note"
            for reflex in self.cm.config.reflexes:
                # The port is this listener's own (one per port), so what is left
                # to ask is whether the message itself is one this reflex hears -
                # a pure question, asked in config.py where it can be tested.
                if reflex.source is None or reflex.source.port != port:
                    continue
                if not reflex_hears(reflex, family, number, channel):
                    continue
                payload = {family: number, "value": value, "channel": channel}
                if family == "note":
                    payload["velocity"] = value
                log.info(
                    "MIDI %s -> reflex %r", midi.describe(kind, channel, number, value),
                    reflex.name,
                )
                self.fire_reflex(reflex.name, payload)

        def sync_midi_listeners(self, now: float) -> None:
            """Open a listener for every port a reflex names, and close the rest.

            Called on the tick as well as at startup, because the ports here are
            virtual cables that come and go with the software at the other end. A
            failure is retried on a slow timer and **logged only when the reason
            changes**, so a port that never appears costs one warning rather than
            one a second.
            """
            wanted = {
                reflex.source.port for reflex in self.cm.config.reflexes
                if reflex.source is not None
            }
            for port in list(self.midi_listeners):
                if port not in wanted:
                    self.midi_listeners.pop(port).stop()
                    self.midi_failed.pop(port, None)
                    log.info("stopped listening for MIDI reflexes on %r", port)
            missing = wanted - set(self.midi_listeners)
            if not missing or now < self.midi_retry_at:
                return
            self.midi_retry_at = now + _MIDI_RETRY_S
            for port in sorted(missing):
                # `p=port` binds the loop variable, so each listener reports the
                # port it was configured with rather than the last one round.
                listener = midi_io.MessageListener(
                    port, lambda status, d1, d2, p=port: self._on_midi(p, status, d1, d2),
                )
                try:
                    where = listener.start()
                except Exception as exc:  # noqa: BLE001 - any failure means no MIDI in
                    message = str(exc)
                    if self.midi_failed.get(port) != message:
                        log.warning(
                            "no MIDI input for reflexes on %r (%s) - retrying",
                            port or "the first input", message,
                        )
                        self.midi_failed[port] = message
                    continue
                self.midi_failed.pop(port, None)
                self.midi_listeners[port] = listener
                log.info("listening for MIDI reflexes on %s", where)

        def close(self) -> None:
            """Stop every listener. Each holds a ctypes callback the driver
            still has the address of, and a callback freed while winmm can
            still reach it takes the process with it (CLAUDE.md) - called
            from `run()`'s shutdown `finally`, before anything else that can
            raise."""
            for listener in self.midi_listeners.values():
                listener.stop()
            self.midi_listeners.clear()

    midi_in = MidiIn(cm, fire_reflex)

    web_server = None
    web_task = None
    if not args.no_web and cm.config.web_enabled:
        try:
            from .webui import WebContext, create_app, make_server

            ctx = WebContext(
                cm=cm,
                store=store,
                # Read-only from the web side (TODO 34): an app's page shows
                # what that app has done and writes nothing back, and a
                # document is written by the button, never by the page.
                documents=documents,
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
                # The one way in for a circumstance nobody pressed. Handed
                # over the same way and for the same reason: the endpoint
                # queues, the loop decides.
                fire_reflex=fire_reflex,
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

    def reminder_look(behavior: NoticeBehavior):
        """What a gentle (non-`urgent`) notice shows on ALERT.

        A named look wins, as everywhere else. With none chosen the fallback is
        *not* the bare ALERT palette entry - that is the urgent look, and a
        reminder indistinguishable from an alarm has failed at the one thing
        it is for. Breathing the same colour reads as "notice me" where the
        urgent hard flash reads as "deal with me", and costs no wire code.
        """
        chosen = look_for(cm.config, lighting.active_mode, LEDState.ALERT)
        if chosen is not None:
            return chosen
        base = cm.config.led_palette.get(LEDState.ALERT.value)
        return None if base is None else replace(
            base, style="breathe", period_s=max(base.period_s, _REMINDER_PERIOD_S)
        )

    async def ring_notice(behavior: NoticeBehavior, mode_name: str) -> ActionResult:
        """The merged alarm/reminder loop (TODO 84): the light goes off until
        the next press clears it, or - on long_press with `snooze_minutes`
        set - goes quiet for that long and fires again, or - if
        `timeout_minutes` is set - gives up on its own. `urgent` decides how:
        loop the alarm tone and hard-flash ALERT, or a single chime and a
        gentle breathe. All waits watch `stop`, so SIGTERM mid-snooze shuts
        down promptly instead of waiting it out.

        Outcome logging is unconditional: cleared logs 1 and missed logs 0
        under `behavior.log_as` (skipped only for the empty string
        `run_countdown`'s "ring on finish" passes, which isn't a real,
        independently-configured notice). `on_cleared`/`on_snoozed`/
        `on_missed` are additional actions on top of that log, not instead of
        it.
        """
        label = behavior.message or behavior.label or mode_name
        verb = "rings" if behavior.urgent else "flashes"
        if args.demo:
            if behavior.urgent:
                set_led(LEDState.ALERT)
                start_loop(Sound.ALARM)
            else:
                set_led(LEDState.ALERT, reminder_look(behavior))
                if behavior.chime:
                    play_sound(Sound.ACK)
            status.last_message = label
            set_status("ALARMING" if behavior.urgent else "REMINDING")
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            if behavior.urgent:
                stop_loop()
            return ActionResult(True, f"{label} (demo: {verb} until dismissed)")

        # Persistence (TODO 44's dead man's switch, generalised): with a
        # timeout set, this is a question with a deadline rather than one
        # that waits forever.
        timeout_s = behavior.timeout_minutes * 60 if behavior.timeout_minutes > 0 else None
        while True:
            if behavior.urgent:
                set_led(LEDState.ALERT)
                start_loop(Sound.ALARM)
            else:
                set_led(LEDState.ALERT, reminder_look(behavior))
                if behavior.chime:
                    play_sound(Sound.ACK)  # once - the light is what persists
            status.last_message = label
            set_status("ALARMING" if behavior.urgent else "REMINDING")
            trigger = await _wait_for_trigger(device.events, stop, timeout_s)
            if behavior.urgent:
                stop_loop()
            if trigger is None and timeout_s is not None and not stop.is_set():
                # Nobody answered. This is the *only* branch that fires
                # on_missed, and it fires once - the notice is over either
                # way, because one that keeps going after raising the alert
                # is just noise on top of the thing it already did.
                set_led(LEDState.IDLE)
                set_status("IDLE")
                late = f"{behavior.timeout_minutes:g} min"
                if behavior.log_as:
                    # Logged on *every* outcome, not only on a clear: a
                    # notice that fires while nobody is watching is only
                    # trustworthy if the record says what happened. value is
                    # numeric: 0 = missed, 1 = cleared - same event name, one
                    # place to look.
                    store.log_event(behavior.log_as, mode=mode_name, value=0)
                action = resolve_action(cm.config, behavior.on_missed)
                if action is None:
                    return ActionResult(True, f"{label} - unanswered after {late}")
                result = await run_action(
                    action, trigger="timeout", mode_name=mode_name,
                )
                log.warning(
                    "notice %r: unanswered after %s - ran %s (%s)",
                    mode_name, late, type(action).__name__, result.message,
                )
                return ActionResult(
                    result.ok, f"{label} - unanswered after {late}: {result.message}"
                )
            if trigger is None:  # shutting down mid-ring
                set_led(LEDState.IDLE)
                return ActionResult(True, f"{label} (interrupted by shutdown)")
            if trigger is TriggerType.LONG_PRESS and behavior.snooze_minutes > 0:
                set_led(LEDState.IDLE)
                set_status("IDLE")
                message = f"{label} - snoozed {behavior.snooze_minutes:g} min"
                action = resolve_action(cm.config, behavior.on_snoozed)
                if action is not None:
                    await run_action(action, trigger="snoozed", mode_name=mode_name)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=behavior.snooze_minutes * 60)
                    return ActionResult(True, message)  # shutting down mid-snooze
                except asyncio.TimeoutError:
                    continue  # snooze elapsed; fires again
            if behavior.log_as:
                # 1 = cleared, matching the 0 the missed branch writes.
                store.log_event(behavior.log_as, mode=mode_name, value=1)
            action = resolve_action(cm.config, behavior.on_cleared)
            if action is not None:
                await run_action(action, trigger="cleared", mode_name=mode_name)
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
            result = await run_action(
                action, trigger=which, mode_name=mode.name, session=carried,
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
        """Run a scheduled mode - a notice's ring or flash - and surface its
        result, then drop back to the ambient layer (IDLE)."""
        play_sound(Sound.ACK)
        status.last_trigger = None
        status.last_mode = mode.name
        log.info("scheduled mode %r firing", mode.name)
        entered_at = store.log_mode_enter(mode.name)
        lighting.active_mode = mode  # so ALERT wears this mode's look, if it has one
        # The other place a mode is entered and left, and hooks fire from both:
        # an alarm the clock started is the same session as one you started by
        # hand.
        spawn_hook(mode, "on_enter")
        try:
            result = await ring_notice(mode.behavior, mode.name)
        except Exception as exc:  # a scheduled-mode bug must never kill the loop
            log.exception("scheduled mode crashed")
            result = ActionResult(False, f"internal error: {exc}")
        store.log_mode_exit(mode.name, entered_at)
        await fire_hook(mode, "on_exit", result.summary)
        lighting.active_mode = None
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

        **`durable` swaps which store that number comes from** (TODO 34), and
        nothing else: off, it is today's rows recounted, which is a habit
        counter and what streaks are built on; on, it is this mode's document,
        which keeps counting past midnight and which `set_value` can write
        from any gesture in any mode - "Smoking +1" without entering the
        Counter (TODO 15). **Rows are written either way**, so history, the
        Events page and the readout do not change at all: what changes is only
        the question the number on the light is answering.

        Reports both numbers it holds (summary.py): `count`, the total, and
        `added`, this session's share of it. A receiver that only ever got the
        first could not tell a busy session from an idle one."""
        event = behavior.event
        # One slot, named in DOC_SLOTS["counter"] - the parser warns about a
        # `set_value` that writes any other one, so this needs no lookup.
        count = (
            documents.get(mode_name, "count", 0.0) if behavior.durable
            else store.count_today(event)
        )
        count = int(count)
        opened_at = count  # what was already there, so `added` can be told
        set_led(LEDState.COUNTING)
        set_status("COUNTING")
        status.last_mode = mode_name
        status.last_message = f"{event}: {count}"

        def tally() -> dict:
            return {"count": count, "added": count - opened_at}

        def bump() -> int:
            """One increment: a row for the history, and - when this counter
            is durable - the document that holds the number. Both, never one:
            the log is what "what happened in March" is asked of, and the
            document is what "what is it now" is asked of."""
            store.log_event(event, mode=mode_name)
            if behavior.durable:
                return int(documents.add(mode_name, "count", 1) or 0)
            return count + 1

        if args.demo:
            count = bump()  # one increment, then out
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
            count = bump()
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
        # How long the current block was given, and the last ramp colour sent.
        # Both exist only for the repainting tick below (TODO 19c).
        phase_span = remaining
        painted: str | None = None
        # A progress-driven stop list, per state: a look is named per state, so
        # WORKING and RESTING are asked separately and either may decline. None
        # when neither names one, which is what keeps the default free.
        sampling = {}
        for phase_state in (LEDState.WORKING, LEDState.RESTING):
            seq = driven_look(phase_state, "progress")
            if seq is not None:
                sampling[phase_state] = sampled_paint(phase_state, seq)

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

        def phase_total() -> float:
            """How long the block currently running was given - the
            denominator of `progress`.

            Kept in step with `extend`, which is the case that makes this a
            variable rather than a lookup of `behavior.work_s`: adding ten
            minutes to a running block makes the block ten minutes longer, so
            the fraction has to be over the longer span. Without that, the
            colour would jump backwards to the start of the ramp the instant
            you extended.
            """
            return max(_POMODORO_MIN_SPAN_S, phase_span)

        def progress() -> float:
            """How far through this block, 0..1.

            **Through the block, not through the session.** A Pomodoro has no
            end to be a fraction of - `rounds` is 0 for the classic one - so
            the block is the only span here that a fraction can mean anything
            over. It resets at every phase change, which is also what makes it
            legible: the colour says how much of *this* block is left.
            """
            done = phase_total() - max(0.0, deadline - loop.time())
            return min(1.0, max(0.0, done / phase_total()))

        def paint_progress() -> None:
            """Repaint the running block's colour for where it has got to.

            Three things can decide it and only one may run: **named stop list
            > ramp**, the ordering CLAUDE.md sets out, one rung shorter than
            `run_countdown`'s because this template has no ladder. A ladder is
            a clock, and a Pomodoro block is not read as a clock.

            Silent when neither is configured, which is the default: a
            Pomodoro that names no look and sets no ramp paints exactly what it
            painted before this existed, on the same two `show()` calls.
            """
            nonlocal painted
            if paused or pending or leading:
                # Not counting, so nothing has moved. `show()` owns the frozen
                # look, and repainting over it would un-freeze it once a second.
                return
            state = LEDState.WORKING if working else LEDState.RESTING
            # Per state, so a Pomodoro may drive its work blocks from a stop
            # list and leave the breaks on a plain colour, or the other way up.
            if state in sampling:
                sampling[state](progress())
                return
            if not behavior.ramp:
                return
            base = base_look(state)
            if base is None:
                return
            # A ramp can only be seen through a style that renders `color` -
            # the same check `run_countdown` makes, and for the same two
            # reasons: under a rainbow it is invisible, and it costs a radio
            # write every time it moves.
            if base.style not in STYLE_USES_COLOR:
                return
            colour = ramp.color_at(behavior.ramp, progress())
            if painted is not None and not ramp.differs(
                painted, colour, _COUNTDOWN_COLOR_STEP
            ):
                return
            painted = colour
            set_led(state, replace(base, color=colour))

        def start_phase(work: bool) -> None:
            nonlocal working, remaining, deadline, paused, pending, leading
            nonlocal phase_span, painted
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
            # A new block is a new fraction: the span it is measured against
            # and the colour already on the light both belong to the old one.
            phase_span = seconds
            painted = None

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
                # Capped at the tick so a running block repaints as it goes -
                # without it a 25-minute block sleeps for 25 minutes and its
                # ramp has nowhere to be walked. Waking is cheap; the colour is
                # only *pushed* when it has visibly moved.
                timeout = max(0.05, min(deadline - loop.time(), _POMODORO_TICK_S))
            paint_progress()
            trigger = await _wait_for_trigger(device.events, stop, timeout=timeout)

            if stop.is_set():
                return summary(" (shutdown)")

            if trigger is None:
                if not (paused or pending) and deadline - loop.time() > 0:
                    # A repaint tick, not the end of anything: the block still
                    # has time on it. Refresh the "x left" line and go round.
                    # `show()` is deliberately not called - it would re-push the
                    # phase's whole effect once a second and undo the colour
                    # `paint_progress` just walked.
                    status.last_message = (
                        f"{mode_name}: {phase_label()}"
                        f" - {_fmt_elapsed(max(0.0, deadline - loop.time()))} left"
                        + (f" ({completed} done)" if completed else "")
                    )
                    continue
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
                # The block itself got longer, so what `progress` is a fraction
                # *of* got longer with it - see `phase_total`.
                phase_span += added
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
        look = look_for(cm.config, lighting.active_mode, LEDState.TIMING)
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
        # A finished countdown *is* a notice going off, so it rings like one
        # rather than growing a second copy of that loop. `log_as=""`
        # deliberately opts this synthetic, internal use out of the
        # unconditional outcome log - it isn't a real, independently
        # configured notice, and the countdown already logged its own finish
        # above.
        return await ring_notice(
            NoticeBehavior(message=f"{label} finished", log_as=""), mode_name,
        )

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

    async def run_lightshow(behavior: LightShowBehavior, mode_name: str) -> ActionResult:
        """A light show: walk a playlist of looks, one cue at a time.

        Short press is the next cue, double tap holds where it is, long press
        leaves - the house rules, with the hold in the slot a Signal uses for
        "say it again", because the one thing you want from a show is to stop
        it on the one you liked.

        **Holding stops the clock, not the light.** The cue underneath keeps
        animating, because a look is a schedule `set_led` is already walking;
        all this loop does is stop asking for the next one. That is also why
        the wait is the *only* timing here - the show never drives a frame.

        A cue naming a look that no longer exists is reported and shown dark
        rather than skipped: the parser already warned about it, the App page
        would call it missing, and silently jumping the cue would make a show
        that is quietly one shorter than the list you are looking at.
        """
        cues = behavior.cues
        if not cues:
            status.last_ok = False
            status.last_message = f"{mode_name}: no cues to show"
            set_led(LEDState.ERROR)
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            set_led(LEDState.IDLE)
            return ActionResult(False, f"{mode_name}: no cues to show")

        index = 0
        held = not behavior.auto
        status.last_mode = mode_name
        set_status("SHOWING")

        def show() -> None:
            cue = cues[index]
            look = (cm.config.looks or {}).get(cue.look)
            if look is None:
                log.warning(
                    "light show %r: cue %d names look %r, which does not exist",
                    mode_name, index + 1, cue.look,
                )
            # None is what set_led already means by "no override", so a missing
            # look falls back to the state's own colour rather than to nothing.
            set_led(LEDState.LISTENING, look)
            where = f"{index + 1}/{len(cues)}"
            status.last_message = (
                f"{cue.look} ({where}){' - held' if held else ''}"
            )
            if behavior.log_as:
                store.log_event(behavior.log_as, mode=mode_name)

        show()
        while True:
            cue = cues[index]
            # Held means no clock: wait for a press with no deadline.
            timeout = None if held else (cue.hold_s or behavior.dwell_s)
            trigger = await _wait_for_trigger(device.events, stop, timeout)
            if trigger is None:
                if stop.is_set():  # shutting down mid-show
                    set_led(LEDState.IDLE)
                    return ActionResult(True, f"{mode_name} (interrupted by shutdown)")
                index = (index + 1) % len(cues)  # the dwell elapsed
                show()
                continue
            if trigger is TriggerType.LONG_PRESS:
                set_led(LEDState.IDLE)
                return ActionResult(True, f"{mode_name} finished")
            if trigger is TriggerType.DOUBLE_TAP:
                held = not held
                show()  # same cue, new status line
                continue
            index = (index + 1) % len(cues)
            show()

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
            result = await run_action(
                action, trigger="signal", mode_name=mode_name,
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
            trigger = await wait_in_app(mode_name)
            if trigger is None:
                return ActionResult(True, f"signal left on {states[index].name} (shutdown)")
            if isinstance(trigger, SetPositionAction):
                # The world says where we are (TODO 74/77). **Shown, not
                # announced**: this position's own action is not fired, for the
                # reason entering does not fire one either - and here it is
                # stronger than politeness, because sending "record" back to
                # the DAW that just told us it is recording is a loop.
                match = next(
                    (i for i, s in enumerate(states) if s.name == trigger.name), None
                )
                if match is None:
                    log.warning(
                        "signal %r: no position named %r", mode_name, trigger.name
                    )
                    status.last_message = f"no position named {trigger.name!r}"
                    continue
                index = match
                state = states[index]
                set_led(LEDState.LISTENING, LedEffect(style=state.style, color=state.color))
                # Logged exactly as a pressed change is: the light was at that
                # position, and how it got there does not change what the log
                # is for. `value` is the index, the same number, so a chart of
                # the day mixes reported and pressed changes without lying
                # about either.
                if behavior.log_as:
                    store.log_event(behavior.log_as, mode=mode_name, value=index)
                status.last_message = f"{state.name} ({index + 1}/{len(states)}, reported)"
                status.last_ok = True
                log.info("signal %r <- %s (reported)", mode_name, state.name)
                continue
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

        **With positions, that resting light is a readout** (TODO 77). A
        reflex - the DAW saying it began recording - hands this loop a
        `SetPositionAction` through `wait_in_app`, and the page wears that
        position's look until something says otherwise. Nothing a finger does
        moves it, which is deliberate: a local toggle is correct until someone
        clicks in the DAW, and then it is silently inverted for the rest of
        the session. Making a *press* depend on the position is TODO 78.

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
        positions = behavior.positions
        index = 0
        # Asked once, on entry, because "it is guessing" is a thing said when
        # the page opens - and because the answer is about the config this
        # session was opened under. A save mid-session replaces cm.config; the
        # next time you open the page it is asked again.
        reporters = position_reporters(cm.config, mode_name) if positions else ()
        guessing = bool(positions) and not reporters

        def resting() -> None:
            """Paint what the surface is showing between commands.

            With no positions this is the state itself, which resolves the
            page's own named look - a remote that always looks the same. With
            positions it is the one the world last reported (TODO 77), and
            **that is the whole rendering change**: a position names a look
            from the pool, a missing or unnamed one falls back to None, and
            None is what `set_led` already means by "no override".
            """
            if not positions:
                set_led(LEDState.LISTENING)
                status.last_message = (
                    f"{mode_name}: {len(behavior.actions)} controls, long press to leave"
                )
                return
            position = positions[index]
            look = (cm.config.looks or {}).get(position.look) if position.look else None
            if position.look and look is None:
                log.warning(
                    "control %r: position %r names look %r, which does not exist",
                    mode_name, position.name, position.look,
                )
            set_led(LEDState.LISTENING, look)
            status.last_message = (
                f"{mode_name}: {position.name} ({index + 1}/{len(positions)})"
                + (" - guessing, nothing reports this" if guessing else "")
            )

        if guessing:
            # Said out loud rather than shown quietly: position one looks
            # identical whether it was reported or assumed, and a transport
            # light that is confidently wrong is worse than one that admits it.
            log.warning(
                "control %r shows positions but no reflex can set one - it is "
                "showing %r without being told", mode_name, positions[0].name,
            )
        resting()
        if args.demo:
            await asyncio.sleep(_SUCCESS_DISPLAY_S)
            return ActionResult(True, f"control (demo: {mode_name})"), None

        while True:
            trigger = await wait_in_app(mode_name)
            if trigger is None:
                return ActionResult(
                    True, f"{mode_name} left ({fired} sent, shutdown)"
                ), None
            if isinstance(trigger, SetPositionAction):
                # The DAW says what it is doing (TODO 74/77). **Shown, not
                # announced**, and here that costs nothing to obey: a control
                # position carries no message of its own, because the gesture
                # map is a separate thing. Nothing goes out - which is the
                # point, since sending "record" back to the thing that just
                # said it was recording is a feedback loop.
                match = next(
                    (i for i, p in enumerate(positions) if p.name == trigger.name), None
                )
                if match is None:
                    log.warning(
                        "control %r: no position named %r", mode_name, trigger.name
                    )
                    status.last_message = f"{mode_name}: no position named {trigger.name!r}"
                    continue
                index = match
                resting()
                # No row, deliberately. `log_as` here means "one command sent",
                # and its readout is a tally of those; a position that arrived
                # is not a command, and counting it as one would inflate the
                # only number this app reports.
                status.last_ok = True
                log.info("control %r <- %s (reported)", mode_name, positions[index].name)
                continue
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
                result = await run_action(
                    action, trigger=trigger.value, mode_name=mode_name,
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
        NoticeBehavior, StopwatchBehavior, CounterBehavior, PomodoroBehavior,
        MetronomeBehavior, CountdownBehavior, LauncherBehavior, HotColdBehavior,
        ReactionBehavior, SignalBehavior, ControlBehavior, LightShowBehavior,
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
            lighting.active_mode = mode
            # Before the loop starts, after the mode_enter row exists: a hook
            # that posts "I am in focus mode" must not be able to arrive ahead
            # of the row that says so.
            spawn_hook(mode, "on_enter")
            chosen = None
            try:
                if isinstance(mode.behavior, LauncherBehavior):
                    result, chosen = await run_launcher(mode.behavior, mode.name)
                elif isinstance(mode.behavior, NoticeBehavior):
                    result = await ring_notice(mode.behavior, mode.name)
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
                elif isinstance(mode.behavior, LightShowBehavior):
                    result = await run_lightshow(mode.behavior, mode.name)
                else:
                    result = ActionResult(
                        False, f"mode {mode.name!r} is not a takeover mode"
                    )
            except Exception as exc:  # a takeover bug must never kill the loop
                log.exception("takeover %r crashed", mode.name)
                result = ActionResult(False, f"internal error: {exc}")
                chosen = None
            store.log_mode_exit(mode.name, entered_at)
            # What the app held aside goes back in the order it arrived (TODO
            # 74). Dropped rather than blocking if the queue has filled while
            # the app ran - the same answer the endpoint gives.
            while deferred:
                held = deferred.pop(0)
                try:
                    inbound.put_nowait(held)
                except asyncio.QueueFull:
                    log.warning("reflex %r dropped: the queue filled while %r ran",
                                held[0], mode.name)
            # After the session row is closed and before the handoff below, so
            # a launcher's chain fires each app's exit hook before the next
            # app's enter hook, in the order they actually happened. The app's
            # own numbers ride out with it (summary.py); an app with nothing to
            # report passes None.
            await fire_hook(mode, "on_exit", result.summary)
            lighting.active_mode = None
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

    def toggle_standby(mode_name: str | None) -> None:
        """Sleep or wake, and say so on the status line. One place, two ways in
        - the long press at the root and a bound `standby` action - because
        they are the same thing happening and a second copy of the wording is a
        second thing to keep true."""
        lighting.set_standby(not lighting.standby)
        status.last_mode = mode_name
        status.last_ok = True
        status.last_message = (
            "asleep - the everyday gestures are off; a long press wakes it"
            if lighting.standby
            else "awake - the everyday gestures are answering again"
        )
        log.info("standby %s", "on" if lighting.standby else "off")

    async def handle(trigger: TriggerType) -> None:
        if trigger is TriggerType.LONG_PRESS:
            # **The root's own gesture** (TODO 104). Long press means "up one
            # level" everywhere, and this is the level with nothing above it -
            # the honest answer to "up" here is off. Answered before anything
            # is resolved because no ambient mode can bind it any more
            # (`_parse_actions_body` drops it): one gesture, one meaning, not a
            # default a config can quietly take away.
            #
            # It runs *ahead of the standby gate below*, which is what makes it
            # the way back as well as the way down. The press is swallowed
            # either way - waking must not also fire whatever it landed on.
            play_sound(Sound.ACK)
            status.last_trigger = trigger.value
            # No LISTENING flash on the way down: the fade is the feedback, and
            # a flash first would be the light getting brighter as it goes out.
            toggle_standby(None)
            return

        resolved = resolve(
            cm.config.modes, trigger.value, clock.now(), logged_today=store.logged_today
        )
        # A binding may name a pooled action rather than hold one
        # (config.NamedAction). Undone here, once, before anything below asks
        # what kind of action it is.
        action = resolve_action(cm.config, resolved[1]) if resolved is not None else None

        if lighting.standby and not isinstance(action, StandbyAction):
            # Asleep: the ambient layer answers nothing and does not let on
            # that it was asked - no ack, no light, no event, no status line
            # moving. What still lands is whatever can undo this, because a
            # standby only a restart could leave would be a button that looks
            # broken: the long press above always, and a bound `standby`
            # action here for a config that spends a gesture on one.
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
            # gesture, and that is state only the loop owns. The long press at
            # the root does the same thing without a binding (TODO 104); this
            # is the same call, so a config that binds `standby` to a five-tap
            # keeps working and looks identical while it does.
            toggle_standby(resolved[0].name)
            return
        elif isinstance(action, SetPositionAction):
            # Reachable only from a config that bound this to a gesture, which
            # the editor does not offer (`appOnly`): a gesture is answered here,
            # at the ambient layer, where by definition no app is running to
            # have a position. Said plainly rather than left to execute()'s
            # "unknown action type", which it is not.
            status.last_mode = resolved[0].name
            await fail(f"set_position {action.name!r}: no app is running")
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
                result = await run_action(
                    action, trigger=trigger.value, mode_name=mode.name,
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

    async def handle_reflex(name: str, payload=None) -> None:
        """One inbound circumstance, dispatched through the action machinery
        that already exists (TODO 71).

        **Deliberately not `handle()`.** Nothing was pressed: there is no
        ambient rule to resolve, no ack tone and no LISTENING flash, because a
        button that lights up as if it were touched is a button lying about
        what happened. What *is* shared is the tail - `enter_mode` goes to
        `enter_takeover` and everything else to `execute()`, the same split
        `run_control` makes, because a mode is not a thing an action primitive
        knows about.
        """
        # **Standby does not mute this**, deliberately: standby puts the
        # *ambient layer* to sleep - it is about presses being answered - and a
        # plant that has gone dry has not stopped meaning it because nobody is
        # at the desk. Revisit only if something asks for a whole-button off.
        reflex = next((r for r in cm.config.reflexes if r.name == name), None)
        if reflex is None:
            # Edited away between the POST and this tick; the endpoint already
            # refuses a name that was never there.
            log.warning("reflex %r is not in the config any more - ignored", name)
            return
        fires, value = reflex_matches(reflex, payload)
        if value is not None:
            # **Logged on arrival, not on firing** (TODO 72): a reading that
            # did not cross the threshold is still a reading, and this column
            # is what turns a moisture sensor into a chart on the Events page.
            # Named after the reflex, because `value` is one untyped slot and
            # everything that reads it groups by name (CLAUDE.md) - one reflex
            # reports one kind of number.
            store.log_event(name, value=value)
        if not fires:
            log.info(
                "reflex %r did not match (%s %s %s, got %s)", name,
                reflex.when.field, reflex.when.op, reflex.when.value,
                "nothing" if value is None else value,
            )
            status.last_message = (
                f"reflex {name}: {reflex.when.field} "
                f"{'is missing' if value is None else value} - no match"
            )
            return
        if reflex.while_app is not None:
            # Scoped to one app, and reaching this line means none is running:
            # while one is, `wait_in_app` takes its own reflexes off the queue
            # before this ever sees them (TODO 74). So a scoped reflex arriving
            # here has missed its app, which is not an error - it is the scope
            # doing exactly what it says.
            running = lighting.active_mode.name if lighting.active_mode is not None else None
            if running != reflex.while_app:
                log.info(
                    "reflex %r skipped: %r is not the running app",
                    name, reflex.while_app,
                )
                status.last_message = f"reflex {name}: {reflex.while_app} is not running"
                return
        # A reflex holds an action or names one, exactly like a gesture - the
        # fifth dispatch site, and the one CLAUDE.md says must call this or the
        # surface silently cannot use the pool.
        action = resolve_action(cm.config, reflex.then)
        status.last_trigger = None
        status.last_mode = None
        log.info(
            "reflex %s -> %s", name,
            type(action).__name__ if action is not None else "nothing",
        )
        if action is None:
            await fail(f"reflex {name!r}: no action named {reflex.then.name!r}")
        elif isinstance(action, SetPositionAction):
            # Only a running app has positions, and reaching this branch means
            # none is running - `wait_in_app` intercepts it when one is. A
            # reflex meant for an app that is not open has simply missed it.
            await fail(
                f"set_position {action.name!r}: no app is running to set it on"
            )
        elif isinstance(action, EnterModeAction):
            target = next(
                (m for m in cm.config.modes if m.name == action.target), None
            )
            if target is not None and isinstance(target.behavior, TAKEOVER_BEHAVIORS):
                # Owns the light and the drop back to IDLE itself, which is why
                # this returns rather than falling into the tail below.
                await enter_takeover(target)
                return
            await fail(f"enter_mode: no takeover mode named {action.target!r}")
        else:
            set_led(LEDState.THINKING)
            try:
                result = await run_action(
                    action, trigger=f"reflex:{name}", mode_name=None,
                )
            except Exception as exc:  # a primitive bug must never kill the loop
                log.exception("reflex action crashed")
                result = ActionResult(False, f"internal error: {exc}")
            if result.ok:
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

    # Reflexes that arrived while an app owned the button and were not
    # addressed to it. Held rather than acted on (a takeover owns the button)
    # and rather than put straight back (which would spin: take, requeue,
    # take), then returned to the queue when the app hands the button back -
    # so an unscoped reflex still fires, just after its turn, exactly as it
    # did before TODO 74.
    deferred: list = []

    async def wait_in_app(mode_name: str, timeout: float | None = None):
        """The wait a takeover makes when it can also receive a reflex (74).

        Returns what `_wait_for_trigger` returns - a `TriggerType`, or None on
        shutdown or timeout - plus one more kind of answer: a `SetPositionAction`,
        when a reflex addressed to *this* app says where it should now be.

        **A reflex reaches a running app only if it names it** (`while`).
        Everything else is a circumstance about the button and the world, and
        the app it interrupted is not the right thing to hand it to.

        Anything else the delivered reflex carries - a webhook, a log - is run
        here rather than handed to the app: it is an ordinary consequence, the
        app has no opinion about it, and running it here keeps the app's light
        alone (no SUCCESS flash over a screen the app owns).

        The timeout is a deadline, not a fresh clock per arrival: a ringing
        alarm's grace period must not be extended by traffic nobody asked for.
        """
        deadline = None if timeout is None else loop.time() + timeout
        while True:
            left = None if deadline is None else max(0.0, deadline - loop.time())
            event = await _wait_for_press_or_reflex(
                device.events, inbound, stop, timeout=left
            )
            if event is None:
                return None
            kind, item = event
            if kind == "press":
                return item
            name, payload = item
            reflex = next((r for r in cm.config.reflexes if r.name == name), None)
            if reflex is None or reflex.while_app != mode_name:
                deferred.append(item)
                continue
            fires, value = reflex_matches(reflex, payload)
            if value is not None:
                # Attributed to the app this time, unlike the top-level row -
                # the reading arrived while that app was running, and the log
                # is the only place that can still say so.
                store.log_event(name, mode=mode_name, value=value)
            if not fires:
                log.info("reflex %r reached %r and did not match", name, mode_name)
                continue
            action = resolve_action(cm.config, reflex.then)
            if isinstance(action, SetPositionAction):
                return action
            if action is None:
                log.warning("reflex %r: no action named %r", name, reflex.then.name)
                continue
            try:
                result = await run_action(
                    action, trigger=f"reflex:{name}", mode_name=mode_name,
                )
            except Exception as exc:  # a primitive bug must never close the app
                log.exception("reflex action crashed inside %r", mode_name)
                result = ActionResult(False, f"internal error: {exc}")
            log.info("reflex %s in %r -> %s", name, mode_name, result.message)


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
                if trigger is TriggerType.LONG_PRESS:
                    # The root's long press is sleep (TODO 104), and a demo that
                    # put itself to sleep would silently swallow every gesture
                    # after it - which is exactly what the demo exists to show.
                    log.info("--- demo: %s (sleep - skipped) ---", trigger.value)
                    continue
                log.info("--- demo: %s ---", trigger.value)
                await handle(trigger)
            return

        log.info("AI Button ready (config: %s, %d mode(s))", cm.path, len(cm.config.modes))
        while not stop.is_set():
            try:
                event = await _wait_for_press_or_reflex(
                    device.events, inbound, stop, timeout=_SCHEDULER_TICK_S
                )
                if stop.is_set():
                    break
                if event is not None and event[0] == "press":
                    await handle(event[1])
                    # Single in-flight action: drop presses made while busy.
                    discarded = 0
                    while not device.events.empty():
                        device.events.get_nowait()
                        discarded += 1
                    if discarded:
                        log.info("discarded %d press(es) made while busy", discarded)
                elif event is not None:
                    # Reflexes are *not* dropped the way presses above are. A
                    # press made while the button was busy is a press whose
                    # moment has passed; a plant reporting that it is dry still
                    # means it, so it waits its turn - bounded by _INBOUND_MAX
                    # so a script in a loop cannot queue an hour of them.
                    await handle_reflex(*event[1])
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
                # A reflex may be fired by MIDI as well as by its URL (TODO
                # 73), and which ports that needs is config the same way the
                # palette is - so it is re-checked here rather than only at
                # startup.
                midi_in.sync_midi_listeners(loop.time())
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
        # Before anything else that can raise: each of these holds a ctypes
        # callback the driver still has the address of, and a callback freed
        # while winmm can still reach it takes the process with it (CLAUDE.md).
        midi_in.close()
        if lighting.sequence_task is not None:
            # Not another `set_led` - shutting down never repaints the light,
            # it just stops walking whatever sequence was mid-flight so the
            # task does not outlive `run()` and trip a loop-closed warning.
            lighting.sequence_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lighting.sequence_task
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
        documents.close()
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
