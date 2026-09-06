"""Installing an app over the air.

The transfer is a mirrored table like everything else on this wire: the host
frames it (`device.app_package_frames`) and the firmware assembles it
(`apppkg.Receiver`), so every test here drives one with the output of the other
rather than asserting against a fixture.

**What is being protected is the failure case, not the happy one.** A push that
half-arrives, arrives corrupt, or arrives well-formed but meaningless must cost
you the transfer and nothing else - the app already on the device keeps
running, because "a package must never stop the button" applies most sharply at
the moment a new one turns up.
"""

import asyncio

import apppkg
import protocol

from aibutton import appc, device
from aibutton.config import parse_config

CONFIG = {
    "looks": {"warm": {"style": "solid", "color": "#ff8800"}},
    "modes": [
        {"name": "Home", "template": "actions", "activation": {"type": "always"},
         "double_tap": {"action": "enter_mode", "target": "Show"}},
        {"name": "Show", "template": "lightshow",
         "activation": {"type": "manual"}, "cues": "warm"},
    ],
}


def _package():
    package, _report = appc.compile_config(parse_config(CONFIG))
    return package


def _receive(frames, limit=protocol.MAX_PACKAGE_BYTES):
    """Play a host-framed transfer into a device-side receiver, exactly as
    `main.serve_package` does - the two decoders being the same code is the
    whole point of testing it this way."""
    receiver = apppkg.Receiver(limit)
    result = (None, None)
    for frame in frames:
        op = frame[0]
        if op == protocol.APP_BEGIN:
            receiver.begin((frame[1] << 8) | frame[2], protocol.APP_ERR_SIZE)
        elif op == protocol.APP_CHUNK:
            receiver.chunk(
                (frame[1] << 8) | frame[2], frame[3:],
                protocol.APP_ERR_STATE, protocol.APP_ERR_SIZE,
            )
        elif op == protocol.APP_COMMIT:
            result = receiver.commit(
                protocol.APP_ERR_STATE, protocol.APP_ERR_CRC,
                protocol.APP_ERR_DECODE,
            )
        elif op == protocol.APP_ABORT:
            receiver.reset()
    return receiver, result


# --- the transfer itself ---------------------------------------------------

def test_a_package_survives_being_framed_and_reassembled():
    package = _package()
    receiver, (bundle, raw) = _receive(device.app_package_frames(package))
    assert receiver.result == protocol.APP_OK or bundle is not None
    assert raw == package
    assert [app.name for app in bundle.apps] == ["Home", "Show"]


def test_it_arrives_in_more_than_one_write():
    """The point of chunking: a package is bigger than a conservative ATT
    write, so the framing has to survive being cut up."""
    frames = device.app_package_frames(_package())
    assert len(frames) >= 3  # begin, at least one chunk, commit
    assert all(len(frame) <= device.APP_CHUNK_BYTES + 3 for frame in frames)


def test_the_opcodes_mean_the_same_thing_on_both_sides():
    """Mirrored constants, and the one place they could silently disagree."""
    assert device.APP_BEGIN == protocol.APP_BEGIN
    assert device.APP_CHUNK == protocol.APP_CHUNK
    assert device.APP_COMMIT == protocol.APP_COMMIT
    assert device.APP_ABORT == protocol.APP_ABORT
    assert device.APP_OK == protocol.APP_OK
    assert device.MAX_PACKAGE_BYTES == protocol.MAX_PACKAGE_BYTES
    for code in (
        protocol.APP_ERR_STATE, protocol.APP_ERR_SIZE, protocol.APP_ERR_CRC,
        protocol.APP_ERR_DECODE, protocol.APP_ERR_WRITE,
    ):
        assert code in device.APP_RESULTS


def test_a_packages_fingerprint_is_the_crc_it_already_carries():
    """Both sides read the last two bytes rather than recomputing.

    Recomputing looks equivalent and is not: a CRC-16/CCITT over a file that
    ends in its own CRC is the constant 0x0000, so a recomputed fingerprint
    would match for every package ever built and the staleness check would be
    silently dead. Asserting the *non*-constant is what keeps it honest.
    """
    package = _package()
    assert device.package_crc(package) == apppkg.stamp(package)
    assert device.package_crc(package) == (package[-2] << 8) | package[-1]
    assert apppkg.crc16(package) == 0, "the residue this test exists to remember"


# --- everything that can go wrong ------------------------------------------

def test_a_flipped_byte_in_flight_is_refused():
    frames = device.app_package_frames(_package())
    broken = bytearray(frames[1])
    broken[10] ^= 0xFF
    frames[1] = bytes(broken)
    receiver, (bundle, raw) = _receive(frames)
    assert bundle is None and raw is None
    assert receiver.result == protocol.APP_ERR_CRC


def test_a_missing_chunk_is_refused():
    """A torn transfer is the case the length-and-checksum pair exists for:
    the bytes that never arrived are zeroes, and zeroes hash differently."""
    frames = device.app_package_frames(_package())
    receiver, (bundle, _raw) = _receive([frames[0]] + frames[2:])
    assert bundle is None
    assert receiver.result == protocol.APP_ERR_CRC


def test_a_chunk_with_no_transfer_open_is_refused():
    frames = device.app_package_frames(_package())
    receiver, _result = _receive(frames[1:2])
    assert receiver.result == protocol.APP_ERR_STATE


