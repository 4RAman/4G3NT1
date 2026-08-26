# To-do

Stage 2 of [ROADMAP.md](ROADMAP.md) — the MVP/demo push. Anything that
reshapes the architecture (the app runtime, the one-manifest move, moving the
brain onto the device) lives in [ARCHITECTURE.md](ARCHITECTURE.md) and the
roadmap, not here. **0a** and **0c** are the exceptions: they are Stage-2 work
*because* deferring them gets expensive once more hardware exists.

A new takeover written as a state machine over `(state, event, now)` will port
to the on-device runtime; one that awaits the device directly gets rewritten.

## Current hardware state

**Flashed to 0.6.1**, re-soldered 2026-08-21 onto **GPIO10** (`BUTTON_PIN`) and
**GPIO12** (`NEOPIXEL_PIN`) — both plain S3 GPIOs, so holding the button through
a reset is safe again. Wiring detail is in
[firmware/hardware.py](firmware/hardware.py).

Two things that will otherwise cost you a session:

- **The pins are source, not state.** Nothing physical produces a gesture until
  `mpremote cp firmware/*.py : + reset` has run. The web UI's simulate buttons
  and `POST /api/trigger` work either way, which is exactly what makes this
  easy to miss.
- **The ring is on 3V3 and renders colour wrong** — R:G:B ≈ 1.00:0.54:0.44, so
  white looks orange and blue-heavy looks read dim. Nothing is broken; it is a
  5 V part run under spec, traded knowingly to keep the data line's logic
  threshold safe (**0c**). **Read this before diagnosing colour work as a
  bug** — judge new colour work on the *onboard* LED, which renders accurately,
  or against the numbers. Anything with a gradient will look warmer on the ring
  than in the web UI's preview, and the preview is the one that is correct.

## How to work this list

Each numbered item stands alone: context, the files involved, and a definition
of done, so it can be picked up cold. **Numbers are never reused or
renumbered** — this file, CLAUDE.md, ROADMAP.md and the commit log all cite
them, which is why the sprint starts at 0a and has gaps.

A rule governing *future* code belongs in [CLAUDE.md](CLAUDE.md); this file
records the decision and points at it. Shipped items are compressed to the
choices that still bind.

Before touching code: read [CLAUDE.md](CLAUDE.md).

**This file used to say "run the suite before and after" and no longer does.**
That line is what turned one authorised run into three in a single session, at
3.5 minutes and a slice of the budget each. The rule is now
[CLAUDE.md](CLAUDE.md)'s *"Do not run the tests without being asked"*: write
them, hand over the command, and let the person paying decide when to spend it.

```bash
.venv/Scripts/python -m pytest -q
```

Only one instance may run (BLE allows a single central). If you need to restart
the service to pick up a change, **confirm first** — it may be live against the
real button.

## Where Stage 2 stands

[ROADMAP.md](ROADMAP.md)'s exit gates, scored 2026-08-26.

| Gate | State |
|---|---|
| Protocol v1 frozen | ✔ **0b** |
| Single-instance guard | ✔ |
| Verified power-cycle recovery | ✔ reconnected cleanly on a real replug |
| A launcher | ✔ **0a** |
| **10 apps** verified on hardware | **eleven built.** Ten verified; **Signal and the control surface have never met the button** |
| **A naive-user run** | not started; unblocked since **14**, and **47** is the desk-bound rehearsal for it - three personas walked the shell, three dead ends fixed, fifteen improvements as **54-68** |
| **24-hour soak** | not started. The service has now sat up for 12 h unattended and **an alarm rang for seven of them** with the button disconnected - not a soak, but the first evidence of what one would find |

**Nothing left is blocked on design.** What remains is hardware time (**0c**,
the soak, walking Signal) and one person sitting down with the button (**14**'s
naive-user run). No amount of code moves those three.

## Six bodies of work, not twenty items

The numbered list is right for picking one item up cold and wrong for deciding
what to do next. This is the other view.

| Body of work | Items | State |
|---|---|---|
| **The colour engine** — named looks, ramps, the safety floor | 3 ✔, 4 ✔, 0b·3 ✔ | Done |
| **The light as a language** — ladder, stop list, one primitive | 19 ✔, **36** ✔, 41 ✔ | **Done.** 19c closed the last thread; nothing else has a fraction to ramp over until `GESTURE_HOLD` (**29**) |
| **The gesture engine** — N taps, hold levels | 0b·2 ✔, 28 ✔ | Taps done. Hold levels need firmware — the cheap half of **29** |
| **Composition** — hooks, session summaries | 23 ✔, **31** ✔, **32** ✔ | Done |
| **Actions as a first-class idea** | 30a ✔, **33**, **34** | The pool shipped; the sequence and app documents are open |
| **Reach and hosting** — launcher, ten apps, remote UI | 0a ✔, 7 ✔, **8**, **40**, 42 ✔, **43** | The page works at phone width (42); reaching it is 8(d), an install not a feature. **40** and **43** are both "where does the host live", answered differently |
| **Reaching other software** — OSC, MIDI out, clock in | 22 ✔, 24 ✔, **25** | Sending and listening work. **25** needs the DAW's Send To pointed back |
| **Saying a number** — ambient counting, count readout | 15 ✔, 17 ✔ | Only the human read test, on hardware |
| **Play** — timing and guessing games | 16 ✔ | Done for forgiving games; tight rhythm needs Stage 3 |
| **The light as a show** — a playlist app, and the ring itself | 52a ✔, **52b** | The show ships on today's wire and cost no wire code; per-pixel (52b) is still a proposal |
| **Getting around** — launcher, control surfaces, colour coding | 0a ✔, 26 ✔, 27 ✔, 28 ✔ | Only **26b**, an eyeball test |
| **Power** — sleep, wake, deliberate off | **29** | Blocked on measuring what it draws |
| **The shell and its vocabulary** — what things are called, where they sit | 46 ✔, 45 ✔, 48c ✔, 53 ✔, 47 ✔ | **Done.** The Events page grew its charts and the read-back ran against the finished shell; what it found is **54-68** |
| **The app paradigm** — an app installed once, holding many items | 48a ✔, 48c ✔, 49 ✔, 50 ✔, 51 ✔ | **Done.** The list groups by app, the page reports reachability, and an app's own page is now the app (51) rather than its settings. Nesting the *format* is parked as **48b**, with the measurement that put it there |

| **Reflexes** — a circumstance, with an action attached | **70**, **71**, **72**, **73**, **74**, **75**, **79** | **New, 2026-08-26, and the biggest thing open.** ARCHITECTURE.md already lists `sensor` as an event kind and nothing produces one. **D10 is decided**: a reflex is an object, because most reflexes start no app at all. **71** (HTTP in) delivers most of it |
| **The DAW, both ways** — the button hears what the transport is doing | 22 ✔, 24 ✔, **25**, **73**, **77**, **78** | **25 stops being a design problem** the moment 73 lands: MCU is two-way, so "recording" is a fact the DAW sends rather than a guess. **77** is the light, **78** is the state machine |
| **Reading it back** — what fifteen minutes as someone else turns up | 42 ✔, 47 ✔, **54-68** | The walk is done and its dead ends are fixed; the improvements are fifteen separate items, none of them blocking |

Outside the table: **0c** is hardware and gates nothing but its own
verification; **18** (Notion) is process and is parked.

## Start here next session

Written 2026-08-26 at the end of the sprint below, so a cold session does not
have to reconstruct it.

**Nothing is blocked on a decision.** ROADMAP **D10** was the one open
question and it was answered on 2026-08-26: **a reflex is an object, not a
field on a mode** — because most reflexes start no app at all, and a field
cannot express "the DAW began recording, so change the light". Read **70**
first; it is the umbrella and it explains why the rest are shaped as they are.

**Start with 71.** A top-level `reflexes` list plus `POST /api/reflex/{name}`,
dispatched through the action machinery that already exists. It makes the plant
alarm real, it is the well-worn 4-to-6 file shape, and every later reflex
source (**73** MIDI in, **79** media keys) plugs into the same dispatch. The
one thing not to forget is that `reachableModes` gains a new root — miss it and
the App page calls a working config broken.

**Then the DAW, which is the demo worth having**: **73** (MIDI in) → **74** (a
reflex reaching a running app) → **77** (the light follows the transport). That
chain turns item **25** from a design problem into a thin app, and it is the
one sequence with a person waiting for it.

**The cheap-and-unblocked queue that was here is now empty.** **69, 76, 56**
and **57** all shipped 2026-08-26, in a low-hanging-fruit pass done on Sonnet
between sessions - see Done. What is left of the read-back is **54, 55** and
**58-68**: thirteen items, still none of them blocking, still each an hour or
less. **71** (below) remains the biggest thing open and the recommended next
start; treat the read-back as filler for a session that stalls on it, same as
before.

**Two things that are not code and block a Stage-2 gate:** a hardware sitting
(**0c**, plus the Signal and control-surface walks and **26b**), and **14**'s
naive-user run. Neither has moved in three sprints.

**Known live state you may trip over:** the service has been up ~12 h with the
button **disconnected**, and an alarm fired at 07:00 and was still ringing.
There is a **Dismiss** button in the header now. The `no-store` header on
`/static` still needs a service restart to take effect — until then a browser
will happily run a stale ES module graph, which looks exactly like your edit
not having happened. Priming the HTTP cache with
`fetch(url, {cache: 'reload'})` for each module before reloading is the
workaround that got this session verified.

## Sprint

### 70. Reflexes — a circumstance, with an action attached

**Asked for 2026-08-26, and named by the owner: these are reflexes.** Not
signals, not triggers — and the word is load-bearing rather than decorative,
because it says what the thing *is*. A reflex is **a circumstance or event with
an action attached to it**, and the button acts on it without anyone pressing
anything.

**This is not a new architecture. It is the host-side half of one already
decided.** [ARCHITECTURE.md](ARCHITECTURE.md)'s app runtime lists its event
kinds as *"gesture · timer expiry · schedule fire · sync reply · **sensor**"*,
and `Request` is described as answering "with an **event** the app can
transition on". Inbound events are in the target design; nothing has ever
produced one. ROADMAP's Stage 6 table says "sensors as activations, same slot
as geofencing" in three separate rows, **and there is no such slot.** This
builds it, on the host, years before any of that hardware.

**Worked examples, the owner's own:** a plant's moisture sensor crossing a
threshold rings an alarm; a DAW reporting that it has started recording changes
what the light does (**77**); a script on the PC starts an app; media
play/pause moves the button into a transport page (**79**).

#### The decision this settles: a reflex is an object, not a field

**ROADMAP D10 is answered, and the owner's definition is what answers it.**
The earlier draft of this item made an inbound event a new *activation type* —
a field on a mode, beside `schedule`. That was wrong, and the reason is in the
word "reflex": *most reflexes do not start an app at all.* "When the DAW starts
recording, make the light pulse red" enters no mode, logs nothing, and has no
mode to be a field on. A field can only ever express "this app starts now",
which is one of the things reflexes do and not the interesting one.

So a reflex is a standalone object:

```
when    a circumstance — an arriving event, optionally with a test on it
then    an action — any action the button already has
```

**And `then` being "any action the button already has" is the whole economy of
this item.** `resolve_action` and `actions.execute()` already exist; a reflex
firing `enter_mode` covers everything the activation-field design could do, and
a reflex firing `osc`, `webhook`, `midi` or a **named action from the pool**
covers everything it could not. Adding reflexes adds a source of events and
**no new vocabulary of consequences.**

**Scope: system-wide by default, app-scoped by exception.** The owner's read is
right — most reflexes are about the button and the world, not about one app. So
`reflexes` is a top-level list. An optional `while: <app name>` limits one to
the times that app is open, which is what **77**'s transport lights want and
what stops a DAW reflex repainting the light in the middle of a Pomodoro.

#### Where a circumstance comes from

Ranked, and the ranking is the recommendation:

1. **HTTP — `POST /api/reflex/{name}`.** Near-zero code, and it **subsumes
   almost everything**: anything that can make a request can drive the button,
   so the plant sensor, a cron job, Home Assistant, an iPhone Shortcut
   (**39**) and any script arrive through one hole. Do this first and most of
   the item is delivered.
2. **MIDI in** (**73**). Half-built — `midi_io` already opens an input for the
   metronome's clock listener. **This is what item 25 has been waiting for.**
3. **OSC in**, the mirror of the `osc` action. Cheap.
4. **OS media transport** (**79**) — possible, with caveats worth reading
   before promising it.
5. **MQTT** is the home-automation lingua franca and the one that costs a
   dependency. **Not now** — a bridge posting to (1) is five lines, and the
   `midi` precedent in CLAUDE.md says check what the platform already has
   before taking a dependency for one feature.

#### What does *not* change

**Schedules stay where they are.** An alarm at 07:00 is a circumstance with an
action attached and is therefore a reflex by this definition — and migrating
`ScheduleActivation` into the reflex list would rewrite every config and scene
for no new capability. The line to hold: **an activation says when an app may
run; a reflex says what makes something happen.** An alarm's time is a property
of that alarm, the way its message is. A reflex is for what a schedule cannot
express — which is everything not on a clock, and every consequence that is not
"start this app".

There is real overlap and it is accepted knowingly. *Do not add a clock source
to reflexes until something wants one an alarm cannot do.*

**Split into build items 71–74, plus 77–79. Do not build the umbrella.**

### 71. A reflex fires an action, and HTTP is the first source

**The cheap half of 70, and the one that delivers the plant alarm.** A
top-level `reflexes` list, `POST /api/reflex/{name}`, and dispatch through the
action machinery that already exists.

The shape, following every other list-of-things in this config:

```json
"reflexes": [
  { "name": "moisture_low", "then": { "action": "enter_mode", "target": "Water me" } },
  { "name": "deploy_done",  "then": "celebrate" }
]
```

The second one is a **bare string, which is a named-action reference** —
`config.resolve_action`, exactly as a gesture binding does. CLAUDE.md is
explicit that a fifth dispatch site calls the resolver or that surface silently
cannot use the pool; this is that fifth site.

**Parse-with-fallback applies as everywhere else**: a reflex naming an action
that does not exist is warned about and left dangling, not quietly dropped.

**The App page has to learn about it.** `reachableModes` starts from the things
nobody has to start; a reflex firing `enter_mode` is a **new root** in that
walk. Miss this and the page calls a working config broken — CLAUDE.md says so
in as many words.

**Definition of done.** A script posting to `/api/reflex/water_me` rings an
alarm; the App page reports that alarm as reachable *because of the reflex*; a
reflex nothing ever fires is visible rather than silent; and a `while` scope
naming a missing app warns.

### 72. A reflex can test the value it arrived with

**The half that makes 70 powerful**, and the half most likely to turn into a
language if nobody is watching. The body carries JSON; a test is **one field,
one operator, one number**. `moisture < 30`, and nothing else.

Bounded by construction, for **D2**'s reason: this must be evaluable by the
on-device runtime eventually, and an expression parser is not. **The moment it
grows an `if` or an `and`, it is a language and it is host-only forever.**

**The value should land in the event log's `value` column**, which exists for
exactly this kind of number — and CLAUDE.md's group-by-name rule then gives it
a chart on the Events page for free.

### 73. MIDI in as a reflex source — and what item 25 was waiting for

A listened MIDI port turns note-on and CC into reflexes. **Read item 25
first**: it establishes that a Mackie Control is *two-way*, that the DAW tells
the surface what the transport is doing, and that **derived state beats
modelled state**. 25's "point the DAW's Send To at a port the button listens
on" is this item, and 25 stops being a design problem.

