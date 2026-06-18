// SCAFFOLD - requires the Arduino-ESP32 toolchain (Arduino.h / LEDC).
#include "hw_led.h"

#include <Arduino.h>
#include <cmath>

namespace aibutton {

namespace {
constexpr int kPwmFreq = 5000;
constexpr int kPwmBits = 8;
constexpr int kPwmMax = (1 << kPwmBits) - 1;

// 0..1 triangle/sine breathe over `periodMs`.
float breathe(uint32_t elapsedMs, float periodMs) {
  const float phase = std::fmod(static_cast<float>(elapsedMs), periodMs) / periodMs;
  return (1.0f - std::cos(2.0f * static_cast<float>(M_PI) * phase)) * 0.5f;
}
}  // namespace

void LedController::begin(int rPin, int gPin, int bPin, bool activeHigh) {
  rPin_ = rPin; gPin_ = gPin; bPin_ = bPin; activeHigh_ = activeHigh;
  ledcAttach(rPin_, kPwmFreq, kPwmBits);
  ledcAttach(gPin_, kPwmFreq, kPwmBits);
  ledcAttach(bPin_, kPwmFreq, kPwmBits);
  setState(LedState::Idle);
}

void LedController::write(float r, float g, float b) {
  auto duty = [this](float v) {
    int d = static_cast<int>(v * kPwmMax + 0.5f);
    if (d < 0) d = 0; if (d > kPwmMax) d = kPwmMax;
    return activeHigh_ ? d : (kPwmMax - d);
  };
  ledcWrite(rPin_, duty(r));
  ledcWrite(gPin_, duty(g));
  ledcWrite(bPin_, duty(b));
}

void LedController::setState(LedState s) {
  state_ = s;
  stateStartMs_ = millis();
}

void LedController::tick(uint32_t nowMs) {
  const uint32_t e = nowMs - stateStartMs_;
  switch (state_) {
    case LedState::Idle:           write(0, 0, breathe(e, 3000)); break;
    case LedState::Listening:      write(1, 1, 0); break;  // solid yellow
    case LedState::Thinking: {     // fast rainbow
      const float h = std::fmod(static_cast<float>(e), 1000.0f) / 1000.0f;
      const float x = 1.0f - std::fabs(std::fmod(h * 6.0f, 2.0f) - 1.0f);
      if (h < 1.0f / 6) write(1, x, 0); else if (h < 2.0f / 6) write(x, 1, 0);
      else if (h < 3.0f / 6) write(0, 1, x); else if (h < 4.0f / 6) write(0, x, 1);
      else if (h < 5.0f / 6) write(x, 0, 1); else write(1, 0, x);
      break;
    }
    case LedState::Success:        write(0, 1, 0); break;
    case LedState::Error:          write((e / 200) % 2 ? 0 : 1, 0, 0); break;  // red flash
    case LedState::Alert:          write(1, (e / 200) % 2, (e / 200) % 2); break;  // red/white
    case LedState::Timing:         write(0, breathe(e, 1600), breathe(e, 1600)); break;  // cyan
    case LedState::Counting:       write(breathe(e, 2200), 0, breathe(e, 2200)); break;  // magenta
    case LedState::PomodoroWork: { const float l = breathe(e, 2000); write(l, 0.4f * l, 0); break; }
    case LedState::PomodoroBreak:  write(0, breathe(e, 3200), 0); break;
    case LedState::PomodoroPaused: { const float l = breathe(e, 4000); write(0.18f * l, 0.07f * l, 0); break; }
    case LedState::Off:            write(0, 0, 0); break;
  }
}

}  // namespace aibutton
