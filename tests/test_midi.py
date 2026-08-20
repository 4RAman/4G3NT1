"""MIDI encoding and the midi action, neither of which needs a MIDI port.

The vectors are written out by hand for the reason test_osc.py's are: encoding
a message and decoding it with the same module proves only that the module
agrees with itself. The status bytes below come from the MIDI spec's
channel-voice table, and the channel arithmetic is the part actually worth
guarding - 1-16 outside, 0-15 on the wire, and one off-by-one puts every
message on a channel the DAW is not listening to.

The send path is tested against a stand-in for `python-rtmidi` rather than the
library, because the library is optional and the interesting cases (no
library, no port, a port that throws) are all reachable without one.
"""

import re
import sys
from pathlib import Path

import pytest

from aibutton import actions, midi, midi_io
from aibutton.actions import execute
from aibutton.config import MidiAction, as_dict, parse_config, parse_with_warnings


# --- the wire format -------------------------------------------------------


def test_a_note_on_is_status_nine_note_velocity():
    assert midi.message("note_on", 1, 60, 127) == bytes((0x90, 60, 127))


def test_a_note_off_is_status_eight():
    assert midi.message("note_off", 1, 60, 0) == bytes((0x80, 60, 0))


def test_a_control_change_is_status_eleven():
    assert midi.message("cc", 1, 7, 100) == bytes((0xB0, 7, 100))


@pytest.mark.parametrize("channel,expected_status", [
    (1, 0x90), (2, 0x91), (10, 0x99), (16, 0x9F),
])
def test_channels_are_one_to_sixteen_outside_and_zero_to_fifteen_on_the_wire(
    channel, expected_status,
):
    """The single most common way a MIDI integration ends up silently on the
    wrong channel. Channel 1 must be status 0x90, not 0x91."""
    assert midi.message("note_on", channel, 60, 127)[0] == expected_status


@pytest.mark.parametrize("kind", midi.KINDS)
def test_every_kind_encodes_to_exactly_three_bytes(kind):
    assert len(midi.message(kind, 1, 60, 64)) == 3


@pytest.mark.parametrize("number,expected", [(-5, 0), (0, 0), (127, 127), (200, 127)])
def test_data_bytes_are_clamped_not_wrapped(number, expected):
    """Wrapping would send 200 as 72 and look like the button inventing
    numbers; clamping reads as 'it went to the top'. Same call osc.py makes."""
    assert midi.message("note_on", 1, number, 0)[1] == expected


@pytest.mark.parametrize("channel,expected_status", [(0, 0x90), (99, 0x9F)])
def test_an_impossible_channel_is_clamped_rather_than_raising(
    channel, expected_status,
):
    """Total by construction: the editor and the parser both refuse these, so
    reaching here means something already went wrong and a traceback in the
    middle of a press would not help."""
    assert midi.message("note_on", channel, 60, 127)[0] == expected_status


def test_an_unknown_kind_falls_back_to_note_on_rather_than_raising():
    assert midi.message("wat", 1, 60, 127) == midi.message("note_on", 1, 60, 127)


def test_the_status_byte_never_collides_across_kinds():
    """Three different kinds on one channel must be three different status
    bytes, or a DAW cannot tell them apart."""
    statuses = {midi.message(k, 1, 60, 64)[0] for k in midi.KINDS}
    assert len(statuses) == len(midi.KINDS)


def test_describe_distinguishes_a_note_from_a_controller():
    """CC 60 and note 60 both read as '60' in a status line, which is exactly
    the ambiguity this exists to remove."""
    assert "CC" in midi.describe("cc", 1, 60, 100)
    assert "note" in midi.describe("note_on", 1, 60, 100)


# --- config ----------------------------------------------------------------


def _mode_with(action: dict) -> dict:
    return {"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": action,
    }]}


def test_a_midi_action_round_trips_through_the_editor():
    raw = _mode_with({"action": "midi", "port": "Button", "kind": "cc",
                      "channel": 10, "number": 7, "value": 64})
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


