# Design: the mode machine

**Status: shipped — this document is history.** It is kept for *why the mode
machine is shaped this way*. It is **not** a schema reference: the config
schema is declared in [schema.js](aibutton/web/static/schema.js) and parsed by
[config.py](aibutton/config.py), which are the only authoritative statements of
it and are drift-tested against each other. The hardware split that followed is
[DESIGN-ESP32.md](DESIGN-ESP32.md); the forward plan is
[ROADMAP.md](ROADMAP.md) and [ARCHITECTURE.md](ARCHITECTURE.md), where "mode"
becomes "app" and templates stop being a core concern.

## The idea in one line

> The button is always in some **mode**. A mode decides what the gestures do
> and how the device looks and sounds. You build the device by defining modes
> and the triggers that switch between them.

Three primitives:

1. **Mode** — a named personality. Owns the gesture→behaviour map, the
   presentation, and any live state. Exactly one mode is active at a time.
2. **Activation** — what turns a mode on: a clock time, a recurring window, or
   being entered from another mode. At least one mode is always-on and is the
   floor everything falls back to (today it is **Home**; see TODO 5, which made
   that a structural invariant rather than a stored flag).
3. **Behaviour template** — *what kind* of mode it is, as a registry.

## Two natures of mode

The template determines a mode's nature; it is not stored separately.

- **Ambient** (`actions`) — passive. It only *answers* gestures while it is in
  scope, which is first-match-wins rule resolution.
- **Takeover** (everything else) — the device *enters* it and it **owns the
  button** until an exit gesture, then control falls back to the ambient layer.

"While the alarm rings, the button means *stop*" stopped being a special case
and became Alarm being a takeover. The same machinery gave stopwatch and
counter for free — and, later, eight more apps.

## Why this abstraction

The same open/closed move already made for actions: a registry of templates,
with the menu rendered from it. Alarms stopped being a bolt-on section and
became one template among several, so new modes are registry entries rather
than new config sections. The surface stays small as capability grows.

The evidence it was right is that every template added since — pomodoro,
metronome, countdown, launcher, control, signal, two games — landed as registry
entries. The evidence it is not *finished* is that each still costs four to six
files; making a template cheaper than that is Stage 3's job
([ARCHITECTURE.md](ARCHITECTURE.md)).

## Decisions baked in

- **"Enter a mode by gesture" is an `enter_mode` action**, not a separate
  activation type — which keeps activations to three real kinds.
- **Counter increments log an event per press**, reusing counts and streaks
  rather than adding a store table.
- **A scheduled alarm firing during another takeover preempts it.**
- **Legacy configs keep loading.** v0.1 `commands` and v0.2 `rules` convert to
  `modes` on read. A gesture mapped to the old `alarm` *action* cannot be
  converted — there is no fire time to synthesise — so it is dropped with a
  loud warning, which is the same per-key fallback discipline the parser uses
  everywhere.
