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
    except AlreadyRunning as exc:
        from .beacon import ask_to_show

        # Ask the running panel to show itself, which is what double-clicking
        # the shortcut a second time means everywhere else. Windows hides new
        # tray icons in an overflow flyout, so "it is already in the tray" is
        # advice a lot of people cannot act on.
        if ask_to_show(config):
            return
        # It holds the lock but will not answer: wedged, not merely running -
        # and "look in the tray" would point at nothing.
        _not_answering(str(exc))
        return

    # Imported here so --help works on a machine without a display or a tray.
    from .tray import ControlPanel

    try:
        ControlPanel(root, config).run()
    finally:
        guard.release()


def _not_answering(detail: str) -> None:
    """Report a panel that holds the lock but will not talk.

    **Never parented to a withdrawn root.** On Windows a modal on a withdrawn
    Tk root can render with no taskbar button and no focus, leaving the process
    holding a dialog nobody can see or dismiss - which is the exact failure
    being reported here. So this is a real window: mapped, raised, topmost for
    a moment, and destroyed on a button rather than by a modal loop.
    """
    message = (
        "The control panel is already running, but it is not responding.\n\n"
        f"{detail}\n\n"
        "End that process, then start the panel again."
    )
    try:
        import tkinter as tk

        win = tk.Tk()
        win.title("Button control")
        win.geometry("520x220")
        tk.Label(
            win, text=message, justify="left", anchor="nw", wraplength=480
        ).pack(fill="both", expand=True, padx=14, pady=(14, 6))
        tk.Button(win, text="Close", width=12, command=win.destroy).pack(pady=(0, 14))
        # Raised deliberately rather than hopefully: this window exists because
        # something else failed to be visible.
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        win.after(1200, lambda: win.attributes("-topmost", False))
        win.mainloop()
    except Exception:  # no display: the log line is all we can offer
        logging.getLogger(__name__).warning(
            "the control panel is already running but not responding: %s", detail
        )


if __name__ == "__main__":
    main()
