"""Entry point: `python -m aibutton.control` (or double-click control.pyw).

Defaults are resolved relative to the project, not the working directory, so
the shortcut works from anywhere.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    root = Path(__file__).resolve().parent.parent.parent
    p = argparse.ArgumentParser(description="Button control panel")
    p.add_argument(
        "--config",
        default=None,
        help="config path (default: <project>/config.json)",
    )
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = Path(args.config) if args.config else root / "config.json"

    # A desktop shortcut is a thing people double-click, and two tray icons
    # fighting over one service is worse than one. Held for the life of the
    # panel; the OS drops it if we crash. This is a *different* lock from the
    # service's own - the panel and the service are allowed to coexist.
    from ..single_instance import AlreadyRunning, SingleInstance

    guard = SingleInstance(config.with_name("control-panel.lock"))
    try:
        guard.acquire()
    except AlreadyRunning:
        # Exiting silently would look like the shortcut did nothing, when in
        # fact the panel is already sitting in the tray.
        _already_running()
        return

    # Imported here so --help works on a machine without a display or a tray.
    from .tray import ControlPanel

    try:
        ControlPanel(root, config).run()
    finally:
        guard.release()


def _already_running() -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        hidden = tk.Tk()
        hidden.withdraw()
        messagebox.showinfo(
            "Button control",
            "The control panel is already running.\n\n"
            "Look for its icon in the system tray, next to the clock.",
        )
        hidden.destroy()
    except Exception:  # no display: the log line is all we can offer
        logging.getLogger(__name__).warning("the control panel is already running")


if __name__ == "__main__":
    main()
