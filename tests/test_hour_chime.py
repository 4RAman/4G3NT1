"""The hour chime (TODO 106), which is three shipped things and one new one.

The three: a Notice (84), a number rendered as a stop list (91's
`readout.py`), and the sequence walker every other look already uses. The new
one is a *recurring* schedule - `every: 'hour'` plus the `between` window that
is the difference between this being usable and being switched off after one
night at 3 AM.

So the tests are grouped by which of those a failure would be about, and the
very first of them pins the thing most likely to be broken by accident: a
schedule that sets neither new field must behave exactly as it did before they
existed. Everything here is a table over pure functions with the clock passed
in - no async, no device, no sleeping, and nothing to mock.
"""

import re
from datetime import datetime, time
from pathlib import Path

import pytest

from aibutton import config as cfg
from aibutton import readout, scheduler, sequencer
from aibutton.config import Mode, NoticeBehavior, ScheduleActivation
from aibutton.device import SAFE_MIN_PERIOD_S
from aibutton.scheduler import current_occurrence, due_alarm

# Half the WCAG floor, which is what a stop's *dwell* is measured against - a
# dwell is on-time, not a period, and two dwells make one period. Restated from
# `readout._FLOOR_S` rather than imported so a change to that private constant
# has to be made deliberately here too.
DWELL_FLOOR_S = SAFE_MIN_PERIOD_S / 2

MONDAY = 15  # 2026-06-15


def when(hour, minute=0, second=0, day=MONDAY):
    return datetime(2026, 6, day, hour, minute, second)


def notice(name, activation, **fields):
    return Mode(name=name, activation=activation, behavior=NoticeBehavior(**fields))


# --- the promise that nothing moved ----------------------------------------
#
# A ScheduleActivation with no `every` and no `between` is every schedule that
# existed before TODO 106, and there is no upgrade step - the fields simply
# default to off. These pin that from both ends: the occurrence it computes,
# and the JSON it writes back.

PLAIN = ScheduleActivation(at=time(7, 0))


@pytest.mark.parametrize("scenario,now,expected", [
    ("fires on the minute", when(7, 0), True),
    ("fires late in the 60s window", when(7, 0, 59), True),
    ("not due a second early", when(6, 59, 59), False),
    ("not due once the window has passed", when(7, 1, 0), False),
    ("not due at the same minute of another hour", when(8, 0), False),
])
def test_a_schedule_with_neither_new_field_behaves_as_before(scenario, now, expected):
    fired = due_alarm((notice("Wake", PLAIN),), now, set()) is not None
    assert fired is expected, scenario


def test_a_plain_schedule_still_computes_todays_occurrence_at_at():
    # The old body, restated: `now` with `at`'s hour and minute on it.
    assert current_occurrence(PLAIN, when(13, 42, 9)) == when(7, 0, 0)


def test_a_plain_schedule_round_trips_without_the_new_keys():
    # Written only when set, so an untouched config file does not grow two
    # keys the day it is next saved.
    written = cfg._activation_to_dict(PLAIN)
    assert written == {"type": "schedule", "at": "07:00"}


def test_a_chime_schedule_round_trips_through_both_new_keys():
    activation = ScheduleActivation(
        at=time(0, 0), every="hour", between=(time(8, 0), time(22, 0)),
    )
    written = cfg._activation_to_dict(activation)
    assert written == {
        "type": "schedule", "at": "00:00", "every": "hour",
        "between": ["08:00", "22:00"],
    }
    assert cfg._parse_activation(written, "modes[0]") == activation


# --- the recurring schedule, and its window --------------------------------

HOURLY = ScheduleActivation(
    at=time(0, 0), every="hour", between=(time(8, 0), time(22, 0)),
)


@pytest.mark.parametrize("scenario,now,expected", [
    ("the first hour in the window fires", when(8, 0, 0), True),
    ("a middle hour fires", when(12, 0, 30), True),
    ("the last hour inside the window fires", when(21, 0, 0), True),
    ("an hour before the window is silent", when(7, 0, 0), False),
    ("the hour the window ends on is silent", when(22, 0, 0), False),
    ("3 AM - the whole reason the window exists", when(3, 0, 0), False),
    ("still only the first 60s of each hour", when(12, 1, 0), False),
])
def test_an_hourly_chime_fires_only_inside_its_window(scenario, now, expected):
    fired = due_alarm((notice("Chime", HOURLY),), now, set()) is not None
    assert fired is expected, scenario


