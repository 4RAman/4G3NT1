# CLAUDE.md

One physical button on an ESP32, a Python brain on the PC, talking BLE.
Read [README.md](README.md) for what it does,
[DESIGN-ESP32.md](DESIGN-ESP32.md) for how it got this shape,
[ROADMAP.md](ROADMAP.md) for where it is going, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the design it is going *to* — the last
two matter more than usual here, because several cheap decisions today are
expensive ones after hardware ships.

## Commands

```bash
.venv/Scripts/python -m pytest -q                       # the whole suite, no hardware needed
.venv/Scripts/python -m aibutton.main --config config.json          # MockDevice + web UI
.venv/Scripts/python -m aibutton.main --ble --config config.json    # the real button
.venv/Scripts/python -m aibutton.control               # the tray control panel
.venv/Scripts/python -m mpremote cp firmware/*.py : + reset         # flash the firmware
.venv/Scripts/python tools/ble_probe.py --cycle        # drive the firmware by hand
.venv/Scripts/python -m aibutton.scenes list|check|activate         # scenes, service stopped
.venv/Scripts/python tools/build_editor.py             # dist/button-editor.html (offline)
```

Only **one** instance may run: BLE allows a single central, so two copies
steal the connection from each other. A second one now *refuses* at startup
(`single_instance.py`) rather than fighting — stop the first, or pass
`--no-lock` if you genuinely mean it.

## The control panel is not the web UI

Two UIs, and the split is structural rather than stylistic:

- **The web UI** (`webui.py`, :8080) is served *by* the running service and
  configures it — modes, lights, events. It can never start the service,
  because it only exists once the service is up.
- **The control panel** (`aibutton/control/`, a tray icon) sits *around* the
  service and owns its lifecycle — start, stop, watch, flash the firmware.

So: anything about *what the button does* goes in the web UI; anything about
*whether the service is running* goes in the control panel. The panel imports
the service, never the reverse.

The panel's Start defaults to `--ble`, the opposite of the command line's
default, and that asymmetry is deliberate: someone running the panel has a
button in front of them. Its own settings live in `control-panel.json`,
*beside* `config.json` and never inside it — the web UI's editor rewrites
that file wholesale, so a panel setting stored there would not survive a
Save.

Stopping is the one non-obvious part. Windows never delivers SIGTERM between
processes, and `CTRL_BREAK_EVENT` needs a console a tray app does not have —
so the polite stop is `POST /api/service/stop`, and signals are the fallback
for POSIX and for a service started from a terminal. A hard kill stays safe
by construction (the OS drops the run lock, the store commits per write); it
just skips the device's goodbye.

## Shape

```
firmware/ (ESP32)              aibutton/ (PC)
  gesture detection  ──BLE──▶    rules → actions → store
  LED + buzzer       ◀──BLE──    modes, scheduler, web UI
```

The ESP32 detects and renders. **Every decision is host-side**, including
what colour each state is. Timing that can't survive radio jitter (the 0.4 s
double-tap window) is the one thing that lives on the device.

## SOLID, as it actually applies here

These aren't aspirations; they're the reasons the existing code is shaped
the way it is. Match them.

**Single responsibility — a pure core with I/O injected at the edges.**
[rules.py](aibutton/rules.py), [scheduler.py](aibutton/scheduler.py) and the
parsing half of [config.py](aibutton/config.py) are side-effect-free
functions over data: no clock, no queue, no hardware. That's why they're
testable without mocks, and why the whole app runs with nothing plugged in.
[trigger.py](firmware/trigger.py) is pure for the same reason — it's the one
piece of firmware the host test suite can execute.
*Keep new logic out of I/O classes; take the clock and the store as
arguments.*

**Open/closed — capability is added as data, not as branches.**
[schema.js](aibutton/web/static/schema.js) declares every action, template,
activation, LED style and setting; the editor, the summaries and the form
widgets are generated from those tables. Adding the Pomodoro template meant
adding a descriptor and a parser, not touching the mode editor.
*If you find yourself adding an `if template == ...` to the UI, add a
descriptor instead.*

