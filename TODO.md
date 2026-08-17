# To-do

The ESP32 transition ([DESIGN-ESP32.md](DESIGN-ESP32.md)) is finished — the
button is real hardware talking to the host over BLE. Everything below is
feature work.

This is the **near-term list**: Stage 2 of [ROADMAP.md](ROADMAP.md), the
MVP/demo push. Anything that reshapes the architecture — the app runtime, the
one-manifest move, moving the brain onto the device — lives in
[ARCHITECTURE.md](ARCHITECTURE.md) and the roadmap, not here. Two items below
(**0a**, **0b**) are the exceptions: they are Stage-2 work *because*
deferring them gets expensive once more hardware exists.

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
  it looks like a dead board. **0c** puts the pin back to 4.
- **No ring.** The board's onboard WS2812 is the only light, and it is now the
  *accurate* one — the byte-order fault that made both LEDs render red as
  green is fixed and flashed (see Done).

The ESP32 itself is untouched and the service runs normally, so the rest of
the list is unaffected. Re-soldering is **0c**, and the 5 V rework belongs in
that same sitting rather than putting it back exactly as it was.

## How to work this list

Each numbered item under **Sprint** is written to stand alone: context, the
exact files involved, and a definition of done, so it can be picked up in a
fresh session with none of the history that produced it. Items are not
strictly independent — where one depends on another it says so — but you
don't need to read the others to start.

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

## Four bodies of work, not fifteen items

The numbered list below is written so each item stands alone, which is right
for picking one up cold and wrong for deciding what to do next: the items that
*share a reflash* are scattered across it. This section is the other view.

**The headline: most of the outstanding feature requests are protocol v1's
payload.** Richer colour (gradients, sequencing, per-colour durations,
per-mode looks) is what **D4**'s "ephemeral effects" is *for*. Arbitrary tap
counts and hold levels are what **D5**'s "parameterised gestures" is *for*.
Neither was specified as a protocol feature when it was asked for; both are.
So they are one revision, or they are four reflashes and four chances to drift
the mirrored tables.

| Body of work | Items it spans | Gate |
|---|---|---|
| **The colour engine** — a stop list instead of `{style, 2 colours, period}`; progress ramps; named looks a mode picks from | 0b·3 ✔, **3** ✔, **4** ✔, 0a's per-app colour ✔ | ~~Wire change~~ — **done**; the stop list itself is now the only piece left, and it lives with 15/16/17 |
| **The gesture engine** — N taps, hold levels, the ramp that renders them | 0b·2 ✔, the 5-tap gesture ✔ (its action is not) | ~~Wire change~~ — **ungated** for taps; hold levels still need firmware |
| **Depth without the wire** — metronome config ✔, event values ✔, filtering/export ✔, Tinker mode | **1** ✔, **9**, **12**, **14** | None — ship freely |
| **Reach and hosting** — launcher, remote UI | **0a**, **7**, **8** | 0a gates 7 |
| **Saying a number** — ambient counting, count readout, progress | **15**, **17** | Wants the stop list (**19b**) first — a readout *is* a stop list |
| **The light as a language** — ladder ✔, stop list, one-offs, where colour is edited | **19** | None for a–c; **19d** is a UI move |
| **Play** — timing/rhythm and guessing games | **16** | Forgiving games ungated; tight rhythm needs Stage 3's on-device runtime |

Two things sit outside the table. **0c** is hardware (re-solder + the 5 V
rework) and gates nothing but its own verification. **18** (Notion) is process
and is **parked** — the analysis is written down, the decision is not needed
yet, and nothing exists in Notion to keep in sync.

**The gate column is the news.** Two of these were blocked on a reflash and
are not any more. With item 3 shipped, **0a's launcher is the next thing on
the critical path** and its only remaining dependency is a core change in
`main.py` — a takeover mode that can enter another one. Colour, gestures and
config are all in place for it.

**Item 4 shipped, and it left the stop list standing alone.** The slider and
the safety floor are done (the floor is a *setting* now, defaulting to 3 Hz —
see item 4). What item 4 was carrying for everyone else is not: a count
readout is a stop list, a Simon sequence is a stop list, and a progress ramp
is a stop list driven by progress instead of the clock. Three of the four
newest items (**15**, **16**, **17**) all queue behind that one structure.
Design it once, deliberately, and they get cheap; improvise a `blink_n_times`
effect instead and you have spent a wire feature on a special case of it.

**One constraint item 4 handed forward, in writing:** the flash floor is
enforced over `period_s`, and a stop list breaks that — five colours at 0.1 s
each is a 2 Hz cycle but a 10 Hz change rate. Whoever designs the stop list
owns redefining the floor over *transitions*. `config.flash_safe` is the one
function to change.

Three things fall out of that table and are worth stating rather than
rediscovering:

- **One structure covers three of the colour asks.** A list of
  `{colour, hold, fade}` stops subsumes all six current styles (solid = one
  stop; flash = colour + black, stepped; fade = two stops, smoothed; breathe =
  colour → black) and *then* gives gradients (many stops), sequencing (stepped
  stops) and asymmetric duty (unequal holds) for nothing. Design it once.
- **A ramp is a different axis from a stop list**, and also reusable: the same
  stops driven by *progress 0→1* instead of by the clock serve a countdown's
  red→violet walk, a Pomodoro block, and the hold-level indicator. Write it
  once, four consumers. ✔ **Built and proven** — [ramp.py](aibutton/ramp.py),
  with the countdown as its first consumer. What the prototype settled, before
  any of it reaches the wire:
  - **Ramp and effect stay separate objects.** The countdown flashes at a fixed
    period the whole way through while the colour travels. Folding progress
    into `LedEffect` would have made "flash" and "fade over the timer" two
    settings fighting over one light.
  - **Positions, not durations.** A stop is pinned at a fraction, so the same
    ramp serves a two-minute egg timer and a two-hour deadline, and nothing in
    the module mentions seconds. That is what lets hold levels reuse it.
  - **Push on change, not on tick.** `ramp.differs` bounds a full sweep to a
    couple of hundred palette writes whatever the duration — the number that
    makes a host-side ramp affordable at all, and the one to keep when this
    moves on-device.
  - **Even spacing is the default, not the rule.** Bare colours spread
    themselves; pinning one keeps it. That is the "make one colour
    shorter/longer" ask, and the editor only re-spaces a ramp that was already
    even.
- **N-tap does not cost latency.** A single tap already waits out the 0.4 s
  double-tap window before it emits ([trigger.py](firmware/trigger.py)).
  Counting to N and firing on a quiet gap is the same wait, measured from the
  last tap instead of the first.

~~**Do not ship the colour work as host-side palette rewrites in the
meantime.**~~ **Moot — pushing a look is now the supported path.** Pass an
effect to `set_led` and the device renders it without storing it; both former
reach-arounds (`run_metronome`, `run_countdown`) were converted and the
stored palette is no longer written by either. What is still host-side is the
*ramp*, which is evaluated on the PC and pushed on change — honest for a
countdown that steps every few seconds, and the thing that moves on-device
later.

## Sprint

### 0a. Reaching more than three apps — a launcher

**Do this before item 7.** "Load the button with as many apps as it will fit"
does not currently work, and the arithmetic is the reason: a takeover mode is
reached by an `enter_mode` action bound to a gesture in an ambient mode, and
there are three gestures. Keep one for everyday logging and **two apps are
reachable**. Building ten apps you cannot get to is wasted work.

**What to build.** A launcher: a takeover mode entered by one gesture, where
short press cycles through the installed apps (the LED showing *which* one),
long press launches, double tap backs out. The alternatives — N-tap gestures,
or picking the active app in the web UI — are in
[ROADMAP.md](ROADMAP.md)'s Stage 2 section with why they lose.

