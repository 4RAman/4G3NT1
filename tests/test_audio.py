import wave

from aibutton.audio import _TONES, ToneLibrary, write_tone_wav
from aibutton.device import Sound


def test_all_tones_produce_valid_wavs(tmp_path):
    for sound, segments in _TONES.items():
        path = tmp_path / f"{sound.value}.wav"
        write_tone_wav(path, segments)
        with wave.open(str(path), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getnframes() > 0
            expected_ms = sum(ms for _, ms in segments)
            actual_ms = w.getnframes() / w.getframerate() * 1000
            assert abs(actual_ms - expected_ms) < 5


def test_every_sound_command_has_a_tone():
    # The web UI serves one WAV per Sound; a new command without a tone
    # would 404 the virtual device panel instead of failing loudly here.
    assert set(_TONES) == set(Sound)


def test_library_writes_and_cleans_up_every_wav():
    tones = ToneLibrary()
    paths = [tones.path_for(sound) for sound in Sound]
    assert all(p is not None and p.exists() for p in paths)
    tones.close()
    assert not any(p.exists() for p in paths)
    tones.close()  # idempotent
