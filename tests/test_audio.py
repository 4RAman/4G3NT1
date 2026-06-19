import asyncio
import wave

from aibutton.audio import _TONES, _VARIANTS, Sound, SoundPlayer, write_tone_wav


def test_every_sound_has_a_tone():
    # The sound bank and the Sound enum stay in sync.
    assert set(_TONES) == set(Sound)


def test_round_robin_serves_distinct_variants(monkeypatch):
    monkeypatch.setattr("aibutton.audio.shutil.which", lambda _: None)
    player = SoundPlayer(enabled=True)
    paths = player._paths[Sound.ACK]
    assert len(paths) == _VARIANTS
    # variant 0 is the base tone the web UI serves; variants differ on disk
    assert player.path_for(Sound.ACK) == paths[0]
    sizes = {p.stat().st_size for p in paths}
    assert len(sizes) > 1  # jitter makes lengths differ
    # _next_variant cycles through the whole bank, then wraps
    served = [player._next_variant(Sound.ACK) for _ in range(_VARIANTS + 1)]
    assert served[:_VARIANTS] == paths
    assert served[_VARIANTS] == paths[0]
    player.close()


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