def test_the_window_is_half_open_at_both_ends():
    # [start, end): 08:00 is in, 22:00 is not - the same half-open span
    # `rules._in_window` uses for an ambient window, and said out loud here
    # because the two are a mirrored predicate.
    assert current_occurrence(HOURLY, when(8, 0)) is not None
    assert current_occurrence(HOURLY, when(22, 0)) is None


def test_only_the_minute_of_at_is_used_when_it_repeats():
    # An hourly schedule happens on every hour; `between` says which. So
    # "08:30 every hour" is :30 past *every* hour in range, not a start time -
    # config.py logs a warning about exactly this, and this is what it warns
    # about.
    half_past = ScheduleActivation(at=time(8, 30), every="hour")
    assert current_occurrence(half_past, when(3, 30, 5)) == when(3, 30, 0)
    assert current_occurrence(half_past, when(19, 30, 5)) == when(19, 30, 0)


# **A midnight-crossing window keeps going across the date boundary, and each
# side of midnight is its own day's occurrence.** That is the behaviour chosen
# here rather than "a window is one calendar day": a night light that stopped
# at midnight and restarted would be a different feature from one that runs
# 22:00-06:00, and the key already carries the date, so the two sides cannot
# suppress one another.
NIGHT = ScheduleActivation(
    at=time(0, 0), every="hour", between=(time(22, 0), time(6, 0)),
)


@pytest.mark.parametrize("scenario,now,expected", [
    ("the evening side is inside", when(22, 0), True),
    ("just before midnight is inside", when(23, 0), True),
    ("midnight itself is inside", when(0, 0), True),
    ("the small hours are inside", when(5, 0), True),
    ("the hour it ends on is outside", when(6, 0), False),
    ("the middle of the day is outside", when(12, 0), False),
    ("the hour before it starts is outside", when(21, 0), False),
])
def test_a_window_that_crosses_midnight_wraps(scenario, now, expected):
    fired = due_alarm((notice("Night", NIGHT),), now, set()) is not None
    assert fired is expected, scenario


def test_each_side_of_midnight_is_a_different_occurrence():
    late = due_alarm((notice("Night", NIGHT),), when(23, 0), set())
    early = due_alarm((notice("Night", NIGHT),), when(0, 0, day=MONDAY + 1), set())
    assert late is not None and early is not None
    assert late[1] != early[1]
    # And firing the late one does not suppress the early one an hour later.
    assert due_alarm(
        (notice("Night", NIGHT),), when(0, 0, day=MONDAY + 1), {late[1]},
    ) is not None


def test_every_hour_gets_its_own_key_so_the_day_is_not_one_fire():
    # The bug this is here to catch: keying an occurrence off the activation's
    # `at` rather than the occurrence's own time gives all twenty-four hours
    # one key, and the day's first chime silences the rest.
    keys = set()
    for hour in range(8, 22):
        result = due_alarm((notice("Chime", HOURLY),), when(hour, 0), set())
        assert result is not None, hour
        keys.add(result[1])
    assert len(keys) == 14


def test_a_fired_hour_does_not_fire_twice():
    chime = notice("Chime", HOURLY)
    _, key = due_alarm((chime,), when(12, 0, 0), set())
    assert due_alarm((chime,), when(12, 0, 30), {key}) is None


def test_days_still_apply_to_every_hour_of_a_recurring_schedule():
    weekdays = ScheduleActivation(
        at=time(0, 0), every="hour", days=frozenset({0, 1, 2, 3, 4}),
    )
    assert due_alarm((notice("C", weekdays),), when(12, 0, day=15), set()) is not None
    assert due_alarm((notice("C", weekdays),), when(12, 0, day=20), set()) is None


# --- the parser: every key falls back on its own, nothing raises -----------

@pytest.mark.parametrize("scenario,raw,expected", [
    ("an unknown repeat falls back to once a day", {"every": "fortnight"},
     ScheduleActivation(at=time(7, 0))),
    ("an empty repeat is no repeat", {"every": ""},
     ScheduleActivation(at=time(7, 0))),
    ("a good repeat is kept", {"every": "hour"},
     ScheduleActivation(at=time(7, 0), every="hour")),
    ("a good window is kept", {"between": ["08:00", "22:00"]},
     ScheduleActivation(at=time(7, 0), between=(time(8, 0), time(22, 0)))),
])
def test_the_schedule_parser_falls_back_per_key(scenario, raw, expected):
    got = cfg._parse_activation({"type": "schedule", "at": "07:00", **raw}, "modes[0]")
    assert got == expected, scenario


