# CLAUDE.md

One physical button on an ESP32, a Python brain on the PC, talking BLE.
Read [README.md](README.md) for what it does,
[DESIGN-ESP32.md](DESIGN-ESP32.md) for how it got this shape,
[ROADMAP.md](ROADMAP.md) for where it is going, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the design it is going *to* — the last
two matter more than usual here, because several cheap decisions today are
expensive ones after hardware ships.

## Commands

```bash
.venv/Scripts/python -m pytest -q                       # the whole suite, no hardware needed
.venv/Scripts/python -m aibutton.main --config config.json          # MockDevice + web UI
.venv/Scripts/python -m aibutton.main --ble --config config.json    # the real button
.venv/Scripts/python -m aibutton.control               # the tray control panel
.venv/Scripts/python -m mpremote cp firmware/*.py : + reset         # flash the firmware
.venv/Scripts/python tools/ble_probe.py --cycle        # drive the firmware by hand
.venv/Scripts/python -m aibutton.scenes list|check|activate         # scenes, service stopped
.venv/Scripts/python tools/build_editor.py             # dist/button-editor.html (offline)
```

## Do not run the tests without being asked

**Standing instruction from the owner of this project, 2026-08-26. It
overrides any habit, any checklist, and anything below that reads like "run
the suite before and after".**

Write tests. Do not run them. When you would have, **print the command and
move on** — the decision to spend three and a half minutes and a slice of a
paid context window belongs to the person paying for it, not to the agent that
feels tidier afterwards.

**The reasoning, in the owner's words: tokens are expensive.** A full run costs
~3.5 minutes and a meaningful share of a session's budget, and the failure mode
is not one run — it is running at the start, again in the middle and again at
the end, tripling that for information that has usually not changed. *This
project has run for three sessions with one known failing test and lost
nothing by it.* A lingering red test is cheap; a habit of re-running the suite
for reassurance is not.

So:

- **Never run `pytest` unprompted**, whole suite or single file. Hand over the
  command instead.
- **One explicit "run the tests" authorises one run**, not a run per phase of
  the work.
- Prefer things that cost nothing: `node --check` on a JavaScript file,
  `python -c` on one function, reading the code.
- If you genuinely cannot tell whether something works without executing it,
  **say so and ask** — do not decide on the owner's behalf.

Only **one** instance may run: BLE allows a single central, so two copies
steal the connection from each other. A second one now *refuses* at startup
(`single_instance.py`) rather than fighting — stop the first, or pass
`--no-lock` if you genuinely mean it.

## The control panel is not the web UI

Two UIs, and the split is structural:

- **The web UI** (`webui.py`, :8080) is served *by* the running service and
  configures it. It can never start the service, because it only exists once
  the service is up.
- **The control panel** (`aibutton/control/`, a tray icon) sits *around* the
  service and owns its lifecycle - start, stop, watch, flash.

Anything about *what the button does* goes in the web UI; anything about
*whether the service is running* goes in the control panel. The panel imports
the service, never the reverse.

The panel's Start defaults to `--ble`, the opposite of the command line, and
deliberately: someone running the panel has a button in front of them. Its
settings live in `control-panel.json`, **never inside `config.json`** - the
editor rewrites that file wholesale, so a panel setting there would not
survive a Save.

**A second launch talks to the first rather than refusing.** It asks over a
loopback socket ([beacon.py](aibutton/control/beacon.py)); answered means the
running panel shows its window and the newcomer exits quietly. **If the holder
does not answer it is wedged, and the newcomer says so and names the PID.**
Three situations used to look identical - running, wedged, and running but
invisible - and Windows hides new tray icons in an overflow flyout, so "look in
the tray" is advice many people cannot act on. The window is shown at launch
(`show_on_start`) for the same reason.

**Never parent a dialog to a withdrawn Tk root.** It renders with no taskbar
button and no focus, so the process sits forever holding a dialog nobody can
see or dismiss.

Stopping: Windows never delivers SIGTERM between processes and
`CTRL_BREAK_EVENT` needs a console a tray app lacks, so the polite stop is
`POST /api/service/stop`, with signals the fallback for POSIX and for a service
started from a terminal. A hard kill is safe by construction (the OS drops the
run lock, the store commits per write); it only skips the device's goodbye.

## Shape

```
firmware/ (ESP32)              aibutton/ (PC)
  gesture detection  ──BLE──▶    rules → actions → store
  LED + buzzer       ◀──BLE──    modes, scheduler, web UI
```

The ESP32 detects and renders. **Every decision is host-side**, including
what colour each state is. Timing that can't survive radio jitter (the 0.4 s
double-tap window) is the one thing that lives on the device.

## SOLID, as it actually applies here

Not aspirations - the reasons the code is shaped as it is. Match them.

**Single responsibility - a pure core with I/O injected at the edges.**
[rules.py](aibutton/rules.py), [scheduler.py](aibutton/scheduler.py) and the
parsing half of [config.py](aibutton/config.py) are side-effect-free functions
over data, which is why they need no mocks and why the app runs with nothing
plugged in. [trigger.py](firmware/trigger.py) is pure for the same reason - the
one piece of firmware the host suite can execute.
*Keep new logic out of I/O classes; take the clock and the store as arguments.*

**Open/closed - capability is added as data, not as branches.**
[schema.js](aibutton/web/static/schema.js) declares every action, template,
activation, LED style and setting; the editor and its widgets are generated
from those tables.
*If you find yourself adding an `if template == ...` to the UI, add a
descriptor instead.*

**Liskov - implementations are interchangeable, no downcasting.** `MockDevice`
and `BLEDevice` differ in everything except behaviour. Widgets all return
`{ el, validate }`.
*The one legitimate `isinstance` on a device is the web UI asking "is this a
mock?" to decide whether to show the virtual panel.*

