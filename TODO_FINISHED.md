# Finished

Everything here shipped completely — nothing was left open under its number
when it moved. This is where [TODO.md](TODO.md) sends a finished item so the
live list stays a list of what's still to do; see TODO.md's "How to work this
list" for the rule. Item numbers are never reused or renumbered, so a number
you're looking for and can't find in TODO.md is almost always here.

**This file has no split yet because nothing has needed one** — it reads
start to finish only when someone is hunting a specific number, never as a
whole. If it passes roughly 4000 lines, split it by ROADMAP stage or by
rough date rather than letting a second copy of TODO.md's old problem grow
back here; until then, one file is simpler and costs nothing extra to keep.

## Shipped items, in full

### 70. Reflexes — a circumstance, with an action attached

**Asked for 2026-08-26, and named by the owner: these are reflexes.** Not
signals, not triggers — and the word is load-bearing rather than decorative,
because it says what the thing *is*. A reflex is **a circumstance or event with
an action attached to it**, and the button acts on it without anyone pressing
anything.

**This is not a new architecture. It is the host-side half of one already
decided.** [ARCHITECTURE.md](ARCHITECTURE.md)'s app runtime lists its event
kinds as *"gesture · timer expiry · schedule fire · sync reply · **sensor**"*,
and `Request` is described as answering "with an **event** the app can
transition on". Inbound events are in the target design; nothing has ever
produced one. ROADMAP's Stage 6 table says "sensors as activations, same slot
as geofencing" in three separate rows, **and there is no such slot.** This
builds it, on the host, years before any of that hardware.

**Worked examples, the owner's own:** a plant's moisture sensor crossing a
threshold rings an alarm; a DAW reporting that it has started recording changes
what the light does (**77**); a script on the PC starts an app; media
play/pause moves the button into a transport page (**79**).

#### The decision this settles: a reflex is an object, not a field

**ROADMAP D10 is answered, and the owner's definition is what answers it.**
The earlier draft of this item made an inbound event a new *activation type* —
a field on a mode, beside `schedule`. That was wrong, and the reason is in the
word "reflex": *most reflexes do not start an app at all.* "When the DAW starts
recording, make the light pulse red" enters no mode, logs nothing, and has no
mode to be a field on. A field can only ever express "this app starts now",
which is one of the things reflexes do and not the interesting one.

So a reflex is a standalone object:

```
when    a circumstance — an arriving event, optionally with a test on it
then    an action — any action the button already has
```

**And `then` being "any action the button already has" is the whole economy of
this item.** `resolve_action` and `actions.execute()` already exist; a reflex
firing `enter_mode` covers everything the activation-field design could do, and
a reflex firing `osc`, `webhook`, `midi` or a **named action from the pool**
covers everything it could not. Adding reflexes adds a source of events and
**no new vocabulary of consequences.**

**Scope: system-wide by default, app-scoped by exception.** The owner's read is
right — most reflexes are about the button and the world, not about one app. So
`reflexes` is a top-level list. An optional `while: <app name>` limits one to
the times that app is open, which is what **77**'s transport lights want and
what stops a DAW reflex repainting the light in the middle of a Pomodoro.

#### Where a circumstance comes from

Ranked, and the ranking is the recommendation:

1. **HTTP — `POST /api/reflex/{name}`.** ✔ **71**, 2026-08-27. Near-zero code,
   and it **subsumed almost everything**: anything that can make a request
   drives the button, so the plant sensor, a cron job, Home Assistant, an
   iPhone Shortcut (**39**) and any script arrive through one hole.
2. **MIDI in** (**73**). ✔ 2026-08-27, and it is what item 25 had been waiting
   for. `ClockListener` was reused rather than doubled: the backends hand over
   all three bytes now and it reads the first.
3. **OSC in**, the mirror of the `osc` action. Cheap.
4. **OS media transport** (**79**) — possible, with caveats worth reading
   before promising it.
5. **MQTT** is the home-automation lingua franca and the one that costs a
   dependency. **Not now** — a bridge posting to (1) is five lines, and the
   `midi` precedent in CLAUDE.md says check what the platform already has
   before taking a dependency for one feature.

#### What does *not* change

**Schedules stay where they are.** An alarm at 07:00 is a circumstance with an
action attached and is therefore a reflex by this definition — and migrating
`ScheduleActivation` into the reflex list would rewrite every config and scene
for no new capability. The line to hold: **an activation says when an app may
run; a reflex says what makes something happen.** An alarm's time is a property
of that alarm, the way its message is. A reflex is for what a schedule cannot
express — which is everything not on a clock, and every consequence that is not
"start this app".

There is real overlap and it is accepted knowingly. *Do not add a clock source
to reflexes until something wants one an alarm cannot do.*

**Split into build items 71–74, plus 77–79. Do not build the umbrella.**
(**71**, **72** and **74** are done; the rest still hold.)

### 81. The scene bar belongs with the other view toggles

**The scene picker is chrome, and it sits where the work is.** It is a full
row above the panel — a select, six buttons, and a message line — permanently
occupying the top of every page for a control most people touch once a month.

Put it behind a toggle in the header cluster beside **Tips**, **Tinker** and
**Press the button**, which is where this page already keeps "things that
change what you can see". It is the same shape as the Test panel's popover
(**48c**): a button that opens it, Escape and an outside click that close it.

Files: [index.html](aibutton/web/index.html) (`#scene-bar`, `.scene-bar`, the
header cluster), [menu.js](aibutton/web/static/menu.js)'s `mounts.scenes`.

**Watch the mount rule.** `mounts.scenes` is optional exactly like `nav` and
`apps`, and the offline editor has no scenes at all. Moving the mount must not
make the bar's *absence* an error, and the toggle must not appear where there
is nothing behind it.

**Done when**: the scene row is not on screen until asked for, the toggle
reads as one of the header set, and the offline editor is unchanged.

