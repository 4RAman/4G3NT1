# AI Button

One physical button, six gestures (short press / long press / double tap /
triple tap / four taps / five taps), routed through a **mode machine** — the
button is always in exactly one mode, and the mode decides what each gesture
means. An RGB LED and feedback sounds show device state.

Modes come in two kinds. **Menus** answer a gesture and hand the button
straight back — always live, fired without thinking (the everyday set, plus
time-windowed overrides, launchers and control pages). **Apps** own the button
until you leave — twelve of
them: alarm,
reminder, stopwatch, tally, intervals (Pomodoro, Tabata or HIIT — one
template, three presets), metronome, countdown, two games (Hot/Cold and a
reaction timer), a signal light that doubles as an OSC or MIDI footswitch,
a control surface that fires a different command per gesture (the DAW
remote), and a light show that walks a playlist of your looks. Nine of those are started by a gesture and there are only six
gestures, so an **app launcher** reaches every one of them from a single
binding. **Long press always means "up one level"** — out of an app,
then out of the menu, and at the menus themselves there is no level left, so
it **puts the button to sleep**; a long press wakes it. One escape gesture to
learn, and it works everywhere.

The hardware is an **ESP32** — it detects gestures and shows feedback; this
Python app is the brain on the PC, connected over BLE. It replaces an
earlier Raspberry Pi build, preserved at the git tag `pi-legacy`; the
transition and its rationale are in [DESIGN-ESP32.md](DESIGN-ESP32.md).

> **Working on real hardware.** The transition is complete: press the button
> and the mode machine on your PC decides what it means, then drives the LED
> and buzzer back. With no ESP32 attached the app runs on a `MockDevice`
> instead, fully drivable from the web UI — no hardware needed to develop.

Menus resolve first-match-wins against eight action primitives:

| Action | What it does |
|---|---|
| `log` | record a timestamped event in SQLite (meds, habits) |
| `readout` | blink today's count for an event back at you — tens as slow pulses, units as quick ones; reads only, never adds a count |
| `timer_toggle` | start/stop a named stopwatch, durations logged |
| `webhook` | POST to any URL — the IFTTT / Make / n8n / Home Assistant hook |
| `osc` | fire an OSC message over UDP — Reaper, QLab, Resolume, TouchOSC |
| `midi` | send a MIDI note or CC to a port — for a DAW that has no OSC |
| `enter_mode` | launch an app — one of the eleven, or the launcher that lists them |
| `standby` | put the menus to sleep; the same gesture wakes them — what a long press does at the menus anyway, bindable elsewhere |

And one thing no press starts: a **reaction** is a circumstance with an action
attached. Name one, and anything that can make an HTTP request fires it —
`POST /api/reaction/moisture_low` from a sensor, a cron job, a deploy script or
an iPhone Shortcut — running any of the actions below, launching an app
included. The button acts with nobody touching it.

Example: between 05:00 and 07:00, a double tap logs `meds_taken`;
any other time it falls through to **Home**, the always-on floor. See the
`modes` section of [config.json](config.json).

Modes are built from **behaviour templates** — Actions, Notice, Stopwatch,
Tally, Intervals, Metronome, Countdown, Hot/Cold, Reaction timer, Signal
light, Control surface, Launcher and Light show — plus an *activation*
saying when each turns on (always / time window / at a clock time /
entered from another mode).

A built-in **web UI** (http://localhost:8080) shows live device state and the
event log, and includes a **point-and-click configuration menu**: add,
reorder, and delete modes; pick each gesture's action from a form (the
right fields appear per action type); install apps, ready-made or blank, and
see which of them anything can actually reach; set the
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
  breathe, flash, alternate, fade, rainbow), colours and speed - or a *named
  look*, which may be a whole sequence of colours the host walks through.
  Edited in the web UI and pushed to the button live.
- **AI**: none on the device, by design. Point the `webhook` action at
  whatever should do the thinking.

## Layout

