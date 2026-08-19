# To-do

The ESP32 transition ([DESIGN-ESP32.md](DESIGN-ESP32.md)) is finished — the
button is real hardware talking to the host over BLE. Everything below is
feature work.

This is the **near-term list**: Stage 2 of [ROADMAP.md](ROADMAP.md), the
MVP/demo push. Anything that reshapes the architecture — the app runtime, the
one-manifest move, moving the brain onto the device — lives in
[ARCHITECTURE.md](ARCHITECTURE.md) and the roadmap, not here. Two items below
(**0a**, **0c**) are the exceptions: they are Stage-2 work *because* deferring
them gets expensive once more hardware exists.

Worth knowing while working this list: the button is getting its own brain,
and an app is becoming *data* rather than code
([ARCHITECTURE.md](ARCHITECTURE.md)). Nothing here has to anticipate that,
but a new takeover loop written as a state machine over `(state, event, now)`
will port; one that awaits the device directly will be rewritten.

## Current hardware state — the button is off the board

**The 19 mm button is de-soldered**, switch *and* LED, pending the rework in
**0c**. Until it goes back on:

- **Presses come from the board's BOOT button — once the firmware is
  flashed.** `BUTTON_PIN` is temporarily **0** rather than 4 in the source so
  there is something to press, but that is a firmware constant: until
  `mpremote cp firmware/*.py : + reset` has run, the board is still reading
  GPIO4 and nothing physical produces a gesture. The web UI's simulate-press
  buttons and `POST /api/trigger` work either way. GPIO0 is a strapping pin,
  so do not hold it through a reset or a replug — that is download mode, and
  it looks exactly like a dead board. **0c** puts the pin back to 4.
- **No ring.** The board's onboard WS2812 is the only light, and it is now the
  *accurate* one — the byte-order fault that made both LEDs render red as
  green is fixed and flashed.

**Flashed to 0.6.0** (2026-08-18) — rainbow brightness is live.

The ESP32 itself is untouched and the service runs normally, so the rest of
the list is unaffected. Re-soldering is **0c**, and the 5 V rework belongs in
that same sitting rather than putting it back exactly as it was.

## How to work this list

Each numbered item under **Sprint** is written to stand alone: context, the
exact files involved, and a definition of done, so it can be picked up in a
fresh session with none of the history that produced it. Items are not
strictly independent — where one depends on another it says so — but you
don't need to read the others to start.

**Numbers are never reused or renumbered**, even when an item ships and moves
to **Done**. [ROADMAP.md](ROADMAP.md), [CLAUDE.md](CLAUDE.md), commit messages
and old sessions all cite them, and a stable number is the only thing making
those citations survive. That is why the sprint below starts at 0a and has
gaps.

**What this file keeps, and what it does not.** A rule that governs *future*
code belongs in [CLAUDE.md](CLAUDE.md); this file records the *decision* and
points at it. Shipped items are compressed to the choices that still bind —
if the reasoning is already an invariant in CLAUDE.md, it is not repeated
here. That is what keeps a sprint list readable as it ages.

Before touching code on any item: read [CLAUDE.md](CLAUDE.md) (the SOLID
conventions section especially — new capability goes in as **data** in
`schema.js`/`config.py`, not as branches in the editor or the loop), skim the
linked files, and run the suite:

```bash
.venv/Scripts/python -m pytest -q
```

Run it again before calling an item done. If you touch
[firmware/protocol.py](firmware/protocol.py) or
[firmware/led.py](firmware/led.py), you *must* touch their host mirrors
([aibutton/device.py](aibutton/device.py),
[aibutton/config.py](aibutton/config.py)) in the same change, or
[test_protocol.py](tests/test_protocol.py) /
[test_firmware_feedback.py](tests/test_firmware_feedback.py) will fail.

Only one instance of the app may run at a time (BLE allows a single
central) — if you need to restart the service to pick up a Python change,
confirm with the user first if it might be running against the real button.

## Where Stage 2 actually stands

[ROADMAP.md](ROADMAP.md)'s exit gates, scored honestly. This is the checkpoint
**item 10** asks for, done on 2026-08-16.

| Gate | State |
|---|---|
| Protocol v1 frozen | ✔ done — item **0b** |
| Single-instance guard | ✔ done |
| **10 apps** verified on hardware | **built — item 7 ✔.** Eight verified on hardware (item **2** ✔); **Hot/Cold, Reaction and Signal are code-complete and unverified** |
| **A launcher** | ✔ done — item **0a** |
| Naive-user run | not started; wants item **14** first |
| 24-hour soak | not started |
| Verified power-cycle recovery | ✔ done — reconnected cleanly on a real replug |

