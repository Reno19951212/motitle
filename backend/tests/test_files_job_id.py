"""Phase 4B — /api/files response includes per-file active job_id."""
import pytest


@pytest.fixture
def alice_with_queued_file(monkeypatch):
    """Alice owns one file; one queued ASR job points at it."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    from jobqueue.db import init_jobs_table, insert_job

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_b1", "secret", is_admin=False)
    except ValueError:
        pass
    uid = get_user_by_username(db, "alice_b1")["id"]
    init_jobs_table(db)

    # Inject a registered file owned by alice
    fake_id = "file-b1"
    with app_module._registry_lock:
        app_module._file_registry[fake_id] = {
            "id": fake_id, "user_id": uid, "stored_name": "x.wav",
            "file_path": "/tmp/b1_fake.wav", "status": "uploaded",
            "original_name": "x.wav", "size": 0, "uploaded_at": 0.0,
            "segments": [], "text": "",
        }
    open("/tmp/b1_fake.wav", "wb").close()

    # Queue an ASR job for that file
    jid = insert_job(db, user_id=uid, file_id=fake_id, job_type="asr")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_b1", "password": "secret"})
    assert r.status_code == 200
    yield c, fake_id, jid

    # Cleanup
    with app_module._registry_lock:
        app_module._file_registry.pop(fake_id, None)
    # Remove all jobs for this file so the next test invocation starts clean.
    conn = __import__("sqlite3").connect(db)
    try:
        conn.execute("DELETE FROM jobs WHERE file_id = ?", (fake_id,))
        conn.commit()
    finally:
        conn.close()
    import os
    if os.path.exists("/tmp/b1_fake.wav"):
        os.remove("/tmp/b1_fake.wav")


def test_api_files_includes_job_id_for_active_job(alice_with_queued_file):
    client, file_id, expected_jid = alice_with_queued_file
    r = client.get("/api/files")
    assert r.status_code == 200
    body = r.get_json()
    files = body.get("files", body if isinstance(body, list) else [])
    target = next((f for f in files if f["id"] == file_id), None)
    assert target is not None, f"file {file_id} not in response"
    assert target.get("job_id") == expected_jid


def test_api_files_job_id_null_when_no_active_job(alice_with_queued_file, monkeypatch):
    """File with no queued/running job → job_id is null."""
    import app as app_module
    from jobqueue.db import update_job_status

    client, file_id, jid = alice_with_queued_file
    db = app_module.app.config["AUTH_DB_PATH"]
    # Mark the only job as done — no active jobs left
    update_job_status(db, jid, "done")

    r = client.get("/api/files")
    body = r.get_json()
    files = body.get("files", body if isinstance(body, list) else [])
    target = next((f for f in files if f["id"] == file_id), None)
    assert target is not None
    assert target.get("job_id") is None
