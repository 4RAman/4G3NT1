# Roadmap

This is the **forward-looking** document — the stages, the gates, and the
decisions that get expensive if deferred. [ARCHITECTURE.md](ARCHITECTURE.md)
is the target design the later stages build toward, and settles **D1**/**D2**
below. [DESIGN.md](DESIGN.md) and [DESIGN-ESP32.md](DESIGN-ESP32.md) are
history — the two transitions that got the code to its current shape.
[TODO.md](TODO.md) is the current sprint. [CLAUDE.md](CLAUDE.md) is how to
write code here.

**Where we are: Stage 2.** The hardware works, the mode machine works, twelve
templates ship, the suite is green with no hardware attached.

---

## The product in one line

> A single button whose meaning is defined by **swappable apps**. No screen,
> no keyboard, no second control — every peripheral we ever add must make the
> button *smarter*, never give it an interface.

That last clause is the design's spine and the test every future feature has
to pass. A speaker that reads a notification back to you makes the button
smarter. A speaker that plays a menu you navigate with presses is a screen
with extra steps.

## Principles, written so they can fail a review

| Principle | The test it has to pass |
|---|---|
| **Simple to use, deep to tinker with** | A non-technical user installs an app and uses it without reading anything. A tinkerer changes any parameter of that same app in the same UI. Neither one sees the other's surface. |
| **Apps, not features** | Shipping an app touches the app's own files and its test. If it touches the core, it isn't an app — it's a core change, and it needs to justify itself as one. |
| **Flexibility over feature count** | New capability arrives as *data* (a manifest, a descriptor), not as a branch in the editor or the run loop. This is the existing Open/Closed rule in [CLAUDE.md](CLAUDE.md), applied to apps. |
| **One button, one light** | Nothing in the design assumes a screen, a keyboard, or a second button — including the recovery paths, which are the ones that quietly assume a laptop. |
| **Nothing is extracted from the user** | No ads, no telemetry, no analytics that leave the machine, no account required to use what you bought. The test: unplug the network and the product is undiminished except for the features that are *obviously* network features (webhooks, AI, the store). |
| **Ship the demo before the paradigm** | No Stage-3 refactor is allowed to block Stage 2. If the two conflict, Stage 2 wins and Stage 3 absorbs the cost. |

The fifth one is a product promise, not a nicety, and it settles a question
that was open: **analytics are local.** [TODO.md](TODO.md) item 12 asks what
"improve performance" means; whatever it turns out to mean, the data stays on
the user's own machine. Usage history is the user's, the button does not phone
home, and "local-first, no account required" in
[ARCHITECTURE.md](ARCHITECTURE.md) is the same promise stated from the other
end. It also rules out the easy version of a Stage-5 business model, which is
worth knowing now rather than discovering after building one.

---

## The six stages

| Stage | Goal | Exit gate — a thing you can actually check |
|---|---|---|
| **1 Conception** ✔ | It works | Physical press → mode machine → LED/sound. Done. |
| **2 MVP / demo** ← *here* | One button, loaded with apps, smooth | See below |
| **3 App runtime** | Apps become portable, swappable, safe | A new app ships as one file + one test, touching no core file |
| **4 Product demo** | Rechargeable, portable, ergonomic key fob | Works for a full day with no PC in the room |
| **5 Business** | Market, IP, manufacturability | Provisional filed before public disclosure; BOM costed; OTA update proven |
| **6 Ecosystem** | Peripherals that make it smarter | Each new sensor ships as a capability old firmware can ignore |

---

## Stage 2 — MVP / demo (current)

**Goal:** load a button with as many apps as it will fit, live with it, tweak
until it's smooth. No architecture changes. The sprint list is
[TODO.md](TODO.md).

### Reaching the apps ✔ solved, twice

Gestures do not scale as a menu: five of them, minus one kept for everyday
logging, reaches four apps — and every extra tap count slows the shorter ones.
Two things fixed that and both shipped.

**The launcher** (TODO 0a) — a takeover entered by one gesture that cycles
every installed app in that app's own colour. It needed the one thing the core
lacked, a takeover able to enter another takeover, and it set the rule the
whole system now follows: **long press means "up one level", everywhere.**

**The control surface** (2026-08-19) — a takeover whose four gestures each fire
their own action, any of which can open another one. So a *tree* of menus now
costs no new code. The two are complementary and both should survive: a
launcher needs no configuration and never goes stale, a control surface is
explicit and can say exactly what you want where. Which is the default front
door is TODO **26**.

### Stage 2 exit gates

- [ ] **10 apps**, verified end-to-end on real hardware (TODO items 2, 7) —
      **eleven exist** and ten are verified. Hot/Cold and Reaction were walked
      on 2026-08-19, which also confirmed the firmware 0.6.1 press-timing fix
      end to end. **Signal and the control surface have never met the button**
      — both host-side with no clock in them, so low risk, but that was equally
      true of the offline editor while it was silently broken
- [x] **A launcher**, so all 10 are reachable without the web UI — one
      gesture opens a menu that cycles every installed app in its own
      colour. Long press means "up one level" throughout, so leaving an app
      lands back in the menu and leaving the menu goes home
- [ ] **A naive-user run**: someone who has never seen it installs an app and
      uses it, unaided, while you keep your mouth shut and take notes
- [ ] **24-hour soak** with no manual restart, no wedged BLE, no lost presses
- [x] **Single-instance guard** — an OS-level file lock; a second copy
      refuses with the holder's PID instead of fighting for the radio
- [x] **Verified power-cycle recovery** — reconnected cleanly on a real
      replug, and `DEVICE_INFO` is re-read on every reconnect, so a board
      reflashed mid-session is not assumed into its old capabilities
- [x] **Protocol v1 frozen** (see below) — the one architectural task Stage 2
      must not defer, and it is done: capability negotiation, ephemeral
      effects and parameterised gestures shipped, OTA and hold levels
      reserved. **Everything else on this page is now reachable without a
      reflash**, which is the property that was actually being bought

### Freeze the protocol *before* you build more hardware

Four cheap additions now cost one reflash. The same four after units exist in
other people's hands cost a flag day, or a permanent compatibility branch.
Land them as one revision, then freeze:

1. ~~**`DEVICE_INFO`**~~ ✔ **shipped.** A read carrying protocol version,
   firmware version and a capability bitmap (led · buzzer · palette, with
   haptics/battery/imu/mic/ota reserved). Bits report what actually came up,
   not what `hardware.py` asked for. This is what makes every *later*
   protocol change non-breaking — a new host asks an old device what it can
   do instead of assuming — and it is why the remaining three below are now
   negotiable additions rather than a flag day. (**D5**, **D8**)
2. ~~**Parameterised gestures**~~ ✔ **shipped.** The wire carries
   `[kind, param]` beside the three original codes, which are frozen and
   still emitted for the gestures that have always had them. So 5-tap and
   triple-tap now arrive as *data* — a `TriggerType` member and a `GESTURES`
   entry — with no reflash under them. Hold levels have their kind code
   claimed (`GESTURE_HOLD`) and are not implemented: the detector emits one
   hold, and raising that is firmware work whenever something wants it.
   (**D5**)
3. ~~**Ephemeral effects**~~ ✔ **shipped.** `LED_EFFECT` renders a look
   immediately and stores nothing, so a per-app appearance costs a write
   rather than a byte of a 255-value namespace mirrored four ways. `0x0B` is
   still the highest LED state code. (**D4**)
4. **OTA hook** — ✔ *reserved*: `OTA_CONTROL_UUID` and `CAP_OTA` are claimed
   and documented as unimplemented, and the version handshake is `DEVICE_INFO`'s
   first byte. The implementation is still Stage 4 and still gates shipping a
   unit to anybody. (**D6**)

---

## Stage 3 — The app runtime

The original brief called this "efficiency, possibly a lower-level language."
That aim is right and the diagnosis needs adjusting:

> **The host's speed is not the problem.** The host is a PC handling a few
> events a day. Rewriting Python that runs once per button press buys
> nothing. The only place efficiency is real is the **ESP32's battery**, and
> there the lever is *radio duty cycle and sleep*, not language choice.
> MicroPython → C might win boot time and RAM. It will not win battery life
> while the radio holds a connection.

So Stage 3 is not a rewrite. It is the three things that make Stages 4–6
possible, and the reason to do them now is that every app written before them
gets rewritten after them.

Stage 3 is **Phase A** (and the start of **B**) of the migration sequence in
[ARCHITECTURE.md](ARCHITECTURE.md) — the entirely host-side half, which is
why it can start immediately and carries almost no hardware risk.

### 3a — Apps become declarative and pure

Today a rich app is a **4-to-6 file change**:
`config.py` (dataclass, parser, allow-list, serialiser, union) ·
`main.py` (a `run_*` coroutine, two `isinstance` chains, an import) ·
`schema.js` (template, takeover set, built-in) · then the tests.

It was 6-to-9 until protocol v1: a new LED state, mirrored four ways, used to
come with the territory and no longer does — an app pushes a look instead.
That is the cheap half of the tax gone. The expensive half is the list above,
which is still not hot-swappable and still nowhere near a third-party app
store, because every one of those files is a place an app author cannot
reach.

The fix is not a new paradigm — it's [CLAUDE.md](CLAUDE.md)'s existing one
applied to the one place it isn't: **a pure core with I/O injected at the
edges**. [rules.py](aibutton/rules.py), [scheduler.py](aibutton/scheduler.py)
and [trigger.py](firmware/trigger.py) already work this way. The takeover
loops in [main.py](aibutton/main.py) do not — they're async coroutines that
own the device, the store and the clock directly.

Target shape:

```
manifest (data)   what the app is called, its fields, defaults, allowed
                  activations, the looks it uses — JSON, no code

step function     (state, event, now) -> (state, [effect], next_wake)
                  pure; no await, no device, no store, no clock

driver            the one thing that owns asyncio, the device and the store,
                  and turns effects into I/O
```

Effects are a closed set — `Show(look)`, `Play(sound)`, `Log(name)`,
`Timer(...)`, `Call(webhook)`, `Enter(app)`, `Exit()`. That single decision
buys four things at once:

- apps are **testable without asyncio**, the way `rules.py` already is;
- apps are **portable** — the same step function can be driven by the Python
  host today and by an on-device interpreter later (see **D1**);
- apps are **safe to install from strangers**, because effects are the only
  way to touch the world (see **D2**);
- adding an app stops touching the core, which is the Stage-3 exit gate.

Migrate the existing eleven takeover templates onto it one at a time, keeping
the tests. `launcher` is the honest canary now: it is the one template that
chooses *another* app, so whatever the runtime does about one app starting
another has to express it.

**Two of them are already in this shape and are worth copying from.**
[hotcold.py](aibutton/hotcold.py) and [reaction.py](aibutton/reaction.py) are
pure `step(state, event, now)` functions over a small closed effect set, with
the `run_*` loops reduced to drivers that own the clock, the queue, the die
roll and the store. They were written that way deliberately, as the canary for
this stage rather than as a game-specific flourish — including the detail that
randomness is *passed in* so `step` stays a total function checkable against a
table. Whatever the manifest format turns out to be, those two should need a
manifest and nothing else.

### 3d — Apps own data, not just history

**The gap, named 2026-08-19.** The only persistence in the system is the
append-only event log. A counter's value is not stored — it is recounted from
rows (`count_today`). A Signal's position is session state and dies when you
leave. Nothing an app knows survives except as history.

That is why **actions and modes feel like separate ideas when they should not
be**: an action can only ever *append*. It cannot read a value, and it cannot
change one. So "add one to my smoking counter" is expressible only as "write a
row that something else will later count", and "set the thermostat preset to
3" is not expressible at all.

**The fix is a small durable document per app instance**, and one new effect
family to read and write it. Not a database — a bounded bag of named values,
because this has to survive the move onto a microcontroller where unbounded
growth is not an option (**D2**: an app is data, bounded by construction).

**Keep both, and keep them separate.** The log is *history* — streaks, "when
did I practise and how fast", export. The document is *current value*. Merging
them loses one of the two: a log cannot answer "what is it now" without a scan,
and a document cannot answer "what happened in March" at all.

Three things fall out of it, and the third is the one that changes the product:

1. **App state survives leaving the app.** A Signal reopens where you left it;
   a counter has a value rather than a query.
2. **The step function's `state` gets a durable sibling.** `(state, event, now)`
   stays session state; the document is what an app deliberately keeps.
3. **Actions can be bound to an app without entering it.** "Smoking +1" becomes
   a thing any gesture in any mode can fire, which is exactly TODO **15**
   ("counting without entering an app") and is the strongest argument for the
   whole idea.

**Which gives actions a taxonomy** (decided 2026-08-19, with **D9**):

| Family | What it is | Where it comes from |
|---|---|---|
| **System** | `log`, `timer_toggle`, `webhook`, `osc`, `midi`, `enter_mode` | Always available; the primitives |
| **Custom** | Named user compositions, including sequences | A pool in config, referenced by name — the same move `looks` already made |
| **App-bound** | "Smoking counter +1", "Pomodoro: skip block" | Offered **only when that app exists in the list**, because an action naming an app you deleted is a broken binding waiting to happen |

The third family is the one that needs the document to exist first — it is
"reach into that app's data", and there is no data to reach into today. The
second is cheap and could be done now. **Do not build the UI for any of this
before the data model is decided**; a tab designed around an object that does
not exist yet gets rebuilt.

**The sequence caveat, restated because it is the thing most likely to go
wrong.** A custom action that is a *sequence* must stay a flat list with
optional delays — no loops, no conditionals, bounded nesting or none. The
moment it grows an `if`, it is a language, and the on-device runtime cannot run
it, which makes it host-only forever — the exact thing this stage exists to
escape. Sequences earn their place where the target is **local and dumb**
(MIDI, OSC, the LED), not where it is a network service that can orchestrate
for itself; that is what the `webhook` rule has always said.

### 3b — One manifest, served

Capability is declared twice today — [schema.js](aibutton/web/static/schema.js)
and [config.py](aibutton/config.py) — and LED states four times. The protocol
mirroring is deliberate and tested (two runtimes, one ships to a
microcontroller). The schema mirroring is not: both halves run on the host.

Serve the manifest from Python over `/api/schema` and have the editor render
from it. A third-party app author cannot be asked to patch the host's
JavaScript bundle. (**D3**)

The honest caveat: `schema.js` holds *functions* — `describe()`, `defaults()`,
dynamic `options()`. Those don't survive JSON. The split is data (fields,
types, ranges, labels, hints, allowed activations) into the manifest,
presentation functions staying in JS keyed by type with a generic fallback.
Budget for the fallback being uglier than the bespoke summaries.

### 3c — Power architecture spike (measure, then size)

**D1 is settled** — the device runs its own brain, so the old worry (a press
on a sleeping button taking 1–3 seconds to reach the host) no longer touches
responsiveness: the app is already running locally and the light responds in
under 50 ms regardless of what the radio is doing. What the spike sizes now
is the *budget*, not the architecture.

Instrument the current firmware for: idle-connected draw, advertising draw,
light-sleep draw, wake latency from light sleep, and RAM headroom with the
BLE stack up. Those four numbers decide two things — whether MicroPython
holds the runtime plus storage plus sync inside budget, and what battery
Stage 4's enclosure has to fit. Targets are in
[ARCHITECTURE.md](ARCHITECTURE.md)'s budget table.

**Check the crystal while you're in there.** Untethered alarms need ~20 ppm
timekeeping; the ESP32's internal RC oscillator drifts percent-level, which
is over an hour a day. If the board doesn't populate a 32.768 kHz crystal,
disconnected scheduling is unreliable and that is a BOM item for Stage 4, not
a firmware bug.

### Stage 3 exit gate

A new app ships as **one manifest + one pure step function + one test**,
touching no core file, and runs unmodified on both the host driver and a
device-side driver stub.

---

## Stage 4 — Product demo

This is **Phases C, D and E** of [ARCHITECTURE.md](ARCHITECTURE.md): the
runtime moves onto the device, the device gets storage and a real clock, and
the phone takes over from the PC. A key fob that stops working when you leave
your desk is not a key fob, and Stage 4 is where that stops being theoretical.

- Battery + charging (wireless is Stage 6; USB-C is fine here)
- Enclosure: ergonomic, pocketable, light pointing **back at the user** —
  a real optical constraint on LED placement and diffusion, worth prototyping
  before the enclosure is drawn
- Light sleep with wake-on-press, sized by 3c's numbers
- **A 32.768 kHz crystal on the BOM**, or scheduled apps drift out of
  usefulness the moment the phone is away
- **Field firmware update working end to end** (**D6**) — do not ship a unit
  to anyone, including a friend, without it

**Gate:** carry it around for a full day, away from any PC or phone, and it
still does its job — [ARCHITECTURE.md](ARCHITECTURE.md)'s first degradation
row, demonstrated rather than asserted.

---

## Stage 5 — Business

Start thinking about this in Stage 3, as the brief says. Concretely, three
things that constrain engineering *before* Stage 5:

**Manufacturability.** One MCU, no exotic parts, no hand-tuning per unit,
firmware flashable on a production line, and every device individually
addressable. If any of these is false at the end of Stage 3, Stage 5
discovers it as a redesign.

**IP — not legal advice, and worth an hour with someone who does this.** The
honest read: "a button that does something" is old, and the prior art is
thick (Flic, Amazon Dash, bttn, Home Assistant's button integrations,
Stream Deck). What might be defensible is the *system* — a gesture grammar
resolved against declarative apps, split so a constrained device renders
host-authored behaviour and falls back to a local runtime when the host is
gone. Two facts that matter more than the odds:

- **Public disclosure starts a 12-month US clock and immediately forfeits
  most non-US rights.** A demo video, a Kickstarter page, a public repo, a
  conference table. If a provisional is wanted at all, it goes in *before*
  the first public showing.
- **The real moat is the ecosystem and the brand**, not the claim. Apps that
  only run here, and a name people ask for. Which brings up:

**The name (D7).** "AI Button" is descriptive — weak as a trademark — and
inaccurate, since [DESIGN-ESP32.md](DESIGN-ESP32.md) deliberately removed the
AI. It is currently baked into the package name (`aibutton`), the default BLE
name (`AIButton`), the docs, and it would become the app-store namespace.
Rename before public disclosure, not after.

**App store legal surface.** You would be distributing other people's code to
other people's devices. **D2** — declarative apps with a closed effect set —
is what makes that tractable instead of terrifying.

---

## Stage 6 — Peripherals and ecosystem

Everything here is gated on the capability model from protocol v1: the device
advertises what it has, the host adapts, old firmware ignores what it doesn't
understand. No peripheral is allowed to become a hard dependency of the core.

Each candidate against the one-line test — *does it make the button smarter,
or does it give the button an interface?*

| Peripheral | Verdict | Note |
|---|---|---|
| Haptics | Smarter | Feedback with no light and no sound — works in a pocket, in the dark, in a meeting |
| Pressure sensitivity | Smarter | Widens the gesture grammar without adding a control |
| IMU / gyro gestures | Smarter | Shake, flip, orientation — the biggest vocabulary win available |
| GPS / geofencing | Smarter | Location as an *activation*, which the mode machine already has a slot for |
| Mic (record / voice note) | Smarter | Capture, not conversation. Transcription is a host/webhook concern |
| Speaker (readback) | **Careful** | Reading one thing back is fine. A navigable audio menu is a screen |
| Laser pointer | Smarter | Genuinely output-only |
| Wireless charging | Neutral | Convenience; no design impact |
| Air quality / environment | Smarter | Sensors as activations, same slot as geofencing |
| MIDI | Smarter | The metronome app already proves the timing path |
| Any display | **No** | Violates the spine |
| An AI assistant | Smarter, *host-side* | Already possible via `webhook`. It stays an integration, never a model on the device |

**Three rows of that table say "sensors as activations, same slot as
geofencing", and there is no such slot.** An activation is a clock or a press;
nothing in the system can be started by a fact about the world. TODO **70**
builds that slot on the host — years before any of this hardware — and the
sensor need not be on the button at all: a plant's moisture probe posting to
the service is the same shape as an IMU that does not exist yet. **Every
peripheral above lands cheaper if the slot is already there**, which is the
argument for doing it in Stage 2 rather than waiting for Stage 6 to discover
it.

---

## Cross-cutting decisions

The point of this table is the last column. Each of these gets *more*
expensive to answer the longer it waits, and several of them are the "going
back and undoing things" the brief is trying to avoid.

| # | Decision | Recommendation | Answer by | Cost of deciding late |
|---|---|---|---|---|
| **D1** ✔ | Where does the brain run when the PC is asleep? | **Decided: on the device.** It runs the OS and the active app; the phone (optionally cloud-backed) holds preferences and does the heavy lifting. See [ARCHITECTURE.md](ARCHITECTURE.md) | — | — |
| **D2** ✔ | Is an app code, or data? | **Decided: data.** A state machine with expressions, compiled to a binary package — bounded by construction, never arbitrary code. See [ARCHITECTURE.md](ARCHITECTURE.md) | — | — |
| **D3** | One schema or two? | **One manifest, served over `/api/schema`** | Stage 3 | Every third-party app needs a patch to the host's JS bundle |
| **D4** ✔ | Per-app looks, or global LED codes? | **Decided and shipped: ephemeral effects, semantic states kept few.** A look is a write, not a byte; `0x0B` is still the highest code. Where the looks are *stored* is TODO item 3 and is now host-side work | — | — |
| **D5** ✔ | Fixed gestures, or parameterised? | **Decided and shipped: kind + parameter**, beside the frozen originals. Tap counts are data now; hold levels have their code reserved and are unimplemented | — | — |
| **D6** | Field firmware update | **Reserve the handshake in v1; implement before any unit leaves the building** | v1 now, working by Stage 4 | You cannot fix a bug in someone else's key fob |
| **D7** | The name | **Rename before public disclosure.** `aibutton` is descriptive and inaccurate | Stage 4/5 boundary | Repo, package, BLE name, app namespace, domain and marks all re-bake |
| **D9** ✔ | Do apps own data, or only write history? | **Decided: a small bounded document per app instance, beside the log** — slots declared in the manifest, read like variables, written by a `Set` effect. See ARCHITECTURE.md "Apps own data"; build items are TODO **33**/**34** | — | — |
| **D8** ✔ | How do hosts and devices stay compatible? | **Decided and shipped: capability negotiation via `DEVICE_INFO`** — never assume, always ask. Protocol v1 | — | — |
| **D10** ✔ | Is a trigger a *field on a mode*, or an *object of its own*? | **Decided 2026-08-26: an object.** A *reflex* is a circumstance with an action attached, and it settles this because **most reflexes start no app at all** — "the DAW began recording, so change the light" enters no mode and has no mode to be a field on. A reflex's `then` is any action the button already has, so this adds a source of events and **no new vocabulary of consequences**. **Schedules are deliberately not migrated**: an activation says when an app may run, a reflex says what makes something happen. TODO **70**–**75**, **77**–**79** | — | — |

