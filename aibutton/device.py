"""The host's view of the button hardware - the one seam the ESP32 plugs into.

    in   events: asyncio.Queue[TriggerType]
    out  set_led(state) / play_sound(sound) / start_loop(sound) / stop_loop()

`MockDevice` is in-memory - it backs the web UI's simulate-press buttons and
virtual device panel. `BLEDevice` ([ble_device.py](ble_device.py)) is the real
thing.

The three enums below are the *wire vocabulary*: gestures notified up, LED
states and sound commands written down. Their byte values are pinned lower
down, mirroring [firmware/protocol.py](../firmware/protocol.py) -
[test_protocol.py](../tests/test_protocol.py) fails if the two drift. That file
documents the wire layouts; this one documents what the host does with them.

Animations and tones render *on the device*; the wire carries the state, not
the frames.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class TriggerType(Enum):
    """A gesture, as detected on-device and notified to the host.

    Tap counts past five are expressible on the wire and have no member here
    yet - adding one is a host-side change with no reflash behind it, which is
    what parameterised gestures exist to buy (ROADMAP D5).
    """

    SHORT_PRESS = "short_press"
    LONG_PRESS = "long_press"
    DOUBLE_TAP = "double_tap"
    TRIPLE_TAP = "triple_tap"
    TAP_4 = "tap_4"
    # Five is far enough out to be unmistakably deliberate, which is what a
    # global on/off wants (TODO 28). Names come from protocol.TAP_NAMES, which
    # covers 4..9; what a count means to the *host* is this table, and a count
    # with no member here is dropped rather than fired - a stray extra tap on a
    # triple should do nothing, not something else.
    TAP_5 = "tap_5"


class LEDState(Enum):
    """What the LED is saying. One animation per member, rendered on-device."""

    IDLE = "IDLE"            # slow blue breathe
    LISTENING = "LISTENING"  # solid yellow
    THINKING = "THINKING"    # fast rainbow fade
    SUCCESS = "SUCCESS"      # green, 2 s
    ERROR = "ERROR"          # three red flashes
    ALERT = "ALERT"          # urgent red/white flash - an alarm is ringing
    TIMING = "TIMING"        # brisk cyan pulse - a stopwatch is running
    COUNTING = "COUNTING"    # magenta breathe - a counter is open
    WORKING = "WORKING"      # a Pomodoro work block is running
    RESTING = "RESTING"      # a Pomodoro break is running
    METRONOME = "METRONOME"  # a metronome is running, pulsing at the tapped tempo


class Sound(Enum):
    """A feedback tone. ALARM is also the looped one (start_loop/stop_loop)."""

    ACK = "ack"
    SUCCESS = "success"
    ERROR = "error"
    ALARM = "alarm"


# --- the wire, host side ----------------------------------------------
#
# Mirrors firmware/protocol.py. BLEDevice encodes with these tables;
# nothing else in the app needs them.

SERVICE_UUID = "f3641400-00b0-4240-ba50-05ca45bf8abc"
BUTTON_EVENT_UUID = "f3641401-00b0-4240-ba50-05ca45bf8abc"
LED_STATE_UUID = "f3641402-00b0-4240-ba50-05ca45bf8abc"
SOUND_CMD_UUID = "f3641403-00b0-4240-ba50-05ca45bf8abc"
LED_PALETTE_UUID = "f3641404-00b0-4240-ba50-05ca45bf8abc"
DEVICE_INFO_UUID = "f3641405-00b0-4240-ba50-05ca45bf8abc"
OTA_CONTROL_UUID = "f3641406-00b0-4240-ba50-05ca45bf8abc"  # reserved, unimplemented
LED_EFFECT_UUID = "f3641407-00b0-4240-ba50-05ca45bf8abc"
GESTURE_CONFIG_UUID = "f3641408-00b0-4240-ba50-05ca45bf8abc"

# --- what the device says it is ---------------------------------------
#
# The host asks rather than assumes (ROADMAP D8). PROTOCOL_VERSION is mirrored
# because both sides must agree what version 1 *means*; the firmware's own
# version is read off the device, never mirrored - a host that hard-coded it
# would only be describing itself.

PROTOCOL_VERSION = 1

CAP_LED = 0x0001
CAP_BUZZER = 0x0002
CAP_PALETTE = 0x0004
CAP_HAPTICS = 0x0008   # the five below are reserved: named so two future
CAP_BATTERY = 0x0010   # features cannot pick the same bit, and reported as 0
CAP_IMU = 0x0020       # until the thing behind them exists
CAP_MIC = 0x0040
CAP_OTA = 0x0080
CAP_EFFECT = 0x0100          # a look can be pushed without allocating an LEDState
CAP_GESTURE_PARAMS = 0x0200  # gestures carry a parameter; GESTURE_CONFIG is read
# The rainbow style reads its brightness from the effect's colour. It earns a
# bit despite being no wire change, because the failure without one is silent -
# see protocol.CAP_RAINBOW_LEVEL.
CAP_RAINBOW_LEVEL = 0x0400

CAPABILITY_NAMES = {
    CAP_LED: "led",
    CAP_BUZZER: "buzzer",
    CAP_PALETTE: "palette",
    CAP_HAPTICS: "haptics",
    CAP_BATTERY: "battery",
    CAP_IMU: "imu",
    CAP_MIC: "mic",
    CAP_OTA: "ota",
    CAP_EFFECT: "effect",
    CAP_GESTURE_PARAMS: "gesture-params",
    CAP_RAINBOW_LEVEL: "rainbow-level",
}

DEVICE_INFO_LEN = 6


@dataclass(frozen=True)
class DeviceInfo:
    """Version and capabilities, as reported by the thing on the other end."""

    protocol_version: int = 0
    firmware_version: tuple[int, int, int] = (0, 0, 0)
    capabilities: int = 0

    def has(self, capability: int) -> bool:
        return bool(self.capabilities & capability)

    @property
    def firmware(self) -> str:
        return "%d.%d.%d" % self.firmware_version

    @property
    def names(self) -> list[str]:
        """The capabilities it claims, for logs and the web UI."""
        return [
            name for bit, name in CAPABILITY_NAMES.items() if self.capabilities & bit
        ]


# What to believe about a device with no DEVICE_INFO characteristic. The only
# firmware that predates it is this project's own, which has an LED, a buzzer
# and palette rendering - so assuming all three keeps an un-reflashed button
# behaving exactly as it did, rather than going dark and silent the moment the
# host learns to ask.
ASSUMED_INFO = DeviceInfo(
    protocol_version=0,
    firmware_version=(0, 0, 0),
    capabilities=CAP_LED | CAP_BUZZER | CAP_PALETTE,
)


def decode_device_info(data) -> DeviceInfo | None:
    """Parse a DEVICE_INFO read, or None if it is too short to trust.

    Extra trailing bytes are ignored rather than rejected: the format grows by
    appending, so a newer device must stay readable by an older host. That is
    the half of forward compatibility the host is responsible for.
    """
    if data is None or len(data) < DEVICE_INFO_LEN:
        return None
    return DeviceInfo(
        protocol_version=data[0],
        firmware_version=(data[1], data[2], data[3]),
        capabilities=(data[4] << 8) | data[5],
    )

# The three original one-byte codes. Frozen: a device in someone else's
# pocket still sends these and they must not come to mean anything else.
GESTURE_CODES: dict[TriggerType, int] = {
    TriggerType.SHORT_PRESS: 0x01,
    TriggerType.LONG_PRESS: 0x02,
    TriggerType.DOUBLE_TAP: 0x03,
}
GESTURE_BY_CODE = {code: trigger for trigger, code in GESTURE_CODES.items()}

# Kinds that take a parameter byte. HOLD is reserved - see protocol.py.
GESTURE_TAP = 0x10
GESTURE_HOLD = 0x11

# What N taps means to the mode machine. This is the *host's* vocabulary, and
# it is deliberately shorter than the wire's: the firmware will count higher,
# but a count the host cannot name is a count nothing could be bound to.
TAP_TRIGGERS: dict[int, TriggerType] = {
    1: TriggerType.SHORT_PRESS,
    2: TriggerType.DOUBLE_TAP,
    3: TriggerType.TRIPLE_TAP,
    4: TriggerType.TAP_4,
    5: TriggerType.TAP_5,
}
TAP_COUNTS = {trigger: count for count, trigger in TAP_TRIGGERS.items()}

DEFAULT_MAX_TAPS = 2  # what an unconfigured detector does: today's behaviour
MAX_TAPS = max(TAP_TRIGGERS)


def decode_gesture(data) -> TriggerType | None:
    """A BUTTON_EVENT notify -> the gesture it means, or None if this host has
    no name for it.

    Both forms are accepted, and that asymmetry is the point: the host must
    understand everything a device might send, because the device is the half
    that is hard to update. One byte is a pre-v1 button, or a v1 one reporting a
    gesture that has always had a code; two is a kind plus its parameter.
    """
    if not data:
        return None
    code = data[0]
    if code == GESTURE_TAP:
        return TAP_TRIGGERS.get(data[1]) if len(data) > 1 else None
    if code == GESTURE_HOLD:
        return None  # reserved: no host vocabulary for hold levels yet
    return GESTURE_BY_CODE.get(code)


def gesture_config_payload(max_taps: int) -> bytes:
    """The GESTURE_CONFIG write: how long a tap burst the device should look
    for. Grows by appending, so a device that learns about hold levels reads a
    longer payload and an older one ignores the tail."""
    return bytes([max(DEFAULT_MAX_TAPS, min(int(max_taps), MAX_TAPS))])


def max_taps_for(triggers) -> int:
    """The longest tap burst any of `triggers` needs.

    Derived rather than configured, because counting further costs a double tap
    its instant response - so a button pays that only once something is actually
    bound to a triple.
    """
    return max(
        [DEFAULT_MAX_TAPS] + [TAP_COUNTS[t] for t in triggers if t in TAP_COUNTS]
    )

LED_CODES: dict[LEDState, int] = {
    LEDState.IDLE: 0x01,
    LEDState.LISTENING: 0x02,
    LEDState.THINKING: 0x03,
    LEDState.SUCCESS: 0x04,
    LEDState.ERROR: 0x05,
    LEDState.ALERT: 0x06,
    LEDState.TIMING: 0x07,
    LEDState.COUNTING: 0x08,
    LEDState.WORKING: 0x09,
    LEDState.RESTING: 0x0A,
    LEDState.METRONOME: 0x0B,
}

SOUND_CODES: dict[Sound, int] = {
    Sound.ACK: 0x01,
    Sound.SUCCESS: 0x02,
    Sound.ERROR: 0x03,
    Sound.ALARM: 0x04,
}

LOOP_FLAG = 0x80  # OR into a sound code to repeat it
STOP_LOOP_CMD = 0x00


def sound_command(sound: Sound, *, loop: bool = False) -> bytes:
    """The SOUND_CMD payload for playing (or looping) `sound`."""
    code = SOUND_CODES[sound]
    return bytes([code | LOOP_FLAG if loop else code])


# What an LED state looks like. The host owns the palette (config.json,
# edited in the web UI) and writes it down; the device renders it.
LED_STYLE_CODES: dict[str, int] = {
    "solid": 0x01,      # one colour, held
    "breathe": 0x02,    # fade between off and colour
    "flash": 0x03,      # hard on/off blink
    "alternate": 0x04,  # swap between colour and colour2
    "rainbow": 0x05,    # hue rotation; colour ignored
    "fade": 0x06,       # crossfade between colour and colour2
}
LED_STYLES = tuple(LED_STYLE_CODES)  # config validation + the web UI's picker

# Styles that ignore `color` / `color2` / `period_s`, so the editor can hide
# fields that would do nothing rather than invite pointless edits.
STYLE_USES_COLOR = {"solid", "breathe", "flash", "alternate", "fade"}
STYLE_USES_COLOR2 = {"alternate", "fade"}
# Styles that read `color` as a *level* rather than a hue. Rainbow is the only
# one: it generates its own hues and takes the colour's brightest channel as its
# brightness. Kept apart from STYLE_USES_COLOR on purpose - the editor has to
# offer a brightness slider here, not a colour picker, and a mode walking a ramp
# must know that pushing a colour into this style shows nothing.
STYLE_USES_LEVEL = {"rainbow"}
# There is deliberately no STYLE_USES_PERIOD: the only consumer is the editor
# deciding which fields to show, so it is declared once on the style descriptors
# in schema.js. A second copy here would have no reader and no drift test, and
# an unwatched mirror is worse than no mirror.

# Styles whose period is a hard on/off transition, which is what
# photosensitivity guidance is actually about. `breathe` and `fade` cross the
# same distance smoothly and do not strobe the same way, so the floor below does
# not apply to them.
STYLE_STROBES = {"flash", "alternate"}

# The recommended floor on how often a light may switch: 3 Hz, per WCAG 2.3.1's
# general-purpose flash threshold. It lives here rather than in config.py
# because both config and main need it and device.py is the module both may
# import (config imports device, never the reverse). It is the *default*, not
# the law - see CLAUDE.md's "The flash floor has one gate, and it is a setting".
SAFE_MIN_PERIOD_S = 1 / 3

_MAX_PERIOD_CS = 0xFFFF  # the wire carries centiseconds in two bytes


def rgb_bytes(color: str) -> bytes:
    """'#rrggbb' -> three bytes. Anything unparseable is black, which is
    visible as "that colour is wrong" rather than raising mid-write."""
    text = color.lstrip("#")
    if len(text) != 6:
        return b"\x00\x00\x00"
    try:
        return bytes.fromhex(text)
    except ValueError:
        return b"\x00\x00\x00"


def effect_payload(effect) -> bytes:
    """The nine bytes describing a look - the LED_EFFECT write, and the tail of
    a palette entry. `effect` is duck-typed on .style/.color/.color2/.period_s
    (config.LedEffect) so this module stays free of config imports."""
    period_cs = max(1, min(int(round(effect.period_s * 100)), _MAX_PERIOD_CS))
    return bytes(
        [
            LED_STYLE_CODES.get(effect.style, LED_STYLE_CODES["solid"]),
            *rgb_bytes(effect.color),
            *rgb_bytes(effect.color2),
            period_cs >> 8,
            period_cs & 0xFF,
        ]
    )


def palette_payload(state: LEDState, effect) -> bytes:
    """The LED_PALETTE write for one state: which state, then what it looks
    like. Same nine bytes as LED_EFFECT, so the two cannot drift."""
    return bytes([LED_CODES[state]]) + effect_payload(effect)


class ButtonDevice(ABC):
    """The button, whatever is behind it. Every feedback method is
    non-blocking and fire-and-forget: the loop only ever *waits* on
    `events`, so a slow or absent device can never stall the mode machine."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[TriggerType] = asyncio.Queue()
        self.palette: dict = {}
        self.max_taps: int = DEFAULT_MAX_TAPS
        # What this device says it is. Read, not asserted - which is why it is
        # an attribute rather than a sixth method on the seam. Anything that is
        # its own hardware knows its own answer; BLEDevice replaces this with
        # what it read off the wire.
        self.info: DeviceInfo = ASSUMED_INFO
        # How much earlier than its arrival a gesture from this device actually
        # happened - an attribute for `info`'s reason, and the correction games
        # subtract (see CLAUDE.md, "A gesture happened earlier than it arrived").
        #
        # Zero here because an *injected* gesture (`press` below, which is what
        # the web UI's simulate buttons and the tests use) is delivered the
        # instant it is made; a real detector is the late case, and BLEDevice
        # sets this accordingly. Known gap: simulate-press *into a real device*
        # borrows the radio's figure and reads early. That is a debugging path,
        # and the alternative is a per-event latency the whole queue would carry.
        self.press_latency_s: float = 0.0

    def press(self, trigger: TriggerType) -> None:
        """Inject a gesture as if the hardware had detected one - what the
        web UI's simulate-press buttons do. Concrete for every backend: a
        simulated press must take the same path as a real one."""
        log.info("button: %s", trigger.value)
        self.events.put_nowait(trigger)

    @abstractmethod
    def set_led(self, state: LEDState, effect=None) -> None:
        """Show `state`, optionally wearing `effect` instead of its palette entry.

        The optional look is how a mode gets its own appearance without
        allocating a global `LEDState` (ROADMAP D4); it is *ephemeral* - not
        stored, not named, gone at the next set_led. `state` stays required and
        still means something, being what the web UI and the status line report
        and what a device without the capability falls back to rendering.
        """

    @abstractmethod
    def play_sound(self, sound: Sound) -> None: ...

    @abstractmethod
    def start_loop(self, sound: Sound) -> None:
        """Repeat `sound` until stop_loop() - a ringing alarm mode."""

    @abstractmethod
    def stop_loop(self) -> None: ...

    def set_palette(self, palette: dict) -> None:
        """Tell the device what each LED state should look like.

        Called on startup and on every config change, so the palette is host
        state the device is told about - exactly like the LED state itself.
        Devices that render locally (MockDevice, whose LED is the browser) just
        remember it.
        """
        self.palette = palette

    def set_gesture_config(self, max_taps: int) -> None:
        """Tell the device how long a tap burst to look for.

        Device state the host asserts, exactly like the palette, and derived
        from what the config binds rather than configured by hand - see
        `max_taps_for`. A device that cannot be told keeps its default of 2,
        which is the behaviour it has always had.
        """
        self.max_taps = max(DEFAULT_MAX_TAPS, min(int(max_taps), MAX_TAPS))

    @property
    def connected(self) -> bool:
        """Whether feedback would actually reach hardware. Always true for a
        device that is its own hardware; BLEDevice overrides it."""
        return True

    async def start(self) -> None:
        """Begin talking to the hardware. Nothing to begin by default."""

    async def close(self) -> None:
        """Silence the device, then release it. Subclasses extend this rather
        than replacing it: a host exiting mid-alarm must not leave the buzzer
        looping on a device that is no longer listening to anyone."""
        self.stop_loop()