def test_a_parsed_action_carries_the_fields_it_was_given():
    cfg = parse_config(_mode_with({"action": "midi", "port": "Button",
                                   "kind": "note_on", "channel": 3,
                                   "number": 64, "value": 100}))
    action = cfg.modes[0].behavior.actions["short_press"]
    assert action == MidiAction(port="Button", channel=3, kind="note_on",
                                number=64, value=100)


@pytest.mark.parametrize("bad", [
    {"channel": 0}, {"channel": 17}, {"channel": True}, {"channel": "1"},
    {"number": -1}, {"number": 128}, {"number": 1.5},
    {"value": 200}, {"value": None},
    {"kind": "aftertouch"}, {"kind": ""},
    {"port": 4},
])
def test_a_field_outside_its_range_is_refused_with_a_warning(bad):
    """Refused rather than clamped, even though midi.message would clamp: a
    config asking for channel 17 is a mistake, and sending it on 16 would be a
    lie that plays."""
    action = {"action": "midi", "port": "Button", "kind": "note_on",
              "channel": 1, "number": 60, "value": 127, **bad}
    cfg, warnings = parse_with_warnings(_mode_with(action))
    assert warnings
    mode = next((m for m in cfg.modes if m.name == "Desk"), None)
    assert mode is None or not mode.behavior.actions


def test_an_omitted_port_is_allowed_and_means_the_first_one():
    """A machine with one virtual cable should not have to name it."""
    cfg = parse_config(_mode_with({"action": "midi", "kind": "note_on",
                                   "channel": 1, "number": 60, "value": 127}))
    assert cfg.modes[0].behavior.actions["short_press"].port == ""


def test_the_editors_own_defaults_parse():
    """Unlike every other action, MIDI's `defaults()` in schema.js carries real
    values rather than blanks - three numbers each with their own range. An
    off-by-one in any of them would make "Add a MIDI message" produce something
    the parser drops on Save, which reads as the editor losing your work."""
    schema = (Path(__file__).resolve().parents[1]
              / "aibutton/web/static/schema.js").read_text(encoding="utf-8")
    block = schema[schema.index("type: 'midi',"):]
    body = block[block.index("defaults: () => ({"):block.index("describe:")]
    raw = {}
    for key, value in re.findall(r"(\w+): ('[^']*'|\d+)", body):
        raw[key] = value.strip("'") if value.startswith("'") else int(value)
    assert raw.pop("action") == "midi"
    assert parse_config(_mode_with({"action": "midi", **raw})).modes[0].behavior.actions


# --- the DAW command table -------------------------------------------------


def _schema_source() -> str:
    return (Path(__file__).resolve().parents[1]
            / "aibutton/web/static/schema.js").read_text(encoding="utf-8")


def _daw_commands() -> list[tuple[str, int]]:
    source = _schema_source()
    block = source[source.index("export const DAW_COMMANDS = ["):]
    block = block[:block.index("\n];")]
    return [(m[0], int(m[1])) for m in
            re.findall(r"id: '([^']+)'.*?_mcu\((\d+)\)", block, re.S)]


def test_the_daw_commands_are_all_sendable_as_midi_actions():
    """The picker writes these straight onto the action, so every one has to
    survive the parser - a number outside 0-127 would make a menu entry that
    silently loses the binding on Save."""
    for name, number in _daw_commands():
        cfg = parse_config(_mode_with({
            "action": "midi", "port": "", "kind": "note_on",
            "channel": 1, "number": number, "value": 127,
        }))
        assert cfg.modes[0].behavior.actions, f"{name} (note {number}) did not parse"


def test_no_two_daw_commands_share_a_note():
    """Two entries on one number would make the reverse lookup ambiguous, so
    the editor would name the wrong command beside a saved action."""
    numbers = [number for _, number in _daw_commands()]
    assert len(set(numbers)) == len(numbers)


def test_each_label_states_the_note_it_actually_sends():
    """The number appears twice per entry now - in the label a person reads and
    in the message that goes out. A label saying 94 while sending 95 would be
    the most confusing possible bug here, because the DAW would do something
    and it would be the wrong thing."""
    source = _schema_source()
    block = source[source.index("export const DAW_COMMANDS = ["):]
    block = block[:block.index("\n];")]
    mismatched = [
        m.group(1) for m in
        re.finditer(r"id: '([^']+)', label: '[^']*?\((\d+)\)'.*?_mcu\((\d+)\)",
                    block, re.S)
        if m.group(2) != m.group(3)
    ]
    assert not mismatched


