# Design: the ESP32 split

Status: **done — this document is history.** All four phases have landed: an
ESP32-S3 Mini runs the firmware, the host connects over BLE, and a physical
press drives the mode machine on the PC. Keep reading for *why the split is
shaped this way* — the protocol, the device seam, and the decisions baked
into both. For what happens next, see [ROADMAP.md](ROADMAP.md); for the
near-term list, [TODO.md](TODO.md). The Raspberry Pi build this replaces is
preserved at the git tag **`pi-legacy`**.

> One decision here is on the clock. *"The host must be awake"* is listed
> below as accepted for the tethered v1 — it stops being acceptable at
> Stage 4, when the button goes in a pocket. ROADMAP **D1** is where that
> gets settled.

Since shipped on top of the original plan: a configurable **LED palette**
(colours live in `config.json`, edited in the web UI, pushed to the device
live) and a **Pomodoro** template with its own `WORKING`/`RESTING` states.

## The idea in one line

> The button becomes an ESP32 **BLE peripheral** that detects gestures and
> shows feedback; everything else — modes, scheduler, store, web UI — is the
> existing Python app running on the PC as the **BLE central**.

## Why

- The Pi was an always-on Linux box to read one button and drive one LED.
  An ESP32 does the hardware edge in a fraction of the size, cost, and boot
  time, and the PC is better at everything else.
- **Embedded AI is shelved.** The Ollama client and the `prompt` action go
  away. If AI comes back it will be as a host-side *integration* — the
  existing `webhook` action posts to whatever you like — rather than a model
  call wired into the device loop.

## Role inversion

Today the Pi is the peripheral, broadcasting status/responses to a phone.
The roles invert: the **ESP32 advertises**, the **PC connects**, gesture
events flow up as notifications, feedback commands flow down as writes.

```
ESP32 (firmware)                      PC host (the existing Python app)
┌──────────────────────┐   BLE GATT   ┌──────────────────────────────────┐
│ button + debounce    │──gesture────▶│ modes → actions → store/webhook  │
│ gesture detection    │  (notify)    │ scheduler (alarms)               │
│ LED (PWM/neopixel)   │◀──led state──│ web UI + REST (unchanged)        │
│ buzzer (PWM tones)   │◀──palette────│ event store (SQLite)             │
└──────────────────────┘   (write)    └──────────────────────────────────┘
```

## What runs where, and why

- **Gesture detection lives on the ESP32.** The double-tap window is 0.4 s
  and the hold threshold 1.0 s — BLE notification jitter would corrupt
  host-side timing. `TriggerDetector` ([button.py](aibutton/button.py)) is
  a pure, timestamp-driven state machine with no hardware dependency; it
  ports to MicroPython nearly verbatim, and
  [test_trigger_detector.py](tests/test_trigger_detector.py) is the spec
  vectors for the port. Phase 1 left both in place for exactly that reason:
  the host no longer runs the detector, it only documents it. The wire
  carries **semantic events** (`short_press` / `long_press` / `double_tap`)
  — exactly what the host loop consumes today.
- **Everything else on the host.** The protocol only has to carry what
  [main.py](aibutton/main.py) already says to hardware: `set_led(state)` and
  `play_sound` / `start_loop` / `stop_loop`. Alarms need no new machinery:
  the host writes ALERT + loop-start, the ESP32 rings locally, the host
  waits for the next button event to dismiss or snooze — `ring_alarm()`
  is unchanged.

## Protocol (v0 — **pinned**)

> **This is the v0 wire, kept as history.** The live spec is
> [firmware/protocol.py](firmware/protocol.py) and its host mirror
> [aibutton/device.py](aibutton/device.py). v1 added `DEVICE_INFO` (ask what
> you are talking to), `LED_EFFECT` (render a look without naming a state),
> `GESTURE_CONFIG` (how many taps to count), a `METRONOME` LED code, and
> two-byte `[kind, param]` gestures. Everything below is still true — v1 added
> and never repurposed — but it is no longer the whole story.

One GATT service, reusing the project UUID base (the old Pi peripheral's
characteristics retire with it):