**Interface segregation - the seam is four methods.** `ButtonDevice` is
`events` in; `set_led` / `play_sound` / `start_loop` / `stop_loop` out, plus
lifecycle. Palettes, reconnection and byte encoding are private to the
implementation. *Resist widening it* - `set_palette` and `set_gesture_config`
earned their places by being device state the host **asserts**, exactly like
the LED state. `info` is the counterpart and stayed an **attribute rather than
a method**, because it is device state the host *reads* and never asserts, so
nothing has to be implemented to satisfy it.

Ephemeral effects are the worked example of *not* widening it: "show this look
now" became an optional second argument to `set_led`, not a fifth method,
because it is the same assertion carrying more detail. The state argument stays
required - it is what the status line reports and what a device too old for
effects falls back to rendering. **That fallback lives inside `BLEDevice`, not
in the run loop**: whether a look costs a borrowed palette entry is the
device's business.

**Dependency inversion - mind the direction.** `main` depends on
`ButtonDevice`, never on `BLEDevice`; the concrete import is deferred to the
one line that chooses it. [device.py](aibutton/device.py) imports nothing from
the package - `config` imports *it*.
*Never let device.py import config.py; palette encoding duck-types the effect
object precisely to avoid that.*

## Apps, not features

The product is *a button that runs swappable apps*. What ships as a "mode"
today becomes an "app" tomorrow, and the direction of travel is that **adding
one touches the app's own files and nothing else**. Full plan in
[ROADMAP.md](ROADMAP.md); what it means today:

**Know what an app currently costs.** A rich template is a 4-to-6 file change:
`config.py` (dataclass, parser, allow-list, serialiser, union), `main.py` (a
`run_*` loop and two `isinstance` chains), `schema.js` (template, takeover set,
built-in), plus tests. Every one is a place a third-party app author cannot
reach. If adding an app means editing the core, **that is the tax - note it,
don't normalise it.** Its own light and a new gesture used to cost more and no
longer do; those are the two taxes protocol v1 removed.

**Prefer a preset to a template.** A new `BUILTIN_MODES` entry costs zero
Python. Reach for a new `*Behavior` only when an existing one genuinely cannot
express the behaviour.

**Don't burn a wire code.** `LEDState` is a one-byte global namespace, mirrored
in four places, `0x0B` already spent, and *shared* - every Pomodoro gets the
same colours. An app wanting its own look pushes an effect, which since
protocol v1 is supported rather than a workaround: the device renders it until
the next state change, storing nothing (`run_metronome` and `run_countdown` are
the two to copy). **Allocating a new `LEDState` needs an argument for why the
app's look is a thing the whole system should have a name for.**

**Keep new logic out of the run loop.** The takeover loops are the one place
the pure-core rule is *not* followed - they await the device, so they need
asyncio and can run nowhere but the host. New behaviour should lean toward a
step function over `(state, event, now)` returning effects. Anything pure
survives the Stage-3 move unchanged; anything awaiting a device gets rewritten.

**The brain is moving to the device - decided.** The button runs its own OS and
the active app; the phone holds preferences and does the heavy lifting. Design
in [ARCHITECTURE.md](ARCHITECTURE.md). Three consequences today:

- Code assuming *"the host is awake and connected"* is fine now and must be
  easy to find later. **Say so in a comment when you write it.**
- Anything that must feel instant (light, sound, what a press means) belongs on
  the device eventually; anything needing a network, a parser or a model
  belongs on the phone permanently. ARCHITECTURE.md's latency budget is the
  arbiter, not taste.
- **An app is data, not code**: a state machine with expressions, bounded by
  construction - no loops, no allocation, no recursion. Extend the *effect set*
  rather than reaching for something only a general-purpose language could
  express.

## Invariants

- **Mirrored tables are tested, not trusted.** The protocol lives twice
  ([protocol.py](firmware/protocol.py) / [device.py](aibutton/device.py)) and
  so do the tone tables and the LED styles, because one side ships to a
  microcontroller. [test_protocol.py](tests/test_protocol.py) and
  [test_firmware_feedback.py](tests/test_firmware_feedback.py) fail on drift.
  Change one side, change the other, in the same commit.
- **A bad config never crashes the service.** Every key falls back
  individually with a logged error, and the web API returns those same
  warnings so the editor shows what was actually accepted. New config
  surfaces follow that pattern — see `_parse_effect` for the shape. A missing
  or broken *scene* is the same rule one level up: it is reported and the base
  config runs.
- **One parser, and scenes merge before it.** A scene
  ([scenes.py](aibutton/scenes.py)) is layered over `config.json` as a **raw
  dict** inside `load_config_full`, so `parse_config` still sees one object
  and every fallback applies to scene files for free. Never add a second
  validation path for scenes — that is the whole reason the merge is where it
  is. `scenes.py` imports nothing from the package, exactly like `device.py`;
  `config` imports *it*.
- **Edits go to the active scene, the pointer stays in config.json.**
  `ConfigManager.write_path` is the one place that decides, so the two files
  never hold two copies of the same modes list. Anything a scene changes that
  is only read at startup (BLE name, web bind, database path) is reported as
  `needs_restart` rather than silently ignored.
- **Feedback is fire-and-forget.** `set_led` and friends are synchronous and
  must never block; `BLEDevice` queues and drops rather than waiting. The
  mode machine cannot afford to await a radio.
  **A mode's `on_enter` hook obeys the same law and its `on_exit` does not**,
  and the asymmetry is the whole point: entry is a thing you are waiting for,
  so `spawn_hook` schedules it and lets the app open now — a webhook timeout
  between the press and the app is a broken button, not a slow server. Exit is
  awaited because nothing is waiting on it and a launcher's chain needs each
  app's exit to land before the next app's entry. A spawned hook is **held in
  a set**: asyncio keeps only a weak reference, so a task nobody holds can be
  collected mid-flight and simply not happen — the same trap as the ctypes
  callback below, a different library.
