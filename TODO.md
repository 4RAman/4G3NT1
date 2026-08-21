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

## Current hardware state — the button is back on, and needs a flash

**Re-soldered 2026-08-21** onto new pins: the switch's green wire to
**GPIO10** (`BUTTON_PIN`) and the LED's red data wire to **GPIO12**
(`NEOPIXEL_PIN`). Both are plain S3 GPIOs, clear of the strapping pins
(0/3/45/46), the SPI flash (26-32), octal PSRAM (33-37) and USB (19/20). The
BOOT-button stand-in on GPIO0 is gone, and so is the download-mode hazard that
came with it — holding the button through a reset is safe again.

- **The pins are source, not state: nothing physical produces a gesture until
  `mpremote cp firmware/*.py : + reset` has run.** Until then the board is
  still reading whatever it was last flashed with. The web UI's simulate-press
  buttons and `POST /api/trigger` work either way, which is exactly what makes
  this easy to miss.
- **The ring is back on 3V3, deliberately, for now** (2026-08-21). So the
  channel imbalance **0c** diagnoses is still live: R > G > B at roughly
  `1.00 : 0.54 : 0.44`, which renders white as light orange, cyan green-tinted
  and magenta red-tinted. Nothing is broken; the part is a 5 V device being
  run under spec, and that trade was taken knowingly to keep the data line's
  logic threshold safe.

  **Read this before diagnosing any colour work as a bug.** Anything with a
  gradient in it — a ramp, a fade, the stop-list curves in **36** — will look
  warmer on the ring than it does in the web UI's preview, and blue-heavy
  looks will read dim. The preview is correct and the ring is the thing that
  is off. Judge new colour work on the *onboard* LED, which renders
  accurately, or against the numbers rather than the ring.

**Flashed to 0.6.1** (2026-08-19) — a press is dated at the edge rather than
at the debounce, which took a ~50 ms systematic error out of every timestamp
the host sees. Verified live: `/api/status` reports
`device_info.firmware = "0.6.1"`. A behaviour change with no wire change still
earns a version bump, because it is the only way to tell a flashed board from
an un-flashed one.

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
**item 10** asks for — last scored 2026-08-19.

| Gate | State |
|---|---|
| Protocol v1 frozen | ✔ done — item **0b** |
| Single-instance guard | ✔ done |
| **10 apps** verified on hardware | **built — item 7 ✔.** Eight verified on hardware (item **2** ✔); **Hot/Cold and Reaction walked on hardware 2026-08-19** and both play correctly; **Signal is code-complete and unverified** |
| **A launcher** | ✔ done — item **0a** |
| Naive-user run | not started; unblocked — item **14** shipped 2026-08-19 |
| 24-hour soak | not started |
| Verified power-cycle recovery | ✔ done — reconnected cleanly on a real replug |

**Four gates are done, one is nearly there, and two are not started. Nothing
left is blocked on design.** Ten apps now exist; what the gate still wants is
**Signal** walked against a real button, the way item **2** walked the first
eight. Then hardware time (**0c**, the soak) and a naive-user run (**14**).

