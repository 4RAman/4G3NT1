#include "sound_bank.h"

#include <cmath>

namespace aibutton::dsp {

namespace {

struct Note {
  float semis;  // offset from base note (A5)
  float ms;
  bool glide;   // true -> portamento from the previous note (no re-gate)
};

// Cue parameters, indexed by CueId. Blends and ADSR follow the research doc's
// core-sound-bank table; intervals are realised in buildNotes() below.
const Cue kCues[static_cast<int>(CueId::Count)] = {
    // blend a    d     s     r     glide jitC  jitMs
    {0.10f, 1.0f, 100.f, 0.00f, 10.f, 0.f, 10.f, 5.f},  // Ack  (standard click)
    {0.30f, 3.0f, 90.f, 0.10f, 60.f, 0.f, 10.f, 5.f},   // Success (rising P5)
    {0.60f, 15.f, 220.f, 0.15f, 80.f, 0.f, 10.f, 5.f},  // Error (falling tritone)
    {0.50f, 2.0f, 150.f, 0.20f, 60.f, 0.f, 10.f, 5.f},  // Alarm (urgent m2)
    {0.20f, 12.f, 60.f, 0.80f, 200.f, 110.f, 8.f, 5.f}, // Wake (rising arp, glide)
    {0.20f, 40.f, 120.f, 0.50f, 280.f, 130.f, 8.f, 5.f},// Sleep (falling arp, glide)
    {0.20f, 4.0f, 110.f, 0.05f, 80.f, 0.f, 8.f, 5.f},   // Phase (rising P4)
    {0.50f, 2.0f, 70.f, 0.00f, 20.f, 0.f, 14.f, 6.f},   // IdleChatter (pentatonic)
};

// Fixed interval contours. Wake/Sleep glide; the rest are staccato (re-gated).
const Note kAck[] = {{10.f, 90.f, false}};                         // ~1568 Hz
const Note kSuccess[] = {{0.f, 90.f, false}, {7.f, 150.f, false}}; // rising P5
const Note kError[] = {{0.f, 120.f, false}, {-6.f, 240.f, false}}; // falling tritone
const Note kAlarm[] = {{2.f, 180.f, false}, {1.f, 180.f, false},   // oscillating m2
                       {2.f, 300.f, false}};
const Note kWake[] = {{0.f, 90.f, true}, {7.f, 90.f, true},        // root-P5-octave
                      {12.f, 200.f, true}};
const Note kSleep[] = {{12.f, 130.f, true}, {3.f, 140.f, true},    // octave-m3-root
                       {0.f, 280.f, true}};
const Note kPhase[] = {{0.f, 110.f, false}, {5.f, 200.f, false}};  // rising P4

// Pentatonic palette for the idle chatter's randomized leaps.
const float kPentatonic[] = {0.f, 2.f, 4.f, 7.f, 9.f, 12.f, 14.f, 16.f};

template <int N>
int copyNotes(const Note (&src)[N], Note* dst, int cap) {
  const int n = N < cap ? N : cap;
  for (int i = 0; i < n; ++i) dst[i] = src[i];
  return n;
}

}  // namespace

uint32_t xorshift32(uint32_t& s) {
  s ^= s << 13;
  s ^= s >> 17;
  s ^= s << 5;
  return s;
}

static float rngUnit(uint32_t& s) {
  return static_cast<float>(xorshift32(s) >> 8) * (1.0f / 16777216.0f);  // [0,1)
}
static float rngSym(uint32_t& s) { return rngUnit(s) * 2.0f - 1.0f; }    // [-1,1)

const Cue& getCue(CueId id) { return kCues[static_cast<int>(id)]; }

static int buildNotes(CueId id, Note* out, int cap, uint32_t& rng) {
  switch (id) {
    case CueId::Ack: return copyNotes(kAck, out, cap);
    case CueId::Success: return copyNotes(kSuccess, out, cap);
    case CueId::Error: return copyNotes(kError, out, cap);
    case CueId::Alarm: return copyNotes(kAlarm, out, cap);
    case CueId::Wake: return copyNotes(kWake, out, cap);
    case CueId::Sleep: return copyNotes(kSleep, out, cap);
    case CueId::Phase: return copyNotes(kPhase, out, cap);
    case CueId::IdleChatter: {
      const int palette = static_cast<int>(sizeof(kPentatonic) / sizeof(float));
      const int n = (6 + static_cast<int>(rngUnit(rng) * 4)) % (cap + 1);  // 6-9 notes
      for (int i = 0; i < n; ++i) {
        out[i].semis = kPentatonic[xorshift32(rng) % palette];
        out[i].ms = 70.f + rngUnit(rng) * 50.f;  // staccato 70-120 ms
        out[i].glide = false;
      }
      return n;
    }
    case CueId::Count: break;
  }
  return 0;
}

static float clampf(float x, float lo, float hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

int renderCue(CueId id, Voice& voice, float* out, int cap, uint32_t& rng) {
  const Cue& cue = getCue(id);
  voice.setBlend(clampf(cue.blend + rngSym(rng) * 0.05f, 0.0f, 1.0f));  // timbral jitter
  const float decay = std::fmax(1.0f, cue.decayMs + rngSym(rng) * cue.decayJitterMs);
  voice.setEnvelope(cue.attackMs, decay, cue.sustain, cue.releaseMs);
  voice.setGlideMs(cue.glideMs);

  Note notes[16];
  const int n = buildNotes(id, notes, 16, rng);
  const float sr = voice.sampleRate();
  int written = 0;
  for (int i = 0; i < n && written < cap; ++i) {
    const float cents = rngSym(rng) * cue.pitchJitterCents;  // micro-detune
    const float hz = noteHz(notes[i].semis) * std::pow(2.0f, cents / 1200.0f);
    if (i == 0) {
      voice.noteOn(hz, false);          // first note: snap + gate
    } else if (notes[i].glide) {
      voice.setPitch(hz);               // glide via portamento, env continues
    } else {
      voice.noteOn(hz, false);          // staccato: re-gate
    }
    const int samples = static_cast<int>(notes[i].ms * sr / 1000.0f);
    for (int j = 0; j < samples && written < cap; ++j) out[written++] = voice.render();
  }
  voice.noteOff();
  while (!voice.idle() && written < cap) out[written++] = voice.render();  // release tail
  return written;
}

}  // namespace aibutton::dsp
