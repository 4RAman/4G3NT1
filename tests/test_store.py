import sqlite3
from datetime import datetime, timedelta, timezone

from aibutton.store import EventStore


def _insert(store, kind, name, days_ago=0, duration_s=None):
    """Back-date a row by writing directly to the DB (log_event/toggle_timer
    always use "now")."""
    local_point = (
        datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
        - timedelta(days=days_ago)
    )
    ts = local_point.astimezone(timezone.utc).isoformat()
    store._conn.execute(
        "INSERT INTO events (ts, kind, name, duration_s) VALUES (?, ?, ?, ?)",
        (ts, kind, name, duration_s),
    )
    store._conn.commit()


def test_log_event(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    ts = store.log_event("meds_taken")
    rows = store.recent()
    assert len(rows) == 1
    assert rows[0][1] == "log"
    assert rows[0][2] == "meds_taken"
    assert rows[0][0] == ts.isoformat()
    store.close()


def test_timer_toggle_pairs(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    state, elapsed = store.toggle_timer("deep_work")
    assert (state, elapsed) == ("started", None)
    state, elapsed = store.toggle_timer("deep_work")
    assert state == "stopped"
    assert elapsed is not None and elapsed >= 0
    # next toggle starts a fresh pair
    state, _ = store.toggle_timer("deep_work")
    assert state == "started"
    store.close()


def test_timers_are_independent_per_name(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    assert store.toggle_timer("a")[0] == "started"
    assert store.toggle_timer("b")[0] == "started"
    assert store.toggle_timer("a")[0] == "stopped"
    assert store.toggle_timer("b")[0] == "stopped"
    store.close()


def test_timer_state_survives_restart(tmp_path):
    path = str(tmp_path / "events.db")
    store = EventStore(path)
    assert store.toggle_timer("focus")[0] == "started"
    store.close()

    reopened = EventStore(path)
    state, elapsed = reopened.toggle_timer("focus")
    assert state == "stopped"
    assert elapsed is not None
    reopened.close()


def test_creates_parent_directory(tmp_path):
    store = EventStore(str(tmp_path / "nested" / "dir" / "events.db"))
    store.log_event("x")
    store.close()
    assert (tmp_path / "nested" / "dir" / "events.db").exists()


def test_count_today(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("pushups")
    store.log_event("pushups")
    store.log_event("situps")
    assert store.count_today("pushups") == 2
    assert store.count_today("situps") == 1
    assert store.count_today("nonexistent") == 0
    store.close()


def test_count_today_ignores_other_days(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    _insert(store, "log", "pushups", days_ago=1)
    store.log_event("pushups")
    assert store.count_today("pushups") == 1
    store.close()


def test_logged_today(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    assert store.logged_today("meds_taken") is False
    store.log_event("meds_taken")
    assert store.logged_today("meds_taken") is True
    store.close()


def test_current_streak_no_events(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    assert store.current_streak("pushups") == 0
    store.close()


def test_current_streak_consecutive_days(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    _insert(store, "log", "pushups", days_ago=2)
    _insert(store, "log", "pushups", days_ago=1)
    store.log_event("pushups")  # today
    assert store.current_streak("pushups") == 3
    store.close()


def test_current_streak_yesterday_still_counts(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    _insert(store, "log", "pushups", days_ago=2)
    _insert(store, "log", "pushups", days_ago=1)
    # nothing logged today yet -- a streak through yesterday is still "alive"
    assert store.current_streak("pushups") == 2
    store.close()


def test_current_streak_broken_by_gap(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    _insert(store, "log", "pushups", days_ago=5)
    store.log_event("pushups")  # today
    assert store.current_streak("pushups") == 1
    store.close()


def test_total_today(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    _insert(store, "timer_stop", "focus", days_ago=0, duration_s=600)
    _insert(store, "timer_stop", "focus", days_ago=0, duration_s=900)
    _insert(store, "timer_stop", "focus", days_ago=1, duration_s=1200)
    assert store.total_today("focus") == 1500
    assert store.total_today("break") == 0
    store.close()


# --- the mode column -----------------------------------------------------

def test_log_event_records_mode(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("meds_taken", mode="Default")
    row = store.recent()[0]
    assert row == (row[0], "log", "meds_taken", None, "Default", None)
    store.close()


def test_log_event_mode_defaults_to_none(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("meds_taken")
    assert store.recent()[0][4] is None
    store.close()


def test_toggle_timer_records_mode_on_both_rows(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.toggle_timer("focus", mode="Default")
    store.toggle_timer("focus", mode="Default")
    rows = store.recent()
    assert [r[4] for r in rows] == ["Default", "Default"]
    store.close()


def test_migration_adds_mode_column_to_an_existing_db(tmp_path):
    """A DB written by the pre-`mode` schema must open cleanly and keep its
    old rows readable, with `mode` coming back as NULL for them."""
    path = tmp_path / "events.db"
    old_schema = """
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        duration_s REAL
    )
    """
    conn = sqlite3.connect(path)
    conn.execute(old_schema)
    conn.execute(
        "INSERT INTO events (ts, kind, name) VALUES (?, 'log', 'legacy')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()

    store = EventStore(str(path))
    try:
        rows = store.recent()
        assert rows[0][2] == "legacy"
        assert rows[0][4] is None  # no mode recorded before the migration
        store.log_event("fresh", mode="Default")  # new inserts still work
        assert store.recent()[0][4] == "Default"
    finally:
        store.close()


# --- the value column ----------------------------------------------------

def test_log_event_records_a_value(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("metronome", mode="Tempo", value=128.5)
    assert store.recent()[0][5] == 128.5
    store.close()


def test_a_value_is_optional_and_absent_by_default(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("meds_taken")
    assert store.recent()[0][5] is None
    store.close()


def test_a_value_does_not_change_what_an_event_counts_as(tmp_path):
    """Counts and streaks group by name, so attaching a number to an event
    must not split it into its own bucket - otherwise every app that starts
    logging a value silently breaks its own history."""
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("pushups")
    store.log_event("pushups", value=20)
    store.log_event("pushups", value=25)
    assert store.count_today("pushups") == 3
    assert store.current_streak("pushups") == 1
    store.close()


def test_migration_adds_the_value_column_to_a_db_that_only_has_mode(tmp_path):
    """The realistic upgrade: a database already migrated once, for `mode`,
    now needing `value` as well."""
    path = tmp_path / "events.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            duration_s REAL,
            mode TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO events (ts, kind, name, mode) VALUES (?, 'log', 'legacy', 'Default')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()

    store = EventStore(str(path))
    try:
        assert store.recent()[0][5] is None  # nothing recorded a value before
        store.log_event("fresh", value=3)
        assert store.recent()[0][5] == 3
    finally:
        store.close()


def test_migration_catches_up_a_database_missing_both_columns(tmp_path):
    """Columns are added independently, so the oldest schema reaches the
    newest in one open rather than one version per open."""
    path = tmp_path / "events.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            duration_s REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO events (ts, kind, name) VALUES (?, 'log', 'ancient')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()

    store = EventStore(str(path))
    try:
        row = store.recent()[0]
        assert (row[2], row[4], row[5]) == ("ancient", None, None)
        store.log_event("fresh", mode="Default", value=42)
        assert store.recent()[0][4:] == ("Default", 42)
    finally:
        store.close()


# --- takeover mode lifecycle ----------------------------------------------

def test_mode_enter_then_exit_records_duration(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    entered_at = store.log_mode_enter("Focus")
    elapsed = store.log_mode_exit("Focus", entered_at)
    assert elapsed >= 0
    rows = store.recent()
    exit_row, enter_row = rows[0], rows[1]
    assert (enter_row[1], enter_row[2], enter_row[4]) == ("mode_enter", "Focus", "Focus")
    assert enter_row[3] is None  # no duration on entry
    assert (exit_row[1], exit_row[2], exit_row[4]) == ("mode_exit", "Focus", "Focus")
    assert exit_row[3] == elapsed
    store.close()
