"""Build the standalone scene editor: one HTML file, no server, no network.

    .venv/Scripts/python tools/build_editor.py

Writes `dist/button-editor.html`. Open it by double-clicking; it edits scene
files through the browser's file picker and never talks to anything.

**Why a bundle at all.** Browsers refuse `<script type="module">` over
`file://` - module loading goes through fetch, and fetch says no to a file
URL. So the editor's ES modules have to arrive as one inline script, which
means resolving the imports here.

**What this bundler handles, and what it refuses.** Only what
`aibutton/web/static/` actually uses: named imports from sibling modules,
optionally aliased, and named exports. It has no opinion about default
exports, namespace imports, dynamic imports or circular graphs - it raises on
all of them rather than emitting something subtly wrong. If those ever become
worth having, this becomes the wrong tool and a real bundler becomes the right
one; the failure is loud so that choice is deliberate.

The page's stylesheet and the default palette are *taken*, not copied: the CSS
is lifted out of index.html and the defaults come from `config.AppConfig()` at
build time, so neither is a second copy anyone has to keep in step.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "aibutton" / "web" / "static"
INDEX = ROOT / "aibutton" / "web" / "index.html"
SHELL = Path(__file__).resolve().parent / "editor_shell.html"
OUT = ROOT / "dist" / "button-editor.html"

# The page loads these; everything else is pulled in as a dependency.
ENTRIES = ("help.js", "menu.js")

_IMPORT = re.compile(r"^import\s*\{(?P<names>[^}]*)\}\s*from\s*'\./(?P<module>[\w.]+)';?\s*$",
                     re.MULTILINE | re.DOTALL)
_UNSUPPORTED = re.compile(r"^import\s+(?!\{)|^export\s+default\b|\bimport\s*\(", re.MULTILINE)
_DECLARATION = re.compile(
    r"^(?:export\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", re.MULTILINE
)


class BuildError(Exception):
    """Something this bundler is deliberately not clever enough to do."""


def _imports(source: str) -> list[tuple[str, list[str]]]:
    """[(module, ['el', 'paint as applySwatch', ...]), ...] for one file."""
    found = []
    for match in _IMPORT.finditer(source):
        names = [n.strip() for n in match.group("names").split(",") if n.strip()]
        found.append((match.group("module"), names))
    return found


def _order(entries=ENTRIES, static: Path = STATIC) -> list[str]:
    """Depth-first topological order, dependencies before dependants."""
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if name in ordered:
            return
        if name in visiting:
            raise BuildError(f"circular import: {' -> '.join((*trail, name))}")
        path = static / name
        if not path.exists():
            raise BuildError(f"{name} does not exist (imported by {trail[-1] if trail else 'the page'})")
        visiting.add(name)
        for module, _ in _imports(path.read_text(encoding="utf-8")):
            visit(module, (*trail, name))
        visiting.discard(name)
        ordered.append(name)

    for entry in entries:
        visit(entry, ())
    return ordered


def _strip(name: str, source: str) -> str:
    """One module's body: imports removed, aliases rebound, exports unmarked."""
    if _UNSUPPORTED.search(source):
        raise BuildError(
            f"{name} uses an import/export form this bundler does not handle "
            "(default export, namespace or side-effect import, or a dynamic import)"
        )
    aliases = []
    for _, names in _imports(source):
        for entry in names:
            parts = entry.split(" as ")
            if len(parts) == 2:
                # Everything shares one scope once concatenated, so an alias
                # is just another name for the same binding.
                aliases.append(f"const {parts[1].strip()} = {parts[0].strip()};")
    body = _IMPORT.sub("", source)
    body = re.sub(r"^export\s+", "", body, flags=re.MULTILINE)
    return "\n".join([*aliases, body])


def bundle(entries=ENTRIES, static: Path = STATIC) -> str:
    """Every module, in dependency order, as one module-scope script body."""
    order = _order(entries, static)
    declared: dict[str, str] = {}
    chunks = []
    for name in order:
        source = (static / name).read_text(encoding="utf-8")
        for symbol in _DECLARATION.findall(source):
            if symbol in declared and declared[symbol] != name:
                raise BuildError(
                    f"{name} and {declared[symbol]} both declare {symbol!r} at the top "
                    "level; they cannot share one scope"
                )
            declared[symbol] = name
        chunks.append(f"// ---- {name} " + "-" * max(0, 60 - len(name)) + "\n" + _strip(name, source))
    return "\n\n".join(chunks)


def page_style() -> str:
    """The served page's stylesheet, so the editor is not a second look to
    maintain. Taken verbatim between the first <style> and </style>."""
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    if match is None:
        raise BuildError(f"no <style> block found in {INDEX}")
    return match.group(1).strip()


def default_config() -> dict:
    """A blank config as Python defines it - the editor seeds a new or partial
    scene from this. Generated here rather than written out in JavaScript, so
    it cannot drift from config.py."""
    sys.path.insert(0, str(ROOT))
    from aibutton.config import AppConfig, as_dict

    config = as_dict(AppConfig())
    config.pop("scenes", None)  # the pointer belongs to config.json alone
    return config


def build() -> Path:
    shell = SHELL.read_text(encoding="utf-8")
    for token, value in (
        ("/*{{STYLE}}*/", page_style()),
        ("/*{{MODULES}}*/", bundle()),
        ("/*{{DEFAULTS}}*/", json.dumps(default_config(), indent=2)),
    ):
        if token not in shell:
            raise BuildError(f"{SHELL.name} has no {token} placeholder")
        shell = shell.replace(token, value)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(shell, encoding="utf-8")
    return OUT


def main() -> int:
    try:
        out = build()
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1
    print(f"{out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