| Path | What |
|---|---|
| `aibutton/` | the application package (config, rules, scheduler, actions, store, device, audio, webui, main) plus the pure light helpers the apps paint through — `sequencer.py` (stop lists), `ramp.py`, `ladder.py` |
| `aibutton/device.py` | the hardware seam: `ButtonDevice` + the wire protocol (gestures, LED states, sound commands, palette, UUIDs) |
| `aibutton/ble_device.py` | the bleak central: scan, connect, subscribe, auto-reconnect |
| `aibutton/button.py` | `TriggerDetector` — no longer runtime code, kept as the spec the firmware port follows |
| `firmware/` | the ESP32 half: MicroPython + `aioble` peripheral, gesture detection, LED animations, buzzer tones |
| `tools/ble_probe.py` | drive the firmware by hand over BLE (`--cycle` runs every animation and tone) |
| `aibutton/control/` | the tray control panel: start/stop the service, watch it, flash the firmware (`status.py` is pure; `tray.py` is the only part that needs a screen) |
| `control.pyw` | double-click launcher for the control panel — no console window |
| `aibutton/web/index.html` | the web UI dashboard — one static page, no build step |
| `aibutton/web/static/` | the configuration menu, as small ES modules (no build step) — `schema.js` is the single place to add an action type or setting |
| `aibutton/documents.py` | an app's durable named values, beside the event log in the same file — the current value, where the log holds the history |
| `aibutton/scenes.py` | scenes: swappable saved configs, merged over `config.json` before parsing — imports nothing from the package, and carries the offline CLI |
| `config.json` | the config the app runs on (override with `--config` or `$AIBUTTON_CONFIG`) |
| `scenes/` | saved setups, one JSON file each — hand-editable with nothing running; `config.json` says which is active |
| `tests/` | pytest suite — runs anywhere, no hardware needed; covers the firmware's hardware-free modules too |

## Architecture

One **single asyncio process** owns everything: the button event loop, the
LED/sound feedback, and an embedded uvicorn server for the web UI + REST
API — no second service, no IPC. They share one live `ConfigManager`,
`EventStore`, and `ButtonDevice`.

The pipeline per press is a one-way flow (a *reaction* is the same flow with an
HTTP request where the gesture would be — one queue over, dispatched by the
same loop into the same actions):

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
design it builds toward, [ARCHITECTURE.md](ARCHITECTURE.md). Design rationale:
[DESIGN.md](DESIGN.md) (the config schema itself is declared in
`aibutton/web/static/schema.js`). Usage:
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

## Numbers the button remembers

The event log only ever appends, which answers "what happened in March" and
cannot answer "what is it now" without recounting — and cannot express *"set
this to 3"* at all. So an app may also keep a small **document**: a bounded bag
of named values, declared per template, stored beside the log and never
instead of it.

Today one app uses it. A **tally** with *Keep counting past midnight* switched
on takes its number from its document rather than from today's rows, which
makes it a running total that survives midnight and restarts. Every press is
still logged, so history, streaks and the Events page are unchanged.

Because a document lives outside every app's run loop, **anything can write
it**: bind a gesture anywhere to **Change an app's number** and you have
"smoking +1" without opening the tally — and the tally opens on that same
number, because it is the same number rather than two that agree. `GET
/api/documents` reads them all; nothing but the button writes them.

The limits are deliberate and small: scalars only, slots declared in advance,
and a ceiling on how many an app may hold. That is the same "bounded by
construction" line the on-device app runtime draws, applied to storage — see
[ARCHITECTURE.md](ARCHITECTURE.md), "Apps own data".

## Seeing a webhook before you send it

A webhook's body is assembled from three places — the event's identity
(`trigger`, `mode`, `ts`), the session summary the app reports as it finishes,
and the payload you wrote — and which keys survive a collision is a rule
rather than an accident: identity beats the app, and your payload beats both.
Every webhook has **Preview payload**, which shows the exact JSON and sends
nothing, and **Send a test**, which posts it and reports what came back. Keys
the summary contract drops are named rather than silently missing.

## Driving a DAW — OSC and MIDI

Two actions reach music software, and which one you want is decided by the
software, not by preference.

**`osc` needs nothing installed.** Reaper, QLab, Resolume, VCV Rack,
TouchDesigner and TouchOSC all listen for OSC over UDP; point the action at
the host and port they are listening on and that is the whole setup.

**`midi` is for the DAWs that do not speak OSC**, Studio One being the one
this was built for — PreSonus document control surfaces over MIDI and Mackie
Control, and Studio One Remote uses their own protocol.

**On Windows it needs no Python package.** MIDI output goes through
`winmm.dll`, which has shipped with the OS since the 90s, reached from
`ctypes`. What it does need is a **virtual MIDI cable**, because Windows has
no built-in way to hand MIDI from one application to another:
[loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) is the usual
choice. Install it, add one port, and put part of its name in the action's
**MIDI port** field. Windows appends a number that changes between sessions,
so a port you called `Button` may enumerate as `Button 2` — matching on part
of the name is why that keeps working.

**Two things that will cost you an evening otherwise**, both learned the hard
way on 2026-08-27:

1. **Name the port.** Leaving the field blank takes *the first output there
   is*, which on a typical Windows machine is `Microsoft GS Wavetable Synth` —
   so every note goes to the built-in software synth and the DAW never hears
   it. There is no error, because nothing failed.
2. **Tell the DAW it has a control surface.** MIDI arriving is not MIDI being
   *understood*: add the port in the DAW as a **Mackie Control** device
   (Studio One: Settings → External Devices → Add… → Mackie → Control, Receive
   From = your port). Point a *keyboard* device at it instead and the notes
   show up in the MIDI monitor, get recorded into tracks, and move nothing —
   which looks exactly like a broken button. If the port is already listed
   under a keyboard device, take it off that one first.

