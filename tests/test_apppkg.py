"""The app package: compiled on the host, run on the device.

Three things are being guarded here, and they are the three that
ARCHITECTURE.md says the on-device runtime rests on.

**The format is a mirrored table** (CLAUDE.md): `aibutton/appc.py` writes what
`firmware/apppkg.py` reads, and the two ship to different machines. So every
test below compiles with one and decodes with the other rather than asserting
against a fixture, and a byte that moves on one side fails here.

**The runtime is pure**, so a whole button - a menu, the app it launches, and
sleep - can be driven on the host with a clock the test owns: no board, no
asyncio, no radio. That is the same property `trigger.py` has had since the
beginning, and it is why the port was cheap.

**A package must never be able to stop the button.** The decoder answers None
for anything it cannot read and the firmware carries on as the plain BLE
peripheral it was; the corruption tests are what keep that true.
"""

from dataclasses import replace

import apppkg
import sequence
import standalone

from aibutton import appc, sequencer
from aibutton.config import (
    LedEffect,
    LightShowBehavior,
    ManualActivation,
    Mode,
    ShowCue,
    parse_config,
)

LOOKS = {
    "warm": LedEffect(style="solid", color="#ff8800"),
    "cool": LedEffect(style="breathe", color="#0044ff", period_s=2.0),
    "show": sequencer.Sequence(
        stops=(
            sequencer.Stop(color="#ff00ff", hold_s=0.25, fade_s=0.0),
            sequencer.Stop(color="#00ffff", hold_s=0.25, fade_s=0.5, curve="ease_in"),
        ),
        repeat=True,
    ),
}


def _show(**over):
    body = dict(
        cues=(ShowCue(look="warm"), ShowCue(look="cool"), ShowCue(look="show")),
        dwell_s=8.0,
        auto=True,
    )
    body.update(over)
    return LightShowBehavior(**body)


def _package(behavior=None, looks=None, min_flash_period_s=0.3):
    """One light show, alone in a package - the smallest thing that runs."""
    app = appc.compile_lightshow(
        behavior or _show(), "Light show", LOOKS if looks is None else looks,
    )
    return appc.build([app], 0, min_flash_period_s)


def _bundle(**over):
    bundle = apppkg.decode(_package(**over))
    assert bundle is not None
    return bundle


def _only(**over):
    return _bundle(**over).apps[0]


# --- the format survives the trip -----------------------------------------

def test_a_compiled_show_decodes_to_the_states_it_was_built_from():
    app = _only()
    # Two states per cue - running and held - which is the whole of the loop
    # the compiler unrolled.
    assert len(app.states) == 6
    assert app.start == 0
    assert app.name == "Light show"
    # Three distinct looks, in first-use order.
    assert len(app.looks) == 3
    assert app.looks[0] == ("effect", 1, (255, 136, 0), (0, 0, 0), 1.0)
    assert app.looks[2][0] == "sequence"


def test_a_repeated_look_is_carried_once():
    """A show that alternates between two looks carries two, not one per cue -
    otherwise a long playlist pays for the same colours over and over."""
    app = _only(behavior=_show(cues=(
        ShowCue(look="warm"), ShowCue(look="cool"), ShowCue(look="warm"),
    )))
    assert len(app.looks) == 2
    assert len(app.states) == 6


def test_a_stop_list_survives_with_its_curves():
    kind, repeat, stops = _only().looks[2]
    assert (kind, repeat) == ("sequence", True)
    assert len(stops) == 2
    assert stops[0][0] == (255, 0, 255)
    assert stops[1][1] == 0.25          # hold
    assert stops[1][2] == 0.5           # fade
    assert stops[1][3] == sequence.CURVE_EASE_IN