**A `when` here needs three fields**: the port, the note (or CC) number, and
**the velocity** — because MCU feedback uses velocity as the lamp: `127` means
that button is lit, `0` means it is not. So "the DAW is now recording" is
*note 95, velocity 127*, and "no longer recording" is *note 95, velocity 0*.
**The same note number means both things**, which is exactly why 72's test
exists and why a reflex ignoring velocity would fire on both.

`ClockListener` already owns a MIDI input and a ctypes callback with a lifetime
trap documented in CLAUDE.md — **reuse it, or read it before writing a second
one.** A driver calling a collected callback kills the process outright: no
traceback, no exception to catch.

### 74. A reflex can change what a running app is doing

**The invasive one, and what every interesting example needs.** Starting an app
is a decision the mode machine already makes; reaching *into* a running
takeover means the run loop accepting an event that is not a press. Every
takeover awaits `device.events`, so there is nowhere for one to arrive.

Options, in increasing order of honesty: inject a synthetic press (works today,
lies about what happened, and a session summary would record a press nobody
made); give the run loop a **second queue** it selects on alongside the
device's; or wait for Stage 3, where `(state, event, now)` takes any event kind
by construction and this costs nothing.

**Recommend the second queue**, and recommend it now rather than at Stage 3,
because two things want it and one is the reason this item exists: **77**'s
transport lights, and 47's ringing-alarm dead end solved for a machine rather
than a person.

*Whatever arrives this way is an event with a kind, not a fake gesture.* An app
that cannot tell a press from the world is an app that will lie in its log.

### 75. What the mode list is called, now that reflexes are real

**"Reflexes" stops being the wrong word the moment 70 exists**, which settles
the complaint that started this. Today the group holds gesture maps — the most
*voluntary* thing on the page — under a word meaning involuntary. After 70 it
means what it says.

The owner's proposal, and it is better than what is there:

| Group | What it means | Holds |
|---|---|---|
| **Menus** | a gesture picks between things | the ambient map, launchers, control surfaces |
| **Apps** | takeovers that do a job | the other ten |
| **Reflexes** | the button acts with nobody pressing it | reflexes (**70**), and scheduled apps |

**And it fixes 69's duplication for the new half by construction.** A reflex is
its own object, so *"moisture_low → Water me"* is a row in Reflexes and the
alarm is a row in Apps — two different things, listed once each. Only scheduled
apps still double-list, because their schedule is still a field; that is the
residue of **70**'s decision not to migrate them, and **69**'s collapsing is
the answer to it.

*Do not rename anything before 71 ships* — the words follow the concept, and a
nav group called Reflexes with nothing in it is worse than the current one.

### 77. The DAW tells the button what it is doing, and the light says so

**Asked for 2026-08-26, and it is the example that makes 70 concrete.** The
owner's words: *one press to record; the DAW tells the button it's recording
and the light turns bright, gently pulsing red; press again, the light turns
dark blue for stopped; another press goes back to recording.*