@pytest.mark.parametrize("scenario,raw", [
    # A malformed window is the one that skips the mode rather than falling
    # back, and deliberately: falling back to "no window" is what puts bells at
    # 3 AM, which is `_parse_activation`'s own "running a scoped mode at the
    # wrong time is worse than not running it".
    ("a one-element window", {"between": ["08:00"]}),
    ("a window that is not a list", {"between": "08:00-22:00"}),
    ("an unparseable time in the window", {"between": ["08:00", "tea time"]}),
    ("a window with no width", {"between": ["09:00", "09:00"]}),
])
def test_a_malformed_window_skips_the_mode_rather_than_dropping_the_window(
    scenario, raw,
):
    got = cfg._parse_activation({"type": "schedule", "at": "07:00", **raw}, "modes[0]")
    assert got is None, scenario


@pytest.mark.parametrize("scenario,raw,expected", [
    ("no key at all is no chime", {}, None),
    ("an empty string is no chime", {"readout_scheme": ""}, None),
    ("an unknown scheme falls back to the ordinary ring",
     {"readout_scheme": "semaphore"}, None),
    ("each shipped scheme is accepted", {"readout_scheme": "hour_colors"},
     "hour_colors"),
])
def test_the_notice_parser_falls_back_on_an_unusable_scheme(scenario, raw, expected):
    body = cfg._parse_notice_body(
        {"log_as": "chime", **raw}, "modes[0]", "notice", "Chime",
    )
    assert body.readout_scheme == expected, scenario


def test_a_bad_fade_length_falls_back_without_losing_the_chime():
    body = cfg._parse_notice_body(
        {"log_as": "c", "readout_scheme": "binary", "readout_fade_s": "slowly"},
        "modes[0]", "notice", "Chime",
    )
    assert body.readout_scheme == "binary"
    assert body.readout_fade_s == cfg.DEFAULT_READOUT_FADE_S


def test_a_notice_written_before_the_chime_existed_is_unchanged():
    before = cfg._parse_notice_body({"log_as": "wake"}, "modes[0]", "notice", "Wake")
    assert before == NoticeBehavior(log_as="wake")


# --- the hour, rendered by 91's compiler -----------------------------------
#
# **The stop counts are the honest cost of each scheme, and that is why they
# are pinned rather than merely computed.** The editor's hint text quotes the
# durations these produce; a scheme that quietly got slower would make that
# text a lie, which is a worse failure than a wrong colour.

# (scheme, stops at hour 12, readout seconds at hour 12)
NOON = [
    ("morse", 19, 7.00),
    ("place_value", 5, 1.72),
    ("binary", 7, 1.80),
    ("hour_colors", 23, 6.02),
]


def test_the_pinned_schemes_are_exactly_the_shipped_ones():
    # A fifth scheme has to appear in the table above with its measured cost,
    # not merely in SCHEMES - see the note over NOON.
    assert tuple(name for name, _, _ in NOON) == readout.SCHEMES


@pytest.mark.parametrize("scheme,stops,seconds", NOON)
def test_each_scheme_renders_noon_at_its_documented_cost(scheme, stops, seconds):
    rendered = readout.render(12, scheme)
    assert len(rendered) == stops
    total = sum(stop.hold_s + stop.fade_s for stop in rendered)
    assert total == pytest.approx(seconds, abs=0.01)


@pytest.mark.parametrize("scheme,_stops,_seconds", NOON)
def test_every_scheme_clears_the_dwell_floor_by_construction(scheme, _stops, _seconds):
    # Not by leaning on `config.sequence_safe`, which runs later and centrally:
    # `readout.py` promises its output is already legal, and the fourth scheme
    # keeps that promise like the three before it.
    for hour in range(0, 13):
        for stop in readout.render(hour, scheme):
            assert stop.hold_s + stop.fade_s >= DWELL_FLOOR_S - 1e-9, (scheme, hour)


@pytest.mark.parametrize("scenario,value,index", [
    ("one o'clock is one pulse of the first colour", 1, 0),
    ("three o'clock is three pulses", 3, 2),
    ("noon is twelve pulses of the last colour", 12, 11),
])
def test_hour_colors_counts_the_value_and_colours_it_by_the_value(
    scenario, value, index,
):
    assert scenario  # named for the report, asserted on below
    stops = readout.hour_colors(value)
    lit = [s for s in stops if s.color != "#000000"]
    assert len(lit) == value
    assert {s.color for s in lit} == {readout.DEFAULT_HOUR_COLORS[index]}


