"""Phase 5 T2.2 — JobQueue worker threads run with Flask app context."""
import pytest
import time


def _wait_status(db_path, jid, target_set, timeout=5.0):
    from jobqueue.db import get_job
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = get_job(db_path, jid)
        if s and s["status"] in target_set:
            return s["status"]
        time.sleep(0.02)
    return get_job(db_path, jid)["status"]


def test_jobqueue_init_accepts_app_kwarg(tmp_path):
    """JobQueue.__init__ accepts an optional app parameter."""
    from jobqueue.queue import JobQueue
    from jobqueue.db import init_jobs_table
    from flask import Flask

    db = str(tmp_path / "q.db")
    init_jobs_table(db)
    app = Flask(__name__)
    q = JobQueue(db, app=app)
    try:
        assert q._app is app
    finally:
        q.shutdown()


def test_handler_can_access_current_app(tmp_path):
    """Inside a worker thread, current_app must resolve when app is provided."""
    from jobqueue.queue import JobQueue
    from jobqueue.db import init_jobs_table
    from flask import Flask, current_app

    app = Flask(__name__)
    app.config["TEST_VALUE"] = "phase5_t22"

    captured = {}

    def handler(job, cancel_event=None):
        captured["test_value"] = current_app.config["TEST_VALUE"]
        captured["logger_works"] = current_app.logger is not None

    db = str(tmp_path / "q.db")
    init_jobs_table(db)
    q = JobQueue(db, pipeline_handler=handler, app=app)
    try:
        jid = q.enqueue(user_id=1, file_id="f1", job_type="pipeline_run")
        q.start_workers()
        final = _wait_status(db, jid, ("done", "failed"))
        assert final == "done", f"handler crashed; status={final!r}"
    finally:
        q.shutdown()

    assert captured.get("test_value") == "phase5_t22"
    assert captured.get("logger_works") is True


def test_jobqueue_no_app_works_without_context(tmp_path):
    """Backward compat: app=None default still works (handler runs without context)."""
    from jobqueue.queue import JobQueue
    from jobqueue.db import init_jobs_table

    ran = {}

    def handler(job, cancel_event=None):
        ran["yes"] = True

    db = str(tmp_path / "q.db")
    init_jobs_table(db)
    q = JobQueue(db, pipeline_handler=handler)
    try:
        jid = q.enqueue(user_id=1, file_id="f1", job_type="pipeline_run")
        q.start_workers()
        _wait_status(db, jid, ("done", "failed"))
    finally:
        q.shutdown()
    assert ran.get("yes") is True
