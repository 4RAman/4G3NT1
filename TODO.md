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
every entry in the list, which defeats the cycling. Treat 0a + 3 + 0b's
ephemeral-effects piece as one body of work, not three.

### 0b. Freeze the wire protocol as v1

Four additions that are cheap now, and a flag day once units exist outside
this room. Land them as one revision — each one separately means another
reflash and another chance to drift the mirrored tables
([device.py](aibutton/device.py) / [firmware/protocol.py](firmware/protocol.py),
guarded by [test_protocol.py](tests/test_protocol.py)).

1. **`DEVICE_INFO`** — a characteristic carrying firmware version plus a
   capability bitmap (has-LED, has-buzzer, has-haptics…). Cheapest item here
   and the one that makes every *later* protocol change non-breaking: the
   host asks instead of assuming.
2. **Parameterised gestures** — the wire carries three constants
   (`0x01`–`0x03`). Make it carry a kind plus a parameter (tap count, hold
   bucket) so 5-tap (already wanted, see "On/Off toggle" below), triple tap
   and hold-levels arrive as data rather than as new codes. Mirrors into
   [trigger.py](firmware/trigger.py) and [button.py](aibutton/button.py).
3. **Ephemeral effects** — a way to push "render *this look*" without
   allocating a global `LEDState`. `0x0B` of a one-byte namespace is spent,
   every code is mirrored four ways, and all instances of a template share
   one palette entry. `run_metronome` already reaches around the abstraction
   to rewrite the palette live; generalise that instead of copying it.
4. **An OTA/version handshake** — reserve it now, implement before any unit
   leaves the building. You cannot fix a bug in a key fob you don't have.

Rationale and the cost of deferring each: **D4**, **D5**, **D6**, **D8** in
[ROADMAP.md](ROADMAP.md).

### 1. Richer, more precise logging in the Events tab

**Partly shipped.** [store.py](aibutton/store.py) now has the `mode` column
(with an `ALTER TABLE` migration in `_migrate` for existing databases) and
`log_mode_enter` / `log_mode_exit`, which the takeover loops in `main.py`
call, so a takeover session is recorded with its duration. `recent()` and
`/api/events` both carry `mode` through.

**What is left:**
- Filtering/search in the Events tab UI (by kind, by name, by date range) —
  `/api/events` ([webui.py](aibutton/webui.py)) still takes `limit` and
  nothing else, and [index.html](aibutton/web/index.html) renders a flat
  table.
- Exporting the log (CSV/JSON download) — there's no export endpoint today.
- Which *gesture* produced an event, which the `mode` column doesn't tell
  you. Only worth adding if item 12 turns out to need it — don't widen the
  schema on spec.

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

