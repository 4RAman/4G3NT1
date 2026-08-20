"""Following a DAW's tempo over MIDI clock.

Everything worth testing here is a list of numbers. A clock pulse train is
timestamps, jitter is timestamps with noise in them, a tempo change is two
trains joined, and a dropout is a gap - so none of this needs a MIDI port, a
DAW, or a running loop. That is the whole reason the estimator is a pure
function over timestamps rather than a method on the listener.

The listener itself is tested against a stand-in backend for the same reason
test_midi.py stubs the send path: what is worth checking is that a `0xF8`
becomes a timestamp and a `0xFC` becomes "not rolling", and neither of those
facts is about Windows.
"""

import pytest

from aibutton import midi_clock, midi_io
from aibutton.config import parse_config, as_dict, parse_with_warnings


def pulses(bpm: float, count: int = 25, start: float = 0.0) -> list[float]:
    """A clean clock train at `bpm`, 24 pulses to the quarter note."""
    step = 60.0 / bpm / midi_clock.PULSES_PER_QUARTER
    return [start + i * step for i in range(count)]


# --- the estimator ---------------------------------------------------------


@pytest.mark.parametrize("bpm", [40, 60, 90, 120, 128, 174, 200])
def test_a_clean_train_reads_back_as_its_own_tempo(bpm):
    assert midi_clock.bpm_from_pulses(pulses(bpm)) == pytest.approx(bpm, rel=1e-6)


def test_the_rate_is_twenty_four_pulses_per_quarter_note():
    """Not a tunable. A reader assuming any other rate reports a tempo that is
    wrong by exactly that ratio, which looks like a working feature."""
    assert midi_clock.PULSES_PER_QUARTER == 24
    # 120 BPM is two beats a second, so 48 pulses a second, so 1/48 s apart.
    assert midi_clock.bpm_from_intervals([1 / 48] * 24) == pytest.approx(120)


def test_one_late_pulse_does_not_move_the_answer():
    """The reason this is a median and not a mean. A driver thread delivering
    one pulse 15 ms late is normal - GC, timer granularity, the DAW's own
    buffer - and a mean would let that single straggler drag the tempo."""
    train = pulses(120)
    train[12] += 0.015  # one pulse arrives late, the next is early by the same
    assert midi_clock.bpm_from_pulses(train) == pytest.approx(120, rel=0.02)


def test_a_burst_of_jitter_still_lands_close():
    train = pulses(120)
    for i in range(2, len(train), 3):
        train[i] += 0.004 if i % 2 else -0.003
    assert midi_clock.bpm_from_pulses(train) == pytest.approx(120, rel=0.05)


def test_a_tempo_change_is_believed_within_about_half_a_window():
    """The cost of the median: a real change takes half a window to outvote the
    old tempo. Half a beat is the right trade against lurching on every hiccup."""
    slow = pulses(90, count=13)
    fast = pulses(180, count=14, start=slow[-1] + 60.0 / 180 / 24)
    settled = midi_clock.bpm_from_pulses(slow + fast)
    assert settled == pytest.approx(180, rel=0.05)


@pytest.mark.parametrize("count", [0, 1])
def test_too_few_pulses_is_none_rather_than_a_guess(count):
    assert midi_clock.bpm_from_pulses(pulses(120, count=count)) is None


def test_two_pulses_are_enough_to_say_something():
    assert midi_clock.bpm_from_pulses(pulses(120, count=2)) == pytest.approx(120)


@pytest.mark.parametrize("bpm", [5, 1000])
def test_an_impossible_tempo_is_refused_rather_than_reported(bpm):
    """A dropout or a device sending something that is not clock. Callers hold
    the last good tempo, which beats displaying nonsense confidently."""
    assert midi_clock.bpm_from_pulses(pulses(bpm)) is None


def test_identical_timestamps_do_not_divide_by_zero():
    assert midi_clock.bpm_from_pulses([1.0, 1.0, 1.0]) is None


def test_only_the_most_recent_window_counts():
    """A listener left running for an hour must answer about now, not about
    the average of the whole session."""
    old = pulses(90, count=40)
    new = pulses(150, count=30, start=old[-1] + 1)
    assert midi_clock.bpm_from_pulses(old + new, window=24) == pytest.approx(150, rel=0.05)


# --- noticing that it stopped ----------------------------------------------


def test_silence_longer_than_two_beats_is_stale():
    """A DAW that is quit or unplugged sends no 0xFC - the pulses just stop,
    and this is the only way to notice."""
    train = pulses(120)
    assert not midi_clock.is_stale(train, train[-1] + 0.05, bpm=120)
    assert midi_clock.is_stale(train, train[-1] + 1.5, bpm=120)


