# Session handoff — 2026-08-19 (evening)

**Delete this file once you have read it.** Nothing in it is durable: the
things that outlive the handoff are in [TODO.md](TODO.md), [CLAUDE.md](CLAUDE.md),
[ROADMAP.md](ROADMAP.md) and [ARCHITECTURE.md](ARCHITECTURE.md). Read CLAUDE.md
first — it is short, it is the house style, and several of its rules exist
because someone already broke them here.

## Where the code is

Branch **`ten-apps`**, pushed to `origin`, working tree clean at `9d4a5a6`.
`main` is still back at `b80ad82` and nothing has been merged.

**The test suite has not been run since `9d4a5a6` was written.** That is not an
oversight — see "How the user wants to work" below — but it means the first
useful thing you can do is ask whether to run it.

```bash
.venv/Scripts/python -m pytest -q
```

## How the user wants to work — read this before doing anything

- **Never run the test suite without asking first.** They will run it
  themselves; the two-minute suite is expensive in context and they said so
  directly. Write the code, hand them the command. Verify with small throwaway
  scripts instead — that is what the last session did and it worked well.
- **The service is usually already running against the real button** (BLE
  allows one central, so a second instance refuses). Do not restart it without
  asking. Note that **code changes need a restart** while config hot-reloads —
  that caused a confusing bug this session where the editor offered a MIDI
  action the running parser had never heard of.
- They are a musician using **Studio One**; the DAW work is for real use, not a
  demo. Their loopMIDI port is called `4G3NT`.
- They prefer being told what you found, including what you got wrong.

## What just shipped (all in `9d4a5a6`)

| Thing | Where |
|---|---|
| `midi` action | [midi.py](aibutton/midi.py) encodes, [midi_io.py](aibutton/midi_io.py) sends |
| 56-command Mackie Control picker | `DAW_COMMANDS` in [schema.js](aibutton/web/static/schema.js) |
| `control` template — gestures→actions as a takeover, branchable | [config.py](aibutton/config.py), `run_control` in [main.py](aibutton/main.py) |
| MIDI clock in → metronome follows the DAW's tempo | [midi_clock.py](aibutton/midi_clock.py) + `ClockListener` |

**MIDI needs no dependency on Windows.** It goes through `winmm.dll` via
ctypes, because `python-rtmidi` publishes no wheel for Python 3.14 and its
source build fails on this machine. rtmidi remains the Linux/macOS backend and
is deliberately **not** in `requirements.txt`.

## What is queued, and it is all triaged

Items **25–29** in [TODO.md](TODO.md) are new and written to stand alone. Read
them rather than this table; the table is only to say what exists.

| # | What | Size |
|---|---|---|
| **25** | Transport app that knows what the DAW is doing | Medium, and read **23** first |
| **26** | Colour-coded Actions pages; decide the launcher's fate | Medium, one real decision in it |
| **27** | Every slider also accepts a typed number | Small |
| **28** | Add the missing four-tap gesture | Small |
| **29** | Sleep, wake, hold-to-power-off | Large, blocked on **0c** |

**Suggested order: 28, then 27, then 26, then 25.** The two small ones are
independent and unblock the five-option menu page that 26 wants; 25 is the
one with a genuine unknown in it (see below). **29 cannot start** — the button
is physically de-soldered (**0c**) so nothing about wake-on-press is testable.

### The one thing worth knowing before starting 25

The user wants a single gesture to record, then later stop-and-rewind. That
needs the button to know the transport state, and **the good news is it does
not have to guess**: Mackie Control is two-way — the DAW sends note-on back to
light the surface's buttons. Point Studio One's device **Send To** at a port
the button listens on and the real state arrives. (README currently says to
leave Send To empty; that advice predates anything listening.)

Also: **MCU has no "return to zero"**. In Studio One a Stop when already
stopped goes to the start, so the gesture is *Stop, Stop* — two messages from
one press, which `MidiAction` cannot express. Check that behaviour in the DAW
before designing around it.

## Verified on hardware, and what is not

- **Verified**: Hot/Cold and Reaction (the two timing-dependent games), the
  firmware 0.6.1 press-timing fix, MIDI reaching a real port, and the clock
  round trip through loopMIDI at 96 → 140 BPM including a live tempo change.
- **Not verified**: the `control` template and the Signal light have **never
  met the button**. Both are host-side with no clock in them, so the risk is
  low — but that was also true of the offline editor, which had been broken for
  weeks while looking built.
- **Not verified**: nothing has confirmed Studio One acting on a Mackie
  command. The user saw MIDI arrive but it was being *recorded into a track*,
  which means the port was attached to a Keyboard device rather than a Mackie
  Control. That is a DAW-side setting, now documented in README.

## Two bugs from this session worth not repeating

- **A ctypes callback `del`-ed inside its own closer killed the process** —
  illegal instruction, no traceback. `del` inside a nested function makes the
  name local to it, so the closure never captured the object at all and the
  driver called freed memory. It reads like careful cleanup. Now in CLAUDE.md's
  conventions.
- **`BUILTIN_MODES` had no test**, which let a preset ship with a
  template/activation pair the parser refuses — it would have saved, been
  silently skipped, and vanished with only a log warning. Covered now in
  [test_schema_mirror.py](tests/test_schema_mirror.py). The general lesson is
  the one that file's docstring already states: **things declared twice are
  tested, not trusted**, and this codebase keeps finding new pairs.

## Loose ends

- **`control-panel.port` is tracked and should not be.** It is runtime state (a
  port number that changes every launch) and is now committed with a changed
  value. Wants `.gitignore` + `git rm --cached`. The user was asked and has not
  answered.
- **`scenes/default.json` in `9d4a5a6` carries the user's bench-test bindings**
  — short press → Reaction, long press → Hot / Cold, launcher `return_after`
  off, IDLE palette changed. That is their config riding along in a feature
  commit; fine, but do not assume it is the intended default.
- **`aibutton` is still a provisional name** (ROADMAP D7). Do not spread the
  string.