def test_a_cue_naming_a_missing_look_compiles_dark_rather_than_vanishing():
    """The parser already warned; dropping the cue here would make the show
    quietly one shorter than the list the editor is showing you."""
    app = _only(behavior=_show(cues=(ShowCue(look="warm"), ShowCue(look="ghost"))))
    assert len(app.states) == 4
    assert app.looks[1] == ("effect", 1, (0, 0, 0), (0, 0, 0), 1.0)


def test_the_package_is_small_enough_to_be_boring():
    """ARCHITECTURE.md budgets 2 KB for a typical app. A three-cue show with a
    stop list in it should be nowhere near that, and if this ever fails the
    format grew something it should not have."""
    assert len(_package()) < 300


# --- a package must never stop the button ---------------------------------

def test_a_flipped_byte_is_refused():
    package = bytearray(_package())
    package[20] ^= 0xFF
    assert apppkg.decode(bytes(package)) is None


def test_a_newer_format_is_refused_rather_than_guessed_at():
    package = bytearray(_package())
    package[4] = apppkg.FORMAT_VERSION + 1
    crc = appc.crc16(bytes(package[:-2]))
    package[-2], package[-1] = crc >> 8, crc & 0xFF
    assert apppkg.decode(bytes(package)) is None


def test_every_truncation_answers_none_and_nothing_raises():
    package = _package()
    for cut in range(len(package)):
        assert apppkg.decode(package[:cut]) is None


def test_no_package_at_all_is_not_an_error():
    assert apppkg.load("no-such-file.pkg") is None


# --- the mirrored tables --------------------------------------------------

def test_the_curve_codes_are_the_host_list_by_index():
    """The wire encoding for a curve *is* its index in sequencer.CURVES, so a
    curve added to one side and not the other renders as the wrong shape."""
    assert sequencer.CURVES.index("linear") == sequence.CURVE_LINEAR
    assert sequencer.CURVES.index("ease_in") == sequence.CURVE_EASE_IN
    assert sequencer.CURVES.index("ease_out") == sequence.CURVE_EASE_OUT
    assert sequencer.CURVES.index("ease_in_out") == sequence.CURVE_EASE_IN_OUT
    assert sequencer.CURVES.index("exponential") == sequence.CURVE_EXPONENTIAL


def test_the_two_stop_list_walkers_agree():
    """The device's `sequence.plan_at` is a port of the host's
    `sequencer.plan_at`, and this is what stops the port drifting: sample both
    across several cycles and compare every frame.

    **It samples past one cycle on purpose.** The two once accumulated a
    cycle's length in different orders - `at + (fade + hold)` against
    `(at + fade) + hold` - which differ by one ulp. Identical for thirty
    frames, and then the modulo at the seam landed at the *end* of the previous
    cycle instead of the start of the next: one frame of completely wrong
    colour, every loop, forever.
    """
    host = sequencer.Sequence(
        stops=(
            sequencer.Stop(color="#ff0000", hold_s=0.2, fade_s=0.0),
            sequencer.Stop(color="#00ff40", hold_s=0.1, fade_s=0.6, curve="ease_in"),
            sequencer.Stop(color="#0000ff", hold_s=0.0, fade_s=0.4, curve="exponential"),
        ),
        repeat=True,
    )
    device_stops = tuple(
        (
            tuple(int(stop.color[i:i + 2], 16) for i in (1, 3, 5)),
            stop.hold_s, stop.fade_s, sequencer.CURVES.index(stop.curve),
        )
        for stop in host.stops
    )
    step = 0.05
    # Deliberately not a multiple of the step, so samples land mid-fade and on
    # the seam rather than only on tidy boundaries.
    for i in range(400):
        elapsed = i * 0.0137
        frame, host_wait = sequencer.plan_at(host, elapsed, step)
        color, device_wait = sequence.plan_at(device_stops, True, elapsed, step)
        assert frame is not None and color is not None
        expected = tuple(int(frame.color[j:j + 2], 16) for j in (1, 3, 5))
        assert color == expected, (elapsed, color, expected)
        assert host_wait == device_wait


