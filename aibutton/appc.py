"""The app compiler: a mode becomes a package the device can run alone.

ARCHITECTURE.md's middle arrow, host-side by design — *config is parsed on the
phone, and the device receives a compiled binary*, which is what keeps the
device's parser (and its attack surface, and its flash footprint) near zero.
The decoder is [firmware/apppkg.py](../firmware/apppkg.py); the two are a
mirrored table in CLAUDE.md's sense and `tests/test_apppkg.py` fails on drift.

**The compiler unrolls what the runtime would otherwise have to compute.** A
light show's "next cue, wrapping at the end" is an index and a modulo on the
host; here it becomes N states pointing at each other, and the device just
walks the table. That is the trade this design is *for*: complexity moves to
the machine with a keyboard attached, and the one in your pocket runs something
a person can audit in an afternoon. It is also why the first runtime needs no
expression evaluator — see firmware/runtime.py for what that costs, honestly.

**Pure, like the parsing half of config.py**: modes and looks in, bytes out,
no file system and no device. That is what lets the whole thing be tested
without hardware.

Only the light show compiles today. The shape generalises — a gesture map is
one state, a signal light is one state per position — but a template is only
worth compiling once the device can render what it does, and the two that
cannot are the ones that keep a *number* (a counter, a stopwatch), which needs
the durable document ARCHITECTURE.md specifies and this runtime has not got.
"""

from __future__ import annotations

from . import sequencer
from .config import (
    ActionsBehavior,
    AlwaysActivation,
    AppConfig,
    EnterModeAction,
    LedEffect,
    LightShowBehavior,
    Mode,
    SignalBehavior,
    StandbyAction,
    flash_safe,
    resolve_action,
    sequence_safe,
)
from .device import effect_payload, rgb_bytes

MAGIC = b"BTNA"
FORMAT_VERSION = 2

# Mirrors firmware/apppkg.py. Kept as literals on both sides rather than
# imported across the seam: firmware/ ships to a board and must not depend on
# the package, exactly as device.py must not depend on config.py.
LOOK_EFFECT = 0x01
LOOK_SEQUENCE = 0x02

OP_SHOW = 0x01
OP_PLAY = 0x02
OP_TIMER = 0x03
OP_ENTER = 0x04

EV_TAP = 0x01
EV_HOLD = 0x02
EV_TIMER = 0x03

EXIT = 0xFF

# The two byte-counted fields anything here can overflow, and the reason each
# is a byte: a package is meant to be small enough to sync over BLE in one
# breath. A show that needs more than 127 cues is a playlist, not a button.
MAX_STATES = 0xFE  # 0xFF is EXIT
MAX_LOOKS = 0xFF
# Centiseconds, the same resolution and ceiling the wire already uses for a
# period (device._MAX_PERIOD_CS), so a dwell cannot mean one thing in a package
# and another in a palette entry.
MAX_CS = 0xFFFF


class CompileError(Exception):
    """The one thing that stops a package being produced. Rare on purpose:
    everything a config can get *wrong* has already been through the parser's
    per-key fallbacks, so what is left here is structural - no cues at all, or
    a show too big for the format."""


def _cs(seconds: float) -> int:
    """Seconds -> centiseconds, clamped into the two bytes that carry it."""
    return max(0, min(int(round(seconds * 100)), MAX_CS))


def _curve_code(curve: str) -> int:
    """A curve name -> its index in `sequencer.CURVES`, which *is* the wire
    encoding (firmware/sequence.py's CURVE_* constants are that index). An
    unknown curve is linear, the same fallback `sequencer.shape` makes."""
    try:
        return sequencer.CURVES.index(curve)
    except ValueError:
        return 0


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE. The mirror of `apppkg.crc16`, and the only integrity
    check a package gets: the device validates a checksum and a version, never
    a schema."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _look_bytes(look, min_flash_period_s: float) -> bytes:
    """One look, floored.

    **This is the third and last place the flash floor is enforced**, and it
    has to be here rather than at `main.set_led`: a package renders on a device
    with no host in the room, so a look that reached flash unfloored would have
    nothing left to clamp it. Same rule as `push_palette`, one call site, and
    CLAUDE.md's floor invariant names all three.
    """
    if isinstance(look, sequencer.Sequence):
        floored = sequence_safe(look, min_flash_period_s)
        stops = floored.stops[:0xFF]
        out = bytearray([LOOK_SEQUENCE, 1 if floored.repeat else 0, len(stops)])
        for stop in stops:
            out += rgb_bytes(stop.color)
            out += bytes([_cs(stop.hold_s) >> 8, _cs(stop.hold_s) & 0xFF])
            out += bytes([_cs(stop.fade_s) >> 8, _cs(stop.fade_s) & 0xFF])
            out.append(_curve_code(stop.curve))
        return bytes(out)
    effect = flash_safe(look, min_flash_period_s)
    return bytes([LOOK_EFFECT]) + effect_payload(effect)


