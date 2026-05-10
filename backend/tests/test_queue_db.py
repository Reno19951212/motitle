"""Tests for backend/jobqueue/db.py — jobs table CRUD.

NOTE: package renamed from `queue` (plan) to `jobqueue` to avoid shadowing
Python stdlib's `queue` module (which provides `queue.Queue`, needed by
C4's worker). URL paths (/api/queue, /api/queue/<id>) are unaffected.
"""
import pytest
import time


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "queue.db")


def test_init_db_creates_jobs_table(db_path):
    from jobqueue.db import init_jobs_table, get_connection
    init_jobs_table(db_path)
    conn = get_connection(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_insert_job_returns_id(db_path):
    from jobqueue.db import init_jobs_table, insert_job
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    assert isinstance(jid, str) and len(jid) > 0


def test_get_job(db_path):
    from jobqueue.db import init_jobs_table, insert_job, get_job
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    j = get_job(db_path, jid)
    assert j["status"] == "queued"
    assert j["user_id"] == 1
    assert j["file_id"] == "f1"
    assert j["type"] == "asr"


def test_update_job_status(db_path):
    from jobqueue.db import init_jobs_table, insert_job, update_job_status, get_job
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    update_job_status(db_path, jid, "running", started_at=time.time())
    j = get_job(db_path, jid)
    assert j["status"] == "running"
    assert j["started_at"] is not None


def test_list_jobs_for_user(db_path):
    from jobqueue.db import init_jobs_table, insert_job, list_jobs_for_user
    init_jobs_table(db_path)
    insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    insert_job(db_path, user_id=1, file_id="f2", job_type="translate")
    insert_job(db_path, user_id=2, file_id="f3", job_type="asr")
    user1_jobs = list_jobs_for_user(db_path, user_id=1)
    assert len(user1_jobs) == 2


def test_list_all_active(db_path):
    """For admin queue panel — see all active jobs from all users."""
    from jobqueue.db import (init_jobs_table, insert_job, update_job_status,
                             list_active_jobs)
    init_jobs_table(db_path)
    j1 = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    j2 = insert_job(db_path, user_id=2, file_id="f2", job_type="asr")
    update_job_status(db_path, j2, "done", finished_at=time.time())
    active = list_active_jobs(db_path)
    assert len(active) == 1
    assert active[0]["id"] == j1


def test_recover_orphaned_running_on_boot(db_path):
    """Server crash leaves status='running' jobs. recover() flips them
    to 'failed' so they can be re-queued or marked errored."""
    from jobqueue.db import (init_jobs_table, insert_job, update_job_status,
                             recover_orphaned_running, get_job)
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    update_job_status(db_path, jid, "running", started_at=time.time())
    recover_orphaned_running(db_path)
    j = get_job(db_path, jid)
    assert j["status"] == "failed"
    assert "server restart" in (j["error_msg"] or "").lower()