**Every piece of this is expressible once 73 and 74 exist, and none of it needs
the button to guess.** MCU is two-way: the DAW lights the surface's own Record
lamp by sending note 95 back, so *"recording"* arrives as a fact rather than an
inference. That is item 25's central finding and the reason it says **derived
state beats modelled state** — a local toggle ("I sent Record, so we must be
recording") is correct until somebody clicks in the DAW, and then it is
silently inverted for the rest of the session, every press doing the opposite
of what the light says.

**The design, and it needs one new idea only.** A control surface already owns
`LISTENING` and already re-paints it after every action — `resting()` does that
today, which is what makes its light survive each press's SUCCESS flash. What
it lacks is *more than one* resting look. So:

- A control surface gains **positions**, each with a name and a look. This is
  **not a new concept**: it is the Signal light's `states`, which is exactly
  "the app is in one of N visible states", in a second template that needs the
  same thing.
- A **reflex sets the current position** (needs **74**). `note 95 velocity 127
  → "Recording"`; `note 95 velocity 0 → "Stopped"`.
- `resting()` paints the current position instead of a fixed LISTENING look.
  **That is the whole rendering change.**

The owner's colours are then config, not code: Recording is a slow breathe on
bright red, Stopped a solid dark blue. Both are ordinary named looks, and a
stop list can shape the pulse however it should feel.

**What this deliberately does not do yet:** make one press mean record-or-stop
depending on the position. That is **78**, and keeping them separate matters —
the light half delivers most of the value and can ship alone, while the press
half is a state machine and should be recognised as one.

**Definition of done.** With the DAW's Send To pointed at a port the button
listens on, arming record **by clicking in the DAW, not by pressing the
button** turns the light red; disarming turns it blue; and with no feedback
port configured the surface says it is guessing rather than pretending to know.

### 78. A control surface where the press depends on the position

**The other half of 77, and the one that is a state machine.** Once a control
surface has positions (**77**), the natural next step is that each position has
its own gesture map: *while Stopped, short press → Record; while Recording,
short press → Stop.* One gesture, two meanings, decided by what the DAW last
reported — which is exactly the owner's "another press goes back to recording".

**This is ARCHITECTURE.md's target app shape arriving early in one template**:
positions are states, reflexes and gestures are events, and a transition is
`(position, event) → (position, actions)`. Keep it exactly that shape and it
ports to the Stage-3 runtime unchanged; let it grow a conditional and it does
not.

**It also answers item 25's last open question** without a `transport`
template. 25 notes that MCU has no "return to zero" and that Studio One needs
*Stop, Stop*, which `MidiAction` cannot express — so this either waits for
**33** (`SequenceAction`) or lets a position fire two actions in order.
**Prefer 33**: a flat list of actions with delays is wanted in several places,
and a per-position pair is that idea with a worse name.

**Do not start this before 77 is running on real hardware.** The whole design
rests on MCU feedback actually arriving, and that has never been tested here.

### 79. Can the button hear the OS's play/pause? — mostly yes, with caveats

**Asked 2026-08-26**, and worth answering properly because the obvious
assumption is wrong in an interesting way.

**Receiving the key press: yes, and cheaply.** Windows media keys are ordinary
virtual key codes (`VK_MEDIA_PLAY_PAUSE` and friends) and can be observed with
a low-level keyboard hook or a registered hotkey, both reachable through
`ctypes` on `user32.dll` — **no dependency**, the same move `midi_io.py` made
with `winmm.dll` and the one CLAUDE.md holds up as the example of checking what
the platform already has. [keys_io.py](aibutton/keys_io.py) already sends keys,
so the receiving half has an obvious home.

**But a key press is not a playback state**, and that difference is the whole
question. A hook tells you *somebody pressed play/pause*; it does not tell you
whether anything is now playing, what it is, or whether the press was even
handled by anything. For "the button should know music is playing", that is the
wrong signal.

**Playback state proper is `GlobalSystemMediaTransportControlsSessionManager`**
— the SMTC session API: real playing/paused status, track metadata, per-app
sessions. It is **WinRT**, so it costs a dependency (`winsdk` or similar) and
is **Windows-only**. That is a real cost against a service that runs on four
packages and is meant to work headless on a Pi (**40**).

**Two caveats on the cheap route, both of which have bitten people:** a global
low-level keyboard hook is exactly the shape antivirus and EDR flag, and it
sits in the input path of every keystroke on the machine — a hook that blocks
is a hung desktop. If it is ever built it must be **opt-in, off by default, and
killable from the tray**.

**Recommendation: do not build either until something concrete wants it.**
Whatever is playing the media can already `POST /api/reflex/now_playing`, which
is one line in a script, works on any OS, needs no hook and no dependency —
the same argument that parks MQTT in **70**. Revisit if a real use appears that
a script genuinely cannot serve.


### 54-68. What the three-POV read-back found

**Raised 2026-08-26 by item 47** (see Done), which walked the finished shell as
three fixed personas. The bugs and dead ends it turned up were fixed in the
same pass; these were fifteen further improvements, five per point of view,
deliberately *not* one item - each stands alone and several are an hour.
**54, 55, 56, 57, 59, 61, 63, 64 and 68 shipped 2026-08-26** - see Done. Six
remain open: 58, 60, 62, 65, 66, 67.

Nothing here is a bug. The page works; these are the places where it makes the
reader do the work.

#### (a) The household user - never opens a config file

- **58. The only way to press the button is behind a toggle labelled "Test".**
  That is right when the button is in your hand and wrong in the case that
  actually sends people to this page: the button is across the room, flat, or
  out of range. **The ringing-alarm half of this was fixed** (see Done); the
  general case is still that a disconnected button leaves the page with no
  visible controls at all.

#### (b) The tinkerer - edits JSON when annoyed

- **60. A validation error names the field and not where it is.**
  `_collectErrors` produces "Wake up: Give up after must be a number" and the
  Save bar prints it. Nothing scrolls to the control or marks it. With eleven
  modes and one editor on screen, finding it is the work.
- **62. Parser warnings appear once, on load, in the Save bar.** They are
  per-key and they know which key. A dangling look or a bad ladder rung should
  mark its own field, not print into a `<pre>` that the next Save overwrites.

#### (c) The developer - wiring the button into other software

- **65. A webhook cannot be previewed or tested.** Every colour picker got
  "Show on the button"; a webhook has no equivalent. An app's summary keys are
  merged flat into the payload, and there is no way to see the result without
  standing up a receiver.
- **66. Which keys an app reports on exit is discoverable only in `main.py`.**
  `summary.clean` merges them flat into a webhook and appends them
  *positionally* to an OSC message - so for OSC the **argument order is the
  contract**, and CLAUDE.md already says an app reports the same keys every
  time or none. The editor should list them per app. This is the one that makes
  `on_exit` usable by someone who did not write the app.
- **67. A MIDI or OSC action reports its result only in the global status
  line.** `last_message` carries "MIDI note on 94 vel 127 ch1 -> Microsoft GS
  Wavetable Synth", which is exactly right and is overwritten by the next
  action anywhere. Wiring a DAW means watching the header and guessing which
  press you are looking at.

### 52b. Per-pixel ring patterns *(a protocol proposal, not a decision)*

**The ring is one lamp on today's wire**: `led.py` paints every pixel the same
colour, and an effect is style plus two colours plus a period. Chases, comets,
wipes and a ring split between two colours are therefore "a capability the
device physically cannot express today" - the exact test
[CLAUDE.md](CLAUDE.md) sets for breaking the v1 freeze.

It needs a firmware renderer that addresses pixels, a **parameterised pattern
set** on the wire (not a per-frame pixel stream - that is a radio the button
does not have), and a capability bit so an un-reflashed device degrades to a
flat colour.

**52a shipped first on purpose.** Play with it before deciding: if a show is
not fun on one lamp, per-pixel will not save it, and if it is, this item gets
a much better brief than it has now.

### 40. A portable host - the button away from the PC

**Asked for 2026-08-23**, alongside 37-39. The goal in the user's words: use
the button with an iPhone, away from the computer, with the GUI reachable and
the button still functional. Portable batteries and a hotspot are available.

**The iPhone cannot be the host, and that is structural.** iOS cannot run the
service, and Safari has no Web Bluetooth - so **8(b) is out for iPhone
specifically**, which is worth writing down because it is the obvious idea. A
native iOS app speaking the existing GATT service is the Stage-4 answer
(ROADMAP **D1**), not a near-term one.

**So relocate the host rather than eliminate it.** A Raspberry Pi Zero 2 W (or
any small Linux box) on a power bank, in the bag with the button:

```
button  <--BLE-->  Pi (the service, unchanged)  <--hotspot-->  iPhone (Safari)
```

**This needs no code.** The service is already headless by design - CLAUDE.md
records that pystray and Pillow are the control panel's alone and "a headless
host still installs four", and `bleak` speaks BlueZ on Linux. The GUI is the
existing web UI at `http://<pi>:8080`.

**Three things that are not free, and the third is a real bug:**

- The `midi` action is Windows-only (`winmm`). It is optional at import, so the
  service degrades rather than failing - already the designed behaviour.
- A `keys` action (**37**) would be *host*-local: on the Pi it types into the
  Pi. Macros and portability are different use cases and should not be sold as
  one.
- **The single-instance lock is per-machine.** `<database_path>.lock` is an OS
  file lock, so a Pi and a PC cannot see each other's, and both will fight for
  the one central the device allows - which presents as a connection that keeps
  dropping, not as an error. **Fix this before recommending the topology to
  anyone**, most likely by having the loser recognise it is not the connected
  host rather than by inventing a distributed lock.

**Definition of done.** The button runs a full day off a power bank with the
service on the Pi, the web UI is usable from an iPhone over the hotspot, and
two hosts contending for the device says so clearly instead of thrashing.

**Not to be confused with 8.** Item 8 hosts the *dashboard* remotely and still
needs a BLE process near the button; this item moves *that process*. 8(a)'s
relay composes with this later if a permanent dashboard is wanted.

### 39. iPhone Shortcuts, through the webhook action

**Asked for 2026-08-23.** Almost certainly **zero Python**: `webhook` already
posts arbitrary JSON, so this is a matter of picking the bridge and writing the
recipe. Candidates, cheapest first:

- **Pushcut** - purpose-built webhook-to-Shortcut. Paid, and the most direct.
- **Home Assistant** - if one is already running, a webhook trigger drives a
  Shortcut via HomeKit.
- **Shortcuts' own "Bluetooth device connects" personal automation** - free and
  native, but fires once per *connection* rather than per gesture, so it can
  express "the button woke up" and nothing finer.

**Verified 2026-08-23, and the answer keeps this item alive.** Apple's trigger
list has **no HTTP/webhook trigger and no hardware-key trigger** - a connected
keyboard can type, but a keypress cannot start a Shortcut. So **38 does not
subsume this item**, which was the one finding that would have merged them.

What *does* exist is connection-level: **Bluetooth device connects** has been a
trigger for years, and **iOS 26 added a "keyboard connection" trigger**
alongside screenshot and notification ones. Both fire once per *connection*, so
they can say "the button arrived" and nothing per-gesture. Worth knowing for 38:
a button paired as an HID keyboard gets that trigger for free.

So Pushcut (or a HomeKit/Home Assistant bridge) remains the route, and the cost
here is still zero Python.

**Definition of done.** A gesture runs a named Shortcut on the phone, written
up in MANUAL.md as a recipe, with no new action and no new dependency. If it
turns out a new action *is* needed, stop and re-scope - the value here was that
it was free.

### 38. BLE HID - a camera remote, and the first app that needs no host

**Asked for 2026-08-23 as "iPhone selfie stick trigger, with countdown
options".** A shutter remote is a BLE HID keyboard sending Volume Up; iOS
Camera fires on that. So the ask is an **HID service alongside the existing
custom one**, not a change to the existing one.

**This clears the v1 freeze bar, and is the first thing to do so.** CLAUDE.md
sets that bar at "a capability the device physically cannot express today", and
talking to a phone that will never speak our GATT service is exactly that.
Adding a service is additive, so **Add, don't repurpose** is satisfied.

**The value is not selfies.** It would be the **first app that works with no
host at all** - the firmware already renders animations unattended, so an
on-device countdown is consistent with what is there. That makes this a
rehearsal for Stage 4 rather than a toy, and it is the argument for doing it
before the on-device runtime rather than after.

**The mechanism is confirmed (2026-08-23), and it is not a keyboard key.**
The shutter is the **Consumer Control** usage `0xE9` (Volume Up), not a
keyboard scancode - so the HID report descriptor needs a **Consumer Page**
collection, which is a different and smaller thing than emulating a keyboard.
iOS has treated volume-up as the shutter across every built-in Camera mode
since iOS 7, with no app installed.

Two consequences worth having before anyone starts:

- **Built-in Camera only.** Third-party camera apps generally take volume-up as
  *volume* and change it instead of firing. So this app targets Apple's Camera
  and should say so rather than being discovered.
- **Pairing as a keyboard is worth doing anyway**, even though the shutter does
  not need it: iOS 26's "keyboard connection" automation trigger would then let
  connecting the button start a Shortcut, which is the only native bridge
  between this item and **39**.

**Decide before code:**

- **The one-central conflict.** Paired to the phone as HID, the button is not
  connected to the PC and none of the app machinery runs. So HID is a *mode*,
  and how you enter and leave it - and how the button says which world it is in
  - is the actual design question. A long press cannot mean "up one level" if
  there is no host to go up to.
- **Where the countdown runs.** On-device is the whole point; that means a
  firmware app, which the project has never written. Keep it a pure step
  function so it ports to the Stage-3 runtime.
- **Pairing and bonding** are new surface: an HID device must bond, and the
  phone remembers it. What happens when both a phone and a PC want it?
- **MicroPython HID over GATT is non-trivial — and the blocker is cleared.**
  Spiked 2026-08-25 as far as desk work goes; the code is
  [spike_hid.py](firmware/spike_hid.py), standalone and imported by nothing.
  - **Bonding is in the stock build.** This was the risk that would have
    killed the item, because HOGP is useless on an unencrypted link.
    `ports/esp32/mpconfigport.h` defines
    `MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING (1)` — in **v1.25.0** as well
    as master — against a default of `(0)` in `extmod/modbluetooth.h`. So the
    plain `ESP32_GENERIC_S3` build README.md already tells you to flash is
    enough. **No custom MicroPython build.**
  - **aioble supplies the rest.** It exports `Descriptor`, which the Report
    Reference (`0x2908`) needs, and ships `security.py` — `load_secrets()`
    plus `pair(connection, bond=True, le_secure=True, …)`, persisting bonds to
    `ble_secrets.json`, reached as `connection.pair()`.
  - **One real gap, and it is the thing left to test.**
    `aioble.Characteristic` takes `read/write/write_no_response/notify/
    indicate/initial/capture` and **no security flags**, so the Report
    characteristics cannot be declared encrypted-only. The spike asks for
    encryption from the peripheral side instead. If iOS refuses to drive an
    HID device whose reports are not access-protected, the escape hatch is raw
    `bluetooth.gatts_register_services` with `FLAG_READ_ENCRYPTED` for the HID
    service alone. **Unknown until it meets a phone.**
  - **The shutter is Consumer Control, one byte, bit 0 = `0xE9`.** Report map,
    HID Information, Battery and PnP ID are all written and commented in the
    spike. Advertised appearance is **Keyboard (0x03C1)** so the same run
    tests whether that alone earns iOS 26's "keyboard connection" trigger —
    the only native bridge to **39**, and worth knowing rather than assuming.
  - **What it costs to run:** `main.py` is renamed aside for the duration
    (it registers its services at import, and re-registering is not something
    NimBLE promises to survive), so the board boots to a bare REPL until it is
    renamed back. Recoverable, never bricked. Forget the pairing on the phone
    between report-map changes or iOS serves a cached GATT table and the
    edit looks like it did nothing.
  - **Not yet run on hardware** — the board was unplugged on 2026-08-25.
    `spike_hid.probe()` answers the build question with no phone involved and
    is the first thing to run at the bench.

**Definition of done.** The button takes a photo on an iPhone with no computer
involved, a countdown is visible on the LED, and leaving camera mode returns the
button to the host without a power cycle.

### 42. The web UI at phone width

**Asked for 2026-08-25**, as the near half of 40: the GUI on an iPhone. The
page already declared `width=device-width` and the shell already stacked at
900px, so this read as done and was not. Measured at 375×812, every tab had
content rendering past the right edge.

**Three faults, and the first was not a phone bug at all.**

- **`.inp { width: 100% }` sat at the bottom of the stylesheet**, below
  `.inp-color`, `.ladder-every`, `.inp-range-num` and `.ramp-at` — equal
  specificity, so source order decided it and every fixed-width control lost
  its width. The visible casualty was the slider rows: the typed number took
  the whole row and pushed the readout off the end **at every window size**,
  desktop included. The rule now sits with the base input styling, above the
  variants that narrow it.
- **The Modes tab put a 250px nav beside the detail form**, leaving the form
  65px wide at 375 — it rendered off-screen, reachable only by scrolling the
  panel sideways, which looks exactly like the mode editor being blank. Now
  stacks below 640px, with the nav unpinned while stacked. 640 rather than
  900 because the split still fits an iPhone in landscape.
- **The Events table dragged its panel sideways.** Six columns will not fit a
  phone at any font size, so the log scrolls in a box of its own.

Verified by measuring every element's right edge against the viewport on all
four tabs at 375 and at 1280: zero overflow at both, and the slider row went
from 500px of content in a 313px row to fitting.

**What is left, and it needs a hand and a phone, not code:** touch targets.
`.mini` buttons are ~24px against Apple's 44px guidance, and there are a lot
of them. Worth a decision — bigger controls on a coarse pointer
(`@media (pointer: coarse)`) is the cheap version — but taken after someone
has actually used the page on a phone rather than before. Fold the dashboard
away first (**◧ Panel**); it costs a third of the screen.

**Reaching it is 8(d), and it is not code.** Tailscale on the host and the
phone, `http://<machine>:8080` from anywhere, nothing public — written up in
MANUAL §4.5. The web UI still has no authentication, so that stays the only
recommended route off the LAN.

### 43. Can the button host the page itself?

**Asked 2026-08-25, and the answer is "yes, and that is not the constraint".**
Recorded because it is the obvious idea and deserves a real answer rather than
being re-derived.

**The page fits, easily.** The whole authoring UI already exists as one
self-contained file — `dist/button-editor.html`, 341 KB, built by
[build_editor.py](tools/build_editor.py) — and it runs with **no service at
all**, swapping `ConfigApi` for `FileApi`. Gzipped it is well under 100 KB
against 4 MB of flash. ARCHITECTURE.md's budget table says it outright:
*storage is a non-issue; RAM headroom and power are the real constraints.*

**So what stops it is not the device. Three things, in order:**

- **Power, which is decisive and is already scored in 21.** BLE connected is
  single-digit mA; WiFi associated is an order of magnitude more with 100-300
  mA bursts, against a 7-day idle target. A button holding a web server up is
  a different battery and therefore a different enclosure.
- **The served page is a view onto the service, not a standalone app.** It
  talks to a REST API that *is* the host: parse-with-fallback, scenes, the
  event store, the scheduler, rules, and the webhook/OSC/MIDI actions. Move
  the page without the brain and you get an editor with nothing behind it.
- **It inverts a decided ownership rule.** ARCHITECTURE.md: config's source of
  truth is the **phone**, and *the device never edits config*. A device-hosted
  config editor writes config on the device, which is the one direction the
  sync design forbids.

**The shape that survives all three: a momentary SoftAP setup mode.** Hold to
enter, the S3 raises its own access point, serves the offline editor from
flash, takes the edited JSON back over one POST, writes it, drops the AP.
WiFi is up for minutes rather than days, so the power objection goes; BLE is
down while it is up, which is exactly 21's *config-time either-or, never
concurrent*; and it needs no brain on the device because the offline editor
already runs without one.

**Its honest limit today is that the button cannot act on what you edited** —
every decision is host-side, so a config the device holds and the host never
sees does nothing. That makes this a **Stage-3 companion**, useful the moment
the on-device runtime lands and near-useless before it. Same verdict, same
reason, and the same trigger as **21**: measure at ROADMAP **3c**, build
after.

**On upgrading the board — don't, for this.** No MCU swap moves the binding
constraint, because the constraint is not flash:

- **S3 N8R8 / N16R8** (8-16 MB flash, 8 MB PSRAM) — same chip, same firmware,
  more room. Buys **RAM headroom for the Stage-3 runtime**, which is one of
  21's named triggers, and buys nothing for hosting. The only upgrade worth
  considering, and 21 says measure before buying.
- **ESP32-P4** — much faster, and **no built-in radio**; it needs a companion
  wireless chip. Wrong direction.
- **ESP32-C6** — better low-power silicon and Thread/Matter, but a weaker
  single RISC-V core than the S3's two. Interesting for **29**, not for this.
- **Pi Zero 2 W** — runs the real service unchanged, which is **40**. ~100 mA
  idle and a ~20 s boot: right in a bag, wrong in a pocket.

### 0c. Re-solder the button, and move its LED to 5 V while it is off

**Do this before anything whose test is "look at the ring".**

**The button went back on 2026-08-21** — switch to GPIO10, LED data to
GPIO12 (see the state note at the top). That closes the first half of this
item.

**The second half is explicitly deferred, not forgotten.** The LED went back
onto **3V3**, the same rail it was on before, so the channel imbalance below
is unchanged and still present. That is a decision rather than an oversight:
3V3 keeps the data line's logic threshold met by construction, and the 5 V
move below cannot be made without also handling the threshold (series diode
or level shifter). Taking the colour fault over an intermittent-flicker fault
is the right way round while the button is being used daily.

What that leaves open is below, unchanged: the three-level and load-ladder
tests still have not been run, so "headroom" remains a diagnosis rather than a
measurement. Run them before buying parts - they cost a minute and decide
whether 5 V is even the right fix.

**What was found.** Pushing known colours at both LEDs from the Lights tab's
test bench turned up two separate faults, not one:

1. **Byte order — fixed, flashed, confirmed on hardware.** `NEOPIXEL_ORDER`
   and `ONBOARD_NEOPIXEL_ORDER` in [hardware.py](firmware/hardware.py) were on
   the wrong LEDs. Nothing to do; it is recorded because the *evidence* is the
   useful part. `#ff0000` lit **both** LEDs green, `#00ff00` lit both red,
   `#0000ff` was correct — one R/G swap on both at once, which is what
   exchanging those two settings produces and is distinguishable from either
   one being wrong alone (that would have made the two disagree). Blue, yellow
   and white are fixed points of an R/G swap, which is exactly why the fault
   hid on them; cyan↔magenta is the pair that talks.

2. **Channel imbalance on the ring — open. This is the rework.** With the
   order corrected the onboard LED renders accurately and the ring still does
   not: white as light orange, cyan with a green tint, magenta with a red
   tint, yellow with an orange tint. One consistent ordering, **R > G > B**,
   measured off video at roughly `1.00 : 0.54 : 0.44`.

**The diagnosis, and why it is a wiring change rather than a constant.** That
ordering is a forward-voltage fingerprint. A WS2812's red die is AlInGaP at
~1.9–2.1 V; green and blue are InGaN at ~3.0–3.2 V. Each channel is a
constant-current sink needing headroom above Vf to regulate. The ring's VDD is
on **3V3** ([hardware.py](firmware/hardware.py)'s wiring block), so red has
~1.3 V of headroom and regulates, while green and blue have ~0.1–0.3 V and
fall out of it — blue worst, its Vf being highest. The part is a 5 V device
being run under spec. It is *not* leakage: leakage makes channels glow when
commanded off, and here the channels that should be strong are the weak ones.

**What to build.** Re-solder the button, and take the LED's VDD to **5 V**
instead of 3V3. The catch is the one README.md already documents: a WS2812's
logic threshold is ~0.7 × VDD, so at 5 V it wants 3.5 V on data and the S3
drives 3.3 V — the marginal case that fails as *flicker*, which is the hardest
failure here to read as wiring. Two standard ways round it, pick one and write
down which:

- a silicon diode in series with the LED's VDD (5 V − 0.7 ≈ 4.3 V, threshold
  drops to ~3.0 V, and 3.3 V data clears it) — the cheap version, usually enough
- a 74AHCT125 level shifter on the data line — the correct version

**Confirm which fault it is first**, because it costs one minute and decides
whether the rework is even the right fix. Three solids through the test bench,
watching the ring only: `#ffffff`, `#808080`, `#202020`. A WS2812 dims by PWM,
not by reducing current, so peak current per die is the same at every level —
if all three are **equally** orange it is Vf headroom and the 5 V move is the
answer. If it **neutralises as it dims**, it is rail sag instead and the fix is
a 100–470 µF cap across the ring's VDD/GND plus shorter, thicker power leads.
Then the load ladder, which tests the blue die specifically: `#0000ff`,
`#ff00ff`, `#ffffff` — blue strong alone and progressively vanishing as
channels join it is sag; blue mediocre even alone is headroom.

**The software fallback, if the hardware route is refused.** A per-channel gain
trim beside `LED_BRIGHTNESS` in [hardware.py](firmware/hardware.py) — exactly a
hardware.py-shaped constant, a property of that physical LED rather than a
preference. The honest cost: it can only attenuate, so it pulls R and G *down*
to meet B and you get neutral white at whatever brightness the starved blue
channel can manage. 5 V buys correct colour *and* full brightness; calibration
buys only the first. Do not add it before the three-level test says headroom is
not the cause.

**Definition of done.** Four clauses, of which one and a half are now met:

- ~~Button re-soldered~~ (2026-08-21, GPIO10/GPIO12) — but **pressing again is
  unconfirmed**: a real gesture has to reach the host, not a simulated one, and
  the board needs the reflash first.
- ~~`BUTTON_PIN` off the BOOT-button stand-in~~ — it is 10 now, on a
  non-strapping pin, so a reset is no longer a coin-flip on download mode.
- The three-level (`#ffffff`/`#808080`/`#202020`) and load-ladder
  (`#0000ff`/`#ff00ff`/`#ffffff`) results written down here. **Still open** -
  and now the *first* thing to do here, because everything below depends on
  what they say.
- The LED's supply recorded in [hardware.py](firmware/hardware.py)'s wiring
  block. ~~Done~~: **3V3**, deliberately, as of 2026-08-21 - see above. No
  level-shifting, because none is needed at 3V3; that is the whole point of
  the trade.
- `#ffffff` reading as white on the ring. **Still open, and knowingly so.**
  The accepted position for now is the note above: the ring runs warm, the
  onboard LED is the accurate one, and colour work is judged there.

### 8. Host the web UI on the user's server (docker / nginx / SSL)

**Do not start building before the topology is picked — it changes the shape of
the whole task.** BLE has short range and this app allows exactly one running
instance. Three shapes:

**(a) Relay.** A local process keeps BLE and the event database and opens an
*outbound* WebSocket to the server, which hosts the dashboard. Works in any
browser including iOS. The server never touches Bluetooth, so the whole
`--net=host` / BT-passthrough question disappears. **The right answer for an
always-on dashboard.**

**(b) Web Bluetooth — the browser holds the button.** Genuinely available:
Chrome/Edge desktop, Chrome Android. Requires HTTPS and a user click to open
the browser's device chooser — no silent auto-connect. Notifications work, and
the custom 128-bit UUIDs in [device.py](aibutton/device.py) are exactly what it
wants. Three consequences:

- Topology is `ESP32 ←BLE→ browser ←HTTPS→ server`; the server holds no radio,
  so there is no Docker Bluetooth story at all.
- The browser and the local service become **mutually exclusive** — the ESP32
  takes one central. The single-instance rule, stretched across two machines.
- **It fails the latency budget if the server does the thinking.** Press →
  browser → server → decision → browser → light is 100–500 ms against
  ARCHITECTURE.md's non-negotiable ≤50 ms. A server-side brain only becomes
  viable *after* the runtime moves onto the device (Phase C).

**No iOS, ever, and that closed a different question.** Safari does not
implement Web Bluetooth and every other iOS browser is WebKit underneath.
Firefox declined on desktop too. That is why ARCHITECTURE.md's "native or PWA?"
is now answered.

**The cheap first move is (b) applied to the editor, not the dashboard.**
[build_editor.py](tools/build_editor.py) already swaps `ConfigApi` for
`FileApi`; a third `BleApi` gives a page that configures the button directly
with no service and no server, and doubles as the phone app's authoring
prototype. Chrome/Android-only is a fair ask for a tinkerer's tool in a way it
is not for the everyday surface.

**Blocking prerequisite, and it is on no other list: the web UI has no
authentication.** [config.py](aibutton/config.py) says so next to `web_host`.
Hosting it publicly exposes the config editor and the whole event log. **Auth
comes before a Dockerfile, not after.**

**(d) A mesh VPN, which this item had not considered and which dominates
(a)–(c) for a single user.** Tailscale or plain WireGuard on the PC and the
phone: the UI is reachable from anywhere at a stable private address, and
**the auth prerequisite above simply does not apply, because nothing is
public**. `web_host` already defaults to `0.0.0.0`, so there is nothing to
build — it is an install and a login, not a feature.

That is worth stating plainly because this item was framed as "host the web UI
on the user's server", and hosting is the expensive way to answer "reach it
from my phone". The relay in (a) is still the right answer for *shipping* this
to other people, where a stranger cannot be asked to join your tailnet; it is
the wrong answer for one person who wants their own dashboard on their own
phone. **Cloudflare Tunnel with Access in front** is the middle option: a real
public hostname, no port forwarding, and the SSO handled at the edge rather
than by code that does not exist yet.

So: (d) now, (a) if and when this becomes a product. Auth is still owed before
anything is genuinely public.

**Once that's settled**: containerize (deps are already in
`requirements.txt`), confirm whether the target server already runs nginx +
certbot, add a docker-compose service and a reverse-proxy vhost.

