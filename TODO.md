# To-do

Stage 2 of [ROADMAP.md](ROADMAP.md) — the MVP/demo push. Anything that
reshapes the architecture (the app runtime, the one-manifest move, moving the
brain onto the device) lives in [ARCHITECTURE.md](ARCHITECTURE.md) and the
roadmap, not here. **0a** and **0c** are the exceptions: they are Stage-2 work
*because* deferring them gets expensive once more hardware exists.

A new takeover written as a state machine over `(state, event, now)` will port
to the on-device runtime; one that awaits the device directly gets rewritten.

Finished items are compressed and moved to
[TODO_FINISHED.md](TODO_FINISHED.md) — this file stays a list of what's left.

## Current hardware state

**Flashed to 0.8.0** (2026-08-29), re-soldered 2026-08-21 onto **GPIO10**
(`BUTTON_PIN`) and **GPIO12** (`NEOPIXEL_PIN`) — both plain S3 GPIOs, so
holding the button through a reset is safe again. Wiring detail is in
[firmware/hardware.py](firmware/hardware.py).

**The switch is off the board as of 2026-08-29.** The owner sat on the button,
it disconnected, and the switch was then removed and desoldered. BLE, the LED
and the host all work; a physical press does nothing, which is exactly what a
missing switch looks like — **0c** is the re-solder.

**The board's own BOOT button is a second input as of firmware 0.8.0** (TODO
**89**, flashed 2026-08-29), always on and in parallel with `BUTTON_PIN`, so
the button works with nothing soldered to it at all. In PowerShell the glob
has to be the shell's, because neither PowerShell nor mpremote expands it for
a native command:

```powershell
./.venv/Scripts/python -m mpremote cp (Get-ChildItem firmware/*.py) : + reset
```

Press it while the board is *running*, never while it starts: GPIO0 held low
at power-on is download mode.

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
- **The MIDI does not come from the button.** A gesture travels over BLE to
  the PC, and the *host* writes the note to a MIDI port - so reflashing can
  change nothing about a DAW that is not responding, and an hour spent there
  is an hour lost. (Whether it should stay that way is **80**.)

## The DAW rig, as it is set up here

Written down 2026-08-27, the day it first worked, because none of it is
guessable and all of it is needed again for **77**'s test.

- **loopMIDI port `4G3NT`** carries the button → DAW direction. Every binding
  on the *DAW Control* surface names it; blank would mean *Microsoft GS
  Wavetable Synth*, which is output 0 on this machine.
- **Studio One has that port added as a Mackie Control device**
  (Settings → External Devices → Add… → Mackie → Control, Receive From =
  `4G3NT`). This is what makes note 94 mean Play. As a *keyboard* device the
  notes arrive, appear in the MIDI monitor, record into tracks and move
  nothing - which is exactly what a broken button looks like.
- **The other direction does not exist yet**: **77**'s test needs a *second*
  loopMIDI port with the same device's **Send To** pointed at it, and a reflex
  listening on it. One cable per direction.
- The bindings, all MCU notes on channel 1: short = Record (95), double =
  Stop (93), triple = Play (94), four = Click (89), five = Loop (86).

## How to work this list

Each numbered item stands alone: context, the files involved, and a definition
of done, so it can be picked up cold. **Numbers are never reused or
renumbered** — this file, TODO_FINISHED.md, CLAUDE.md, ROADMAP.md and the
commit log all cite them, which is why the sprint starts at 0a and has gaps.
A number you're looking for and can't find here is almost always in
[TODO_FINISHED.md](TODO_FINISHED.md) or the Parking lot below.

A rule governing *future* code belongs in [CLAUDE.md](CLAUDE.md); this file
records the decision and points at it. **When an item ships with nothing left
open under its number, move its whole write-up to
[TODO_FINISHED.md](TODO_FINISHED.md) in the same commit**, compressed to the
choices that still bind. An item with any open thread — a hardware test not
yet run, a "still open" sub-question — stays here whole, even if most of it
has shipped; don't split one item across both files.

Before touching code: read [CLAUDE.md](CLAUDE.md).

**This file used to say "run the suite before and after" and no longer does.**
That line is what turned one authorised run into three in a single session, at
3.5 minutes and a slice of the budget each. The rule is now
[CLAUDE.md](CLAUDE.md)'s *"Do not run the tests without being asked"*: write
them, hand over the command, and let the person paying decide when to spend it.