**The core change it needs**, and the reason this isn't just another preset:
today `enter_mode` is only reachable from the ambient layer
([main.py](aibutton/main.py)'s `handle`); `enter_takeover` has no path back
into itself, so a takeover mode cannot start another one. That is the one
thing to add, and it wants care — a launcher that can launch itself, or an
app that enters the launcher that enters the app, needs a depth guard or an
explicit "replace, don't nest" rule. Decide which and write it down.

~~**Depends on** per-app colour (item 3)~~ — **that dependency is discharged.**
Ephemeral effects shipped (0b·3) and named looks shipped (item 3), so a
launcher cycling through apps can show each one's colour by reading
`mode.looks` and calling `set_led(state, effect)`. Nothing in the firmware and
nothing in config is missing for it.

**Also cheaper than it was:** `triple_tap` is a real gesture now, so the
launcher can be reached without spending one of the original three.

**What is actually left**, and it is now the only thing: the core change in
the next paragraph — a takeover mode that can enter another takeover mode,
plus the depth guard or the explicit "replace, don't nest" rule.


### 0c. Re-solder the button, and move its LED to 5 V while it is off

**Do this before anything whose test is "look at the ring".** The button is
currently de-soldered (see the state note at the top). This item puts it back
— and the reason to read it before reaching for the iron is that soldering it
back exactly as it was would preserve a known fault.

**What was found.** Pushing known colours at both LEDs from the Lights tab's
test bench turned up two separate faults, not one:

1. **Byte order — fixed, flashed, confirmed on hardware.** `NEOPIXEL_ORDER`
   and `ONBOARD_NEOPIXEL_ORDER` in [hardware.py](firmware/hardware.py) were on
   the wrong LEDs. Nothing else to do here; it is recorded because the
   *evidence* is the useful part. `#ff0000` lit **both** LEDs green, `#00ff00`
   lit both red, `#0000ff` was correct — one R/G swap on both at once, which
   is what exchanging those two settings produces and is distinguishable from
   either one being wrong alone (that would have made the two disagree). Blue,
   yellow and white are fixed points of an R/G swap, which is exactly why the
   fault hid on them; cyan↔magenta is the pair that talks.

2. **Channel imbalance on the ring — open. This is the rework.** With the
   order corrected the onboard LED renders accurately and the ring still does
   not: it renders white as light orange, cyan with a green tint, magenta with
   a red tint, yellow with an orange tint. One consistent ordering,
   **R > G > B**, measured off video at roughly `1.00 : 0.54 : 0.44`.

**The diagnosis, and why it is a wiring change rather than a constant.** That
ordering is a forward-voltage fingerprint. A WS2812's red die is AlInGaP at
~1.9–2.1 V; green and blue are InGaN at ~3.0–3.2 V. Each channel is a
constant-current sink that needs headroom above Vf to regulate. The ring's VDD
is on **3V3** ([hardware.py](firmware/hardware.py)'s wiring block), so red has
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
trim beside `LED_BRIGHTNESS` in [hardware.py](firmware/hardware.py) — it is
exactly a hardware.py-shaped constant, a property of that physical LED rather
than a preference, and it would belong on the device for the same reason the
palette's rendering does. The honest cost: it can only attenuate, so it pulls
R and G *down* to meet B and you get neutral white at whatever brightness the
starved blue channel can manage. 5 V buys correct colour *and* full brightness;
calibration buys only the first. Do not add it before the three-level test
says headroom is not the cause.

**Definition of done.** Button re-soldered and pressing again (a real gesture
reaching the host, not a simulated one); **`BUTTON_PIN` back to 4** — it is
temporarily 0 so the board's BOOT button can stand in, and leaving it there
would make every reset a coin-flip on entering download mode; the three-level
and load-ladder results written down here; the LED's supply and any
level-shifting recorded in [hardware.py](firmware/hardware.py)'s wiring block;
and `#ffffff` reading as white on the ring, or an explicit note saying how far
off it still is and why that was accepted.


### 0b. Freeze the wire protocol as v1 ✔ done

**All four landed.** Two shipped (`DEVICE_INFO`, then effects + gestures
together) and two are reserved-and-documented (`OTA_CONTROL`,
`GESTURE_HOLD`). Kept here rather than moved to **Done** because the
reasoning is the map for the next wire change.

What the freeze actually bought, and the reason to state it as a bar rather
than a milestone: **everything on this list below is now reachable without a
reflash.** Per-app looks, more tap counts, a launcher's per-entry colour — all
of them are host-side data changes now. So the bar for the next protocol
revision is a capability the device physically cannot express today, not a
feature that would merely be tidier on the wire.

The original framing follows, because it is why the shape is what it is:

Four additions that are cheap now, and a flag day once units exist outside
this room. Land them as one revision — each one separately means another
reflash and another chance to drift the mirrored tables
([device.py](aibutton/device.py) / [firmware/protocol.py](firmware/protocol.py),
guarded by [test_protocol.py](tests/test_protocol.py)).

1. ~~**`DEVICE_INFO`**~~ ✔ **shipped, and deliberately shipped first.** A read
   carrying protocol version, firmware version and a capability bitmap
   (`led`/`buzzer`/`palette`, with haptics/battery/imu/mic/ota reserved so two
   future features cannot claim the same bit).

   Going first is a departure from "land them as one revision", and the reason
   is that this item's entire job is to make the other three non-breaking: with
   it in place they are capability-gated additions an old device can decline,
   not a flag day. Batching still applies to everything that is *not* a
   negotiation mechanism.

   Three details worth keeping when the rest lands: bits report what actually
   *came up* (both backends degrade to Null, and a bit claiming a buzzer nobody
   can hear is worse than no bit); a device with no `DEVICE_INFO` falls back to
   `ASSUMED_INFO` so learning to ask never silences an un-reflashed button; and
   `decode_device_info` ignores trailing bytes, so the payload grows by
   appending and an older host stays able to read a newer device.
2. ~~**Parameterised gestures**~~ ✔ **shipped.** The wire carries
   `[kind, param]` alongside the three legacy codes — `GESTURE_TAP` with a
   count, `GESTURE_HOLD` reserved for levels. The classic three still go out
   as one byte and always will, so an un-reflashed host is unaffected; only a
   gesture with no legacy code takes the new form, and `decode_gesture` reads
   both. `triple_tap` is the first host-side gesture to arrive this way, which
   takes the button from three bindable gestures to four — 5-tap and the rest
   are now a data change in `TriggerType`/`GESTURES` with **no reflash under
   them**, which was the whole point.

   The one real decision inside it: counting to N means a double tap can no
   longer fire the instant the second press lands — it has to outlive the
   0.4 s window to prove it is not the start of a triple. Rather than charge
   every button that latency, the host writes `max_taps` over
   `GESTURE_CONFIG`, derived from what the config actually binds
   (`bound_triggers` → `max_taps_for`). At 2 — the default, and what a
   button with nothing longer bound gets — the detector is byte-for-byte the
   one that shipped before, which is why every existing detector test passes
   unedited.
3. ~~**Ephemeral effects**~~ ✔ **shipped.** `LED_EFFECT` takes the same nine
   bytes as a palette entry minus the state code, renders immediately, stores
   nothing, and ends at the next `LED_STATE` write. On the host it is an
   optional second argument to `set_led` rather than a fifth seam method,
   because it is the same assertion carrying more detail.

   `run_metronome` and `run_countdown` were the two reach-arounds and are now
   the two consumers: neither touches the stored palette, so neither needs a
   `finally` to put anything back. A device without `CAP_EFFECT` still shows
   the look — `BLEDevice` borrows the state's palette entry and gives it back
   when the look ends — so the run loops never learn which kind of device they
   are talking to. **No new `LEDState` was allocated; `0x0B` is still the
   highest code.**
4. **An OTA/version handshake** — ✔ *reserved*: `OTA_CONTROL_UUID` and
   `CAP_OTA` are claimed and documented as unimplemented, and the version
   handshake is `DEVICE_INFO`'s first byte. Implementing it is still Stage 4
   and still gates handing a unit to anyone, including a friend. You cannot fix
   a bug in a key fob you don't have.

Rationale and the cost of deferring each: **D4**, **D5**, **D6**, **D8** in
[ROADMAP.md](ROADMAP.md).

### 1. Richer, more precise logging in the Events tab

**Partly shipped.** [store.py](aibutton/store.py) now has the `mode` column
(with an `ALTER TABLE` migration in `_migrate` for existing databases) and
`log_mode_enter` / `log_mode_exit`, which the takeover loops in `main.py`
call, so a takeover session is recorded with its duration. `recent()` and
`/api/events` both carry `mode` through.

**Also shipped since:** the `value` column — one nullable REAL an event may
carry, so the log can record *how much* rather than only *that*. Deliberately
one untyped slot (a column per app doesn't survive third-party apps; folding
the number into `name` breaks `count_today`/`current_streak`, which group by
exactly that string). The metronome is its first user. `_migrate` now adds
each column independently, so a database from any version catches up in one
open.

**Filtering and export shipped too.** `/api/events` takes `kind`, `name`,
`mode`, `since` and `until` alongside `limit`; `/api/events/export` returns the
same rows as a CSV or JSON download; `/api/events/kinds` backs the picker.

Four things worth keeping:

- **One query, two consumers.** The table and the export share `_events()`, so
  a downloaded file cannot disagree with the table it came from — which is the
  failure that makes an export worse than none.
- **`name` is a substring, `kind` and `mode` are exact.** You search a log for
  "coff" and expect "coffee"; you pick a kind off a list and expect that kind.
  LIKE's own wildcards are escaped, so searching for `%` finds rows containing
  a percent sign rather than everything.
- **The window is text comparison, and that is not a shortcut.** `ts` is UTC
  ISO-8601, where lexical order *is* chronological order. That property is the
  reason the stored format is not negotiable.
- **An export defaults to the whole log, not to one page.** Silently handing
  back the most recent 50 rows is the kind of wrong answer only noticed later,
  in a spreadsheet.

The date pickers are days and the log is instants, so the UI converts local
midnight to local midnight with `until` inclusive of the day you chose.
Suite: `test_events_filter.py`.

**What is left:**
- Which *gesture* produced an event, which the `mode` column doesn't tell
  you. Only worth adding if item 12 turns out to need it — don't widen the
  schema on spec. Note this gets *harder* to defer once gestures are
  parameterised (0b·2): "which gesture" stops being one of three.

Whatever you build, keep [test_webui.py](tests/test_webui.py)'s pattern:
assert against the real `EventStore`, not a mock.

### 2. Verify stopwatch / Pomodoro / alarm actually work end to end

Not a feature — a correctness pass. `test_main_takeover.py` and
`test_pomodoro.py` pass, but that only proves the *loops* behave against a
`MockDevice`; it doesn't prove the whole path (BLE gesture → `main.py`
dispatch → LED/sound → web UI status) is right on real hardware. Walk each
one manually with `--ble --config config.json` (or `MockDevice` +
`/api/trigger/*` if hardware isn't at hand) and confirm:

- **Stopwatch**: enter via its gesture, short press laps (check
  `last_message`), long press stops and the elapsed time is what you'd
  expect from a stopwatch, `TIMING` LED shows the whole time.
- **Pomodoro**: work→break→work cycles match `advance` (`auto` / `manual` /
  `break_only`), `extend`/`skip`/`restart` do what their names say, the long
  break fires on the right block count, `WORKING`/`RESTING` LEDs switch at
  the right moments, and a finished work block is actually logged under
  `log_as`.
- **Alarm**: fires at its scheduled time even if another takeover mode is
  running (`main.py` says a due alarm takes priority — confirm it actually
  interrupts), snoozes for exactly `snooze_minutes` and rings again, dismiss
  logs `dismiss_event` once and only once.

File anything broken as its own item here rather than fixing inline if it's
non-trivial - this item is about finding gaps, not necessarily closing them
all in one sitting.

### 3. Put mode-relevant LED pickers inside the Modes tab ✔ shipped

**All three parts of the stronger version landed.** A top-level `looks` pool
in config, referenced by name per LED state from a mode; the picker at the
*top* of a mode's form, above the behaviour fields; and the Lights tab split
into the button's own colours, the mode defaults, and the named-look pool.

The shape, and why it is this and not a per-mode inline effect:

- **A mode names a look; it does not own one.** `looks: {"focus-warm": {...}}`
  at the top level, `"looks": {"WORKING": "focus-warm"}` on the mode. That
  solves "two Pomodoros cannot look different" *and* gives reuse across modes
  *and* is already the shape D4 pushes down the wire - a named look is a thing
  you can send without allocating a global `LEDState`.
- **Which states a mode may colour is data.** `MODE_LED_STATES` in
  `config.py`, mirrored as `ledStates` on each template descriptor in
  `schema.js`, with `test_webui.py` failing on drift. Adding a template means
  adding a descriptor, not a branch in the editor.
- **A missing look costs a colour, never a mode.** A dangling name is dropped
  with a warning and the mode runs on the palette entry. Deleting a look from
  the pool deliberately leaves the references pointing at nothing - the editor
  shows `(missing)` and the parser warns, which is more honest than silently
  changing what several modes look like. Renaming *does* rewrite references,
  because there the intent is unambiguous.
- **The global entry is the fallback, not dead weight.** A mode that picks
  nothing resolves to `None`, which is what `set_led` already means by "no
  override" - so it costs no effect write at all, and a device with no
  `CAP_EFFECT` behaves exactly as it did.
- **Where a live effect gets its shape.** `run_countdown` and `run_metronome`
  build on the mode's look when it has one and on the palette otherwise. That
  makes the countdown's own `style`/`period_s` fields redundant when a look is
  set, and the look wins - having the template's fields quietly override a
  chosen look would make picking one do nothing. Those two fields are now a
  deprecation candidate.

**Verified** in a throwaway instance on port 8099: the Lights tab renders the
three groups, a Pomodoro's form shows one picker per owned state at the top,
picking a look updates the summary live, Save round-trips through the real
parser with no warnings, and renaming a look rewrote the references in two
other modes. Suite: `test_looks.py`, plus the drift guard in `test_webui.py`.

**Left open:** item 14 (Tinker mode) was waiting on this and can now decide
what "basic" contains - the look picker is the thing that should be at the top
of a basic form. The old scope of this item follows.

---

**Current state.** The Lights tab ([menu.js](aibutton/web/static/menu.js)
`_renderPaletteSection`/`_renderPaletteRow`) lists all 10 `LED_STATES`
globally, flat. Four of them are really "what does *this specific takeover
mode* look like": `alarm`→`ALERT`, `stopwatch`→`TIMING`,
`counter`→`COUNTING`, `pomodoro`→`WORKING`+`RESTING`. Right now, editing a
Pomodoro's colours means leaving the Modes tab, finding `WORKING`/`RESTING`
in a flat list of ten, and having no visual link back to which mode they
belong to.

**What to build.** In `ModeEditor`'s detail pane
([modeEditor.js](aibutton/web/static/modeEditor.js)), for a takeover mode,
render the effect editor for its associated LED state(s) inline - reuse
`_renderPaletteRow`'s swatch/style-picker/colour-picker construction (it's
already built from `LED_FIELDS`/`LED_STYLE_BY_TYPE` in
[schema.js](aibutton/web/static/schema.js), so it should lift out cleanly
rather than duplicate). Map template → LED state key via a small table next
to `TEMPLATE_BY_TYPE` (or add an `ledStates: string[]` field on each
takeover template's descriptor - that's the Open/Closed-correct place per
CLAUDE.md's schema-as-data rule).

**The stronger version that was actually asked for**, and it is worth building
this rather than the paragraph above, because the two cost about the same and
only one of them scales:

- **Colours come first, not last.** In a mode's detail pane the look sits at
  the *top*, above the behaviour fields. What a mode looks like is how you
  recognise it going off across the room; it is not an afterthought setting.
- **A mode picks from a pool of named looks rather than owning an inline
  effect.** A top-level `looks: { "focus-warm": {...} }` in config, referenced
  by name. This is strictly better than a per-mode override: it solves "two
  Pomodoros cannot look different" *and* gives reuse across modes, *and* it is
  already the shape **D4**'s ephemeral effects want to push down the wire — a
  named look is a thing you can send without allocating a global `LEDState`.
- **The split stays clean.** System states (IDLE/LISTENING/THINKING/SUCCESS/
  ERROR) stay in the Lights tab, because they belong to the button rather than
  to any mode. Mode-owned states (ALERT/TIMING/COUNTING/WORKING/RESTING/
  METRONOME) move into the mode editor as a look reference. "Mode light
  settings in modes, everything else in the lights panel" is exactly that line.

**Real dependency, not optional polish:** every Pomodoro today shares the
*one* `WORKING`/`RESTING` palette entry — this was already flagged as
"Palette for the built-in modes" in the old list. Moving the picker into the
Modes tab without solving this means two Pomodoros still can't look
different, which defeats the point of putting the picker next to the mode.
Solving it needs a per-mode override stored on the `Mode`/behaviour itself
(`config.py`), not just the global `led_palette` dict, with the global entry
becoming the fallback when a mode has no override.

**The wire half of that is done.** It used to also need "its own wire path,
or folded into what's sent on connect"; it doesn't, because a per-mode look
*is* an ephemeral effect — `set_led(state, effect)` already pushes one and
`run_countdown` already does exactly this with a colour it computes per
tick. So what is left is `config.py` (parsing and validation for a named
`looks` pool, or a per-mode override), the editor, and having the takeover
loops pass the mode's look to `set_led` instead of nothing. **No firmware, no
reflash.**

### 4. Turn "seconds per cycle" into a slider, with a safety floor ✔ shipped

**Both halves landed, and the number turned out to be a third question.** The
slider exists, the floor is enforced in one place rather than three, and the
answer to "3 Hz or 4 Hz" was *neither as a constant*: it is a **setting**,
`min_flash_period_s`, defaulting to the recommended 3 Hz.

The shape, and why it is this:

- **The floor is a setting, and that is a deliberate product call.** This is
  one button on one desk and its owner may decide it can go faster. So a value
  below the recommendation is *honoured and warned about* - silently clamping
  would make the setting a lie, and silently accepting would make the hazard
  invisible. A value that is not a positive number is a different failure and
  falls back per-key like anything else.
- **One constant, in the module both halves may import.**
  `device.SAFE_MIN_PERIOD_S` (3 Hz, per WCAG 2.3.1), because `config` imports
  `device` and never the reverse. `main._MIN_FLASH_PERIOD_S` is gone;
  `metronome_flash(bpm, min_period_s)` takes the effective floor as an
  argument, which is the pure-core rule applied to a number that is now
  configurable.
- **One gate, not three.** `config.flash_safe(effect, floor)` is pure, and
  `main.set_led` is the single choke point every pushed look passes through -
  so a mode computing its own effect cannot route around it, and neither can a
  hand-edited scene file. The stored palette is floored where it is *pushed*,
  because the device renders those entries without asking. `run_countdown`'s
  own `max(...)` was removed rather than left as a second place to keep in
  step, and the Lights tab's test bench is floored too.
- **Only hard on/off styles are floored.** `flash` and `alternate`
  (`device.STYLE_STROBES`, mirrored as `strobes: true` on each style
  descriptor in `schema.js`, with a drift test). A fast `breathe` or `fade`
  travels the same distance smoothly and reads as shimmer, so flooring them
  would cost the slowest legal fade a third of a second and buy nothing.
- **The slider's minimum is live.** `LED_FIELDS`' `period_s` is
  `kind: 'range'` with `min` as a *function of ctx* - the same trick `select`
  already used for dynamic `options` - so raising the setting widens the
  slider instead of leaving it lying about what will be accepted. `number`
  learned the same dynamic bounds on the way past. The ceiling stretches to
  fit a stored value already above it, so a 600-second breathe in an existing
  config is not silently rewritten the moment its form renders.

**Still open, and it was already written down here:** the floor is defined
over `period_s`, and once effects become **stop lists** it has to be defined
over *transitions* - five colours at 0.1 s each is a 2 Hz cycle but a 10 Hz
change rate, which this check does not catch. That is a constraint on the
stop-list design (items **15**/**16**/**17**), not a defect in this one.

Suite: `test_flash_floor.py` - the pure floor, the setting's two failure
modes, the metronome's guarantee restated over an arbitrary floor, the bench,
and the mirrored-table drift guard.

The original scope follows.

---

**Current state.** `LED_FIELDS` in [schema.js](aibutton/web/static/schema.js)
has `{ key: 'period_s', kind: 'number', min: 0.1, max: 600, step: 0.1 }`, a
plain `<input type=number>`. `widgets.js`'s `WIDGETS` table has no `range`/
slider kind at all - `createField` falls back to `WIDGETS.text` for any
unknown `kind`, so this needs a new widget, not a tweak. Validation lives in
two more places: `config.py`'s `_parse_effect` only checks `period > 0` (no
upper bound on flash rate), and `device.py`'s `palette_payload` floors the
wire value at `max(1, ...)` centiseconds - i.e. 0.01 s - purely so the byte
math doesn't divide by zero, not for safety.

**What to build.** A `range` widget in `widgets.js` (slider + live numeric
readout, same `{ el, validate }` contract as every other widget), with
`LED_FIELDS`' `period_s` switched to `kind: 'range'`. Enforce the floor in
*all three* places that currently allow anything above zero: the slider's
`min`, `config.py`'s `_parse_effect`, and reject-not-just-clamp in
`device.py` (or at minimum raise the clamp floor from 0.01 s to the real
safety floor - it's a one-line change to the `max(1, ...)`).

**The number is now load-bearing, and still unconfirmed.**
`_METRONOME_MIN_PERIOD_S = 1/3` in [main.py](aibutton/main.py) is a real,
shipped, enforced floor — `metronome_flash()` groups beats so no tapped tempo
can strobe past it, and there are tests over the whole tempo range saying so.
So the guess below is already in the product; confirming it is now a change to
working code rather than a decision before writing any.

Two things that follow. **Whatever number is picked, there should be one
constant**, and `_METRONOME_MIN_PERIOD_S` is the obvious one to promote —
config.py and device.py should import it rather than each holding a copy.
And **the stop-list work (item 3's stronger version) multiplies the ways to
strobe**: a sequence of five colours at 0.1 s each is a 2 Hz cycle but a 10 Hz
*change* rate, which the current per-effect check would not catch at all. The
floor needs to be defined over transitions, not over `period_s`.

**Confirm the number.** The request was "no lower than 4Hz
cycles, to prevent seizures" - taken literally that's a period floor of
`0.25 s` (1/4 Hz), i.e. flashing is allowed *up to* 4 times/second. Standard
photosensitive-epilepsy guidance (WCAG 2.3.1) generally caps general-purpose
flashing at **3** times/second or fewer, which would be a floor of `~0.33 s`
instead. Implement with the floor as one named constant
(e.g. `MIN_PERIOD_S` next to `LED_FIELDS`, mirrored in `config.py`) so
picking the exact number is a one-line change either way, but get the actual
number confirmed rather than shipping either guess silently. This only
matters for styles that actually flash (`flash`, `alternate`, `fade`) - a
slow `breathe` at 0.25 s doesn't strobe the same way; worth deciding whether
the floor applies to breathe/rainbow too or only the harder on/off styles.

### 5. Make the floor mode permanent, rename it, and route by default into takeovers

Two things tangled together - do the resolution-semantics half first, it's
the one with test coverage riding on it.

**a) The floor mode can't currently be protected.** This is the old "Default
Mode Logic" item, still true: nothing in [rules.py](aibutton/rules.py) or
`config.py` prevents deleting or rescoping the one ambient mode a fresh
config ships with (`_default_modes()` in `config.py`), which means a button
can be configured into a state where *no* ambient mode ever matches (already
visible in the live dashboard as "no mode matches short_press right now").
Fix: something has to guarantee exactly one ambient mode is permanent -
`Always` activation, can't be deleted, can't have its activation changed
away from `Always`. Whether that's a `protected: true`/role flag on the
`Mode` dataclass or a structural rule ("the last ambient mode in the list is
always treated as the floor") is a real design decision - `rules.py`'s
`resolve()` docstring already talks about "explicit priority instead of
relying on list order alone," which is the same underlying problem. In the
UI, `ModeEditor`'s delete button (`_header()` in `modeEditor.js`) and the
name/template fields need to refuse to remove or repurpose whichever mode is
protected.

**b) Rename "Default" and change its default bindings.** Currently
`_default_modes()` ships one mode named `"Default"` with
`short_press → Log(button_press)`, `long_press → TimerToggle(focus)`,
`double_tap → Log(note)`. **The name is decided: `"Home"`** — confirmed, and
chosen over `"Mode Selection"` (a UI label, not a mode name) because it is the
place you return to, which is exactly what item 0a's launcher will want to
call it. Change its default bindings to
`short_press → Log`, `long_press → Enter "Pomodoro"`,
`double_tap → Enter "Stopwatch"`. That last part means `_default_modes()`
can no longer return a single mode - it needs to also seed default Pomodoro
and Stopwatch modes (`activation: manual`) for those `enter_mode` targets to
resolve against, which changes what a from-scratch `config.json` looks like.
Depends on (a): renaming/re-purposing only makes sense once this mode can't
be deleted out from under the defaults it's supposed to route to.

### 6. Make the Press/Clock side-panel sections collapsible ✔ shipped

Shipped as one fold of the *whole* pane rather than per-block disclosures
([sidepane.js](aibutton/web/static/sidepane.js)), toggled from the header
beside Tips. The three blocks are one thing — inspection surface — and
someone driving a real button wants all of it gone, not two thirds of it.
Expanded is the default; the choice is remembered.

Two things left behind for the next toggle rather than this one:
[prefs.js](aibutton/web/static/prefs.js) now holds the throw-guarded
localStorage helpers (storage *raises* in private browsing and off
`file://`), and `.header-tools` is the cluster Tinker mode joins.

### 7. Build at least 10 modes total

**Item 0a first, or most of these are unreachable** — with `triple_tap` and
`tap_5` now bindable the ceiling is four launchable apps rather than two, which
buys room but does not solve it: a launcher is still what turns "as many apps
as it will fit" into a real sentence. Scheduled modes (alarm, reminder) are the
exception and always were — a clock starts them, not a gesture.

**Three are done** - Tap metronome, Countdown and Reminder (item 11), which
leaves seven. The countdown
was on the candidate list at the bottom of this item and is now a real
template, which leaves eight. The
Morse code logger that was the other specified mode is on hold in favor of a
bigger idea - see "Recorded/translated communication mode" in the parking
lot below. Build it as originally scoped (short press = dot, long press =
dash, a timing gap commits a letter) only if the bigger version turns out to
be more than you want right now.

**Before inventing the other nine, sort ideas into two very different
costs:**
- *Cheap*: a new **preset** of an existing template
  (`BUILTIN_MODES` in `schema.js`) - zero Python changes. E.g. a mood
  check-in (`actions` template, three gestures log three different mood
  events), a dice/random picker, a countdown timer built from `alarm`'s
  shape with `manual` activation instead of `schedule`.
- *Expensive*: a genuinely new template - a new `*Behavior` dataclass in
  `config.py`, a `run_*` loop in `main.py`, a `schema.js` `TEMPLATES` entry.
  It used to also usually mean a new `LEDState` mirrored four ways; it does
  not any more. Push a look with `set_led(state, effect)` and borrow whichever
  existing state best describes what the button is *doing*. Allocating `0x0C`
  now needs an argument for why the whole system should have a name for it.

**Known hardware constraint, and it moved:** the LED still renders one
animation at a time, entirely on-device (`firmware/led.py`), but the host can
now push *any* one of them at any moment without it being a named state -
`set_led(state, effect)`, as often as it likes. So a mode can drive a
sequence of looks by pushing them one after another, which is what a
Simon-Says memory game needs and could not do before.

What is still true: the *shape* of an animation is one of the six styles, so
"flash this exact arbitrary waveform" is not expressible, and a sequence
driven from the host needs the host awake and costs a radio write per step.
A stop list (the colour-engine work above) is what makes a sequence one push
instead of many.

**Other candidates to pick from** (adjust freely, this is a starting list,
not a spec): reaction-timer (random-delay flash, logs response time),
interval/HIIT timer (Pomodoro's shape, shorter default blocks, a round
counter), a scheduled counter-nudge (counts something, `ALERT`-flashes if
it hasn't been bumped in N hours), a countdown timer (single fixed
countdown to zero, alarm-shaped but manually started), per-gesture counter
increments (+1 / +10 / +20 configurable - this was on the old list as its
own item; folding it in here since it's a `CounterBehavior` enhancement, not
a new template). A standalone "just play a sound" action (`ACTIONS` in
`schema.js`) is also currently missing even though `device.py.play_sound`
already exists - cheap, not a mode by itself, but useful for several of the
above.

### 8. Host the web UI on the user's server (docker / nginx / SSL)

**Do not start building before the topology is picked - it changes the shape
of the whole task.** BLE has short range and this app allows exactly one
running instance (`CLAUDE.md`'s single-instance rule; `DESIGN-ESP32.md`'s
"host must be awake" constraint). Three shapes, and the research below rules
one of them in that was not previously on the list:

**(a) Relay.** A local process keeps BLE and the event database and opens an
*outbound* WebSocket to the server, which hosts the dashboard. Works in any
browser including iOS. The server never touches Bluetooth, so the whole
`--net=host` / BT-passthrough question disappears. This is the old option (b),
and it is still the right answer for an always-on dashboard.

**(b) Web Bluetooth — the browser holds the button.** Genuinely available, and
it was not considered before. Chrome/Edge on desktop, Chrome on Android.
Requires HTTPS (already planned) and a user click to open the browser's own
device chooser — no silent auto-connect. Notifications work, so gestures
arrive fine, and the custom 128-bit UUIDs in [device.py](aibutton/device.py)
are exactly what it wants. Three consequences:

- The topology is `ESP32 ←BLE→ browser ←HTTPS→ server`. The server holds no
  radio, so there is no Docker Bluetooth story at all.
- The browser and the local service become **mutually exclusive** — the ESP32
  takes one central, so this is the single-instance rule stretched across two
  machines, not a second connection.
- **It fails the latency budget if the server does the thinking.** Press →
  browser → server → decision → browser → light is 100–500 ms against
  ARCHITECTURE.md's non-negotiable ≤50 ms. So a server-side brain only becomes
  viable *after* the runtime moves onto the device (Phase C), at which point it
  is nearly free.

**No iOS, ever, and that closed a different question.** Safari does not
implement Web Bluetooth and every other iOS browser is WebKit underneath, so
there is no workaround. Firefox declined on desktop too. That is why
ARCHITECTURE.md's "native or PWA?" is now answered — see the resolved bullet
there.

**The cheap first move is (b) applied to the editor, not the dashboard.**
[build_editor.py](tools/build_editor.py) already swaps `ConfigApi` for
`FileApi`; a third `BleApi` gives a page that configures the button directly
with no service and no server, and doubles as the phone app's authoring
prototype. Chrome/Android-only is a fair ask for a tinkerer's tool in a way it
is not for the everyday surface.

**Blocking prerequisite for any of this, and it is on no other list:** the web
UI has **no authentication**. [config.py](aibutton/config.py) says so in a
comment next to `web_host` ("LAN-facing; the web UI has no auth"). Hosting it
publicly exposes the config editor and the whole event log. Auth comes before
a Dockerfile, not after.

**Once that's settled**, the concrete work: containerize
(`requirements.txt`/`requirements-dev.txt` already list the deps - fastapi,
uvicorn, bleak, httpx), confirm whether the target server already has nginx
+ certbot/SSL running for other projects or whether that also needs setting
up (the user believes it does but hasn't confirmed), add a
docker-compose service, and a reverse-proxy vhost. If BLE needs to reach
into the container, that's `--net=host` or explicit Bluetooth device
passthrough, not a normal bridge network - confirm docker's actual
Bluetooth-passthrough story on whatever host OS is in play before assuming
it's straightforward.

### 9. Make Tips content more concise - ASCII/shorthand, no emoji

Scope: the `[data-help]` content gated by the Tips toggle
([help.js](aibutton/web/static/help.js)) - the primer
(`_renderPrimer()` in `menu.js`), the two group blurbs (`MODE_GROUPS` in
`schema.js`), and every field's `hint` text (`schema.js`, rendered by
`widgets.js`). Tighten toward fragments over sentences, use `->`/`:`/`-`
instead of prose connectors. None of the current Tips copy uses emoji
already (the `⚠`/`ⓘ`/`●` in the UI are text symbols, not emoji glyphs) so
this is really "shorter," not "de-emoji'd" - the actual emoji in the app
(🔵/⚪ in the header's connected/offline indicator,
`⚠️` in some `main.py` status strings) are outside Tips scope; flag to the
user whether those should go too, don't remove them unasked.

### 10. Checkpoint - review and re-triage

Do this after finishing a batch of the above (all of 0a-9 is a reasonable
point), before starting 11/12: re-read this file against what actually
shipped, move finished items to **Done** below, fold in anything discovered
along the way (item 2 in particular is likely to produce new items), and
confirm 11/12 are still wanted as scoped before spending time on them - they
're both bigger and vaguer than 1-9.

Then check the batch against [ROADMAP.md](ROADMAP.md)'s Stage 2 exit gates -
ten apps verified on hardware, a launcher, a naive-user run, a 24-hour soak,
the single-instance guard, verified power-cycle recovery, protocol v1 frozen -
and decide whether Stage 3 starts or Stage 2 has more in it.

### 11. Split Alarm into "Alarm" (clock) and a new "Reminders" mode ✔ shipped

`ReminderBehavior` + `run_reminder` + a `reminders` template descriptor. The
alarm is untouched, which was the first instruction and is asserted by a test.

The decisions, because they are the item:

- **Any press clears it.** Nominating a gesture would make a reminder as
  demanding as an alarm, which is the thing it exists not to be — and it makes
  "escapable with a press" trivially true rather than something to check.
- **No snooze.** A reminder you can postpone is an alarm with extra steps. If
  you want it again, schedule it again.
- **It gives up.** `timeout_minutes` (default 5, 0 = forever) is the other half
  of being ignorable — a reminder nobody was in the room for should not still
  be flashing at midnight. **A timeout is not a clear**: nothing is logged,
  because nobody saw it.
- **It reuses `ALERT` and does not look like one.** No new `LEDState`. With no
  named look it breathes rather than flashes — pushed as an ephemeral effect,
  so it is visibly not an alarm without a wire code, a mirror or a reflash. A
  named look still wins, as everywhere else.
- **The scheduler was generalised, not duplicated.** What makes a mode
  scheduled is its *activation*, not its behaviour, so `due_alarm` matches
  `ScheduleActivation` against a tuple of allowed behaviours and the parser
  keeps deciding which templates may carry one. A parallel `due_reminder`
  would have been the same twenty lines with one `isinstance` swapped, and the
  third scheduled template would have made it three copies. Config order
  decides a tie at the same minute, which puts an alarm above a reminder if it
  is listed first — the right way round, and now written down.

Suite: `test_reminders.py` — the flash, the clear, the timeout that logs
nothing, per-key fallback, the round-trip, and a guard that the alarm template
still behaves exactly as it did.

The original scope follows.

---

Keep `alarm`'s current behaviour (`AlarmBehavior`/`ring_alarm` in
`main.py`: looping tone + `ALERT` LED until dismissed, optional snooze) as
the "real alarm clock" case - don't touch it. Add a new template,
`reminders`: fires on a schedule like `alarm` does
(`scheduler.py`'s `due_alarm` currently matches
`AlarmBehavior + ScheduleActivation` specifically and will need
generalizing, or a parallel `due_reminder`, to also match the new behaviour),
but the feedback is a flash rather than a ring - a distinct look rather than
reusing `ALERT`, since `ALERT` already means "alarm is ringing" and a
reminder shouldn't look identical to one. **0b has landed, so that look is an
ephemeral effect and costs nothing** - push it with `set_led(ALERT, effect)`
and it looks like a reminder rather than an alarm without a wire code, a
mirror, or a reflash. No looping sound (a single chime, or none).
Clearing it (any press, or a specific gesture - decide) logs a
"cleared today" event and stops the flash, mirroring how
`unless_logged_today` already lets an *ambient* mode stand down once
something is logged today, except this is a *scheduled/takeover* mode doing
the equivalent. New `ReminderBehavior` in `config.py`, a `run_reminder` loop
in `main.py` (mirrors `ring_alarm`, much simpler - no snooze branch), and a
`TEMPLATES` entry in `schema.js` (`nature: 'takeover'`,
`allowedActivations: ['schedule']`, `startedBy: 'schedule'`).

### 12. Look into analytics/tracking - scope first, this is vague as given

**One half is now decided: it is all local.** "No invasive distractions. No
ads." is a product promise, and it is written into
[ROADMAP.md](ROADMAP.md)'s principles as *nothing is extracted from the user*.
So whatever this turns out to mean, the data stays on the user's machine,
nothing phones home, and there is no analytics vendor. That also rules out the
easy Stage-5 business model, which is better known now than later.

**Also easier than it was:** the `value` column (item 1) means the log can
carry numbers, not just occurrences - which was the actual blocker under any
reading of (a) below.

What is still open is which *question* this answers. "improve performance"
needs to be pinned down -
it could mean (a) *habit* analytics for the user (mode usage, streaks,
time-of-day patterns - a real dashboard over `EventStore`), (b) *device*
telemetry (BLE reconnect frequency, gesture-to-feedback latency, dropped
presses while busy - already flagged as a known rough edge below), or
(c) *hosting* metrics once item 8 exists (server-side, nginx/docker level).
Ask which. Whichever it is, it depends on item 1: today's event log doesn't
carry enough detail (no mode/source column, no takeover-session records) to
build much analysis on top of, so item 1's scope decision should account for
whatever this item ends up needing.

### 13. Scenes - swappable, offline-editable button configs ✔ shipped

**Status: all four stages landed** ([scenes.py](aibutton/scenes.py),
[config.py](aibutton/config.py), [webui.py](aibutton/webui.py),
[scenes.js](aibutton/web/static/scenes.js),
[supervisor.py](aibutton/control/supervisor.py),
[tray.py](aibutton/control/tray.py),
[build_editor.py](tools/build_editor.py)). Kept here rather than moved to
**Done** because the reasoning below is why the code is shaped the way it is,
and the next person to touch config loading needs it.

**One thing is untested against reality:** the tray's `Scene >` submenu is
covered by unit tests on `Supervisor.scene_state` / `switch_scene` and the
pystray menu is built the same way the status slots are, but nobody has
clicked it - `tray.py` needs a screen, so the suite deliberately does not
import it. Click it once before trusting it.

**The want:** save a whole button setup, keep several of them, swap between
them in one click. A/B two arrangements of the same modes; keep a "work" set
and a "kitchen" set; hand someone a file. And **edit them with nothing
running** - no service, no button, no browser talking to localhost.

**The shape.** `config.json` stays the entry point and gains one key. The
active scene file is shallow-merged over the base *raw dict* before
`parse_config` ever sees it:

```jsonc
// config.json
{ "database_path": "data/events.db", "web_port": 8080,
  "scenes": { "dir": "scenes", "active": "focus" },
  "modes": [ /* the fallback when no scene resolves */ ] }

// scenes/focus.json - every key it defines wins
{ "name": "Focus", "modes": [ /* ... */ ], "led_palette": { /* ... */ } }
```

Four reasons for that exact shape, each of which rules out an alternative:

- **The merge happens on raw dicts inside `load_config`, not inside
  `parse_config`.** `parse_config` stays pure and untouched, so every
  existing per-key fallback, every warning string, and
  `POST /api/config/validate` all apply to scene files with **no new
  validation code**.
- **It lives in `load_config`, not `ConfigManager`**, so every caller gets
  it - including `control/supervisor.py`'s `status_url()`, which loads the
  config to find the web port. Put the merge a layer up and the tray
  silently reads the wrong port for the active scene.
- **The editor writes the scene file; only the one-line `scenes.active`
  pointer is written back to `config.json`.** No copy of the config to keep
  in sync, so no way for a hand-edit to be silently clobbered by the next
  switch.
- **No `scenes` key means today's behaviour, byte for byte.** `--config` is
  unchanged. A `config.json` with no scenes dir is still just a config.

A scene *may* be a whole config, but the merge is shallow, so it doesn't have
to be: a scene that defines only `modes` inherits the base's lights, which is
what you want when A/B-testing behaviour and holding appearance constant.
**A scene's own `scenes` key is dropped during the merge** - a scene
repointing the active scene is a loop and a footgun.

**The honest cost of whole-config scenes.** `web_host`, `web_port`,
`database_path` and `ble_device_name` are read **once at startup**
(`config.py`'s docstring already says so for the web bind address; the store,
the lock and the BLE name are the same). A scene that changes them reloads
cleanly and then does nothing, which is the worst kind of bug. So the API
tells the truth instead: the activate/save endpoints diff the newly-effective
values against a snapshot of the config the process actually started with and
return `needs_restart: ["web_port", ...]`; the UI shows it and the tray - which
already owns the process lifecycle - offers the restart.

Two related things worth knowing but **not** in scope here: the
single-instance lock is derived from `database_path` (`main.py`), so a scene
changing it changes which lock is held; and the event log has no column for
*which scene produced a row*, which is the real blocker for A/B-testing on
data rather than on feel. Keep `database_path` constant across scenes; the
event column belongs with item 1.

**Stages, all landed.** Each was useful on its own and the offline
requirement is satisfied by the first.

1. **Files and switching, no UI.** New
   [scenes.py](aibutton/scenes.py): pure `merge()` / `slugify()` /
   `scene_id()`, plus the I/O edge (`list_scenes`, `read_scene`,
   `write_scene` atomically via tmp + `os.replace`, `set_active`).
   [config.py](aibutton/config.py): `"scenes"` added to the `known` key set
   (or it warns as unknown), a `_parse_scenes` following `_parse_effect`'s
   per-key-fallback pattern, `SceneSettings` on `AppConfig`, emitted by
   `as_dict` so the round-trip holds, and `load_config` doing the resolve +
   merge. A missing dir, a missing file or broken JSON logs and runs the base
   config - **a bad scene never crashes the service**, same invariant as a bad
   config. Then a CLI: `python -m aibutton.scenes list | check <file> |
   activate <id>`, where `check` runs the *real* parser and prints the real
   warnings. That CLI is the offline validation story, and it is the reason
   not to write a second parser in JavaScript.
2. **The web UI picker.** `GET /api/scenes`, `POST /api/scenes`
   (new / duplicate / save-as), `POST /api/scenes/{id}/activate`,
   `PUT /api/scenes/{id}`, `DELETE /api/scenes/{id}` (refuses the active
   one). `PUT /api/config` gains one documented branch: it writes the active
   scene file when there is one. A new `web/static/scenes.js` owns the scene
   bar so `menu.js` doesn't pick up a second responsibility, and the new
   calls go on `api.js` - it stays the only module that touches `fetch`.
   Export/Import buttons here are the bridge to and from offline files.
3. **The tray submenu.** A `Scene >` radio list in
   [tray.py](aibutton/control/tray.py), with the list and the activate call
   in `supervisor.py`/`status.py` per that package's own contract (decisions
   out of the Tk layer). It uses the API when the service is running and the
   *files* when it isn't, so switching works before the button is even up.