With those two right, the transport buttons work unlearned: a DAW told it has
a Mackie Control already knows that note 94 is Play.

**On Linux and macOS** it needs `pip install python-rtmidi` instead, which is
not in `requirements.txt` on purpose — it is a C extension with no wheel for
Python 3.14, and requiring it would let the whole install fail over a feature
most people never touch. With no backend at all you lose the `midi` action and
nothing else; the service starts and every other action works.

### The quick way: add the DAW transport app

In the web UI, **Apps tab → Control surface → DAW transport (MIDI)**. It
drops in a **control
surface** — an app you open from the launcher, with one command per gesture:

| Gesture | Command |
|---|---|
| short press | Play |
| double tap | Record |
| triple tap | Stop |
| five taps | Drop a marker |
| **long press** | **leave the app** |

Set the MIDI port and you are done. The note numbers are **Mackie Control**,
so adding a Mackie Control device in your DAW pointed at the same port makes
them work with nothing to learn — no Control Link, no note numbers to look up.
Every MIDI action also has a **Start from a DAW command** picker covering the
whole Mackie map — transport, navigation, banking, channel strip, automation
modes and F1–F8 — grouped, with each entry's note number in its name.

> **The one mistake that costs an hour: adding it as a keyboard.** The DAW has
> to be told the port is a **Mackie Control**. Point a "New Keyboard" at it
> instead and every command arrives as an ordinary MIDI note, which the DAW
> will happily *record into a track* — you will see notes appear, switch the
> action to CC to investigate, and watch it record "controller effect depth"
> instead. That is not the button misbehaving; it is the DAW being told it has
> an instrument. A Mackie Control device never shows up as a track input.

Two more things about **Record** specifically, because it is the one that
looks broken: on real Mackie hardware the transport is a tape deck, so Record
*arms* and Play *rolls* — if one press does nothing, try Record then Play. And
nothing records unless a track is record-enabled.

Record is on the double tap deliberately: it is the one command whose
accidental firing costs you a take. The marker is on five taps rather than the
long press because **long press always means "up one level"** — an app that ate
it would strand you inside itself.

### The other direction: the light follows the DAW

A control surface can also be a **readout**. Give it **positions** — a name
and one of your named looks each, say *Stopped* wearing a dark blue and
*Recording* wearing a slow red breathe — and the page wears whichever position
it was last told it is in, instead of a single resting colour.

Nothing you press moves it. A position arrives as a **reaction**: the DAW lights
its own Record lamp by sending note 95 back down the wire, so *"recording"*
reaches the button as a fact rather than as a guess about what you last
pressed. That distinction is the whole point — a local toggle is right until
somebody clicks in the DAW, and then it is silently inverted for the rest of
the session, every press doing the opposite of what the light says.

What it needs:

1. **A second loopMIDI port** for the return direction. One cable per
   direction; the DAW's Mackie Control device has a **Send To** as well as a
   **Receive From**.
2. **A reaction per position**, each listening on that port
   (*From: MIDI*, note 95), scoped with **Only while** to the surface's name,
   and running **Put an app on a position**. Velocity is what tells them
   apart: `velocity == 127` is the lamp coming on, `velocity == 0` is it going
   off — one source, two opposite tests.

The position's own gestures are **not** fired when it changes this way.
Sending "record" back to the thing that just told you it is recording is a
loop.

**A surface with positions and no reaction able to set one says so** — in the
log and on the dashboard — rather than showing the first position as if it had
been reported. Position one looks identical whether it is a fact or an
assumption, so it has to say which.

### Following the project tempo

The **metronome** can take its tempo from the DAW instead of from your taps.
Set the mode's **Follow a DAW (MIDI clock in)** field to part of a MIDI input
port name, then turn on **MIDI Clock Out** in the DAW pointed at that port —
in Studio One that is a checkbox on the External Device, next to the port.

MIDI Clock carries no tempo number: it is one byte sent **24 times per quarter
note**, and the tempo is inferred from how fast the pulses arrive. Two things
follow from that. The button reads the *median* interval over about a beat, so
one late pulse cannot lurch the tempo but a deliberate tempo change takes
around half a beat to be believed. And if the DAW goes quiet without saying so
— quit, unplugged, paused mid-stream — the **last tempo is held**, because a
metronome that blanks when a cable twitches is less useful than one that keeps
time and says it is on its own.

While it is following a clock, **tapping marks a beat but no longer sets the
tempo**; two things steering one number is how you get a metronome that argues
with the session. Leave the field blank and nothing changes — it is the tap
metronome it has always been.