**The two timing-dependent apps are verified.** Hot/Cold and Reaction were the
ones most likely to behave differently on a radio than on a MockDevice, being
the first things here whose *correctness depends on timing* — that is precisely
why `press_latency_s` exists (CLAUDE.md's invariants). Both were walked with
`--ble` on 2026-08-19, after firmware 0.6.1 dated the press at the edge, and
both play the way they do under simulation. **That is the timing correction
confirmed end to end**, and it is the part that was theory until somebody
pressed the button.

Signal is the remaining one and is the least likely to surprise anyone: it
holds a state and pushes a colour, with no clock in it. Walk it anyway — the
same was said about the offline editor.

## Six bodies of work, not twenty items

The numbered list is written so each item stands alone, which is right for
picking one up cold and wrong for deciding what to do next. This is the other
view.

| Body of work | Items it spans | Gate |
|---|---|---|
| **The colour engine** — named looks, ramps, the safety floor | **3** ✔, **4** ✔, 0b·3 ✔ | Done. What is left of it is the stop list, in **19b** |
| **The gesture engine** — N taps, hold levels | 0b·2 ✔, 5-tap gesture ✔, **28** ✔ | Taps are done. Hold levels still need firmware and are the cheap half of **29** |
| **Depth without the wire** — metronome config ✔, event values ✔, filtering/export ✔ | **1** ✔, **9** ✔, **12**, **14** ✔ | None — ship freely |
| **Reach and hosting** — launcher ✔, ten apps ✔, remote UI | **0a** ✔, **7** ✔, **8** | Only the hardware walk left on 7 |
| **The light as a language** — ladder ✔, where colour is edited ✔, stop list ✔ | **19** (a ✔, b ✔, c *checked, not free*, d ✔, e ✔), **36** | Item **19** is spent; **36** is where the light goes next — curves, a style per stop, one primitive |
| **Saying a number** — ambient counting ✔, count readout ✔ | **15** ✔, **17** ✔ | Only the human read test, on hardware (same sitting as **26b**) |
| **Play** — timing/rhythm and guessing games | **16** ✔ | Done for forgiving games; tight rhythm still needs Stage 3's on-device runtime |
| **Reaching other software** — OSC ✔, MIDI out ✔, clock in ✔, transport state | ✔ shipped with **7**, **22** ✔, **24** ✔, **25** | Sending and listening both work. **25** wants MCU's *return* feedback, which needs the DAW's Send To pointed back |
| **One machine, many timers** — Pomodoro/HIIT/Tabata as presets | **20** ✔ | Done |
| **Getting around** — launcher ✔, control surfaces ✔, colour-coded pages ✔ | **0a** ✔, **26** ✔, **27** ✔, **28** ✔ | Only **26b**, an eyeball test on real hardware |
| **Power** — sleep, wake, deliberate off | **29** | The button is back on (**0c**, 2026-08-21); still blocked on measuring what it draws |

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
| **Stop list** [sequencer.py](aibutton/sequencer.py) | the clock | Fade/Flash/Evolve, gradients, sequencing, **a number you can read** | ✔ core built 2026-08-19; editor UI pending (**19b**) |

A ramp answers "how far through are you", a ladder answers "what time is it",
a stop list answers "what happens next". None can express the others. The
stop list's core shipped 2026-08-19, so **items 15 and 17 are unblocked** —
a count readout *is* a stop list, and the play-once mode was built for it.

**16 no longer queues behind it**, which is worth recording because it was the
assumption that made games look expensive. A host-pushed *sequence* needs the
stop list; a game that pushes **one** effect and then does arithmetic does not.
Hot/Cold spins a single rainbow and computes where it has got to, so it costs
one radio write per round. Simon Says is still on the far side of 19b — that
one genuinely is a sequence.

---

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

### 36. One colour primitive — curves, effects per stop, and one editor

Asked for 2026-08-21 as "the primo colour editor", and the framing that
justifies it is not the UI. [ARCHITECTURE.md](ARCHITECTURE.md) lists three
ways an app may gain a capability and ranks **"extend the effect set (a
system decision, not an app's)"** second, above shipping native code; the
rule it has to satisfy is *bounded by construction* — no loops, no
allocation, no recursion, worst case knowable before the app runs. **A stop
list with curves is exactly that**: a finite table. So this is the sanctioned
growth path for what a light can say, and it costs the on-device runtime
nothing it was not already prepared to pay.

**The vision, as given.** A step sequencer over "nodes": 0% solid red, 50%
solid yellow, 75% flashing yellow, 100% solid green. A loop checkbox (unchecked
= play once, then back to the previous colour). Positions in percent, or
seconds/ms, or beats, chosen from a dropdown. Interpolation you can shape
between nodes — hold red a while, then a fast exponential run up to yellow,
then a linear fade to green — the synth idea of a waveform whose peaks are
shorter than its valleys and lag behind centre. And programmable one-offs:
a confirmation that is *green pause green pause green blink green blink* over
two seconds rather than "the flash style".

**What was already built.** [sequencer.py](aibutton/sequencer.py) (item 19b,
2026-08-19) is the step sequencer: ordered stops, per-stop `hold_s` and
`fade_s`, `repeat`, and `repeat: false` meaning play once and fall back. The
colour engine already edits them. So the ask is the four things below, not the
whole thing.

**The unification is real, with one correction.** sequencer.py's own docstring
already draws the diagram — `ramp` is driven by progress 0→1, a stop list by
the clock, a `ladder` by a counter — and these *are* one primitive with three
clocks. The correction: the drive belongs to the **sequence**, not the stop
(mixing beats and milliseconds in one list leaves `plan_at` with no single
timeline, and it is currently total over its domain). The consequence worth
deciding before code: a ramp and a ladder are parameterised by something
*outside themselves* — a countdown owns its progress, a metronome owns its
beat — while a stop list owns its own clock and is the only one of the three
that can stand alone. So a percent-driven look is meaningless on IDLE. **One
editor for all three is right; where you may bind the result depends on the
drive**, which is `MODE_LED_STATES`-level logic, not editor logic.

**Where "it replaces every other colour mode" stops being true.** The system
palette ships to the device and renders **unattended**, which is why
`_parse_palette` is effect-only. A sequence is a schedule only the host can
walk. That constraint gets *more* important as the device gets more
autonomous, not less. The resolution taken here is better than replacement:
**the sequence is the authoring surface and `LedEffect` is the fallback
form** — the same relationship `looks` and `led_palette` already have.

**Asymmetric periodic styles are deliberately not a wire change.** Giving
`breathe` a duty cycle and a phase skew would mean firmware, a protocol
change and a reflash, against a v1 CLAUDE.md just froze with the bar at "a
capability the device physically cannot express today". A host-walked stop
list approximates any curve with no wire change at all, so the shape is
available immediately as a sequence and only becomes a cheap device-rendered
primitive if a v2 ever happens for other reasons. **Do not spend a style code
on this.**

**Bandwidth is the real limit, and it decides what sequences are for.**
`_SEQUENCE_MIN_STEP_S` is 50 ms because feedback is fire-and-forget and
`BLEDevice` drops rather than waits. A two-second exponential fade is ~40
radio writes: fine for something that *happens* (a confirmation, a transition,
an alarm), wrong for something that idles. Rich sequences are events. IDLE
stays a device-rendered style until Stage 3 moves the walker onto the device.

**Concept count is the other limit.** Item **30** already notes there are
eleven concepts here and a novice holds about three. A node editor with curves
and unit dropdowns is unambiguously **tinker-tier**; `LOOK_PRESETS` is the
front door, and today it cannot offer a ramp or a stop list at all. Making the
preset library carry sequences is what stops the power tool being the only
door.

#### a) Sequence presets, and a system state may name a look — **built 2026-08-21**

`LOOK_PRESETS` becomes effect-*or*-sequence, and the system states
(IDLE/LISTENING/THINKING/SUCCESS/ERROR) may name a look from the pool the way
a mode already may. **The precedent already exists**: `control` → `LISTENING`
is a dual citizen in `MODE_LED_STATES`, a page naming a look that overrides
the global colour while it is open. Generalising it is not a new concept.
Resolution order becomes explicit effect → the active mode's look → the global
state look → `None`, which is what `set_led` already means by "fall back to
the palette". This is what unblocks the programmable confirmation, and it is
the smallest of the four.

#### b) A curve on each stop — **built 2026-08-21**

`Stop.curve`: linear (today's behaviour and the default), ease-in, ease-out,
ease-in-out, exponential. Pure, ~30 lines, and it survives the Stage-3 move
unchanged because `plan_at` still answers only "what colour now, and for how
long". No firmware mirror: firmware/led.py does not walk sequences, so nothing
drifts.

#### c) A stop may carry a style, not only a colour — **built 2026-08-21**

What makes "75% flashing yellow" and the rainbow applause at the end
expressible. `sequencer.py` is a leaf and must not import `config`, so a stop
carries plain `style`/`period_s` fields and main.py assembles the `LedEffect`.
**The style applies during the stop's hold; a fade is always plain solid
interpolation** — a flashing target half-way through a crossfade is not a
thing anyone means. Care needed at the flash floor: this must be `flash_safe`
applied *inside* `sequence_safe`, not a second call site (CLAUDE.md).

#### d) `drive` on the sequence — the actual unification — **built 2026-08-21**

`clock` (today), `progress` (what `ramp` does), `beats` (what `ladder` does).

**Walked versus sampled turned out to be the real distinction, not the unit.**
A clock-driven list owns its position and `plan_at` walks it, sleeping between
frames. The other two are parameterised from *outside themselves*, so they are
sampled: `sample_at(seq, 0..1)` answers "what colour at this point" and
returns no wait, because only the app knows when its own number will move
next. That is one new pure function, not a second driver.

Two consequences that were not obvious until it was written:

- **Sampled fades interpolate continuously; walked ones stay quantised.** The
  50 ms stepping exists because a walked sequence pushes every frame over a
  radio. A sampled one pushes only when the app ticks — a countdown steps once
  a second, already twenty times coarser — so quantising on top loses the
  gradient for nothing. Getting this wrong the first time produced a stop list
  with no gradient at all: `min_step_s = 0` collapses a fade to a single hard
  cut, which is `_fade_step`'s documented degenerate case and exactly the wrong
  default for sampling.
- **The binding table is keyed by template, not by state, and that is forced.**
  `TIMING` belongs to both the countdown and the stopwatch, and only one of
  them has an end to be a fraction of. `DRIVE_TEMPLATES` in config.py, mirrored
  as `drives` on the descriptors in schema.js.

**Precedence, derived rather than invented:** named stop list > ladder > ramp,
in both `run_countdown` and `run_metronome`. It is the rule `run_countdown`
already used between the ladder and the ramp — the more explicit thing wins —
extended by one step, because a look you had to build, name and point a mode at
is more deliberate than a checkbox on the mode.

**A stranded drive is warned about, not refused.** Binding a progress look
where nothing supplies progress keeps the binding and plays it on the clock;
dropping it would leave the state with no look at all, a bigger change to what
the button does than rendering the same colours on the wrong axis.

**Pomodoro is still not wired, and for 19c's reason.** `run_pomodoro`'s
`show()` fires on phase transitions only — it has no repainting tick, so there
is no place to sample from. Giving it one is the same piece of work **19c**
describes, and it should be done once, for both.

**The preset library is now the front door it was supposed to be.** 100 stop-list
presets landed 2026-08-21 in eleven groups — Confirm, Countdown, Tempo, Nature,
Signals, Retro, Focus, Mood, Play, Ambient, Patterns — bringing `LOOK_PRESETS`
to 142 entries (37 effects, 105 sequences; 84 clock, 11 progress, 10 beats).
Countdown and Tempo are the drive-specific ones, so those two groups only mean
anything under the app that supplies their number. They were designed as Python
data and validated against the real parser, both floors and the drive table
before being emitted as JS, which caught two that the dwell floor would have
rewritten and five whose labels collided with the existing library.

**Tests for (a)–(c) are owed.** They were skipped deliberately at the end of
the 2026-08-21 session and are the first thing to write next. What needs
covering, in rough order of how much it would hurt to get wrong: `shape()` at
the ends and the middle of every curve; `plan_at` returning a solid mid-fade
and the stop's own style during its hold; `sequence_safe` flooring a stop's
style period *even for a one-shot of three stops* (the exemption asymmetry
above); `look_for`'s four-step resolution order, including a mode look beating
a state look; the round-trip of the three new stop keys; and
`test_look_presets.py`, which slices `LOOK_PRESETS` and currently assumes
every entry has an `effect` — five of them now have a `sequence` instead, and
both floors need checking, not just `flash_safe`. A hand-run of that last
check passed at the time of writing (all 42 presets clear both floors).

### 35. A freshly seeded scene fails its own Check

Found 2026-08-20 while driving the offline editor to verify **30a** — not
caused by it, and present on the commit before. Click **New scene**, click
**Check**, and the editor rejects the config it just wrote you:

> • Pomodoro: Get-ready countdown must be more than zero
> • Stopwatch: Timer name is required

Two separate causes, each small and each worth fixing on its own terms:

- **The `duration` widget ignores its own `min`.** Its `validate()` hard-codes
  `seconds <= 0` as an error ([widgets.js](aibutton/web/static/widgets.js)),
  while `lead_in_s` declares `min: 0` and defaults to `0.0` — zero is the
  *documented* value there ("Zero for a Pomodoro — you started it
  deliberately"). So a legal default is unsaveable through the editor. The fix
  is for the widget to honour `spec.min` rather than assume every duration is
  positive; check the other `duration` fields before changing the default, in
  case any of them is relying on the accident.
- **`StopwatchBehavior.log_as` defaults to `''` while schema.js marks it
  `required: true`.** One of the two is wrong. A stopwatch that logs nothing is
  a coherent thing to want, so the descriptor is the likelier offender — but
  this is the mirrored-tables problem in its softest form (a Python default and
  a JS `required` disagreeing), and neither side is currently tested against
  the other.

The general lesson is the testable one: **nothing checks that the modes the
editor seeds pass the editor's own validators.** `test_schema_mirror.py`
already deleted a "descriptor defaults must parse" test for a good reason
(`defaults()` deliberately starts required fields blank), but *seeded whole
modes* are the opposite case — `BUILTIN_MODES` and the from-scratch seed are
meant to be complete. That is the test to add.

### 31. Lifecycle hooks — `on_enter` / `on_exit` on `Mode`

**Split out of 23 (designed 2026-08-19). The design is ARCHITECTURE.md
"Composition: an app's edges" — read it first; this item is build only.**
Two optional `Action` fields on `Mode`, not on each behaviour: parser +
serialiser in [config.py](aibutton/config.py), fired from `enter_takeover`
in [main.py](aibutton/main.py) at the two moments it already logs
`mode_enter`/`mode_exit`, editor fields in
[schema.js](aibutton/web/static/schema.js) (tinker tier, once **14** ships).
A hook is fire-and-forget like all feedback: a webhook that fails logs a
warning and never blocks entry or exit.

**Definition of done.** A mode can post a status webhook on enter and clear
it on exit with zero per-template code; tests cover parse fallback (a bad
hook is dropped with a warning, the mode survives) and firing order (enter
hook before the loop starts, exit hook after it ends).

### 32. Session summaries — apps report structured results

**Split out of 23; needs 31, because hooks are the carrier.** Each takeover
reports a flat bounded dict of scalars on exit (`{"rounds": 8, "total_s":
480}`); the exit hook merges it into a webhook payload and maps it to OSC
arguments. Contents are each app's decision — the contract (flat, scalars
only, bounded key count) is in ARCHITECTURE.md, and it is deliberately a
snapshot a future manifest can declare as data. Start with pomodoro,
stopwatch, counter, reaction and hotcold; the rest may honestly report
nothing.

**Definition of done.** An exit webhook carries the session's numbers; apps
with nothing to say cost nothing; tests assert one real summary end to end.

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

- **Presses dropped while busy.** The loop runs one action at a time and
  discards presses during the 2 s SUCCESS display. Deliberate, but it makes
  fast repeated taps feel dead — worth revisiting if it grates in daily use.
  (Relevant to 12b if "performance" means device latency.)
- **Sound design** *(firmware)* — review "Smart Button Sound Design Research"
  (Obsidian) and replace the placeholder tone tables carried over from the Pi
  build. A matching sound palette, pushed the way the LED palette is, is the
  obvious shape.
- **MANUAL.md's reference tables have fallen behind.** §5.1's "Available
  actions" lists four of the nine that exist (no readout, OSC, MIDI, standby or
  named actions) and §2's gesture table stops at the triple tap, three sprints
  after four- and five-tap shipped. Noticed while adding `standby`; deliberately
  not half-fixed, because a table that is 5/9 correct reads as audited and is
  not. One sitting, against `ACTIONS` and `GESTURES` in schema.js.

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

- ~~**30a. A named action pool**~~ — shipped 2026-08-20. `AppConfig.actions`,
  referenced from any gesture by a **bare string** (`"short_press": "smoke"`),
  which is free by construction: every binding ever written is an object, so a
  string can only mean this. Internally `config.NamedAction`, resolved at *use*
  time by `config.resolve_action` at the three dispatch sites that bind an
  action (main.py's ambient `handle`, `run_control`, `run_signal`).
  Naming stays optional and inline actions are untouched. The parser warns
  about a name with nothing behind it and **keeps the reference**; a pool entry
  may not itself be a name, which is where the one-level guarantee is made
  instead of a cycle check. UI: a tinker-tier **Named actions** section on the
  Modes tab (rename rewrites every reference, delete deliberately does not) and
  a "Use a named action" option on the mode editor's gesture picker.
  The rule this leaves behind is in [CLAUDE.md](CLAUDE.md).

- ~~**The on/off toggle's action**~~ (Smaller, worth doing) — shipped
  2026-08-20 as the `standby` action, which is what the 5-tap gesture had been
  waiting for. **Ambient-only**, which was the open decision: it toggles a
  session flag, and while it is set the ambient layer answers nothing and logs
  nothing except the gesture that undoes it. Takeovers are untouched — a
  scheduled alarm still rings — because an alarm you set is not a thing a
  stray five-tap should cancel. Not persisted: an "off" surviving a restart is
  a button that comes back dead with nothing on it saying why. IDLE wears a dim
  solid `#101010` while asleep, substituted inside `main.set_led` at the same
  point a mode's own look is (so every path back to IDLE stays dim, and the
  flash floor is still applied exactly once).

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

- ~~**26. Colour-coded Actions pages, and the launcher's fate**~~ — shipped
  2026-08-19 (the eyeball check on hardware split off as **26b**). A control
  page owns its colour at zero new code: `MODE_LED_STATES["control"]` claims
  LISTENING — the state the page actually sits in — so a page names a look,
  wears it the whole time it is open (`resting()` already re-pushes after
  every action's flash), and a sub-page visibly changes it via the machinery
  `enter_mode` already had. LISTENING became the system's one **dual
  citizen** (see CLAUDE.md's Lights-tab invariant): the ambient layer wears
  it with no mode involved, so it stays globally editable too. **The
  launcher's fate, decided in writing: both survive.** The launcher stays
  the fresh-config front door — it is self-maintaining (`targets: []` lists
  every app), and a fresh config cannot know what pages its user wants;
  an Actions page becomes the front door by binding it yourself, which is
  the power move and the documented intent. A fresh config ships
  `double_tap → Launcher` (TODO 5).

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

- ~~**5. The floor mode is permanent, named "Home", and routes into
  takeovers**~~ — shipped 2026-08-19. Protection is **structural, not a
  stored flag**: the invariant is "at least one Always-ambient mode exists" —
  the parser seeds Home (appended last, warning surfaced to the editor)
  whenever a config would violate it, scenes covered for free because they
  merge before the one parser; the editor refuses only the delete or rescope
  that would leave zero, never a particular mode. A fresh config ships four
  modes: Home (`short → log`, `double → Launcher`, `long → Pomodoro`) plus
  Launcher, Pomodoro and Stopwatch. **One deviation from the old spec, on
  purpose:** double tap enters the *launcher*, not the stopwatch — that spec
  predates the launcher, double tap is the launcher's gesture by rule, and a
  fresh config with no launcher binding would fail the "all apps reachable
  without the web UI" gate.

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

- ~~**24. Follow the DAW's tempo — MIDI clock in**~~ — shipped 2026-08-19. The
  metronome takes a `clock_port`; set it and the tempo follows the project.

  **What arrives.** MIDI Clock is `0xF8` sent **24 times per quarter note**,
  plus `0xFA`/`0xFB`/`0xFC` for start/continue/stop. The tempo is never
  transmitted — it is inferred from the intervals. **Not MIDI Time Code**,
  which carries SMPTE position and says nothing about tempo; a DAW offers both.

  **A median, not a mean** ([midi_clock.py](aibutton/midi_clock.py)). One late
  delivery is normal on a driver thread, and a mean lets a single 15 ms
  straggler drag the answer. The price is that a deliberate tempo change takes
  half a window to be believed, which is half a beat — the right trade against
  lurching on every scheduling hiccup. Measured on a loopback: within 1–2% of
  the target, and that residual was the *test sender's* per-pulse overhead, not
  the receiver.

  **`midi_out.py` became `midi_io.py`.** Sending and receiving are not
  symmetrical — output is a call, input is a callback on someone else's thread
  — but they share the backend question, and answering it twice in two modules
  would have been the drift this codebase keeps testing for.

  **The bug worth remembering, because it kills the process rather than raising.**
  A ctypes callback the driver still holds must be kept alive by something
  Python can see. The first version closed over the `WINFUNCTYPE` object and
  then `del`-ed it inside the closer — which makes the name *local to that
  function*, so the closure never captured it, the object was freed the moment
  `listen()` returned, and the next pulse called freed memory: **illegal
  instruction, no traceback**. It reads like careful cleanup. Now parked on the
  closer as an attribute, and written up in CLAUDE.md's conventions.

  **Three decisions.** The clock owns the tempo while it is running and **taps
  no longer set it** (they still mark a beat and still click) — two things
  steering one number is a metronome that argues with the session. Silence
  longer than two beats **holds the last tempo** rather than blanking, because
  a DAW that is quit sends no `0xFC` and the pulses simply stop. And the light
  is only re-pushed when the estimate moves by ≥0.5 BPM, or a rock-steady
  project would cost a radio write five times a second.

  **This is permanently host-side**, not one of the "assumes the host is awake"
  compromises to find and remove later — the DAW is on the host by definition.

- ~~**A control-surface template, and a DAW command picker**~~ — the two
  things bench-testing MIDI against Studio One turned up, shipped 2026-08-19.

  **The picker.** A MIDI action now opens with "Start from a DAW command" —
  Play, Record, Stop, Marker, Loop, Metronome and the rest, as **Mackie
  Control** note numbers. That choice is the whole value: MCU is a de-facto
  standard every major DAW implements, so a DAW told it has a Mackie Control
  already knows what note 94 means and there is nothing to learn. The table is
  **JS-only and creates no mirror** — the action stores a number, and `describe`
  reads the name back off it, so Python never needs to know 94 is Play.
  Reusing the webhook's preset widget meant generalising it first: it assigned
  `url` and `payload` *by name*, so a generic-looking widget was quietly
  webhook-only. It writes whatever its table says now.

  **The template.** `control` — a takeover whose gestures each fire their own
  action. It exists because neither existing shape worked as a remote: an
  ambient `actions` mode maps gestures to actions but **cannot be an
  `enter_mode` target**, and a `signal` light is a takeover but **cycles**, so
  reaching Record would pass through Play and start playback. Behaviour was
  free (`ActionsBehavior` already had the map); the cost was the usual template
  tax — dataclass, parser, allow-lists, serialiser, run loop, descriptor.

  **Three decisions in it.** Long press is **not bindable and the parser drops
  it** — this is the template where breaking the escape rule is most tempting,
  so it is enforced rather than documented (now an invariant in CLAUDE.md).
  The confirmation flash is `_CONTROL_CONFIRM_S = 0.3` rather than the ambient
  layer's 2 s, because a surface you stay inside is meant to be played and two
  seconds between Play and Record would feel broken; presses during it queue
  rather than drop, and a test presses ten times to prove it. And the editor's
  gesture list became **descriptor data** (`gestures`, `unlessLogged`) rather
  than a branch, so a third gesture-mapped template costs nothing there.

  **Also caught: `BUILTIN_MODES` had no test at all.** The DAW preset first
  shipped as `actions` + `manual`, which is not an allowed pair — it would have
  saved, been skipped by the parser, and vanished with only a warning in a log
  nobody reads. Every preset's template/activation pair is checked now.

- ~~**22. A `midi` action, because Studio One does not speak OSC**~~ — a
  sibling of `osc`, shipped 2026-08-19. [midi.py](aibutton/midi.py) encodes the
  three bytes and knows nothing about ports;
  [midi_io.py](aibutton/midi_io.py) gets them to one; `actions.py` maps the
  result onto ok/not-ok and nothing else.

  **The research, kept because it is the expensive part.** PreSonus document
  control surfaces over **MIDI / Mackie Control** and Studio One Remote uses
  their own UCNet protocol — neither is OSC. TouchOSC's own documented route
  into a DAW is a bridge converting OSC *to* MIDI, which is the same admission
  from the other side. **High confidence, not certainty**: the PreSonus thread
  that would have settled it was closed in November 2024. If a native OSC
  listener turns up in Studio One, `osc` was always there.

  **The dependency the item accepted turned out not to be installable, and
  is no longer the route.** `python-rtmidi` publishes **no wheel for Python
  3.14** — `pip download --only-binary=:all:` finds nothing — so it builds from
  source, and the build fails on this machine inside meson's own temp-directory
  cleanup (`PermissionError: WinError 32`) after compiling successfully. Rather
  than pin an older Python or chase the build, MIDI now goes out through
  **`winmm.dll` via `ctypes`** ([midi_io.py](aibutton/midi_io.py)):
  `midiOutShortMsg` exists to send exactly this three-byte message, it has
  shipped with Windows since the 90s, and **it is what python-rtmidi calls one
  layer down** — its own error strings name `MidiOutWinMM`. So the action costs
  **no dependency at all on Windows**, which is strictly better than what the
  item planned. rtmidi is kept as the Linux/macOS backend and stays unlisted.

  **Three decisions worth not relitigating.** The backend is chosen **once at
  import, Windows first**, because both answers are about the machine rather
  than the moment. The port is matched on **part of its name**, because Windows
  renames what loopMIDI creates (`Button` → `Button 2`) with a suffix that
  changes between sessions. And the port is **opened per send rather than
  cached**: a held handle goes stale exactly when loopMIDI or the DAW restarts,
  and it fails as silence, which is the worst failure available here.

  **What is proven, and what is not.** The encoder is tested against the spec's
  status bytes, and the send path is tested **against the real OS** — the suite
  enumerates this machine's MIDI devices and sends a note-off to one, which is
  what catches a truncated ctypes handle or a mis-packed DWORD. What has *not*
  happened is loopMIDI and Studio One: nothing has confirmed Control Link
  learning a message. That is a bench test, and it is the only thing between
  this and the item's original definition of done.

- ~~**A drift audit, and the mirrors it found unwatched**~~ — a deliberate
  sweep for dead code, unfinished edges and untested duplication.

  **The real finding was four mirrored tables with no drift test**, in a
  codebase whose stated rule is that mirrors are tested rather than trusted:
  the three default ramps (countdown, hot/cold, reaction), `POMODORO_COMMANDS`,
  the whole style table's `uses`/`strobes` flags, and the Signal template's
  default positions. Two comments in `schema.js` even claimed *"test_webui.py
  fails if they drift"* — it did not, and never had.
  [test_schema_mirror.py](tests/test_schema_mirror.py) now covers all of them
  and those comments point at something real.

  **Dead code removed**, each verified unreferenced repo-wide first:
  `device.STYLE_USES_PERIOD` (no reader, no mirror, no test — a copy waiting to
  drift; which styles use a period is declared once on the editor's own style
  descriptors now), `INTEGRATION_BY_ID`, `ledPreview.unpaint` (the animation
  loop already drops disconnected nodes, so it was redundant rather than
  load-bearing), `help.isHelpOn`, two unused test imports, and two engine
  helpers that no longer needed exporting.

  **One capability had gone missing in the colour-engine move**:
  `/api/dev/led`'s `state` parameter had no caller left, so every live preview
  reported IDLE. It is passed by whoever mounts the control now — which is
  strictly better than the bench's dropdown, because the caller already knows
  which state it is editing.

  Also: `control-panel.port` joined `.gitignore` beside its lock and prefs, and
  the prose that still described a "test bench" was corrected in six places.

  **Deliberately left alone**, so the next sweep does not re-litigate them: the
  reserved-and-unimplemented `OTA_CONTROL` / `GESTURE_HOLD` (documented as
  reserved, and the reflash bar is high); the v0.2 `rules` and `*_minutes`
  migration paths (tested, and the whole point is that old configs keep
  working); and `schema.js`'s internally-used exports, which are a coherent
  public surface for a data module and would only churn.

- ~~**19d/e. One colour control, and mode colour moved onto the mode**~~ —
  [colorEngine.js](aibutton/web/static/colorEngine.js) is now the only thing
  that edits a `LedEffect`, mounted by the Lights tab's system states, the
  named-look pool and each mode's own page. It returns `{el, validate}` like
  every widget, so it drops in anywhere.

  **The Lights tab holds the button's vocabulary and nothing else.** Mode-owned
  states are edited on the mode, because a mode you configure in two tabs is
  not modular. Their palette entries stay in config as the invisible fallback
  (19d's original decision, unchanged) — only the editor group went. **19e came
  free with it**: the metronome's dead period field was in that group.

  **The test bench was scrapped as a place and kept as a capability.** Pushing
  a look at the hardware now belongs to *every* picker, which is where it
  should always have been — it is how you tell a wiring fault from a config
  one. It is optional by construction (`api.showLook` may be absent), so the
  offline editor still works; the Diagnostic row that README's byte-order
  diagnosis depends on rides along with it.

  A mode page can now make a look without leaving: pick a preset and it lands
  in the pool, named and selected. Editing a look shared with other modes says
  so and offers a copy, because a *named* look changing everywhere is correct
  and surprising in equal measure.

  **37 built-in presets** in eight groups (`LOOK_PRESETS` in schema.js),
  offered wherever colour is chosen and stored nowhere until saved.
  [test_look_presets.py](tests/test_look_presets.py) runs every one through the
  real parser and the real flash floor, so the library cannot ship a colour the
  config would reject or a rate it would clamp.

- ~~**The offline editor was dead on arrival, and had been for a while**~~ —
  found by opening it rather than by a test. `menu.js` and `modeEditor.js` both
  wrote `paint as applySwatch`; the bundler emitted that binding once per
  module, and the browser refused the entire script with *"Identifier
  'applySwatch' has already been declared"*. Every module in the editor never
  ran and the page opened blank.

  Two modules agreeing on an alias is the normal case, so the bundler now binds
  it once and only raises when one alias would mean two different symbols.
  The gap that let it ship is closed too: the suite checked the bundler's
  *inputs* and never that the bundle it emitted could be parsed. It now asserts
  nothing is declared twice in the shared scope — over the emitted bundle,
  because the duplicate appears in neither source file.

  Same lesson as the sliver: **it looked built.**

- ~~**The control panel wedged, invisibly**~~ — reported as "it says it's
  already open but it's not showing in the tray, and the window won't appear".
  Three separate faults wearing one symptom:

  **The dialog could not be seen or dismissed.** `_already_running()` built a
  Tk root, *withdrew* it, and put a modal `showinfo` on it. On Windows that
  renders with no taskbar button and no focus, so the second process sat there
  forever holding an invisible modal. The rule is now in CLAUDE.md: never
  parent a dialog to a withdrawn root.

  **The advice was unfollowable.** It said to look in the system tray, and
  Windows files new tray icons into a hidden overflow flyout by default. The
  panel now shows its window at launch (`show_on_start`, switchable from the
  menu), because a tray icon is not a discoverable place to put the only UI.

  **"Already running" and "wedged" were indistinguishable.** A second launch
  now asks the first over a loopback socket
  ([beacon.py](aibutton/control/beacon.py)): answered means it raises its own
  window and the newcomer exits quietly, which is what every other
  single-instance app does. No answer means wedged, and it says so with the
  PID instead of reassuring you. The port file is deliberately *not* trusted on
  its own — connecting is what settles it, the same reason the run lock is an
  OS lock rather than a PID file.

  Also: `control.pyw` waited on the panel for the whole session, leaving a
  second `pythonw` with an identical command line — confusing in Task Manager
  when you are already trying to work out why there seem to be two. It now
  launches and exits.

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