def _state_bytes(ops, transitions) -> bytes:
    out = bytearray([len(ops)])
    for op in ops:
        if op[0] == OP_TIMER:
            value = _cs(op[1])
            out += bytes([OP_TIMER, value >> 8, value & 0xFF])
        else:
            out += bytes([op[0], int(op[1])])
    out.append(len(transitions))
    for kind, param, target in transitions:
        out += bytes([kind, param, target])
    return bytes(out)


class CompiledApp:
    """One app's parts, before they become bytes. Held rather than serialised
    per template because looks are numbered *within* an app, and a bundle has
    to lay several apps out end to end."""

    def __init__(self, name: str, looks: list, states: list):
        self.name = name
        self.looks = looks    # LedEffect | sequencer.Sequence, in index order
        self.states = states  # already-serialised state blocks


class LookTable:
    """Numbers the looks an app uses, one entry per distinct look - a show that
    alternates between two carries two, not one per cue."""

    def __init__(self):
        self.order: list = []
        self._by_key: dict = {}

    def add(self, look) -> int:
        key = repr(look)
        if key not in self._by_key:
            self._by_key[key] = len(self.order)
            self.order.append(look)
        return self._by_key[key]


# What a cue naming a look that is not in the pool compiles to. Dark rather
# than skipped: the parser already warned, and dropping the cue would make a
# show quietly one shorter than the list the editor is showing you.
DARK = LedEffect(style="solid", color="#000000")


def _event_for(trigger: str):
    """A trigger name -> (event kind, parameter) for the package, or None.

    Mirrors `standalone.event_for` on the device side. `long_press` answers
    None on purpose: it is never *bound* (the parser refuses it in a menu), and
    the compiler emits it as "up one level" itself.
    """
    if trigger == "long_press":
        return None
    counts = {"short_press": 1, "double_tap": 2, "triple_tap": 3}
    count = counts.get(trigger)
    if count is None and trigger.startswith("tap_"):
        try:
            count = int(trigger[4:])
        except ValueError:
            count = None
    if count is None:
        return None
    return (EV_TAP, count)


def compile_lightshow(
    behavior: LightShowBehavior, name: str, looks: dict,
) -> CompiledApp:
    """A light show as a state machine: two states per cue, and no arithmetic.

    Every cue gets a *running* state (shows the look, sets the dwell) and a
    *held* one (shows the look, no timer). That is the whole of `run_lightshow`
    minus the loop, and the pair is what makes double tap a transition rather
    than a boolean the runtime would have to keep:

        running i --tap 1--> running i+1      --tap 2--> held i
        held i    --tap 1--> held i+1         --tap 2--> running i
        either    --hold-->  EXIT             --timer--> running i+1

    Holding advances *and stays held*, which is what the host does today: a
    show you have frozen is one you are stepping through by hand.

    `auto: false` starts on the held side, expressed by *rotating* the state
    list rather than by an app carrying a start index - every app in a bundle
    begins at state 0, which keeps one way of saying where a machine starts.
    """
    cues = behavior.cues
    if not cues:
        raise CompileError("%s: no cues to show" % name)
    if len(cues) * 2 > MAX_STATES:
        raise CompileError(
            "%s: %d cues is more than a package can hold" % (name, len(cues))
        )

    table = LookTable()
    indices = [table.add(looks.get(cue.look) or DARK) for cue in cues]
    count = len(cues)

    # Which (cue, held) pair each state index holds, start first.
    order = list(range(2 * count))
    if not behavior.auto:
        order = [1, 0] + order[2:]
    where = {old: new for new, old in enumerate(order)}

    states: list = []
    for old in order:
        i, held = old // 2, old % 2
        next_i = (i + 1) % count
        if held:
            states.append(_state_bytes(
                ((OP_SHOW, indices[i]),),
                (
                    (EV_TAP, 1, where[2 * next_i + 1]),
                    (EV_TAP, 2, where[2 * i]),
                    (EV_HOLD, 0, EXIT),
                ),
            ))
        else:
            dwell = cues[i].hold_s if cues[i].hold_s else behavior.dwell_s
            states.append(_state_bytes(
                ((OP_SHOW, indices[i]), (OP_TIMER, dwell)),
                (
                    (EV_TAP, 1, where[2 * next_i]),
                    (EV_TAP, 2, where[2 * i + 1]),
                    (EV_HOLD, 0, EXIT),
                    (EV_TIMER, 0, where[2 * next_i]),
                ),
            ))
    return CompiledApp(name, table.order, states)


