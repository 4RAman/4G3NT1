#include "synth.h"

#include <cmath>

namespace aibutton::dsp {

namespace {
float gSine[kTableSize];
float gSquare[kTableSize];
bool gReady = false;
}  // namespace

float noteHz(float semitones, float base) {
  return base * std::pow(2.0f, semitones / 12.0f);
}

void initTables() {
  for (int i = 0; i < kTableSize; ++i) {
    const float ph = static_cast<float>(i) / kTableSize;
    gSine[i] = std::sin(2.0f * static_cast<float>(M_PI) * ph);
    gSquare[i] = ph < 0.5f ? 1.0f : -1.0f;  // naive; bandlimited is the upgrade
  }
  gReady = true;
}

static float lookup(const float* table, float phase01) {
  if (!gReady) initTables();
  float x = phase01 - std::floor(phase01);
  const float pos = x * kTableSize;
  const int i0 = static_cast<int>(pos) % kTableSize;
  const int i1 = (i0 + 1) % kTableSize;
  const float frac = pos - std::floor(pos);
  return table[i0] + (table[i1] - table[i0]) * frac;  // linear interpolation
}

float sampleSine(float phase01) { return lookup(gSine, phase01); }
float sampleSquare(float phase01) { return lookup(gSquare, phase01); }

float Oscillator::next() {
  const float s = sampleSine(phase_);
  const float q = sampleSquare(phase_);
  const float out = s + (q - s) * blend_;  // morph sine -> square
  phase_ += freq_ / sampleRate_;
  if (phase_ >= 1.0f) phase_ -= std::floor(phase_);
  return out;
}

// --- ADSR (Nigel Redmon target-ratio) -------------------------------------

float ADSR::calcCoef(float rate, float targetRatio) {
  if (rate <= 0.0f) return 0.0f;
  return std::exp(-std::log((1.0f + targetRatio) / targetRatio) / rate);
}

void ADSR::recompute() {
  attackCoef_ = calcCoef(attackRate_, targetRatioA_);
  attackBase_ = (1.0f + targetRatioA_) * (1.0f - attackCoef_);
  decayCoef_ = calcCoef(decayRate_, targetRatioDR_);
  decayBase_ = (sustain_ - targetRatioDR_) * (1.0f - decayCoef_);
  releaseCoef_ = calcCoef(releaseRate_, targetRatioDR_);
  releaseBase_ = -targetRatioDR_ * (1.0f - releaseCoef_);
}

void ADSR::setAttack(float samples) { attackRate_ = samples; recompute(); }
void ADSR::setDecay(float samples) { decayRate_ = samples; recompute(); }
void ADSR::setRelease(float samples) { releaseRate_ = samples; recompute(); }
void ADSR::setSustain(float level) { sustain_ = level; recompute(); }
void ADSR::setTargetRatioA(float r) { targetRatioA_ = r < 1e-6f ? 1e-6f : r; recompute(); }
void ADSR::setTargetRatioDR(float r) { targetRatioDR_ = r < 1e-9f ? 1e-9f : r; recompute(); }

void ADSR::gate(bool on) { state_ = on ? State::Attack : State::Release; }

float ADSR::process() {
  switch (state_) {
    case State::Idle:
      break;
    case State::Attack:
      output_ = attackBase_ + output_ * attackCoef_;
      if (output_ >= 1.0f) { output_ = 1.0f; state_ = State::Decay; }
      break;
    case State::Decay:
      output_ = decayBase_ + output_ * decayCoef_;
      if (output_ <= sustain_) { output_ = sustain_; state_ = State::Sustain; }
      break;
    case State::Sustain:
      output_ = sustain_;
      break;
    case State::Release:
      output_ = releaseBase_ + output_ * releaseCoef_;
      if (output_ <= 0.0f) { output_ = 0.0f; state_ = State::Idle; }
      break;
  }
  return output_;
}

// --- Portamento -----------------------------------------------------------

void Portamento::setGlideMs(float ms) {
  if (ms <= 0.0f) { coef_ = 1.0f; return; }
  // One-pole coefficient for the requested glide time constant.
  coef_ = 1.0f - std::exp(-1.0f / (ms * 0.001f * sampleRate_));
}

float Portamento::process() {
  current_ += coef_ * (target_ - current_);
  return current_;
}

// --- soft clip ------------------------------------------------------------

float softClip(float x) {
  if (x >= 1.0f) return 1.0f;
  if (x <= -1.0f) return -1.0f;
  return 1.5f * x - 0.5f * x * x * x;  // smooth, derivative -> 0 at +/-1
}

// --- Voice ----------------------------------------------------------------

Voice::Voice() {
  adsr_.setTargetRatioA(0.3f);
  adsr_.setTargetRatioDR(0.0001f);
  setEnvelope(5.0f, 80.0f, 0.0f, 80.0f);
}

void Voice::setSampleRate(float sr) {
  sampleRate_ = sr;
  osc_.setSampleRate(sr);
  porta_.setSampleRate(sr);
}

void Voice::setEnvelope(float attackMs, float decayMs, float sustain, float releaseMs) {
  adsr_.setAttack(attackMs * 0.001f * sampleRate_);
  adsr_.setDecay(decayMs * 0.001f * sampleRate_);
  adsr_.setSustain(sustain);
  adsr_.setRelease(releaseMs * 0.001f * sampleRate_);
}

void Voice::noteOn(float hz, bool glide) {
  if (glide) {
    porta_.setTarget(hz);
  } else {
    porta_.snap(hz);
  }
  adsr_.gate(true);
}

void Voice::noteOff() { adsr_.gate(false); }

float Voice::render() {
  const float hz = porta_.process();
  osc_.setFrequency(hz);
  const float env = adsr_.process();
  return softClip(osc_.next() * env);
}

void Voice::render(float* out, int n) {
  for (int i = 0; i < n; ++i) out[i] = render();
}

}  // namespace aibutton::dsp
