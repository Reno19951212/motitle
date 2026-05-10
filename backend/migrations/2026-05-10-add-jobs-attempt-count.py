"""Phase 5 T1.5 — add attempt_count column to existing jobs table.

Idempotent: safe to re-run on databases that already have the column.
``init_jobs_table`` also runs the same ALTER on boot, so this script is
mainly for operators who want to verify the migration succeeded against a
specific database file outside the normal startup path.

Usage:
    python backend/migrations/2026-05-10-add-jobs-attempt-count.py [DB_PATH]
"""
import sqlite3
import sys


def migrate(db_path: str) -> bool:
    """Returns True if the column was added, False if already present."""
    conn = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "attempt_count" in cols:
            return False
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1"
        )
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "backend/data/app.db"
    added = migrate(p)
    print(f"{'Added' if added else 'Already present'}: jobs.attempt_count in {p}")
