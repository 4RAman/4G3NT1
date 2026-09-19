"""Build the scene gallery's manifest and shards from `scenes/library/`.

TODO **114b**. The format is not this tool's to invent: the owner settled it on
2026-09-09 by reusing **113**'s contract whole
([docs/light-library-format.md](../docs/light-library-format.md) section 7) -
an `index.json` carrying counts, **facets with counts** and a shard list, plus
one shard per group, each shard a `{format_version, group, label, part, rows}`
object. Only the *row body* changes: a scene's `title`/`blurb`/`for`/`assumes`
header and its config, where a look had `style`/`color`/`stops`.

    ./.venv/Scripts/python tools/build_scene_index.py
    ./.venv/Scripts/python tools/build_scene_index.py --dry-run
    ./.venv/Scripts/python tools/build_scene_index.py --source scenes/library --out ...

**One order of magnitude smaller, same contract.** Thirteen scenes fit in one
shard and will for a long time, and the sharding code below is still the
light library's: the point is one gallery format rather than two, and a second
format would be the thing that made a scene gallery a second page to maintain
instead of the same page with a different row.

**What is validated, and what is only reported.** A scene that cannot be read,
is not an object, or has no `title` is **rejected** - it has no gallery entry
to show. A scene that *would load with warnings* is **reported and kept**: a
warning is the parser's per-key fallback doing its job, the scene still runs,
and hiding it from the gallery would be a far worse answer than printing the
sentence. The report is the deliverable, exactly as it is for the light
library; the exit code is non-zero when anything was rejected.

**The readiness facet is not here, and cannot be.** "Does this machine have a
loopMIDI port called Button" is a fact about a machine, not about a file, so it
is answered live by the web API (`scenes.check_assumes`, probes injected in
webui.py) and merged into the same generic facet list in the browser. A static
manifest that claimed it would be lying by the time anybody read it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aibutton import scenes  # noqa: E402
from aibutton.config import parse_with_warnings  # noqa: E402

SOURCE_DIR = ROOT / "scenes" / "library"
OUT_DIR = ROOT / "aibutton" / "web" / "scene-library"

# The same number as the light library's, and the same rule: bumped when the
# *shape* changes in a way a page written against the old one would misread.
# Adding a key nothing reads is not that.
FORMAT_VERSION = 1

# One shard per group, split at this many rows. Nowhere near reachable today;
# kept because the contract has it and because the day it *is* reachable is
# not the day to discover the writer never handled it.
MAX_SHARD_ROWS = 200

# Every scene in `scenes/library/` is one group today: they are one curated
# set, and a chip row with a single chip filters nothing. The key stays in the
# manifest because that is what tells a gallery which facet the shards are
# partitioned by (lightLibrary.js's `shardFacetKey` derives it rather than
# naming it), and because a second group - shipped against a `group` key in the
# scene header - then costs no code anywhere.
DEFAULT_GROUP = "library"
GROUP_LABELS = {"library": "Scene library"}

# The `assumes` value a scene with an empty list falls into. A real bucket
# rather than an absence, because "needs nothing but the button" is the single
# most useful thing to filter *for* and there would otherwise be no chip for
# it.
NO_ASSUMPTIONS = "nothing beyond the button"


# Words a blurb is full of and nobody searches for. A short list on purpose:
# it exists to keep a checked-in file readable, not to be a stemmer, and every
# word dropped here is a word that can no longer be searched.
_STOPWORDS = frozenset("""
and are but can does for from has have not the that them they this those
what when which who whose with without you your its it's one two
""".split())


def _slug(text: str) -> str:
    """A facet value id from a plain-English phrase. Ids travel in a URL
    fragment and in `aria-pressed` state; the phrase itself stays the label,
    so nothing a person reads is ever slugified."""
    out = []
    for ch in text.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join(part for part in "".join(out).split("-") if part)[:64] or "x"


@dataclass
class Row:
    """One gallery row. The light library's `id`/`tags`/`group` frame with a
    scene's header and config as the body."""

    id: str
    group: str
    meta: scenes.SceneMeta
    config: dict
    warnings: list[str] = field(default_factory=list)

    def emit(self) -> dict:
        assume_ids = [_slug(scenes.canonical_assumption(a)) for a in self.meta.assumes]
        return {
            "id": self.id,
            "title": self.meta.title,
            "blurb": self.meta.blurb,
            # `for` is the key the scene files write and a JSON key may be a
            # Python keyword, so the wire name matches the file rather than
            # `SceneMeta.audience`. The browser reads the file's word.
            "for": self.meta.audience,
            "assumes": list(self.meta.assumes),
            "group": self.group,
            # Which facet values this row holds, by facet key - the shape
            # docs/light-library-format.md section 7 already allows for "a
            # value that would collide with the documented fields", which is
            # exactly the case here: `assumes` the field is the phrases a
            # person reads and `assumes` the facet is their slugs. Pre-slugged
            # so the browser never reimplements `_slug` to match a chip to a
            # row: the facet's id and the row's copy of it come off the same
            # line of Python.
            "facets": {
                "group": self.group,
                "assumes": assume_ids or [_slug(NO_ASSUMPTIONS)],
            },
            "modes": len(self.config.get("modes") or []),
            "tags": sorted(self._tags()),
            # The whole scene body, header stripped. It is what "Use this
            # scene" posts, so picking one is not a second fetch - and it is
            # the row *body*, exactly where a look's `style`/`stops` sit.
            "config": self.config,
            # A scene is curated by construction: somebody wrote the file.
            "curated": True,
            "warnings": self.warnings,
        }

    def _tags(self) -> set[str]:
        """What free-text search matches on. The header is the whole corpus -
        `for` in particular, which is a sentence about a person and therefore
        the thing somebody actually types ("streamer", "tabletop", "ADHD")."""
        words: set[str] = {self.id}
        blob = " ".join([
            self.id.replace("-", " "), self.meta.title, self.meta.blurb,
            self.meta.audience, " ".join(self.meta.assumes),
        ]).lower()
        for word in blob.replace("-", " ").split():
            cleaned = "".join(ch for ch in word if ch.isalnum())
            if len(cleaned) > 2 and cleaned not in _STOPWORDS:
                words.add(cleaned)
        return words


