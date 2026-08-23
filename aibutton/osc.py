"""OSC 1.0 message encoding - the wire format, and nothing else.

Open Sound Control is what music and show-control software listens on when it
is listening for a physical control: Reaper, TouchOSC, QLab, Resolume, VCV
Rack, TouchDesigner, SuperCollider. A message is an address, a type-tag
string, and the arguments, each part null-padded to a multiple of four bytes.
That is the entire specification this needs, which is why it is forty lines of
stdlib rather than a dependency.

**No sockets here.** This module is pure - bytes in, bytes out - for the reason
[device.py](device.py) is: encoding is the half worth testing against a table,
and the half that has to run somewhere else eventually. The UDP send lives in
[actions.py](actions.py) next to the webhook's HTTP call, which is where the
other I/O of that shape already is.

**Why UDP and not something with a reply.** OSC is fire-and-forget by design,
which is the same contract the LED writes have (CLAUDE.md's invariants): the
button must never block on something at the other end of a wire. A webhook
that hangs costs a press; an OSC send physically cannot.

**MIDI is a sibling of this module and of `OscAction`**, not a mode of them - a
MIDI note does not travel over OSC and vice versa. See [midi.py](midi.py) and
[midi_io.py](midi_io.py).
"""

from __future__ import annotations

import struct

# OSC pads every part out to a four-byte boundary. Not an alignment nicety -
# receivers parse by walking those boundaries, so a message that is short by
# one byte is not a slightly wrong message, it is an unparseable one.
_ALIGN = 4

# 'i' is a 32-bit signed integer on the wire. Out-of-range values are clamped
# rather than wrapped: a config asking for 40000 on a MIDI-ish parameter is a
# mistake, and clamping is visible as "it went to the top" where wrapping
# looks like the button sending nonsense.
_INT32_MIN = -(2 ** 31)
_INT32_MAX = 2 ** 31 - 1


def _padded(data: bytes) -> bytes:
    return data + b"\x00" * (-len(data) % _ALIGN)


def _string(text: str) -> bytes:
    """An OSC-string: UTF-8, at least one null, padded to four.

    The trailing null is added before padding rather than counted as part of
    it, because a four-character string needs a fifth byte and therefore a
    whole extra word - the case that is wrong in every naive implementation.
    """
    return _padded(text.encode("utf-8") + b"\x00")


def _argument(value) -> tuple[str, bytes]:
    """One argument as (type tag, payload). Booleans carry no payload at all.

    Checked before int deliberately: bool is a subclass of int in Python, so
    the obvious ordering would send True as the integer 1. Some receivers
    treat those identically and some do not, and the one that does not is the
    one you find out about on stage.
    """
    if isinstance(value, bool):
        return ("T" if value else "F"), b""
    if isinstance(value, int):
        return "i", struct.pack(">i", max(_INT32_MIN, min(value, _INT32_MAX)))
    if isinstance(value, float):
        return "f", struct.pack(">f", value)
    return "s", _string(str(value))


def message(address: str, args=()) -> bytes:
    """Encode one OSC message.

    Total by construction, the way `ramp.color_at` is: an address with no
    leading slash gets one rather than raising, because the alternative is a
    press that does nothing and logs a traceback. The editor validates the
    same rule up front, so this is the second line of defence and not the
    explanation anybody reads.
    """
    if not address.startswith("/"):
        address = "/" + address
    tags = ","
    payload = b""
    for value in args:
        tag, encoded = _argument(value)
        tags += tag
        payload += encoded
    return _string(address) + _string(tags) + payload