class MockDevice(ButtonDevice):
    """In-memory ButtonDevice: presses are injected rather than detected, and
    feedback is recorded rather than shown.

    This is the whole of dev mode. The web UI's simulate-press buttons call
    press(); its virtual device panel renders the LED state and plays the tones
    in the browser (main.py mirrors both into DeviceStatus). The attributes
    below are that same state, for tests to assert against.
    """

    def __init__(self) -> None:
        super().__init__()
        self.led_state = LEDState.IDLE
        # The look currently overriding led_state's palette entry, if any.
        # main.py mirrors it into DeviceStatus so the browser's virtual LED
        # shows what the real one would.
        self.led_effect = None
        self.last_sound: Sound | None = None
        self.looping: Sound | None = None
        # The mock's hardware is the browser, which renders the LED and plays
        # the tones, so it genuinely has all of these rather than inheriting
        # ASSUMED_INFO. Taps are counted in Python, so params are free too.
        self.info = DeviceInfo(
            protocol_version=PROTOCOL_VERSION,
            capabilities=(
                CAP_LED | CAP_BUZZER | CAP_PALETTE | CAP_EFFECT | CAP_GESTURE_PARAMS
            ),
        )

    def set_led(self, state: LEDState, effect=None) -> None:
        self.led_state = state
        self.led_effect = effect

    def play_sound(self, sound: Sound) -> None:
        self.last_sound = sound

    def start_loop(self, sound: Sound) -> None:
        self.looping = sound
        self.last_sound = sound

    def stop_loop(self) -> None:
        self.looping = None
