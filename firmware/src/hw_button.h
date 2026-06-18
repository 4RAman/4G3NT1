// GPIO button input for the ESP32-C3 - the firmware counterpart of
// aibutton/button.py's ButtonListener. Polls the pin (debounced), drives the
// portable TriggerDetector, fabricates the hold and the resolve-timeout, and
// returns the next resolved gesture. Call poll() every loop.
//
// SCAFFOLD: written against the Arduino-ESP32 GPIO API; not yet compiled.
#pragma once

#include <cstdint>

#include "trigger_detector.h"

namespace aibutton {

class ButtonInput {
 public:
  void begin(int pin, bool activeLow = true);
  Trigger poll(uint32_t nowMs);  // Trigger::None when nothing resolved

 private:
  int pin_ = 0;
  bool activeLow_ = true;
  bool pressed_ = false;          // debounced logical state
  bool raw_ = false;
  uint32_t lastEdgeMs_ = 0;
  bool holdSent_ = false;
  bool deadlinePending_ = false;
  double deadline_ = 0.0;
  TriggerDetector detector_;
};

}  // namespace aibutton
