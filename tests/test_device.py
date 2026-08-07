"""MockDevice, and the ButtonDevice contract every backend has to keep."""

import inspect

import pytest

from aibutton.device import ButtonDevice, LEDState, MockDevice, Sound, TriggerType


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


def test_incomplete_backend_cannot_be_instantiated():
    class HalfDevice(ButtonDevice):
        def set_led(self, state): ...

    with pytest.raises(TypeError):
        HalfDevice()
