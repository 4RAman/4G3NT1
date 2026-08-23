"""The keyboard/mouse vocabulary, and how a chord is spelled.

Pure: names in, names out, no ctypes and no OS. [keys_io.py](keys_io.py) is the
half that actually presses anything, exactly as `midi.py` encodes and
`midi_io.py` sends.

**The vocabulary is declared, not passed through.** A config could otherwise
name any key on the machine, and "type this string" is a different and much
larger promise than "press this chord" - one the parser could not bound and the
editor could not offer a picker for. So a name that is not in `KEYS` is a
config error, not a keystroke.

TODO 37 decided the scope with it: **one chord, not a sequence.** A list of
keystrokes with delays between them is `SequenceAction` (TODO 33), and building
a second one here would be the thing that has to be un-built later.
"""

from __future__ import annotations

# Modifiers are separated from keys because they are held rather than struck:
# the chord is every modifier down, the key struck, then the modifiers up.
MODIFIERS: tuple[str, ...] = ("ctrl", "shift", "alt", "win")

# The media keys are first because they are the ones a button is actually for:
# they work with no window focused, which is the failure mode every other key
# in this table has (see `CAVEAT`).
MEDIA_KEYS: tuple[str, ...] = (
    "playpause", "nexttrack", "prevtrack", "stop",
    "volumeup", "volumedown", "mute",
)

NAVIGATION_KEYS: tuple[str, ...] = (
    "enter", "tab", "esc", "space", "backspace", "delete", "insert",
    "home", "end", "pageup", "pagedown", "up", "down", "left", "right",
)

LETTERS: tuple[str, ...] = tuple("abcdefghijklmnopqrstuvwxyz")
DIGITS: tuple[str, ...] = tuple("0123456789")
FUNCTION_KEYS: tuple[str, ...] = tuple(f"f{n}" for n in range(1, 25))

KEYS: tuple[str, ...] = (
    MEDIA_KEYS + NAVIGATION_KEYS + LETTERS + DIGITS + FUNCTION_KEYS
)

CLICKS: tuple[str, ...] = ("left", "right", "middle", "double")

MAX_MODIFIERS = len(MODIFIERS)

#: Worth saying in the editor rather than discovering: synthesized input goes
#: wherever focus already is. The button cannot choose the window, so a chord
#: bound to a game's hotkey does nothing while the browser is in front. Media
#: keys are the exception and the reason they are listed first.
CAVEAT = "Goes to whatever window has focus. Media keys are the exception."


def parse_combo(text: str) -> tuple[tuple[str, ...], str] | None:
    """Split `"ctrl+shift+p"` into `(("ctrl", "shift"), "p")`.

    Returns None for anything malformed - an unknown name, a repeated
    modifier, no key or more than one, or a modifier after the key. The caller
    logs; this function does not, because it is also what the *editor* would
    use to validate and a warning there would be noise.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    parts = [p.strip().lower() for p in text.split("+")]
    if any(not p for p in parts):
        return None  # "ctrl+" or "a++b"

    modifiers: list[str] = []
    for index, part in enumerate(parts):
        if part in MODIFIERS:
            if part in modifiers:
                return None  # "ctrl+ctrl+a"
            if index != len(modifiers):
                return None  # a modifier after the key: "a+ctrl"
            modifiers.append(part)
    key_parts = parts[len(modifiers):]
    if len(key_parts) != 1 or key_parts[0] not in KEYS:
        return None
    return tuple(modifiers), key_parts[0]


def describe(combo: str, click: str) -> str:
    """What the editor and the status line call this, in one phrase."""
    bits = []
    if combo:
        bits.append(combo)
    if click:
        bits.append("double click" if click == "double" else f"{click} click")
    return " then ".join(bits) if bits else "nothing"
