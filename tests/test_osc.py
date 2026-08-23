"""OSC encoding, checked against the format rather than against ourselves.

The padding rules are the whole specification worth testing: a receiver parses
by walking four-byte boundaries, so a message that is short by one byte is not
slightly wrong, it is unreadable. These vectors are written out by hand for
that reason - encoding a message and decoding it with the same module would
agree with itself no matter what it did.
"""

import asyncio
import struct

import pytest

from aibutton import osc
from aibutton.actions import execute
from aibutton.config import OscAction, parse_config, as_dict, parse_with_warnings


# --- the wire format -------------------------------------------------------


def test_a_bare_message_is_the_address_then_an_empty_type_tag():
    assert osc.message("/go") == b"/go\x00" + b",\x00\x00\x00"


def test_a_string_needing_no_padding_still_gets_a_whole_extra_word():
    """The case every naive implementation gets wrong: '/abc' is four bytes,
    so its terminating null pushes it to eight - not to four."""
    assert osc.message("/abc")[:8] == b"/abc\x00\x00\x00\x00"


def test_an_integer_argument_is_big_endian_int32():
    encoded = osc.message("/x", [1])
    assert encoded == b"/x\x00\x00" + b",i\x00\x00" + struct.pack(">i", 1)


def test_a_float_argument_is_big_endian_float32():
    encoded = osc.message("/x", [0.5])
    assert encoded == b"/x\x00\x00" + b",f\x00\x00" + struct.pack(">f", 0.5)


def test_booleans_travel_as_type_tags_with_no_payload():
    """And are checked before int, because bool subclasses int in Python -
    the obvious ordering would send True as the integer 1, which some
    receivers treat differently."""
    assert osc.message("/x", [True, False]) == b"/x\x00\x00" + b",TF\x00"


def test_a_string_argument_is_padded_like_the_address():
    encoded = osc.message("/x", ["hi"])
    assert encoded == b"/x\x00\x00" + b",s\x00\x00" + b"hi\x00\x00"


def test_mixed_arguments_keep_their_order():
    encoded = osc.message("/m", [1, 2.0, "three"])
    assert encoded[4:8] == b",ifs"


def test_every_message_is_a_whole_number_of_words():
    for address, args in [
        ("/a", []), ("/abc", [1]), ("/longer/path", ["x", 2, 3.5, True]),
        ("/z", ["four"]), ("/y", ["12345"]),
    ]:
        assert len(osc.message(address, args)) % 4 == 0, (address, args)


def test_an_address_without_a_slash_gets_one_rather_than_raising():
    """Total, like ramp.color_at: the editor validates this properly, and a
    press that raises is worse than a press that guesses the obvious thing."""
    assert osc.message("go") == osc.message("/go")


def test_an_out_of_range_integer_is_clamped_not_wrapped():
    """Wrapping would look like the button sending nonsense; clamping reads
    as 'it went to the top'."""
    encoded = osc.message("/x", [2 ** 40])
    assert encoded[-4:] == struct.pack(">i", 2 ** 31 - 1)


# --- the action ------------------------------------------------------------


def test_a_malformed_address_is_dropped_loudly_rather_than_repaired():
    """The one field where a quiet fix reaches the wrong handler on somebody
    else's machine."""
    cfg, warnings = parse_with_warnings({
        "modes": [{
            "name": "Desk", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "osc", "host": "127.0.0.1", "port": 8000,
                            "address": "transport/play"},
        }],
    })
    assert warnings
    mode = next((m for m in cfg.modes if m.name == "Desk"), None)
    assert mode is None or not mode.behavior.actions


@pytest.mark.parametrize("port", [0, 70000, "8000", True])
def test_an_impossible_port_is_refused(port):
    _, warnings = parse_with_warnings({
        "modes": [{
            "name": "Desk", "template": "actions", "activation": {"type": "always"},
            "short_press": {"action": "osc", "host": "127.0.0.1", "port": port,
                            "address": "/go"},
        }],
    })
    assert warnings


def test_an_osc_action_round_trips_through_the_editor():
    raw = {"modes": [{
        "name": "Desk", "template": "actions", "activation": {"type": "always"},
        "short_press": {"action": "osc", "host": "10.0.0.4", "port": 9000,
                        "address": "/clip/1/launch", "args": [1, 0.5, "go"]},
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
            OscAction(host="127.0.0.1", port=port, address="/go", args=(1,)),
            trigger="short_press", mode_name="Desk", store=None,
        )
        assert result.ok
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        assert received == [osc.message("/go", [1])]
    finally:
        transport.close()


async def test_a_sessions_numbers_ride_after_the_configured_arguments():
    """TODO 32: the other carrier. Positional, so two things are being
    asserted - that the numbers arrive at all, and that they arrive *after*
    the arguments the action already had, so a mode growing an exit hook does
    not renumber what a receiver was already mapping. Their own order is by
    key name (summary.as_args)."""
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
            OscAction(host="127.0.0.1", port=port, address="/done", args=(1,)),
            trigger="on_exit", mode_name="Focus", store=None,
            session={"focused_s": 6000.0, "blocks": 4},
        )
        assert result.ok
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        # 1 is the action's own argument; then blocks, then focused_s - by key
        # name, not by the order the app happened to build the dict in.
        assert received == [osc.message("/done", [1, 4, 6000.0])]
    finally:
        transport.close()


async def test_an_unreachable_host_fails_the_press_without_raising():
    result = await execute(
        OscAction(host="no.such.host.invalid", port=9000, address="/go"),
        trigger="short_press", mode_name="Desk", store=None,
    )
    assert not result.ok
    assert "OSC failed" in result.message
