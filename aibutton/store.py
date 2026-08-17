"""SQLite event log backing the `log` and `timer_toggle` actions.

stdlib sqlite3, no extra dependency. Writes are sub-millisecond on the
Pi's SD card at this volume (a few rows per day), so calls run inline on
the event loop. Timer state is derived from the log itself (last
start/stop row per timer name), so timers survive service restarts.

Timestamps are stored as UTC ISO-8601; render in local time at display.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,          -- 'log' | 'timer_start' | 'timer_stop'
                                  -- | 'mode_enter' | 'mode_exit'
    name TEXT NOT NULL,
    duration_s REAL,             -- set on 'timer_stop' / 'mode_exit' rows
    mode TEXT,                   -- which mode was active when this fired
    value REAL                   -- a number this event carried; see below
)
"""

# `value` is deliberately one untyped numeric slot rather than a column per
# app. A metronome session's BPM, a counter's tally, a lap number and a sensor
# reading are all "the number this press produced", and the two alternatives
# are worse: a column each does not survive third-party apps, and folding the
# number into `name` breaks count_today/current_streak, which group by exactly
# that string. What a value *means* is read off `name` and `kind`, the same way
# `duration_s` already means different things on a timer_stop and a mode_exit.
#
# NULL is the normal case: most events are the fact that something happened.


_MEMORY = ":memory:"
# How long a write waits on a competing writer before raising "database is
# locked". One process holds one connection, so contention means something
# else has the file open - a stale copy of the service, or a DB browser.
# Waiting a few seconds beats failing a press over a transient lock.
_BUSY_TIMEOUT_S = 5.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _like_escape(text: str) -> str:
    """Neutralise LIKE's own wildcards in a user's search text.

    Without this, searching for `100%` matches every row - the string is bound
    safely (so this is not an injection question), but `%` and `_` still mean
    something to LIKE, and a search box that quietly treats them as operators
    surprises people."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _local_day_bounds_utc() -> tuple[str, str]:
    """UTC ISO bounds [start, end) of "today" in the system's local
    timezone - ts is stored as UTC, but "today" means the Pi's wall
    clock, same as rule resolution."""
    local_midnight = datetime.now().astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = local_midnight.astimezone(timezone.utc)
    end = (local_midnight + timedelta(days=1)).astimezone(timezone.utc)
    return start.isoformat(), end.isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    """`CREATE TABLE IF NOT EXISTS` only helps a brand-new file - an
    existing events.db predating a column needs it added by hand, or every
    insert below fails against the old schema.

    Each column is added independently, so a database from any earlier
    version catches up in one pass rather than only the most recent one."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "mode" not in columns:
        conn.execute("ALTER TABLE events ADD COLUMN mode TEXT")
    if "value" not in columns:
        conn.execute("ALTER TABLE events ADD COLUMN value REAL")


