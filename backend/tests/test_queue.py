"""Tests for backend/jobqueue/queue.py — JobQueue threaded class.

Package renamed from `queue` (plan) to `jobqueue` to keep stdlib `queue`
importable for the worker pool.
"""
import pytest
import time
import threading


@pytest.fixture
def db_path(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def test_enqueue_returns_job_id(db_path):
    from jobqueue.queue import JobQueue
    q = JobQueue(db_path)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    assert isinstance(jid, str)
    q.shutdown()


def test_position_is_zero_indexed_in_queue(db_path):
    from jobqueue.queue import JobQueue
    q = JobQueue(db_path)
    j1 = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    j2 = q.enqueue(user_id=2, file_id="f2", job_type="asr")
    j3 = q.enqueue(user_id=1, file_id="f3", job_type="asr")
    assert q.position(j1) == 0
    assert q.position(j2) == 1
    assert q.position(j3) == 2
    q.shutdown()


def test_register_handler_then_run_one(db_path):
    from jobqueue.queue import JobQueue
    completed = []

    def fake_asr(job, cancel_event=None):
        completed.append(job["id"])

    q = JobQueue(db_path, asr_handler=fake_asr)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()
    # wait for completion
    deadline = time.time() + 5
    while time.time() < deadline:
        from jobqueue.db import get_job
        if get_job(db_path, jid)["status"] == "done":
            break
        time.sleep(0.05)
    from jobqueue.db import get_job
    assert get_job(db_path, jid)["status"] == "done"
    assert jid in completed
    q.shutdown()


def test_handler_exception_marks_failed(db_path):
    from jobqueue.queue import JobQueue
    from jobqueue.db import get_job

    def bad_handler(job, cancel_event=None):
        raise RuntimeError("boom")

    q = JobQueue(db_path, asr_handler=bad_handler)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()
    deadline = time.time() + 5
    while time.time() < deadline:
        if get_job(db_path, jid)["status"] in ("failed", "done"):
            break
        time.sleep(0.05)
    j = get_job(db_path, jid)
    assert j["status"] == "failed"
    assert "boom" in (j["error_msg"] or "")
    q.shutdown()
