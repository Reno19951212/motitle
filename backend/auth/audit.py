"""SQLite-backed audit log for Phase 3 admin actions."""
import json
import sqlite3
import time
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  actor_user_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  target_kind TEXT,
  target_id TEXT,
  details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id);
"""


def init_audit_log(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def log_audit(
    db_path: str,
    actor_id: int,
    action: str,
    target_kind: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_log (ts, actor_user_id, action, target_kind, target_id, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                time.time(),
                actor_id,
                action,
                target_kind,
                str(target_id) if target_id is not None else None,
                json.dumps(details) if details is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit(
    db_path: str,
    limit: int = 100,
    actor_id: Optional[int] = None,
) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if actor_id is not None:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE actor_user_id = ? "
                "ORDER BY ts DESC LIMIT ?",
                (actor_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "actor_user_id": r["actor_user_id"],
                "action": r["action"],
                "target_kind": r["target_kind"],
                "target_id": r["target_id"],
                "details": json.loads(r["details_json"]) if r["details_json"] else None,
            }
            for r in rows
        ]
    finally:
        conn.close()