**D4, D5 and D6 were one piece of work with D8 — and D8 went first, on
purpose.** The reason to batch protocol changes is that each one costs a
reflash and a chance to drift the mirrored tables, which is ruinous once units
are in other people's hands. But `DEVICE_INFO` is the one whose whole job is to
make the *others* non-breaking. With it shipped, D4 and D5 arrived as
capability-gated additions an old device can decline, rather than a flag day —
a batch of two, negotiable, instead of a batch of four that had to be perfect
first time. Both landed together, in one reflash, as intended.

That reasoning does not generalise. Anything that is *not* a
negotiation mechanism still batches.

**What the freeze means for the next change.** The bar is no longer "is this
cheap now?" — it is a capability the device physically cannot express. Both
of the taxes that used to push work onto the wire are gone: an app's own look
is a write, and an app's own gesture is a `TriggerType` member. If a proposal
wants a new characteristic, check first that it is not really one of those.

---

## Architecture: where this is going

Full design in [ARCHITECTURE.md](ARCHITECTURE.md). In one picture:

```
        today                                    target

  ESP32          PC                  BUTTON              PHONE            CLOUD
  ┌────────┐    ┌──────────┐        ┌────────────┐    ┌───────────┐   ┌──────────┐
  │ detect │───▶│ decide   │        │ detect     │    │ authoring │   │ app store│
  │ render │◀───│ store    │        │ run the app│◀──▶│ prefs     │◀─▶│ sync     │
  └────────┘    │ web UI   │        │ render     │    │ webhooks  │   │ heavy AI │
    dumb        └──────────┘        │ log locally│    │ AI calls  │   └──────────┘
                host must be        └────────────┘    └───────────┘    optional
                awake               works alone        heavy lifting
```

