# The feedback tones, as (frequency_hz, duration_ms) segments; 0 Hz is silence.
#
# Data only, no hardware - buzzer.py plays these on a PWM pin, and the host
# synthesizes the same tables into WAVs (aibutton/audio.py) so the web UI's
# virtual device plays exactly what the buzzer does. tests/test_tones.py
# fails if the two tables drift.
#
# Keyed by the protocol's sound codes, so a SOUND_CMD byte indexes straight
# into this table.

from protocol import SOUND_ACK, SOUND_ALARM, SOUND_ERROR, SOUND_SUCCESS

TONES = {
    SOUND_ACK: ((880, 70),),
    SOUND_SUCCESS: ((660, 90), (990, 160)),
    SOUND_ERROR: ((220, 130), (0, 70), (220, 130), (0, 70), (220, 200)),
    SOUND_ALARM: ((988, 160), (0, 90), (988, 160), (0, 90), (784, 300)),
}

# Pause between repeats while a sound is looping (a ringing alarm).
LOOP_GAP_MS = 1000
