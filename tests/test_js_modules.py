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
