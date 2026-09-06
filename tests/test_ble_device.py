"""BLEDevice against a fake bleak - the reconnect behaviour especially.

A radio link is the one part of the system that is *expected* to fail at
runtime, so what matters here is not the happy path (real hardware proves
that) but everything around it: writes while disconnected, a link dropping
mid-session, and whether reconnecting leaves the device showing what the
host actually believes.

BleakScanner/BleakClient are replaced module-side, so no radio and no board
is involved and the tests run in milliseconds.
"""

import asyncio
import contextlib

import protocol as fw  # firmware/protocol.py - see conftest.py
import pytest

from aibutton import ble_device
from aibutton.device import (
    BUTTON_EVENT_UUID,
    CAP_BUZZER,
    CAP_LED,
    CAP_PALETTE,
    DEVICE_INFO_UUID,
    GESTURE_CONFIG_UUID,
    GESTURE_TAP,
    LED_CODES,
    LED_EFFECT_UUID,
    LED_PALETTE_UUID,
    LED_STATE_UUID,
    SOUND_CMD_UUID,
    STOP_LOOP_CMD,
    LEDState,
    Sound,
    TriggerType,
    effect_payload,
    palette_payload,
    sound_command,
)

# What this firmware actually reports, so the fake stands in for the board on
# the bench rather than for one nobody has any more. The reduced payloads
# below are the *older* devices, and they are what the fallback paths are
# tested against.
FULL_INFO = fw.device_info_payload(
    fw.CAP_LED | fw.CAP_BUZZER | fw.CAP_PALETTE | fw.CAP_EFFECT | fw.CAP_GESTURE_PARAMS
)
PRE_V1_INFO = fw.device_info_payload(fw.CAP_LED | fw.CAP_BUZZER | fw.CAP_PALETTE)


class _Look:
    """A stand-in for config.LedEffect - palette_payload duck-types it, and
    this module has no business importing config to say "orange, flashing"."""

    def __init__(self, style="flash", color="#ff8800", color2="#000000", period_s=0.5):
        self.style, self.color, self.color2, self.period_s = (
            style, color, color2, period_s
        )


class FakeBleakDevice:
    address = "AA:BB:CC:DD:EE:FF"


