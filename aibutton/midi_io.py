"""Reaching MIDI ports on this machine - sending to them, and listening.

[midi.py](midi.py) says what to send and [midi_clock.py](midi_clock.py) says
what an arriving tempo means; this module is the only place that touches a
port. The split is the one [osc.py](osc.py) makes against `actions.py`, in its
own module for a reason that only showed up when the code was written: there
turned out to be **two** ways to reach a MIDI port and neither is available
everywhere, so the choice needs somewhere to live that is not an action
executor.

**It was `midi_out.py` until the metronome needed to listen.** Sending and
receiving are not symmetrical - output is a call, input is a *callback on
someone else's thread* - but they share the backend question, and answering
that question twice in two modules would have been the drift this codebase
keeps testing for.

**Windows needs no dependency.** `winmm.dll` has shipped with every Windows
since the 90s and `midiOutShortMsg` exists precisely to send a three-byte
channel-voice message. It is reachable from `ctypes`, so on the platform this
project actually runs on, MIDI costs nothing to install. That is not a
workaround - `python-rtmidi` calls the same API one layer down, which its own
error strings admit by naming `MidiOutWinMM`.

**The dependency was tried first and could not be installed.** TODO 22 decided
to accept `python-rtmidi`; what that decision did not know is that it publishes
no wheel for Python 3.14 and its source build fails on this machine inside
meson's own temp-directory cleanup. It is still supported here, because it is
the only route on Linux and macOS and someone will eventually run this on one.
But it is no longer the route, and nothing has to be installed to use MIDI on
Windows.

**Both backends can be absent**, and that is a normal state rather than an
error: a Linux host with no rtmidi loses the `midi` action and keeps the
service, exactly as the LED and buzzer degrade to Null backends in the firmware
rather than failing to boot.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import sys
import time
from collections import deque

from . import midi_clock

log = logging.getLogger(__name__)


class MidiUnavailable(RuntimeError):
    """No way to reach a MIDI port on this machine."""


class PortNotFound(LookupError):
    """There are ports, but none whose name matches."""


def match_port(names: list[str], wanted: str) -> int | None:
    """Index of the first port whose name contains `wanted`, ignoring case.

    Substring rather than equality because Windows renames the thing you
    created: a loopMIDI port called "Button" is enumerated as "Button 2" with a
    suffix that changes between sessions, so an exact name in a config file
    would work until the next reboot. An empty `wanted` takes the first port,
    which is right on a machine with one virtual cable and is why the editor
    hint says to name it once you have two.
    """
    if not names:
        return None
    if not wanted:
        return 0
    needle = wanted.lower()
    for index, name in enumerate(names):
        if needle in name.lower():
            return index
    return None


# --- the Windows backend ---------------------------------------------------

_MAXPNAMELEN = 32


class _MidiOutCaps(ctypes.Structure):
    """MIDIOUTCAPSW. The fields after the name are unused here but must be
    declared: the struct is passed by size, and a short one makes
    midiOutGetDevCapsW reject the call rather than fill in less."""

    _fields_ = [
        ("wMid", ctypes.c_ushort),
        ("wPid", ctypes.c_ushort),
        ("vDriverVersion", ctypes.c_uint),
        ("szPname", ctypes.c_wchar * _MAXPNAMELEN),
        ("wTechnology", ctypes.c_ushort),
        ("wVoices", ctypes.c_ushort),
        ("wNotes", ctypes.c_ushort),
        ("wChannelMask", ctypes.c_ushort),
        ("dwSupport", ctypes.c_ulong),
    ]


class _MidiInCaps(ctypes.Structure):
    """MIDIINCAPSW. Shorter than the output one - an input has no voices, no
    notes and no channel mask, so the struct genuinely differs and cannot be
    shared however similar the first four fields look."""

    _fields_ = [
        ("wMid", ctypes.c_ushort),
        ("wPid", ctypes.c_ushort),
        ("vDriverVersion", ctypes.c_uint),
        ("szPname", ctypes.c_wchar * _MAXPNAMELEN),
        ("dwSupport", ctypes.c_ulong),
    ]


# A MIDI input callback, as winmm will call it. Declared at module scope
# because the prototype must outlive every instance that uses it.
#
#   void CALLBACK MidiInProc(HMIDIIN, UINT wMsg, DWORD_PTR dwInstance,
#                            DWORD_PTR dwParam1, DWORD_PTR dwParam2)
_MIDI_IN_PROC = ctypes.WINFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint,
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
)
_MIM_DATA = 0x3C3          # a complete short message arrived
_CALLBACK_FUNCTION = 0x00030000


class _WinMM:
    """MIDI through the Windows multimedia API."""

    name = "winmm"

    def __init__(self) -> None:
        self._dll = ctypes.WinDLL("winmm")
        # Declared rather than left to ctypes' defaults because a handle is a
        # pointer: on 64-bit, an undeclared restype is truncated to int and the
        # handle you close is not the one you opened.
        self._dll.midiOutOpen.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
        ]
        self._dll.midiOutClose.argtypes = [ctypes.c_void_p]
        self._dll.midiOutShortMsg.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._dll.midiInOpen.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint,
            _MIDI_IN_PROC, ctypes.c_void_p, ctypes.c_ulong,
        ]
        for name in ("midiInStart", "midiInStop", "midiInClose", "midiInReset"):
            getattr(self._dll, name).argtypes = [ctypes.c_void_p]

    def _names(self, count_fn, caps_fn, caps_type) -> list[str]:
        names = []
        for index in range(count_fn()):
            caps = caps_type()
            if caps_fn(index, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                names.append(caps.szPname)
            else:
                # Keep the position: an index that does not line up with the
                # list is worse than a port with an unhelpful name, because
                # every later port would then open the wrong device.
                names.append(f"<device {index}>")
        return names

    def ports(self) -> list[str]:
        return self._names(
            self._dll.midiOutGetNumDevs, self._dll.midiOutGetDevCapsW,
            _MidiOutCaps,
        )

    def in_ports(self) -> list[str]:
        return self._names(
            self._dll.midiInGetNumDevs, self._dll.midiInGetDevCapsW,
            _MidiInCaps,
        )

    def listen(self, index: int, on_message):
        """Open input `index` and call `on_message(status_byte)` per message.

        Returns a closer. The callback runs on a **driver thread**, not the
        event loop - see ClockListener for what that means for anything done
        inside it.
        """
        def trampoline(_handle, message, _instance, param1, _param2):
            if message == _MIM_DATA:
                on_message((param1 or 0) & 0xFF)

        proc = _MIDI_IN_PROC(trampoline)
        handle = ctypes.c_void_p()
        code = self._dll.midiInOpen(
            ctypes.byref(handle), index, proc, None, _CALLBACK_FUNCTION,
        )
        if code != 0:
            raise self._fail(code, "midiInOpen")
        self._dll.midiInStart(handle)

        def close():
            # Stop and reset before closing so the driver is quiet before the
            # callback address stops being valid.
            self._dll.midiInStop(handle)
            self._dll.midiInReset(handle)
            self._dll.midiInClose(handle)

        # **The ctypes callback must outlive the driver's use of it.** If it is
        # collected while winmm still holds its address, the next pulse calls
        # freed memory and the process dies with an illegal instruction - no
        # traceback, no exception, just gone. Parked on the closer, whose
        # lifetime is exactly the listener's.
        #
        # Note what does *not* work: closing over `proc` and then writing
        # `del proc` in this function. That makes the name local to `close`,
        # so the closure never captures it and the object is freed the moment
        # `listen` returns. It reads like careful cleanup and is the bug.
        close.keep_alive = proc
        return close

    def _fail(self, code: int, doing: str) -> MidiUnavailable:
        buffer = ctypes.create_unicode_buffer(256)
        self._dll.midiOutGetErrorTextW(code, buffer, len(buffer))
        return MidiUnavailable(f"{doing} failed: {buffer.value or code}")

    def send(self, index: int, data: bytes) -> None:
        handle = ctypes.c_void_p()
        code = self._dll.midiOutOpen(ctypes.byref(handle), index, None, None, 0)
        if code != 0:
            raise self._fail(code, "midiOutOpen")
        try:
            # Status in the low byte, then the two data bytes. The fourth is
            # unused for a short message and must be zero.
            packed = data[0] | (data[1] << 8) | (data[2] << 16)
            code = self._dll.midiOutShortMsg(handle, packed)
            if code != 0:
                raise self._fail(code, "midiOutShortMsg")
        finally:
            self._dll.midiOutClose(handle)


# --- the portable backend --------------------------------------------------


class _RtMidi:
    """MIDI out through python-rtmidi, for the platforms winmm is not on."""

    name = "python-rtmidi"

    def __init__(self) -> None:
        import rtmidi

        self._rtmidi = rtmidi

    def ports(self) -> list[str]:
        out = self._rtmidi.MidiOut()
        try:
            return list(out.get_ports())
        finally:
            del out

    def in_ports(self) -> list[str]:
        port = self._rtmidi.MidiIn()
        try:
            return list(port.get_ports())
        finally:
            del port

    def listen(self, index: int, on_message):
        port = self._rtmidi.MidiIn()
        port.open_port(index)
        # **rtmidi discards clock by default.** `timing` covers exactly the
        # 0xF8 pulses this exists to receive, so without this line the listener
        # opens successfully, reports no errors and hears nothing at all.
        port.ignore_types(sysex=True, timing=False, active_sense=True)
        port.set_callback(lambda message, _delta: on_message(message[0][0]))

        def close():
            port.cancel_callback()
            port.close_port()

        return close

    def send(self, index: int, data: bytes) -> None:
        out = self._rtmidi.MidiOut()
        try:
            out.open_port(index)
            out.send_message(list(data))
        finally:
            # rtmidi frees the port in its destructor, and on Windows one left
            # to the garbage collector stays claimed long enough for the next
            # press to find it busy.
            try:
                out.close_port()
            except Exception:  # noqa: BLE001 - closing must not mask the send
                pass
            del out


def _choose():
    """The first backend that loads. Windows first, deliberately.

    Preferring winmm where both exist is not a downgrade: rtmidi's Windows
    implementation is a wrapper over this same API, so choosing it directly
    removes a layer rather than settling for less.
    """
    candidates = []
    if sys.platform == "win32":
        candidates.append(_WinMM)
    candidates.append(_RtMidi)
    for candidate in candidates:
        try:
            return candidate()
        except Exception as exc:  # noqa: BLE001 - any failure means "not this one"
            log.debug("midi backend %s unavailable: %s", candidate.name, exc)
    return None


# Resolved once. Both backends answer a question about the machine rather than
# about the moment, and re-deciding on every press would cost a DLL load for an
# answer that cannot have changed.
_BACKEND = _choose()


def backend_name() -> str | None:
    """Which backend is in use, or None. For diagnostics and the README."""
    return _BACKEND.name if _BACKEND else None


def ports() -> list[str]:
    if _BACKEND is None:
        raise MidiUnavailable(
            "no MIDI backend: install python-rtmidi, or run on Windows"
        )
    return _BACKEND.ports()


def in_ports() -> list[str]:
    """Input ports. A separate list from `ports()` and separately indexed -
    a machine commonly has different counts of each, so an index from one is
    meaningless against the other."""
    if _BACKEND is None:
        raise MidiUnavailable(
            "no MIDI backend: install python-rtmidi, or run on Windows"
        )
    return _BACKEND.in_ports()


class ClockListener:
    """Timestamps MIDI clock pulses arriving on a port.

    **The whole design constraint is the thread.** The backend calls
    `_on_message` from a driver thread that is not the event loop and is not
    running Python otherwise, so that method does the least work that could
    possibly be useful: a `perf_counter()` and a `deque.append`, both of which
    are atomic enough to need no lock. Anything heavier - deciding a tempo,
    touching the config, driving an LED - happens on the loop when someone
    calls `bpm()`. Doing arithmetic in the callback would put a garbage
    collection between two pulses of somebody's take.

    `deque(maxlen=...)` is doing real work here: it bounds memory with no
    trimming logic on the hot path, and a listener left running for an hour
    holds one beat of timestamps rather than 86,000.
    """

    def __init__(self, port: str = "", window: int = midi_clock.DEFAULT_WINDOW):
        self._port = port
        self._window = window
        # One spare so `window` intervals are available, not window-minus-one.
        self._pulses: deque[float] = deque(maxlen=window + 1)
        self._close = None
        self._rolling = False
        self.port_name = ""

    def _on_message(self, status: int) -> None:
        if status == midi_clock.CLOCK:
            self._pulses.append(time.perf_counter())
        elif status in (midi_clock.START, midi_clock.CONTINUE):
            self._rolling = True
        elif status == midi_clock.STOP:
            self._rolling = False

    def start(self) -> str:
        names = in_ports()
        index = match_port(names, self._port)
        if index is None:
            available = ", ".join(names) if names else "none"
            raise PortNotFound(
                f"MIDI input {self._port!r} not found (available: {available})"
            )
        self._close = _BACKEND.listen(index, self._on_message)
        self.port_name = names[index]
        return self.port_name

    def stop(self) -> None:
        if self._close is not None:
            with contextlib.suppress(Exception):
                self._close()
            self._close = None

    @property
    def rolling(self) -> bool:
        """Whether the DAW said it was playing. Only as good as the last
        transport byte - a DAW that is quit mid-stream never sends `0xFC`,
        which is what `stale` is for."""
        return self._rolling

    def bpm(self) -> float | None:
        """The tempo implied by the pulses so far, or None."""
        return midi_clock.bpm_from_pulses(self._pulses, self._window)

    def stale(self, bpm: float | None = None) -> bool:
        return midi_clock.is_stale(self._pulses, time.perf_counter(), bpm=bpm)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.stop()
        return False


def send(port: str, data: bytes) -> str:
    """Send `data` to the first port matching `port`. Returns the port used.

    Opens and closes around every send rather than holding the port. A cached
    handle goes stale exactly when loopMIDI or the DAW restarts, and it fails
    as silence - the worst failure available here. Opening costs a couple of
    milliseconds against a press that already waited out a 0.4 s tap window.
    """
    names = ports()
    index = match_port(names, port)
    if index is None:
        available = ", ".join(names) if names else "none"
        raise PortNotFound(f"MIDI port {port!r} not found (available: {available})")
    _BACKEND.send(index, data)
    return names[index]
