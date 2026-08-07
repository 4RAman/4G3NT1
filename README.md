# AI Button

One physical button, three gestures (short press / long press / double
tap), routed through a **mode machine** — the button is always in exactly
one mode (the Default, a time-windowed override, a ringing alarm, a
running stopwatch, an open counter), and the mode decides what each
gesture means. An RGB LED and feedback sounds show device state.

The hardware is an **ESP32** — it detects gestures and shows feedback; this
Python app is the brain on the PC, connected over BLE. It replaces an
earlier Raspberry Pi build, preserved at the git tag `pi-legacy`; the
transition and its rationale are in [DESIGN-ESP32.md](DESIGN-ESP32.md).

> **Working on real hardware.** The transition is complete: press the button
> and the mode machine on your PC decides what it means, then drives the LED
> and buzzer back. With no ESP32 attached the app runs on a `MockDevice`
> instead, fully drivable from the web UI — no hardware needed to develop.

Ambient modes resolve first-match-wins against four action primitives:

| Action | What it does |
|---|---|
| `log` | record a timestamped event in SQLite (meds, habits) |
| `timer_toggle` | start/stop a named stopwatch, durations logged |
| `webhook` | POST to any URL — the IFTTT / Make / n8n / Home Assistant hook |
| `enter_mode` | switch into a takeover mode (alarm / stopwatch / counter) |

Example: between 05:00 and 07:00, a double tap logs `meds_taken`;
any other time it falls through to the Default mode. See the `modes`
section of [config.json](config.json).

Modes are built from six **behaviour templates** — actions, alarm, stopwatch,
counter, pomodoro and metronome — plus an *activation* saying when each turns
on (always / time window / at a clock time / entered from another mode).

A built-in **web UI** (http://localhost:8080) shows live device state and the
event log, and includes a **point-and-click configuration menu**: add,
reorder, and delete modes; pick each gesture's action from a form (the
right fields appear per action type); drop in ready-made modes; set the
time/day scope; recolour every light the button shows; and edit device
settings — no hand-written JSON. **Check** previews what the
server would accept (and which keys fall back) before you **Save**, which
hot-reloads with no restart. It can also simulate button presses. It runs
inside the service process and exposes a REST API (`/api/status`,
`/api/config`, `/api/config/validate`, `/api/events`, `/api/trigger/...`)
that a future phone app can reuse.

- **Hardware**: an ESP32 with a momentary button, an RGB LED, and a piezo
  buzzer, speaking BLE to the host — wiring and flashing in
  [firmware/README.md](firmware/README.md). Developed against an ESP32-S3
  Mini; other boards are a line in `hardware.py`.
- **Lights**: eleven device states, each with a configurable style (solid,
  breathe, flash, alternate, fade, rainbow), colours and speed. Edited in the
  web UI and pushed to the button live.
- **AI**: none on the device, by design. Point the `webhook` action at
  whatever should do the thinking.

## Layout

| Path | What |
|---|---|
| `aibutton/` | the application package (config, rules, actions, store, device, audio, button, webui, main) |
| `aibutton/device.py` | the hardware seam: `ButtonDevice` + the wire protocol (gestures, LED states, sound commands, palette, UUIDs) |
| `aibutton/ble_device.py` | the bleak central: scan, connect, subscribe, auto-reconnect |
| `aibutton/button.py` | `TriggerDetector` — no longer runtime code, kept as the spec the firmware port follows |
| `firmware/` | the ESP32 half: MicroPython + `aioble` peripheral, gesture detection, LED animations, buzzer tones |
| `tools/ble_probe.py` | drive the firmware by hand over BLE (`--cycle` runs every animation and tone) |
| `aibutton/control/` | the tray control panel: start/stop the service, watch it, flash the firmware (`status.py` is pure; `tray.py` is the only part that needs a screen) |
| `control.pyw` | double-click launcher for the control panel — no console window |
| `aibutton/web/index.html` | the web UI dashboard — one static page, no build step |
| `aibutton/web/static/` | the configuration menu, as small ES modules (no build step) — `schema.js` is the single place to add an action type or setting |
| `config.json` | the config the app runs on (override with `--config` or `$AIBUTTON_CONFIG`) |
| `tests/` | pytest suite — runs anywhere, no hardware needed; covers the firmware's hardware-free modules too |

