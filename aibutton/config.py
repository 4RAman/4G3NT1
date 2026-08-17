"""Config loading, validation, and hot-reload for the AI Button.

The config file is `config.json` in the working directory (override with
the AIBUTTON_CONFIG environment variable or the --config CLI flag).

Config errors never crash the service: a missing file, broken JSON, or a
wrongly-typed key is logged loudly and replaced by its safe default. The
merge is per-key; invalid modes/actions are skipped individually.

v0.3 schema - modes
-------------------
"modes" is an ordered list. The button is always in exactly one mode; a
mode is a named personality made of a behaviour *template* plus an
*activation* that decides when it turns on. Template-specific fields are
stored flat on the mode object, mirroring how actions store their fields.

    "modes": [
      { "name": "Default",
        "template": "actions",
        "activation": { "type": "always" },
        "short_press": { "action": "log", "event": "button_press" } },
      { "name": "Morning meds",
        "template": "actions",
        "activation": { "type": "window", "between": ["05:00", "07:00"],
                        "days": ["mon","tue","wed","thu","fri"] },
        "unless_logged_today": "meds_taken",
        "double_tap": { "action": "log", "event": "meds_taken" } },
      { "name": "Wake up",
        "template": "alarm",
        "activation": { "type": "schedule", "at": "07:00",
                        "days": ["mon","tue","wed","thu","fri"] },
        "message": "Wake up", "snooze_minutes": 9, "dismiss_event": "woke_up" }
    ]

Two natures of mode (the template picks the nature):

* **Ambient** (`actions`) - passive; it only *answers* gestures while in
  scope. Pairs with `always`/`window` activations. Resolved first-match-wins
  in config order (see rules.py).
* **Takeover** (`alarm`) - the device *enters* it (a `schedule` fires at a
  clock time) and it owns the button until dismissed (see scheduler.py +
  main.py). The standalone `alarm` *action* of v0.2 is gone - alarms are a
  template now.

Action primitives (the `actions` template body): log (SQLite event),
timer_toggle (start/stop stopwatch pairs), webhook (POST - the
IFTTT/Make/n8n hook), enter_mode (switch to a takeover mode).

v0.4 - scenes
-------------
An optional "scenes" block makes the whole config swappable:

    "scenes": { "dir": "scenes", "active": "focus" }

The named file in that directory is layered over this one *as raw JSON*
before anything below runs (see load_config_full and [scenes.py](scenes.py)),
so a scene is validated by the same parser, with the same per-key fallbacks,
as the config it overrides. No "scenes" block means none of this happens.

Migration / back-compat: legacy v0.2 "rules" configs load and are converted
to ambient `actions` modes (window activation from between/days, else
always). Two removed actions are dropped with a loud warning rather than
silently mangled: `alarm` (a template now, and a rule has no fire time to
synthesise) and `prompt` (the on-device AI is gone - see DESIGN-ESP32.md;
use a webhook). Legacy v0.1 "commands" configs, which are all prompts,
therefore no longer carry anything over. Hot reload via SIGHUP re-reads
every key; the web server's bind address is only read at startup.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import dataclass, field, fields, replace
from datetime import time

from . import ladder, ramp, scenes
from .device import LED_STYLES, SAFE_MIN_PERIOD_S, STYLE_STROBES, LEDState, TriggerType
from .scenes import SceneSettings

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.json"

# Every gesture a mode may bind. Mirrors device.TriggerType, which is the
# vocabulary the wire and the mode machine share - test_config.py fails if the
# two drift. Adding a longer tap here is a data change: the wire has carried a
# tap *count* since protocol v1 (ROADMAP D5), so nothing needs reflashing.
TRIGGER_TYPES = tuple(t.value for t in TriggerType)

_DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # index = datetime.weekday()


# --- action primitives -------------------------------------------------

@dataclass(frozen=True)
class LogAction:
    event: str


@dataclass(frozen=True)
class TimerToggleAction:
    log_as: str


@dataclass(frozen=True)
class WebhookAction:
    url: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EnterModeAction:
    """Switch into the named takeover mode (alarm/stopwatch/counter). This is
    how a gesture in an ambient mode starts a takeover, so "entered by a
    gesture" needs no special activation type - it is simply an action that
    switches modes. The target is resolved at runtime (main.py), not at parse
    time: forward references and config ordering mean the target may be defined
    later in the list, and a missing/non-takeover target is handled gracefully
    by the runtime (fail state, never a crash)."""

    target: str


Action = LogAction | TimerToggleAction | WebhookAction | EnterModeAction


# --- activations -------------------------------------------------------
#
# Tagged by .type in JSON. always/window are ambient; schedule is takeover.

@dataclass(frozen=True)
class AlwaysActivation:
    """The base Default; active whenever nothing else has taken over."""


@dataclass(frozen=True)
class WindowActivation:
    """Active while the wall-clock is inside `between` (may cross midnight,
    e.g. 22:00-06:00) and the weekday is in `days`. At least one of the two
    is present - an empty window would just be `always`."""

    between: tuple[time, time] | None = None
    days: frozenset[int] | None = None  # 0=Mon .. 6=Sun


@dataclass(frozen=True)
class ScheduleActivation:
    """Fires (enters the mode) at clock time `at`, on `days` (or every day
    when days is None)."""

    at: time
    days: frozenset[int] | None = None  # 0=Mon .. 6=Sun


@dataclass(frozen=True)
class ManualActivation:
    """Never auto-activates - the mode is reached only via an enter_mode
    action from another mode. Takeover-only: it is never ambient-resolved
    (rules.py) and never scheduled (scheduler.py)."""


Activation = AlwaysActivation | WindowActivation | ScheduleActivation | ManualActivation


# --- behaviour templates -----------------------------------------------

@dataclass(frozen=True)
class ActionsBehavior:
    """The everyday ambient template: a gesture -> action map, with an
    optional `unless_logged_today` that stands the whole mode down for the
    rest of the day once the named event has been logged."""

    actions: dict[str, Action]  # trigger value -> action
    unless_logged_today: str | None = None

    @property
    def template(self) -> str:
        return "actions"


@dataclass(frozen=True)
class AlarmBehavior:
    """The takeover alarm template: rings (ALERT LED + looping tone) until a
    press dismisses it, or - on long_press with snooze_minutes set - snoozes.
    Handled by main.py's ring loop, not actions.execute(), since ringing
    owns the LED/sound/button-event loop."""

    message: str = ""
    label: str = ""
    snooze_minutes: float = 0  # 0 = long_press dismisses like any other press
    dismiss_event: str = ""  # optional `log` event name written on dismiss

    @property
    def template(self) -> str:
        return "alarm"


def _default_rungs() -> tuple[ladder.Rung, ...]:
    """The ladder someone has to be able to read across a room: white on the
    ten, yellow on the five, light blue on even seconds, dark blue on odd.

    Chosen so the *rate* tells you the unit before you know the code - a
    colour you see twice a minute is obviously the coarse one - and so the two
    most frequent colours are a light/dark pair rather than two hues, which
    survives both this build's warm ring cast (TODO 0c) and a colourblind
    reader.
    """
    return (
        ladder.Rung(10.0, "#ffffff"),
        ladder.Rung(5.0, "#ffff00"),
        ladder.Rung(2.0, "#66ccff"),
        ladder.Rung(1.0, "#0033aa"),
    )


@dataclass(frozen=True)
class LadderSpec:
    """A subdivision ladder plus the cadence it is sampled at.

    Off by default, because it replaces a mode's ordinary look with a clock,
    and that should be something you turn on rather than something that
    happens to you the first time you open a stopwatch.

    It lives on the *behaviour* rather than on a palette entry for the same
    reason a ramp does: a ladder says which colour, not how the light moves,
    so it composes with the look instead of competing with it.
    """

    enabled: bool = False
    tick_s: float = 0.5
    base: str = "#000000"  # ticks landing on no rung; black = a dark off-beat
    rungs: tuple[ladder.Rung, ...] = field(default_factory=_default_rungs)


@dataclass(frozen=True)
class StopwatchBehavior:
    """The takeover stopwatch template: enter starts a timer (logged under
    `log_as`); short_press/double_tap mark a lap; long_press stops and exits.
    Handled by main.py's run_stopwatch loop, not actions.execute(), since it
    owns the LED/sound/button-event loop while running."""

    log_as: str = ""
    # Optional: turn the light into a clock while it runs. Defined here rather
    # than on the palette entry because it is what this *mode* is doing, and
    # because a ladder is not an effect - it says which colour, not how the
    # light moves (same split as ramp).
    ladder: LadderSpec = field(default_factory=LadderSpec)

    @property
    def template(self) -> str:
        return "stopwatch"


@dataclass(frozen=True)
class CounterBehavior:
    """The takeover counter template: enter resets the tally to 0;
    short_press/double_tap logs `event` (so existing count_today/streaks just
    work) and bumps the count; long_press exits. Handled by main.py's
    run_counter loop, not actions.execute()."""

    event: str = ""

    @property
    def template(self) -> str:
        return "counter"


@dataclass(frozen=True)
class PomodoroBehavior:
    """The takeover Pomodoro template: alternating work and break blocks,
    with a long break every `blocks_before_long_break`. Handled by main.py's
    run_pomodoro loop, not actions.execute().

    `advance` is the setting that decides how much the button asks of you:

        auto        both transitions happen on their own
        manual      every transition waits for a gesture
        break_only  breaks start themselves; going back to work is deliberate

    `gestures` maps a trigger to a POMODORO_COMMANDS entry, so what each
    press does is yours to change - the defaults are toggle / exit / extend.
    """

    work_minutes: float = 25
    break_minutes: float = 5
    long_break_minutes: float = 15
    blocks_before_long_break: int = 4
    extend_minutes: float = 10  # what `extend` adds
    advance: str = "auto"
    log_as: str = "pomodoro"  # a completed work block is logged under this
    gestures: dict[str, str] = field(
        default_factory=lambda: {
            "short_press": "toggle",
            "long_press": "exit",
            "double_tap": "extend",
        }
    )

    @property
    def template(self) -> str:
        return "pomodoro"


# What a gesture can be bound to inside a running Pomodoro.
POMODORO_COMMANDS = ("toggle", "restart", "extend", "skip", "exit")
POMODORO_ADVANCE = ("auto", "manual", "break_only")


@dataclass(frozen=True)
class MetronomeBehavior:
    """The takeover metronome template: short_press/double_tap mark a beat,
    long_press exits. Handled by main.py's run_metronome loop, not
    actions.execute().

    The *tempo* remains session state - you tap it in, it is never stored -
    but how the tempo is read, bounded and shown is config:

        start_bpm     what the light pulses at before the first tap lands
        tap_history   how many recent intervals the rolling average spans
        reset_gap_s   a silence this long starts the average over
        max_bpm       the ceiling a tap sequence can register at

    `max_bpm` is about contact bounce, not taste: two edges 20 ms apart imply
    3000 BPM, and without a ceiling one bad press throws the average away.
    Raising it is how this mode goes faster - it is *not* the same limit as
    the LED's flash floor, which is a safety cap the light works around by
    marking every Nth beat (see main.py's run_metronome).
    """

    start_bpm: float = 120.0
    tap_history: int = 8
    reset_gap_s: float = 2.0
    max_bpm: float = 300.0
    sound_on_tap: bool = True
    log_as: str = "metronome"  # a finished session logs its BPM under this

    @property
    def template(self) -> str:
        return "metronome"


def _default_countdown_ramp() -> tuple[ramp.Stop, ...]:
    """Red at the start, walking to violet as the time runs out, then the
    alarm. Warm-to-cool rather than the usual green-to-red: the colour tracks
    *how much is left*, so a full timer is the loud end and the quiet violet is
    the one that means "about to go off"."""
    return ramp.even([
        "#ff0000",  # red
        "#ff8800",  # orange
        "#ffff00",  # yellow
        "#00ff00",  # green
        "#4b0082",  # indigo
        "#8f00ff",  # violet
    ])


@dataclass(frozen=True)
class CountdownBehavior:
    """The takeover countdown template: a fixed run to zero, started by hand,
    with the LED's *colour* walking a ramp as the time goes. Handled by
    main.py's run_countdown loop, not actions.execute().

    Style and colour are separated on purpose. `style`/`period_s` say how the
    light moves (flash, breathe, solid); `ramp` says what colour it is right
    now. That is what makes "set it to flash, but fade the colour over the
    whole timer" one setting each rather than two that fight.

    The ramp is stored here rather than in `led_palette` because it belongs to
    *this* countdown - a five-minute tea timer and a two-hour deadline want
    different colours, and the global palette has one entry per LED state for
    everyone to share. When per-mode looks land (TODO item 3) this is the shape
    they generalise to.
    """

    minutes: float = 10.0
    label: str = ""
    style: str = "flash"  # how the light moves while counting
    period_s: float = 1.0  # ...and how fast, floored for flash safety
    ramp: tuple[ramp.Stop, ...] = field(default_factory=_default_countdown_ramp)
    ring_on_finish: bool = True
    log_as: str = "countdown"  # a finished run logs its length under this
    # Turn the light into a clock instead of a ramp. The two both decide which
    # colour, so only one runs - see run_countdown.
    ladder: LadderSpec = field(default_factory=LadderSpec)

    @property
    def template(self) -> str:
        return "countdown"


@dataclass(frozen=True)
class ReminderBehavior:
    """The scheduled *nudge*: fires on a clock time like an alarm, but flashes
    instead of ringing and clears on any press.

    Why this is its own template rather than a setting on AlarmBehavior: an
    alarm is a thing you have to deal with - it rings until dismissed, and its
    whole design is that it cannot be ignored. A reminder is a thing you should
    notice. Folding them together would mean one dataclass whose fields half
    apply depending on another field, which is the shape that produces "why is
    my snooze doing nothing".

    It owns no new LED state. `ALERT` already means "look at the button", and
    the reminder's *look* is a named look pushed as an ephemeral effect, so a
    reminder is visibly not an alarm without spending a wire code (ROADMAP D4).
    """

    message: str = ""
    label: str = ""
    # A single chime, not a loop. Empty means silent - the point of a reminder
    # over an alarm is that it may be ignorable, and a silent one is a real
    # choice rather than a broken one.
    chime: bool = True
    # Logged when the reminder is cleared. Mirrors `unless_logged_today` one
    # level up: an ambient mode stands down once something is logged today, and
    # this is the scheduled equivalent writing that row.
    cleared_event: str = ""
    # How long it flashes before giving up on its own. 0 = until pressed.
    # A reminder nobody was in the room for should not still be flashing at
    # midnight, which is exactly the way an alarm and a reminder differ.
    timeout_minutes: float = 5.0

    @property
    def template(self) -> str:
        return "reminders"


Behavior = (
    ActionsBehavior | AlarmBehavior | StopwatchBehavior | CounterBehavior
    | PomodoroBehavior | MetronomeBehavior | CountdownBehavior
    | ReminderBehavior
)

# Which activation types each template accepts (per-template allow-list,
# mirroring schema.js's `allowedActivations`). A mode whose activation type is
# not allowed for its template is skipped at parse time with a warning.
_ALLOWED_ACTIVATIONS = {
    "actions": (AlwaysActivation, WindowActivation),
    "alarm": (ScheduleActivation,),
    "reminders": (ScheduleActivation,),
    "stopwatch": (ManualActivation,),
    "counter": (ManualActivation,),
    "pomodoro": (ManualActivation,),
    "metronome": (ManualActivation,),
    # Manual, not schedule: a countdown that starts itself at a clock time is
    # an alarm, and that template already exists.
    "countdown": (ManualActivation,),
}

# Which LED states belong to a *mode* rather than to the button.
#
# The split this encodes: IDLE/LISTENING/THINKING/SUCCESS/ERROR describe what
# the button is doing and are edited once, globally, in the Lights tab. The
# states below describe what a particular mode is doing, so their appearance
# is edited next to the mode - and, since a mode names a look rather than
# owning the global entry, two Pomodoros can finally look different.
#
# Mirrored by `ledStates` on each template descriptor in schema.js;
# test_webui.py fails if they drift.
MODE_LED_STATES: dict[str, tuple[str, ...]] = {
    "actions": (),  # ambient: it never takes the light over
    "alarm": (LEDState.ALERT.value,),
    # Same state as an alarm, deliberately. ALERT means "look at the button";
    # what distinguishes a reminder from a ringing alarm is the look it wears,
    # which is why naming one matters more here than anywhere else - a
    # reminder that picks no look is indistinguishable from an alarm.
    "reminders": (LEDState.ALERT.value,),
    "stopwatch": (LEDState.TIMING.value,),
    "counter": (LEDState.COUNTING.value,),
    "pomodoro": (LEDState.WORKING.value, LEDState.RESTING.value),
    "metronome": (LEDState.METRONOME.value,),
    "countdown": (LEDState.TIMING.value,),
}

# The rest: the button's own vocabulary, which no mode owns.
SYSTEM_LED_STATES: tuple[str, ...] = tuple(
    state.value
    for state in LEDState
    if not any(state.value in states for states in MODE_LED_STATES.values())
)


@dataclass(frozen=True)
class Mode:
    """A named personality: a behaviour template + the activation that turns
    it on. `template` is derived from the behaviour, never stored separately."""

    name: str
    behavior: Behavior
    activation: Activation
    # Which named look this mode wears for each LED state it owns, e.g.
    # {"WORKING": "focus-warm"}. A state left out falls back to the global
    # palette entry, which is what every mode did before looks existed - so an
    # empty map is exactly today's behaviour. Keys are validated against
    # MODE_LED_STATES for the template; values against the config's look pool.
    looks: dict[str, str] = field(default_factory=dict)

    @property
    def template(self) -> str:
        return self.behavior.template


def bound_triggers(modes) -> set[str]:
    """Every gesture name `modes` binds to anything.

    What it is for: counting past two taps costs a double tap its instant
    response (see [button.py](button.py)), so the host tells the device how far
    to count and derives the number from what is actually bound.

    Read off the dataclass fields rather than by asking each behaviour what it
    binds. A behaviour's gesture map is always a dict keyed by trigger name -
    `actions` on the everyday template, `gestures` on Pomodoro - so scanning
    for that shape stays correct for a template nobody has written yet, which
    an isinstance chain per template would not.
    """
    names: set[str] = set()
    for mode in modes:
        for field_ in fields(mode.behavior):
            value = getattr(mode.behavior, field_.name)
            if isinstance(value, dict):
                names |= {key for key in value if key in TRIGGER_TYPES}
    return names


def _default_modes() -> tuple[Mode, ...]:
    """The fail-soft floor: one always-on mode that maps all three gestures
    to primitives needing no setup, so a button with no config (or a broken
    one) still does something legible instead of erroring on every press."""
    return (
        Mode(
            name="Default",
            activation=AlwaysActivation(),
            behavior=ActionsBehavior(
                actions={
                    "short_press": LogAction(event="button_press"),
                    "long_press": TimerToggleAction(log_as="focus"),
                    "double_tap": LogAction(event="note"),
                },
            ),
        ),
    )


# --- LED palette --------------------------------------------------------

@dataclass(frozen=True)
class LedEffect:
    """What one LED state looks like: a style, its colours, and its speed.

    Fields the style ignores are still carried (and edited) so switching
    style back and forth doesn't lose your colours."""

    style: str = "solid"
    color: str = "#0000ff"
    color2: str = "#000000"  # `alternate` and `fade` only
    period_s: float = 1.0


def _default_palette() -> dict[str, LedEffect]:
    """The starting point for edits, and the one definition of these colours:
    the firmware's own table is only a fallback for running with no host."""
    return {
        LEDState.IDLE.value: LedEffect("breathe", "#0000ff", period_s=3.0),
        LEDState.LISTENING.value: LedEffect("solid", "#ffff00"),
        LEDState.THINKING.value: LedEffect("rainbow", "#ffffff", period_s=1.0),
        LEDState.SUCCESS.value: LedEffect("solid", "#00ff00"),
        LEDState.ERROR.value: LedEffect("flash", "#ff0000", period_s=0.4),
        LEDState.ALERT.value: LedEffect("alternate", "#ff0000", "#ffffff", 0.4),
        LEDState.TIMING.value: LedEffect("breathe", "#00ffff", period_s=1.6),
        LEDState.COUNTING.value: LedEffect("breathe", "#ff00ff", period_s=2.2),
        # Slow enough to sit next to you for 25 minutes without nagging.
        LEDState.WORKING.value: LedEffect("breathe", "#ff4400", period_s=5.0),
        LEDState.RESTING.value: LedEffect("breathe", "#00ff88", period_s=5.0),
        # ~120 BPM until a tap sets a real tempo; main.py rewrites period_s live.
        LEDState.METRONOME.value: LedEffect("flash", "#ffaa00", period_s=0.5),
    }


_HEX_DIGITS = set("0123456789abcdef")


def _parse_color(raw, where: str, default: str) -> str:
    """'#rrggbb' (case-insensitive, '#' optional) normalised to lowercase."""
    if isinstance(raw, str):
        text = raw.strip().lstrip("#").lower()
        if len(text) == 6 and set(text) <= _HEX_DIGITS:
            return f"#{text}"
    log.error("config: %s must be a colour like \"#ff8800\" - using %s", where, default)
    return default


def _parse_effect(raw, where: str, default: LedEffect) -> LedEffect:
    """One palette entry, falling back per field: a bad colour costs you that
    colour, not the whole state's appearance."""
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - using defaults", where)
        return default

    style = raw.get("style", default.style)
    if not (isinstance(style, str) and style in LED_STYLES):
        log.error(
            "config: %s.style must be one of %s - using %r",
            where, "/".join(LED_STYLES), default.style,
        )
        style = default.style

    period = raw.get("period_s", default.period_s)
    if not (isinstance(period, (int, float)) and not isinstance(period, bool) and period > 0):
        log.error("config: %s.period_s must be a number > 0 - using %s", where, default.period_s)
        period = default.period_s

    return LedEffect(
        style=style,
        color=_parse_color(raw.get("color", default.color), f"{where}.color", default.color),
        color2=_parse_color(raw.get("color2", default.color2), f"{where}.color2", default.color2),
        period_s=float(period),
    )


def _parse_ramp(raw, where: str, default: tuple[ramp.Stop, ...]) -> tuple[ramp.Stop, ...]:
    """A colour ramp: a list of stops, each either a bare colour or an object
    with a `color` and an optional `at` (0..1).

        "ramp": ["#ff0000", "#00ff00"]
        "ramp": [{"color": "#00ff00"}, {"color": "#ff0000", "at": 0.8}]

    Bare colours are spread evenly, which is what almost everyone wants. An
    entry that pins `at` keeps that position; one that doesn't keeps the even
    slot it would have had, so the two forms mix without a second syntax.
    Positions need not be sorted or span 0..1 - ramp.color_at handles both.

    Same per-key rule as everything else: one bad stop costs you that stop's
    colour, not the ramp.
    """
    if not isinstance(raw, list) or not raw:
        log.error("config: %s must be a non-empty list of colours - using the default", where)
        return default

    last = len(raw) - 1
    stops: list[ramp.Stop] = []
    for index, entry in enumerate(raw):
        slot = 0.0 if last == 0 else index / last
        if isinstance(entry, str):
            stops.append(ramp.Stop(slot, _parse_color(entry, f"{where}[{index}]", "#000000")))
            continue
        if not isinstance(entry, dict):
            log.error("config: %s[%d] must be a colour or an object - ignored", where, index)
            continue
        color = _parse_color(entry.get("color"), f"{where}[{index}].color", "#000000")
        at = entry.get("at", slot)
        if not (isinstance(at, (int, float)) and not isinstance(at, bool) and 0.0 <= at <= 1.0):
            log.error(
                "config: %s[%d].at must be a number from 0 to 1 - using %s",
                where, index, slot,
            )
            at = slot
        stops.append(ramp.Stop(float(at), color))

    if not stops:
        log.error("config: %s has no usable stops - using the default", where)
        return default
    return tuple(stops)


def _parse_palette(raw) -> dict[str, LedEffect]:
    """Merge the configured palette over the defaults. Always returns an
    entry for every LED state: a state the device can enter but the palette
    has no colour for would be an invisible button."""
    palette = _default_palette()
    if "led_palette" not in raw:
        return palette
    entries = raw["led_palette"]
    if not isinstance(entries, dict):
        log.error("config: 'led_palette' must be an object - using defaults")
        return palette
    for name, entry in entries.items():
        if name not in palette:
            log.warning("config: led_palette has unknown LED state %r - ignored", name)
            continue
        palette[name] = _parse_effect(entry, f"led_palette.{name}", palette[name])
    return palette


def _parse_looks(raw) -> dict[str, LedEffect]:
    """The named-look pool: `{"focus-warm": {...}}`.

    A pool rather than an inline effect per mode, for three reasons that all
    point the same way: two Pomodoros can want different colours, two *modes*
    can want the same colour, and a name is the thing an ephemeral effect
    already pushes down the wire (ROADMAP D4). Empty by default - a pool of
    invented names would be noise, and a mode with no look falls back to the
    global palette exactly as it always has.

    Per-key fallback like everything else: one broken look costs you that
    look, not the pool.
    """
    looks: dict[str, LedEffect] = {}
    if "looks" not in raw:
        return looks
    entries = raw["looks"]
    if not isinstance(entries, dict):
        log.error("config: 'looks' must be an object - ignored")
        return looks
    for name, entry in entries.items():
        if not (isinstance(name, str) and name.strip()):
            log.error("config: looks has an unusable name %r - ignored", name)
            continue
        looks[name] = _parse_effect(entry, f"looks.{name}", LedEffect())
    return looks


def _parse_mode_looks(raw, where: str, template: str, known: set[str]) -> dict[str, str]:
    """One mode's state -> look-name map, dropping anything unusable.

    Never fatal: a mode whose look is misspelled should light up in its
    default colour and say so, not vanish. That is the same fail-soft rule
    every other key follows, and it matters more here because a look is
    cosmetic - losing the mode over it would be wildly disproportionate.
    """
    entry = raw.get("looks")
    if entry is None:
        return {}
    if not isinstance(entry, dict):
        log.error("config: %s.looks must be an object - ignored", where)
        return {}

    owned = MODE_LED_STATES.get(template, ())
    chosen: dict[str, str] = {}
    for state, look in entry.items():
        if state not in owned:
            log.warning(
                "config: %s.looks names %r, which a %r mode does not own (%s) - ignored",
                where, state, template, "/".join(owned) or "no LED states",
            )
            continue
        if not (isinstance(look, str) and look in known):
            log.warning(
                "config: %s.looks[%r] is %r, which is not in 'looks' - "
                "using the palette colour for %s",
                where, state, look, state,
            )
            continue
        chosen[state] = look
    return chosen


@dataclass(frozen=True)
class AppConfig:
    # The name the ESP32 advertises; the host scans for it (see DESIGN-ESP32.md).
    ble_device_name: str = "AIButton"
    sounds_enabled: bool = True
    database_path: str = "data/events.db"  # relative to the working directory
    web_enabled: bool = True
    web_host: str = "0.0.0.0"  # LAN-facing; the web UI has no auth (see webui.py)
    web_port: int = 8080
    modes: tuple[Mode, ...] = field(default_factory=_default_modes)
    # What each LED state looks like. Pushed to the device on connect and on
    # every edit, so the button and the web UI's virtual device agree.
    led_palette: dict[str, LedEffect] = field(default_factory=_default_palette)
    # Named looks a mode can wear instead of the palette entry for the state
    # it is showing (see `look_for`). Empty means every mode uses the palette,
    # which is what they all did before this existed.
    looks: dict[str, LedEffect] = field(default_factory=dict)
    # Where the swappable scene files live and which one is active. The scene
    # itself is merged in before parsing (see load_config_full), so nothing
    # downstream of here knows a scene was involved.
    scenes: SceneSettings = field(default_factory=SceneSettings)
    # The shortest a hard on/off flash may be, in seconds. Defaults to the 3 Hz
    # photosensitivity floor (device.SAFE_MIN_PERIOD_S) and is deliberately a
    # setting rather than a constant: this is one button on one desk, and the
    # person who owns it may decide it can go faster. Taking it below the
    # recommendation is allowed and warns; it is never silently ignored.
    min_flash_period_s: float = SAFE_MIN_PERIOD_S


# --- parsing helpers ----------------------------------------------------

def _take(raw: dict, key: str, expected: type, default):
    """Return raw[key] if present and well-typed, else the default."""
    if key not in raw:
        return default
    value = raw[key]
    if expected is float:
        # Accept ints for float fields, but never bools (bool is an int subclass).
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    elif expected is bool:
        if isinstance(value, bool):
            return value
    elif isinstance(value, expected) and not isinstance(value, bool):
        return value
    log.error(
        "config: %r should be %s, got %r - using default %r",
        key, expected.__name__, value, default,
    )
    return default


def _parse_action(raw, where: str) -> Action | None:
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - ignored", where)
        return None
    # Legacy v0.1 command entries have no "action" key, just prompt/label.
    kind = raw.get("action", "prompt" if "prompt" in raw else None)
    if kind == "log":
        event = raw.get("event")
        if isinstance(event, str) and event:
            return LogAction(event=event)
    elif kind == "timer_toggle":
        log_as = raw.get("log_as")
        if isinstance(log_as, str) and log_as:
            return TimerToggleAction(log_as=log_as)
    elif kind == "webhook":
        url, payload = raw.get("url"), raw.get("payload", {})
        if (
            isinstance(url, str)
            and url.startswith(("http://", "https://"))
            and isinstance(payload, dict)
        ):
            return WebhookAction(url=url, payload=payload)
    elif kind == "enter_mode":
        # The target is validated as a non-empty string only; whether a
        # takeover mode by that name actually exists is left to the runtime
        # (forward references / config ordering - see EnterModeAction).
        target = raw.get("target")
        if isinstance(target, str) and target:
            return EnterModeAction(target=target)
    elif kind == "alarm":
        # v0.2 standalone alarm *action* is removed (alarm is a template
        # now). It cannot be migrated inline (no fire time), so callers that
        # see one drop it with a loud warning - see _migrate_rule.
        log.error(
            "config: %s uses the removed 'alarm' action - alarms are now an "
            "alarm-template mode; ignored", where,
        )
        return None
    elif kind == "prompt":
        # The on-device AI is gone with the Pi build (DESIGN-ESP32.md); there
        # is nothing on the host to send a prompt to. Say so plainly rather
        # than letting it fall through as a generic "not a valid action".
        log.error(
            "config: %s uses the removed 'prompt' action - the on-device AI "
            "client is gone; POST to an AI via a webhook instead; ignored", where,
        )
        return None
    log.error("config: %s is not a valid action - ignored", where)
    return None


def _parse_time(value) -> time | None:
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    return None


def _parse_days(raw_days, where: str) -> frozenset[int] | None | object:
    """Parse a `days` list into a weekday-index set. Returns None when no
    days key was meaningful, or the sentinel _INVALID when present but
    malformed (so the caller can skip the mode)."""
    if isinstance(raw_days, list) and raw_days and all(
        isinstance(d, str) and d.lower() in _DAY_NAMES for d in raw_days
    ):
        return frozenset(_DAY_NAMES.index(d.lower()) for d in raw_days)
    log.error("config: %s must be a list of %s", where, "/".join(_DAY_NAMES))
    return _INVALID


_INVALID = object()  # sentinel: a key was present but malformed -> skip the mode


def _parse_activation(raw, where: str) -> Activation | None:
    """Parse an activation object (tagged by .type). Returns None on any
    problem so the caller skips the whole mode - running a scoped mode at
    the wrong time is worse than not running it."""
    if not isinstance(raw, dict):
        log.error("config: %s.activation must be an object - mode skipped", where)
        return None
    kind = raw.get("type")

    if kind == "always":
        return AlwaysActivation()

    if kind == "manual":
        return ManualActivation()

    if kind == "window":
        between = None
        if "between" in raw:
            pair = raw["between"]
            if isinstance(pair, list) and len(pair) == 2:
                start, end = _parse_time(pair[0]), _parse_time(pair[1])
                if start is not None and end is not None:
                    between = (start, end)
            if between is None:
                log.error(
                    "config: %s.activation.between must be [\"HH:MM\", \"HH:MM\"] - mode skipped",
                    where,
                )
                return None
        days = None
        if "days" in raw:
            days = _parse_days(raw["days"], f"{where}.activation.days")
            if days is _INVALID:
                log.error("config: %s - mode skipped", where)
                return None
        if between is None and days is None:
            # A window with neither bound is just "always".
            return AlwaysActivation()
        return WindowActivation(between=between, days=days)

    if kind == "schedule":
        at = _parse_time(raw.get("at"))
        if at is None:
            log.error("config: %s.activation.at must be \"HH:MM\" - mode skipped", where)
            return None
        days = None
        if "days" in raw:
            days = _parse_days(raw["days"], f"{where}.activation.days")
            if days is _INVALID:
                log.error("config: %s - mode skipped", where)
                return None
        return ScheduleActivation(at=at, days=days)

    log.error("config: %s.activation has unknown type %r - mode skipped", where, kind)
    return None


def _parse_actions_body(raw: dict, where: str, name: str) -> ActionsBehavior | None:
    """Parse the flat actions-template fields. An invalid action is dropped
    individually; a mode left with zero valid gesture actions is skipped."""
    unless_logged_today = None
    if "unless_logged_today" in raw:
        value = raw["unless_logged_today"]
        if isinstance(value, str) and value:
            unless_logged_today = value
        else:
            log.error(
                "config: %s.unless_logged_today must be a non-empty string - mode skipped",
                where,
            )
            return None

    actions: dict[str, Action] = {}
    for trigger in TRIGGER_TYPES:
        if trigger in raw:
            action = _parse_action(raw[trigger], f"{where}.{trigger}")
            if action is not None:
                actions[trigger] = action
    if not actions:
        log.error("config: %s (%r) has no valid gesture actions - skipped", where, name)
        return None
    return ActionsBehavior(actions=actions, unless_logged_today=unless_logged_today)


def _parse_alarm_body(raw: dict, where: str) -> AlarmBehavior | None:
    """Parse the flat alarm-template fields, each falling back per-key."""
    defaults = AlarmBehavior()

    message = raw.get("message", defaults.message)
    if not isinstance(message, str):
        log.error("config: %s.message must be a string - using default", where)
        message = defaults.message

    label = raw.get("label", defaults.label)
    if not isinstance(label, str):
        log.error("config: %s.label must be a string - using default", where)
        label = defaults.label

    snooze = raw.get("snooze_minutes", defaults.snooze_minutes)
    if not (isinstance(snooze, (int, float)) and not isinstance(snooze, bool) and snooze >= 0):
        log.error("config: %s.snooze_minutes must be a number >= 0 - using default", where)
        snooze = defaults.snooze_minutes

    dismiss_event = raw.get("dismiss_event", defaults.dismiss_event)
    if not isinstance(dismiss_event, str):
        log.error("config: %s.dismiss_event must be a string - using default", where)
        dismiss_event = defaults.dismiss_event

    return AlarmBehavior(
        message=message, label=label,
        snooze_minutes=float(snooze), dismiss_event=dismiss_event,
    )


def _parse_ladder(raw, where: str) -> LadderSpec:
    """One subdivision ladder, each key falling back on its own.

    Same rule as `_parse_effect`: a bad rung costs you that rung, a bad tick
    costs you the tick, and neither costs you the mode. A ladder is a *look*,
    and losing a stopwatch over the colour of its off-beat would be wildly
    disproportionate.

    An `enabled` ladder with no usable rungs left is turned back off rather
    than run as a base-colour-only clock: showing one flat colour and calling
    it a time reference is worse than showing the mode's ordinary look.
    """
    defaults = LadderSpec()
    if raw is None:
        return defaults
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - ignored", where)
        return defaults

    enabled = raw.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        log.error("config: %s.enabled must be true or false - using default", where)
        enabled = defaults.enabled

    tick = raw.get("tick_s", defaults.tick_s)
    if not (isinstance(tick, (int, float)) and not isinstance(tick, bool) and tick > 0):
        log.error("config: %s.tick_s must be a number > 0 - using default", where)
        tick = defaults.tick_s

    # _parse_color rather than a local check: it already owns normalisation
    # ('#' optional, case-folded), and a second opinion about what a colour is
    # would be a mirrored table with nothing testing the mirror.
    base = _parse_color(raw["base"], f"{where}.base", defaults.base) \
        if "base" in raw else defaults.base

    entries = raw.get("rungs", None)
    if entries is None:
        rungs = defaults.rungs
    elif not isinstance(entries, list):
        log.error("config: %s.rungs must be a list - using defaults", where)
        rungs = defaults.rungs
    else:
        rungs = tuple(_parse_rungs(entries, where))

    if enabled and not rungs:
        log.warning(
            "config: %s has no usable rungs - the subdivision light is off", where
        )
        enabled = False
    return LadderSpec(
        enabled=enabled, tick_s=float(tick), base=base, rungs=rungs
    )


def _parse_rungs(entries: list, where: str):
    """Each rung independently; an unusable one is dropped with a warning."""
    for index, entry in enumerate(entries):
        at = f"{where}.rungs[{index}]"
        if not isinstance(entry, dict):
            log.error("config: %s must be an object - dropped", at)
            continue
        every = entry.get("every_s")
        if not (
            isinstance(every, (int, float))
            and not isinstance(every, bool)
            and every > 0
        ):
            log.error("config: %s.every_s must be a number > 0 - dropped", at)
            continue
        # A rung with no readable colour is dropped rather than defaulted:
        # unlike `base`, there is no sensible colour to substitute, and a rung
        # silently becoming black would look exactly like the off-beat.
        raw_color = entry.get("color")
        color = _parse_color(raw_color, f"{at}.color", "")
        if not color:
            continue
        yield ladder.Rung(every_s=float(every), color=color)


def _parse_reminder_body(raw: dict, where: str) -> ReminderBehavior | None:
    """Parse the flat reminder-template fields, each falling back per-key."""
    defaults = ReminderBehavior()

    message = raw.get("message", defaults.message)
    if not isinstance(message, str):
        log.error("config: %s.message must be a string - using default", where)
        message = defaults.message

    label = raw.get("label", defaults.label)
    if not isinstance(label, str):
        log.error("config: %s.label must be a string - using default", where)
        label = defaults.label

    chime = raw.get("chime", defaults.chime)
    if not isinstance(chime, bool):
        log.error("config: %s.chime must be true or false - using default", where)
        chime = defaults.chime

    cleared_event = raw.get("cleared_event", defaults.cleared_event)
    if not isinstance(cleared_event, str):
        log.error("config: %s.cleared_event must be a string - using default", where)
        cleared_event = defaults.cleared_event

    timeout = raw.get("timeout_minutes", defaults.timeout_minutes)
    if not (isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout >= 0):
        log.error(
            "config: %s.timeout_minutes must be a number >= 0 - using default", where
        )
        timeout = defaults.timeout_minutes

    return ReminderBehavior(
        message=message, label=label, chime=chime,
        cleared_event=cleared_event, timeout_minutes=float(timeout),
    )


def _parse_stopwatch_body(raw: dict, where: str) -> StopwatchBehavior | None:
    """Parse the flat stopwatch-template field, falling back per-key."""
    defaults = StopwatchBehavior()
    log_as = raw.get("log_as", defaults.log_as)
    if not isinstance(log_as, str):
        log.error("config: %s.log_as must be a string - using default", where)
        log_as = defaults.log_as
    return StopwatchBehavior(
        log_as=log_as, ladder=_parse_ladder(raw.get("ladder"), f"{where}.ladder")
    )


def _parse_counter_body(raw: dict, where: str) -> CounterBehavior | None:
    """Parse the flat counter-template field, falling back per-key."""
    defaults = CounterBehavior()
    event = raw.get("event", defaults.event)
    if not isinstance(event, str):
        log.error("config: %s.event must be a string - using default", where)
        event = defaults.event
    return CounterBehavior(event=event)


def _parse_pomodoro_body(raw: dict, where: str) -> PomodoroBehavior | None:
    """Parse the flat pomodoro-template fields, falling back per key. A bad
    duration costs you that duration, not the whole mode."""
    defaults = PomodoroBehavior()

    def minutes(key: str, default: float) -> float:
        value = raw.get(key, default)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
        log.error("config: %s.%s must be a number > 0 - using %s", where, key, default)
        return default

    blocks = raw.get("blocks_before_long_break", defaults.blocks_before_long_break)
    if not (isinstance(blocks, int) and not isinstance(blocks, bool) and blocks > 0):
        log.error(
            "config: %s.blocks_before_long_break must be a whole number > 0 - using %s",
            where, defaults.blocks_before_long_break,
        )
        blocks = defaults.blocks_before_long_break

    advance = raw.get("advance", defaults.advance)
    if not (isinstance(advance, str) and advance in POMODORO_ADVANCE):
        log.error(
            "config: %s.advance must be one of %s - using %r",
            where, "/".join(POMODORO_ADVANCE), defaults.advance,
        )
        advance = defaults.advance

    log_as = raw.get("log_as", defaults.log_as)
    if not (isinstance(log_as, str) and log_as):
        log.error("config: %s.log_as must be a non-empty string - using %r",
                  where, defaults.log_as)
        log_as = defaults.log_as

    gestures = dict(defaults.gestures)
    for trigger in TRIGGER_TYPES:
        if trigger not in raw:
            continue
        command = raw[trigger]
        if command in (None, ""):  # explicitly unbound
            gestures.pop(trigger, None)
        elif isinstance(command, str) and command in POMODORO_COMMANDS:
            gestures[trigger] = command
        else:
            log.error(
                "config: %s.%s must be one of %s - keeping %r",
                where, trigger, "/".join(POMODORO_COMMANDS), gestures.get(trigger),
            )
    if "exit" not in gestures.values():
        # Every other takeover mode can be left with a press. A Pomodoro with
        # no exit gesture would own the button until the session ended.
        log.warning(
            "config: %s has no gesture bound to 'exit' - the only way out is "
            "finishing the session", where,
        )

    return PomodoroBehavior(
        work_minutes=minutes("work_minutes", defaults.work_minutes),
        break_minutes=minutes("break_minutes", defaults.break_minutes),
        long_break_minutes=minutes("long_break_minutes", defaults.long_break_minutes),
        blocks_before_long_break=blocks,
        extend_minutes=minutes("extend_minutes", defaults.extend_minutes),
        advance=advance,
        log_as=log_as,
        gestures=gestures,
    )


def _parse_metronome_body(raw: dict, where: str) -> MetronomeBehavior:
    """Parse the flat metronome-template fields, falling back per key. A bad
    tempo costs you that tempo, not the whole mode."""
    defaults = MetronomeBehavior()

    def positive(key: str, default: float) -> float:
        value = raw.get(key, default)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
        log.error("config: %s.%s must be a number > 0 - using %s", where, key, default)
        return default

    start_bpm = positive("start_bpm", defaults.start_bpm)
    max_bpm = positive("max_bpm", defaults.max_bpm)
    if start_bpm > max_bpm:
        # Not a fallback but a reconciliation: both values parsed fine, they
        # just disagree. Lifting the ceiling keeps the tempo the user actually
        # asked to start at, rather than silently slowing them down.
        log.warning(
            "config: %s.start_bpm (%s) is above max_bpm (%s) - raising max_bpm to match",
            where, start_bpm, max_bpm,
        )
        max_bpm = start_bpm

    tap_history = raw.get("tap_history", defaults.tap_history)
    if not (isinstance(tap_history, int) and not isinstance(tap_history, bool) and tap_history >= 2):
        # Two taps is one interval - the least you can average anything over.
        log.error(
            "config: %s.tap_history must be a whole number >= 2 - using %s",
            where, defaults.tap_history,
        )
        tap_history = defaults.tap_history

    sound_on_tap = raw.get("sound_on_tap", defaults.sound_on_tap)
    if not isinstance(sound_on_tap, bool):
        log.error("config: %s.sound_on_tap must be true or false - using %s",
                  where, defaults.sound_on_tap)
        sound_on_tap = defaults.sound_on_tap

    log_as = raw.get("log_as", defaults.log_as)
    if not (isinstance(log_as, str) and log_as):
        log.error("config: %s.log_as must be a non-empty string - using %r",
                  where, defaults.log_as)
        log_as = defaults.log_as

    return MetronomeBehavior(
        start_bpm=start_bpm,
        tap_history=tap_history,
        reset_gap_s=positive("reset_gap_s", defaults.reset_gap_s),
        max_bpm=max_bpm,
        sound_on_tap=sound_on_tap,
        log_as=log_as,
    )


def _parse_countdown_body(raw: dict, where: str) -> CountdownBehavior:
    """Parse the flat countdown-template fields, falling back per key."""
    defaults = CountdownBehavior()

    minutes = raw.get("minutes", defaults.minutes)
    if not (isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0):
        log.error("config: %s.minutes must be a number > 0 - using %s", where, defaults.minutes)
        minutes = defaults.minutes

    label = raw.get("label", defaults.label)
    if not isinstance(label, str):
        log.error("config: %s.label must be a string - using default", where)
        label = defaults.label

    style = raw.get("style", defaults.style)
    if not (isinstance(style, str) and style in LED_STYLES):
        log.error(
            "config: %s.style must be one of %s - using %r",
            where, "/".join(LED_STYLES), defaults.style,
        )
        style = defaults.style

    period = raw.get("period_s", defaults.period_s)
    if not (isinstance(period, (int, float)) and not isinstance(period, bool) and period > 0):
        log.error("config: %s.period_s must be a number > 0 - using %s", where, defaults.period_s)
        period = defaults.period_s

    ring = raw.get("ring_on_finish", defaults.ring_on_finish)
    if not isinstance(ring, bool):
        log.error("config: %s.ring_on_finish must be true or false - using %s",
                  where, defaults.ring_on_finish)
        ring = defaults.ring_on_finish

    log_as = raw.get("log_as", defaults.log_as)
    if not (isinstance(log_as, str) and log_as):
        log.error("config: %s.log_as must be a non-empty string - using %r",
                  where, defaults.log_as)
        log_as = defaults.log_as

    stops = defaults.ramp
    if "ramp" in raw:
        stops = _parse_ramp(raw["ramp"], f"{where}.ramp", defaults.ramp)

    return CountdownBehavior(
        minutes=float(minutes), label=label, style=style, period_s=float(period),
        ramp=stops, ring_on_finish=ring, log_as=log_as,
        ladder=_parse_ladder(raw.get("ladder"), f"{where}.ladder"),
    )


def _parse_mode(raw, idx: int, looks: set[str] | None = None) -> Mode | None:
    """Parse one mode. A mode with a broken activation, a template<->
    activation nature mismatch, or no usable body is skipped entirely
    (logged) - the fail-soft floor is the built-in default modes."""
    where = f"modes[{idx}]"
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - skipped", where)
        return None
    name = raw["name"] if isinstance(raw.get("name"), str) and raw.get("name") else f"mode {idx + 1}"

    activation = _parse_activation(raw.get("activation", {"type": "always"}), where)
    if activation is None:
        return None

    template = raw.get("template", "actions")
    allowed = _ALLOWED_ACTIVATIONS.get(template)
    if allowed is None:
        log.error("config: %s (%r) has unknown template %r - skipped", where, name, template)
        return None
    if not isinstance(activation, allowed):
        log.error(
            "config: %s (%r) is a %r mode but its activation is %s - skipped",
            where, name, template, type(activation).__name__,
        )
        return None

    if template == "actions":
        behavior = _parse_actions_body(raw, where, name)
    elif template == "alarm":
        behavior = _parse_alarm_body(raw, where)
    elif template == "reminders":
        behavior = _parse_reminder_body(raw, where)
    elif template == "stopwatch":
        behavior = _parse_stopwatch_body(raw, where)
    elif template == "counter":
        behavior = _parse_counter_body(raw, where)
    elif template == "pomodoro":
        behavior = _parse_pomodoro_body(raw, where)
    elif template == "metronome":
        behavior = _parse_metronome_body(raw, where)
    elif template == "countdown":
        behavior = _parse_countdown_body(raw, where)
    else:  # pragma: no cover - allow-list keys and this dispatch stay in sync
        log.error("config: %s (%r) has unknown template %r - skipped", where, name, template)
        return None

    if behavior is None:
        return None
    return Mode(
        name=name,
        behavior=behavior,
        activation=activation,
        looks=_parse_mode_looks(raw, where, template, looks or set()),
    )


def _migrate_rule(raw, idx: int) -> Mode | None:
    """Convert one legacy v0.2 rule into an ambient actions mode: window
    activation when it had between/days, else always. A gesture using the
    removed `alarm` action cannot be migrated (no fire time) and is dropped
    with a loud warning; if that empties the rule, it is skipped."""
    where = f"rules[{idx}]"
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - skipped", where)
        return None
    name = raw["name"] if isinstance(raw.get("name"), str) and raw.get("name") else f"rule {idx + 1}"

    between = None
    if "between" in raw:
        pair = raw["between"]
        if isinstance(pair, list) and len(pair) == 2:
            start, end = _parse_time(pair[0]), _parse_time(pair[1])
            if start is not None and end is not None:
                between = (start, end)
        if between is None:
            log.error("config: %s.between must be [\"HH:MM\", \"HH:MM\"] - rule skipped", where)
            return None

    days = None
    if "days" in raw:
        days = _parse_days(raw["days"], f"{where}.days")
        if days is _INVALID:
            log.error("config: %s.days invalid - rule skipped", where)
            return None

    unless_logged_today = None
    if "unless_logged_today" in raw:
        value = raw["unless_logged_today"]
        if isinstance(value, str) and value:
            unless_logged_today = value
        else:
            log.error("config: %s.unless_logged_today must be a non-empty string - rule skipped", where)
            return None

    actions: dict[str, Action] = {}
    for trigger in TRIGGER_TYPES:
        if trigger in raw:
            entry = raw[trigger]
            if isinstance(entry, dict) and entry.get("action") == "alarm":
                log.warning(
                    "config: %s.%s uses the removed 'alarm' action - cannot migrate a "
                    "gesture-fired alarm to a scheduled alarm mode; dropped. Re-add it as "
                    "an alarm-template mode with a schedule.", where, trigger,
                )
                continue
            action = _parse_action(entry, f"{where}.{trigger}")
            if action is not None:
                actions[trigger] = action
    if not actions:
        log.error("config: %s (%r) has no migratable gesture actions - skipped", where, name)
        return None

    if between is not None or days is not None:
        activation: Activation = WindowActivation(between=between, days=days)
    else:
        activation = AlwaysActivation()
    return Mode(
        name=name,
        behavior=ActionsBehavior(actions=actions, unless_logged_today=unless_logged_today),
        activation=activation,
    )


def _parse_modes(raw: dict, looks: set[str] | None = None) -> tuple[Mode, ...]:
    """Resolve the modes list, applying the migration ladder:
    modes (v0.3) -> rules (v0.2) -> commands (v0.1) -> built-in defaults.

    `looks` is the pool of names a mode may reference; it is parsed first so a
    dangling reference is caught here and reported, rather than discovered at
    the moment the light should have changed colour. The legacy ladders below
    predate looks entirely and never produce one.
    """
    if isinstance(raw.get("modes"), list):
        modes = tuple(
            mode
            for idx, entry in enumerate(raw["modes"])
            if (mode := _parse_mode(entry, idx, looks)) is not None
        )
        if not modes:
            log.error("config: no valid modes - using defaults")
            return _default_modes()
        return modes

    if raw.get("modes") is not None:
        log.error("config: 'modes' must be a list - falling back to legacy/defaults")

    if isinstance(raw.get("rules"), list):
        log.info("config: legacy 'rules' schema - migrating to ambient actions modes")
        modes = tuple(
            mode
            for idx, entry in enumerate(raw["rules"])
            if (mode := _migrate_rule(entry, idx)) is not None
        )
        if not modes:
            log.error("config: no migratable rules - using defaults")
            return _default_modes()
        return modes

    if raw.get("rules") is not None:
        log.error("config: 'rules' must be a list - using defaults")

    if isinstance(raw.get("commands"), dict):
        # Legacy v0.1 schema: commands become a single default actions mode.
        log.info("config: legacy 'commands' schema - treating as one default mode")
        mode = _migrate_rule({"name": "Default", **raw["commands"]}, 0)
        if mode is not None:
            return (mode,)
        log.error("config: legacy commands had no valid actions - using defaults")

    return _default_modes()


def parse_config(raw: dict) -> AppConfig:
    """Validate a raw config object. Never raises - bad keys fall back
    per-key with a logged warning/error. Also the validation path for
    configs submitted through the web API."""
    defaults = AppConfig()
    known = {
        "ble_device_name", "sounds_enabled", "database_path",
        "web_enabled", "web_host", "web_port",
        "modes", "rules", "commands", "led_palette", "looks", "scenes",
        "min_flash_period_s",
    }
    for key in raw:
        if key not in known:
            log.warning("config: unknown key %r - ignored", key)

    # The look pool is parsed before the modes so a mode naming a look that
    # does not exist is reported here rather than at the moment the light
    # should have changed colour.
    looks = _parse_looks(raw)

    return AppConfig(
        ble_device_name=_take(raw, "ble_device_name", str, defaults.ble_device_name),
        sounds_enabled=_take(raw, "sounds_enabled", bool, defaults.sounds_enabled),
        database_path=_take(raw, "database_path", str, defaults.database_path),
        web_enabled=_take(raw, "web_enabled", bool, defaults.web_enabled),
        web_host=_take(raw, "web_host", str, defaults.web_host),
        web_port=_take(raw, "web_port", int, defaults.web_port),
        modes=_parse_modes(raw, set(looks)),
        led_palette=_parse_palette(raw),
        looks=looks,
        scenes=scenes.parse_settings(raw.get("scenes")),
        min_flash_period_s=_parse_min_flash_period(raw),
    )


def _parse_min_flash_period(raw: dict) -> float:
    """The effective flash floor, with the recommendation as the default.

    Two different failures, told apart on purpose. A value that is not a
    positive number is *broken* - there is no reading of it, so it falls back
    like any other bad key. A value that is merely lower than the recommended
    floor is a *choice*: it is honoured and warned about, because the whole
    reason this is a setting is that someone may mean it.
    """
    value = _take(raw, "min_flash_period_s", float, SAFE_MIN_PERIOD_S)
    if value <= 0:
        log.error(
            "config: min_flash_period_s must be greater than 0, got %r - "
            "using %.3f", value, SAFE_MIN_PERIOD_S,
        )
        return SAFE_MIN_PERIOD_S
    if value < SAFE_MIN_PERIOD_S:
        log.warning(
            "config: min_flash_period_s %.3fs allows flashing at %.1f Hz, above "
            "the recommended %.1f Hz photosensitivity limit - honoured, but it "
            "is a seizure risk for some people",
            value, 1 / value, 1 / SAFE_MIN_PERIOD_S,
        )
    return value


def flash_safe(effect: LedEffect | None, min_period_s: float) -> LedEffect | None:
    """`effect` with its period raised to `min_period_s` if it strobes.

    Pure, so the safety property is testable without a device or a clock -
    and one function rather than a clamp repeated at each call site, because
    a floor enforced in three places is a floor with three chances to drift.

    Only hard on/off styles are floored (device.STYLE_STROBES). `breathe` and
    `fade` travel the same distance smoothly, so a fast one reads as shimmer
    rather than as a strobe, and flooring them would make the slowest legal
    breathe a third of a second for no benefit. None passes through - it is
    what `set_led` means by "no override", and the palette entry it falls back
    to has been through here already.
    """
    if effect is None or effect.style not in STYLE_STROBES:
        return effect
    if effect.period_s >= min_period_s:
        return effect
    return replace(effect, period_s=min_period_s)


def look_for(config: AppConfig, mode: Mode | None, state: LEDState) -> LedEffect | None:
    """The look `mode` wears for `state`, or None to use the palette entry.

    None rather than the palette entry on purpose: None is what `set_led`
    already means by "no override", so a mode that has not chosen a look costs
    nothing - no effect write, no borrowed palette entry, and a device that
    predates ephemeral effects behaves exactly as it did.
    """
    if mode is None:
        return None
    name = mode.looks.get(state.value)
    return config.looks.get(name) if name else None


@contextlib.contextmanager
def _collecting(warnings: list[str]):
    """Route the parser's per-key fallback complaints into `warnings`.

    Both loggers are captured: a scene's own keys are validated in scenes.py,
    and a warning the editor never sees is a warning nobody acts on.
    """

    class _Collector(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.WARNING)

        def emit(self, record: logging.LogRecord) -> None:
            warnings.append(record.getMessage())

    collector = _Collector()
    loggers = [log, logging.getLogger(scenes.__name__)]
    for logger in loggers:
        logger.addHandler(collector)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeHandler(collector)


def parse_with_warnings(raw: dict) -> tuple[AppConfig, list[str]]:
    """`parse_config` plus the warnings it logged along the way.

    The web API returns these to the editor and the scenes CLI prints them, so
    both show exactly what the service would accept - there is one parser, and
    this is how its complaints get out of the journal.
    """
    warnings: list[str] = []
    with _collecting(warnings):
        cfg = parse_config(raw)
    return cfg, warnings


def parse_effect_with_warnings(raw, where: str = "effect") -> tuple[LedEffect, list[str]]:
    """One look, through the config parser's own rules.

    The Lights tab's test bench shows a look the button never stores, but
    "what counts as a valid look" must not fork: a colour the editor would
    reject when saved has to be rejected the same way when shown, or the
    bench stops being a test of the real thing. Same per-field fallback as
    everywhere else - a bad colour costs you that colour, not the request.
    """
    warnings: list[str] = []
    with _collecting(warnings):
        effect = _parse_effect(raw, where, LedEffect())
    return effect, warnings


@dataclass(frozen=True)
class LoadedConfig:
    """What `load_config_full` returns: the effective config, plus which scene
    produced it. `scene_error` is why a *configured* scene isn't loaded - the
    service runs the base config in that case, so the UI needs to be able to
    say what happened rather than showing an active scene that isn't."""

    config: AppConfig
    scene_id: str | None = None
    scene_path: str | None = None
    scene_error: str = ""


def _read_config_file(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        log.warning("config: %s not found - using built-in defaults", path)
        return None
    except (OSError, json.JSONDecodeError) as exc:
        log.error("config: cannot read %s (%s) - using built-in defaults", path, exc)
        return None
    if not isinstance(raw, dict):
        log.error("config: top level of %s is not an object - using defaults", path)
        return None
    return raw


def load_config_full(path: str) -> LoadedConfig:
    """Load `path`, layer the active scene over it, and parse the result.

    Never raises. A scene that is missing or broken is reported and the base
    config runs on its own - a bad scene never crashes the service, for the
    same reason a bad config doesn't.
    """
    raw = _read_config_file(path)
    if raw is None:
        return LoadedConfig(config=AppConfig())

    settings = scenes.parse_settings(raw.get("scenes"))
    if settings.active is None:
        return LoadedConfig(config=parse_config(raw))

    scene_file = scenes.path_for(path, settings, settings.active)
    if scene_file is None or not scene_file.exists():
        error = f"scene {settings.active!r} not found in {scenes.dir_for(path, settings)}"
        log.error("config: %s - running the base config", error)
        return LoadedConfig(config=parse_config(raw), scene_error=error)

    scene_raw = scenes.read_json(scene_file)
    if scene_raw is None:
        error = f"scene {settings.active!r} is not a readable JSON object"
        log.error("config: %s - running the base config", error)
        return LoadedConfig(config=parse_config(raw), scene_error=error)

    return LoadedConfig(
        config=parse_config(scenes.merge(raw, scene_raw)),
        scene_id=settings.active,
        scene_path=str(scene_file),
    )


def load_config(path: str) -> AppConfig:
    """The effective config at `path`, active scene included. Never raises -
    bad input falls back per-key."""
    return load_config_full(path).config


def _action_to_dict(action: Action) -> dict:
    if isinstance(action, LogAction):
        return {"action": "log", "event": action.event}
    if isinstance(action, TimerToggleAction):
        return {"action": "timer_toggle", "log_as": action.log_as}
    if isinstance(action, WebhookAction):
        return {"action": "webhook", "url": action.url, "payload": action.payload}
    if isinstance(action, EnterModeAction):
        return {"action": "enter_mode", "target": action.target}
    raise TypeError(f"unknown action type {type(action).__name__}")


def _activation_to_dict(activation: Activation) -> dict:
    if isinstance(activation, AlwaysActivation):
        return {"type": "always"}
    if isinstance(activation, ManualActivation):
        return {"type": "manual"}
    if isinstance(activation, WindowActivation):
        entry: dict = {"type": "window"}
        if activation.between is not None:
            entry["between"] = [t.strftime("%H:%M") for t in activation.between]
        if activation.days is not None:
            entry["days"] = [_DAY_NAMES[i] for i in sorted(activation.days)]
        return entry
    if isinstance(activation, ScheduleActivation):
        entry = {"type": "schedule", "at": activation.at.strftime("%H:%M")}
        if activation.days is not None:
            entry["days"] = [_DAY_NAMES[i] for i in sorted(activation.days)]
        return entry
    raise TypeError(f"unknown activation type {type(activation).__name__}")


def _ladder_to_dict(spec: LadderSpec) -> dict:
    """Written out in full, longest interval first - the order it reads in, so
    the file shows the ladder the way the editor does."""
    return {
        "enabled": spec.enabled,
        "tick_s": spec.tick_s,
        "base": spec.base,
        "rungs": [
            {"every_s": rung.every_s, "color": rung.color}
            for rung in ladder.sorted_rungs(spec.rungs)
        ],
    }


def _effect_to_dict(effect: LedEffect) -> dict:
    return {
        "style": effect.style,
        "color": effect.color,
        "color2": effect.color2,
        "period_s": effect.period_s,
    }


def _mode_to_dict(mode: Mode) -> dict:
    entry: dict = {
        "name": mode.name,
        "template": mode.template,
        "activation": _activation_to_dict(mode.activation),
    }
    if mode.looks:  # omitted when empty, so a mode that uses the palette
        entry["looks"] = dict(mode.looks)  # round-trips as the plain object it was
    if isinstance(mode.behavior, ActionsBehavior):
        if mode.behavior.unless_logged_today is not None:
            entry["unless_logged_today"] = mode.behavior.unless_logged_today
        for trigger, action in mode.behavior.actions.items():
            entry[trigger] = _action_to_dict(action)
    elif isinstance(mode.behavior, AlarmBehavior):
        entry["message"] = mode.behavior.message
        entry["label"] = mode.behavior.label
        entry["snooze_minutes"] = mode.behavior.snooze_minutes
        entry["dismiss_event"] = mode.behavior.dismiss_event
    elif isinstance(mode.behavior, ReminderBehavior):
        entry["message"] = mode.behavior.message
        entry["label"] = mode.behavior.label
        entry["chime"] = mode.behavior.chime
        entry["cleared_event"] = mode.behavior.cleared_event
        entry["timeout_minutes"] = mode.behavior.timeout_minutes
    elif isinstance(mode.behavior, StopwatchBehavior):
        entry["log_as"] = mode.behavior.log_as
        entry["ladder"] = _ladder_to_dict(mode.behavior.ladder)
    elif isinstance(mode.behavior, CounterBehavior):
        entry["event"] = mode.behavior.event
    elif isinstance(mode.behavior, PomodoroBehavior):
        entry["work_minutes"] = mode.behavior.work_minutes
        entry["break_minutes"] = mode.behavior.break_minutes
        entry["long_break_minutes"] = mode.behavior.long_break_minutes
        entry["blocks_before_long_break"] = mode.behavior.blocks_before_long_break
        entry["extend_minutes"] = mode.behavior.extend_minutes
        entry["advance"] = mode.behavior.advance
        entry["log_as"] = mode.behavior.log_as
        for trigger, command in mode.behavior.gestures.items():
            entry[trigger] = command
    elif isinstance(mode.behavior, CountdownBehavior):
        entry["minutes"] = mode.behavior.minutes
        entry["label"] = mode.behavior.label
        entry["style"] = mode.behavior.style
        entry["period_s"] = mode.behavior.period_s
        # Positions are always written out, even when they came in as a bare
        # list of colours: the round-trip has to be exact, and a reader should
        # not have to know the even-spacing rule to see where a stop sits.
        entry["ramp"] = [
            {"color": stop.color, "at": stop.at} for stop in mode.behavior.ramp
        ]
        entry["ring_on_finish"] = mode.behavior.ring_on_finish
        entry["log_as"] = mode.behavior.log_as
        entry["ladder"] = _ladder_to_dict(mode.behavior.ladder)
    elif isinstance(mode.behavior, MetronomeBehavior):
        entry["start_bpm"] = mode.behavior.start_bpm
        entry["tap_history"] = mode.behavior.tap_history
        entry["reset_gap_s"] = mode.behavior.reset_gap_s
        entry["max_bpm"] = mode.behavior.max_bpm
        entry["sound_on_tap"] = mode.behavior.sound_on_tap
        entry["log_as"] = mode.behavior.log_as
    return entry


def as_dict(cfg: AppConfig) -> dict:
    """JSON-ready view of an AppConfig. Round-trips: the output is valid
    input for parse_config, so the web UI can edit the effective config.

    Only activation fields that are set are emitted; a window with neither
    bound is never produced (migration picks `always` instead)."""
    return {
        "ble_device_name": cfg.ble_device_name,
        "sounds_enabled": cfg.sounds_enabled,
        "database_path": cfg.database_path,
        "web_enabled": cfg.web_enabled,
        "web_host": cfg.web_host,
        "web_port": cfg.web_port,
        "min_flash_period_s": cfg.min_flash_period_s,
        "scenes": scenes.settings_to_dict(cfg.scenes),
        "modes": [_mode_to_dict(mode) for mode in cfg.modes],
        "led_palette": {
            name: _effect_to_dict(effect) for name, effect in cfg.led_palette.items()
        },
        "looks": {name: _effect_to_dict(effect) for name, effect in cfg.looks.items()},
    }


class ConfigManager:
    """Holds the live AppConfig; reload() re-reads the file (SIGHUP hook).

    It keeps the whole `LoadedConfig` rather than just the AppConfig so the
    API can answer "which scene is running, and if not the configured one,
    why not" without re-reading the disk to find out."""

    def __init__(self, path: str | None = None):
        self._path = path or os.environ.get("AIBUTTON_CONFIG", DEFAULT_CONFIG_PATH)
        self._loaded = load_config_full(self._path)

    @property
    def path(self) -> str:
        return self._path

    @property
    def config(self) -> AppConfig:
        return self._loaded.config

    @property
    def loaded(self) -> LoadedConfig:
        return self._loaded

    @property
    def write_path(self) -> str:
        """Where an edit to the *contents* of the config goes: the active
        scene's file when one is loaded, otherwise config.json itself. The
        scene pointer is the one thing that still goes to config.json (see
        scenes.set_active), which is what keeps the two files from ever
        holding two copies of the same modes list."""
        return self._loaded.scene_path or self._path

    def reload(self) -> None:
        self._loaded = load_config_full(self._path)
        scene = self._loaded.scene_id
        log.info(
            "config reloaded from %s%s", self._path,
            f" (scene {scene!r})" if scene else "",
        )
