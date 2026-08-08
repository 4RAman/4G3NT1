"""The firmware's LED and buzzer layers, driven on the host.

Both keep their `machine` imports inside the backend constructors, so the
animation dispatch and tone sequencing can be exercised here against
recording backends - the parts that would otherwise only ever be tested by
watching a device blink.
"""

import asyncio
import sys
import types
from contextlib import contextmanager

import buzzer as fw_buzzer
import hardware as fw_hardware
import led as fw_led
import protocol
import pytest
from tones import LOOP_GAP_MS, TONES

from aibutton.audio import _TONES as HOST_TONES
from aibutton.device import SOUND_CODES


class RecordingLED:
    def __init__(self):
        self.colors = []

    def set(self, r, g, b):
        self.colors.append((round(r, 3), round(g, 3), round(b, 3)))

    def off(self):
        self.set(0, 0, 0)


class RecordingBuzzer:
    def __init__(self):
        self.events = []  # ("tone", hz) / ("silence",)

    def tone(self, freq):
        self.events.append(("tone", freq))

    def silence(self):
        self.events.append(("silence",))

    @property
    def tones(self):
        return [hz for kind, *rest in self.events if kind == "tone" for hz in rest]


@contextmanager
def _fake_machine(neopixel_class):
    """Stand in for the two MicroPython modules `NeoPixelBackend` imports as
    it constructs. They exist only on the device - which is exactly why
    those imports are inside __init__ - so supplying them here is what makes
    the driver itself, and not just the animations above it, testable."""
    machine = types.ModuleType("machine")
    machine.Pin = type("Pin", (), {"OUT": 1, "__init__": lambda self, *a, **k: None})
    neopixel = types.ModuleType("neopixel")
    neopixel.NeoPixel = neopixel_class

    saved = {name: sys.modules.get(name) for name in ("machine", "neopixel")}
    sys.modules["machine"], sys.modules["neopixel"] = machine, neopixel
    try:
        yield
    finally:
        for name, module in saved.items():
            if module is None:
                del sys.modules[name]
            else:
                sys.modules[name] = module


# --- tone tables -------------------------------------------------------

def test_firmware_and_host_tone_tables_match():
    # The host synthesizes WAVs from its table so the web UI's virtual
    # device plays what the buzzer plays. Different tables = a mirror that
    # lies about the hardware.
    by_code = {SOUND_CODES[sound]: segments for sound, segments in HOST_TONES.items()}
    assert TONES == by_code


def test_every_sound_code_has_a_tone():
    assert set(TONES) == set(protocol.SOUND_CODES.values())


# --- LED ---------------------------------------------------------------

def test_every_led_code_has_a_default_effect():
    # A state the host can enter with no palette entry would be an invisible
    # button, so the device's own defaults must cover all of them.
    assert set(fw_led.DEFAULT_PALETTE) == set(protocol.LED_CODES.values())


def test_every_style_has_an_animation():
    controller = fw_led.LEDController(RecordingLED())
    assert set(controller._styles) == set(protocol.STYLE_CODES.values())


def test_unknown_led_code_is_ignored_not_blanked():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(0x7F)
    assert backend.colors == []


async def test_set_state_lights_the_led_and_switching_replaces_it():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)

    controller.set_state(protocol.LED_LISTENING)
    await asyncio.sleep(0.02)
    assert backend.colors[-1] == (1, 1, 0)  # solid yellow

    controller.set_state(protocol.LED_SUCCESS)
    await asyncio.sleep(0.02)
    assert backend.colors[-1] == (0, 1, 0)  # green; the yellow task is gone

    controller.off()
    assert backend.colors[-1] == (0, 0, 0)


async def test_alternate_swaps_between_two_colours():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(protocol.LED_ALERT)  # red/white by default
    await asyncio.sleep(0.5)  # >= one full cycle
    assert (1, 0, 0) in backend.colors and (1, 1, 1) in backend.colors
    controller.off()