def compile_signal(behavior: SignalBehavior, name: str) -> tuple:
    """A signal light: one state per position, and a press moves to the next.

    The cheapest template to compile, and the one that proves the format is not
    light-show-shaped: a position *carries* its colour (unlike a show's cue,
    which names one), so there is no pool to resolve and the whole app is N
    states in a ring.

    **What does not come across is the per-position action.** A position that
    fires a webhook or a MIDI note needs the phone, and this runs when there is
    no phone - so the light travels and the message does not. That is
    ARCHITECTURE.md's `Request` hole, unbuilt, and it is reported rather than
    left to be discovered on the button.
    """
    positions = behavior.states
    if not positions:
        raise CompileError("%s: no positions" % name)
    if len(positions) > MAX_STATES:
        raise CompileError("%s: too many positions" % name)

    table = LookTable()
    start = behavior.start_at % len(positions)
    order = [(start + i) % len(positions) for i in range(len(positions))]
    indices = [
        table.add(LedEffect(style=positions[i].style, color=positions[i].color))
        for i in order
    ]
    states = [
        _state_bytes(
            ((OP_SHOW, indices[i]),),
            ((EV_TAP, 1, (i + 1) % len(order)), (EV_HOLD, 0, EXIT)),
        )
        for i in range(len(order))
    ]
    dropped = [
        (positions[i].name, "its message needs the phone")
        for i in order if positions[i].action is not None
    ]
    return CompiledApp(name, table.order, states), dropped


def compile_menu(
    behavior: ActionsBehavior, name: str, app_index: dict, config: AppConfig,
) -> tuple:
    """A gesture map as one state, plus a list of what could not come with it.

    **A menu is the smallest app there is** - one state, one transition per
    gesture, no timer - and it is what makes a package a *button* rather than
    one app in a box, because its gestures are what reach the others.

    Two kinds of binding survive the trip: `enter_mode`, which becomes
    `OP_ENTER` when its target compiled too, and `standby`, which is already
    what leaving the root does. Everything else - a webhook, a MIDI note, a log
    row, a readout - needs the phone or storage this runtime has not got, so it
    is dropped **and named**. A menu that loses gestures still compiles: a
    button that does three of five things is a button, and refusing to build
    one is not a safer answer, only a less useful one.
    """
    transitions: list = []
    launches: list = []
    dropped: list = []
    for trigger, binding in behavior.actions.items():
        event = _event_for(trigger)
        if event is None:
            dropped.append((trigger, "not a gesture the package can carry"))
            continue
        action = resolve_action(config, binding)
        if isinstance(action, EnterModeAction):
            target = app_index.get(action.target)
            if target is None:
                dropped.append((trigger, "%s does not compile" % action.target))
                continue
            # **Launching is an op, not a transition target.** A transition
            # points at a *state* in this app; entering another app is
            # something a state *does*. So each launching gesture gets a state
            # of its own whose only job is the OP_ENTER - the same unrolling
            # the light show's cue ring uses, one layer up.
            transitions.append(event + (1 + len(launches),))
            launches.append(target)
        elif isinstance(action, StandbyAction):
            transitions.append(event + (EXIT,))
        elif action is None:
            dropped.append((trigger, "names an action that is not in the pool"))
        else:
            kind = type(action).__name__.replace("Action", "").lower()
            dropped.append((trigger, "%s needs the phone" % kind))

    # The root's own gesture, emitted rather than bound: `_parse_actions_body`
    # refuses a long press in a menu precisely so this can always mean "up",
    # and up from the root is off (TODO 104). `standalone` turns an EXIT with
    # nowhere to return to into sleep.
    transitions.append((EV_HOLD, 0, EXIT))
    states = [_state_bytes((), tuple(transitions))]
    states += [_state_bytes(((OP_ENTER, target),), ()) for target in launches]
    # No looks of its own: a state that shows nothing wears the button's own
    # IDLE light, which is what a menu should look like and what the host
    # already drops back to when a takeover ends.
    return CompiledApp(name, [], states), dropped


