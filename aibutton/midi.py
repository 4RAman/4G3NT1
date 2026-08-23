"""MIDI channel-voice message encoding - the wire format, and nothing else.

MIDI is what a DAW listens on when it is listening for a physical control.
Studio One is the case that forced it: PreSonus document control surfaces over
MIDI / Mackie Control and Studio One Remote speaks their own UCNet, so there is
no OSC listener to point [osc.py](osc.py) at. TouchOSC's own documented route
into a DAW is a bridge converting OSC *to* MIDI - the same admission from the
other side.

**No ports here**, for the reason [osc.py](osc.py) has no sockets and
[device.py](device.py) has no radio: encoding is the half worth testing against
a table, and the half that runs anywhere. Getting the bytes to a port is
[midi_io.py](midi_io.py).

**Three bytes, and the useful part is which three.** A channel-voice message
is a status byte carrying the message kind in its high nibble and the channel
in its low one, then two data bytes that mean different things per kind. The
kinds here are the ones Studio One's Control Link can learn by right-click →
Assign → move the controller, which is the whole point of the exercise.

**Channels are 1-16 to a human and 0-15 on the wire**, and that off-by-one is
the single most common way a MIDI integration ends up silently on the wrong
channel. The boundary is here: everything outside this module says 1-16,
because that is what the DAW's own UI says.
"""

from __future__ import annotations

# High nibble of the status byte. Note-off is included even though a control
# surface rarely needs it, because an instrument track does: a note-on with no
# partner hangs that note until something else stops it.
NOTE_OFF = "note_off"
NOTE_ON = "note_on"
CONTROL_CHANGE = "cc"

_STATUS = {
    NOTE_OFF: 0x80,
    NOTE_ON: 0x90,
    CONTROL_CHANGE: 0xB0,
}

# Every kind this module can encode, in the order the editor should offer
# them. A list rather than a set so the editor's <select> is stable.
KINDS = (NOTE_ON, NOTE_OFF, CONTROL_CHANGE)

CHANNEL_MIN, CHANNEL_MAX = 1, 16
DATA_MIN, DATA_MAX = 0, 127


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def message(kind: str, channel: int, number: int, value: int) -> bytes:
    """Encode one channel-voice message as its three bytes.

    Total by construction, the way `osc.message` is: out-of-range numbers are
    clamped and an unknown kind falls back to note-on, because the alternative
    is a press that raises mid-action. The editor and `_parse_action` both
    validate up front, so this is the second line of defence.

    Clamping rather than wrapping is the same call `osc.py` makes on int32: 200
    arriving as 127 looks like "it went to the top", where the modulo would send
    72 and look like the button inventing numbers.
    """
    status = _STATUS.get(kind, _STATUS[NOTE_ON])
    wire_channel = _clamp(channel, CHANNEL_MIN, CHANNEL_MAX) - 1
    return bytes((
        status | wire_channel,
        _clamp(number, DATA_MIN, DATA_MAX),
        _clamp(value, DATA_MIN, DATA_MAX),
    ))


def describe(kind: str, channel: int, number: int, value: int) -> str:
    """A human-readable one-liner, for the action result and the logs.

    Says note or CC in the vocabulary the DAW uses, because the number alone
    is ambiguous - CC 60 and note 60 are different things that both read as
    "60" in a status line.
    """
    if kind == CONTROL_CHANGE:
        return f"CC {number}={value} ch{channel}"
    name = "note off" if kind == NOTE_OFF else "note on"
    return f"{name} {number} vel {value} ch{channel}"
