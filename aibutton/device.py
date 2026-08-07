"""The host's view of the button hardware - the one seam the ESP32 plugs into.

Everything the app says to hardware goes through `ButtonDevice`, and
everything hardware says back arrives as a `TriggerType` on its `events`
queue. That is the whole contract:

    in   events: asyncio.Queue[TriggerType]
    out  set_led(state) / play_sound(sound) / start_loop(sound) / stop_loop()

`MockDevice` is in-memory - it backs the web UI's simulate-press buttons and
virtual device panel. `BLEDevice` ([ble_device.py](ble_device.py)) is the
real thing.

The three enums below are the *wire vocabulary*: gestures notified up, LED
states and sound commands written down. Their byte values are pinned at the
bottom of this module, mirroring
[firmware/protocol.py](../firmware/protocol.py) -
[test_protocol.py](../tests/test_protocol.py) fails if the two drift.

Animations and tones render *on the device*; the wire carries the state,
not the frames.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum

log = logging.getLogger(__name__)


class TriggerType(Enum):
    """A gesture, as detected on-device and notified to the host."""

    SHORT_PRESS = "short_press"
    LONG_PRESS = "long_press"
    DOUBLE_TAP = "double_tap"


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

GESTURE_CODES: dict[TriggerType, int] = {
    TriggerType.SHORT_PRESS: 0x01,
    TriggerType.LONG_PRESS: 0x02,
    TriggerType.DOUBLE_TAP: 0x03,
}
GESTURE_BY_CODE = {code: trigger for trigger, code in GESTURE_CODES.items()}

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
STYLE_USES_PERIOD = {"breathe", "flash", "alternate", "rainbow", "fade"}

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


def palette_payload(state: LEDState, effect) -> bytes:
    """The LED_PALETTE write for one state. `effect` is duck-typed on
    .style/.color/.color2/.period_s (config.LedEffect) so this module stays
    free of config imports."""
    period_cs = max(1, min(int(round(effect.period_s * 100)), _MAX_PERIOD_CS))
    return bytes(
        [
            LED_CODES[state],
            LED_STYLE_CODES.get(effect.style, LED_STYLE_CODES["solid"]),
            *rgb_bytes(effect.color),
            *rgb_bytes(effect.color2),
            period_cs >> 8,
            period_cs & 0xFF,
        ]
    )


class ButtonDevice(ABC):
    """The button, whatever is behind it. Every feedback method is
    non-blocking and fire-and-forget: the loop only ever *waits* on
    `events`, so a slow or absent device can never stall the mode machine."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[TriggerType] = asyncio.Queue()
        self.palette: dict = {}

    def press(self, trigger: TriggerType) -> None:
        """Inject a gesture as if the hardware had detected one - what the
        web UI's simulate-press buttons do. Concrete for every backend: a
        simulated press must take the same path as a real one."""
        log.info("button: %s", trigger.value)
        self.events.put_nowait(trigger)

    @abstractmethod
    def set_led(self, state: LEDState) -> None: ...

    @abstractmethod
    def play_sound(self, sound: Sound) -> None: ...

    @abstractmethod
    def start_loop(self, sound: Sound) -> None:
        """Repeat `sound` until stop_loop() - a ringing alarm mode."""

    @abstractmethod
    def stop_loop(self) -> None: ...

    def set_palette(self, palette: dict) -> None:
        """Tell the device what each LED state should look like.

        Called on startup and whenever the config changes, so the palette is
        host state the device is told about - exactly like the LED state
        itself. Devices that render locally (MockDevice, whose LED is the
        browser) just remember it.
        """
        self.palette = palette

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
    """In-memory ButtonDevice: presses are injected rather than detected,
    and feedback is recorded rather than shown.

    This is the whole of dev mode. The web UI's simulate-press buttons call
    press(); its virtual device panel renders the LED state and plays the
    tones in the browser (main.py mirrors both into DeviceStatus). The
    attributes below are that same state, for tests to assert against.
    """

    def __init__(self) -> None:
        super().__init__()
        self.led_state = LEDState.IDLE
        self.last_sound: Sound | None = None
        self.looping: Sound | None = None

    def set_led(self, state: LEDState) -> None:
        self.led_state = state

    def play_sound(self, sound: Sound) -> None:
        self.last_sound = sound

    def start_loop(self, sound: Sound) -> None:
        self.looping = sound
        self.last_sound = sound

    def stop_loop(self) -> None:
        self.looping = None