class FakeClient:
    """One BLE session. `instances` records every session so a test can see
    what happened across a reconnect."""

    instances: list["FakeClient"] = []
    # What a DEVICE_INFO read returns. None means the characteristic isn't
    # there at all - a button running firmware from before it existed. Set on
    # the class because instances are created inside the connect loop, where a
    # test cannot reach them beforehand.
    info_payload: bytes | None = FULL_INFO

    def __init__(self, device, disconnected_callback=None, **kwargs):
        self.device = device
        self._disconnected_callback = disconnected_callback
        self.writes: list[tuple[str, bytes]] = []
        self.reads: list[str] = []
        self.notify_handler = None
        self.write_fails = False
        FakeClient.instances.append(self)

    async def read_gatt_char(self, uuid):
        self.reads.append(uuid)
        if FakeClient.info_payload is None:
            raise RuntimeError("no such characteristic")
        return bytearray(FakeClient.info_payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def start_notify(self, uuid, handler):
        assert uuid == BUTTON_EVENT_UUID
        self.notify_handler = handler

    async def write_gatt_char(self, uuid, data, response=True):
        if self.write_fails:
            raise RuntimeError("link died")
        self.writes.append((uuid, bytes(data)))

    def drop(self):
        """Simulate the link going away."""
        if self._disconnected_callback:
            self._disconnected_callback(self)

    @property
    def payloads(self):
        return [data for _uuid, data in self.writes]


@pytest.fixture(autouse=True)
def fake_bleak(monkeypatch):
    FakeClient.instances = []
    FakeClient.info_payload = FULL_INFO
    found = {"device": FakeBleakDevice()}

    async def find_device_by_name(name, timeout=None):
        return found["device"]

    monkeypatch.setattr(
        ble_device.BleakScanner, "find_device_by_name", staticmethod(find_device_by_name)
    )
    monkeypatch.setattr(ble_device, "BleakClient", FakeClient)
    return found


async def _connected_device(**kwargs):
    device = ble_device.BLEDevice("AIButton", retry_s=0.01, **kwargs)
    await device.start()
    for _ in range(200):  # let the connect loop get there
        if device.connected:
            break
        await asyncio.sleep(0.005)
    assert device.connected, "never connected"
    return device


async def _settle():
    """Give the pump a few turns to drain the outbox."""
    for _ in range(20):
        await asyncio.sleep(0.005)


# --- connecting --------------------------------------------------------

async def test_connects_subscribes_and_asserts_the_led():
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        assert client.notify_handler is not None  # subscribed to gestures
        # The current LED state goes down on connect, so the device is never
        # left showing an animation from a previous session.
        assert (LED_STATE_UUID, bytes([LED_CODES[LEDState.IDLE]])) in client.writes
    finally:
        await device.close()


async def test_not_connected_until_the_link_is_up(fake_bleak):
    fake_bleak["device"] = None  # nothing in range
    device = ble_device.BLEDevice("AIButton", retry_s=0.01)
    await device.start()
    await _settle()
    assert device.connected is False
    await device.close()


# --- asking what it is -------------------------------------------------

async def test_the_device_is_asked_what_it_is_before_anything_is_sent():
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        assert DEVICE_INFO_UUID in client.reads
        assert device.info.protocol_version == fw.PROTOCOL_VERSION
        assert device.info.firmware == "%d.%d.%d" % fw.FIRMWARE_VERSION
        assert set(device.info.names) == {
            "led", "buzzer", "palette", "effect", "gesture-params",
        }
    finally:
        await device.close()


async def test_a_button_with_no_device_info_is_assumed_to_be_a_pre_v1_one():
    """Learning to ask must not silence every button that hasn't been
    reflashed - so an unreadable characteristic falls back to the capabilities
    this project's older firmware actually has."""
    FakeClient.info_payload = None
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        device.play_sound(Sound.ACK)
        await _settle()
        assert device.info.protocol_version == 0  # "these are guesses"
        assert (SOUND_CMD_UUID, sound_command(Sound.ACK)) in client.writes
    finally:
        await device.close()


async def test_no_buzzer_means_no_sound_writes():
    FakeClient.info_payload = fw.device_info_payload(fw.CAP_LED | fw.CAP_PALETTE)
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        device.play_sound(Sound.ACK)
        device.start_loop(Sound.ALARM)
        await _settle()
        assert not device.info.has(CAP_BUZZER)
        assert not [u for u, _ in client.writes if u == SOUND_CMD_UUID]
    finally:
        await device.close()


async def test_silencing_is_never_gated_even_with_no_buzzer_reported():
    """stop_loop is the safety path. A device that gained a buzzer between
    connections must not be left ringing because we decided it had none."""
    FakeClient.info_payload = fw.device_info_payload(fw.CAP_LED)
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        device.stop_loop()
        await _settle()
        assert (SOUND_CMD_UUID, bytes([STOP_LOOP_CMD])) in client.writes
    finally:
        await device.close()


async def test_no_led_means_no_palette_writes():
    from aibutton.config import LedEffect

    FakeClient.info_payload = fw.device_info_payload(fw.CAP_BUZZER)
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        device.set_palette({LEDState.IDLE.value: LedEffect("solid", "#ff0000")})
        await _settle()
        assert not device.info.has(CAP_LED)
        assert not [u for u, _ in client.writes if u == LED_PALETTE_UUID]
    finally:
        await device.close()


async def test_an_led_capable_device_still_gets_its_palette():
    from aibutton.config import LedEffect

    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        device.set_palette({LEDState.IDLE.value: LedEffect("solid", "#ff0000")})
        await _settle()
        assert device.info.has(CAP_LED) and device.info.has(CAP_PALETTE)
        assert [u for u, _ in client.writes if u == LED_PALETTE_UUID]
    finally:
        await device.close()


async def test_capabilities_are_re_asked_on_every_reconnect():
    """The thing on the other end may have been reflashed since - or be a
    different button entirely."""
    device = await _connected_device()
    try:
        FakeClient.instances[0].drop()
        for _ in range(200):
            if len(FakeClient.instances) > 1 and device.connected:
                break
            await asyncio.sleep(0.005)
        assert DEVICE_INFO_UUID in FakeClient.instances[-1].reads
    finally:
        await device.close()


# --- gestures in -------------------------------------------------------

async def test_notification_becomes_a_press():
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        client.notify_handler(None, bytearray([0x03]))  # double_tap
        assert device.events.get_nowait() is TriggerType.DOUBLE_TAP
    finally:
        await device.close()


async def test_a_parameterised_notification_becomes_a_press():
    """The other half of the wire's gesture vocabulary: a tap count arrives as
    a kind plus a parameter rather than as a code of its own."""
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        client.notify_handler(None, bytearray([GESTURE_TAP, 3]))
        assert device.events.get_nowait() is TriggerType.TRIPLE_TAP
    finally:
        await device.close()


async def test_unknown_and_empty_notifications_are_ignored():
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        client.notify_handler(None, bytearray([0x7F]))
        client.notify_handler(None, bytearray())
        client.notify_handler(None, bytearray([GESTURE_TAP, 8]))  # past our vocabulary
        client.notify_handler(None, bytearray([GESTURE_TAP]))     # no parameter
        assert device.events.empty()
    finally:
        await device.close()


# --- how far to count --------------------------------------------------

async def test_the_tap_count_is_written_on_connect():
    device = await _connected_device()
    try:
        device.set_gesture_config(3)
        await _settle()
        client = FakeClient.instances[0]
        assert (GESTURE_CONFIG_UUID, bytes([2])) in client.writes  # the default
        assert (GESTURE_CONFIG_UUID, bytes([3])) in client.writes
    finally:
        await device.close()


async def test_a_device_that_cannot_count_further_is_not_told_to():
    """Writing to a characteristic an un-reflashed button does not have would
    only log a failure. It keeps counting to two, which is what it has always
    done and what the host will therefore keep receiving."""
    FakeClient.info_payload = PRE_V1_INFO
    device = await _connected_device()
    try:
        device.set_gesture_config(3)
        await _settle()
        client = FakeClient.instances[0]
        assert not [w for w in client.writes if w[0] == GESTURE_CONFIG_UUID]
        assert device.max_taps == 3  # the host still knows what it wanted
    finally:
        await device.close()


# --- feedback out ------------------------------------------------------

async def test_feedback_reaches_the_device():
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        opening = len(client.writes)  # whatever the connect handshake sent
        device.set_led(LEDState.THINKING)
        device.play_sound(Sound.ACK)
        device.start_loop(Sound.ALARM)
        device.stop_loop()
        await _settle()
        assert client.writes[opening:] == [
            (LED_STATE_UUID, bytes([LED_CODES[LEDState.THINKING]])),
            (SOUND_CMD_UUID, sound_command(Sound.ACK)),
            (SOUND_CMD_UUID, sound_command(Sound.ALARM, loop=True)),
            (SOUND_CMD_UUID, bytes([STOP_LOOP_CMD])),
        ]
    finally:
        await device.close()


# --- showing a look nothing has a name for -----------------------------

async def test_a_one_off_look_is_pushed_without_touching_the_palette():
    """ROADMAP D4, stated as behaviour: the look goes down as an effect, and
    the stored palette entry for that state is not written at all."""
    look = _Look()
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        opening = len(client.writes)
        device.set_led(LEDState.TIMING, look)
        await _settle()
        assert client.writes[opening:] == [
            (LED_STATE_UUID, bytes([LED_CODES[LEDState.TIMING]])),
            (LED_EFFECT_UUID, effect_payload(look)),
        ]
    finally:
        await device.close()


async def test_refreshing_a_look_does_not_restate_the_led():
    """A countdown pushes a colour every few seconds. Re-sending LED_STATE
    each time would restart the state's animation on the device, so the flash
    would stutter every time the colour moved."""
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        device.set_led(LEDState.TIMING, _Look(color="#ff0000"))
        await _settle()
        opening = len(client.writes)
        device.set_led(LEDState.TIMING, _Look(color="#00ff00"))
        device.set_led(LEDState.TIMING, _Look(color="#0000ff"))
        await _settle()
        assert [uuid for uuid, _ in client.writes[opening:]] == [
            LED_EFFECT_UUID, LED_EFFECT_UUID,
        ]
    finally:
        await device.close()


async def test_a_device_without_effects_borrows_the_palette_entry_and_gives_it_back():
    """The fallback for an un-reflashed button, and the reason it lives here
    rather than in the run loop: the loop asks for a look, and whether that
    costs a borrowed palette entry is the device's business. Borrowing without
    giving back would leave the next stopwatch wearing a countdown's colour."""
    FakeClient.info_payload = PRE_V1_INFO
    configured = _Look(style="breathe", color="#00ffff", period_s=1.6)
    look = _Look(color="#ff0000")
    device = await _connected_device()
    try:
        device.set_palette({LEDState.TIMING.value: configured})
        await _settle()
        client = FakeClient.instances[0]
        opening = len(client.writes)

        device.set_led(LEDState.TIMING, look)
        await _settle()
        assert client.writes[opening:] == [
            (LED_STATE_UUID, bytes([LED_CODES[LEDState.TIMING]])),
            (LED_PALETTE_UUID, palette_payload(LEDState.TIMING, look)),
        ]

        borrowed = len(client.writes)
        device.set_led(LEDState.IDLE)  # the look ends
        await _settle()
        assert client.writes[borrowed:] == [
            (LED_STATE_UUID, bytes([LED_CODES[LEDState.IDLE]])),
            (LED_PALETTE_UUID, palette_payload(LEDState.TIMING, configured)),
        ]
    finally:
        await device.close()


async def test_reconnect_restores_a_look_in_progress():
    """A countdown that loses the link mid-sweep must not sit on the wrong
    colour until its next change - which, late in a long ramp, is minutes."""
    look = _Look(color="#ff0000")
    device = await _connected_device()
    try:
        device.set_led(LEDState.TIMING, look)
        await _settle()
        FakeClient.instances[0].drop()
        for _ in range(200):
            if len(FakeClient.instances) > 1 and device.connected:
                break
            await asyncio.sleep(0.005)
        await _settle()
        fresh = FakeClient.instances[-1]
        assert (LED_STATE_UUID, bytes([LED_CODES[LEDState.TIMING]])) in fresh.writes
        assert (LED_EFFECT_UUID, effect_payload(look)) in fresh.writes
    finally:
        await device.close()


async def test_writes_while_disconnected_are_dropped_not_queued(fake_bleak):
    # Feedback that arrives seconds late is worse than feedback that never
    # arrives: a SUCCESS flash replayed on reconnect would be a lie.
    fake_bleak["device"] = None
    device = ble_device.BLEDevice("AIButton", retry_s=0.01)
    await device.start()
    await _settle()

    device.play_sound(Sound.ACK)
    device.play_sound(Sound.ERROR)

    fake_bleak["device"] = FakeBleakDevice()
    for _ in range(200):
        if device.connected:
            break
        await asyncio.sleep(0.005)
    await _settle()
    try:
        client = FakeClient.instances[-1]
        # The LED re-assert, and no stale sounds - the two tones queued while
        # nothing was listening are gone rather than replayed on connect.
        assert (LED_STATE_UUID, bytes([LED_CODES[LEDState.IDLE]])) in client.writes
        assert not [w for w in client.writes if w[0] == SOUND_CMD_UUID]
    finally:
        await device.close()


async def test_outbox_cannot_grow_without_bound():
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        client.write_fails = True  # stall the pump's writes
        for _ in range(ble_device.OUTBOX_MAX * 3):
            device.play_sound(Sound.ACK)
        assert device._outbox.qsize() <= ble_device.OUTBOX_MAX
    finally:
        await device.close()


async def test_a_full_outbox_drops_the_oldest_write_not_the_newest():
    """OUTBOX_MAX's own reasoning ('the backlog is stale by definition') only
    holds if the newest write is the one that survives - a burst that outruns
    the pump (a repeating Morse look, TODO 83, pushes a colour every
    0.15-0.7s while each write awaits a real over-the-air response) must
    recover towards the current colour once the link catches up, not keep
    delivering whichever ancient ones happened to queue first."""
    device = await _connected_device()
    try:
        client = FakeClient.instances[0]
        client.write_fails = True  # stall the pump so nothing drains
        newest = ble_device.OUTBOX_MAX + 5
        for i in range(newest + 1):
            device.set_led(LEDState.TIMING, _Look(color=f"#{i:06x}"))
        survivors = []
        with contextlib.suppress(asyncio.QueueEmpty):
            while True:
                survivors.append(device._outbox.get_nowait())
        assert len(survivors) == ble_device.OUTBOX_MAX
        assert survivors[-1] == (
            LED_EFFECT_UUID, effect_payload(_Look(color=f"#{newest:06x}")),
        )
    finally:
        await device.close()


# --- losing the link ---------------------------------------------------

async def test_reconnects_after_the_link_drops():
    device = await _connected_device()
    try:
        first = FakeClient.instances[0]
        assert device.connected
        first.drop()
        for _ in range(200):  # a second session appears on its own
            if len(FakeClient.instances) > 1 and device.connected:
                break
            await asyncio.sleep(0.005)
        assert len(FakeClient.instances) > 1, "did not reconnect"
        assert device.connected
    finally:
        await device.close()


async def test_reconnect_restores_the_current_led_state():
    device = await _connected_device()
    try:
        device.set_led(LEDState.TIMING)  # a stopwatch is running
        await _settle()
        FakeClient.instances[0].drop()
        for _ in range(200):
            if len(FakeClient.instances) > 1 and device.connected:
                break
            await asyncio.sleep(0.005)
        # The new session opens on TIMING, not on IDLE: the host still
        # believes a stopwatch is running, and the LED should say so.
        second = FakeClient.instances[-1]
        assert (LED_STATE_UUID, bytes([LED_CODES[LEDState.TIMING]])) in second.writes
        assert (LED_STATE_UUID, bytes([LED_CODES[LEDState.IDLE]])) not in second.writes
    finally:
        await device.close()


async def test_a_failing_write_does_not_kill_the_loop():
    device = await _connected_device()
    try:
        FakeClient.instances[0].write_fails = True
        device.play_sound(Sound.ACK)
        for _ in range(200):
            if len(FakeClient.instances) > 1:
                break
            await asyncio.sleep(0.005)
        assert len(FakeClient.instances) > 1, "a dead write ended the session for good"
    finally:
        await device.close()


# --- shutdown ----------------------------------------------------------

async def test_close_silences_a_ringing_alarm():
    device = await _connected_device()
    client = FakeClient.instances[0]
    device.start_loop(Sound.ALARM)
    await _settle()
    await device.close()
    # The stop goes out directly, not through the outbox the close is about
    # to cancel - a host exiting mid-alarm must not leave the buzzer ringing.
    assert client.writes[-1] == (SOUND_CMD_UUID, bytes([STOP_LOOP_CMD]))
    assert device._task is None


async def test_close_is_safe_when_never_connected(fake_bleak):
    fake_bleak["device"] = None
    device = ble_device.BLEDevice("AIButton", retry_s=0.01)
    await device.start()
    await _settle()
    await device.close()  # must not raise


async def test_close_before_start_is_safe():
    device = ble_device.BLEDevice("AIButton")
    await device.close()
