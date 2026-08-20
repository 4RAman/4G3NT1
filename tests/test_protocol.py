"""The host/firmware protocol tables are one contract in two files.

aibutton/device.py can't import firmware/protocol.py at runtime (that file
ships to the ESP32 and the host has no business depending on it), so this
is what keeps them honest: it imports both halves and compares them
member by member. A code changed on one side and not the other fails here
rather than on the wire.
"""

import protocol as fw  # firmware/protocol.py - see conftest.py

from aibutton import device


def test_uuids_match():
    assert device.SERVICE_UUID == fw.SERVICE_UUID
    assert device.BUTTON_EVENT_UUID == fw.BUTTON_EVENT_UUID
    assert device.LED_STATE_UUID == fw.LED_STATE_UUID
    assert device.SOUND_CMD_UUID == fw.SOUND_CMD_UUID
    assert device.LED_PALETTE_UUID == fw.LED_PALETTE_UUID
    assert device.DEVICE_INFO_UUID == fw.DEVICE_INFO_UUID
    assert device.OTA_CONTROL_UUID == fw.OTA_CONTROL_UUID
    assert device.LED_EFFECT_UUID == fw.LED_EFFECT_UUID
    assert device.GESTURE_CONFIG_UUID == fw.GESTURE_CONFIG_UUID


def test_uuids_are_distinct_and_share_the_project_base():
    uuids = [
        fw.SERVICE_UUID, fw.BUTTON_EVENT_UUID, fw.LED_STATE_UUID,
        fw.SOUND_CMD_UUID, fw.LED_PALETTE_UUID, fw.DEVICE_INFO_UUID,
        fw.OTA_CONTROL_UUID, fw.LED_EFFECT_UUID, fw.GESTURE_CONFIG_UUID,
    ]
    assert len(set(uuids)) == 9
    assert all(u.endswith("-00b0-4240-ba50-05ca45bf8abc") for u in uuids)


# --- device info -------------------------------------------------------

def test_protocol_version_matches():
    """Both sides have to agree on what version 1 *means*, so this one is
    mirrored. The firmware's own version deliberately is not - the host reads
    it off the device."""
    assert device.PROTOCOL_VERSION == fw.PROTOCOL_VERSION


def test_capability_bits_match():
    for name in (
        "CAP_LED", "CAP_BUZZER", "CAP_PALETTE", "CAP_HAPTICS",
        "CAP_BATTERY", "CAP_IMU", "CAP_MIC", "CAP_OTA",
        "CAP_EFFECT", "CAP_GESTURE_PARAMS",
    ):
        assert getattr(device, name) == getattr(fw, name), name


def test_every_capability_bit_is_distinct_and_named():
    bits = list(device.CAPABILITY_NAMES)
    assert len(set(bits)) == len(bits)
    # Each is a single bit: an overlapping mask would make two features
    # indistinguishable on the wire.
    assert all(bit and not (bit & (bit - 1)) for bit in bits)


def test_host_decodes_what_the_firmware_reports():
    caps = fw.CAP_LED | fw.CAP_BUZZER | fw.CAP_PALETTE
    payload = fw.device_info_payload(caps, firmware=(1, 2, 3))
    assert len(payload) == fw.DEVICE_INFO_LEN

    info = device.decode_device_info(payload)
    assert info.protocol_version == fw.PROTOCOL_VERSION
    assert info.firmware_version == (1, 2, 3)
    assert info.firmware == "1.2.3"
    assert set(info.names) == {"led", "buzzer", "palette"}
    assert info.has(device.CAP_LED) and not info.has(device.CAP_IMU)


def test_a_device_reporting_no_buzzer_says_so():
    payload = fw.device_info_payload(fw.CAP_LED | fw.CAP_PALETTE)
    info = device.decode_device_info(payload)
    assert info.has(device.CAP_LED)
    assert not info.has(device.CAP_BUZZER)


