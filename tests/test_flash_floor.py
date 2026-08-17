"""The flash floor: what it protects, and what it deliberately does not.

The floor is a photosensitivity limit (WCAG 2.3.1's 3 flashes/second) that is
also a *setting*, and those two facts pull in opposite directions - so the
scenarios worth pinning are the ones where they meet: a value below the
recommendation is honoured and complained about, a value that is not a number
at all is not, and no path to the light can route around whatever the effective
number is.
"""

import json
import re
from pathlib import Path

import httpx
import pytest

from aibutton.audio import ToneLibrary
from aibutton.config import (
    AppConfig,
    ConfigManager,
    LedEffect,
    as_dict,
    flash_safe,
    parse_config,
    parse_with_warnings,
)
from aibutton.device import SAFE_MIN_PERIOD_S, STYLE_STROBES, LED_STYLES, MockDevice
from aibutton.main import Clock, DeviceStatus, metronome_flash
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app

_SCHEMA = Path(__file__).resolve().parents[1] / "aibutton" / "web" / "static" / "schema.js"


# --- the pure floor --------------------------------------------------------

@pytest.mark.parametrize("style", sorted(STYLE_STROBES))
def test_a_strobing_style_is_slowed_to_the_floor(style):
    raised = flash_safe(LedEffect(style=style, period_s=0.02), 1 / 3)
    assert raised.period_s == pytest.approx(1 / 3)


@pytest.mark.parametrize("style", ["breathe", "fade", "rainbow", "solid"])
def test_a_style_that_does_not_strobe_keeps_its_period(style):
    """A fast breathe is a shimmer, not a strobe. Flooring it would cost the
    slowest legal fade a third of a second and buy nothing."""
    kept = flash_safe(LedEffect(style=style, period_s=0.02), 1 / 3)
    assert kept.period_s == pytest.approx(0.02)


def test_an_effect_already_inside_the_floor_is_returned_untouched():
    original = LedEffect(style="flash", period_s=2.0)
    assert flash_safe(original, 1 / 3) is original


def test_no_override_stays_no_override():
    """None is what set_led means by 'use the palette', and the palette has
    been through the floor already - inventing an effect here would turn a
    cheap no-op into a wire write."""
    assert flash_safe(None, 1 / 3) is None


def test_raising_the_setting_slows_the_light_further():
    """The setting is the floor, not a floor under a floor."""
    assert flash_safe(LedEffect(style="flash", period_s=0.5), 2.0).period_s == pytest.approx(2.0)


def test_lowering_the_setting_lets_the_light_go_faster():
    kept = flash_safe(LedEffect(style="flash", period_s=0.1), 0.05)
    assert kept.period_s == pytest.approx(0.1)


# --- the setting -----------------------------------------------------------

def test_the_default_is_the_recommended_limit():
    assert parse_config({}).min_flash_period_s == pytest.approx(SAFE_MIN_PERIOD_S)
    assert SAFE_MIN_PERIOD_S == pytest.approx(1 / 3), "3 flashes/second, per WCAG 2.3.1"


def test_going_faster_than_the_recommendation_is_honoured_and_warned_about():
    """The whole reason this is a setting: someone may mean it. Silently
    clamping would make the setting a lie; silently accepting would make the
    hazard invisible."""
    cfg, warnings = parse_with_warnings({"min_flash_period_s": 0.1})
    assert cfg.min_flash_period_s == pytest.approx(0.1)
    assert any("photosensitivity" in w for w in warnings)


def test_a_meaningless_floor_falls_back_like_any_other_bad_key():
    for bad in (0, -1, "fast", None):
        cfg = parse_config({"min_flash_period_s": bad})
        assert cfg.min_flash_period_s == pytest.approx(SAFE_MIN_PERIOD_S)


def test_a_slower_floor_needs_no_warning():
    _, warnings = parse_with_warnings({"min_flash_period_s": 1.0})
    assert not [w for w in warnings if "photosensitivity" in w]


def test_the_setting_round_trips_through_the_editor():
    cfg = parse_config({"min_flash_period_s": 0.5})
    assert parse_config(as_dict(cfg)).min_flash_period_s == pytest.approx(0.5)


# --- the consumers ---------------------------------------------------------

@pytest.mark.parametrize("bpm", [1, 45, 179, 180, 181, 240, 600, 3000])
@pytest.mark.parametrize("floor", [0.1, 1 / 3, 1.0])
def test_no_tempo_can_blink_past_whichever_floor_is_configured(bpm, floor):
    """The metronome's guarantee, restated over the setting rather than over
    the old constant: raising the limit must slow the light at every tempo,
    not just the ones near the old number."""
    period, _ = metronome_flash(bpm, floor)
    assert period >= floor


def test_metronome_defaults_to_the_recommendation_when_handed_nothing():
    period, _ = metronome_flash(3000)
    assert period >= SAFE_MIN_PERIOD_S


# --- the test bench cannot route around it ---------------------------------

@pytest.fixture
def ctx(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"ble_device_name": "TestBtn"}), encoding="utf-8")
    store = EventStore(str(tmp_path / "events.db"))
    tones = ToneLibrary()
    context = WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        device=MockDevice(),
        clock=Clock(),
        tones=tones,
    )
    yield context
    store.close()
    tones.close()


@pytest.fixture
async def client(ctx):
    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_the_light_test_bench_is_subject_to_the_floor(client):
    """A bench that could strobe past the configured limit would be a hole in
    the floor rather than a test of the light."""
    res = await client.post("/api/dev/led", json={"style": "flash", "period_s": 0.02})
    assert res.status_code == 200
    assert res.json()["effect"]["period_s"] == pytest.approx(SAFE_MIN_PERIOD_S)


async def test_the_bench_reports_what_is_actually_on_the_light(client, ctx):
    """What comes back has to be what was pushed, or the page is describing a
    look nobody is seeing."""
    res = await client.post("/api/dev/led", json={"style": "flash", "period_s": 0.02})
    assert res.json()["effect"]["period_s"] == pytest.approx(
        ctx.status.led_effect.period_s
    )


async def test_the_bench_leaves_a_breathe_alone(client):
    res = await client.post("/api/dev/led", json={"style": "breathe", "period_s": 0.05})
    assert res.json()["effect"]["period_s"] == pytest.approx(0.05)


# --- the mirrored table ----------------------------------------------------

def test_which_styles_strobe_has_not_drifted_from_the_editor():
    """STYLE_STROBES ships to the host and `strobes: true` ships to the
    browser; one of them deciding a style is safe while the other does not is
    exactly the drift CLAUDE.md says to test rather than trust."""
    source = _SCHEMA.read_text(encoding="utf-8")
    in_js = {
        match.group(1)
        for match in re.finditer(
            r"\{\s*type:\s*'(\w+)'[^}]*?strobes:\s*true", source, re.S
        )
    }
    assert in_js == STYLE_STROBES


def test_every_strobing_style_is_a_real_style():
    assert STYLE_STROBES <= set(LED_STYLES)
