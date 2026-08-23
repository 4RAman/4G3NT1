# Design: the ESP32 split

**Status: done — this document is history.** All four phases landed: an
ESP32-S3 runs the firmware, the host connects over BLE, and a physical press
drives the mode machine on the PC. Kept for *why the split is shaped this way*.

It is **not** a wiring or protocol reference. Pins, wire colours and the LED
rail live in [firmware/hardware.py](firmware/hardware.py); the protocol is
[protocol.py](firmware/protocol.py) and [device.py](aibutton/device.py), which
are mirrored and drift-tested, and its rules for changing are in
[CLAUDE.md](CLAUDE.md). Protocol v1 is frozen; the v0 description this document
used to carry is gone rather than left to rot. The Raspberry Pi build this
replaced is preserved at the git tag **`pi-legacy`**.

## The idea in one line

> The button becomes an ESP32 **BLE peripheral** that detects gestures and
> shows feedback; everything else — modes, scheduler, store, web UI — is the
> Python app running on the PC as the **BLE central**.

## Why

The Pi was an always-on Linux box reading one button and driving one LED. An
ESP32 does the hardware edge in a fraction of the size, cost and boot time, and
the PC is better at everything else.

**Embedded AI was shelved with it.** If AI returns it will be a host-side
integration through the `webhook` action, not a model call wired into the
device loop. (The project name `aibutton` predates that decision and is
provisional — ROADMAP **D7**.)

## Role inversion

On the Pi the device was the peripheral, broadcasting to a phone. The roles
invert: the **ESP32 advertises**, the **PC connects**, gestures flow up as
notifications, feedback flows down as writes.

```
ESP32 (firmware)                      PC host (the Python app)
┌──────────────────────┐   BLE GATT   ┌──────────────────────────────────┐
│ button + debounce    │──gesture────▶│ modes → actions → store/webhook  │
│ gesture detection    │  (notify)    │ scheduler (alarms)               │
│ LED (PWM/neopixel)   │◀──led state──│ web UI + REST                    │
│ buzzer (PWM tones)   │◀──palette────│ event store (SQLite)             │
└──────────────────────┘   (write)    └──────────────────────────────────┘
```

## What runs where, and why

**Gesture detection lives on the device**, because BLE notification jitter
would corrupt host-side timing. The wire carries **semantic events**, not
edges. [trigger.py](firmware/trigger.py) is a pure timestamp-driven state
machine, which is why the host suite can still execute it as the spec for the
port.

**Everything else is host-side.** The protocol only carries what the run loop
already said to hardware: an LED state and sound commands. Alarms needed no new
machinery — the host writes ALERT plus a loop-start, the device rings locally,
and the host waits for the next button event.

## Decisions baked in

- **MicroPython over Arduino C++** — one language across the project, the
  detector ports as-is, and `mpremote` iteration is fast. Revisit only if
  battery/deep-sleep work demands NimBLE-level control (TODO **29**).
- **AI code was deleted, not left dormant.** `pi-legacy` preserves it, and the
  action registry makes re-adding a primitive cheap.
- **The host must be awake.** Alarms ring only while the PC app runs. Accepted
  for the tethered v1, and it stops being acceptable at Stage 4 when the button
  goes in a pocket — ROADMAP **D1** settles it.
- **ESP32 capacity is a non-issue**: gesture timing and PWM against a 240 MHz
  dual-core MCU with 520 KB RAM.
- **A fourth phase was planned and deliberately not built** — an MCP server as
  a second control surface. The web UI and the `webhook` action cover what the
  button is for; revisit when something concrete wants to drive it
  programmatically.
