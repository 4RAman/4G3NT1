# Design: the mode machine

Status: **built** (Phases 1–3 shipped). This is the cross-phase reference for
the button's **mode machine** — the rework from a flat *rules + actions* model.
The schema and runtime described here are live in
[config.py](aibutton/config.py) and [main.py](aibutton/main.py); the Phase 3
section at the bottom records what landed most recently. The body below is kept
as the original design narrative.

## The idea in one line

> The button is always in some **mode**. A mode decides what the three
> gestures do and how the device looks and sounds. You build the device by
> defining modes and the **triggers** that switch between them.

Everything the device can do collapses into three primitives:

1. **Mode** — a named personality. Owns the gesture→behaviour map, the
   LED/sound presentation, and any live state (a running timer, a tally).
   Exactly one mode is active at any moment.
2. **Trigger (activation)** — what turns a mode on: a specific clock time,
   a recurring time-window, or being entered from another mode. One mode is
   the **Default** — always on, the floor everything falls back to.
3. **Behaviour template** — *what kind* of mode it is. A registry, exactly
   like the action registry today: `actions`, `alarm`, `stopwatch`, `counter`.

## Two natures of mode

The template determines a mode's *nature* (it is not stored separately):

- **Ambient** (`actions`) — passive. It only *answers* gestures while it is
  in scope. This is exactly today's first-match-wins rule resolution.
- **Takeover** (`alarm`, `stopwatch`, `counter`) — the device *enters* it
  (via a time trigger or an `enter_mode` action) and it **owns the button**
  until an exit gesture, then control falls back to the ambient layer.

"While the alarm rings, the button means *stop*" is no longer a special
case — it is just Alarm being a takeover mode. The same machinery gives
stopwatch and counter for free.

## Why this abstraction

It is the same Open/Closed move already made for actions in
[schema.js](aibutton/web/static/schema.js): a registry of templates, with the
menu rendered from it. Alarms stop being a bolt-on section — they are one
template among several. New modes (Pomodoro, dice, checklist…) become new
registry entries with no menu rewrite and no new config section, which is the
whole point: the surface stays small as capability grows.

---

## Config schema (v0.3 — `modes`)

`rules` is replaced by `modes`. A mode is `name + template + activation +
template-specific fields` (fields stored flat, mirroring how actions store
their fields today).

```jsonc
{
  "modes": [
    {
      "name": "Default",
      "template": "actions",
      "activation": { "type": "always" },
      "short_press": { "action": "prompt", "prompt": "...", "label": "..." },
      "long_press":  { "action": "enter_mode", "target": "Focus" },
      "double_tap":  { "action": "log", "event": "water" }
    },
    {
      "name": "Morning meds",
      "template": "actions",
      "activation": { "type": "window", "between": ["05:00", "07:00"],
                      "days": ["mon", "tue", "wed", "thu", "fri"] },
      "unless_logged_today": "meds_taken",
      "double_tap": { "action": "log", "event": "meds_taken" }
    },
    {
      "name": "Wake up",
      "template": "alarm",
      "activation": { "type": "schedule", "at": "07:00",
                      "days": ["mon", "tue", "wed", "thu", "fri"] },
      "message": "Wake up", "label": "", "snooze_minutes": 9,
      "dismiss_event": "woke_up"
    },
    {
      "name": "Focus",
      "template": "stopwatch",
      "activation": { "type": "manual" },
      "log_as": "focus"
    },
    {
      "name": "Water count",
      "template": "counter",
      "activation": { "type": "manual" },
      "event": "water"
    }
  ]
}
```

### Activation types

| type | nature it pairs with | fields | meaning |
|---|---|---|---|
| `always` | ambient | — | the base Default; exactly one mode has this |
| `window` | ambient | `between` `[HH:MM, HH:MM]`, `days?` | active while inside the window (may cross midnight) |
| `schedule` | takeover | `at` `HH:MM`, `days?` | fires (enters the mode) at that clock time |
| `manual` | takeover | — | never auto-activates; reached only via an `enter_mode` action |

