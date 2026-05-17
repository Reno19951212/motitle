"""SQLite-backed jobs table CRUD."""
import json
import sqlite3
import time
import uuid
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  file_id TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('asr', 'translate', 'render', 'pipeline_run')),
  status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  error_msg TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 1,  -- R5 Phase 5 T1.5: poison-pill cap
  payload TEXT  -- v4 A1: JSON blob for pipeline_run {pipeline_id, file_id}
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_jobs_table(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    # R5 Phase 5 T2.3: WAL allows concurrent reads while a worker writes.
    # synchronous=NORMAL trades a tiny crash-recovery window for ~2x write
    # throughput, which is fine for our queue / audit workload.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=memory")

    # Column backfills — ALTER TABLE ADD COLUMN is idempotent-safe because we
    # check cols before altering.
    # R5 Phase 5 T1.5: backfill attempt_count.
    # v4 A1: backfill payload for pipeline_run jobs.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "attempt_count" not in cols:
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1"
        )
    if "payload" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN payload TEXT")

    # v4 A1: Migrate CHECK constraint to include 'pipeline_run'.
    # SQLite does not support ALTER TABLE … MODIFY CONSTRAINT. The only safe
    # path is a 4-step table-rebuild: rename → create-new → copy → drop-old.
    # We detect whether migration is needed by inspecting the CREATE TABLE DDL
    # stored in sqlite_master.
    ddl_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    if ddl_row and "pipeline_run" not in ddl_row[0]:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        conn.execute("ALTER TABLE jobs RENAME TO _jobs_old")
        conn.execute("""
            CREATE TABLE jobs (
              id TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              file_id TEXT NOT NULL,
              type TEXT NOT NULL CHECK(type IN ('asr', 'translate', 'render', 'pipeline_run')),
              status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
              created_at REAL NOT NULL,
              started_at REAL,
              finished_at REAL,
              error_msg TEXT,
              attempt_count INTEGER NOT NULL DEFAULT 1,
              payload TEXT
            )
        """)
        conn.execute("""
            INSERT INTO jobs (id, user_id, file_id, type, status, created_at,
                              started_at, finished_at, error_msg, attempt_count)
            SELECT id, user_id, file_id, type, status, created_at,
                   started_at, finished_at, error_msg,
                   COALESCE(attempt_count, 1)
            FROM _jobs_old
        """)
        conn.execute("DROP TABLE _jobs_old")
        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys=ON")

    conn.commit()
    conn.close()


_VALID_JOB_TYPES = ("pipeline_run",)


def insert_job(db_path: str, user_id: int, file_id: str, job_type: str,
               parent_job_id: Optional[str] = None,
               payload: Optional[dict] = None) -> str:
    """Insert a queued job. If `parent_job_id` is given (re-enqueue from
    boot recovery), inherit attempt_count + 1 from the parent so the
    poison-pill cap can stop re-enqueue loops.

    v4 A1: optional `payload` dict is serialised as JSON and stored in the
    payload column.  Used by pipeline_run jobs to carry {pipeline_id, file_id}.
    """
    if job_type not in _VALID_JOB_TYPES:
        raise ValueError(f"invalid job_type: {job_type!r}")
    jid = uuid.uuid4().hex
    attempt_count = 1
    if parent_job_id is not None:
        parent = get_job(db_path, parent_job_id)
        if parent is not None:
            attempt_count = (parent.get("attempt_count") or 1) + 1
    payload_json = json.dumps(payload) if payload is not None else None
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO jobs (id, user_id, file_id, type, status, created_at, "
            "attempt_count, payload) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)",
            (jid, user_id, file_id, job_type, time.time(), attempt_count, payload_json),
        )
        conn.commit()
        return jid
    finally:
        conn.close()