```bash
./.venv/Scripts/python -m pytest -q
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
| **10 apps** verified on hardware | **eleven built.** The **control surface is verified against a real DAW** (2026-08-27, Studio One over loopMIDI, transport driven by the button). **Signal is the last one that has never met the button** |
| **A naive-user run** | not started; unblocked since **14**, and **47** is the desk-bound rehearsal for it - three personas walked the shell, three dead ends fixed, fifteen improvements as **54-68** |
| **24-hour soak** | not started. The service has now sat up for 12 h unattended and **an alarm rang for seven of them** with the button disconnected - not a soak, but the first evidence of what one would find |

**Nothing left is blocked on design** *for Stage 2*. What remains of the gates
is hardware time (**0c**, the soak, walking Signal) and one person sitting down
with the button (**14**'s naive-user run). No amount of code moves those three.

**Beyond the gates, that changed on 2026-08-29**: **90** and **97** both turn
on whether the brain moves onto the device (Stage 3) before a phone app or a
product exists, and **96** is blocked on a secret store that has not been
designed. Those are decisions, not work.

*(✔ rows are shipped in full — detail in [TODO_FINISHED.md](TODO_FINISHED.md).)*

## Six bodies of work, not twenty items

The numbered list is right for picking one item up cold and wrong for deciding
what to do next. This is the other view.

| Body of work | Items | State |
|---|---|---|
| **The colour engine** — named looks, ramps, the safety floor | 3 ✔, 4 ✔, 0b·3 ✔ | Done |
| **The light as a language** — ladder, stop list, one primitive | 19 ✔, **36** ✔, 41 ✔ | **Done.** 19c closed the last thread; nothing else has a fraction to ramp over until `GESTURE_HOLD` (**29**) |
| **The gesture engine** — N taps, hold levels | 0b·2 ✔, 28 ✔ | Taps done. Hold levels need firmware — the cheap half of **29** |
| **Composition** — hooks, session summaries | 23 ✔, **31** ✔, **32** ✔ | Done |
| **Actions as a first-class idea** | 30a ✔, 33 ✔, 34 ✔ | **Done.** The pool, the sequence and app documents with `set_value` - all three halves of **30** |
| **Reach and hosting** — launcher, ten apps, remote UI | 0a ✔, 7 ✔, **8**, **40**, 42 ✔, **43**, **90** | The page works at phone width (42); reaching it is 8(d), an install not a feature. **40**, **43** and **90** are all "where does the host live", answered differently — and **90** is the one that forces the choice |
| **Reaching the rest of the world** — integrations, credentials, polling | **96**, **99**, **100**, 93 ✔ | New 2026-08-29. **100** is the finding that reorders it: the best first integrations need no credential, so they are not blocked on **96**'s secret store |
| **Becoming a product** — security, manufacturing, the pitch | **97**, **98**, ROADMAP Stage 4/5 | New 2026-08-29, and the honest answer today is "not yet". **97** is a map with owners missing; **98** says the demo is the spec |
| **Reaching other software** — OSC, MIDI out, clock in | 22 ✔, 24 ✔, **25** | **The outbound half is proven on real hardware** (2026-08-27): the button drives Studio One's transport. **25**'s remaining half is the DAW's Send To pointed back, which is **77**'s test |
| **Saying a number** — ambient counting, count readout | 15 ✔, 17 ✔, 83 ✔, **91**, **106** | The two-digit readout works; **91** lifts the 0-99 cap and adds Morse and binary, reusing **83**'s now-shipped compiler for the Morse scheme. **106** (the hour chime) is that compiler's second caller and needs no renderer of its own |
| **Play** — timing and guessing games | 16 ✔ | Done for forgiving games; tight rhythm needs Stage 3 |
| **The light as a show** — a playlist app, and the ring itself | 52a ✔, **52b** | The show ships on today's wire and cost no wire code; per-pixel (52b) is still a proposal |
| **Getting around** — launcher, control surfaces, colour coding | 0a ✔, 26 ✔, 27 ✔, 28 ✔ | Only **26b**, an eyeball test |
| **Power** — sleep, wake, deliberate off | 104 ✔, **29**, **105** | **Half shipped, 2026-08-29.** **104** is in: a long press at the root fades the light down and stops the button answering, host-side, with schedules and reflexes still running. **29**'s device deep sleep is the other half and stays blocked on measurement; **105** decides which notices may pierce either |
| **The shell and its vocabulary** — what things are called, where they sit | 46 ✔, 45 ✔, 48c ✔, 53 ✔, 47 ✔, 54-68 ✔, 81 ✔, 82 ✔, 85 ✔, 86 ✔, 87 ✔, 88 ✔, 92 ✔, 101 ✔, 102 ✔, 103 ✔, 107 ✔ | **Done.** The imagined read-back closed with **62** and **65**; then the owner used it, and **81-88** is what that found — all shipped (**88** absorbed into **101**, which with **102** is one change: the Actions destination is what empties the Reflexes group) |
| **The app paradigm** — an app installed once, holding many items | 48a ✔, 48c ✔, 49 ✔, 50 ✔, 51 ✔ | **Done.** The list groups by app, the page reports reachability, and an app's own page is now the app (51) rather than its settings. Nesting the *format* is parked as **48b**, with the measurement that put it there |

| **Reflexes** — a circumstance, with an action attached | 70 ✔, 71 ✔, 72 ✔, 73 ✔, 74 ✔, 75 ✔, **79** | **Done bar one source, 2026-08-27.** A `reflexes` list, `POST /api/reflex/{name}`, MIDI in, a one-field test on what arrives, dispatch beside the presses, and delivery into a running app. **79** (the media keys) is the only source left, and it is optional |
| **The DAW, both ways** — the button hears what the transport is doing | 22 ✔, 24 ✔, **25**, 73 ✔, **77**, **78**, **80** | **25 stopped being a design problem when 73 landed**: MCU is two-way, so "recording" is a fact the DAW sends rather than a guess, and a signal light already follows it. **77** puts that on a control surface, **78** is the state machine, and **80** asks why a user has to install loopMIDI at all |
| **Reading it back** — what fifteen minutes as someone else turns up | 42 ✔, 47 ✔, **54-68** | The walk is done and its dead ends are fixed; the improvements are fifteen separate items, none of them blocking |

Outside the table: **0c** is hardware and gates nothing but its own
verification; **18** (Notion) is process and is parked.

*(✔ entries are shipped in full — detail in [TODO_FINISHED.md](TODO_FINISHED.md).)*

## Start here next session

**Rewritten 2026-08-29** after moving every fully-shipped item out to
[TODO_FINISHED.md](TODO_FINISHED.md). Nothing below is blocked on an
undecided question — ROADMAP D10 (a reflex is an object, not a field on a
mode) was the last one, and **70** in TODO_FINISHED.md has the reasoning if
you need it.

### The device now runs an app on its own — and it has never been flashed

**111** shipped 2026-08-30: a compiled light show runs on the ESP32 with no
host connected, and the host suite drives every part of it. What it has not
had is a board. Flashing needs the service stopped (one BLE central), so it is
a deliberate sitting rather than something to slip in: copy the four new
firmware files plus `app.pkg`, reset, stop the service, and press the button.
Everything else in 111's "what is left" is downstream of that working.

### The DAW rig comes first — it's a desk, not an editor

**77**'s code shipped; what's left is the rig test: a second loopMIDI port,
the DAW's Mackie Control **Send To** pointed at it, two reflexes on
`note 95 velocity 127 / 0` scoped to the surface, then arming record *by
clicking in Studio One* to watch the light go red. Don't start **78** (one
press meaning record-or-stop, depending on what the DAW reports) before that
test has run on real hardware — the whole design rests on MCU feedback
actually arriving, and that's never been tested here. **80** (getting off
loopMIDI entirely) waits on the same test, for the same reason: it's cheaper
to debug the protocol conversation over a cable that already works.

### Low-hanging fruit

Re-populated 2026-09-03, after a pass that shipped **109** and 111's staleness
UI. What is left here is genuinely pick-up-cold: each one is bounded, decided,
and needs no hardware.

- **95's picker** — the check is done (see the item): a theme is not usefully a
  scene, so what remains is a palette set the Lights tab can apply. A table in
  schema.js plus a row beside the system states. Two of the three themes can be
  authored today; the ring-cast one waits on **0c**.
- ~~**The `better` field on a counter**~~ **Shipped 2026-09-05**: `renderTally`
  now reads `better` exactly like `renderMeasured` does, so a counter's editor
  offers "Is one of these best?" and a `better: 'low'` counter's readout
  crowns the quietest day instead of the busiest. Deliberately *not* extended
  to every `tally` template - a launcher's tally (how many times the menu
  itself opened) has no best to crown, so only the counter offers the field;
  `test_a_tally_may_also_declare_a_best` pins that split. The frontend widget
  is unverified by an automated test (DOM-producing code, per CLAUDE.md's
  own convention for `tests/js/`) but was checked live against a running
  preview instance.
- ~~**A capability bit for standalone apps**~~ (111) — **already true, not a
  gap**: checked 2026-09-05, `CAP_APP` already answers this. Firmware sets it
  once `apppkg`/`runtime`/`standalone` import cleanly (they're unconditional
  imports in firmware/main.py as of 0.9.0, so an old build without them simply
  can't boot this main.py at all), and `webui.py`'s `/api/app` already reports
  `"supported": ctx.device.info.has(device_module.CAP_APP)`. No separate bit
  was needed because installing a package and running one standalone shipped
  as one firmware capability, not two.

### The rest, in the order I would take it

- **105** — the tier that decides what is allowed to interrupt sleep, now
  that there is a sleep to interrupt (**104** shipped 2026-08-29). Four
  ordered tiers on a Notice, `when_free` the default; nothing else changed
  underneath it, so this is the field, the waiting rule and the editor.
  **A `when_free` notice waiting for an app to exit is the part with no
  precedent** - everything else reuses 84's timeout and miss.
- **84b** — fire or log a missed Notice window on reconnect. Needs its own
  questions answered first (what counts as "offline", whether a host-only
  action already fires with no device connected) — not low-hanging fruit.
- **83 shipped 2026-09-05** (compiler, look-pool shape, a colour-ramp overlay
  across the message, and the editor widget) — **91 and 106 come next**, and
  cheaper for it: place-value colours and binary are the only two schemes
  91 still has to write, since its Morse scheme is 83's compiler called
  directly, and 106's only remaining requirement is the recurring schedule.
- **99 with 100 in front of it** — a reflex that polls a URL, built to reach
  the keyless endpoints (calendars, feeds) first since **96**'s secret store
  doesn't exist yet.
- **80** — *the button should be the MIDI port*. Waits on the DAW rig test
  above.
- **A hardware sitting** closes several threads at once: walk **Signal**
  (the one app that's never met the button), **26b**'s colour-coding
  eyeball, **0c**'s re-solder and three-level/load-ladder test, **89**'s
  open GPIO10 question, and **77**'s rig test.
- **14**'s naive-user run and the **24-hour soak** — neither has moved in
  several sprints, and no amount of code moves them.
- **Small, if a session stalls**: **79** (media keys as a reflex source —
  its own recommendation is *don't, until something wants it*), **52b**
  (per-pixel ring, a protocol proposal against a frozen v1), and **110** (a
  sequence cannot show a count — one seam, and the argument for waiting is
  that Stage 3 re-decides it anyway).

- **Triaged 2026-09-05 and not started**: **113** (the light library - a
  searchable page replacing the preset dropdown, generated rather than
  authored), **114** (a scene library per customer archetype; its research
  half is [ARCHETYPES.csv](ARCHETYPES.csv), already written). **112**, **115**
  and **116** went to the parking lot - a tinkerer's cipher app for the
  release-day bank, and the two halves of multi-button work, which are
  structural and want deciding before more hardware exists rather than after.

**Known live state you may trip over:** the `no-store` header on `/static`
needs a service restart to take effect — until then a browser will happily
run a stale ES module graph, which looks exactly like your edit not having
happened. Priming the HTTP cache with `fetch(url, {cache: 'reload'})` per
module before reloading is the workaround. And **the offline editor renders
from a snapshot**: after `tools/build_editor.py`, navigate to the file again
rather than reloading, or you will test the previous build.

## Sprint

### 111. The device runs its own app - Phase C, one app at a time

**Asked 2026-08-30**: *"get me something that will run the lightshow app (at
the very least) without depending on a Bluetooth connection."* Shipped the same
day, for the light show, on the ESP32-S3 that is already on the desk.

**What is on the device now.** `apppkg.py` decodes a compiled package,
`runtime.py` is the step function over it - `(app, state, kind, param) ->
(state, ops)`, pure, no allocation - `standalone.py` gives that a clock and a
light, and `sequence.py` is `sequencer.py`'s rendering half so a *stop list*
plays on-device rather than being pushed a frame at a time over the radio. The
compiler is host-side: `aibutton/appc.py`, driven by `tools/install_app.py`.

**The numbers, because they are the argument.** The owner's real config
compiles to a **180-byte** package: the ambient menu, the light show behind it
(two cues, both stop lists, one a 15.5 s triple fade) and a second menu. The
whole live config is 5,893 bytes of JSON. Against 4 MB of flash.

#### What can reasonably run without a host, measured 2026-08-30

Derived from what each template actually keeps, not from taste:

| Runs standalone now | Needs one compiler pass | Needs a runtime feature |
|---|---|---|
| **lightshow** - cue ring unrolled | **countdown** - its ramp is a one-shot stop list; no new runtime feature, and the *ladder* would not come | **stopwatch, counter** - variables and the durable document |
| **signal** - one state per position (its per-position *message* stays host-side) | | **pomodoro, metronome, hotcold, reaction** - expressions |
| **actions** - one state, plus one per launching gesture | | **notice** - a real clock, and the 32.768 kHz crystal on the BOM |
| | | **control** - the phone, by design: every command it sends is MIDI or OSC |
| | | **launcher** - an app list the device can enumerate |

So **three of thirteen templates run today**, a fourth is a compiler pass, and
the rest split cleanly into "needs expressions", "needs storage or a clock" and
"needs the phone forever". `tools/install_app.py` prints this per config,
naming every gesture and mode left behind - because what a standalone button
will not do is a thing to read before flashing, not to discover by pressing.

Six decisions worth not re-litigating:

- **The compiler unrolls, the runtime walks.** "Next cue, wrapping" is not
  arithmetic on the device: it is two states per cue (running and held)
  pointing at each other. That is what buys a runtime with no expression
  evaluator, no variables and no allocation - and it is the honest first slice
  rather than a shortcut, because the apps that genuinely need arithmetic are
  exactly the ones ARCHITECTURE.md already says need expressions.
- **One interpreter, not two.** ARCHITECTURE.md anticipates a device runtime
  and a host runtime guarded by a conformance suite. Until the web UI grows one
  in JavaScript, `firmware/runtime.py` imported by the host suite is strictly
  better than two files that agree today. The *format* is mirrored (encoder
  host-side, decoder device-side) and is tested as one.
- **No package means nothing changed.** Every branch is behind
  `apppkg.load()` returning something. A board with no `app.pkg` is the board
  it was last week, which is the safety argument for putting any of this on a
  device you have to re-flash to debug.
- **The host wins while it is connected.** The app takes the LED on disconnect
  and hands it back on connect; they never write it together.
- **The floor moved to compile time** for this path, and CLAUDE.md now names
  all three paths to the light. A package renders with no host to clamp it.
- **A package holds several apps, and the start app is the ambient menu.**
  That is what makes it a button rather than one app in a box: the menu's
  gestures `OP_ENTER` the others, leaving one returns to it, and leaving *it*
  has nowhere above to go, so it sleeps. `_return_to` is a single slot, not a
  stack, because `return_after` is one level host-side too.

**Two bugs found by the tests rather than by a board.** The second: a menu's
launching gesture was emitted as a *transition* whose target was the app index
- but a transition points at a **state**, so it jumped inside the menu and the
runtime printed "transition to missing state". Launching is an **op**; the
gesture now goes to a one-op state whose only job is the `OP_ENTER`. The
unrolling rule, one layer up from where it was first needed.

**The first, and why the sweep samples past one cycle**: the two stop-list walkers accumulated a cycle's length in different
orders - `at + (fade + hold)` versus `(at + fade) + hold` - differed by one
ulp, and therefore disagreed *completely* at the loop seam, where the modulo
landed at the end of the previous cycle instead of the start of the next.
Identical for 30 frames, then one frame of a totally wrong colour, every loop.

#### What is left, in the order it matters

- **Untested on hardware.** Everything above is driven by the host suite and a
  by-hand simulation; the board has not been flashed. That is the next thing
  and it needs a service stop.
- **The countdown**, which is the next cheap one: its ramp compiles to a
  one-shot stop list and its ring is an `OP_PLAY`. No runtime change. What
  would not come is the ladder, which is a second animation layer over the
  same light.
- **Expressions**, for the metronome. The stress case ARCHITECTURE.md names,
  and the thing the unrolling trick deliberately postpones.
- **The event ring buffer** (128 KB at 8k events), which is what actually
  breaks the tether: presses while disconnected are still dropped, and the
  firmware still says so in a comment.
- ~~**Sync.**~~ **Done 2026-08-30, the same day**: `APP_PACKAGE` installs a
  package over BLE through the running service (`install_app.py --push`, or
  `POST /api/app/install`). Three decisions in it:
  - **The payload is opaque to the transport.** Whoever compiled it - the PC
    today, a phone later, a store one day - the device sees a length, bytes and
    the package's own checksum. That is what makes the phone app a *client* of
    this protocol rather than a second implementation of it, and it is the
    reason to have designed the transport this way before the phone exists.
  - **The old package survives every failure.** Length, CRC and a full decode
    all pass before anything is written, and the first error is the one
    reported (a transfer refused at BEGIN must not read back as "a chunk
    arrived with no transfer open").
  - **A package's fingerprint is the CRC it already carries, read not
    recomputed.** A CRC-16/CCITT over a file that *ends* in its own CRC is the
    constant 0x0000 - so the recomputed version, which is what was written
    first, would have matched for every package ever built and the staleness
    check would have been silently dead. `test_app_push.py` caught it by
    compiling two different configs and expecting two different answers.

  What is left of sync is the other direction: events up, time down. Nothing
  goes up yet.
- ~~**The staleness warning has an endpoint and no UI.**~~ **Shipped
  2026-09-03**: an "On its own" section at the foot of the Apps page, which is
  the page that already answers "can anything get to this?" one level up.
  `standaloneVerdict` (schema.js, pure, table-tested) turns `/api/app` into one
  of five states - unsupported, unbuildable, empty, stale, current - and the
  section names the start menu, the apps that made it, every mode that stays
  host-only with what it is waiting on, every gesture dropped with why, and an
  **Install on the button** button. Three things worth not re-deciding: the
  answer is fetched **once per load, not per render**, because the server
  compares against what is on *disk* and typing cannot move it (Save and
  Install drop the cached answer instead, and an unsaved page says so beside
  the button); **`installed_crc: 0` is "no package", not a checksum**, which is
  what a never-flashed board actually reports and would otherwise have read as
  merely out of date; and a service too old to answer costs the *section*, not
  the page.
- **A capability bit.** Nothing on the host negotiates "runs apps standalone"
  yet, so no bit was burned. Add one when a host needs to ask.
- **Power.** None of this touches ROADMAP **3c**, and 3c is still what decides
  whether MicroPython holds the runtime plus storage plus sync inside budget.


### 77. The DAW tells the button what it is doing, and the light says so

**Asked for 2026-08-26, and it is the example that makes 70 concrete.** The
owner's words: *one press to record; the DAW tells the button it's recording
and the light turns bright, gently pulsing red; press again, the light turns
dark blue for stopped; another press goes back to recording.*

**Every piece of this is expressible now that 73 and 74 have shipped, and none
of it needs the button to guess.** MCU is two-way: the DAW lights the surface's own Record
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
- A **reflex sets the current position** - built (**74**): `set_position` is
  an action, and the signal light already takes one over HTTP. `note 95
  velocity 127 → "Recording"`; `note 95 velocity 0 → "Stopped"` is that same
  action with **73** in front of it, and the velocity is **72**'s test.
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

#### The code shipped 2026-08-28. What is left is the rig.

**All four pieces are in** - `ControlBehavior.positions` (each **naming a
look**, never carrying a colour), `run_control` on `wait_in_app`, `resting()`
painting the current position, and `config.position_reporters` answering
"can anything actually set one" so the surface says it is guessing rather
than showing position one as a fact. Positions are optional and a surface
without them is byte-for-byte the remote it was.

Three decisions worth not re-litigating:

- **A position names a look; it does not carry a colour.** The opposite of a
  Signal position, because this template already answers "what does this look
  like" through `MODE_LED_STATES["control"]`, and two controls for one
  question is what CLAUDE.md forbids. A position with no look wears the page's
  own LISTENING look - the existing fallback chain, unchanged.
- **A reported position writes no row.** `log_as` here means "one command
  sent" and its readout is a tally of those; counting an arrival as a command
  would inflate the only number this app reports. A Signal logs both because
  both are "the light was there", and that is a different question.
- **"Guessing" is a walk over reflexes, not over MIDI ports.** A reflex is the
  general answer - the HTTP endpoint reaches a position too - so the check is
  `while == this app` plus an action that resolves to `set_position`.

**What is left is the test, and it is all rig**: a second loopMIDI port, the
DAW's Mackie Control **Send To** pointed at it, two reflexes on
`note 95 velocity 127 / 0`, and arming record *by clicking in Studio One*.
Documented in README ("The other direction") and MANUAL §7 for whoever sits
down to it.

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
*Stop, Stop*, which `MidiAction` cannot express — **33 shipped 2026-08-27 and
is that**, so a position fires one action that happens to be two messages, and
this item needs no per-position pair of its own.

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

### 80. The button should *be* the MIDI port — getting off loopMIDI

**Asked by the owner 2026-08-27, at the desk, with a DAW that could see our
notes and would not act on them:** *"would it be at all possible to build our
own path, rather than using loopMIDI? I don't want users to have to depend on
third party software. How do MIDI controller devs do it?"*

**The answer to the second question settles the first: they don't have this
problem, because the controller *is* a MIDI port.** A Launchpad needs no
virtual cable - it enumerates over USB as a class-compliant MIDI device, and
Windows, macOS, Linux and iOS all show it in the DAW's port list with nothing
installed. Wireless controllers do the same over **BLE-MIDI**, a published
GATT service that those four operating systems pair natively.

**Why we need loopMIDI today and they do not.** Our MIDI comes out of a *PC
application* that is pretending to be a controller, and **Windows has no API
for an application to create a MIDI port.** WinMM and WinRT MIDI can only open
ports the system already enumerates. Creating one means shipping a kernel
driver - which is exactly what loopMIDI is a front end for (teVirtualMIDI,
commercially licensed) - with the code signing and installer burden that
implies. That is not a road this project should go down for one action.

So the real fix is not a better cable. **It is to stop being a PC app in the
MIDI path**, which is the direction [ARCHITECTURE.md](ARCHITECTURE.md) is
already travelling.

#### The two paths that remove the dependency

- **(a) USB-MIDI when it is plugged in — and on Windows this is the one that
  actually works.** The S3 has native USB and micropython-lib ships a
  `usb-device-midi` class on top of `machine.USBDevice`. A class-compliant USB
  MIDI device needs no driver anywhere, and - the part that matters here - it
  enumerates as an *ordinary* MIDI port, so every DAW sees it however old its
  MIDI plumbing is.
  **The risk to test first:** this board's MicroPython uses the USB-Serial/JTAG
  peripheral (see the sticky-download-mode gotcha in CLAUDE.md), and a TinyUSB
  device build may be a different firmware - which would also change how the
  board is flashed and talked to. Verify before promising it.

- **(b) BLE-MIDI from the ESP32 — free on macOS and iOS, and the Windows
  caveat is the whole story.** The button already speaks BLE, and BLE-MIDI is a
  standard GATT service that macOS and iOS pair as a MIDI port with nothing
  installed. **Windows is the problem**: its BLE-MIDI support arrived with the
  WinRT/UWP MIDI API, and ports that appear there are not visible to the WinMM
  enumeration most Windows DAWs still use - which is precisely why Windows
  users of BLE controllers end up installing a bridge *and loopMIDI*. So on the
  platform this project runs on, (b) may swap one third-party dependency for
  another.
  **Verify that before building it** - it is a single question with a decisive
  answer (does Studio One list a paired BLE-MIDI device on Windows?), and it
  decides whether (b) is a Windows answer or only a Mac/iOS one.
  There is a second risk either way: the host already holds a BLE connection to
  the same peripheral, and whether the OS MIDI stack and `bleak` can share one
  device is unknown here.

#### What not to do

- **Do not write a Windows virtual MIDI driver.** Kernel mode, EV signing,
  WHQL, an installer, and a support burden per Windows release - for one
  feature that (a) and (b) deliver as a side effect of hardware doing its job.
- **Do not bundle loopMIDI.** teVirtualMIDI's SDK is licensed, and shipping
  someone else's driver is a dependency with a lawyer attached rather than a
  download.
- **Windows MIDI Services** (Microsoft's new open-source MIDI stack) offers
  app-created virtual endpoints *and* a modern route to BLE-MIDI, which would
  remove this problem on Windows for free and would also un-block (b). It is
  not everywhere yet, so it is a thing to watch rather than a plan to build on
  - but it is the reason not to invest in a driver of our own.

#### What this changes if it lands

**The DAW link stops being a host feature and becomes a device one.** Item
**25**, **77** and **78** are all written around the host sending MCU notes and
listening for MCU feedback (**73**); if the button is the port, the feedback
arrives *at the button*. On (a) that is fine - the device already talks to the
host - but the reflex would come in over the button's own link rather than
through `midi_io`, and `MidiSource` would gain a second source kind rather than
being replaced. **Nothing built so far is wasted**: the actions, the reflexes,
the tests on the value and the transport app are all above the transport layer.

**Do not start this before 77 has run once on real hardware over loopMIDI.**
The point of that test is to prove the *protocol* conversation works - which
notes, which velocities, which device type - and it is much cheaper to debug
with a cable that already exists than through a new one being written.

**84b is what's left of the shell read-back's second pass** — raised
2026-08-29 alongside 81, 82, 83, 84, 85, 86, 87 and 88; all but 84b have
shipped and now live in [TODO_FINISHED.md](TODO_FINISHED.md).

### 84b. Fire (or at least log) a missed window on reconnect, not just live

**Raised 2026-08-29, while designing 84 above, and deliberately not built
yet.** Today, if the service or the BLE connection is down at a Notice's
scheduled time, `scheduler.due_alarm`'s 60-second window (`_FIRE_WINDOW`)
simply passes and the occurrence is gone - no ring, no flash, and as of 84,
still no log row, since nothing ever called `ring_notice` for it at all. A
missed dead-man's-switch check-in during an outage currently looks identical
to one nobody armed.

The owner's own framing, two options rather than one required design:

- **Catch up on reconnect**: if a window was missed while offline, ring/flash
  immediately once the button/service is back, and start the miss-timeout
  clock *then* rather than backdating it to the original time.
- **Or, if that is turned off, still log/act host-side** even with the
  *button* unreachable, since a webhook or a log row needs the PC online, not
  the BLE link - "should be doable if the computer is online, right?"

Real open questions, not yet decided:

- **What counts as "offline"?** The service not running, BLE not connected,
  or either - these are different failure modes with different recovery
  points (a service restart replays from a cold `fired` set; a BLE drop
  leaves the service's clock loop running the whole time).
- **Does a host-only action fire with no device connected?** `on_missed`
  today runs through the same `run_action`/`resolve_action` path every other
  action does, which does not require the device for a webhook/log/OSC action
  - so this may already work for the "still log/act" half; worth confirming
  rather than assuming.
- **How does `due_alarm`/`fired` need to change?** The 60-second window and
  the per-occurrence `fired` set are sized for "the loop was always running
  and ticking within a second," not for "the service was down for hours" -
  catching up needs the scheduler to notice a *missed* occurrence, not just a
  *due* one, which is a different question the current function was never
  asked.

**Not low-hanging fruit.** Needs the questions above answered before any code,
the same way 84 itself needed the outcome-logging question answered first.

### 89. The button stopped answering after the desolder *(hardware triage)*

**Reported 2026-08-29**, after the owner sat on the button and then removed
and desoldered the switch. BLE reconnects, the light follows the web UI, and a
physical press does nothing.

**What that already told us**: the firmware is running, the radio is up, the
LED path is fine and the host is dispatching. The fault is on the **input**
side alone.

**And the first answer was never code.** `BUTTON_PIN` is 10 with the internal
pull-up on and `ACTIVE_LOW`, so with no switch across it the pin reads 1 -
"not pressed" - for ever. A desoldered switch and a button nobody is pressing
are the same reading, and no firmware change makes a press happen.

#### Shipped 2026-08-29: the BOOT button is a second input, always on

Firmware **0.8.0**. `hardware.BOOT_BUTTON_PIN` (GPIO0, the switch the board
already has) is polled in parallel with `BUTTON_PIN` and ORed **before** the
debounce, so the two are one button: either is a press, every gesture works
from either, and a press can move from one to the other mid-hold without
becoming two. Nothing downstream knows there are two - no protocol change, and
no capability bit, because a host would not act differently if it were told.

Three decisions worth not re-litigating:

- **Always on, not opt-in.** The whole value is being there on the day the
  wired switch is not, which is a day nobody plans for. `None` turns it off.
- **Read through `getattr` with defaults.** hardware.py is the one file people
  edit and carry forward; an older copy missing these names must degrade to
  "no BOOT button" rather than raising at startup, which on a headless board
  is indistinguishable from a dead board.
- **Deduped when it *is* the wired pin**, so a board whose only switch is on
  GPIO0 opens one input rather than two.

**The caveat ships with it and is in three places now**: GPIO0 held low at
power-on or reset enters download mode, and the board then sits silent in the
bootloader until it is physically replugged. Press it while the board is
running, never while it starts.

**Flashed to the real board 2026-08-29.** The code landing in the repo and the
board actually running it were two separate steps - this closes the second
one. The board is on 0.8.0 and the BOOT button works as a second input.

#### Still open: is GPIO10 alive?

The spare makes the button usable; it does not say whether the pin survived
being sat on. Answer it at the same desk as **0c**'s re-solder:

1. **Is a switch on GPIO10 at all?** If not, this is **0c**, not a bug.
2. **Prove the pin.** With `main.py` interrupted (`mpremote exec` does that -
   `reset` afterwards, see [CLAUDE.md](CLAUDE.md)), read
   `Pin(10, Pin.IN, Pin.PULL_UP).value()` while shorting pin 10 to GND with a
   jumper. 1 -> 0 proves the pin, the pull-up and the config in one move.
3. **If it never reads 0**, `BUTTON_PIN` is one line and a reflash; any plain
   S3 GPIO will do, and the header of
   [hardware.py](firmware/hardware.py) says which are safe.

**Done when**: the answer to (2) is written here.

### 90-100. The whiteboard, 2026-08-29

**Filed in one sitting by the owner**, and they are not one body of work: two
are product strategy, two are integration policy, three are app-shaped, and
one is a second client. What they share is that most of them are **bigger than
they look**, so each says up front which part is decided and which is not.

### 90. The iOS app — and the question it forces

**Asked 2026-08-29**, with Xcode installed and the whiteboard cleared: an iOS
app (Swift, yes - SwiftUI plus CoreBluetooth) that mirrors the current
interface, talks to the button over BLE, and adds camera switching, Shortcuts,
texts, incoming information and a find-my-phone.

**Read 40, 43, 38 and 39 first.** This is item **40** ("a portable host")
arriving with a name, and half of what is asked for is already scoped in 38
and 39 and needs no app at all.

#### The question, and it decides everything else

**Every decision in this system is host-side.** The device detects and
renders; rules, scheduler, modes and actions all live in
[main.py](aibutton/main.py) and [config.py](aibutton/config.py). So an iOS app
that talks BLE to the button is not a *view* of the button - it is a **second
brain**, and writing it means reimplementing the parser, the mode machine and
every action in Swift, then keeping the two in step for ever. That is the
single largest fact about this request.

Three ways out, and **the recommendation is (a) now and (c) as the real
answer**:

- **(a) A thin client over HTTP.** The app is a window onto the running
  service - the web UI already works at phone width (**42**), and the REST API
  is already the whole surface. Days, not months, and it needs no second
  brain. **The cost is honest and must be said out loud: it does nothing when
  the PC is off**, which is exactly the complaint 40 exists about.
- **(b) A second host in Swift.** The button works with no PC. Also forks the
  brain, permanently, and every future item ships twice.
- **(c) Wait for Stage 3.** ARCHITECTURE.md's whole design is that the runtime
  moves onto the device and the phone holds preferences and does the heavy
  lifting. After that, an iOS app is a preferences editor plus a `Request`
  fulfiller - which is a normal app, not a second implementation.

So: **(a) is worth building now** (it is genuinely useful and nothing is
wasted - the REST API is the same API the phone will use later), **(b) should
not be built**, and (c) is what makes the app small.

#### What the native capabilities actually cost, checked rather than assumed

- **Camera shutter** is **38**, and needs no app: BLE HID volume-up is the
  universal shutter on iOS. *Switching* front/back is not a HID key, so that
  part does need the app and its own camera view.
- **Shortcuts** is **39** and already works through a webhook. The native
  route is **App Intents**, which is nicer and is a small addition once an app
  exists.
- **Sending a text: not possible from a third-party app.**
  `MFMessageComposeViewController` pre-fills a message and the *user* taps
  Send; there is no background or silent send on iOS, at any entitlement
  level. Design around it (a pre-filled draft is still one tap) or use a
  webhook to a service that can send.
- **Find My iPhone: no public API.** Nothing third-party can trigger it.
  What *is* achievable is our own app playing a loud sound when the button
  reaches it, which needs the `bluetooth-central` background mode and state
  restoration and works while iOS keeps the app alive. Useful, and **not the
  same promise** - do not call it Find My.
- **Receiving information** is the easy half: a CoreBluetooth central
  subscribing to the gesture characteristic is the same conversation
  [ble_device.py](aibutton/ble_device.py) already has.

**Done when**: there is a decision recorded here about (a) vs (c), and if (a),
an app that shows the config and fires a gesture. Not before the decision.

### 91. The counter stops being an app

**Asked 2026-08-29, and it is right:** *"Counter feels wrong. It is an app but
I do not know what I would launch it for. Count should be an action -
`counter_name` counts by x, x defaults to 1."*

**Half of this shipped on 2026-08-29 and the ask may already be met.**
`set_value` (**34**) is exactly "counter_name counts by x": name the app, name
the slot, add 1 (or any number, negative included), from any gesture in any
mode without entering anything. **Check that first** - the remaining question
is whether the *template* should still exist.

**The recommendation is a pool, not a template.** Counters become a top-level
`counters` object beside `looks`, `actions` and `reflexes` - a name, a colour
scheme for its readout, and nothing else - and `set_value` names one. That
removes a takeover nobody launches, and it removes the oddity that a durable
counter's number lives in a document keyed by a mode that exists only to hold
it. It also fits **88**: an app kind with no items under it should not be in
the nav.

**Keep the takeover as a preset if anything wants it.** "Open a tally and
press it up thirty times" is a real use (**15**); it just is not what the app
list should lead with.

#### The readout, which is the interesting half

`sequencer.readout` today is tens-as-slow-pulses and units-as-quick, **capped
at 0-99** (`_READOUT_MAX`). The ask is three schemes and no cap:

1. **Morse.** Numbers are five symbols each and unambiguous - and this is
   **83**'s compiler, reused directly (`morse.encode(str(n), unit_s, color)`
   handles digits already). 83 shipped 2026-09-05, so this scheme is close to
   free.
2. **Place-value colours.** A colour per decimal place (1s blue, 10s cyan,
   100s green, 1000s yellow, user-editable and extendable), each place blinking
   its digit 1-9 times, on a steady strobe. 1021 is yellow, cyan, cyan, blue.
   **This is the existing scheme generalised** - two fixed places become N
   configurable ones - so the shape is already right.
3. **Binary**, two colours for 0 and 1. Cheap, and the third option.

**All three are stop-list generators, which is the unifying point** and the
same conclusion **83** reached about Morse: a number and a scheme go in, a
`tuple[Stop, ...]` comes out, and everything downstream treats the result as
the ordinary stop list it is. So this is one pure module with three functions,
not three features. **The flash floor applies to all of them** - `readout`
today is written to clear `SAFE_MIN_PERIOD_S / 2` by construction rather than
lean on the clamp, and any new scheme has to do the same or say why.

**Done when**: a number of any size can be read back in any of the three
schemes, the scheme and its colours are configured on the counter rather than
on each binding, and the tests are tables of `(value, scheme) -> stops`.

### 94. One "Lights" app out of Light Show and Signal

**Asked 2026-08-29**, and it is the same observation **84** makes about the
alarm family: two templates, one machine.

Both wear one of N looks. The only difference is what advances them:

| | Signal | Light show |
|---|---|---|
| Advances on | a press | a clock (`dwell_s`), or a press when `auto` is off |
| Holds | always (it *is* a status) | double tap freezes it |
| Set from outside | `set_position` (**74**) | no |
| Each entry is | a name + an inline colour + an optional action | a look **named** from the pool |

So: one template, an `advance` setting (`press` / `clock`), and a list of
entries. Both existing behaviours fall out, and `set_position` reaching a
show for free is a bonus nobody asked for.

**The one decision that contradicts something written down.** CLAUDE.md
currently says a Signal position *carries* its colour "because a look is bound
to an `LEDState` and these are not states", and `ShowCue`'s docstring calls
naming the *opposite* choice for the opposite reason. Merging forces one
answer, and **the answer is naming**: the look pool did not exist when Signal
was written, a named look is the rich form, and the control surface's
positions (**77**) already went that way. Inline colours stay accepted so
every existing signal loads - but the rule in CLAUDE.md gets rewritten in the
same commit rather than quietly broken.

**Done when**: one template, both presets, every existing `signal` and
`lightshow` config loads and behaves the same, and CLAUDE.md's rule says the
new thing.

### 95. Colour themes — *check whether scenes already are this*

**Asked 2026-08-29:** a theme the whole button follows, rather than colours
set one at a time.

**Do not build a new config layer before checking the one that exists.** A
scene is a partial config merged over `config.json` before parsing, so a scene
carrying only `led_palette`, `looks` and `state_looks` **is a colour theme
already** - it changes every colour on the button and nothing else. If that is
true, this item is a *UI* item ("apply a palette set") and not a data item,
which is an order of magnitude cheaper.

The reason to be strict about it: **there is one parser and scenes merge
before it**, and a second overlay mechanism with its own precedence is exactly
the thing that rule exists to prevent.

What might still be missing after that check: shipped themes worth having
(one high-contrast, one warm, one that is legible on the 3V3 ring's colour
cast - see **0c**), and a way to preview one without committing.

#### The check was run 2026-09-03, and the answer is "mechanically yes, usefully no"

**Mechanically a theme is a scene.** `scenes.merge` is shallow and key-by-key,
so a file carrying only `led_palette`, `looks` and `state_looks` inherits the
modes, the settings and everything else from the base. Nothing needed
building for that to be true.

**But a scene is a *slot*, not a layer, and the slot is already taken.** One
scene is active at a time (`scenes.active` is a single id), and this config's
active scene is `personal`, which carries the whole thing - modes included.
Switching to a theme scene would not tint the arrangement, it would *replace*
it. Stacking a second overlay is exactly what "there is one parser and scenes
merge before it" exists to prevent, and `ConfigManager.write_path` compounds
it: edits go to the active scene, so a theme in that slot would quietly become
where every subsequent edit lands.

**So this is the UI item the write-up predicted** - "apply a palette set",
writing the colours into whatever is already active, rather than a second
config layer. A picker on the Lights tab beside the system states, and a table
of palettes in schema.js.

**One of the three asked-for themes cannot be authored yet.** "Legible on the
3V3 ring's colour cast" needs **0c**'s eyeball test - its `#ffffff`-reads-as-
white question is still open - so shipping that one before the bench sitting
would be inventing numbers. The high-contrast and warm ones do not wait on
anything.

