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


def test_uuids_are_distinct_and_share_the_project_base():
    uuids = [
        fw.SERVICE_UUID, fw.BUTTON_EVENT_UUID, fw.LED_STATE_UUID,
        fw.SOUND_CMD_UUID, fw.LED_PALETTE_UUID,
    ]
    assert len(set(uuids)) == 5
    assert all(u.endswith("-00b0-4240-ba50-05ca45bf8abc") for u in uuids)


def test_gesture_codes_match():
    assert {t.value: c for t, c in device.GESTURE_CODES.items()} == fw.GESTURE_CODES


def test_led_codes_match():
    assert {s.value: c for s, c in device.LED_CODES.items()} == fw.LED_CODES


def test_sound_codes_match():
    assert {s.value: c for s, c in device.SOUND_CODES.items()} == fw.SOUND_CODES


def test_loop_flag_matches():
    assert device.LOOP_FLAG == fw.LOOP
    assert device.STOP_LOOP_CMD == fw.STOP_LOOP


def test_every_enum_member_has_a_code():
    # A new LEDState or Sound without a code would be unsendable.
    assert set(device.GESTURE_CODES) == set(device.TriggerType)
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