> Do **not** use MIDI Time Code for this. MTC carries SMPTE position, not
> tempo. A DAW will happily offer both.

### The flexible way: Control Link

If you want something the MCU table does not cover, use **New Keyboard**
instead of Mackie Control, then in Studio One **right-click the control you
want → Assign → Control Link**, and press the button. Almost anything in the
DAW can learn a message this way. Any note number works; the picker's numbers
are as good a starting point as any.

> **What this cannot honestly do: live looping.** A press is held for the
> multi-tap window (0.4 s) before it can be told apart from a double tap, and
> the radio adds tens of milliseconds on top. That is roughly twenty times the
> accuracy punch-in needs. Transport, markers, mutes and scene launches are
> fine; anything you have to land *on* a beat is not.

## Control panel

The web UI configures the button; it cannot *start* it, since it is served by
the very service it would launch. That job belongs to the **tray control
panel**. Put it on the desktop and Start Menu with:

```powershell
.\tools\install_shortcuts.ps1          # -Remove to take them away again
```

or run it directly (`control.pyw`, or `python -m aibutton.control`):

- a tray dot whose colour is the whole status at a glance — grey stopped,
  amber running-but-no-button, green ready, red died on its own;
- **Start** / **Stop** the service, with stop asking politely (so open timers
  close and a ringing alarm is silenced) before it escalates;
- **Update the button's firmware** — `mpremote` copy + reset, with the output
  in the log window, because flashing this chip fails in ways you need to
  read;
- **Open web UI**, for everything about what the button actually does.

Start launches the **real** button (`--ble`) by default — a panel that
silently ran a simulated one would look like it worked and do nothing.
*Use the real button* in the menu turns that off for working with no
hardware around, and the choice sticks in `control-panel.json`.

**Scene ▸** switches the whole saved setup from the tray. It asks the running
service (so the change is instant) and falls back to moving the pointer in
`config.json` when nothing is running, so you can line up tomorrow's scene
before you start.

## Scenes

A **scene** is a whole saved config you can swap in one click — a "Work" set
and a "Kitchen" set, or the two halves of an A/B test. They are plain files in
`scenes/`, one per scene, and `config.json` holds a pointer:

```jsonc
// config.json
{ "web_port": 8080, "scenes": { "dir": "scenes", "active": "focus" }, ... }

// scenes/focus.json — every key it defines wins over config.json
{ "name": "Deep Focus", "modes": [ ... ] }
```

The active scene is layered over `config.json` *as raw JSON* before the parser
runs, which is why a scene gets the same per-key fallbacks and the same
warnings as a config: there is only one parser. A scene need only carry what
it changes — one holding just `modes` keeps the base's colours.

**`scenes/default.json` is the one exception to "these are yours to make"** —
it is the curated, shipped starter every clone of this repo gets, checked into
git so it can be handed to someone with nothing configured yet. Every other
scene is somebody's own button, made through the UI or by hand, and
`.gitignore` keeps it that way: `scenes/*.json` is ignored except
`default.json`, so a personal scene never ends up in a commit by accident.
Name yours anything but `default`.

Because they are files, they are editable with nothing running:

```bash
./.venv/Scripts/python -m aibutton.scenes list           # what exists, what is active
./.venv/Scripts/python -m aibutton.scenes check focus    # validate, with the real parser
./.venv/Scripts/python -m aibutton.scenes activate focus # switch, applies at next start
```

Switching is hot — modes, colours and all — with one honest exception: the BLE
name, the web host/port and the database path are only read at startup, so a
scene that changes them reports `needs_restart` rather than pretending. No
`scenes` block in `config.json` means none of this is in play.

For a GUI with nothing running, build the standalone editor:

```bash
./.venv/Scripts/python tools/build_editor.py
```

That writes `dist/button-editor.html` — one self-contained file you can
double-click on any machine. It reuses the served UI's own modules and
stylesheet (bundled, because browsers refuse ES modules over `file://`) and
edits scene files through the file picker. The one thing it cannot bring along
is the parser, which is Python: it checks fields as you type and points at
`aibutton.scenes check` for the rest, rather than keeping a second validator
in JavaScript that nothing tests.

With `MockDevice` behind the seam, the browser *is* the button — you drive
everything from the page:

- **Simulate buttons** fire every gesture the button can send — through the
  real rules → actions → status pipeline. The row is generated from the
  gesture table, so it covers whatever a config can bind.
- **Virtual device panel** mirrors the LED (same animations: blue
  breathe, white pulse, …) and plays the device's actual feedback
  tones in the browser.
- **Test clock** — set it to 06:30 and a 5–7am rule matches *now*.
  Time-windowed rules become testable in seconds instead of waiting
  for the right hour. The override keeps ticking, never persists
  across restarts, and never alters event-log timestamps.
