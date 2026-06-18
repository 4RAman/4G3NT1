// RGB LED driver for the ESP32-C3 (LEDC PWM) - the firmware counterpart of
// aibutton/led.py. Non-blocking: setState() picks an animation, tick(nowMs)
// advances it. States mirror LEDState in led.py one-for-one.
//
// SCAFFOLD: written against the Arduino-ESP32 3.x LEDC API; not yet compiled.
#pragma once

#include <cstdint>

namespace aibutton {

enum class LedState {
  Idle, Listening, Thinking, Success, Error, Alert,
  Timing, Counting, Off, PomodoroWork, PomodoroBreak, PomodoroPaused,
};

class LedController {
 public:
  void begin(int rPin, int gPin, int bPin, bool activeHigh = true);
  void setState(LedState s);
  void tick(uint32_t nowMs);  // call every loop to animate

 private:
  void write(float r, float g, float b);  // each channel 0..1

  int rPin_ = 0, gPin_ = 0, bPin_ = 0;
  bool activeHigh_ = true;
  LedState state_ = LedState::Idle;
  uint32_t stateStartMs_ = 0;
};

}  // namespace aibutton