- **An app's result is data, and the contract is enforced rather than asked
  for.** A takeover reports a flat dict of scalars on exit
  ([summary.py](aibutton/summary.py)) and the `on_exit` hook carries it out -
  merged flat into a webhook's payload, appended to an OSC message's arguments.
  `summary.clean` is the single gate (flat, scalars, `MAX_KEYS`), for the
  reason `flash_safe` is one: a rule each app is trusted to remember is a rule
  that drifts. A key that breaks it is dropped with a warning and the hook
  still fires. **An app reports the same keys on every exit, or none at all** -
  one carrier is positional, so a key that appears only sometimes renumbers
  every argument after it; report a zero, plus the count that says whether the
  zero means anything. Nothing to report costs nothing: no key, no empty
  object, no branch.
- **The host owns state; the device renders it.** The firmware's palette and
  animations are a *fallback* for running with no host attached. Anything
  persistent belongs in `config.json`.
- **The flash floor has one gate, and it is a setting.**
  `min_flash_period_s` defaults to `device.SAFE_MIN_PERIOD_S` (3 Hz, WCAG
  2.3.1) and may be taken lower deliberately — that is honoured *and* warned
  about, because clamping a setting silently makes it a lie. Enforcement is
  `config.flash_safe`, applied in `main.set_led` (every pushed look) and where
  the palette is pushed (the device renders those unasked). Do not add a
  second clamp: a floor in three places is a floor with three chances to
  drift. Only `device.STYLE_STROBES` styles are floored, mirrored as
  `strobes: true` in `schema.js`. A stop list ([sequencer.py](aibutton/sequencer.py))
  is the second shape of the same law: `config.sequence_safe`, applied at the
  same single point in `main.set_led`, floors each stop's *dwell* at half the
  floor — a stop list has no period, so the floor is defined over transitions
  — and a one-shot of three stops or fewer is exempt, which is the
  confirmation-flash rule. One call site each, still.
- **Long press means "up one level", everywhere.** Alarm, stopwatch, counter,
  pomodoro, metronome, countdown, both games, the signal light, the control
  surface and the launcher all leave on a long press;
  the Pomodoro parser warns if you unbind its only exit. **The control surface
  is the case where the parser takes the choice away entirely** — it is a
  gesture→action map like an ambient mode, so binding `long_press` is a thing
  a config can obviously *say*, and `_parse_control_body` drops it with a
  warning. Four gestures feels tight and the fifth is right there; that is
  precisely why it is enforced rather than documented. The launcher is the
  case that proves it - it launches on a *double tap*, because a menu where the
  universal escape gesture instead committed you to something would be the one
  exception to a rule people are supposed to trust without thinking. Modes
  entered from a launcher return to it (`return_after`, on by default), so the
  gesture always travels exactly one level rather than one-or-two depending on
  how you arrived. **A new takeover binds long press to leaving, or has a very
  good reason.**
- **A gesture happened earlier than it arrived, and only the device knows how
  much earlier.** A single press is held back until the multi-tap window
  closes, *unconditionally* — `max_taps_for` floors at `DEFAULT_MAX_TAPS = 2`,
  so no config makes a press instant, and binding only a short press does not
  either. It is a constant rather than jitter, so anything measuring human
  timing subtracts it: `ButtonDevice.press_latency_s`, read from the device
  the way `info` is, because an injected press (the web UI's simulate buttons,
  every test) arrives the instant it is made and correcting *that* would be
  the same bug backwards. **Never hardcode the window in an app** — a game
  that did would be wrong under simulation and would not survive the move onto
  the device. What is left after the correction is tens of milliseconds of
  radio and scheduling, and that is the real precision floor: ±150 ms games
  are honest, tight rhythm judgement is Stage 3.
- **One colour control, used everywhere colour is chosen.**
  [colorEngine.js](aibutton/web/static/colorEngine.js) is the only thing that
  edits a `LedEffect`: the Lights tab's system states, the named-look pool and
  a mode's own look all mount the same component, and it returns the widget
  contract (`{el, validate}`) so it drops into a form beside any field. It
  absorbed the test bench rather than replacing it — pushing a look at the
  hardware is a *capability of every picker* now, and the Diagnostic row is the
  wiring test README's gotchas depend on. **Live preview is optional by
  construction** (`api.showLook` may be absent): the offline editor has no
  device, so a colour control that required one would be the wrong seam. New
  places that need a colour mount the engine; they do not grow their own.
- **One control answers "what does this look like", never two.** A state that
  can wear a named look offers it as the last option in its **Style dropdown**
  (`o.namedLook`, `__look__`), and the pool picker appears only once it is
  chosen. It was a second select of its own, and the cost was not tidiness:
  the row went on summarising, swatching and previewing the *palette entry*
  while the button wore the look, so a feature that worked read as broken.
  Whatever the control decides is what its head describes and what "Show on
  the button" pushes — `shownLook()` is the one answer, used three times.
  *A new way to colour something appears inside that dropdown or explains
  why not.*
- **A look is asserted; a palette entry is stored.** The device holds the
  palette and re-renders it unasked, so pushing an edited palette is enough.
  Nothing on the device holds a *look*, so an edited look has to be
  re-asserted or the light keeps showing the old one until the next press —
  which is indistinguishable from the edit not working, and was reported as
  exactly that. `main`'s tick re-asserts **IDLE** when its resolved look
  changes, alongside the palette push. IDLE alone, because it is the only
  state the ambient layer rests in; every other state is repainted by the next
  press anyway.
