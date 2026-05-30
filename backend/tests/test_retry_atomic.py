"""Bug #19 — retry cap check + insert must be atomic (BEGIN IMMEDIATE).

Without the fix, two concurrent POST /api/queue/<id>/retry on the same failed
job can both observe attempt_count < cap and both insert, bypassing the
poison-pill cap. These tests cover:

  1. Deterministic: at-cap job → insert_retry_job raises + returns None (no row).
  2. Concurrency: 2 threads retry a cap-1 job concurrently; exactly ONE new job
     is created (mirrors test_admin_atomic.py's Barrier pattern).
"""
import sqlite3
import threading
import time
import pytest


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def _make_failed_job(db_path: str, attempt_count: int) -> str:
    """Insert a 'failed' job with a specific attempt_count and return its id."""
    from jobqueue.db import insert_job, update_job_status
    import sqlite3

    jid = insert_job(db_path, user_id=1, file_id="f-atomic", job_type="asr")
    # Override attempt_count directly — insert_job always starts at 1.
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE jobs SET attempt_count = ? WHERE id = ?", (attempt_count, jid))
    conn.commit()
    conn.close()
    update_job_status(db_path, jid, "failed", error_msg="simulated failure")
    return jid


# ---------------------------------------------------------------------------
# 1. Deterministic: at-cap → insert_retry_job returns None, no new row
# ---------------------------------------------------------------------------

def test_insert_retry_job_at_cap_returns_none(db_path, monkeypatch):
    """insert_retry_job must return None when parent attempt_count >= max_retry."""
    from jobqueue.db import insert_retry_job, list_active_jobs

    monkeypatch.delenv("R5_MAX_JOB_RETRY", raising=False)  # default cap = 3
    jid = _make_failed_job(db_path, attempt_count=3)  # at cap

    result = insert_retry_job(
        db_path,
        user_id=1,
        file_id="f-atomic",
        job_type="asr",
        parent_job_id=jid,
        max_retry=3,
    )

    assert result is None, "insert_retry_job must return None when at cap"
    active = list_active_jobs(db_path)
    assert len(active) == 0, "no new job row must be inserted when at cap"


def test_insert_retry_job_below_cap_succeeds(db_path, monkeypatch):
    """insert_retry_job must return a new job id when below cap."""
    from jobqueue.db import insert_retry_job, get_job

    monkeypatch.delenv("R5_MAX_JOB_RETRY", raising=False)  # cap = 3
    jid = _make_failed_job(db_path, attempt_count=2)  # one below cap

    new_id = insert_retry_job(
        db_path,
        user_id=1,
        file_id="f-atomic",
        job_type="asr",
        parent_job_id=jid,
        max_retry=3,
    )

    assert new_id is not None, "insert_retry_job must return a new job id below cap"
    new_job = get_job(db_path, new_id)
    assert new_job is not None
    assert new_job["attempt_count"] == 3  # parent 2 + 1
    assert new_job["status"] == "queued"


# ---------------------------------------------------------------------------
# 2. Concurrency: 2 threads retry a cap-1 job — exactly one must win
# ---------------------------------------------------------------------------

def test_concurrent_retry_only_one_wins(db_path, monkeypatch):
    """Two threads call insert_retry_job concurrently on a job at cap-1.

    The cap is set to 3 and the parent has attempt_count=2 (one below cap).
    Both threads should race; exactly ONE must get a new job id back and
    ONE must get None (cap enforced atomically). Total queued rows == 1.

    Mirrors the Barrier pattern from test_admin_atomic.py (Phase 5 T2.7).
    """
    from jobqueue.db import insert_retry_job, list_active_jobs

    monkeypatch.delenv("R5_MAX_JOB_RETRY", raising=False)
    jid = _make_failed_job(db_path, attempt_count=2)  # cap=3, one below

    results = []   # None or new_job_id, one per thread
    errors = []
    barrier = threading.Barrier(2)

    def do_retry():
        barrier.wait()  # release both threads at the same instant
        try:
            r = insert_retry_job(
                db_path,
                user_id=1,
                file_id="f-atomic",
                job_type="asr",
                parent_job_id=jid,
                max_retry=3,
            )
            results.append(r)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=do_retry)
    t2 = threading.Thread(target=do_retry)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"unexpected exceptions: {errors}"
    assert len(results) == 2, "expected exactly 2 results (one per thread)"

    successes = [r for r in results if r is not None]
    nones = [r for r in results if r is None]

    # Exactly one thread must have inserted a new job.
    assert len(successes) == 1, (
        f"Bug #19: expected 1 successful insert, got {len(successes)}. "
        f"results={results} — cap not enforced atomically"
    )
    assert len(nones) == 1, (
        f"expected 1 cap-rejected None, got {len(nones)}. results={results}"
    )

    # Confirm the DB has exactly 1 new queued row (not 2).
    active = list_active_jobs(db_path)
    assert len(active) == 1, (
        f"Bug #19: {len(active)} queued jobs created instead of 1 — "
        "cap bypassed by concurrent retries"
    )
