# An app package, as the device reads it.
#
# ARCHITECTURE.md: *an app is a state machine with expressions, compiled to a
# binary package. It is not code.* This is the decoder half - the compiler is
# aibutton/appc.py, host-side, where the JSON parser already lives and is
# staying (the device validates a checksum and a version, never a schema).
#
# **The format is a table, and the host unrolls the loops into it.** A light
# show's "next cue, wrapping at the end" is not arithmetic here: the compiler
# emits one state per cue and points the last at the first. That is what buys
# a runtime with no expression evaluator, no variables and no allocation - and
# it is the honest first slice of the design rather than a shortcut, because
# apps that *do* need arithmetic (the metronome's tempo average) are exactly
# the ones ARCHITECTURE.md says need expressions. Those are the next increment;
# this decoder will grow a variables table beside `looks` when they arrive.
#
# Layout, all big-endian, all lengths one byte:
#
#   0   4   magic 'BTNA'
#   4   1   format version
#   5   1   flags (reserved, 0)
#   6   1   app count
#   7   1   start app - the ambient one, entered at boot
#           per app:
#             1   name length
#             n   name, ascii, for the log line and nothing else
#             1   look count
#             1   state count
#             1   start state
#                 looks    - see _read_look
#                 states   - see _read_state
#   -2  2   CRC-16/CCITT over every byte before it
#
# **A package holds several apps**, which is what makes the device a button
# rather than one app in a box: the start app is a menu whose gestures OP_ENTER
# the others, and leaving one returns to it. Format v1 held exactly one and was
# never flashed anywhere, so v2 replaces it outright rather than growing a
# compatibility path nothing needs.
#
# Nothing here raises. A short, corrupt or newer package returns None and the
# firmware carries on as the plain BLE peripheral it has always been, because
# a button that will not boot is worse than a button with no app on it.

MAGIC = b"BTNA"
FORMAT_VERSION = 2

# A look is either something the device animates by itself (an effect, the same
# nine bytes the LED_EFFECT characteristic already carries) or a schedule it
# walks (a stop list). Same split as the host's LedEffect vs Sequence, same
# reason: one is a style, the other is a timeline.
LOOK_EFFECT = 0x01
LOOK_SEQUENCE = 0x02

# What entering a state does. Named ops rather than "effects" to keep the word
# free for led.Effect, which is a different thing entirely.
OP_SHOW = 0x01   # + look index
OP_PLAY = 0x02   # + sound code (protocol.SOUND_*)
OP_TIMER = 0x03  # + centiseconds, big-endian: fire EV_TIMER after this long
OP_ENTER = 0x04  # + app index: hand the button to another app in this package

# What a transition waits for. Taps carry their count so one kind covers
# short/double/triple/N; a hold carries its level, which is 0 today and is
# where TODO 29's hold levels land without a format change.
EV_TAP = 0x01
EV_HOLD = 0x02
EV_TIMER = 0x03

# A transition target meaning "leave the app". Not an op, because leaving is a
# thing that happens *to* a state machine rather than an output it emits.
#
# Leaving the *start* app has nowhere above it to go, so standalone.py answers
# it with sleep - CLAUDE.md's "up one level, and at the root up means off",
# arrived at from the other end.
EXIT = 0xFF

STOP_LEN = 8    # r g b, hold_cs hi/lo, fade_cs hi/lo, curve
EFFECT_LEN = 9  # protocol.EFFECT_LEN - style, rgb, rgb2, period hi/lo
TRANSITION_LEN = 3


def crc16(data, end=None):
    """CRC-16/CCITT-FALSE over data[:end]. Twenty lines and no import, which
    is the whole reason it is this polynomial rather than a zlib call."""
    if end is None:
        end = len(data)
    crc = 0xFFFF
    for i in range(end):
        crc ^= data[i] << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class App:
    """One decoded app. Plain attributes and tuples - no dict lookups in the
    run loop, and nothing here is written to after decode."""

    def __init__(self, name, looks, states, start):
        self.name = name
        self.looks = looks    # tuple of ("effect", ...) / ("sequence", repeat, stops)
        self.states = states  # tuple of (ops, transitions)
        self.start = start