**Done when**: a handful of themes ship as a palette set the Lights tab can
apply. Not as scenes - that question is answered above.

### 96. Pre-built integrations — *and the secret store that has to come first*

**Asked 2026-08-29:** a growing catalogue of API integrations - Alpaca, Google
Calendar, Slack - where you paste a key and choose an endpoint.

**This cannot be built as described, and the blocker is not the integrations.**
API keys would live in `config.json`, and `config.json` is: returned in full
by `GET /api/config`, editable by anyone who can reach the web UI (**which has
no authentication at all**, by its own docstring), written into scene files,
and - as of **92** - committed to git. Putting a brokerage key in there is a
credential leak by construction, not by accident.

So this is **two items in a trench coat**:

- **(a) A secret store.** Values that live outside `config.json`, are never
  returned by the API, are referenced by name from an action, and are absent
  from every scene and export. This is the prerequisite, it is a real piece of
  design, and it is what makes the rest safe.
- **(b) The catalogue**, which is mostly data once (a) exists: the webhook
  action already reaches anything, and "pick a service and it fills in a
  template" already exists for IFTTT and Make. Each integration is a
  descriptor - base URL, auth style, a few endpoints - which is
  [schema.js](aibutton/web/static/schema.js)'s whole pattern.

**And read 100 before picking the first integrations.** Several of the most
wanted ones need no key at all, which means they can ship before (a) does.

