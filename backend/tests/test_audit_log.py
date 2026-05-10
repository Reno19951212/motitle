"""Phase 3B — audit_log SQLite table + helper."""
import pytest


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "audit.db")


def test_init_audit_log_creates_table(db_path):
    from auth.audit import init_audit_log
    import sqlite3
    init_audit_log(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_log_audit_inserts_row(db_path):
    from auth.audit import init_audit_log, log_audit, list_audit
    init_audit_log(db_path)
    log_audit(db_path, actor_id=1, action="user.create",
              target_kind="user", target_id="42",
              details={"username": "bob"})
    rows = list_audit(db_path)
    assert len(rows) == 1
    assert rows[0]["action"] == "user.create"
    assert rows[0]["target_id"] == "42"
    # details stored as JSON string; helper returns parsed dict
    assert rows[0]["details"]["username"] == "bob"


def test_list_audit_orders_newest_first(db_path):
    import time
    from auth.audit import init_audit_log, log_audit, list_audit
    init_audit_log(db_path)
    log_audit(db_path, actor_id=1, action="a"); time.sleep(0.01)
    log_audit(db_path, actor_id=1, action="b"); time.sleep(0.01)
    log_audit(db_path, actor_id=1, action="c")
    rows = list_audit(db_path, limit=10)
    actions = [r["action"] for r in rows]
    assert actions == ["c", "b", "a"]


def test_list_audit_filter_by_actor(db_path):
    from auth.audit import init_audit_log, log_audit, list_audit
    init_audit_log(db_path)
    log_audit(db_path, actor_id=1, action="a")
    log_audit(db_path, actor_id=2, action="b")
    rows = list_audit(db_path, actor_id=2)
    assert len(rows) == 1
    assert rows[0]["action"] == "b"