**Real dependency, not optional polish:** every Pomodoro today shares the
*one* `WORKING`/`RESTING` palette entry — this was already flagged as
"Palette for the built-in modes" in the old list. Moving the picker into the
Modes tab without solving this means two Pomodoros still can't look
different, which defeats the point of putting the picker next to the mode.
Solving it needs a per-mode override stored on the `Mode`/behaviour itself
(`config.py`), not just the global `led_palette` dict, with the global entry
becoming the fallback when a mode has no override. Touches `config.py`
(parsing/validation), `device.py` (still keyed by `LEDState`, so a per-mode
override needs its own wire path or gets folded into what's sent on connect),
and `main.py` (`set_led` calls would need to also push the override).

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

**Confirm the number before shipping.** The request was "no lower than 4Hz
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

### 6. Make the Press/Clock side-panel sections collapsible

Small, self-contained. `.side-block` in [index.html](aibutton/web/index.html)
(Virtual device / Press / Clock) are always fully expanded, which is most of
the side pane's height on a short viewport. Wrap each in a native
`<details>`/`<summary>` (the project already leans on plain HTML disclosure
widgets elsewhere before this session's rewrite removed the last of them;
it's the simplest option and needs no new JS) or a small custom toggle if you
want the state to persist across reloads (`localStorage`, same pattern as
[help.js](aibutton/web/static/help.js)'s Tips toggle). Decide whether
collapsed is the sensible default or only remembers what the user last set.

### 7. Build at least 10 modes total

**Item 0a first, or most of these are unreachable** — three gestures means
two launchable apps until a launcher exists.

**One was specified and is done** - Tap metronome (see Done below). The
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
  `config.py`, a `run_*` loop in `main.py`, a `schema.js` `TEMPLATES` entry,
  and usually a new `LEDState` (protocol.py/device.py/led.py, next free code
  is `0x0C` now that metronome took `0x0B` - see item 3's cross-file rule).

**Known hardware constraint, worth knowing before proposing more ideas:**
the LED renders one animation *per state*, entirely on-device
(`firmware/led.py`); the host can only select which state and edit that
state's static effect. There is no way to push an arbitrary one-off
animation (e.g. "flash this exact sequence") - so ideas like a Simon-Says
memory game are not straightforwardly buildable on the current firmware
without a new wire concept.

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

**Do not start building before this is answered - it changes the shape of
the whole task:** BLE has short range and this app allows exactly one
running instance (`CLAUDE.md`'s single-instance rule; `DESIGN-ESP32.md`'s
"host must be awake" constraint; "WiFi transport" is explicitly parked below
*because* it would remove this constraint, which it hasn't been). So "host
on my server" only makes sense if either (a) the server named `4g3nt.0` -
confirm the exact hostname, that may be a rendering of the BLE device name
`4G3NT0` seen in the live dashboard rather than a real server name - is
physically near the button and holds the Bluetooth connection itself, or
(b) the intent is to host *only* the read-only web dashboard remotely while
a separate local process (this Windows machine, today) keeps the actual BLE
connection and event database. Those are architecturally different builds.
Ask before writing a Dockerfile.

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
reminder shouldn't look identical to one. If item 0b has landed, that look is
an ephemeral effect and costs nothing; if it hasn't, it is a new `LEDState`
(next free wire code `0x0C`, metronome took `0x0B`) mirrored per item 3's
cross-file rule, plus a `test_firmware_feedback.py`/`test_protocol.py` entry -
which is exactly the tax 0b exists to remove. No looping sound (a single chime, or none).
Clearing it (any press, or a specific gesture - decide) logs a
"cleared today" event and stops the flash, mirroring how
`unless_logged_today` already lets an *ambient* mode stand down once
something is logged today, except this is a *scheduled/takeover* mode doing
the equivalent. New `ReminderBehavior` in `config.py`, a `run_reminder` loop
in `main.py` (mirrors `ring_alarm`, much simpler - no snooze branch), and a
`TEMPLATES` entry in `schema.js` (`nature: 'takeover'`,
`allowedActivations: ['schedule']`, `startedBy: 'schedule'`).

### 12. Look into analytics/tracking - scope first, this is vague as given

Before building anything: "improve performance" needs to be pinned down -
it could mean (a) *habit* analytics for the user (mode usage, streaks,
time-of-day patterns - a real dashboard over `EventStore`), (b) *device*
telemetry (BLE reconnect frequency, gesture-to-feedback latency, dropped
presses while busy - already flagged as a known rough edge below), or
(c) *hosting* metrics once item 8 exists (server-side, nginx/docker level).
Ask which. Whichever it is, it depends on item 1: today's event log doesn't
carry enough detail (no mode/source column, no takeover-session records) to
build much analysis on top of, so item 1's scope decision should account for
whatever this item ends up needing.

## Smaller, worth doing

- **Single-instance guard.** Two copies of the app fight over the button:
  BLE allows one central, so the connection ping-pongs and the web UI
  flickers between connected and offline. Detect it at startup and refuse,
  rather than leaving it to be diagnosed from a log.
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
- **On/Off toggle** *(firmware)* - "5 taps" as a global toggle, needs a new
  gesture in [trigger.py](firmware/trigger.py) *and* its mirror in
  [button.py](aibutton/button.py), plus a wire code. **Fold into item 0b** -
  a parameterised gesture gives you this and triple-tap and hold-levels for
  the same reflash.

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
