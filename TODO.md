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
8. ⏳ **Hardware Validation (ESP32)**: feasibility assessed and documented
   (DESIGN.md — yes, an ESP32-C3 + I²S DAC/amp can run this). Actual firmware
   port is the deferred future refactor; the mode machine, store, and config
   schema are platform-agnostic and carry over.

## Remaining / future

- ESP32-C3 firmware port: reimplement the GPIO/LED/audio/BLE I/O layers and the
  generative audio synth; reuse the mode machine, store, and config schema.
