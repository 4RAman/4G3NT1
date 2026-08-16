"""The MicroPython gesture detector must behave exactly like the host's.

test_trigger_detector.py pins what the state machine *should* do; this
pins that the port does the same thing. Rather than duplicating the
assertion matrix (two copies drift), each scenario is an event script run
through both detectors in lockstep, comparing every return value.

The port is importable under CPython because it deliberately touches no
MicroPython API - the hardware lives in main.py, not in the detector.
"""

import pytest
import trigger as fw  # firmware/trigger.py - see conftest.py

from aibutton.button import DOUBLE_WINDOW_S as HOST_WINDOW
from aibutton.button import HOLD_S as HOST_HOLD
from aibutton.button import TriggerDetector as HostDetector


def test_timing_constants_match():
    from aibutton.button import DEBOUNCE_S, _EPSILON

    assert fw.HOLD_S == HOST_HOLD
    assert fw.DOUBLE_WINDOW_S == HOST_WINDOW
    assert fw.DEBOUNCE_S == DEBOUNCE_S
    assert fw._EPSILON == _EPSILON


def test_event_names_match_the_host_enum():
    from aibutton.device import TriggerType

    assert fw.SHORT_PRESS == TriggerType.SHORT_PRESS.value
    assert fw.LONG_PRESS == TriggerType.LONG_PRESS.value
    assert fw.DOUBLE_TAP == TriggerType.DOUBLE_TAP.value
    assert fw.TRIPLE_TAP == TriggerType.TRIPLE_TAP.value


# (name, [(method, timestamp), ...]) - the same scenarios the host matrix
# covers, plus a few multi-gesture sequences that exercise state carried
# from one gesture into the next.
SCRIPTS = [
    ("short press emits after its window", [
        ("press", 0.0), ("release", 0.1), ("timeout", 0.4),
    ]),
    ("press outliving the window emits on release", [
        ("press", 0.0), ("release", 0.5),
    ]),
    ("release just under the hold threshold is short", [
        ("press", 0.0), ("release", 0.999),
    ]),
    ("hold fires long press and consumes the release", [
        ("press", 0.0), ("hold", 1.0), ("release", 1.4),
    ]),
    ("missed hold callback still yields long on release", [
        ("press", 0.0), ("release", 1.001),
    ]),
    ("double tap, with a stale timer arriving after", [
        ("press", 0.0), ("release", 0.1), ("press", 0.3),
        ("timeout", 0.4), ("release", 0.45),
    ]),
    ("second press just inside the window is a double", [
        ("press", 0.0), ("release", 0.1), ("press", 0.399),
    ]),
    ("second press at the window boundary is not a double", [
        ("press", 0.0), ("release", 0.1), ("press", 0.401),
    ]),
    ("two slow taps are two shorts", [
        ("press", 0.0), ("release", 0.1), ("timeout", 0.4),
        ("press", 0.6), ("release", 0.7), ("timeout", 1.0),
    ]),
    ("tap then held second press is a double only", [
        ("press", 0.0), ("release", 0.1), ("press", 0.3),
        ("hold", 1.3), ("release", 2.0),
    ]),
    ("triple tap is a double then a pending short", [
        ("press", 0.0), ("release", 0.1), ("press", 0.2), ("release", 0.3),
        ("press", 0.5), ("release", 0.6), ("timeout", 1.0),
    ]),
    ("stale timeout with nothing pending", [
        ("timeout", 99.0),
    ]),
    ("release without a press", [
        ("release", 1.0),
    ]),
    ("long press then a double tap", [
        ("press", 0.0), ("hold", 1.0), ("release", 1.2),
        ("press", 2.0), ("release", 2.1), ("press", 2.3), ("release", 2.4),
    ]),
    ("timeouts polled every tick, as main.py does", [
        ("press", 0.0), ("timeout", 0.05), ("release", 0.1),
        ("timeout", 0.2), ("timeout", 0.3), ("timeout", 0.4), ("timeout", 0.5),
    ]),
]


def _step(detector, method, t, to_value):
    """Run one scripted call, normalising the host's enum to its value so
    the two implementations are directly comparable."""
    if method == "press":
        return to_value(detector.on_press(t))
    if method == "hold":
        return to_value(detector.on_hold(t))
    if method == "timeout":
        return to_value(detector.on_timeout(t))
    event, deadline = detector.on_release(t)
    return to_value(event), deadline