class Bundle:
    """Everything installed on the device: several apps and which one is the
    ambient layer."""

    def __init__(self, apps, start):
        self.apps = apps
        self.start = start


def _read_look(data, at):
    """(look, next offset) or (None, None)."""
    if at >= len(data):
        return None, None
    kind = data[at]
    at += 1
    if kind == LOOK_EFFECT:
        if len(data) - at < EFFECT_LEN:
            return None, None
        period_s = ((data[at + 7] << 8) | data[at + 8]) / 100
        look = (
            "effect",
            data[at],
            (data[at + 1], data[at + 2], data[at + 3]),
            (data[at + 4], data[at + 5], data[at + 6]),
            period_s,
        )
        return look, at + EFFECT_LEN
    if kind == LOOK_SEQUENCE:
        if len(data) - at < 2:
            return None, None
        repeat = bool(data[at])
        count = data[at + 1]
        at += 2
        if len(data) - at < count * STOP_LEN:
            return None, None
        stops = []
        for _ in range(count):
            stops.append((
                (data[at], data[at + 1], data[at + 2]),
                ((data[at + 3] << 8) | data[at + 4]) / 100,
                ((data[at + 5] << 8) | data[at + 6]) / 100,
                data[at + 7],
            ))
            at += STOP_LEN
        return ("sequence", repeat, tuple(stops)), at
    return None, None


def _read_state(data, at):
    """((ops, transitions), next offset) or (None, None)."""
    if at >= len(data):
        return None, None
    n_ops = data[at]
    at += 1
    ops = []
    for _ in range(n_ops):
        if at >= len(data):
            return None, None
        kind = data[at]
        at += 1
        if kind == OP_TIMER:
            if len(data) - at < 2:
                return None, None
            ops.append((kind, ((data[at] << 8) | data[at + 1]) / 100))
            at += 2
        elif kind in (OP_SHOW, OP_PLAY, OP_ENTER):
            if at >= len(data):
                return None, None
            ops.append((kind, data[at]))
            at += 1
        else:
            return None, None
    if at >= len(data):
        return None, None
    n_trans = data[at]
    at += 1
    if len(data) - at < n_trans * TRANSITION_LEN:
        return None, None
    transitions = []
    for _ in range(n_trans):
        transitions.append((data[at], data[at + 1], data[at + 2]))
        at += TRANSITION_LEN
    return (tuple(ops), tuple(transitions)), at


def _read_app(data, at):
    """(App, next offset) or (None, None)."""
    if at >= len(data):
        return None, None
    name_len = data[at]
    at += 1
    if len(data) - at < name_len + 3:
        return None, None
    try:
        name = bytes(data[at:at + name_len]).decode()
    except Exception:  # noqa: BLE001 - a name is a label, never a reason to fail
        name = "?"
    at += name_len
    n_looks, n_states, start = data[at], data[at + 1], data[at + 2]
    at += 3

    looks = []
    for _ in range(n_looks):
        look, at = _read_look(data, at)
        if look is None:
            return None, None
        looks.append(look)
    states = []
    for _ in range(n_states):
        state, at = _read_state(data, at)
        if state is None:
            return None, None
        states.append(state)
    if start >= n_states:
        return None, None
    return App(name, tuple(looks), tuple(states), start), at


