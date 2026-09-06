from datetime import datetime, time

from aibutton.config import (
    ActionsBehavior,
    AlwaysActivation,
    AppConfig,
    CounterBehavior,
    EnterModeAction,
    LogAction,
    ManualActivation,
    Mode,
    NoticeBehavior,
    ScheduleActivation,
    StopwatchBehavior,
    TimerToggleAction,
    WindowActivation,
)
from aibutton.rules import _in_window, resolve


def ambient(name, actions, activation=None, unless_logged_today=None):
    return Mode(
        name=name,
        activation=activation or AlwaysActivation(),
        behavior=ActionsBehavior(actions=actions, unless_logged_today=unless_logged_today),
    )


MEDS = ambient(
    "Morning meds",
    {"double_tap": LogAction(event="meds_taken")},
    WindowActivation(between=(time(5, 0), time(7, 0))),
)
NIGHT = ambient(
    "Night",
    {"short_press": LogAction(event="awake")},
    WindowActivation(between=(time(22, 0), time(6, 0))),  # crosses midnight
)
WEEKDAYS = ambient(
    "Weekdays",
    {"short_press": LogAction(event="work")},
    WindowActivation(days=frozenset({0, 1, 2, 3, 4})),  # Mon-Fri
)
DEFAULT = ambient(
    "Default",
    {
        "short_press": TimerToggleAction(log_as="focus"),
        "double_tap": LogAction(event="note"),
    },
)


def at(hour, minute=0, day=15):  # 2026-06-15 is a Monday
    return datetime(2026, 6, day, hour, minute)


def test_window_match_picks_scoped_mode():
    mode, action = resolve((MEDS, DEFAULT), "double_tap", at(6))
    assert mode.name == "Morning meds"
    assert action == LogAction(event="meds_taken")


def test_outside_window_falls_to_default():
    mode, action = resolve((MEDS, DEFAULT), "double_tap", at(8))
    assert mode.name == "Default"


def test_window_boundaries_inclusive_start_exclusive_end():
    assert resolve((MEDS, DEFAULT), "double_tap", at(5, 0))[0].name == "Morning meds"
    assert resolve((MEDS, DEFAULT), "double_tap", at(7, 0))[0].name == "Default"


def test_matching_mode_without_trigger_falls_through():
    # Inside the meds window, a short press isn't defined there -> Default.
    mode, action = resolve((MEDS, DEFAULT), "short_press", at(6))
    assert mode.name == "Default"
    assert action == TimerToggleAction(log_as="focus")


def test_overnight_window():
    assert _in_window(time(23, 30), time(22, 0), time(6, 0))
    assert _in_window(time(2, 0), time(22, 0), time(6, 0))
    assert not _in_window(time(12, 0), time(22, 0), time(6, 0))
    assert resolve((NIGHT, DEFAULT), "short_press", at(23))[0].name == "Night"
    assert resolve((NIGHT, DEFAULT), "short_press", at(12))[0].name == "Default"


def test_day_filter():
    assert resolve((WEEKDAYS, DEFAULT), "short_press", at(10, day=15))[0].name == "Weekdays"  # Monday
    assert resolve((WEEKDAYS, DEFAULT), "short_press", at(10, day=20))[0].name == "Default"  # Saturday


def test_first_match_wins_order():
    shadow = ambient("Shadow", {"double_tap": LogAction(event="shadow")})
    mode, _ = resolve((shadow, MEDS, DEFAULT), "double_tap", at(6))
    assert mode.name == "Shadow"


def test_no_match_returns_none():
    only_meds = (MEDS,)
    assert resolve(only_meds, "double_tap", at(12)) is None
    assert resolve(only_meds, "triple_tap", at(6)) is None


def test_alarm_modes_are_not_gesture_resolved():
    # Takeover alarm modes never answer gestures - they fire via the
    # scheduler. An alarm mode in the list is skipped during resolution.
    alarm = Mode(
        name="Wake up",
        activation=ScheduleActivation(at=time(7, 0)),
        behavior=NoticeBehavior(message="Wake up"),
    )
    assert resolve((alarm,), "short_press", at(7)) is None
    # ...and it doesn't shadow an ambient mode that does define the gesture.
    mode, _ = resolve((alarm, DEFAULT), "short_press", at(7))
    assert mode.name == "Default"


REMINDER = ambient(
    "Meds reminder",
    {"short_press": LogAction(event="meds_taken")},
    WindowActivation(between=(time(7, 30), time(7, 31))),
    unless_logged_today="meds_taken",
)


def test_unless_logged_today_skips_when_already_logged():
    mode, _ = resolve((REMINDER, DEFAULT), "short_press", at(7, 30), logged_today=lambda name: True)
    assert mode.name == "Default"


def test_unless_logged_today_matches_when_not_logged():
    mode, action = resolve((REMINDER, DEFAULT), "short_press", at(7, 30), logged_today=lambda name: False)
    assert mode.name == "Meds reminder"
    assert action == LogAction(event="meds_taken")


def test_unless_logged_today_checks_the_named_event():
    seen = []

    def logged_today(name):
        seen.append(name)
        return False

    resolve((REMINDER, DEFAULT), "short_press", at(7, 30), logged_today=logged_today)
    assert seen == ["meds_taken"]


def test_unless_logged_today_without_callback_does_not_skip():
    # No store wired up (e.g. pure unit test) -> behaves as if nothing's logged.
    mode, _ = resolve((REMINDER, DEFAULT), "short_press", at(7, 30))
    assert mode.name == "Meds reminder"


# --- enter_mode + takeover modes ----------------------------------------

def test_enter_mode_action_resolves_from_ambient_mode():
    # An ambient actions mode whose gesture is an enter_mode action resolves
    # normally and returns that EnterModeAction (main.py then dispatches it).
    starter = ambient("Default", {"tap_4": EnterModeAction(target="Focus")})
    mode, action = resolve((starter,), "tap_4", at(12))
    assert mode.name == "Default"
    assert action == EnterModeAction(target="Focus")


def test_default_modes_resolve_their_enter_mode_bindings():
    # Exercises the actual shipped defaults (config._default_modes via
    # AppConfig()) rather than a hand-built fixture: Home's double_tap should
    # resolve to the enter_mode action that reaches the Launcher it ships
    # alongside (TODO 5). Home is ambient, so resolve() finds it directly -
    # the Launcher/Pomodoro/Stopwatch modes those actions target are manual
    # takeovers, reached only by dispatching the returned action (main.py's
    # job, not rules.py's).
    modes = AppConfig().modes
    mode, action = resolve(modes, "double_tap", at(12))
    assert mode.name == "Home"
    assert action == EnterModeAction(target="Launcher")

    # And nothing answers a long press: at a menu it is sleep, handled by the
    # run loop before resolution (TODO 104).
    assert resolve(modes, "long_press", at(12)) is None


def test_stopwatch_and_counter_modes_are_never_resolved():
    # Takeover stopwatch/counter modes (manual activation) are reached only via
    # an enter_mode action, never by a gesture resolving directly to them.
    focus = Mode(name="Focus", activation=ManualActivation(),
                 behavior=StopwatchBehavior(log_as="focus"))
    water = Mode(name="Water", activation=ManualActivation(),
                 behavior=CounterBehavior(event="water"))
    assert resolve((focus, water), "short_press", at(12)) is None
    assert resolve((focus, water), "tap_4", at(12)) is None
    assert resolve((focus, water), "double_tap", at(12)) is None
    # ...and they don't shadow an ambient mode that does define the gesture.
    mode, _ = resolve((focus, water, DEFAULT), "short_press", at(12))
    assert mode.name == "Default"
