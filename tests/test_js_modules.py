"""Run the JavaScript unit tests, if this machine can.

Half this app is JavaScript and none of it had a unit test. The Python tests
next door check *mirrors* - that a table declared twice says the same thing on
both sides - which is the right tool for drift and no tool at all for logic.
The Events page's aggregations (TODO 53) are logic: which rows count, which
would be counted twice, what "today" means to someone who is not on UTC. Those
are pure functions over data, exactly like `rules.py`, and they deserve the
same kind of table-driven test.

**No new dependency, and none is possible.** `node --test` has been built into
Node since v18: no runner, no config, no package.json. And node is *optional* -
absent, this skips with a reason rather than failing, so the suite still runs
green on a machine that has only Python. CLAUDE.md's rule is about what the
service runs on; nothing here ships with it.

The JavaScript half lives in tests/js/. Only pure functions are exercised
there - anything touching the DOM is verified in a browser, which is the
honest split rather than a gap.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_TESTS = ROOT / "tests" / "js"
STATIC = ROOT / "aibutton" / "web" / "static"

# Every .test.mjs, named individually rather than handed to node as a
# directory: `node --test <dir>` resolves the path as a module on Windows and
# dies with MODULE_NOT_FOUND, which reads as a broken test rather than as the
# argument-shape problem it is.
TEST_FILES = sorted(p.name for p in JS_TESTS.glob("*.test.mjs"))

node = shutil.which("node")
needs_node = pytest.mark.skipif(
    node is None,
    reason="node is not installed - the JavaScript tests are optional, and "
           "nothing the service runs needs it",
)


def test_the_javascript_tests_are_still_being_collected():
    """Guards the skip above from becoming permanent silence: if the files are
    renamed or moved, this fails on every machine rather than the suite quietly
    testing no JavaScript at all."""
    assert TEST_FILES, "no *.test.mjs found in tests/js"


@needs_node
@pytest.mark.parametrize("name", TEST_FILES)
def test_javascript_module(name):
    result = subprocess.run(
        [node, "--test", str(JS_TESTS / name)],
        capture_output=True, text=True, cwd=ROOT,
    )
    # node --test prints TAP-ish output; on failure it is the only useful
    # thing, so it goes into the assertion rather than being swallowed.
    assert result.returncode == 0, (
        f"{name} failed:\n{result.stdout}\n{result.stderr}"
    )


# --- does it even parse? ----------------------------------------------------
# Cheaper than any test here and it caught nothing for the same reason it was
# never written: the modules with logic are imported by tests/js, and the rest
# are only ever parsed by a browser. A stray apostrophe in a hint string in
# schema.js broke the whole editor with one console line and no failing test.


@needs_node
@pytest.mark.parametrize("name", sorted(p.name for p in STATIC.glob("*.js")))
def test_a_static_module_parses(name, tmp_path):
    """Every browser module is valid ES, checked as ES.

    **`node --check` on a `.js` file is not this check.** With no package.json
    saying otherwise node treats the file as ambiguous, and a real syntax error
    exits 0 - which is how a schema.js that could not load passed its check.
    The extension is what decides the parser, so the file is copied to `.mjs`
    first. Copied rather than renamed: these are the files the service serves.
    """
    target = tmp_path / (Path(name).stem + ".mjs")
    target.write_bytes((STATIC / name).read_bytes())
    result = subprocess.run(
        [node, "--check", str(target)], capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{name} does not parse:\n{result.stderr}"
