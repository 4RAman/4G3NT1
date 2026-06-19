from datetime import UTC, datetime, timedelta

from aibutton.store import EventStore


def _insert(store, kind, name, days_ago=0, duration_s=None):
    """Back-date a row by writing directly to the DB (log_event/toggle_timer
    always use "now")."""
    local_point = (
        datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
        - timedelta(days=days_ago)
    )
    ts = local_point.astimezone(UTC).isoformat()
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


def test_count_today_sums_increments(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.log_event("water")            # +1
    store.log_event("water", count=10)  # +10
    store.log_event("water", count=20)  # +20
    assert store.count_today("water") == 31
    # recorded as three rows, not 31 of them
    assert len(store.recent()) == 3
    store.close()


def test_count_column_migrated_onto_old_db(tmp_path):
    """A DB created before the count column still loads, and pre-existing
    log rows read back as +1 each."""
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "ts TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, duration_s REAL)"
    )
    conn.execute(
        "INSERT INTO events (ts, kind, name) VALUES (?, 'log', 'water')",
        (datetime.now(UTC).isoformat(),),
    )
    conn.commit()
    conn.close()

    store = EventStore(str(path))
    assert store.count_today("water") == 1  # legacy row counts as +1
    store.log_event("water", count=5)
    assert store.count_today("water") == 6
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