4. **The standalone editor.** `tools/build_editor.py` ->
   `dist/button-editor.html`: `index.html` with the `static/*.js` modules
   inlined - **required**, because browsers block ES modules over `file://` -
   and `ConfigApi` swapped for a `FileApi` using the File System Access API
   with a download fallback. One limitation to state plainly rather than
   paper over: `parse_config` is Python and cannot run in that page, so the
   standalone editor gets the existing per-widget `validate()` and nothing
   more. Full validation is stage 1's CLI, or importing the scene.

**Not the launcher.** A scene picker is a PC-side control and does not
discharge item 0a's gate - reaching apps *from the button* is still that
item's job. Scenes are also orthogonal to the Stage-3 app runtime: the merge
is on raw dicts, so it survives `modes` becoming app manifests unchanged.

**Verified:** scene files in `scenes/` hand-edited and picked up on reload;
switching from the web UI applies modes *and* colours live (the palette push
the main loop already does covers it) with no restart; a scene changing
`web_port`/`ble_device_name` reports `needs_restart` naming both;
`aibutton.scenes check` reports the real parser's warnings with the service
stopped; the built `dist/button-editor.html` opens with no network at all and
edits a scene. Suite: `test_scenes.py`, `test_webui_scenes.py`,
`test_build_editor.py`, plus the scene half of `test_control.py`.

