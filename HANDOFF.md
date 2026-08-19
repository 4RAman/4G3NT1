# Session handoff — 2026-08-19

**Delete this file once you have read it.** It exists to orient one new
session and nothing in it is durable: everything that outlives the handoff is
already in [TODO.md](TODO.md), [CLAUDE.md](CLAUDE.md), [ROADMAP.md](ROADMAP.md)
and [ARCHITECTURE.md](ARCHITECTURE.md). A second permanent source of truth is
the exact failure TODO item 18 is parked to avoid.

## Where the code is

Branch **`ten-apps`**, five commits ahead of `main`, working tree clean,
**983 tests passing**.

```bash
.venv/Scripts/python -m pytest -q
```

| Commit | What |
|---|---|
| `db0a140` | Press dated at the edge (firmware); Hot/Cold wheel quantised |
| `ddd2632` | Drift audit — mirror tests added, dead code removed |
| `7cf4ccc` | One colour control; mode colour moved onto the mode |
| `91152c7` | Control panel wedge fixed |
| `581dcd9` | Ten apps: two games, a signal light, OSC, intervals |

`main` is untouched at `b80ad82`. Merge when hardware testing passes:

```bash
git checkout main && git merge ten-apps
```

## The two things to do next, both decided

Read the items — they are written to stand alone.

- **[TODO 22](TODO.md)** — build a `midi` action. Studio One does not speak
  OSC; the research is recorded in the item so it is not repeated. **Decided:
  build it**, accepting `python-rtmidi` as a dependency.
- **[TODO 23](TODO.md)** — the composition vision (apps firing actions at
  their edges, carrying their data). **Decided: write the full design into
  ARCHITECTURE.md before building any of it.** The item says why.

## What needs hardware, and why it has not happened

**The reflash is done** — firmware **0.6.1**, flashed and verified on
2026-08-19 (`/api/status` → `device_info.firmware`). The board rebooted and
reconnected on its own; no replug was needed, because `mpremote cp` copies over
the REPL and never enters download mode, so the sticky-bootloader gotcha in
CLAUDE.md does not apply to this command.

What is *not* verified is how it feels: the timing fix is proven by tests and
the flash is proven by the version, but nobody has pressed the button since.
Expect the reaction timer to read about 50 ms faster than before.

Two separate things are waiting on a bench session, and they are independent:

- **The three new apps have never met the button** (Hot/Cold, Reaction,
  Signal). That is the last thing the Stage-2 "10 apps" gate wants. Hot/Cold
  and Reaction are the first apps whose correctness depends on timing, so they
  are where a radio will surprise you; `press_latency_s` is the number to
  suspect if a press lands somewhere you did not aim.
- **TODO 0c** — the button is still de-soldered and `BUTTON_PIN` is
  temporarily `0` so the BOOT button can stand in. Putting it back to `4` and
  the 5 V LED rework belong in the same sitting.

## Findings from this session worth not rediscovering

- **The offline editor had been dead on arrival**, and not recently: two
  modules both wrote `paint as applySwatch`, the bundler emitted the binding
  twice, and the browser refused the whole script. Fixed, and the suite now
  checks the emitted bundle parses. The lesson generalised: **open the thing
  occasionally**, because both this and the earlier "sliver" bug looked built.
- **Four mirrored tables had no drift test**, in a codebase whose stated rule
  is that mirrors are tested. Covered now by
  [test_schema_mirror.py](tests/test_schema_mirror.py). Two comments even
  claimed a test that did not exist — worth distrusting that kind of claim.
- **There is no such thing as an instant press.** `max_taps_for` floors at 2,
  so every single press waits out the 0.4 s window whatever the config binds.
  It is a constant, so it is subtracted — see `ButtonDevice.press_latency_s`
  and CLAUDE.md's invariant. Never hardcode the window in an app.

## Open, unanswered

- **Phone access**: recommended a mesh VPN (Tailscale/WireGuard) over hosting,
  since the web UI has no auth and a VPN makes that moot. Nothing to build —
  `web_host` already binds `0.0.0.0`. Written up as option (d) in TODO 8.
- ~~A pair of `pythonw` processes I could not explain~~ — **resolved, and it
  was nothing.** The venv's `pythonw.exe` is a redirector stub: it launches the
  base interpreter as a child with the same command line and waits on it. The
  giveaway is the profile — the parent had 0.02 s of CPU and one thread after
  three and a half hours while the child held port 8080 with 106 s and three
  threads. The single-instance guard was never failing, and a pair is expected
  for *any* venv-launched process here. Recorded so nobody chases it a third
  time.
