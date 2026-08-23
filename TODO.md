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

Before touching code: read [CLAUDE.md](CLAUDE.md), and run the suite before and
after.

```bash
.venv/Scripts/python -m pytest -q
```

Only one instance may run (BLE allows a single central). If you need to restart
the service to pick up a change, **confirm first** — it may be live against the
real button.

## Where Stage 2 stands

[ROADMAP.md](ROADMAP.md)'s exit gates, scored 2026-08-22.

| Gate | State |
|---|---|
| Protocol v1 frozen | ✔ **0b** |
| Single-instance guard | ✔ |
| Verified power-cycle recovery | ✔ reconnected cleanly on a real replug |
| A launcher | ✔ **0a** |
| **10 apps** verified on hardware | **eleven built.** Ten verified; **Signal and the control surface have never met the button** |
| **A naive-user run** | not started; unblocked since **14** |
| **24-hour soak** | not started |

**Nothing left is blocked on design.** What remains is hardware time (**0c**,
the soak, walking Signal) and one person sitting down with the button (**14**'s
naive-user run). No amount of code moves those three.

## Six bodies of work, not twenty items

The numbered list is right for picking one item up cold and wrong for deciding
what to do next. This is the other view.

| Body of work | Items | State |
|---|---|---|
| **The colour engine** — named looks, ramps, the safety floor | 3 ✔, 4 ✔, 0b·3 ✔ | Done |
| **The light as a language** — ladder, stop list, one primitive | 19 ✔, **36** ✔ | Done; **19c** (a repainting tick for Pomodoro) is the one thread left |
| **The gesture engine** — N taps, hold levels | 0b·2 ✔, 28 ✔ | Taps done. Hold levels need firmware — the cheap half of **29** |
| **Composition** — hooks, session summaries | 23 ✔, **31** ✔, **32** ✔ | Done |
| **Actions as a first-class idea** | 30a ✔, **33**, **34** | The pool shipped; the sequence and app documents are open |
| **Reach and hosting** — launcher, ten apps, remote UI | 0a ✔, 7 ✔, **8** | Only the hardware walk on 7 |
| **Reaching other software** — OSC, MIDI out, clock in | 22 ✔, 24 ✔, **25** | Sending and listening work. **25** needs the DAW's Send To pointed back |
| **Saying a number** — ambient counting, count readout | 15 ✔, 17 ✔ | Only the human read test, on hardware |
| **Play** — timing and guessing games | 16 ✔ | Done for forgiving games; tight rhythm needs Stage 3 |
| **Getting around** — launcher, control surfaces, colour coding | 0a ✔, 26 ✔, 27 ✔, 28 ✔ | Only **26b**, an eyeball test |
| **Power** — sleep, wake, deliberate off | **29** | Blocked on measuring what it draws |

Outside the table: **0c** is hardware and gates nothing but its own
verification; **18** (Notion) is process and is parked.

## Sprint

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

**Last run: 2026-08-19**, at the end of the host-side sprint that shipped
items **5, 9, 14, 15, 17, 19b, 26, 27, 28**, the MIDI port dropdown, the
item-23 design and decision **D9**, and created build items **31–34**.
Shipped items are compressed into **Done**, superseded scope deleted, and
the gates re-scored above. Nothing shipped today has met the button.

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

Part (a), the subdivision ladder, shipped — see **Done**. Four parts remain.

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

**Still open on this item:** an *animated* device-side live preview —
`/api/dev/led` previews a sequence as its first stop, static, with a
warning saying so. Honest, but not a preview; needs a cancellable task in
webui.py mirroring main.py's driver.

**15 and 17 are now unblocked; Simon-says (16's parked half) too.**

#### c) Reuse the ramp widget wherever a gradient makes sense

**Checked 2026-08-20: "a descriptor change per template, not new code" is
wrong, and the item as written is already half-done.** Two corrections.

The widget is *not* only offered on the countdown - hot/cold and reaction both
offer it already (`HOTCOLD_RAMP`, `REACTION_RAMP` in schema.js), and both walk
it in their run loops. Those are the templates whose ramp is driven by *how
well you did*; the countdown's is driven by time. Between them they are every
template that currently has a `ramp` field at all.

That leaves Pomodoro as the only real candidate, and it costs four files, not
one:

- `PomodoroBehavior` has no `ramp` field, so config.py needs the field, a
  `_default_pomodoro_ramp()`, a `_parse_ramp` call in `_parse_pomodoro` and a
  line in `as_dict` - the same four-place change any new template field costs.
- **`run_pomodoro` has nowhere to walk it.** Its `show()` is called on phase
  transitions and gestures only; it never repaints while a block runs. The
  countdown's ramp works because `run_countdown` has a 1 s tick
  (`_COUNTDOWN_TICK_S`) and a `paint(progress)` that pushes only when the
  colour visibly moved (`_COUNTDOWN_COLOR_STEP`). Giving Pomodoro a ramp means
  giving it that tick - new run-loop code, which is the one place CLAUDE.md
  says logic should *not* go, and which Stage 3 will rewrite.

So the honest cost is "a template field plus a repainting tick", and the
tick is the part worth thinking about before it is written. **Not built.**
Hold levels are not a candidate either way: `GESTURE_HOLD` is claimed and
unimplemented, so there is no progress value to ramp over yet (item **29**).

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
  style per stop, and `drive`. **Walked versus sampled turned out to be the
  real distinction, not the unit**: `plan_at` walks and returns a wait,
  `sample_at` samples and returns none. Precedence is named stop list > ladder
  > ramp. The rules are in [CLAUDE.md](CLAUDE.md).
  **Left open:** `run_pomodoro` has no repainting tick, so nothing can sample
  from it - that is **19c**, and it should be done once for both.

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
