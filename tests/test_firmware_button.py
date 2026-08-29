"""firmware/main.py's button loop, run on the host against a fake pin.

This is the part of the firmware with no host-side counterpart to compare
against: debounce, the hold deadline, polling the double-tap timeout, and
turning what comes out into notify bytes. Watching a device blink is a poor
way to test it, so the MicroPython modules are stubbed and the loop is
driven by a virtual clock: `now_s` advances exactly one poll interval per
iteration, and the pin answers according to that same virtual time. Runs in
milliseconds, and a bounce pattern that would need a real dodgy switch is
just another row in a script.

What this cannot cover is BLE itself - that is what tools/ble_probe.py and
a real ESP32 are for.
"""

import asyncio
import sys
import types

import protocol
import pytest

POLL_S = 0.01  # what main._POLL_S is; the virtual clock advances by this


class VirtualClock:
    """Stands in for clock.now_s: one poll interval per call, so the loop's
    own iteration rate defines virtual time."""

    def __init__(self):
        self.t = 0.0

    def now_s(self):
        self.t += POLL_S
        return self.t


class ScriptedPin:
    """A button that answers according to the virtual clock. `transitions`
    is [(t_seconds, pressed)] - including the ugly ones a real switch does."""

    def __init__(self, clock, transitions):
        self._clock = clock
        self._transitions = sorted(transitions)

    def value(self):
        pressed = False
        for t, state in self._transitions:
            if self._clock.t >= t:
                pressed = state
            else:
                break
        return 0 if pressed else 1  # active low, matching hardware.py


class ReleasedPin:
    """A pin nothing is connected to: the pull-up holds it high for ever.

    What the BOOT button reads as while nobody is touching it, which is the
    state every test here except the two about it should see."""

    def value(self):
        return 1


class PinStub:
    """machine.Pin: constructing one hands back the scripted pin under test.
    The class attributes are there because main.py reads Pin.IN / Pin.PULL_UP
    off the class, exactly as MicroPython exposes them.

    `by_num` is consulted first, because the loop now opens two inputs (the
    wired button and the board's BOOT button) and a test about one of them has
    to be able to hold the other still. `made` counts constructions, which is
    the only way to see from out here that a pin was opened once rather than
    twice."""

    IN = 0
    PULL_UP = 1
    scripted = None
    by_num = {}
    made = []

    def __new__(cls, num, mode, pull):
        cls.made.append(num)
        return cls.by_num.get(num, cls.scripted)


class FakeCharacteristic:
    def __init__(self, *args, **kwargs):
        self.notified = []
        self.value = b""

    def notify(self, connection, data):
        self.notified.append(data)

    async def written(self):
        await asyncio.Event().wait()  # never; this test drives the button only

    def write(self, data):
        """aioble: set the local value a central's read returns."""
        self.value = bytes(data)

    def read(self):
        return self.value


