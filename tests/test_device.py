"""MockDevice, and the ButtonDevice contract every backend has to keep."""

import inspect
import sys
from pathlib import Path

import pytest

from aibutton.device import (
    GESTURE_TAP,
    ButtonDevice,
    LEDState,
    MockDevice,
    Sound,
    TriggerType,
    decode_gesture,
    gesture_config_payload,
    max_taps_for,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware"))
import protocol  # noqa: E402  - the device's own copy, run under CPython


async def test_press_queues_the_gesture():
    device = MockDevice()
    device.press(TriggerType.DOUBLE_TAP)
    assert device.events.get_nowait() is TriggerType.DOUBLE_TAP
    assert device.events.empty()


async def test_feedback_is_recorded():
    device = MockDevice()
    assert device.led_state is LEDState.IDLE
    device.set_led(LEDState.THINKING)
    device.play_sound(Sound.ACK)
    assert device.led_state is LEDState.THINKING
    assert device.last_sound is Sound.ACK
    assert device.looping is None


async def test_loop_starts_and_stops():
    device = MockDevice()
    device.start_loop(Sound.ALARM)
    assert device.looping is Sound.ALARM
    assert device.last_sound is Sound.ALARM  # the ring is audible immediately
    device.stop_loop()
    assert device.looping is None


async def test_close_is_awaitable_and_leaves_the_device_quiet():
    device = MockDevice()
    device.start_loop(Sound.ALARM)
    await device.close()
    assert device.looping is None


def test_devices_share_one_queue_and_press_implementation():
    # press() is concrete on the base class precisely so a simulated press
    # takes the same path as a real one on every backend.
    assert MockDevice.press is ButtonDevice.press
    assert inspect.iscoroutinefunction(ButtonDevice.close)


def test_five_taps_reaches_the_host_with_no_reflash_under_it():
    """The promise protocol v1 made: a new tap count is a host-side data
    change. The firmware has named 4..9 since v1 shipped, so this asserts the
    whole path against the *device's own* encoder rather than a hand-written
    payload - which is what proves no reflash is involved."""
    payload = protocol.gesture_payload("tap_5")
    assert payload == bytes([GESTURE_TAP, 5])
    assert decode_gesture(payload) is TriggerType.TAP_5


def test_a_count_the_host_cannot_name_is_dropped_rather_than_guessed():
    """Four taps is deliberately unnamed: a stray extra tap on a triple should
    do nothing, not something else."""
    assert decode_gesture(protocol.gesture_payload("tap_4")) is None


def test_binding_five_taps_is_what_makes_the_button_count_that_far():
    """Nobody sets max_taps by hand - it is derived from what is bound, so the
    cost of counting is paid only by a button that has a long tap on it."""
    assert max_taps_for([TriggerType.DOUBLE_TAP]) == 2
    assert max_taps_for([TriggerType.TAP_5]) == 5
    assert gesture_config_payload(max_taps_for([TriggerType.TAP_5])) == bytes([5])
    assert protocol.decode_gesture_config(bytes([5])) == 5


def test_incomplete_backend_cannot_be_instantiated():
    class HalfDevice(ButtonDevice):
        def set_led(self, state): ...

    with pytest.raises(TypeError):
        HalfDevice()