**Left open, deliberately:**

- The tray submenu is unclicked (above).
- A scene saved *through the editor* carries the whole effective config,
  including `database_path`, because that is what the page had on screen. So
  UI-made scenes lose the "inherit what I don't mention" property that
  hand-written ones keep. Fine as specified, worth revisiting if scenes ever
  start disagreeing about where the database is.
- The event log still has no `scene` column, so you cannot yet answer "which
  scene produced this row" - the thing an A/B test eventually wants. Belongs
  with item 1, not here.

### 14. Tinker mode - one flag that decides how much surface you see

The base experience should be obvious to someone who has never seen it; the
fringe options should still exist. That is [ROADMAP.md](ROADMAP.md)'s first
principle ("neither one sees the other's surface"), and today nothing
implements it - every field a template has is rendered to everybody.

**Build it exactly like Tips.** Add `tier: 'basic' | 'tinker'` to field
descriptors in [schema.js](aibutton/web/static/schema.js), default `basic`
when absent, and have `widgets.js` mark the node so a single toggle hides the
lot. Data on descriptors, one renderer change, no branches - the Open/Closed
rule the schema already follows. The toggle joins `.header-tools` next to
Tips, and reads its state through
[prefs.js](aibutton/web/static/prefs.js) like the side pane does.

**They are two axes, not one, and that is worth keeping straight:** Tips is
*explain / don't explain*; Tinker is *show / hide surface*. A basic user with
Tips on should get a short, fully-explained form. Do not collapse them into a
single "beginner mode".

