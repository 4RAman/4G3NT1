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
    mode TEXT                    -- which mode was active when this fired
)
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


class EventStore:
    def __init__(self, path: str):
        db_path = Path(path)
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._migrate()
        self._conn.commit()
        log.info("event store at %s", db_path)

    def _migrate(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` only helps a brand-new file - an
        existing events.db predating the `mode` column needs it added by
        hand, or every insert below fails against the old schema."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(events)")}
        if "mode" not in columns:
            self._conn.execute("ALTER TABLE events ADD COLUMN mode TEXT")

    def log_event(self, name: str, mode: str | None = None) -> datetime:
        now = _utcnow()
        self._conn.execute(
            "INSERT INTO events (ts, kind, name, mode) VALUES (?, 'log', ?, ?)",
            (now.isoformat(), name, mode),
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

    def recent(self, limit: int = 50) -> list[tuple]:
        """Newest-first (ts, kind, name, duration_s, mode) rows - backs the
        web UI's Events tab."""
        return self._conn.execute(
            "SELECT ts, kind, name, duration_s, mode FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def close(self) -> None:
        self._conn.close()