| Characteristic | UUID | Props | Payload |
|---|---|---|---|
| `BUTTON_EVENT` | `f3641401-…` | notify | 1 byte: gesture code |
| `LED_STATE` | `f3641402-…` | write | 1 byte: `LEDState` code |
| `SOUND_CMD` | `f3641403-…` | write | 1 byte: sound command |
| `LED_PALETTE` | `f3641404-…` | write | 10 bytes: what one state *looks* like |

- Gesture codes: `0x01` short_press, `0x02` long_press, `0x03` double_tap.
- LED codes: `0x01`–`0x0A`, one per `LEDState` (IDLE, LISTENING, THINKING,
  SUCCESS, ERROR, ALERT, TIMING, COUNTING, WORKING, RESTING) — animations
  render on-device.
- Sound commands: `0x01`–`0x04` play ACK / SUCCESS / ERROR / ALARM once,
  `| 0x80` loops that sound, `0x00` stops the loop. One flag bit covers the
  host's whole sound API without a separate characteristic.
- Palette entries: one write per state — `[state, style, rgb, rgb2, period]`
  in ten bytes, so nothing needs fragmenting at the default ATT MTU. Six
  styles (solid / breathe / flash / alternate / fade / rainbow). The host
  writes all ten on connect and re-writes one when you edit it, which makes a
  colour picker in the web UI change the real LED as you drag it. The device
  keeps built-in defaults for running with no host attached.

> **Why the palette is host state, not device state.** It would have been
> less work to store colours on the ESP32 and edit them over a REPL. Keeping
> them in `config.json` means they live where every other preference lives:
> versioned, hot-reloadable, editable in the same menu, and applied by the
> same "host decides, device renders" rule as `LED_STATE` itself. The device
> never persists them, so a reflash can't lose your colours.

The table lives twice, once per side — [device.py](aibutton/device.py) and
[firmware/protocol.py](firmware/protocol.py) — mirrored the same way
[schema.js](aibutton/web/static/schema.js) and
[config.py](aibutton/config.py) mirror each other, and with the same kind of
guard: [test_protocol.py](tests/test_protocol.py) imports both and fails on
any drift.

## The device abstraction (host) — **built**

One seam in the host, [device.py](aibutton/device.py): a `ButtonDevice` ABC —

- in: `events: asyncio.Queue[TriggerType]`, filled by `press(trigger)`
- out: `set_led(state)`, `play_sound(sound)`, `start_loop(sound)`, `stop_loop()`
- lifecycle: `await close()` — silences the device before releasing it

| Implementation | Backing | Phase |
|---|---|---|
| `MockDevice` | in-memory; drives the web UI's simulate-press buttons and virtual device panel | 1 ✔ |
| `BLEDevice` | `bleak` central connected to the ESP32 | 3 |

`main.run(args, device=None)` takes the device, so tests inject their own
and Phase 3 has one line to change. This *simplified* dev mode as hoped:
the gpiozero mock-pin-factory dance is gone, the mock is a plain object,
and `--mock` / `--real-ai` / `--no-ble` went with it.

## What carries over, what goes

| Fate | What |
|---|---|
| **Unchanged on the host** | [config.py](aibutton/config.py) (minus the AI keys), [rules.py](aibutton/rules.py), [scheduler.py](aibutton/scheduler.py), [store.py](aibutton/store.py), [webui.py](aibutton/webui.py) + the whole web UI (test clock, simulate presses), most of `tests/` |
| **Replaced by `ButtonDevice`** ✔ | `ButtonListener` (`button.py`), `led.py` entirely, the playback half of [audio.py](aibutton/audio.py) — what is left there synthesizes the tones the web UI plays |
| **Ported to firmware** | `TriggerDetector`, the LED animations, the feedback tones |
| **Retired** (kept at `pi-legacy`) ✔ | `ble_peripheral.py`, `device_tests/`, `central_test/`, `aibutton.service`, `SETUP.md` (the Pi wiring/systemd guide, replaced by [firmware/README.md](firmware/README.md)), `gpiozero`/`lgpio`/`bluez-peripheral` deps |
| **Shelved** (kept at `pi-legacy`) ✔ | `ai_client.py`, the `prompt` action (its `schema.js`/`config.py`/`actions.py` branches), the `ollama` dep — superseded by the `webhook` action |

