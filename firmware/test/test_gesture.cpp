// Native unit tests for the portable TriggerDetector (mirrors
// tests/test_trigger_detector.py). Built and run on the host by the Makefile.
#include <cstdio>
#include <initializer_list>

#include "trigger_detector.h"

using aibutton::ReleaseResult;
using aibutton::Trigger;
using aibutton::TriggerDetector;

static int g_fail = 0;
#define CHECK(cond)                                                      \
  do {                                                                   \
    if (!(cond)) {                                                       \
      std::printf("  FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);      \
      ++g_fail;                                                          \
    }                                                                    \
  } while (0)

static void test_short() {
  TriggerDetector d;
  CHECK(d.onPress(0.0) == Trigger::None);
  ReleaseResult r = d.onRelease(0.1);
  CHECK(r.event == Trigger::None && r.hasDeadline);
  CHECK(d.onTimeout(r.deadline) == Trigger::Short);
}

static void test_short_outliving_window() {
  TriggerDetector d;
  d.onPress(0.0);
  ReleaseResult r = d.onRelease(0.5);  // 0.4 <= dur < 1.0
  CHECK(r.event == Trigger::Short && !r.hasDeadline);
}

static void test_long_on_hold() {
  TriggerDetector d;
  d.onPress(0.0);
  CHECK(d.onHold(1.0) == Trigger::Long);
  ReleaseResult r = d.onRelease(1.4);
  CHECK(r.event == Trigger::None && !r.hasDeadline);
}

static void test_long_safety_net() {
  TriggerDetector d;
  d.onPress(0.0);
  ReleaseResult r = d.onRelease(1.001);
  CHECK(r.event == Trigger::Long);
}

static void test_double() {
  TriggerDetector d;
  CHECK(d.onPress(0.0) == Trigger::None);
  ReleaseResult r1 = d.onRelease(0.1);
  CHECK(r1.hasDeadline);
  CHECK(d.onPress(0.3) == Trigger::None);
  ReleaseResult r2 = d.onRelease(0.35);
  CHECK(d.onTimeout(0.4) == Trigger::None);   // stale first-tap timer no-ops
  CHECK(d.onTimeout(r2.deadline) == Trigger::Double);
}

static void test_triple_and_quad_are_nothing() {
  TriggerDetector d;
  for (double t : {0.0, 0.1, 0.2}) { d.onPress(t); d.onRelease(t + 0.03); }
  CHECK(d.onTimeout(0.2 + 0.4) == Trigger::None);

  TriggerDetector e;
  for (double t : {0.0, 0.1, 0.2, 0.3}) { e.onPress(t); e.onRelease(t + 0.03); }
  CHECK(e.onTimeout(0.3 + 0.4) == Trigger::None);
}

static void test_quintuple() {
  TriggerDetector d;
  for (double t : {0.0, 0.1, 0.2, 0.3}) { CHECK(d.onPress(t) == Trigger::None); d.onRelease(t + 0.03); }
  CHECK(d.onPress(0.4) == Trigger::Quintuple);     // fires on the 5th press
  ReleaseResult r = d.onRelease(0.43);
  CHECK(r.event == Trigger::None && !r.hasDeadline);  // its release is swallowed
  CHECK(d.onTimeout(0.4 + 0.4) == Trigger::None);     // trailing timers no-op
  // chord resets: a later single tap is a clean short again
  CHECK(d.onPress(1.0) == Trigger::None);
  ReleaseResult r2 = d.onRelease(1.1);
  CHECK(d.onTimeout(r2.deadline) == Trigger::Short);
}

static void test_hold_after_taps_is_not_long() {
  TriggerDetector d;
  d.onPress(0.0);
  d.onRelease(0.1);
  d.onPress(0.3);  // chord has two taps
  CHECK(d.onHold(1.3) == Trigger::None);
}

int main() {
  test_short();
  test_short_outliving_window();
  test_long_on_hold();
  test_long_safety_net();
  test_double();
  test_triple_and_quad_are_nothing();
  test_quintuple();
  test_hold_after_taps_is_not_long();
  if (g_fail == 0) std::printf("gesture: all tests passed\n");
  return g_fail == 0 ? 0 : 1;
}
