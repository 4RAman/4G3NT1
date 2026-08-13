# The wire protocol, firmware side. Mirrored by aibutton/device.py;
# tests/test_protocol.py imports both halves and fails if they drift, so
# change one and change the other.
#
#   DEVICE_INFO   read    version + what this device can do  (ESP32 -> host)
#   BUTTON_EVENT  notify  gesture code           (ESP32 -> host)
#   LED_STATE     write   LED state code         (host -> ESP32)
#   SOUND_CMD     write   sound command byte     (host -> ESP32)
#   LED_PALETTE   write   what one state looks like
#   OTA_CONTROL   -       reserved, not implemented (see below)
#
# Rules for changing any of this, because the next device may be in someone
# else's pocket and there is no way to reflash one you do not have:
#
#   Add, never repurpose.   A byte that meant something must not come to mean
#                           something else.
#   Ask, never assume.      DEVICE_INFO exists so a host can find out what it
#                           is talking to instead of inferring it from a
#                           version number. Gate every new capability on a bit.
#   Append, never insert.   DEVICE_INFO may grow fields on the end; a reader
#                           takes what it understands and ignores the rest.

SERVICE_UUID = "f3641400-00b0-4240-ba50-05ca45bf8abc"
BUTTON_EVENT_UUID = "f3641401-00b0-4240-ba50-05ca45bf8abc"
LED_STATE_UUID = "f3641402-00b0-4240-ba50-05ca45bf8abc"
SOUND_CMD_UUID = "f3641403-00b0-4240-ba50-05ca45bf8abc"
LED_PALETTE_UUID = "f3641404-00b0-4240-ba50-05ca45bf8abc"
DEVICE_INFO_UUID = "f3641405-00b0-4240-ba50-05ca45bf8abc"

# Reserved, deliberately unimplemented. Claiming the UUID now costs nothing
# and means the day OTA is built it is not also a protocol break - which
# matters because "you cannot fix a bug in a key fob you do not have" is the
# whole argument for shipping the handshake before the hardware (ROADMAP D6).
OTA_CONTROL_UUID = "f3641406-00b0-4240-ba50-05ca45bf8abc"

# --- device info (read up) ---------------------------------------------
#
# What this device is and what it can do, so the host asks instead of
# assuming (ROADMAP D8). Six bytes today:
#
#   [0]    protocol version
#   [1:4]  firmware version   major, minor, patch
#   [4:6]  capability bitmap, big-endian
#
# PROTOCOL_VERSION is mirrored on the host: both sides have to agree on what
# version 1 *means*. FIRMWARE_VERSION is not - the host reads it off the
# device, and a host that hard-coded it would be describing itself.

PROTOCOL_VERSION = 1
FIRMWARE_VERSION = (0, 4, 0)

CAP_LED = 0x0001      # an LED came up and can be driven
CAP_BUZZER = 0x0002   # a buzzer came up and can be driven
CAP_PALETTE = 0x0004  # LED_PALETTE writes are understood and rendered

# Reserved. Named now so two future features cannot quietly pick the same
# bit; all report 0 until the thing behind them exists.
CAP_HAPTICS = 0x0008
CAP_BATTERY = 0x0010
CAP_IMU = 0x0020
CAP_MIC = 0x0040
CAP_OTA = 0x0080

DEVICE_INFO_LEN = 6


def device_info_payload(capabilities, firmware=None, protocol_version=PROTOCOL_VERSION):
    """The DEVICE_INFO value for this device."""
    major, minor, patch = firmware if firmware is not None else FIRMWARE_VERSION
    return bytes([
        protocol_version & 0xFF,
        major & 0xFF, minor & 0xFF, patch & 0xFF,
        (capabilities >> 8) & 0xFF, capabilities & 0xFF,
    ])

# --- gestures (notified up) -------------------------------------------

SHORT_PRESS = 0x01
LONG_PRESS = 0x02
DOUBLE_TAP = 0x03