## Phasing

| Phase | Scope | Done when |
|---|---|---|
| **1** ✔ | Host cleanup: extract `ButtonDevice` + `MockDevice`; remove the AI client, the `prompt` action, and all Pi-only files/deps | ~~tests green; `dev.ps1` web UI fully working against `MockDevice`; no `gpiozero` import anywhere~~ — all three met |
| **2** ✔ | `firmware/`: MicroPython + `aioble` peripheral; `TriggerDetector` port; LED animations + buzzer tones; the characteristics | ~~gestures visible in a `bleak` probe; LED/sound respond to writes~~ — verified on hardware with [tools/ble_probe.py](tools/ble_probe.py) |
| **3** ✔ | `BLEDevice` on the host: scan/connect/subscribe via `bleak`, auto-reconnect, connection state surfaced in the web UI | ~~physical press → mode pipeline on the PC → LED/sound on the ESP32~~ — verified. *Power-cycle recovery is tested against a fake bleak but not yet on hardware* |

The transition ends there. A fourth phase — an MCP server exposing the store
and config as a second control surface — was planned and is **deliberately
not built**: the button earns its keep through the web UI and the `webhook`
action, and a second way to drive it can wait until something actually wants
one. Feature work from here is in [TODO.md](TODO.md).

## Decisions baked in (flag any to revisit)

- **MicroPython over Arduino C++** — one language across the project,
  `TriggerDetector` ports as-is, iteration via `mpremote` is fast. Revisit
  only if battery/deep-sleep work demands NimBLE-level control.
- **AI code is deleted, not left dormant** — `pi-legacy` preserves it, and
  the action registry makes re-adding a primitive cheap.
- **Gesture detection on-device**; the wire carries semantic events only.
- **The host must be awake.** Alarms ring only while the PC app runs.
  Accepted for the tethered v1; the parking lot holds the fixes.
- ESP32 capacity is a non-issue: gesture timing + PWM against a 240 MHz
  dual-core MCU with 520 KB RAM (closes the old TODO item 8).

## Open items

- ~~**Which ESP32 variant?**~~ **Settled: the ESP32-S3 Mini**, which is the
  board on hand. Bring-up used its onboard WS2812 and the BOOT button, so
  the firmware was testable before anything was soldered.
- ~~**Which button?**~~ **Settled: a 19 mm illuminated momentary
  (ChromaTek)** — one switch and one WS2812 in a single panel-mount part,
  which is the whole product in one component. It moved both pins off the
  board's own hardware: the switch to **GPIO4** and the LED data line to
  **GPIO1**, both plain GPIOs clear of the strapping pins, flash, PSRAM and
  USB. Two consequences worth keeping:
  - The button is no longer GPIO0, so it can no longer hold the chip in
    download mode at power-on — a class of "bad flash" that was never a bad
    flash.
  - The LED runs from **3V3, not 5V**, so its data threshold (~0.7×VDD)
    matches what the S3 drives. A 5 V pixel on a 3.3 V line works until it
    doesn't, and fails as flicker rather than as silence.

  [firmware/hardware.py](firmware/hardware.py) holds all of it, and the LED
  driver is still chosen by one constant there, so a C3 or a discrete RGB
  LED on three PWM pins remains a one-line change.
- **Sound hardware**: settled — a piezo buzzer on a PWM pin replaces the
  3.5 mm speaker. The tone tables carry over verbatim from the Pi build
  (the host still synthesizes them for the web UI's virtual device, and a
  test fails if the two drift). The sound *design* pass is still queued in
  [TODO.md](TODO.md).

## Parking lot (deliberately later)

- Battery + deep sleep (the one thing that might motivate a C++ rework)
- Offline buffering of presses while disconnected (needs time sync)
- WiFi transport option (removes the PC-awake constraint entirely)
- The [TODO.md](TODO.md) feature queue: Pomodoro template, counter
  increments per gesture, 5-tap global toggle (firmware gesture), sound
  design pass
- Phone app over the existing REST API
