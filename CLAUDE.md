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
*Resist widening it. `set_palette` and `set_gesture_config` earned their
places by being device state the host asserts, exactly like the LED state.*
`info` is the counterpart and stayed an **attribute rather than a method**
for exactly that reason: it is device state the host *reads*, never asserts,
so nothing has to be implemented to satisfy it — a backend that is its own
hardware just knows its own answer.

Ephemeral effects are the worked example of *not* widening it.
"Show this look right now" became an optional second argument to `set_led`,
not a fifth method, because it is the same assertion the seam already makes
carrying more detail. The state argument stays required and still means
something — it is what the status line and the web UI report, and what a
device too old for effects falls back to rendering. **That fallback lives
inside `BLEDevice`, not in the run loop**: a mode asks for a look, and
whether showing it costs a borrowed palette entry is the device's business.

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

**Know what an app currently costs.** A rich template is a 4-to-6 file
change — `config.py` (dataclass, parser, allow-list, serialiser, union),
`main.py` (a `run_*` loop and two `isinstance` chains), `schema.js`
(template, takeover set, built-in), plus tests. Every one of those is a place
a third-party app author cannot reach. If you are adding an app and find
yourself editing the core, that is the tax — note it, don't normalise it.

*Its own light used to add three more files* (`device.py` /
`firmware/protocol.py` / `firmware/led.py`, plus the palette and the
editor's state list) and no longer does: push an effect. That is one of the
two taxes protocol v1 removed. The other is a new gesture — a longer tap is
now a data change in `TriggerType` and `GESTURES`, with no reflash under it.

**Prefer a preset to a template.** A new entry in `BUILTIN_MODES` costs zero
Python. Reach for a new `*Behavior` only when the behaviour genuinely cannot
be expressed by an existing one.

**Don't burn a wire code.** `LEDState` is a one-byte global namespace,
mirrored in four places, and `0x0B` is already spent. It is also *shared* —
every Pomodoro gets the same colours. A new app wanting its own look is a
reason to push an effect, not to allocate a state — and since protocol v1
that is a supported thing to do rather than a workaround: pass an effect to
`set_led` and the device renders it until the next state change, storing
nothing. `run_metronome` and `run_countdown` are the two consumers to copy.
**Allocating a new `LEDState` now needs an argument for why the app's look is
a thing the whole system should have a name for.**

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
- **The flash floor has one gate, and it is a setting.**
  `min_flash_period_s` defaults to `device.SAFE_MIN_PERIOD_S` (3 Hz, WCAG
  2.3.1) and may be taken lower deliberately — that is honoured *and* warned
  about, because clamping a setting silently makes it a lie. Enforcement is
  `config.flash_safe`, applied in `main.set_led` (every pushed look) and where
  the palette is pushed (the device renders those unasked). Do not add a
  second clamp: a floor in three places is a floor with three chances to
  drift. Only `device.STYLE_STROBES` styles are floored, mirrored as
  `strobes: true` in `schema.js`.
- **Long press means "up one level", everywhere.** Alarm, stopwatch, counter,
  pomodoro, metronome, countdown and the launcher all leave on a long press;
  the Pomodoro parser warns if you unbind its only exit. The launcher is the
  case that proves it - it launches on a *double tap*, because a menu where the
  universal escape gesture instead committed you to something would be the one
  exception to a rule people are supposed to trust without thinking. Modes
  entered from a launcher return to it (`return_after`, on by default), so the
  gesture always travels exactly one level rather than one-or-two depending on
  how you arrived. **A new takeover binds long press to leaving, or has a very
  good reason.**
- **A mode names a look; it never owns one.** The pool is `AppConfig.looks`
  and a mode holds `{state: look-name}`. Which states a mode may colour is
  `MODE_LED_STATES` in [config.py](aibutton/config.py), mirrored as
  `ledStates` on each template descriptor in
  [schema.js](aibutton/web/static/schema.js) —
  [test_webui.py](tests/test_webui.py) fails on drift. A mode that names
  nothing resolves to `None`, which is what `set_led` already means by "no
  override", so the palette stays the fallback and costs no wire traffic.

### When you change the protocol

Not descriptions of today — rules for the next change, because the protocol
is the one surface that will exist in someone else's pocket.

- **Add, don't repurpose.** A byte that once meant something must never come
  to mean something else. There is no way to reflash a device you don't have.
- **Negotiate, don't assume.** `DEVICE_INFO` exists now (protocol v1): a read
  giving protocol version, firmware version and a capability bitmap. So
  **gate every new capability on a bit** rather than on a version number, and
  let an old device answer honestly instead of being assumed into working.
  `BLEDevice` re-reads it on every reconnect — the thing on the other end may
  have been reflashed since.
  - Capability bits report what *came up*, not what `hardware.py` asked for:
    the LED and buzzer both degrade to Null backends, and a bit claiming a
    buzzer nobody can hear is worse than no bit at all.
  - A device with no `DEVICE_INFO` falls back to `ASSUMED_INFO`, because the
    only firmware that predates it is ours and it has all three. Learning to
    ask must never silence a button nobody has reflashed.
- **Append, never insert.** `DEVICE_INFO` grows by adding fields on the end,
  and `decode_device_info` ignores trailing bytes it doesn't know. That is the
  half of forward compatibility the *host* owns, and it is what keeps a newer
  device readable by an older host.
- **Batch the breaks.** Protocol changes cost a reflash and a chance to drift
  the mirrored tables. Land them together, then freeze.
- **Protocol v1 is frozen.** `DEVICE_INFO`, ephemeral effects and
  parameterised gestures all shipped; `OTA_CONTROL` and `GESTURE_HOLD` are
  claimed and unimplemented. Everything below v1 needs is now reachable
  without a reflash, so the bar for the *next* wire change is a capability the
  device physically cannot express today — not a feature that would merely be
  tidier on the wire.
- **The host must read everything a device might send; the device sends the
  oldest form that will do.** That asymmetry is deliberate — the host is the
  half that is easy to update. So the classic three gestures still go out as
  one byte and always will, and only a gesture with no legacy code travels as
  `[kind, param]`. `decode_gesture` accepts both.
- **Cost that changes how the button feels is opt-in, and derived.**
  Counting to three taps is what stops a double tap firing on contact, so
  `max_taps` is written down the wire from what the config actually binds
  (`bound_triggers` → `max_taps_for`) rather than being a setting. A button
  with nothing longer than a double bound behaves exactly as it always has.

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
- **Keep [TODO.md](TODO.md) current in the same commit as the work.** When an
  item ships, move it to **Done** and delete the scope the shipped version
  superseded — a "✔ shipped" banner above the original plan is how that file
  grew to 1600 lines of instructions nobody should follow any more. Two rules
  keep the pruning safe: a rule governing *future* code belongs here in
  CLAUDE.md and TODO.md only records the decision and points at it; and item
  numbers are never reused or renumbered, because this file, ROADMAP.md and
  the commit log all cite them.

## Hardware gotchas

- **ESP32-S3, USB-Serial/JTAG.** Entering download mode sets a sticky flag
  that survives a reset — after flashing, the board sits in the bootloader,
  silent, until you physically replug. It looks exactly like a bad flash.
- **WS2812 byte order varies by board, and this build's two LEDs disagree.**
  The ring is GRB, the onboard one is RGB (`NEOPIXEL_ORDER` /
  `ONBOARD_NEOPIXEL_ORDER` in [hardware.py](firmware/hardware.py)). Diagnose by
  pushing *known* colours from the Lights tab's test bench, never by watching
  the rainbow — every permutation of a rainbow is still a rainbow, so it shows
  at most a direction reversal and a camera's white balance will happily fake
  one of those. One LED wrong means that LED's setting is wrong; **both wrong
  the same way means the two settings are on the wrong LEDs**. Red, green, cyan
  and magenta are the colours that talk — blue, yellow and white are fixed
  points of an R/G swap and look perfect while it is broken.
- **The button's WS2812 runs on 3V3, and that is a trade, not a fix.** Its data
  threshold is ~0.7×VDD, so a 5 V-powered pixel driven by the S3's 3.3 V sits
  on the edge and fails as *flicker*, not as silence — the hardest failure here
  to read as wiring. 3V3 removes that and buys a colour fault instead: the red
  die runs at ~2 V and the green and blue dies at ~3.2 V, so on a 3.3 V rail
  only red keeps its current sink in regulation and white renders orange
  (measured R:G:B ≈ 1.00 : 0.54 : 0.44). Going to 5 V means handling the
  threshold as well — series diode or level shifter, never 5 V alone. TODO 0c.
- **`mpremote exec` interrupts `main.py`.** The board stops advertising until
  you `reset` it.