def _row_to_job(row: sqlite3.Row) -> dict:
    keys = row.keys()
    payload_raw = row["payload"] if "payload" in keys else None
    payload = json.loads(payload_raw) if payload_raw else None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "file_id": row["file_id"],
        "type": row["type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_msg": row["error_msg"],
        # R5 Phase 5 T1.5: tolerate pre-Phase-5 rows that pre-date ALTER.
        "attempt_count": row["attempt_count"] if "attempt_count" in keys else 1,
        # v4 A1: payload dict for pipeline_run jobs; None for all other types.
        "payload": payload,
    }


def get_job(db_path: str, job_id: str) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def update_job_status(
    db_path: str,
    job_id: str,
    status: str,
    started_at: Optional[float] = None,
    finished_at: Optional[float] = None,
    error_msg: Optional[str] = None,
) -> None:
    if status not in ("queued", "running", "done", "failed", "cancelled"):
        raise ValueError(f"invalid status: {status!r}")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, started_at = COALESCE(?, started_at), "
            "finished_at = COALESCE(?, finished_at), "
            "error_msg = COALESCE(?, error_msg) "
            "WHERE id = ?",
            (status, started_at, finished_at, error_msg, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def cancel_if_queued(db_path: str, job_id: str) -> bool:
    """Atomically cancel a job IFF its current DB status is 'queued'.

    Returns True if the row was actually flipped (status was 'queued'),
    False if the worker had already picked it up (status='running' by the
    time we got here). Caller should fall back to the running-cancel path
    when False. Closes the cancel-queued worker race (R6 audit R2) — the
    naive two-step `get_job` → `update_job_status` left a window where the
    worker could pop the jid and transition to 'running' between the read
    and the write, and the write would clobber that transition.
    """
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "UPDATE jobs SET status = 'cancelled', finished_at = ? "
            "WHERE id = ? AND status = 'queued'",
            (__import__('time').time(), job_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_jobs_for_user(db_path: str, user_id: int) -> list:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def list_active_jobs(db_path: str) -> list:
    """Across all users — for admin queue panel."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('queued', 'running') "
            "ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def list_recent_finished_jobs(db_path: str, since_ts: float) -> list:
    """Jobs finished after `since_ts` (done / failed / cancelled), newest first.

    Used by the shared queue panel so all clients can see what just completed
    in the past few minutes, not only what's currently active.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('done', 'failed', 'cancelled') "
            "AND finished_at IS NOT NULL AND finished_at >= ? "
            "ORDER BY finished_at DESC",
            (since_ts,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def recover_orphaned_running(db_path: str, auto_retry: bool = False):
    """Boot-time recovery: any 'running' job left from previous server
    process is failed (treated as crashed mid-execution).

    If auto_retry=False (default): returns int count (backward-compatible).

    If auto_retry=True: returns list of dicts {id, user_id, file_id, type,
    attempt_count} for orphans whose attempt_count is **below** the
    R5_MAX_JOB_RETRY cap (env, default 3). Jobs already at-or-past the
    cap are still failed in the DB but excluded from the returned list,
    so the caller does NOT re-enqueue them. This stops poison-pill loops
    where a misconfigured handler crashes immediately on every retry.
    """
    import os
    max_retry = int(os.environ.get("R5_MAX_JOB_RETRY", "3"))

    conn = get_connection(db_path)
    try:
        # Capture orphans BEFORE update so we can return their details
        orphans = conn.execute(
            "SELECT id, user_id, file_id, type, attempt_count "
            "FROM jobs WHERE status = 'running'"
        ).fetchall()
        result = [dict(o) for o in orphans]
        if result:
            conn.execute(
                "UPDATE jobs SET status = 'failed', "
                "error_msg = 'orphaned by server restart', "
                "finished_at = ? "
                "WHERE status = 'running'",
                (time.time(),),
            )
            conn.commit()
        if auto_retry:
            return [
                o for o in result
                if (o.get("attempt_count") or 1) < max_retry
            ]
        return len(result)
    finally:
        conn.close()