def test_hour_colors_reads_zero_as_a_counted_zero_not_as_nothing():
    # `(0 - 1) % 12` is 11, so an unguarded wheel would have made midnight look
    # exactly like noon. It is the dim neutral blink `place_value` uses instead.
    stops = readout.hour_colors(0)
    assert len(stops) == 1
    assert stops[0].color not in readout.DEFAULT_HOUR_COLORS


def test_hour_colors_wraps_on_a_shorter_wheel_rather_than_raising():
    # The wheel is a wheel, not a clock - a three-colour wheel is a scheme that
    # says "which third of the count you are in".
    stops = readout.hour_colors(4, colors=("#ff0000", "#00ff00", "#0000ff"))
    lit = [s for s in stops if s.color != "#000000"]
    assert len(lit) == 4
    assert lit[0].color == "#ff0000"  # (4 - 1) % 3 == 0


def test_render_dispatches_the_fourth_scheme_like_the_other_three():
    assert readout.render(7, "hour_colors") == readout.hour_colors(7)
    with pytest.raises(ValueError):
        readout.render(7, "sundial")


# --- the resting-look token ------------------------------------------------

def one_shot(*colors):
    return sequencer.Sequence(
        stops=tuple(sequencer.Stop(c, hold_s=0.5) for c in colors), repeat=False,
    )


def test_the_token_resolves_to_the_resting_look():
    seq = one_shot(sequencer.RESTING, "#ffffff", sequencer.RESTING)
    got = sequencer.resolve_resting(seq, "#112233")
    assert [s.color for s in got.stops] == ["#112233", "#ffffff", "#112233"]


def test_the_token_resolves_to_black_when_nothing_is_resting():
    # The honest answer, and the pre-token behaviour: a one-shot that ends on
    # the token is never worse than one that ends on black, only softer when
    # there is something to land on.
    got = sequencer.resolve_resting(one_shot(sequencer.RESTING), None)
    assert [s.color for s in got.stops] == ["#000000"]


def test_a_sequence_with_no_token_comes_back_untouched():
    # Identity, not equality: this runs on every sequence that reaches the
    # walker, and every look any config can express today has no token in it.
    seq = one_shot("#ff0000", "#00ff00")
    assert sequencer.resolve_resting(seq, "#112233") is seq


def test_an_unresolved_token_degrades_to_black_rather_than_crashing():
    # The sigil keeps it out of the colour space (no hex string starts with
    # "@"), and `device.rgb_bytes` answers black for anything unparseable - so
    # a token that somehow reached the walker renders as exactly the
    # "end on black" behaviour the token replaces. Wrong, visibly, never fatal.
    assert sequencer.RESTING.startswith("@")
    assert sequencer.mix(sequencer.RESTING, "#000000", 0.0) == "#000000"


def test_resolving_preserves_everything_else_about_a_stop():
    seq = sequencer.Sequence(
        stops=(sequencer.Stop(sequencer.RESTING, hold_s=0.25, fade_s=9.0,
                              curve="ease_out"),),
        repeat=False,
    )
    stop = sequencer.resolve_resting(seq, "#010203").stops[0]
    assert (stop.color, stop.hold_s, stop.fade_s, stop.curve) == \
        ("#010203", 0.25, 9.0, "ease_out")


# --- the chime as a whole: 91's compiler wrapped in two fades ---------------

def chime_sequence(hour, scheme, fade_s=10.0, resting="#221100"):
    """`main.hour_chime`'s body, restated over an injected hour and resting
    colour so the shape can be checked with no clock and no device.

    It is a restatement rather than an import because the real one is a closure
    inside `run()` over the device, the store and the wall clock - the same
    reason `test_lightshow.py` and friends rebuild what they check. What must
    not drift is the *ingredients*, and each of those is asserted below against
    the module the real one uses.
    """
    stops = (
        sequencer.Stop(sequencer.RESTING, hold_s=0.0, fade_s=0.0),
        sequencer.Stop(cfg.READOUT_WASH_COLOR, hold_s=0.0, fade_s=fade_s,
                       curve="ease_in"),
        *readout.render(hour, scheme),
        sequencer.Stop(sequencer.RESTING, hold_s=0.0, fade_s=fade_s,
                       curve="ease_out"),
    )
    return sequencer.resolve_resting(
        sequencer.Sequence(stops=stops, repeat=False), resting,
    )


