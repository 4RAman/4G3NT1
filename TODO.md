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
| **The colour engine** — a stop list instead of `{style, 2 colours, period}`; progress ramps; named looks a mode picks from | 0b·3 ✔, **3**, **4**, 0a's per-app colour | ~~Wire change~~ — **ungated**, effects shipped |
| **The gesture engine** — N taps, hold levels, the ramp that renders them | 0b·2 ✔, the 5-tap toggle | ~~Wire change~~ — **ungated** for taps; hold levels still need firmware |
| **Depth without the wire** — metronome config ✔, event values ✔, Tinker mode, filtering/export | **1**, **9**, **12** | None — ship freely |
| **Reach and hosting** — launcher, remote UI | **0a**, **7**, **8** | 0a gates 7 |

**The gate column is the news.** Two of these four were blocked on a reflash
and are not any more, which makes item **3** (named looks per mode) the
obvious next thing: it is the last piece 0a's launcher needs, and it is now
pure host-side work.

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

**Depends on** per-app colour (item 3), or the LED shows the same thing for
every entry in the list, which defeats the cycling. That dependency is now
**entirely host-side**: 0b's ephemeral effects shipped, so showing a
different colour per entry is a `set_led(state, effect)` call in the
launcher's loop and needs nothing from the firmware. Item 3 is what decides
where those colours are *stored*.

**Also cheaper than it was:** `triple_tap` is a real gesture now, so the
launcher can be reached without spending one of the original three. The
arithmetic in the first paragraph was written when there were three.

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

**What is left:**
- Filtering/search in the Events tab UI (by kind, by name, by date range) —
  `/api/events` ([webui.py](aibutton/webui.py)) still takes `limit` and
  nothing else, and [index.html](aibutton/web/index.html) renders a flat
  table. Now worth more than it was: there is a numeric column to filter and
  sort on.
- Exporting the log (CSV/JSON download) — there's no export endpoint today.
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

### 3. Put mode-relevant LED pickers inside the Modes tab

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

### 4. Turn "seconds per cycle" into a slider, with a safety floor

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
`double_tap → Log(note)`. Change the name (the request says "mode
selection" - `"Mode Selection"` reads more like a UI label than a mode name;
confirm what the user actually wants it called) and its default bindings to
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

**Item 0a first, or most of these are unreachable** — three gestures means
two launchable apps until a launcher exists.

**Two are done** - Tap metronome and Countdown (see Done below); the countdown
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

### 11. Split Alarm into "Alarm" (clock) and a new "Reminders" mode

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
- **On/Off toggle** - "5 taps" as a global toggle. **No longer firmware.**
  0b·2 shipped, so this is now: add `TAP_5 = "tap_5"` to `TriggerType`, the
  matching entry to `GESTURES` in `schema.js`, and an action to bind it to.
  The detector already counts that far and the wire already carries it; the
  host writes `max_taps=5` by itself the moment something binds it. Worth
  knowing that binding it *does* cost the double tap its instant response -
  that is the trade `max_taps` makes explicit, and the reason not to bind a
  long tap by default.

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