def decode(data):
    """A package's bytes -> Bundle, or None with a printed reason.

    Every failure is the same failure from the outside: no app runs. The
    reasons are printed because the only debugger on a headless board is the
    serial log, and "it did nothing" is the hardest bug to chase.
    """
    if data is None or len(data) < 10:
        print("app: package too short")
        return None
    if bytes(data[0:4]) != MAGIC:
        print("app: not a package (bad magic)")
        return None
    if data[4] != FORMAT_VERSION:
        # Refused, not best-effort: a newer format may mean something different
        # by a byte this build would happily render.
        print("app: format v%d, this build reads v%d" % (data[4], FORMAT_VERSION))
        return None
    stored = (data[-2] << 8) | data[-1]
    if crc16(data, len(data) - 2) != stored:
        print("app: checksum failed - package ignored")
        return None

    n_apps = data[6]
    start = data[7]
    at = 8
    apps = []
    for i in range(n_apps):
        app, at = _read_app(data, at)
        if app is None:
            print("app: bad app %d" % i)
            return None
        apps.append(app)
    if not apps or start >= len(apps):
        print("app: start app %d does not exist" % start)
        return None
    return Bundle(tuple(apps), start)


class Receiver:
    """Assembles an APP_PACKAGE transfer, and refuses anything it cannot vouch
    for (protocol.APP_*).

    **It lives beside the decoder because it asks the same question.** "Is this
    a package" is answered in two halves - the checksum and the decode - and
    splitting them across two files would be splitting one decision.

    **Nothing is written until everything passes.** Length, CRC and a full
    decode all have to succeed before the caller is handed bytes to store, so a
    push that arrives torn, corrupt or simply wrong costs you nothing: the app
    already on the device keeps running. The buffer is dropped either way, so a
    failed transfer cannot leak RAM into the next one.
    """

    def __init__(self, limit):
        self.limit = limit
        self.result = 0  # protocol.APP_IDLE
        self._failed = False
        self.reset()

    def reset(self):
        self._buf = None

    def _fail(self, code):
        """Record the *first* thing that went wrong and drop the buffer.

        First, not last, because the host sends every frame before it reads the
        answer - so a transfer refused at BEGIN would otherwise be reported as
        "a chunk arrived with no transfer open", which is true and useless. The
        size that was refused is the fact worth having.
        """
        self.reset()
        if not self._failed:
            self.result = code
            self._failed = True

    def begin(self, length, err_size):
        self.reset()
        self._failed = False
        if length <= 0 or length > self.limit:
            self._fail(err_size)
            return False
        self._buf = bytearray(length)
        return True

    def chunk(self, offset, data, err_state, err_size):
        if self._buf is None:
            self._fail(err_state)
            return False
        if offset < 0 or offset + len(data) > len(self._buf):
            self._fail(err_size)
            return False
        self._buf[offset:offset + len(data)] = data
        return True

    def commit(self, err_state, err_crc, err_decode):
        """(bundle, bytes) if it is good, or (None, None) with `result` set.

        The buffer is released before either answer: a caller that gets None
        has nothing to clean up, and a caller that gets bytes owns them.
        """
        if self._buf is None:
            self._fail(err_state)
            return None, None
        data = bytes(self._buf)
        self.reset()
        # The package's own CRC is the integrity check - there is no second one
        # on the wire, because a checksum over a file that ends in its own
        # checksum is a constant (see device.package_crc). Checked here as well
        # as inside `decode` so "it arrived corrupt" and "it is not a package"
        # stay two different answers.
        if len(data) < 2 or crc16(data, len(data) - 2) != stamp(data):
            self._fail(err_crc)
            return None, None
        bundle = decode(data)
        if bundle is None:
            self._fail(err_decode)
            return None, None
        return bundle, data


def stamp(data):
    """A package's fingerprint: the CRC in its last two bytes. Mirrors
    `device.package_crc`, and read rather than recomputed for the reason
    spelled out there."""
    if data is None or len(data) < 2:
        return 0
    return (data[-2] << 8) | data[-1]


def load(path="app.pkg"):
    """The package on flash, or None if there isn't one. A missing file is the
    normal case - it is what "no app installed" looks like - so it is not an
    error and does not print."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    return decode(data)
