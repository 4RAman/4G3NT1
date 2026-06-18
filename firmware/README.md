# 4G3NT1 firmware (ESP32-C3) — port in progress

The eventual home of the button on a self-contained **ESP32-C3** instead of a
Raspberry Pi. This directory is the **start** of that port: the
platform-independent, algorithmically hard parts are implemented and
**host-tested**, and the hardware I/O is scaffolded against the Arduino-ESP32 /
ESP-IDF APIs.

> **Status.** `lib/gesture` and `lib/synth` are implemented and pass native
> unit tests (`make test`, run with plain g++ — no ESP32 toolchain needed).
> The `src/` hardware glue (I2S audio, LEDC RGB, GPIO button) and
> `platformio.ini` are written but have **not** been compiled or flashed yet —
> that needs the `espressif32` PlatformIO platform on a machine with the device.
> The full mode machine is **not yet ported** (see Port plan).

## Why ESP32-C3

The sound-design research (`Smart Button Sound Design Research`, Google Drive)
specifies a **generative** audio identity — live wavetable synthesis, not WAV
playback — running on an ESP32-C3 with an I²S DAC/amp. That is the thing the Pi
can only approximate (it plays pre-rendered, round-robin WAVs). The C3 also
folds the LED, button, BLE and Wi-Fi onto one ~$2 chip with no OS to boot.

## Hardware

| Part | Connection |
|---|---|
| ESP32-C3 dev board | — |
| Momentary button | `GPIO9` → GND (active-low, internal pull-up) |
| RGB LED (common-cathode, 330 Ω/ch) | R `GPIO3`, G `GPIO4`, B `GPIO5` |
| MAX98357A I²S amp + speaker | BCLK `GPIO0`, LRC `GPIO1`, DIN `GPIO2`, GAIN/SD per datasheet |

Pins are placeholders set in `src/main.cpp` — adjust to your board.

## Layout

| Path | What | State |
|---|---|---|
| `lib/gesture/` | `TriggerDetector` — tap-chord → short/long/double/**quintuple** | ✅ implemented + tested |
| `lib/synth/` | generative synth: wavetable morph, exp ADSR, IIR portamento, soft-clip, micro-variation, the cue bank | ✅ implemented + tested |
| `src/hw_led.*` | LEDC RGB driver (mirrors `led.py`) | 🚧 scaffold (uncompiled) |
| `src/hw_audio.*` | I²S output + FreeRTOS render task | 🚧 scaffold (uncompiled) |
| `src/hw_button.*` | GPIO poll → detector | 🚧 scaffold (uncompiled) |
| `src/main.cpp` | setup/loop wiring (gesture → cue + LED, 5-tap on/off) | 🚧 scaffold (uncompiled) |
| `test/` | native unit tests for the pure cores | ✅ runs via `make test` |
| `Makefile` | host build of the cores + tests (g++) | ✅ |
| `platformio.ini` | ESP32-C3 build + `native` test env | 🚧 needs PlatformIO |

## Build & test

Host-native verification of the portable cores (works anywhere with g++):

```
cd firmware
make test        # builds + runs the gesture and synth tests
```

ESP32 build/flash (needs PlatformIO + the device):

```
pio run -e esp32c3            # compile
pio run -e esp32c3 -t upload  # flash
pio device monitor            # serial @115200
pio test -e native            # the same core tests under PlatformIO
```

## How the cores map to the Python build

| Python (Pi) | Firmware (C3) |
|---|---|
| `aibutton/button.py` `TriggerDetector` | `lib/gesture/trigger_detector.*` (faithful port; same timing constants and matrix) |
| `aibutton/audio.py` (synth tones + round-robin variants) | `lib/synth/*` — but **generative**: live wavetable/ADSR/portamento + per-trigger jitter instead of pre-rendered WAVs |
| `Sound` enum | `dsp::CueId` (+ `IdleChatter`, the R2-D2 babble the Pi omits) |
| `aibutton/led.py` `LEDState` | `src/hw_led.*` `LedState` (same states/animations) |
| `aibutton/config.py`, `aibutton/main.py` (mode machine) | **not yet ported** — see below |

## Port plan

1. **Cores (done).** Gesture detector + generative synth, host-tested.
2. **Hardware bring-up.** Compile `src/` with PlatformIO; verify on the bench
   that a press lights the LED and plays a cue, and the 5-tap toggles off/on.
3. **Mode machine.** Port `config.py`'s data model (templates / activations /
   modes) and `main.py`'s runtime (ambient resolution, the scheduler, the
   alarm/stopwatch/counter/pomodoro takeovers, the contextual 5-tap). The logic
   is platform-agnostic; only the I/O it calls changes. Config can be parsed
   from JSON with ArduinoJson (already a dep) so the existing `config.json`
   format carries over.
4. **Storage.** Replace SQLite with NVS counters / a small ring log in flash
   (or an SD card) behind the same `store.py` interface (`log_event`,
   `count_today`, `toggle_timer`, `total_today`, `log_duration`).
5. **Connectivity.** Re-add the BLE peripheral and, optionally, the web UI /
   REST API (served from the C3 over Wi-Fi) so the existing front-end still
   works.
6. **MIDI (stretch).** The research doc's user-MIDI playback (VLQ parser +
   monophonic last-note-priority voice with glide) on top of the synth Voice.

## Production notes

- The synth uses `float` for clarity. The C3 has no hardware FPU; the hot path
  (oscillator, envelope, soft-clip) should move to **fixed-point (Q16)** per the
  research doc before shipping. The algorithms are unchanged — only the numeric
  type.
- The square wavetable is naive (aliases at high pitch); swap in a
  **bandlimited** table for the final voice.
