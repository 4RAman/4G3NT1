# CLAUDE.md

One physical button on an ESP32, a Python brain on the PC, talking BLE.
Read [README.md](README.md) for what it does,
[DESIGN-ESP32.md](DESIGN-ESP32.md) for how it got this shape,
[ROADMAP.md](ROADMAP.md) for where it is going, and
[ARCHITECTURE.md](ARCHITECTURE.md) for the design it is going *to* — the last
two matter more than usual here, because several cheap decisions today are
expensive ones after hardware ships. This file holds the rules that apply
regardless of what you're touching; [INVARIANTS.md](INVARIANTS.md) holds the
rest, filed by subsystem (colour & light, actions/reflexes, the nav shell,
config warnings & fields, readout & events, small gotchas, hardware) — read
its section for whatever you're about to touch, before you touch it.

## Commands

```bash
./.venv/Scripts/python -m pytest -q                       # the whole suite, no hardware needed
./.venv/Scripts/python -m aibutton.main --config config.json          # MockDevice + web UI
./.venv/Scripts/python -m aibutton.main --ble --config config.json    # the real button
./.venv/Scripts/python -m aibutton.control               # the tray control panel
./.venv/Scripts/python -m mpremote cp firmware/*.py : + reset         # flash (bash)
./.venv/Scripts/python tools/ble_probe.py --cycle        # drive the firmware by hand
./.venv/Scripts/python -m aibutton.scenes list|check|activate         # scenes, service stopped
./.venv/Scripts/python tools/build_editor.py             # dist/button-editor.html (offline)
```

**The leading `./` is not decoration.** This machine's shell is PowerShell,
where a command beginning `.venv\...` is not a path at all - it is looked up
as a command name and fails with "not recognized". `./.venv/Scripts/python`
is the one spelling both PowerShell and bash accept, so it is the one written
everywhere here.

**The flash line is the exception, and only because of the glob.** PowerShell
does not expand `firmware/*.py` for a native executable and mpremote does not
expand it either, so the literal string reaches the board and nothing copies.
In PowerShell, let the shell do it:

```powershell
./.venv/Scripts/python -m mpremote cp (Get-ChildItem firmware/*.py) : + reset
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
- Prefer things that cost nothing: `python -c` on one function, reading the
  code, and — for a browser module — a **copy to `.mjs`** before
  `node --check`. Not `node --check` on the `.js` itself; see below for why
  that one lies.
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

Cross-cutting rules — the ones any change, regardless of subsystem, tends to
run into. Topic-specific invariants (colour & light, actions/reflexes,
the nav shell, config warnings & fields, readout & events, small gotchas,
hardware) live in [INVARIANTS.md](INVARIANTS.md) — read the section for
whatever you're touching before you touch it.

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
  callback in [INVARIANTS.md](INVARIANTS.md)'s "Small gotchas", a different
  library.
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
- **A new action shape is resolved in `resolve_action`, not at each dispatch
  site.** Sequences reached all six sites without one of them being edited,
  because that function is where a binding becomes the thing that runs. *If a
  future shape needs unpacking, unpack it there.*

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
- **The JavaScript has tests now, and node is optional.** `node --test` is
  built in, so [tests/js/](tests/js/) costs no dependency;
  [test_js_modules.py](tests/test_js_modules.py) runs it and **skips with a
  reason** where node is absent, so a Python-only machine still goes green.
  The no-new-dependencies rule below is about what the *service* runs on.
  Only pure functions are tested there — anything touching the DOM is verified
  in a browser, which is the honest split rather than a gap. Pass node the
  **file**, not the directory: `node --test <dir>` resolves the path as a
  module on Windows and dies with `MODULE_NOT_FOUND`.
- **`node --check` on a `.js` file here exits 0 on code that cannot load.**
  These are ES modules in a directory with no `package.json`, so node treats
  the extension as ambiguous and a genuine `SyntaxError` comes back as
  success. It is worse than no check, because it is a check you believed: an
  unescaped apostrophe inside a `schema.js` hint string passed it and took the
  whole editor down with one console line. **The extension picks the parser** —
  copy to a temp `.mjs` and check *that*, which is what
  `test_a_static_module_parses` does for every file in `web/static` and what
  any by-hand check should do too. Copy, never rename; those files are served.
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
- **Keep [TODO.md](TODO.md) current in the same commit as the work, and move
  finished items out of it.** When an item ships with nothing left open under
  its number, move its whole write-up to
  [TODO_FINISHED.md](TODO_FINISHED.md), compressed to the choices that still
  bind — a "✔ shipped" banner above the original plan is how TODO.md once grew
  past 4500 lines of instructions nobody should follow any more. An item with
  *any* open thread — a hardware test not yet run, a "still open"
  sub-question — stays in TODO.md whole, even if most of it has shipped;
  don't split one item across both files. Two rules keep the pruning safe: a
  rule governing *future* code belongs here in CLAUDE.md, and
  TODO.md/TODO_FINISHED.md only record the decision and point at it; and item
  numbers are never reused or renumbered, because both files, ROADMAP.md and
  the commit log all cite them.