def _needs(behavior) -> str:
    """Why a template cannot compile yet, in the runtime's own vocabulary - so
    the answer names a missing *feature* rather than shrugging."""
    template = behavior.template
    if template in ("stopwatch", "counter"):
        return "variables and the durable document"
    if template in ("pomodoro", "metronome", "hotcold", "reaction"):
        return "expressions"
    if template == "notice":
        return "a real-time clock, and the 32.768 kHz crystal on the BOM"
    if template == "countdown":
        return "a compiler pass for its ramp - no new runtime feature"
    if template == "control":
        return "the phone, by design - every command it sends is MIDI or OSC"
    if template == "launcher":
        return "an app list the device can enumerate"
    return "a feature this runtime has not got"


def compiles(mode: Mode) -> bool:
    """Whether this build can turn `mode` into an app at all.

    Structural, and separate from `compile_app` because a menu cannot be
    compiled until every app it might name has an index - so the bundle needs
    to know *what is going in* before it can compile any of it.
    """
    return isinstance(
        mode.behavior, (LightShowBehavior, SignalBehavior, ActionsBehavior)
    )


def compile_app(mode: Mode, config: AppConfig, app_index: dict = None) -> tuple:
    """One mode -> (app, dropped gestures), or a CompileError saying what is
    missing. Only a menu ever drops anything, and only bindings."""
    behavior = mode.behavior
    if isinstance(behavior, LightShowBehavior):
        return compile_lightshow(behavior, mode.name, config.looks or {}), []
    if isinstance(behavior, SignalBehavior):
        return compile_signal(behavior, mode.name)
    if isinstance(behavior, ActionsBehavior):
        return compile_menu(behavior, mode.name, app_index or {}, config)
    raise CompileError(
        "%s is a %s; it needs %s" % (mode.name, behavior.template, _needs(behavior))
    )


def _app_bytes(app: CompiledApp, min_flash_period_s: float) -> bytes:
    label = app.name.encode("ascii", "replace")[:0xFF]
    if len(app.looks) > MAX_LOOKS:
        raise CompileError("%s: too many distinct looks" % app.name)
    if len(app.states) > MAX_STATES:
        raise CompileError("%s: too many states" % app.name)
    out = bytearray([len(label)])
    out += label
    out += bytes([len(app.looks), len(app.states), 0])
    for look in app.looks:
        out += _look_bytes(look, min_flash_period_s)
    for state in app.states:
        out += state
    return bytes(out)


def build(apps: list, start: int, min_flash_period_s: float) -> bytes:
    """Several compiled apps, and which one is the ambient layer, as one file."""
    if not apps:
        raise CompileError("nothing to install")
    if len(apps) > 0xFF or start >= len(apps):
        raise CompileError("too many apps, or a start that is not one of them")
    body = bytearray(MAGIC)
    body += bytes([FORMAT_VERSION, 0, len(apps), start])
    for app in apps:
        body += _app_bytes(app, min_flash_period_s)
    crc = crc16(bytes(body))
    body += bytes([crc >> 8, crc & 0xFF])
    return bytes(body)


def compilable(config: AppConfig) -> list:
    """Which modes this build can turn into a package, in config order."""
    return [mode for mode in config.modes if compiles(mode)]


def compile_config(config: AppConfig) -> tuple:
    """The whole config -> one package, and a report of what did not fit.

    **Two passes, because a menu names apps.** Everything that compiles is
    listed and numbered first; only then can a gesture bound to `enter_mode`
    become an `OP_ENTER` with an index in it. That ordering is also what lets a
    menu open another menu, which is how a button gets past five gestures.

    The ambient `actions` mode becomes the start app. With no ambient mode the
    first app *is* the button and leaving it sleeps.

    Returns `(package, report)`. The report is the point as much as the bytes
    are: what a standalone button will and will not do is a thing to read
    before flashing, not to discover by pressing.
    """
    going = compilable(config)
    if not going:
        raise CompileError("nothing in this config compiles yet")

    ambient = next(
        (
            mode for mode in going
            if isinstance(mode.behavior, ActionsBehavior)
            and isinstance(mode.activation, AlwaysActivation)
        ),
        None,
    )
    # The ambient menu is app 0 - the one entered at boot and returned to.
    order = ([ambient] if ambient is not None else []) + [
        mode for mode in going if mode is not ambient
    ]
    app_index = {mode.name: i for i, mode in enumerate(order)}

    apps: list = []
    dropped: list = []
    for mode in order:
        app, lost = compile_app(mode, config, app_index)
        apps.append(app)
        dropped.extend((mode.name, trigger, why) for trigger, why in lost)

    report = {
        "menu": ambient.name if ambient is not None else None,
        "apps": [mode.name for mode in order],
        "dropped": dropped,
        "skipped": [
            (mode.name, _needs(mode.behavior))
            for mode in config.modes if not compiles(mode)
        ],
    }
    return build(apps, 0, config.min_flash_period_s), report
