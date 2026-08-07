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


@pytest.mark.parametrize("name,script", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_port_matches_host_step_for_step(name, script):
    host, port = HostDetector(), fw.TriggerDetector()
    for method, t in script:
        expected = _step(host, method, t, lambda e: e.value if e else None)
        actual = _step(port, method, t, lambda e: e)
        assert actual == expected, f"{name}: {method}({t}) diverged"


def test_scripts_cover_every_gesture():
    """A guard on the table above: if a gesture stopped being produced the
    comparison would still pass while testing nothing about it."""
    seen = set()
    for _name, script in SCRIPTS:
        detector = fw.TriggerDetector()
        for method, t in script:
            result = _step(detector, method, t, lambda e: e)
            event = result[0] if isinstance(result, tuple) else result
            if event is not None:
                seen.add(event)
    assert seen == {fw.SHORT_PRESS, fw.LONG_PRESS, fw.DOUBLE_TAP}