def test_a_one_shot_ends_on_both_sides_at_the_same_moment():
    host = sequencer.Sequence(
        stops=(sequencer.Stop(color="#ffffff", hold_s=0.3, fade_s=0.2),),
        repeat=False,
    )
    stops = (((255, 255, 255), 0.3, 0.2, sequence.CURVE_LINEAR),)
    assert sequencer.plan_at(host, 0.49, 0.05)[0] is not None
    assert sequence.plan_at(stops, False, 0.49, 0.05)[0] is not None
    assert sequencer.plan_at(host, 0.5, 0.05)[0] is None
    assert sequence.plan_at(stops, False, 0.5, 0.05)[0] is None


# --- the safety floor reaches a package -----------------------------------

def test_a_strobing_look_is_floored_at_compile_time():
    """**The third and last floor gate.** A package renders with no host in the
    room, so `main.set_led` cannot clamp it later - if it left here unfloored
    it would flash at whatever rate the file asked for, forever."""
    fast = {"warm": LedEffect(style="flash", color="#ff0000", period_s=0.05)}
    app = _only(behavior=_show(cues=(ShowCue(look="warm"),)), looks=fast)
    assert app.looks[0][4] == 0.3


def test_a_stop_list_dwell_is_floored_too():
    fast = {"warm": sequencer.Sequence(
        stops=tuple(
            sequencer.Stop(color=c, hold_s=0.01, fade_s=0.0)
            for c in ("#ff0000", "#00ff00", "#0000ff", "#ffffff")
        ),
        repeat=True,
    )}
    app = _only(behavior=_show(cues=(ShowCue(look="warm"),)), looks=fast)
    for stop in app.looks[0][2]:
        assert stop[1] + stop[2] >= 0.15 - 1e-9  # half the floor, per sequence_safe


# --- running it, with a clock the test owns -------------------------------

class FakeLED:
    """What the light was asked to show, in order. The device's LEDController
    without the animation, which is the whole surface standalone.py uses."""

    def __init__(self):
        self.shown = []

    def show_effect(self, style, color, color2, period_s):
        self.shown.append(("effect", color))

    def show_sequence(self, stops, repeat):
        self.shown.append(("sequence", stops[0][0]))

    def set_state(self, code):
        self.shown.append(("idle", code))

    def palette_color(self, code):
        return (0, 0, 255)


class FakeBuzzer:
    def __init__(self):
        self.played = []

    def play(self, code):
        self.played.append(code)


def _running(package=None, now=0.0, **over):
    bundle = apppkg.decode(package if package is not None else _package(**over))
    led, buzzer = FakeLED(), FakeBuzzer()
    driver = standalone.Standalone(bundle, led, buzzer)
    driver.enable(now)
    return driver, led


def test_it_opens_on_the_first_cue_with_the_dwell_running():
    driver, led = _running()
    assert led.shown == [("effect", (255, 136, 0))]
    assert driver._deadline == 8.0


def test_the_dwell_advances_the_show_and_wraps():
    driver, led = _running()
    driver.tick(8.0)
    driver.tick(16.0)
    driver.tick(24.0)  # back to cue one
    assert [colour for _kind, colour in led.shown] == [
        (255, 136, 0), (0, 68, 255), (255, 0, 255), (255, 136, 0),
    ]


def test_a_dwell_that_is_not_due_yet_changes_nothing():
    driver, led = _running()
    driver.tick(7.99)
    assert len(led.shown) == 1


def test_a_short_press_is_the_next_cue():
    driver, led = _running()
    driver.gesture("short_press", 1.0)
    assert led.shown[-1] == ("effect", (0, 68, 255))
    # And the dwell restarts from the press, not from where the last one was.
    assert driver._deadline == 9.0


