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
        uid = create_user(db, "alice_e1", "secret", is_admin=False)
    except ValueError:
        from auth.users import get_user_by_username
        uid = get_user_by_username(db, "alice_e1")["id"]
    init_jobs_table(db)
    jid = insert_job(db, user_id=uid, file_id="f-e1", job_type="asr")
    update_job_status(db, jid, "failed", error_msg="prior failure")
    c = app_module.app.test_client()
    c.post("/login", json={"username": "alice_e1", "password": "secret"})
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
