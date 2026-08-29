"""An app's durable named values - its *document* (TODO 34, ROADMAP D9).

The event log can only append. A counter's number is recounted from rows, a
signal light's position dies when it exits, and *"set this to 3"* is not
expressible at all. ARCHITECTURE.md's "Apps own data" settles that: an app
instance may own **a small bounded bag of named values, alongside the log and
never instead of it**.

Three rules, and each one is load-bearing rather than tidy:

- **Bounded by construction.** Slots are declared per template
  (`config.DOC_SLOTS`, the manifest's precursor), so a document's size is
  fixed before it holds anything. No growth, no collections, no nesting - the
  same line the app runtime draws, applied to storage. This module enforces
  nothing about *which* slots exist, because it cannot see the config; the
  parser and the action's allow-list do that, and what is enforced here is the
  shape of a value.
- **The log stays separate.** History and current value are different jobs: a
  log cannot answer "what is it now" without a scan, and a document cannot
  answer "what happened in March" at all. An app that writes here usually
  writes a row too, and neither is derived from the other.
- **It lives outside any app's run loop**, which is the whole point of the
  `set_value` action: a gesture in Home can add one to the Counter's tally
  without entering the Counter (TODO 15).

Values are scalars only - a float, a string or a bool - for the reason
[summary.py](summary.py) allows the same three: anything richer is a schema,
and a schema is a thing that has to be migrated on a device nobody can reach.

Same file as the event log, its own table. One more table in a database the
service already opens beats a second file to back up, lose, or find missing.

**Keyed by the mode's name, which is the only handle a config has** - modes
have no id yet, and inventing one here would be inventing half the manifest
(ARCHITECTURE.md, Stage 3). The cost is stated rather than hidden: renaming an
app in the editor is a new document, so a durable counter renamed reads its
default again. There is no rename *event* to follow - the name is a text box
somebody types in - so the fix is app ids, not a callback.
"""

from __future__ import annotations

import logging
import sqlite3

from .store import open_database

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    app TEXT NOT NULL,           -- the mode's name: one document per instance
    slot TEXT NOT NULL,          -- declared in config.DOC_SLOTS per template
    value,                       -- REAL, TEXT or INTEGER; see Scalar below
    PRIMARY KEY (app, slot)
)
"""

# What a slot may hold. `bool` before `int` matters nowhere here (sqlite stores
# both as INTEGER) but the read path restores it, so a flag comes back a flag.
Scalar = float | int | str | bool

# A ceiling on how many slots one app may actually occupy, enforced on write.
# The declared slots are already the real bound; this is the backstop for the
# case the declaration is wrong or an old row was left behind by a rename, and
# it exists for the reason `summary.MAX_KEYS` does - a rule each caller is
# trusted to remember is a rule that drifts.
MAX_SLOTS = 16


def _clean(value):
    """A value the store will accept, or None with a complaint logged.

    Rejecting rather than coercing: a dict silently stored as its `repr` is a
    value that reads back wrong forever, and the caller can always send a
    number.
    """
    if isinstance(value, bool) or isinstance(value, (int, float, str)):
        return value
    log.warning(
        "document: %r is not a number, a word or a flag - not stored",
        type(value).__name__,
    )
    return None


class DocumentStore:
    """The documents table, keyed by `(app, slot)`.

    Fails soft the way [store.py](store.py) does: a database that cannot be
    opened degrades to memory rather than stopping the button, because a
    button that will not press because its notebook is unwritable is the wrong
    trade.
    """

    def __init__(self, path: str):
        self.path = path
        self.degraded = False
        try:
            self._conn = open_database(path, _SCHEMA)
        except (sqlite3.Error, OSError) as exc:
            log.error(
                "documents: cannot open %s (%s) - keeping values in memory "
                "only, they will be lost on exit", path, exc,
            )
            self.degraded = True
            self._conn = open_database(":memory:", _SCHEMA)

    def get(self, app: str, slot: str, default: Scalar = 0.0) -> Scalar:
        """What `app` has in `slot`, or `default` if it has never written one.

        `default` rather than None so a caller never has to branch on "first
        run": a slot's declared default is the value it has until something
        sets it, which is what makes a document readable like a variable.
        """
        row = self._conn.execute(
            "SELECT value FROM documents WHERE app = ? AND slot = ?", (app, slot),
        ).fetchone()
        if row is None:
            return default
        # A bool went in as 0/1 and comes back as an int; the declared default
        # is the only thing that still knows which it was.
        if isinstance(default, bool):
            return bool(row[0])
        return row[0]

    def set(self, app: str, slot: str, value: Scalar) -> Scalar | None:
        """Write `slot`, returning what was stored (None if it was refused)."""
        value = _clean(value)
        if value is None:
            return None
        if not self._has_room(app, slot):
            return None
        self._conn.execute(
            "INSERT INTO documents (app, slot, value) VALUES (?, ?, ?) "
            "ON CONFLICT(app, slot) DO UPDATE SET value = excluded.value",
            (app, slot, value),
        )
        self._conn.commit()
        return value

    def add(self, app: str, slot: str, delta: float, default: float = 0.0):
        """`slot += delta`, returning the new value - the operation the whole
        feature exists for ("Smoking +1" from a gesture in Home).

        Read-then-write rather than SQL arithmetic because the slot may not
        exist yet and because a non-numeric slot has to be refused rather than
        silently becoming a number. One process holds one connection, so there
        is no second writer to race with.
        """
        current = self.get(app, slot, default)
        if isinstance(current, str):
            log.warning(
                "document: %s.%s holds text, so it cannot be added to", app, slot,
            )
            return None
        return self.set(app, slot, float(current) + float(delta))

    def all(self, app: str) -> dict[str, Scalar]:
        """Everything `app` has written, for the page that shows it."""
        return {
            slot: value
            for slot, value in self._conn.execute(
                "SELECT slot, value FROM documents WHERE app = ? ORDER BY slot",
                (app,),
            )
        }

    def everything(self) -> dict[str, dict[str, Scalar]]:
        """Every app's document. What `GET /api/documents` answers with, and
        the only reader that wants the whole table."""
        out: dict[str, dict[str, Scalar]] = {}
        for app, slot, value in self._conn.execute(
            "SELECT app, slot, value FROM documents ORDER BY app, slot"
        ):
            out.setdefault(app, {})[slot] = value
        return out

    def clear(self, app: str, slot: str | None = None) -> int:
        """Forget one slot, or the app's whole document. Returns rows removed.

        Deleting rather than writing the default back, so "never set" and
        "set back to its default" stay the same state - there is nothing in
        this design that can tell them apart, and pretending otherwise would
        invent a distinction the on-device runtime cannot carry.
        """
        if slot is None:
            cur = self._conn.execute("DELETE FROM documents WHERE app = ?", (app,))
        else:
            cur = self._conn.execute(
                "DELETE FROM documents WHERE app = ? AND slot = ?", (app, slot),
            )
        self._conn.commit()
        return cur.rowcount

    def _has_room(self, app: str, slot: str) -> bool:
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM documents WHERE app = ? AND slot != ?", (app, slot),
        ).fetchone()
        if count < MAX_SLOTS:
            return True
        log.warning(
            "document: %r already holds %d values, which is the limit - %r "
            "not stored", app, count, slot,
        )
        return False

    def close(self) -> None:
        self._conn.close()