**OAuth is a third thing again** (Google, Slack): it needs a redirect URI, a
token refresh loop and an app registration per provider, which is a service
and not a button feature. ARCHITECTURE.md already says heavy lifting belongs
on the phone or the cloud; this is that, exactly.

**Done when**: (a) exists and one keyed integration uses it. Not before.

### 97. Could this be a product? — *the honest answer today is no, and here is the list*

**Asked 2026-08-29:** could we mass-produce this with ESP32s, printed
enclosures and ordered buttons, as it stands?

**No, and the gaps are specific rather than vague.** ROADMAP Stage 4 and
Stage 5 hold most of them; this item is the security half, which is thinner
than the rest and needs to stop being.

**Security, as it actually is today** - each of these is a deliberate,
documented choice that is correct for a workshop and wrong for a product:

- **The web API has no authentication.** It can rewrite the whole config,
  fire any action, and stop the service. Its docstring says so and says "front
  it with a reverse proxy" - which is not an answer a shipped product can give
  its user.
- **BLE is unauthenticated and unbonded.** Anything in range can connect and
  drive the LED, and read every gesture. Pairing with bonding is the fix and
  it is a protocol-adjacent change, so it wants doing before units exist.
- **The `keys` action types on the host** and the `sequence` action can chain.
  On a shared machine that is a remote keyboard.