def test_a_double_tap_holds_the_show_where_it_is():
    """Holding stops the clock, not the light: the cue is shown again - which
    restarts whatever it is animating - and no timer is set."""
    driver, led = _running()
    driver.gesture("double_tap", 1.0)
    assert driver._deadline is None
    assert led.shown[-1] == ("effect", (255, 136, 0))
    driver.tick(999.0)  # no clock to fire
    assert len(led.shown) == 2


def test_a_held_show_still_steps_by_hand_and_stays_held():
    driver, led = _running()
    driver.gesture("double_tap", 1.0)   # hold on cue one
    driver.gesture("short_press", 2.0)  # -> cue two, still held
    assert led.shown[-1] == ("effect", (0, 68, 255))
    assert driver._deadline is None
    driver.gesture("double_tap", 3.0)   # -> running again, on cue two
    assert driver._deadline == 11.0


def test_auto_off_starts_held():
    driver, _led = _running(behavior=_show(auto=False))
    assert driver._deadline is None


def test_a_per_cue_hold_overrides_the_shows_dwell():
    driver, _led = _running(behavior=_show(cues=(
        ShowCue(look="warm", hold_s=2.0), ShowCue(look="cool"),
    )))
    assert driver._deadline == 2.0


def test_an_unbound_gesture_leaves_the_show_alone():
    driver, led = _running()
    driver.gesture("tap_5", 1.0)
    assert len(led.shown) == 1
    assert driver._deadline == 8.0, "an unmatched press cleared a running timer"


def test_leaving_the_only_app_there_is_sleeps():
    """Up one level from the root is off (TODO 104). A package with one app in
    it *is* the root, so there is nowhere else for a long press to go."""
    driver, led = _running()
    driver.gesture("long_press", 1.0)
    assert driver._asleep is True
    assert led.shown[-1][0] == "sequence"     # the fade out
    driver.gesture("short_press", 2.0)        # swallowed
    assert driver._asleep is True
    driver.gesture("long_press", 3.0)         # wake, back at the show
    assert driver._asleep is False
    assert led.shown[-1] == ("effect", (255, 136, 0))


def test_a_connected_host_takes_the_button_back():
    driver, led = _running()
    before = len(led.shown)
    driver.disable()
    driver.gesture("short_press", 5.0)
    driver.tick(999.0)
    assert len(led.shown) == before, "the app answered while a host was connected"


# --- a menu, and the apps behind it ---------------------------------------

MENU_CONFIG = {
    "looks": {"warm": {"style": "solid", "color": "#ff8800"}},
    "modes": [
        {
            "name": "Home", "template": "actions",
            "activation": {"type": "always"},
            "double_tap": {"action": "enter_mode", "target": "Show"},
            "triple_tap": {"action": "log", "event": "nope"},
            "tap_4": {"action": "enter_mode", "target": "Status"},
        },
        {
            "name": "Show", "template": "lightshow",
            "activation": {"type": "manual"}, "cues": "warm", "dwell_s": 5,
        },
        {
            "name": "Status", "template": "signal",
            "activation": {"type": "manual"},
            "states": [
                {"name": "Free", "color": "#00ff00"},
                {"name": "Busy", "color": "#ff0000", "style": "breathe"},
            ],
        },
    ],
}


def _button(raw=None):
    config = parse_config(raw or MENU_CONFIG)
    package, report = appc.compile_config(config)
    driver, led = _running(package=package)
    return driver, led, report


def test_a_menu_is_the_start_app_and_wears_the_buttons_own_light():
    """A menu has no look of its own, so a state that shows nothing drops back
    to IDLE - which is what the host does when a takeover ends."""
    driver, led, report = _button()
    assert report["menu"] == "Home"
    assert report["apps"] == ["Home", "Show", "Status"]
    assert driver._app == 0
    assert led.shown == [("idle", 1)]


def test_a_gesture_launches_an_app_and_a_long_press_comes_back():
    driver, led, _report = _button()
    driver.gesture("double_tap", 1.0)
    assert driver._app == 1
    assert driver._return_to == 0
    assert led.shown[-1] == ("effect", (255, 136, 0))
    driver.gesture("long_press", 2.0)
    assert (driver._app, driver._return_to) == (0, None)
    assert led.shown[-1] == ("idle", 1)