@dataclass
class Rejection:
    id: str
    kind: str
    reason: str


def read_scene(path: Path, base: dict) -> tuple[Row | None, Rejection | None]:
    """One file into a row, or a reason it cannot be one.

    Validated through the *real* parser, merged over the real base config, for
    the reason the scenes CLI's `check` exists: there is one parser, and a
    gallery that accepted something the service would not run would be a
    second opinion about what a valid scene is.
    """
    scene_id = path.stem
    raw = scenes.read_json(path)
    if raw is None:
        return None, Rejection(scene_id, "file", "not a readable JSON object")

    meta = scenes.parse_meta(raw)
    if not meta.title:
        return None, Rejection(
            scene_id, "header",
            "no 'title' - a gallery row with no name is a row nobody can pick",
        )
    if not meta.blurb:
        return None, Rejection(
            scene_id, "header",
            "no 'blurb' - the one sentence answering 'what does pressing this do'",
        )

    body = scenes.config_body(raw)
    _, warnings = parse_with_warnings(scenes.merge(base, raw))
    group = raw.get("group") if isinstance(raw.get("group"), str) else DEFAULT_GROUP
    return Row(
        id=scene_id, group=group or DEFAULT_GROUP, meta=meta, config=body,
        warnings=list(warnings),
    ), None


def facets(rows: list[Row]) -> dict:
    """The manifest's facet table - `{key: [{id, label, count}]}`.

    Two facets, both facts about the files: which shard a row is in, and what
    it assumes. **Not `for`**: it is a full sentence per scene, so a chip row
    built from it would be one chip per row and would filter nothing. It is
    searched instead (see `Row._tags`) - and if the header ever grows a closed
    `audience` key, it becomes a facet by appearing here, with no change to the
    gallery, which reads this table generically.
    """
    groups: dict[str, int] = {}
    assumes: dict[str, tuple[str, int]] = {}
    for row in rows:
        groups[row.group] = groups.get(row.group, 0) + 1
        seen = {scenes.canonical_assumption(a) for a in row.meta.assumes} or {NO_ASSUMPTIONS}
        for text in seen:
            key = _slug(text)
            label, count = assumes.get(key, (text, 0))
            assumes[key] = (label, count + 1)
    return {
        "group": [
            {"id": key, "label": GROUP_LABELS.get(key, key), "count": count}
            for key, count in sorted(groups.items())
        ],
        "assumes": [
            {"id": key, "label": label, "count": count}
            # Commonest first: the chip row reads as "what most of these need".
            for key, (label, count) in sorted(
                assumes.items(), key=lambda kv: (-kv[1][1], kv[1][0])
            )
        ],
    }


