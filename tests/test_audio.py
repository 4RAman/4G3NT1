import asyncio
import wave

from aibutton.audio import _TONES, Sound, SoundPlayer, write_tone_wav


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


async def test_player_noops_without_aplay_or_when_disabled(monkeypatch):
    monkeypatch.setattr("aibutton.audio.shutil.which", lambda _: None)
    player = SoundPlayer(enabled=True)
    player.play(Sound.ACK)  # must not raise
    player.close()

    disabled = SoundPlayer(enabled=False)
    disabled.play(Sound.ERROR)
    disabled.close()


def test_wavs_synthesized_even_without_aplay(monkeypatch):
    # the web UI serves these for browser playback, aplay or not
    monkeypatch.setattr("aibutton.audio.shutil.which", lambda _: None)
    player = SoundPlayer(enabled=True)
    for sound in Sound:
        path = player.path_for(sound)
        assert path is not None and path.exists()
    player.close()
    assert not player.path_for(Sound.ACK).exists()  # cleaned up


async def test_start_loop_noop_when_disabled(monkeypatch):
    monkeypatch.setattr("aibutton.audio.shutil.which", lambda _: None)
    player = SoundPlayer(enabled=True)  # aplay missing -> disabled
    player.start_loop(Sound.ALARM)
    assert player._loop_task is None
    player.close()


async def test_start_loop_repeats_until_stopped(monkeypatch):
    monkeypatch.setattr("aibutton.audio._ALARM_LOOP_GAP_S", 0.001)
    player = SoundPlayer(enabled=True)
    player._enabled = True  # force on regardless of aplay availability

    played = []

    async def fake_play(sound):
        played.append(sound)

    monkeypatch.setattr(player, "_play", fake_play)

    player.start_loop(Sound.ALARM)
    await asyncio.sleep(0.05)
    assert len(played) > 1
    assert all(s == Sound.ALARM for s in played)

    player.stop_loop()
    count = len(played)
    await asyncio.sleep(0.05)
    assert len(played) == count  # no more plays once stopped

    player.close()


async def test_start_loop_replaces_running_loop(monkeypatch):
    monkeypatch.setattr("aibutton.audio._ALARM_LOOP_GAP_S", 0.001)
    player = SoundPlayer(enabled=True)
    player._enabled = True

    played = []

    async def fake_play(sound):
        played.append(sound)

    monkeypatch.setattr(player, "_play", fake_play)

    player.start_loop(Sound.ALARM)
    await asyncio.sleep(0.02)
    first_task = player._loop_task

    player.start_loop(Sound.ACK)
    assert player._loop_task is not first_task
    await asyncio.sleep(0.02)
    assert Sound.ACK in played

    player.close()


async def test_close_stops_loop(monkeypatch):
    monkeypatch.setattr("aibutton.audio._ALARM_LOOP_GAP_S", 0.001)
    player = SoundPlayer(enabled=True)
    player._enabled = True
    monkeypatch.setattr(player, "_play", lambda sound: asyncio.sleep(0))

    player.start_loop(Sound.ALARM)
    await asyncio.sleep(0.01)
    player.close()
    assert player._loop_task is None
