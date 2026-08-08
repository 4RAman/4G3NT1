# Architecture: where the brain lives

**Decided.** The button has its own brain. The phone does the heavy lifting.
The phone (optionally backed by a cloud) is where preferences live.

This document settles ROADMAP **D1** and **D2** and derives everything that
follows from them: what must run on the device, what must never run there,
what an "app" actually is, and what happens when the pieces can't see each
other. [ROADMAP.md](ROADMAP.md) says *when*; this says *what*.

---

## The three tiers

| Tier | Runs | Owns | Must work when the others are gone |
|---|---|---|---|
| **Device** — the OS | The active app, gesture recognition, timing, rendering, local log | *Running* state | **Always.** This is the whole point |
| **Phone** — the companion | Authoring, the app library, network calls, sensors it has and the button doesn't | *Authoritative* preferences | Yes — a phone with no cloud is fully functional |
| **Cloud** — optional | App store, cross-device sync, long-term history, heavy AI | *Replica* only | n/a — nothing depends on it |

The PC web UI does not go away. It becomes a **peer of the phone**: the same
authoring surface, same protocol, aimed at the tinkerer rather than the
everyday user. That directly serves "deep options for tinkerers, smooth for
non-tech-savvy folks" — two surfaces, one contract, rather than one surface
compromising between them.

**Local-first, and no account required.** The cloud is a replica, never a
dependency. A button and a phone, out of the box, with no sign-up, is a
complete product.

---

## The forcing function: a latency budget

The tier split isn't a preference. It falls out of what a button has to feel
like:

| Path | Budget | Therefore it runs |
|---|---|---|
| Press → light and sound respond | **≤ 50 ms** | On the device. Always. No exceptions |
| Press → the event is durably recorded | ≤ 100 ms | On the device, to local flash |
| Press → an app decides what the press *means* | ≤ 50 ms | On the device |
| Press → the phone knows | ≤ 2 s connected; else next connect | Sync, best-effort |
| Press → a webhook actually fires | ≤ 5 s, phone required | On the phone |
| Press → an AI answers | seconds, phone + network required | Cloud |

Anything in the first three rows that needs a radio round-trip is a design
error. Anything in the last three that we try to put on the device is wasted
flash and battery.

**A derived hardware requirement.** For an alarm to fire correctly after a
day with no phone, the clock has to hold within a couple of seconds — roughly
20 ppm. The ESP32's internal RC oscillator is nowhere near that (percent-level
drift, which is over an hour a day). So: **an external 32.768 kHz crystal is a
BOM requirement**, or scheduled apps silently become unreliable exactly when
the product claims to be untethered. Verify whether the current ESP32-S3 Mini
populates one before trusting any disconnected-alarm test.

---

## What runs on the device

Eight things, and nothing else.

1. **Gesture recognition.** Debounce, timing, the tap/hold grammar.
   *Already here* ([trigger.py](firmware/trigger.py)) and already the right
   call — a 0.4 s double-tap window can't survive radio jitter. Grows to
   parameterised gestures (tap count, hold levels) and later IMU gestures.

2. **The clock and scheduler.** Time-of-day activations and alarms must fire
   with no phone in the room. Needs a real RTC, disciplined by the phone on
   every connect. *New* — today the host owns time entirely.

3. **The app runtime.** Loads app packages from flash, tracks which app is
   active, dispatches events, evaluates transitions, emits effects. Fixed
   memory budget: one active app plus the ambient layer, no dynamic
   allocation. This is "the OS." *New.*

4. **Mode resolution.** Ambient-vs-takeover, first-match-wins, the exact
   semantics in [rules.py](aibutton/rules.py) today. Pure, tiny, and it ports
   almost verbatim — which is the payoff for having kept it pure.

5. **Rendering.** LED effects and tones, driven by the active app rather than
   a fixed table of states. *Mostly here* ([led.py](firmware/led.py),
   [buzzer.py](firmware/buzzer.py)); needs ephemeral effects so apps own
   their own looks instead of sharing eleven global states.

6. **Persistent storage.** Installed app packages, their settings, and a
   local event ring buffer. The ring buffer is what actually breaks the
   tether: log locally, sync opportunistically, never lose a press because
   nothing was listening. *New* — the firmware drops disconnected presses
   today, and says so in a comment.

7. **Sync.** Config down, events up, time sync, and request/response for
   effects the phone has to fulfil. *Replaces* today's one-way command
   protocol.

8. **Power management.** Light sleep between events, wake on GPIO, connection
   interval duty-cycling.

### What must never run on the device

HTTP and webhooks · TLS · JSON parsing of user config · the app editor ·
analytics and history beyond the ring buffer · any model, ever · the app
store · anything that needs a name resolved.

One of those deserves its reasoning stated, because it's the non-obvious one:
**config is parsed on the phone, and the device receives a compiled binary.**
That keeps the device's parser (and its attack surface, and its flash
footprint) near zero, and it leaves the per-key fallback discipline in
[config.py](aibutton/config.py) exactly where it already works. The device
validates a checksum and a version, not a schema.

