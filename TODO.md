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

## Remaining / future

- ESP32 firmware: compile/flash the hardware glue on-device, then port the mode
  machine (config.py + main.py — ambient resolution, scheduler, takeovers, the
  contextual 5-tap) and storage (NVS) behind the same interfaces. The config
  schema (config.json) and the mode logic are platform-agnostic and carry over.
  See [firmware/README.md](firmware/README.md) for the full port plan.
