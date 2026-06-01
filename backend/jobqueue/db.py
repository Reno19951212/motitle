"""SQLite-backed jobs table CRUD."""
import sqlite3
import time
import uuid
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  file_id TEXT NOT NULL,
  type TEXT NOT NULL,  -- job-type validity enforced Python-side in insert_job; no CHECK to avoid rebuild-on-add
  status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  error_msg TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 1  -- R5 Phase 5 T1.5: poison-pill cap
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
    # R5 Phase 5 T1.5: backfill attempt_count column on databases created
    # before Phase 5 (CREATE TABLE IF NOT EXISTS skips the new column).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "attempt_count" not in cols:
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1"
        )
    # T3 output-lang: backfill output_language column on databases created
    # before T3 (CREATE TABLE IF NOT EXISTS skips the new column).
    if "output_language" not in cols:
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN output_language TEXT"
        )
    conn.commit()
    # T3 output-lang: rebuild the table WITHOUT the legacy `type` CHECK when a
    # stale one is present. SQLite can't ALTER a CHECK constraint, and the live
    # data/app.db was created by an older schema whose CHECK omits 'asr_output'
    # — inserting one would raise IntegrityError. We reconstruct the table from
    # PRAGMA table_info (which naturally omits ALL CHECK constraints), preserving
    # every existing column (incl. drifted ones like `payload`) and every row.
    _drop_stale_type_check(conn)
    conn.close()


def _drop_stale_type_check(conn: sqlite3.Connection) -> None:
    """Idempotently rebuild `jobs` without the `type` CHECK if a stale one
    exists. After rebuild the DDL no longer contains 'CHECK(type IN', so this
    is a no-op on subsequent runs and on fresh DBs created by the new _SCHEMA.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    jobs_sql = row[0] if row else None
    if not jobs_sql or "CHECK(type IN" not in jobs_sql:
        return  # fresh DB or already migrated → idempotent no-op

    # Reconstruct column definitions verbatim from the existing schema so we
    # preserve EVERY column (incl. drifted ones). PRAGMA table_info gives the
    # column list with no CHECK constraints — exactly what we want to drop.
    info = conn.execute("PRAGMA table_info(jobs)").fetchall()
    col_names = [r[1] for r in info]
    col_defs = []
    for r in info:
        # r = (cid, name, type, notnull, dflt_value, pk)
        name, ctype, notnull, dflt_value, pk = r[1], r[2], r[3], r[4], r[5]
        parts = [name, ctype]
        if notnull:
            parts.append("NOT NULL")
        if dflt_value is not None:
            # dflt_value from PRAGMA is already SQL-literal-formatted.
            parts.append("DEFAULT {}".format(dflt_value))
        if pk:
            parts.append("PRIMARY KEY")
        col_defs.append(" ".join(parts))

    cols_csv = ", ".join(col_names)
    # foreign_keys is OFF by default in sqlite3, but set it defensively around
    # the table rename so the DROP/RENAME can't trip any FK action.
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            "CREATE TABLE jobs__migrated ({})".format(", ".join(col_defs))
        )
        conn.execute(
            "INSERT INTO jobs__migrated ({cols}) SELECT {cols} FROM jobs".format(
                cols=cols_csv
            )
        )
        conn.execute("DROP TABLE jobs")
        conn.execute("ALTER TABLE jobs__migrated RENAME TO jobs")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)"
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys={}".format("ON" if fk_prev else "OFF"))


def insert_job(db_path: str, user_id: int, file_id: str, job_type: str,
               parent_job_id: Optional[str] = None,
               output_language: Optional[str] = None) -> str:
    """Insert a queued job. If `parent_job_id` is given (re-enqueue from
    boot recovery), inherit attempt_count + 1 from the parent so the
    poison-pill cap can stop re-enqueue loops."""
    if job_type not in ("asr", "asr_output", "translate", "render"):
        raise ValueError(f"invalid job_type: {job_type!r}")
    jid = uuid.uuid4().hex
    attempt_count = 1
    if parent_job_id is not None:
        parent = get_job(db_path, parent_job_id)
        if parent is not None:
            attempt_count = (parent.get("attempt_count") or 1) + 1
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO jobs (id, user_id, file_id, type, status, created_at, attempt_count, output_language) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)",
            (jid, user_id, file_id, job_type, time.time(), attempt_count, output_language),
        )
        conn.commit()
        return jid
    finally:
        conn.close()


def insert_retry_job(
    db_path: str,
    user_id: int,
    file_id: str,
    job_type: str,
    parent_job_id: str,
    max_retry: int,
) -> Optional[str]:
    """Atomically check the poison-pill cap and insert a retry job.

    The cap is scoped to the **retry chain of the specific parent job**, not
    the whole ``(file_id, type)`` family.  Inside a single ``BEGIN IMMEDIATE``
    transaction we:

      1. read the parent's ``attempt_count`` (k),
      2. reject (return None) if ``k >= max_retry``,
      3. INSERT the child at ``attempt_count = k + 1``,
      4. bump the parent's ``attempt_count`` to ``k + 1`` — consuming a cap
         slot so a concurrent OR repeated retry of the SAME failed job sees
         the higher count and is bounded by the cap.

    Why parent-scoped, not ``MAX(attempt_count)`` over (file_id, type):
    a ``MAX`` over the whole family is a *lifetime* cap that wrongly blocks a
    fresh job chain (e.g. a re-transcribe of the same file) once any earlier
    chain reached the cap.  Reading the specific parent keeps the cap per
    retry-chain.  Concurrency safety comes from ``BEGIN IMMEDIATE`` serializing
    the read+bump: two simultaneous retries of a job one-below-cap let exactly
    one through (it bumps the parent to the cap; the other then sees ``>= cap``).

    Returns the new job id on success, or ``None`` if the cap is reached
    (or the parent no longer exists).  Mirrors the ``BEGIN IMMEDIATE`` pattern
    from ``auth/admin.py`` ``_atomic_set_admin`` (R5 Phase 5 T2.7).
    """
    if job_type not in ("asr", "asr_output", "translate", "render"):
        raise ValueError(f"invalid job_type: {job_type!r}")

    # isolation_level=None → autocommit off; we drive transactions manually.
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        prow = conn.execute(
            "SELECT attempt_count FROM jobs WHERE id = ?",
            (parent_job_id,),
        ).fetchone()
        if prow is None:
            conn.execute("ROLLBACK")
            return None
        parent_count = prow["attempt_count"] or 1
        if parent_count >= max_retry:
            conn.execute("ROLLBACK")
            return None
        new_count = parent_count + 1
        jid = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO jobs (id, user_id, file_id, type, status, created_at, attempt_count) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (jid, user_id, file_id, job_type, time.time(), new_count),
        )
        # Consume a cap slot on the parent so repeat/concurrent retries of the
        # same failed job can't bypass the cap (parent row is the chain counter).
        conn.execute(
            "UPDATE jobs SET attempt_count = ? WHERE id = ?",
            (new_count, parent_job_id),
        )
        conn.execute("COMMIT")
        return jid
    finally:
        conn.close()


def _row_to_job(row: sqlite3.Row) -> dict:
    keys = row.keys()
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
        # T3 output-lang: tolerate pre-T3 rows that pre-date ALTER.
        "output_language": row["output_language"] if "output_language" in keys else None,
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
