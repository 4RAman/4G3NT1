"""Config loading, validation, and hot-reload for the button.

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
      { "name": "Morning meds",
        "template": "actions",
        "activation": { "type": "window", "between": ["05:00", "07:00"],
                        "days": ["mon","tue","wed","thu","fri"] },
        "unless_logged_today": "meds_taken",
        "double_tap": { "action": "log", "event": "meds_taken" } },
      { "name": "Wake up",
        "template": "alarm",
        "activation": { "type": "schedule", "at": "07:00" },
        "message": "Wake up", "snooze_minutes": 9 }
    ]

Two natures of mode (the template picks the nature):

* **Ambient** (`actions`) - passive; it only *answers* gestures while in
  scope. Pairs with `always`/`window` activations. Resolved first-match-wins
  in config order (see rules.py).
* **Takeover** (`alarm` and the rest) - the device *enters* it and it owns
  the button until it exits (see scheduler.py + main.py).

v0.4 - scenes
-------------
An optional `"scenes": {"dir": "scenes", "active": "focus"}` block layers
the named file over this one *as raw JSON* before anything below runs (see
load_config_full and [scenes.py](scenes.py)), so a scene is validated by the
same parser, with the same per-key fallbacks, as the config it overrides.

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
import re
from dataclasses import dataclass, field, fields, replace
from datetime import time
from typing import get_args

from . import keys, ladder, midi, ramp, scenes, sequencer
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
class ReadoutAction:
    """Show `event`'s count for today on the light, without entering an app:
    tens digit as slow pulses, units digit as quick ones (see
    `sequencer.readout`). Exact counts are what blink *rhythm* is good at and
    hue is not, so the scheme survives the ring's colour cast, a warm room and
    a colourblind reader (TODO 17).

    Dispatched by main.py's `handle()` rather than by `execute()`, like
    `EnterModeAction`: it pushes a whole one-shot sequence at the LED.
    """

    event: str
    tens_color: str = "#ff8800"  # warm orange - the coarse (tens) digit
    units_color: str = "#3399ff"  # cool blue - the fine (units) digit


@dataclass(frozen=True)
class TimerToggleAction:
    log_as: str


@dataclass(frozen=True)
class WebhookAction:
    url: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OscAction:
    """Fire one OSC message at something listening on UDP - a DAW, a lighting
    desk, a TouchOSC layout, anything in that family. A datagram that either
    leaves or does not, where a webhook is a request with an answer; see
    [osc.py](osc.py) on why fire-and-forget is the right contract here.

    `args` are JSON values and their OSC types are inferred: bool -> T/F,
    int -> i, float -> f, anything else -> s. That inference is the whole type
    system, and it is why the editor's hint says what it says.
    """

    host: str
    port: int
    address: str  # the OSC path, e.g. "/transport/play"
    args: tuple = ()


@dataclass(frozen=True)
class MidiAction:
    """Send one MIDI message to a port another application is listening on -
    a DAW, chiefly. It exists alongside `OscAction` because the DAW in
    question is Studio One, which speaks MIDI and Mackie Control and not OSC
    (see [midi.py](midi.py)).

    `port` is matched as a case-insensitive substring of the open MIDI output
    ports, not as an exact name: Windows decorates a loopMIDI port with a
    numeric suffix that changes between sessions, so "Button" is the name a
    config can hold and "Button 2" is what the system will actually call it.
    An empty port means the first one available, which is right on a machine
    with exactly one virtual cable and wrong to rely on anywhere else.

    `channel` is 1-16 the way a DAW's own UI says it; midi.py owns the
    conversion to the wire's 0-15.
    """

    port: str
    channel: int
    kind: str  # one of midi.KINDS
    number: int  # note number, or CC number
    value: int  # velocity, or CC value


@dataclass(frozen=True)
class KeysAction:
    """Press a key chord, and/or click, on the host running the service.

    A sibling of `MidiAction` and `OscAction` - the third way the button
    reaches other software - and the bluntest of the three: it drives whatever
    already has focus rather than addressing an application by name.

    **One chord, not a sequence** (TODO 37). A list of keystrokes with delays
    is `SequenceAction` (TODO 33) and a `keys` step inside it, not a second
    implementation here.

    `combo` is spelled the way a menu spells it (`ctrl+shift+p`) and is
    validated against `keys.KEYS` at parse time, so an unknown name is a config
    error rather than a keystroke. `click` is one of `keys.CLICKS`. At least
    one of the two is present - an action that does neither is a typo.

    **Host-local, permanently.** This is one of the things that stays on
    whatever machine runs the service (TODO 40): moved to a Pi it types into
    the Pi. That is not a bug to fix; it is what synthesizing input means.
    """

    combo: str = ""
    click: str = ""


@dataclass(frozen=True)
class EnterModeAction:
    """Switch into the named takeover mode, which is how a gesture starts one -
    so "entered by a gesture" needs no special activation type.

    The target is resolved at runtime (main.py), not at parse time: forward
    references and config ordering mean it may be defined later in the list,
    and a missing/non-takeover target fails as a fail state, never a crash."""

    target: str


@dataclass(frozen=True)
class StandbyAction:
    """Put the ambient layer to sleep, or wake it - one gesture, both ways.

    **Ambient-only, and session-only**, both decided rather than fallen into.
    Ambient: what sleeps is the layer answering everyday gestures, while a
    takeover already running and a scheduled one about to start are untouched -
    an alarm you set is not a thing a stray five-tap should be able to cancel.
    Session: an "off" that survived a restart would be a button that comes back
    dead with nothing on it to say why, so the flag lives in main.py's run loop
    and nowhere on disk.

    Handled by main.py's `handle()` rather than by `execute()`, like
    `EnterModeAction` and `ReadoutAction`: it changes what the loop does with
    the *next* gesture, and that is state only the loop owns.
    """


@dataclass(frozen=True)
class SequenceStep:
    """One step of a `SequenceAction`: an action, and how long to wait *before*
    running it.

    Before rather than after, because what a sequence is usually for is a gap
    *between* two messages - Mackie has no return-to-zero, so "stop and rewind"
    is Stop, a beat, Stop - and a delay written on the second step is where a
    reader looks for it.
    """

    action: Action
    wait_s: float = 0.0


@dataclass(frozen=True)
class SequenceAction:
    """A flat list of actions with optional delays (TODO 33).

    **Bounded by construction**: no loops, no conditionals, no nesting, a
    capped step count and a capped total duration. That is not tidiness - it
    is the difference between a thing the on-device runtime can eventually run
    and a language it never can (ROADMAP D2). *If it ever grows an `if`, it is
    host-only forever.*

    **It holds the button.** The steps are awaited in order, so a sequence with
    delays is exactly as long as its delays say, and presses made while it runs
    are dropped by the same rule that drops presses during any other action.

    A step may name a pooled action, and `resolve_action` unpacks that the way
    it unpacks any other binding - which is also where the one-level guarantee
    is made, since a pool entry may itself be a sequence.
    """

    steps: tuple[SequenceStep, ...]


@dataclass(frozen=True)
class SetPositionAction:
    """Put the *running* app on one of its named positions (TODO 74).

    The one action a takeover performs rather than `execute()` - the third of
    its kind, after `enter_mode` (only the loop can start an app) and
    `standby` (only the loop owns that flag). This one is narrower still:
    only an app that *has* positions can do anything with it, so it is
    delivered to whatever is running and fails clearly when nothing is.

    It is what a reflex says to a running app: "the DAW is recording now".
    Deliberately not offered to a gesture - a gesture at the ambient layer has
    no app to say it to (`appOnly` in schema.js).
    """

    name: str


# What `set_value` may do to a slot. Two, and deliberately only two: a delta
# and an absolute. Anything else - multiply, min, clamp - is arithmetic, and
# arithmetic on the button is the app runtime's expression language
# (ARCHITECTURE.md), not an action's business. Mirrored in schema.js.
SET_VALUE_OPS: tuple[str, ...] = ("add", "set")


@dataclass(frozen=True)
class SetValueAction:
    """Write one slot of an app's document (TODO 34, ROADMAP D9's third action
    family).

    **App-bound**: it names an app and reaches into that app's data, which is
    what makes it the answer to TODO 15's *"Smoking +1 without entering the
    Counter"*. It is nonetheless an ordinary fire-and-forget primitive - it
    changes no app's loop, owns no light and hands the button straight back -
    so it works on a gesture, a hook, a reflex and a sequence step with no
    site having to learn about it.

    Not delivered to the running app the way `set_position` is, and the
    difference is the point: a position is a thing only a running app can be
    *in*, while a document lives outside every run loop precisely so anything
    can write it. An app reads its own slot when it next looks.

    **A name that no mode has is a dangling reference**, kept and warned about
    like every other one here: quietly repointing it at some other app would
    be worse, and deleting the binding would lose the number's owner.
    """

    app: str  # the mode's name - its document is keyed by that
    slot: str  # one of DOC_SLOTS[template]
    op: str = "add"  # "add" (a delta) or "set" (an absolute value)
    value: float | str | bool = 1


@dataclass(frozen=True)
class NamedAction:
    """A reference into `AppConfig.actions` - the pool - by name.

    In JSON it is a bare string, and that is what makes it free: every binding
    ever written is an object, so a string can only mean this, and no existing
    config can be misread as one. Naming stays optional; most actions are used
    once, and forcing those through a library is indirection for nothing.

    Resolved at use time (`resolve_action`), not at parse time, and a dangling
    reference stays dangling on purpose - see CLAUDE.md.
    """

    name: str


Action = (
    LogAction | ReadoutAction | TimerToggleAction | WebhookAction | OscAction
    | MidiAction | KeysAction | EnterModeAction | NamedAction | StandbyAction
    | SetPositionAction | SetValueAction | SequenceAction
)


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
class ControlPosition:
    """One position a control surface can be *told* it is in (TODO 77).

    **The Signal light's `states`, in the template that needed the same
    thing** - "the app is in one of N visible states" - and the difference is
    where each one gets its colour. A Signal position *carries* one, because a
    status you invented has nothing else in the system it could mean. A control
    position **names a look from the pool**, because a control surface already
    answers "what does this look like" through `MODE_LED_STATES["control"]`,
    and a second colour control on the same app would be exactly the two
    answers CLAUDE.md forbids.

    Nothing sets one by pressing. A position arrives as a `SetPositionAction`
    from a reflex - *the DAW says it is recording* - which is why a surface
    with positions and no reflex to report them says it is guessing rather than
    showing the first one as if it were a fact.

    An empty `look` is a position that wears the page's own LISTENING look: the
    fallback chain is `set_led`'s, unchanged, and "more explicit wins" is why a
    named look overrides it.
    """

    name: str
    look: str = ""  # a name in AppConfig.looks; "" = the page's own look


@dataclass(frozen=True)
class ControlBehavior:
    """A control surface: an app whose gestures fire actions, like the ambient
    layer, but only while it is open.

    **The same map as `ActionsBehavior`, at the other level**, which is why it
    is cheap: an ambient actions mode answers gestures whenever nothing has
    taken over, and this answers them because you opened it. Nothing about what
    a gesture means changes; only when it applies.

    **Long press is not bindable, and `_parse_control_body` enforces it** -
    CLAUDE.md's "up one level" rule, in the app most likely to be used without
    looking. So the budget is five: short press, double tap, triple tap, four
    taps, five taps. If that is not enough, **bind one of them to `enter_mode`
    and branch** - a surface can open another one, so five gestures per page
    buys as many pages as you care to build. That is what `return_after` is
    for: without it, long press out of a sub-page would drop you all the way to
    the ambient layer, and the gesture would mean "up one level" or "up two"
    depending on how deep you had gone.
    """

    actions: dict[str, Action]  # trigger value -> action, never long_press
    log_as: str = ""  # optional event name written on each fire
    # On: a surface this one opens returns here when it is left, so long press
    # always travels exactly one level.
    return_after: bool = True
    # What the world says this surface is showing (TODO 77). Empty is the
    # ordinary remote: one resting look, and nothing to report. Non-empty makes
    # `resting()` paint the current position instead, and the page becomes a
    # readout of something else's state.
    positions: tuple[ControlPosition, ...] = ()

    @property
    def template(self) -> str:
        return "control"


@dataclass(frozen=True)
class NoticeBehavior:
    """The takeover notice template (TODO 84): the light goes off at a
    scheduled time and stays that way until cleared, snoozed, or missed. One
    machine behind three presets - Alarm, Reminder, and a dead man's switch -
    which used to be two templates (`AlarmBehavior`, `ReminderBehavior`) plus
    a preset. Handled by main.py's `ring_notice`, not `actions.execute()`,
    since it owns the LED/sound/button-event loop while it runs.

    `timeout_minutes` is persistence: 0 rings/flashes forever (an alarm's
    classic behaviour) until cleared or snoozed; >0 gives up after that long
    (a reminder's classic behaviour) - the missed outcome.

    `snooze_minutes` is 0 = no snooze offered; >0 = long_press snoozes for
    that long instead of clearing, then it rings/flashes again with a fresh
    `timeout_minutes`. Independent of persistence - a notice that also gives
    up on its own can still be snoozed in the meantime.

    `urgent` is the one thing the two old templates never shared a name for:
    True loops the alarm tone and hard-flashes ALERT (an alarm); False plays
    at most one chime and breathes ALERT gently (a reminder). It is
    independent of `timeout_minutes` on purpose - an old reminder configured
    to "wait forever" must keep breathing gently forever, not start looping
    the alarm tone just because persistence now reads the same as an alarm's.
    `chime` layers on top: whether it makes any sound at all when it fires -
    an alarm had no way to be silent, so migrating one always sets `chime`
    (True).

    **Outcome logging is unconditional**, unlike the old `dismiss_event`/
    `cleared_event` opt-in fields: cleared logs 1 and missed logs 0, always,
    under `log_as` - the same convention every other template's own log name
    already follows (`StopwatchBehavior.log_as` and friends). `on_cleared`,
    `on_snoozed` and `on_missed` are *additional* actions on top of that log,
    not a replacement for it - "log is an action" turned out to want the
    logging to happen regardless of what the user configured, with the three
    hooks free for whatever else should happen (a webhook, an OSC message).

    **It depends on this host being awake, and its whole point is firing while
    nobody is watching.** If the service stops, the machine sleeps, or BLE
    drops, it does not fire and cannot know that it did not. That is why every
    outcome is logged and why the editor says plainly that this is not a
    safety device. A promise the button cannot keep is worse here than in any
    other app.
    """

    message: str = ""
    label: str = ""
    log_as: str = "notice"  # always logs 1 (cleared) / 0 (missed) here
    timeout_minutes: float = 0.0  # 0 = rings/flashes until answered
    snooze_minutes: float = 0.0  # 0 = no snooze; long_press just clears
    urgent: bool = True  # True: loop the alarm tone, hard ALERT flash.
    chime: bool = True  # whether it makes any sound at all when it fires
    on_cleared: Action | None = None
    on_snoozed: Action | None = None
    on_missed: Action | None = None

    @property
    def template(self) -> str:
        return "notice"


def _default_rungs() -> tuple[ladder.Rung, ...]:
    """The ladder someone has to be able to read across a room: white on the
    ten, yellow on the five, light blue on even seconds, dark blue on odd.

    Chosen so the *rate* tells you the unit before you know the code, and so
    the two most frequent colours are a light/dark pair rather than two hues -
    which survives both this build's warm ring cast (TODO 0c) and a colourblind
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

    One field name serves two meanings: `every_s` counts *seconds* for the
    timers and *beats* for the metronome, where `tick_s` is unused because the
    tempo supplies the cadence. The ladder is unit-agnostic - `ladder.color_at`
    takes a number - so what a rung counts is the consumer's decision, declared
    on the field descriptor in schema.js rather than stored here. One dataclass
    is what lets the parser, the widget and the round-trip be written once.
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

    # A real name, not "": `run_stopwatch` logs unconditionally, so an empty
    # one is not "log nothing" - it files every unnamed stopwatch into one
    # nameless bucket that `total_today("")` then adds up together. Where a
    # blank genuinely means "log nothing" the loop says so (`if
    # behavior.log_as:` in run_signal / run_control / run_launcher).
    log_as: str = "stopwatch"
    # Optional: turn the light into a clock while it runs.
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

    # Named for the same reason the stopwatch's is: `event` is `required` in
    # the editor and run_counter uses it unguarded, so "" writes rows called
    # "" and sums every unnamed counter into one bucket.
    event: str = "counter"
    # Off: the number is today's rows, recounted (`count_today`) - a habit
    # counter, which is what this template has always been and what streaks
    # are built on. On: the number is this mode's document (TODO 34), which
    # keeps counting past midnight and can be written from anywhere by
    # `set_value` - a running total, and a different question.
    #
    # **A flag rather than a second template**, and not a silent change of
    # meaning either: "how many today" and "how many ever" are both things
    # people want from a counter, and the log is written the same way in both
    # cases, so history and streaks work whichever is chosen.
    durable: bool = False

    @property
    def template(self) -> str:
        return "counter"


@dataclass(frozen=True)
class PomodoroBehavior:
    """Alternating work and rest blocks, with a longer rest every
    `blocks_before_long_break`. Handled by main.py's run_pomodoro loop, not
    actions.execute().

    **This is the interval-timer template, and "Pomodoro" is one preset of
    it.** A Pomodoro is 25/5 with a long break every fourth and no end; Tabata
    is 20s/10s for eight rounds; HIIT is 40s/20s. Same machine, different
    numbers, so they ship as `BUILTIN_MODES` entries rather than as three
    templates. The `template` string stays `"pomodoro"` because it is the key
    `MODE_LED_STATES`, schema.js and every existing config are written against.

    **Durations are seconds, and `*_minutes` is still accepted.** The old names
    were unusable for the short end (`work_minutes: 0.667` is not a way to
    write forty seconds), so seconds are canonical and the parser converts the
    legacy names on the way in - "add, don't repurpose" applied to config.

    `advance` decides how much the button asks of you:

        auto        both transitions happen on their own
        manual      every transition waits for a gesture
        break_only  breaks start themselves; going back to work is deliberate

    `gestures` maps a trigger to a POMODORO_COMMANDS entry, so what each
    press does is yours to change - the defaults are toggle / exit / extend.

    `waiting_style` is shown instead of the phase's usual animation whenever
    the timer is not actually running - paused, or a block ended and `advance`
    is waiting for a press. It still wears WORKING's or RESTING's *colour*;
    only the movement changes, exactly like a countdown's ramp borrows TIMING's
    appearance rather than switching state.

    `ramp` walks the colour of whichever block is running, and is **empty by
    default** where a countdown's is not (TODO 19c). The reason is that a
    countdown has one state and nothing else to say with colour, while this
    template has two - WORKING and RESTING are different colours precisely so
    you can tell focus from break at a glance, and a ramp overrides both. So it
    is opt-in: unset, each phase keeps its own look, which is what every
    existing config already does.

    A **named stop list wins over it**, and that is the better answer here for
    the same reason: a look is named per state, so a progress-driven list on
    WORKING leaves RESTING alone. The ramp is the one-field version.
    """

    work_s: float = 25 * 60
    break_s: float = 5 * 60
    long_break_s: float = 15 * 60
    blocks_before_long_break: int = 4
    extend_s: float = 10 * 60  # what `extend` adds
    rounds: int = 0  # 0 = alternate until you leave; a workout sets eight
    # A "get ready" pause before the first work block. Zero for a Pomodoro -
    # you started it deliberately - and ten seconds for anything you have to
    # put the phone down for.
    lead_in_s: float = 0.0
    advance: str = "auto"
    log_as: str = "pomodoro"  # a completed work block is logged under this
    waiting_style: str = "solid"  # frozen, not animated - "not counting"
    # Empty means "each phase keeps its own colour" - see the class docstring.
    ramp: tuple[ramp.Stop, ...] = ()
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
    Raising it is how this mode goes faster - it is *not* the LED's flash
    floor, which the light works around by marking every Nth beat (see
    main.py's run_metronome).
    """

    start_bpm: float = 120.0
    tap_history: int = 8
    reset_gap_s: float = 2.0
    max_bpm: float = 300.0
    sound_on_tap: bool = True
    log_as: str = "metronome"  # a finished session logs its BPM under this
    # Follow a DAW's MIDI clock instead of taps; empty means tap-only. When
    # set, **the clock owns the tempo and tapping no longer changes it** - two
    # things steering one number is how you get a metronome that argues with
    # the session. A tap still marks a beat and still makes its sound. See
    # [midi_clock.py](midi_clock.py) for what arrives on the wire.
    clock_port: str = ""
    # A subdivision ladder counted in **beats**, not seconds: the tempo already
    # decides the timing, what a metronome wants from a colour is an *accent*
    # ("every 4th beat"), and a seconds-based ladder would drift against the
    # tempo the moment you tapped a new one.
    ladder: LadderSpec = field(default_factory=LadderSpec)

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
    everyone to share.
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
class LauncherBehavior:
    """The app launcher: short press cycles the installed apps, **double tap
    launches** the one showing, and long press backs out.

    Launching on a double tap is deliberate: long press still means "up one
    level" here, because a menu where the universal escape gesture instead
    committed you to something would be the single exception to a rule people
    are meant to trust without thinking. See `run_launcher`, authoritative.

    Why it exists at all: an app is reached by an `enter_mode` action bound to
    a gesture, and there are six gestures. Keep one for everyday logging and
    one for leaving and you can reach four - against eleven apps. One gesture
    spent on this reaches all of them.

    `targets` empty means **every takeover mode in config order**, so a newly
    added app appears in the launcher without anyone editing a list. Naming
    them explicitly is how you get a shorter menu or a different order; a name
    that matches nothing is dropped with a warning at run time rather than at
    parse time, because a launcher whose target is defined later in the file is
    the normal case, not an error.

    It owns no LED state (see MODE_LED_STATES): the whole point is that it
    wears the *target's* colour, so the light answers "which app".
    """

    targets: tuple[str, ...] = ()
    # Whether leaving an app returns to the launcher. **On**, because it is
    # what makes long press mean one thing everywhere: up one level. Off makes
    # long press skip a level from inside an app, which is the same gesture
    # meaning two different distances depending on how you got there.
    return_after: bool = True
    log_as: str = ""  # optional: log which app was launched, under this name

    @property
    def template(self) -> str:
        return "launcher"


@dataclass(frozen=True)
class SignalState:
    """One position of a Signal: what it is called, what it looks like, and
    what goes out when you land on it.

    The outbound message is an ordinary `Action`, which is why this template is
    cheap: a position can fire a webhook, an OSC message or a log row without
    this template knowing what any of those are, and a new action primitive
    works here on the day it is added. `None` is a position that only shows a
    colour - "on air" is often just a light.
    """

    name: str
    color: str = "#ffffff"
    style: str = "solid"
    action: Action | None = None


def _default_signal_states() -> tuple[SignalState, ...]:
    """A two-position light, which is the smallest thing that is still a
    signal. Colours only: a default that fired a webhook at somebody's server
    on first press would be a surprising thing to ship."""
    return (
        SignalState(name="Free", color="#00ff00"),
        SignalState(name="Busy", color="#ff0000"),
    )


# A show swaps looks; it does not animate inside one, so the flash floor
# (which governs a look's own rate) cannot see this axis at all. One second
# is already faster than anything a person reads as a scene change.
_MIN_SHOW_DWELL_S = 1.0


@dataclass(frozen=True)
class ShowCue:
    """One scene of a light show: a look from the pool, and how long it holds.

    It **names** a look rather than carrying one, which is the opposite of a
    Signal position and for the opposite reason. A position is a status you
    invented and there is nothing else in the system it could mean, so it
    carries its colour inline. A cue is the whole point of the app - it wants
    the *rich* form, a `sequencer.Sequence` with curves and stops, and that
    only exists in the look pool. Naming one also means a show and a mode can
    share a look, so retuning "Ember" retunes both.
    """

    look: str
    hold_s: float = 0.0  # 0 = use the show's own dwell


@dataclass(frozen=True)
class LightShowBehavior:
    """A light show: a playlist of looks the button walks through.

    **Why this is a template and not a preset.** Everything else here is data
    already - a look can be a stop list, a stop list already fades and holds
    and loops. What no existing template can do is *advance on its own*: a
    Signal light waits for a press, and a look, however long, is one look. A
    show is a sequence of them with a clock, and the clock is the code.

    Gestures follow the house rules: **long press leaves**, short press is the
    next cue, and double tap holds where it is - a show you can freeze on the
    one you liked. Holding stops the clock, not the look: the cue underneath
    carries on animating, because a stop list is a schedule the host is
    already walking.

    It owns no `LEDState` (see `MODE_LED_STATES`). Each cue is pushed as an
    ephemeral effect over LISTENING, exactly as a Signal position is, so the
    show costs no wire code and stores nothing on the device.
    """

    cues: tuple[ShowCue, ...] = ()
    dwell_s: float = 8.0
    auto: bool = True  # False: it only ever moves when you press
    log_as: str = ""  # optional: one row per cue change

    @property
    def template(self) -> str:
        return "lightshow"


@dataclass(frozen=True)
class SignalBehavior:
    """A signal light: short press moves to the next position, and it *stays*
    there. Long press leaves; double tap re-sends the current position.

    **The app whose point is to persist rather than to finish.** Every other
    takeover is doing something and then done; this one is an output device
    that sits there being your status until you change it. The honest cost is
    the "one foreground app" decision becoming visible: while a Signal is
    showing, nothing else on the button is reachable, and long press is what
    releases it.

    Two shapes fall out of one machine, which is why this is one template and
    two presets:

        a status light   Free / Heads-down / On air, firing a webhook
        a footswitch     Stop / Play / Record, firing OSC at a DAW

    See [osc.py](osc.py) for what a footswitch can honestly do over this link -
    not live looping, and the reason why.

    Positions carry their colour inline rather than naming a look, because a
    look is bound to an `LEDState` and these are not states - there can be five
    of them and they mean whatever you say.
    """

    states: tuple[SignalState, ...] = field(default_factory=_default_signal_states)
    start_at: int = 0  # which position it opens on, not counting as a change
    log_as: str = ""  # optional: one row per change, with the position's index

    @property
    def template(self) -> str:
        return "signal"


def _default_hotcold_ramp() -> tuple[ramp.Stop, ...]:
    """Cold to hot - the one colour metaphor nobody has to be taught.

    Five stops rather than two because `ramp.mix` is a straight RGB lerp: blue
    straight to red passes through a muddy grey that reads as "no signal"
    exactly where the game most needs to be legible.
    """
    return ramp.even([
        "#0000ff",  # ice: as wrong as the wheel allows
        "#00ffff",
        "#00ff00",
        "#ffff00",
        "#ff0000",  # dead on
    ])


@dataclass(frozen=True)
class HotColdBehavior:
    """The Hot/Cold game: a hue wheel spins, a press stops it, and the light
    says how close you landed to a target only the button knows.

    The rules are a pure step function in [hotcold.py](hotcold.py), driven by
    main.py's run_hotcold - the shape ROADMAP Stage 3 wants every app in, and
    the reason this one can be tested with numbers instead of a device. What
    lives here is only what the editor stores.

    It owns no LED state (see MODE_LED_STATES): every frame is an ephemeral
    effect it computed, so a palette entry would only ever be the thing briefly
    overwritten before you could read it.

    `tolerance` is measured in the same normalised distance `hotcold.distance`
    returns, where 1.0 is half a turn away. It is not tighter by default
    because the press latency correction leaves tens of milliseconds of
    genuine residual (see hotcold.PRESS_LATENCY_S), and a game that demands
    more precision than the radio can deliver reads as a broken game.
    """

    sweep_s: float = 4.0  # one full turn of the wheel
    rounds: int = 5  # 0 = keep dealing until you leave
    # How many places the wheel has. A continuous wheel (0) turned out to be
    # far harder than it reads on paper - a press is accurate to a few tens of
    # milliseconds and the sweep is four seconds, so the honest target is about
    # one percent of a turn. Twelve places makes "close enough" a real thing
    # without making it free.
    segments: int = 12
    tolerance: float = 0.08
    reveal_s: float = 1.5  # how long the answer stays up
    log_as: str = "hotcold"  # each guess logs its closeness as the value
    ramp: tuple[ramp.Stop, ...] = field(default_factory=_default_hotcold_ramp)

    @property
    def template(self) -> str:
        return "hotcold"


def _default_reaction_ramp() -> tuple[ramp.Stop, ...]:
    """Slow at the left, fast at the right - the ramp is walked by *how well
    you did*, not by how long you took, so the good end is the far end here
    exactly as it is on hot/cold."""
    return ramp.even([
        "#ff0000",  # sluggish
        "#ff8800",
        "#ffff00",
        "#00ff00",  # sharp
    ])


@dataclass(frozen=True)
class ReactionBehavior:
    """The reaction timer: the light goes out, then comes on without warning,
    and the time until you press is logged in milliseconds.

    The rules are a pure step function in [reaction.py](reaction.py), driven by
    main.py's run_reaction. Read that module's header before trusting a number
    off this: the multi-tap window is corrected for, the one-way radio latency
    cannot be, so readings are comparable with each other rather than with a
    stopwatch. It owns no LED state, like the other game.

    `slowest_ms` is only the ramp's far end: a press slower than it is still
    logged honestly, it just cannot look any redder.
    """

    min_delay_s: float = 2.0
    max_delay_s: float = 6.0
    rounds: int = 5  # 0 = keep dealing until you leave
    slowest_ms: float = 600.0
    reveal_s: float = 1.2
    log_as: str = "reaction"  # each attempt logs its milliseconds as the value
    ramp: tuple[ramp.Stop, ...] = field(default_factory=_default_reaction_ramp)

    @property
    def template(self) -> str:
        return "reaction"


Behavior = (
    ActionsBehavior | NoticeBehavior | StopwatchBehavior | CounterBehavior
    | PomodoroBehavior | MetronomeBehavior | CountdownBehavior
    | LauncherBehavior | HotColdBehavior | ReactionBehavior
    | SignalBehavior | ControlBehavior | LightShowBehavior
)

# Which activation types each template accepts (per-template allow-list,
# mirroring schema.js's `allowedActivations`). A mode whose activation type is
# not allowed for its template is skipped at parse time with a warning.
_ALLOWED_ACTIVATIONS = {
    "actions": (AlwaysActivation, WindowActivation),
    # "alarm" and "reminders" are migrated template names (TODO 84) - both
    # parse into NoticeBehavior now, so both need the same allow-list entry
    # `notice` itself uses.
    "alarm": (ScheduleActivation,),
    "reminders": (ScheduleActivation,),
    "notice": (ScheduleActivation,),
    "stopwatch": (ManualActivation,),
    "counter": (ManualActivation,),
    "pomodoro": (ManualActivation,),
    "metronome": (ManualActivation,),
    # Manual throughout below: an app that started itself on a clock time is an
    # app interrupting you, and the one shape that *should* do that (a
    # countdown fired at 07:00) is an alarm, which is already a template.
    "countdown": (ManualActivation,),
    "launcher": (ManualActivation,),
    "hotcold": (ManualActivation,),
    "reaction": (ManualActivation,),
    "signal": (ManualActivation,),
    # An always-on control surface is just an actions mode, which exists.
    "control": (ManualActivation,),
    "lightshow": (ManualActivation,),
}

# Which LED states belong to a *mode* rather than to the button - the split
# CLAUDE.md's "the Lights tab is the button's vocabulary" invariant describes.
# An empty tuple means the app paints every frame itself, so a named look would
# only ever be one wrong frame before it paints over it.
#
# Mirrored by `ledStates` on each template descriptor in schema.js;
# test_webui.py fails if they drift.
MODE_LED_STATES: dict[str, tuple[str, ...]] = {
    "actions": (),  # ambient: it never takes the light over
    # "alarm" and "reminders" are migrated template names (TODO 84), both
    # parsing into NoticeBehavior - same ALERT state as `notice` itself.
    "alarm": (LEDState.ALERT.value,),
    "reminders": (LEDState.ALERT.value,),
    "notice": (LEDState.ALERT.value,),
    "stopwatch": (LEDState.TIMING.value,),
    "counter": (LEDState.COUNTING.value,),
    "pomodoro": (LEDState.WORKING.value, LEDState.RESTING.value),
    "metronome": (LEDState.METRONOME.value,),
    "countdown": (LEDState.TIMING.value,),
    "launcher": (),  # it wears the selected app's colour
    "hotcold": (),
    "reaction": (),
    "signal": (),  # a position's colour is the app's own, not a state
    # Same answer, same reason: a cue's colour is a look it names, and there
    # can be twenty of them. Nothing here is a *state*.
    "lightshow": (),
    # LISTENING is ownable here because a control surface is not only a remote:
    # bind enter_mode and it is a menu of pages, and a menu's job is telling you
    # where you are. A page names a look for the state it sits in between
    # actions and wears it the whole time it is open, at zero wire cost -
    # set_led already resolves the active mode's look, and main.py's `resting()`
    # re-pushes LISTENING after each action's SUCCESS/ERROR flash.
    "control": (LEDState.LISTENING.value,),
}

@dataclass(frozen=True)
class DocSlot:
    """One named value an app of this template may keep (TODO 34).

    **The manifest's precursor.** ARCHITECTURE.md's app package declares its
    document's slots - names, types, defaults - so the size is fixed at
    install time; until packages exist, the template declares them and this
    table is the declaration. When a manifest arrives, this moves into it and
    nothing else about a document changes.

    The default is what the slot reads as before anything writes it, which is
    what lets a document be read like a variable with no first-run branch. It
    also carries the *type*: a bool default is how `DocumentStore.get` knows
    to hand back a flag rather than the 1 sqlite stored.
    """

    name: str
    default: float | str | bool = 0.0
    about: str = ""  # one line, shown by the editor beside the slot


# Which slots each template's document holds. Empty for every app that has
# nothing durable to keep, which is most of them - a document costs nothing
# until a slot is declared.
#
# Mirrored as `docSlots` on each template descriptor in schema.js;
# test_documents.py fails if they drift.
DOC_SLOTS: dict[str, tuple[DocSlot, ...]] = {
    "counter": (
        DocSlot(
            "count", 0.0,
            "The running total, when this counter keeps counting past midnight.",
        ),
    ),
}


# The rest: the button's own vocabulary, which no mode owns. LISTENING is the
# one dual citizen (see MODE_LED_STATES["control"]) and is kept here as well,
# because the ambient layer wears it with no mode involved - deriving it out
# would delete the system default from the Lights tab while it still renders.
SYSTEM_LED_STATES: tuple[str, ...] = tuple(
    state.value
    for state in LEDState
    if state is LEDState.LISTENING
    or not any(state.value in states for states in MODE_LED_STATES.values())
)


# The two lifecycle hooks, in the order they fire. They live on `Mode` rather
# than on each behaviour because there is exactly one pair of moments to hang
# them on and the run loop already owns both (ARCHITECTURE.md, "Composition: an
# app's edges"). One field serves every takeover: adding an app adds no hook.
MODE_HOOKS: tuple[str, ...] = ("on_enter", "on_exit")

# What a hook may be: the fire-and-forget primitives `actions.execute()` runs.
# The three that are missing are the three `main.handle()` keeps for itself -
# `enter_mode`, `readout` and `standby` each change what the *loop* does next,
# and a hook fires beside the loop rather than inside it. `enter_mode` is why
# this is enforced rather than documented: a mode whose on_enter entered
# another mode would be a takeover starting a takeover from inside the moment
# the first one begins, which is what `enter_takeover`'s replace-don't-nest
# rule exists to refuse.
#
# A bare name (`NamedAction`) is allowed and resolved at use time like every
# other binding, so a pool entry that happens to be one of those three fails at
# dispatch the way a dangling name does - clearly, and only for that hook.
# Mirrored as HOOK_ACTIONS in schema.js; test_schema_mirror.py fails on drift.
# The fire-and-forget primitives: everything that does its job and hands the
# button straight back. Named once because three allow-lists are built from it
# and they must not drift apart.
FIRE_AND_FORGET_ACTIONS: tuple[type, ...] = (
    LogAction, TimerToggleAction, WebhookAction, OscAction, MidiAction,
    KeysAction, SetValueAction,
)

# What a step of a `SequenceAction` may be (TODO 33): the primitives, and
# **deliberately not a sequence**. This is where "no nesting" is a fact about
# the data rather than a promise in a comment - see also `resolve_action`,
# which enforces the same thing for a step that names a pooled sequence.
SEQUENCE_ACTIONS: tuple[type, ...] = FIRE_AND_FORGET_ACTIONS

# The two edges TODO 33 says to decide before writing any code, and they are
# enforced by the **parser** rather than by the editor: a config is a file
# people hand-edit, and a limit only the UI knows is not a limit. Both are
# generous for what a sequence is for (a press/release pair, a Stop-Stop, a
# webhook and the MIDI note that goes with it) and small enough that a
# runaway one cannot hold the button for a minute.
MAX_SEQUENCE_STEPS = 8
MAX_SEQUENCE_S = 10.0

HOOK_ACTIONS: tuple[type, ...] = (*FIRE_AND_FORGET_ACTIONS, SequenceAction)

# What a reflex may fire (TODO 71): the hook set, plus `enter_mode`. That one
# difference is the point - a hook fires *beside* the run loop, while a reflex
# is dispatched *by* it, so starting an app is exactly what a reflex is for and
# `enter_takeover` is right there to do it.
#
# `readout` and `standby` stay out for the reason they are out of HOOK_ACTIONS,
# read one step further: each changes what the loop does with the *next
# gesture*, and a circumstance arriving from the network is not a gesture and
# has nobody standing at the button to see the answer.
#
# Mirrored as REFLEX_ACTIONS in schema.js; test_schema_mirror.py fails on drift.
REFLEX_ACTIONS: tuple[type, ...] = (*HOOK_ACTIONS, EnterModeAction, SetPositionAction)


# The operators a reflex's test may use, and the whole list on purpose (TODO
# 72). **One field, one operator, one number** - the moment this grows an `if`
# or an `and` it is a language, and a language is host-only forever (ROADMAP
# D2: the on-device runtime has to be able to evaluate this, and an expression
# parser is not something it will ever have).
#
# Written as functions rather than as a dispatch on the string at use time so
# there is exactly one place a new operator could be added and one place it is
# spelled. Mirrored as REFLEX_OPS in schema.js; test_schema_mirror.py fails on
# drift.
REFLEX_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass(frozen=True)
class ReflexTest:
    """`moisture < 30` - one field of the arriving body, one operator, one
    number. Nothing else, and see `REFLEX_OPS` for why.

    The field is read from the top level of the posted JSON object. Flat, not
    a path: a dotted path is the first half of a query language, and anything
    that can post can flatten what it sends.
    """

    field: str
    op: str
    value: float


@dataclass(frozen=True)
class MidiSource:
    """A reflex fired by a MIDI message arriving on a port (TODO 73).

    **This is a source, not a test.** It says which messages *reach* the
    reflex - this port, this note or controller number, optionally this
    channel - and the message's value is then handed to the ordinary
    `when` test as a payload. That split is why 73 needed no new comparison
    language: `note 95 velocity 127` is this source plus
    `when: velocity == 127`, and the *same* note with velocity 0 is the same
    source and the opposite test.

    It is the reason item 25 stopped being a design problem: a Mackie Control
    is two-way, so "the DAW is recording" arrives as a fact on note 95 rather
    than being inferred from what the button last sent (**derived state beats
    modelled state**).

    `port` is a substring, matched the way every other port name here is -
    Windows renames the port you created. Empty means the first input.
    """

    port: str = ""
    # "note" or "cc". Note covers both note-on and note-off, because a lamp
    # that goes dark can be spelled either way (see midi.decode).
    kind: str = "note"
    number: int = 0
    # 1-16 as the DAW writes it, or None for "any channel", which is the
    # sensible default: a control surface protocol pins the note number and
    # leaves the channel to the DAW's own configuration.
    channel: int | None = None


@dataclass(frozen=True)
class Reflex:
    """A circumstance with an action attached - the button acting with nobody
    pressing anything (TODO 70).

    **A standalone object, not a field on a mode** (ROADMAP D10). Most reflexes
    start no app at all - "when the DAW starts recording, pulse red" enters no
    mode and has no mode to be a field on - and a field could only ever express
    the one case that *is* an app starting.

    The circumstance is, today, an HTTP POST naming this reflex: one hole that
    anything able to make a request can drive, which is what makes a plant
    sensor, a cron job and an iPhone Shortcut the same feature. Later sources
    (MIDI in, OSC in, the media keys) arrive at the same dispatch and add no
    new vocabulary of consequences.
    """

    name: str
    # Inline, or a bare string naming one in the pool (`NamedAction`) - the
    # fifth dispatch site CLAUDE.md says must call `resolve_action`.
    then: Action
    # Limits this reflex to while one named app is running. Optional and rare:
    # a reflex is about the button and the world, not about one app. The JSON
    # key is `while`, which is a Python keyword, hence the field name.
    while_app: str | None = None
    # A test on the value that arrived with it (TODO 72). None means "fire on
    # arrival", which is what a reflex carrying no numbers can do.
    when: ReflexTest | None = None
    # Where it can arrive from, besides its own URL (TODO 73). None means HTTP
    # only; a source *adds* a way in and never removes the endpoint, so a MIDI
    # reflex is still testable with `curl`.
    source: MidiSource | None = None


@dataclass(frozen=True)
class Mode:
    """A named personality: a behaviour template + the activation that turns
    it on. `template` is derived from the behaviour, never stored separately."""

    name: str
    behavior: Behavior
    activation: Activation
    # Which named look this mode wears for each LED state it owns, e.g.
    # {"WORKING": "focus-warm"}. A state left out falls back to the global
    # palette entry. Keys are validated against MODE_LED_STATES for the
    # template; values against the config's look pool.
    looks: dict[str, str] = field(default_factory=dict)
    # Fired as this mode is entered and as it ends (see MODE_HOOKS above).
    # None means nothing happens and nothing costs anything - a mode with no
    # hooks is one `getattr` per session.
    on_enter: Action | None = None
    on_exit: Action | None = None

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
    for that shape stays correct for a template nobody has written yet.
    """
    names: set[str] = set()
    for mode in modes:
        for field_ in fields(mode.behavior):
            value = getattr(mode.behavior, field_.name)
            if isinstance(value, dict):
                names |= {key for key in value if key in TRIGGER_TYPES}
    return names


def _home_mode() -> Mode:
    """The permanent ambient floor: always on, binding the everyday gestures
    to primitives and app launches needing no setup, so a button with no
    config (or a broken one) still does something legible instead of
    erroring on every press.

    Split out from `_default_modes()` so `_ensure_ambient_always` can seed
    exactly this one mode when a hand-edited config is caught with none -
    not the three apps below it, which only a from-scratch config needs.

    It binds three of the six gestures rather than all of them: a longer tap
    costs every shorter one its instant response (see `max_taps_for`), so the
    default config must not spend one nobody asked for."""
    return Mode(
        name="Home",
        activation=AlwaysActivation(),
        behavior=ActionsBehavior(
            actions={
                "short_press": LogAction(event="button_press"),
                "double_tap": EnterModeAction(target="Launcher"),
                "long_press": EnterModeAction(target="Pomodoro"),
            },
        ),
    )


def _default_modes() -> tuple[Mode, ...]:
    """The fail-soft floor a from-scratch config gets: "Home" (see
    `_home_mode`) plus the three apps its own bindings promise to reach, so
    that promise is true the moment the file exists rather than only once
    someone adds those modes by hand.

    double_tap goes to the Launcher rather than straight to an app: a fresh
    config with no launcher binding would fail the Stage-2 gate that every app
    must be reachable without the web UI, and one binding on a launcher reaches
    all of them (`LauncherBehavior.targets` defaults to every takeover mode in
    config order).
    """
    return (
        _home_mode(),
        Mode(name="Launcher", activation=ManualActivation(), behavior=LauncherBehavior()),
        Mode(name="Pomodoro", activation=ManualActivation(), behavior=PomodoroBehavior()),
        Mode(name="Stopwatch", activation=ManualActivation(), behavior=StopwatchBehavior()),
    )


def _has_ambient_always(modes: tuple[Mode, ...]) -> bool:
    """True if `modes` already contains an ambient (`actions`-template) mode
    with an Always activation - the invariant `_ensure_ambient_always`
    maintains."""
    return any(
        mode.template == "actions" and isinstance(mode.activation, AlwaysActivation)
        for mode in modes
    )


def _ensure_ambient_always(modes: tuple[Mode, ...]) -> tuple[Mode, ...]:
    """Guarantee at least one ambient mode with an Always activation exists.

    Structural, not a stored flag: a flag saying "this one is the floor" can be
    hand-deleted exactly like the mode itself, so the parser would need this
    check anyway, and a derived property cannot drift from what the config
    actually contains.

    Every path through `_parse_modes` funnels through here - the "modes" list,
    both legacy migration ladders, and the built-in defaults - so a config that
    deletes or rescopes its only ambient-Always mode gets one back rather than
    leaving the button with no mode to answer a gesture. Scenes are covered
    too: they merge into the raw dict before `parse_config` runs.

    Appended last, at the lowest priority: a seeded Home mode must never shadow
    an ambient mode someone actually configured, only catch gestures nothing
    else claims.
    """
    if _has_ambient_always(modes):
        return modes
    home = _home_mode()
    log.warning(
        "config: no ambient mode has an Always activation - every gesture "
        "would eventually fall through to nothing; adding the default %r mode",
        home.name,
    )
    return modes + (home,)


# --- per-key fallback helpers -------------------------------------------
#
# A bad config never crashes the service: every key falls back on its own and
# says which key and what it should have been, and those same messages reach
# the editor (`parse_with_warnings`). These are the shapes that repeat across
# the template parsers. A key whose complaint has to say something more
# specific than these do still spells its check out inline.

def _is_num(value) -> bool:
    """A real number, never a bool. The bool exclusion is the point: `True` is
    an `int` in Python, so `"channel": true` would otherwise validate as
    channel 1 and play."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_whole(value) -> bool:
    """A whole number, never a bool (see `_is_num`)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_int_in(value, low: int, high: int) -> bool:
    """A whole number inside an inclusive range."""
    return _is_whole(value) and low <= value <= high


def _take(raw: dict, key: str, expected: type, default):
    """A top-level key of the config object, well-typed or the default."""
    if key not in raw:
        return default
    value = raw[key]
    if expected is float:
        if _is_num(value):
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


def _positive(raw: dict, key: str, where: str, default: float) -> float:
    """`raw[key]` as a number greater than zero."""
    value = raw.get(key, default)
    if _is_num(value) and value > 0:
        return float(value)
    log.error("config: %s.%s must be a number > 0 - using %s", where, key, default)
    return default


def _nonneg(raw: dict, key: str, where: str, default: float) -> float:
    """`raw[key]` as a number of zero or more."""
    value = raw.get(key, default)
    if _is_num(value) and value >= 0:
        return float(value)
    log.error("config: %s.%s must be a number >= 0 - using %s", where, key, default)
    return default


def _string(raw: dict, key: str, where: str, default: str) -> str:
    """`raw[key]` as a string; empty is allowed and usually means "not set"."""
    value = raw.get(key, default)
    if isinstance(value, str):
        return value
    log.error("config: %s.%s must be a string - using default", where, key)
    return default


def _nonempty(raw: dict, key: str, where: str, default: str) -> str:
    """`raw[key]` as a string with something in it - for the `log_as`/`event`
    fields a run loop uses unguarded, where "" is not "log nothing" but a
    nameless bucket every unnamed session then adds up together."""
    value = raw.get(key, default)
    if isinstance(value, str) and value:
        return value
    log.error(
        "config: %s.%s must be a non-empty string - using %r", where, key, default
    )
    return default


def _whole(
    raw: dict, key: str, where: str, default: int, minimum: int = 0, note: str = "",
) -> int:
    """`raw[key]` as a whole number of at least `minimum`. `note` says what the
    smallest value means, for the fields where 0 is a mode rather than none."""
    value = raw.get(key, default)
    if _is_whole(value) and value >= minimum:
        return value
    log.error(
        "config: %s.%s must be a whole number >= %s%s - using %s",
        where, key, minimum, note, default,
    )
    return default


def _flag(raw: dict, key: str, where: str, default: bool) -> bool:
    """`raw[key]` as a true/false."""
    value = raw.get(key, default)
    if isinstance(value, bool):
        return value
    log.error("config: %s.%s must be true or false - using default", where, key)
    return default


def _style(raw: dict, key: str, where: str, default: str) -> str:
    """`raw[key]` as one of the LED styles (device.LED_STYLES)."""
    value = raw.get(key, default)
    if isinstance(value, str) and value in LED_STYLES:
        return value
    log.error(
        "config: %s.%s must be one of %s - using %r",
        where, key, "/".join(LED_STYLES), default,
    )
    return default


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
    colour, not the whole state's appearance. This is the shape every other
    config surface follows - CLAUDE.md points new ones here."""
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - using defaults", where)
        return default
    return LedEffect(
        style=_style(raw, "style", where, default.style),
        color=_parse_color(raw.get("color", default.color), f"{where}.color", default.color),
        color2=_parse_color(raw.get("color2", default.color2), f"{where}.color2", default.color2),
        period_s=_positive(raw, "period_s", where, default.period_s),
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
        if not (_is_num(at) and 0.0 <= at <= 1.0):
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


# Which templates can supply each drive's number (TODO 36d). `clock` is absent
# because it needs nothing: a stop list walked by the clock owns its own
# position and renders anywhere. The other two are parameterised from outside
# themselves - a countdown knows how far through it is, a metronome knows what
# beat it is on, and IDLE knows neither. Keyed by template rather than by
# state, which CLAUDE.md explains and `TIMING` forces.
#
# Mirrored as `drives` on each template descriptor in schema.js.
DRIVE_TEMPLATES: dict[str, tuple[str, ...]] = {
    # A Pomodoro joined the countdown once `run_pomodoro` grew a repainting
    # tick (TODO 19c): the drive needs an app that knows how far through it is
    # *and* repaints often enough for the answer to move. Its progress is
    # through the **current block**, so it resets at every phase change - and
    # since a look is named per state, WORKING and RESTING can be driven
    # separately or one of them left alone.
    "progress": ("countdown", "pomodoro"),
    "beats": ("metronome",),
}


def _parse_stop(raw, where: str) -> sequencer.Stop | None:
    """One stop in a sequence: a bare colour, or an object with `color` plus
    optional `hold_s` / `fade_s`.

    Mirrors `_parse_ramp`'s two-tier fallback: an entry of the wrong *shape*
    (not a string or an object) is dropped - `None` here, skipped by the
    caller - while a dict with a bad *field* keeps the stop and falls back
    per field. "One bad stop costs that stop" means the shape rule; a typo in
    `hold_s` costs you a number, not the stop.

    `curve` (the fade's shape) defaults to what every stop written before it
    existed meant, so an old config parses to exactly the sequence it always
    did. A `style`/`period_s` left over from when a hold could animate
    (TODO 36e) is ignored in silence rather than warned about: it is a key we
    used to write ourselves, and shouting at a config for containing what we
    put there is not a fallback, it is a scolding.
    """
    if isinstance(raw, str):
        return sequencer.Stop(_parse_color(raw, where, "#000000"))
    if not isinstance(raw, dict):
        log.error("config: %s must be a colour or an object - ignored", where)
        return None

    curve = raw.get("curve", "linear")
    if curve not in sequencer.CURVES:
        log.error(
            "config: %s.curve must be one of %s - using 'linear'",
            where, "/".join(sequencer.CURVES),
        )
        curve = "linear"

    return sequencer.Stop(
        color=_parse_color(raw.get("color"), f"{where}.color", "#000000"),
        hold_s=_nonneg(raw, "hold_s", where, 0.5),
        fade_s=_nonneg(raw, "fade_s", where, 0.0),
        curve=curve,
    )


def _parse_sequence(raw: dict, where: str, default: LedEffect) -> LedEffect | sequencer.Sequence:
    """`raw["stops"]` as a `sequencer.Sequence` - the stop-list form of a
    look, alongside the plain-effect form `_parse_effect` already handles.

    Falls back to `default` (a plain `LedEffect`, never an invented
    `Sequence`) rather than to some degenerate stop list: a look that fails to
    parse should end up looking like *something* real. That covers both an
    unusable `stops` list and one whose every entry turned out unusable - a
    sequence with nothing left to play is as broken as one that never had
    anything.
    """
    entries = raw.get("stops")
    if not isinstance(entries, list) or not entries:
        log.error(
            "config: %s.stops must be a non-empty list - using the default look", where
        )
        return default

    repeat = _flag(raw, "repeat", where, True)

    stops: list[sequencer.Stop] = []
    for index, entry in enumerate(entries):
        stop = _parse_stop(entry, f"{where}.stops[{index}]")
        if stop is not None:
            stops.append(stop)

    if not stops:
        log.error("config: %s.stops has no usable stops - using the default look", where)
        return default
    drive = raw.get("drive", "clock")
    if drive not in sequencer.DRIVES:
        log.error(
            "config: %s.drive must be one of %s - using 'clock'",
            where, "/".join(sequencer.DRIVES),
        )
        drive = "clock"

    return sequencer.Sequence(stops=tuple(stops), repeat=repeat, drive=drive)


def _parse_look(raw, where: str, default: LedEffect) -> LedEffect | sequencer.Sequence:
    """One look, either shape it may take: a plain effect, or - when `raw` has
    a `stops` key - a stop list.

    The dispatch is that key's presence alone, not a `"type"` field: a look is
    either "the one colour and style it wears" or "the playlist it wears", and
    those two questions have different required keys already.
    """
    if isinstance(raw, dict) and "stops" in raw:
        return _parse_sequence(raw, where, default)
    return _parse_effect(raw, where, default)


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


def _parse_looks(raw) -> dict[str, LedEffect | sequencer.Sequence]:
    """The named-look pool: `{"focus-warm": {...}}`.

    A pool rather than an inline effect per mode, for three reasons that all
    point the same way: two Pomodoros can want different colours, two *modes*
    can want the same colour, and a name is the thing an ephemeral effect
    already pushes down the wire (ROADMAP D4). Empty by default - a pool of
    invented names would be noise.

    A pool entry may be a plain effect or a stop list (`_parse_look`), where
    the system palette stays effect-only (`_parse_palette`): a palette entry
    ships to the device and renders unattended, and a sequence is a schedule
    only the host can walk. One broken look costs you that look, not the pool.
    """
    looks: dict[str, LedEffect | sequencer.Sequence] = {}
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
        looks[name] = _parse_look(entry, f"looks.{name}", LedEffect())
    return looks


def _parse_state_looks(raw, known: dict[str, object]) -> dict[str, str]:
    """The system states' own look names: `{"SUCCESS": "three-blinks"}`.

    A control page can already name a look for LISTENING
    (`MODE_LED_STATES["control"]`); this is that one scope up, letting the
    button's own vocabulary name a pool look instead of being limited to what
    the palette can hold. Which matters because the palette **cannot hold a
    sequence** (`_parse_palette`): naming a look is what lets SUCCESS be
    "green, pause, green, pause, green" rather than "the flash style", while
    the palette entry stays underneath as what a host-less button shows.

    Resolution order ends up: an explicit effect, then the active mode's look,
    then this, then None - which is what `set_led` already means by "use the
    palette". See `look_for`.

    Fail-soft per key, and for a stronger reason than usual: a misnamed look on
    SUCCESS must cost you a colour, never the button's ability to tell you
    something worked.
    """
    entry = raw.get("state_looks")
    if entry is None:
        return {}
    if not isinstance(entry, dict):
        log.error("config: 'state_looks' must be an object - ignored")
        return {}
    chosen: dict[str, str] = {}
    for state, look in entry.items():
        if state not in SYSTEM_LED_STATES:
            log.warning(
                "config: state_looks names %r, which is not one of the button's "
                "own states (%s) - ignored; a mode's own states are named on the "
                "mode", state, "/".join(SYSTEM_LED_STATES),
            )
            continue
        if not (isinstance(look, str) and look in known):
            log.warning(
                "config: state_looks[%r] is %r, which is not in 'looks' - using "
                "the palette colour for %s", state, look, state,
            )
            continue
        entry = known[look]
        if isinstance(entry, sequencer.Sequence) and entry.drive != "clock":
            # No app underneath these at all - they are the button's own
            # states, worn between modes - so nothing could ever supply a
            # progress or a beat. Kept on the clock, like every stranded drive.
            log.warning(
                "config: state_looks[%r] names a %r-driven look, and the "
                "button's own states have no app to supply that - it will play "
                "on the clock instead", state, entry.drive,
            )
        chosen[state] = look
    return chosen


def _parse_action_pool(raw) -> dict[str, Action]:
    """The named-action pool: `{"smoke": {"action": "log", "event": "cig"}}`.

    `_parse_looks` again, key for key: empty by default, per-entry fallback,
    an unusable name dropped with a complaint.

    One rule of its own: **a pool entry may not itself be a name.** Chains
    would need cycle detection to be safe and buy nothing that a second
    binding to the same name does not, so the one-level guarantee is made
    here, where it is cheap, rather than in `resolve_action`, where it would
    be a loop with a counter.
    """
    pool: dict[str, Action] = {}
    if "actions" not in raw:
        return pool
    entries = raw["actions"]
    if not isinstance(entries, dict):
        log.error("config: 'actions' must be an object - ignored")
        return pool
    for name, entry in entries.items():
        if not (isinstance(name, str) and name.strip()):
            log.error("config: actions has an unusable name %r - ignored", name)
            continue
        if isinstance(entry, str):
            log.error(
                "config: actions[%r] is a name rather than an action - a pool "
                "entry cannot reference another one; ignored", name,
            )
            continue
        action = _parse_action(entry, f"actions.{name}")
        if action is not None:
            pool[name] = action
    return pool


def _parse_reflexes(
    raw, actions: set[str], mode_names: set[str]
) -> tuple[Reflex, ...]:
    """The top-level `reflexes` list (TODO 71):

        [{"name": "moisture_low", "then": {"action": "enter_mode", ...}},
         {"name": "deploy_done",  "then": "celebrate", "while": "Focus"}]

    Per-entry fallback like every other list here: one unusable reflex is
    dropped with a complaint and the rest still load.

    Two things are reported and *kept* rather than dropped, because both are
    states a half-finished config passes through. A `then` naming a pool entry
    that does not exist stays dangling, exactly as a gesture's does. A `while`
    naming an app that does not exist stays too: the scope is honoured, so the
    reflex simply never matches, which is the same clear failure a dangling
    `enter_mode` target gives.
    """
    if "reflexes" not in raw:
        return ()
    entries = raw["reflexes"]
    if not isinstance(entries, list):
        log.error("config: 'reflexes' must be a list - ignored")
        return ()
    out: list[Reflex] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"reflexes[{index}]"
        if not isinstance(entry, dict):
            log.error("config: %s must be an object - ignored", where)
            continue
        name = entry.get("name")
        if not (isinstance(name, str) and name.strip()):
            log.error("config: %s has no usable name - ignored", where)
            continue
        name = name.strip()
        if name in seen:
            # The name is what a POST addresses, so two of them is not a style
            # question: one of the pair could never be fired.
            log.error(
                "config: two reflexes are named %r - the second is ignored", name
            )
            continue
        action = _parse_action(entry.get("then"), f"reflexes[{name}].then", actions)
        if action is None:
            log.error("config: reflex %r has no usable action - ignored", name)
            continue
        if not isinstance(action, (*REFLEX_ACTIONS, NamedAction)):
            log.error(
                "config: reflex %r cannot run a %s action - ignored", name,
                type(action).__name__,
            )
            continue
        test = _parse_reflex_test(entry.get("when"), f"reflexes[{name}].when")
        origin = _parse_reflex_source(entry.get("from"), f"reflexes[{name}].from")
        scope = entry.get("while")
        if scope is not None and not (isinstance(scope, str) and scope.strip()):
            log.error("config: %s.while must be an app name - ignored", where)
            scope = None
        elif isinstance(scope, str):
            scope = scope.strip()
            if scope not in mode_names:
                log.warning(
                    "config: reflex %r is limited to app %r, which no mode is "
                    "named - it will never fire until one is", name, scope,
                )
        seen.add(name)
        out.append(Reflex(
            name=name, then=action, while_app=scope, when=test, source=origin,
        ))
    return tuple(out)


def _parse_reflex_source(raw, where: str) -> MidiSource | None:
    """`{"midi": {"port": "Button", "note": 95, "channel": 1}}`, or None.

    Dropping the source keeps the reflex, exactly as a broken test does: the
    URL still fires it, so what is lost is one way in rather than the whole
    thing, and the warning says which.

    `note` and `cc` are separate keys rather than a `kind` field because that
    is how a DAW's own UI asks the question, and naming exactly one of them is
    a shape a person can get right without reading anything.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - ignored, the URL still fires it", where)
        return None
    unknown = set(raw) - {"midi"}
    if unknown:
        log.warning(
            "config: %s has no source called %s - ignored",
            where, ", ".join(sorted(repr(k) for k in unknown)),
        )
    spec = raw.get("midi")
    if spec is None:
        return None
    if not isinstance(spec, dict):
        log.error("config: %s.midi must be an object - ignored", where)
        return None
    has_note, has_cc = "note" in spec, "cc" in spec
    if has_note == has_cc:
        log.error(
            "config: %s.midi needs exactly one of 'note' or 'cc' - ignored", where,
        )
        return None
    kind = "note" if has_note else "cc"
    number = spec.get("note" if has_note else "cc")
    if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= 127:
        log.error("config: %s.midi %s must be 0-127 - ignored", where, kind)
        return None
    channel = spec.get("channel")
    if channel is not None:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 1 <= channel <= 16:
            log.error(
                "config: %s.midi channel must be 1-16 - ignored, any channel "
                "will do", where,
            )
            channel = None
    port = spec.get("port", "")
    if not isinstance(port, str):
        log.error("config: %s.midi port must be a name - using the first input", where)
        port = ""
    return MidiSource(port=port, kind=kind, number=number, channel=channel)


def _parse_reflex_test(raw, where: str) -> ReflexTest | None:
    """`{"field": "moisture", "op": "<", "value": 30}`, or None.

    Every failure here drops the *test* and keeps the reflex, which is the
    one choice worth stating: a broken test that silenced its reflex would
    make a typo look like a sensor that stopped reporting, and a reflex firing
    unconditionally is at least visible. The warning says which it is.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - ignored, the reflex always fires", where)
        return None
    field_name = raw.get("field")
    if not (isinstance(field_name, str) and field_name.strip()):
        log.error("config: %s needs a field name - ignored, the reflex always fires", where)
        return None
    op = raw.get("op")
    if op not in REFLEX_OPS:
        log.error(
            "config: %s has operator %r, which is not one of %s - ignored, the "
            "reflex always fires", where, op, " ".join(REFLEX_OPS),
        )
        return None
    value = raw.get("value")
    # bool is an int in Python and `moisture > true` is nonsense, so it is
    # refused here rather than compared as 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        log.error(
            "config: %s needs a number to compare against - ignored, the "
            "reflex always fires", where,
        )
        return None
    return ReflexTest(field=field_name.strip(), op=op, value=float(value))


def reflex_hears(reflex: Reflex, kind: str, number: int, channel: int) -> bool:
    """Does this reflex's source cover an arriving message?

    The other half of `reflex_matches`, and pure for the same reason: which
    messages *reach* a reflex is a question over data, asked from the run
    loop's `_dispatch_midi` and answerable without a port, a driver or a DAW.

    `kind` is "note" or "cc" - note-on and note-off are one family here,
    because a lamp going dark can be spelled either way (`midi.decode`).
    A source with no channel hears every channel.
    """
    source = reflex.source
    if source is None:
        return False
    if source.kind != kind or source.number != number:
        return False
    return source.channel is None or source.channel == channel


def reflex_matches(reflex: Reflex, payload) -> tuple[bool, float | None]:
    """Does this reflex's test pass, and what number did it read?

    Returns `(fires, value)`. `value` is what arrived in the tested field, or
    None when there was no test or nothing usable in it - and it is returned
    even when the test *fails*, because a reading that did not cross the
    threshold is still a reading and the event log wants it (TODO 72).

    Pure, and here rather than in the endpoint, because every later source of
    circumstances (MIDI in, OSC in) has to apply the same test at its own edge
    and a second implementation is a second answer.

    A reflex with a test and no usable value **does not fire**. The alternative
    - firing when the field is missing - turns a renamed sensor field into an
    alarm that goes off constantly, which is the failure people throw the
    device away over.
    """
    if reflex.when is None:
        return True, None
    if not isinstance(payload, dict):
        return False, None
    raw = payload.get(reflex.when.field)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return False, None
    value = float(raw)
    return REFLEX_OPS[reflex.when.op](value, reflex.when.value), value


def _drive_warning(look, where: str, template: str) -> str | None:
    """Why `look`'s drive cannot be honoured under `template`, or None.

    A `clock` sequence (and any plain effect) is always fine - it owns its own
    position. The other drives need an app to supply the number, and
    `DRIVE_TEMPLATES` says which apps have it.

    Reported, never enforced: the binding is kept and `main.set_led` walks a
    stranded sequence by the clock instead (see its Sequence branch). Dropping
    it would leave the state with no look at all, which is a bigger change to
    what the button does than rendering the same colours on the wrong axis.
    """
    if not isinstance(look, sequencer.Sequence) or look.drive == "clock":
        return None
    allowed = DRIVE_TEMPLATES.get(look.drive, ())
    if template in allowed:
        return None
    return (
        f"config: {where} names a {look.drive!r}-driven look, which only "
        f"{'/'.join(allowed) or 'nothing here'} can supply - it will play on "
        f"the clock instead"
    )


def _parse_mode_looks(
    raw, where: str, template: str, known: dict[str, object],
) -> dict[str, str]:
    """One mode's state -> look-name map, dropping anything unusable.

    Never fatal: a mode whose look is misspelled should light up in its default
    colour and say so, not vanish - a look is cosmetic, and losing the mode
    over one would be wildly disproportionate.

    `known` is the whole pool rather than only its names, because a look's
    *drive* decides whether this template can render it (`_drive_warning`) -
    which is a fact about the look, not about the reference to it.
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
        if (complaint := _drive_warning(known[look], f"{where}.looks[{state!r}]", template)):
            log.warning("%s", complaint)
        chosen[state] = look
    return chosen


def _parse_hooks(
    raw, where: str, template: str, actions: set[str] | None,
) -> dict[str, Action]:
    """One mode's `on_enter` / `on_exit` actions, dropping anything unusable.

    Never fatal, for the reason `_parse_mode_looks` gives just above: a hook is
    something the mode does *around* itself, so a bad one is dropped with a
    warning and the mode runs without it.

    `actions` is the pool's names, handed through so a hook naming something
    absent is reported at load like every other reference.
    """
    chosen: dict[str, Action] = {}
    for key in MODE_HOOKS:
        if raw.get(key) is None:
            continue
        action = _parse_action(raw[key], f"{where}.{key}", actions)
        if action is None:
            continue  # _parse_action has already said why
        if not isinstance(action, (*HOOK_ACTIONS, NamedAction)):
            log.error(
                "config: %s.%s is a %r action, which a hook cannot run - it "
                "changes what the mode loop does next rather than the world "
                "outside it; ignored",
                where, key, raw[key].get("action") if isinstance(raw[key], dict) else raw[key],
            )
            continue
        if template == "actions":
            # Kept rather than dropped: it round-trips, and the fix is to change
            # the template rather than to lose what was written. But an everyday
            # mode is never entered or left, so nothing will ever fire it - and
            # a hook that silently does nothing is what a load warning is for.
            log.warning(
                "config: %s.%s is on an everyday (actions) mode, which is "
                "never entered or left - the hook will never fire", where, key,
            )
        chosen[key] = action
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
    # Named looks a mode can wear instead of the palette entry for the state it
    # is showing (see `look_for`). Empty means every mode uses the palette. A
    # look is a plain effect or a stop list - see `_parse_looks`.
    looks: dict[str, LedEffect | sequencer.Sequence] = field(default_factory=dict)
    # Named actions a gesture can reference instead of holding one inline (see
    # `resolve_action`). Naming is optional by design: this is for the action
    # used in three places, not for the one used once.
    actions: dict[str, Action] = field(default_factory=dict)
    # Circumstances with an action attached, fired by something other than a
    # finger (see `Reflex`). A list rather than a dict because order is how a
    # person reads them and nothing looks one up by position; the name is the
    # key over HTTP.
    reflexes: tuple[Reflex, ...] = ()
    # A look the button's own states wear instead of their palette entry (see
    # `_parse_state_looks`). The palette stays underneath either way, as what a
    # host-less button shows.
    state_looks: dict[str, str] = field(default_factory=dict)
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


# --- parsing ------------------------------------------------------------

def _parse_action_sequence(
    raw: dict, where: str, known: set[str] | None,
) -> SequenceAction | None:
    """A flat list of actions with optional delays (TODO 33):

        {"action": "sequence", "steps": [
            {"action": "midi", "kind": "note_on", "number": 95, "value": 127},
            {"action": "midi", "kind": "note_on", "number": 95, "value": 0,
             "wait_s": 0.05}]}

    A step is an ordinary action object, which may carry `wait_s`, or a bare
    string naming a pooled one. **A named step has no delay** and that is not
    an omission: a string has nowhere to put one, and inventing a wrapper
    object for the case would be a second step shape to read and to write.

    **The limits are enforced here, not in the editor** (`MAX_SEQUENCE_STEPS`,
    `MAX_SEQUENCE_S`). A config is a file people hand-edit; a bound only the UI
    knows is not a bound. Over either limit the list is *truncated* with a
    warning rather than rejected, which is the same call every other list here
    makes: what was written up to that point still does what it says.
    """
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        log.error("config: %s needs a non-empty 'steps' list - ignored", where)
        return None
    steps: list[SequenceStep] = []
    budget = MAX_SEQUENCE_S
    for index, entry in enumerate(steps_raw):
        if len(steps) >= MAX_SEQUENCE_STEPS:
            log.warning(
                "config: %s has more than %d steps - the rest are dropped",
                where, MAX_SEQUENCE_STEPS,
            )
            break
        wait_s = 0.0
        if isinstance(entry, dict):
            # Refused by name before parsing, so the message says what is
            # actually wrong rather than "unknown action". Nesting is the one
            # thing that would turn this into something the device cannot run.
            if entry.get("action") == "sequence":
                log.error(
                    "config: %s step %d is itself a sequence - dropped, "
                    "sequences do not nest", where, index + 1,
                )
                continue
            raw_wait = entry.get("wait_s", 0)
            if isinstance(raw_wait, bool) or not isinstance(raw_wait, (int, float)):
                log.error(
                    "config: %s step %d wait_s must be a number - using 0",
                    where, index + 1,
                )
            elif raw_wait < 0:
                log.error(
                    "config: %s step %d cannot wait for less than nothing - "
                    "using 0", where, index + 1,
                )
            else:
                wait_s = float(raw_wait)
        action = _parse_action(entry, f"{where}.steps[{index}]", known)
        if action is None:
            continue  # _parse_action has already said why
        if not isinstance(action, (*SEQUENCE_ACTIONS, NamedAction)):
            log.error(
                "config: %s step %d cannot be a %s - dropped; a step does its "
                "job and hands the button back", where, index + 1,
                type(action).__name__,
            )
            continue
        if wait_s > budget:
            log.warning(
                "config: %s waits longer than the %.0fs a sequence may take - "
                "step %d trimmed", where, MAX_SEQUENCE_S, index + 1,
            )
            wait_s = budget
        budget -= wait_s
        steps.append(SequenceStep(action=action, wait_s=wait_s))
        if budget <= 0 and index < len(steps_raw) - 1:
            log.warning(
                "config: %s has spent its %.0fs - the steps after %d are "
                "dropped", where, MAX_SEQUENCE_S, index + 1,
            )
            break
    if not steps:
        log.error("config: %s has no usable steps - ignored", where)
        return None
    return SequenceAction(steps=tuple(steps))


def _parse_action(raw, where: str, known: set[str] | None = None) -> Action | None:
    """One gesture's action: an inline object, or a bare string naming one in
    the pool (`AppConfig.actions`).

    `known` is the pool's names, passed at every call site that has one in
    scope, so a misspelled reference is reported at load instead of at the
    moment the gesture failed to do anything. It is only ever a warning; the
    reference is kept either way (see `NamedAction`). The legacy migration
    ladders pass nothing, because a v0.1 config predates the pool.
    """
    if isinstance(raw, str):
        if not raw.strip():
            log.error("config: %s is an empty action name - ignored", where)
            return None
        if known is not None and raw not in known:
            log.warning(
                "config: %s names action %r, which is not in 'actions' - it "
                "does nothing until one exists", where, raw,
            )
        return NamedAction(name=raw)
    if not isinstance(raw, dict):
        log.error("config: %s must be an object or an action name - ignored", where)
        return None
    # Legacy v0.1 command entries have no "action" key, just prompt/label.
    kind = raw.get("action", "prompt" if "prompt" in raw else None)
    if kind == "sequence":
        # `_parse_action_sequence`, not `_parse_sequence`: that name was taken
        # by the *stop list* parser above, and a look and an action are two
        # different things that both call themselves a sequence here.
        return _parse_action_sequence(raw, where, known)
    elif kind == "set_position":
        target = raw.get("name")
        if isinstance(target, str) and target.strip():
            return SetPositionAction(name=target.strip())
    elif kind == "set_value":
        app = raw.get("app")
        slot = raw.get("slot")
        op = raw.get("op", "add")
        value = raw.get("value", 1)
        if not (isinstance(app, str) and app.strip()):
            log.error("config: %s.app must name an app - ignored", where)
        elif not (isinstance(slot, str) and slot.strip()):
            log.error("config: %s.slot must name a value to write - ignored", where)
        elif op not in SET_VALUE_OPS:
            log.error(
                "config: %s.op must be one of %s - ignored",
                where, ", ".join(SET_VALUE_OPS),
            )
        elif not isinstance(value, (int, float, str, bool)):
            # The same three kinds a summary carries, and refused for the same
            # reason: a document holds scalars, and a dict stored as its repr
            # is a value that reads back wrong forever.
            log.error(
                "config: %s.value must be a number, a word or true/false - "
                "ignored", where,
            )
        elif op == "add" and isinstance(value, (str, bool)):
            # Caught here rather than at write time: "add the word 'five'" is
            # a mistake the editor should hear about, and discovering it when
            # somebody presses the button is too late. Same call the osc
            # branch makes about a malformed address.
            log.error("config: %s cannot add %r to anything - ignored", where, value)
        else:
            return SetValueAction(
                app=app.strip(), slot=slot.strip(), op=op, value=value,
            )
    elif kind == "log":
        event = raw.get("event")
        if isinstance(event, str) and event:
            return LogAction(event=event)
    elif kind == "readout":
        event = raw.get("event")
        if isinstance(event, str) and event:
            defaults = ReadoutAction(event=event)
            return ReadoutAction(
                event=event,
                tens_color=_parse_color(
                    raw.get("tens_color", defaults.tens_color),
                    f"{where}.tens_color", defaults.tens_color,
                ),
                units_color=_parse_color(
                    raw.get("units_color", defaults.units_color),
                    f"{where}.units_color", defaults.units_color,
                ),
            )
    elif kind == "standby":
        # No fields: it is a toggle, and which way it goes is session state
        # the run loop holds rather than anything a config can say.
        return StandbyAction()
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
    elif kind == "osc":
        host = raw.get("host", "127.0.0.1")
        port = raw.get("port")
        address = raw.get("address")
        args = raw.get("args", [])
        if (
            isinstance(host, str)
            and host
            and _is_int_in(port, 1, 65535)
            and isinstance(address, str)
            and address.startswith("/")
            and isinstance(args, list)
        ):
            return OscAction(
                host=host, port=port, address=address, args=tuple(args)
            )
        # Nothing is guessed here, unlike osc.message's leading slash: an
        # address is the one field where a typo silently reaches the wrong
        # handler on the receiving end, so a malformed one is dropped loudly
        # rather than repaired quietly.
    elif kind == "midi":
        port = raw.get("port", "")
        channel = raw.get("channel", 1)
        midi_kind = raw.get("kind", midi.NOTE_ON)
        number = raw.get("number")
        value = raw.get("value", 127)
        # Ranges are checked here even though midi.message clamps, for the
        # reason the osc branch drops a bad address: a config asking for
        # channel 17 is a mistake the editor should be told about, and
        # silently sending it on channel 16 would be a lie that plays.
        if (
            isinstance(port, str)
            and midi_kind in midi.KINDS
            and _is_int_in(channel, midi.CHANNEL_MIN, midi.CHANNEL_MAX)
            and _is_int_in(number, midi.DATA_MIN, midi.DATA_MAX)
            and _is_int_in(value, midi.DATA_MIN, midi.DATA_MAX)
        ):
            return MidiAction(
                port=port, channel=channel, kind=midi_kind,
                number=number, value=value,
            )
    elif kind == "keys":
        combo = raw.get("combo", "")
        click = raw.get("click", "")
        # The vocabulary is checked here rather than at send time for the
        # reason the osc branch checks its address: the editor should be told
        # about a key this build cannot press, and discovering it when someone
        # presses the button is too late.
        if (
            isinstance(combo, str)
            and isinstance(click, str)
            and (combo or click)
            and (not combo or keys.parse_combo(combo) is not None)
            and (not click or click in keys.CLICKS)
        ):
            return KeysAction(combo=combo, click=click)
    elif kind == "enter_mode":
        # The target is validated as a non-empty string only; whether a
        # takeover mode by that name actually exists is left to the runtime
        # (forward references / config ordering - see EnterModeAction).
        target = raw.get("target")
        if isinstance(target, str) and target:
            return EnterModeAction(target=target)
    elif kind == "alarm":
        # Removed: an alarm is a template now, and this cannot be migrated
        # inline because a gesture has no fire time - see _migrate_rule.
        log.error(
            "config: %s uses the removed 'alarm' action - alarms are now an "
            "alarm-template mode; ignored", where,
        )
        return None
    elif kind == "prompt":
        # The on-device AI went with the Pi build (DESIGN-ESP32.md), so there is
        # nothing to send a prompt to. Named rather than left to fall through as
        # a generic "not a valid action".
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


def _parse_actions_body(
    raw: dict, where: str, name: str, known: set[str] | None = None,
) -> ActionsBehavior | None:
    """Parse the flat actions-template fields. An invalid action is dropped
    individually; a mode left with zero valid gesture actions is skipped.

    A binding that merely *names* a missing action is not invalid and does not
    count against that rule: it is a reference the pool has yet to fill, and
    losing the mode over one would be exactly the silent rewrite
    `NamedAction` exists to avoid."""
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
            action = _parse_action(raw[trigger], f"{where}.{trigger}", known)
            if action is not None:
                actions[trigger] = action
    if not actions:
        log.error("config: %s (%r) has no valid gesture actions - skipped", where, name)
        return None
    return ActionsBehavior(actions=actions, unless_logged_today=unless_logged_today)


def _parse_control_positions(
    raw, where: str, looks: dict[str, object],
) -> tuple[ControlPosition, ...]:
    """A control surface's positions, dropping anything unusable rather than
    the surface.

    `_parse_show_cues` one template over, with its dangling-reference rule
    intact: a position naming a look that is not in the pool is **kept and
    warned about**, because a missing look is far more often a rename than a
    mistake, and dropping the position would renumber a list somebody is
    looking at. The run loop falls back to the page's own look and says so.
    """
    if not isinstance(raw, list):
        if raw is not None:
            log.error("config: %s.positions must be a list - using none", where)
        return ()
    positions: list[ControlPosition] = []
    for index, entry in enumerate(raw):
        at = f"{where}.positions[{index}]"
        if not isinstance(entry, dict):
            log.error("config: %s must be an object - skipped", at)
            continue
        name = entry.get("name")
        if not (isinstance(name, str) and name):
            log.error("config: %s.name must be a non-empty string - skipped", at)
            continue
        look = entry.get("look", "")
        if not isinstance(look, str):
            log.error("config: %s.look must be a look name - ignored", at)
            look = ""
        if look and look not in looks:
            log.warning("config: %s names look %r, which does not exist", at, look)
        positions.append(ControlPosition(name=name, look=look))
    return tuple(positions)


def _parse_control_body(
    raw: dict, where: str, name: str, known: set[str] | None = None,
    looks: dict[str, object] | None = None,
) -> ControlBehavior | None:
    """Parse a control surface: the same gesture map as an actions mode, minus
    the long press.

    A bound `long_press` is dropped with a warning rather than honoured - it is
    how you leave every takeover, and an app that ate it would strand you
    inside itself with no gesture left to say so.

    `positions` is optional and orthogonal to the map: it changes what the
    page *shows* between commands, never what a gesture does. That is TODO 78,
    and keeping the two apart is why the light half could ship alone.
    """
    defaults = ControlBehavior(actions={})
    actions: dict[str, Action] = {}
    for trigger in TRIGGER_TYPES:
        if trigger not in raw:
            continue
        if trigger == "long_press":
            log.error(
                "config: %s.long_press is how you leave a control surface and "
                "cannot be bound - ignored", where,
            )
            continue
        action = _parse_action(raw[trigger], f"{where}.{trigger}", known)
        if action is not None:
            actions[trigger] = action
    if not actions:
        log.error("config: %s (%r) has no valid gesture actions - skipped", where, name)
        return None
    return ControlBehavior(
        actions=actions,
        log_as=_string(raw, "log_as", where, defaults.log_as),
        return_after=_flag(raw, "return_after", where, defaults.return_after),
        positions=_parse_control_positions(raw.get("positions"), where, looks or {}),
    )


def _parse_notice_body(
    raw: dict, where: str, template: str, name: str, actions: set[str] | None = None,
) -> NoticeBehavior:
    """Parse the flat notice-template fields, each falling back per-key.

    Also the migration path for the old `alarm` and `reminders` template
    names (TODO 84): each branch reads its own legacy field names into the
    same `NoticeBehavior`, so a config written before the merge loads and
    behaves unchanged. `urgent` and `chime` are not user-configurable when
    migrating - an alarm always rendered urgently, a reminder never did, and
    that must stay a fact about which template a mode used to be, not a
    default that a `timeout_minutes` value could be misread into.
    """
    defaults = NoticeBehavior()
    message = _string(raw, "message", where, defaults.message)
    label = _string(raw, "label", where, defaults.label)
    snooze = _nonneg(raw, "snooze_minutes", where, defaults.snooze_minutes)

    if template == "alarm":
        timeout = _nonneg(raw, "grace_minutes", where, 0.0)
        urgent = True
        chime = True
        explicit_log = _string(raw, "dismiss_event", where, "")
        on_missed = (
            _parse_action(raw["on_timeout"], f"{where}.on_timeout", actions)
            if raw.get("on_timeout") is not None else None
        )
        on_cleared = None
        on_snoozed = None
    elif template == "reminders":
        timeout = _nonneg(raw, "timeout_minutes", where, 5.0)
        snooze = 0.0  # a reminder never offered one - stray key, ignored as before
        urgent = False
        chime = _flag(raw, "chime", where, True)
        explicit_log = _string(raw, "cleared_event", where, "")
        on_missed = None
        on_cleared = None
        on_snoozed = None
    else:
        timeout = _nonneg(raw, "timeout_minutes", where, defaults.timeout_minutes)
        urgent = _flag(raw, "urgent", where, defaults.urgent)
        chime = _flag(raw, "chime", where, defaults.chime)
        explicit_log = _string(raw, "log_as", where, "")
        on_cleared = (
            _parse_action(raw["on_cleared"], f"{where}.on_cleared", actions)
            if raw.get("on_cleared") is not None else None
        )
        on_snoozed = (
            _parse_action(raw["on_snoozed"], f"{where}.on_snoozed", actions)
            if raw.get("on_snoozed") is not None else None
        )
        on_missed = (
            _parse_action(raw["on_missed"], f"{where}.on_missed", actions)
            if raw.get("on_missed") is not None else None
        )

    # Outcome logging is unconditional (TODO 84) - no opt-in field to remember.
    # A config that already named its event (dismiss_event/cleared_event/
    # log_as) keeps that exact name and its history; one that didn't gets the
    # mode's own name, which is the closest thing to "log it with the alarm's
    # name" for a mode nobody configured this on.
    log_as = explicit_log or name

    if on_missed is not None and not timeout:
        log.warning(
            "config: %s sets on_missed but timeout_minutes is 0 - it will "
            "never fire, because this notice rings/flashes until answered", where,
        )

    return NoticeBehavior(
        message=message, label=label, log_as=log_as,
        timeout_minutes=timeout, snooze_minutes=snooze,
        urgent=urgent, chime=chime,
        on_cleared=on_cleared, on_snoozed=on_snoozed, on_missed=on_missed,
    )


def _parse_ladder(raw, where: str) -> LadderSpec:
    """One subdivision ladder, each key falling back on its own: a bad rung
    costs you that rung, a bad tick costs you the tick, and neither costs you
    the mode.

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

    enabled = _flag(raw, "enabled", where, defaults.enabled)
    tick = _positive(raw, "tick_s", where, defaults.tick_s)
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
    return LadderSpec(enabled=enabled, tick_s=tick, base=base, rungs=rungs)


def _parse_rungs(entries: list, where: str):
    """Each rung independently; an unusable one is dropped with a warning."""
    for index, entry in enumerate(entries):
        at = f"{where}.rungs[{index}]"
        if not isinstance(entry, dict):
            log.error("config: %s must be an object - dropped", at)
            continue
        every = entry.get("every_s")
        if not (_is_num(every) and every > 0):
            log.error("config: %s.every_s must be a number > 0 - dropped", at)
            continue
        # A rung with no readable colour is dropped rather than defaulted:
        # unlike `base`, there is no sensible colour to substitute, and a rung
        # silently becoming black would look exactly like the off-beat.
        color = _parse_color(entry.get("color"), f"{at}.color", "")
        if not color:
            continue
        yield ladder.Rung(every_s=float(every), color=color)


def _parse_launcher_body(raw: dict, where: str) -> LauncherBehavior:
    """Parse the flat launcher fields, each falling back per-key.

    `targets` accepts a newline-separated **string** as well as a list, which
    is not a convenience: the editor's field for it is a textarea, so it writes
    a string, and accepting only a list meant that opening a launcher in the
    web UI and saving turned a curated menu into "offer every app" - with an
    error in the log and nothing at all in the UI. `_parse_show_cues` already
    took both shapes for exactly this reason and said so in a comment pointing
    here; this is that comment being acted on (TODO 47's fix pass).
    """
    defaults = LauncherBehavior()

    targets = raw.get("targets", defaults.targets)
    if isinstance(targets, str):
        # One mode name per line, blanks dropped. An all-whitespace box means
        # an empty list, which is what the field's own hint promises: blank
        # offers every app.
        targets = [line.strip() for line in targets.splitlines() if line.strip()]
    if isinstance(targets, (list, tuple)):
        named = [t for t in targets if isinstance(t, str) and t]
        if len(named) != len(targets):
            log.error(
                "config: %s.targets must be a list of mode names - dropped %d bad entry(s)",
                where, len(targets) - len(named),
            )
        targets = tuple(named)
    else:
        log.error("config: %s.targets must be a list - offering every app", where)
        targets = defaults.targets

    return LauncherBehavior(
        targets=targets,
        return_after=_flag(raw, "return_after", where, defaults.return_after),
        log_as=_string(raw, "log_as", where, defaults.log_as),
    )


def _parse_stopwatch_body(raw: dict, where: str) -> StopwatchBehavior:
    """Parse the flat stopwatch-template fields, falling back per-key."""
    defaults = StopwatchBehavior()
    return StopwatchBehavior(
        log_as=_string(raw, "log_as", where, defaults.log_as),
        ladder=_parse_ladder(raw.get("ladder"), f"{where}.ladder"),
    )


def _parse_counter_body(raw: dict, where: str) -> CounterBehavior:
    """Parse the flat counter-template fields, falling back per-key."""
    defaults = CounterBehavior()
    return CounterBehavior(
        event=_string(raw, "event", where, defaults.event),
        durable=_flag(raw, "durable", where, defaults.durable),
    )


def _parse_pomodoro_body(raw: dict, where: str) -> PomodoroBehavior:
    """Parse the flat pomodoro-template fields, falling back per key. A bad
    duration costs you that duration, not the whole mode."""
    defaults = PomodoroBehavior()

    def duration(key: str, default: float) -> float:
        """Seconds under `<key>_s`, or the legacy `<key>_minutes`.

        The legacy name is read only when the seconds one is absent, so a
        config carrying both (a hand-edit mid-migration) resolves to the
        canonical field rather than to whichever the parser tried second.
        """
        seconds_key, minutes_key = f"{key}_s", f"{key}_minutes"
        if seconds_key in raw:
            value, name, scale = raw[seconds_key], seconds_key, 1.0
        elif minutes_key in raw:
            value, name, scale = raw[minutes_key], minutes_key, 60.0
        else:
            return default
        if _is_num(value) and value > 0:
            return float(value) * scale
        log.error(
            "config: %s.%s must be a number > 0 - using %s seconds",
            where, name, default,
        )
        return default

    rounds = _whole(
        raw, "rounds", where, defaults.rounds, note=" (0 = until you leave)"
    )
    lead_in = _nonneg(raw, "lead_in_s", where, defaults.lead_in_s)
    blocks = _whole(
        raw, "blocks_before_long_break", where,
        defaults.blocks_before_long_break, minimum=1,
    )

    advance = raw.get("advance", defaults.advance)
    if not (isinstance(advance, str) and advance in POMODORO_ADVANCE):
        log.error(
            "config: %s.advance must be one of %s - using %r",
            where, "/".join(POMODORO_ADVANCE), defaults.advance,
        )
        advance = defaults.advance

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
        work_s=duration("work", defaults.work_s),
        break_s=duration("break", defaults.break_s),
        long_break_s=duration("long_break", defaults.long_break_s),
        blocks_before_long_break=blocks,
        extend_s=duration("extend", defaults.extend_s),
        rounds=rounds,
        lead_in_s=lead_in,
        advance=advance,
        log_as=_nonempty(raw, "log_as", where, defaults.log_as),
        waiting_style=_style(raw, "waiting_style", where, defaults.waiting_style),
        # Only parsed when it is there. `_parse_ramp` refuses an empty list, so
        # letting it see an absent key would complain about every Pomodoro ever
        # written - and "no ramp" is this template's default, not an error.
        ramp=_parse_ramp(raw["ramp"], f"{where}.ramp", ()) if "ramp" in raw else (),
        gestures=gestures,
    )


def _parse_metronome_body(raw: dict, where: str) -> MetronomeBehavior:
    """Parse the flat metronome-template fields, falling back per key. A bad
    tempo costs you that tempo, not the whole mode."""
    defaults = MetronomeBehavior()

    start_bpm = _positive(raw, "start_bpm", where, defaults.start_bpm)
    max_bpm = _positive(raw, "max_bpm", where, defaults.max_bpm)
    if start_bpm > max_bpm:
        # Not a fallback but a reconciliation: both values parsed fine, they
        # just disagree. Lifting the ceiling keeps the tempo the user actually
        # asked to start at, rather than silently slowing them down.
        log.warning(
            "config: %s.start_bpm (%s) is above max_bpm (%s) - raising max_bpm to match",
            where, start_bpm, max_bpm,
        )
        max_bpm = start_bpm

    clock_port = raw.get("clock_port", defaults.clock_port)
    if not isinstance(clock_port, str):
        log.error("config: %s.clock_port must be a string - using tap tempo", where)
        clock_port = defaults.clock_port

    return MetronomeBehavior(
        start_bpm=start_bpm,
        # Two taps is one interval - the least you can average anything over.
        tap_history=_whole(raw, "tap_history", where, defaults.tap_history, minimum=2),
        reset_gap_s=_positive(raw, "reset_gap_s", where, defaults.reset_gap_s),
        max_bpm=max_bpm,
        sound_on_tap=_flag(raw, "sound_on_tap", where, defaults.sound_on_tap),
        log_as=_nonempty(raw, "log_as", where, defaults.log_as),
        clock_port=clock_port,
        ladder=_parse_ladder(raw.get("ladder"), f"{where}.ladder"),
    )


def _parse_countdown_body(raw: dict, where: str) -> CountdownBehavior:
    """Parse the flat countdown-template fields, falling back per key."""
    defaults = CountdownBehavior()
    return CountdownBehavior(
        minutes=_positive(raw, "minutes", where, defaults.minutes),
        label=_string(raw, "label", where, defaults.label),
        style=_style(raw, "style", where, defaults.style),
        period_s=_positive(raw, "period_s", where, defaults.period_s),
        ramp=_parse_ramp(raw["ramp"], f"{where}.ramp", defaults.ramp)
        if "ramp" in raw else defaults.ramp,
        ring_on_finish=_flag(raw, "ring_on_finish", where, defaults.ring_on_finish),
        log_as=_nonempty(raw, "log_as", where, defaults.log_as),
        ladder=_parse_ladder(raw.get("ladder"), f"{where}.ladder"),
    )


def _parse_hotcold_body(raw: dict, where: str) -> HotColdBehavior:
    """Parse the flat hot/cold fields, falling back per key."""
    defaults = HotColdBehavior()

    # Tolerance is bounded above by 1.0 because that is *half a turn* in the
    # normalised distance hotcold.distance returns - a tolerance of 1 already
    # means every guess is a hit, and anything beyond it is the same game with
    # a number that lies about how generous it is.
    tolerance = raw.get("tolerance", defaults.tolerance)
    if not (_is_num(tolerance) and 0 < tolerance <= 1.0):
        log.error(
            "config: %s.tolerance must be a number > 0 and <= 1 - using %s",
            where, defaults.tolerance,
        )
        tolerance = defaults.tolerance

    return HotColdBehavior(
        sweep_s=_positive(raw, "sweep_s", where, defaults.sweep_s),
        rounds=_whole(
            raw, "rounds", where, defaults.rounds, note=" (0 = until you leave)"
        ),
        segments=_whole(
            raw, "segments", where, defaults.segments, note=" (0 = a smooth wheel)"
        ),
        tolerance=float(tolerance),
        reveal_s=_positive(raw, "reveal_s", where, defaults.reveal_s),
        log_as=_nonempty(raw, "log_as", where, defaults.log_as),
        ramp=_parse_ramp(raw["ramp"], f"{where}.ramp", defaults.ramp)
        if "ramp" in raw else defaults.ramp,
    )


def _parse_signal_body(
    raw: dict, where: str, known: set[str] | None = None,
) -> SignalBehavior:
    """Parse the Signal template, falling back per key and per position.

    A broken position costs that position, not the mode - and a mode left with
    no positions at all falls back to the defaults rather than being dropped,
    because a signal light with nothing to show is the one shape that would
    take over the button and then do nothing.
    """
    defaults = SignalBehavior()

    entries = raw.get("states", None)
    states: list[SignalState] = []
    if entries is None:
        states = list(defaults.states)
    elif not isinstance(entries, list):
        log.error("config: %s.states must be a list - using the defaults", where)
        states = list(defaults.states)
    else:
        for index, entry in enumerate(entries):
            spot = f"{where}.states[{index}]"
            if not isinstance(entry, dict):
                log.error("config: %s must be an object - skipped", spot)
                continue
            name = entry.get("name")
            if not (isinstance(name, str) and name):
                log.error("config: %s.name must be a non-empty string - skipped", spot)
                continue
            action = None
            if entry.get("action") is not None:
                # A broken message costs the message, not the position: a
                # status light whose webhook has a typo should still light up.
                action = _parse_action(entry["action"], f"{spot}.action", known)
            states.append(SignalState(
                name=name,
                color=_parse_color(entry.get("color"), f"{spot}.color", "#ffffff"),
                style=_style(entry, "style", spot, "solid"),
                action=action,
            ))
        if not states:
            log.error(
                "config: %s.states left nothing usable - using the defaults", where,
            )
            states = list(defaults.states)

    start_at = raw.get("start_at", defaults.start_at)
    if not (_is_whole(start_at) and 0 <= start_at < len(states)):
        log.error(
            "config: %s.start_at must be a whole number from 0 to %s - using 0",
            where, len(states) - 1,
        )
        start_at = 0

    return SignalBehavior(
        states=tuple(states),
        start_at=start_at,
        log_as=_string(raw, "log_as", where, defaults.log_as),
    )


def _parse_reaction_body(raw: dict, where: str) -> ReactionBehavior:
    """Parse the flat reaction-timer fields, falling back per key."""
    defaults = ReactionBehavior()

    minimum = _positive(raw, "min_delay_s", where, defaults.min_delay_s)
    maximum = _positive(raw, "max_delay_s", where, defaults.max_delay_s)
    if maximum < minimum:
        # Swapped rather than rejected: the pair is obviously meant as a range,
        # and picking a delay out of an inverted one would hang on the first
        # round with nothing on screen to explain why.
        log.error(
            "config: %s.max_delay_s (%s) is below min_delay_s (%s) - swapping them",
            where, maximum, minimum,
        )
        minimum, maximum = maximum, minimum

    return ReactionBehavior(
        min_delay_s=minimum,
        max_delay_s=maximum,
        rounds=_whole(
            raw, "rounds", where, defaults.rounds, note=" (0 = until you leave)"
        ),
        slowest_ms=_positive(raw, "slowest_ms", where, defaults.slowest_ms),
        reveal_s=_positive(raw, "reveal_s", where, defaults.reveal_s),
        log_as=_nonempty(raw, "log_as", where, defaults.log_as),
        ramp=_parse_ramp(raw["ramp"], f"{where}.ramp", defaults.ramp)
        if "ramp" in raw else defaults.ramp,
    )


def _parse_show_cues(raw, where: str, looks: dict[str, object]) -> tuple[ShowCue, ...]:
    """A show's cue list, dropping anything unusable rather than the show.

    A cue naming a look that is not in the pool is **kept and warned about**,
    not dropped: that is the same dangling-reference rule `enter_mode` targets
    follow, and for the same reason - quietly removing a cue would renumber the
    show under someone who was mid-edit, and a missing look is much more often
    a rename than a mistake. The run loop skips it and says so.
    """
    if isinstance(raw, str):
        # What the editor's textarea writes: one look name per line. Accepted
        # rather than rejected because the launcher's `targets` does *not*
        # accept it, and the result there is a list silently reverting to "all
        # apps" the moment someone edits it in the web UI.
        raw = [line.strip() for line in raw.splitlines() if line.strip()]
    if not isinstance(raw, list):
        if raw is not None:
            log.error("config: %s.cues must be a list of look names - using none", where)
        return ()
    cues: list[ShowCue] = []
    for idx, entry in enumerate(raw):
        at = f"{where}.cues[{idx}]"
        if isinstance(entry, str):  # a bare look name is the common case
            entry = {"look": entry}
        if not isinstance(entry, dict):
            log.error("config: %s must be an object or a look name - skipped", at)
            continue
        look = entry.get("look")
        if not isinstance(look, str) or not look:
            log.error("config: %s needs a look name - skipped", at)
            continue
        if look not in looks:
            log.warning("config: %s names look %r, which does not exist", at, look)
        hold = _nonneg(entry, "hold_s", at, 0.0)
        cues.append(ShowCue(look=look, hold_s=hold))
    return tuple(cues)


def _parse_lightshow_body(raw, where: str, looks: dict[str, object]) -> LightShowBehavior:
    """The light show template's body. Every key falls back on its own."""
    defaults = LightShowBehavior()
    dwell = _positive(raw, "dwell_s", where, defaults.dwell_s)
    # A zero dwell would spin the show as fast as the loop can push frames,
    # which is a strobe nobody asked for and one the flash floor cannot catch
    # (it governs a look's own rate, not how often we swap looks). One second
    # is already faster than anything readable.
    if dwell < _MIN_SHOW_DWELL_S:
        if raw.get("dwell_s") is not None:
            log.warning(
                "config: %s.dwell_s %.2fs is below the %.1fs floor - using the floor",
                where, dwell, _MIN_SHOW_DWELL_S,
            )
        dwell = _MIN_SHOW_DWELL_S
    auto = raw.get("auto", defaults.auto)
    if not isinstance(auto, bool):
        log.error("config: %s.auto must be true or false - using %s", where, defaults.auto)
        auto = defaults.auto
    log_as = raw.get("log_as", defaults.log_as)
    if not isinstance(log_as, str):
        log.error("config: %s.log_as must be text - ignored", where)
        log_as = defaults.log_as
    return LightShowBehavior(
        cues=_parse_show_cues(raw.get("cues"), where, looks or {}),
        dwell_s=dwell,
        auto=auto,
        log_as=log_as,
    )


def _parse_mode(
    raw, idx: int, looks: dict | None = None, actions: set[str] | None = None,
) -> Mode | None:
    """Parse one mode. A mode with a broken activation, a template<->
    activation nature mismatch, or no usable body is skipped entirely
    (logged) - the fail-soft floor is the built-in default modes.

    `looks` and `actions` are the two pools' names, passed only so a mode
    referencing something absent is *reported*; neither can cause a skip."""
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
        behavior = _parse_actions_body(raw, where, name, actions)
    elif template in ("alarm", "reminders", "notice"):
        behavior = _parse_notice_body(raw, where, template, name, actions)
    elif template == "launcher":
        behavior = _parse_launcher_body(raw, where)
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
    elif template == "hotcold":
        behavior = _parse_hotcold_body(raw, where)
    elif template == "reaction":
        behavior = _parse_reaction_body(raw, where)
    elif template == "signal":
        behavior = _parse_signal_body(raw, where, actions)
    elif template == "control":
        behavior = _parse_control_body(raw, where, name, actions, looks or {})
    elif template == "lightshow":
        behavior = _parse_lightshow_body(raw, where, looks or {})
    else:  # pragma: no cover - allow-list keys and this dispatch stay in sync
        log.error("config: %s (%r) has unknown template %r - skipped", where, name, template)
        return None

    if behavior is None:
        return None
    return Mode(
        name=name,
        behavior=behavior,
        activation=activation,
        looks=_parse_mode_looks(raw, where, template, looks or {}),
        **_parse_hooks(raw, where, template, actions),
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


def _parse_modes(
    raw: dict, looks: dict | None = None, actions: set[str] | None = None,
) -> tuple[Mode, ...]:
    """Resolve the modes list, then guarantee it can actually answer a
    gesture: `_ensure_ambient_always` is the last step so nothing upstream
    (the migration ladder, a hand-written "modes" list, a scene merged over
    either) has to re-derive the same fail-soft rule."""
    return _ensure_ambient_always(_resolve_mode_list(raw, looks, actions))


def _resolve_mode_list(
    raw: dict, looks: dict | None, actions: set[str] | None = None,
) -> tuple[Mode, ...]:
    """The migration ladder itself: modes (v0.3) -> rules (v0.2) -> commands
    (v0.1) -> built-in defaults.

    `looks` and `actions` are the two pools of names a mode may reference;
    both are parsed first so a dangling reference is caught here and reported,
    rather than discovered at the moment the light should have changed colour
    or the gesture should have done something. The legacy ladders below
    predate both pools entirely and never produce a reference into either.
    """
    if isinstance(raw.get("modes"), list):
        modes = tuple(
            mode
            for idx, entry in enumerate(raw["modes"])
            if (mode := _parse_mode(entry, idx, looks, actions)) is not None
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
        "modes", "rules", "commands", "led_palette", "looks", "actions",
        "reflexes", "state_looks", "scenes", "min_flash_period_s",
    }
    for key in raw:
        if key not in known:
            log.warning("config: unknown key %r - ignored", key)

    # Both pools are parsed before the modes, so a mode naming something that
    # does not exist is reported here rather than at the moment the light
    # should have changed colour or the gesture should have done something.
    looks = _parse_looks(raw)
    action_pool = _parse_action_pool(raw)
    # And the modes before the reflexes, for the third instance of the same
    # rule: a reflex scoped to an app that is not there is worth saying at
    # load, not at the moment nothing happened.
    modes = _parse_modes(raw, looks, set(action_pool))

    config = AppConfig(
        ble_device_name=_take(raw, "ble_device_name", str, defaults.ble_device_name),
        sounds_enabled=_take(raw, "sounds_enabled", bool, defaults.sounds_enabled),
        database_path=_take(raw, "database_path", str, defaults.database_path),
        web_enabled=_take(raw, "web_enabled", bool, defaults.web_enabled),
        web_host=_take(raw, "web_host", str, defaults.web_host),
        web_port=_take(raw, "web_port", int, defaults.web_port),
        modes=modes,
        led_palette=_parse_palette(raw),
        looks=looks,
        actions=action_pool,
        reflexes=_parse_reflexes(
            raw, set(action_pool), {mode.name for mode in modes}
        ),
        state_looks=_parse_state_looks(raw, looks),
        scenes=scenes.parse_settings(raw.get("scenes")),
        min_flash_period_s=_parse_min_flash_period(raw),
    )
    _warn_about_documents(config)
    return config


def _warn_about_documents(config: AppConfig) -> None:
    """Complain about a `set_value` that names an app or a slot nobody has.

    **Last, because it needs the finished config**: an app-bound action points
    at a mode, and which slots that mode has depends on its template, so
    neither question can be answered while the modes are still being parsed.
    `iter_actions` is what makes it one short pass rather than a second tour
    of everything.

    **Warned about and kept**, the dangling-reference rule every other named
    thing here follows: quietly repointing the binding at some other app would
    be worse, dropping it loses the number's owner, and a rename is a much
    more likely explanation than a mistake. The runtime writes the slot
    anyway - a document is keyed by name and needs no mode to exist - so the
    value is still there when the app comes back.
    """
    by_name = {mode.name: mode for mode in config.modes}
    for where, action in iter_actions(config):
        if not isinstance(action, SetValueAction):
            continue
        mode = by_name.get(action.app)
        if mode is None:
            log.warning(
                "config: %s writes to app %r, which no mode is named", where,
                action.app,
            )
            continue
        slots = {slot.name for slot in DOC_SLOTS.get(mode.template, ())}
        if action.slot not in slots:
            log.warning(
                "config: %s writes %r on %r, which keeps %s", where, action.slot,
                action.app,
                ", ".join(sorted(slots)) if slots else "no values of its own",
            )


def _parse_min_flash_period(raw: dict) -> float:
    """The effective flash floor, with the recommendation as the default.

    A value that is not a positive number is *broken* - there is no reading of
    it, so it falls back like any other bad key.

    **A value merely lower than the recommendation is a choice, and it is not
    warned about here** (TODO 108). It was, on every load, and that was the
    mistake: this is a setting precisely because someone may mean it, and a
    parser that re-states the hazard every time the service starts is not
    informing anyone by the second time. It is the mirror of the error the
    flash-floor invariant already names - clamping silently makes a setting a
    lie, and scolding forever makes it a nag. The hazard is stated where the
    number is chosen (schema.js's hint, and the first-run question when that
    exists), which is the only place it can still change a mind.
    """
    value = _take(raw, "min_flash_period_s", float, SAFE_MIN_PERIOD_S)
    if value <= 0:
        log.error(
            "config: min_flash_period_s must be greater than 0, got %r - "
            "using %.3f", value, SAFE_MIN_PERIOD_S,
        )
        return SAFE_MIN_PERIOD_S
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


def sequence_safe(seq: sequencer.Sequence, min_period_s: float) -> sequencer.Sequence:
    """`seq` with every stop's dwell raised to `min_period_s / 2`, if the
    sequence is one that could sustain a strobe.

    **The maths, carried over from `flash_safe`.** `flash_safe` floors
    `period_s`, and `period_s` is a *full cycle* - `_flash`/`_alternate` in
    firmware/led.py toggle at `period_s / 2` - so the existing floor already
    means "no transition interval shorter than half the period". A stop list
    has no period; it has stops, and moving from one stop to the next is one
    transition. Flooring a stop's dwell (`hold_s + fade_s`: the time it
    occupies before the *next* transition starts) at `min_period_s / 2`
    enforces the identical property over the axis that actually moves here -
    the same move `main.ladder_paint` makes for its tick, independently
    arrived at (see CLAUDE.md for why the two are not unified into one
    number: a ladder's tick and a stop's dwell floor at different multiples
    of `min_period_s`, so sharing the constant would mean changing one of
    their behaviours, not just their code).

    **Exempt: a one-shot of three stops or fewer.** A handful of transitions
    played once - three quick confirmation flashes, say - is not what WCAG
    2.3.1 is worried about; that limit is about *sustained* flashing, and a
    sequence that plays once and stops cannot sustain anything. Once a
    sequence can either repeat or run past three stops, it can flash for as
    long as something keeps it running, which is exactly the strobing-style
    case `flash_safe` already floors.

    **One axis, since TODO 36e.** A stop used to be able to carry a strobing
    style of its own, which the exemption above deliberately did not reach - a
    0.05 s flash held for two seconds is forty of them, one-shot or not. Stops
    are flat colours now, so the only thing that can move here is the walk
    between them, and the dwell floor is the whole floor.

    Pure, like `flash_safe`, and enforced at the same single point: `main.
    set_led`'s Sequence branch, mirroring where `flash_safe` runs for a plain
    effect. Nothing else calls this - a second call site would be a second
    floor with its own chance to drift from this one. `flash_safe` is reused
    below rather than reimplemented for stops, so "which styles strobe and how
    slow is slow enough" stays one answer in one place.
    """
    if not (seq.repeat or len(seq.stops) > 3):
        return seq
    floor = min_period_s / 2
    stops = tuple(
        stop if stop.hold_s + stop.fade_s >= floor
        else replace(stop, hold_s=floor - stop.fade_s)
        for stop in seq.stops
    )
    if stops == seq.stops:
        return seq
    return replace(seq, stops=stops)


def look_for(
    config: AppConfig, mode: Mode | None, state: LEDState
) -> LedEffect | sequencer.Sequence | None:
    """The look `mode` wears for `state`, or None to use the palette entry.

    None rather than the palette entry on purpose: None is what `set_led`
    already means by "no override", so a mode that has not chosen a look costs
    nothing - no effect write, no borrowed palette entry, and a device that
    predates ephemeral effects behaves exactly as it did.
    """
    if mode is not None and (name := mode.looks.get(state.value)):
        return config.looks.get(name)
    # No mode look: the button's own states may still name one globally, which
    # is what lets SUCCESS be a whole confirmation pattern rather than one
    # style the palette can hold (see `_parse_state_looks`). Checked second on
    # purpose - a mode that has chosen a look for a state it owns is the more
    # specific answer, and must win.
    name = config.state_looks.get(state.value)
    return config.looks.get(name) if name else None


def resolve_action(config: AppConfig, action: Action | None) -> Action | None:
    """The action to actually run: `action` itself, or whatever it names.

    The single place a `NamedAction` becomes a real one, which is why it lives
    here rather than inlined at the four dispatch sites that need it (main.py's
    ambient `handle`, `run_control`, `run_signal` and `fire_hook`). A name with
    nothing behind it returns None and the caller fails clearly - the same
    contract `EnterModeAction`'s target has had since it was written.

    One level, by construction: `_parse_action_pool` refuses an entry that is
    itself a name, so there is no chain to walk here and no cycle to detect.

    **A `SequenceAction` is resolved through here too** (TODO 33), step by
    step, which is why every dispatch site got sequences for free rather than
    growing a resolver of its own. It is also where the no-nesting rule is
    enforced for the one shape the parser cannot see: a step naming a pool
    entry that turns out to *be* a sequence. That step is dropped and the rest
    of the sequence runs, the same call a dangling step gets.
    """
    if isinstance(action, NamedAction):
        action = config.actions.get(action.name)
    if isinstance(action, SequenceAction):
        steps = []
        for index, step in enumerate(action.steps, start=1):
            inner = step.action
            if isinstance(inner, NamedAction):
                inner = config.actions.get(inner.name)
                if inner is None:
                    log.warning(
                        "sequence step %d names action %r, which is not in "
                        "'actions' - skipped", index, step.action.name,
                    )
                    continue
                if isinstance(inner, SequenceAction):
                    log.warning(
                        "sequence step %d names %r, which is itself a "
                        "sequence - skipped, sequences do not nest",
                        index, step.action.name,
                    )
                    continue
            steps.append(replace(step, action=inner))
        return replace(action, steps=tuple(steps)) if steps else None
    return action


# Every action class, read off the `Action` union rather than listed again.
# A fourth allow-list beside FIRE_AND_FORGET/HOOK/REFLEX_ACTIONS would be a
# fourth thing to forget when a primitive is added, and this one has no
# opinion about *which* actions are allowed anywhere - it only needs to
# recognise one when it walks past it.
_ACTION_CLASSES: tuple[type, ...] = get_args(Action)


def iter_actions(config: AppConfig):
    """Every action in the config, as `(where, action)` pairs.

    One walk, because "which actions do X?" keeps being a question and each
    asker was otherwise going to write its own tour of modes, hooks, signal
    positions, reflexes and the pool - and miss one. `where` is prose for a
    human reading a log, not a path anything should parse.

    Two rules worth knowing:

    - **A `NamedAction` is yielded as itself and not followed.** The pool
      entry it names is yielded once, under `actions[...]`, so a shared action
      is reported where it is *defined* rather than once per binding - which
      is also where you would go to fix it.
    - **A sequence yields its steps as well as itself**, flattened, because a
      step is a real action that really runs. No recursion is needed for that
      and none is possible: sequences do not nest, by parser and by
      `resolve_action` both.

    Behaviour fields are found by *shape* rather than by a list of templates,
    the same move `bound_triggers` makes: an action-valued field, a dict of
    them (a gesture map), or a tuple of objects carrying one (a signal
    light's positions). A template written tomorrow is walked for free.
    """
    def unpack(where: str, action):
        if action is None:
            return
        yield where, action
        if isinstance(action, SequenceAction):
            for number, step in enumerate(action.steps, start=1):
                if step.action is not None:
                    yield f"{where} step {number}", step.action

    for name, action in config.actions.items():
        yield from unpack(f"actions[{name!r}]", action)
    for reflex in config.reflexes:
        yield from unpack(f"reflex {reflex.name!r}", reflex.then)
    for mode in config.modes:
        for hook in MODE_HOOKS:
            yield from unpack(f"mode {mode.name!r}.{hook}", getattr(mode, hook))
        for field_ in fields(mode.behavior):
            value = getattr(mode.behavior, field_.name)
            if isinstance(value, _ACTION_CLASSES):
                yield from unpack(f"mode {mode.name!r}.{field_.name}", value)
            elif isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, _ACTION_CLASSES):
                        yield from unpack(f"mode {mode.name!r}.{key}", item)
            elif isinstance(value, tuple):
                for index, item in enumerate(value):
                    inner = getattr(item, "action", None)
                    if isinstance(inner, _ACTION_CLASSES):
                        yield from unpack(
                            f"mode {mode.name!r}.{field_.name}[{index}]", inner
                        )


def blank_midi_ports(config: AppConfig, outputs) -> tuple[str, ...]:
    """Where a `midi` action names no port while this machine offers a choice.

    **The failure this exists to name cost an evening** (see TODO's "Smaller,
    worth doing"): an empty port means *the first output on the machine*, which
    on Windows is the built-in synth. The DAW hears nothing, the synth hears
    everything, and nothing reports an error because nothing has failed. The
    editor's half of the fix shipped the same day - the field is basic-tier and
    its hint says what blank does - and this is the half that reaches a file
    somebody edited by hand.

    **Silent when there is only one output**, because then blank is not
    ambiguous: it is the only thing it could mean, and warning about it would
    be noise on exactly the machine the default was written for. Pure, and the
    port list is passed in - enumerating MIDI hardware is I/O, and the parsing
    half of this module does not do I/O.
    """
    if len(outputs) < 2:
        return ()
    return tuple(
        where
        for where, action in iter_actions(config)
        if isinstance(action, MidiAction) and not action.port.strip()
    )


def position_reporters(config: AppConfig, mode_name: str) -> tuple[str, ...]:
    """Every reflex that can put the app called `mode_name` on a position.

    The question behind TODO 77's "says it is guessing": a control surface's
    positions are only ever set by the world, so a surface with positions and
    nothing able to report them is showing the first one as if it were a fact.
    Answering that is a walk over data - reflexes scoped to this app whose
    action resolves to a `SetPositionAction` - so it lives here with
    `resolve_action` rather than in the run loop, which cannot be asked a
    question without being started.

    Names rather than a bare bool: a caller that has to explain *why* a page
    is guessing needs to be able to say which reflexes it looked for, and
    truthiness is the only thing the run loop asks of it.
    """
    return tuple(
        reflex.name
        for reflex in config.reflexes
        if reflex.while_app == mode_name
        and isinstance(resolve_action(config, reflex.then), SetPositionAction)
    )


@dataclass(frozen=True)
class ParseWarning:
    """One complaint from the parser, with where it came from (TODO 62).

    The editor prints these into a banner that the next Save overwrites, and
    the reason it cannot do better is that a warning was a plain sentence: it
    knows which key it is about and the string threw that away. This carries
    it - `mode` is the index into `modes`, `key` the field on that mode - so a
    dangling look or a bad ladder rung can mark the field it belongs to.

    **Both may be None, and that is a normal answer, not a failure.** A
    complaint about a top-level key belongs to no mode; one about the shape of
    the file belongs to no field. The message alone is what has always been
    shown, and it is still the thing that must always be right.
    """

    message: str
    mode: int | None = None  # index into config["modes"], as written
    key: str | None = None   # the field on that mode, e.g. "short_press"


# What the parser's `where` strings look like, and the only thing read out of
# them: `modes[3].short_press`, `modes[3].states[0].action`, `modes[3]`.
#
# **Derived from the log record's first argument, never from the rendered
# message.** Every one of these calls passes `where` first and the rest after
# it, so `record.args[0]` is the location with no formatting in the way -
# which makes this a lookup rather than the fragile business of parsing back a
# sentence we just built. A record whose first argument is not a location
# simply has none, and renders exactly as it always did.
_WHERE_RE = re.compile(r"^modes\[(\d+)\](?:\.([A-Za-z_][\w]*))?")


def _locate(record: logging.LogRecord) -> tuple[int | None, str | None]:
    """Which mode and which field `record` is complaining about, if any."""
    args = record.args
    first = args[0] if isinstance(args, tuple) and args else None
    if not isinstance(first, str):
        return None, None
    found = _WHERE_RE.match(first)
    if found is None:
        return None, None
    return int(found.group(1)), found.group(2)


@contextlib.contextmanager
def _collecting(warnings: list, structured: bool = False):
    """Route the parser's per-key fallback complaints into `warnings`.

    Both loggers are captured: a scene's own keys are validated in scenes.py,
    and a warning the editor never sees is a warning nobody acts on.

    `structured` decides the shape: plain strings (what every caller has had),
    or `ParseWarning`s carrying where they came from (TODO 62). One collector
    rather than two, because a second one is a second thing to keep in step
    with which loggers matter.
    """

    class _Collector(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.WARNING)

        def emit(self, record: logging.LogRecord) -> None:
            if not structured:
                warnings.append(record.getMessage())
                return
            mode, key = _locate(record)
            warnings.append(ParseWarning(record.getMessage(), mode, key))

    collector = _Collector()
    loggers = [log, logging.getLogger(scenes.__name__)]
    for logger in loggers:
        logger.addHandler(collector)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeHandler(collector)


def parse_with_details(raw: dict) -> tuple[AppConfig, list[ParseWarning]]:
    """`parse_with_warnings`, with each complaint's origin attached (TODO 62).

    A second function rather than a wider return from the one below, because
    six callers depend on that one answering with strings and a warning that
    stopped being printable would be a regression in the thing that has always
    worked. The API returns both: the sentences, and these beside them.
    """
    warnings: list[ParseWarning] = []
    with _collecting(warnings, structured=True):
        cfg = parse_config(raw)
    return cfg, warnings


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

    A live preview shows a look the button never stores, but "what counts as a
    valid look" must not fork: a colour the editor would reject when saved has
    to be rejected the same way when shown, or the preview stops predicting
    the thing it is previewing. Same per-field fallback as everywhere else - a
    bad colour costs you that colour, not the request.
    """
    warnings: list[str] = []
    with _collecting(warnings):
        effect = _parse_effect(raw, where, LedEffect())
    return effect, warnings


def parse_action_with_warnings(
    raw, where: str = "action", known: set[str] | None = None
) -> tuple[Action | None, list[str]]:
    """One action, through the config parser's own rules.

    `parse_look_with_warnings` for the other half of the editor, and it exists
    for exactly the same reason: a webhook preview (TODO 65) has to be built
    from an action the parser would *accept*, or it stops predicting the thing
    it is previewing. None means nothing usable, and the warnings say why.
    """
    warnings: list[str] = []
    with _collecting(warnings):
        action = _parse_action(raw, where, known)
    return action, warnings


def parse_look_with_warnings(
    raw, where: str = "look"
) -> tuple[LedEffect | sequencer.Sequence, list[str]]:
    """`parse_effect_with_warnings`, but a `stops` body parses as a
    `sequencer.Sequence` too - the same dispatch `_parse_looks` uses for the
    named-look pool (see `_parse_look`).

    A separate function rather than widening `parse_effect_with_warnings`:
    that one's return type is depended on as always-`LedEffect` (test_look_
    presets.py, and everywhere a preview is asserted to be a plain effect),
    and a look-pool entry or a test-bench push are the only two places that
    legitimately need the wider answer.
    """
    warnings: list[str] = []
    with _collecting(warnings):
        look = _parse_look(raw, where, LedEffect())
    return look, warnings


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


def _action_to_dict(action: Action) -> dict | str:
    """Round-trip one action. A `NamedAction` comes back as the bare string it
    was written as, which is the whole reason a string was chosen for it."""
    if isinstance(action, NamedAction):
        return action.name
    if isinstance(action, StandbyAction):
        return {"action": "standby"}
    if isinstance(action, LogAction):
        return {"action": "log", "event": action.event}
    if isinstance(action, ReadoutAction):
        return {
            "action": "readout", "event": action.event,
            "tens_color": action.tens_color, "units_color": action.units_color,
        }
    if isinstance(action, TimerToggleAction):
        return {"action": "timer_toggle", "log_as": action.log_as}
    if isinstance(action, SetValueAction):
        return {
            "action": "set_value", "app": action.app, "slot": action.slot,
            "op": action.op, "value": action.value,
        }
    if isinstance(action, WebhookAction):
        return {"action": "webhook", "url": action.url, "payload": action.payload}
    if isinstance(action, OscAction):
        return {
            "action": "osc", "host": action.host, "port": action.port,
            "address": action.address, "args": list(action.args),
        }
    if isinstance(action, MidiAction):
        return {
            "action": "midi", "port": action.port, "channel": action.channel,
            "kind": action.kind, "number": action.number, "value": action.value,
        }
    if isinstance(action, KeysAction):
        return {"action": "keys", "combo": action.combo, "click": action.click}
    if isinstance(action, EnterModeAction):
        return {"action": "enter_mode", "target": action.target}
    if isinstance(action, SetPositionAction):
        return {"action": "set_position", "name": action.name}
    if isinstance(action, SequenceAction):
        steps: list[dict | str] = []
        for step in action.steps:
            body = _action_to_dict(step.action)
            # A named step is a bare string and never carries a wait, so there
            # is nothing to merge into - which is what keeps the round-trip
            # exact for both step shapes.
            if isinstance(body, str):
                steps.append(body)
            elif step.wait_s:
                steps.append({**body, "wait_s": step.wait_s})
            else:
                steps.append(body)
        return {"action": "sequence", "steps": steps}
    raise TypeError(f"unknown action type {type(action).__name__}")


def _reflex_to_dict(reflex: Reflex) -> dict:
    """Round-trips: `then` comes back as the bare string it was written as when
    it names a pool entry, and `while` is omitted when unset so every config
    written before reflexes existed still round-trips byte for byte."""
    entry: dict = {"name": reflex.name, "then": _action_to_dict(reflex.then)}
    if reflex.when is not None:
        entry["when"] = {
            "field": reflex.when.field,
            "op": reflex.when.op,
            "value": reflex.when.value,
        }
    if reflex.source is not None:
        midi_spec: dict = {"port": reflex.source.port}
        midi_spec[reflex.source.kind] = reflex.source.number
        if reflex.source.channel is not None:
            midi_spec["channel"] = reflex.source.channel
        entry["from"] = {"midi": midi_spec}
    if reflex.while_app:
        entry["while"] = reflex.while_app
    return entry


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


def look_to_dict(look: LedEffect | sequencer.Sequence) -> dict:
    """One look-pool entry, either shape. A sequence writes back the same
    `stops`/`repeat` keys `_parse_sequence` reads, always in the object form
    (never the bare-colour shorthand `_parse_stop` also accepts) - the
    round-trip has to be exact the way `ramp`'s does, not merely equivalent.

    Public, unlike its neighbours, because the web layer answers with a look
    too: `/api/dev/led` reports what it actually put on the light, and that may
    be either shape. One serialiser, so the preview and the saved config can
    never describe the same look differently."""
    if isinstance(look, sequencer.Sequence):
        return {
            "stops": [
                {
                    "color": stop.color, "hold_s": stop.hold_s,
                    "fade_s": stop.fade_s, "curve": stop.curve,
                }
                for stop in look.stops
            ],
            "repeat": look.repeat,
            "drive": look.drive,
        }
    return _effect_to_dict(look)


def _mode_to_dict(mode: Mode) -> dict:
    entry: dict = {
        "name": mode.name,
        "template": mode.template,
        "activation": _activation_to_dict(mode.activation),
    }
    if mode.looks:  # omitted when empty, so a mode that uses the palette
        entry["looks"] = dict(mode.looks)  # round-trips as the plain object it was
    # Same rule, same reason: a mode with no hooks writes no hook keys, so every
    # config written before they existed round-trips byte for byte.
    for hook in MODE_HOOKS:
        action = getattr(mode, hook)
        if action is not None:
            entry[hook] = _action_to_dict(action)
    if isinstance(mode.behavior, ActionsBehavior):
        if mode.behavior.unless_logged_today is not None:
            entry["unless_logged_today"] = mode.behavior.unless_logged_today
        for trigger, action in mode.behavior.actions.items():
            entry[trigger] = _action_to_dict(action)
    elif isinstance(mode.behavior, NoticeBehavior):
        # Always the new field names on the way out, whichever legacy
        # template name it was parsed from (TODO 84) - the same one-way
        # migration Pomodoro's seconds-only round-trip already documents.
        entry["message"] = mode.behavior.message
        entry["label"] = mode.behavior.label
        entry["log_as"] = mode.behavior.log_as
        entry["timeout_minutes"] = mode.behavior.timeout_minutes
        entry["snooze_minutes"] = mode.behavior.snooze_minutes
        entry["urgent"] = mode.behavior.urgent
        entry["chime"] = mode.behavior.chime
        if mode.behavior.on_cleared is not None:
            entry["on_cleared"] = _action_to_dict(mode.behavior.on_cleared)
        if mode.behavior.on_snoozed is not None:
            entry["on_snoozed"] = _action_to_dict(mode.behavior.on_snoozed)
        if mode.behavior.on_missed is not None:
            entry["on_missed"] = _action_to_dict(mode.behavior.on_missed)
    elif isinstance(mode.behavior, LauncherBehavior):
        entry["targets"] = list(mode.behavior.targets)
        entry["return_after"] = mode.behavior.return_after
        entry["log_as"] = mode.behavior.log_as
    elif isinstance(mode.behavior, StopwatchBehavior):
        entry["log_as"] = mode.behavior.log_as
        entry["ladder"] = _ladder_to_dict(mode.behavior.ladder)
    elif isinstance(mode.behavior, CounterBehavior):
        entry["event"] = mode.behavior.event
        entry["durable"] = mode.behavior.durable
    elif isinstance(mode.behavior, PomodoroBehavior):
        # Seconds only. A config that came in with the legacy `*_minutes`
        # names is rewritten the first time it is saved, which is the whole
        # migration - there is no second format to keep supporting on the way
        # out, only on the way in.
        entry["work_s"] = mode.behavior.work_s
        entry["break_s"] = mode.behavior.break_s
        entry["long_break_s"] = mode.behavior.long_break_s
        entry["blocks_before_long_break"] = mode.behavior.blocks_before_long_break
        entry["extend_s"] = mode.behavior.extend_s
        entry["rounds"] = mode.behavior.rounds
        entry["lead_in_s"] = mode.behavior.lead_in_s
        entry["advance"] = mode.behavior.advance
        entry["log_as"] = mode.behavior.log_as
        entry["waiting_style"] = mode.behavior.waiting_style
        # Omitted when empty rather than written as `[]`: an empty list is what
        # `_parse_ramp` rejects, so writing one would make every Pomodoro warn
        # on the next load. Absent is how "no ramp" round-trips.
        if mode.behavior.ramp:
            entry["ramp"] = [
                {"color": stop.color, "at": stop.at} for stop in mode.behavior.ramp
            ]
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
        entry["ladder"] = _ladder_to_dict(mode.behavior.ladder)
        entry["start_bpm"] = mode.behavior.start_bpm
        entry["tap_history"] = mode.behavior.tap_history
        entry["reset_gap_s"] = mode.behavior.reset_gap_s
        entry["max_bpm"] = mode.behavior.max_bpm
        entry["sound_on_tap"] = mode.behavior.sound_on_tap
        entry["log_as"] = mode.behavior.log_as
        entry["clock_port"] = mode.behavior.clock_port
    elif isinstance(mode.behavior, HotColdBehavior):
        entry["sweep_s"] = mode.behavior.sweep_s
        entry["rounds"] = mode.behavior.rounds
        entry["segments"] = mode.behavior.segments
        entry["tolerance"] = mode.behavior.tolerance
        entry["reveal_s"] = mode.behavior.reveal_s
        entry["log_as"] = mode.behavior.log_as
        entry["ramp"] = [
            {"color": stop.color, "at": stop.at} for stop in mode.behavior.ramp
        ]
    elif isinstance(mode.behavior, ControlBehavior):
        # Flat, exactly like an actions mode - one key per gesture. The two
        # templates round-trip through the same shape on purpose: changing a
        # mode from always-on to an app should be a one-word edit.
        for trigger, action in mode.behavior.actions.items():
            entry[trigger] = _action_to_dict(action)
        entry["log_as"] = mode.behavior.log_as
        entry["return_after"] = mode.behavior.return_after
        # Omitted when empty, for the reason a Pomodoro's ramp is: every
        # control surface written before TODO 77 round-trips byte for byte,
        # and "no positions" is the ordinary remote rather than a setting.
        if mode.behavior.positions:
            entry["positions"] = [
                {"name": p.name, **({"look": p.look} if p.look else {})}
                for p in mode.behavior.positions
            ]
    elif isinstance(mode.behavior, SignalBehavior):
        entry["states"] = [
            {
                "name": state.name, "color": state.color, "style": state.style,
                **({"action": _action_to_dict(state.action)} if state.action else {}),
            }
            for state in mode.behavior.states
        ]
        entry["start_at"] = mode.behavior.start_at
        entry["log_as"] = mode.behavior.log_as
    elif isinstance(mode.behavior, LightShowBehavior):
        entry["cues"] = [
            {"look": cue.look, **({"hold_s": cue.hold_s} if cue.hold_s else {})}
            for cue in mode.behavior.cues
        ]
        entry["dwell_s"] = mode.behavior.dwell_s
        entry["auto"] = mode.behavior.auto
        entry["log_as"] = mode.behavior.log_as
    elif isinstance(mode.behavior, ReactionBehavior):
        entry["min_delay_s"] = mode.behavior.min_delay_s
        entry["max_delay_s"] = mode.behavior.max_delay_s
        entry["rounds"] = mode.behavior.rounds
        entry["slowest_ms"] = mode.behavior.slowest_ms
        entry["reveal_s"] = mode.behavior.reveal_s
        entry["log_as"] = mode.behavior.log_as
        entry["ramp"] = [
            {"color": stop.color, "at": stop.at} for stop in mode.behavior.ramp
        ]
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
        "looks": {name: look_to_dict(look) for name, look in cfg.looks.items()},
        "actions": {
            name: _action_to_dict(action) for name, action in cfg.actions.items()
        },
        "reflexes": [_reflex_to_dict(reflex) for reflex in cfg.reflexes],
        "state_looks": dict(cfg.state_looks),
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