**The judgement is which fields are which**, and it is the whole value of the
item - a Tinker flag on everything is the same as no flag. First pass worth
arguing with: metronome's `tap_history`/`reset_gap_s`/`max_bpm` are tinker and
`start_bpm` is basic; Pomodoro's `extend_minutes` and per-gesture command
bindings are tinker; every `log_as`/event name is basic (it is what you came
for); the whole Device settings group is tinker except `sounds_enabled`.

**Do this after item 3's look work, not before.** Colour is the thing that
should be at the top of a basic mode form, so deciding what "basic" contains
before the look editor exists means deciding it twice.

### 15. Counting without entering an app — and what "background" actually means

**Half of this already works, and that is the first thing to know.** Binding a
gesture to count something specific does *not* need the Counter takeover and
never did: `LogAction` is an ambient action, and
[store.py](aibutton/store.py)'s `count_today` / `current_streak` group by the
event name, so this counts coffees today with no code at all —

```json
{ "name": "Everyday", "template": "actions", "activation": {"type": "always"},
  "double_tap": {"action": "log", "event": "coffee"} }
```

**So what is the Counter takeover actually for?** Three things, and only the
third is hard: it zeroes a session tally, it owns `COUNTING` on the LED, and
it *tells you the number*. An ambient `log` gives you a `SUCCESS` flash — you
learn that it counted, not what it counted to. **The gap is the readout, which
makes this item and item 17 the same feature.** Do 17's scheme first, then
this is a new ambient action (`log` with a `readout` flag, or a `count_readout`
action) and a preset, not a new template.

