# The wire protocol, firmware side. Mirrored by aibutton/device.py;
# tests/test_protocol.py imports both halves and fails if they drift, so
# change one and change the other.
#
#   DEVICE_INFO     read    version + what this device can do  (ESP32 -> host)
#   BUTTON_EVENT    notify  gesture code (+ parameter)         (ESP32 -> host)
#   LED_STATE       write   LED state code         (host -> ESP32)
#   SOUND_CMD       write   sound command byte     (host -> ESP32)
#   LED_PALETTE     write   what one state looks like
#   LED_EFFECT      write   render *this look*, now, without naming a state
#   GESTURE_CONFIG  write   how many taps to look for
#   APP_PACKAGE     write   install an app package; read back the last result
#   OTA_CONTROL     -       reserved, not implemented (see below)
#
# Add never repurpose, ask never assume, append never insert: the rules for
# changing any of this are CLAUDE.md's "When you change the protocol", strict
# because there is no way to reflash a device you do not have. v1 is frozen.

SERVICE_UUID = "f3641400-00b0-4240-ba50-05ca45bf8abc"
BUTTON_EVENT_UUID = "f3641401-00b0-4240-ba50-05ca45bf8abc"
LED_STATE_UUID = "f3641402-00b0-4240-ba50-05ca45bf8abc"
SOUND_CMD_UUID = "f3641403-00b0-4240-ba50-05ca45bf8abc"
LED_PALETTE_UUID = "f3641404-00b0-4240-ba50-05ca45bf8abc"
DEVICE_INFO_UUID = "f3641405-00b0-4240-ba50-05ca45bf8abc"
LED_EFFECT_UUID = "f3641407-00b0-4240-ba50-05ca45bf8abc"
GESTURE_CONFIG_UUID = "f3641408-00b0-4240-ba50-05ca45bf8abc"
APP_PACKAGE_UUID = "f3641409-00b0-4240-ba50-05ca45bf8abc"

# Reserved, deliberately unimplemented. Claiming the UUID costs nothing now and
# means the day OTA is built it is not also a protocol break - "you cannot fix a
# bug in a key fob you do not have" is the whole argument for shipping the
# handshake before the hardware (ROADMAP D6).
OTA_CONTROL_UUID = "f3641406-00b0-4240-ba50-05ca45bf8abc"

# --- device info (read up) ---------------------------------------------
#
# What this device is and what it can do, so the host asks instead of assuming
# (ROADMAP D8). Six bytes today, growing only by appending:
#
#   [0]    protocol version
#   [1:4]  firmware version   major, minor, patch
#   [4:6]  capability bitmap, big-endian
#   [6:8]  installed app package CRC, big-endian; 0 when none  (appended v0.9)
#
# The CRC is here rather than on APP_PACKAGE because it answers *what is this
# device*, which is the question DEVICE_INFO exists for and the one a host asks
# on every connect. It is what lets a host say "the button is running an older
# package" instead of leaving you to find out by unplugging it.
#
# PROTOCOL_VERSION is mirrored on the host - both sides must agree what version
# 1 *means*. FIRMWARE_VERSION is not: the host reads it off the device, and a
# host that hard-coded it would only be describing itself.

PROTOCOL_VERSION = 1
# Bumped on any behaviour change, wire change or not, because the version is the
# only way to tell a flashed board from an un-flashed one. 0.9.0: the device
# runs compiled app packages with no host attached (apppkg/runtime/standalone),
# and accepts them over the air on APP_PACKAGE. 0.8.0: the board's own BOOT
# button is a second input, always on, in parallel with the wired one
# (hardware.BOOT_BUTTON_PIN).
FIRMWARE_VERSION = (0, 9, 0)

CAP_LED = 0x0001      # an LED came up and can be driven
CAP_BUZZER = 0x0002   # a buzzer came up and can be driven
CAP_PALETTE = 0x0004  # LED_PALETTE writes are understood and rendered

# Reserved: named now so two future features cannot quietly pick the same bit,
# and reported as 0 until the thing behind them exists.
CAP_HAPTICS = 0x0008
CAP_BATTERY = 0x0010
CAP_IMU = 0x0020
CAP_MIC = 0x0040
CAP_OTA = 0x0080

CAP_APP = 0x1000  # APP_PACKAGE is understood: apps can be installed over the air