# Keyed by the host's TriggerType values: the wire carries exactly what the
# mode machine consumes.
GESTURE_CODES = {
    "short_press": SHORT_PRESS,
    "long_press": LONG_PRESS,
    "double_tap": DOUBLE_TAP,
}

# --- LED states (written down) ----------------------------------------
# One code per host LEDState; led.py renders the animation. An unknown code
# is ignored rather than blanking the LED.

LED_IDLE = 0x01
LED_LISTENING = 0x02
LED_THINKING = 0x03
LED_SUCCESS = 0x04
LED_ERROR = 0x05
LED_ALERT = 0x06
LED_TIMING = 0x07
LED_COUNTING = 0x08
LED_WORKING = 0x09
LED_RESTING = 0x0A
LED_METRONOME = 0x0B

LED_CODES = {
    "IDLE": LED_IDLE,
    "LISTENING": LED_LISTENING,
    "THINKING": LED_THINKING,
    "SUCCESS": LED_SUCCESS,
    "ERROR": LED_ERROR,
    "ALERT": LED_ALERT,
    "TIMING": LED_TIMING,
    "COUNTING": LED_COUNTING,
    "WORKING": LED_WORKING,
    "RESTING": LED_RESTING,
    "METRONOME": LED_METRONOME,
}

# --- sound commands (written down) ------------------------------------
# A sound code, optionally with LOOP set: play once, or repeat until
# STOP_LOOP. Covers play_sound / start_loop / stop_loop in one byte.

SOUND_ACK = 0x01
SOUND_SUCCESS = 0x02
SOUND_ERROR = 0x03
SOUND_ALARM = 0x04

SOUND_CODES = {
    "ack": SOUND_ACK,
    "success": SOUND_SUCCESS,
    "error": SOUND_ERROR,
    "alarm": SOUND_ALARM,
}

LOOP = 0x80  # OR into a sound code to repeat it (a ringing alarm)
STOP_LOOP = 0x00  # silence whatever is looping


def decode_sound(cmd):
    """(sound_code, looping) for a command byte; (None, False) to stop.

    Returns None for the sound code on STOP_LOOP so callers can branch on
    it without knowing about the flag bit.
    """
    if cmd == STOP_LOOP:
        return None, False
    return cmd & ~LOOP, bool(cmd & LOOP)


# --- LED palette (written down) ---------------------------------------
# What each state *looks* like. The host owns it (config.json, edited in the
# web UI) and writes it on connect and on every edit; led.py's own table is
# only a fallback for running with no host. One write per state, ten bytes,
# so nothing outgrows a default ATT MTU:
#
#   [0]     LED state code
#   [1]     style code
#   [2:5]   colour   r, g, b     (0-255)
#   [5:8]   colour2  r, g, b     (alternate and fade only)
#   [8:10]  period, centiseconds, big-endian (0.01-655.35 s)

STYLE_SOLID = 0x01      # one colour, held
STYLE_BREATHE = 0x02    # fade between off and colour
STYLE_FLASH = 0x03      # hard on/off blink
STYLE_ALTERNATE = 0x04  # swap between colour and colour2
STYLE_RAINBOW = 0x05    # hue rotation; colour ignored
STYLE_FADE = 0x06       # crossfade between colour and colour2

STYLE_CODES = {
    "solid": STYLE_SOLID,
    "breathe": STYLE_BREATHE,
    "flash": STYLE_FLASH,
    "alternate": STYLE_ALTERNATE,
    "rainbow": STYLE_RAINBOW,
    "fade": STYLE_FADE,
}

PALETTE_ENTRY_LEN = 10


def decode_palette_entry(data):
    """(led_code, style, (r,g,b), (r2,g2,b2), period_s) for one write, or
    None if the payload is the wrong length - a truncated write should
    leave the palette alone rather than render garbage."""
    if data is None or len(data) < PALETTE_ENTRY_LEN:
        return None
    period_s = ((data[8] << 8) | data[9]) / 100
    return (
        data[0],
        data[1],
        (data[2], data[3], data[4]),
        (data[5], data[6], data[7]),
        period_s,
    )