def test_staleness_scales_with_the_tempo():
    """Two beats at 60 BPM is two seconds; at 240 it is half of one. A fixed
    timeout would be trigger-happy at slow tempos and sleepy at fast ones."""
    train = pulses(60)
    assert not midi_clock.is_stale(train, train[-1] + 1.5, bpm=60)
    assert midi_clock.is_stale(train, train[-1] + 1.5, bpm=240)


def test_no_pulses_at_all_is_stale():
    assert midi_clock.is_stale([], 100.0)


# --- the listener ----------------------------------------------------------


class FakeBackend:
    """Stands in for winmm/rtmidi. Hands back the callback so a test can play
    a clock train into it directly."""

    name = "fake"

    def __init__(self, names=("Studio One 1",)):
        self.names = list(names)
        self.on_message = None
        self.closed = False

    def in_ports(self):
        return list(self.names)

    def listen(self, index, on_message):
        self.on_message = on_message
        self.index = index

        def close():
            self.closed = True

        return close


@pytest.fixture
def fake_backend(monkeypatch):
    def install(**kwargs):
        backend = FakeBackend(**kwargs)
        monkeypatch.setattr(midi_io, "_BACKEND", backend)
        return backend

    return install


def test_a_clock_byte_becomes_a_timestamp(fake_backend):
    backend = fake_backend()
    listener = midi_io.ClockListener("Studio")
    listener.start()
    for _ in range(5):
        backend.on_message(midi_clock.CLOCK)
    assert len(listener._pulses) == 5


def test_transport_bytes_are_tracked_and_are_not_pulses(fake_backend):
    backend = fake_backend()
    listener = midi_io.ClockListener("Studio")
    listener.start()
    assert not listener.rolling
    backend.on_message(midi_clock.START)
    assert listener.rolling
    backend.on_message(midi_clock.STOP)
    assert not listener.rolling
    backend.on_message(midi_clock.CONTINUE)
    assert listener.rolling
    assert not listener._pulses  # none of those was a clock pulse


def test_other_midi_on_the_port_is_ignored(fake_backend):
    """A port carrying notes as well as clock must not have its notes counted
    as pulses - that would read as an impossible tempo."""
    backend = fake_backend()
    listener = midi_io.ClockListener("Studio")
    listener.start()
    for status in (0x90, 0xB0, 0xFE, 0x80):  # note on, CC, active sensing, note off
        backend.on_message(status)
    assert not listener._pulses


def test_the_ring_holds_one_window_however_long_it_runs(fake_backend):
    """An hour of clock is 170,000 pulses. The deque's maxlen is what keeps
    that from being 170,000 floats in memory."""
    backend = fake_backend()
    listener = midi_io.ClockListener("Studio", window=24)
    listener.start()
    for _ in range(5000):
        backend.on_message(midi_clock.CLOCK)
    assert len(listener._pulses) == 25  # window + 1, for 24 intervals


def test_a_missing_input_port_says_what_was_available(fake_backend):
    fake_backend(names=["Something else"])
    with pytest.raises(midi_io.PortNotFound) as caught:
        midi_io.ClockListener("Studio One").start()
    assert "Something else" in str(caught.value)


def test_stopping_closes_the_port(fake_backend):
    backend = fake_backend()
    listener = midi_io.ClockListener("Studio")
    listener.start()
    listener.stop()
    assert backend.closed


def test_the_listener_is_a_context_manager(fake_backend):
    backend = fake_backend()
    with midi_io.ClockListener("Studio"):
        assert not backend.closed
    assert backend.closed


# --- config ----------------------------------------------------------------


def _metronome(**over) -> dict:
    mode = {"name": "Click", "template": "metronome",
            "activation": {"type": "manual"}}
    mode.update(over)
    return {"modes": [mode]}


def test_a_metronome_is_tap_only_unless_a_clock_port_is_named():
    """The mode has always been tap tempo and stays that way by default."""
    config = parse_config(_metronome())
    assert config.modes[0].behavior.clock_port == ""


def test_a_clock_port_round_trips():
    once = parse_config(_metronome(clock_port="Studio One"))
    assert once.modes[0].behavior.clock_port == "Studio One"
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


def test_a_bad_clock_port_costs_the_sync_and_not_the_mode():
    """Every key falls back individually - a metronome with a broken port
    setting is still a metronome."""
    config, warnings = parse_with_warnings(_metronome(clock_port=42))
    assert warnings
    mode = next(m for m in config.modes if m.name == "Click")
    assert mode.behavior.clock_port == ""