**"Can alarm / Pomodoro run in the background?" splits three ways**, and the
answers are different — worth separating before anyone designs for it:

- **Background *timekeeping*** — the clock keeps running. Alarms already do
  this: `due_alarm` fires from the ambient loop in [main.py](aibutton/main.py)
  and preempts whatever is running. Nothing to build.
- **Background *gesture handling*** — the button still answers other gestures
  while a timer runs. **This is the real change.** A takeover awaits
  `device.events` directly and so monopolises every press; that is the same
  sentence CLAUDE.md flags as the one place the pure-core rule is broken.
- **Background *display*** — two running things wanting one LED. This cannot
  be solved by sharing; it needs a stated priority rule (or the readout from
  17, so a backgrounded timer is *asked* rather than *watched*).

**This is a genuinely new architectural question — and it now has an answer.**

**Decided: one foreground app, and shared state lives in the event log rather
than in the app.** Not "N concurrent apps with a priority rule". The case that
prompted it — count something from Home, then enter the Counter and *continue*
the same tally — needs no concurrency at all, because `count_today` already
groups by event name. An ambient `log` of `coffee` and a Counter whose event is
`coffee` are already the same rows.

**What actually has to change is one line of state.** The Counter takeover
holds its session number as a local integer starting at zero, which is the only
reason the two disagree about what "the count" is. Read it from the store
instead and they agree by construction: counting from Home and counting in the
Counter become the same count, and "count something else in counter mode" is
just a different event name. No priority rule, no second run loop, no
display-arbitration problem.

That is also why this stays cheap under the Stage-3 move: the log is the shared
surface, and it is already the thing that survives a restart, a reflash and a
change of host. **Write this paragraph into ARCHITECTURE.md** — the decision
matters more than the code change, because the next person to want two things
at once needs to find it.

The two questions it does *not* answer, and neither is urgent: a genuinely
backgrounded timer still monopolises gestures (a takeover awaits
`device.events` directly), and two things wanting the LED still needs a stated
priority — or the readout from 17, so a backgrounded timer is *asked* rather
than watched.

**Definition of done.** Ambient counting with a readout gesture, shipped as
data (an action plus a preset, no new template); and a paragraph in
ARCHITECTURE.md that answers "can two apps run at once" one way or the other,
so the next person does not have to guess.


### 16. Games — timing, rhythm, and a hot/cold guesser

Simon-Says-style timing games; a hot/cold detector that cycles a rainbow,
stops on a press, and flashes how close you were. Creative latitude wanted.