- **The Lights tab is the button's vocabulary; a mode's colour lives on the
  mode.** IDLE/LISTENING/THINKING/SUCCESS/ERROR are edited once, globally.
  LISTENING is the one dual citizen (TODO 26): the ambient layer wears it
  with no mode involved, so its global default stays on the Lights tab —
  *and* a control page may name a look for it, overriding the global colour
  only while that page is open. Two scopes, one state; every other state
  belongs to exactly one side.
  Everything a mode owns (ALERT/TIMING/COUNTING/WORKING/RESTING/METRONOME) is
  edited on that mode's page, because a mode you configure in two tabs is not
  modular. Their palette entries **stay in config** as the invisible fallback a
  mode with no named look renders (`base_look` reads them) — only the editor
  group went away. Deleting the entries would leave such a mode with nothing.
  The mode list shows each mode's **first owned state** as a live swatch
  (`_modeLook`, mirroring `main.app_look`): a mode is a thing you recognise by
  its light, and a template that owns no state gets an empty ring rather than
  an invented colour.
- **The named-look pool is a list; one entry is open at a time.** Every entry
  used to be an expanded editor, which made six looks six editors and "which
  one is Ember?" a scrolling problem. A look is identified by its light and
  its name, so those are the line — with where it is worn, because *editing a
  shared look changes it everywhere* and that has to be visible before the
  edit, not after it.
- **A stop list is the rich form; a palette entry is the fallback form.**
  A `sequencer.Sequence` shapes each fade (`Stop.curve`), which makes it able
  to express nearly every look in the system — *except* the one thing that
  matters most: a palette entry ships to the device and renders with **no host
  attached**, and a sequence is a schedule only the host can walk. So a
  sequence never goes in `led_palette`. The system states name one instead
  (`AppConfig.state_looks`), and resolution runs **explicit effect → the active
  mode's look → the global state look → None**, where None still means "the
  device's palette entry". Both layers stay populated on purpose. *Do not
  "simplify" this by moving sequences into the palette — that is the button
  going dark when the host does.*
- **A stop list is walked or sampled, and that decides which function reads
  it.** `Sequence.drive` is `clock` (walked by `plan_at`, which returns a
  wait), `progress` or `beats` (sampled by `sample_at`, which returns none —
  only the app knows when its number moves next). **Sampled fades interpolate
  continuously; walked ones keep the 50 ms quantisation**, because that
  stepping models what a radio carries when the host is pushing every frame,
  and nothing is pushing a sampled one. Which apps can supply which drive is
  `DRIVE_TEMPLATES` — **keyed by template, not by state**, because `TIMING`
  belongs to both the countdown and the stopwatch and only one of them has an
  end to be a fraction of. A drive bound where nothing supplies it is warned
  about and played on the clock, never dropped.
- **When more than one thing can colour a state, the more explicit one wins.**
  Named stop list > ladder > ramp, in `run_countdown`, `run_metronome` and
  `run_pomodoro` alike: a ramp is the template's own default, a ladder is a
  checkbox you tick, and a look you had to build, name and point a mode at is
  the most deliberate of the three. A template that has no ladder simply skips
  that rung. *A fourth colour source obeys the same ordering or explains why
  not.*
- **A ramp is opt-in where the template already speaks in colour.** A
  countdown's ramp is on by default because TIMING is its only state and it
  has nothing else to say; a Pomodoro's is **empty** by default because
  WORKING and RESTING are two colours precisely so you can tell focus from
  break, and a ramp overrides both. The better answer there is a named stop
  list, which is chosen *per state* - so a progress-driven look on WORKING
  leaves RESTING alone. *A new template with more than one state defaults its
  ramp empty, or says why its states are interchangeable.*
- **A drive needs an app that both knows the number and repaints.** Knowing is
  not enough: `run_pomodoro` always knew how far through a block it was and
  still could not carry `progress`, because `show()` ran only on phase changes
  and gestures, so nothing sampled the look. The tick is what put it in
  `DRIVE_TEMPLATES` (TODO 19c). Its progress is through the **current block** -
  a classic Pomodoro has no end to be a fraction of - so it resets every phase,
  and `extend` grows the denominator with the deadline or the colour snaps back
  to the start of the ramp. *Adding a template to `DRIVE_TEMPLATES` means
  checking it repaints, not just that it could answer.*
- **A stop is one flat colour, and the movement is the walk between stops.**
  A stop briefly carried its own `style`/`period_s`, so one node could be
  "flashing yellow" (TODO 36c, removed in 36e). It went because a list that
  walks colours *and* animates inside them is two clocks on one light and no
  layout could say which one you were setting — and because everything it
  expressed is expressible as more stops: a flash is on, off, on. *Resist
  putting a rate back on a stop.* The `style`/`period_s` keys are still
  accepted and ignored in silence — they were ours to write and ours to drop,
  and warning about a key we put there ourselves is scolding, not a fallback.
- **`sequence_safe` floors one axis: a stop's dwell.** `hold_s + fade_s`, at
  half the flash period, exempt for a one-shot of ≤3 stops (a handful of
  transitions played once sustains nothing — the confirmation-flash rule).
  There used to be a second axis, a stop's own style period, floored
  unconditionally because the exemption's reasoning did not reach inside a
  single stop; stops are flat now, so the dwell is the whole floor. Spelling
  a flash out as stops does not get round it — three stops 0.05 s apart are
  three transitions 0.05 s apart. Still one call site, still `main.set_led`.
- **A rainbow's two colour fields are its brightness and its saturation.**
  Neither is a hue — a rainbow is all of them — so `color`'s brightest channel
  is the level and `color2`'s is the colour strength, each **0 meaning full**
  because that is what an unset field looks like in a config written before
  the meaning existed. An addition rather than a repurpose (those bytes were
  discarded for this style), no wire change, and a capability bit each
  (`CAP_RAINBOW_LEVEL`, `CAP_RAINBOW_SAT`) — without one, a slider doing
  nothing on un-reflashed firmware is indistinguishable from one that works.
  `STYLE_USES_LEVEL` / `STYLE_USES_SATURATION` stay disjoint from
  `STYLE_USES_COLOR` / `STYLE_USES_COLOR2`: one byte, one control, or only
  one of them is telling the truth.