async def test_breathe_sweeps_the_whole_range():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(protocol.LED_TIMING)  # cyan, 1.6 s period
    await asyncio.sleep(1.7)
    levels = [g for _r, g, _b in backend.colors]
    assert min(levels) < 0.1 and max(levels) > 0.9
    assert all(r == 0 for r, _g, _b in backend.colors)  # cyan has no red
    controller.off()


async def test_flash_is_full_on_and_full_off():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(protocol.LED_ERROR)  # red flash
    await asyncio.sleep(0.5)
    assert (1, 0, 0) in backend.colors and (0, 0, 0) in backend.colors
    # Unlike breathe, nothing in between.
    assert all(c in ((1, 0, 0), (0, 0, 0)) for c in backend.colors)
    controller.off()


async def test_fade_crossfades_where_alternate_swaps():
    # No default state uses `fade`, so it arrives the way a user's would:
    # written into the palette by the host.
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_effect(
        protocol.LED_IDLE, protocol.STYLE_FADE, (255, 0, 0), (0, 0, 255), 1.0
    )
    controller.set_state(protocol.LED_IDLE)
    await asyncio.sleep(1.1)  # one full cycle
    colors = list(backend.colors)  # before off() adds a black
    controller.off()

    reds = [r for r, _g, _b in colors]
    assert max(reds) > 0.95 and max(b for _r, _g, b in colors) > 0.85  # both ends
    assert any(0.2 < r < 0.8 for r in reds)  # and everything between them
    # A mix of the two colours, never a third one: red fades out exactly as
    # fast as blue fades in, and neither endpoint has any green to borrow.
    assert all(g == 0 for _r, g, _b in colors)
    assert all(abs(r + b - 1) < 0.01 for r, _g, b in colors)


async def test_rainbow_visits_several_hues():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(protocol.LED_THINKING)
    await asyncio.sleep(1.1)  # one full rotation
    assert len(set(backend.colors)) > 10  # a rotation, not a colour
    controller.off()


# --- the palette the host writes ---------------------------------------

async def test_set_effect_changes_what_a_state_looks_like():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_effect(
        protocol.LED_IDLE, protocol.STYLE_SOLID, (255, 128, 0), (0, 0, 0), 1.0
    )
    controller.set_state(protocol.LED_IDLE)
    await asyncio.sleep(0.02)
    r, g, b = backend.colors[-1]
    assert (round(r, 2), round(g, 2), b) == (1.0, 0.5, 0.0)  # orange, not blue
    controller.off()


async def test_editing_the_live_state_restarts_it_immediately():
    # What makes a colour picker usable: you see the change while dragging,
    # without having to make the button re-enter the state.
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(protocol.LED_IDLE)
    await asyncio.sleep(0.02)
    controller.set_effect(
        protocol.LED_IDLE, protocol.STYLE_SOLID, (0, 255, 0), (0, 0, 0), 1.0
    )
    await asyncio.sleep(0.02)
    assert backend.colors[-1] == (0, 1, 0)
    controller.off()


async def test_editing_another_state_does_not_disturb_the_live_one():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    controller.set_state(protocol.LED_LISTENING)
    await asyncio.sleep(0.02)
    controller.set_effect(
        protocol.LED_ERROR, protocol.STYLE_SOLID, (0, 0, 255), (0, 0, 0), 1.0
    )
    await asyncio.sleep(0.05)
    assert backend.colors[-1] == (1, 1, 0)  # still listening yellow
    controller.off()


def test_bad_palette_entries_are_ignored():
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    before = dict(controller._palette)
    controller.set_effect(0x7F, protocol.STYLE_SOLID, (1, 2, 3), (0, 0, 0), 1.0)
    controller.set_effect(protocol.LED_IDLE, 0x7F, (1, 2, 3), (0, 0, 0), 1.0)
    assert controller._palette == before


def test_zero_period_cannot_divide_by_zero():
    effect = fw_led.Effect(protocol.STYLE_BREATHE, (255, 0, 0), period_s=0)
    assert effect.period_s > 0


# --- WS2812 byte order -------------------------------------------------

