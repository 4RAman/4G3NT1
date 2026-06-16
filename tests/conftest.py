import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory, MockPWMPin


@pytest.fixture
def mock_pins():
    """gpiozero mock pin factory with PWM support (RGBLED needs it)."""
    old = Device.pin_factory
    Device.pin_factory = MockFactory(pin_class=MockPWMPin)
    yield Device.pin_factory
    Device.pin_factory.close()
    Device.pin_factory = old
