# LED state animations, rendered on-device from a host-supplied palette.
#
# The wire carries a state, not frames: the host writes one LED_STATE byte and
# the effect for that state runs here until the next write. What each state
# *looks* like is the palette (style, colours, period), which the host writes on
# connect and on every edit; DEFAULT_PALETTE below is only what an ESP32 shows
# when no host has told it otherwise. set_state() cancels the running animation
# and starts the new one, then returns - a BLE write must never wait on a fade.
#
# Hardware imports live inside the backend constructors, so this module is
# importable (and its animation maths testable) on the host.

import asyncio

import hardware
import protocol
from clock import now_s

_FRAME_S = 0.05  # 20 fps - smooth fades, nothing for a 240 MHz MCU


def _hsv_to_rgb(hue, sat, val):
    """HSV (each 0..1) -> (r, g, b) each 0..1. MicroPython has no colorsys."""
    i = int(hue * 6.0)
    f = hue * 6.0 - i
    p = val * (1.0 - sat)
    q = val * (1.0 - sat * f)
    t = val * (1.0 - sat * (1.0 - f))
    i = i % 6
    if i == 0:
        return val, t, p
    if i == 1:
        return q, val, p
    if i == 2:
        return p, val, t
    if i == 3:
        return p, q, val
    if i == 4:
        return t, p, val
    return val, p, q


def _scale(rgb, level):
    return (rgb[0] * level, rgb[1] * level, rgb[2] * level)


def _mix(a, b, level):
    """`level` 0..1 walks from a to b, component by component."""
    return (
        a[0] + (b[0] - a[0]) * level,
        a[1] + (b[1] - a[1]) * level,
        a[2] + (b[2] - a[2]) * level,
    )


def _norm(rgb):
    """(0-255, ...) -> (0.0-1.0, ...)"""
    return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)


_GRB_ORDER = (1, 0, 2, 3)  # what MicroPython's neopixel driver defaults to


def neopixel_order(name):
    """'RGB'/'GRB'/'BGR'... -> the driver's ORDER tuple, where ORDER[i] is where
    component i lands in the wire buffer. Derived from the name so any
    permutation works without a lookup table; an unrecognised name keeps the
    driver default rather than scrambling colours in a new way."""
    name = str(name).upper()
    if sorted(name) != ["B", "G", "R"]:
        print("led: NEOPIXEL_ORDER %r is not a permutation of RGB - using GRB" % name)
        return _GRB_ORDER
    return (name.index("R"), name.index("G"), name.index("B"), 3)


class Effect:
    """One palette entry: how a state looks."""

    def __init__(self, style, color, color2=(0, 0, 0), period_s=1.0):
        self.style = style
        self.color = color
        self.color2 = color2
        self.period_s = period_s if period_s > 0 else 1.0


# Used until the host says otherwise - the colours the project has always had.
DEFAULT_PALETTE = {
    protocol.LED_IDLE: Effect(protocol.STYLE_BREATHE, (0, 0, 255), period_s=3.0),
    protocol.LED_LISTENING: Effect(protocol.STYLE_SOLID, (255, 255, 0)),
    protocol.LED_THINKING: Effect(protocol.STYLE_RAINBOW, (255, 255, 255), period_s=1.0),
    protocol.LED_SUCCESS: Effect(protocol.STYLE_SOLID, (0, 255, 0)),
    protocol.LED_ERROR: Effect(protocol.STYLE_FLASH, (255, 0, 0), period_s=0.4),
    protocol.LED_ALERT: Effect(protocol.STYLE_ALTERNATE, (255, 0, 0), (255, 255, 255), 0.4),
    protocol.LED_TIMING: Effect(protocol.STYLE_BREATHE, (0, 255, 255), period_s=1.6),
    protocol.LED_COUNTING: Effect(protocol.STYLE_BREATHE, (255, 0, 255), period_s=2.2),
    # Slow enough to sit next to you for 25 minutes without nagging.
    protocol.LED_WORKING: Effect(protocol.STYLE_BREATHE, (255, 68, 0), period_s=5.0),
    protocol.LED_RESTING: Effect(protocol.STYLE_BREATHE, (0, 255, 136), period_s=5.0),
    # ~120 BPM until a tap sets a real tempo; the host rewrites period_s live.
    protocol.LED_METRONOME: Effect(protocol.STYLE_FLASH, (255, 170, 0), period_s=0.5),
}


class NullBackend:
    """No LED wired. The button still works; you just can't see it."""

    # Read by DEVICE_INFO: a capability bit that lies is worse than no bit at
    # all, so CAP_LED means one actually came up, not that hardware.py asked.
    usable = False

    def set(self, r, g, b):
        pass

    def off(self):
        pass