**Four gates are done, one is a hardware session away, and two are not
started. Nothing left is blocked on design.** Ten apps now exist; what the
gate still wants is the three new ones walked against a real button, the way
item **2** walked the first eight. Then hardware time (**0c**, the soak) and a
naive-user run (**14**).

**The three new apps have never met the hardware.** Two of them are the first
things here whose *correctness depends on timing*, so they are the ones most
likely to behave differently on a radio than on a MockDevice — that is
precisely why `press_latency_s` exists (CLAUDE.md's invariants). Walk them
with `--ble` before believing the gate.

## Six bodies of work, not twenty items

The numbered list is written so each item stands alone, which is right for
picking one up cold and wrong for deciding what to do next. This is the other
view.

| Body of work | Items it spans | Gate |
|---|---|---|
| **The colour engine** — named looks, ramps, the safety floor | **3** ✔, **4** ✔, 0b·3 ✔ | Done. What is left of it is the stop list, in **19b** |
| **The gesture engine** — N taps, hold levels | 0b·2 ✔, 5-tap gesture ✔ | Ungated for taps; hold levels still need firmware |
| **Depth without the wire** — metronome config ✔, event values ✔, filtering/export ✔ | **1** ✔, **9**, **12**, **14** | None — ship freely |
| **Reach and hosting** — launcher ✔, ten apps ✔, remote UI | **0a** ✔, **7** ✔, **8** | Only the hardware walk left on 7 |
| **The light as a language** — ladder ✔, stop list, one-offs, where colour is edited | **19** | None for b–e |
| **Saying a number** — ambient counting, count readout, progress | **15**, **17** | Wants the stop list (**19b**) first — a readout *is* a stop list |
| **Play** — timing/rhythm and guessing games | **16** ✔ | Done for forgiving games; tight rhythm still needs Stage 3's on-device runtime |
| **Reaching other software** — OSC ✔, MIDI if ever | ✔ shipped with **7** | Ungated. MIDI costs a dependency and a virtual port; nothing needs it yet |
| **One machine, many timers** — Pomodoro/HIIT/Tabata as presets | **20** ✔ | Done |

Two things sit outside the table. **0c** is hardware (re-solder + the 5 V
rework) and gates nothing but its own verification. **18** (Notion) is process
and is **parked**.

**The news since the last triage.** The colour engine is finished and the
protocol freeze paid off exactly as intended: named looks, richer colour, more
tap counts and the whole subdivision ladder all landed as **host-side data
changes with no reflash under them**. Rainbow brightness was the one reflash
pending (a firmware *rendering* change rather than a wire change) and it
shipped 2026-08-18.

**What that leaves.** Three structures now describe every light this thing can
make, and only one of them is unbuilt:

| | Driven by | Serves | State |
|---|---|---|---|
| **Ramp** [ramp.py](aibutton/ramp.py) | progress 0→1 | countdown, Pomodoro block, hold level, hot/cold | ✔ built |
| **Subdivision ladder** [ladder.py](aibutton/ladder.py) | a counter | a time reference on any timer, beat accents | ✔ built |
| **Stop list** | the clock | Fade/Flash/Evolve, gradients, sequencing, **a number you can read** | **19b**, unbuilt |

A ramp answers "how far through are you", a ladder answers "what time is it",
a stop list answers "what happens next". None can express the others, and
**items 15 and 17 queue behind the stop list** — a count readout *is* a stop
list. Build it once, deliberately, and both get cheap.

**16 no longer queues behind it**, which is worth recording because it was the
assumption that made games look expensive. A host-pushed *sequence* needs the
stop list; a game that pushes **one** effect and then does arithmetic does not.
Hot/Cold spins a single rainbow and computes where it has got to, so it costs
one radio write per round. Simon Says is still on the far side of 19b — that
one genuinely is a sequence.

---

## Sprint

### 0c. Re-solder the button, and move its LED to 5 V while it is off

**Do this before anything whose test is "look at the ring".** The button is
currently de-soldered (see the state note at the top). This item puts it back —
and the reason to read it before reaching for the iron is that soldering it
back exactly as it was would preserve a known fault.

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

**Definition of done.** Button re-soldered and pressing again (a real gesture
reaching the host, not a simulated one); **`BUTTON_PIN` back to 4** — it is
temporarily 0 so the board's BOOT button can stand in, and leaving it there
makes every reset a coin-flip on entering download mode; the three-level and
load-ladder results written down here; the LED's supply and any level-shifting
recorded in [hardware.py](firmware/hardware.py)'s wiring block; and `#ffffff`
reading as white on the ring, or an explicit note saying how far off it still
is and why that was accepted.

### 5. Make the floor mode permanent, rename it to "Home", route into takeovers

Two things tangled together — do the resolution-semantics half first, it's the
one with test coverage riding on it.

**a) The floor mode can't currently be protected.** Nothing in
[rules.py](aibutton/rules.py) or `config.py` prevents deleting or rescoping the
one ambient mode a fresh config ships with (`_default_modes()`), which means a
button can be configured into a state where *no* ambient mode ever matches
(visible in the dashboard as "no mode matches short_press right now"). Fix:
guarantee exactly one ambient mode is permanent — `Always` activation, can't be
deleted, can't have its activation changed away from `Always`. Whether that's a
`protected: true`/role flag on `Mode` or a structural rule ("the last ambient
mode in the list is the floor") is a real design decision — `resolve()`'s
docstring already talks about "explicit priority instead of relying on list
order alone", which is the same underlying problem. In the UI, `ModeEditor`'s
delete button (`_header()`) and the name/template fields need to refuse.

**b) Rename it "Home" and change its default bindings.** The name is
**decided: `"Home"`** — chosen over `"Mode Selection"` (a UI label, not a mode
name) because it is the place you return to, which is exactly what **0a**'s
launcher wants to call it. Change its default bindings to
`short_press → Log`, `long_press → Enter "Pomodoro"`,
`double_tap → Enter "Stopwatch"`. That means `_default_modes()` can no longer
return a single mode — it must also seed default Pomodoro and Stopwatch modes
(`activation: manual`) for those `enter_mode` targets to resolve against, which
changes what a from-scratch `config.json` looks like. Depends on (a): renaming
and repurposing only make sense once this mode can't be deleted out from under
the defaults it routes to.

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