- **A gesture holds an action or names one, and the name is resolved at use
  time.** The pool is `AppConfig.actions`; a binding that is a **bare string**
  is a reference into it (`NamedAction`). One resolver,
  `config.resolve_action`, called at each of the five places an action is
  dispatched (`main.handle`, `run_control`, `run_signal`, `fire_hook` for a
  mode's `on_enter`/`on_exit`, and `handle_reflex` — which was the predicted
  fifth and arrived as one) — a sixth dispatch site calls it too, or that
  surface silently cannot use the pool. Naming is optional and inline actions
  are untouched, because most actions are used once. **Deleting a pool entry leaves the references dangling on purpose**:
  the parser warns, the editor shows "(missing)", and the runtime fails
  clearly, all of which beat quietly repointing several gestures at something
  nobody chose. Renaming in the editor rewrites references; a hand-edited file
  can still dangle, which is why the parser warns at all. A pool entry may not
  itself be a name — that is where one-level-only is guaranteed, so
  `resolve_action` needs no cycle check.
- **A sequence is flat, bounded, and its limits live in the parser.**
  `SequenceAction` (TODO 33) is a list of primitives with optional waits — no
  loops, no conditionals, **no nesting**, because the on-device runtime has to
  be able to run it (ROADMAP D2) and an interpreter is exactly what it cannot
  have. Nesting is refused **twice**, and both are load-bearing: the parser
  refuses an inline `sequence` step, and `resolve_action` refuses a step that
  *names* a pooled sequence — the shape the parser cannot see. A step is a
  fire-and-forget primitive (`SEQUENCE_ACTIONS`); the four the run loop keeps
  for itself are not steps, for the same reason they are not hooks.
  `MAX_SEQUENCE_STEPS` and `MAX_SEQUENCE_S` are enforced in `config.py` and
  mirrored into the editor — a bound only the UI knows is one a hand-edited
  file walks straight past. Over either, the list is **truncated with a
  warning**, never rejected. And it **holds the button**: presses made while it
  runs are dropped by the rule that already drops them during any other action.
- **A new action shape is resolved in `resolve_action`, not at each dispatch
  site.** Sequences reached all six sites without one of them being edited,
  because that function is where a binding becomes the thing that runs. *If a
  future shape needs unpacking, unpack it there.*
