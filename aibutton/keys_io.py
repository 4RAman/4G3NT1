"""Press what [keys.py](keys.py) spells, on whatever host we are running on.

Windows goes through `user32.dll`'s `SendInput` via `ctypes`, which is the same
call every macro tool makes and costs **no dependency at all** - the `midi`
action's winmm route, applied again (CLAUDE.md, Conventions: check what the
platform already has before taking a dependency for one action).

There is deliberately **no Linux/macOS backend**. Linux would need `uinput`
(root, or a udev rule) or an X-only helper, and macOS needs an Accessibility
grant the user must click through - both are real work with real permissions
questions, and neither belongs in the same change as the Windows one. The
action degrades exactly as `midi` does on a machine with no backend: it is
absent, not broken, and nothing else in the service notices.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from . import keys

log = logging.getLogger("aibutton")


class KeysUnavailable(RuntimeError):
    """No way to synthesize input on this host."""


_NO_BACKEND = "no input backend: the keys action is Windows-only for now"

# Virtual-key codes. Windows has never renumbered one of these, which is why
# writing them down here is safe and looking them up at runtime is not.
_VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "playpause": 0xB3, "nexttrack": 0xB0, "prevtrack": 0xB1, "stop": 0xB2,
    "volumeup": 0xAF, "volumedown": 0xAE, "mute": 0xAD,
    "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}
_VK.update({c: 0x41 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")})
_VK.update({d: 0x30 + i for i, d in enumerate("0123456789")})
_VK.update({f"f{n}": 0x6F + n for n in range(1, 25)})  # VK_F1 = 0x70

_INPUT_MOUSE, _INPUT_KEYBOARD = 0, 1
_KEYEVENTF_KEYUP = 0x0002
_MOUSE_FLAGS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}

_ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(_ULONG_PTR))]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(_ULONG_PTR))]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    # `type` and the union, in that order. Getting the padding wrong here is
    # the classic SendInput bug: it returns success and nothing happens.
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _InputUnion)]


class _Win32:
    """user32's SendInput. Present on every Windows since 2000."""

    name = "user32"

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

    def _send(self, events: list[_Input]) -> None:
        if not events:
            return
        array = (_Input * len(events))(*events)
        sent = self._user32.SendInput(
            len(events), ctypes.byref(array), ctypes.sizeof(_Input)
        )
        if sent != len(events):
            code = ctypes.get_last_error()
            # UIPI: a normal-integrity process cannot inject into an elevated
            # window, and this is how that presents. Worth naming, because the
            # only symptom otherwise is a chord that works everywhere but one.
            raise KeysUnavailable(
                f"SendInput sent {sent} of {len(events)} events (error {code}); "
                "an elevated window will refuse input from a normal process"
            )

    @staticmethod
    def _key(code: int, up: bool) -> _Input:
        event = _Input(type=_INPUT_KEYBOARD)
        event.ki = _KeyBdInput(wVk=code, wScan=0,
                               dwFlags=_KEYEVENTF_KEYUP if up else 0,
                               time=0, dwExtraInfo=None)
        return event

    @staticmethod
    def _mouse(flags: int) -> _Input:
        event = _Input(type=_INPUT_MOUSE)
        event.mi = _MouseInput(dx=0, dy=0, mouseData=0, dwFlags=flags,
                               time=0, dwExtraInfo=None)
        return event

    def chord(self, modifiers: tuple[str, ...], key: str) -> None:
        events = [self._key(_VK[m], up=False) for m in modifiers]
        events.append(self._key(_VK[key], up=False))
        events.append(self._key(_VK[key], up=True))
        # Modifiers release in reverse, so the state the OS sees unwinds the
        # way it was built - the same discipline as closing brackets.
        events += [self._key(_VK[m], up=True) for m in reversed(modifiers)]
        self._send(events)

    def click(self, which: str) -> None:
        down, up = _MOUSE_FLAGS["left" if which == "double" else which]
        events = [self._mouse(down), self._mouse(up)]
        if which == "double":
            events += [self._mouse(down), self._mouse(up)]
        self._send(events)


def _choose():
    if sys.platform != "win32":
        return None
    try:
        return _Win32()
    except Exception as exc:  # noqa: BLE001 - a missing DLL must not stop the service
        log.warning("keys: no input backend (%s)", exc)
        return None


_BACKEND = _choose()


def backend_name() -> str | None:
    """Which backend is live, or None. The web UI reports it; tests assert it."""
    return _BACKEND.name if _BACKEND else None


def send(combo: str, click: str) -> str:
    """Press `combo` then `click`; returns what happened, for the status line.

    Raises `KeysUnavailable` when there is no backend, which `actions.execute`
    turns into a failed `ActionResult` - the same shape a webhook 500 takes.
    """
    if _BACKEND is None:
        raise KeysUnavailable(_NO_BACKEND)
    if combo:
        parsed = keys.parse_combo(combo)
        if parsed is None:
            # The parser refused this at load time, so reaching here means the
            # vocabulary and the config disagree - worth failing loudly.
            raise KeysUnavailable(f"not a chord this build knows: {combo!r}")
        _BACKEND.chord(*parsed)
    if click:
        _BACKEND.click(click)
    return keys.describe(combo, click)
