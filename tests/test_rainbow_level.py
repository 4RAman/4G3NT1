"""A rainbow's brightness and saturation, and the mirrors they keep in step.

The colour bytes were discarded for this style before, so giving them a meaning
is an addition rather than a repurpose - but only if nothing that was written
earlier is now misread. That compatibility rule is the first thing asserted
here, because it is the one that costs a reflash to get wrong.
"""

import asyncio
import re
import sys
from pathlib import Path

import pytest

from aibutton.device import (
    CAP_RAINBOW_LEVEL,
    CAP_RAINBOW_SAT,
    CAPABILITY_NAMES,
    STYLE_USES_COLOR,
    STYLE_USES_COLOR2,
    STYLE_USES_LEVEL,
    STYLE_USES_SATURATION,
    LED_STYLES,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware"))
import led as fw_led  # noqa: E402
import protocol  # noqa: E402

_SCHEMA = Path(__file__).resolve().parents[1] / "aibutton" / "web" / "static" / "schema.js"


class RecordingLED:
    """Whatever the controller pushed, in order."""

    def __init__(self):
        self.colors = []
        self.usable = True

    def set(self, r, g, b):
        self.colors.append((r, g, b))

    def off(self):
        self.set(0, 0, 0)


async def _sweep(color, seconds=0.4, color2=(0, 0, 0)):
    """One rainbow's worth of frames at `color` (brightness) and `color2`
    (saturation)."""
    backend = RecordingLED()
    controller = fw_led.LEDController(backend)
    # show_effect, not set_effect: the latter only *starts* an entry when that
    # state is already on screen, so a palette write with nothing showing
    # renders nothing - which is correct, and is why a one-off look has its own
    # call.
    controller.show_effect(protocol.STYLE_RAINBOW, color, color2, 0.3)
    await asyncio.sleep(seconds)
    frames = list(backend.colors)
    controller.off()
    return frames


def _peak(colors):
    """The brightest channel anything reached over the sweep - a rainbow visits
    every hue, so at full value some frame hits the top of the range."""
    return max(max(frame) for frame in colors if any(frame))


# --- the compatibility rule -------------------------------------------------

async def test_a_rainbow_written_before_this_existed_still_renders_full():
    """Every rainbow saved earlier carried whatever was in the colour field,
    very often #000000. Reading that as "off" would black out configs on
    reflash, and a rainbow nobody can see is not something anyone configures -
    so zero means full."""
    colors = await _sweep((0, 0, 0))
    assert _peak(colors) == pytest.approx(1.0, abs=0.02)


async def test_full_white_is_also_full_brightness():
    colors = await _sweep((255, 255, 255))
    assert _peak(colors) == pytest.approx(1.0, abs=0.02)


# --- what the setting does --------------------------------------------------

@pytest.mark.parametrize("level,expected", [(64, 0.25), (128, 0.5), (191, 0.75)])
async def test_the_brightest_channel_sets_the_brightness(level, expected):
    colors = await _sweep((level, level, level))
    assert _peak(colors) == pytest.approx(expected, abs=0.05)


async def test_a_dim_rainbow_is_still_a_rainbow():
    """Brightness must scale the hues, not collapse them - the point of the
    style survives being turned down."""
    colors = await _sweep((128, 128, 128))
    lit = [frame for frame in colors if any(frame)]
    # Some frame is mostly red, some mostly green or blue: the hue still turns.
    assert any(r > g and r > b for r, g, b in lit)
    assert any(g > r or b > r for r, g, b in lit)


async def test_brightness_comes_off_the_brightest_channel_not_the_average():
    """A saturated colour dragged into the field should not read as dim -
    it is a *level*, and the level of #ff0000 is full."""
    colors = await _sweep((255, 0, 0))
    assert _peak(colors) == pytest.approx(1.0, abs=0.02)


# --- saturation, the second reading of the same trick ----------------------


def _greyness(colors):
    """How close to white the most colourful frame got: 0 is a pure hue, 1 is
    white. `1 - (max-min)/max` is HSV saturation read back off the pixel."""
    lit = [frame for frame in colors if any(frame)]
    return min(1.0 - (max(f) - min(f)) / max(f) for f in lit)


async def test_a_rainbow_written_before_saturation_existed_is_full_strength():
    """`color2` was discarded for this style, so it is almost always #000000 -
    and reading that as "no saturation" would turn every rainbow ever saved
    into a plain white blink. Zero means full, exactly as it does for the
    brightness one field over."""
    colors = await _sweep((255, 255, 255), color2=(0, 0, 0))
    assert _greyness(colors) == pytest.approx(0.0, abs=0.02)


async def test_turning_the_strength_down_walks_the_cycle_towards_white():
    weak = await _sweep((255, 255, 255), color2=(64, 64, 64))
    strong = await _sweep((255, 255, 255), color2=(255, 255, 255))
    assert _greyness(weak) > _greyness(strong)
    assert _greyness(weak) == pytest.approx(0.75, abs=0.05)


async def test_a_washed_out_rainbow_is_still_a_rainbow():
    """Strength must tint the hues, not flatten them - a low setting is pale
    colour, not the absence of colour."""
    colors = await _sweep((255, 255, 255), color2=(64, 64, 64))
    lit = [frame for frame in colors if any(frame)]
    assert any(r > g and r > b for r, g, b in lit)
    assert any(g > r or b > r for r, g, b in lit)


async def test_brightness_and_strength_are_independent():
    """Two fields, two properties: turning the colour down must not turn the
    light down, or the two sliders would fight over one axis."""
    colors = await _sweep((128, 128, 128), color2=(64, 64, 64))
    assert _peak(colors) == pytest.approx(0.5, abs=0.05)
    assert _greyness(colors) == pytest.approx(0.75, abs=0.05)


# --- the mirrors ------------------------------------------------------------

@pytest.mark.parametrize("host,name", [
    (CAP_RAINBOW_LEVEL, "CAP_RAINBOW_LEVEL"),
    (CAP_RAINBOW_SAT, "CAP_RAINBOW_SAT"),
])
def test_the_capability_bit_matches_the_firmware(host, name):
    assert host == getattr(protocol, name)
    assert host in CAPABILITY_NAMES


def test_the_new_bit_did_not_land_on_an_existing_one():
    """A capability namespace is one-way: two features on one bit cannot be
    told apart afterwards, and there is no way to reflash a device you do not
    have."""
    bits = [
        value for name, value in vars(protocol).items()
        if name.startswith("CAP_") and isinstance(value, int)
    ]
    assert len(bits) == len(set(bits))


def test_rainbow_reads_a_level_and_not_a_colour():
    """The two sets stay disjoint: a style either shows a hue you picked or
    generates its own. Something in both would make the editor offer a colour
    picker and a brightness slider for the same byte."""
    assert STYLE_USES_LEVEL == {"rainbow"}
    assert not (STYLE_USES_LEVEL & STYLE_USES_COLOR)
    assert STYLE_USES_LEVEL <= set(LED_STYLES)


def test_rainbow_reads_a_strength_and_not_a_second_colour():
    """The same rule one field over, and the same failure if it broke: a
    style in both sets would offer a second colour picker and a strength
    slider for one byte, and only one of them could be telling the truth."""
    assert STYLE_USES_SATURATION == {"rainbow"}
    assert not (STYLE_USES_SATURATION & STYLE_USES_COLOR2)
    assert STYLE_USES_SATURATION <= set(LED_STYLES)


def test_the_editor_agrees_about_which_styles_take_a_level():
    """schema.js decides which control renders; device.py decides what the
    byte means. One of them changing alone is the drift CLAUDE.md says to test
    rather than trust."""
    source = _SCHEMA.read_text(encoding="utf-8")
    in_js = {
        match.group(1)
        for match in re.finditer(
            r"\{\s*type:\s*'(\w+)',[^}]*?uses:\s*\[([^\]]*)\]", source, re.S
        )
        if "'level'" in match.group(2)
    }
    assert in_js == STYLE_USES_LEVEL


def test_the_editor_agrees_about_which_styles_take_a_strength():
    source = _SCHEMA.read_text(encoding="utf-8")
    in_js = {
        match.group(1)
        for match in re.finditer(
            r"\{\s*type:\s*'(\w+)',[^}]*?uses:\s*\[([^\]]*)\]", source, re.S
        )
        if "'saturation'" in match.group(2)
    }
    assert in_js == STYLE_USES_SATURATION
