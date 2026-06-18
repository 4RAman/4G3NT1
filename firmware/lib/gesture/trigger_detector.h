// Portable tap-chord gesture detector - the C++ port of aibutton/button.py's
// TriggerDetector. Pure (no Arduino/GPIO), so it compiles and unit-tests on the
// host as well as on the ESP32-C3. Quick presses accumulate into a chord that
// resolves on a timeout:
//   1 tap  -> Short
//   2 taps -> Double
//   5 taps -> Quintuple (fired immediately on the 5th press; the global escape)
//   3/4    -> nothing (ambiguous partial chord)
// A single sustained press is a Long press.
//
// Timestamps are monotonic seconds (double). The caller must invoke
// onTimeout(now) at/after the deadline returned by onRelease(); stale timeouts
// are harmless no-ops.
#pragma once

namespace aibutton {

enum class Trigger { None, Short, Long, Double, Quintuple };

struct ReleaseResult {
  Trigger event;
  double deadline;     // valid only when hasDeadline is true
  bool hasDeadline;
};

class TriggerDetector {
 public:
  static constexpr double kHoldS = 1.0;
  static constexpr double kDoubleWindowS = 0.4;
  static constexpr int kQuintupleTaps = 5;
  static constexpr double kEpsilon = 1e-6;

  Trigger onPress(double t);
  Trigger onHold(double t);
  ReleaseResult onRelease(double t);
  Trigger onTimeout(double t);

 private:
  Trigger resolve();  // close the chord, map the tap count to a gesture

  double pressT_ = 0.0;     // current press start, for duration measurement
  bool hasPress_ = false;
  bool ignoreCurrent_ = false;  // this press's hold/release already spoken for
  int count_ = 0;           // taps in the open chord (0 = none pending)
  double lastPressT_ = 0.0; // start of the most recent tap in the chord
};

}  // namespace aibutton