- **A reflex adds a source of events and no new vocabulary of consequences.**
  A reflex ([config.py](aibutton/config.py)'s `Reflex`, TODO 70/71) is *a
  circumstance with an action attached* — a standalone top-level object, not a
  field on a mode, because most reflexes start no app at all and a field could
  only ever say "this app starts now". `then` is any action the button already
  has (`REFLEX_ACTIONS`: the hook set plus `enter_mode`, which a hook may not
  have because a hook fires *beside* the run loop and a reflex is dispatched
  *by* it). So **a new source — MIDI in, OSC in, the media keys — puts a name
  on `main`'s inbound queue and stops there.** If adding one means adding a
  consequence, the consequence belongs in the action table where every other
  surface gets it too.
- **A reflex's test is one field, one operator, one number — and that is the
  whole language.** `REFLEX_OPS` in [config.py](aibutton/config.py) is the
  complete operator list, mirrored in schema.js. **The moment it grows an
  `and`, an `or` or a second condition it is an expression language, and an
  expression language cannot move onto the device** (ROADMAP D2) — which is
  the one thing this has to stay able to do. The matcher (`reflex_matches`) is
  **pure and called from exactly one place**, the run loop, so a later source
  (MIDI in, OSC in) applies the same test rather than growing a second answer;
  the endpoint carries the body and never reads it.
  Two behaviours worth not flipping: **a test whose field is missing does not
  fire** (firing on missing turns a renamed sensor field into an alarm that
  never stops), and **a broken test is dropped while its reflex is kept**
  (silencing it would make a typo look like a sensor that stopped reporting).
- **A source says which messages reach a reflex; the test says whether they
  fire it.** That split (TODO 73) is why MIDI in needed no comparison language
  of its own: `MidiSource` pins the port, the note-or-CC number and optionally
  the channel, the message becomes a **payload** (`velocity` and `value` are
  the same number under the two names a DAW uses), and `when` does the rest —
  *note 95 velocity 127* and *the same note at 0* are one source and two
  opposite tests. **A new source builds a payload and stops there.** Both
  halves are pure and live in [config.py](aibutton/config.py) (`reflex_hears`,
  `reflex_matches`), because the run loop is not a place a question about data
  can be tested.
- **A driver callback hands three bytes to the loop and does nothing else.**
  `asyncio.Queue.put_nowait` is not thread-safe and neither is reading the live
  config, so `main._on_midi` is one `loop.call_soon_threadsafe` and every
  decision happens in `_dispatch_midi` on the loop — the same discipline
  `ClockListener` documents for its ring of timestamps, one step stricter
  because this one wants the config. **And a MIDI input opens exclusively on
  Windows**: one listener per port, so a metronome following the clock on the
  port a reflex listens to falls back to tap-only and says so. Two ports is
  the answer; loopMIDI makes them free.
- **A number that arrived is logged whether or not it fired.** `handle_reflex`
  writes one row per *arrival* that carried a tested value, named after the
  reflex — so the Events page charts the sensor, not the alarm history, and
  the group-by-name rule below applies unchanged: one reflex reports one kind
  of number. No test means no row, because nothing to report costs nothing.
- **A circumstance is not a press, and never travels as one.** The run loop
  selects on two queues (`_wait_for_press_or_reflex`): the device's, and
  `inbound`. Injecting a synthetic press would work and would make every app's
  log a lie — a session summary would record a press nobody made.
  **A reflex is not dropped the way a press made while busy is**: a press
  whose moment has passed is noise, a plant that has gone dry still means it.
- **A reflex reaches a running app only by naming it** (`while`), and what it
  hands over is an action, not a keystroke. `wait_in_app` is the takeover's
  version of `_wait_for_trigger` (TODO 74): it returns a press, or a
  `SetPositionAction` when a reflex addressed to *this* app says where it should
  now be, and it runs anything else the reflex carries itself — an ordinary
  consequence the app has no opinion about, kept off the app's light.
  A reflex **not** addressed to the running app is *held* and put back when the
  button is handed over, so a system-wide reflex still fires, just after its
  turn. Held rather than requeued immediately, which would spin.
  *An app that wants to hear from the world adopts `wait_in_app`; one that
  does not simply keeps `_wait_for_trigger`, and reflexes wait for it.*
- **What the world reports is shown, not announced.** `run_signal` paints a
  reported position without firing that position's own action, the same rule
  entering a signal light already followed — and with a DAW it is stronger
  than politeness: sending "record" back to the thing that just told you it is
  recording is a feedback loop. **Derived state beats modelled state**
  (item 25): the position is a fact that arrived, never one the button
  inferred from its own presses.
- **A mode names a look; it never owns one.** The pool is `AppConfig.looks`
  and a mode holds `{state: look-name}`. Which states a mode may colour is
  `MODE_LED_STATES` in [config.py](aibutton/config.py), mirrored as
  `ledStates` on each template descriptor in
  [schema.js](aibutton/web/static/schema.js) —
  [test_webui.py](tests/test_webui.py) fails on drift. A mode that names
  nothing resolves to `None`, which is what `set_led` already means by "no
  override", so the palette stays the fallback and costs no wire traffic.
- **An app's page reads the store and never writes it.** A takeover's own page
  shows what that app has done ([appReadout.js](aibutton/web/static/appReadout.js),
  TODO 51), and everything on it is a *read*: rows through `/api/events`, plus
  the mode's config. Nothing it computes is written back and nothing the button
  does depends on it — the moment something here needs storing, that is item 34
  (app documents), not another view. Which rows an app owns is declared as
  `readout` on its template descriptor, so a new app that logs gets a history
  by adding four keys; one that adds a `log_as` field and no `readout` is
  caught by [test_app_readout.py](tests/test_app_readout.py), which also checks
  the `nameField` against the **real parser's** dataclass rather than a
  hand-written map.
- **`value` is one untyped column, so anything reading it groups by `name`.**
  A metronome's BPM, a reaction timer's milliseconds, a countdown's minutes and
  an alarm's 0/1 share that slot and nothing else. Every reader gives each name
  its **own scale** — `seriesByName` draws a panel per name rather than a chart
  with several series, and `READOUT_MEASURES` splits `outcome` from `value`
  precisely so 0s and 1s are counted rather than averaged. *Pooling them
  produces a chart that renders, looks fine, and is meaningless.*
- **Two rows can describe one session, and only one of them is the session.**
  A stopwatch writes both a `timer_stop` and the `mode_exit` that contained it.
  Anything summing durations takes `mode_exit` alone (`durationTotals`), or it
  double-counts exactly the app most likely to top the chart — plausibly, which
  is why it is pinned by a test rather than a comment.
- **The Events page's aggregations are pure and exported; the drawing is not.**
  Same split as [rules.py](aibutton/rules.py), for the same reason: every
  question worth getting wrong (which rows count, which double-count, what
  "today" means off UTC) is a function over data, checked against a table in
  [tests/js/](tests/js/). *New chart logic goes in the pure half or it cannot
  be tested at all.*
- **A chart is CSS unless geometry forbids it.** Text inside an SVG `viewBox`
  scales with the box, so an 11px label is 6px on a phone — unreadable rather
  than overflowing, which no overflow measurement catches. Bars, columns and
  the heatmap are flex and grid; SVG is kept for the donut arc and the
  sparklines, and **both keep every label in HTML around the plot**. Anything
  that cannot shrink past a point scrolls in its own `.scroll-x`, never
  dragging the panel sideways.
- **A field that decides whether an action does anything at all is not
  tinker-tier.** The `midi` action's port was hidden as an advanced option, so
  a control surface got configured five times with no port - and an empty port
  means *the first output on the machine*, which on Windows is the built-in
  synth. The DAW heard nothing, and nothing reported an error, because nothing
  had failed. *Tier hides detail, never the difference between working and
  silently going somewhere else.*
- **A group of fields is as hidden as its fields.** A settings group whose every
  field is `tier: 'tinker'` is itself tinker-tier, derived from the specs rather
  than declared — otherwise a basic user gets a heading with nothing under it,
  which is what the Device page's "Web server" did (TODO 47). *Derived, so a
  group that gains one basic field starts showing again on its own.*
- **A field edited as a textarea parses a string as well as a list.** The
  widget writes a newline-separated string; a parser accepting only a list
  turns a curated value into the default **on save**, with an error in the log
  and nothing in the UI. `targets` and `cues` both take either shape now, and
  that is the rule for the next list-shaped field.

### When you change the protocol

Not descriptions of today — rules for the next change, because the protocol
is the one surface that will exist in someone else's pocket.

- **Add, don't repurpose.** A byte that once meant something must never come
  to mean something else. There is no way to reflash a device you don't have.
- **Negotiate, don't assume.** `DEVICE_INFO` exists now (protocol v1): a read
  giving protocol version, firmware version and a capability bitmap. So
  **gate every new capability on a bit** rather than on a version number, and
  let an old device answer honestly instead of being assumed into working.
  `BLEDevice` re-reads it on every reconnect — the thing on the other end may
  have been reflashed since.
  - Capability bits report what *came up*, not what `hardware.py` asked for:
    the LED and buzzer both degrade to Null backends, and a bit claiming a
    buzzer nobody can hear is worse than no bit at all.
  - A device with no `DEVICE_INFO` falls back to `ASSUMED_INFO`, because the
    only firmware that predates it is ours and it has all three. Learning to
    ask must never silence a button nobody has reflashed.
- **Append, never insert.** `DEVICE_INFO` grows by adding fields on the end,
  and `decode_device_info` ignores trailing bytes it doesn't know. That is the
  half of forward compatibility the *host* owns, and it is what keeps a newer
  device readable by an older host.
- **Batch the breaks.** Protocol changes cost a reflash and a chance to drift
  the mirrored tables. Land them together, then freeze.
- **Protocol v1 is frozen.** `DEVICE_INFO`, ephemeral effects and
  parameterised gestures all shipped; `OTA_CONTROL` and `GESTURE_HOLD` are
  claimed and unimplemented. Everything below v1 needs is now reachable
  without a reflash, so the bar for the *next* wire change is a capability the
  device physically cannot express today — not a feature that would merely be
  tidier on the wire.
- **The host must read everything a device might send; the device sends the
  oldest form that will do.** That asymmetry is deliberate — the host is the
  half that is easy to update. So the classic three gestures still go out as
  one byte and always will, and only a gesture with no legacy code travels as
  `[kind, param]`. `decode_gesture` accepts both.
- **Cost that changes how the button feels is opt-in, and derived.**
  Counting to three taps is what stops a double tap firing on contact, so
  `max_taps` is written down the wire from what the config actually binds
  (`bound_triggers` → `max_taps_for`) rather than being a setting. A button
  with nothing longer than a double bound behaves exactly as it always has.

## Conventions

- Comments explain **why**, not what. The tricky ones here are hardware
  reality (WS2812 byte order, sticky download mode) and deliberate
  trade-offs (dropping presses while busy) — those are worth a sentence.
- **Two `def`s of the same name shadow silently, and Python says nothing.**
  `_parse_sequence` was the stop-list parser in
  [config.py](aibutton/config.py); adding an *action* called a sequence
  (TODO 33) took the name, and every named look began parsing to `None` - the
  web API answered 500 on a config that had been fine a minute earlier, with
  no error at the point of the mistake. The action one is
  `_parse_action_sequence` now, and
  [test_config.py](tests/test_config.py) fails on any module-level
  redefinition in the package. *A "sequence" here is a stop list; check the
  name is free before reusing the word.*
- **A ctypes callback must be kept alive by something Python can see.**
  [midi_io.py](aibutton/midi_io.py)'s clock listener parks its `WINFUNCTYPE`
  object on the closer it returns, because a driver calling a collected
  callback kills the process outright — illegal instruction, no traceback, no
  exception to catch. Closing over the object and then `del`-ing it inside the
  nested function is the trap: `del` makes the name *local to that function*,
  so the closure never captures it at all. It reads like tidy cleanup and it
  is the bug.
- **The JavaScript has tests now, and node is optional.** `node --test` is
  built in, so [tests/js/](tests/js/) costs no dependency;
  [test_js_modules.py](tests/test_js_modules.py) runs it and **skips with a
  reason** where node is absent, so a Python-only machine still goes green.
  The no-new-dependencies rule below is about what the *service* runs on.
  Only pure functions are tested there — anything touching the DOM is verified
  in a browser, which is the honest split rather than a gap. Pass node the
  **file**, not the directory: `node --test <dir>` resolves the path as a
  module on Windows and dies with `MODULE_NOT_FOUND`.
- **One home for a shared formatter.**
  [format.js](aibutton/web/static/format.js) holds how this page writes a
  duration, a number and a day, because each is shown in two places now (the
  Events table and an app's readout). Two copies of "how long is 3661 seconds"
  is a mirrored table with nothing testing it. *`schema.js`'s `fmtLength` is
  the deliberate exception and says why in its docstring* — a configured
  length ("25m") and an elapsed measurement ("8:41") round and abbreviate
  differently, and they shared a name until the editor bundle refused to hold
  two.
- Tests assert behaviour and name the scenario, not the method. Prefer one
  event-script table over many near-identical cases (see
  [test_trigger_port.py](tests/test_trigger_port.py)).
- No new runtime dependencies without a reason; the service runs on httpx,
  fastapi, uvicorn and bleak. The tray control panel adds **pystray** and
  **Pillow** — a tray icon has no stdlib equivalent on Windows, and its
  window is plain Tk. Those two are the control panel's alone: nothing in
  the service imports them, so a headless host still installs four.
  **The `midi` action is the worked example of not adding a fifth.** TODO 22
  decided to accept `python-rtmidi`; it turned out to publish no wheel for
  Python 3.14 and to fail its source build here, and the OS API underneath it
  (`winmm.dll`, via `ctypes`) did the whole job. Before taking a dependency for
  one action, check what the platform already has — and if you take one anyway,
  make it **optional at import** and leave it out of `requirements.txt`, so a
  machine that cannot install it loses that action and not the service.
- **`aibutton` is a provisional name.** It is descriptive and inaccurate —
  there is deliberately no AI on the device. A rename is coming
  (ROADMAP **D7**), so don't spread the string further than it already is:
  new user-facing text says "the button", and new identifiers don't embed it.
- **"Can anything reach this?" is a walk, and it lives in one pure function.**
  `reachableModes` ([schema.js](aibutton/web/static/schema.js)) starts from the
  things nobody has to start — a gesture map is live by definition, a clock
  starts its own apps — and follows `enter_mode` bindings and launcher lists
  from there. **It is transitive on purpose**: a launcher you cannot open
  cannot open anything either, so installing one nobody points at fixes
  nothing, and the App page says so. It resolves **named actions** on the way,
  which `findEntryPoints` never did. *A new way to open an app is an edge in
  that walk, or the App page will call working configs broken.*
- **A mount `menu.js` renders into may be absent, and that is the seam between
  the two shells.** `mounts.nav` and `mounts.apps` are both optional; a missing
  one means one section fewer, never a broken menu. **But absent is not the
  same as unnecessary** — removing the ready-made picker left the offline
  editor with no way to add an app at all, because its mount resolved to
  nothing and nobody noticed. *When a capability moves onto a new mount, give
  the offline editor that mount too rather than a second code path.*
- **The mode list is the page's navigation, and it lives in the shell.**
  `menu.js` renders it into `mounts.nav` (the side panel) and the mode editor
  into `mounts.modes`, and **`mounts.nav` is optional**: absent, the nav falls
  back inside the panel, which is the only reason the offline editor still
  works — it is the menu with no shell around it. Selecting a mode has to
  bring its editor up, and `menu.js` **asks** for that with a
  `button:show-panel` event rather than reaching for the shell's tab state.
  *A new destination in the nav is a listener on that event, not a second
  place that hides panels.*
- **Below 900px the shell stops being a fixed-height frame.** Two panes in a
  viewport is a desktop idea; stacked, a wrapped header plus a capped nav plus
  a wrapped scene bar left the work surface **zero pixels tall**, which looks
  exactly like the page failing to load and overflows nothing, so no
  measurement catches it. The narrow layout is an ordinary scrolling document
  instead: nav capped with its own scroller, panel flowing, save bar sticky.
  *Check panel height, not just overflow, when you touch the shell.*
- **An override at equal specificity must come after what it overrides.** This
  stylesheet has now lost that argument twice — `.inp` under its own variants
  (TODO 42) and `.tab-panel { position: static }` above `position: absolute`
  (TODO 45). Both failed **silently**, because a rule that loses still parses.
  *Put a media query below every rule it reaches into, and verify the computed
  value rather than assuming the cascade agreed with you.*
- **An action bound to something that is not a press is still a binding.**
  `on_timeout` (TODO 44) is offered by the same sub-editor as a gesture and a
  hook, through a **`bindings`** key on the template descriptor — not a
  `kind: 'action'` field widget, which would be a second way to edit the same
  thing. It offers `HOOK_ACTIONS` only, for the reason hooks do: `enter_mode`,
  `readout` and `standby` change what the mode *loop* does next, and there is
  no loop left to change once an app has finished. *A new non-gesture trigger
  declares a binding; it does not grow its own editor.*
- **Three words in the UI copy: a *menu*, an *app*, a *reflex*** (TODO 46,
  renamed by TODO 75). A menu is a press picking between things — the everyday
  gesture map, a launcher, a control page; an app takes the button over until
  you leave; a reflex fires with nobody pressing anything (`AppConfig.
  reflexes`, plus the apps a clock starts). The gesture that starts an app
  reads "Launch an app". **The word "reflex" moved once and must not move
  again**: it headed the gesture maps — the most *voluntary* thing on the page
  — until there was something involuntary to give it to.
  **The tokens did not move and must not**: `nature: 'takeover'` in schema.js
  mirrors `TAKEOVER_BEHAVIORS` in Python, `MENU_TEMPLATES` is UI-only grouping
  beside `MODE_GROUPS`, and the config key is still `modes` — renaming a
  mirrored value to improve a sentence is a drift risk taken for nothing,
  since no user ever reads it. "Mode" stays the umbrella noun in generic
  chrome, because a menu and an app are two kinds of one config object — and a
  reflex is *not* one, which is why it is a list of its own. *New copy uses
  the new words; comments and docstrings may keep the old ones where they
  describe code.*
- Firmware changes need a **reflash** before they mean anything. Firmware
  modules import each other by bare name and sit flat on the device.
- **Keep [TODO.md](TODO.md) current in the same commit as the work.** When an
  item ships, move it to **Done** and delete the scope the shipped version
  superseded — a "✔ shipped" banner above the original plan is how that file
  grew to 1600 lines of instructions nobody should follow any more. Two rules
  keep the pruning safe: a rule governing *future* code belongs here in
  CLAUDE.md and TODO.md only records the decision and points at it; and item
  numbers are never reused or renumbered, because this file, ROADMAP.md and
  the commit log all cite them.

## Hardware gotchas

- **ESP32-S3, USB-Serial/JTAG.** Entering download mode sets a sticky flag
  that survives a reset — after flashing, the board sits in the bootloader,
  silent, until you physically replug. It looks exactly like a bad flash.
- **WS2812 byte order varies by board, and this build's two LEDs disagree.**
  The ring is GRB, the onboard one is RGB (`NEOPIXEL_ORDER` /
  `ONBOARD_NEOPIXEL_ORDER` in [hardware.py](firmware/hardware.py)). Diagnose by
  pushing *known* colours from any colour picker's Diagnostic row
  ([colorEngine.js](aibutton/web/static/colorEngine.js)), never by watching
  the rainbow — every permutation of a rainbow is still a rainbow, so it shows
  at most a direction reversal and a camera's white balance will happily fake
  one of those. One LED wrong means that LED's setting is wrong; **both wrong
  the same way means the two settings are on the wrong LEDs**. Red, green, cyan
  and magenta are the colours that talk — blue, yellow and white are fixed
  points of an R/G swap and look perfect while it is broken.
- **The button's WS2812 runs on 3V3, and that is a trade, not a fix.** Its data
  threshold is ~0.7×VDD, so a 5 V-powered pixel driven by the S3's 3.3 V sits
  on the edge and fails as *flicker*, not as silence — the hardest failure here
  to read as wiring. 3V3 removes that and buys a colour fault instead: the red
  die runs at ~2 V and the green and blue dies at ~3.2 V, so on a 3.3 V rail
  only red keeps its current sink in regulation and white renders orange
  (measured R:G:B ≈ 1.00 : 0.54 : 0.44). Going to 5 V means handling the
  threshold as well — series diode or level shifter, never 5 V alone. TODO 0c.
- **`mpremote exec` interrupts `main.py`.** The board stops advertising until
  you `reset` it.
