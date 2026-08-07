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

    # Imported here so --help works on a machine without a display or a tray.
    from .tray import ControlPanel

    ControlPanel(root, config).run()


if __name__ == "__main__":
    main()
