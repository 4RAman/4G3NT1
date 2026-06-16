"""Timing matrix for the pure TriggerDetector state machine.

Timestamps are plain floats (seconds); no GPIO or event loop involved.
Quick taps accumulate into a chord that resolves on on_timeout:
1->short, 2->double, 5->quintuple (fired on the 5th press), 3/4->nothing.
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


def test_double_tap_resolves_on_timeout():
    d = TriggerDetector()
    assert d.on_press(0.0) is None
    assert d.on_release(0.1) == (None, DOUBLE_WINDOW_S)
    assert d.on_press(0.3) is None  # second tap joins the chord, no immediate fire
    _, deadline = d.on_release(0.35)
    assert deadline == 0.3 + DOUBLE_WINDOW_S
    # a stale timer from the first tap is a no-op (chord not closed yet)
    assert d.on_timeout(DOUBLE_WINDOW_S) is None
    assert d.on_timeout(deadline) is TriggerType.DOUBLE_TAP


def test_double_tap_boundary_just_inside():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    assert d.on_press(0.399) is None  # within the window -> chord continues
    _, deadline = d.on_release(0.45)
    assert d.on_timeout(deadline) is TriggerType.DOUBLE_TAP


def test_second_press_at_window_starts_fresh_chord():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    # >= 0.4 s after the first press start: a new chord, not a double.
    assert d.on_press(0.401) is None
    _, deadline = d.on_release(0.45)
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS


def test_two_slow_taps_are_two_shorts():
    d = TriggerDetector()
    d.on_press(0.0)
    _, deadline = d.on_release(0.1)
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS
    d.on_press(0.6)
    _, deadline = d.on_release(0.7)
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS


def test_triple_tap_resolves_to_nothing():
    d = TriggerDetector()
    for t in (0.0, 0.1, 0.2):
        assert d.on_press(t) is None
        d.on_release(t + 0.03)
    # window closes after the third tap: an ambiguous 3-chord does nothing
    assert d.on_timeout(0.2 + DOUBLE_WINDOW_S) is None


def test_quadruple_tap_resolves_to_nothing():
    d = TriggerDetector()
    for t in (0.0, 0.1, 0.2, 0.3):
        assert d.on_press(t) is None
        d.on_release(t + 0.03)
    assert d.on_timeout(0.3 + DOUBLE_WINDOW_S) is None


def test_quintuple_tap_emits_on_fifth_press():
    d = TriggerDetector()
    taps = (0.0, 0.1, 0.2, 0.3, 0.4)
    for t in taps[:4]:
        assert d.on_press(t) is None
        d.on_release(t + 0.03)
    # the fifth tap fires immediately, without waiting for a window
    assert d.on_press(taps[4]) is TriggerType.QUINTUPLE_TAP
    # its release is swallowed and trailing stale timers no-op
    assert d.on_release(taps[4] + 0.03) == (None, None)
    assert d.on_timeout(taps[4] + DOUBLE_WINDOW_S) is None


def test_chord_resets_after_quintuple():
    d = TriggerDetector()
    for t in (0.0, 0.1, 0.2, 0.3):
        d.on_press(t)
        d.on_release(t + 0.03)
    assert d.on_press(0.4) is TriggerType.QUINTUPLE_TAP
    d.on_release(0.43)
    # a later single tap is a clean short press again
    assert d.on_press(1.0) is None
    _, deadline = d.on_release(1.1)
    assert d.on_timeout(deadline) is TriggerType.SHORT_PRESS


def test_hold_after_taps_is_not_long_press():
    d = TriggerDetector()
    d.on_press(0.0)
    d.on_release(0.1)
    d.on_press(0.3)  # chord has two taps now
    assert d.on_hold(1.3) is None  # a hold mid-chord is ignored, not a long press


def test_stale_timeout_is_noop():
    d = TriggerDetector()
    assert d.on_timeout(99.0) is None


def test_release_without_press_is_noop():
    d = TriggerDetector()
    assert d.on_release(1.0) == (None, None)