def test_a_commit_with_no_transfer_open_is_refused():
    receiver, (bundle, _raw) = _receive([bytes([protocol.APP_COMMIT])])
    assert bundle is None
    assert receiver.result == protocol.APP_ERR_STATE


def test_a_package_too_big_for_the_buffer_is_refused_before_it_arrives():
    """Refused at BEGIN, not after 4 KB of it has been accepted: the length is
    declared up front precisely so a hostile push cannot allocate first."""
    receiver, _result = _receive(
        device.app_package_frames(_package()), limit=32,
    )
    assert receiver.result == protocol.APP_ERR_SIZE


def test_a_chunk_past_the_declared_end_is_refused():
    package = _package()
    frames = device.app_package_frames(package)
    frames.insert(1, bytes([protocol.APP_CHUNK, 0xFF, 0xF0]) + b"\x00\x10")
    receiver, _result = _receive(frames)
    assert receiver.result == protocol.APP_ERR_SIZE


def test_well_formed_bytes_that_are_not_a_package_are_refused():
    """The checksum only says it arrived intact. A decode is what says it is a
    package at all - and the two failures stay tellable apart."""
    body = b"not a package, but intact"
    crc = appc.crc16(body)
    junk = body + bytes([crc >> 8, crc & 0xFF])
    receiver, (bundle, raw) = _receive(device.app_package_frames(junk))
    assert bundle is None and raw is None
    assert receiver.result == protocol.APP_ERR_DECODE


def test_an_abort_leaves_nothing_behind():
    frames = device.app_package_frames(_package())
    receiver, _ = _receive(frames[:2] + [bytes([protocol.APP_ABORT])])
    assert receiver._buf is None
    # ...and the next transfer is unaffected by the abandoned one.
    receiver2, (bundle, _raw) = _receive(frames)
    assert bundle is not None


def test_a_failed_transfer_does_not_hold_its_buffer():
    """A push that failed must not leave a kilobyte of RAM pinned on a device
    with half a megabyte of it."""
    frames = device.app_package_frames(_package())
    broken = bytearray(frames[1])
    broken[10] ^= 0xFF
    frames[1] = bytes(broken)
    receiver, _result = _receive(frames)
    assert receiver._buf is None


# --- what the device says about itself afterwards --------------------------

def test_device_info_carries_the_installed_package_and_older_hosts_ignore_it():
    """Appended, never inserted (ROADMAP D8). The six-byte form still parses,
    which is what stops a newer device going dark on an older host."""
    payload = protocol.device_info_payload(protocol.CAP_APP, package_crc=0xBEEF)
    assert len(payload) == protocol.DEVICE_INFO_LEN
    info = device.decode_device_info(payload)
    assert info.package_crc == 0xBEEF
    assert info.has(device.CAP_APP)
    # The same read, truncated to what a host from before this field expects.
    older = device.decode_device_info(payload[:6])
    assert older is not None and older.package_crc == 0


def test_a_device_that_cannot_be_sent_apps_says_so_rather_than_being_tried():
    """`CAP_APP` is the ask-don't-assume half: writing into a characteristic an
    un-reflashed board has never heard of is the failure v1 replaced."""
    info = device.decode_device_info(
        protocol.device_info_payload(protocol.CAP_LED)
    )
    assert not info.has(device.CAP_APP)


def test_the_mock_accepts_a_push_so_the_ui_works_with_no_board():
    mock = device.MockDevice()
    assert mock.info.has(device.CAP_APP)
    package = _package()
    ok, detail = asyncio.run(mock.push_package(package))
    assert ok and detail == "installed"
    assert mock.package == package
    assert mock.info.package_crc == device.package_crc(package)


def test_a_push_bigger_than_the_limit_is_refused_by_the_mock_too():
    mock = device.MockDevice()
    ok, _detail = asyncio.run(
        mock.push_package(b"x" * (device.MAX_PACKAGE_BYTES + 1))
    )
    assert not ok


def test_a_device_with_no_flash_refuses_politely():
    """The seam's default: a device that is its own hardware has nowhere to
    install to, and says that rather than pretending it worked."""

    class Bare(device.ButtonDevice):
        def set_led(self, state, effect=None): pass
        def play_sound(self, sound): pass
        def start_loop(self, sound): pass
        def stop_loop(self): pass

    ok, detail = asyncio.run(Bare().push_package(b"x"))
    assert not ok and "does not install" in detail


# --- staleness -------------------------------------------------------------

def test_an_edited_config_no_longer_matches_what_is_installed():
    """The drift this whole feature exists to make visible: the package on the
    button and the config on the host are two copies of one intention, and only
    one of them changes when you press Save."""
    config = parse_config(CONFIG)
    installed, _report = appc.compile_config(config)

    edited = dict(CONFIG)
    edited["looks"] = {"warm": {"style": "solid", "color": "#00ff88"}}
    wanted, _report = appc.compile_config(parse_config(edited))

    assert device.package_crc(installed) != device.package_crc(wanted)


def test_the_same_config_compiles_to_the_same_bytes_every_time():
    """Which is what makes the comparison above meaningful rather than noise -
    a compiler that varied would report every button as stale."""
    config = parse_config(CONFIG)
    first, _ = appc.compile_config(config)
    second, _ = appc.compile_config(config)
    assert first == second
