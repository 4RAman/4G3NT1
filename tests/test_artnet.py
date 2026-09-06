"""Art-Net (ArtDmx) encoding, checked against the format rather than against
ourselves - the same discipline test_osc.py applies to its sibling protocol.

The vectors below are written out by hand against the Art-Net 4 spec, because
encoding a packet and decoding it with the same module would agree with
itself no matter what it did. The one fact worth over-testing is the OpCode
byte order: it is the single field in this packet that is not big-endian, and
getting it backwards is invisible until a receiver's parser disagrees.
"""

import asyncio

import pytest

from aibutton import artnet
from aibutton.actions import execute
from aibutton.config import ArtnetAction, as_dict, parse_config, parse_with_warnings

_HEADER = b"Art-Net\x00" + b"\x00\x50" + b"\x00\x0e"  # ID, OpCode (low byte first), ProtVer


# --- the wire format ---------------------------------------------------

def test_a_bare_packet_is_the_header_then_universe_zero_and_one_channel():
    assert artnet.dmx(0, [255]) == (
        _HEADER + b"\x00\x00" + b"\x00\x00" + b"\x00\x02" + b"\xff\x00"
    )


def test_an_odd_number_of_channels_is_padded_to_even():
    """Art-Net requires an even data length - three channels must arrive as
    four bytes, with the padding channel silently at zero."""
    encoded = artnet.dmx(0, [255, 0, 128])
    assert encoded[-4:] == b"\xff\x00\x80\x00"
    assert encoded[-6:-4] == b"\x00\x04"  # LengthHi, Length


def test_an_even_number_of_channels_needs_no_padding():
    encoded = artnet.dmx(0, [10, 20])
    assert encoded[-2:] == b"\x0a\x14"
    assert encoded[-4:-2] == b"\x00\x02"


def test_the_universe_splits_into_subuni_and_net_low_byte_first():
    """300 = 0x012C: SubUni (low byte) 0x2C, Net (high byte) 0x01 - and in
    that order, unlike Length just after it."""
    encoded = artnet.dmx(300, [1])
    sub_uni_net = encoded[14:16]
    assert sub_uni_net == b"\x2c\x01"


def test_length_is_sent_high_byte_first_unlike_the_opcode_just_before_it():
    """The two multi-byte fields in this header disagree on endianness, which
    is exactly what makes OpCode the field worth pinning on its own."""
    encoded = artnet.dmx(0, list(range(1, 11)))  # 10 channels, even already
    assert encoded[16:18] == b"\x00\x0a"


def test_no_channels_still_sends_a_valid_even_length_packet():
    encoded = artnet.dmx(0, [])
    assert encoded[16:18] == b"\x00\x02"
    assert encoded[18:] == b"\x00\x00"


def test_channel_values_are_clamped_not_wrapped():
    """Wrapping would look like the button sending nonsense; clamping reads
    as 'it went to the top' or 'to zero'."""
    encoded = artnet.dmx(0, [300, -5, 100])
    assert encoded[-4:] == b"\xff\x00\x64\x00"


def test_more_than_512_channels_is_truncated_to_one_universe():
    encoded = artnet.dmx(0, [1] * 600)
    data = encoded[18:]
    assert len(data) == artnet.MAX_CHANNELS


def test_the_universe_is_masked_to_fifteen_bits():
    """A config asking for universe 40000 gets *a* universe rather than a
    crash - the same total-function shape as osc.message's leading slash."""
    encoded = artnet.dmx(40000, [1])
    assert artnet.dmx(40000 & 0x7FFF, [1]) == encoded


# --- the action ----------------------------------------------------------

@pytest.mark.parametrize("universe", [0, 32767])
def test_universe_bounds_are_accepted(universe):
    _, warnings = parse_with_warnings({
        "modes": [{
            "name": "Desk", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "artnet", "host": "127.0.0.1",
                             "universe": universe, "channels": [255]},
        }],
    })
    assert not warnings, warnings


def test_an_out_of_range_universe_is_dropped_loudly():
    cfg, warnings = parse_with_warnings({
        "modes": [{
            "name": "Desk", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "artnet", "host": "127.0.0.1",
                             "universe": 40000, "channels": [255]},
        }],
    })
    assert warnings
    mode = next((m for m in cfg.modes if m.name == "Desk"), None)
    assert mode is None or not mode.behavior.actions


@pytest.mark.parametrize("channels", [[], [1] * 513, [300], [-1], ["x"], "not-a-list"])
def test_bad_channel_lists_are_dropped_loudly(channels):
    _, warnings = parse_with_warnings({
        "modes": [{
            "name": "Desk", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "artnet", "host": "127.0.0.1",
                             "universe": 0, "channels": channels},
        }],
    })
    assert warnings


def test_the_port_defaults_to_the_standard_artnet_port():
    cfg = parse_config({
        "modes": [{
            "name": "Desk", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "artnet", "host": "127.0.0.1",
                             "universe": 0, "channels": [255]},
        }],
    })
    mode = next(m for m in cfg.modes if m.name == "Desk")
    action = mode.behavior.actions["short_press"]
    assert action.port == 6454


def test_an_artnet_action_round_trips_through_the_editor():
    raw = {"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": {"action": "artnet", "host": "10.0.0.4", "port": 6454,
                         "universe": 1, "channels": [255, 0, 128]},
    }]}
    once = parse_config(raw)
    twice = parse_config(as_dict(once))
    assert as_dict(once)["modes"] == as_dict(twice)["modes"]


async def test_a_press_actually_puts_a_datagram_on_the_wire():
    """End to end over a real loopback socket - the encoder is tested above,
    so what this proves is that the action reaches a listener at all."""
    loop = asyncio.get_running_loop()
    received: list[bytes] = []
    ready = asyncio.Event()

    class Receiver(asyncio.DatagramProtocol):
        def datagram_received(self, data, _addr):
            received.append(data)
            ready.set()

    transport, _protocol = await loop.create_datagram_endpoint(
        Receiver, local_addr=("127.0.0.1", 0)
    )
    try:
        port = transport.get_extra_info("sockname")[1]
        result = await execute(
            ArtnetAction(host="127.0.0.1", port=port, universe=0, channels=(255, 0)),
            trigger="short_press", mode_name="Desk", store=None,
        )
        assert result.ok
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        assert received == [artnet.dmx(0, (255, 0))]
    finally:
        transport.close()


async def test_an_unreachable_host_fails_the_press_without_raising():
    result = await execute(
        ArtnetAction(host="no.such.host.invalid", port=6454, universe=0, channels=(1,)),
        trigger="short_press", mode_name="Desk", store=None,
    )
    assert not result.ok
    assert "Art-Net failed" in result.message
