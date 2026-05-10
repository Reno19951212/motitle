"""Phase 5 T2.3 — all SQLite databases initialized with WAL mode."""
import sqlite3
import pytest


def _journal_mode(p: str) -> str:
    conn = sqlite3.connect(p)
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
    finally:
        conn.close()


def test_jobs_db_uses_wal(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    assert _journal_mode(p) == "wal"


def test_users_db_uses_wal(tmp_path):
    from auth.users import init_db
    p = str(tmp_path / "u.db")
    init_db(p)
    assert _journal_mode(p) == "wal"


def test_audit_db_uses_wal(tmp_path):
    from auth.audit import init_audit_log
    p = str(tmp_path / "a.db")
    init_audit_log(p)
    assert _journal_mode(p) == "wal"