**Liskov — implementations are interchangeable, no downcasting.**
`MockDevice` and `BLEDevice` differ in everything except behaviour;
[main.py](aibutton/main.py) never asks which it has. Widgets all return
`{ el, validate }` so the mode editor treats them uniformly.
*The one legitimate `isinstance` on a device is the web UI asking "is this a
mock?" to decide whether to show the virtual panel.*

**Interface segregation — the seam is four methods.**
`ButtonDevice` is `events` in; `set_led` / `play_sound` / `start_loop` /
`stop_loop` out, plus lifecycle. Everything else — palettes, reconnection,
byte encoding — is a private concern of the implementation.
*Resist widening it. `set_palette` earned its place by being device state
the host asserts, exactly like the LED state.*

**Dependency inversion — depend on the abstraction, and mind the direction.**
`main` depends on `ButtonDevice`, never on `BLEDevice`; the import of the
concrete class is deferred to the one line that chooses it.
[device.py](aibutton/device.py) imports nothing from the package — `config`
imports *it*, not the reverse — so the wire vocabulary has no opinions about
config.
*Never let device.py import config.py; palette encoding duck-types the
effect object precisely to avoid that.*

## Apps, not features

The product is *a button that runs swappable apps*, not a button with a list
of built-in behaviours. What ships as a "mode" today becomes an "app"
tomorrow, and the direction of travel is that **adding one touches the app's
own files and nothing else**. Full plan in [ROADMAP.md](ROADMAP.md); what it
means while writing code today:

**Know what an app currently costs.** A rich template with its own light is a
6-to-9 file change — `config.py` (dataclass, parser, allow-list, serialiser,
union), `main.py` (a `run_*` loop and two `isinstance` chains), `schema.js`
(template, takeover set, built-in), plus `device.py` /
`firmware/protocol.py` / `firmware/led.py` / `_default_palette` /
`LED_STATES` for the LED state, plus tests. Every one of those is a place a
third-party app author cannot reach. If you are adding an app and find
yourself editing the core, that is the tax — note it, don't normalise it.

**Prefer a preset to a template.** A new entry in `BUILTIN_MODES` costs zero
Python. Reach for a new `*Behavior` only when the behaviour genuinely cannot
be expressed by an existing one.

**Don't burn a wire code.** `LEDState` is a one-byte global namespace,
mirrored in four places, and `0x0B` is already spent. It is also *shared* —
every Pomodoro gets the same colours. A new app wanting its own look is a
reason to push an effect, not to allocate a state. `run_metronome` already
does this by rewriting the palette live; that is a workaround, and
generalising it is the fix.

**Keep new logic out of the run loop.** The takeover loops in `main.py` are
the one place the "pure core, injected I/O" rule is *not* followed — they
await the device directly, which is why they can't be tested without asyncio
and can't run anywhere but the host. New behaviour should lean toward a step
function over `(state, event, now)` returning effects, even before the
runtime formally exists. Anything pure survives the Stage-3 move unchanged;
anything that awaits a device gets rewritten.

**The brain is moving to the device — decided.** The button will run its own
OS and the active app; the phone holds preferences and does the heavy lifting
(webhooks, AI, the store). Full design in [ARCHITECTURE.md](ARCHITECTURE.md).
Three consequences for code written today:

- Code that assumes *"the host is awake and connected"* is fine for now and
  must be easy to find later. Say so in a comment when you write it.
- Anything that must feel instant (light, sound, what a press means) belongs
  on the device eventually. Anything needing a network, a parser or a model
  belongs on the phone — permanently. The latency budget in
  ARCHITECTURE.md is the arbiter, not taste.
- **An app is data, not code**: a state machine with expressions, bounded by
  construction — no loops, no allocation, no recursion. When you extend an
  app's abilities, extend the *effect set* (a system decision) rather than
  reaching for something that only a general-purpose language could express.

## Invariants

- **Mirrored tables are tested, not trusted.** The protocol lives twice
  ([protocol.py](firmware/protocol.py) / [device.py](aibutton/device.py)) and
  so do the tone tables and the LED styles, because one side ships to a
  microcontroller. [test_protocol.py](tests/test_protocol.py) and
  [test_firmware_feedback.py](tests/test_firmware_feedback.py) fail on drift.
  Change one side, change the other, in the same commit.