The menu offers only the valid activations for the chosen template
(ambient → always/window, takeover → schedule/manual).

### Behaviour templates

| template | nature | fields | gestures |
|---|---|---|---|
| `actions` | ambient | per-gesture action objects, `unless_logged_today?` | each gesture runs its action primitive |
| `alarm` | takeover | `message`, `label`, `snooze_minutes`, `dismiss_event` | any press dismisses; long-press snoozes if set |
| `stopwatch` | takeover | `log_as` | short = lap; long = stop & exit |
| `counter` | takeover | `event` | short/double = +1; long = exit |

### Action primitives (the `actions` template body)

The existing primitives are unchanged — `prompt`, `log`, `timer_toggle`,
`webhook` — **plus one new primitive**:

- **`enter_mode`** `{ target }` — switch into the named takeover mode. This is
  how a gesture starts a stopwatch/counter, so "entered by a gesture" needs no
  special trigger type; it is simply an action that switches modes.

The standalone `alarm` *action* is **removed** — alarms are now a template.

---

## Runtime (main.py)

### State

The run loop gains one piece of state: an optional **active takeover mode**
(plus that mode's live state — elapsed timer, counter value).

### Resolving a gesture

1. **Takeover active?** → route the press to that mode's handler. The handler
   may exit, popping back to the ambient layer.
2. **Otherwise** → resolve against **ambient modes only** (`window` modes in
   config order, then the `always` mode), first-match-wins. This is today's
   [`resolve()`](aibutton/rules.py) almost unchanged, filtered to ambient
   modes. If the matched action is `enter_mode`, enter that takeover.

### Scheduler

The wait becomes a race of **press / shutdown / next scheduled fire**.
`_wait_for_trigger` already races press vs stop; add "soonest `schedule`
activation due, computed from `clock.now()`". When the timer wins, enter that
mode's takeover handler. A single consumer of the press queue is preserved.

- Reads time through the existing `Clock`, so the test clock drives schedules
  too — exactly what the `Clock` docstring anticipated.
- **Recompute on a short tick (≤1s).** Without this, setting the test clock to
  06:59 would not fire a 07:00 alarm until the originally-computed timeout
  elapsed. The loop wakes at least once per second (or sooner if a fire is
  imminent) and recomputes against `clock.now()`.
- Track **last-fired timestamp per scheduled mode** to avoid double-firing
  inside the same minute.
- If a scheduled alarm fires while another takeover is active, the **alarm
  preempts** it.

### Template handlers

- **actions** — today's `execute()` path, plus `enter_mode` handled inline.
- **alarm** — generalise the existing `ring_alarm()` (rename off `AlarmAction`).
- **stopwatch** — enter starts a timer (`store.toggle_timer`), LED `TIMING`;
  short = lap (a `log` event named `<log_as>_lap`), long = stop & exit (logs
  elapsed via `toggle_timer`).
- **counter** — enter resets the tally, LED `COUNTING`; short/double = +1
  (each `store.log_event(event)`, so existing `count_today`/`current_streak`
  just work), long = exit.

Both new modes **reuse the existing store** — no SQLite schema change.

---

## What changes, file by file

### Python

- **[config.py](aibutton/config.py)** — replace `Rule` with `Mode` +
  `Activation`; new `_parse_mode`/`_parse_activation`; remove `AlarmAction`
  and its `_parse_action`/`_action_to_dict` branches; add the `enter_mode`
  action; teach `as_dict`/`parse_config` the `modes` key; **migrate** legacy
  `rules` (and v0.1 `commands`) → `modes` with `template:"actions"` and an
  activation derived from `between`/`days` (→ `window`) or none (→ `always`).
- **[rules.py](aibutton/rules.py)** — `resolve()` becomes ambient-mode
  resolution (rename to suit; same first-match-wins logic).
- **[main.py](aibutton/main.py)** — active-takeover state; the 3-way
  scheduler race + ≤1s tick; per-template handlers; generalise `ring_alarm`.
- **[led.py](aibutton/led.py)** — add `TIMING` and `COUNTING` to `LEDState`,
  their animations, and register them in `_animations` (`ALERT` already
  covers alarm).
- **[store.py](aibutton/store.py)** — no schema change; stopwatch/counter
  reuse `toggle_timer` and `log_event`.
- **[webui.py](aibutton/webui.py)** — `/api/status` `rule_count` →
  `mode_count`; round-trips already flow through `as_dict`/`parse_config`.

### Web

- **[schema.js](aibutton/web/static/schema.js)** — two new registries beside
  `ACTIONS`: `TEMPLATES` (type, label, fields, defaults, describe, nature,
  allowed activations) and `ACTIVATIONS` (always/window/schedule/manual:
  fields + describe). Add `enter_mode` to `ACTIONS`.
- **[widgets.js](aibutton/web/static/widgets.js)** — **add a `select`
  widget** (static options) and support **dynamic options** (a function that
  returns options at render time) for the `enter_mode` mode-name picker.
- **[ruleEditor.js](aibutton/web/static/ruleEditor.js) → modeEditor.js** —
  uniform card: *name → template picker (body adapts) → activation picker
  (body adapts)*. The `actions` template body reuses the existing
  gesture×action sub-editor; the `window`/`schedule` activation bodies reuse
  the existing `_days`/`_window` editors (moved here).
- **[menu.js](aibutton/web/static/menu.js)** — render a **Modes** list of
  collapsed one-line **summaries** (`template.describe` + `activation.describe`),
  click to expand; move device settings into a `<details>` **drawer**.
- **[index.html](aibutton/web/index.html)** — `.led.TIMING`/`.led.COUNTING`
  animations and `.badge.ALARMING`/`.badge.TIMING`/`.badge.COUNTING` styles;
  dashboard reads `mode_count` instead of `rule_count`.

### Tests ([tests/](tests/))

- `test_rules.py` → ambient mode resolution.
- `test_config.py` → mode + activation parsing, `as_dict` round-trip, and the
  `rules`→`modes` migration.
- New: scheduler fires at the injected clock time; takeover preempts ambient;
  `enter_mode` round-trip; stopwatch/counter handlers.

### Sample config

[config.json](config.json) currently uses the removed `alarm` *action*; it
will be rewritten to a `schedule`d alarm mode plus a Default actions mode.

---

## Migration & back-compat

- Legacy `rules` configs load and are converted to `modes` on read (window
  activation from `between`/`days`, else always). v0.1 `commands` still loads
  via the same path.
- A gesture mapped to the old `alarm` **action** cannot be converted (no fire
  time to synthesise), so it is **dropped with a loud warning** on load — the
  same per-key fallback discipline the parser already uses.

## Decisions baked in (flag any to revisit)

- "Enter a mode by gesture" is an **`enter_mode` action**, not a separate
  trigger type — keeps triggers to three real kinds.
- Counter increments **log an event per press** (reusing counts/streaks)
  rather than adding a store table.
- A scheduled alarm firing during another takeover **preempts** it.
- Old `alarm`-action configs are **dropped with a warning** on load.

## Phasing

| Phase | Scope |
|---|---|
| **1** | Mode model + ambient resolution + **scheduler** (with ≤1s tick), `actions` + `alarm` templates, `always`/`window`/`schedule` activations, the **collapsible Modes menu + Device drawer**, `select` widget, migration, remove the `alarm` action, tests. → *ships scheduled alarms and the whole new UX.* |
| **2** | `stopwatch` + `counter` templates, `manual` activation + the `enter_mode` action, `TIMING`/`COUNTING` LED states, tests. → *pure registry additions.* |
| **3** | `pomodoro` template (assignable gestures), counter **increments**, the **5-tap** global on/off + takeover escape, the **permanent locked Default** floor, interval-based **feedback sounds**, `OFF`/`POMODORO_WORK`/`POMODORO_BREAK` LED states, tests. → *shipped; see below.* |

---

## Phase 3 — implemented

The TODO.md feature set landed on top of the mode machine. Highlights and the
choices baked in:

### Pomodoro template (`pomodoro`)

A fourth takeover template, `manual` activation, reached by an `enter_mode`
gesture exactly like stopwatch/counter (registry addition, no new wiring). A
work→break countdown that **auto-repeats**; each completed work block is logged
via `store.log_duration()` (a `timer_stop` row) so `total_today` accumulates
focus time with no schema change. Its three gestures are **assignable** to
commands `start_pause` / `restart` / `extend` (stored flat as
`short_press`/`long_press`/`double_tap` = command string, mirroring how actions
store fields). Defaults: short = start/pause, long = restart, double = +10 min.
The async handler races press vs a ≤1 s display tick (same pattern as the
scheduler) and reads `loop.time()` for the countdown.

### Counter increments

Each gesture adds its own configurable amount (defaults short +1, long +10,
double +20) instead of a flat +1. To keep `count_today` accurate without
inflating the table, the store gained a `count` column (default 1, migrated
onto older DBs with `ALTER TABLE`); `+N` is one row, `count_today` sums it.

### The 5-tap gesture — global on/off + takeover escape

The button's reassignment of long-press (counter +10, Pomodoro restart) left
takeovers with no per-gesture exit, so a **fifth gesture** was added.
`TriggerDetector` was generalised from "double-tap special case" into a
**tap-chord counter** that resolves on the inter-tap timeout: 1→short, 2→double,
5→`quintuple_tap` (fired immediately on the 5th press); 3 and 4 are ignored. The
5-tap is **contextual escape** (the chosen model): during a takeover it exits to
the ambient layer; on the Default it toggles the device **off** (LED dark,
gestures ignored, `OFF` state) and **on** again. Scheduled alarms still fire
while off (it is an alarm clock), returning to off when dismissed. `quintuple_tap`
is deliberately **not** in `TRIGGER_TYPES` — it is reserved, never mode-mappable.

### Permanent, locked Default (priority for overrides)

`resolve()` is unchanged: priority is still **config order, first-match-wins**.
"Locking the Default to Always" is realised as: the built-in set and the web UI
guarantee exactly one always-`actions` mode, **pinned last** (the lowest-priority
floor), with its delete/move/activation locked in the editor and new modes
inserted **above** it so they override it. The built-in set now ships 5AM Alarm,
Gratitude counter, Stopwatch and Pomodoro, all reachable from the Default's
`enter_mode` gestures.

### Feedback sounds — decision (TODO 7)

The "Smart Button Sound Design Research" doc targets a generative ESP32-C3 DSP
synth (wavetable morphing, exponential ADSR, IIR portamento, MIDI playback).
That belongs to the ESP32 refactor, not the Pi today. The **decision for now**:
apply the doc's *principles* in a lightweight, dependency-free way on the Pi —
rebuild the stdlib-`wave` tone bank around the doc's **musical-interval
semantics** (rising P5 = success, falling tritone = error, root-P5-octave
wake / its inverse sleep, P4 phase chime) in the upper-mid "sweet" register with
a soft exponential ping decay, and add the doc's **micro-variation** as a
round-robin bank of jittered renders (the sample-based stand-in for live
generative variation) to dodge the "machine-gun" fatigue effect. The full DSP
engine is captured below as future ESP32 work.

### ESP32 audio + hardware assessment (TODO 8)

Deferred per the project direction ("Python on the Pi is fine for now"), but the
research answers the feasibility question: **yes**, an ESP32-C3 can drive these
features. The synth runs as a FreeRTOS task feeding I²S DMA buffers into a
MAX98357A class-D amp; with fixed-point / minimised-float wavetable synthesis,
target-ratio exponential envelopes, first-order IIR portamento and cubic soft
clipping it fits the single RISC-V core alongside the BLE/Wi-Fi stacks. When the
firmware is ported, `audio.py`'s `Sound` enum + interval definitions map onto
synth patches, and the round-robin variants become live parameter jitter. The
mode machine, store, and config schema are platform-agnostic and carry over;
the GPIO/LED/audio/BLE I/O layers are what get reimplemented.
