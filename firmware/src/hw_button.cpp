// SCAFFOLD - requires the Arduino-ESP32 toolchain (Arduino.h / GPIO).
#include "hw_button.h"

#include <Arduino.h>

namespace aibutton {

namespace {
constexpr uint32_t kDebounceMs = 50;
}

void ButtonInput::begin(int pin, bool activeLow) {
  pin_ = pin;
  activeLow_ = activeLow;
  pinMode(pin_, activeLow_ ? INPUT_PULLUP : INPUT_PULLDOWN);
}

Trigger ButtonInput::poll(uint32_t nowMs) {
  const double t = nowMs / 1000.0;
  const bool level = digitalRead(pin_) == (activeLow_ ? LOW : HIGH);

  // Debounce: accept an edge only after the line has settled.
  if (level != raw_) { raw_ = level; lastEdgeMs_ = nowMs; }
  Trigger out = Trigger::None;
  if (level != pressed_ && (nowMs - lastEdgeMs_) >= kDebounceMs) {
    pressed_ = level;
    if (pressed_) {                       // press edge
      holdSent_ = false;
      deadlinePending_ = false;
      out = detector_.onPress(t);
    } else {                              // release edge
      ReleaseResult r = detector_.onRelease(t);
      if (r.hasDeadline) { deadlinePending_ = true; deadline_ = r.deadline; }
      out = r.event;
    }
  }

  // Fabricate the hold event once the press has been held long enough.
  if (pressed_ && !holdSent_ && (t - 0.0) >= 0.0 &&
      (nowMs - lastEdgeMs_) >= static_cast<uint32_t>(TriggerDetector::kHoldS * 1000)) {
    holdSent_ = true;
    const Trigger h = detector_.onHold(t);
    if (h != Trigger::None) out = h;
  }

  // Fire the chord-resolve timeout when its deadline passes.
  if (out == Trigger::None && deadlinePending_ && t >= deadline_) {
    deadlinePending_ = false;
    out = detector_.onTimeout(t);
  }
  return out;
}

}  // namespace aibutton
