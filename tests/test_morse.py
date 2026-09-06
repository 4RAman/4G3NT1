"""aibutton.morse: a pure compiler from text to a stop list (TODO 83).

No config, no device, no clock - `encode` just turns a message and a unit
length into `sequencer.Stop`s, the same rhythm a telegraph key would send.
"""

from aibutton import morse
from aibutton.sequencer import Stop

ON = "#ff0000"
OFF = "#000000"


def test_alphabet_has_every_letter_and_digit_once():
    assert set(morse.ALPHABET) == set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    # Every code is dots and dashes only, and nothing is blank.
    for code in morse.ALPHABET.values():
        assert code and set(code) <= {".", "-"}


def test_a_single_dot():
    """'E' is one dot - one unit on, nothing else."""
    assert morse.encode("E", 1.0, ON) == (Stop(ON, 1.0, 0.0),)


def test_a_single_dash():
    """'T' is one dash - three units on."""
    assert morse.encode("T", 1.0, ON) == (Stop(ON, 3.0, 0.0),)


def test_sos_is_the_textbook_pattern():
    """S = ...  O = ---  S = ..., with the standard 1/3/1/3/7 gaps.

    Written out longhand rather than derived, so the test would catch the
    same mistake the algorithm could make.
    """
    dot, dash, gap, letter_gap = (
        Stop(ON, 1.0, 0.0), Stop(ON, 3.0, 0.0),
        Stop(OFF, 1.0, 0.0), Stop(OFF, 3.0, 0.0),
    )
    assert morse.encode("SOS", 1.0, ON) == (
        dot, gap, dot, gap, dot,           # S
        letter_gap,
        dash, gap, dash, gap, dash,        # O
        letter_gap,
        dot, gap, dot, gap, dot,           # S
    )


def test_a_word_gap_is_seven_units():
    one_word = morse.encode("SOS", 1.0, ON)
    two_words = morse.encode("SOS SOS", 1.0, ON)
    assert two_words == one_word + (Stop(OFF, 7.0, 0.0),) + one_word


def test_unit_seconds_scale_every_stop():
    fast = morse.encode("E", 1.0, ON)
    slow = morse.encode("E", 2.5, ON)
    assert slow == (Stop(ON, 2.5, 0.0),)
    assert slow[0].hold_s == fast[0].hold_s * 2.5


def test_unknown_characters_are_dropped_with_no_gap_of_their_own():
    """A character this alphabet does not know costs nothing - not even a
    pause - so 'A,B' plays identically to 'AB'."""
    assert morse.encode("A,B", 1.0, ON) == morse.encode("AB", 1.0, ON)


def test_a_message_of_only_unknown_characters_encodes_to_nothing():
    assert morse.encode("@@@", 1.0, ON) == ()
    assert morse.encode("", 1.0, ON) == ()
    assert morse.encode("   ", 1.0, ON) == ()


def test_unknown_chars_reports_each_once_in_first_seen_order():
    assert morse.unknown_chars("Hello, World!") == (",", "!")


def test_unknown_chars_excludes_space_and_known_letters():
    assert morse.unknown_chars("SOS") == ()
    assert morse.unknown_chars("S O S") == ()


def test_lowercase_is_accepted_like_uppercase():
    assert morse.encode("sos", 1.0, ON) == morse.encode("SOS", 1.0, ON)
    assert morse.unknown_chars("sos") == morse.unknown_chars("SOS")


# --- a colour that changes across the message -----------------------------
# `color` may be a callable rather than a string - config.py's way of baking a
# ramp onto the message at compile time, with this module staying ignorant of
# what the callable actually does (see `encode`'s docstring).

def test_a_callable_colour_is_sampled_once_per_symbol():
    calls: list[float] = []

    def color(progress):
        calls.append(progress)
        return "#000001"

    morse.encode("SOS", 1.0, color)
    assert len(calls) == 9  # S, O, S are three dots/dashes each - one call per symbol


def test_the_callable_is_never_sampled_for_a_gap():
    """Gaps stay `off` regardless of what the colour callable would say -
    only a lit symbol asks it anything."""
    stops = morse.encode("SOS", 1.0, lambda _progress: "#ffffff", off="#000000")
    assert all(s.color in ("#ffffff", "#000000") for s in stops)
    assert stops[1].color == "#000000"  # the gap after the first dot


def test_progress_runs_from_the_start_of_the_message_towards_its_end():
    """The first symbol is sampled at 0.0; later symbols see a strictly
    larger fraction, because each is further into the message than the last."""
    seen: list[float] = []

    def color(progress):
        seen.append(progress)
        return "#000000"

    morse.encode("SOS", 1.0, color)
    assert seen[0] == 0.0
    assert seen == sorted(seen)
    assert len(set(seen)) == len(seen)  # SOS's six symbols never share a start


def test_a_callable_that_always_returns_one_colour_matches_a_flat_string():
    """The escape hatch: a ramp of exactly one colour is indistinguishable
    from not having one at all."""
    flat = morse.encode("SOS", 1.0, "#ff8800")
    ramped = morse.encode("SOS", 1.0, lambda _progress: "#ff8800")
    assert flat == ramped


# --- the pause between repeats --------------------------------------------
# A looping sequence wraps straight from its last stop to its first with no
# gap of its own - fine for an ordinary colour loop, wrong for a beacon: the
# last symbol and the first would sit flush together on every lap, with
# nothing marking "the message just ended". Reported 2026-09-05 as "the
# repeats are getting stuck together".

def test_repeat_appends_a_pause_longer_than_any_gap_inside_the_message():
    plain = morse.encode("SOS", 1.0, ON)
    looped = morse.encode("SOS", 1.0, ON, repeat=True)
    assert looped[:-1] == plain
    extra = looped[-1]
    assert extra.color == OFF
    assert extra.hold_s > 7.0  # longer than the 7-unit word gap


def test_no_repeat_means_no_extra_pause():
    assert morse.encode("SOS", 1.0, ON, repeat=False) == morse.encode("SOS", 1.0, ON)


def test_an_empty_message_gets_no_pause_even_if_told_to_repeat():
    assert morse.encode("@@@", 1.0, ON, repeat=True) == ()
    assert morse.encode("", 1.0, ON, repeat=True) == ()


def test_the_repeat_pause_does_not_shrink_a_ramps_progress():
    """The ramp should still span the message, not the message-plus-its-own-
    trailing-silence - otherwise every symbol samples a smaller fraction than
    it would as a one-shot, and a looping message never quite reaches the
    ramp's far end."""
    seen_once: list[float] = []
    seen_looped: list[float] = []
    morse.encode("SOS", 1.0, lambda p: seen_once.append(p) or ON)
    morse.encode("SOS", 1.0, lambda p: seen_looped.append(p) or ON, repeat=True)
    assert seen_once == seen_looped