- **No OTA path.** `OTA_CONTROL` is claimed in the protocol and unimplemented,
  and ROADMAP Stage 4 already says: do not ship a unit to anyone, including a
  friend, without field update working end to end.
- **No secret store** (**96**), so any integration a user adds is stored in
  clear and served over that unauthenticated API.

**Manufacturing, briefly** - the roadmap has this and it is worth restating in
one place: no enclosure, no battery or charging, no sleep (**29**, blocked on
measuring draw), no 32.768 kHz crystal on a BOM that does not exist, no
regulatory work for a radio product, and MicroPython on a dev board is right
for tens of units and not for thousands.

**And the topology is the biggest one.** A button whose brain is a Python
service on a PC is not a product anybody can unbox. That is Stage 3, and it is
the reason Stage 3 exists.

**Done when**: this list has owners and numbers. It is a map, not a task.

### 98. What the pitch has to be able to show

**Asked 2026-08-29:** *"a small, almost gimmicky, cheap keychain button you'd
find in a dollar store - then show off its most powerful features."*

**That framing is the product, and it is worth writing down because it decides
what gets finished.** The demo is the spec:

- **It has to work with nothing attached.** A demo that begins "first, start
  the service on my laptop" tells the room this is a script, not a product.
  Stage 3, again, and this is the strongest argument for it.
- **The first thirty seconds must be dumb.** Press, light, beep. The gimmick
  has to land before the power does, or the reveal has nothing to reveal.
- **The reveal should be one press doing something nobody expects a keychain
  toy to do** - the DAW transport is already the best candidate here and it is
  already verified on real hardware (**25**, **77**).
- **Then breadth, fast**: the same button as a timer, a counter, a status
  light, a remote. The launcher is what makes that a single object rather
  than five.
- **Then it has to survive being handed over.** Someone else presses it and it
  does the right thing. That is **14**'s naive-user run, which has not moved
  in four sprints and is the single cheapest thing on this list.