## Architecture

One **single asyncio process** owns everything: the button event loop, the
LED/sound feedback, and an embedded uvicorn server for the web UI + REST
API — no second service, no IPC. They share one live `ConfigManager`,
`EventStore`, and `ButtonDevice`.

The pipeline per press is a one-way flow:

```
device.py ──gesture──▶ rules.py ──(mode, action)──▶ actions.py ──result──▶ main.py
 (BLE or               (resolve,                     (log/timer/            (LED + sound
  MockDevice)           time-aware,                   webhook)               back out through
                        first-match)                                         the device + web)
```

Two design choices keep it extensible:

- **Registry-driven, Open/Closed.** Action types and device settings are
  declared once in [schema.js](aibutton/web/static/schema.js) (web) and
  mirrored by the parser in [config.py](aibutton/config.py) (Python); the
  rule editor, summaries, and form widgets are all data-driven from those
  tables, so adding a capability is adding a descriptor, not rewiring the UI.
  The wire protocol is mirrored the same way, between
  [device.py](aibutton/device.py) and
  [firmware/protocol.py](firmware/protocol.py) — in both cases a test fails
  if the two halves drift.
- **Pure core, injected I/O.** Rule resolution ([rules.py](aibutton/rules.py))
  and config parsing are side-effect-free and unit-testable; the hardware
  ([device.py](aibutton/device.py)) and the database are injected, which is
  what lets the whole thing run with no hardware attached.

Config errors never crash the service — a missing file, bad JSON, or a
wrongly-typed key falls back per-key with a logged warning, and the web API
surfaces those same warnings so the editor shows what was actually accepted.

Where this is going — swappable apps, an untethered button, the decisions
that get expensive if deferred: [ROADMAP.md](ROADMAP.md), and the target
design it builds toward, [ARCHITECTURE.md](ARCHITECTURE.md). Design rationale
and the config schema reference: [DESIGN.md](DESIGN.md). Usage:
[MANUAL.md](MANUAL.md). Contributing (and the principles the code is shaped
around): [CLAUDE.md](CLAUDE.md).

> **Stage 2 of six.** The concept is proven and the hardware works; the
> current push is loading it with apps and making the whole thing smooth
> enough to demo. Beyond that the button grows its own brain — it runs the
> apps itself, with a phone holding preferences and doing the heavy lifting,
> so it keeps working when you walk away from the computer.

## Quickstart

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
control.pyw                                                    # tray control panel (double-click)
.\dev.ps1                                                      # MockDevice, web UI at :8080
.venv\Scripts\python -m aibutton.main --ble --config config.json   # the real button
.venv\Scripts\python -m aibutton.main --demo --no-web          # one-shot smoke test
```

Flashing the ESP32 is in [firmware/README.md](firmware/README.md). Only one
instance can run at a time — BLE allows a single central — and a second one
refuses at startup rather than fighting the first for the connection.

## Control panel

The web UI configures the button; it cannot *start* it, since it is served by
the very service it would launch. That job belongs to the **tray control
panel** (`control.pyw`, or `python -m aibutton.control`):

- a tray dot whose colour is the whole status at a glance — grey stopped,
  amber running-but-no-button, green ready, red died on its own;
- **Start** / **Stop** the service, with stop asking politely (so open timers
  close and a ringing alarm is silenced) before it escalates;
- **Update the button's firmware** — `mpremote` copy + reset, with the output
  in the log window, because flashing this chip fails in ways you need to
  read;
- **Open web UI**, for everything about what the button actually does.

With `MockDevice` behind the seam, the browser *is* the button — you drive
everything from the page:

- **Simulate buttons** fire short press / long press / double tap
  through the real rules → actions → status pipeline.
- **Virtual device panel** mirrors the LED (same animations: blue
  breathe, white pulse, …) and plays the device's actual feedback
  tones in the browser.
- **Test clock** — set it to 06:30 and a 5–7am rule matches *now*.
  Time-windowed rules become testable in seconds instead of waiting
  for the right hour. The override keeps ticking, never persists
  across restarts, and never alters event-log timestamps.