def test_a_short_device_info_is_rejected_rather_than_half_read():
    assert device.decode_device_info(b"\x01\x00\x04") is None
    assert device.decode_device_info(b"") is None
    assert device.decode_device_info(None) is None


def test_trailing_bytes_are_ignored_so_the_format_can_grow():
    """The format grows by appending. An older host must stay able to read a
    newer device - that is the half of forward compatibility the host owns,
    and the reason DEVICE_INFO exists before more hardware does."""
    payload = fw.device_info_payload(fw.CAP_LED) + b"\x99\x88\x77"
    info = device.decode_device_info(payload)
    assert info is not None
    assert info.firmware_version == fw.FIRMWARE_VERSION
    assert info.has(device.CAP_LED)


def test_the_assumed_info_keeps_an_un_reflashed_button_working():
    """A button with no DEVICE_INFO is this project's own older firmware,
    which has all three. Assuming less would silence every button that hasn't
    been reflashed the moment the host learns to ask."""
    assert device.ASSUMED_INFO.protocol_version == 0  # "these are guesses"
    for cap in (device.CAP_LED, device.CAP_BUZZER, device.CAP_PALETTE):
        assert device.ASSUMED_INFO.has(cap)


def test_gesture_codes_match():
    assert {t.value: c for t, c in device.GESTURE_CODES.items()} == fw.GESTURE_CODES


def test_gesture_kinds_match():
    assert device.GESTURE_TAP == fw.GESTURE_TAP
    assert device.GESTURE_HOLD == fw.GESTURE_HOLD
    # A kind byte and a legacy code must never collide, or a two-byte notify
    # would be readable as a one-byte one.
    assert not set(fw.GESTURE_CODES.values()) & {fw.GESTURE_TAP, fw.GESTURE_HOLD}


def test_the_classic_three_still_travel_as_one_byte():
    """The whole compatibility bet. A host that only understands one-byte
    notifies keeps working, because the gestures it knows about are still sent
    the way it has always received them - parameterised codes are additions,
    not replacements."""
    for name in ("short_press", "long_press", "double_tap"):
        assert fw.gesture_payload(name) == bytes([fw.GESTURE_CODES[name]])


def test_a_longer_tap_travels_as_a_kind_plus_a_count():
    assert fw.gesture_payload("triple_tap") == bytes([fw.GESTURE_TAP, 3])
    assert fw.gesture_payload("tap_4") == bytes([fw.GESTURE_TAP, 4])
    assert fw.gesture_payload("tap_5") == bytes([fw.GESTURE_TAP, 5])


def test_the_host_reads_a_pre_v1_button():
    """One-byte notifies are what an un-reflashed button sends, and the host
    is the half that has to keep understanding them - it is the half that is
    easy to update."""
    for trigger, code in device.GESTURE_CODES.items():
        assert device.decode_gesture(bytes([code])) is trigger


def test_a_gesture_the_host_cannot_name_is_dropped_rather_than_guessed():
    # A tap count past the host's vocabulary, a reserved kind, a truncated
    # parameterised notify, and nothing at all.
    assert device.decode_gesture(bytes([fw.GESTURE_TAP, 7])) is None
    assert device.decode_gesture(bytes([fw.GESTURE_HOLD, 2])) is None
    assert device.decode_gesture(bytes([fw.GESTURE_TAP])) is None
    assert device.decode_gesture(b"\x99") is None
    assert device.decode_gesture(b"") is None
    assert device.decode_gesture(None) is None


def test_every_gesture_survives_the_round_trip():
    """A gesture the host can name must be one the firmware can send and the
    host can read back.

    This replaced "every enum member has a code", and had to: since v1 not
    every gesture *has* a code. A tap count past two travels as a kind plus a
    parameter, so what matters is that the encoding round-trips, not that a
    byte was allocated.
    """
    for trigger in device.TriggerType:
        payload = fw.gesture_payload(trigger.value)
        assert payload is not None, trigger
        assert device.decode_gesture(payload) is trigger


