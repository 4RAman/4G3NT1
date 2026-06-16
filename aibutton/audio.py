"""Feedback sounds: ack chirp, success/error tones, alarm pattern.

No binary assets - tones are synthesized with the stdlib `wave` module
into a temp directory at startup and played fire-and-forget through
ALSA's `aplay`. On machines without aplay (Windows dev box) or with
sounds_enabled=false, every call is a silent no-op.

Hardware (optional, ~$3-4): PAM8302-class amp + mini speaker on the
Pi's 3.5 mm jack - zero GPIO cost, see SETUP.md. The ALARM tone is used
both as a one-shot (play) and, via start_loop/stop_loop, repeated until
a ringing alarm mode is dismissed or snoozed.
"""

from __future__ import annotations

import asyncio
import logging
import math
import shutil
import struct
import tempfile
import wave
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

_RATE = 22050
_VOLUME = 0.4
_RAMP_S = 0.005  # fade edges to avoid clicks
_ALARM_LOOP_GAP_S = 1.0  # pause between repeats while an alarm is ringing


class Sound(Enum):
    ACK = "ack"
    SUCCESS = "success"
    ERROR = "error"
    ALARM = "alarm"


# (frequency_hz, duration_ms) segments; frequency 0 = silence
_TONES: dict[Sound, tuple[tuple[int, int], ...]] = {
    Sound.ACK: ((880, 70),),
    Sound.SUCCESS: ((660, 90), (990, 160)),
    Sound.ERROR: ((220, 130), (0, 70), (220, 130), (0, 70), (220, 200)),
    Sound.ALARM: ((988, 160), (0, 90), (988, 160), (0, 90), (784, 300)),
}


def synth_frames(segments: tuple[tuple[int, int], ...]) -> bytes:
    """16-bit mono PCM for a sequence of (hz, ms) segments."""
    frames = bytearray()
    for freq, ms in segments:
        n = int(_RATE * ms / 1000)
        ramp = min(int(_RATE * _RAMP_S), max(n // 2, 1))
        for i in range(n):
            if freq == 0:
                sample = 0.0
            else:
                sample = math.sin(2 * math.pi * freq * i / _RATE)
                if i < ramp:
                    sample *= i / ramp
                elif i >= n - ramp:
                    sample *= (n - i) / ramp
            frames += struct.pack("<h", int(sample * _VOLUME * 32767))
    return bytes(frames)


def write_tone_wav(path: Path, segments: tuple[tuple[int, int], ...]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes(synth_frames(segments))


class SoundPlayer:
    def __init__(self, enabled: bool = True):
        # WAVs are always synthesized (~100 KB total): the web UI's
        # virtual device fetches and plays them in the browser even on
        # machines without aplay. `enabled` only gates local playback.
        self._dir: Path | None = Path(tempfile.mkdtemp(prefix="aibutton-sounds-"))
        self._paths: dict[Sound, Path] = {}
        for sound, segments in _TONES.items():
            path = self._dir / f"{sound.value}.wav"
            write_tone_wav(path, segments)
            self._paths[sound] = path
        self._enabled = enabled and shutil.which("aplay") is not None
        if enabled and not self._enabled:
            log.info("aplay not found - local sound playback disabled")
        self._loop_task: asyncio.Task | None = None

    def path_for(self, sound: Sound) -> Path | None:
        """WAV file path for a sound (web UI serves these)."""
        return self._paths.get(sound)

    def play(self, sound: Sound) -> None:
        """Fire-and-forget; never blocks the event loop."""
        if not self._enabled:
            return
        asyncio.get_running_loop().create_task(self._play(sound))

    async def _play(self, sound: Sound) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "aplay", "-q", str(self._paths[sound]),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except OSError as exc:
            log.warning("sound playback failed: %s", exc)

    def start_loop(self, sound: Sound) -> None:
        """Repeat `sound` with a brief pause until stop_loop() - used by an
        alarm mode to ring until the next button press dismisses or
        snoozes it. Replaces any loop already running."""
        self.stop_loop()
        if not self._enabled:
            return
        self._loop_task = asyncio.get_running_loop().create_task(self._loop(sound))

    def stop_loop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None

    async def _loop(self, sound: Sound) -> None:
        try:
            while True:
                await self._play(sound)
                await asyncio.sleep(_ALARM_LOOP_GAP_S)
        except asyncio.CancelledError:
            pass

    def close(self) -> None:
        self.stop_loop()
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None
        self._enabled = False
