"""Phase 3E — explicit retry endpoint + boot-time auto-retry."""
import pytest


@pytest.fixture
def alice_client_with_failed_job(monkeypatch, tmp_path):
    """Logged-in alice with one failed job in the queue DB."""
    import app as app_module
    from auth.users import init_db, create_user
    from jobqueue.db import init_jobs_table, insert_job, update_job_status
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        uid = create_user(db, "alice_e1", "TestPass1!", is_admin=False)
    except ValueError:
        from auth.users import get_user_by_username, update_password
        update_password(db, "alice_e1", "TestPass1!")
        uid = get_user_by_username(db, "alice_e1")["id"]
    init_jobs_table(db)
    jid = insert_job(db, user_id=uid, file_id="f-e1", job_type="asr")
    update_job_status(db, jid, "failed", error_msg="prior failure")
    c = app_module.app.test_client()
    c.post("/login", json={"username": "alice_e1", "password": "TestPass1!"})
    yield c, jid


def test_retry_creates_new_job_id(alice_client_with_failed_job):
    client, old_jid = alice_client_with_failed_job
    r = client.post(f"/api/queue/{old_jid}/retry")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["new_job_id"] != old_jid


def test_retry_only_valid_for_failed_status(alice_client_with_failed_job):
    """Cannot retry a queued or running job — only failed."""
    import app as app_module
    from jobqueue.db import insert_job, get_job
    db = app_module.app.config["AUTH_DB_PATH"]
    # Queued job
    qjid = insert_job(db, user_id=99, file_id="f-e2", job_type="asr")
    client, _ = alice_client_with_failed_job
    r = client.post(f"/api/queue/{qjid}/retry")
    assert r.status_code in (403, 409)  # 403 if owner check, 409 if status check


def test_retry_404_for_unknown_id(alice_client_with_failed_job):
    client, _ = alice_client_with_failed_job
    r = client.post("/api/queue/nonexistent-job-id/retry")
    assert r.status_code == 404


def test_recover_orphaned_running_with_auto_retry_returns_orphan_ids(tmp_path):
    """When auto_retry=True, recover_orphaned_running returns a list of
    (job_id, user_id, file_id, type) tuples so caller can re-enqueue."""
    import time
    from jobqueue.db import (init_jobs_table, insert_job, update_job_status,
                             recover_orphaned_running)
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    j1 = insert_job(p, user_id=1, file_id="f1", job_type="asr")
    update_job_status(p, j1, "running", started_at=time.time())
    j2 = insert_job(p, user_id=2, file_id="f2", job_type="translate")
    update_job_status(p, j2, "running", started_at=time.time())
    orphans = recover_orphaned_running(p, auto_retry=True)
    assert isinstance(orphans, list)
    assert len(orphans) == 2
    ids = {o["id"] for o in orphans}
    assert {j1, j2} == ids
    # Each entry has the fields needed to re-enqueue
    for o in orphans:
        assert "user_id" in o and "file_id" in o and "type" in o


def test_jobqueue_init_re_enqueues_orphans_when_recovered(tmp_path, monkeypatch):
    """After server restart with stuck running jobs, JobQueue boot
    re-enqueues them automatically."""
    import time
    from jobqueue.db import init_jobs_table, insert_job, update_job_status, get_job
    from jobqueue.queue import JobQueue
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    orphan = insert_job(p, user_id=1, file_id="f1", job_type="asr")
    update_job_status(p, orphan, "running", started_at=time.time())
    # Boot a fresh JobQueue — should recover + re-enqueue
    q = JobQueue(p)
    # Old orphan is now status='failed'
    assert get_job(p, orphan)["status"] == "failed"
    # A NEW job exists with the same file_id + type
    from jobqueue.db import list_active_jobs
    active = list_active_jobs(p)
    assert any(j["file_id"] == "f1" and j["type"] == "asr" for j in active)
    q.shutdown()
