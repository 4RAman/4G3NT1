"""Feedback sounds: ack chirp, success/error tones, alarm, wake/sleep, phase.

No binary assets - tones are synthesized with the stdlib `wave` module
into a temp directory at startup and played fire-and-forget through
ALSA's `aplay`. On machines without aplay (Windows dev box) or with
sounds_enabled=false, every call is a silent no-op.

Sound design (see the "Smart Button Sound Design Research" doc): each cue
is built from a musical interval whose emotional valence matches the event
- a *rising* perfect 5th says "success", a *falling* tritone says "denied",
a rising root-5th-octave arpeggio is "waking up", its inverse is "sleep".
Tones sit in the upper-mid "sweet" register (pure-ish sines, gently decaying
like an analog ping) rather than flat buzzes. To dodge the "machine gun
effect" - the listener fatigue of one identical sample on repeat - each cue
is pre-rendered as a small bank of micro-varied WAVs (tiny pitch/length
jitter) that play round-robin, the sample-based stand-in for the generative
micro-variation the eventual ESP32 synth will do live.

Hardware (optional, ~$3-4): PAM8302-class amp + mini speaker on the
Pi's 3.5 mm jack - zero GPIO cost, see SETUP.md. The ALARM tone is used
both as a one-shot (play) and, via start_loop/stop_loop, repeated until
a ringing alarm mode is dismissed or snoozed.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
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
# Each non-silent note decays a little across its length - a soft "ping"
# instead of a flat organ tone, which reads as warmer / less fatiguing.
_DECAY_K = 0.9
# Round-robin micro-variation: how many slightly-different renders per cue,
# and how far each may drift in pitch (cents) and length (ms).
_VARIANTS = 5
_PITCH_JITTER_CENTS = 12.0
_LENGTH_JITTER_MS = 4.0

# Base note for melodic cues: A5, an upper-mid "sweet" register that suggests
# a small, non-threatening resonator (the doc's auditory-cuteness markers).
_BASE_HZ = 880.0


def _note(semitones: float, base: float = _BASE_HZ) -> int:
    """Frequency of `semitones` above (or below) the base note."""
    return int(round(base * 2 ** (semitones / 12)))


class Sound(Enum):
    ACK = "ack"          # a press registered
    SUCCESS = "success"  # action succeeded
    ERROR = "error"      # action failed / no mode matched
    ALARM = "alarm"      # a ringing alarm (loops)
    WAKE = "wake"        # device turned on (5-tap wake)
    SLEEP = "sleep"      # device turned off (5-tap sleep)
    PHASE = "phase"      # a Pomodoro phase change (work <-> break)


# (frequency_hz, duration_ms) segments; frequency 0 = silence. Built from
# intervals so the emotional reading is intentional, not arbitrary.
_TONES: dict[Sound, tuple[tuple[int, int], ...]] = {
    # Single bright high click - instant, gets out of the way.
    Sound.ACK: ((1568, 70),),
    # Rising perfect 5th - bright, "yes".
    Sound.SUCCESS: ((_note(0), 90), (_note(7), 150)),
    # Falling tritone into a low note, with an "uh-oh" stutter - "no".
    Sound.ERROR: ((622, 130), (0, 40), (440, 260)),
    # Oscillating minor 2nd - dissonant, urgent (loops until dismissed).
    Sound.ALARM: ((988, 180), (0, 60), (932, 180), (0, 60), (988, 300)),
    # Rising root-5th-octave arpeggio - "powering up".
    Sound.WAKE: ((_note(0), 90), (_note(7), 90), (_note(12), 200)),
    # Falling octave-m3-root arpeggio - "powering down".
    Sound.SLEEP: ((_note(12), 130), (_note(3), 140), (_note(0), 280)),
    # Rising perfect 4th - stable "progress / next phase".
    Sound.PHASE: ((_note(0), 110), (_note(5), 200)),
}


def synth_frames(segments: tuple[tuple[int, int], ...]) -> bytes:
    """16-bit mono PCM for a sequence of (hz, ms) segments. Each note gets
    edge ramps (anti-click) plus a gentle exponential body decay (the soft
    analog "ping" the sound research calls for)."""
    frames = bytearray()
    for freq, ms in segments:
        n = int(_RATE * ms / 1000)
        ramp = min(int(_RATE * _RAMP_S), max(n // 2, 1))
        for i in range(n):
            if freq == 0:
                sample = 0.0
            else:
                sample = math.sin(2 * math.pi * freq * i / _RATE)
                sample *= math.exp(-_DECAY_K * i / n)  # ping decay
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


def _vary(
    segments: tuple[tuple[int, int], ...], rng: random.Random
) -> tuple[tuple[int, int], ...]:
    """A micro-varied copy of `segments`: each note nudged a few cents in
    pitch and a couple ms in length. Silences are left untouched."""
    out = []
    for freq, ms in segments:
        if freq == 0:
            out.append((freq, ms))
            continue
        cents = rng.uniform(-_PITCH_JITTER_CENTS, _PITCH_JITTER_CENTS)
        dms = rng.uniform(-_LENGTH_JITTER_MS, _LENGTH_JITTER_MS)
        out.append((int(round(freq * 2 ** (cents / 1200))), max(20, int(ms + dms))))
    return tuple(out)


class SoundPlayer:
    def __init__(self, enabled: bool = True):
        # WAVs are always synthesized (~100 KB total): the web UI's
        # virtual device fetches and plays them in the browser even on
        # machines without aplay. `enabled` only gates local playback.
        self._dir: Path | None = Path(tempfile.mkdtemp(prefix="aibutton-sounds-"))
        # A small round-robin bank of micro-varied renders per cue. Variant 0
        # is the exact base tone (what path_for / the web UI serves); the rest
        # are jittered so repeated presses never sound identical.
        self._paths: dict[Sound, list[Path]] = {}
        self._rr: dict[Sound, int] = {}
        rng = random.Random(0xA1B)  # fixed seed: stable across restarts
        for sound, segments in _TONES.items():
            paths: list[Path] = []
            for v in range(_VARIANTS):
                variant = segments if v == 0 else _vary(segments, rng)
                path = self._dir / f"{sound.value}.{v}.wav"
                write_tone_wav(path, variant)
                paths.append(path)
            self._paths[sound] = paths
            self._rr[sound] = 0
        self._enabled = enabled and shutil.which("aplay") is not None
        if enabled and not self._enabled:
            log.info("aplay not found - local sound playback disabled")
        self._loop_task: asyncio.Task | None = None

    def path_for(self, sound: Sound) -> Path | None:
        """Representative WAV file path for a sound (web UI serves these) -
        the base, un-jittered variant 0."""
        paths = self._paths.get(sound)
        return paths[0] if paths else None

    def play(self, sound: Sound) -> None:
        """Fire-and-forget; never blocks the event loop."""
        if not self._enabled:
            return
        asyncio.get_running_loop().create_task(self._play(sound))

    def _next_variant(self, sound: Sound) -> Path:
        paths = self._paths[sound]
        idx = self._rr[sound]
        self._rr[sound] = (idx + 1) % len(paths)
        return paths[idx]

    async def _play(self, sound: Sound) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "aplay", "-q", str(self._next_variant(sound)),
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
