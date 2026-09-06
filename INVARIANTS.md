# Invariants

Topic-specific rules that bind future code, split out of
[CLAUDE.md](CLAUDE.md) so a session that isn't touching a given subsystem
doesn't pay to read about it. The cross-cutting rules that apply regardless
of subsystem stayed in CLAUDE.md's own "Invariants" section — read that
first. A rule here binds exactly as hard as one in CLAUDE.md; it's filed
here for what it's about, not for how important it is.

## Colour & light

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
- **A mode's own "How it looks" is that same list, one row per owned state**
  (TODO 86). It used to be an always-expanded picker per state, which read as
  a wall of controls on anything owning two states and never collapsed on
  anything owning one. `modeEditor.js`'s `_renderLookStateRow` mirrors the
  Lights tab's row exactly — swatch, name, meaning, summary, Edit/Done, one
  open at a time — because it is the same question ("what does this state
  look like") asked in a shorter list, not a different control.
- **Single Color / Sequence / Preset are tabs on one editor, not a toggle plus
  a separate drawer.** `createLookEditor` used to offer the shape as two mini
  buttons and bury presets in a `<details>` above them — two controls for "how
  is this look specified," which is the thing CLAUDE.md's colour-control rule
  exists to prevent. Preset is a picker rather than a persisted shape:
  applying one switches to whichever of the other two tabs shows the result,
  so choosing never leaves you staring at an unrelated tab.
- **A sequence's timeline is proportion, not decoration.** The strip above a
  stop list's rows sizes each fade/hold segment with `flex-grow`/`flex-shrink`
  set to that stop's own number — the browser's layout arithmetic *is* the
  scaling, so it is exact under any `drive` (a share and a beat scale exactly
  like a second) and a zero-duration fade truly disappears rather than
  rendering as a sliver. Do not replace this with hand-rolled percentages;
  that is the rounding this design exists to avoid.
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
- **A position carries a colour only where nothing else can answer for it.**
  A signal light's positions carry theirs inline: the template owns no
  `LEDState`, so there is nothing else the colour could come from. A control
  surface's positions (TODO 77) **name a look from the pool**, because that
  template *does* own LISTENING, and a position carrying a colour beside a
  page that already has one is the two answers the rule below forbids. An
  unnamed look falls through to the page's own — `set_led`'s existing chain,
  not a new one. *A third template with positions asks which of those two it
  is before inventing a third.*
- **A mode names a look; it never owns one.** The pool is `AppConfig.looks`
  and a mode holds `{state: look-name}`. Which states a mode may colour is
  `MODE_LED_STATES` in [config.py](aibutton/config.py), mirrored as
  `ledStates` on each template descriptor in
  [schema.js](aibutton/web/static/schema.js) —
  [test_webui.py](tests/test_webui.py) fails on drift. A mode that names
  nothing resolves to `None`, which is what `set_led` already means by "no
  override", so the palette stays the fallback and costs no wire traffic.

## Actions, reflexes & documents

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
- **An app owns a document; the log owns the history.** A takeover may keep a
  small bag of named values ([documents.py](aibutton/documents.py), TODO 34) -
  the *current* value, which a log cannot answer without a scan and which
  "set this to 3" could not express at all. **Bounded by construction**: slots
  are declared per template (`DOC_SLOTS`, mirrored as `docSlots` in schema.js,
  the manifest's precursor), values are scalars, and `MAX_SLOTS` is the
  backstop for the reason `summary.MAX_KEYS` is one. **Both are written, never
  one** - a durable counter logs every press *and* moves its slot, so history,
  streaks and the Events page do not change when the flag is flipped. It is
  keyed by the mode's *name* because modes have no id yet, and the cost is
  stated in the module rather than hidden: a renamed app reads its default
  again. *An app that wants to remember something writes a document, not
  config* (ARCHITECTURE.md, "Who owns which truth").
- **A document lives outside every run loop, which is what `set_value` is
  for.** It is the third action family (ROADMAP 3d, **app-bound**): it names an
  app and writes one of that app's slots, so "Smoking +1" is bindable to a
  gesture in Home without entering the Counter (TODO 15). Ordinary
  fire-and-forget otherwise - no loop changed, no light owned - which is why it
  reached a gesture, a hook, a reflex and a sequence step by being added to one
  allow-list. *Deliberately not delivered to the running app the way
  `set_position` is*: a position is a thing only a running app can be in.
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
  Two have adopted it: the signal light and, since TODO 77, the control
  surface.
- **What the world reports is shown, not announced.** `run_signal` and
  `run_control` paint a reported position without firing that position's own
  action, the same rule entering a signal light already followed — and with a DAW it is stronger
  than politeness: sending "record" back to the thing that just told you it is
  recording is a feedback loop. **Derived state beats modelled state**
  (item 25): the position is a fact that arrived, never one the button
  inferred from its own presses.
- **An action bound to something that is not a press is still a binding.**
  The Notice template's `on_cleared`/`on_snoozed`/`on_missed` (TODO 44, TODO
  84 — `on_timeout` under its old, alarm-only name) are offered by the same
  sub-editor as a gesture and a hook, through a **`bindings`** key on the
  template descriptor — not a `kind: 'action'` field widget, which would be a
  second way to edit the same thing. It offers `HOOK_ACTIONS` only, for the
  reason hooks do: `enter_mode`, `readout` and `standby` change what the mode
  *loop* does next, and there is no loop left to change once an app has
  finished. *A new non-gesture trigger declares a binding; it does not grow
  its own editor.*

## The nav & shell

- **A nav row's line has two halves, and only the first is guaranteed.** What
  an item *is* comes from the config and is written synchronously; what it has
  *done* comes from `/api/events/summary` and arrives later or never (TODO
  101). One request for the whole list, not one per row — the nav re-renders on
  every keystroke that changes the model. The degradation is the API surface
  itself: `FileApi` has no `eventSummary`, so the offline editor never asks and
  every row keeps its config half. *A live number in a list is fetched once for
  the list, or it is a request per keystroke.*
- **A `better` is a fact about an app, never a guess about its user.** Most
  readout descriptors set `better: null` and that is a decision: the same
  stopwatch times a mile run, where quicker is better, and a cake, where it is
  not. So the nav shows a best only where the descriptor declares one.
  *Adding `better` to a template to make one row read nicer prints a judgement
  the config never made, on every item of that kind.*
- **A control that can throw away the page it is on does not get a
  confirmation, it gets removed.** "What it does" was a `<select>` that swapped
  a mode's whole body, discarding every field the old template owned — and it
  looked like a label (TODO 87). Once the nav groups items under the app they
  belong to, an item's template *is* which group it lives in, so changing it
  means moving it and a dropdown that silently rehomes a row is describing
  something the rest of the page no longer believes. Changing type is
  delete-and-add, which is what it always was underneath. **Say so where the
  control used to be**: a door people used, removed in silence, is how a page
  earns a bug report.
- **A list of usages and a list of things to rewrite are one list.** The
  action pool's rename walked a hand-written set of places — gestures, and a
  signal light's positions — and quietly missed hooks, a Notice's outcomes, a
  reaction's `then` and every step of a sequence, so renaming from the editor
  could dangle exactly the references the parser then warns about.
  `actionRefs` is the single walk both callers use, and a template's
  `bindings` key joins it for free. *A new place a binding can live is a case
  in that walk, or renaming will half-work.*
- **A nav row says what a thing *is* by its group and what *starts it* by its
  glyph — and nothing is listed twice.** A scheduled alarm used to appear under
  Apps *and* under Reflexes, deliberately (TODO 48a): the groups are questions,
  not boxes, and it answered two. `startedBy` answers the second **on the row**
  (TODO 101), which is strictly better — one line says both, and the list is
  shorter by every scheduled app you own. It is a render of `reachableModes`,
  so the fourth answer, **"nothing starts this"**, comes free and is the
  valuable one: an app you can configure and never reach is a bug in a config
  and was previously reported only in prose on a page you had to go to.
  *A new way to open an app is an edge in that walk (it already was) and a
  case in `startedBy`, or the glyph will call a working config broken.*
- **A template descriptor's `describe` says what distinguishes an item from its
  siblings, never what the template is.** The nav already says "Stopwatch" as a
  heading, so a row reading `Stopwatch “mile run”` spent its only line
  repeating what the reader had just been told (TODO 101). A caller that needs
  the kind as well prefixes `label` itself — which the `enter_mode` picker
  does — so there is still exactly one description per mode. *A `describe` that
  starts with its own template's name is the bug this rule exists for.*
- **Lights holds the look pool; Actions holds the action pool and the reactions
  made from it.** Two nav destinations with the same shape, and the pairing in
  the second is the argument (TODO 102): a reaction is a circumstance with an
  action attached, and its entire vocabulary of consequences *is* that pool, so
  one is the ingredient list for the other. Both mounts are **optional**, like
  `nav` and `apps` — absent, the pools fall back into the Modes panel rather
  than disappearing. *And the offline editor is given each new mount rather
  than the fallback*, which is the rule below about `mounts` restated: a
  capability that lands on a mount that shell lacks is one that shell silently
  loses.
- **A fallback may degrade a capability; it may never invent a
  classification.** `menu.js` answered `'ambient'` for a template it had no
  descriptor for — "the harmless default: they answer gestures" — and the nav
  files everything ambient under **Menus**. So a browser running a stale
  `/static` module graph against a newer config put every scheduled Notice
  under Menus, where it read as a gesture map somebody had mis-added: a wrong
  answer, stated confidently, on a page whose whole job is to say what the
  button will do (TODO 107). `_natureOf` answers `'unknown'` now and the nav
  has a fourth group that says the page is behind. *The shape to copy is
  `ASSUMED_INFO`'s, not this one's: that fallback assumes a capability a
  device certainly has, which is a degradation. Guessing which **kind** of
  thing something is is not.*
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

## Config, warnings & fields

- **A warning carries where it came from, and the sentence stays
  authoritative.** `parse_with_details` (TODO 62) answers with
  `ParseWarning(message, mode, key)` beside the plain strings, so the editor
  marks the field instead of printing into a banner the next Save overwrites.
  The location is read from the **log record's first argument**, never parsed
  back out of the rendered message - every parser call passes `where` first,
  which makes it a lookup rather than a guess. **A warning it cannot place is
  not dropped**: `mode` is None, the field goes unmarked, and the Save bar
  prints it exactly as it always did. *Add a warning by logging `where` first,
  and it places itself.*
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

## Readout & events

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
- **Which end is "best" is the item's answer, and it is read through one
  function.** Most templates set `readout.better: null`, because "fastest" is
  a fact about a reaction timer and a guess about a stopwatch — the same
  template times a mile run and a loaf of bread (TODO 109). A mode may override
  it (`Mode.better`, `MODE_BETTER`, mirrored in schema.js), and every reader
  goes through `betterFor(mode, readout)` rather than off the descriptor, or
  the override is silently ignored on whichever page forgot. The field is
  offered by exactly the templates that would *read* it — `duration` and
  `value` measures whose descriptor declines to answer — and
  [test_schema_mirror.py](tests/test_schema_mirror.py) derives that set rather
  than listing it, so a new timing app either offers the choice or fails.
- **Anything a row shows twice — as a number and as a colour — stays a number
  until the last moment.** A readout's delta arrived at `measuredRow` already
  formatted, so the good/bad test compared `"-0:02"` with `0`: NaN, false, and
  therefore *every* reaction attempt painted worse and every Hot/Cold guess
  painted better, whichever way the number had actually gone. It rendered
  perfectly and had no failing test, because the wrong half is a CSS class.
  *Pass the value and the formatter, not the string.*
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

## Small gotchas

- **A ctypes callback must be kept alive by something Python can see.**
  [midi_io.py](aibutton/midi_io.py)'s clock listener parks its `WINFUNCTYPE`
  object on the closer it returns, because a driver calling a collected
  callback kills the process outright — illegal instruction, no traceback, no
  exception to catch. Closing over the object and then `del`-ing it inside the
  nested function is the trap: `del` makes the name *local to that function*,
  so the closure never captures it at all. It reads like tidy cleanup and it
  is the bug.
- **One home for a shared formatter.**
  [format.js](aibutton/web/static/format.js) holds how this page writes a
  duration, a number and a day, because each is shown in two places now (the
  Events table and an app's readout). Two copies of "how long is 3661 seconds"
  is a mirrored table with nothing testing it. *`schema.js`'s `fmtLength` is
  the deliberate exception and says why in its docstring* — a configured
  length ("25m") and an elapsed measurement ("8:41") round and abbreviate
  differently, and they shared a name until the editor bundle refused to hold
  two.

## Hardware

- **ESP32-S3, USB-Serial/JTAG.** Entering download mode sets a sticky flag
  that survives a reset — after flashing, the board sits in the bootloader,
  silent, until you physically replug. It looks exactly like a bad flash.
- **The board's BOOT button is a second button input, always on** (firmware
  0.8.0, TODO 89): `hardware.BOOT_BUTTON_PIN` is polled beside `BUTTON_PIN`
  and ORed *before* the debounce, so the two are one button and a press can
  move between them mid-hold. It exists so a board whose switch is unsoldered
  or broken is still pressable — which is the state this project was in the
  day it was written. **The strapping-pin caveat is about pressing it, not
  reading it**: GPIO0 held low at power-on is download mode, so press it while
  the board runs and never while it starts. A new optional `hardware.py` name
  is read with `getattr` and a default, like `NEOPIXEL_ORDER` — that file is
  the one people edit and carry forward, and an `AttributeError` at startup on
  a headless board is a dead board.
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
