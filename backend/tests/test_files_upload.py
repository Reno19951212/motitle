"""POST /api/files/upload — pure upload, no pipeline enqueue.

Mirrors /api/transcribe's file-save + register behavior but does NOT push a
pipeline_run job. The file ends up in the registry with status='uploaded' so
the dashboard's QueueItem can render a per-file 執行 button to trigger the
run on demand.
"""
from __future__ import annotations

import io

import pytest


@pytest.fixture
def client_with_admin():
    """Logged-in admin client against the global app."""
    import app as app_module
    from auth.users import init_db, create_user, update_password

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_upload_test", "TestPass1!", is_admin=True)
    except ValueError:
        update_password(db_path, "alice_upload_test", "TestPass1!")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_upload_test", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield c


def test_upload_succeeds_with_video_file(client_with_admin):
    """Happy path: POST a small .mp4 → 200 + registry has the file w/ status='uploaded'."""
    data = {
        "file": (io.BytesIO(b"fake video bytes"), "sample.mp4"),
    }
    resp = client_with_admin.post(
        "/api/files/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "file_id" in body
    assert body["status"] == "uploaded"
    assert body["filename"].endswith(".mp4")

    # The file lives in the per-user registry.
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(body["file_id"])
    assert entry is not None
    assert entry["status"] == "uploaded"


def test_upload_does_not_enqueue_any_job(client_with_admin):
    """The whole point: upload alone must NOT push a pipeline_run job."""
    import app as _app
    from jobqueue.db import list_active_jobs

    data = {
        "file": (io.BytesIO(b"fake video bytes"), "sample.mp4"),
    }

    # Snapshot active job count before the request.
    db_path = _app.app.config["AUTH_DB_PATH"]
    jobs_before = len(list_active_jobs(db_path))
    resp = client_with_admin.post(
        "/api/files/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    jobs_after = len(list_active_jobs(db_path))

    assert jobs_after == jobs_before, (
        f"Expected no new jobs after /api/files/upload, "
        f"but queue grew from {jobs_before} to {jobs_after}"
    )


def test_upload_rejects_missing_file_part(client_with_admin):
    """Multipart request without a 'file' field → 400."""
    resp = client_with_admin.post(
        "/api/files/upload",
        data={},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "error" in body


def test_upload_rejects_unsupported_extension(client_with_admin):
    """Files with non-media suffix → 400 (mirrors /api/transcribe gate)."""
    data = {
        "file": (io.BytesIO(b"not a video"), "evil.txt"),
    }
    resp = client_with_admin.post(
        "/api/files/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "error" in body
    assert "不支持" in body["error"] or "format" in body["error"].lower()