class NeoPixelBackend:
    """WS2812s on one data line - the ring inside the button, or the onboard
    RGB on an S3/C3 dev board. Every pixel is written the same colour: the
    LED is one indicator, so a ring is a bigger indicator, not a display."""

    usable = True

    def __init__(self, pin, brightness, order="GRB", count=1):
        from machine import Pin
        from neopixel import NeoPixel

        self._count = count if count > 0 else 1
        self._np = NeoPixel(Pin(pin, Pin.OUT), self._count)
        # The driver ships assuming a GRB strip and reorders for you; on a board
        # wired RGB that reorder *is* the bug.
        self._np.ORDER = neopixel_order(order)
        self._brightness = brightness

    def set(self, r, g, b):
        scale = 255 * self._brightness
        pixel = (int(r * scale), int(g * scale), int(b * scale))
        for i in range(self._count):
            self._np[i] = pixel
        self._np.write()

    def off(self):
        self.set(0, 0, 0)


class MultiBackend:
    """Fans one state out to several physical LEDs - the button's own WS2812 and
    the board's onboard one, lit the same. Each `set`/`off` reaches every
    backend even if one raises, so a bad onboard LED can't blank the button's."""

    def __init__(self, backends):
        self._backends = backends
        # One working LED is enough to claim the capability, even if the other
        # failed to come up.
        self.usable = any(getattr(b, "usable", True) for b in backends)

    def set(self, r, g, b):
        for backend in self._backends:
            try:
                backend.set(r, g, b)
            except Exception as exc:  # noqa: BLE001 - one LED's fault, not the other's
                print("led: backend failed (%s)" % exc)

    def off(self):
        for backend in self._backends:
            try:
                backend.off()
            except Exception as exc:  # noqa: BLE001
                print("led: backend failed (%s)" % exc)


class PWMBackend:
    """A discrete RGB LED, one PWM channel per colour (330R per channel)."""

    usable = True

    def __init__(self, pins, active_high, freq):
        from machine import PWM, Pin

        self._channels = [PWM(Pin(p), freq=freq, duty_u16=0) for p in pins]
        self._active_high = active_high

    def set(self, r, g, b):
        for channel, level in zip(self._channels, (r, g, b)):
            level = 0.0 if level < 0 else (1.0 if level > 1 else level)
            if not self._active_high:
                level = 1.0 - level
            channel.duty_u16(int(level * 65535))

    def off(self):
        self.set(0, 0, 0)


def _announce(what, pin):
    """Say out loud which pin we think an LED is on.

    A WS2812 has no readback, and `NeoPixel(Pin(n))` constructs happily for any
    valid GPIO - so a wrong pin number fails *silently*, with no exception and
    no log, just an LED that never lights. Printing the assumption is what turns
    "it's dark and I don't know why" into "it's dark and it thinks it's on 48".
    """
    print("led: %s on GPIO%s" % (what, pin))


def _make_primary_backend():
    """The LED described by LED_KIND. A miswired or unsupported LED must not
    stop the button from reporting gestures, so failures degrade to
    NullBackend with a printed reason rather than a boot loop."""
    try:
        if hardware.LED_KIND == "neopixel":
            backend = NeoPixelBackend(
                hardware.NEOPIXEL_PIN,
                hardware.LED_BRIGHTNESS,
                getattr(hardware, "NEOPIXEL_ORDER", "GRB"),
                getattr(hardware, "NEOPIXEL_COUNT", 1),
            )
            _announce("WS2812", hardware.NEOPIXEL_PIN)
            return backend
        if hardware.LED_KIND == "rgb_pwm":
            backend = PWMBackend(
                hardware.RGB_PINS, hardware.RGB_ACTIVE_HIGH, hardware.RGB_PWM_FREQ
            )
            print("led: RGB LED on GPIOs %s" % (tuple(hardware.RGB_PINS),))
            return backend
    except Exception as exc:  # noqa: BLE001 - any driver failure, same fallback
        print("led: %s backend failed (%s) - running dark" % (hardware.LED_KIND, exc))
        return NullBackend()
    return NullBackend()


def _make_onboard_backend():
    """The board's own WS2812, if ONBOARD_NEOPIXEL_PIN says one exists. Same
    degrade-to-dark rule as the primary LED, and more so - it is a bonus
    indicator, not one the button can afford to crash over."""
    pin = getattr(hardware, "ONBOARD_NEOPIXEL_PIN", None)
    if pin is None:
        return None
    try:
        backend = NeoPixelBackend(
            pin,
            getattr(hardware, "ONBOARD_LED_BRIGHTNESS", 0.25),
            getattr(hardware, "ONBOARD_NEOPIXEL_ORDER", "GRB"),
            1,
        )
    except Exception as exc:  # noqa: BLE001 - same fallback as the primary LED
        print("led: onboard backend failed (%s) - running dark" % exc)
        return None
    _announce("onboard WS2812", pin)
    return backend


def make_backend():
    """The LED(s) described by hardware.py - just the one in the button, or
    that one plus the board's onboard LED mirroring it, if configured."""
    backends = [_make_primary_backend()]
    onboard = _make_onboard_backend()
    if onboard is not None:
        backends.append(onboard)
    return backends[0] if len(backends) == 1 else MultiBackend(backends)