CAP_EFFECT = 0x0100          # LED_EFFECT: a look can be pushed without a state code
CAP_GESTURE_PARAMS = 0x0200  # gestures carry a parameter, and GESTURE_CONFIG is read
# The rainbow style takes its brightness from the effect's colour. No wire
# change - those bytes were discarded for this style before - but it earns a bit
# anyway, because without one a slider doing nothing on un-reflashed firmware is
# indistinguishable from a slider that worked.
CAP_RAINBOW_LEVEL = 0x0400
# ...and its saturation from the effect's *second* colour, the same way and for
# the same reason: those bytes were discarded for this style, zero means full,
# and a slider that does nothing on un-reflashed firmware has to be tellable
# from one that works.
CAP_RAINBOW_SAT = 0x0800

DEVICE_INFO_LEN = 8


def device_info_payload(
    capabilities, firmware=None, protocol_version=PROTOCOL_VERSION, package_crc=0,
):
    """The DEVICE_INFO value for this device.

    `package_crc` is appended, never inserted: a host that predates it reads the
    first six bytes and ignores the rest, which is the half of forward
    compatibility the *host* owns (device.decode_device_info).
    """
    major, minor, patch = firmware if firmware is not None else FIRMWARE_VERSION
    return bytes([
        protocol_version & 0xFF,
        major & 0xFF, minor & 0xFF, patch & 0xFF,
        (capabilities >> 8) & 0xFF, capabilities & 0xFF,
        (package_crc >> 8) & 0xFF, package_crc & 0xFF,
    ])


# --- app package (written down) ---------------------------------------
#
# Installing an app, in four opcodes. A transfer rather than a poke, because a
# package is bigger than one ATT write and because the device must be able to
# refuse a half-arrived one:
#
#   [0x01, len_hi, len_lo]                   BEGIN   how much is coming
#   [0x02, off_hi, off_lo, ...bytes]         CHUNK   at this offset
#   [0x03]                                   COMMIT  verify, decode, store, apply
#   [0x04]                                   ABORT   forget it
#
# **BEGIN carries the length and no checksum.** A package already ends in a CRC
# over its own body, and a second CRC taken over the whole file - body plus that
# CRC - is a mathematical constant rather than a check. The length catches a
# torn transfer; the package's own CRC catches a corrupt one.
#
# **The device verifies before it stores, and keeps what it had if anything is
# wrong.** Length, CRC and a full decode all have to pass; only then is the file
# written. A failed push must never cost you the app that was already working -
# which is the same rule as "a package must never stop the button", applied to
# the moment the package arrives.
#
# **The payload is opaque to the transport.** Whoever compiled it - the PC
# today, a phone later, a store one day - the device sees bytes and a checksum
# and nothing else. That is deliberate: it is what makes the phone app a
# *client* of this protocol rather than a second implementation of it.
#
# A read of the characteristic answers one byte: how the last transfer went.
# What is *installed* is DEVICE_INFO's business, not this one's.

APP_BEGIN = 0x01
APP_CHUNK = 0x02
APP_COMMIT = 0x03
APP_ABORT = 0x04

APP_IDLE = 0x00        # nothing has been pushed since boot
APP_OK = 0x01          # the last package installed
APP_ERR_STATE = 0x02   # a chunk or commit with no begin
APP_ERR_SIZE = 0x03    # bigger than MAX_PACKAGE_BYTES, or the wrong length
APP_ERR_CRC = 0x04     # arrived intact-shaped but hashed wrong
APP_ERR_DECODE = 0x05  # a well-formed transfer of something that is not a package
APP_ERR_WRITE = 0x06   # the filesystem refused it

# Bigger than any package this compiler can produce and small enough that a
# hostile write cannot exhaust RAM: the buffer is allocated as it arrives.
MAX_PACKAGE_BYTES = 4096

# --- gestures (notified up) -------------------------------------------
#
# A notify is one byte, or two:
#
#   [code]         the classic three, unchanged and unchangeable
#   [kind, param]  a gesture kind plus a number - N taps, hold level N
#
# The device sends the oldest form that will do: legacy wherever one exists
# (1 tap, 2 taps, a hold), parameterised only past that. So a host that only
# understands one-byte notifies keeps working exactly as it did, and never
# receives a gesture it could not have named anyway (ROADMAP D5). The host's
# half of this asymmetry - read everything - is in device.decode_gesture.

SHORT_PRESS = 0x01
LONG_PRESS = 0x02
DOUBLE_TAP = 0x03

# Kinds, which take a parameter byte, in a range the legacy codes never reach.
GESTURE_TAP = 0x10   # param: how many taps
# Reserved, unimplemented - the detector emits one hold level today. Claiming
# the kind now makes hold levels a host-side change later instead of a reflash,
# the same bet OTA_CONTROL_UUID makes.
GESTURE_HOLD = 0x11  # param: which hold level