**Shipped 2026-08-29.** `#scene-bar` stayed exactly where menu.js's
`mounts.scenes` looks for it, now nested inside a new `#scene-pop` popover
(reusing `.dash-pop`'s look, anchored to the opposite side so it can't stack
under the Test panel's) toggled by a new `#scene-toggle` button beside Tips /
Tinker / Test panel. Open/close is a new tiny module,
[scenePop.js](aibutton/web/static/scenePop.js), mirroring
[sidepane.js](aibutton/web/static/sidepane.js) line for line - same
Escape/outside-click/re-focus behaviour, same "served-page only" note, since
the offline editor has no scenes and never loads this file. Verified live
against the running service: the toggle opens/closes the popover correctly
and the offline editor (`tools/editor_shell.html`) was not touched.

### 82. The "Manage apps →" button is a second door to one room

The nav's footer has **+ Add menu** and **Manage apps →**; the latter fires
`button:show-panel` at the `apps` tab, which is the tab already listed above
it. Two controls, one destination.

**Read [CLAUDE.md](CLAUDE.md)'s mount rule before removing it** — this exact
button is what that rule was written about. Taking the ready-made picker off
its old mount left the *offline editor* with no way to add an app at all,
because its mount resolved to nothing and nobody noticed. The offline editor
has no tab strip, so **the Apps tab is not a replacement there**.

So the shape is: drop it where the tab exists, keep a way in where it does
not, and check `dist/button-editor.html` rather than assuming.

**Done when**: the service's editor has one way to reach Apps, the offline
editor can still add one, and `tools/build_editor.py`'s output is opened and
looked at.

**Shipped 2026-08-29 - the trap had already been fixed by the time this ran.**
`tools/editor_shell.html` turned out to already have its own `.tab-bar`
including an **Apps** tab and its own `mounts.apps` (`editor-apps`), added
somewhere in the App-page work (48/49/51) after this item was written and
before it was picked up - so `dist/button-editor.html` was opened and looked
at exactly as asked, and both shells now reach Apps the same way. The button
was removed from [menu.js](aibutton/web/static/menu.js)'s `_renderModesLayout`
(the `manage` button and its half of `.add-row`), and the four places in
[README.md](README.md) and [MANUAL.md](MANUAL.md) that told someone to click
it - including MANUAL's own mode-list mockup, which was missing the **Apps**
top-nav item in its ASCII art despite the prose two paragraphs above it saying
there are four - were reworded to point at the Apps tab directly.

### 84. One "Notice" app — alarm, reminder and dead man's switch are one machine — shipped 2026-08-29

**Asked 2026-08-29, and it is right.** *"At a certain time the light goes off.
The user decides whether it clears itself, whether snooze is available, and
what happens when it is cleared, snoozed or missed."* That is one template
with three settings, and we ship it as two templates and a preset.

What is actually different today:

| | Alarm | Reminder |
|---|---|---|
| Persistence | rings until answered | gives up after `timeout_minutes` |
| Snooze | `snooze_minutes` | none |
| Cleared | `dismiss_event` (a log *name*) | `cleared_event` (a log *name*) |
| Unanswered | `on_timeout` (an *action*) | nothing |

So: one `NoticeBehavior` whose persistence is a setting, whose snooze is a
number where 0 means none, and whose three outcomes — **cleared, snoozed,
missed** — each bind an action from `HOOK_ACTIONS`. That last part is the real
gain, and it is a generalisation rather than an addition: two of the four rows
above are log *names* where an action would have done, and `log` is an action.

**Migration is not optional and not hard.** `alarm` and `reminders` stay
accepted template names that parse into `NoticeBehavior`, exactly as `rules`
and `commands` still migrate. A config written last week must load and behave
identically; that is the whole test.

Knock-on: `MODE_LED_STATES` (both already own `ALERT`, so the merge is free),
`TAKEOVER_BEHAVIORS`, schema.js's template plus `MENU_TEMPLATES`, the readout
descriptor, and **the three presets that make the difference findable** —
*Alarm*, *Reminder* and *Dead man's switch* become `BUILTIN_MODES` entries
over one template, which is the direction "prefer a preset to a template"
points. Template count goes 12 → 11 and the vocabulary gets smaller, which is
the point.

**Done when**: one template, three presets, every existing alarm and reminder
config loads unchanged, and the three outcomes take actions.

#### Shipped 2026-08-29 — two decisions made along the way, not in the original note

**Outcome logging became unconditional, at the owner's direction.** The note
above says the three outcomes "each bind an action from `HOOK_ACTIONS`" as a
generalisation of the old `dismiss_event`/`cleared_event` log-name fields.
Asked to confirm the exact mechanics (a `value`-carrying log action, to
preserve the dead-man's-switch "answered 6 of the last 7" readout), the owner
reframed it: cleared and missed should log **regardless of what the user
configures** - no opt-in field to remember. So `NoticeBehavior.log_as` is
required and always logs 1 (cleared) / 0 (missed), the same convention every
other template's own log name already follows; `on_cleared`, `on_snoozed` and
`on_missed` are *additional* actions layered on top of that log, not the
thing carrying it. A config that already named its event (`dismiss_event`/
`cleared_event`) keeps that exact name on migration; one that didn't gets the
mode's own name, which is what "log it with the alarm's name" meant for a
mode nobody configured this on.

**`urgent` is a field the original note didn't name, and turned out not to be
optional.** The two old templates never shared a name for "loop the alarm
tone and hard-flash" vs "chime once and breathe gently" - it was simply which
template you were in. Deriving it from `timeout_minutes` (persistent =
urgent) was considered and rejected: an old reminder set to "wait forever"
(`timeout_minutes: 0`, a real, supported setting) must keep breathing gently
forever, not start ringing just because persistence now reads the same as an
alarm's. So `urgent` is its own field, fixed by the parser to `True` when
migrating `alarm` and `False` when migrating `reminders`, regardless of any
other field's value - a fact about which template a mode used to be, not
something the migration infers.

One parser-time warning changed shape rather than disappearing: "sets
`grace_minutes`/timeout but no action - nothing will happen if unanswered"
stopped being true (something *always* happens now, a logged 0) and was
dropped; "sets an action but the timeout is 0 - it will never fire" survived,
renamed to the new field names, because an action that can structurally never
run is still worth a warning regardless of what else changed.

**Filed separately rather than folded in**: the owner also raised "fire on
reconnect if a scheduled window was missed while the button/service was
offline" - see the new item below. It is a real, related gap, but a scheduler/
offline-semantics problem rather than a template-merge one, and was
deliberately scoped out of this item to keep the merge itself reviewable.

Touched: `config.py` (`NoticeBehavior` replaces `AlarmBehavior`/
`ReminderBehavior`; `_parse_notice_body` replaces `_parse_alarm_body`/
`_parse_reminder_body` and is the migration path; `_ALLOWED_ACTIVATIONS`,
`MODE_LED_STATES`, `Behavior`, `_mode_to_dict`), `main.py` (`ring_notice`
replaces `ring_alarm`/`run_reminder`; `fire_alarm`, `enter_takeover`,
`TAKEOVER_BEHAVIORS`, `run_countdown`'s ring-on-finish all collapse to one
call each), `scheduler.py` (`SCHEDULED_BEHAVIORS`), `schema.js` (`notice`
template replaces `alarm`/`reminders`; `TAKEOVER_TEMPLATES`; the `enter_mode`
target picker no longer excludes gentle notices, since `ring_notice` handles
either style now; `BUILTIN_MODES` gained `alarm` and `reminder` presets and
updated `deadman`/`alarm5am`). Verified against the real parser directly
(migration, round-trip idempotency, both new warnings) rather than by running
the suite, per this project's standing rule; `tests/test_config.py`,
`tests/test_reminders.py`, `tests/test_dead_man_switch.py`,
`tests/test_scheduler.py`, `tests/test_rules.py` and `tests/test_webui.py`
were updated to match (the last one's `MODE_LED_STATES`/schema.js mirror test
now excludes the two migrated aliases by name, since they exist in Python for
`_parse_mode_looks` but deliberately have no schema.js descriptor of their
own).

### 85. A mode's sections collapse, and open themselves when they matter

**How it looks**, **What it does**, **When it's on** and **Around the
session** are four always-open blocks, and on a simple app three of them say
nothing you chose. Make them expandable, **collapsed when they hold nothing
but defaults** and open otherwise, so the page's shape tells you where you
have been.

"Nothing but defaults" is a comparison against the template's `defaults()`,
which already exists and is already the seed for a new mode — so this is a
diff, not a new declaration. A section with a validation error opens
regardless, and so does one carrying a parser warning (**62**), or the mark
lands somewhere nobody can see.

Files: [modeEditor.js](aibutton/web/static/modeEditor.js) (`_looksPicker`,
`_templatePicker`, `_activationPicker`, `_hooks`),
[index.html](aibutton/web/index.html) for the disclosure styling.

**Done when**: a freshly added app shows one open section, an app you have
configured opens the parts you touched, and nothing is ever hidden while it is
complaining.

**Shipped 2026-08-29.** One judgment call made along the way, worth recording
rather than re-litigating: **"What it does" always starts open**, unconditionally,
rather than being diffed against `defaults()` like the other three. A freshly
added mode's template fields are often *already* what `defaults()` returns
(a fresh "+ Add menu" mode's `short_press` literally is
`TEMPLATE_BY_TYPE.actions.defaults()`), so diffing that section the same way
the other three are diffed would have closed all four on a brand new mode -
zero open sections, not "one". "What it does" is also the reason you opened
this app's page at all (the point TODO 87 makes about the select inside it),
so it stays open by construction instead.

The other three each got their own diff, all against real seed values so
"untouched" means the same thing everywhere:

- **How it looks** opens when `mode.looks` names anything - `_looksDefaultOpen`.
- **When it's on** opens when the activation differs from
  `ACTIVATION_BY_TYPE[type].defaults()` (`JSON.stringify` compare, since both
  sides are built the same seeded way) - `_activationDefaultOpen`.
- **Around the session** opens when a `MODE_HOOKS` key is actually bound -
  `_hooksDefaultOpen`. It also moved its `data-tier="tinker"` from the inner
  content div to the `<details>` itself, so the whole section disappears as
  one unit when Tinker is off rather than leaving an empty heading behind.

A new `_section(label, contentEl, defaultOpen, {tinker})` wraps each in a
plain `<details>`/`<summary>` (no new widget - the same idiom
[colorEngine.js](aibutton/web/static/colorEngine.js)'s preset and fallback
drawers already used) and skips wrapping anything that arrives `.hidden`
(an ambient mode's "How it looks", an everyday mode's hooks) - a `<details>`
around nothing would still be a control that does nothing.

**"Opens regardless while complaining" is a sweep, not a second bookkeeping
structure.** `_openSectionsWithProblems()` walks every section built this
render and force-opens any whose subtree holds a `.fld-warn` or a non-empty
`.fld-err` - both of which are DOM state a parser-warning paint or a client
validator already leaves behind as a side effect, so there is nothing new to
keep in sync. Called from `_paintWarnings()` (parser warnings) and from
`validate()` (client-side checks, which populate `.fld-err` as a side effect
of running). Verified directly: a synthetic `.fld-err`/`.fld-warn` injected
into a closed section's DOM and swept flips `.open` to `true` in both cases.

### 86. "How it looks" reads oddly inside an app — scoped and shipped 2026-08-29

**The owner supplied the scope directly, mid-session, with a concrete design**
rather than the one-sentence complaint this item originally asked for: make an
app's "How it looks" match the **Lights** tab — a short list of state rows,
each with a swatch/summary and an **Edit** button, instead of the
always-expanded picker it was. Built the same session, in `_looksPicker()`
([modeEditor.js](aibutton/web/static/modeEditor.js)):

- **A row per owned state, collapsed by default, one open at a time** —
  `_renderLookStateRow`/`_renderLooksPicker`, mirroring menu.js's own
  `_renderStateRow`/`_expandedState`, down to the same CSS classes
  (`.look-entry`, `.look-line`, `.palette-*`) so it reads as the same kind of
  list. The underlying model is unchanged: a state still only ever *names* a
  pool look (`mode.looks[key]`) or falls back to the palette — this is
  presentation, not a new way to colour a mode.
- **"Edit" opens straight into the pool look's own colour sequencer**, not a
  second screen — the existing inline `createLookEditor(..., allowSequence:
  true)` moved into the row's body unchanged, so it inherited the tab and
  timeline work below for free.
- **Both candidates the item flagged turned out fine as they stood**: a
  template owning no LED state already hides the whole block
  (`states.length` guard, untouched), and the "which picker is work, which is
  rest" ambiguity is answered by the row itself — `state.label` +
  `state.meaning` name each one (e.g. "Pomodoro working — a work block is
  running" / "Pomodoro resting — a break is running").

**Done.** The two colorEngine.js changes below (tabs, timeline) shipped in the
same pass, since the redesigned row is what surfaces them on an app's page.

### colorEngine.js — tabs instead of a toggle + drawer, and a sequence timeline

**Asked alongside 86, 2026-08-29.** Two changes to `createLookEditor()`,
used everywhere a colour is chosen (CLAUDE.md's "one colour control" rule),
so both land on the Lights tab's system states, its Named-looks pool, *and*
every app's "How it looks" row at once:

- **Single Color / Sequence / Preset are tabs now**, replacing the old
  2-button shape toggle plus the separate "Start from a preset" `<details>`
  drawer the owner called visual clutter. Sequence is offered only where
  `allowSequence` allows the shape at all (system palette rows still can't);
  Preset is a picker, not a persisted shape — applying one switches to
  whichever of the other two tabs shows the result.
- **A proportional timeline bar** sits above the stop rows in the Sequence
  tab: one segment per fade-then-hold, sized by `flex-grow`/`flex-shrink` set
  to the stop's own `fade_s`/`hold_s` — exact ratios from the browser's own
  layout math, no percentage rounded by hand, and a zero-duration fade
  collapses to nothing rather than a sliver. Works under any `drive`
  (clock/progress/beats) since it reads proportions of the typed numbers, not
  wall-clock time.

**Done.**

### 87. "What it does" is the one control that can destroy the page it is on

**Asked 2026-08-29, and the reasoning is sound:** you reached this page *by
opening this app*, so a select that says "what it does" is redundant with
where you are — and it is not merely redundant. Changing it swaps the whole
template body, which discards every field the old template owned. It is the
only control on the page that can throw your work away, and it looks like a
label.

Options, and **the middle one is the recommendation**:

- Remove the select, keep the fields, and title the section with the app's own
  type ("Stopwatch settings"). Changing type becomes delete-and-add, which is
  what it already is underneath.
- Keep it, move it behind **Tinker**, and confirm before swapping. Cheapest,
  and it keeps a door that is genuinely useful when a mode was added from the
  wrong preset.
- Leave it and rename the section. Does not address the destruction.

**Read 88 first.** If the nav groups by app, then an item's template is
decided by *which group it lives in*, and changing it means moving it — at
which point this select is not just risky but wrong, and the first option
becomes the only coherent one.

**Done when**: the template of an existing mode cannot be changed by accident,
and the section's heading names the app rather than asking what it is.

#### Shipped 2026-08-29 - option one, as 88 predicted

The `<select>` is gone rather than confirmed. Once **101** made the nav group
items under the app they belong to, an item's template *is* which group it
lives in, so a dropdown that silently rehomes a row is describing something the
rest of the page no longer believes - the reasoning this item recorded in
advance, and it held.

The section is headed **"Stopwatch settings"** (`_templateHeading`, falling back
to the old wording for a template this page does not know - TODO 107's rule one
layer along), the template's `about` sits where the select was, and one hint
says changing type is delete-and-add. **That line is the whole replacement, and
it is not optional**: a door people used, removed in silence, is how a page
earns a bug report. `_switchTemplate` had exactly one caller and went with it.

### 88. The nav is a tree: apps hold their items, and an app is not renamable

**Absorbed by 101 on 2026-08-29 - build it there, not here.** Everything
below is still the right design and 101 contains all of it; what 101 adds is
the answer to the question this item left open, which is what the *rows* say
once the headings stop being editable names.

**Asked 2026-08-29.** *"I can rename Stopwatch. I want to create and name
iterations of the stopwatch, not rename the app. The side menu should show
`Intervals` with `Pomodoro` underneath."*

```
Apps
  Stopwatch    SW_1_Running · SW_2_Swimming
  Notice       morningalarm · medsreminder · textmywifeiloveher
  Intervals    Pomodoro
```

**This is presentation, and that is the whole reason it is cheap.** Item
**48b** parked the same-shaped idea and parked it *on a measurement*: every
runtime consumer of `modes` is flat — `bound_triggers` scans, `rules.resolve`
walks in priority order, `due_alarm` scans, `enter_mode` resolves by name — so
nesting the **config** would be flattened again at nine call sites. None of
that applies to a nav that groups a flat list by `template` for display.
*Keep it that way*: group in the view, leave `modes` alone, and 48b stays
parked with its reasoning intact.

Three parts:

- **Group by template**, with the template's `label` as the heading — a name
  that comes from schema.js and therefore cannot be edited, which is exactly
  the property being asked for. `_siblings()` already computes this set ("In
  this app"); this is the same fact in the nav.
- **Collapsible**, remembered per browser through [prefs.js](aibutton/web/static/prefs.js)
  like Tips and Tinker. A group with one item still shows its heading, or the
  hierarchy appears and disappears depending on how many stopwatches you own.
- **An item's own name stays editable**; the group's never was a name. Note
  that today an *item* called "Stopwatch" is just a mode that happens to be
  named that — nothing is lost, the heading simply stops being that string.

**One thing to decide while building it**: a mode's name is currently its
identity everywhere — `enter_mode` targets, `while` scopes, launcher
`targets`, and now a document's key (**34**). Grouping changes none of that
and must not start to.

**Done when**: the nav shows one heading per app kind with the user's items
under it, headings collapse and remember, and no heading is an editable field.

### 92. `scenes/default.json` is a shipped artefact, not a scratchpad

**Decided by the owner 2026-08-29:** the file in git *is* the default, and
personal setups go in their own scene alongside it.

That makes it a thing with a standard rather than a thing that drifts: it
should demonstrate the button rather than reflect whoever edited it last, and
every change to it is a change to what a new user opens.

The work: read what is in there now against that standard, decide what a
shipped default should contain, and put anything personal in its own file.
Worth deciding at the same time whether `scenes/*.json` other than the default
should be **gitignored**, because "personal scenes live beside the shipped
one" and "the scenes directory is tracked" only coexist if the rule is
written down.

**Low-hanging, and the only one in this batch.** Mostly a decision and a tidy.

**Done when**: `scenes/default.json` is a curated default, the rule about
personal scenes is in [README.md](README.md), and `.gitignore` agrees with it.

#### Attempted 2026-08-29 — the file, .gitignore and config.json all moved; the curated content did not stick

The owner's own live setup (Stopwatch, Pomodoro, Metronome, Counter, Alarm,
Countdown 60s, Action Menu, DAW Control, Light show) moved verbatim to the new
`scenes/personal.json`, `config.json`'s `scenes.active` was repointed at it,
[.gitignore](.gitignore) picked up `scenes/*.json` / `!scenes/default.json`,
and a small curated `scenes/default.json` was written in its place (Home,
Launcher, Stopwatch, Pomodoro, Countdown 10 min — all field defaults left
alone, so it is nearly all template + activation) and checked against the real
parser (`python -m aibutton.scenes check default` → ok).

**Then something with a live session against this service saved while the
service still had the old scene active in memory, and that write landed back
in `scenes/default.json`** - clobbering the curated content with the owner's
old personal one again, byte for byte. `config.json`'s pointer was untouched
(a scene save never repoints the active scene - CLAUDE.md's rule held), only
the *content* of whichever file the server still considered active.

**Why**: `config.json` was edited on disk, but the running service loads
`scenes.active` once at startup and does not notice a file change on its own -
exactly the caveat `scenes.py`'s own CLI prints ("restart the service or POST
/api/config/reload to apply it"). Until that reload happens, *any* save from
*any* client - another browser tab, the tray control panel, this one - writes
to whichever scene the process still thinks is active, which was still
`default`. Reapplying the curated file without reloading first would only
race the same clobber again.

**Done when** (revised): the service has been reloaded or restarted so its
`scenes.active` matches `config.json`'s `"personal"`, the curated content is
reapplied to `scenes/default.json` and confirmed to stick afterward, and the
personal-scenes rule is written into [README.md](README.md) (not done yet
either - the file/gitignore side shipped, the doc paragraph didn't).

#### Resolved 2026-08-29 — reloaded, reapplied, and it held

The owner confirmed the live tinkering was theirs and stood back for a moment.
`POST /api/config/reload` picked up `config.json`'s `"personal"` pointer (the
response's `scenes.active` came back `"personal"`), and `scenes/default.json`
was rewritten with the curated five-mode content and re-checked against the
real parser (`ok`). Proof the reload actually fixed the routing rather than
just quieting the symptom: a rename and a new "Wake up" alarm the owner made
*after* the reload landed correctly in `scenes/personal.json`, not
`scenes/default.json` - a save now goes where `config.json` says it should.
The personal-scenes paragraph was also added to
[README.md](README.md)'s Scenes section. **Done**, for real this time.

### 101. The nav is a map of what can happen, not a list of what is configured - shipped 2026-08-29

The owner's sketch, kept close to verbatim because the shape is the ask:

```
Settings
Event Log
Lights
Actions
Menus (2)
  Main Menu
  DAW Control
Apps (8)  (manage)
  Stopwatch (2)
    % "Mile Run"          Fastest: 7:57
    % "Work Commute"      Fastest: 18:45
  Intervals (2)
    % Pomodoro Standard   Recent: 01/01/01 01:01
    % HIIT Standard       Recent: 01/02/01 01:01
  Metronome (2)
    % 4/4 120 BPM
    % 3/4 121 BPM
  Notice (3)
    @ Alarm: "Good Morning!"     7 AM Weekdays
    @ Reminder: "Take Out Trash" 4 PM Thursdays
    @ Reminder: "Rent Due"       8 AM, 1st of the month
  Tally (3)
    $ +1 Said the word "Um"
    $ +1 Stitch counter
```

Three changes, and they are one idea: **every row says what starts it, and
nothing on the page describes a template.**

#### (a) The glyph is reachability, and it already exists as a function

The owner's `$ / % / @` are answering *what sets this off*, and that is
exactly what `reachableModes` and `findEntryPoints` in
[schema.js](aibutton/web/static/schema.js) already compute. So the glyph is a
render of a pure function this project has had since 48a - not new logic.

**It wants four values, not three, and the fourth is the valuable one:**

| Starts it | Meaning |
|---|---|
| a press | some gesture, somewhere, opens this |
| a clock | a schedule opens it with nobody pressing anything |
| a reaction | something outside opens it (**102**) |
| **nothing** | **it can be configured and never reached** |

Unreachability is reported today only on the Apps page, in prose, on a page
you have to go to. It is the one fact in this list that is *a bug in the
user's config*, and it belongs where they are already looking.

**And the glyph deletes the double listing.** Today a scheduled Notice is
listed under Apps *and* under Reflexes - "On a schedule", deliberately (48a):
it answers two questions, so it gets two rows. One row with a clock glyph
answers both. That removes `_appendReflexList`'s scheduled half **and** the
reason `navButtons` maps a mode to a *list* of entries rather than one.

**On the symbols themselves: do not ship `$ % @`.** They are borrowed shell
punctuation, they mean nothing to someone who has not read this note, and one
of them is actively wrong - `$` reads as money, on a row that says
*+1 Said the word "Um"*. Use glyphs that name the starter, each with a
`title`, and one legend line at the top of the nav. Text glyphs behind a CSS
class, not emoji: emoji render differently on every platform and several are
colour-only, and **colour is already spoken for by the swatch**.

**Watch the row width.** A row already carries a live dot and a look swatch;
name and summary make four columns and the glyph makes five, in a panel that
is a sidebar. Put the glyph in the dot's column or beside the name - do not
add a fifth.

#### (b) The subtitle stops describing the template

This is the owner's "remove all descriptions", and it is right: the summary on
a nav row is `describeTemplate(mode)`, which says what a *stopwatch* is on
every stopwatch. It answers a question you already answered by opening the
group. What distinguishes two stopwatches is their own data.

**Split it in two, because half is free and half is a network call:**

- **From config** - "4/4 120 BPM", "7 AM Weekdays", "25/5, 4 blocks", "+1 per
  press". Synchronous, already available, one rewrite per template's
  `describe`. **Build this half first; it is most of the sketch.**
- **From the store** - "Fastest: 7:57", "Recent: 01/01/01". These need
  `/api/events`, and two constraints come with them:
  - **One aggregate request, cached per load.** `_renderModeNav` runs on every
    model change; a per-row query would fire dozens of requests per keystroke.
  - **It must degrade to the config line.** The offline editor
    (`tools/build_editor.py`) has no service, and a nav that renders blank
    subtitles there is the same class of mistake as the ready-made picker that
    vanished when its mount did (CLAUDE.md).

#### (c) The group blurbs already have an off switch

The paragraphs under Menus / Apps / Reflexes are `data-help`, so **Tips
already hides them**. Deleting them removes the only place the menus-vs-apps
distinction is *stated*, which was the entire point of 75. Recommendation:
leave them where they are and default Tips off after first run.

#### What the sketch does not settle, and should

- **What a count counts.** The sketch says `Apps (8)` over groups totalling
  twelve items. Pick one and use it everywhere: **items**, so `Apps (12)` with
  `Stopwatch (2)` under it, and the numbers add up.
- **`(manage)` is the door 82 just removed.** Do not reinstate a second link
  to the Apps page; make the *heading* the door.
- **Order means different things in the two groups.** Menus are a priority
  list read top to bottom - order is behaviour, and `canReorder` already
  restricts dragging to them. Apps have no order; leave insertion order and do
  not offer to sort them.
- **Adding an app should offer presets, not templates.** The single largest
  ease-of-use gain available here is not in the sketch: `+` on the Apps
  heading should list `BUILTIN_MODES` ("Pomodoro", "Tabata", "Dead man's
  switch"), not the twelve template types. A new user can pick from the first
  list and cannot pick from the second. This is CLAUDE.md's "prefer a preset
  to a template" pointed at the UI.
- **A filter box: not yet.** At twelve items the nav is fine. Revisit at
  roughly twenty, and let a real config be the trigger rather than a guess.

**Done when**: no row on the nav describes a template, every leaf row says
what starts it including "nothing", and a scheduled app appears exactly once.

#### Shipped 2026-08-29 - and three things the sketch had not decided

**The glyph took a fifth value, not four**, and the fifth draws nothing.
A gesture map is never *started* - it listens - so `live` is a real answer and
its glyph is the empty string. Every row in Menus is one, which is why an empty
column there reads as a property of the group rather than as a missing value.
The other four are `◷` a clock, `⚡` a reaction, `▸` a press, `⊘` nothing.

**`reached` is passed in, not computed per row.** `startedBy(mode, reached,
actions, reflexes)` takes the `reachableModes` set as an argument because
`_renderModeNav` runs on every keystroke that changes the model - computing it
inside would make an O(n) walk O(n squared) for an answer that cannot differ
between two rows of one render.

**Rewriting `describe` was most of the work and it was subtraction.** Every
template already carried its own data; what it also carried was its own name -
`Stopwatch “mile run”`, `Countdown 10 min`, `Reaction timer - 3 attempts` -
under a heading that had just said the same word. Thirteen of them now return
the distinguishing half alone, and **Notice reads its time off the activation**,
which is what the sketch actually asked for (*Alarm “Good Morning!” · at 07:00*).
The one caller that needs both halves is the `enter_mode` picker, which prefixes
`label` itself rather than a second description existing to carry it.

**The store-derived half (b) shipped the same day** - see below.

Touched: `schema.js` (thirteen `describe` bodies, `STARTERS`/`STARTER_BY_KEY`/
`startedBy`, `MODE_GROUPS` loses its third group), `menu.js` (`_renderModeNav`,
`_navRow`, `_membersOf`, `_appendReflexList` and `_navReflexRow` deleted),
`widgets.js` (`describePick`), `index.html` (the starter styles),
`MANUAL.md` §4.1, and `tests/js/startedBy.test.mjs` - five cases, run.

#### 101(b) shipped 2026-08-29 - and "Fastest" is a question, not a number

`GET /api/events/summary` (one row per `(kind, name)`: count, last, and the
extremes of `duration_s` and `value` separately) backs a second clause on every
nav row - *logs “mile run” — 12 runs so far · last Aug 20*. One request for the
whole list, fetched beside the render rather than awaited, and **optional at
the API**: `FileApi` has no `eventSummary`, so the offline editor never asks
and every row keeps its config half. That is the degradation this was shaped
around rather than a fallback bolted on afterwards.

**Deliberately not windowed**, unlike `/api/events`: that one is a feed with a
limit and this one is a total, and a "12 runs" quietly meaning "12 of the last
500 rows" would look right for months.

**"so far" earns its four characters.** A reaction timer's config line already
says *3 attempts* (the rounds it is set to) and the live one says how many have
been played. Two numbers under one noun on one row is exactly the ambiguity a
live line was supposed to remove.

**And the sketch's "Fastest: 7:57" is not what shipped**, on purpose. The
stopwatch descriptor sets `better: null`, and that is a decision this file
should not quietly overturn: the same template times a mile run, where quicker
is better, and a cake, where it is not. So a best shows only where a descriptor
declares one (the reaction timer, Hot/Cold). **The open question, for the
owner**: either set `better: 'low'` on the stopwatch and accept that a cake
timer will advertise its fastest bake, or let an *item* carry it - which is a
new config field and therefore a real item rather than a word. Filed as **109**.

Touched: `store.py` (`readout_summary`), `webui.py` (the endpoint and the
header), `api.js` (`eventSummary`), `schema.js` (`readoutStat`, structured
rather than formatted - it holds no `format.js` import), `menu.js`
(`_loadEventStats`, `_statLine`, the row's two-half line),
`tests/js/readoutStat.test.mjs` (seven cases, run) and three endpoint tests in
`tests/test_events_filter.py`.

### 102. An Actions page - the pool, and the reactions that fire from it - shipped 2026-08-29

**Asked 2026-08-29**: *"Actions should have a menu available in the side-bar...
the Actions menu item points to the main config page for named actions as well
as Reactions."*

**The symmetry is the argument.** Lights is a nav destination that holds the
look pool. Actions is the same page for the action pool (`AppConfig.actions`),
and a **reaction is a circumstance with an action attached** - its entire
vocabulary of consequences *is* that pool (`REFLEX_ACTIONS`). They belong on
one page because one is the ingredient list for the other.

**It also resolves a comment that admits it is a workaround.**
`_jumpToReflex` scrolls the reflex editor into view inside the Modes panel,
with a note saying "two editors for one object is how a page starts lying".
Giving reactions their own destination makes that a real navigation instead.

**And it is what empties the Reflexes nav group**, which with 101's clock
glyph removes the last reason a mode is listed twice.

**One question to answer while building it**: does the page list *inline*
actions - the ones written directly on a gesture rather than named in the
pool? Recommendation: **no, but show where each pool entry is used.**
`config.iter_actions` already walks every action in a config, and the look
pool's row already shows where a look is worn, for the same reason: editing a
shared thing changes it everywhere, and that has to be visible before the
edit. Same fact, same control, second pool.

**Done when**: Actions is a top-level destination holding the named-action
pool and the reactions, the Reflexes nav group is gone, and each pool entry
says where it is used.

#### Shipped 2026-08-29, bar the last clause

Actions is a nav destination in **both shells** - `mounts.actions`, optional
like `nav` and `apps`, so a shell without it keeps the two pools under the
modes and loses a section rather than a capability. The offline editor was
given the mount rather than the fallback, which is CLAUDE.md's rule about what
happened the last time a capability landed on a mount that shell did not have.

The Reactions nav group is gone, and that is what removed the last reason a
mode was listed twice. `_jumpToReflex` asks the mount which panel to show
rather than naming a tab, so it works in either shell - and it stopped being
the workaround its own comment admitted to, because there is somewhere to jump
*to* now.

#### The last clause shipped 2026-08-29 - and it was a bug, not a feature

Each pool entry's row now says **where it is used**, the same sentence the look
pool's row already carried, for the same reason: editing a shared thing changes
it everywhere and that has to be visible before the edit.

**Writing it found a real fault.** The editor's rename walked a hand-written
list of places - gestures, and a signal light's positions - and quietly missed
**mode hooks, a Notice's `on_cleared`/`on_snoozed`/`on_missed`, a reaction's
`then`, and every step of a sequence**. So renaming a pooled action from the
editor could dangle exactly the references the parser then warns about, which
reads to a user as the rename having half worked.

The list of usages and the list of things to rewrite are the same list, so
`schema.js`'s **`actionRefs`** is now the one walk both callers use, and a
template's `bindings` key joins it for free - which is what that key is for.
`tests/js/actionRefs.test.mjs` pins all seven slot kinds and asserts the thing
that used to fail silently: not that the new name is somewhere, but that the
old name is *nowhere*.

### 103. Two renames, both copy-only: reflex to reaction, Counter to Tally - shipped 2026-08-29

**Asked 2026-08-29.** *"Let's rename reflexes to 'reactions' - to signify it
involves 'actions'."* and *"rename Counter to Tally, which is less
polysemous."* Both are good and both are cheap, **because CLAUDE.md already
decides how a rename like this is done**: new copy uses the new words, and
mirrored tokens do not move.

So `AppConfig.reflexes`, the `Reflex` dataclass, `REFLEX_ACTIONS`,
`REFLEX_OPS`, `reflex_hears`/`reflex_matches`, `CounterBehavior`,
`template: "counter"` and `DOC_SLOTS["counter"]` all stay exactly as they are.
No config migrates.

**Two places are genuinely user-facing and need a decision each:**

- **`POST /api/reflex/{name}` is written down outside this repo.** It is the
  address a Shortcut, a cron job or a plant sensor posts to (**71**), and
  renaming it breaks things nobody here can edit. **Keep the route; add
  `/api/reaction/{name}` as an alias** - two lines, no migration - and let the
  docs teach the new one.
- **The config key `reflexes` is hand-editable.** Precedent: `modes` survived
  the menus/apps rename for exactly this reason. Keep it.

**CLAUDE.md says the word "reflex" moved once and must not move again.** This
is it moving again, and the reason it is allowed is that it is moving to a
*synonym* - nothing else is taking the name, no concept is changing hands.
That was not true the first time, which is what the rule is guarding. Update
the rule's wording when this ships, or the next reader will think it was
broken.

**Tally has a collision worth checking first: 91.** That item recommends the
counter template stop existing and become a top-level pool. If 91 lands,
"Tally" is the name of the *pool*, the template may be gone, and this copy
gets written twice. **Do 103's Tally half with 91, or accept doing it twice.**
The `COUNTING` LED state is labelled "Counter open" and moves with it.

**Done when**: no user-facing string says "reflex" or "counter", no token
moved, and `/api/reflex/{name}` still answers.

#### Shipped 2026-08-29 - and one collision found on the way

**"Reaction" was already taken, and it turned out not to matter.** The
reaction-time game is a template, and its label is `Reaction timer` - two
words. So the nav reads *Apps -> Reaction timer* beside a top-level
*Reactions*, which is close but not ambiguous, and nothing was renamed to
avoid it. **Worth knowing before anyone shortens that label to "Reaction",**
which is the change that would make the collision real.

The route did not follow the word: `/api/reaction/{name}` was added as a
second path onto the same handler and `/api/reflex/{name}` is not deprecated
and never will be. That asymmetry has a rule behind it - **this URL is the one
thing in the project written down outside it**, in a phone shortcut, a cron
line or a sensor's firmware, none of which can be edited from here. The editor
shows the new spelling because only one can be shown; the MANUAL says both.

`README.md` also carried a **stale template list** ("actions, alarm,
reminders, ...") from before **84** merged the two into `notice`. Corrected in
the same pass, and rewritten to labels rather than tokens, since it is prose
for a reader rather than a mirrored table.

Touched: `menu.js` (six strings, plus `_reflexUrl`), `schema.js` (the group
title and blurb, the `positions` hint, the Tally label / about / describe /
docSlot, the `COUNTING` state label), `webui.py` (the alias route and the
module header), `README.md`, `MANUAL.md`, `tests/test_reflex.py` (two tests
pinning that both spellings answer). No token moved and no config migrates.

### 107. An unknown template must not quietly become a menu - shipped 2026-08-29

**Reported 2026-08-29**: *"we were working on creating the Notices app and then
Alarms showed up as Menus in the side-bar."*

**Traced, and the config was never wrong.** `menu.js`'s `_natureOf` returned
`'ambient'` for any template schema.js had no descriptor for, with a comment
calling it "the harmless default: they answer gestures" - and `_membersOf`
files everything ambient under **Menus**. So the moment a mode was saved as
`template: "notice"` while the browser was still running a **schema.js from
before 84**, every alarm moved into Menus and looked like a gesture map
somebody had mis-added.

**And the stale module graph is not a fluke here, it is documented.**
`/static` is served `no-store` only after a service restart; until then a
browser will happily run an old ES module graph against a freshly saved
config. This file already warns about that under "Known live state you may
trip over" - what was missing was the editor *saying so* instead of guessing.

Fixed: `_natureOf` answers `'unknown'`, and a fourth nav group -
**Unrecognised**, rendered only when it has members - shows those modes with a
line saying the page is behind, reload, and restart the service if they are
still there. Nothing is hidden, nothing is filed under a heading that is not
true, and `canReorder` stops offering to drag a mode whose nature is a guess.

**The rule this stands for is in [CLAUDE.md](CLAUDE.md)**: a fallback may
degrade a capability, never invent a classification.

Touched: `menu.js` (`_natureOf`, `_membersOf`, `_renderModeNav`), `schema.js`
(`MODE_GROUPS` gains `unknown`).

### 54-68. What the three-POV read-back found

**Raised 2026-08-26 by item 47** (see Done), which walked the finished shell as
three fixed personas. The bugs and dead ends it turned up were fixed in the
same pass; these were fifteen further improvements, five per point of view,
deliberately *not* one item - each stands alone and several are an hour.
**54, 55, 56, 57, 58, 59, 60, 61, 63, 64, 66, 67 and 68 shipped 2026-08-26**,
and the last two - **62** and **65** - on 2026-08-29. See Done.

Nothing here is a bug. The page works; these are the places where it makes the
reader do the work.

**62 and 65 shipped 2026-08-29 - see Done.** Nothing from this read-back is
open any more.

### 30. Actions as a first-class idea — a pool, a taxonomy, and the data under it

**Conceptualised 2026-08-19. Design before code; the UI last.** The full
write-up is ROADMAP **3d** and decision **D9** — read those, this is the sprint
view.

**D9 is decided (2026-08-19)** — ARCHITECTURE.md "Apps own data" is the
design, ROADMAP 3d the taxonomy (System / Custom / App-bound). The build
halves are numbered: **(a) the named action pool shipped 2026-08-20, (b) the
`SequenceAction` on 2026-08-27 and (c) app documents with app-bound actions on
2026-08-29 — see Done for each.**

**Nothing is left open under this number, and all three halves have shipped.**

### 19. The light as a language — sequencer, one-offs, and where colour is edited

Part (a), the subdivision ladder, shipped — see **Done**. **b and c are done
too**; this item is closed, and what is below is the record of what it decided.

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

**The animated device-side preview shipped in 41.** It needed no
cancellable task in webui.py after all - mirroring main.py's driver there
would have been a second flash-floor gate. `WebContext.show_look` is main's
own `set_led`, which already owns both the task and `sequence_safe`; with no
driver attached the endpoint still degrades to the first stop and says so.

**15 and 17 are now unblocked; Simon-says (16's parked half) too.**

#### c) Reuse the ramp widget wherever a gradient makes sense — **shipped 2026-08-23**

Pomodoro was the only real candidate and it cost what this item predicted: a
template field, plus the repainting tick `run_pomodoro` did not have. Hot/cold
and reaction already offered a ramp and already walked it; the countdown's is
where the pattern came from. Nothing else has a fraction to ramp over — hold
levels still need `GESTURE_HOLD` (item **29**).

**The ramp is empty by default here**, unlike the countdown's, and that is the
decision worth keeping: this template says work-versus-rest *with colour*, and
a ramp overrides both states. The rule is in [CLAUDE.md](CLAUDE.md).

**The tick turned out to be worth more than the field.** A drive needs an app
that knows the number *and* repaints often enough for it to move, so the tick
is what let `pomodoro` join `DRIVE_TEMPLATES["progress"]` — and a named stop
list is chosen per state, so WORKING can be driven while RESTING keeps a plain
colour. That is the better answer for this template, and the ramp is the
one-field version of it.

Progress is through the **current block**, not the session (a classic Pomodoro
has no end), so it resets at every phase change and `extend` grows the
denominator along with the deadline.

## Small fixes

- **An empty MIDI port still means "the first output", and now it says so.**
  Found 2026-08-27, the hard way: a DAW Control surface with five MCU bindings
  had `"port": ""` on every one, so every note went to *Microsoft GS Wavetable
  Synth* - output 0 on this machine - while the DAW sat waiting on a loopMIDI
  port. The field was `tier: 'tinker'`, so the setup path that produced it
  never showed the field at all.

  **Fixed the same day**: the port is a basic-tier field now, and its hint
  says what blank does. The rule it stands for is in
  [CLAUDE.md](CLAUDE.md) - a field that decides whether an action does
  anything at all is not an advanced option.

  **The load-time warning shipped 2026-08-29** (`config.blank_midi_ports`,
  see Done): with more than one output on the machine, every blank port is
  named at startup.

## Earlier shipped work (compressed record, pre-2026-08-29)

Compressed to the decisions that still bind. Where a rule governs future code
it lives in [CLAUDE.md](CLAUDE.md) and is not repeated here.

- ~~**34. App documents, and app-bound actions**~~ - 2026-08-29, and with it
  the last open half of **30**. An app may keep a bounded bag of named values
  ([documents.py](aibutton/documents.py)) beside the log: slots declared per
  template (`DOC_SLOTS`, mirrored as `docSlots` in schema.js - the manifest's
  precursor), scalars only, `MAX_SLOTS` as the backstop.

  Three decisions that bind:

  - **The log stays separate, and both are written.** A durable counter logs
    every press *and* moves its slot, so flipping the flag changes what the
    number on the light means and changes nothing about history, streaks or
    the Events page.
  - **`durable` is a flag on the counter, not a second template.** "How many
    today" and "how many ever" are both ordinary things to want, and the
    default is the template exactly as it was.
  - **`set_value` is app-bound but ordinary.** It names an app and writes one
    slot, which makes TODO **15**'s "Smoking +1 without entering the Counter"
    a binding rather than a feature; it changes no loop and owns no light, so
    adding it to `FIRE_AND_FORGET_ACTIONS` reached a gesture, a hook, a reflex
    and a sequence step at once.

  **Known gap, stated rather than hidden**: a document is keyed by the mode's
  *name*, because modes have no id. Renaming an app in the editor is a new
  document, and there is no rename event to follow - the name is a text box
  somebody types in. The fix is app ids, which is the manifest (**ROADMAP
  3b**), not a callback.

- ~~**65. A webhook can be previewed and tested**~~ - 2026-08-29. `actions.
  webhook_payload` is the body `execute` would POST, pulled out so it can be
  shown without being sent; `POST /api/webhook/preview` returns it, and
  `send: true` performs the real request. The three-way merge is visible at
  last - identity beats the app's summary, the user's payload beats both - and
  keys the summary contract drops are *named* rather than quietly absent.
  The editor mounts it as a **field descriptor that is a control**, so a
  gesture, a hook, a reflex, a pool entry and a sequence step all got it from
  one entry in `ACTIONS`.

- ~~**62. Parser warnings know which field they are about**~~ - 2026-08-29,
  the backend half being the whole blocker. `parse_with_details` answers with
  `ParseWarning(message, mode, key)` beside the strings, and the location is
  read from the **log record's first argument** rather than parsed back out of
  the rendered sentence - every parser call passes `where` first, which makes
  it a lookup. The editor marks the field; a warning it cannot place is still
  printed in the Save bar, which is why the bar was not replaced.

  **Closed 2026-08-30.** The one remaining offender was `_drive_warning`,
  which built its own rendered sentence and handed it back for the caller to
  re-log via `log.warning("%s", complaint)` - burying `where` inside the
  message text where `_locate` could never find it. It now logs directly
  with `where` first, like every sibling call site; `test_config.py`'s
  `test_a_drive_mismatch_warning_is_placed_too` pins it. That was the only
  call site left in this shape - grepping for `log.warning("%s"` across
  config.py and scenes.py turns up nothing else.

- ~~**An empty MIDI port warns at load**~~ - 2026-08-29, the half of the
  2026-08-27 fix that reaches a hand-edited file. `config.blank_midi_ports` is
  pure and takes the port list, because enumerating MIDI hardware is I/O and
  the parsing half of that module does none; `main` asks it once at startup.
  **Silent when the machine has one output**, where blank is unambiguous. It
  rides on `config.iter_actions`, which is the other thing that came out of
  this: one walk over every action in a config, found by *shape* rather than
  by a list of templates, so "which actions do X?" is asked once.

- ~~**33. `SequenceAction` — a flat list with delays**~~ - 2026-08-27. The
  action item **25** has wanted since it was written: Mackie has no
  return-to-zero, so "stop and rewind" is *Stop, a beat, Stop* - two messages
  one gesture has to send.

  ```json
  { "action": "sequence", "steps": [
      { "action": "midi", "port": "4G3NT", "kind": "note_on", "number": 93, "value": 127 },
      { "action": "midi", "port": "4G3NT", "kind": "note_on", "number": 93, "value": 0, "wait_s": 0.05 } ] }
  ```

  The rules that bind are in [CLAUDE.md](CLAUDE.md) — *flat, bounded, and its
  limits live in the parser*, and *a new action shape is resolved in
  `resolve_action`, not at each dispatch site*. The decisions worth keeping:

  - **The two edges the item said to decide first.** It **holds the button**
    (presses during it are dropped by the existing rule, and the editor hint
    says so), and the parser — not the editor — enforces
    `MAX_SEQUENCE_STEPS = 8` and `MAX_SEQUENCE_S = 10`, truncating with a
    warning rather than rejecting. Both numbers are mirrored into schema.js so
    the editor stops you where the parser would.
  - **`wait_s` is written on the step it delays**, not after the previous one:
    "wait, then do this" is the order a person reads, and a sequence's whole
    job is the gap *between* two messages.
  - **A step may name a pooled action; a named step has no delay.** A bare
    string has nowhere to put one, and inventing a wrapper object for that case
    would be a second step shape to read and write.
  - **Nesting is refused twice.** Inline, by the parser; by name, by
    `resolve_action` - the shape the parser cannot see, since a pool entry may
    itself be a sequence. Both drop the step and keep the rest.
  - **Every step runs even after one fails**, and the first failure is what the
    status line reports. A sequence is a script, not a transaction: if the
    webhook is down, the MIDI note that was going to follow it is still what
    the button was asked to send.
  - **The editor got one new widget, not one new page** (`kind: 'steps'` in
    [widgets.js](aibutton/web/static/widgets.js)): numbered rows with the
    action's own fields, a wait box, reorder arrows and a remove. It lives with
    the field system rather than with one page because a sequence binds
    anywhere an action binds.

  **What this unblocks:** **78** (a control surface where the press depends on
  the position) wanted this for the Stop-Stop case and can now have it, and a
  DAW that expects a *press and a release* rather than a bare trigger is one
  two-step sequence away.

- ~~**73. MIDI in as a reflex source — and what item 25 was waiting for**~~ -
  2026-08-27. A listened port turns notes and CCs into reflexes, which is the
  half of item **25** that was never a design problem so much as a missing
  input.

  ```json
  { "name": "rec_on",
    "from": { "midi": { "port": "Button", "note": 95 } },
    "when": { "field": "velocity", "op": "==", "value": 127 },
    "while": "Transport",
    "then": { "action": "set_position", "name": "Recording" } }
  ```

  The rules that bind are in [CLAUDE.md](CLAUDE.md) — *a source says which
  messages reach a reflex; the test says whether they fire it*, and *a driver
  callback hands three bytes to the loop and does nothing else*. What is worth
  keeping here:

  - **It needed no new comparison language.** The message becomes a payload
    (`{note, velocity, value, channel}`) and **72**'s one-field test does the
    rest, which is what makes *note 95 velocity 127* and *the same note at 0*
    one source and two opposite tests — the exact ambiguity item 73 was
    written to point at.
  - **A note-off reads as value 0** (`midi.decode`). The only thing that sends
    notes *to* a button is a control-surface protocol using them as lamps, and
    a DAW that spells the dark half as a note-off means the same thing. One
    test catches both spellings.
  - **`listen` now hands over all three bytes**, both backends. `ClockListener`
    reads the status byte and defaults the rest, so the single-byte clock
    messages it exists for are unchanged.
  - **One listener per port, opened on the tick.** The wanted set is derived
    from the config, so a reflex added in the editor starts listening without a
    restart, and a port that only exists once loopMIDI or the DAW is running is
    retried on a slow timer (`_MIDI_RETRY_S`), warning only when the reason
    changes.
  - **`from` is additive.** A MIDI reflex keeps its URL, so it is testable with
    `curl` while the DAW is closed — which is how most of this was verified.

  **Verified end to end against a fake backend**: the service opened the port,
  a CC fired a top-level reflex, note 95 velocity 127 moved a *running* signal
  light to Recording and velocity 0 moved it back (**74** + **77**'s light half
  in one line), readings were attributed to the app while it ran and to nothing
  before it, a note nobody named and a clock byte did nothing, and the listener
  closed on shutdown. **Not yet run against a real DAW** — that is **77**'s
  definition of done and needs the Send To pointed at a loopMIDI port.

- ~~**74. A reflex can change what a running app is doing**~~ - 2026-08-27.
  The invasive one, and it went in as the recommended **second queue** rather
  than as a synthetic press.

  ```json
  { "name": "rec_on", "while": "Transport",
    "when": { "field": "velocity", "op": "==", "value": 127 },
    "then": { "action": "set_position", "name": "Recording" } }
  ```

  The rules are in [CLAUDE.md](CLAUDE.md) - *a reflex reaches a running app
  only by naming it*, and *what the world reports is shown, not announced*.
  The four decisions:

  - **`wait_in_app` is the takeover's `_wait_for_trigger`.** Same contract
    (press, or None on shutdown/timeout) plus one more answer: a
    `SetPositionAction`. Anything else the reflex carries it runs itself, so an
    app never grows a second `execute()` path and the app's light is left
    alone. **An app opts in by calling it**; one that does not keeps
    `_wait_for_trigger` and reflexes wait for it, exactly as under **71**.
  - **The timeout is a deadline, not a fresh clock per arrival.** A ringing
    alarm's grace period must not be extended by traffic nobody asked for -
    the bug you only find at 3 a.m.
  - **A reflex for somebody else is held, not requeued.** Requeueing
    immediately spins (take, put back, take); acting on it now would let the
    world interrupt an app it was not addressed to. It goes back on the queue
    when the app hands the button over, in arrival order, which is exactly the
    "waits its turn" behaviour 71 shipped.
  - **`set_position` is the third loop-owned action**, after `enter_mode` and
    `standby`, and the narrowest: only a *running* app can perform it. Marked
    `appOnly` in schema.js so a gesture is never offered it - a gesture is
    answered at the ambient layer, where there is no app to have a position -
    and `handle` says so plainly if a hand-written config binds one anyway.

  **The consumer today is the signal light**, which already had named states:
  a reflex moves it between them, paints it, and logs the position the same
  way a press does - so a day's chart mixes reported and pressed changes
  without lying about either. It does **not** fire that position's own action,
  the rule entering already followed, and with a DAW that is the difference
  between a light and a feedback loop. **This is 77's design prototyped on the
  template that already had positions**; what 77 adds is the same on a control
  surface, fed by MIDI (**73**) instead of by HTTP.

  Verified end to end over HTTP against a throwaway service: a press opened
  the app, then `rec_on`/`rec_off` moved the light with nobody touching the
  button, a velocity failing its test left the position alone but still logged
  the reading, an unknown position was reported rather than guessed, and an
  unscoped reflex sat waiting until the app was left and then fired.

- ~~**72. A reflex can test the value it arrived with**~~ - 2026-08-27, the
  same day as **71**, because a reflex that cannot look at what it was told is
  a doorbell rather than a sensor.

  ```json
  { "name": "moisture_low", "when": { "field": "moisture", "op": "<", "value": 30 },
    "then": { "action": "enter_mode", "target": "Water me" } }
  ```

  ```bash
  curl -X POST localhost:8080/api/reflex/moisture_low -d '{"moisture": 12}' -H 'content-type: application/json'
  ```

  The rules that bind are in [CLAUDE.md](CLAUDE.md) - *one field, one
  operator, one number*, and *a number that arrived is logged whether or not
  it fired*. What is worth keeping here:

  - **`REFLEX_OPS` is the whole language**, six comparisons, mirrored in
    schema.js and pinned by [test_schema_mirror.py](tests/test_schema_mirror.py).
    There is deliberately no "add another condition" in the editor: two
    conditions is an expression parser, and an expression parser never moves
    onto the device (**D2**).
  - **The loop evaluates, the endpoint carries.** `reflex_matches` is pure and
    has one call site, so **73**'s MIDI source applies the same test instead of
    growing its own. The HTTP reply still says *accepted*, never *matched* -
    it is a queue, and the button may be busy.
  - **A missing field does not fire.** The alternative - firing when the field
    is absent - turns a renamed sensor key into an alarm nobody can stop,
    which is the failure people unplug the device over.
  - **A broken `when` is dropped and the reflex is kept**, firing
    unconditionally and warning. A silenced reflex is indistinguishable from a
    sensor that stopped reporting; a noisy one is at least visible.
  - **The reading is logged on arrival, under the reflex's name**, so 88 and 12
    both land in `value` and the Events page charts the sensor for free. The
    action's own rows are separate and unchanged.

  Verified end to end over real HTTP against a throwaway service (MockDevice,
  its own port and database): 12 fired and logged, 88 logged only, a wrong
  field did neither, a pooled action fired by name, a typo answered 404 naming
  the reflexes that exist, and `enter_mode` put the button in the app.

- ~~**75. What the mode list is called, now that reflexes are real**~~ -
  2026-08-27, straight after **71**, because the word collided the moment a
  real reflex existed. Three groups, the owner's own table:

  | Group | What it means | Holds |
  |---|---|---|
  | **Menus** | a press picks between things | the everyday gesture map, launchers, control pages |
  | **Apps** | takeovers that do a job | the other ten |
  | **Reflexes** | the button acts with nobody pressing it | reflexes (**71**), and the apps a clock starts |

  The vocabulary rule is in [CLAUDE.md](CLAUDE.md) - three words, and the
  tokens still do not move. What is worth keeping here:

  - **`MENU_TEMPLATES` is UI-only grouping** (`actions`, `launcher`,
    `control`), beside `MODE_GROUPS` in schema.js. A launcher's `nature` is
    still `'takeover'`, because that mirrors `TAKEOVER_BEHAVIORS`; what
    changed is which *heading* it is listed under, and that was never a
    mirrored fact.
  - **A group is keyed by `key`, not by `nature`** - there are three groups
    and two natures now, which is exactly why the old code could not express
    this.
  - **The Reflexes group lists things that are not modes**, so it does not go
    through `_navRow`: a reflex has no look to swatch and can never be the
    running thing. Selecting one scrolls its row in the Reflexes section into
    view and marks it (`_jumpToReflex`, the move TODO 60 built) rather than
    filling the detail pane - **two editors for one object is how a page
    starts lying**.
  - **The duplication 69 complained about is fixed for the new half by
    construction**: a reflex is its own object, so *"moisture_low → Water me"*
    is a row in Reflexes and the alarm is a row in Apps - two things, listed
    once each. Only a *scheduled* app still appears twice, which is **70**'s
    decision not to migrate schedules; folding (**69**) is the mitigation that
    already shipped for it.

- ~~**71. A reflex fires an action, and HTTP is the first source**~~ -
  2026-08-27. The cheap half of **70**, and the one that makes the plant alarm
  real: a top-level `reflexes` list, `POST /api/reflex/{name}`, and dispatch
  through the action machinery that already existed.

  ```json
  "reflexes": [
    { "name": "moisture_low", "then": { "action": "enter_mode", "target": "Water me" } },
    { "name": "deploy_done",  "then": "celebrate", "while": "Focus" }
  ]
  ```

  What still binds is in [CLAUDE.md](CLAUDE.md) — *a reflex adds a source of
  events and no new vocabulary of consequences*, and *a circumstance is not a
  press and never travels as one*. The four decisions behind them:

  - **`then` is any action, from a list.** `REFLEX_ACTIONS` is the hook set
    plus `enter_mode` — mirrored in schema.js, tested in
    [test_schema_mirror.py](tests/test_schema_mirror.py). `readout` and
    `standby` stay out: both change what the loop does with the *next gesture*,
    and nobody is standing at the button to see the answer. A bare string is a
    pool reference, so `handle_reflex` is the fifth `resolve_action` site
    CLAUDE.md predicted.
  - **A second queue, not a synthetic press.** `_wait_for_press_or_reflex`
    selects on the device's queue and `inbound`; a press wins a tie and
    whichever getter also fired is put back rather than dropped. `run()` takes
    the queue as an argument the way it takes the device, which is how the
    tests post a circumstance with no web server up.
  - **Presses made while busy are dropped; reflexes are not.** A press whose
    moment passed is noise; a plant that has gone dry still means it. Bounded
    at `_INBOUND_MAX = 16` so a script in a loop cannot queue an hour of them,
    and the endpoint answers 503 rather than waiting.
  - **`while` was enforced from the first version and could not match yet.**
    A takeover is awaited inside `handle`, so nothing drained `inbound` while
    an app ran. Enforced anyway so the field would never mean one thing and
    later another - and **74**, later the same day, made it fire.

  **The App page learned about it** (`reachableModes`, `findEntryPoints`,
  `danglingTargets` all take reflexes): an app opened only by a reflex now
  reads *"the reflex “moisture_low”"* rather than "unreachable", and a reflex
  pointing at no mode is named in the same warning a gesture gets. Verified in
  the offline editor.

  **Where you edit one**: the Modes tab, above the named-action pool, each row
  carrying the URL that fires it — a reflex has no press to watch for, so the
  config is the only place it can be seen at all.

  **Standby does not mute a reflex** - standby puts the *ambient layer* to
  sleep, and a plant that has gone dry has not stopped meaning it because
  nobody is at the desk. Said in a comment at the one place it is decided.

  **Not built, on purpose**: no event row per fire (that arrives with **72**'s
  value, which is what the `value` column is for) and no clock source (**70**
  says not until something wants one an alarm cannot do). The endpoint accepts
  a JSON body and ignores it, so a script written today survives **72**.

- ~~**A named look built from a preset arrived empty**~~ - 2026-08-26.
  Reported as "it always defaults to selecting single colour, which removes the
  other colours in a sequence, and they don't come back".

  **`modeEditor.js` read `preset.effect`, and most presets do not have one.**
  105 of the 142 look presets are sequence-only and carry `stops` instead, so
  `.effect` was `undefined`, `_addLook` spread it into `{}`, and the new look
  was genuinely empty - which is why the editor showed *single colour* (an
  empty object has no stops) and why the colours never came back (they had
  never been copied anywhere). It now goes through `presetLook`, which is
  `sequence || effect` **deep-copied** - and the copy matters as much as the
  fallback, because handing over the preset's own object would have shared its
  stops array with the module-level table and let editing your look rewrite the
  preset for the rest of the session. Every other preset consumer in the app
  already used that helper; this was the one that did not.

  **Merely looking at an existing sequence never corrupted it** - checked
  against the real component, which mutates nothing on mount. The damage was
  only ever at the moment of creating one from the dropdown, which is why it
  read as "always".

  The destructive toggle underneath it was **76**, fixed below.

- ~~**76. Switching a look to "single colour" destroyed it, silently**~~ -
  2026-08-26. `switchShape` in
  [colorEngine.js](aibutton/web/static/colorEngine.js) `delete`d every key on
  a flip with nothing kept, so one accidental click on *Single colour*
  discarded a stop list you had spent ten minutes on, with no confirmation and
  nothing to recover from.

  **Fixed by parking, not by asking.** Each shape now parks the exact fields
  it is leaving in the widget's own closure - never written to the model, so
  it costs the saved config nothing - and a flip back restores them rather
  than rebuilding from the one carried colour. Only the first flip into a
  shape (nothing parked yet) falls back to that reconstruction, same as
  before. A confirm dialog would have been noise for the direction that loses
  nothing; parking fixes the direction that does.

- ~~**69. The mode list needed to fold**~~ - 2026-08-26. With eleven modes the
  side panel ran longer than the screen, and the group you were not working in
  was pure scrolling. Each group's title in
  [menu.js](aibutton/web/static/menu.js) is a button now; a click folds that
  group's body, remembered per browser via `nav-fold:<group>` in
  [prefs.js](aibutton/web/static/prefs.js) - a view preference, so it costs
  `config.json` nothing and does not survive to a scene.

  **The item's second complaint - Alarm and its kind listed twice - is
  deliberately untouched.** That is **48a** working as designed, and the real
  fix was **75**'s taxonomy, which has since landed: a reflex is its own
  object and is listed once, and only a *scheduled* app still appears twice -
  **69** is still the answer to that half.

- ~~**56. The App page led with a warning a novice could not act on**~~ -
  2026-08-26. "4 installed apps have nothing that can reach them" sat above
  every app in [menu.js](aibutton/web/static/menu.js)'s `_renderAppsSection` -
  the best line on the page for a tinkerer, a wall of alarm for someone who
  had installed one thing.

  **Deleted, not moved.** The diagnosis it was aggregating already sits beside
  the app it is about: the "Unreachable" pill on the card (`_appStatus`) and,
  per copy, exactly why (`_howReached`, "nothing opens it - bind a gesture to
  ‘Launch an app’…"). The count was reporting nothing those two did not already
  say, one level up and with less specificity. The dangling-target warning
  stays - it names a gesture pointing at an app that does not exist, which has
  no card to sit beside and is directly actionable ("Install it below").

- ~~**57. Nothing said what a press would do right now**~~ - 2026-08-26. The
  nav's live dot already knew - `active_modes` from `/api/status`, the same
  ambient resolution the dot's hover title used - but seeing it meant hovering
  a dot in a list you might not have open.

  **A line under the header's "Last: …"** (`aibutton/web/index.html`) now says
  it without being asked: `Right now: short press → Coffee count · long press
  → Focus`, one entry per bound gesture, in `GESTURES` order. No backend
  change - `active_modes` already carried exactly this, one poll away.

- ~~**55, 63, 64, 68 - four small read-back fixes**~~ - 2026-08-26, a
  low-hanging-fruit pass done on Sonnet between sessions.

  - **55.** Header no longer counts modes - "11 modes" was the one number
    nobody could act on, left over from the vocabulary item 46 retired.
    Dropped rather than recomputed, since nothing needed the exact split.
  - **63.** The flash floor's readout says `Floor: 0.30s (3.3 flashes/sec)`
    now (`schema.js`) - the word was previously only in tinker-tier help text,
    for the one setting that is *honoured and warned about* rather than
    clamped.
  - **64.** The Web server settings group carries a line pointing at `/api/`
    and webui.py's own docstring for the endpoint list - zero mentions of the
    REST API existed anywhere in the UI before. Gated the same as the rest of
    that group (Tinker-tier): the fields it sits beside already are, and one
    visibility rule beat a special case for one paragraph.
  - **68.** `DeviceInfo.names_absent` (`device.py`) mirrors `.names` - what a
    device does *not* claim, from the same `CAPABILITY_NAMES` table, so no
    second list to drift. `/api/status` carries it as `capabilities_absent`
    and the header shows `(missing: …)` when non-empty - the half that
    decides whether a developer's feature will work, previously invisible.

- ~~**58, 60, 66, 67 - four more read-back fixes**~~ - 2026-08-26, another
  low-hanging-fruit pass done on Sonnet between sessions.

  - **58.** The header's pane toggle (`index.html`) relabels itself "◧ Press
    the button" and picks itself out in amber whenever the real button is
    connected but not `mock` and not `device_connected` - exactly the case
    that sends someone here. Not opened automatically - `sidepane.js`'s
    "only appears when asked" still holds - just made obvious that asking is
    the way in.
  - **60.** A failed Check/Save (`menu.js`) now switches to the first error's
    panel and mode, re-validates the freshly selected mode so its `.fld-err`
    spans populate, and scrolls the bad field into view with a brief `.fld-jump`
    outline. `_collectErrors` returns `{text, panel, mode}` per error instead
    of a bare string; the Save bar's text is unchanged.
  - **66.** Each app that reports something on exit now carries
    `summaryKeys` on its template descriptor (`schema.js`) - key names sorted
    the way `summary.clean` will actually send them over OSC, not the order
    the Python happens to build the dict in - shown as a hint under "Around
    the session" (`modeEditor.js`). Covers the five apps that report anything:
    Stopwatch, Counter, Intervals, Hot/Cold, Reaction. **Not yet mirror-tested**
    against `main.py`'s real `tally()`/summary dicts the way `readout` is
    (`test_app_readout.py`) - a manual read of the source as of 2026-08-26,
    and CLAUDE.md's own rule says that should not stay true for long.
  - **67.** A short client-side history (`index.html`, `#press-log`, 5 deep)
    keeps the last few `last_message`s in the Test panel's Press section
    instead of only the header's one line, which the next action overwrote
    before a DAW-wiring session could read it. No backend change - polls the
    same `/api/status` and appends on every value change.

  **Found in passing, not fixed**: testing 60 against the live config turned
  up three pre-existing validation failures already sitting in the saved
  file - Pomodoro's ramp colour and both Alarm/Work Alarm's "Give up after" -
  none related to this session's edits and none saved over. Worth a look next
  time that page is open; `Check` on the Modes tab will jump straight there.

- ~~**The launcher offered Alarm modes and `enter_mode` did not**~~ -
  2026-08-26. Found 2026-08-22, resolved the same low-hanging-fruit pass.
  `main.py`'s `enter_takeover` dispatches `AlarmBehavior` through the same
  `ring_alarm` either way a mode is entered - by its schedule or by hand - and
  `launcher_targets` (filtering on `TAKEOVER_BEHAVIORS`) already offered Alarm
  as a manual target on that basis. The `enter_mode` action's own target
  picker (`schema.js`) was the odd one out: it filtered on
  `startedBy: 'gesture'`, a field describing a mode's *default* activation,
  not whether a gesture can enter it - which happened to exclude Alarm too.

  **Fixed by widening the picker to match what `enter_takeover` actually
  dispatches**, not by narrowing the launcher: `enter_mode`'s options are now
  every `TAKEOVER_TEMPLATES` entry except `reminders`, the one template with
  no `enter_takeover` branch at all (it would fail clean with "not a takeover
  mode" if targeted, which is why it stays excluded rather than the
  inconsistency going the other way). Verified live: Alarm and Work Alarm now
  appear in a gesture's "App to launch" picker; Reminder still does not.
  No backend change - `enter_mode`'s dispatch already accepted an Alarm
  target, the UI just never offered it.

- ~~**54. The Lights tab opened five colour editors at once**~~ - 2026-08-26.
  The named-look pool got a collapsed row years ago for exactly this reason;
  the five system states still rendered fully expanded, the same problem in
  the first place a novice lands.

  `_renderStateRow` (`menu.js`) mirrors `_renderLookEntry` exactly - swatch,
  name, summary, one **Edit**/**Done** toggle, one open at a time
  (`_expandedState`) - minus Duplicate/Delete, which a fixed system state
  does not have.

- ~~**59. There was no way to see the JSON**~~ - 2026-08-26. Export downloads
  a scene and Import replaces one; neither answers "what does this control
  actually write" without leaving the page.

  A **View raw JSON** toggle on the Device tab (`_renderRawJson`, `menu.js`)
  shows the working copy as formatted, read-only JSON, plus **Copy**. Nothing
  new to load - it stringifies `this.model`, the same object every other
  control already edits.

- ~~**61. The named-action pool was invisible until you knew it existed**~~ -
  2026-08-26. An empty picker under a gesture's "Use a named action" described
  in prose where the pool was, on a page that already scrolled.

  A **Make one** button (`modeEditor.js`'s `_namedActionField`) creates a pool
  entry and points the gesture at it in one click, through the same
  `_addAction` the pool's own "+ Add" button now calls
  ([menu.js](aibutton/web/static/menu.js)) - one path to a new entry, not two.

- ~~**A control surface's DAW commands appeared wiped on reload**~~ -
  2026-08-26. Reported as settings that "save and appear to update the button
  but when I re-open the page, the settings appear wiped".

  **Nothing was ever wiped, and no config on disk was damaged** - the notes,
  channels and ports were correct the whole time. `daw_command` is a *preset
  inserter*: it fills in the real fields and is deliberately not round-tripped,
  which is the right lifetime for "this is how the number got there". But the
  widget recovered its selection only by reading that dropped key, and **every
  raw MIDI field is Tinker-tier and hidden** - so after any save the dropdown
  was the only control on screen for that gesture, and it reverted to
  "- start from… -" while the button went on sending the right note.

  Fixed by making the preset recognisable again from what it wrote: a `derive`
  hook on the field spec, pointed at `dawCommandFor` - the reverse lookup
  `describe()` had been using all along to show "Play" beside note 94.

  **The MIDI numbers were also doubted and are correct.** The MCU table is
  internally consistent, has no duplicate note numbers across 60+ entries, and
  every gesture's label matches its own number. The doubt was almost certainly
  caused by this bug: with the labels blanked there was no way to confirm at a
  glance what each gesture sent. If a DAW still ignores a command, README's
  note applies - the port has to be added as a **Mackie Control**, not as a
  new keyboard.

- ~~**47. Read the menu back from three points of view**~~ - 2026-08-26. Three
  personas walked the finished shell. **Fifteen improvements are items 54-68**;
  what follows is only what got fixed on the way.

  **Three dead ends, and the third had been live for seven hours.**

  - **A curated launcher menu could not survive being looked at.** `targets` is
    a textarea, so the editor writes a string; `_parse_launcher_body` accepted
    only a list, so opening a launcher in the web UI and saving reverted it to
    "offer every app" - error in the log, nothing in the UI. `cues` had taken
    both shapes since 52a *and said so in a comment pointing at this bug*.
    Now a rule in CLAUDE.md rather than a comment.
  - **A heading with nothing under it.** All three "Web server" settings are
    tinker-tier, so a basic user got the title and blank space. A group is now
    tinker-tier when every field in it is - derived from the specs, so a group
    that gains a basic field starts showing again on its own.
  - **A ringing alarm could be seen and not acted on.** The badge pulses red,
    the only presses live behind a toggle labelled *Test panel*, and the button
    was disconnected - so there was nothing in the room to press either. Found
    with a real alarm that had been ringing since 07:00. There is a **Dismiss**
    button in the header now, shown for `ALARMING` and nothing else: any press
    dismisses an alarm, so it is an ordinary short press rather than a new
    endpoint. Every other takeover is something you chose to open and can leave
    with a long press, and a page-wide "get me out" would compete with the
    button itself.

  Also fixed, found by the suite rather than the walk: the **5AM alarm preset
  was unsaveable**. It hand-listed its fields and predated `grace_minutes`, so
  the editor's own check refused it the moment it was added. It spreads the
  template defaults now, like every other preset.

  **What it did not cover, deliberately:** touch targets. 42 already settled
  that they need a hand and a real phone.

- ~~**53. The Events page grows sub-tabs and charts**~~ - 2026-08-26. The table
  keeps its place as the default view and gains three sibling pages - Overview
  & Activity, Mode & Time, Patterns & Metrics - carrying nine charts. Verified
  against the live log (380 rows): zero overflow at 375 and 1280, every view.

  **The two decisions the item pre-answered held.** No library: every chart is
  hand-rolled, no build step, no runtime dependency. Aggregation is client-side
  and there are no new endpoints - the same grouping logic in Python *and*
  JavaScript would be a mirrored table with no test behind it.

  **The open question is answered: the offline editor gets none of it.** It has
  no service and therefore no events, so `eventCharts.js` is simply not in
  build_editor's entry list - the seam `sidepane.js` already sits on. Verified
  by serving the bundle and driving it.

  **Mostly not SVG, which is where this departs from the item's own
  recommendation.** Text inside a `viewBox` scales with the box, so an 11px
  label is 6px on a phone - unreadable rather than overflowing, which no
  measurement catches. Rule now in CLAUDE.md.

  **Two things the data would have got wrong**, both now pinned by tests:
  summing `timer_stop` *and* `mode_exit` double-counts a stopwatch, and
  `toISOString().slice(0, 10)` files evening events under tomorrow for everyone
  not on UTC.

  The fetch bug the item named is fixed: `/api/events` defaults to 50, so every
  caller now states its own limit. The table draws 200 of them and says "200 of
  380 rows" when that bites.

- ~~**51. Apps with real interfaces**~~ - 2026-08-26. An app's page is the app
  now, not just its settings: what it has done sits above the knobs. **Zero
  Python** - it reads `/api/events` and the config, which is exactly the line
  the item drew.

  **Two halves.** A stopwatch shows its runs compared against each other -
  bars, best and worst, and each run's delta against the one before it. And an
  app with more than one item lists its siblings, so you move between your two
  alarms from inside the alarm. Two or more, like the nav's grouping: a row of
  chips holding only the item you are looking at says nothing.

  **Declared as data, so it is not a stopwatch feature.** Thirteen templates
  carry a `readout`, and a new app gets a history by adding four keys.
  `measure` has four values because `value` is one untyped column - and the
  reason `outcome` exists is that an alarm's 0/1 must be counted, never
  averaged into "0.86 alarms".

  **`better` is null far more often than not**, and that is the point of it
  being nullable: a tempo has no good end and neither does a countdown's
  length. Only a game declares one.

  **The exact-name filter is client-side on purpose.** `/api/events?name=` is a
  substring match - right for a search box, wrong for "this counter's rows",
  where a counter called `water` would quietly absorb `water_reminder`.

  Found while walking it: `noun + 's'` gave "presss", "guesss" and "launchs".
  One `plural()` in format.js, because a `plural` key on twelve descriptors to
  fix three of them is a field nobody reads.

- ~~**48c. The editor reads as an app and its items**~~ - 2026-08-25. The nav
  groups by app and the App page lists the copies; a mode's own page was the
  last screen still calling one of them a mode. Its head now names the app
  (ALARM, INTERVALS) and the name field says what it is naming.

  **Delete says the item's name, not its kind.** "Delete this alarm" was fine
  and "Delete this intervals" and "Delete this hot / cold" were not - a label
  built from a template name has to survive every template. `Delete "Wake up"`
  survives all twelve and says exactly what is about to go.

  Vocabulary only. No data changed, which is the whole point of it being
  separable from **48b**.

- ~~**44. Dead man's switch - an alarm that acts when you *don't* answer**~~ -
  2026-08-25. Two fields on `AlarmBehavior`: `grace_minutes` and `on_timeout`.
  With no grace period it is today's alarm, byte for byte - the switch is
  opt-in, and a test pins that.

  **The mechanism was already next door, inverted.** `run_reminder`'s timeout
  branch says a timeout is not a clear, *because nobody saw it*; this is that
  sentence turned around - nobody saw it, so tell someone. It hangs off the
  alarm rather than the reminder because the alarm **insists** (it loops, it
  snoozes) where a reminder gives up.

  **A preset, not a template**, which is the whole point: the alarm already
  rings and already waits, so the switch is two fields. What the preset buys is
  **findability** - nobody looking for a dead man's switch would think to open
  an alarm and read its fields.

  **`on_timeout` is a binding, not a field.** There is no `kind: 'action'`
  widget and there should not be one: an action bound to something that is not
  a press is exactly what a hook already is, so it reuses that sub-editor
  through a new **`bindings`** key on the descriptor. It offers `HOOK_ACTIONS`
  only - `enter_mode`, `readout` and `standby` change what the mode loop does
  next, and there is no loop left to change once the alarm has given up.

  **Every outcome is logged, not just the dismissal.** `dismiss_event` now
  writes `value: 1` when answered and `value: 0` when not - same event name,
  both outcomes, one place to look. A switch that fires while nobody is
  watching is only worth having if the record says what happened.

  **It depends on this host being awake and its whole point is firing while
  nobody is watching.** Service stops, machine sleeps, Bluetooth drops - it
  does not fire, and cannot know it did not. Said plainly in the editor hint,
  commented at the dataclass, and the reason for the logging above. *It is a
  nudge, not a safety device.*

  Verified through `main.run` with the clock parked on the alarm's minute:
  answered runs nothing, unanswered runs the action, it stops ringing once it
  has given up, and `grace_minutes: 0` still rings forever.
  [test_dead_man_switch.py](tests/test_dead_man_switch.py).

- ~~**52a. A light show app**~~ - 2026-08-25. A playlist of named looks,
  walked on a clock. Short press is the next cue, **double tap holds** it on
  the one you liked, long press leaves.

  **Why it earned a template rather than a preset**, which was the first thing
  triage checked: everything else about a show is already data - a look can be
  a stop list, and a stop list already fades, holds and loops. What no existing
  template can do is **advance on its own**. A Signal light waits for a press;
  a look, however long, is one look. The clock is the only new thing, and the
  clock is the code.

  **A cue names a look; it never carries one** - the opposite of a Signal
  position, for the opposite reason. A position is a status you invented and
  nothing else could mean it, so it carries its colour inline. A cue wants the
  *rich* form, which only exists in the pool, and naming one means retuning
  "Ember" retunes every show using it.

  **It owns no `LEDState`**: each cue is pushed as an ephemeral effect over
  LISTENING, exactly as a Signal position is, so the whole app cost **no wire
  code** and stores nothing on the device.

  **The dwell has a floor of its own (1s), and needed one.** `sequence_safe`
  governs how fast a look flashes *inside itself*; nothing watched how fast the
  show swaps between looks, so a `dwell_s: 0.05` would have been a strobe the
  existing guard could not see.

  **Verified against a real run loop**, not just the dataclass: enters on the
  first cue, short press advances, **advances on the clock with no press**,
  double tap holds it through a full dwell, long press returns to IDLE, and an
  empty show reports an error instead of spinning. [test_lightshow.py](tests/test_lightshow.py)
  covers the same six plus the parser rules.

  **(b), per-pixel ring patterns, remains a proposal** and is unchanged by
  this: the ring is still one lamp, and (a) is what says whether it needs to
  stop being one.

- ~~**50. A colour on the app pickers**~~ - 2026-08-25. "Launch an app" is a
  button and a list of buttons now, not a `<select>`: each option carries the
  same live swatch the nav and the App page paint, plus what that app does.
  A `<select>` could never do it - an `<option>` holds text, and the half of a
  look that identifies it is the **movement**. "The slow blue one" is how
  anyone actually refers to a mode.

  **A widget kind (`modeSelect`), not a special case in the picker**, because
  capability is declared as data here: anything that comes to pick a mode asks
  for that kind and gets the swatch. The options are real buttons, so Tab and
  Enter work without a listbox implementation; Escape closes and hands focus
  back.

  **`modeLook` moved into [schema.js](aibutton/web/static/schema.js)** and the
  nav's private copy became a call to it - three places now answer "what
  colour does this run in?" with one function, which is the rule the colour
  engine already sets. A target naming a mode that no longer exists shows as
  **"(missing)"** in amber rather than as unset, because the parser warns
  about exactly that and the editor must not disagree with it.

  **Fixed while here, and it was a live bug**: 48a made `navButtons` a list of
  rows per mode, and the rename handler still treated it as one row - typing in
  a mode's name threw. Each row now also remembers *which line it shows*, so a
  rename cannot swap a Reflex row's trigger for a template summary.

  **The web UI's own assets are served `no-store`.** There is no build step and
  no hashed filenames, so an edited module keeps its URL - and a browser that
  caches it runs last week's editor against this week's service. An ES module
  graph is cached per URL, so a reload will not shift it, which makes the
  failure look exactly like the edit not having happened. It cost real time
  twice in one session. Needs a service restart to take effect.

  **Not done, deliberately:** the launcher's target list. It is a textarea of
  free-typed names, and turning it into a multi-select is a different job from
  putting a colour on a picker.

- ~~**49. An App management page**~~ - 2026-08-25. A fourth destination
  listing every app as **Available**, **Installed** or **Unreachable**, with
  each installed copy showing *how* it is reached ("Triple tap → Home", "at
  07:00 Mon-Fri") or what to do if it is not.

  **Reachability is a walk, not a filter, and that is the whole value.** Roots
  are the things nobody has to start - a gesture map is live by definition, a
  clock starts its own apps - and everything else is reachable only by being
  pointed at. It is **transitive**, because a launcher you cannot open cannot
  open anything either. `reachableModes` is pure over data
  ([schema.js](aibutton/web/static/schema.js)), so it is the same kind of
  function as `rules.py`, and it resolves **named actions** on the way -
  `findEntryPoints` never did, so a gesture holding a pool entry read as going
  nowhere.

  **It found four real faults in the live config the moment it rendered**:
  Counter, Metronome, Intervals and Reaction stranded with nothing able to
  open them, and a long press pointing at a "Launcher" that does not exist.
  That is the case for the page in one screenshot - none of it is visible from
  any single mode's card.

  **Installing a launcher nobody can open fixes nothing, and the page says
  so.** Verified both ways: install it and the four stay stranded; point one
  gesture at it and all four flip to reachable as the walk runs through it.

  **Two verbs under the mode list, not one.** "+ Add mode" became **"+ Add
  reflex"** and **"Manage apps →"**, because writing a gesture map and choosing
  between twelve apps are not the same act. The ready-made picker went with it:
  its fourteen presets are now what **Install** offers, so choosing an app and
  choosing which *kind* of it you want stopped being two controls in two
  places.

  **The offline editor got the page too, rather than a second code path.**
  Removing the picker had quietly left it with no way to add an app at all -
  the mount is optional, and it was resolving to nothing. It now has the panel,
  the tab, and the `button:show-panel` listener that makes "Manage apps"
  more than a dead button there.

- ~~**48a. Alarms stop looking like five apps**~~ - 2026-08-25. Presentation
  only: no `config.py`, no `main.py`, no wire. Two alarms now read as
  **"Alarm (2)"** with both nested under it, and grouping starts at two -
  a header over a single child doubles the list to say nothing, and one
  stopwatch really is one stopwatch.

  **A mode may be listed twice, and that is the point.** The two groups
  stopped being boxes a mode falls into and became two questions - *what
  wakes the button up*, *what can it run* - so an alarm answers both and
  appears under both. `startedBy: 'schedule'` is the test rather than a list
  of templates, because it is already the descriptor's answer to "does a
  person start this?", so a new clock-started template joins the Reflexes list
  with no edit to the nav.

  **The two listings must not read identically**, or the second looks like a
  duplicate rather than a second answer: the Reflex row shows the *trigger*
  ("at 07:00 Mon-Fri"), the Apps row shows the template summary.

  **Reflexes is two sections, because only one of them is a queue.** A gesture
  map is read top-to-bottom, first match wins, and its order is a setting the
  blurb tells you to use. A scheduled app's position means nothing. Run
  together they read as one priority list and someone would reasonably drag an
  alarm up the page expecting it to matter - so anything a clock owns sits
  below its own **"On a schedule"** label, and the blurb now says so. *The
  blurb was the bug: it promised priority ordering over a list that had just
  stopped being one.*

  `navButtons` maps a mode to a **list** of rows, not one row. Both consumers
  walk it; with a bare entry the second row silently replaced the first and
  only one of a mode's two rows ever lit its live dot.

- ~~**45. The modes list is the side panel; the page opens on Events**~~ -
  2026-08-25. The tab bar is gone. The side panel is the whole navigation -
  Events, Lights, Device, then every mode under **Reflexes** and **Apps** -
  and the main pane shows whichever one you picked. **One nav, not two**: the
  mode list used to be a second 250px nav *inside* one of four tabs, so
  reaching a mode was two choices and the list vanished the moment you looked
  at anything else.

  **`mounts.nav` is optional, and that is what keeps the offline editor
  alive** - with nowhere to put the nav it renders inside the panel exactly as
  before. `menu.js` **asks** the shell to show the modes panel
  (`button:show-panel`) rather than reaching for its tab state; rule in
  [CLAUDE.md](CLAUDE.md).

  **The test panel is a popover** hanging off the header, not remembered
  between loads - appearing unasked is the column it replaced. Closes on
  Escape, the toggle, or a click outside; clicks *inside* keep it up, because
  pressing the simulated button four times running is the main thing anyone
  does in there.

  **The narrow layout was rebuilt, and the bug it had was invisible.** Stacked,
  the fixed-height frame gave the work surface zero height - nothing
  overflowed, so 42's measurement passed while the page rendered empty. Below
  900px the shell is a scrolling document now. The override that fixed it
  *also* failed silently first, sitting above `.tab-panel { position:
  absolute }` at equal specificity - the second time this stylesheet has lost
  that argument. Both rules are in CLAUDE.md.

  Left for **47**: the Actions pool still sits at the foot of the mode page
  rather than having a destination of its own, which is a thing to look at
  once someone reads the nav cold.

- ~~**46. What the two kinds of mode are called**~~ - 2026-08-25.
  **Takeover → App, Everyday → Reflex.** Half of it was decided elsewhere
  already: the product line is "a button that runs swappable apps", so using
  the word now avoids renaming twice. The other group needed a word for
  *always on, fires instantly, never seizes the button* - a reflex fires
  without thinking, an app takes over. Rejected: **Hotkeys / Apps** (no
  flair), **Daemons / Apps** (accurate, asks too much of someone who has never
  met the word). The `enter_mode` action reads **"Launch an app"** and
  describes as `Launch “X”`, which is what makes the group name land - the
  gesture that starts one now says the same word the group does.

  **The copy changed and no token did.** `nature: 'takeover'`, the dataclass
  names, `TAKEOVER_BEHAVIORS`, the config key `modes` and the wire are
  untouched, so the mirrored-table tests were never in play; comments and
  docstrings keep the old words where they describe code. Files:
  `schema.js`, `menu.js`, `modeEditor.js`, README, MANUAL.

  **"Mode" survives as the umbrella noun** in generic chrome - Add mode, Mode
  name, Delete mode - because a reflex and an app are two kinds of one config
  object and the key is literally `modes`. Whether the umbrella needs its own
  word is a question for **45**, which replaces the tab bar that carries it.

- ~~**41. The colour menus say what the button will actually do**~~ -
  2026-08-23. Seven reports from using it, one cause under most of them: the
  Lights tab was describing the *palette entry* while the button wore the
  *named look*, so a working feature read as broken. The runtime was right
  throughout (`look_for` resolved it; a test now drives it end to end).

  **A named look is an option in the Style dropdown** (`__look__`), with the
  pool picker appearing only when it is chosen and the palette entry folded
  into a "what it shows with nothing connected" drawer beneath. That removes
  the second select, and with it the divider that used to sit between a state
  and its own second setting - the thing that made that setting look like it
  belonged to the next state down. The head swatch, the summary and "Show on
  the button" all follow `shownLook()`.

  **"Show on the button" plays a sequence** instead of flashing its first
  colour. `/api/dev/led` gained no driver of its own: `WebContext.show_look`
  is main's `set_led`, which already owns the cancellable task and the
  `sequence_safe` gate. With no driver attached it degrades to the first
  colour and says so.

  **A stop lost its `style`/`period_s`** (36e). Two clocks on one light, and
  no layout could say which one you were setting; everything it expressed is
  more stops, and the eight presets that used it were rewritten as stop lists -
  Rainbow Chase is better for it. The keys parse and are ignored in silence.
  `sequence_safe` is down to one axis as a result.

  **The fade moved into the gap between the two colours it crosses**, named
  from both ends - including the first gap, which is the only place the editor
  can say that a one-shot arrives out of black and a loop out of its own last
  stop.

  **The named-look pool is a list**: swatch, name, where it is worn, and Edit /
  Duplicate / Delete, with one editor open at a time.

  **A rainbow got a saturation**, riding `color2` exactly as its brightness
  rides `color` - no wire change, `CAP_RAINBOW_SAT`, zero means full. Needs a
  reflash to show on hardware.

  **The mode list shows each mode's colour** (`_modeLook`, mirroring
  `main.app_look`); a template owning no LED state gets an empty ring.

  **One fix was not a UI fix**: a look is *asserted*, not stored on the device
  like a palette entry, so an edited look sat behind the old one until the next
  press. The tick re-asserts IDLE when its resolved look changes. That rule,
  and the rest, are in [CLAUDE.md](CLAUDE.md).

- ~~**37. A `keys` action - the button types, clicks, and runs macros**~~ -
  shipped 2026-08-23, the day it was triaged. A new action, not a template: no
  protocol change, no reflash, and it joins the named-action pool and the
  lifecycle hooks for free.

  **No dependency**, which is the `midi` precedent applied a second time:
  `user32.dll`'s `SendInput` through `ctypes` does chords and clicks, so
  Windows costs nothing to support. **There is deliberately no Linux/macOS
  backend** - uinput needs root or a udev rule and macOS needs an
  Accessibility grant, and neither belonged in this change. The action is
  absent rather than broken without one.

  **The vocabulary is declared, not passed through** ([keys.py](aibutton/keys.py)):
  modifiers, media keys, navigation, letters, digits, F1-F24. A name outside it
  is a *config* error caught at load, because "type this string" is a much
  larger promise than "press this chord" - one the parser could not bound and
  the editor could not offer a picker for. Media keys are listed first and for
  a reason: they are the only ones that work with no window focused.

  **One chord, not a sequence.** A list with delays is **33**, and `keys`
  becomes a step inside it rather than growing its own second implementation.

  **Permanently host-local**, which matters for **40**: moved to a Pi it types
  into the Pi. That is what synthesizing input means, not a bug to fix.

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
  style per stop (**removed again in 41** - it was two clocks on one light),
  and `drive`. **Walked versus sampled turned out to be the
  real distinction, not the unit**: `plan_at` walks and returns a wait,
  `sample_at` samples and returns none. Precedence is named stop list > ladder
  > ramp. The rules are in [CLAUDE.md](CLAUDE.md).
  **That last thread closed in 19c** (2026-08-23): `run_pomodoro` has a
  repainting tick now, so it supplies `progress` too - per state, which is
  what lets WORKING be driven while RESTING keeps a plain colour.

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
