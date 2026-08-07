"""The feedback tones, as WAVs the browser can play.

The buzzer is on the ESP32 and the host never drives a speaker. What it
still does is *synthesize* the tones, so the web UI's virtual device plays
exactly what the buzzer would - which is only true while this table and
firmware/tones.py agree, so a test compares them.

No binary assets: the tables below are the tones, written to a temp
directory at startup (~100 KB) and served by /api/dev/sound/{name}.
"""

from __future__ import annotations

import logging
import math
import shutil
import struct
import tempfile
import wave
from pathlib import Path

from .device import Sound

log = logging.getLogger(__name__)

_RATE = 22050
_VOLUME = 0.4
_RAMP_S = 0.005  # fade edges to avoid clicks


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


class ToneLibrary:
    """The synthesized tones on disk; close() removes them."""

    def __init__(self) -> None:
        self._dir: Path | None = Path(tempfile.mkdtemp(prefix="aibutton-sounds-"))
        self._paths: dict[Sound, Path] = {}
        for sound, segments in _TONES.items():
            path = self._dir / f"{sound.value}.wav"
            write_tone_wav(path, segments)
            self._paths[sound] = path

    def path_for(self, sound: Sound) -> Path | None:
        """WAV file path for a sound (the web UI serves these)."""
        return self._paths.get(sound)

    def close(self) -> None:
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None