# Keyed by the host's TriggerType values: the wire carries exactly what the mode
# machine consumes.
GESTURE_CODES = {
    "short_press": SHORT_PRESS,
    "long_press": LONG_PRESS,
    "double_tap": DOUBLE_TAP,
}

# Taps beyond this are a fidget, not a gesture, and the limit keeps the name
# table finite so nothing has to parse a string on the device.
MAX_TAPS_LIMIT = 9

# What N taps is called. The first two are the mode machine's long-standing
# names; the rest exist so a new tap count is a host-side data change rather
# than another reflash, which is the entire point of parameterising.
TAP_NAMES = {1: "short_press", 2: "double_tap", 3: "triple_tap"}
for _count in range(4, MAX_TAPS_LIMIT + 1):
    TAP_NAMES[_count] = "tap_%d" % _count
TAP_COUNTS = {}
for _count in TAP_NAMES:
    TAP_COUNTS[TAP_NAMES[_count]] = _count


def gesture_payload(name):
    """The BUTTON_EVENT notify for a gesture, or None if it has no encoding:
    legacy one-byte where one exists, [GESTURE_TAP, count] past that."""
    code = GESTURE_CODES.get(name)
    if code is not None:
        return bytes([code])
    count = TAP_COUNTS.get(name)
    if count is None:
        return None
    return bytes([GESTURE_TAP, count])


# --- gesture config (written down) ------------------------------------
#
#   [0]  max taps  (2..MAX_TAPS_LIMIT)
#
# How many taps the detector should look for. The host derives it from what is
# actually bound and writes it on connect, so only a button with a long tap
# bound pays what counting further costs - see trigger.py's header. One byte
# today; it grows by appending (hold levels are the next field), so decode takes
# what it understands and ignores the rest.

DEFAULT_MAX_TAPS = 2


def decode_gesture_config(data):
    """max_taps for a GESTURE_CONFIG write, or None if there is nothing to read.

    Out-of-range values are clamped rather than rejected: a host asking for
    something impossible should get the closest thing that works, not a
    detector that silently kept the old setting."""
    if not data:
        return None
    count = data[0]
    if count < DEFAULT_MAX_TAPS:
        return DEFAULT_MAX_TAPS
    if count > MAX_TAPS_LIMIT:
        return MAX_TAPS_LIMIT
    return count

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

    The code is None on STOP_LOOP so callers can branch on it without knowing
    about the flag bit.
    """
    if cmd == STOP_LOOP:
        return None, False
    return cmd & ~LOOP, bool(cmd & LOOP)


# --- LED palette (written down) ---------------------------------------
# What each state *looks* like. The host owns it (config.json, edited in the web
# UI) and writes it on connect and on every edit; led.py's own table is only a
# fallback for running with no host. One write per state, ten bytes, so nothing
# outgrows a default ATT MTU:
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

EFFECT_LEN = 9
PALETTE_ENTRY_LEN = EFFECT_LEN + 1


def decode_effect(data, offset=0):
    """(style, (r,g,b), (r2,g2,b2), period_s) from `offset`, or None if there
    are not enough bytes - a truncated write should change nothing rather
    than render whatever the missing bytes would have been."""
    if data is None or len(data) - offset < EFFECT_LEN:
        return None
    period_s = ((data[offset + 7] << 8) | data[offset + 8]) / 100
    return (
        data[offset],
        (data[offset + 1], data[offset + 2], data[offset + 3]),
        (data[offset + 4], data[offset + 5], data[offset + 6]),
        period_s,
    )


def decode_palette_entry(data):
    """(led_code, style, (r,g,b), (r2,g2,b2), period_s) for one write, or None
    if the payload is the wrong length.

    A palette entry is a state code followed by exactly an effect, so this reads
    the layout one byte along rather than restating it - the two cannot drift
    into disagreeing about where the period is.
    """
    effect = decode_effect(data, 1)
    if effect is None:
        return None
    return (data[0],) + effect


# --- ephemeral effect (written down) ----------------------------------
#
# "Render this look, now." Same nine bytes as a palette entry minus the state
# code, because there is no state: it is not stored, not named, and lasts until
# the next LED_STATE write replaces it. This is what stops every one-off look
# costing a byte of the scarce LED_STATE namespace - see CLAUDE.md's "Don't
# burn a wire code" (ROADMAP D4).