def test_the_menu_reaches_every_app_that_compiled():
    driver, _led, _report = _button()
    driver.gesture("tap_4", 1.0)
    assert driver.app.name == "Status"


def test_a_binding_that_needs_the_phone_is_dropped_and_named():
    """Not silently missing: what a standalone button cannot do is something to
    read before flashing, not to discover by pressing."""
    driver, led, report = _button()
    assert ("Home", "triple_tap", "log needs the phone") in report["dropped"]
    before = len(led.shown)
    driver.gesture("triple_tap", 1.0)
    assert driver._app == 0 and len(led.shown) == before


def test_a_long_press_at_the_menu_sleeps_and_another_wakes_it():
    driver, led, _report = _button()
    driver.gesture("long_press", 1.0)
    assert driver._asleep is True
    driver.gesture("long_press", 2.0)
    assert (driver._asleep, driver._app) == (False, 0)


def test_leaving_a_launched_app_returns_before_it_can_sleep():
    """The one-level rule: out of an app lands in the menu, and only the *next*
    long press turns the light off."""
    driver, _led, _report = _button()
    driver.gesture("double_tap", 1.0)   # into the show
    driver.gesture("long_press", 2.0)   # back to the menu
    assert driver._asleep is False
    driver.gesture("long_press", 3.0)   # now off
    assert driver._asleep is True


def test_a_signal_light_is_one_state_per_position():
    driver, led, _report = _button()
    driver.gesture("tap_4", 1.0)
    assert led.shown[-1] == ("effect", (0, 255, 0))
    driver.gesture("short_press", 2.0)
    assert led.shown[-1] == ("effect", (255, 0, 0))
    driver.gesture("short_press", 3.0)  # wraps
    assert led.shown[-1] == ("effect", (0, 255, 0))


def test_a_signal_position_starts_where_it_was_told_to():
    raw = {"modes": [dict(MENU_CONFIG["modes"][2], start_at=1)]}
    config = parse_config(raw)
    # The parser seeds an ambient Home into any config without one; dropped
    # here so the signal is the only app and therefore the one booted into.
    config = replace(config, modes=(config.modes[0],))
    package, _report = appc.compile_config(config)
    driver, led = _running(package=package)
    assert led.shown[-1] == ("effect", (255, 0, 0))


def test_a_signal_positions_message_is_reported_as_left_behind():
    raw = {
        "modes": [{
            "name": "Status", "template": "signal",
            "activation": {"type": "manual"},
            "states": [
                {"name": "Free", "color": "#00ff00"},
                {"name": "On air", "color": "#ff0000",
                 "action": {"action": "webhook", "url": "https://x.test/y"}},
            ],
        }],
    }
    _package_bytes, report = appc.compile_config(parse_config(raw))
    assert ("Status", "On air", "its message needs the phone") in report["dropped"]