### 9. Make Tips content more concise — ASCII/shorthand, no emoji

Scope: the `[data-help]` content gated by the Tips toggle
([help.js](aibutton/web/static/help.js)) — the primer (`_renderPrimer()` in
`menu.js`), the group blurbs (`MODE_GROUPS`), and every field's `hint`
(`schema.js`, rendered by `widgets.js`). Tighten toward fragments over
sentences, `->`/`:`/`-` instead of prose connectors.

None of the current Tips copy uses emoji (the `⚠`/`ⓘ`/`●` are text symbols),
so this is really "shorter", not "de-emoji'd". The actual emoji in the app
(🔵/⚪ in the header indicator, `⚠️` in some `main.py` status strings) are
outside Tips scope — **flag to the user whether those should go too, don't
remove them unasked.**

Note this item got bigger while nobody was looking: the ladder, the flash
floor and the reminder template all added hint text.

### 10. Checkpoint — review and re-triage

**Last run: 2026-08-16** (this cleanup). Shipped items compressed into
**Done**, superseded scope deleted, Stage-2 gates scored in "Where Stage 2
actually stands" above.

**Next checkpoint: after 0a and 2.** Those two together answer the only
question Stage 2 has left — whether ten apps are real and reachable — and
between them they will produce new items, which is what a checkpoint is for.

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

### 14. Tinker mode — one flag that decides how much surface you see

The base experience should be obvious to someone who has never seen it; the
fringe options should still exist. That is [ROADMAP.md](ROADMAP.md)'s first
principle, and today nothing implements it — every field a template has is
rendered to everybody. **It is also what the naive-user exit gate needs.**

**Build it exactly like Tips.** Add `tier: 'basic' | 'tinker'` to field
descriptors in [schema.js](aibutton/web/static/schema.js), default `basic` when
absent, and have `widgets.js` mark the node so one toggle hides the lot. Data
on descriptors, one renderer change, no branches. The toggle joins
`.header-tools` next to Tips and reads its state through
[prefs.js](aibutton/web/static/prefs.js) like the side pane does.

**They are two axes, not one:** Tips is *explain / don't explain*; Tinker is
*show / hide surface*. A basic user with Tips on should get a short, fully
explained form. Do not collapse them into one "beginner mode".

**The judgement is which fields are which**, and it is the whole value of the
item — a Tinker flag on everything is the same as no flag. First pass worth
arguing with: metronome's `tap_history`/`reset_gap_s`/`max_bpm` are tinker and
`start_bpm` is basic; Pomodoro's `extend_minutes` and per-gesture command
bindings are tinker; every `log_as`/event name is basic (it is what you came
for); the whole Device settings group is tinker except `sounds_enabled`; the
ladder's rungs are basic but its off-beat colour and tick are tinker.

**Unblocked** — it was waiting on item 3's look work, which shipped.

### 15. Counting without entering an app

**Half of this already works.** Binding a gesture to count something does not
need the Counter takeover and never did: `LogAction` is an ambient action and
`count_today`/`current_streak` group by event name, so this counts coffees with
no code at all —

```json
{ "name": "Home", "template": "actions", "activation": {"type": "always"},
  "double_tap": {"action": "log", "event": "coffee"} }
```

