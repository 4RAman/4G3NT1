# AI Button

A Raspberry Pi 3B+ device: one physical button, three gestures (short
press / long press / double tap) plus a reserved **5-tap** escape, routed
through **time-aware modes** — the same gesture can mean different things
at different times of day or in different modes. An RGB LED and feedback
sounds show device state; a BLE GATT peripheral broadcasts state changes
and results to any subscribed phone/laptop.

The everyday **actions** mode resolves a gesture first-match-wins against
four action primitives:

| Action | What it does |
|---|---|
| `prompt` | ask the AI (remote Ollama, automatic local fallback) |
| `log` | record a timestamped event in SQLite (meds, habits) |
| `timer_toggle` | start/stop a named stopwatch, durations logged |
| `webhook` | POST to any URL — the IFTTT / Make / n8n / Home Assistant hook |

Example: between 05:00 and 07:00, a double tap logs `meds_taken`;
any other time it falls through to the permanent Default mode. See the
`modes` section of [config.json](config.json).

A built-in **web UI** (http://\<pi\>:8080) shows live device state and the
event log, and includes a **point-and-click configuration menu**: add,
reorder, and delete rules; pick each gesture's action from a form (the
right fields appear per action type); set the time/day scope; and edit
device settings — no hand-written JSON. **Check** previews what the
server would accept (and which keys fall back) before you **Save**, which
hot-reloads with no restart. It can also simulate button presses. It runs
inside the service process and exposes a REST API (`/api/status`,
`/api/config`, `/api/config/validate`, `/api/events`, `/api/trigger/...`)
that a future phone app can reuse.

- **Hardware**: momentary button on GPIO17 (active low), RGB LED on
  GPIO18/23/24 (330R series resistors, common cathode), optional mini
  speaker + amp on the 3.5 mm jack for feedback sounds.
- **AI**: remote Ollama server on the LAN (`llama3.2:1b`), automatic
  fallback to Ollama on the Pi itself (`smollm2:135m`).
- **Provisioning**: see [SETUP.md](SETUP.md) — wiring, dependencies,
  Ollama, config, systemd, and the on-device test sequence.

## Layout

| Path | What |
|---|---|
| `aibutton/` | the application package (config, rules, actions, store, audio, led, button, ai_client, ble_peripheral, webui, main) |
| `aibutton/web/index.html` | the web UI dashboard — one static page, no build step |
| `aibutton/web/static/` | the configuration menu, as small ES modules (no build step) — `schema.js` is the single place to add an action type or setting |
| `config.json` | sample config → deploy to `/etc/aibutton/config.json` |
| `aibutton.service` | systemd unit |
| `device_tests/` | standalone hardware test scripts (run on the Pi) |
| `central_test/ble_central.py` | BLE subscriber test (run on a laptop, needs `bleak`) |
| `tests/` | pytest suite — runs anywhere, no hardware needed |
| `tests_js/` | web UI ES-module tests (`npm test`, node:test + jsdom) |
| `firmware/` | ESP32-C3 port (in progress): host-tested gesture + generative-synth cores, scaffolded hardware glue — see [firmware/README.md](firmware/README.md) |

## Architecture

One **single asyncio process** (started by systemd) owns everything: the
button event loop, the LED/sound feedback, the BLE peripheral, and an
embedded uvicorn server for the web UI + REST API — no second service, no
IPC. They share one live `ConfigManager`, `EventStore`, and press queue.

The pipeline per press is a one-way flow:

```
button.py ──gesture──▶ rules.py ──(rule, action)──▶ actions.py ──result──▶ main.py
 (GPIO/                (resolve,                     (prompt/log/             (LED +
  debounce)             time-aware,                   timer/webhook)           sound +
                        first-match)                                           BLE + web)
```

Two design choices keep it extensible:

- **Registry-driven, Open/Closed.** Action types and device settings are
  declared once in [schema.js](aibutton/web/static/schema.js) (web) and
  mirrored by the parser in [config.py](aibutton/config.py) (Python); the
  rule editor, summaries, and form widgets are all data-driven from those
  tables, so adding a capability is adding a descriptor, not rewiring the UI.
- **Pure core, injected I/O.** Rule resolution ([rules.py](aibutton/rules.py))
  and config parsing are side-effect-free and unit-testable; GPIO, the AI
  client, and the database are injected, which is what lets the whole thing
  run mocked on a laptop (`--mock`).

Config errors never crash the service — a missing file, bad JSON, or a
wrongly-typed key falls back per-key with a logged warning, and the web API
surfaces those same warnings so the editor shows what was actually accepted.

> **The mode machine (shipped).** The button is always in one *mode*, built
> from a *behaviour template* — `actions`, `alarm`, `stopwatch`, `counter`,
> `pomodoro` — activated by a *trigger* (always / time-window / scheduled time /
> entered from another mode). **Ambient** modes (actions) answer gestures
> first-match-wins in config order; the permanent **Default** is the locked
> always-on floor at the bottom that everything else overrides. **Takeover**
> modes own the button until you exit them — an alarm fires on a schedule and
> rings until dismissed; a stopwatch, counter or Pomodoro is started by an
> *enter a mode* gesture. A reserved **5-tap** is the global escape: it exits a
> takeover, or toggles the device off/on from the Default. Counters count up by
> configurable increments (+1/+10/+20); Pomodoro is a 25/5 auto-repeating focus
> timer with assignable gestures. Full design, decisions, and the ESP32 audio
> plan in [DESIGN.md](DESIGN.md); usage in [MANUAL.md](MANUAL.md).

## Dev quickstart (no Pi needed)

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.\dev.ps1            # dev environment: web UI at http://localhost:8080
.\dev.ps1 -RealAI    # same, but real Ollama backends for prompt testing
.venv\Scripts\python -m aibutton.main --mock --demo --no-ble   # one-shot smoke test
```

The web UI ES modules have their own test suite (Node's built-in runner +
jsdom — no browser needed):

```
npm install      # one-time: pulls jsdom
npm test         # runs tests_js/*.test.mjs
```

The dev environment mocks the GPIO pins and (by default) the AI, then
lets you drive everything from the browser:

- **Simulate buttons** fire short press / long press / double tap
  through the real rules → actions → status pipeline.
- **Virtual device panel** mirrors the LED (same animations: blue
  breathe, white pulse, …) and plays the device's actual feedback
  tones in the browser.
- **Test clock** — set it to 06:30 and a 5–7am rule matches *now*.
  Time-windowed rules become testable in seconds instead of waiting
  for the right hour. The override keeps ticking, never persists
  across restarts, and never alters event-log timestamps.
