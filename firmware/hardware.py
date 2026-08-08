# Board wiring - the one file you edit for your ESP32.
#
# Defaults target the build this project actually has: an **ESP32-S3 Mini**
# with a 19 mm illuminated momentary button (ChromaTek), whose switch and
# WS2812 are wired out to two GPIOs. Other boards still work - a board with
# an onboard WS2812 only changes NEOPIXEL_PIN, and a classic ESP32 with a
# discrete common-cathode RGB LED is LED_KIND = "rgb_pwm".
#
#   button common (white)  -> GND        LED VDD (black) -> 3V3
#   button NO     (green)  -> BUTTON_PIN LED GND         -> GND
#                                        LED data (red)  -> NEOPIXEL_PIN

DEVICE_NAME = "AIButton"  # what the host scans for; match config.json's ble_device_name

# --- button ------------------------------------------------------------
# Any momentary switch between the pin and GND, using the internal pull-up:
# the switch's normally-open contact here, its common to GND.
#
# GPIO4 is a plain S3 GPIO, clear of the strapping pins (0/3/45/46), so the
# button cannot influence boot. (That is the reason not to reuse GPIO0/BOOT
# once a real button exists: held low *at power-on* it enters download mode
# instead of running.)
BUTTON_PIN = 4
BUTTON_PULL_UP = True   # False if you wire your own pull-down + button to 3V3
BUTTON_ACTIVE_LOW = True  # pressed reads 0 (the pull-up case)

# --- LED ---------------------------------------------------------------
# "neopixel" - WS2812s on one data line (in the button, or onboard)
# "rgb_pwm"  - a discrete RGB LED, one PWM pin per channel + 330R resistors
# "none"     - no LED; the firmware still runs and reports gestures
LED_KIND = "neopixel"

# GPIO1 for the button's LED: a plain GPIO on the S3, clear of the
# strapping pins (0/3/45/46), the SPI flash (26-32), octal PSRAM (33-37) and
# USB (19/20). Any free pin does - WS2812 data is an ordinary push-pull
# output - so if your board routes something else to GPIO1, move this and
# nothing else changes.
#
# For an *onboard* WS2812 instead, boards sold as "ESP32-S3 Mini" disagree:
# 48 on the common Super Mini clones and DevKitC-1 v1.0, 47 on the
# LOLIN/Wemos S3 Mini, 21 on the Waveshare S3-Zero, 38 on DevKitC-1 v1.1.
# README.md has a snippet that identifies it in ten seconds.
NEOPIXEL_PIN = 1

# How many WS2812s are chained on that data line. All of them show the same
# colour - the LED is one indicator, not a display - so this only has to be
# big enough. Over-estimating is harmless (surplus bytes fall off the end of
# the chain); under-estimating leaves the rest of the ring dark.
NEOPIXEL_COUNT = 1

# 0..1, scaling every colour before it reaches the button's WS2812.
#
# Full scale. Note this does *not* fix a warm/orange cast on white: the
# onboard LED and this one are written identical bytes (MultiBackend fans one
# set() out to both), so a colour difference between them is electrical, not
# arithmetic - see "white looks orange" in README.md. Raising this makes the
# LED brighter and, if anything, the cast slightly stronger, because more
# current means more droop on a rail that is already marginal for blue.
LED_BRIGHTNESS = 1.0

# Byte order of the LED itself. MicroPython's neopixel driver assumes "GRB",
# which most strips are - but plenty of dev-board LEDs are wired "RGB", and
# then that assumption swaps two of your colours.
#
# Diagnose it against *what is set here now*, not against an absolute: whatever
# two components look swapped, swap those two letters in this name.
#
# This LED and the onboard one are NOT the same order - the button's WS2812 is
# RGB, the board's is GRB. That is normal (they are different parts from
# different makers) and it is why each has its own setting rather than sharing
# one.
#
# White is useless for this. It is three equal components, so every
# permutation of it is still white - a byte-order fault only shows on colours
# with unequal components (red, green, cyan, magenta).
NEOPIXEL_ORDER = "RGB"

RGB_PINS = (18, 19, 20)   # (red, green, blue) when LED_KIND == "rgb_pwm"
RGB_ACTIVE_HIGH = True    # False for a common-anode LED
RGB_PWM_FREQ = 1000

# --- onboard LED (optional, mirrors the LED above) ----------------------
# Most "ESP32-S3 Mini" boards also carry their own WS2812 next to the USB
# port, separate from the one wired into the button. Set this to drive it
# too - it always shows the same state as the LED above, just as a second,
# always-visible copy (handy with the button's LED buried inside a case).
# None (the default) leaves it dark.
#
# Pin disagrees by board: 48 on the common Super Mini clones and DevKitC-1
# v1.0, 47 on the LOLIN/Wemos S3 Mini, 21 on the Waveshare S3-Zero, 38 on
# DevKitC-1 v1.1. README.md has a snippet that identifies it in ten seconds.
# 48 is measured, not guessed: confirmed lit on this build's Melife
# ESP32-S3FH4R2 ("Super Mini"-style clone). Another board is another number -
# the REPL snippet in README.md identifies it.
ONBOARD_NEOPIXEL_PIN = 48

ONBOARD_NEOPIXEL_ORDER = "GRB"  # onboard WS2812s are usually wired GRB
ONBOARD_LED_BRIGHTNESS = 0.25

# --- buzzer ------------------------------------------------------------
# A piezo buzzer between the pin and GND. None disables sound entirely.
#
# Any free GPIO does. Avoid the S3's reserved ranges: 26-32 are the SPI
# flash, 33-37 go to octal PSRAM on boards that have it, and 0/3/45/46 are
# strapping pins. GPIO5 is on the header of every S3 Mini variant and free
# on all of them.
BUZZER_PIN = 5
BUZZER_VOLUME = 0.5  # 0..1; a piezo is loudest around 0.5 (50% duty cycle)