**What a room of investors will ask, and what we can answer today**: what
stops anyone cloning it (nothing yet - see Stage 5's IP note), what it costs
to make (unknown, no BOM), how it updates in the field (it does not - **97**),
and who it is for (undecided, and the demo above quietly assumes three
different people).

**Done when**: there is a demo script, and every step in it works without a
laptop.

### 99. A reflex that goes and looks — "check this every hour"

**Asked 2026-08-29**, alongside "when x signal is received - MIDI, keyboard,
or something else".

**The signal half is mostly built and may just be undiscoverable.** A reflex
already fires from an HTTP POST (**71**) or a MIDI message (**73**), with a
one-field test on the value (**72**), and reflexes are already add/edit/remove
in the editor's panel. **Check that UI before building anything** - if the ask
is really "I could not find it", that is **88**'s problem, not a feature.
Keyboard in is **79**, which recommends against a global hook and says why.

**The new thing is a reflex with a clock and a URL**: fetch this every N
minutes, and hand what comes back to the ordinary `when` test. That fits the
architecture exactly as written - *"a new source builds a payload and stops
there"* - because the comparison language already exists and the consequence
vocabulary does not grow. `MidiSource` gains a sibling; nothing else changes.

Three things to get right, all of them the kind that bite later:

- **A poll is not a press**, so it goes on `main`'s `inbound` queue like every
  other reflex and never becomes a synthetic gesture.
- **Failure has to be quiet and visible**: a server that is down must not fire
  the reflex, must not spam the log every minute, and must be findable when
  somebody asks why nothing happened.
- **Authenticated polling needs 96(a)**, so the first ones should be the
  endpoints that need no key - see **100**.

**Done when**: a reflex can name a URL and an interval, its reading is logged
under the reflex's own name exactly as a posted one is, and a dead endpoint
costs one log line rather than sixty an hour.

### 100. Prefer a URL to an API — *decided: it changes what 96 builds first*

**Asked 2026-08-29:** *"Are APIs always the best way? Would iCal or similar
make things better? Could there be a user-friendly non-API integration with
Google, Microsoft or Apple?"*

**No, they are not, and this is the most useful finding in the batch.**

Google Calendar, Outlook and iCloud all publish a **secret `.ics` URL** for a
calendar: a plain HTTPS GET, no OAuth, no app registration, no API key, no
consent screen, no token refresh. Fetch it and parse it. For *"what is my next
meeting"* that is one HTTP request against several hundred lines of OAuth
plumbing and a Google Cloud project. The same shape exists elsewhere:
**RSS/Atom** for feeds, **CalDAV** for two-way calendar, **IMAP** for mail,
and a great many services publish a read-only token URL.

Where a real API still wins: **writing** data, anything real-time, and
anything that must be per-user with revocable access.

Two consequences, and they are the point of writing this down:

- **96 should ship its keyless integrations first.** They need no secret
  store, so they are not blocked on 96(a) at all - a calendar reflex ("my next
  meeting starts in 10 minutes") can be built the day **99** lands.
- **"Paste a URL" is a better user experience than "authorise this app"** for
  the non-technical user this product is aiming at, which is the opposite of
  what the integration catalogue would have assumed.

**Done when**: 96 and 99 both say which of their targets need a credential and
which need a URL, and the first one built is a URL.

### 101-108. The sidebar as a map, and what came with it

**Raised by the owner 2026-08-29**, the evening after 90-100, from actually
living with the finished nav. **101, 102, 103 and 107 shipped** and now live
in [TODO_FINISHED.md](TODO_FINISHED.md). What's left:

### 105. A notice says how far it is allowed to interrupt

**Asked 2026-08-29, alongside 104** (which shipped the same day), and it is
the question sleep forces:
*"some notices should take over no matter what, even when asleep. Some notices
take over only when idle or in a menu."* **Settled the same day at four tiers,
not three** - the owner's completion was that *"While Awake"* has to be
distinguishable from *"Always"*, and it does: they behave identically while
the button is awake and differ only in whether they are allowed to wake it.

| `interrupts` | Wakes a sleeping button | Interrupts a running app | Shows at the root |
|---|---|---|---|
| `always` | **yes** | yes | yes |
| `while_awake` | no | yes | yes |
| `when_free` | no | no | yes |
| `never` | no | no | **no** |

#### It is a ladder, and that is the property to protect

Read the table down any column: **each tier is strictly weaker than the one
above it**, and every tier's permissions are a subset of its predecessor's. So
this is *one ordered enum*, not two orthogonal flags dressed as four names -
which is why it is a single four-way choice in the editor rather than a pair
of checkboxes whose sixteen combinations include twelve that mean nothing.

**The rule that falls out, and it is the reason to write this down: a proposed
fifth tier either slots into that order, or it is not a tier.** Something that
is not simply more-or-less permissive than its neighbours is a *second axis*
and belongs on its own field - exactly the argument that keeps `urgent`
separate below.

#### Waiting is one rule, shared by both middle tiers

A notice that arrives but is not allowed to show yet **waits**, and its own
`timeout_minutes` decides whether waiting turns into a miss - logged 0,
`on_missed` fires, exactly as **84** already does. `when_free` waits for the
running app to exit; `while_awake` waits for the button to be woken. Same
machinery, same field, no new concept.

**Which makes `always` easy to state precisely**: it is the tier that does not
wait.

**`never` is not a degenerate case, it is a gap being filled.** "At 9 AM, POST
this webhook, no light" is not expressible today: a schedule can only start an
app, and every app owns the button. This makes a Notice able to be a *silent
scheduled action*, which several people will want before they want bells.

**The default must be `when_free`.** If new notices default to `always`, sleep
means nothing within a week - and `while_awake` is the wrong default for the
same reason one rung down: a reminder that interrupts a Pomodoro is a reminder
people turn off.

**Keep it off `urgent`, and expect pressure to merge them.** `urgent` (from
**84**) is *how loud* - loop the tone, hard flash. `interrupts` is *whether it
is allowed to speak at all*. They look mergeable and are not: a gentle chime
that must still pierce sleep is `urgent: false, interrupts: always`, and 84
already rejected deriving one such field from another for the same reason.

**Where this generalises, and the trigger to lift it**: a *reaction* firing
`enter_mode` while asleep asks the identical question. Do not build for that
yet - ship `interrupts` on Notice, and lift it to the dispatch site the first
time a reaction needs it, which is the point at which one flag in one place
beats two fields.

**Done when**: the four tiers exist on a Notice as one ordered field,
`when_free` is the default, an `always` notice wakes a sleeping button and puts
it back, a `while_awake` notice waits for a wake instead of forcing one, and a
`never` notice fires its action with the light untouched.

### 106. The hour chime - church bells, and 91's compiler finding its second caller

**Asked 2026-08-29.** *"Every hour, the light could fade to white over 10s,
then flash to indicate what hour it is, then fade back to whatever menu the
device was in. Choose between 1-12 flashes colour-coded per hour, the
colour-coded number system we already have, or binary."*

**The finding that makes this cheap: it is not a new feature.** It is three
things this project either has or has already designed:

1. **A Notice** - shipped, **84**.
2. **A number rendered as a stop list** - that is **91**'s compiler exactly
   (`number + scheme` gives `tuple[Stop, ...]`), and **83**'s. The owner names
   three schemes and they are 91's three; "a colour per hour, 1-12" is a
   fourth, and it is the same shape.
3. **A recurring schedule** - and this is the only genuinely new part.

**So the triage is: build 91's compiler once, and the chime is its second
caller.** Do not write a bell renderer.

#### The one new part, and the thing missing from the sketch

`ScheduleActivation` is `at: "HH:MM"` plus days. Hourly needs a repeat, and the
cheapest honest shape is `every: 'hour'`. **But the sketch has no window, and
nobody wants bells at 3 AM** - so `between: ["08:00", "22:00"]` is not a
refinement, it is the difference between this being usable and being turned
off on the first night.

#### Two things worth knowing before anyone promises it

- **"Fade back to whatever it was" is not expressible today.** A stop list is
  a schedule of colours and does not know what the light was doing before it
  started. Two options: end on black and let the host re-assert IDLE, which
  snaps; or let a stop name **the resting look** as a token the loop
  substitutes from `base_look`. **Recommend the token** - it is one value in
  the parser, and it makes *every* one-shot sequence able to land softly
  rather than just this one.
- **The flash floor decides how long noon takes.** At 3 Hz, twelve flashes is
  four seconds, plus a ten-second fade each way: **about 25 seconds of bells at
  midday.** That is a long time for a light on a desk, and it is the honest
  argument for the alternative schemes rather than a taste one - noon in
  binary is four symbols, not twelve. It is also an argument that **108**
  should be settled first.

**Done when**: a Notice can repeat hourly within a window, the hour is rendered
by 91's compiler in a scheme chosen on the notice, and the light returns to
what it was showing.

### 108. The flash floor is a setup decision, not a warning on every save

**Asked 2026-08-29**: *"The epilepsy warning is a little jarring and I'm not
sure it's really relevant. I'd love the light to flash much faster, especially
in the metronome / light-shows. I have a single neo-pixel LED. Is this really
something that could cause seizures on a consumer product?"*

#### The honest answer: for one small LED the floor is over-applied

Photosensitive epilepsy affects roughly 1 in 4,000 people, and the provocative
band is about 3-60 Hz with sensitivity peaking near 15-20 Hz - so 3 Hz sits at
the very bottom edge of it. **The decisive variable is not rate, it is how much
of the visual field the stimulus fills.** WCAG 2.3.1, ITU-R BT.1702 and the
Harding test are all written for *displays*, and WCAG's own exemption is a
flashing area below roughly 25% of the central 10 degrees of vision. A single
5 mm pixel at desk distance is far under that threshold. Bicycle lights, hazard
lamps, smoke-alarm indicators and strobing toys all flash in this band, sold to
consumers, without warnings.

**So the 3 Hz constant was borrowed from a standard that does not describe this
device**, and the code has always half-known it: `main.py` calls it *"the
default for `config.min_flash_period_s` rather than a law - one button on one
desk, and its owner may decide it can go faster."*

**Three caveats that are worth keeping, none of which is "keep the floor":**

1. **It stops being one small pixel.** A ring (**52b**) bounced off a white
   wall in a dark room is a different stimulus, and the light-show app is aimed
   at exactly that. Whatever replaces the floor should be a decision about
   *what is lit*, not a constant that assumed a dot.
2. **There is no safe harbour.** Today "we follow WCAG 2.3.1" is a sentence
   that defends itself; "we removed the limit" needs its own paper trail. That
   matters at Stage 4/5 (**97**), not on this desk.
3. **Brightness matters as much as rate**, so a floor on rate alone was never
   the whole answer even on its own terms.

#### What is actually jarring, and it is not the limit

The owner's config already sets `min_flash_period_s: 0.300`. That is 3.33 Hz -
a 10% change - and it prints this on **every load**:

> `min_flash_period_s 0.300s allows flashing at 3.3 Hz, above the recommended
> 3.0 Hz photosensitivity limit - honoured, but it is a seizure risk for some
> people`

A warning that fires on a setting the user deliberately chose, every single
time, on a 10% deviation, is not information - and it is the mirror of the
mistake CLAUDE.md's own rule already names: clamping silently makes a setting a
lie, and scolding forever makes it a nag. **Same error, opposite face.**

#### And it costs the metronome real behaviour, measurably

`metronome_flash` divides the flash rate to stay above the floor, so **above
180 BPM the light flashes every other beat**:

| BPM | Today | With no floor |
|---|---|---|
| 180 | every beat | every beat |
| 200 | **every 2nd beat** | every beat |
| 240 | **every 2nd beat** | every beat |
| 300 | **every 2nd beat** | every beat |

That is probably the actual motivation behind the ask, and it is a bug the user
can feel rather than a preference.

#### The recommendation - move the decision, do not delete the mechanism

1. **Keep `min_flash_period_s` and both pure functions.** `flash_safe` and
   `sequence_safe` stay, still one call site each in `main.set_led`. What
   changes is who decides the number, not where it is enforced.
2. **Ask once, at first run.** The new-user setup flow the owner is planning is
   the natural home: one screen, two choices, remembered. That is a genuine
   informed opt-out, which the current design is only pretending to be.
3. **Delete the parser warning.** Warn at the moment it is *lowered in the
   editor* - once, with a confirm - and never again from `parse_config`. The
   sentence should also stop implying a cliff at 3.0 Hz that the evidence does
   not support at this stimulus size.
4. **Then let the metronome and the light show run unfloored**, and drop
   `metronome_flash`'s division when the effective floor allows it.

**Blocked on nothing but the setup flow existing**, and step 3 alone can ship
today - it is the half that is actually annoying.

#### Step 3 shipped 2026-08-29

`_parse_min_flash_period` no longer warns for a value below the
recommendation; a value that is not a positive number is still an error and
still falls back, because that is broken rather than chosen. The hazard now
lives where the number is chosen - schema.js's hint, rewritten to say what the
guideline actually covers ("written for screens filling much of your vision,
not for one small LED on a desk") instead of asserting a seizure risk.
`tests/test_flash_floor.py` pins the **silence**, because a warning creeping
back is a regression nobody notices until it has been in a log for a week.

**Steps 1 and 2 remain**: the number is still edited on the Device page
rather than asked once at setup.

**Step 4 was already true, checked 2026-09-03** - the sentence that used to
stand here ("`metronome_flash` still divides above 180 BPM whatever the
effective floor is") was wrong. It takes `min_period_s` and both call sites
pass `cm.config.min_flash_period_s`, so the division is derived from the
*effective* floor and nothing else. Measured, with this config's chosen
0.300 s beside the 0.333 s default:

| BPM | default floor | at `min_flash_period_s: 0.300` |
|---|---|---|
| 180 | every beat | every beat |
| 200 | **every 2nd** | every beat |
| 240 | every 2nd | every 2nd |
| 300 | every 2nd | every 2nd |

So there is nothing to drop: lowering the floor already buys the beats back,
and 240 needs 0.25 s. What is left of step 4 is step 2 deciding the number.

**Done when**: no warning fires on load for a deliberately chosen floor, the
choice is made once at setup, and a 240 BPM metronome flashes on every beat.

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

**Eight red tests, 2026-09-03, and not one of them was a bug in the code.**
Worth recording because it is the shape this file's own rule predicts: a
lingering red test is cheap, but eight of them stop saying anything. Four were
tests left behind by decisions that had already shipped — the readout guard
still counted the templates from before `alarm` and `reminders` merged into
`notice` (**84**), the round-trip still expected a counter without `durable`
(**34**), a reminder still asserted that a timeout logs *nothing* when 84 made
outcome logging unconditional, and the mirror reader could not follow
`POOL_ACTIONS = HOOK_ACTIONS` because it only read array literals. The other
four were migration artefacts: `long_press` became `tap_4` in a shared test
config (**104**), which made all three max-taps cases answer 4, and two
document tests pressed three times 0.12 s apart *inside* the 2 s SUCCESS hold
the run loop deliberately discards behind. **The lesson for the next pass: a
decision that changes what is logged or serialised needs a grep for tests
asserting the old rule, in the same sitting.**

**Last run: 2026-08-29** — a context-cost pass, not a feature sprint. Moved
every fully-shipped item (whole items only, per "How to work this list") to
the new [TODO_FINISHED.md](TODO_FINISHED.md), rewrote the Sprint list's
navigation sections so they only describe what's left, and folded **21** and
**18** back into the Parking lot now that they're both ⏸-parked like
everything else there. [CLAUDE.md](CLAUDE.md) got the same treatment: split
into it and the new [INVARIANTS.md](INVARIANTS.md), topic-specific rules
moved out so a session not touching that topic doesn't pay to read it.
Nothing here changed status; this pass only changed what it costs to find.

Previous run: 2026-08-26, at the end of the sprint that shipped **44, 45, 46,
48a, 48c, 49, 50, 51, 52a, 53** and ran the **47** read-back. It compressed
those into **Done**, rescored the gates, deleted the launcher-`targets` note
that got fixed, and created **54-68** (the read-back's findings) and **69-75**
(signals, and what the mode list is called). Decision **D10** was opened.

Before that: 2026-08-19, which shipped **5, 9, 14, 15, 17, 19b, 26, 27, 28**,
the MIDI port dropdown, the item-23 design and **D9**, and created **31-34**.

**Nothing in either feature sprint has met the button.** Eleven items of
host-side work now sit between the last hardware sitting and this line.

**Next checkpoint: after the next hardware sitting.** That sitting now has
a queue worth doing in one go: **0c** (re-solder + the 5 V rework), the
Signal and control-surface walks, **26b** (does the colour coding read),
`tap_4` end to end (**28**'s residue), and the human readout test (**17**'s
residue). One session at the bench clears every open hardware residue;
checkpoint after it.

The standing job: re-read this file against what actually shipped, move
whole finished items to [TODO_FINISHED.md](TODO_FINISHED.md), prune what the
shipped version superseded, and score the roadmap's exit gates. Do the same
skim over [CLAUDE.md](CLAUDE.md) and [INVARIANTS.md](INVARIANTS.md) while
you're at it — a rule that's gone stale or a bullet that grew a paragraph
nobody needs any more is paid for by every session after this one, not just
by whoever's reading this list.

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

**Mostly answered, 2026-08-27.** The outbound half is **verified on real
hardware**: a control surface drives Studio One's transport over loopMIDI, and
the two things that stopped it working are written down in
[README.md](README.md) and [MANUAL.md](MANUAL.md) - name the port, and add it
to the DAW as a *Mackie Control* device rather than a keyboard. The inbound
half is a `from` on any reflex (**73**), so "a port the button listens on" is
no longer a design problem either.

What is left of this item is the *transport app*: **77** for the light,
**78** for the press that depends on it - and **80** for the question of why a
user has to install loopMIDI to have any of it. **Read 70 before starting.**

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

### 110. A sequence cannot show a count, and the reason is a seam

**Reported 2026-08-29**: *"Read count isn't available in the 'Do several
things in order' dropdown."* Correct, and deliberate today - `readout` is
absent from `SEQUENCE_ACTIONS` (config.py, mirrored in schema.js, drift-tested)
alongside `enter_mode` and `standby`. What makes it worth an item rather than a
line of documentation is that **"log it, then show me the total" is the most
natural sequence anyone would write for a habit button**, and it is the one
sequence that cannot be written.

**Two obstacles, and the second is the interesting one.**

1. **`actions.execute()` has no light.** Its collaborators are `store`,
   `documents`, `webhook_transport` and `session` - deliberately, since it runs
   fire-and-forget primitives and a sequence's steps run inside it. A readout's
   entire output *is* the light, so no amount of editor work reaches it.
2. **The SUCCESS flash would cut it off.** `handle()` plays SUCCESS after any
   ordinary action, and `set_led` cancels the running stop list on every call -
   which is exactly why `ReadoutAction` returns early from `handle()` and never
   goes near `execute()`. Give `execute` a light and a readout at the end of a
   sequence still dies about 200 ms in.

**The shape of a fix, if it is worth it.** An optional `show=` callback on
`execute()`, in the same shape as its other injected collaborators, plus a way
for a result to say *"do not flash over me"* - the honest form of which is
`ActionResult` growing a flag that `handle()` reads, rather than `handle()`
sniffing the action tree for a readout step. That flag is the part to think
about before building: it is a second thing an action can say about *how it
should be presented*, and there is exactly one caller for it today.

**Cheaper alternatives that need no core change**, in order of how much they
give up: bind the readout to its own gesture beside the sequence (what the
button does now); or accept that a sequence's feedback is SUCCESS and put the
number on the web UI instead.

**Not blocked on anything.** It is a decision about widening one seam, and the
argument for waiting is that `run_countdown`-style loops move to the device in
Stage 3 while `execute()` does not - so a light seam added to `execute` today
is a seam that has to be re-decided there.

---

### 113. The light library - a page, not a dropdown

**Asked 2026-09-05**: *"Remove our current light presets menu in favor of a
light library - a separate page with a massive bank of categorized, searchable
light presets... I'm hoping for at LEAST tens of thousands of options."*
Triaged, not started.

**What exists.** `LOOK_PRESETS` in schema.js is **142 entries** in one strict
JSON array, grouped nine ways, offered as a group-scoped dropdown by
`modeEditor.js` and by `colorEngine.js`'s look editor. `test_look_presets.py`
slices the array out of the source and feeds **every** entry through the real
Python parser, so no preset can ship a colour the config rejects or a rate the
flash floor would rewrite.

**Why the current shape cannot hold the ask.** Three limits, all real:

- **schema.js is shipped whole.** 142 entries is ~20 KB. 30,000 is ~4 MB, in
  an ES module the browser parses before the editor draws, and
  `tools/build_editor.py` **inlines it into one offline HTML file**. The
  library has to become a separate, fetched, paged data file; schema.js keeps
  a curated few dozen for the inline "start from a preset" path, or that path
  becomes a link to the library page.
- **A dropdown is not a search.** Tens of thousands needs a query, tags and
  facets (source, colour family, style, motion, "safe in a strobe-sensitive
  room"), not `<optgroup>`.
- **Nobody can hand-author 30,000 looks.** They have to be **generated** from
  source tables x recipes: ~200 national flags, club and franchise colour
  pairs, holidays and festivals, game and film palettes, common Morse
  messages (83's compiler already emits those as stop lists), colour-theory
  sets. `tools/build_light_library.py` writing a dated data file is the shape;
  hand-written entries stay a curated overlay on top of it.

**The honest ceiling, worth saying out loud before promising a number.** One
RGB LED means a look is *colour x colour2 x style (6) x period x optional stop
list*. Tens of thousands of **rows** is easy; tens of thousands of
**distinguishable** looks is not - past a few thousand, two entries differ by
20 ms of period and nobody can tell. So the generator must **dedupe on
perceptual distance**, and the number that gets advertised should be the one
that survives it. A library of 8,000 looks anybody can find in three keystrokes
beats 40,000 nobody can tell apart.

**The rules it must not break.**

- **The flash floor is a generation-time gate here**, exactly as `appc.py`'s
  `_look_bytes` is for packages. An entry the parser would clamp must not be
  emitted at all - clamping a preset silently makes the preset a lie, which is
  the same argument CLAUDE.md makes for `min_flash_period_s`. A sequence entry
  clears the second floor (`config.sequence_safe`) too.
- **`test_look_presets.py` keeps its teeth.** It cannot parse 30,000 entries
  per run, so it validates the curated overlay whole plus a fixed **seeded
  sample** of the generated file, and the generator carries the gate. The
  invariant survives; the runtime does not blow up.
- **A preset is still a starting point, never a stored thing.** Picking one
  copies its body. Nothing in the library reaches `config.json`, which is the
  only reason it can be this big at all.

**The "+" the ask names** is the other half: the library page is also where a
named look is *composed* - click "+" to push a colour onto a look you have
named, rather than editing one effect at a time. That is a second editor
surface over the same look object, not a new config shape.

**One question to answer before release, not after.** Colour pairs are not
protectable; **club and franchise names are trademarks**. Shipping a preset
called by a club's name invites a letter; shipping "Green Bay - Green & Gold"
does not, and users still find it by searching the team name if the *tags*
carry it. Decide the naming policy at generator level, once, or it has to be
unpicked across every generated row. Flags, holidays, colour theory and Morse
carry no such problem.

### 114. A real scene library, and the archetypes it is built from

**Asked 2026-09-05**: *"Let's actually build a running scene library... files
for many different customer identity archetypes."* The research half is
**done** ([ARCHETYPES.csv](ARCHETYPES.csv), 2026-09-05); the scenes are not
started.

**What exists.** `scenes/` holds two files - `default.json` and
`personal.json`. A scene is a raw dict layered over `config.json` inside
`load_config_full`, so every parser fallback already applies to it and a broken
scene is reported rather than fatal. That machinery is finished; what is
missing is *content*, plus the small amount of metadata a picker needs.

**What a library needs that a scene does not have today.**

- **Self-description.** A title, a one-line blurb, who it is for, and what it
  assumes (a DAW, a MIDI port, a webhook endpoint, more than one button).
  Today a scene is anonymous data; a gallery needs a header. Cheapest shape is
  reserved top-level keys promoted to real fields.
- **Honest degradation at pick time.** A musician scene naming a loopMIDI port
  this machine does not have must land with a warning the picker *shows*, not
  a silent no-op. `needs_restart` is the precedent - same idea, different
  failure.
- **A gallery, not a dropdown.** Same argument as **113**, one order of
  magnitude smaller.

**[ARCHETYPES.csv](ARCHETYPES.csv) is the input, and it is also a roadmap
feed.** Each row scores how likely marketing is to land (1-100), says what the
button solves for that person, and names **2-3 things they would want that the
button cannot do today**. Those gap columns are where the next app ideas come
from - read them before inventing one. The top-scoring archetypes are the
scenes to write first; the low scorers are written down to record *why not*,
so the question is not re-opened every quarter.


## Smaller, worth doing

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
- **117. A sequence should be able to end in a readout.** Asked 2026-09-05,
  from a config that already tried it: `short_press` was `{sequence: [log
  "Habit", "Count \"Habit\""]}`, where the named step was a pooled `readout`.
  The press logged the count and then went red - `execute()` has no branch for
  a `ReadoutAction`, so the sequence answered *unknown action type*.

  **The immediate hole is closed** (2026-09-05): `resolve_action` now checks a
  named step against `SEQUENCE_ACTIONS` the way the parser checks an inline
  one, so the step is dropped at resolve time with a reason instead of failing
  the press. What that does *not* do is give anyone count-then-read on one
  press, which is the thing that was actually wanted.

  **Why it is not just a branch in `execute()`.** A readout's light *is* its
  result, and `execute()` has no LED - it takes a store and a document store,
  and the light belongs to `main.handle`. Worse, `set_led` cancels the running
  sequence on every call, so the SUCCESS flash the generic branch plays after
  an action would cut a readout off mid-digit. That is exactly why `handle`
  intercepts `readout`, `standby` and `enter_mode` *before* `execute()` and
  returns early.

  **The shape that works: last step only.** `handle` runs the leading steps
  through `execute()`, then takes its own readout branch and returns without
  the SUCCESS tail. "Last only" is a real constraint rather than an arbitrary
  one - nothing can follow a readout, because the next `set_led` kills it -
  and it is the same argument that keeps `enter_mode` out of a sequence
  entirely.

  **What it touches**: `_parse_action_sequence`'s allow-list (a trailing
  exception), `resolve_action`'s new check, `handle`'s sequence path,
  `SEQUENCE_ACTIONS` in schema.js plus a `lastOnly` notion the step widget can
  render, and `test_schema_mirror.py`. Not large; the design question is
  whether `standby` gets the same treatment (probably not - a sequence that
  ends by going to sleep reads like a mistake) and whether the control
  surface's unwired `readout`, one bullet above, is the same fix at a second
  site or a different one.

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

  **Asked again on 2026-08-29, and it is still parked** - because what was
  asked for is the *nav* becoming a tree, which is **88**. Grouping a flat
  list by `template` for display costs nothing here and changes nothing the
  runtime reads. If 88 is ever tempted to nest `modes` to make itself easier,
  that is this item, and this measurement.

- **21. WiFi as an alternative transport.** ⏸ Decided 2026-08-18: not now.
  BLE is adequate, and the reason to wait is not cost — it is that waiting
  makes this cheaper *and* more useful.

  **The motivation is real.** Range, and flexibility; and the S3 already has
  the radio, so the BOM cost is zero and the capability is sitting there
  unused. That is a genuine argument and it is why this got its own
  write-up rather than a one-line entry.

  **What it would cost today.** A second transport in the firmware — note
  that `ButtonDevice` abstracts only the *host* half, so the device half
  doubles with nothing to hide behind. One shared 2.4 GHz radio, so
  coexistence adds jitter to the budget ARCHITECTURE.md pins at ≤50 ms. RAM:
  MicroPython plus BLE plus lwIP on an S3FH4R2 is tight. Power is the
  decisive one — BLE connected is single-digit mA, WiFi associated is an
  order of magnitude more with 100–300 mA bursts, which is a different
  battery and therefore a different enclosure (Stage 4).

  **Why later is genuinely better, not just cheaper.** ROADMAP's old reason
  for parking this — "don't build a transport before deciding where the
  brain lives" — has expired: **D1 is decided.** But deciding it changed
  what WiFi *is* here. While the host owns the brain, WiFi is a second way
  to do exactly what BLE already does, and it must coexist with a live
  link. After the runtime moves onto the device, the button needs
  **occasional sync, not a live link** — and periodic wake → connect → sync
  → sleep is precisely WiFi's good case, with no coexistence problem
  because there is no live BLE session to share the radio with. The same
  feature is expensive now and natural later.

  **The trigger.** Revisit when any of these is true: the button must reach
  a host that is not in the room (a real complaint, not a hypothetical);
  the Stage-3 spike (ROADMAP **3c**) reports RAM headroom that makes it
  comfortable; or Stage 4 picks a battery that can carry it. This is also
  what would change the calculus on item **8**.

  **The shape, if it is ever built.** A **config-time either-or, never
  concurrent** — one transport per boot, chosen like `--ble` is. Measure
  first (3c's idle/TX current and RAM numbers), build second. Do not start
  with a Dockerfile or a protocol change: the wire vocabulary is
  transport-agnostic already and should stay that way.

- **18. Move project management into Notion.** ⏸ Deferred deliberately, not
  dropped. Nothing is created in Notion and nothing should be until the
  split is chosen.

  **The risk is not the migration, it is ending up with two sources of
  truth.** Most of this file is *reasoning*, and the fresh-session pickup
  property lives in prose. Notion is not better at prose. What Notion *is*
  better at: status, priority, what is in flight, sequencing, and seeing
  the whole thing without scrolling.

  **Decide the split before creating anything:**

  - **A — Notion tracks state, TODO.md keeps reasoning.** One card per item
    (status / priority / gated-by / body-of-work), each linking to its
    heading here.
  - **B — migrate wholesale**, CLAUDE.md repoints at Notion, this file
    becomes an archive.

  **Recommend A**, because the fresh-session property is load-bearing and B
  puts it behind a network call and an auth prompt.

  **Trigger to revisit.** The chosen split written into
  [CLAUDE.md](CLAUDE.md) — one sentence saying which document a fresh
  session reads for what — and the items loaded. Without that sentence
  this is just a second backlog.

- Battery + deep sleep — the one thing that might justify a C++/NimBLE rework.
  **Now written up as item 29**, which was asked for directly; this line stays
  because the *battery* half is still parked and 29 says to measure first.
- Offline buffering of presses while disconnected (needs a time sync)
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

- **112. "Secret Message" - a private alphabet in dots, dashes and colour.**
  Asked 2026-09-05, filed **C-tier, for the release-day bank of apps** rather
  than for now. *"A person can use their own distinct combinations of dots,
  dashes, and colors to represent individual characters... they can print a
  small decoder sheet."*

  **Most of it already exists.** **83** shipped the message compiler: text ->
  stop list, with a colour ramp overlaid across the message and an editor
  widget. Secret Message is that compiler pointed at a **user-defined
  alphabet** instead of the Morse table - a map from character to
  `(symbols, colour)` - and it is therefore a *table plus a picker*, not a new
  runtime feature. It compiles to a stop list, so it installs into a package
  and plays standalone (111's "needs one compiler pass" column).

  **The genuinely new part is the decoder sheet**, and it is the reason to
  build the app at all: a printable page mapping each character to its symbol
  and colour, generated from the same table the button plays. That is a new
  *output* for the editor - a print stylesheet over generated HTML - and
  nothing else in the project produces paper. Cheap, but it is the work.

  **Two things to decide when it is picked up.** Whether an alphabet is a
  config object of its own (shareable, nameable, reusable across modes) or a
  field on the app - the pool pattern in CLAUDE.md argues for the former. And
  whether colour carries meaning *per character* or *per word*: per character
  multiplies the alphabet by the number of distinguishable colours and makes
  short messages possible, which is the point, but it is also the part a human
  reading the sheet will get wrong first.

- **115. Sync and Crowd Sync - one name over two very different problems.**
  Asked 2026-09-05: a light show that runs across several buttons - *"at
  sports games you can blast your teams colors in a gradient across the stands
  and even have coordinated lightshows."* Parked as **next-gen**, and blocked
  behind **116**, but the triage is worth keeping because the two halves cost
  wildly different amounts.

  **Split them, because one is nearly free and one is a product.**

  - **Sync** = several buttons, one host, one owner. The host already owns all
    state and already renders the show; making two lights show the same thing
    is not a clock problem, it is the *singular device seam* (see **116**).
    Cost is almost entirely 116's.
  - **Crowd Sync** = strangers, a server, and a shared clock. That is an
    account system, a backend, a phone doing the networking (the button has no
    internet and never will), and time base good enough that a 0.45 s strobe
    does not visibly scatter across a stand. ARCHITECTURE.md's latency budget
    is the arbiter here, not taste.

  **The stadium gradient is not a sync problem, and noticing that is the cheap
  first slice.** One LED is one pixel; "a gradient across the stands" is each
  button knowing *its seat* and looking up a colour. That is a lookup plus a
  join code - no coordinated animation, no tight clock - and it would demo
  most of the vision. Coordinated *animation* is the expensive half, and it
  wants a start-time-plus-show-description push (play show X starting at time
  T) rather than a stream of frames, so that jitter costs alignment and not
  the whole show.

  **The image-as-pixels idea belongs here**, not in 116: once each button
  knows a seat index, "each button is one pixel of an image" is the same
  lookup with a bigger table.

- **116. More than one button - the mesh, and apps that unlock at N.**
  Asked 2026-09-05: *"people can combine whatever number of buttons can
  realistically network together... certain apps would unlock when you have
  the minimum required number of buttons connected. When any button triggers
  a synced app, it takes over all of the others until the app is closed."*
  Parked as **next-gen**; it is the structural item **115** waits on.

  **The blocker is that "the device" is singular everywhere.** `main` holds
  one `ButtonDevice`; `BLEDevice` connects to one peripheral; the web UI shows
  one status line and one virtual panel; `config.json` is one button's gesture
  map. None of that is wrong today - it is exactly the interface segregation
  CLAUDE.md argues for - but every one of those is a place where "which
  button?" has no answer yet. **Decide the addressing model before writing
  any of it**, because it reaches config, the protocol and the UI at once.

  **One question decides the shape.** Is a second button *another device the
  host owns*, or *a peripheral of the first button*? Today's architecture says
  the first and is cheap; ARCHITECTURE.md's direction of travel (the brain
  moves onto the device) says the second and is not. The wrong answer is
  expensive after hardware ships - which is the standing reason this file
  cares about it early.

  **The cheap slice that needs no mesh at all**: an app declares how many
  buttons it needs, and the launcher hides the ones whose minimum is not met.
  That is a config field plus a filter over `launcher_targets`, it can be
  written and tested with a mock second device, and it is the piece every
  later idea assumes.

  **App ideas from the ask, triaged by what they are actually worth.** A full
  QWERTY across N buttons is an *advert*, and should be built as one - it is
  not a product. Bigger menus and a macro hub (keys/OSC/MIDI over several
  buttons) are the real use, and they reuse actions that already exist. A
  walkie-talkie / pager over morse is the one with a genuinely new
  requirement, and it is device-to-device messaging, which is the mesh itself
  rather than an app on top of it.


## Done

Everything that shipped completely has moved to
[TODO_FINISHED.md](TODO_FINISHED.md), per this file's own rule in "How to work
this list". Nothing lives in this section any more — check TODO_FINISHED.md
for the compressed record.