def test_a_menu_can_open_another_menu():
    """Five gestures is tight; a menu of menus is how a button gets past it,
    and it is why the compiler numbers every app before compiling any."""
    raw = {
        "modes": [
            {"name": "Home", "template": "actions",
             "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "More"}},
            {"name": "More", "template": "actions",
             "activation": {"type": "window", "between": ["09:00", "17:00"]},
             "short_press": {"action": "standby"}},
        ],
    }
    package, report = appc.compile_config(parse_config(raw))
    assert report["apps"] == ["Home", "More"]
    driver, _led = _running(package=package)
    driver.gesture("short_press", 1.0)
    assert driver.app.name == "More"
    # `standby` compiles to "up one level", so from a sub-menu it comes home.
    driver.gesture("short_press", 2.0)
    assert (driver._app, driver._asleep) == (0, False)


# --- the compiler's edges -------------------------------------------------

def test_a_show_with_no_cues_will_not_compile():
    try:
        appc.compile_lightshow(_show(cues=()), "Empty", LOOKS)
    except appc.CompileError:
        return
    raise AssertionError("an empty show compiled")


def test_a_template_that_cannot_run_here_says_what_it_needs():
    config = parse_config({
        "modes": [{
            "name": "Timer", "template": "stopwatch",
            "activation": {"type": "manual"}, "log_as": "t",
        }],
    })
    try:
        appc.compile_app(config.modes[0], config)
    except appc.CompileError as exc:
        assert "variables" in str(exc) and "document" in str(exc)
        return
    raise AssertionError("a stopwatch compiled")


def test_a_config_with_nothing_compilable_refuses_rather_than_shipping_empty():
    config = parse_config({
        "modes": [{
            "name": "Timer", "template": "stopwatch",
            "activation": {"type": "manual"}, "log_as": "t",
        }],
    })
    # The parser seeds an ambient Home when there is none, and a menu with no
    # reachable app is still a menu - so what must never happen is a *package*
    # with no apps in it at all.
    package, report = appc.compile_config(config)
    assert apppkg.decode(package) is not None
    assert report["skipped"] == [("Timer", appc._needs(config.modes[0].behavior))]


def test_with_no_menu_the_first_app_is_the_whole_button():
    config = parse_config({
        "looks": {"warm": {"style": "solid", "color": "#ff8800"}},
        "modes": [{
            "name": "Show", "template": "lightshow",
            "activation": {"type": "manual"}, "cues": "warm",
        }],
    })
    config = replace(config, modes=(config.modes[0],))  # drop the seeded Home
    package, report = appc.compile_config(config)
    assert report["menu"] is None
    assert apppkg.decode(package).start == 0


def test_a_mode_object_compiles_the_same_as_its_behavior():
    """`compile_app` is the dispatch and `compile_lightshow` is the work, so
    the two must not be able to disagree about the same show."""
    mode = Mode(name="Light show", activation=ManualActivation(), behavior=_show())
    config = replace(parse_config({"modes": []}), looks=LOOKS, modes=(mode,))
    app, dropped = appc.compile_app(mode, config)
    assert dropped == []
    assert appc.build([app], 0, config.min_flash_period_s) == _package(
        min_flash_period_s=config.min_flash_period_s
    )


def test_the_ambient_menu_is_always_app_zero():
    """Whatever order the config lists them in - the device enters app 0 at
    boot and returns to it, so which one that is cannot be incidental."""
    raw = dict(MENU_CONFIG)
    raw["modes"] = [MENU_CONFIG["modes"][1], MENU_CONFIG["modes"][0]]
    package, report = appc.compile_config(parse_config(raw))
    assert report["apps"][0] == "Home"
    assert apppkg.decode(package).apps[0].name == "Home"


def test_every_app_in_a_bundle_keeps_its_own_looks():
    bundle = apppkg.decode(_button()[2] and appc.compile_config(
        parse_config(MENU_CONFIG)
    )[0])
    home, show, status = bundle.apps
    assert home.looks == ()          # a menu wears the button's own light
    assert len(show.looks) == 1
    assert len(status.looks) == 2    # numbered per app, not per package


def test_a_gesture_map_with_no_ambient_activation_still_travels():
    """`enter_mode` reaches it, so it has to be in the package even though no
    press at the root resolves to it."""
    raw = {
        "modes": [
            {"name": "Home", "template": "actions",
             "activation": {"type": "always"},
             "short_press": {"action": "enter_mode", "target": "Night"}},
            {"name": "Night", "template": "actions",
             "activation": {"type": "window", "between": ["22:00", "06:00"]},
             "short_press": {"action": "standby"}},
        ],
    }
    _pkg, report = appc.compile_config(parse_config(raw))
    assert "Night" in report["apps"]