def test_the_host_vocabulary_fits_inside_what_the_wire_will_carry():
    assert device.MAX_TAPS <= fw.MAX_TAPS_LIMIT
    assert device.DEFAULT_MAX_TAPS == fw.DEFAULT_MAX_TAPS
    for count, trigger in device.TAP_TRIGGERS.items():
        assert fw.TAP_NAMES[count] == trigger.value


# --- gesture config ----------------------------------------------------

def test_the_device_reads_the_tap_count_the_host_asks_for():
    for count in range(device.DEFAULT_MAX_TAPS, device.MAX_TAPS + 1):
        payload = device.gesture_config_payload(count)
        assert fw.decode_gesture_config(payload) == count


def test_an_impossible_tap_count_is_clamped_at_both_ends():
    """Clamped rather than rejected, on both sides: a host asking for
    something out of range should get the nearest thing that works, not a
    detector that silently kept its old setting."""
    assert fw.decode_gesture_config(bytes([0])) == fw.DEFAULT_MAX_TAPS
    assert fw.decode_gesture_config(bytes([250])) == fw.MAX_TAPS_LIMIT
    assert fw.decode_gesture_config(b"") is None
    assert device.gesture_config_payload(1) == bytes([device.DEFAULT_MAX_TAPS])
    assert device.gesture_config_payload(99) == bytes([device.MAX_TAPS])


def test_max_taps_is_derived_from_what_is_actually_bound():
    """Counting past two costs a double tap its instant response, so the
    number follows the bindings rather than being a setting."""
    T = device.TriggerType
    assert device.max_taps_for([]) == 2
    assert device.max_taps_for([T.SHORT_PRESS, T.LONG_PRESS]) == 2
    assert device.max_taps_for([T.DOUBLE_TAP]) == 2
    assert device.max_taps_for([T.SHORT_PRESS, T.TRIPLE_TAP]) == 3
    assert device.max_taps_for([T.TAP_4]) == 4


def test_led_codes_match():
    assert {s.value: c for s, c in device.LED_CODES.items()} == fw.LED_CODES


def test_sound_codes_match():
    assert {s.value: c for s, c in device.SOUND_CODES.items()} == fw.SOUND_CODES


def test_loop_flag_matches():
    assert device.LOOP_FLAG == fw.LOOP
    assert device.STOP_LOOP_CMD == fw.STOP_LOOP


def test_every_enum_member_has_a_code():
    # A new LEDState or Sound without a code would be unsendable. Gestures are
    # no longer in this list - see test_every_gesture_survives_the_round_trip,
    # which is the stronger check that replaced it.
    assert set(device.LED_CODES) == set(device.LEDState)
    assert set(device.SOUND_CODES) == set(device.Sound)


def test_codes_are_unique_within_each_table():
    for table in (device.GESTURE_CODES, device.LED_CODES, device.SOUND_CODES):
        assert len(set(table.values())) == len(table)


def test_sound_codes_leave_room_for_the_loop_flag():
    # The command byte is `code | LOOP`, so a code must not collide with it.
    assert all(code & fw.LOOP == 0 for code in device.SOUND_CODES.values())
    assert all(code != fw.STOP_LOOP for code in device.SOUND_CODES.values())


def test_host_encodes_what_the_firmware_decodes():
    for sound, code in device.SOUND_CODES.items():
        once = device.sound_command(sound)
        assert fw.decode_sound(once[0]) == (code, False)
        looped = device.sound_command(sound, loop=True)
        assert fw.decode_sound(looped[0]) == (code, True)
    assert fw.decode_sound(device.STOP_LOOP_CMD) == (None, False)


# --- LED palette -------------------------------------------------------

def test_style_codes_match():
    assert device.LED_STYLE_CODES == fw.STYLE_CODES


