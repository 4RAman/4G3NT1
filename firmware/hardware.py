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

LED_BRIGHTNESS = 0.25     # WS2812s are painfully bright at full scale

# Byte order of the LED itself. MicroPython's neopixel driver assumes "GRB",
# which most strips are - but plenty of dev-board LEDs are wired "RGB", and
# then that assumption swaps two of your colours.
#
# Diagnose it by which colours are wrong, not by guessing:
#   red <-> green swapped (cyan shows as magenta, blue fine) -> "RGB"
#   everything right                                         -> "GRB"
#   blue involved in the swap                                -> "BGR" / "BRG"
NEOPIXEL_ORDER = "RGB"

RGB_PINS = (18, 19, 20)   # (red, green, blue) when LED_KIND == "rgb_pwm"
RGB_ACTIVE_HIGH = True    # False for a common-anode LED
RGB_PWM_FREQ = 1000

# --- buzzer ------------------------------------------------------------
# A piezo buzzer between the pin and GND. None disables sound entirely.
#
# Any free GPIO does. Avoid the S3's reserved ranges: 26-32 are the SPI
# flash, 33-37 go to octal PSRAM on boards that have it, and 0/3/45/46 are
# strapping pins. GPIO5 is on the header of every S3 Mini variant and free
# on all of them.
BUZZER_PIN = 5
BUZZER_VOLUME = 0.5  # 0..1; a piezo is loudest around 0.5 (50% duty cycle)