@pytest.fixture(scope="module")
def main():
    """firmware/main.py with the MicroPython-only modules stubbed out.

    `machine` provides Pin and nothing else, so the LED and buzzer backends
    take their "not wired" fallbacks - which is also a check that a board
    with no LED still reports gestures.
    """
    stubs = {
        "aioble": types.SimpleNamespace(
            Service=lambda uuid: types.SimpleNamespace(uuid=uuid),
            Characteristic=FakeCharacteristic,
            register_services=lambda *services: None,
            advertise=None,
        ),
        "bluetooth": types.SimpleNamespace(UUID=str),
        "machine": types.SimpleNamespace(Pin=PinStub),
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    sys.modules.pop("main", None)
    import main as firmware_main

    yield firmware_main

    sys.modules.pop("main", None)
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def test_a_board_with_no_led_or_buzzer_reports_exactly_that(main):
    """This fixture stubs `machine` down to Pin, so both backends take their
    "not wired" fallbacks - which makes it the honest place to check that
    DEVICE_INFO describes what actually came up rather than what hardware.py
    asked for. A capability bit that claims a buzzer nobody can hear is worse
    than no bit at all.
    """
    from aibutton.device import (
        CAP_BUZZER,
        CAP_EFFECT,
        CAP_GESTURE_PARAMS,
        CAP_LED,
        CAP_PALETTE,
        decode_device_info,
    )

    main.ButtonPeripheral()
    info = decode_device_info(main._info_char.read())

    assert info is not None
    assert info.protocol_version == main.protocol.PROTOCOL_VERSION
    assert info.firmware_version == main.protocol.FIRMWARE_VERSION
    assert info.has(CAP_PALETTE)          # this firmware always renders them
    assert info.has(CAP_GESTURE_PARAMS)   # counting taps needs no hardware
    assert not info.has(CAP_LED)          # degraded to NullBackend
    assert not info.has(CAP_BUZZER)       # degraded to NullBuzzer
    # A look is a thing you can only be *shown*, so with no LED this bit is
    # off for the same reason CAP_BUZZER is: claiming it would be a lie the
    # host would then act on.
    assert not info.has(CAP_EFFECT)


async def _run(main, transitions, until, connected=True, max_taps=None, boot=None):
    """Run the button loop over a scripted pin until `until` virtual
    seconds, and return the gesture codes it notified.

    `boot` scripts the board's BOOT button in the same shape; None leaves it
    released, which is what a board nobody is poking at looks like."""
    clock = VirtualClock()
    pin = ScriptedPin(clock, transitions)

    peripheral = main.ButtonPeripheral()
    peripheral._connection = object() if connected else None
    if max_taps is not None:  # what a GESTURE_CONFIG write does
        peripheral._detector.set_max_taps(max_taps)
    main._button_char.notified.clear()

    original_now, original_poll = main.now_s, main._POLL_S
    main.now_s = clock.now_s
    main._POLL_S = 0  # spin as fast as the event loop will go; time is virtual
    PinStub.scripted = pin
    PinStub.made = []
    # The BOOT button, held released unless this test is about it. Explicit
    # rather than left to fall through to `scripted`: an input that mirrored
    # the wired one would make the loop's OR test nothing.
    PinStub.by_num = {
        getattr(main.hardware, "BOOT_BUTTON_PIN", 0): (
            ScriptedPin(clock, boot) if boot else ReleasedPin()
        ),
    }
    try:
        task = asyncio.create_task(peripheral.read_button_forever())
        while clock.t < until and not task.done():
            await asyncio.sleep(0)
        if task.done():  # the loop raised instead of running
            task.result()
        task.cancel()
    finally:
        main.now_s, main._POLL_S = original_now, original_poll
    return [data[0] for data in main._button_char.notified]


async def test_short_press(main):
    # Held 100 ms: too short for a hold, too short to skip the double-tap
    # window, so it emits when that window closes.
    codes = await _run(main, [(0.1, True), (0.2, False)], until=1.0)
    assert codes == [protocol.SHORT_PRESS]


async def test_long_press_fires_while_still_held(main):
    codes = await _run(main, [(0.1, True), (2.0, False)], until=1.6)
    # Emitted at ~1.15 s (press debounced at 0.15 + 1.0 s hold), well before
    # the release at 2.0 s - the point of firing on hold, not on release.
    assert codes == [protocol.LONG_PRESS]


async def test_long_press_release_emits_nothing_more(main):
    codes = await _run(main, [(0.1, True), (1.5, False)], until=2.5)
    assert codes == [protocol.LONG_PRESS]  # the release was consumed


async def test_double_tap(main):
    codes = await _run(
        main, [(0.1, True), (0.2, False), (0.3, True), (0.4, False)], until=1.2
    )
    assert codes == [protocol.DOUBLE_TAP]


async def test_two_slow_taps_are_two_short_presses(main):
    codes = await _run(
        main, [(0.1, True), (0.2, False), (0.8, True), (0.9, False)], until=1.8
    )
    assert codes == [protocol.SHORT_PRESS, protocol.SHORT_PRESS]


async def test_contact_bounce_is_one_press_not_several(main):
    # A switch chattering on both edges: 4 spurious transitions inside the
    # 50 ms debounce window. Without debounce this reads as a double tap.
    codes = await _run(
        main,
        [
            (0.10, True), (0.11, False), (0.12, True), (0.13, False), (0.14, True),
            (0.30, False), (0.31, True), (0.32, False),
        ],
        until=1.2,
    )
    assert codes == [protocol.SHORT_PRESS]


async def test_bounce_does_not_fake_a_long_press(main):
    # Chatter during a hold must not re-arm the press timer and delay (or
    # duplicate) the long press.
    codes = await _run(
        main,
        [(0.1, True), (0.11, False), (0.12, True), (2.0, False)],
        until=1.6,
    )
    assert codes == [protocol.LONG_PRESS]


async def test_presses_while_disconnected_are_dropped_not_queued(main):
    codes = await _run(main, [(0.1, True), (0.2, False)], until=1.0, connected=False)
    assert codes == []


async def test_button_already_held_at_boot_is_not_a_press(main):
    # The BOOT button on a C3 is a strapping pin; whatever state the pin is
    # in at startup is the baseline, not an edge.
    codes = await _run(main, [(0.0, True), (0.5, False)], until=1.5)
    assert codes == []


async def test_notified_codes_are_single_bytes(main):
    """The compatibility promise, checked rather than asserted in a comment: a
    button doing what it has always done still says so the way it always has,
    so a host that only understands one-byte notifies is unaffected by v1."""
    await _run(main, [(0.1, True), (0.2, False)], until=1.0)
    assert all(len(data) == 1 for data in main._button_char.notified)


async def test_a_triple_tap_notifies_a_kind_and_a_count(main):
    """And the other half: a gesture with no legacy code travels as one, which
    is what stops the next tap count from costing a byte of a 255-value
    namespace and a reflash."""
    codes = await _run(
        main,
        [(0.1, True), (0.2, False), (0.3, True), (0.4, False),
         (0.5, True), (0.6, False)],
        until=1.5,
        max_taps=3,
    )
    assert codes == [main.protocol.GESTURE_TAP]
    assert main._button_char.notified == [bytes([main.protocol.GESTURE_TAP, 3])]


async def test_the_same_taps_are_a_double_when_nothing_counts_that_far(main):
    """Same three taps, default settings: the device stops at two and the
    third starts a fresh burst. Counting further is opt-in because it is what
    makes a double tap wait."""
    codes = await _run(
        main,
        [(0.1, True), (0.2, False), (0.3, True), (0.4, False),
         (0.5, True), (0.6, False)],
        until=1.5,
    )
    assert codes == [main.protocol.DOUBLE_TAP, main.protocol.SHORT_PRESS]


# --- when a gesture says it happened ---------------------------------------
# Which gestures fire was covered above; *when* was not, and that is where a
# 50 ms systematic error lived unnoticed. The host subtracts a known constant
# (ButtonDevice.press_latency_s) to recover the moment the finger moved, so an
# error here is one the host cannot see and cannot correct.


async def test_a_press_is_dated_at_the_edge_not_at_the_debounce(main):
    """Press down at 0.10 s: the short press must be emitted one double-tap
    window after *that*, at 0.50 s - not at 0.55 s, a debounce later.

    Asserted as a deadline rather than a timestamp because the harness sees
    notifications, not clocks: at 0.52 s it must already have fired.
    """
    script = [(0.10, True), (0.20, False)]
    assert await _run(main, script, until=0.52) == [protocol.SHORT_PRESS]


async def test_it_has_not_fired_before_the_window_is_actually_up(main):
    """The other side of the same clamp, so the test above cannot be satisfied
    by simply firing early."""
    script = [(0.10, True), (0.20, False)]
    assert await _run(main, script, until=0.48) == []


async def test_a_hold_is_measured_from_the_edge_too(main):
    """One second of holding is one second from when the finger landed, so a
    long press lands at 1.10 s rather than 1.15 s."""
    script = [(0.10, True), (2.0, False)]
    assert await _run(main, script, until=1.12) == [protocol.LONG_PRESS]
    assert await _run(main, script, until=1.05) == []


# --- the board's own BOOT button, always an input (TODO 89) ----------------
# Added the day the wired switch came off the board and a press stopped
# meaning anything. The property under test is that there is no second kind of
# press: both inputs feed the one detector, so every gesture already tested
# above works from either, and nothing downstream can tell which was used.


async def test_the_boot_button_is_a_press(main):
    """The whole point: nothing is wired to GPIO10 and the button still
    works."""
    codes = await _run(
        main, [], until=1.0, boot=[(0.1, True), (0.2, False)],
    )
    assert codes == [protocol.SHORT_PRESS]


async def test_the_boot_button_makes_the_same_gestures(main):
    """Not a second kind of press. It feeds the same detector, so a double tap
    off the BOOT button is a double tap."""
    codes = await _run(
        main, [], until=1.2,
        boot=[(0.1, True), (0.2, False), (0.3, True), (0.4, False)],
    )
    assert codes == [protocol.DOUBLE_TAP]


async def test_both_at_once_is_one_press_not_two(main):
    """They are one button in parallel, so holding both is holding it."""
    codes = await _run(
        main,
        [(0.1, True), (0.3, False)],
        until=1.2,
        boot=[(0.1, True), (0.3, False)],
    )
    assert codes == [protocol.SHORT_PRESS]


async def test_a_press_can_move_from_one_input_to_the_other(main):
    """ORed *before* the debounce, which is what makes this a hold rather than
    a release and a fresh press: letting go of one and taking hold of the
    other is what a person doing it would mean."""
    codes = await _run(
        main,
        [(0.1, True), (0.5, False)],       # wired: held, then released
        until=2.5,
        boot=[(0.45, True), (2.0, False)],  # BOOT: picked up before that
    )
    # One continuous hold across the handover, so it is a long press - not two
    # short ones with a gap.
    assert codes == [protocol.LONG_PRESS]


async def test_the_wired_button_is_unaffected(main):
    """The guard on all of the above: adding an input must not change what the
    one that was already there does."""
    codes = await _run(main, [(0.1, True), (0.2, False)], until=1.0)
    assert codes == [protocol.SHORT_PRESS]


async def test_one_pin_is_opened_when_the_wired_button_is_the_boot_button(
    main, monkeypatch,
):
    """A board whose only switch is on GPIO0 must not poll it twice - and the
    dedupe is in the firmware rather than left to be harmless, because two Pin
    objects on one strapping pin is the kind of thing that is harmless until
    it is not."""
    monkeypatch.setattr(main.hardware, "BUTTON_PIN", 0)
    await _run(main, [(0.1, True), (0.2, False)], until=0.5)
    assert PinStub.made == [0]


async def test_an_older_hardware_py_still_boots(main, monkeypatch):
    """The reason those two settings are read through `getattr`. hardware.py is
    the one file people edit and carry forward, and a copy predating these
    names must degrade to "no BOOT button" rather than raising at startup -
    which on a headless board is indistinguishable from a dead board."""
    monkeypatch.delattr(main.hardware, "BOOT_BUTTON_PIN", raising=False)
    monkeypatch.delattr(main.hardware, "BOOT_BUTTON_ACTIVE_LOW", raising=False)
    codes = await _run(main, [(0.1, True), (0.2, False)], until=1.0)
    assert codes == [protocol.SHORT_PRESS]


def test_hardware_declares_the_boot_button_on_by_default(main):
    """It is "always active" by decision, not by accident - a default of None
    would make every board that never edits hardware.py lose the spare."""
    assert main.hardware.BOOT_BUTTON_PIN == 0
    assert main.hardware.BOOT_BUTTON_ACTIVE_LOW is True
