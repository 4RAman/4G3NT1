# ESP32 firmware

The hardware half of the [ESP32 split](../DESIGN-ESP32.md). It detects
gestures, notifies them to the host as one byte each, and renders the LED
state and buzzer tone the host writes back. Nothing else: modes, schedules,
the event log and the web UI all live in the Python app on the PC.

| File | What |
|---|---|
| `hardware.py` | **the file you edit** — pins, LED type, device name |
| `protocol.py` | UUIDs and byte codes; mirrors `aibutton/device.py` |
| `trigger.py` | gesture detection, ported from `aibutton/button.py` |
| `clock.py` | one wrap-safe monotonic clock |
| `led.py` | the state animations (colours come from the host's palette; the table here is only the fallback for running with no host) |
| `tones.py` / `buzzer.py` | the tone tables and the PWM player |
| `main.py` | the BLE peripheral and the button poll loop |

## Hardware

Defaults target the build this project has: an **ESP32-S3 Mini** and a 19 mm
illuminated momentary button (ChromaTek), whose switch and WS2812 come out as
five wires:

| Wire | Goes to | Why |
|---|---|---|
| switch common (white) | any GND | the internal pull-up supplies the other side |
| switch NO (green) | **GPIO4** (`BUTTON_PIN`) | pressed pulls it to GND |
| LED VDD (black) | **3V3** | not 5V — see below |
| LED GND | any GND | |
| LED data in (red) | **GPIO1** (`NEOPIXEL_PIN`) | |

**Power the LED from 3V3, not 5V.** A WS2812 wants its data line at ~0.7×VDD
to read a 1; the S3 drives 3.3 V, so a 5 V-powered pixel sits right on the
edge and fails intermittently — the failure looks like flicker or wrong
colours, not like nothing working. At 3V3 the levels match by construction.
Slightly dimmer is the whole cost.

Neither GPIO is special: **4** and **1** are plain S3 GPIOs, clear of the
strapping pins (0/3/45/46), the SPI flash (26–32), octal PSRAM (33–37) and
USB (19/20). Any other free pin works — change the constant, nothing else.

Other hardware is a line in `hardware.py`:

| Board | `hardware.py` |
|---|---|
| This build | defaults as shipped (`BUTTON_PIN = 4`, `NEOPIXEL_PIN = 1`) |
| Onboard WS2812 instead | `NEOPIXEL_PIN` per the table below |
| ESP32-C3 (onboard RGB) | `BUTTON_PIN = 9`, `NEOPIXEL_PIN = 8` |
| Any board + discrete RGB LED | `LED_KIND = "rgb_pwm"`, set `RGB_PINS` |
| A ring of *n* pixels | `NEOPIXEL_COUNT = n` |

Also:

- **Buzzer** — a piezo between `BUZZER_PIN` (GPIO5) and GND. Set
  `BUZZER_PIN = None` to run silent.
- **Discrete RGB LED** (only for `rgb_pwm`) — one 330R resistor per channel,
  common cathode to GND. Common anode: `RGB_ACTIVE_HIGH = False`.

A missing or miswired LED/buzzer never stops the firmware: those drivers
fall back to a no-op and the button still reports gestures.

### How many pixels is the ring?

`NEOPIXEL_COUNT` is how many WS2812s are chained on the data line; they all
show the same colour, so it only has to be *big enough*. Over-estimating is
harmless — the surplus bytes fall off the end of the chain — while
under-estimating leaves the rest of the ring dark. If part of the ring stays
unlit, raise it.

### Which pin is an onboard RGB LED on?

Only relevant if you drive a board's own WS2812 rather than the button's.
Boards sold as "ESP32-S3 Mini" disagree: **48** on the common Super Mini
clones, **47** on the LOLIN/Wemos S3 Mini, **21** on the Waveshare S3-Zero,
**38** on a DevKitC-1 v1.1. Rather than guess from the silkscreen, paste this
into the REPL (`mpremote connect COM5 repl`) and watch which number is
printed when the LED turns red:

```python
import time
from machine import Pin
from neopixel import NeoPixel
for pin in (48, 47, 21, 38):
    try:
        np = NeoPixel(Pin(pin, Pin.OUT), 1)
        np[0] = (40, 0, 0); np.write(); print("pin", pin); time.sleep(2)
        np[0] = (0, 0, 0); np.write()
    except Exception as exc:
        print("pin", pin, "unusable:", exc)
```

Put the winner in `hardware.py` as `NEOPIXEL_PIN`. If none of them light up,
the board may gate the LED behind a power pin (some Feather-style boards do);
`LED_KIND = "none"` keeps everything else working meanwhile.

## Flashing

`esptool` and `mpremote` are in `requirements-dev.txt`, and every step below
is also a VS Code task (see *Editing in VS Code*).

1. **MicroPython** — take the plain **ESP32_GENERIC_S3** build from
   [micropython.org/download](https://micropython.org/download/). Not the
   `SPIRAM_OCT` one (this board's PSRAM is quad, not octal), and there is no
   longer a `FLASH_4M` variant to choose — it was retired after v1.25.0
   because 1.26+ sizes the filesystem from the flash it detects. The app
   partition is 2 MB, so the generic build fits 4 MB boards fine.

   ```bash
   python -m esptool --chip esp32s3 --port COM3 erase-flash
   python -m esptool --chip esp32s3 --port COM3 write-flash 0 ESP32_GENERIC_S3-*.bin
   ```

   (esptool v5 renamed its commands to hyphens: `erase-flash`, `write-flash`.
   Baud rate is irrelevant here — the S3 talks over native USB, not a UART.)

2. **Power-cycle the board.** Not optional on this chip, and the step that
   wastes the most time when skipped: entering download mode over
   USB-Serial/JTAG sets a *sticky* force-download-boot flag that survives
   `--after hard-reset` and even `esptool run`. Until you unplug and replug
   the USB cable, the chip sits in the bootloader, prints nothing, and every
   `mpremote` command fails with `could not enter raw repl` — looking exactly
   like a bad flash. If you are unsure which state it is in:

   ```bash
   python -m esptool --chip esp32s3 --port COM3 --before no-reset --after no-reset chip-id
   ```

   If that answers *without* resetting the board, it is stuck in the
   bootloader; replug and try again. If it still will not run afterwards,
   suspect GPIO0 being held low — a stuck BOOT button does exactly this.
   (The project's button is on GPIO4 precisely so it can never cause that.)

3. **aioble** — not in the base firmware; install it onto the device
   (`mip` downloads on the PC and copies over the serial link):

   ```bash
   python -m mpremote mip install aioble
   ```

4. **This directory** — every file goes to the filesystem root (they import
   each other by bare name, and MicroPython runs `main.py` on boot):

   ```bash
   python -m mpremote cp protocol.py trigger.py clock.py hardware.py tones.py led.py buzzer.py main.py : + reset
   ```

   No port is given: `mpremote` uses the only attached board. With several
   plugged in, add `connect COM3` after `-m mpremote`, and run
   `python -m mpremote devs` to see which is which (Espressif's USB vendor
   ID is `303a`).

5. **Watch it boot** — `python -m mpremote repl` should print
   `AI Button firmware ready - advertising as AIButton`, and the LED should
   settle into a slow blue breathe. Ctrl-C stops the firmware for editing,
   Ctrl-D restarts it.

   No LED? It printed which backend failed and why, and the run continued —
   check `NEOPIXEL_PIN` and the LED's own wiring. Press the button and the
   REPL should print `button: short_press` whether or not the LED works;
   nothing printed means the switch wiring, not the firmware.

## Editing in VS Code

**PlatformIO is not the tool here.** It builds C/C++ (Arduino or ESP-IDF)
and has no MicroPython framework, so there is nothing to configure it with —
what it would give you (an upload button, a serial monitor, IntelliSense)
comes from three much smaller pieces, all already wired up in `.vscode/`.

**Extensions** — `.vscode/extensions.json` will offer these:

| Extension | Why |
|---|---|
| **Python** (`ms-python.python`) | interpreter, test runner |
| **Pylance** (`ms-python.vscode-pylance`) | IntelliSense, which the stubs below make useful |
| **Serial Monitor** (`ms-vscode.vscode-serial-monitor`) | watch the board's output at 115200 |

Deliberately *not* recommended: MicroPico, Pymakr, RT-Thread MicroPython.
They each bring their own file-sync and flashing model, which duplicates —
and can fight — the `mpremote` tasks below. If you want a device file
explorer in the sidebar, MicroPico (`paulober.pico-w-go`) is the most
maintained of them and does work with an ESP32 over serial, but expect to
pick one workflow or the other, not both.

**IntelliSense for MicroPython** — `machine`, `bluetooth` and `neopixel`
don't exist on your PC, so Pylance flags them until you install stubs:

```bash
python -m pip install -U --target typings --no-user micropython-esp32-stubs
```

or run the **MicroPython: refresh stubs** task. They land in `typings/`
(gitignored, type-checking only — never importable at runtime, so they can't
affect the tests). `aioble` has no published stub package, so
[`stubs/aioble.pyi`](../stubs/aioble.pyi) is a hand-written one covering
exactly the API the firmware uses. `.vscode/settings.json` puts `firmware/`
on the analysis path too, so the bare `import protocol` imports resolve.

**Tasks** (Ctrl-Shift-P → *Run Task*) — the mpremote workflow, one keystroke
each. `MicroPython: upload firmware` is the default build task, so Ctrl-Shift-B
copies every module to the board and resets it:

| Task | Does |
|---|---|
| MicroPython: list devices | which boards are attached |
| MicroPython: install aioble on device | one-time, after flashing MicroPython |
| **MicroPython: upload firmware** | copy all modules + reset (default build task) |
| MicroPython: REPL | live REPL and `print()` output |
| MicroPython: refresh stubs | (re)install the stubs into `typings/` |
| BLE probe / BLE probe: cycle everything | drive the firmware over BLE |
| Run the app (web UI) | the host app at localhost:8080 |
| Tests | the pytest suite |

Only one program can hold the serial port: close the REPL task before
uploading, and the Serial Monitor before either.

## Testing it

Without leaving the PC:

```bash
python tools/ble_probe.py           # gestures print as you press; type `idle`, `play ack`, …
python tools/ble_probe.py --cycle   # every LED animation and tone, then exit
```

`--cycle` is the one to run first: if all eight animations play and all four
tones sound, the LED, buzzer, and both write characteristics are good. Then
press the button and check that a tap, a hold, and a double tap print
`short_press`, `long_press`, and `double_tap`. nRF Connect on a phone works
too — the gesture characteristic is `f3641401-…`.

Half of this code is also tested on the host, since the modules that touch
no hardware import fine under CPython:

```bash
python -m pytest tests/test_trigger_port.py tests/test_firmware_button.py tests/test_firmware_feedback.py tests/test_protocol.py
```

Those check that the gesture detector matches the host's spec step for step,
that debounce rejects contact bounce, that every LED code has an animation
and every tone matches the WAV the web UI plays, and that the protocol
tables on both sides agree.

## Notes

- **One central at a time.** The firmware advertises, accepts a connection,
  and re-advertises when it drops — power-cycling either end recovers on its
  own.
- **Presses while disconnected are dropped**, not queued: replaying them
  later would fire modes against the wrong time of day. Offline buffering
  needs a time sync and is parked (see DESIGN-ESP32.md).
- **A ringing alarm stops on disconnect.** Nobody is left who could dismiss
  it, and a buzzer that rings until the battery dies is the one failure
  everyone notices.
