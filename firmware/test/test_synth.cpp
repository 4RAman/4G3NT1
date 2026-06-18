// Native unit tests for the portable synth DSP + cue bank. Verifies the
// research doc's algorithms behave (bounded, convergent, non-silent) on the
// host before any of it runs on the ESP32-C3. Built/run by the Makefile.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>

#include "sound_bank.h"
#include "synth.h"

using namespace aibutton::dsp;

static int g_fail = 0;
#define CHECK(cond)                                                      \
  do {                                                                   \
    if (!(cond)) {                                                       \
      std::printf("  FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);      \
      ++g_fail;                                                          \
    }                                                                    \
  } while (0)

static void test_soft_clip() {
  CHECK(softClip(2.0f) == 1.0f);
  CHECK(softClip(-2.0f) == -1.0f);
  CHECK(std::fabs(softClip(0.0f)) < 1e-6f);
  // monotonic and bounded across the domain
  float prev = -2.0f;
  for (float x = -1.5f; x <= 1.5f; x += 0.05f) {
    const float y = softClip(x);
    CHECK(y <= 1.0001f && y >= -1.0001f);
    CHECK(y >= prev - 1e-4f);  // non-decreasing
    prev = y;
  }
}

static void test_note_hz() {
  CHECK(std::fabs(noteHz(0.0f) - 880.0f) < 0.5f);
  CHECK(std::fabs(noteHz(12.0f) - 1760.0f) < 1.0f);   // octave up
  CHECK(std::fabs(noteHz(7.0f) - 1318.5f) < 2.0f);    // perfect fifth
}

static void test_oscillator_bounds_and_blend() {
  initTables();
  Oscillator sine;
  sine.setFrequency(440.0f);
  sine.setBlend(0.0f);
  float peak = 0.0f;
  for (int i = 0; i < 2000; ++i) {
    const float s = sine.next();
    CHECK(s <= 1.0001f && s >= -1.0001f);
    peak = std::fmax(peak, std::fabs(s));
  }
  CHECK(peak > 0.9f);  // a full-scale sine

  Oscillator sq;
  sq.setFrequency(440.0f);
  sq.setBlend(1.0f);
  float energy = 0.0f;
  for (int i = 0; i < 2000; ++i) { const float s = sq.next(); energy += std::fabs(s); }
  CHECK(energy / 2000.0f > 0.8f);  // square sits near +/-1 most of the time
}

static void test_adsr_shape() {
  ADSR env;
  env.setAttack(100.0f);
  env.setDecay(200.0f);
  env.setSustain(0.5f);
  env.setRelease(200.0f);
  env.gate(true);
  float peak = 0.0f;
  for (int i = 0; i < 100; ++i) peak = std::fmax(peak, env.process());  // attack
  CHECK(peak > 0.9f);
  for (int i = 0; i < 2000; ++i) env.process();  // settle to sustain
  CHECK(std::fabs(env.value() - 0.5f) < 0.05f);
  env.gate(false);
  for (int i = 0; i < 5000; ++i) env.process();  // release
  CHECK(env.value() < 0.01f);
  CHECK(env.idle());
  // never exceeds unity
  ADSR e2; e2.setAttack(50); e2.setDecay(50); e2.setSustain(0.8f); e2.setRelease(50);
  e2.gate(true);
  for (int i = 0; i < 1000; ++i) CHECK(e2.process() <= 1.0001f);
}

static void test_portamento() {
  Portamento p;
  p.setSampleRate(kSampleRate);
  p.snap(500.0f);
  p.setGlideMs(20.0f);
  p.setTarget(1000.0f);
  float last = 500.0f;
  for (int i = 0; i < 20000; ++i) last = p.process();  // >> the 20 ms time constant
  CHECK(std::fabs(last - 1000.0f) < 1.0f);  // converges to target
  // glide 0 -> instant
  Portamento q; q.snap(100.0f); q.setGlideMs(0.0f); q.setTarget(2000.0f);
  CHECK(std::fabs(q.process() - 2000.0f) < 1e-3f);
}

static bool bounded_nonsilent(const std::vector<float>& buf, int n) {
  float energy = 0.0f;
  for (int i = 0; i < n; ++i) {
    if (buf[i] > 1.0001f || buf[i] < -1.0001f) return false;
    energy += std::fabs(buf[i]);
  }
  return n > 0 && energy > 0.0f;
}

static void test_cue_bank_renders() {
  initTables();
  Voice v;
  v.setSampleRate(kSampleRate);
  const int cap = static_cast<int>(kSampleRate * 3);  // up to 3 s
  std::vector<float> buf(cap);
  uint32_t rng = 0xC0FFEEu;
  for (int c = 0; c < static_cast<int>(CueId::Count); ++c) {
    const int n = renderCue(static_cast<CueId>(c), v, buf.data(), cap, rng);
    CHECK(bounded_nonsilent(buf, n));
  }
}

static void test_micro_variation_differs() {
  initTables();
  Voice v;
  v.setSampleRate(kSampleRate);
  const int cap = static_cast<int>(kSampleRate);
  std::vector<float> a(cap), b(cap);
  uint32_t rng = 0x1234u;
  const int na = renderCue(CueId::Ack, v, a.data(), cap, rng);
  const int nb = renderCue(CueId::Ack, v, b.data(), cap, rng);  // rng advanced
  // Same cue, different micro-variation -> not bit-identical.
  bool identical = (na == nb);
  if (identical) {
    for (int i = 0; i < na; ++i) if (std::fabs(a[i] - b[i]) > 1e-6f) { identical = false; break; }
  }
  CHECK(!identical);
}

int main() {
  test_soft_clip();
  test_note_hz();
  test_oscillator_bounds_and_blend();
  test_adsr_shape();
  test_portamento();
  test_cue_bank_renders();
  test_micro_variation_differs();
  if (g_fail == 0) std::printf("synth: all tests passed\n");
  return g_fail == 0 ? 0 : 1;
}