---

## What an app is

**An app is a state machine with expressions, compiled to a binary package.
It is not code.**

That is the load-bearing decision, and it's the one that makes everything
else possible: it runs on a microcontroller, it is safe to install from a
stranger, it can be analysed before it runs, and the same definition executes
identically on the device and on the host.

```
authored          JSON manifest — fields, defaults, states, transitions
   ↓  (phone/PC)
compiled          binary package — a few hundred bytes to a few KB
   ↓  (sync)
interpreted       identically by the device runtime and the host runtime
```

### Is that enough power? Test it against what already ships

The honest way to decide this is to check the six templates that exist, not
to argue from taste.

| App | State it keeps | What the runtime must therefore have |
|---|---|---|
| `actions` | none | event → effect map |
| `counter` | one integer | integer variable, increment |
| `stopwatch` | lap count, one running timer | elapsed-time read |
| `alarm` | ringing/snoozing, a one-shot timer | timers, re-entrant states |
| `pomodoro` | phase, block count, remaining, paused/pending | **modulo arithmetic** (`completed % blocks_before_long_break`), boolean conditions, a *pausable* countdown |
| `metronome` | ring of 8 tap timestamps | **bounded buffer, float mean, and a computed effect parameter** (LED period = f(BPM)) |
| launcher *(0a)* | selected index | enumerate installed apps, enter by index — *privileged* |

`metronome` is the stress case and it's the one that settles the design: a
static transition table cannot express "average the last eight intervals and
make the light pulse at that rate." So the runtime needs **expressions**, not
just transitions.

It does **not** need loops, recursion, dynamic allocation, or a heap. Every
app above runs in bounded time and bounded memory. That's the line:

> **Bounded by construction.** No unbounded loops, no allocation, no
> recursion. Worst-case execution time is knowable before the app runs.

Which is exactly what makes an app store safe without a review team.

### The pieces

```
states        named; each with an entry effect list
events        gesture · timer expiry · schedule fire · sync reply · sensor
variables     a small fixed set of ints/floats + one bounded ring buffer
expressions   arithmetic, comparison, boolean — no calls, no side effects
transitions   (state, event, guard) → (state, effects)
effects       Show(look) · Play(sound) · Log(name) · Timer(set/cancel)
              Enter(app) · Exit() · Request(payload)   ← the escape hatch
```

`Request` is how an app reaches anything the device can't do. The device
emits it, the phone fulfils it — a webhook, an AI call, an SMS, a lookup —
and answers with an event the app can transition on. Every "smart" feature
in Stage 6 arrives through that one hole, and the device learns nothing about
HTTP.

### What this deliberately cannot express