- **A bad config never crashes the service.** Every key falls back
  individually with a logged error, and the web API returns those same
  warnings so the editor shows what was actually accepted. New config
  surfaces follow that pattern — see `_parse_effect` for the shape. A missing
  or broken *scene* is the same rule one level up: it is reported and the base
  config runs.
- **One parser, and scenes merge before it.** A scene
  ([scenes.py](aibutton/scenes.py)) is layered over `config.json` as a **raw
  dict** inside `load_config_full`, so `parse_config` still sees one object
  and every fallback applies to scene files for free. Never add a second
  validation path for scenes — that is the whole reason the merge is where it
  is. `scenes.py` imports nothing from the package, exactly like `device.py`;
  `config` imports *it*.
- **Edits go to the active scene, the pointer stays in config.json.**
  `ConfigManager.write_path` is the one place that decides, so the two files
  never hold two copies of the same modes list. Anything a scene changes that
  is only read at startup (BLE name, web bind, database path) is reported as
  `needs_restart` rather than silently ignored.
- **Feedback is fire-and-forget.** `set_led` and friends are synchronous and
  must never block; `BLEDevice` queues and drops rather than waiting. The
  mode machine cannot afford to await a radio.
- **The host owns state; the device renders it.** The firmware's palette and
  animations are a *fallback* for running with no host attached. Anything
  persistent belongs in `config.json`.
- **A takeover mode must be escapable with a press.** Alarm, stopwatch,
  counter, pomodoro and metronome all exit on a gesture; the Pomodoro parser
  warns if you unbind its only exit.

### When you change the protocol

Not descriptions of today — rules for the next change, because the protocol
is the one surface that will exist in someone else's pocket.

- **Add, don't repurpose.** A byte that once meant something must never come
  to mean something else. There is no way to reflash a device you don't have.
- **Negotiate, don't assume.** The host must be able to *ask* a device what
  it supports rather than inferring it from a version number. Until
  `DEVICE_INFO` exists (ROADMAP **D8**), every new capability is a flag day —
  which is why it should exist before more hardware does.
- **Batch the breaks.** Protocol changes cost a reflash and a chance to drift
  the mirrored tables. Land them together, then freeze.

## Conventions

- Comments explain **why**, not what. The tricky ones here are hardware
  reality (WS2812 byte order, sticky download mode) and deliberate
  trade-offs (dropping presses while busy) — those are worth a sentence.
- Tests assert behaviour and name the scenario, not the method. Prefer one
  event-script table over many near-identical cases (see
  [test_trigger_port.py](tests/test_trigger_port.py)).
- No new runtime dependencies without a reason; the service runs on httpx,
  fastapi, uvicorn and bleak. The tray control panel adds **pystray** and
  **Pillow** — a tray icon has no stdlib equivalent on Windows, and its
  window is plain Tk. Those two are the control panel's alone: nothing in
  the service imports them, so a headless host still installs four.
- **`aibutton` is a provisional name.** It is descriptive and inaccurate —
  there is deliberately no AI on the device. A rename is coming
  (ROADMAP **D7**), so don't spread the string further than it already is:
  new user-facing text says "the button", and new identifiers don't embed it.
- Firmware changes need a **reflash** before they mean anything. Firmware
  modules import each other by bare name and sit flat on the device.

## Hardware gotchas

- **ESP32-S3, USB-Serial/JTAG.** Entering download mode sets a sticky flag
  that survives a reset — after flashing, the board sits in the bootloader,
  silent, until you physically replug. It looks exactly like a bad flash.
- **WS2812 byte order varies by board.** `NEOPIXEL_ORDER` in
  [hardware.py](firmware/hardware.py); diagnose by which colours are wrong
  (red↔green swapped, blue fine → the strip is RGB, not GRB).
- **The button's WS2812 runs on 3V3, not 5V.** Its data threshold is ~0.7×VDD
  and the S3 drives 3.3 V, so a 5 V-powered pixel sits on the edge and fails
  as *flicker*, not as silence — the hardest failure here to read as wiring.
- **`mpremote exec` interrupts `main.py`.** The board stops advertising until
  you `reset` it.