**So what is the Counter takeover for?** Three things, and only the third is
hard: it zeroes a session tally, it owns `COUNTING`, and it *tells you the
number*. An ambient `log` gives you a `SUCCESS` flash — you learn that it
counted, not what it counted to. **The gap is the readout, which makes this
item and item 17 the same feature.** Do 17's scheme first, then this is a new
ambient action and a preset, not a new template.

**The concurrency question is decided: one foreground app, and shared state
lives in the event log rather than in the app.** Not "N concurrent apps with a
priority rule". Counting from Home and then entering the Counter to *continue*
the same tally needs no concurrency — they are already the same rows.

**What actually has to change is one line of state.** The Counter holds its
session number as a local integer starting at zero, which is the only reason
the two disagree. Read it from the store instead and they agree by
construction; "count something else in counter mode" is just a different event
name. No priority rule, no second run loop, no display arbitration.

**Write that paragraph into ARCHITECTURE.md** — the decision outlives the code
change, and the next person to want two things at once needs to find it.

Two questions it does *not* answer, neither urgent: a backgrounded timer still
monopolises gestures (a takeover awaits `device.events` directly), and two
things wanting the LED still needs a stated priority — or the readout from 17,
so a backgrounded timer is *asked* rather than watched.

**Definition of done.** Ambient counting with a readout gesture, shipped as
data; the Counter reading its number from the store; and the concurrency
paragraph in ARCHITECTURE.md.

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

### 17. A number you can read off one light

**The question was whether a universal colour-to-digit code exists. It does:**
the resistor colour code (IEC 60062) — black 0, brown 1, **red 2**, orange 3,
yellow 4, green 5, blue 6, violet 7, grey 8, white 9.

**And it is the wrong tool here.** Black is 0, which on an LED is *off* and
indistinguishable from idle; brown and grey are "dim orange" and "dim white",
which is to say not colours a diffused pixel can deliver; violet against blue
is hard on a single dot. That is ten-way hue discrimination on one diffused
LED — and this build's ring has a *measured* colour cast (**0c**) that eats
exactly those distinctions. A number system nobody can read under a warm
lampshade is not a number system.

**One LED has three channels, and they are not equally good at numbers:**

| Channel | Good for | Bad for |
|---|---|---|
| Count / rhythm | **exact integers**, no legend, no learning | anything large |
| Hue | **proportion**, magnitude, hot/cold | exact values |
| Brightness | emphasis, grouping | anything on its own |

So: **exact counts are blinks, proportions are hue.** Do not make hue carry
digits.

**The proposal** — tens as slow pulses in one colour, units as quick pulses in
another. 27 is two slow, then seven quick. It covers 0–99 in at most eleven
blinks, reads like an abacus, needs no legend, and has an engineering property
worth more than elegance here: **it does not depend on telling colours apart at
all**, so it survives the ring's cast, a warm room, and a colourblind user. Hue
then stays free to mean *which thing* is being counted.

**The subdivision ladder is not this**, and the difference is worth keeping
straight: a ladder is driven by a clock and repeats forever; a readout is
driven by a *value* and happens once. The readout is a **stop list** (**19b**),
including its one-shot mode.

**Definition of done.** The scheme written down as data (in `schema.js` and
`config.py`, not as branches); a readout reachable from an ambient counter
(item 15); and one person who has *not* been told the rule reading a two-digit
number off it correctly. That last one is the actual test — if it needs
explaining, it failed.

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

#### b) The sequencer — a stop list, and one-offs

The `{colour, hold, fade}` stop list: it subsumes all six current styles
(solid = one stop; flash = colour + black, stepped; fade = two stops, smoothed;
breathe = colour → black) and *then* gives gradients (many stops), sequencing
(stepped stops) and asymmetric duty (unequal holds) for nothing. **"Fade,
Flash, Evolve" are three presets over one structure, not three features.**

**The new requirement, and it is a real addition to the effect model: not
everything loops.** "Do x sequence over y interval" needs a *play once* mode.
Today every style repeats until the next state change, and the 0.03 s
confirmation flash is a one-off only because it is a state display rather than
an effect.

That has a safety consequence to settle **before** building: **0.03 s is 33 Hz
and is fine precisely because it happens once.** So `config.flash_safe` needs to
know whether an effect repeats — the floor is over *repeating* transitions. A
one-off and a looping sequence are different questions and the current
signature cannot tell them apart.

**The other floor gap, already paid for once:** the flash floor is enforced
over `period_s`, and a stop list breaks that — five colours at 0.1 s each is a
2 Hz cycle but a 10 Hz *change* rate. The ladder solved this for itself by
flooring its cadence (`ladder_paint`); the stop list must do the same, and the
right fix is to redefine the floor over transitions once, in `flash_safe`, for
both.

**This is the item items 15, 16 and 17 are waiting on.**

