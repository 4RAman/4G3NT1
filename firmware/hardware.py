# Board wiring - the one file you edit for your ESP32.
#
# Defaults target the build this project actually has: an **ESP32-S3 Mini** with
# a 19 mm illuminated momentary button (ChromaTek), switch and WS2812 wired out
# to two GPIOs. Other boards work - an onboard WS2812 only changes
# NEOPIXEL_PIN, a discrete common-cathode RGB LED is LED_KIND = "rgb_pwm".
#
# **IMPORTANT: the button's wire colours are non-standard.** Verify against
# these when re-soldering; black=ground / red=power does *not* hold here.
#
#   button common (white)  -> GND        LED VDD (black) -> 3V3
#   button NO     (green)  -> BUTTON_PIN LED GND         -> GND
#                                        LED data (red)  -> NEOPIXEL_PIN
#
# **LED VDD on 3V3 is a known fault, not a choice** - see TODO 0c. A WS2812 is
# a 5 V part: its red die runs at ~2 V and its green and blue dies at ~3.2 V,
# so on a 3.3 V rail only red keeps enough headroom for its current sink to
# regulate. Green and blue starve, and white comes out orange. Moving VDD to
# 5 V is the fix, and it drags the data threshold (~0.7 x VDD) up with it - a
# marginal threshold fails as *flicker*, not silence. Do both or neither:
# series diode or level shifter, never 5 V alone.
#
# **Pins to avoid on the S3**, which every pin you *wire something to* is
# chosen against: the strapping pins (0/3/45/46), the SPI flash (26-32), octal
# PSRAM (33-37) and USB (19/20). The strapping pins are a requirement rather
# than a nicety - a button holding one low *at power-on* enters download mode
# instead of running, and the board then sits silent in the bootloader until it
# is physically replugged, which looks exactly like a failed flash.
#
# `BOOT_BUTTON_PIN` is the one deliberate exception, and it is not a
# contradiction: GPIO0 already *has* a switch on it, put there by whoever made
# the board, and reading a pin does not strap anything. The caveat is about
# pressing it while the board starts, and it is written out below.

DEVICE_NAME = "AIButton"  # what the host scans for; match config.json's ble_device_name

# --- button ------------------------------------------------------------
# Any momentary switch between the pin and GND, using the internal pull-up: the
# switch's normally-open contact - **the green wire** - here, its common to GND.
BUTTON_PIN = 10
BUTTON_PULL_UP = True   # False if you wire your own pull-down + button to 3V3
BUTTON_ACTIVE_LOW = True  # pressed reads 0 (the pull-up case)

# The board's own **BOOT** button, wired in parallel with the one above: either
# is a press, and the firmware cannot tell them apart. It is always on, and
# that is the point - a board whose switch is unsoldered, unplugged or sat on
# is still a button you can press, which is exactly the position this project
# was in on 2026-08-29 (TODO 89).
#
# GPIO0 on every ESP32-S3 dev board seen here, with the switch to GND and a
# pull-up already on the board; the internal pull-up is enabled anyway, so it
# works on a board that lacks one. Set to None to turn it off.
#
# **The strapping-pin caveat is real and applies to *pressing* it, not to
# reading it.** GPIO0 is a strapping pin: held low **at power-on or reset** the
# chip enters download mode instead of running, and then sits silent in the
# bootloader until it is physically replugged - which looks exactly like a
# failed flash. Configuring it as an input changes nothing about that. Press it
# while the board is running, never while it is starting.
BOOT_BUTTON_PIN = 0
BOOT_BUTTON_ACTIVE_LOW = True

# --- LED ---------------------------------------------------------------
# "neopixel" - WS2812s on one data line (in the button, or onboard)
# "rgb_pwm"  - a discrete RGB LED, one PWM pin per channel + 330R resistors
# "none"     - no LED; the firmware still runs and reports gestures
LED_KIND = "neopixel"

# WS2812 data in - **the red wire**, *not* power. Any free pin does (this is an
# ordinary push-pull output), so move it if your board routes something else
# here and nothing else changes.
NEOPIXEL_PIN = 12

# How many WS2812s are chained on that data line. All show the same colour - the
# LED is one indicator, not a display - so this only has to be big enough:
# over-estimating is harmless (surplus bytes fall off the end of the chain),
# under-estimating leaves the rest of the ring dark.
NEOPIXEL_COUNT = 1

# 0..1, scaling every colour before it reaches the button's WS2812. Not the
# knob for the orange cast on white - that is the 3V3 fault above, and turning
# this up makes it slightly worse, since more current means more droop on a rail
# already marginal for blue. Nor is a difference between the two LEDs arithmetic:
# MultiBackend fans one set() out to both, so they get identical bytes.
LED_BRIGHTNESS = 1.0

# Byte order of the LED itself. MicroPython's neopixel driver assumes "GRB",
# which most strips are - but plenty of dev-board LEDs are wired "RGB", and then
# that assumption swaps two of your colours. This LED and the onboard one are
# NOT the same order; that is normal (different parts, different makers) and is
# why each has its own setting rather than sharing one. Both values below are
# measured, not guessed.
#
# Diagnose against *what is set here now*, not an absolute: whatever two
# components look swapped, swap those two letters. Push known colours from the
# Lights picker's Diagnostic row and read the result per CLAUDE.md's byte-order
# gotcha - which colours talk, and what one-LED-wrong vs both-wrong means.
NEOPIXEL_ORDER = "GRB"

RGB_PINS = (18, 19, 20)   # (red, green, blue) when LED_KIND == "rgb_pwm"
RGB_ACTIVE_HIGH = True    # False for a common-anode LED
RGB_PWM_FREQ = 1000

# --- onboard LED (optional, mirrors the LED above) ----------------------
# Most "ESP32-S3 Mini" boards also carry their own WS2812 next to the USB port,
# separate from the one in the button. Set this to drive it too, as a second
# always-visible copy of the same state (handy with the button's LED buried in a
# case); None leaves it dark.
#
# The pin disagrees by board: 48 on the common Super Mini clones and DevKitC-1
# v1.0, 47 on the LOLIN/Wemos S3 Mini, 21 on the Waveshare S3-Zero, 38 on
# DevKitC-1 v1.1. 48 is measured on this build's Melife ESP32-S3FH4R2 ("Super
# Mini" clone); README.md has a snippet that identifies another board's.
ONBOARD_NEOPIXEL_PIN = 48
ONBOARD_NEOPIXEL_ORDER = "RGB"  # measured; see NEOPIXEL_ORDER above
ONBOARD_LED_BRIGHTNESS = 0.25

# --- buzzer ------------------------------------------------------------
# A piezo buzzer between the pin and GND. None disables sound entirely. Any
# free GPIO clear of the exclusions above does; GPIO5 is on the header of
# every S3 Mini variant and free on all of them.
BUZZER_PIN = 5
BUZZER_VOLUME = 0.5  # 0..1; a piezo is loudest around 0.5 (50% duty cycle)