class LEDController:
    """Public surface: set_state(code), set_effect(...) and off()."""

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else make_backend()
        self._task = None
        self._state = None
        self._palette = dict(DEFAULT_PALETTE)
        self._styles = {
            protocol.STYLE_SOLID: self._solid,
            protocol.STYLE_BREATHE: self._breathe,
            protocol.STYLE_FLASH: self._flash,
            protocol.STYLE_ALTERNATE: self._alternate,
            protocol.STYLE_RAINBOW: self._rainbow,
            protocol.STYLE_FADE: self._fade,
        }

    def set_state(self, code):
        """Switch animations. Non-blocking. An unknown code is ignored, so a
        newer host can't blank the LED by writing a state we don't have."""
        effect = self._palette.get(code)
        if effect is None:
            print("led: unknown state 0x%02x - ignored" % code)
            return
        self._state = code
        self._start(effect)

    def set_effect(self, code, style, color, color2, period_s):
        """Apply one palette entry from the host. If it is the state showing
        right now, restart it so an edit in the web UI is visible while you
        are making it - which is the whole point of a colour picker."""
        if code not in self._palette:
            print("led: palette entry for unknown state 0x%02x - ignored" % code)
            return
        if style not in self._styles:
            print("led: unknown style 0x%02x - ignored" % style)
            return
        self._palette[code] = Effect(style, color, color2, period_s)
        if code == self._state:
            self._start(self._palette[code])

    def show_effect(self, style, color, color2, period_s):
        """Render a look that belongs to no state, until the next set_state().

        The palette is left alone: this is a thing the host is *showing*, not a
        thing it is changing. `_state` is cleared because nothing named is on
        screen any more, so a palette edit arriving mid-effect updates the
        stored entry without yanking the light off what it is displaying.
        """
        if style not in self._styles:
            print("led: unknown style 0x%02x - ignored" % style)
            return
        self._state = None
        self._start(Effect(style, color, color2, period_s))

    @property
    def usable(self):
        """Whether an LED actually came up - reported over DEVICE_INFO."""
        return getattr(self._backend, "usable", True)

    def off(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._backend.off()

    def _start(self, effect):
        if self._task is not None:
            self._task.cancel()
        self._task = asyncio.create_task(self._run(effect))

    async def _run(self, effect):
        animation = self._styles.get(effect.style, self._solid)
        try:
            await animation(effect)
        except asyncio.CancelledError:
            pass  # a newer state took over
        except Exception as exc:  # noqa: BLE001 - an animation bug must not kill BLE
            print("led: animation crashed (%s)" % exc)

    # --- the six styles -----------------------------------------------
    # Every one runs forever: the host decides when a state ends (it already
    # holds SUCCESS for two seconds, then writes IDLE), so nothing here needs to
    # know how long anything lasts.

    async def _solid(self, effect):
        self._backend.set(*_norm(effect.color))
        while True:
            await asyncio.sleep(1)

    async def _breathe(self, effect):
        """Triangle-wave fade rather than a cosine: indistinguishable to the
        eye, and it avoids importing math for one call."""
        color = _norm(effect.color)
        start = now_s()
        while True:
            phase = ((now_s() - start) % effect.period_s) / effect.period_s
            level = 2 * phase if phase < 0.5 else 2 * (1 - phase)
            self._backend.set(*_scale(color, level))
            await asyncio.sleep(_FRAME_S)

    async def _flash(self, effect):
        color = _norm(effect.color)
        half = effect.period_s / 2
        while True:
            self._backend.set(*color)
            await asyncio.sleep(half)
            self._backend.off()
            await asyncio.sleep(half)

    async def _alternate(self, effect):
        first, second = _norm(effect.color), _norm(effect.color2)
        half = effect.period_s / 2
        while True:
            self._backend.set(*first)
            await asyncio.sleep(half)
            self._backend.set(*second)
            await asyncio.sleep(half)

    async def _fade(self, effect):
        """`alternate` with the swap smoothed out: the same triangle wave as
        _breathe, but crossfading to colour2 instead of down to black."""
        first, second = _norm(effect.color), _norm(effect.color2)
        start = now_s()
        while True:
            phase = ((now_s() - start) % effect.period_s) / effect.period_s
            level = 2 * phase if phase < 0.5 else 2 * (1 - phase)
            self._backend.set(*_mix(first, second, level))
            await asyncio.sleep(_FRAME_S)

    async def _rainbow(self, effect):
        """Hue rotates a full turn per period.

        The colour is not a *hue* here - a rainbow is all of them - but its
        brightest channel is the **brightness**, which is the one thing about a
        rainbow worth setting. An addition rather than a repurpose: these bytes
        never meant anything for this style, so nothing written before can be
        misread now.

        Zero means full, deliberately. Rainbows written before this carried
        whatever was in the colour field, very often #000000, and a rainbow
        rendering black is indistinguishable from the light being off - which
        nobody configures a rainbow to do. So the one value we cannot honour is
        the one meaning "unset", and treating it as full is what makes an
        un-updated config render after a reflash exactly as it always did.
        """
        level = max(effect.color) / 255.0
        if level <= 0:
            level = 1.0
        start = now_s()
        while True:
            hue = ((now_s() - start) % effect.period_s) / effect.period_s
            self._backend.set(*_hsv_to_rgb(hue, 1.0, level))
            await asyncio.sleep(_FRAME_S)