### 10. Checkpoint — review and re-triage

**Last run: 2026-08-26**, at the end of the sprint that shipped **44, 45, 46,
48a, 48c, 49, 50, 51, 52a, 53** and ran the **47** read-back. It compressed
those into **Done**, rescored the gates, deleted the launcher-`targets` note
that got fixed, and created **54-68** (the read-back's findings) and **69-75**
(signals, and what the mode list is called). Decision **D10** was opened.

Previous run: 2026-08-19, which shipped **5, 9, 14, 15, 17, 19b, 26, 27, 28**,
the MIDI port dropdown, the item-23 design and **D9**, and created **31-34**.

**Nothing in either sprint has met the button.** Eleven items of host-side work
now sit between the last hardware sitting and this line.

**Next checkpoint: after the next hardware sitting.** That sitting now has
a queue worth doing in one go: **0c** (re-solder + the 5 V rework), the
Signal and control-surface walks, **26b** (does the colour coding read),
`tap_4` end to end (**28**'s residue), and the human readout test (**17**'s
residue). One session at the bench clears every open hardware residue;
checkpoint after it.

The standing job: re-read this file against what actually shipped, move
finished items to Done, prune what the shipped version superseded, and score
the roadmap's exit gates.

### 12. Look into analytics/tracking — scope first, this is vague as given

**One half is decided: it is all local.** "Nothing is extracted from the user"
is a ROADMAP principle, so the data stays on the machine, nothing phones home,
and there is no analytics vendor. That also rules out the easy Stage-5 business
model, which is better known now than later.

**Also easier than it was:** the `value` column means the log carries numbers,
and `/api/events` now filters and exports — which was the actual blocker under
any reading of (a).

What is still open is which *question* this answers. Pin down "improve
performance": (a) *habit* analytics for the user (mode usage, streaks,
time-of-day patterns — a dashboard over `EventStore`), (b) *device* telemetry
(BLE reconnect frequency, gesture-to-feedback latency, dropped presses), or
(c) *hosting* metrics once item 8 exists. **Ask which.**

### 33. `SequenceAction` — a flat list with delays

**Split out of 30b (D9 decided — see ROADMAP 3d).** A flat list of actions
with optional per-step delays. TODO **25** needs it (Mackie has no
return-to-zero, so "stop and rewind" is *Stop, Stop*). **Bounded by
construction — no loops, no conditionals, no nesting**, or it is a language
the device runtime cannot run. Decide the two edges before code: a sequence
with delays *holds the button* (presses during it follow the existing
drop-while-busy rule, and the editor hint says so), and the parser enforces a
maximum length and total duration rather than trusting the editor to.

### 34. App documents, and app-bound actions

