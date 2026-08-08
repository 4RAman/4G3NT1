"""The standalone editor's bundler.

Mostly it asserts the *refusals*. The bundler only understands the handful of
import forms `aibutton/web/static/` actually uses, and the danger is not that
it fails on something else - it is that it silently emits JavaScript that is
subtly wrong. Every case below is one it has to notice out loud.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# tools/ is scripts, not a package - there is nothing to install and nothing
# else imports from it, so the path goes on for this module the same way
# conftest.py puts firmware/ on for the firmware tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_editor  # noqa: E402


def write(directory: Path, name: str, source: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


# --- ordering and rewriting ---------------------------------------------

def test_dependencies_are_emitted_before_the_modules_that_use_them(tmp_path):
    write(tmp_path, "dom.js", "export function el() {}\n")
    write(tmp_path, "menu.js", "import { el } from './dom.js';\nel();\n")

    assert build_editor._order(("menu.js",), tmp_path) == ["dom.js", "menu.js"]


def test_a_module_imported_twice_is_emitted_once(tmp_path):
    write(tmp_path, "dom.js", "export function el() {}\n")
    write(tmp_path, "a.js", "import { el } from './dom.js';\nexport const A = el;\n")
    write(tmp_path, "b.js", "import { el } from './dom.js';\nexport const B = el;\n")
    write(tmp_path, "menu.js", "import { A } from './a.js';\nimport { B } from './b.js';\n")

    order = build_editor._order(("menu.js",), tmp_path)

    assert order.count("dom.js") == 1
    assert order.index("dom.js") == 0


def test_an_aliased_import_becomes_a_rebinding(tmp_path):
    """`import { paint as applySwatch }` has to survive losing the module
    boundary - one scope means the alias is just another name."""
    write(tmp_path, "led.js", "export function paint() {}\n")
    write(tmp_path, "menu.js", "import { paint as applySwatch } from './led.js';\napplySwatch();\n")

    out = build_editor.bundle(("menu.js",), tmp_path)

    assert "const applySwatch = paint;" in out
    assert "import" not in out


def test_export_markers_are_stripped_but_the_declarations_survive(tmp_path):
    write(tmp_path, "menu.js", "export const A = 1;\nexport function f() {}\nexport class C {}\n")

    out = build_editor.bundle(("menu.js",), tmp_path)

    assert "const A = 1;" in out and "function f()" in out and "class C" in out
    assert not re.search(r"^export\s", out, re.MULTILINE)


def test_a_multiline_import_list_is_handled(tmp_path):
    write(tmp_path, "schema.js", "export const A = 1;\nexport const B = 2;\n")
    write(tmp_path, "menu.js", "import {\n  A,\n  B,\n} from './schema.js';\n")

    out = build_editor.bundle(("menu.js",), tmp_path)

    assert "import" not in out


# --- the refusals --------------------------------------------------------

def test_a_default_export_is_refused(tmp_path):
    write(tmp_path, "menu.js", "export default class Thing {}\n")

    with pytest.raises(build_editor.BuildError, match="does not handle"):
        build_editor.bundle(("menu.js",), tmp_path)


def test_a_namespace_import_is_refused(tmp_path):
    write(tmp_path, "dom.js", "export const el = 1;\n")
    write(tmp_path, "menu.js", "import * as dom from './dom.js';\n")

    with pytest.raises(build_editor.BuildError, match="does not handle"):
        build_editor.bundle(("menu.js",), tmp_path)


def test_a_dynamic_import_is_refused(tmp_path):
    write(tmp_path, "menu.js", "const mod = await import('./late.js');\n")

    with pytest.raises(build_editor.BuildError, match="does not handle"):
        build_editor.bundle(("menu.js",), tmp_path)


def test_a_circular_import_is_refused_rather_than_looping(tmp_path):
    write(tmp_path, "a.js", "import { b } from './b.js';\nexport const a = 1;\n")
    write(tmp_path, "b.js", "import { a } from './a.js';\nexport const b = 2;\n")

    with pytest.raises(build_editor.BuildError, match="circular"):
        build_editor.bundle(("a.js",), tmp_path)


def test_two_modules_declaring_the_same_name_are_refused(tmp_path):
    """One scope means one namespace. Emitting both would shadow silently."""
    write(tmp_path, "a.js", "export const shared = 1;\n")
    write(tmp_path, "b.js", "export const shared = 2;\n")
    write(tmp_path, "menu.js", "import { shared } from './a.js';\nimport { shared as other } from './b.js';\n")

    with pytest.raises(build_editor.BuildError, match="both declare"):
        build_editor.bundle(("menu.js",), tmp_path)


def test_a_missing_module_names_who_imported_it(tmp_path):
    write(tmp_path, "menu.js", "import { gone } from './gone.js';\n")

    with pytest.raises(build_editor.BuildError, match="menu.js"):
        build_editor.bundle(("menu.js",), tmp_path)


# --- the real thing ------------------------------------------------------

def test_the_real_modules_bundle(tmp_path):
    out = build_editor.bundle()

    assert "class ConfigMenu" in out
    assert "class ModeEditor" in out
    assert "function createField" in out
    assert not re.search(r"^import\s", out, re.MULTILINE)


def test_the_built_page_fetches_nothing(tmp_path, monkeypatch):
    """The one property that makes file:// work: a browser refuses to load an
    ES module - or any subresource - from a file URL, so there must be none."""
    monkeypatch.setattr(build_editor, "OUT", tmp_path / "button-editor.html")

    page = build_editor.build().read_text(encoding="utf-8")

    assert not re.search(r'(?:src|href)\s*=\s*"', page)
    assert not re.search(r"/\*\{\{\w+\}\}\*/", page)  # every placeholder filled


def test_the_defaults_come_from_python_not_a_second_copy(tmp_path):
    """The editor seeds a new scene from these; a hand-written JS copy would
    be a mirrored table with no test behind it."""
    from aibutton.config import AppConfig

    defaults = build_editor.default_config()

    assert set(defaults["led_palette"]) == set(AppConfig().led_palette)
    assert "scenes" not in defaults  # the pointer belongs to config.json
