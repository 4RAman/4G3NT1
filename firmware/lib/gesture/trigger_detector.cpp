#include "trigger_detector.h"

namespace aibutton {

Trigger TriggerDetector::resolve() {
  const int count = count_;
  count_ = 0;
  if (count == 1) return Trigger::Short;
  if (count == 2) return Trigger::Double;
  if (count >= kQuintupleTaps) return Trigger::Quintuple;  // usually fired on press
  return Trigger::None;  // 3 or 4: ambiguous partial chord
}

Trigger TriggerDetector::onPress(double t) {
  if (count_ > 0 && (t - lastPressT_) < kDoubleWindowS) {
    count_ += 1;  // continues the open chord
  } else {
    count_ = 1;   // starts a fresh chord
  }
  lastPressT_ = t;
  pressT_ = t;
  hasPress_ = true;
  ignoreCurrent_ = false;
  if (count_ >= kQuintupleTaps) {
    // Fire the moment the fifth tap lands; swallow its hold/release and close
    // the chord so trailing timeouts no-op.
    count_ = 0;
    ignoreCurrent_ = true;
    return Trigger::Quintuple;
  }
  return Trigger::None;
}

Trigger TriggerDetector::onHold(double /*t*/) {
  // Only a single sustained press is a long press; a hold after taps is ignored.
  if (ignoreCurrent_ || count_ != 1) return Trigger::None;
  count_ = 0;
  ignoreCurrent_ = true;  // consume the upcoming release
  return Trigger::Long;
}

ReleaseResult TriggerDetector::onRelease(double t) {
  const bool had = hasPress_;
  const double pressT = pressT_;
  hasPress_ = false;
  if (ignoreCurrent_) {
    ignoreCurrent_ = false;
    return {Trigger::None, 0.0, false};
  }
  if (!had) return {Trigger::None, 0.0, false};  // release without a press
  const double duration = t - pressT;
  if (duration >= kHoldS) {
    count_ = 0;
    return {Trigger::Long, 0.0, false};  // safety net if the hold event was missed
  }
  if (duration >= kDoubleWindowS) {
    // Outlived the inter-tap window, so no later tap can join - resolve now.
    return {resolve(), 0.0, false};
  }
  // A quick tap: wait for the window after it to close before resolving.
  return {Trigger::None, lastPressT_ + kDoubleWindowS, true};
}

Trigger TriggerDetector::onTimeout(double t) {
  if (count_ == 0) return Trigger::None;
  if ((t - lastPressT_) >= kDoubleWindowS - kEpsilon) return resolve();
  return Trigger::None;
}

}  // namespace aibutton