def test_commands_of_a_group_are_listed_together():
    """The preset widget builds an <optgroup> per *run* of same-group entries,
    so a stray Transport command down among the modifiers would silently open a
    second Transport group rather than joining the first."""
    source = _schema_source()
    block = source[source.index("export const DAW_COMMANDS = ["):]
    block = block[:block.index("\n];")]
    groups = re.findall(r"group: '([^']+)'", block)
    runs = [g for i, g in enumerate(groups) if i == 0 or groups[i - 1] != g]
    assert len(runs) == len(set(runs)), f"a group is split across the table: {runs}"


def test_the_transport_commands_are_the_mackie_control_numbers():
    """Pinned deliberately. These are not ours to choose - a DAW told it has a
    Mackie Control already knows what they mean, and that is the entire reason
    the picker needs no learning step. Changing one silently breaks every
    config built from the menu."""
    by_id = dict(_daw_commands())
    assert by_id["rewind"] == 91
    assert by_id["forward"] == 92
    assert by_id["stop"] == 93
    assert by_id["play"] == 94
    assert by_id["record"] == 95


# The DAW preset's own bindings are checked in test_control.py, beside the
# template it uses - it moved from an ambient actions mode to a control surface
# once one existed, and asserting its shape from here as well would be two
# places to update for one change.


def test_the_preset_widget_writes_whatever_the_table_says():
    """It used to assign `url` and `payload` by name, which made a
    generic-looking widget webhook-only. The DAW picker is the second user and
    writes three different keys, so the coupling had to go."""
    widgets = (Path(__file__).resolve().parents[1]
               / "aibutton/web/static/widgets.js").read_text(encoding="utf-8")
    block = widgets[widgets.index("  preset(spec, obj, onInput, ctx) {"):]
    block = block[:block.index("\n  textarea(")]
    assert "chosen.set" in block
    assert "url:" not in block and "payload:" not in block


def test_every_preset_table_uses_the_set_key():
    """Both tables feed the one widget, so an entry still written the old way
    would fill in nothing and look like the picker was broken."""
    source = _schema_source()
    for name in ("INTEGRATIONS", "DAW_COMMANDS"):
        block = source[source.index(f"export const {name} = ["):]
        block = block[:block.index("\n];")]
        ids = re.findall(r"^  \{$|id: '", block, re.M)
        assert block.count("set: ") == len(re.findall(r"id: '", block)), name
        assert ids


# --- port matching ---------------------------------------------------------


@pytest.mark.parametrize("names,wanted,expected", [
    # Windows renames the port you created, so the config holds the stem.
    (["Button 2"], "Button", 0),
    (["Microsoft GS Wavetable Synth 0", "Button 2"], "button", 1),
    (["A", "B"], "", 0),          # no name given: the first port
    (["A", "B"], "C", None),      # named and absent: not a silent fallback
    ([], "Button", None),         # nothing at all
    ([], "", None),
])
def test_a_port_is_matched_on_part_of_its_name(names, wanted, expected):
    assert midi_io.match_port(names, wanted) == expected


# --- the backend -----------------------------------------------------------


def test_windows_needs_no_dependency_to_send_midi():
    """The finding that redesigned this action: python-rtmidi publishes no
    wheel for 3.14 and will not build here, but winmm.dll has shipped with
    Windows since the 90s and does exactly this job from ctypes."""
    if sys.platform != "win32":
        pytest.skip("winmm is the Windows backend")
    assert midi_io.backend_name() == "winmm"


def test_there_is_always_an_answer_about_which_backend_is_in_use():
    """None is a legitimate answer, not an error - a Linux host with no rtmidi
    loses this action and keeps the service."""
    assert midi_io.backend_name() in (None, "winmm", "python-rtmidi")


