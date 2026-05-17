"""Phase 5 T1.5 — boot recovery skips re-enqueue past attempt_count cap."""
import pytest
import sqlite3
import time


@pytest.fixture
def db_path(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def test_jobs_table_has_attempt_count_column(db_path):
    """Schema migration: jobs.attempt_count exists."""
    from jobqueue.db import get_connection
    conn = get_connection(db_path)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "attempt_count" in cols, "T1.5 — jobs.attempt_count column missing"
    finally:
        conn.close()


def test_insert_job_default_attempt_count_is_1(db_path):
    from jobqueue.db import insert_job, get_job
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run")
    assert get_job(db_path, jid)["attempt_count"] == 1


def test_insert_job_with_parent_increments_attempt_count(db_path):
    from jobqueue.db import insert_job, get_job
    parent = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run")
    retry = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run",
                       parent_job_id=parent)
    assert get_job(db_path, retry)["attempt_count"] == 2


def test_insert_job_chain_increments_each_time(db_path):
    """Re-enqueue twice → attempt_count 1 → 2 → 3."""
    from jobqueue.db import insert_job, get_job
    j1 = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run")
    j2 = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run", parent_job_id=j1)
    j3 = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run", parent_job_id=j2)
    assert get_job(db_path, j3)["attempt_count"] == 3


def test_recover_orphaned_running_skips_at_max_attempt(db_path, monkeypatch):
    """T1.5 — orphan job at attempt_count=3 (default cap) is NOT re-enqueued."""
    from jobqueue.db import insert_job, update_job_status, get_job, recover_orphaned_running

    monkeypatch.delenv("R5_MAX_JOB_RETRY", raising=False)  # use default 3

    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run")
    c = sqlite3.connect(db_path)
    c.execute("UPDATE jobs SET attempt_count = 3 WHERE id = ?", (jid,))
    c.commit()
    c.close()
    update_job_status(db_path, jid, "running", started_at=time.time())

    orphans = recover_orphaned_running(db_path, auto_retry=True)
    assert get_job(db_path, jid)["status"] == "failed"
    assert len(orphans) == 0, f"T1.5 — should skip re-enqueue, got {orphans}"


def test_recover_orphaned_running_re_enqueues_under_cap(db_path, monkeypatch):
    """T1.5 — orphan at attempt_count=1 IS re-enqueued (default cap=3)."""
    from jobqueue.db import insert_job, update_job_status, recover_orphaned_running

    monkeypatch.delenv("R5_MAX_JOB_RETRY", raising=False)

    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run")
    update_job_status(db_path, jid, "running", started_at=time.time())

    orphans = recover_orphaned_running(db_path, auto_retry=True)
    assert len(orphans) == 1
    assert orphans[0]["id"] == jid
    assert orphans[0]["attempt_count"] == 1


def test_max_retry_env_override(db_path, monkeypatch):
    """T1.5 — R5_MAX_JOB_RETRY env var overrides default cap of 3."""
    from jobqueue.db import insert_job, update_job_status, recover_orphaned_running

    monkeypatch.setenv("R5_MAX_JOB_RETRY", "1")  # cap at 1 = block immediately

    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="pipeline_run")
    update_job_status(db_path, jid, "running", started_at=time.time())

    orphans = recover_orphaned_running(db_path, auto_retry=True)
    assert len(orphans) == 0, "T1.5 — env cap of 1 must block re-enqueue at attempt 1"


def test_migration_script_idempotent(tmp_path):
    """Migration script ALTER ADD COLUMN is safe to re-run."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_migration", "migrations/2026-05-10-add-jobs-attempt-count.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "old.db")
    init_jobs_table(p)
    # First run: column already added by init_jobs_table; migration says "already present"
    assert m.migrate(p) is False
    # Second run: still already present
    assert m.migrate(p) is False