#### c) Reuse the ramp widget wherever a gradient makes sense

The `ramp` widget exists and is only offered on the countdown. Pomodoro blocks,
hold levels and any "how far through" surface want the same control. A
descriptor change per template, not new code.

#### d) Move mode colour fully into the mode, and grow the picker

The Lights tab should hold **system states only** (IDLE / LISTENING / THINKING
/ SUCCESS / ERROR). Mode-owned states (ALERT / TIMING / COUNTING / WORKING /
RESTING / METRONOME) belong on each mode's own page.

**Decided:** the global palette entries for mode-owned states **stay in config
as the invisible fallback** — they are what a mode with no named look renders,
and `base_look` reads them. Only the *editor group* goes away. Removing the
entries would leave a mode that names nothing with nothing to show.

The test bench is the right springboard for the per-mode picker: it already
pushes a look through the real parser and the real seam. What it needs to grow
is saved user styles — which is what the `looks` pool already is, so this is a
UI move rather than a new concept.

#### e) The metronome's period field in the Lights tab — confirmed dead

Verified, and nothing depends on it: `push_tempo` does
`replace(base, period_s=period)` on every tick, so the stored value is
overridden before it is ever rendered — including before the first tap, where
`start_bpm` drives it. Removing the field from the editor changes nothing at
runtime. **It resolves for free when METRONOME moves to the mode page (d).**

---

## Smaller, worth doing

- **Presses dropped while busy.** The loop runs one action at a time and
  discards presses during the 2 s SUCCESS display. Deliberate, but it makes
  fast repeated taps feel dead — worth revisiting if it grates in daily use.
  (Relevant to 12b if "performance" means device latency.)
- **Sound design** *(firmware)* — review "Smart Button Sound Design Research"
  (Obsidian) and replace the placeholder tone tables carried over from the Pi
  build. A matching sound palette, pushed the way the LED palette is, is the
  obvious shape.
- **The on/off toggle's action.** The 5-tap *gesture* shipped; there is no
  "toggle the button off" action to bind it to. That is an `actions.py` +
  `ACTIONS` + `config.py` change, and it needs a decision first: does "off"
  mean the ambient layer stops matching, the device goes dark, or both?
  **Ambient-only is the cheap and honest one.**
- **The service is not always under the tray.** Started from a terminal it
  works identically (the panel polls `/api/status`, not the process table), but
  the panel's Start/Stop won't own it. Worth knowing when debugging.

## Parking lot (deliberately later)

- Battery + deep sleep — the one thing that might justify a C++/NimBLE rework
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

- ~~**20. Pomodoro is an interval timer**~~ — generalised, and Tabata and HIIT
  are now **presets costing zero Python**. The template's `type` string stays
  `pomodoro` (its label is "Intervals"): renaming it would have been a
  migration for every saved config in exchange for a tidier word, and
  `MODE_LED_STATES`, `schema.js` and `test_webui.py`'s drift test all key off
  it.

  **Seconds are canonical and `*_minutes` still parses.** The old names could
  not express the short end — `work_minutes: 0.333` is not a way to write
  twenty seconds — so `work_s`/`break_s`/`long_break_s`/`extend_s` are the
  fields and the parser converts the legacy names on the way in. One format
  out: a minutes config is rewritten as seconds the first time it is saved,
  so the migration completes itself and there is no second format to keep
  supporting forward. Both live configs here were checked and parse with **no
  new warnings**.

  Two fields were added, both defaulting to exactly what a Pomodoro already
  did: **`rounds`** (0 = alternate until you leave) and **`lead_in_s`** (0 = no
  get-ready countdown). A workout sets them to 8 and 10.

  The editor got a **`duration` widget** out of it — a number plus a sec/min
  unit, storing seconds and *inferring* the unit for display, so 1500 opens as
  "25 min" and 20 opens as "20 sec" with nothing stored about which it "is".
  Without it the merge would have been a straight regression for anyone editing
  a Pomodoro.

  The old test config said `2 * (1/60)` minutes to mean two seconds. That it
  now just says `work_s: 2` is the clearest evidence the unit was wrong.

