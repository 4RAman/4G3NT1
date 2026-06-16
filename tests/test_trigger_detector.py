"""Timing matrix for the pure TriggerDetector state machine.

Timestamps are plain floats (seconds); no GPIO or event loop involved.
"""

from aibutton.button import DOUBLE_WINDOW_S, TriggerDetector, TriggerType


def test_short_press_emits_after_window():
    d = TriggerDetector()
    assert d.on_press(0.0) is None
    event, deadline = d.on_release(0.1)
    assert event is None
    assert deadline == 0.0 + DOUBLE_WINDOW_S
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS


def test_press_outliving_window_emits_short_on_release():
    d = TriggerDetector()
    d.on_press(0.0)
    event, deadline = d.on_release(0.5)  # 0.4 <= duration < 1.0
    assert event is TriggerType.SHORT_PRESS
    assert deadline is None


def test_release_just_under_hold_is_short():
    d = TriggerDetector()
    d.on_press(0.0)
    event, _ = d.on_release(0.999)
    assert event is TriggerType.SHORT_PRESS


def test_long_press_fires_on_hold_and_release_is_consumed():
    d = TriggerDetector()
    d.on_press(0.0)
    assert d.on_hold(1.0) is TriggerType.LONG_PRESS
    assert d.on_release(1.4) == (None, None)


def test_long_press_safety_net_on_release():
    d = TriggerDetector()
    d.on_press(0.0)
    # hold callback never arrived
    event, deadline = d.on_release(1.001)
    assert event is TriggerType.LONG_PRESS
    assert deadline is None


def test_double_tap():
    d = TriggerDetector()
    d.on_press(0.0)
    assert d.on_release(0.1) == (None, DOUBLE_WINDOW_S)
    assert d.on_press(0.3) is TriggerType.DOUBLE_TAP
    # stale timer for the first press is a no-op
    assert d.on_timeout(0.4) is None
    assert d.on_release(0.45) == (None, None)


def test_double_tap_boundary_just_inside():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    assert d.on_press(0.399) is TriggerType.DOUBLE_TAP


def test_second_press_at_window_is_not_double():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    # In practice the 0.4s timer fires first and emits SHORT_PRESS;
    # the detector itself just refuses the double.
    assert d.on_press(0.401) is None


def test_two_slow_taps_are_two_shorts():
    d = TriggerDetector()
    d.on_press(0.0)
    _, deadline = d.on_release(0.1)
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS
    d.on_press(0.6)
    _, deadline = d.on_release(0.7)
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS


def test_tap_then_held_second_press_is_double_only():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    assert d.on_press(0.3) is TriggerType.DOUBLE_TAP
    assert d.on_hold(1.3) is None       # second press already consumed
    assert d.on_release(2.0) == (None, None)


def test_triple_tap_is_double_then_pending_short():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    assert d.on_press(0.2) is TriggerType.DOUBLE_TAP
    d.on_release(0.3)
    # third tap starts a fresh cycle
    assert d.on_press(0.5) is None
    event, deadline = d.on_release(0.6)
    assert event is None
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS


def test_stale_timeout_is_noop():
    d = TriggerDetector()
    assert d.on_timeout(99.0) is None


def test_release_without_press_is_noop():
    d = TriggerDetector()
    assert d.on_release(1.0) == (None, None)