def test_neopixel_order_places_each_component():
    # ORDER[i] is where component i (R, G, B) goes in the wire buffer.
    assert fw_led.neopixel_order("GRB") == (1, 0, 2, 3)  # the driver default
    assert fw_led.neopixel_order("RGB") == (0, 1, 2, 3)
    assert fw_led.neopixel_order("BGR") == (2, 1, 0, 3)
    assert fw_led.neopixel_order("rgb") == (0, 1, 2, 3)  # case-insensitive


def test_bad_order_falls_back_instead_of_scrambling():
    # A typo must not invent a fourth wrong colour scheme.
    assert fw_led.neopixel_order("RGBW") == (1, 0, 2, 3)
    assert fw_led.neopixel_order("RRG") == (1, 0, 2, 3)
    assert fw_led.neopixel_order(None) == (1, 0, 2, 3)


def test_whole_ring_shows_the_state_not_just_the_first_pixel():
    # The button's LED is a ring on one data line, and every pixel renders
    # the same state - a regression to writing only pixel 0 is invisible
    # anywhere but on the device, so it is caught here instead.
    pixels, written = {}, []

    class FakeNeoPixel:
        ORDER = None

        def __init__(self, _pin, count):
            self.count = count

        def __setitem__(self, i, value):
            pixels[i] = value

        def write(self):
            written.append(dict(pixels))

    with _fake_machine(FakeNeoPixel):
        backend = fw_led.NeoPixelBackend(1, brightness=1.0, order="RGB", count=4)
        backend.set(1.0, 0.0, 0.0)

    assert written[-1] == {i: (255, 0, 0) for i in range(4)}


def test_a_ring_of_zero_pixels_still_constructs():
    # NEOPIXEL_COUNT comes from a hand-edited file; 0 must not mean a
    # NeoPixel of length 0 and a dark button with no error.
    class FakeNeoPixel:
        ORDER = None

        def __init__(self, _pin, count):
            self.count = count

        def __setitem__(self, i, value):
            pass

        def write(self):
            pass

    with _fake_machine(FakeNeoPixel):
        assert fw_led.NeoPixelBackend(1, 1.0, "RGB", count=0)._count == 1


def test_rgb_and_grb_differ_only_by_swapping_red_and_green():
    # The exact symptom this setting exists for: blue is untouched either
    # way, which is why blue looks fine while cyan comes out magenta.
    rgb, grb = fw_led.neopixel_order("RGB"), fw_led.neopixel_order("GRB")
    assert rgb[2] == grb[2]  # blue lands in the same slot
    assert (rgb[0], rgb[1]) == (grb[1], grb[0])  # red and green trade places


def test_hsv_to_rgb_hits_the_primaries():
    assert fw_led._hsv_to_rgb(0.0, 1, 1) == (1, 0, 0)
    assert fw_led._hsv_to_rgb(1 / 3, 1, 1) == (0, 1, 0)
    assert fw_led._hsv_to_rgb(2 / 3, 1, 1) == (0, 0, 1)
    assert fw_led._hsv_to_rgb(0.5, 0, 1) == (1, 1, 1)  # no saturation = white


# --- onboard LED mirroring ----------------------------------------------

def test_multi_backend_fans_out_to_every_led():
    a, b = RecordingLED(), RecordingLED()
    multi = fw_led.MultiBackend([a, b])
    multi.set(1.0, 0.0, 0.0)
    assert a.colors[-1] == b.colors[-1] == (1, 0, 0)
    multi.off()
    assert a.colors[-1] == b.colors[-1] == (0, 0, 0)


def test_multi_backend_survives_one_led_failing():
    # An onboard LED going bad must not blank the one in the button.
    class BrokenLED:
        def set(self, r, g, b):
            raise RuntimeError("no such pin")

        def off(self):
            raise RuntimeError("no such pin")

    good = RecordingLED()
    multi = fw_led.MultiBackend([BrokenLED(), good])
    multi.set(0.0, 1.0, 0.0)
    assert good.colors[-1] == (0, 1, 0)


