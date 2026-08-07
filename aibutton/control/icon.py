"""The control panel's artwork: the tray dot and the application icon.

Split out from [tray.py](tray.py) so the shortcut installer and the window
can use it without importing pystray - Pillow is the only dependency here.

Both images are drawn rather than shipped as files. A dot in a flat colour
and a ring are exactly the shapes that survive being scaled to 16 px on a
taskbar, and drawing them keeps the tray's status colours and the app icon
from drifting apart the way two hand-made PNGs would.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw

from .status import COLOURS, Level

log = logging.getLogger(__name__)

_PX = 256
# Windows picks the nearest of these for the taskbar, Alt-Tab and Explorer.
_ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

_BEZEL = (58, 62, 72, 255)     # the button's housing
_FACE = (0, 214, 224, 255)     # its lit face - the IDLE cyan from config.json


def status_dot(level: Level, px: int = 64) -> Image.Image:
    """The tray icon: a filled dot in the level's colour.

    Deliberately not a glyph. At 16 px on a taskbar colour is the only thing
    that reads reliably, so the shape stays constant and only the hue moves.
    """
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, px // 10)
    box = (pad, pad, px - pad, px - pad)
    draw.ellipse(box, fill=COLOURS[level] + (255,))
    # A dark rim keeps the dot visible against a same-coloured taskbar.
    draw.ellipse(box, outline=(20, 20, 24, 200), width=max(1, px // 20))
    return img


def app_icon(px: int = _PX) -> Image.Image:
    """The application icon: the button itself, seen from above."""
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    outer = px // 16
    draw.ellipse((outer, outer, px - outer, px - outer), fill=_BEZEL)
    inset = px // 5
    draw.ellipse((inset, inset, px - inset, px - inset), fill=_FACE)
    # A highlight arc, so it reads as a domed cap rather than a flat disc.
    rim = px // 3
    draw.arc(
        (rim, rim, px - rim, px - rim),
        start=190, end=320,
        fill=(255, 255, 255, 190),
        width=max(2, px // 32),
    )
    return img


def ensure_ico(directory: Path) -> Path | None:
    """Write `button.ico` into `directory` if it is not already there.

    Returns None rather than raising when it cannot be written: the icon is
    cosmetic, and an unwritable install directory must not stop the panel
    from starting or the shortcut from being created.
    """
    path = directory / "button.ico"
    if path.exists():
        return path
    try:
        app_icon().save(path, format="ICO", sizes=_ICO_SIZES)
    except (OSError, ValueError) as exc:
        log.warning("could not write %s: %s", path, exc)
        return None
    return path
