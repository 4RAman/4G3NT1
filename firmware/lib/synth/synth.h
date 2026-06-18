// Portable generative-synthesis core for the 4G3NT1 button, implementing the
// DSP described in "Sonic Interaction Design and Embedded Audio Synthesis for
// the 4G3NT1 Smart Button":
//   * sine<->square wavetable morphing (Oscillator)
//   * exponential, target-ratio ADSR envelopes (ADSR)
//   * first-order IIR portamento / note glide (Portamento)
//   * cubic soft clipping for safe, warm summing (softClip)
//   * a monophonic Voice tying them together
//
// Pure C++17, no Arduino/ESP-IDF dependency, so it compiles and unit-tests on
// the host (see firmware/test) and on the ESP32-C3 alike. Uses float for
// clarity; production firmware on the FPU-less C3 should port the hot path to
// fixed-point (Q16) per the research doc - the algorithms are unchanged.
#pragma once

#include <cstdint>

namespace aibutton::dsp {

constexpr float kSampleRate = 44100.0f;
constexpr int kTableSize = 1024;
constexpr float kBaseHz = 880.0f;  // A5 - the upper-mid "sweet" register

// Frequency `semitones` above (or below) the base note.
float noteHz(float semitones, float base = kBaseHz);

// One cycle each of a sine and a (naive) square wave, shared by all voices.
// A bandlimited square is the production refinement; the naive table keeps the
// scaffold self-contained. Call once at startup.
void initTables();
float sampleSine(float phase01);    // phase in [0,1)
float sampleSquare(float phase01);

// Sine<->square morphing oscillator driven by a phase accumulator.
class Oscillator {
 public:
  void setSampleRate(float sr) { sampleRate_ = sr; }
  void setFrequency(float hz) { freq_ = hz; }
  void setBlend(float blend01) { blend_ = blend01; }  // 0 = sine, 1 = square
  void reset() { phase_ = 0.0f; }
  float next();  // one sample in [-1, 1]

 private:
  float sampleRate_ = kSampleRate;
  float freq_ = kBaseHz;
  float blend_ = 0.0f;
  float phase_ = 0.0f;  // [0,1)
};

// Exponential ADSR after Nigel Redmon's target-ratio method: one add + one
// multiply per sample, naturally asymptotic like an analog RC envelope.
class ADSR {
 public:
  void setAttack(float samples);
  void setDecay(float samples);
  void setRelease(float samples);
  void setSustain(float level);
  void setTargetRatioA(float ratio);   // attack overshoot (~0.3)
  void setTargetRatioDR(float ratio);  // decay/release floor (~0.0001 = -80 dB)

  void gate(bool on);     // true -> attack, false -> release
  float process();        // next envelope value
  bool idle() const { return state_ == State::Idle; }
  float value() const { return output_; }

 private:
  enum class State { Idle, Attack, Decay, Sustain, Release };
  static float calcCoef(float rate, float targetRatio);
  void recompute();

  State state_ = State::Idle;
  float output_ = 0.0f;
  float attackRate_ = 1.0f, decayRate_ = 1.0f, releaseRate_ = 1.0f;
  float sustain_ = 0.7f;
  float targetRatioA_ = 0.3f, targetRatioDR_ = 0.0001f;
  float attackCoef_ = 0.0f, attackBase_ = 0.0f;
  float decayCoef_ = 0.0f, decayBase_ = 0.0f;
  float releaseCoef_ = 0.0f, releaseBase_ = 0.0f;
};

// First-order IIR (one-pole) smoother modelling analog portamento. With glide
// time 0 it jumps instantly; otherwise it sweeps toward the target frequency.
class Portamento {
 public:
  void setSampleRate(float sr) { sampleRate_ = sr; }
  void setGlideMs(float ms);
  void setTarget(float hz) { target_ = hz; }
  void snap(float hz) { current_ = target_ = hz; }
  float process();
  float current() const { return current_; }

 private:
  float sampleRate_ = kSampleRate;
  float coef_ = 1.0f;     // 1 = instant
  float target_ = kBaseHz;
  float current_ = kBaseHz;
};

// Cubic soft clip: smooth, division-free peak rounding (warm, alias-light).
float softClip(float x);

// A monophonic voice: oscillator -> ADSR (amplitude) -> soft clip, with a
// portamento-smoothed pitch. Enough to render the UI cue bank.
class Voice {
 public:
  Voice();
  void setSampleRate(float sr);
  void setBlend(float b) { osc_.setBlend(b); }
  void setGlideMs(float ms) { porta_.setGlideMs(ms); }
  void setEnvelope(float attackMs, float decayMs, float sustain, float releaseMs);

  void noteOn(float hz, bool glide);  // glide=false snaps pitch
  void setPitch(float hz) { porta_.setTarget(hz); }
  void noteOff();
  bool idle() const { return adsr_.idle(); }
  float sampleRate() const { return sampleRate_; }

  float render();                 // one sample
  void render(float* out, int n); // n samples

 private:
  Oscillator osc_;
  ADSR adsr_;
  Portamento porta_;
  float sampleRate_ = kSampleRate;
};

}  // namespace aibutton::dsp
