# Next Updates To-Do List

Status of the feature set (implemented on the Python / Raspberry Pi build;
the ESP32 refactor is intentionally deferred). Design notes and rationale in
[DESIGN.md](DESIGN.md) (see "Phase 3 — implemented"); usage in
[MANUAL.md](MANUAL.md).

1. ✅ **Default Mode Logic**: The permanent Default is locked to "Always" and
   pinned last as the lowest-priority floor; priority for overrides is config
   order (modes above the Default override it). Enforced in the built-in set
   and the web editor (no delete/move, activation locked).
2. ✅ **New Mode: Pomodoro**: `pomodoro` takeover template — a 25/5
   auto-repeating work/break countdown; completed work blocks logged for daily
   focus totals.
3. ✅ **Built-in Modes Set**: 5AM Alarm, Gratitude counter, Stopwatch and
   Pomodoro ship by default (reachable from the Default's gestures); Default is
   permanent, the rest are removable.
4. ✅ **On/Off Toggle**: "5 taps" is a global gesture — contextual escape that
   exits an active takeover, or toggles the device off/on from the Default.
5. ✅ **Counter Mode Enhancements**: short / long / double tap count up by
   configurable increments (defaults +1 / +10 / +20), summed accurately via a
   new `count` column.
6. ✅ **Pomodoro Configuration**: assignable gestures — defaults single tap =
   Start/Pause, long press = Restart, double tap = +10:00.
7. ✅ **Sound Design**: feedback tones rebuilt around the research's
   musical-interval semantics + round-robin micro-variation on the Pi now; the
   full generative ESP32-C3 DSP synth (wavetable/ADSR/portamento/MIDI) is
   documented in DESIGN.md as the ESP32 work.
8. 🚧 **Hardware Validation (ESP32)**: feasibility assessed (DESIGN.md — yes,
   an ESP32-C3 + I²S DAC/amp can run this) **and the port started** in
   [firmware/](firmware/): the portable cores — the tap-chord gesture detector
   and the full generative synth (wavetable morph, exponential ADSR, IIR
   portamento, soft-clip, micro-variation, cue bank) — are implemented and pass
   host-native tests (`cd firmware && make test`); the I²S/LEDC/GPIO glue and a
   PlatformIO project are scaffolded (not yet compiled/flashed).

## Next 10

The next wave, roughly prioritized within each group.

### Continue the ESP32 port

9. **Bench bring-up.** Compile `firmware/src/` with the `espressif32` PlatformIO
   platform and flash a real C3 — confirm press→LED→cue and the 5-tap toggle,
   and fix whatever the uncompiled glue (`hw_audio`/`hw_led`/`hw_button`) gets
   wrong against the real I²S/LEDC/GPIO APIs.
10. **Port the mode machine.** Bring `config.py` + `main.py` over: template /
    activation / mode model, ambient first-match resolution, the scheduler, the
    alarm/stopwatch/counter/pomodoro takeovers, and the contextual 5-tap —
    loading the existing `config.json` via ArduinoJson.
11. **Port storage to NVS.** Implement the `store.py` interface (`log_event`,
    `count_today`, `current_streak`, `toggle_timer`, `total_today`,
    `log_duration`) on flash/NVS (or an SD ring log) — no SQLite on the MCU.
12. **Production-harden the synth.** Move the oscillator/envelope/soft-clip hot
    path to fixed-point (Q16) for the FPU-less C3, and swap the naive square for
    a bandlimited wavetable (both flagged in `firmware/README.md`).
13. **BLE + Wi-Fi on the C3.** Re-add the BLE peripheral and serve the existing
    web UI / REST API over Wi-Fi from the device, so one front-end drives both
    Pi and C3.

### Pi-side product & UX

14. **Stats dashboard.** Surface what the store already computes — daily counts,
    streaks, focus/timer totals (`count_today` / `current_streak` /
    `total_today`); show the counter `count` in the Recent-events table; expose
    `asleep` in `/api/status`.
15. **Selectable / tunable feedback sounds.** A "sound theme" + per-cue tuning in
    the config schema + web UI (via `audio.py`), and port the R2-D2 idle-chatter
    cue back to the Pi.
16. **Web UI auth.** The config-mutating endpoints (`PUT /api/config`,
    `/api/trigger/...`) have no auth and bind to the LAN — add an optional
    shared-token / basic-auth.

### Correctness & quality

17. **Resolve the alarm-preemption divergence.** `DESIGN.md` says a scheduled
    alarm *preempts* a running takeover, but the loop is blocked inside the
    takeover handler so it actually waits — implement preemption or correct the
    doc, with a test pinning the chosen behavior.
18. ✅ **CI + linting.** GitHub Actions runs `ruff` + `pytest`, `eslint` +
    `npm test`, and `firmware/ make test` on every push/PR
    ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

Honorable mentions (easy swaps): configurable gesture timing for accessibility;
a phone companion app over BLE; OTA firmware updates for the C3; the doc's
user-MIDI playback feature on the synth Voice.

## Remaining / future

- ESP32 firmware: compile/flash the hardware glue on-device, then port the mode
  machine (config.py + main.py — ambient resolution, scheduler, takeovers, the
  contextual 5-tap) and storage (NVS) behind the same interfaces. The config
  schema (config.json) and the mode logic are platform-agnostic and carry over.
  See [firmware/README.md](firmware/README.md) for the full port plan.