# The same, with the detector told to count to three. Everything above stays
# in the table unchanged on purpose: max_taps=2 is not a special case in the
# code, it is the general algorithm with a limit of two, and the fact that the
# original scripts still pass is what says so.
TRIPLE_SCRIPTS = [
    ("a triple tap fires on the third press", [
        ("press", 0.0), ("release", 0.1), ("press", 0.2), ("release", 0.3),
        ("press", 0.4), ("release", 0.5),
    ]),
    ("a double tap now has to wait out the window", [
        ("press", 0.0), ("release", 0.1), ("press", 0.2), ("release", 0.3),
        ("timeout", 0.6),
    ]),
    ("a burst whose last tap outlives the window emits without waiting", [
        ("press", 0.0), ("release", 0.1), ("press", 0.2), ("release", 0.7),
    ]),
    ("a fourth tap starts a fresh burst", [
        ("press", 0.0), ("release", 0.1), ("press", 0.2), ("release", 0.3),
        ("press", 0.4), ("release", 0.5),
        ("press", 0.6), ("release", 0.7), ("timeout", 1.1),
    ]),
    ("holding part-way through a burst ends it as a long press", [
        ("press", 0.0), ("release", 0.1), ("press", 0.2), ("hold", 1.2),
        ("release", 1.3), ("press", 2.0), ("release", 2.1), ("timeout", 2.5),
    ]),
    ("three slow taps are three short presses", [
        ("press", 0.0), ("release", 0.1), ("timeout", 0.4),
        ("press", 1.0), ("release", 1.1), ("timeout", 1.4),
        ("press", 2.0), ("release", 2.1), ("timeout", 2.4),
    ]),
]


@pytest.mark.parametrize("name,script", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_port_matches_host_step_for_step(name, script):
    host, port = HostDetector(), fw.TriggerDetector()
    for method, t in script:
        expected = _step(host, method, t, lambda e: e.value if e else None)
        actual = _step(port, method, t, lambda e: e)
        assert actual == expected, f"{name}: {method}({t}) diverged"


@pytest.mark.parametrize(
    "name,script", TRIPLE_SCRIPTS, ids=[s[0] for s in TRIPLE_SCRIPTS]
)
def test_port_matches_host_when_counting_to_three(name, script):
    host, port = HostDetector(max_taps=3), fw.TriggerDetector(max_taps=3)
    for method, t in script:
        expected = _step(host, method, t, lambda e: e.value if e else None)
        actual = _step(port, method, t, lambda e: e)
        assert actual == expected, f"{name}: {method}({t}) diverged"


def test_counting_further_is_what_delays_a_double_tap():
    """The cost the host is deciding about when it writes max_taps, stated as
    a test so it cannot change by accident: at 2 a double tap lands on the
    second press, at 3 it cannot, because a third tap might still be coming."""
    taps = [("press", 0.0), ("release", 0.1), ("press", 0.2)]
    instant = fw.TriggerDetector(max_taps=2)
    patient = fw.TriggerDetector(max_taps=3)
    for method, t in taps:
        instant_out = _step(instant, method, t, lambda e: e)
        patient_out = _step(patient, method, t, lambda e: e)
    assert instant_out == fw.DOUBLE_TAP
    assert patient_out is None
    # ...and arrives when the window closes instead.
    _step(patient, "release", 0.3, lambda e: e)
    assert _step(patient, "timeout", 0.7, lambda e: e) == fw.DOUBLE_TAP


def test_changing_max_taps_abandons_the_burst_in_progress():
    """Otherwise a burst counted under one setting finishes under another and
    emits a gesture neither of them describes."""
    for detector in (fw.TriggerDetector(max_taps=3), HostDetector(max_taps=3)):
        detector.on_press(0.0)
        detector.on_release(0.1)
        detector.on_press(0.2)  # two taps in, nothing emitted yet
        detector.set_max_taps(2)
        assert detector.on_timeout(1.0) is None


def test_scripts_cover_every_gesture():
    """A guard on the tables above: if a gesture stopped being produced the
    comparison would still pass while testing nothing about it."""
    seen = set()
    for scripts, max_taps in ((SCRIPTS, 2), (TRIPLE_SCRIPTS, 3)):
        for _name, script in scripts:
            detector = fw.TriggerDetector(max_taps=max_taps)
            for method, t in script:
                result = _step(detector, method, t, lambda e: e)
                event = result[0] if isinstance(result, tuple) else result
                if event is not None:
                    seen.add(event)
    assert seen == {fw.SHORT_PRESS, fw.LONG_PRESS, fw.DOUBLE_TAP, fw.TRIPLE_TAP}