@pytest.mark.parametrize("scheme,_stops,readout_s", NOON)
def test_the_chime_at_noon_costs_the_readout_plus_both_fades(
    scheme, _stops, readout_s,
):
    seq = chime_sequence(12, scheme)
    played = cfg.sequence_safe(seq, SAFE_MIN_PERIOD_S)
    # The leading zero-width stop is floored to one dwell by `sequence_safe` -
    # it exists to give the wash somewhere to fade *from*, and a sixth of a
    # second at the colour already on screen is invisible.
    assert sequencer.span_total(played) == pytest.approx(
        readout_s + 20.0 + DWELL_FLOOR_S, abs=0.02,
    )


def test_the_chime_starts_and_ends_on_the_light_it_interrupted():
    # Both seams, which is the whole of "fade back to whatever it was": a
    # one-shot fades from black by construction, so without the leading token
    # stop the wash would begin by snapping the light off.
    seq = chime_sequence(3, "binary", resting="#221100")
    assert seq.stops[0].color == "#221100"
    assert seq.stops[-1].color == "#221100"
    assert seq.stops[1].color == cfg.READOUT_WASH_COLOR
    assert seq.repeat is False


def test_nothing_in_a_chime_is_left_as_a_token():
    for scheme in readout.SCHEMES:
        for stop in chime_sequence(12, scheme).stops:
            assert stop.color.startswith("#"), scheme


def test_a_chime_survives_the_flash_floor_without_a_second_clamp():
    # It renders as an ordinary stop list through `main.set_led`'s one gate.
    # Nothing here calls `sequence_safe` a second time, and after the one call
    # every dwell is legal.
    played = cfg.sequence_safe(chime_sequence(12, "hour_colors"), SAFE_MIN_PERIOD_S)
    for stop in played.stops:
        assert stop.hold_s + stop.fade_s >= DWELL_FLOOR_S - 1e-9


@pytest.mark.parametrize("scenario,wall_hour,spoken", [
    ("midnight counts as twelve", 0, 12),
    ("one in the morning is one", 1, 1),
    ("noon is twelve", 12, 12),
    ("one in the afternoon is one", 13, 1),
    ("eleven at night is eleven", 23, 11),
])
def test_the_chime_speaks_a_twelve_hour_clock(scenario, wall_hour, spoken):
    # `main.hour_chime`'s fold, restated: `hour % 12 or 12`, applied before any
    # scheme sees the number, so noon is 12 in binary and Morse too rather than
    # the colour scheme carrying a special case at the call site.
    assert (wall_hour % 12 or 12) == spoken, scenario
    # And it is a fold every scheme sees the same way - twelve pulses of one
    # colour, four binary symbols, both for the same wall-clock noon.
    assert len(readout.render(spoken, "binary")) <= len(
        readout.render(spoken, "hour_colors")
    )


# --- the mirrored table: readout.SCHEMES lives twice ------------------------

SCHEMA_JS = (
    Path(__file__).resolve().parents[1] / "aibutton/web/static/schema.js"
).read_text(encoding="utf-8")


def test_the_editors_scheme_list_matches_the_compilers():
    """Mirrored tables are tested, not trusted (CLAUDE.md).

    The editor offers a scheme per option; the parser accepts a scheme per
    `readout.SCHEMES`. A fifth compiled scheme that nobody could choose, or an
    option the parser drops on save, are both silent failures.
    """
    block = re.search(
        r"key: 'readout_scheme'.*?options: \[(.*?)\],", SCHEMA_JS, re.S,
    )
    assert block, "the readout_scheme field is not a literal option list any more"
    offered = re.findall(r"value: '([a-z_]*)'", block.group(1))
    assert offered[0] == "", "the first option must be the empty 'no chime' one"
    assert set(offered[1:]) == set(readout.SCHEMES)


def test_the_editors_repeat_list_matches_the_parsers():
    block = re.search(r"repeats: \[(.*?)\],\n", SCHEMA_JS, re.S)
    assert block, "the schedule activation no longer declares its repeats"
    offered = re.findall(r"value: '([a-z_]*)'", block.group(1))
    assert offered[0] == "", "the first repeat must be the empty 'once a day' one"
    assert tuple(offered[1:]) == cfg.SCHEDULE_REPEATS