def _connect(path: str) -> sqlite3.Connection:
    """Open (creating the directory if needed), apply the schema, migrate."""
    target: str | Path = path
    if path != _MEMORY:
        db_path = Path(path)
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        target = db_path
    conn = sqlite3.connect(target, timeout=_BUSY_TIMEOUT_S)
    conn.execute(_SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


class EventStore:
    def __init__(self, path: str):
        self.path = path
        # True when the on-disk database could not be opened and history is
        # being kept in memory instead. Read by the web UI so a degraded log
        # is visible rather than silently empty.
        self.degraded = False
        try:
            self._conn = _connect(path)
        except (sqlite3.Error, OSError) as exc:
            # A button that refuses to start because its logbook is
            # unwritable is the wrong trade - pressing it still has to do
            # something. Fall back to an in-memory log and say so loudly.
            log.error(
                "event store: cannot open %s (%s) - logging to memory only, "
                "history will be lost on exit",
                path, exc,
            )
            self.degraded = True
            self._conn = _connect(_MEMORY)
        log.info("event store at %s", _MEMORY if self.degraded else path)

    def log_event(
        self, name: str, mode: str | None = None, value: float | None = None
    ) -> datetime:
        """Record that `name` happened. `value` is an optional number the
        event carried (see the note on the schema above) - counts and streaks
        ignore it, so adding one never changes what an existing event means."""
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO events (ts, kind, name, mode, value) VALUES (?, 'log', ?, ?, ?)",
            (now.isoformat(), name, mode, value),
        )
        self._conn.commit()
        return now

    def count_today(self, name: str) -> int:
        """Number of `log` events named `name` since local midnight
        (inclusive of one just written) - for habit counters."""
        start, end = _local_day_bounds_utc()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE kind = 'log' AND name = ? AND ts >= ? AND ts < ?",
            (name, start, end),
        ).fetchone()
        return row[0]

    def logged_today(self, name: str) -> bool:
        """Whether a `log` event named `name` has happened since local
        midnight - backs the `unless_logged_today` rule condition."""
        return self.count_today(name) > 0

    def current_streak(self, name: str) -> int:
        """Consecutive local days (most recent first) with at least one
        `log` event named `name`. A gap before today/yesterday breaks
        the streak (returns 0); yesterday-only keeps it "alive" until
        today ends."""
        rows = self._conn.execute(
            "SELECT ts FROM events WHERE kind = 'log' AND name = ?",
            (name,),
        ).fetchall()
        if not rows:
            return 0
        days = {datetime.fromisoformat(ts).astimezone().date() for (ts,) in rows}
        today = datetime.now().astimezone().date()
        expected = today if today in days else today - timedelta(days=1)
        if expected not in days:
            return 0
        streak = 0
        while expected in days:
            streak += 1
            expected -= timedelta(days=1)
        return streak

    def total_today(self, name: str) -> float:
        """Sum of `duration_s` for `timer_stop` events named `name`
        since local midnight - Pomodoro/focus-time daily totals."""
        start, end = _local_day_bounds_utc()
        row = self._conn.execute(
            "SELECT COALESCE(SUM(duration_s), 0) FROM events "
            "WHERE kind = 'timer_stop' AND name = ? AND ts >= ? AND ts < ?",
            (name, start, end),
        ).fetchone()
        return row[0]

    def toggle_timer(self, name: str, mode: str | None = None) -> tuple[str, float | None]:
        """Returns ("started", None) or ("stopped", elapsed_seconds)."""
        row = self._conn.execute(
            "SELECT ts, kind FROM events WHERE name = ? AND kind IN "
            "('timer_start', 'timer_stop') ORDER BY id DESC LIMIT 1",
            (name,),
        ).fetchone()
        now = _utcnow()
        if row is not None and row[1] == "timer_start":
            elapsed = (now - datetime.fromisoformat(row[0])).total_seconds()
            self._conn.execute(
                "INSERT INTO events (ts, kind, name, duration_s, mode) "
                "VALUES (?, 'timer_stop', ?, ?, ?)",
                (now.isoformat(), name, elapsed, mode),
            )
            self._conn.commit()
            return "stopped", elapsed
        self._conn.execute(
            "INSERT INTO events (ts, kind, name, mode) VALUES (?, 'timer_start', ?, ?)",
            (now.isoformat(), name, mode),
        )
        self._conn.commit()
        return "started", None

    def log_mode_enter(self, mode_name: str) -> datetime:
        """Record a takeover mode taking over the button - pair with
        `log_mode_exit` (passed the datetime this returns) when it lets go."""
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO events (ts, kind, name, mode) VALUES (?, 'mode_enter', ?, ?)",
            (now.isoformat(), mode_name, mode_name),
        )
        self._conn.commit()
        return now

    def log_mode_exit(self, mode_name: str, entered_at: datetime) -> float:
        """Record a takeover mode handing the button back. Returns the
        session length in seconds."""
        now = _utcnow()
        elapsed = (now - entered_at).total_seconds()
        self._conn.execute(
            "INSERT INTO events (ts, kind, name, duration_s, mode) "
            "VALUES (?, 'mode_exit', ?, ?, ?)",
            (now.isoformat(), mode_name, elapsed, mode_name),
        )
        self._conn.commit()
        return elapsed

    def recent(
        self,
        limit: int = 50,
        kind: str | None = None,
        name: str | None = None,
        mode: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[tuple]:
        """Newest-first (ts, kind, name, duration_s, mode, value) rows - backs
        the web UI's Events tab.

        `value` is appended rather than slotted in beside the other nullable
        columns so existing positional reads keep meaning what they meant.

        Every filter is optional and they combine with AND, which is what a
        filter bar means by having several boxes filled in. `name` is a
        substring match because you search a log for "coff" and expect to find
        "coffee"; `kind` and `mode` are exact, because those come from a
        fixed list and a substring match on them would be a way to select the
        wrong thing by accident.

        `since`/`until` are UTC ISO strings compared as text. That works
        because `ts` is stored as UTC ISO-8601, where lexical order *is*
        chronological order - the property that makes a string column usable
        as a timeline, and the reason the format is not negotiable.

        Fragments are assembled, values are always bound. The one rule here:
        nothing a caller supplies is ever interpolated into the SQL.
        """
        where: list[str] = []
        params: list[object] = []
        if kind:
            where.append("kind = ?")
            params.append(kind)
        if name:
            where.append("name LIKE ? ESCAPE '\\'")
            params.append(f"%{_like_escape(name)}%")
        if mode:
            where.append("mode = ?")
            params.append(mode)
        if since:
            where.append("ts >= ?")
            params.append(since)
        if until:
            where.append("ts < ?")
            params.append(until)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        return self._conn.execute(
            "SELECT ts, kind, name, duration_s, mode, value "
            f"FROM events{clause} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()

    def kinds(self) -> list[str]:
        """Every `kind` present in the log, so the filter's picker offers what
        is actually there rather than a hard-coded list that drifts as new
        event kinds appear."""
        return [row[0] for row in self._conn.execute(
            "SELECT DISTINCT kind FROM events ORDER BY kind"
        )]

    def close(self) -> None:
        self._conn.close()