**Split out of 30c (D9 decided — ARCHITECTURE.md "Apps own data" is the
design; this is build).** A bounded named-value document per app instance,
host-side first: storage beside the event store, slots declared per template
(the manifest's precursor), a `Set`-shaped action any mode can bind
("Smoking +1" without entering the Counter — TODO **15**), and the Counter
reading its number from its document instead of a local integer. Keep the
log separate — history and current value are different jobs. App-bound
actions are offered **only while the target app is in the list**.

### 30. Actions as a first-class idea — a pool, a taxonomy, and the data under it

**Conceptualised 2026-08-19. Design before code; the UI last.** The full
write-up is ROADMAP **3d** and decision **D9** — read those, this is the sprint
view.

**D9 is decided (2026-08-19)** — ARCHITECTURE.md "Apps own data" is the
design, ROADMAP 3d the taxonomy (System / Custom / App-bound). The build
halves are numbered: **(a) the named action pool shipped 2026-08-20 — see
Done**; (b) the `SequenceAction` is item **33**; (c) app documents and
app-bound actions are item **34**.

Nothing is left open under this number itself.

### 25. A transport app that knows what the DAW is doing

**Asked for 2026-08-19.** One gesture should mean different things depending on
what the DAW is *currently* doing:

| Gesture | Wanted |
|---|---|
| short press | record → (later) stop **and return to 00:00** → record again |
| double tap | play / pause toggle |
| triple tap | metronome on/off |
| five taps | cycle/loop on/off |

**Three of the four are already possible and need no state.** Click and Cycle
are toggles *in the DAW* — MCU note 89 and 86 flip them, so the button sends
one message and the DAW remembers. Play/pause is the same: MCU Play toggles in
most DAWs. Those three are a `control` surface today (**shipped**), and if that
is all someone wants, this item is not needed. **Only the record cycle needs
state**, because "start recording" and "stop and rewind" are different messages
that share a gesture.

**Superseded in part by item 73.** "A port the button listens on" is now its
own item, under the umbrella of **70** - so this stops being a design problem
and becomes a thin app on top of a general inbound-signal source. **Read 70
before starting this.**

**The important finding: the state does not have to be guessed.** A Mackie
Control is a *two-way* protocol - the DAW sends note-on back to the surface to
light its buttons, so a real MCU knows the transport state because the DAW told
it. Point the device's **Send To** at a port the button listens on and the same
feedback arrives here. (README currently says to leave Send To empty, which was
right when nothing listened and is now the thing to revisit.) There is also a
second, cruder source already built: MIDI clock's `0xFA`/`0xFC` are start and
stop, and `ClockListener.rolling` already tracks them.

**So the design decision is derived state versus modelled state, and derived
wins.** A local toggle ("I sent Record, so we must be recording") is correct
until somebody clicks in the DAW, and then it is silently inverted for the rest
of the session - every press doing the opposite of what the light says. Model
locally only as the fallback when no feedback port is configured, and *say so*
on the status line rather than pretending to know.

**A second finding, and it is a real gap: MCU has no "return to zero".** The
transport section is Rewind/FF/Stop/Play/Record and nothing else. In Studio One
a Stop when already stopped returns to the start, so "stop and return to 00:00"
is **Stop, Stop** - two messages from one gesture, which `MidiAction` cannot
express. That is the other thing to decide: a *sequence* action (a list of
messages with optional gaps, useful well beyond this) or a transport app that
owns the sequence internally. The sequence action is more general and is
probably right; check first whether Stop-twice is actually what S1 does,
because the whole need rests on it.

**Where it should live.** Probably not a new template - a `control` surface
plus per-gesture state is most of it. Worth asking whether this is really
"apps can hold state and choose between actions", which is TODO **23**'s (now
designed — ARCHITECTURE.md "Composition: an app's edges"; build items **31**/**32**)
composition question wearing a DAW costume. Read 23 before starting.

**Definition of done.** A short press records, and a later short press stops
and returns to zero, *driven by what the DAW reports* rather than by what the
button last sent; a session where someone clicks Stop in the DAW by hand does
not invert the button; and the no-feedback case is honest about being a guess.

### 26b. Check the launcher's colour-coding actually reads *(hardware walk)*

What is left of item 26 after the code shipped (see Done): the launcher
already colours each entry by app; if that is not landing on the real ring,
the cause may be several apps resolving to similar palette colours rather
than a missing feature. Look before rebuilding — `app_look` in main.py. The
new page colours (a control mode's LISTENING look) want the same eyeball
test in the same sitting.

### 29. Power: sleep, wake, and a hold that turns it off

**Asked for 2026-08-19**, and the largest thing on this list by some way. Three
related wants: **hold roughly 3× the normal long press to power off**, wake
again with the button, and an **auto-sleep** after idle.

**Measure before building.** There is no battery on this build and therefore no
power budget to optimise against - "saves power" cannot be checked, and an
optimisation nobody can measure is a guess that costs complexity. First number
wanted: what the board actually draws idle, advertising, and connected. This
is the item the parking lot flags as *"the one thing that might justify a
C++/NimBLE rework"*, so knowing whether MicroPython's floor is the problem
decides how big this is.

**What already exists to build on.** `GESTURE_HOLD` is **claimed and
unimplemented** in protocol v1, which is exactly the reserved wire code a
hold-level gesture wants - so "hold 3× as long" is the gesture the protocol was
already left room for. Doing it as a *level* rather than a special case also
gives every other app graded holds for free.

**What makes it hard, and it is not the sleeping.** ESP32-S3 deep sleep with
GPIO wake is well-trodden. The problems are around it:

- **Deep sleep drops the BLE connection.** The host already reconnects, but a
  button that vanishes and reappears needs the *host* to not treat that as an
  error - and needs `DEVICE_INFO` re-read on reconnect, which `BLEDevice`
  already does.
- **Waking is a press, and that press must not also mean something.** The wake
  press should be swallowed, or the first thing you do after waking is fire
  whatever short press is bound.
- **Auto-sleep must not fire mid-app.** A Pomodoro with 20 minutes left is idle
  from the button's point of view and must not sleep. The device does not know
  what app is running; the host does. So either the host says "stay awake" or
  the device's idle timer is reset by more than presses.
- **Off must be distinguishable from broken.** A button that is asleep and a
  button that has crashed look identical to a user. Whatever "off" is, it needs
  a visible confirmation on the way down.

**Split it.** This is at least three items - the hold-level gesture (cheap,
useful alone), auto-sleep on the device, and the deliberate power-off. The
first is worth doing on its own even if the rest is parked. The button went
back on 2026-08-21 (**0c**), so "wake on a button press" is testable again -
**once the board has been reflashed onto the new pins**, which is what makes a
physical press reach the host at all.

### 21. WiFi as an alternative transport ⏸ parked, with a trigger

**Decided 2026-08-18: not now. BLE is adequate, and the reason to wait is not
cost — it is that waiting makes this cheaper *and* more useful.**

**The motivation is real.** Range, and flexibility; and the S3 already has the
radio, so the BOM cost is zero and the capability is sitting there unused. That
is a genuine argument and it is why this is an item rather than a line in the
parking lot.

**What it would cost today.** A second transport in the firmware — note that
`ButtonDevice` abstracts only the *host* half, so the device half doubles with
nothing to hide behind. One shared 2.4 GHz radio, so coexistence adds jitter to
the budget ARCHITECTURE.md pins at ≤50 ms. RAM: MicroPython plus BLE plus lwIP
on an S3FH4R2 is tight. Power is the decisive one — BLE connected is
single-digit mA, WiFi associated is an order of magnitude more with 100–300 mA
bursts, which is a different battery and therefore a different enclosure
(Stage 4).

**Why later is genuinely better, not just cheaper.** ROADMAP's old reason for
parking this — "don't build a transport before deciding where the brain lives"
— has expired: **D1 is decided.** But deciding it changed what WiFi *is* here.
While the host owns the brain, WiFi is a second way to do exactly what BLE
already does, and it must coexist with a live link. After the runtime moves
onto the device, the button needs **occasional sync, not a live link** — and
periodic wake → connect → sync → sleep is precisely WiFi's good case, with no
coexistence problem because there is no live BLE session to share the radio
with. The same feature is expensive now and natural later.

**The trigger.** Revisit when any of these is true: the button must reach a
host that is not in the room (a real complaint, not a hypothetical); the
Stage-3 spike (ROADMAP **3c**) reports RAM headroom that makes it comfortable;
or Stage 4 picks a battery that can carry it.

**The shape, if it is ever built.** A **config-time either-or, never
concurrent** — one transport per boot, chosen like `--ble` is. Measure first
(3c's idle/TX current and RAM numbers), build second. Do not start with a
Dockerfile or a protocol change: the wire vocabulary is transport-agnostic
already and should stay that way.

### 18. Move project management into Notion ⏸ parked

**Deferred deliberately, not dropped.** Nothing is created in Notion and
nothing should be until the split is chosen.

**The risk is not the migration, it is ending up with two sources of truth.**
Most of this file is *reasoning*, and the fresh-session pickup property lives
in prose. Notion is not better at prose. What Notion *is* better at: status,
priority, what is in flight, sequencing, and seeing the whole thing without
scrolling.

**Decide the split before creating anything:**

- **A — Notion tracks state, TODO.md keeps reasoning.** One card per item
  (status / priority / gated-by / body-of-work), each linking to its heading
  here.
- **B — migrate wholesale**, CLAUDE.md repoints at Notion, this file becomes an
  archive.

**Recommend A**, because the fresh-session property is load-bearing and B puts
it behind a network call and an auth prompt.

**Definition of done.** The chosen split written into
[CLAUDE.md](CLAUDE.md) — one sentence saying which document a fresh session
reads for what — and the items loaded. Without that sentence this is just a
second backlog.

### 19. The light as a language — sequencer, one-offs, and where colour is edited

Part (a), the subdivision ladder, shipped — see **Done**. **b and c are done
too**; this item is closed, and what is below is the record of what it decided.

#### b) The sequencer — a stop list, and one-offs — **core shipped 2026-08-19**

The Python half is in: [sequencer.py](aibutton/sequencer.py) (a pure leaf —
`Stop`/`Sequence`/`plan_at`, table-tested), a `stops` key parsing anywhere a
*look* parses (per-stop fallback; the system palette stays plain effects,
because palette entries ship to the device), `as_dict` round-tripping, and a
driver in `main.set_led` that walks the planner and pushes each step as a
plain solid — cancelled by the next `set_led`, so a sequence lasts exactly as
long as an ephemeral effect. `repeat: false` is the play-once mode; a
finished one-shot falls back to the palette (`set_led(state, None)`), which
is what makes it the readout primitive **15**/**17** want.

**The floor is settled and is now a CLAUDE.md invariant**: `sequence_safe`,
applied at the same single point as `flash_safe`, floors each stop's dwell at
half the floor (a stop is one transition; a period is two). A one-shot of
≤3 stops is exempt — the confirmation-flash rule, decided rather than
inherited. The ladder was **not** unified with it: a ladder tick floors at
the *full* period and a stop's dwell at *half*, different multiples for
different shapes, so sharing the constant would have changed one behaviour
rather than deduplicating code. Both docstrings say so.

**The UI half shipped the same day.** The colour engine edits stop lists
(`allowSequence`, opt-in — on for the named-look pool and the mode page's
inline pool editor, off by construction for the system palette, whose
entries ship to the device); `describeEffect` and ledPreview's `colorAt`
both know the shape, so a sequence look summarises and animates correctly
in every swatch, with fades quantised to the same 50 ms steps the host
pushes — the preview keeps its never-disagree-with-hardware rule, except
that a one-shot previews looping, because a swatch that goes dark looks
broken.

**The animated device-side preview shipped in 41.** It needed no
cancellable task in webui.py after all - mirroring main.py's driver there
would have been a second flash-floor gate. `WebContext.show_look` is main's
own `set_led`, which already owns both the task and `sequence_safe`; with no
driver attached the endpoint still degrades to the first stop and says so.

**15 and 17 are now unblocked; Simon-says (16's parked half) too.**

#### c) Reuse the ramp widget wherever a gradient makes sense — **shipped 2026-08-23**

Pomodoro was the only real candidate and it cost what this item predicted: a
template field, plus the repainting tick `run_pomodoro` did not have. Hot/cold
and reaction already offered a ramp and already walked it; the countdown's is
where the pattern came from. Nothing else has a fraction to ramp over — hold
levels still need `GESTURE_HOLD` (item **29**).

**The ramp is empty by default here**, unlike the countdown's, and that is the
decision worth keeping: this template says work-versus-rest *with colour*, and
a ramp overrides both states. The rule is in [CLAUDE.md](CLAUDE.md).

**The tick turned out to be worth more than the field.** A drive needs an app
that knows the number *and* repaints often enough for it to move, so the tick
is what let `pomodoro` join `DRIVE_TEMPLATES["progress"]` — and a named stop
list is chosen per state, so WORKING can be driven while RESTING keeps a plain
colour. That is the better answer for this template, and the ramp is the
one-field version of it.

Progress is through the **current block**, not the session (a classic Pomodoro
has no end), so it resets at every phase change and `extend` grows the
denominator along with the deadline.

---

## Smaller, worth doing

- **The launcher offers Alarm modes and `enter_mode` does not.**
  `launcher_targets` filters on `TAKEOVER_BEHAVIORS`, which includes
  `AlarmBehavior`, so a scheduled alarm shows up in the launcher menu and can be
  started by hand; the `enter_mode` target picker in schema.js filters on
  `startedBy: 'gesture'` and excludes it. `ReminderBehavior` is in neither,
  being absent from `TAKEOVER_BEHAVIORS` entirely. Either one of the two filters
  is wrong or the difference is deliberate and wants writing down — it is
  currently neither. Found 2026-08-22.

- **Presses dropped while busy.** The loop runs one action at a time and
  discards presses during the 2 s SUCCESS display. Deliberate, but it makes
  fast repeated taps feel dead — worth revisiting if it grates in daily use.
  (Relevant to 12b if "performance" means device latency.)
- **Sound design** *(firmware)* — review "Smart Button Sound Design Research"
  (Obsidian) and replace the placeholder tone tables carried over from the Pi
  build. A matching sound palette, pushed the way the LED palette is, is the
  obvious shape.
- **The service is not always under the tray.** Started from a terminal it
  works identically (the panel polls `/api/status`, not the process table), but
  the panel's Start/Stop won't own it. Worth knowing when debugging.
- **The apps count is eleven now, not ten.** The control surface is a new
  takeover template (see Done), so ROADMAP's "10 apps" gate is met with one to
  spare — but the new one has the same status the other three had: **it has
  never met the button.** It is host-side dispatch with no clock in it, so the
  risk is low, but the offline editor looked built too.
- **`readout` inside a control surface is not wired.** The action is
  ambient-only: `run_control` hands actions to the generic `execute()`,
  which does not know it, and a page's `resting()` repaint would cancel the
  sequence anyway — wiring it means the page lending its light to the
  readout and taking it back. Do it when someone actually binds one there;
  the failure today is a visible action error, not a silent wrong thing.

## Parking lot (deliberately later)

- **48b. Nesting the config format: apps over items.** ⏸ Considered and
  parked 2026-08-25, **on a measurement rather than a preference** - and the
  measurement contradicted this file's own triage of it a day earlier.

  The idea: `modes` stops being a flat list and becomes apps, each holding its
  items, so five alarms are one Alarm app with five alarms in it.

  **Every runtime consumer of `modes` is flat** - all nine. `bound_triggers`
  scans, `rules.resolve` walks in priority order, `due_alarm` scans,
  `launcher_targets` filters, `enter_mode` resolves `m.name == target` twice.
  Nesting would be flattened again at every one of those sites, because the
  grouping answers an authoring question the runtime never asks.

  **The migration driver named in triage does not exist.** "A target becomes
  app+item, so every `config.json`, scene and pool action needs rewriting" is
  true only if targets are made *structural*. Item names are already globally
  unique - that is how `enter_mode` resolves today - so with resolution left as
  a name lookup, nothing needs rewriting. The expensive half was self-inflicted.

  **Cost if done anyway:** `_parse_mode` (139 lines) and `_parse_modes` (62)
  restructured, `_mode_to_dict`, `scenes.py`'s merge (a scene layers a `modes`
  list), the migration ladder plus a rung, `model.modes` throughout the editor
  JS, 25 test files. **Runtime benefit: none.**

  **What the ask wanted is already shipped.** "Several alarms from one alarm
  app, not several alarm apps" is **48a** (the list groups by app) plus **49**
  (one card, "+ Add another", copies underneath) plus **48c** (the item's page
  names its app). Those cost no format change.

  **The trigger to reopen it: the first thing that needs genuinely app-level
  state** - a setting shared by every alarm that no single alarm can own.
  There is none today, and adding the container before there are contents is
  how a config format grows a level nobody uses. Reopen with that setting as
  the reason, and the cost above as the budget.

- Battery + deep sleep — the one thing that might justify a C++/NimBLE rework.
  **Now written up as item 29**, which was asked for directly; this line stays
  because the *battery* half is still parked and 29 says to measure first.
- Offline buffering of presses while disconnected (needs a time sync)
- WiFi transport, which would remove the host-must-be-awake constraint (and
  would change the calculus on item 8)
- Phone app over the existing REST API
- A second control surface (an MCP server over the store and config was the
  original Phase 4). Dropped for now: the web UI and the `webhook` action cover
  what the button is actually for. Revisit if something concrete wants to read
  the event log or drive the button programmatically.
- **Recorded/translated communication mode.** Grew out of the Morse code logger
  idea (item 7): instead of one gesture = one symbol logged immediately, a
  takeover mode with three phases — *listen* (record a whole sequence of
  presses and the gaps between them), *translate* (decode once something
  signals you're done — a distinct gesture, or trailing silence), *read back*
  (surface the decoded text — no display, so the LED blinking it out and/or a
  buzzer pattern and/or the web UI's status line). Needs spec'ing: what
  encoding the listen phase decodes (Morse is the obvious default, not the only
  option), what commits a recording, and whether read-back can lean on the web
  UI. Prototype the decode logic host-side and pure, the way `rules.py` and
  `trigger.py` already are, before wiring it into a takeover loop. The stretch
  goal is real communication: **button-to-button** (a real architecture change
  — today one host owns one button, so two buttons talking needs either a
  shared server or a host that can peer with another host) or **actual SMS**
  (much cheaper — once the listen phase has decoded text, sending it is the
  existing `webhook` action pointed at a texting API). Scope the logging-only
  version first.

---

## Done

Compressed to the decisions that still bind. Where a rule governs future code
it lives in [CLAUDE.md](CLAUDE.md) and is not repeated here.

- ~~**A named look built from a preset arrived empty**~~ - 2026-08-26.
  Reported as "it always defaults to selecting single colour, which removes the
  other colours in a sequence, and they don't come back".

  **`modeEditor.js` read `preset.effect`, and most presets do not have one.**
  105 of the 142 look presets are sequence-only and carry `stops` instead, so
  `.effect` was `undefined`, `_addLook` spread it into `{}`, and the new look
  was genuinely empty - which is why the editor showed *single colour* (an
  empty object has no stops) and why the colours never came back (they had
  never been copied anywhere). It now goes through `presetLook`, which is
  `sequence || effect` **deep-copied** - and the copy matters as much as the
  fallback, because handing over the preset's own object would have shared its
  stops array with the module-level table and let editing your look rewrite the
  preset for the rest of the session. Every other preset consumer in the app
  already used that helper; this was the one that did not.

  **Merely looking at an existing sequence never corrupted it** - checked
  against the real component, which mutates nothing on mount. The damage was
  only ever at the moment of creating one from the dropdown, which is why it
  read as "always".

  The destructive toggle underneath it was **76**, fixed below.

- ~~**76. Switching a look to "single colour" destroyed it, silently**~~ -
  2026-08-26. `switchShape` in
  [colorEngine.js](aibutton/web/static/colorEngine.js) `delete`d every key on
  a flip with nothing kept, so one accidental click on *Single colour*
  discarded a stop list you had spent ten minutes on, with no confirmation and
  nothing to recover from.

  **Fixed by parking, not by asking.** Each shape now parks the exact fields
  it is leaving in the widget's own closure - never written to the model, so
  it costs the saved config nothing - and a flip back restores them rather
  than rebuilding from the one carried colour. Only the first flip into a
  shape (nothing parked yet) falls back to that reconstruction, same as
  before. A confirm dialog would have been noise for the direction that loses
  nothing; parking fixes the direction that does.

- ~~**69. The mode list needed to fold**~~ - 2026-08-26. With eleven modes the
  side panel ran longer than the screen, and the group you were not working in
  was pure scrolling. Each group's title in
  [menu.js](aibutton/web/static/menu.js) is a button now; a click folds that
  group's body, remembered per browser via `nav-fold:<nature>` in
  [prefs.js](aibutton/web/static/prefs.js) - a view preference, so it costs
  `config.json` nothing and does not survive to a scene.

  **The item's second complaint - Alarm and its kind listed twice - is
  deliberately untouched.** That is **48a** working as designed, and the real
  fix is **75**'s taxonomy; folding was named as the cheap mitigation for it
  and nothing more, so 75 keeps whatever it still has to say.

- ~~**56. The App page led with a warning a novice could not act on**~~ -
  2026-08-26. "4 installed apps have nothing that can reach them" sat above
  every app in [menu.js](aibutton/web/static/menu.js)'s `_renderAppsSection` -
  the best line on the page for a tinkerer, a wall of alarm for someone who
  had installed one thing.

  **Deleted, not moved.** The diagnosis it was aggregating already sits beside
  the app it is about: the "Unreachable" pill on the card (`_appStatus`) and,
  per copy, exactly why (`_howReached`, "nothing opens it - bind a gesture to
  ‘Launch an app’…"). The count was reporting nothing those two did not already
  say, one level up and with less specificity. The dangling-target warning
  stays - it names a gesture pointing at an app that does not exist, which has
  no card to sit beside and is directly actionable ("Install it below").

- ~~**57. Nothing said what a press would do right now**~~ - 2026-08-26. The
  nav's live dot already knew - `active_modes` from `/api/status`, the same
  ambient resolution the dot's hover title used - but seeing it meant hovering
  a dot in a list you might not have open.

  **A line under the header's "Last: …"** (`aibutton/web/index.html`) now says
  it without being asked: `Right now: short press → Coffee count · long press
  → Focus`, one entry per bound gesture, in `GESTURES` order. No backend
  change - `active_modes` already carried exactly this, one poll away.

- ~~**55, 63, 64, 68 - four small read-back fixes**~~ - 2026-08-26, a
  low-hanging-fruit pass done on Sonnet between sessions.

  - **55.** Header no longer counts modes - "11 modes" was the one number
    nobody could act on, left over from the vocabulary item 46 retired.
    Dropped rather than recomputed, since nothing needed the exact split.
  - **63.** The flash floor's readout says `Floor: 0.30s (3.3 flashes/sec)`
    now (`schema.js`) - the word was previously only in tinker-tier help text,
    for the one setting that is *honoured and warned about* rather than
    clamped.
  - **64.** The Web server settings group carries a line pointing at `/api/`
    and webui.py's own docstring for the endpoint list - zero mentions of the
    REST API existed anywhere in the UI before. Gated the same as the rest of
    that group (Tinker-tier): the fields it sits beside already are, and one
    visibility rule beat a special case for one paragraph.
  - **68.** `DeviceInfo.names_absent` (`device.py`) mirrors `.names` - what a
    device does *not* claim, from the same `CAPABILITY_NAMES` table, so no
    second list to drift. `/api/status` carries it as `capabilities_absent`
    and the header shows `(missing: …)` when non-empty - the half that
    decides whether a developer's feature will work, previously invisible.

- ~~**54. The Lights tab opened five colour editors at once**~~ - 2026-08-26.
  The named-look pool got a collapsed row years ago for exactly this reason;
  the five system states still rendered fully expanded, the same problem in
  the first place a novice lands.

  `_renderStateRow` (`menu.js`) mirrors `_renderLookEntry` exactly - swatch,
  name, summary, one **Edit**/**Done** toggle, one open at a time
  (`_expandedState`) - minus Duplicate/Delete, which a fixed system state
  does not have.

- ~~**59. There was no way to see the JSON**~~ - 2026-08-26. Export downloads
  a scene and Import replaces one; neither answers "what does this control
  actually write" without leaving the page.

  A **View raw JSON** toggle on the Device tab (`_renderRawJson`, `menu.js`)
  shows the working copy as formatted, read-only JSON, plus **Copy**. Nothing
  new to load - it stringifies `this.model`, the same object every other
  control already edits.

- ~~**61. The named-action pool was invisible until you knew it existed**~~ -
  2026-08-26. An empty picker under a gesture's "Use a named action" described
  in prose where the pool was, on a page that already scrolled.

  A **Make one** button (`modeEditor.js`'s `_namedActionField`) creates a pool
  entry and points the gesture at it in one click, through the same
  `_addAction` the pool's own "+ Add" button now calls
  ([menu.js](aibutton/web/static/menu.js)) - one path to a new entry, not two.

- ~~**A control surface's DAW commands appeared wiped on reload**~~ -
  2026-08-26. Reported as settings that "save and appear to update the button
  but when I re-open the page, the settings appear wiped".

  **Nothing was ever wiped, and no config on disk was damaged** - the notes,
  channels and ports were correct the whole time. `daw_command` is a *preset
  inserter*: it fills in the real fields and is deliberately not round-tripped,
  which is the right lifetime for "this is how the number got there". But the
  widget recovered its selection only by reading that dropped key, and **every
  raw MIDI field is Tinker-tier and hidden** - so after any save the dropdown
  was the only control on screen for that gesture, and it reverted to
  "- start from… -" while the button went on sending the right note.

  Fixed by making the preset recognisable again from what it wrote: a `derive`
  hook on the field spec, pointed at `dawCommandFor` - the reverse lookup
  `describe()` had been using all along to show "Play" beside note 94.

  **The MIDI numbers were also doubted and are correct.** The MCU table is
  internally consistent, has no duplicate note numbers across 60+ entries, and
  every gesture's label matches its own number. The doubt was almost certainly
  caused by this bug: with the labels blanked there was no way to confirm at a
  glance what each gesture sent. If a DAW still ignores a command, README's
  note applies - the port has to be added as a **Mackie Control**, not as a
  new keyboard.

- ~~**47. Read the menu back from three points of view**~~ - 2026-08-26. Three
  personas walked the finished shell. **Fifteen improvements are items 54-68**;
  what follows is only what got fixed on the way.

  **Three dead ends, and the third had been live for seven hours.**

  - **A curated launcher menu could not survive being looked at.** `targets` is
    a textarea, so the editor writes a string; `_parse_launcher_body` accepted
    only a list, so opening a launcher in the web UI and saving reverted it to
    "offer every app" - error in the log, nothing in the UI. `cues` had taken
    both shapes since 52a *and said so in a comment pointing at this bug*.
    Now a rule in CLAUDE.md rather than a comment.
  - **A heading with nothing under it.** All three "Web server" settings are
    tinker-tier, so a basic user got the title and blank space. A group is now
    tinker-tier when every field in it is - derived from the specs, so a group
    that gains a basic field starts showing again on its own.
  - **A ringing alarm could be seen and not acted on.** The badge pulses red,
    the only presses live behind a toggle labelled *Test panel*, and the button
    was disconnected - so there was nothing in the room to press either. Found
    with a real alarm that had been ringing since 07:00. There is a **Dismiss**
    button in the header now, shown for `ALARMING` and nothing else: any press
    dismisses an alarm, so it is an ordinary short press rather than a new
    endpoint. Every other takeover is something you chose to open and can leave
    with a long press, and a page-wide "get me out" would compete with the
    button itself.

  Also fixed, found by the suite rather than the walk: the **5AM alarm preset
  was unsaveable**. It hand-listed its fields and predated `grace_minutes`, so
  the editor's own check refused it the moment it was added. It spreads the
  template defaults now, like every other preset.

  **What it did not cover, deliberately:** touch targets. 42 already settled
  that they need a hand and a real phone.

- ~~**53. The Events page grows sub-tabs and charts**~~ - 2026-08-26. The table
  keeps its place as the default view and gains three sibling pages - Overview
  & Activity, Mode & Time, Patterns & Metrics - carrying nine charts. Verified
  against the live log (380 rows): zero overflow at 375 and 1280, every view.

  **The two decisions the item pre-answered held.** No library: every chart is
  hand-rolled, no build step, no runtime dependency. Aggregation is client-side
  and there are no new endpoints - the same grouping logic in Python *and*
  JavaScript would be a mirrored table with no test behind it.

  **The open question is answered: the offline editor gets none of it.** It has
  no service and therefore no events, so `eventCharts.js` is simply not in
  build_editor's entry list - the seam `sidepane.js` already sits on. Verified
  by serving the bundle and driving it.

  **Mostly not SVG, which is where this departs from the item's own
  recommendation.** Text inside a `viewBox` scales with the box, so an 11px
  label is 6px on a phone - unreadable rather than overflowing, which no
  measurement catches. Rule now in CLAUDE.md.

  **Two things the data would have got wrong**, both now pinned by tests:
  summing `timer_stop` *and* `mode_exit` double-counts a stopwatch, and
  `toISOString().slice(0, 10)` files evening events under tomorrow for everyone
  not on UTC.

  The fetch bug the item named is fixed: `/api/events` defaults to 50, so every
  caller now states its own limit. The table draws 200 of them and says "200 of
  380 rows" when that bites.

- ~~**51. Apps with real interfaces**~~ - 2026-08-26. An app's page is the app
  now, not just its settings: what it has done sits above the knobs. **Zero
  Python** - it reads `/api/events` and the config, which is exactly the line
  the item drew.

  **Two halves.** A stopwatch shows its runs compared against each other -
  bars, best and worst, and each run's delta against the one before it. And an
  app with more than one item lists its siblings, so you move between your two
  alarms from inside the alarm. Two or more, like the nav's grouping: a row of
  chips holding only the item you are looking at says nothing.

  **Declared as data, so it is not a stopwatch feature.** Thirteen templates
  carry a `readout`, and a new app gets a history by adding four keys.
  `measure` has four values because `value` is one untyped column - and the
  reason `outcome` exists is that an alarm's 0/1 must be counted, never
  averaged into "0.86 alarms".

  **`better` is null far more often than not**, and that is the point of it
  being nullable: a tempo has no good end and neither does a countdown's
  length. Only a game declares one.

  **The exact-name filter is client-side on purpose.** `/api/events?name=` is a
  substring match - right for a search box, wrong for "this counter's rows",
  where a counter called `water` would quietly absorb `water_reminder`.

  Found while walking it: `noun + 's'` gave "presss", "guesss" and "launchs".
  One `plural()` in format.js, because a `plural` key on twelve descriptors to
  fix three of them is a field nobody reads.

- ~~**48c. The editor reads as an app and its items**~~ - 2026-08-25. The nav
  groups by app and the App page lists the copies; a mode's own page was the
  last screen still calling one of them a mode. Its head now names the app
  (ALARM, INTERVALS) and the name field says what it is naming.

  **Delete says the item's name, not its kind.** "Delete this alarm" was fine
  and "Delete this intervals" and "Delete this hot / cold" were not - a label
  built from a template name has to survive every template. `Delete "Wake up"`
  survives all twelve and says exactly what is about to go.

  Vocabulary only. No data changed, which is the whole point of it being
  separable from **48b**.

- ~~**44. Dead man's switch - an alarm that acts when you *don't* answer**~~ -
  2026-08-25. Two fields on `AlarmBehavior`: `grace_minutes` and `on_timeout`.
  With no grace period it is today's alarm, byte for byte - the switch is
  opt-in, and a test pins that.

  **The mechanism was already next door, inverted.** `run_reminder`'s timeout
  branch says a timeout is not a clear, *because nobody saw it*; this is that
  sentence turned around - nobody saw it, so tell someone. It hangs off the
  alarm rather than the reminder because the alarm **insists** (it loops, it
  snoozes) where a reminder gives up.

  **A preset, not a template**, which is the whole point: the alarm already
  rings and already waits, so the switch is two fields. What the preset buys is
  **findability** - nobody looking for a dead man's switch would think to open
  an alarm and read its fields.

  **`on_timeout` is a binding, not a field.** There is no `kind: 'action'`
  widget and there should not be one: an action bound to something that is not
  a press is exactly what a hook already is, so it reuses that sub-editor
  through a new **`bindings`** key on the descriptor. It offers `HOOK_ACTIONS`
  only - `enter_mode`, `readout` and `standby` change what the mode loop does
  next, and there is no loop left to change once the alarm has given up.

  **Every outcome is logged, not just the dismissal.** `dismiss_event` now
  writes `value: 1` when answered and `value: 0` when not - same event name,
  both outcomes, one place to look. A switch that fires while nobody is
  watching is only worth having if the record says what happened.

  **It depends on this host being awake and its whole point is firing while
  nobody is watching.** Service stops, machine sleeps, Bluetooth drops - it
  does not fire, and cannot know it did not. Said plainly in the editor hint,
  commented at the dataclass, and the reason for the logging above. *It is a
  nudge, not a safety device.*

  Verified through `main.run` with the clock parked on the alarm's minute:
  answered runs nothing, unanswered runs the action, it stops ringing once it
  has given up, and `grace_minutes: 0` still rings forever.
  [test_dead_man_switch.py](tests/test_dead_man_switch.py).

- ~~**52a. A light show app**~~ - 2026-08-25. A playlist of named looks,
  walked on a clock. Short press is the next cue, **double tap holds** it on
  the one you liked, long press leaves.

  **Why it earned a template rather than a preset**, which was the first thing
  triage checked: everything else about a show is already data - a look can be
  a stop list, and a stop list already fades, holds and loops. What no existing
  template can do is **advance on its own**. A Signal light waits for a press;
  a look, however long, is one look. The clock is the only new thing, and the
  clock is the code.

  **A cue names a look; it never carries one** - the opposite of a Signal
  position, for the opposite reason. A position is a status you invented and
  nothing else could mean it, so it carries its colour inline. A cue wants the
  *rich* form, which only exists in the pool, and naming one means retuning
  "Ember" retunes every show using it.

  **It owns no `LEDState`**: each cue is pushed as an ephemeral effect over
  LISTENING, exactly as a Signal position is, so the whole app cost **no wire
  code** and stores nothing on the device.

  **The dwell has a floor of its own (1s), and needed one.** `sequence_safe`
  governs how fast a look flashes *inside itself*; nothing watched how fast the
  show swaps between looks, so a `dwell_s: 0.05` would have been a strobe the
  existing guard could not see.

  **Verified against a real run loop**, not just the dataclass: enters on the
  first cue, short press advances, **advances on the clock with no press**,
  double tap holds it through a full dwell, long press returns to IDLE, and an
  empty show reports an error instead of spinning. [test_lightshow.py](tests/test_lightshow.py)
  covers the same six plus the parser rules.

  **(b), per-pixel ring patterns, remains a proposal** and is unchanged by
  this: the ring is still one lamp, and (a) is what says whether it needs to
  stop being one.

- ~~**50. A colour on the app pickers**~~ - 2026-08-25. "Launch an app" is a
  button and a list of buttons now, not a `<select>`: each option carries the
  same live swatch the nav and the App page paint, plus what that app does.
  A `<select>` could never do it - an `<option>` holds text, and the half of a
  look that identifies it is the **movement**. "The slow blue one" is how
  anyone actually refers to a mode.

  **A widget kind (`modeSelect`), not a special case in the picker**, because
  capability is declared as data here: anything that comes to pick a mode asks
  for that kind and gets the swatch. The options are real buttons, so Tab and
  Enter work without a listbox implementation; Escape closes and hands focus
  back.

  **`modeLook` moved into [schema.js](aibutton/web/static/schema.js)** and the
  nav's private copy became a call to it - three places now answer "what
  colour does this run in?" with one function, which is the rule the colour
  engine already sets. A target naming a mode that no longer exists shows as
  **"(missing)"** in amber rather than as unset, because the parser warns
  about exactly that and the editor must not disagree with it.

  **Fixed while here, and it was a live bug**: 48a made `navButtons` a list of
  rows per mode, and the rename handler still treated it as one row - typing in
  a mode's name threw. Each row now also remembers *which line it shows*, so a
  rename cannot swap a Reflex row's trigger for a template summary.

  **The web UI's own assets are served `no-store`.** There is no build step and
  no hashed filenames, so an edited module keeps its URL - and a browser that
  caches it runs last week's editor against this week's service. An ES module
  graph is cached per URL, so a reload will not shift it, which makes the
  failure look exactly like the edit not having happened. It cost real time
  twice in one session. Needs a service restart to take effect.

  **Not done, deliberately:** the launcher's target list. It is a textarea of
  free-typed names, and turning it into a multi-select is a different job from
  putting a colour on a picker.

- ~~**49. An App management page**~~ - 2026-08-25. A fourth destination
  listing every app as **Available**, **Installed** or **Unreachable**, with
  each installed copy showing *how* it is reached ("Triple tap → Home", "at
  07:00 Mon-Fri") or what to do if it is not.

  **Reachability is a walk, not a filter, and that is the whole value.** Roots
  are the things nobody has to start - a gesture map is live by definition, a
  clock starts its own apps - and everything else is reachable only by being
  pointed at. It is **transitive**, because a launcher you cannot open cannot
  open anything either. `reachableModes` is pure over data
  ([schema.js](aibutton/web/static/schema.js)), so it is the same kind of
  function as `rules.py`, and it resolves **named actions** on the way -
  `findEntryPoints` never did, so a gesture holding a pool entry read as going
  nowhere.

  **It found four real faults in the live config the moment it rendered**:
  Counter, Metronome, Intervals and Reaction stranded with nothing able to
  open them, and a long press pointing at a "Launcher" that does not exist.
  That is the case for the page in one screenshot - none of it is visible from
  any single mode's card.

  **Installing a launcher nobody can open fixes nothing, and the page says
  so.** Verified both ways: install it and the four stay stranded; point one
  gesture at it and all four flip to reachable as the walk runs through it.

  **Two verbs under the mode list, not one.** "+ Add mode" became **"+ Add
  reflex"** and **"Manage apps →"**, because writing a gesture map and choosing
  between twelve apps are not the same act. The ready-made picker went with it:
  its fourteen presets are now what **Install** offers, so choosing an app and
  choosing which *kind* of it you want stopped being two controls in two
  places.

  **The offline editor got the page too, rather than a second code path.**
  Removing the picker had quietly left it with no way to add an app at all -
  the mount is optional, and it was resolving to nothing. It now has the panel,
  the tab, and the `button:show-panel` listener that makes "Manage apps"
  more than a dead button there.

- ~~**48a. Alarms stop looking like five apps**~~ - 2026-08-25. Presentation
  only: no `config.py`, no `main.py`, no wire. Two alarms now read as
  **"Alarm (2)"** with both nested under it, and grouping starts at two -
  a header over a single child doubles the list to say nothing, and one
  stopwatch really is one stopwatch.

  **A mode may be listed twice, and that is the point.** The two groups
  stopped being boxes a mode falls into and became two questions - *what
  wakes the button up*, *what can it run* - so an alarm answers both and
  appears under both. `startedBy: 'schedule'` is the test rather than a list
  of templates, because it is already the descriptor's answer to "does a
  person start this?", so a new clock-started template joins the Reflexes list
  with no edit to the nav.

  **The two listings must not read identically**, or the second looks like a
  duplicate rather than a second answer: the Reflex row shows the *trigger*
  ("at 07:00 Mon-Fri"), the Apps row shows the template summary.

  **Reflexes is two sections, because only one of them is a queue.** A gesture
  map is read top-to-bottom, first match wins, and its order is a setting the
  blurb tells you to use. A scheduled app's position means nothing. Run
  together they read as one priority list and someone would reasonably drag an
  alarm up the page expecting it to matter - so anything a clock owns sits
  below its own **"On a schedule"** label, and the blurb now says so. *The
  blurb was the bug: it promised priority ordering over a list that had just
  stopped being one.*

  `navButtons` maps a mode to a **list** of rows, not one row. Both consumers
  walk it; with a bare entry the second row silently replaced the first and
  only one of a mode's two rows ever lit its live dot.

- ~~**45. The modes list is the side panel; the page opens on Events**~~ -
  2026-08-25. The tab bar is gone. The side panel is the whole navigation -
  Events, Lights, Device, then every mode under **Reflexes** and **Apps** -
  and the main pane shows whichever one you picked. **One nav, not two**: the
  mode list used to be a second 250px nav *inside* one of four tabs, so
  reaching a mode was two choices and the list vanished the moment you looked
  at anything else.

  **`mounts.nav` is optional, and that is what keeps the offline editor
  alive** - with nowhere to put the nav it renders inside the panel exactly as
  before. `menu.js` **asks** the shell to show the modes panel
  (`button:show-panel`) rather than reaching for its tab state; rule in
  [CLAUDE.md](CLAUDE.md).

  **The test panel is a popover** hanging off the header, not remembered
  between loads - appearing unasked is the column it replaced. Closes on
  Escape, the toggle, or a click outside; clicks *inside* keep it up, because
  pressing the simulated button four times running is the main thing anyone
  does in there.

  **The narrow layout was rebuilt, and the bug it had was invisible.** Stacked,
  the fixed-height frame gave the work surface zero height - nothing
  overflowed, so 42's measurement passed while the page rendered empty. Below
  900px the shell is a scrolling document now. The override that fixed it
  *also* failed silently first, sitting above `.tab-panel { position:
  absolute }` at equal specificity - the second time this stylesheet has lost
  that argument. Both rules are in CLAUDE.md.

  Left for **47**: the Actions pool still sits at the foot of the mode page
  rather than having a destination of its own, which is a thing to look at
  once someone reads the nav cold.

- ~~**46. What the two kinds of mode are called**~~ - 2026-08-25.
  **Takeover → App, Everyday → Reflex.** Half of it was decided elsewhere
  already: the product line is "a button that runs swappable apps", so using
  the word now avoids renaming twice. The other group needed a word for
  *always on, fires instantly, never seizes the button* - a reflex fires
  without thinking, an app takes over. Rejected: **Hotkeys / Apps** (no
  flair), **Daemons / Apps** (accurate, asks too much of someone who has never
  met the word). The `enter_mode` action reads **"Launch an app"** and
  describes as `Launch “X”`, which is what makes the group name land - the
  gesture that starts one now says the same word the group does.

  **The copy changed and no token did.** `nature: 'takeover'`, the dataclass
  names, `TAKEOVER_BEHAVIORS`, the config key `modes` and the wire are
  untouched, so the mirrored-table tests were never in play; comments and
  docstrings keep the old words where they describe code. Files:
  `schema.js`, `menu.js`, `modeEditor.js`, README, MANUAL.

  **"Mode" survives as the umbrella noun** in generic chrome - Add mode, Mode
  name, Delete mode - because a reflex and an app are two kinds of one config
  object and the key is literally `modes`. Whether the umbrella needs its own
  word is a question for **45**, which replaces the tab bar that carries it.

- ~~**41. The colour menus say what the button will actually do**~~ -
  2026-08-23. Seven reports from using it, one cause under most of them: the
  Lights tab was describing the *palette entry* while the button wore the
  *named look*, so a working feature read as broken. The runtime was right
  throughout (`look_for` resolved it; a test now drives it end to end).

  **A named look is an option in the Style dropdown** (`__look__`), with the
  pool picker appearing only when it is chosen and the palette entry folded
  into a "what it shows with nothing connected" drawer beneath. That removes
  the second select, and with it the divider that used to sit between a state
  and its own second setting - the thing that made that setting look like it
  belonged to the next state down. The head swatch, the summary and "Show on
  the button" all follow `shownLook()`.

  **"Show on the button" plays a sequence** instead of flashing its first
  colour. `/api/dev/led` gained no driver of its own: `WebContext.show_look`
  is main's `set_led`, which already owns the cancellable task and the
  `sequence_safe` gate. With no driver attached it degrades to the first
  colour and says so.

  **A stop lost its `style`/`period_s`** (36e). Two clocks on one light, and
  no layout could say which one you were setting; everything it expressed is
  more stops, and the eight presets that used it were rewritten as stop lists -
  Rainbow Chase is better for it. The keys parse and are ignored in silence.
  `sequence_safe` is down to one axis as a result.

  **The fade moved into the gap between the two colours it crosses**, named
  from both ends - including the first gap, which is the only place the editor
  can say that a one-shot arrives out of black and a loop out of its own last
  stop.

  **The named-look pool is a list**: swatch, name, where it is worn, and Edit /
  Duplicate / Delete, with one editor open at a time.

  **A rainbow got a saturation**, riding `color2` exactly as its brightness
  rides `color` - no wire change, `CAP_RAINBOW_SAT`, zero means full. Needs a
  reflash to show on hardware.

  **The mode list shows each mode's colour** (`_modeLook`, mirroring
  `main.app_look`); a template owning no LED state gets an empty ring.

  **One fix was not a UI fix**: a look is *asserted*, not stored on the device
  like a palette entry, so an edited look sat behind the old one until the next
  press. The tick re-asserts IDLE when its resolved look changes. That rule,
  and the rest, are in [CLAUDE.md](CLAUDE.md).

- ~~**37. A `keys` action - the button types, clicks, and runs macros**~~ -
  shipped 2026-08-23, the day it was triaged. A new action, not a template: no
  protocol change, no reflash, and it joins the named-action pool and the
  lifecycle hooks for free.

  **No dependency**, which is the `midi` precedent applied a second time:
  `user32.dll`'s `SendInput` through `ctypes` does chords and clicks, so
  Windows costs nothing to support. **There is deliberately no Linux/macOS
  backend** - uinput needs root or a udev rule and macOS needs an
  Accessibility grant, and neither belonged in this change. The action is
  absent rather than broken without one.

  **The vocabulary is declared, not passed through** ([keys.py](aibutton/keys.py)):
  modifiers, media keys, navigation, letters, digits, F1-F24. A name outside it
  is a *config* error caught at load, because "type this string" is a much
  larger promise than "press this chord" - one the parser could not bound and
  the editor could not offer a picker for. Media keys are listed first and for
  a reason: they are the only ones that work with no window focused.

  **One chord, not a sequence.** A list with delays is **33**, and `keys`
  becomes a step inside it rather than growing its own second implementation.

  **Permanently host-local**, which matters for **40**: moved to a Pi it types
  into the Pi. That is what synthesizing input means, not a bug to fix.

- ~~**32. Session summaries**~~ - 2026-08-22, on 31's exit hook. Reporting:
  pomodoro, stopwatch, counter, reaction, hotcold; the other seven return
  `None` and add no key. `summary.py` is pure and `clean` is the single
  enforcement point - *flat* means a nested value is **dropped**, not
  flattened, and non-finite floats go too (`nan` has no JSON spelling and would
  fail the whole body over one key). Over eight keys it truncates. Webhook
  precedence is identity > session > user payload. The rule enforcement cannot
  check is in [CLAUDE.md](CLAUDE.md): same keys every exit, or none at all.

- ~~**31. Lifecycle hooks - `on_enter`/`on_exit` on `Mode`**~~ - 2026-08-22.
  On `Mode`, not per behaviour, so all eleven takeovers gained them with zero
  per-template code; fired from `enter_takeover` **and `fire_alarm`**, because
  a mode reached by schedule and by gesture must not differ. Entry is spawned
  and exit awaited ([CLAUDE.md](CLAUDE.md) says why).
  `enter_mode`/`readout`/`standby` are refused as hooks - `enter_mode` on entry
  is the recursion "bounded by construction" exists to forbid. `fire_hook` is
  the fourth action dispatch site, so it resolves named actions.

- ~~**The web UI cannot simulate a four- or five-tap**~~ - 2026-08-22, and
  **not by adding two buttons**: the Press row was hard-coded markup, which is
  why it never noticed a data change, and is now generated from `GESTURES`. A
  second private copy of the table behind the "Last: ..." line had been
  rendering a real `tap_4` as its raw key. The guard asserts index.html names
  **no** gesture in markup, so hand-written buttons fail the test.

- ~~**36. One colour primitive**~~ - 2026-08-21, owed tests closed
  2026-08-22. `LOOK_PRESETS` became effect-*or*-sequence, plus `Stop.curve`, a
  style per stop (**removed again in 41** - it was two clocks on one light),
  and `drive`. **Walked versus sampled turned out to be the
  real distinction, not the unit**: `plan_at` walks and returns a wait,
  `sample_at` samples and returns none. Precedence is named stop list > ladder
  > ramp. The rules are in [CLAUDE.md](CLAUDE.md).
  **That last thread closed in 19c** (2026-08-23): `run_pomodoro` has a
  repainting tick now, so it supplies `progress` too - per state, which is
  what lets WORKING be driven while RESTING keeps a plain colour.

- ~~**35. A freshly seeded scene fails its own Check**~~ - 2026-08-22. The
  `duration` widget hard-coded `seconds <= 0` and now honours `spec.min`.
  **`log_as` went the opposite way to the one this item predicted**: the
  descriptor was right and the Python default wrong, because `run_stopwatch`
  logs unconditionally, so `""` does not log nothing - it files every unnamed
  stopwatch into one bucket. `CounterBehavior.event` carried the identical bug.
  The generalising test is that every seeded mode passes the validators the
  editor would apply - and the from-scratch seed lives in
  `tools/build_editor.py`, not `scenes.py`.

- ~~**MANUAL.md's reference tables had fallen behind**~~ - resynced
  2026-08-22, with README. One **factual** error rather than a stale count: a
  paused Pomodoro was documented as showing LISTENING, and it actually freezes
  the phase colour into `waiting_style`. §7's recipes were rebuilt rather than
  patched, because four of them taught the reader to build what the shipped
  config already does, which reads as "my button is broken".

- ~~**30a. A named action pool**~~ - 2026-08-20. `AppConfig.actions`,
  referenced from any gesture by a **bare string**, which is free by
  construction: every binding ever written is an object, so a string can only
  mean this. Resolved at *use* time. A name with nothing behind it warns and
  **keeps the reference**; a pool entry may not itself be a name, which is
  where the one-level guarantee replaces a cycle check. Rename rewrites every
  reference, delete deliberately does not. The rule is in
  [CLAUDE.md](CLAUDE.md).

- ~~**The on/off toggle's action**~~ - 2026-08-20 as `standby`, which is what
  the 5-tap gesture had been waiting for. **Ambient-only**: takeovers are
  untouched, so a scheduled alarm still rings - an alarm you set is not a thing
  a stray five-tap should cancel. Not persisted, because an "off" surviving a
  restart is a button that comes back dead with nothing on it saying why.

- ~~**17. A number you can read off one light**~~ — shipped 2026-08-19 as
  `sequencer.readout(value, tens_color, units_color)`: tens as slow pulses
  (0.5 s on / 0.35 s off), a 0.7 s group gap only when both digits have
  pulses, units quick (0.18 s / 0.18 s), zero as one dim neutral blink;
  one-shot, 0–99, every dwell clears the flash floor by construction.
  Blinks not hues, exactly as designed — it survives the ring's colour cast
  and a colourblind user, and hue stays free to mean *which thing*. **The
  human test remains**: someone who has not been told the rule reads a
  two-digit number correctly — that needs the button, same sitting as 26b.

- ~~**15. Counting without entering an app**~~ — shipped 2026-08-19. The
  `readout` action is ambient data: bind it to any gesture and it counts
  today's rows for an event and plays the number — it bypasses the SUCCESS
  flash on purpose (the readout *is* the feedback) and any next press
  cancels it, so it never holds the button. The Counter now reads its
  session number from the store (`count_today`), so counting from Home and
  continuing in the Counter agree by construction. The concurrency decision
  lives in ARCHITECTURE.md ("Composition: an app's edges"); the app-bound
  "+1 without a log row" generalisation is item **34**.

- ~~**The MIDI port dropdown**~~ (from "Smaller, worth doing") — shipped
  2026-08-19. `GET /api/midi/ports` (in and out listed separately, graceful
  when no backend), a generic `suggest:` datalist on the text widget, free
  text still first-class, offline editor degrades to the plain box by
  construction — the colour engine's optionality rule, applied again.

- ~~**26. Colour-coded Actions pages, and the launcher's fate**~~ -
  2026-08-19; the eyeball check on hardware split off as **26b**. A control
  page owns its colour at zero new code by claiming LISTENING, which made that
  the system's one **dual citizen** (see [CLAUDE.md](CLAUDE.md)). **Both
  survive:** the launcher stays the fresh-config front door because it is
  self-maintaining and a fresh config cannot know what pages its user wants.

- ~~**14. Tinker mode**~~ — shipped 2026-08-19, built exactly like Tips:
  `tier: 'tinker'` on ~36 field descriptors (default basic when absent),
  `widgets.js` marks `data-tier`, `help.js` owns the toggle and its
  localStorage flag beside Tips's. Two axes kept separate — Tips explains,
  Tinker reveals. The toggle is built at runtime beside whatever Tips button
  the shell has, because the served page and the offline editor have
  different headers and Tips is the one anchor both share. The naive-user
  gate is now unblocked. Tier judgement calls live in schema.js; argue with
  them there.

- ~~**9. Tips content, tightened**~~ — shipped 2026-08-19. Fragments, `->`
  for consequence, every fact and safety number kept — which is why the cut
  is an honest ~21%, not the 50% hoped for: the hints were already dense
  with load-bearing costs and gotchas, and shorter-than-the-facts was not on
  offer. The app's actual emoji (header indicator, `main.py` status strings)
  were out of scope and stay put pending a user decision.

- ~~**5. The floor mode is permanent, named "Home"**~~ - 2026-08-19.
  Protection is **structural, not a stored flag**: the invariant is "at least
  one Always-ambient mode exists", and the parser seeds Home whenever a config
  would violate it - so scenes are covered for free, by merging before the one
  parser. The editor refuses only the edit that would leave zero. Double tap
  enters the *launcher*, not the stopwatch: double tap is the launcher's
  gesture by rule, and no launcher binding would fail the reachability gate.

- ~~**28. Four taps**~~ — shipped 2026-08-19, and it cost exactly what
  protocol v1 promised: **nothing on the wire**. Firmware already names
  `tap_4`..`tap_9` generically, so this was a `TriggerType` member, a
  `GESTURES` entry whose hint states the honest cost (shorter taps wait
  longer), and a new drift test pinning schema.js's gesture list to
  `TriggerType`. The control surface's budget grew to five gestures — the
  five-option page the request wanted. **Not yet walked on hardware**, same
  standing as Signal and the control surface.

- ~~**27. Every slider also accepts a typed number**~~ — shipped 2026-08-19.
  `range` and `level` grew a number box bound to the same key, one shared
  `set()` path for drag and type. Out-of-range typing **clamps per
  keystroke**, matching the slider's ends — chosen so an unsafe flash period
  can never sit in config even momentarily; blur reconciles the box's text
  with the committed value. No schema change, by design: one field, richer
  widget.

- ~~**23. Composition — apps that fire actions at their edges**~~ — designed
  2026-08-19, which was the whole deliverable. ARCHITECTURE.md "Composition:
  an app's edges" settles the three layers: hooks on `Mode` (build: **31**),
  session summaries as bounded scalar dicts (build: **32**), and conditional
  flow **refused as a host feature** — "when it ends" is a hook, "when it
  crosses a threshold" is a guarded transition inside the app, and a host
  rule engine would be the scripting-language trade in different clothes.

- ~~**24. Follow the DAW's tempo - MIDI clock in**~~ - 2026-08-19. MIDI Clock
  is `0xF8` sent 24x per quarter note; the tempo is never transmitted, only
  inferred. Not MIDI Time Code, which carries position and says nothing about
  tempo. **A median, not a mean**: one late delivery on a driver thread is
  normal and a mean lets a single 15 ms straggler drag the answer; the price is
  half a window before a deliberate change is believed. Three decisions - the
  clock owns the tempo and **taps no longer set it**; silence longer than two
  beats **holds** the last tempo, because a DAW that is quit sends no `0xFC`
  and the pulses simply stop; the light re-pushes only past 0.5 BPM of
  movement. Permanently host-side: the DAW is on the host by definition.

- ~~**A control-surface template, and a DAW command picker**~~ - 2026-08-19.
  The picker offers **Mackie Control** note numbers, which is the whole value:
  a DAW told it has a Mackie Control already knows what note 94 means, so
  there is nothing to learn. The table is **JS-only and creates no mirror** -
  the action stores a number. `control` exists because neither existing shape
  worked as a remote: an ambient mode cannot be an `enter_mode` target, and a
  `signal` **cycles**, so reaching Record would pass through Play and start
  playback. Confirmation is 0.3 s rather than the ambient layer's 2 s, and
  presses during it **queue rather than drop**. Long press is unbindable and
  the parser drops it ([CLAUDE.md](CLAUDE.md)). Also caught: `BUILTIN_MODES`
  had no test at all, and the DAW preset had shipped with an invalid pair.

- ~~**22. A `midi` action**~~ - 2026-08-19, because Studio One speaks Mackie
  rather than OSC. **The dependency this item accepted turned out not to be
  installable**: `python-rtmidi` publishes no wheel for Python 3.14 and its
  source build fails here. MIDI goes out through **`winmm.dll` via ctypes**,
  which is what rtmidi calls one layer down, so the action costs **no
  dependency at all on Windows**. Three decisions: the backend is chosen **once
  at import**; the port is matched on **part of its name**, because Windows
  renames what loopMIDI creates between sessions; and the port is **opened per
  send**, because a cached handle goes stale exactly when the DAW restarts and
  fails as silence. **Left open:** nothing has confirmed Control Link learning
  a message - that bench test is all that stands between this and done.

- ~~**A drift audit, and the mirrors it found unwatched**~~ - the real finding
  was **four mirrored tables with no drift test**, in a codebase whose stated
  rule is that mirrors are tested rather than trusted; two comments in
  `schema.js` even claimed a test covered them, and it did not.
  `test_schema_mirror.py` now does. Dead code was removed, each item verified
  unreferenced repo-wide first. **Deliberately left alone, so the next sweep
  does not re-litigate them:** the reserved `OTA_CONTROL`/`GESTURE_HOLD`, the
  v0.2 `rules` and `*_minutes` migration paths (the whole point is that old
  configs keep working), and `schema.js`'s internally-used exports.

- ~~**19d/e. One colour control, and mode colour moved onto the mode**~~ -
  `colorEngine.js` is the only thing that edits a `LedEffect`, and returns the
  widget contract so it drops into any form. **The test bench was scrapped as a
  place and kept as a capability**: pushing a look at the hardware belongs to
  every picker, which is how you tell a wiring fault from a config one, and it
  is optional by construction (`api.showLook` may be absent) so the offline
  editor still works. Mode-owned palette entries stay in config as the
  invisible fallback; only the editor group went.

- ~~**The offline editor was dead on arrival**~~ - found by opening it rather
  than by a test. Two modules both wrote `paint as applySwatch`; the bundler
  emitted that binding once per module and the browser refused the entire
  script, so every module never ran and the page opened blank. Two modules
  agreeing on an alias is the normal case, so the bundler binds it once and
  raises only when one alias would mean two symbols. The gap that let it ship:
  the suite checked the bundler's *inputs*, never that the bundle it emitted
  could be parsed. **It looked built.**

- ~~**The control panel wedged, invisibly**~~ - three separate faults wearing
  one symptom. A modal parented to a *withdrawn* Tk root renders with no
  taskbar button and no focus, so the second process sat holding a dialog
  nobody could see or dismiss. The advice ("look in the tray") was
  unfollowable, because Windows files new tray icons into a hidden overflow
  flyout. And "already running" and "wedged" were indistinguishable - a second
  launch now asks the first over a loopback socket, and no answer means wedged
  and says so with the PID instead of reassuring you. The port file is
  deliberately not trusted on its own; connecting is what settles it.

- ~~**20. Pomodoro is an interval timer**~~ - generalised, so Tabata and HIIT
  are **presets costing zero Python**. **The template's `type` string stays
  `pomodoro`** (its label is "Intervals"): renaming it would have been a
  migration for every saved config in exchange for a tidier word. Seconds are
  canonical and `*_minutes` still parses, rewritten as seconds on first save so
  the migration completes itself and there is no second format to support
  forward. `rounds` and `lead_in_s` were added, both defaulting to exactly what
  a Pomodoro already did. The editor's `duration` widget came out of it.

- ~~**7. Build at least 10 modes total**~~ - Hot/Cold, Reaction and Signal
  took the count to ten. **Two are written the way Stage 3 wants every app
  written**, which was the point of doing the games first: pure
  `step(state, event, now)` over a closed effect set, with randomness passed
  *in* precisely so `step` stays checkable against a table. **Signal is the
  first app whose point is to persist rather than finish**, and it is what made
  the one-foreground-app decision visible; a status light and an OSC footswitch
  are the same machine, so they ship as two presets over one template.
  **Left open:** Signal's positions are edited as a JSON field, because there
  is no repeating-sub-form widget.

- ~~**16. Games**~~ - Hot/Cold shipped and Reaction came nearly free beside
  it, sharing the shape rather than the code. **Two things this item asserted
  turned out to be wrong, and both mattered.** A mode binding only short press
  does *not* get an instant press - every single press on every config waits
  out the window, so what saves a timing game is that the delay is a
  **constant** you subtract, read from the device because an injected press
  arrives instantly and correcting that would be the same bug backwards. And
  the host *can* know the device's rainbow phase exactly: pushing an effect
  restarts the coroutine, so phase 0 **is** the push, which makes it arithmetic
  rather than the approximation this item took it for - one radio write per
  round is the only reason the game works over a fire-and-forget link at all.
  What still stands: ±150 ms games are honest, judging a beat is Stage 3.

- ~~**An OSC action, and no dependency for it**~~ - `osc.py` is pure encoding
  over stdlib UDP, so it cost **zero new runtime dependencies**. A sibling of
  `webhook` rather than a setting on it: one is a request with an answer and a
  failure mode, the other a datagram that either leaves or does not, which is
  why the result says "sent" and never "delivered". **What OSC cannot honestly
  do is live looping** - the tap window plus the radio is 20x what punch-in
  needs. Transport, scene launch, record-arm and mute are fine; anything on the
  beat is Stage 3.

- ~~**2. Verify the takeover modes work end to end**~~ - walked eight
  templates against real hardware. **Found and fixed on the way:** Pomodoro's
  paused indicator hardcoded the global LISTENING state and so silently
  overrode whatever look the mode had chosen - LISTENING is deliberately
  global-only, so a Pomodoro could never own it. It now freezes the current
  phase's own colour into a `waiting_style` instead.

- ~~**Verified power-cycle recovery**~~ — a real USB replug mid-session
  reconnected on its own; reconnect logic was previously only exercised
  against a fake bleak.

- ~~**0a. The app launcher**~~ - one gesture reaches every app, so "load the
  button with as many apps as it will fit" is true for the first time. **The
  core rule was the actual work: replace, don't nest.** `enter_takeover` is a
  loop rather than a single dispatch - a launcher *names* what runs next, and
  its session closes before the app's opens. Chosen over a depth guard because
  with no stack there is nothing to overflow, and the event log gets one clean
  `mode_enter`/`mode_exit` pair per app instead of nested ones. **No hop limit,
  deliberately:** every handoff costs a gesture so no chain runs unattended,
  and the one shape that could - a launcher offering itself - is excluded from
  its own menu instead. It owns no `LEDState`, wearing the target's look over
  LISTENING. **The gestures were backwards on the first cut** (launch on long
  press), and the fix became the "long press means up one level" invariant.

- ~~**Rainbow brightness**~~ - `_rainbow` takes the effect colour's brightest
  channel as its HSV value; the colour bytes were *discarded* for this style
  before, so this is an addition rather than a repurpose. **Zero means full,
  and that is the whole compatibility story**: every rainbow saved earlier very
  often carried `#000000`, and reading that literally would black out existing
  configs on reflash - a rainbow rendering black is indistinguishable from the
  light being off, which nobody configures a rainbow to do.
  `CAP_RAINBOW_LEVEL` was allocated even though the wire is unchanged, because
  without it the failure is a slider that silently does nothing.

- ~~**19a. The subdivision ladder**~~ - at any moment the colour is the one on
  the **largest interval that divides the elapsed time**. Four things worth
  keeping: **parity needs no notion of parity** (a 2 s rung catches the even
  seconds and a 1 s rung whatever is left, so a 15 s rung needs no code);
  **whole milliseconds, not floats**, because `2.0 % 0.5` can land on
  0.4999999999999998 and a ladder that worked at 1 s and failed at 0.1 s is the
  worst kind of intermittent; **ticks evaluate at their nominal time**, not the
  wall time the loop woke; and **the floor applies to the cadence, not
  `period_s`** - the transitions `flash_safe` cannot see, since a `solid` never
  strobes by its own reckoning.

- ~~**11. Reminders**~~ - scheduled like an alarm, deliberately not one, with a
  test asserting the alarm template is untouched. Any press clears it; **no
  snooze**, because a postponable reminder is an alarm with extra steps; it
  gives up on its own, and a timeout logs nothing because nobody saw it. The
  scheduler was generalised rather than duplicated: what makes a mode scheduled
  is its *activation*.

- ~~**4. The flash floor, and the period slider**~~ - the answer to "3 Hz or
  4 Hz" was *neither as a constant*: it is a setting, defaulting to WCAG
  2.3.1's 3 Hz. Below the recommendation is **honoured and warned about** -
  clamping a setting silently makes it a lie, and accepting silently makes the
  hazard invisible. The `range` widget's minimum is a function of ctx, so
  raising the setting widens the slider instead of lying about what will be
  accepted. The rule is in [CLAUDE.md](CLAUDE.md).

- ~~**1. The event log, interrogable**~~ — `mode` and `value` columns, then
  `kind`/`name`/`mode`/`since`/`until` filters on `/api/events`, a CSV/JSON
  export honouring the same filters, and `/api/events/kinds` behind the picker.
  **One query behind the table and the export**, so a downloaded file cannot
  disagree with what you were looking at. `name` is a substring (you search
  "coff", you want "coffee") with LIKE's wildcards escaped; an export defaults
  to the whole log, not one page.

  Still open, if item 12 ever needs it: *which gesture* produced an event, and a
  `scene` column. Don't widen the schema on spec.

- ~~**The 5-tap gesture**~~ — `TriggerType.TAP_5` plus a `GESTURES` entry, a
  pure data change with no reflash, proved end to end against the firmware's own
  encoder. **Four taps is deliberately unnamed**: a count with no member is
  dropped rather than fired, which is right for a stray extra tap on a triple.
  Binding five costs every shorter tap its instant response — the one gesture
  whose cost is paid by the others.

- ~~**3. Named looks — a mode's colour, not the button's**~~ — a top-level
  `looks` pool referenced by name per LED state, the picker at the *top* of a
  mode's form, and the Lights tab split into the button's colours, the mode
  defaults, and the pool. A missing look costs a colour, never a mode; renaming
  rewrites references, deleting deliberately does not. The invariant is in
  CLAUDE.md. (Item **19d** finishes the job by moving mode colour out of the
  Lights tab entirely.)

- ~~**0b. Protocol v1, frozen**~~ - `DEVICE_INFO`, ephemeral effects and
  parameterised gestures shipped; `OTA_CONTROL` and `GESTURE_HOLD` claimed and
  unimplemented. **No `LEDState` was spent.** What it bought, stated as a bar
  rather than a milestone: everything on this list is now reachable **without a
  reflash**, so the bar for the next wire revision is a capability the device
  physically cannot express today. The judgement call worth remembering:
  counting to N costs a double tap its instant response, so `max_taps` is
  derived from what the config binds rather than being a setting - at 2 the
  detector is byte-for-byte the one that shipped before.

- ~~**13. Scenes**~~ - a scene is shallow-merged over `config.json` as a **raw
  dict** before `parse_config` sees it, so every existing fallback and warning
  applies to scene files with no new validation code. Startup-only keys come
  back as `needs_restart` rather than reloading cleanly and doing nothing. The
  invariants are in [CLAUDE.md](CLAUDE.md). **Left open:** the tray's `Scene >`
  submenu is unit-tested but has never been clicked (`tray.py` needs a screen,
  so the suite deliberately does not import it); and a scene saved *through the
  editor* carries the whole effective config, so it loses the "inherit what I
  don't mention" property a hand-written one keeps.

- ~~**A light test bench, and the byte-order fault it caught**~~ - it needed no
  new device method, because "show this look" is already what an ephemeral
  effect means, and it validates through the config's own parser so a colour
  the editor would reject on Save is rejected identically here. **The diagnosis
  came from pushing *known* colours, not from staring at a rainbow** - every
  permutation of a rainbow is still a rainbow, so it shows at most a direction
  reversal, and a camera's white balance will happily fake one of those.

- ~~**Colour ramps, and a countdown to prove them**~~ - colours pinned at
  fractions, blended the same way `firmware/led.py`'s `_fade` does, with a test
  that fails if the two disagree. **Positions, not durations**, so the same
  ramp serves a two-minute egg timer and a two-hour deadline. **Push on change,
  not on tick**, which bounds a full sweep to a couple of hundred writes
  whatever the duration. Ramp and effect stay separate objects. One gap found
  later: a ramp under a style that ignores colour (rainbow) is invisible, so
  the countdown stops pushing rather than sending colour into a style that
  discards it.

- ~~**The metronome can go fast, and has settings**~~ — tempo and flash rate are
  separate limits. `max_bpm` bounds the tempo and is yours to raise;
  `metronome_flash()` keeps the light legal by marking every Nth beat and saying
  so in the status line. 240 BPM is a real 240 BPM rather than a lie or a
  strobe. `max_bpm` also stops one bounced contact (two edges 20 ms apart imply
  3000 BPM) throwing the average away.

- ~~**An event can carry a number**~~ — one nullable `value REAL`, appended so
  existing positional reads keep meaning what they meant, with a test that
  attaching a value never changes what an event *counts* as.

- ~~**6. The side pane folds away**~~ — one fold of the *whole* pane rather than
  per-block disclosures. The three blocks are one thing (inspection surface) and
  someone driving a real button wants all of it gone, not two thirds.
  [prefs.js](aibutton/web/static/prefs.js) came out of it, holding the
  throw-guarded localStorage helpers (storage *raises* in private browsing and
  off `file://`), and `.header-tools` is the cluster Tinker mode joins.

- ~~**The offline editor rendered as a sliver**~~ — its layout container carried
  only `.body-split`, a class the shared stylesheet does not define, so
  `display: grid` never applied and `.tab-panels` resolved to zero height. It
  looked built, which is why it survived a look. The test asserts the invariant
  (a layout container must carry a class the stylesheet actually defines) rather
  than pixels.

- ~~**Single-instance guard**~~ — an OS-level lock on `<database_path>.lock`; a
  second copy refuses with the holder's PID and exit 1. A file lock rather than a
  PID file precisely so a crash or hard kill leaves nothing to clear by hand.
  `--no-lock` opts out.

- ~~**The run loop survives its own components**~~ — `resolve()`,
  `store.logged_today`, `due_alarm()` and the palette push all sat unguarded in
  the `while` body, so one locked-database write ended the service. The iteration
  now has a backstop that logs, drops the LED back to IDLE (a fault mid-`handle()`
  used to leave it stuck on LISTENING) and holds at tick rate rather than
  spinning. Repeat faults are throttled by `FaultTracker` — pure, so the throttle
  is tested without a clock.

- ~~**A bad event log no longer stops the button**~~ — an unopenable database
  degrades to an in-memory log with a loud error and a `degraded` flag. Writes
  get a busy timeout so a transient lock doesn't fail a press.

- ~~**Graceful shutdown on Windows**~~ — SIGTERM/SIGINT were registered behind a
  `hasattr(signal, "SIGHUP")` check, so on the host this actually runs on they
  were never wired at all. Registered separately now, falling back to
  `signal.signal` where the loop has no `add_signal_handler`; a second Ctrl+C
  restores the default handler so a wedged shutdown is still killable.

- ~~**Earlier work**~~ — Pomodoro template; the built-in modes set; hardware
  validation on an ESP32-S3 Mini; editable LED colours pushed live; the `fade`
  style mirrored across firmware and host; `WORKING`/`RESTING` added to the
  Lights tab with a drift test; mode-switching explainers with a live "active
  now" mark sourced from the host's own `resolve()`; the app-shell rewrite
  (fixed-viewport layout, tabs, side pane, master/detail mode editing, the Tips
  toggle); and the tap metronome.
