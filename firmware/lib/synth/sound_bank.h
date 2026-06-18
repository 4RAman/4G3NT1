// The 4G3NT1 cue bank: the "Designing the Core Sound Bank" table from the sound
// research doc, expressed as parameterised generative patches over the synth
// Voice. Each cue carries a wavetable blend, an exponential ADSR profile, a
// glide time, and micro-variation amounts; renderCue() sequences its note
// contour (an interval relationship) into a Voice with per-trigger jitter, the
// generative replacement for sample round-robin.
//
// CueIds line up with aibutton/audio.py's Sound enum, plus IdleChatter - the
// R2-D2-style pentatonic babble the doc describes (not built on the Pi).
#pragma once

#include <cstdint>

#include "synth.h"

namespace aibutton::dsp {

enum class CueId {
  Ack,
  Success,
  Error,
  Alarm,
  Wake,
  Sleep,
  Phase,
  IdleChatter,
  Count,
};

struct Cue {
  float blend;            // sine(0)<->square(1) base
  float attackMs;
  float decayMs;
  float sustain;
  float releaseMs;
  float glideMs;          // portamento between glide notes (0 = snap)
  float pitchJitterCents; // +/- per-note detune
  float decayJitterMs;    // +/- envelope decay jitter
};

const Cue& getCue(CueId id);

// Render `id` into `out` (mono float, [-1,1]) using `voice`, advancing `rng`
// (xorshift32 state) for the micro-variation. Returns the number of samples
// written (<= cap). Deterministic for a given rng seed - handy for tests.
int renderCue(CueId id, Voice& voice, float* out, int cap, uint32_t& rng);

// xorshift32 PRNG - portable, no <random>, identical on host and MCU.
uint32_t xorshift32(uint32_t& state);

}  // namespace aibutton::dsp
