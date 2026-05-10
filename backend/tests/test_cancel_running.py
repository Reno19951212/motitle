# backend/tests/test_cancel_running.py
"""Phase 4D — worker thread interrupt + JobCancelled → status='cancelled'."""
import pytest
import threading
import time


@pytest.fixture
def db_path(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def test_jobcancelled_exception_class_exists():
    from jobqueue.queue import JobCancelled
    assert issubclass(JobCancelled, Exception)


def test_handler_raising_jobcancelled_marks_status_cancelled(db_path):
    """When a handler raises JobCancelled, the job status becomes 'cancelled'
    (not 'failed' — that's reserved for unexpected exceptions)."""
    from jobqueue.queue import JobQueue, JobCancelled
    from jobqueue.db import get_job

    def cancelling_handler(job, cancel_event=None):
        raise JobCancelled("user requested cancel")

    q = JobQueue(db_path, asr_handler=cancelling_handler)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()

    deadline = time.time() + 5
    while time.time() < deadline:
        s = get_job(db_path, jid)["status"]
        if s in ("cancelled", "failed", "done"):
            break
        time.sleep(0.05)

    j = get_job(db_path, jid)
    assert j["status"] == "cancelled", f"expected cancelled, got {j['status']!r} (error_msg={j.get('error_msg')!r})"
    q.shutdown()


def test_jobqueue_cancel_job_sets_event(db_path):
    """JobQueue.cancel_job(job_id) sets the per-job cancel event for the
    currently-running handler to observe."""
    from jobqueue.queue import JobQueue, JobCancelled
    from jobqueue.db import get_job

    handler_started = threading.Event()
    handler_saw_cancel = threading.Event()

    def slow_handler(job, cancel_event=None):
        handler_started.set()
        # Poll for up to 3 seconds
        for _ in range(60):
            if cancel_event is not None and cancel_event.is_set():
                handler_saw_cancel.set()
                raise JobCancelled("cancel observed")
            time.sleep(0.05)

    q = JobQueue(db_path, asr_handler=slow_handler)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()

    # Wait for the handler to start
    assert handler_started.wait(timeout=3.0), "handler never started"

    # Cancel the running job
    found = q.cancel_job(jid)
    assert found is True

    # Wait for handler to observe the cancel
    assert handler_saw_cancel.wait(timeout=3.0), "handler never saw cancel event"

    # Wait for status to flip
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if get_job(db_path, jid)["status"] == "cancelled":
            break
        time.sleep(0.05)
    assert get_job(db_path, jid)["status"] == "cancelled"
    q.shutdown()


def test_cancel_job_returns_false_for_unknown_id(db_path):
    from jobqueue.queue import JobQueue
    q = JobQueue(db_path)
    assert q.cancel_job("nonexistent") is False
    q.shutdown()
