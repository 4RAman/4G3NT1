# Feedback tones on a piezo buzzer.
#
# A SOUND_CMD byte is a sound code, optionally with the LOOP flag: play the
# tone from tones.py once, or repeat it with a gap until the host writes
# STOP_LOOP (that is how an alarm rings until dismissed). Every entry point
# is non-blocking - a BLE write starts a task and returns.
#
# The machine import lives inside the constructor so this module is
# importable on the host for tests.

import asyncio

import hardware
import protocol
from tones import LOOP_GAP_MS, TONES


class NullBuzzer:
    """No buzzer wired, or PWM unavailable: silence, but never an error."""

    def tone(self, freq):
        pass

    def silence(self):
        pass


class PWMBuzzer:
    """Square wave on one pin. A piezo is loudest near 50% duty, so volume
    scales that half-range rather than the full 0..65535."""

    def __init__(self, pin, volume):
        from machine import PWM, Pin

        self._pwm = PWM(Pin(pin), freq=1000, duty_u16=0)
        self._duty = int(32768 * min(max(volume, 0.0), 1.0))

    def tone(self, freq):
        self._pwm.freq(freq)
        self._pwm.duty_u16(self._duty)

    def silence(self):
        self._pwm.duty_u16(0)


def make_backend():
    if hardware.BUZZER_PIN is None:
        return NullBuzzer()
    try:
        return PWMBuzzer(hardware.BUZZER_PIN, hardware.BUZZER_VOLUME)
    except Exception as exc:  # noqa: BLE001 - stay silent rather than fail to boot
        print("buzzer: PWM unavailable (%s) - running silent" % exc)
        return NullBuzzer()


class Buzzer:
    """Public surface: play(cmd) for a SOUND_CMD byte, plus stop()."""

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else make_backend()
        self._task = None

    def play(self, cmd):
        """Run a SOUND_CMD byte. Replaces whatever was playing, so a
        loop-start during a one-shot (or a second alarm) does the right
        thing without the host having to sequence stops."""
        code, looping = protocol.decode_sound(cmd)
        self.stop()
        if code is None:
            return
        segments = TONES.get(code)
        if segments is None:
            print("buzzer: unknown sound 0x%02x - ignored" % cmd)
            return
        self._task = asyncio.create_task(self._run(segments, looping))

    def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._backend.silence()

    async def _run(self, segments, looping):
        try:
            while True:
                await self._play_once(segments)
                if not looping:
                    return
                await asyncio.sleep(LOOP_GAP_MS / 1000)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001 - a tone bug must not kill BLE
            print("buzzer: playback crashed (%s)" % exc)
        finally:
            # Cancellation lands mid-tone; leaving the PWM driven would hold
            # a note forever, which is the one failure everyone can hear.
            self._backend.silence()

    async def _play_once(self, segments):
        for freq, ms in segments:
            if freq:
                self._backend.tone(freq)
            else:
                self._backend.silence()
            # sleep(), not MicroPython's sleep_ms(): the same source has to
            # run under CPython for the host-side tests.
            await asyncio.sleep(ms / 1000)
        self._backend.silence()