def test_make_backend_is_just_the_button_led_with_no_onboard_pin(monkeypatch):
    monkeypatch.setattr(fw_hardware, "LED_KIND", "neopixel", raising=False)
    monkeypatch.setattr(fw_hardware, "ONBOARD_NEOPIXEL_PIN", None, raising=False)

    class FakeNeoPixel:
        ORDER = None

        def __init__(self, _pin, count):
            pass

        def __setitem__(self, i, value):
            pass

        def write(self):
            pass

    with _fake_machine(FakeNeoPixel):
        backend = fw_led.make_backend()
    assert isinstance(backend, fw_led.NeoPixelBackend)


def test_make_backend_adds_the_onboard_led_when_configured(monkeypatch):
    monkeypatch.setattr(fw_hardware, "LED_KIND", "neopixel", raising=False)
    monkeypatch.setattr(fw_hardware, "NEOPIXEL_PIN", 1, raising=False)
    monkeypatch.setattr(fw_hardware, "ONBOARD_NEOPIXEL_PIN", 48, raising=False)

    class FakeNeoPixel:
        ORDER = None

        def __init__(self, _pin, count):
            pass

        def __setitem__(self, i, value):
            pass

        def write(self):
            pass

    with _fake_machine(FakeNeoPixel):
        backend = fw_led.make_backend()
    assert isinstance(backend, fw_led.MultiBackend)
    assert len(backend._backends) == 2
    assert all(isinstance(b, fw_led.NeoPixelBackend) for b in backend._backends)


# --- buzzer ------------------------------------------------------------

async def test_play_runs_the_tone_segments_in_order():
    backend = RecordingBuzzer()
    b = fw_buzzer.Buzzer(backend)
    b.play(protocol.SOUND_SUCCESS)
    await asyncio.sleep(0.4)  # 90 + 160 ms of tone
    assert backend.tones == [660, 990]
    assert backend.events[-1] == ("silence",)  # never leaves the pin driven


async def test_rests_are_silence_not_tones():
    backend = RecordingBuzzer()
    b = fw_buzzer.Buzzer(backend)
    b.play(protocol.SOUND_ERROR)  # 220, rest, 220, rest, 220
    await asyncio.sleep(0.7)
    assert backend.tones == [220, 220, 220]


async def test_loop_repeats_until_stopped():
    backend = RecordingBuzzer()
    b = fw_buzzer.Buzzer(backend)
    b.play(protocol.SOUND_ACK | protocol.LOOP)
    await asyncio.sleep(0.1)
    assert backend.tones == [880]  # first pass; the gap is a full second
    b.stop()
    played = len(backend.tones)
    await asyncio.sleep(LOOP_GAP_MS / 1000 + 0.1)
    assert len(backend.tones) == played  # nothing after the stop


async def test_stop_loop_command_silences_a_ringing_alarm():
    backend = RecordingBuzzer()
    b = fw_buzzer.Buzzer(backend)
    b.play(protocol.SOUND_ALARM | protocol.LOOP)
    await asyncio.sleep(0.05)
    b.play(protocol.STOP_LOOP)
    assert backend.events[-1] == ("silence",)
    played = len(backend.tones)
    await asyncio.sleep(0.5)
    assert len(backend.tones) == played


async def test_a_new_sound_replaces_the_one_playing():
    backend = RecordingBuzzer()
    b = fw_buzzer.Buzzer(backend)
    b.play(protocol.SOUND_ERROR)  # long, with rests
    await asyncio.sleep(0.05)
    b.play(protocol.SOUND_ACK)
    await asyncio.sleep(0.15)
    assert backend.tones[-1] == 880


async def test_unknown_sound_is_ignored():
    backend = RecordingBuzzer()
    b = fw_buzzer.Buzzer(backend)
    b.play(0x7E)
    await asyncio.sleep(0.05)
    assert backend.tones == []


@pytest.mark.parametrize("cmd", [protocol.STOP_LOOP, 0x7E])
async def test_quiet_commands_never_raise(cmd):
    b = fw_buzzer.Buzzer(RecordingBuzzer())
    b.play(cmd)
    await asyncio.sleep(0.02)
    b.stop()