def test_enumerating_ports_names_something_real():
    """Not asserting a particular port: what is being checked is that the
    backend talks to the OS at all. Windows always has at least the GS
    Wavetable Synth, so an empty list here means the call failed silently."""
    if midi_io.backend_name() is None:
        pytest.skip("no MIDI backend on this machine")
    names = midi_io.ports()
    assert isinstance(names, list)
    assert all(isinstance(n, str) and n for n in names)


def test_a_real_send_reaches_a_real_port():
    """End to end against whatever MIDI device this machine has, the way
    test_osc.py sends a real datagram to a real socket. What it proves is that
    the ctypes declarations are right - a truncated handle or a mis-packed
    DWORD fails here and nowhere else."""
    if midi_io.backend_name() is None or not midi_io.ports():
        pytest.skip("no MIDI port on this machine")
    # Note off rather than note on: this may well be a real synth, and a test
    # run should not leave a note ringing on somebody's speakers.
    used = midi_io.send("", midi.message("note_off", 1, 60, 0))
    assert used in midi_io.ports()


def test_a_named_port_that_is_absent_raises_rather_than_using_another():
    if midi_io.backend_name() is None:
        pytest.skip("no MIDI backend on this machine")
    with pytest.raises(midi_io.PortNotFound):
        midi_io.send("no such port exists anywhere", b"\x90\x3c\x00")


# --- the action ------------------------------------------------------------


NOTE_ON_MIDDLE_C = MidiAction(
    port="Button", channel=1, kind="note_on", number=60, value=127,
)


@pytest.fixture
def stub_send(monkeypatch):
    """Replace midi_io.send. The backends are tested against the real OS
    above; what these check is how a press reports what happened."""
    def install(result=None, raises=None):
        sent = []

        def fake(port, data):
            sent.append((port, data))
            if raises is not None:
                raise raises
            return result

        monkeypatch.setattr(actions.midi_io, "send", fake)
        return sent

    return install


async def test_a_press_sends_three_bytes_to_the_named_port(stub_send):
    sent = stub_send(result="Button 2")
    result = await execute(
        NOTE_ON_MIDDLE_C, trigger="short_press", mode_name="Desk", store=None,
    )
    assert result.ok
    assert sent == [("Button", bytes((0x90, 60, 127)))]


async def test_the_result_names_the_port_actually_used(stub_send):
    """Not the one asked for: "Button" matched "Button 2", and the status line
    saying so is how a person confirms the substring did what they meant."""
    stub_send(result="Button 2")
    result = await execute(
        NOTE_ON_MIDDLE_C, trigger="short_press", mode_name="Desk", store=None,
    )
    assert "Button 2" in result.message


async def test_no_backend_costs_the_action_and_not_the_service(stub_send):
    """The whole reason the backend is optional: a machine that cannot do MIDI
    fails this action and keeps everything else working."""
    stub_send(raises=midi_io.MidiUnavailable("no MIDI backend"))
    result = await execute(
        NOTE_ON_MIDDLE_C, trigger="short_press", mode_name="Desk", store=None,
    )
    assert not result.ok
    assert "unavailable" in result.message.lower()


async def test_a_named_port_that_is_absent_says_what_was_available(stub_send):
    """The one failure a person can actually fix, so the message names the
    ports that do exist rather than only the one that does not."""
    stub_send(raises=midi_io.PortNotFound(
        "MIDI port 'Button' not found (available: Microsoft GS Wavetable Synth)"
    ))
    result = await execute(
        NOTE_ON_MIDDLE_C, trigger="short_press", mode_name="Desk", store=None,
    )
    assert not result.ok
    assert "Microsoft GS Wavetable Synth" in result.message


async def test_a_driver_that_throws_fails_the_press_without_raising(stub_send):
    """Both backends reach a C layer and neither documents its exception set,
    so this is caught broadly - a MIDI cable never takes the service down."""
    stub_send(raises=OSError("exception 0xC0000005 from a MIDI driver"))
    result = await execute(
        NOTE_ON_MIDDLE_C, trigger="short_press", mode_name="Desk", store=None,
    )
    assert not result.ok
    assert "MIDI failed" in result.message