Arbitrary computation. A Simon-Says memory game needs to emit a generated
sequence; a Morse decoder needs a lookup table over a variable-length buffer.
Some of that is reachable with a bounded buffer and a table effect; some
isn't. Three answers, in order of preference: push the work to the phone via
`Request`; extend the effect set (a system-wide decision, not an app's); or —
rarely, and reviewed — ship it as a **native app** compiled into the
firmware, never through the store.

Do not solve this by adding a scripting language. That trade has been made
here deliberately, and reversing it later means either abandoning the on-device
runtime or shipping an unsafe app store.

### Two privilege levels

- **User apps** — the store's output. May emit any effect except `Enter` on
  an arbitrary app, and may only touch their own state.
- **System apps** — the launcher, settings, pairing. Ship with the firmware,
  may enumerate and enter other apps.

That boundary is the app-store security model, and it's why the launcher
(TODO 0a) is a system app rather than a clever user app.

---

## Who owns which truth

Designed so a merge conflict is impossible rather than resolvable:

| Data | Source of truth | Direction | Conflict rule |
|---|---|---|---|
| App library, settings, palettes | **Phone** | phone → device | Generation counter; higher wins. The device never edits config |
| Live app state (count, elapsed, tempo) | **Device** | device → phone | Device is authoritative; the phone only observes |
| Event log | **Device** until drained | device → phone → cloud | Append-only, monotonic ids; drain is idempotent |
| Wall-clock time | **Phone** | phone → device | Device disciplines its RTC on every connect |
| Installed app packages | **Phone** (from cloud store) | phone → device | Content-addressed; the device asks for what it's missing |

**Config never flows upward, and app state never flows downward.** An app
that wants to remember something writes app state, not config. That single
rule removes the entire class of sync bugs the product would otherwise spend
Stage 4 debugging.

---

## Degradation

The table the product is actually judged on:

| Available | What works |
|---|---|
| Device alone | Everything except `Request` effects. Apps run, alarms ring, presses log to the ring buffer, LED and sound are full-speed. `Request` effects queue if the app marks them deferrable, else fail visibly |
| Device + phone | Add webhooks, AI, notifications, live config edits, log drain, time sync |
| Device + phone + cloud | Add the app store, cross-device sync, long-term history, heavy compute |
| Phone alone (button flat or out of range) | Read history, edit config, install apps. Changes apply at next connect |

The first row is the promise. Everything else is additive.

---

## Budgets

Targets to design against, and the things Stage 3's power spike must measure
rather than assume:

| Resource | Target | Note |
|---|---|---|
| App package | ≤ 2 KB typical | 50 apps well under 100 KB of flash |
| Event ring buffer | 8k events | ~128 KB at 16 bytes/event; days of use offline |
| Runtime RAM | ≤ 32 KB working set | One active app; no allocation at run time |
| Press → local feedback | ≤ 50 ms | Non-negotiable |
| Idle battery | 7 days for the Stage-4 demo | 30 days is the aspiration, and probably needs the C question answered |
| Clock drift, disconnected | ≤ 2 s/day | Drives the crystal requirement above |

**Storage is a non-issue; RAM headroom and power are the real constraints.**
Which is where the "lower-level language" instinct from the original brief is
right — but about the **device runtime**, not the host, and the deciding
factors are RAM and fine-grained radio/sleep control (NimBLE), not execution
speed. Measure first: if MicroPython holds the runtime, the storage layer and
the sync protocol inside budget with light sleep working, it stays.

---

## What this does to today's code

| Today | Becomes |
|---|---|
| [rules.py](aibutton/rules.py), [scheduler.py](aibutton/scheduler.py), [trigger.py](firmware/trigger.py) | The device runtime's core. Already pure — they port, they don't get rewritten. This is the payoff for the existing discipline |
| [config.py](aibutton/config.py) parsing | Stays host-side, gains a **compiler** to the binary package format |
| `main.py`'s `run_*` takeover loops | Become app *definitions*. The biggest single change, and the one that ends the "an app costs six files" problem |
| [device.py](aibutton/device.py)'s `ButtonDevice` seam | **Inverts.** "Host commands device" becomes "host syncs with device." The four-method feedback interface becomes a sync protocol |
| The web UI's virtual device | Becomes the **host-side interpreter** — no longer a dev convenience but the reference implementation and the conformance-test harness |
| [webui.py](aibutton/webui.py) | The tinkerer's authoring surface; the phone app is the everyday one. Same API |

Two interpreters, one spec, guarded by a shared conformance suite — the same
discipline [test_protocol.py](tests/test_protocol.py) already applies to the
wire, for the same reason.

---

## Getting there without breaking Stage 2

Each phase is independently useful and nothing gets thrown away.

| Phase | Work | Visible change | Risk |
|---|---|---|---|
| **A** | Define the app format. Build the **host-side** interpreter. Migrate the six templates onto it behind the existing UI | **None** — same behaviour, same tests | Low. Pure host-side. **Start here** |
| **B** | Protocol v1: capability negotiation, ephemeral effects, parameterised gestures, OTA handshake (TODO 0b) | Per-app colours; richer gestures | One reflash |
| **C** | Port the interpreter to firmware. Apps run on-device, PC still acts as "the phone" | Presses feel instant; feedback survives a stalled host | Medium |
| **D** | On-device storage, event ring buffer, RTC | **The tether breaks.** Alarms ring with the PC asleep | Medium |
| **E** | Phone app takes over from the PC host | The product | Highest, and by then everything under it is proven |

Phase A is the one to start now, and it's worth being explicit about why:
it's entirely host-side, it's fully testable with the existing suite, it
delivers the "adding an app touches one file" win on its own, and it makes
every later phase a port rather than a design.

---

## Deliberately unresolved

- **Cloud identity and the store's economics.** Stage 5. Nothing above
  depends on the answer, which is the point of local-first.
- ~~**Whether the phone app is native or a PWA.**~~ **Resolved: it cannot be a
  PWA.** The check was Web Bluetooth support, and the answer is that no browser
  on iOS has it — Safari does not implement it, and every other iOS browser is
  WebKit underneath, so "use Chrome instead" is not an escape. Firefox declined
  on desktop too. A PWA companion would be Android-and-desktop only, which is
  not a phone app. So: **native, or a native shell with a BLE bridge.** Still
  doesn't change any contract here — the sync protocol is the same either way.

  What Web Bluetooth *is* good for is the tinkerer's surface, where
  Chrome/Edge/Android is a fair ask: a hosted or offline page that pairs with
  the button directly, with no service and no server holding the radio. That is
  a small delta on [build_editor.py](tools/build_editor.py) — a third `*Api`
  implementation beside `ConfigApi` and `FileApi` — and it is the honest
  prototype for the phone app's authoring half.
- **How many apps can be *installed* vs *reachable*.** Flash says hundreds;
  the launcher's UX says maybe a dozen before cycling gets tedious. That's a
  design problem for the launcher, not a capacity one.
- **Multi-button households.** One phone, several buttons, is a natural
  extension of this model. Button-to-button remains parked.
