"""Art-Net (the ArtDmx packet) - the wire format, and nothing else.

Art-Net is DMX512 over UDP: the same shape [osc.py](osc.py) already has for a
different room. Every serious lighting desk (QLab, Resolume, Chamsys, a
grandMA) and a cheap Art-Net node speaks it over a plain UDP socket - no
dependency, no reply expected (TODO 93).

**No sockets here**, for the same reason osc.py has none: encoding is the
half worth testing against a table (the Art-Net 4 spec's ArtDmx layout), and
the half that has to run somewhere else eventually. The UDP send lives in
[actions.py](actions.py), next to osc's and the webhook's - the same
fire-and-forget contract, restated for a different wire: the button must
never block on something at the other end of it.

**The one field that is not network order, and the classic transcription
bug**: everything in this packet is big-endian *except* OpCode, which the
spec sends low byte first. Get that one backwards and every other field still
looks plausible - only a receiver's parser disagrees.
"""

from __future__ import annotations

_ID = b"Art-Net\x00"
_OPCODE_DMX = 0x5000  # ArtDmx - sent low byte first, unlike everything else here
_PROTOCOL_VERSION = 14

# A DMX512 universe. Not a config choice - the standard fixes it.
MAX_CHANNELS = 512


def dmx(universe: int, channels) -> bytes:
    """One ArtDmx packet: `channels` (each clamped to a byte) on `universe`.

    Total by construction, like `osc.message`: `universe` is masked to the
    protocol's 15 bits (Net + Sub-Net + Universe, packed as the wire's SubUni
    and Net fields) rather than rejected, and `channels` is clamped to
    1-`MAX_CHANNELS` values and padded to an even count - Art-Net requires an
    even data length, and a config asking for something out of range is a
    mistake a fixture should show, not a packet a receiver silently drops.
    """
    universe &= 0x7FFF
    data = bytes(max(0, min(255, int(v))) for v in channels)[:MAX_CHANNELS]
    if not data:
        data = b"\x00"
    if len(data) % 2:
        data += b"\x00"
    length = len(data)
    return (
        _ID
        + bytes([_OPCODE_DMX & 0xFF, (_OPCODE_DMX >> 8) & 0xFF])  # OpCode, low byte first
        + bytes([0, _PROTOCOL_VERSION])                            # ProtVerHi, ProtVerLo
        + bytes([0, 0])                                            # Sequence, Physical - unused
        + bytes([universe & 0xFF, (universe >> 8) & 0xFF])         # SubUni, Net
        + bytes([(length >> 8) & 0xFF, length & 0xFF])             # LengthHi, Length
        + data
    )