**Read [ARCHITECTURE.md](ARCHITECTURE.md)'s "What this deliberately cannot
express" before designing any of it** — it names Simon Says specifically, as
the worked example of what a bounded state machine *can't* do (it has to emit
a generated sequence). It also gives the three sanctioned answers, in order:
push the work to the phone, extend the **effect set** (a system decision, not
an app's), or ship it as a native app compiled into the firmware. A scripting
language is explicitly refused. So a game is not a reason to reopen that; it
is a reason to grow the effect set, which is the same work as item 4 and 17.

**The latency budget decides which games are possible now.** ARCHITECTURE's
table puts "press → the app decides what it means" at **≤ 50 ms, on device, no
exceptions**. A host-side game over BLE cannot meet that. Therefore:

- **Forgiving games are buildable today** — hot/cold, guessing, anything with
  a window of ±150 ms or looser.
- **Tight rhythm judgement is Stage 3 work**, on-device, and pretending
  otherwise will produce a game that feels broken and gets blamed on the
  radio. Do not start there.

**A non-obvious constraint that falls straight out of the existing design, and
will bite whoever writes the first game:** a single press does not fire until
the multi-tap window has elapsed, and how long that is comes from `max_taps`,
which the host derives from *what the config binds*. A mode that binds only
short press gets an instant press; the same mode with a double tap bound eats
0.4 s before every single press. **So a timing game must bind exactly one
gesture**, and that is a config fact, not something to fix in firmware.

**Hot/cold has one real problem worth knowing before you start it:** the host
does not know the device's rainbow phase, because `_rainbow` renders
on-device. Two ways out — drive the sweep from the host (fights "feedback is
fire-and-forget", and burns radio), or compute the phase from send-time plus
period, which works precisely because the press latency is bounded and known
once the mode binds one gesture. Prefer the second.

**The "how close were you" flash is already built.** `ramp.color_at` in
[ramp.py](aibutton/ramp.py) maps progress 0→1 onto a colour ramp, which is
exactly "cold → warm → hot". That module was written to have four consumers;
this is one of them. Do not write a second distance-to-colour function.

**Definition of done.** One shipped game (hot/cold is the cheap one), written
as a step function over `(state, event, now)` rather than as a loop that
awaits the device — per CLAUDE.md, that is the difference between porting to
the Stage-3 runtime unchanged and being rewritten.


### 17. A number you can read off one light

**The question was whether a universal colour-to-digit code exists. It does:**
the resistor colour code (IEC 60062), which is genuinely standard and genuinely
known — black 0, brown 1, **red 2**, orange 3, yellow 4, green 5, blue 6,
violet 7, grey 8, white 9. That is the "red = *n* by a universal metric" thing,
though red is 2 rather than 1.

**And it is the wrong tool here.** Black is 0, which on an LED is *off* and
therefore indistinguishable from idle; brown and grey are "dim orange" and
"dim white" on a WS2812, which is to say they are not colours a diffused pixel
can deliver; violet against blue is hard on a single dot. That is ten-way hue
discrimination on one diffused LED — and this build's ring has a *measured*
colour cast (item **0c**) that eats exactly those distinctions. A number system
nobody can read under a warm lampshade is not a number system.

**One LED has three channels, and they are not equally good at numbers:**

| Channel | Good for | Bad for |
|---|---|---|
| Count / rhythm | **exact integers**, no legend, no learning | anything large |
| Hue | **proportion**, magnitude, hot/cold | exact values |
| Brightness | emphasis, grouping | anything on its own |

So: **exact counts are blinks, proportions are hue.** Do not make hue carry
digits.

**The proposal, which is the tally idea with the grouping made explicit** —
tens as slow pulses in one colour, units as quick pulses in another. 27 is two
slow, then seven quick. It covers 0–99 in at most eleven blinks, reads like an
abacus, needs no legend, and has an engineering property worth more than
elegance here: **it does not depend on telling colours apart at all**, so it
survives the ring's cast, a warm room, and a colourblind user. Hue then stays
free to mean *which thing* is being counted.

**For proportion, use what exists.** `ramp.color_at` already maps 0→1 onto a
ramp; a Pomodoro's progress, a countdown, a hold level and item 16's hot/cold
are the same primitive. Nothing new to design.

**The protocol note, and the reason to do item 4 first: a readout *is* a stop
list.** The colour-engine section above already wants `{colour, hold, fade}`
stops to replace `{style, 2 colours, period}`, because that one structure
subsumes all six styles and gives gradients and sequencing for free. "Two slow
amber, seven quick white" is precisely a stop list. So building a bespoke
`blink_n_times` effect would spend a wire feature on a special case of one
already planned. **Build the stop list; get the readout for free.**

**Definition of done.** The scheme written down as data (in `schema.js` and
`config.py`, not as branches); a readout reachable from an ambient counter
(item 15); and one person who has *not* been told the rule reading a
two-digit number off it correctly. That last one is the actual test — if it
needs explaining, it failed.


### 18. Move project management into Notion ⏸ parked — not yet

**Deferred deliberately, not dropped.** Nothing is created in Notion and
nothing should be until the split below is chosen. The analysis is kept
because the decision is the expensive part and it is already made once here.

**The risk is not the migration, it is ending up with two sources of truth.**
This file is 1000+ lines and most of that is *reasoning*: why an item exists,
which files it touches, what done means. [CLAUDE.md](CLAUDE.md) and the "How
to work this list" section both lean on each item standing alone well enough
to be picked up cold in a fresh session. That property lives in prose, and
Notion is not better at prose.

What Notion *is* better at: status, priority, what is in flight, dates,
sequencing, and looking at the whole thing without scrolling a wall of text.
Which is exactly what this file is worst at.

**So decide the split before creating anything:**

- **A — Notion tracks state, TODO.md keeps reasoning.** One card per item
  (status / priority / gated-by / body-of-work), each linking to its heading
  here. Notion answers "what now", the file answers "what and why".
- **B — migrate wholesale**, CLAUDE.md repoints at Notion, this file becomes
  an archive.

**Recommend A**, on the grounds that the fresh-session property is load-bearing
for how this project is actually worked and B puts it behind a network call and
an auth prompt. The five bodies of work in the table above are the natural
Notion views; the numbered items are the cards.

**Cheap to execute** — the Notion MCP is available, so the mechanical part is
a script over the headings, not a copy-paste job. Do not create the database
until the split is chosen, because the field set follows from it.

**Definition of done.** The chosen split written into
[CLAUDE.md](CLAUDE.md) — one sentence saying which document a fresh session
should read for what — and the items loaded. Without that sentence this is
just a second backlog.


### 19. The light as a language — sequencer, one-offs, and where colour is edited

Three of the four pieces below are unbuilt; the subdivision ladder is done and
is written up here because it establishes the vocabulary the rest reuses.

**There are three structures, not one, and conflating them is the trap.**

| | Driven by | Shape | Serves |
|---|---|---|---|
| **Ramp** ✔ [ramp.py](aibutton/ramp.py) | progress 0→1 | colours pinned at fractions | countdown, Pomodoro block, hold level, hot/cold |
| **Stop list** — unbuilt | the clock | ordered `{colour, hold, fade}` | Fade / Flash / Evolve, gradients, sequencing |
| **Subdivision ladder** ✔ [ladder.py](aibutton/ladder.py) | a *counter* | `{interval → colour}`, largest match wins | a time reference on any timer |

A ramp answers "how far through are you", a ladder answers "what time is it",
a stop list answers "what happens next". None can express the others —
modular arithmetic is not interpolation — which is why they are three modules
and not three modes of one.

#### a) The subdivision ladder ✔ shipped

The light as a clock: at any moment the colour is the one on the **largest
interval that divides the elapsed time**. Defaults are the spec as asked —
10 s white, 5 s yellow, even seconds light blue, odd dark blue, 0.5 s ticks,
every interval and colour editable.

What the "largest wins" rule buys, and the reason not to special-case it:
**parity needs no notion of parity.** A rung at 2 s catches the even seconds
and a rung at 1 s catches whatever is left, so "even and odd differ" falls out
of division rather than being a rule anyone wrote. Adding a 15 s rung needs no
code.

Four details worth keeping:

- **Whole milliseconds, not floats.** `2.0 % 0.5` can land on
  0.4999999999999998. A ladder that worked at 1 s and failed at 0.1 s would be
  the worst kind of intermittent, so everything divides in integer ms with a
  1 ms slop either side of a boundary.
- **Ticks are evaluated at their nominal time**, not at the wall time the loop
  woke up. A tick scheduled for 2.000 s that fires at 2.013 s must still be the
  two-second colour, or the marker silently never appears on a host that also
  talks to a radio.
- **The flash floor applies to the *cadence*, not to `period_s`.** This is the
  transitions hole item 4 flagged: a 0.1 s tick is a 10 Hz colour change however
  sedate the style, and `flash_safe` cannot see it because a `solid` never
  strobes by its own reckoning. `ladder_paint` floors the tick.
- **Opt-in, and it replaces the ramp.** Both decide *which colour*, so only one
  runs; the ladder wins because turning it on is an explicit "make this a
  clock". A plain stopwatch still blocks on the next press and costs no radio
  traffic at all — the tick only exists when a ladder does.

Shipped on **stopwatch** and **countdown** (countdown drives it from time
*remaining*, which is what a countdown is about). Suite: `test_ladder.py`
(the pure arithmetic), `test_ladder_modes.py` (the config surface and a
running timer).

**Left open:** the metronome, which wants it most and is the one place the
ladder's counter should be *beats* rather than seconds — that is a different
axis and deserves its own thought, not a copy of this wiring.

#### b) The sequencer — a stop list, and one-offs

The `{colour, hold, fade}` stop list the colour-engine section has wanted all
along: it subsumes all six current styles (solid = one stop; flash = colour +
black, stepped; fade = two stops, smoothed; breathe = colour → black) and then
gives gradients, sequencing and asymmetric duty for free. "Fade, Flash, Evolve"
are three presets over one structure, not three features.

**The new requirement, and it is a real addition to the effect model: not
everything loops.** "Do x sequence over y interval" needs a *play once* mode.
Today every style repeats until the next state change, and the 0.03 s
confirmation flash is a one-off only because it is a state display rather than
an effect.

That has a safety consequence worth stating before anything is built: **0.03 s
is 33 Hz and is fine precisely because it happens once.** So `flash_safe` needs
to know whether an effect repeats — the floor is over *repeating* transitions.
A one-off sequence and a looping one are different questions and the current
signature cannot tell them apart.

#### c) Reuse the ramp widget wherever a gradient makes sense

The `ramp` widget already exists and is only offered on the countdown. Pomodoro
blocks, hold levels and any "how far through" surface want the same control.
This is a descriptor change per template, not new code.

#### d) Move mode colour fully into the mode, and grow the picker

The Lights tab should hold **system states only** (IDLE / LISTENING / THINKING
/ SUCCESS / ERROR). Mode-owned states (ALERT / TIMING / COUNTING / WORKING /
RESTING / METRONOME) belong on each mode's own page.

**Decided:** the global palette entries for mode-owned states **stay in config
as the invisible fallback** — they are what a mode with no named look renders,
and `base_look` reads them. Only the *editor group* goes away. Removing the
entries themselves would leave a mode that names nothing with nothing to show.

The test bench is the right springboard for the per-mode picker: it already
pushes a look through the real parser and the real seam. What it needs to grow
is saved user styles — which is what the `looks` pool already is, so this is a
UI move rather than a new concept.

#### e) The metronome's period field in the Lights tab — confirmed dead

Verified, and nothing depends on it: `push_tempo` does
`replace(base, period_s=period)` on every tick, so the stored value is
overridden before it is ever rendered — including before the first tap, where
`start_bpm` drives it. Removing the field from the editor changes nothing at
runtime. It resolves for free when METRONOME moves to the mode page (d).

## Smaller, worth doing

- **Verify power-cycle recovery.** Phase 3's last unchecked criterion: pull
  the ESP32's USB mid-session and confirm the host reconnects on its own.
  Reconnect logic is tested against a fake bleak, not against real hardware.
- **Presses dropped while busy.** The loop runs one action at a time and
  discards presses during the 2 s SUCCESS display. Deliberate, but it makes
  fast repeated taps feel dead - worth revisiting if it grates in daily use.
  (Relevant to item 12b if "performance" turns out to mean device latency.)
- **Sound design** *(firmware)* - review "Smart Button Sound Design
  Research" (from Obsidian) and replace the placeholder tone tables carried
  over from the Pi build. A matching sound palette, pushed the same way the
  LED palette now is, is the obvious shape.
- **On/Off toggle** - "5 taps" as a global toggle. **The gesture half is
  shipped; the action is what's left.** `TriggerType.TAP_5` and the `GESTURES`
  entry landed as a pure data change with no reflash under them - which is the
  promise 0b·2 made, now demonstrated end to end against the *firmware's own*
  encoder (`test_device.py`). The host writes `max_taps=5` by itself the moment
  something binds it.

  Two decisions worth keeping. **Four taps is deliberately unnamed**: the
  firmware has named 4..9 since v1, but a count with no `TAP_TRIGGERS` member
  is dropped rather than fired, and dropping is the right behaviour for a
  stray extra tap on a triple. And binding five *does* cost every shorter tap
  its instant response - the `GESTURES` hint says so, because it is the one
  gesture whose cost is paid by the other gestures.

  **What is left is the action**: there is no "toggle the button off" action to
  bind it to. That is an `actions.py` + `ACTIONS` + `config.py` change, and it
  needs a decision first - does "off" mean the ambient layer stops matching, or
  the device goes dark, or both? Ambient-only is the cheap and honest one.

## Parking lot (deliberately later)

- Battery + deep sleep - the one thing that might justify a C++/NimBLE rework
- Offline buffering of presses while disconnected (needs a time sync)
- WiFi transport, which would remove the host-must-be-awake constraint (and
  would change the calculus on item 8)
- Phone app over the existing REST API
- A second control surface (an MCP server over the store and config was the
  original Phase 4). Dropped for now: the web UI and the `webhook` action
  cover what the button is actually for. Revisit if something concrete wants
  to read the event log or drive the button programmatically.
- **Recorded/translated communication mode.** Grew out of the Morse code
  logger idea (item 7): instead of one gesture = one symbol logged
  immediately, a takeover mode with three phases - *listen* (record a whole
  sequence of presses and the gaps between them, not react to each one),
  *translate* (decode the recording into text once something signals you're
  done - a distinct gesture, or a trailing silence), *read back* (surface the
  decoded text - no on-device display, so this means the LED blinking it out
  and/or a buzzer pattern and/or the web UI's status line). Needs spec'ing
  out before building, in particular: what encoding the listen phase decodes
  (Morse is the obvious default, not the only option), what commits a
  recording, and whether "read back" needs to be sighted/heard-only or can
  lean on the web UI. Prototype the decode logic host-side and pure, the way
  `rules.py`/`trigger.py` already are, before wiring it into a takeover loop -
  same caution as the original Morse idea, just for a richer payload.
  The stretch goal is real communication, not just a log entry: **button-to-
  button** (a real architecture change - today's model is one host owning
  one button, so two buttons talking to each other needs either each host
  relaying through a shared server or a host that can be a peer to another
  host, not a small addition) or **actual SMS** (much cheaper - once the
  listen phase has produced decoded text, sending it is just the existing
  `webhook` action pointed at a texting API's endpoint, no new plumbing).
  Scope the logging-only version first; button-to-button is parking-lot-
  worthy in its own right even after the mode itself exists.

## Done

- ~~**A light test bench, and the byte-order fault it caught**~~ - the Lights
  tab grew a **Test bench**: push any style/colour/period straight at the LED,
  saving nothing. It needed no new device method, because "show this look" is
  already what an ephemeral effect means - `POST /api/dev/led` makes the same
  call `run_metronome` does, so the four-method seam was used rather than
  widened. It writes nothing and marks nothing dirty; the next press repaints
  from the palette, which is what makes it safe to poke at with a real button
  attached. Validation goes through the config's own `_parse_effect`, so a
  colour the editor would reject on Save is rejected identically here and the
  caller is told what it actually got - one parser, no second opinion about
  what a look is.

  It immediately earned itself. `NEOPIXEL_ORDER` and `ONBOARD_NEOPIXEL_ORDER`
  were on the wrong LEDs, so *both* rendered red as green and green as red
  while blue, yellow and white looked perfect - those three being the fixed
  points of an R/G swap. Corrected and flashed; the onboard LED is now
  accurate. The ring's remaining warm cast is a different fault and is item
  **0c**.

  Worth keeping in mind for the next fault like it: the diagnosis came from
  pushing *known* colours and reading them back, not from staring at a
  rainbow. A rainbow is the worst test available for a mapping fault - every
  permutation of it is still a rainbow, so it only shows a direction reversal,
  and the camera's own white balance is happy to fake one of those.

- ~~**Protocol v1, finished: a look you can push and a gesture that carries a
  number**~~ - the second and last revision of the wire (see item 0b for the
  detail). Two capability bits, two characteristics, no `LEDState` spent, and
  `0x0B` is still the highest code.

  **Effects.** `LED_EFFECT` is a palette entry without the state byte: render
  it now, store nothing, end at the next `LED_STATE` write. The two run loops
  that used to rewrite the palette live no longer touch it, so neither needs a
  `finally` to put anything back - and the tests that pinned those overrides
  now assert on *what the light shows* rather than on which mechanism put it
  there, which is why they survived the change with one helper edited.

  **Gestures.** `[kind, param]` alongside the frozen three one-byte codes. The
  degradation goes both ways on purpose: the firmware emits the legacy form
  whenever one exists, so an old host never sees anything new, and
  `decode_gesture` reads both, so a new host still understands an un-reflashed
  button. `triple_tap` is the first gesture to arrive this way and takes the
  button to four bindable gestures.

  **The one judgement call**, and it is a product one rather than a protocol
  one: counting to N costs a double tap its instant response, because it has
  to outlive the 0.4 s window to prove it is not the start of a triple. So the
  host writes `max_taps`, derived from what the config binds rather than set
  by hand. At 2 the detector is the one that shipped before, line for line -
  the evidence being that every pre-existing detector test passes unedited,
  against both implementations, with nothing in the code special-casing two.
- ~~**Colour ramps, and a countdown to prove them**~~ -
  [ramp.py](aibutton/ramp.py) is the pure half: a list of stops, each a colour
  pinned at a fraction, and `color_at` blending between the two either side. No
  clock, no device, nothing that mentions seconds - which is what lets a
  Pomodoro block and a hold level reuse it later. It blends the same way
  [firmware/led.py](firmware/led.py)'s `_fade` does, with a test that fails if
  the two ever disagree.

  The `countdown` template is its first consumer: a fixed run to zero where the
  light's *colour* walks the ramp while style and period hold still, ending in
  the alarm. Verified end to end - red to blue over twelve seconds, the flash
  period unmoved at 0.5 s throughout, the palette handed back on exit, and one
  `log` row carrying the length it ran for.

  Two things it does *not* do, on purpose. It burns no wire code: it rewrites
  the TIMING palette entry live, the same reach-around `run_metronome` uses,
  which is safe only because one takeover mode runs at a time. And it needs the
  host awake. **D4**'s ephemeral effects are what fix both.

  The editor got a `ramp` widget - a gradient strip over a row per stop, colour
  and position side by side, sitting at the *top* of the countdown's form.
  Adding or removing re-spaces the ramp only when it was already evenly spaced,
  so a hand-tuned ramp is never silently flattened by a click.
- ~~**The metronome can go fast, and has settings**~~ - it had no config at
  all (the tempo is session state, so the dataclass was empty), and its
  ceiling was not a number anyone had chosen: `_METRONOME_MIN_PERIOD_S` is a
  photosensitivity floor that capped the *light* at 180 BPM. Tempo and flash
  rate are now separate limits - `max_bpm` bounds the tempo and is yours to
  raise, while `metronome_flash()` keeps the light legal by marking every Nth
  beat and saying so in the status line. 240 BPM is a real 240 BPM rather than
  a lie or a strobe. Plus `start_bpm`, `tap_history`, `reset_gap_s`,
  `sound_on_tap`, `log_as`, each falling back per key. `max_bpm` also stops one
  bounced contact (two edges 20 ms apart imply 3000 BPM) throwing the average
  away. A finished session logs its tempo in the new `value` column; backing
  out without setting one logs nothing.
- ~~**An event can carry a number**~~ - one nullable `value REAL`, appended so
  existing positional reads keep meaning what they meant, with a test that
  attaching a value never changes what an event *counts* as. See item 1.
- ~~**The side pane folds away**~~ - see item 6.
- ~~**The offline editor rendered as a sliver**~~ - its layout container
  carried only `.body-split`, a class the shared stylesheet does not define,
  so `display: grid` and `flex: 1` never applied and `.tab-panels` resolved to
  zero height. It looked built - toolbar and tabs render - which is why it
  survived a look. The test asserts the invariant (a layout container must
  carry a class the stylesheet actually defines) rather than pixels.
- ~~**Single-instance guard**~~ - [single_instance.py](aibutton/single_instance.py)
  takes an OS-level lock on `<database_path>.lock` at startup and a second
  copy refuses with the holder's PID and exit 1, instead of two processes
  ping-ponging the BLE connection. The lock is a file lock rather than a PID
  file precisely so a crash or a hard kill leaves nothing to clear by hand -
  verified by killing the holder with `-Force` and starting a fresh one.
  `--no-lock` opts out for the rare deliberate second instance.
- ~~**The run loop survives its own components**~~ - `handle()` and the
  takeover loops guarded their own bodies, but `resolve()`, `store.logged_today`,
  `due_alarm()`, `log_mode_enter()` and the palette push all sat unguarded in
  the `while` body, so one locked-database write ended the service. The
  iteration now has a backstop that logs, drops the LED back to IDLE (a fault
  mid-`handle()` used to leave it stuck on LISTENING) and holds at tick rate
  rather than spinning. Repeat faults are throttled by `FaultTracker` - pure,
  so the throttle is tested without a clock.
- ~~**A bad event log no longer stops the button**~~ - an unopenable database
  degrades to an in-memory log with a loud error and a `degraded` flag,
  instead of `EventStore.__init__` preventing startup. Writes also get a
  busy timeout so a transient lock doesn't fail a press.
- ~~**Graceful shutdown on Windows**~~ - SIGTERM/SIGINT were registered
  behind a `hasattr(signal, "SIGHUP")` check, so on the host this actually
  runs on they were never wired at all and Ctrl+C unwound as a
  `KeyboardInterrupt` straight through the takeover loops. They are now
  registered separately from SIGHUP, falling back to `signal.signal` where
  the event loop has no `add_signal_handler`; a second Ctrl+C restores the
  default handler so a wedged shutdown is still killable.
- ~~**Pomodoro mode**~~ - a takeover template with configurable durations, an
  `advance` setting (auto / manual / breaks-only), and assignable gestures.
- ~~**Built-in modes set**~~ - Pomodoro, Gratitude counter, Stopwatch and 5AM
  alarm, offered as ready-made modes in the web UI.
- ~~**Hardware validation**~~ - an ESP32-S3 Mini runs the firmware with room
  to spare.
- ~~**Editable LED colours**~~ - the palette lives in config, is edited in
  the web UI, and is pushed to the device live.
- ~~**`fade` LED style**~~ - a true crossfade between two colours (as
  opposed to `alternate`'s hard swap), mirrored across
  `firmware/protocol.py`/`led.py`, `device.py`/`config.py`, and both web
  previews.
- ~~**Pomodoro's own LED states editable**~~ - `WORKING`/`RESTING` existed in
  config and firmware but were missing from the Lights tab's state list;
  fixed, plus a test that catches the editor's state/style lists drifting
  from the device's again.
- ~~**Mode-switching explainers**~~ - a plain-language primer, everyday vs.
  takeover grouping, a live "active now" mark sourced from the host's own
  `resolve()` (not re-derived in JS), and per-takeover-mode "how to start it
  / how to leave it" text, including a warning when a mode has no gesture
  that can reach it.
- ~~**App shell rewrite**~~ - fixed-viewport layout (no page-level scroll),
  tabs (Modes/Lights/Events/Device), a device/status side pane, master/detail
  mode editing instead of a stacked accordion, a squared-off dark theme, and
  a global Tips toggle (`help.js`) that hides tutorial copy by default.
- ~~**Tap metronome mode**~~ - a takeover template with no config surface of
  its own (the tempo is session state): short press/double tap mark a beat,
  long press exits, BPM is a rolling average of recent tap intervals (a >2s
  gap starts the average over), and the LED pulses live at the tapped tempo
  via a new `METRONOME` state (`0x0B`) whose period is pushed to the device
  in real time and floored for flash safety, reverting to the configured
  palette on exit.
