"""Compile your config into an app package the button can run on its own.

    ./.venv/Scripts/python tools/install_app.py            # what would go, and what would not
    ./.venv/Scripts/python tools/install_app.py --push     # send it to the button, over BLE
    ./.venv/Scripts/python tools/install_app.py --write    # or just build dist/app.pkg

**`--push` goes through the running service**, which is the only thing holding
the radio - one BLE central, and it is already taken. Nothing is stopped and
nothing is unplugged; the button has the new package a moment later.

`--write` is the offline path: it saves the file and prints the `mpremote` line
that copies it over USB, for a board with firmware too old to be sent apps.

**Read the report before you flash.** Most of a config cannot run without the
host - a webhook needs a network, a DAW command needs a DAW - so a standalone
button does a *subset* of what your button does, and which subset is a thing
you should know in advance rather than discover by pressing. Everything left
out is named, with what it is waiting on.

**What lands on the device is not your config.** It is compiled state machines
(see [aibutton/appc.py](../aibutton/appc.py)): no JSON, no names, no parser.
The device validates a checksum and a version, and a two-app package is a few
hundred bytes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aibutton.appc import CompileError, compile_config  # noqa: E402
from aibutton.config import load_config_full  # noqa: E402

OUT = ROOT / "dist" / "app.pkg"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--write", action="store_true", help="build the package")
    parser.add_argument(
        "--push", action="store_true",
        help="install it on the button through the running service",
    )
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args(argv)

    config = load_config_full(args.config).config
    try:
        package, report = compile_config(config)
    except CompileError as exc:
        print("cannot build: %s" % exc)
        return 1

    if report["menu"]:
        print("menu:  %s" % report["menu"])
    print("apps:  %s" % ", ".join(report["apps"]))
    if report["dropped"]:
        print()
        print("gestures that cannot come along:")
        for where, trigger, why in report["dropped"]:
            print("  %-12s in %-14s %s" % (trigger, where[:14], why))
    if report["skipped"]:
        print()
        print("these modes stay host-only:")
        for name, why in report["skipped"]:
            print("  %-16s needs %s" % (name[:16], why))

    print()
    print("package: %d bytes" % len(package))

    if args.push:
        import json
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            args.url.rstrip("/") + "/api/app/install", method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as answer:
                json.load(answer)
        except urllib.error.HTTPError as exc:
            print("the service refused it: %s" % exc.read().decode(errors="replace"))
            return 1
        except OSError as exc:
            print("no service at %s (%s) - start it, or use --write" % (args.url, exc))
            return 1
        print("installed on the button")
        return 0

    if not args.write:
        print("(pass --push to install it, or --write to save the file)")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(package)
    print("written to %s" % out)
    print()
    print("Stop the service, then:")
    print("  ./.venv/Scripts/python -m mpremote cp %s :app.pkg + reset" % out)
    print()
    print("To take it off again:")
    print("  ./.venv/Scripts/python -m mpremote rm :app.pkg + reset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