- ~~**7. Build at least 10 modes total**~~ — three new templates took the
  count to ten (not counting the launcher, which launches apps rather than
  being one): **Hot/Cold**, **Reaction timer** and **Signal**. All three are
  code-complete and **none has met the hardware** — that is what the Stage-2
  gate still wants.

  **Two of them are written the way Stage 3 wants every app written**, which
  was the point of doing the games first: [hotcold.py](aibutton/hotcold.py) and
  [reaction.py](aibutton/reaction.py) are pure `step(state, event, now)`
  functions returning a small closed effect set, and the `run_*` loops in
  `main.py` are drivers holding only the clock, the queue, the die roll and the
  store. A whole session is a list of calls with numbers in it, so the scoring
  is tested without asyncio and without a device. Randomness is passed *in*
  (`next_target`, `next_delay`) precisely so `step` stays checkable against a
  table.

  **Signal is the first app whose point is to persist rather than finish**, and
  it is what made the "one foreground app" decision (item **15**) visible:
  while it holds the light, nothing else on the button is reachable. It is also
  the economy in the set — a status light and an OSC footswitch are the *same*
  machine (cycle named positions, hold one, send something on arrival), so they
  ship as two presets over one template rather than two templates. Each
  position carries an ordinary `Action`, which is why the template does not
  know what a webhook or an OSC message is and why the next primitive will work
  there for free.

  Cost, noted rather than normalised: three templates × the usual
  `config.py`/`main.py`/`schema.js` tax, about 27 touch points in three core
  files. **No new `LEDState`, no protocol change, no reflash** — all three own
  no state and push effects, which is exactly the bar 0b set.

  Left open: Signal's positions are edited as a **JSON field**, because there
  is no repeating-sub-form widget and `webhook`'s payload set that precedent.
  The two presets are complete so nobody has to write one, but a real widget is
  the follow-up (and is item **14**'s tinker/basic split arriving early).

- ~~**16. Games**~~ — **Hot/Cold** shipped, to its own definition of done: a
  hue wheel spins, a press stops it, `ramp.color_at` flashes how close you got,
  and each guess logs its closeness in the `value` column. **Reaction timer**
  came nearly free beside it, sharing the shape rather than the code.

  **Two things this item asserted turned out to be wrong, and both mattered:**

  - *"A mode binding only short press gets an instant press."* It does not.
    `max_taps_for` floors at `DEFAULT_MAX_TAPS = 2`, so **every** single press
    on **every** config waits out the 0.4 s window. There is no such thing as
    an instant press, and "bind exactly one gesture" buys nothing. What saves a
    timing game is that the delay is a *constant*: subtract it and you recover
    the moment the player meant. That is now an invariant in CLAUDE.md, and it
    is read from `ButtonDevice.press_latency_s` rather than hardcoded — because
    an *injected* press (the web UI's simulate buttons, every test) arrives
    instantly, and correcting that would be the same bug backwards. Without
    this the reaction timer scores every simulated attempt as a false start.
  - *"The host does not know the device's rainbow phase."* It can know it
    exactly. `_rainbow` sets `start = now_s()` when the effect arrives, and
    pushing an effect restarts that coroutine — so phase 0 **is** the push, and
    "compute it from send-time plus period" is arithmetic rather than the
    approximation this item took it for. One radio write per round, not one per
    frame, which is the only reason a stop-the-spinner game works over a
    fire-and-forget link at all.

  What this item said about *tight rhythm* still stands and is untouched: ±150 ms
  games are honest today, judging a beat is Stage 3 on-device work.

- ~~**An OSC action, and no dependency for it**~~ — `osc` joins log /
  timer_toggle / webhook / enter_mode, so any gesture in any mode can drive
  Reaper, TouchOSC, QLab, Resolume, VCV Rack or TouchDesigner.
  [osc.py](aibutton/osc.py) is pure encoding — address, type tags, big-endian
  args, everything null-padded to four bytes — over stdlib UDP, so it cost
  **zero new runtime dependencies**.

  A sibling of `webhook` rather than a setting on it: one is a request with an
  answer and a failure mode, the other is a datagram that either leaves or does
  not, and the result says "sent" and never "delivered" because UDP cannot know.
  Fire-and-forget also happens to be the contract the rest of the feedback path
  already has.

  **MIDI is deliberately not here.** It would need `python-rtmidi` *and*, on
  Windows, a virtual port like loopMIDI, because there is no built-in way to
  hand MIDI to another application. It is a sibling module and a sibling action
  if it is ever wanted, not a mode of this one — a MIDI note does not travel
  over OSC. **What OSC cannot honestly do is live looping**: 0.4 s of tap
  window plus the radio is 20× over what punch-in needs. Transport, scene
  launch, record-arm, mute and talkback are fine; anything on the beat is
  Stage 3.

- ~~**2. Verify the takeover modes work end to end**~~ — walked all eight
  templates against real hardware (`--ble --config config.json`): Stopwatch,
  Pomodoro, Alarm, Reminder, Metronome and Countdown all behave as the suite
  says they should.

  **Found and fixed on the way:** Pomodoro's paused/waiting-for-a-press
  indicator was hardcoding the global `LISTENING` state, so it silently
  overrode whatever look the mode itself had chosen — `LISTENING` is
  deliberately global-only (see `MODE_LED_STATES` in `config.py`), so a
  Pomodoro could never own it. It now freezes the *current phase's own*
  colour into a `waiting_style` (default `solid`) instead, so a paused or
  finished block still wears Work's/Break's colour, just not animated. See
  `PomodoroBehavior.waiting_style`.

- ~~**Verified power-cycle recovery**~~ — a real USB replug mid-session
  reconnected on its own; reconnect logic was previously only exercised
  against a fake bleak.

- ~~**0a. The app launcher, and a takeover that can start another one**~~ —
  a `launcher` template: short press cycles the installed apps in each app's
  own colour, long press launches, double tap backs out. Reached by one
  gesture, so "load the button with as many apps as it will fit" is true for
  the first time.

  **The core rule, which was the actual work: replace, don't nest.**
  `enter_takeover` is now a loop rather than a single dispatch — a launcher
  *names* what runs next, and its session is closed before the app's is
  opened. Chosen over a depth guard because with no stack there is nothing to
  overflow, the event log gets one clean `mode_enter`/`mode_exit` pair per app
  instead of nested ones, and leaving an app returns you to where you actually
  are rather than to a menu you had forgotten was underneath it. `return_after`
  opts into going back, exactly once.

  **No hop limit, deliberately.** Every handoff costs a long press, so no chain
  runs unattended — and the one shape that could, a launcher offering itself,
  is excluded from the menu instead. A test proves that exclusion by counting
  the cycle rather than by inspecting it.

  **It owns no `LEDState`.** It wears the target's look over `LISTENING`, which
  is honest for the status line and for a device too old for effects. An empty
  `targets` list offers every takeover mode in config order, so a new app
  appears without editing a list; a named target that does not exist warns at
  *run* time, because config order is not dependency order.

  Cost, noted rather than normalised (CLAUDE.md's "know what an app costs"):
  `config.py` dataclass + parser + allow-list + LED states + union +
  serialiser, `main.py` loop + dispatch, `schema.js` descriptor + takeover set.
  Nine touch points in three core files for one app — which is exactly the tax
  Stage 3's runtime exists to remove.

  **The gestures were wrong on the first cut, and the fix is a rule.** It
  originally launched on a long press and backed out on a double tap - exactly
  backwards, since every other takeover leaves on a long press. It now launches
  on a **double tap** and leaves on a **long press**, and `return_after`
  defaults to *on*, so long press means "up one level" everywhere: out of an
  app lands in the menu, out of the menu goes home. Two presses from anywhere,
  nothing to learn. That is now an invariant in CLAUDE.md rather than a
  property of this one mode.

  Suite: `test_launcher.py`. Also fixed on the way past: the `enter_mode`
  target picker offered schedule-started modes (alarm, and reminders since it
  shipped). It now filters on the descriptor's own `startedBy`, so the next
  schedule-started template does not repeat the bug.

- ~~**Rainbow brightness**~~ — `_rainbow` takes the effect colour's brightest
  channel as its HSV value. The colour bytes were *discarded* for this style
  before, so this is an addition rather than a repurpose.

  **Zero means full, and that is the whole compatibility story.** Every rainbow
  saved earlier carried whatever was in the colour field, very often `#000000`;
  reading that literally would black out existing configs on reflash, and a
  rainbow rendering black is indistinguishable from the light being off, which
  nobody configures a rainbow to do. So the one value that cannot be honoured
  is the one that means "unset". The editor's slider floors at 1% for the same
  reason.

  `CAP_RAINBOW_LEVEL` was allocated even though the wire is unchanged: without
  it the failure is silent — a slider that does nothing on an un-reflashed
  button. Firmware 0.6.0, flashed 2026-08-18.

- ~~**19a. The subdivision ladder**~~ — [ladder.py](aibutton/ladder.py): at any
  moment the colour is the one on the **largest interval that divides the
  elapsed time**. Live on stopwatch, countdown (driven by time *remaining*) and
  metronome (counted in **beats**, because a tempo already supplies the timing
  and what a colour adds there is an accent).

  Four things worth keeping:
  - **Parity needs no notion of parity.** A rung at 2 s catches the even
    seconds and a rung at 1 s catches whatever is left. Adding a 15 s rung needs
    no code.
  - **Whole milliseconds, not floats.** `2.0 % 0.5` can land on
    0.4999999999999998; a ladder that worked at 1 s and failed at 0.1 s would be
    the worst kind of intermittent.
  - **Ticks evaluate at their nominal time**, not the wall time the loop woke.
    A tick scheduled for 2.000 s that fires at 2.013 s must still be the
    two-second colour.
  - **The floor applies to the cadence, not `period_s`** — the transitions hole
    `flash_safe` cannot see, since a `solid` never strobes by its own reckoning.

  Opt-in, and it replaces the ramp (both decide *which colour*). A timer with no
  ladder still blocks on the next press and costs no radio traffic — the tick
  exists only when a ladder does.

- ~~**11. Reminders**~~ — scheduled like an alarm, deliberately not one. The
  alarm template is untouched, with a test asserting it. Any press clears it;
  **no snooze** (a postponable reminder is an alarm with extra steps); it
  **gives up on its own**, and a timeout logs nothing because nobody saw it. It
  reuses `ALERT` and breathes rather than flashing, pushed as an ephemeral
  effect — visibly not an alarm without a wire code or a reflash.

  **The scheduler was generalised, not duplicated:** what makes a mode scheduled
  is its *activation*, and the parser already decides which templates may carry
  one. Config order breaks a tie at the same minute, which puts an alarm above a
  reminder if listed first.

- ~~**4. The flash floor, and the period slider**~~ — the answer to "3 Hz or
  4 Hz" was *neither as a constant*: it is a **setting**,
  `min_flash_period_s`, defaulting to `device.SAFE_MIN_PERIOD_S` (3 Hz, WCAG
  2.3.1). Below the recommendation is **honoured and warned about** — clamping
  a setting silently makes it a lie; accepting silently makes the hazard
  invisible. One gate (`config.flash_safe`), applied in `main.set_led` and at
  the palette push. Only hard on/off styles are floored. The rule is in
  CLAUDE.md's invariants.

  The `range` widget's minimum is a *function of ctx*, so raising the setting
  widens the slider instead of lying about what will be accepted; its ceiling
  stretches to fit an already-larger stored value.

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

- ~~**0b. Protocol v1, frozen**~~ — `DEVICE_INFO` (capability negotiation),
  ephemeral effects and parameterised gestures shipped; `OTA_CONTROL` and
  `GESTURE_HOLD` claimed and unimplemented. **No `LEDState` was spent; `0x0B` is
  still the highest code.**

  What it bought, stated as a bar rather than a milestone: **everything on this
  list is now reachable without a reflash** — per-app looks, more tap counts, a
  launcher's per-entry colour, the whole subdivision ladder. So the bar for the
  next *wire* revision is a capability the device physically cannot express
  today, not a feature that would be tidier on the wire. The rules for making
  that change are CLAUDE.md's "When you change the protocol".

  The one judgement call worth remembering: counting to N costs a double tap its
  instant response, so the host writes `max_taps` derived from what the config
  binds rather than from a setting. At 2 the detector is byte-for-byte the one
  that shipped before.

- ~~**13. Scenes**~~ — swappable, offline-editable button configs. A scene is
  shallow-merged over `config.json` as a **raw dict** before `parse_config` sees
  it, so every existing fallback and warning applies to scene files with no new
  validation code. The editor writes the scene file; only the `scenes.active`
  pointer goes back to `config.json`. Startup-only keys (`web_port`,
  `database_path`, `ble_device_name`, `web_host`) come back as `needs_restart`
  rather than reloading cleanly and doing nothing. The invariants are in
  CLAUDE.md.

  **Left open:** the tray's `Scene >` submenu is unit-tested but has never been
  clicked — `tray.py` needs a screen, so the suite deliberately does not import
  it. Click it once before trusting it. Also: a scene saved *through the editor*
  carries the whole effective config, so UI-made scenes lose the "inherit what I
  don't mention" property hand-written ones keep.

- ~~**A light test bench, and the byte-order fault it caught**~~ — push any
  style/colour/period straight at the LED, saving nothing. It needed no new
  device method, because "show this look" is already what an ephemeral effect
  means. Validation goes through the config's own `_parse_effect`, so a colour
  the editor would reject on Save is rejected identically here.

  It immediately earned itself by catching `NEOPIXEL_ORDER` /
  `ONBOARD_NEOPIXEL_ORDER` being on the wrong LEDs. **The diagnosis came from
  pushing *known* colours, not from staring at a rainbow** — every permutation
  of a rainbow is still a rainbow, so it shows at most a direction reversal, and
  a camera's white balance will happily fake one of those.

- ~~**Colour ramps, and a countdown to prove them**~~ —
  [ramp.py](aibutton/ramp.py): colours pinned at fractions, blended the same way
  `firmware/led.py`'s `_fade` does, with a test that fails if the two disagree.
  **Positions, not durations**, so the same ramp serves a two-minute egg timer
  and a two-hour deadline. **Push on change, not on tick** (`ramp.differs`)
  bounds a full sweep to a couple of hundred writes whatever the duration.
  **Ramp and effect stay separate objects** — the countdown flashes at a fixed
  period while the colour travels.

  One gap found later and fixed: a ramp under a style that ignores `color`
  (rainbow) is invisible, so the countdown now checks and stops pushing rather
  than sending colour into a style that discards it.

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