What stays true across the move — and is therefore safe to build on now:

- The **mode machine** is the model. Gestures resolve against apps; exactly
  one app owns the button at a time.
- The **pure core** is the portable part. Anything side-effect-free survives
  the move unchanged; anything that awaits a device does not.
- **Config is the source of truth**, versioned and hot-reloadable.
- **A bad config never crashes anything**, per-key fallback, warnings surfaced
  to the editor.
- **Mirrored tables are tested, not trusted.**

What changes: *"the host owns state, the device renders it"* becomes *"the
device owns the running app; the phone owns preferences, history and
integrations."* That is the single biggest invariant flip on this roadmap,
and it is now **decided** rather than pending — which is what makes Phase A
worth starting before anything else.

---

## Deliberately not doing yet

Elevated from [TODO.md](TODO.md)'s parking lot, with the reason each is
parked:

- **WiFi transport** — the old reason to park this ("don't build a transport
  before deciding where the brain lives") has expired: **D1 is decided.** It is
  still parked, for a better reason. While the host owns the brain, WiFi is a
  second way to do what BLE already does and has to share one radio with a live
  link. After the runtime moves onto the device the button needs *occasional
  sync*, which is WiFi's good case and has no coexistence problem at all. Same
  feature, expensive now and natural later. Trigger conditions and the power /
  RAM numbers it waits on are [TODO.md](TODO.md) item **21**.
- **Offline press buffering** — needs a time sync, and is a subset of D1.
- **Phone app** — the REST API already supports it; it's a Stage 3/4
  deliverable once D1 says what the phone actually *is* (a host, or a remote
  control for a device that no longer needs one).
- **Button-to-button communication** — a genuine architecture change (today's
  model is one host, one button). Parking-lot-worthy even after the
  recorded-communication mode exists.
- **A second control surface (MCP or similar)** — the webhook action covers
  what the button is for. Revisit when something concrete wants it.
- **Rewriting the host in a lower-level language** — see Stage 3's opening.
  Revisit only if profiling on real hardware says otherwise.