def test_palette_entry_survives_the_round_trip():
    from aibutton.config import LedEffect

    effect = LedEffect(style="alternate", color="#ff8800", color2="#0044ff", period_s=2.5)
    payload = device.palette_payload(device.LEDState.ALERT, effect)
    assert len(payload) == fw.PALETTE_ENTRY_LEN

    led_code, style, color, color2, period_s = fw.decode_palette_entry(payload)
    assert led_code == device.LED_CODES[device.LEDState.ALERT]
    assert style == fw.STYLE_ALTERNATE
    assert color == (0xFF, 0x88, 0x00)
    assert color2 == (0x00, 0x44, 0xFF)
    assert period_s == 2.5


def test_every_default_palette_entry_encodes():
    from aibutton.config import AppConfig

    for name, effect in AppConfig().led_palette.items():
        state = device.LEDState(name)
        decoded = fw.decode_palette_entry(device.palette_payload(state, effect))
        assert decoded is not None
        assert decoded[0] == device.LED_CODES[state]
        assert decoded[1] == fw.STYLE_CODES[effect.style]


def test_short_palette_writes_are_rejected():
    # A truncated write must leave the palette alone rather than render
    # whatever the missing bytes would have been.
    assert fw.decode_palette_entry(b"\x01\x02\x03") is None
    assert fw.decode_palette_entry(b"") is None
    assert fw.decode_palette_entry(None) is None


def test_period_is_clamped_to_what_two_bytes_can_carry():
    from aibutton.config import LedEffect

    huge = device.palette_payload(
        device.LEDState.IDLE, LedEffect("breathe", "#ffffff", period_s=10_000)
    )
    assert fw.decode_palette_entry(huge)[4] == 655.35  # the ceiling, not a wrap
    tiny = device.palette_payload(
        device.LEDState.IDLE, LedEffect("breathe", "#ffffff", period_s=0.0001)
    )
    assert fw.decode_palette_entry(tiny)[4] > 0  # never zero: it divides periods


def test_unparseable_colour_encodes_as_black_rather_than_raising():
    from aibutton.config import LedEffect

    payload = device.palette_payload(
        device.LEDState.IDLE, LedEffect("solid", "not-a-colour")
    )
    assert fw.decode_palette_entry(payload)[2] == (0, 0, 0)


# --- ephemeral effects -------------------------------------------------

def test_an_ephemeral_effect_survives_the_round_trip():
    from aibutton.config import LedEffect

    effect = LedEffect(style="fade", color="#112233", color2="#445566", period_s=1.25)
    payload = device.effect_payload(effect)
    assert len(payload) == fw.EFFECT_LEN

    style, color, color2, period_s = fw.decode_effect(payload)
    assert style == fw.STYLE_FADE
    assert color == (0x11, 0x22, 0x33)
    assert color2 == (0x44, 0x55, 0x66)
    assert period_s == 1.25


def test_a_palette_entry_is_a_state_byte_then_exactly_an_effect():
    """One layout, defined once. If the two ever disagreed about where the
    period sits, a palette write and an effect write would render differently
    from the same nine bytes."""
    from aibutton.config import LedEffect

    effect = LedEffect(style="flash", color="#ff0000", period_s=0.5)
    entry = device.palette_payload(device.LEDState.ALERT, effect)
    assert entry[0] == device.LED_CODES[device.LEDState.ALERT]
    assert entry[1:] == device.effect_payload(effect)
    assert fw.decode_palette_entry(entry)[1:] == fw.decode_effect(entry, 1)


def test_a_short_effect_write_is_rejected_rather_than_half_read():
    assert fw.decode_effect(b"\x01\x02\x03") is None
    assert fw.decode_effect(b"") is None
    assert fw.decode_effect(None) is None


def test_an_effect_costs_no_led_state_code():
    """The point of the whole thing (ROADMAP D4): a one-off look is a write,
    not a byte out of a 255-value namespace that is mirrored four ways."""
    assert fw.EFFECT_LEN == fw.PALETTE_ENTRY_LEN - 1
    assert max(device.LED_CODES.values()) == 0x0B  # unchanged by this revision