def _dumps(payload: dict) -> str:
    # Indented, unlike the light library's minified shards: thirteen scenes is
    # 40 KB, it is checked into git, and a readable diff is worth more here
    # than the bytes.
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_index(rows: list[Row], out_dir: Path, *, source: Path) -> dict:
    """`index.json` plus one shard per group. Returns the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()

    by_group: dict[str, list[Row]] = {}
    for row in rows:
        by_group.setdefault(row.group, []).append(row)

    shards = []
    for group in sorted(by_group):
        entries = sorted(by_group[group], key=lambda r: r.meta.title.lower())
        parts = [
            entries[i:i + MAX_SHARD_ROWS]
            for i in range(0, len(entries), MAX_SHARD_ROWS)
        ] or [[]]
        for number, part in enumerate(parts, start=1):
            name = f"{group}.json" if number == 1 else f"{group}-{number}.json"
            text = _dumps({
                "format_version": FORMAT_VERSION,
                "group": group,
                "label": GROUP_LABELS.get(group, group),
                "part": number,
                "rows": [row.emit() for row in part],
            })
            (out_dir / name).write_text(text, encoding="utf-8")
            shards.append({
                "file": name,
                "group": group,
                "label": GROUP_LABELS.get(group, group),
                "part": number,
                "rows": len(part),
                "bytes": len(text.encode("utf-8")),
            })

    manifest = {
        "format_version": FORMAT_VERSION,
        "generated": date.today().isoformat(),
        "generator": "tools/build_scene_index.py",
        # The light library names an inlined fallback here because schema.js
        # ships one. Scenes have none: a scene is a whole config and inlining
        # thirteen of them into the editor bundle would be the page weight the
        # format exists to avoid. Null rather than absent, so a reader can tell
        # "no fallback" from "an older manifest that never said".
        "fallback": None,
        "settings": {
            "max_shard_rows": MAX_SHARD_ROWS,
            # Posix, always: this string is read by a browser and printed in
            # a report, and a backslash in it is a Windows detail nobody asked
            # about.
            "source": (
                source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT)
                else source.as_posix()
            ),
        },
        "counts": {
            "total": len(rows),
            "curated": len(rows),
            "generated": 0,
        },
        "facets": facets(rows),
        "shards": shards,
    }
    (out_dir / "index.json").write_text(_dumps(manifest), encoding="utf-8")
    return manifest


def build(source: Path, base: dict) -> tuple[list[Row], list[Rejection]]:
    rows: list[Row] = []
    rejected: list[Rejection] = []
    seen: set[str] = set()
    for path in sorted(source.glob(f"*{scenes.SUFFIX}")):
        row, bad = read_scene(path, base)
        if bad is not None:
            rejected.append(bad)
            continue
        assert row is not None
        if row.id in seen:  # pragma: no cover - filenames are unique per dir
            rejected.append(Rejection(row.id, "duplicate", "that id was already used"))
            continue
        seen.add(row.id)
        rows.append(row)
    return rows, rejected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", default=str(SOURCE_DIR), help="the scenes to index")
    parser.add_argument("--out", default=str(OUT_DIR), help="output directory")
    parser.add_argument(
        "--config", default=str(ROOT / "config.json"),
        help="the base config a scene is validated against (it is merged over it)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.is_dir():
        print(f"no such directory: {source}")
        return 2

    base = scenes.read_json(Path(args.config)) or {}
    rows, rejected = build(source, base)

    if args.dry_run:
        manifest = {
            "counts": {"total": len(rows)},
            "facets": facets(rows),
            "shards": [],
        }
    else:
        manifest = write_index(rows, Path(args.out), source=source)

    print("scene library index")
    print(f"  read       : {len(rows) + len(rejected)} scene(s)")
    print(f"  rejected   : {len(rejected)}")
    print(f"  accepted   : {len(rows)}")
    print(
        "  assumes    : "
        + ", ".join(f"{f['label']} {f['count']}" for f in manifest["facets"]["assumes"])
    )
    shards = manifest["shards"]
    print(
        f"  written    : index.json + {len(shards)} shard(s), "
        f"{sum(s['bytes'] for s in shards) / 1024:.1f} KB"
        if shards else "  written    : nothing (--dry-run)"
    )

    noisy = [row for row in rows if row.warnings]
    if noisy:
        print(f"\nWARNINGS ({sum(len(r.warnings) for r in noisy)}) - these scenes still ship")
        for row in noisy:
            for line in row.warnings:
                print(f"  {row.id:<18} {line}")
    if rejected:
        print(f"\nREJECTED ({len(rejected)})")
        for bad in rejected:
            print(f"  {bad.id:<18} {bad.kind:<9} {bad.reason}")
    return 1 if rejected else 0


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    raise SystemExit(main())
