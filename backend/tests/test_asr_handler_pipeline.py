# backend/tests/test_asr_handler_pipeline.py
"""Phase 2B — _asr_handler does full registry pipeline (status/segments/auto_translate trigger)."""
import pytest


@pytest.fixture
def fake_file_in_registry(monkeypatch, tmp_path):
    """Inject a registered file with a known stored audio path."""
    import app
    fake_id = "asr-pipe-test-1"
    fake_path = str(tmp_path / "fake_audio.wav")
    # Touch the file so resolve_file_path() doesn't 404 the lookup.
    open(fake_path, "wb").close()
    with app._registry_lock:
        app._file_registry[fake_id] = {
            "id": fake_id,
            "user_id": 1,
            "original_name": "fake.wav",
            "stored_name": "fake.wav",
            "file_path": fake_path,
            "size": 0,
            "status": "uploaded",
            "uploaded_at": 0.0,
            "segments": [],
            "text": "",
            "error": None,
        }
    yield fake_id
    with app._registry_lock:
        app._file_registry.pop(fake_id, None)


def test_asr_handler_marks_status_done_on_success(fake_file_in_registry, monkeypatch):
    import app
    fake_result = {
        "text": "hello world",
        "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
        "language": "en",
        "model": "small",
        "backend": "faster-whisper",
    }
    monkeypatch.setattr(app, "transcribe_with_segments",
                        lambda *a, **kw: fake_result)
    # Stub auto-translate so this test stays focused on ASR registry update.
    monkeypatch.setattr(app, "_auto_translate", lambda *a, **kw: None)

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    app._asr_handler(job)

    with app._registry_lock:
        entry = app._file_registry[fake_file_in_registry]
    assert entry["status"] == "done"
    assert entry["text"] == "hello world"
    assert len(entry["segments"]) == 1
    assert entry["model"] == "small"
    assert entry["asr_seconds"] is not None and entry["asr_seconds"] >= 0


def test_asr_handler_enqueues_translate_job_after_done(fake_file_in_registry, monkeypatch):
    import app
    fake_result = {"text": "x", "segments": [{"start": 0, "end": 1, "text": "x"}],
                   "language": "en", "model": "small", "backend": "faster-whisper"}
    monkeypatch.setattr(app, "transcribe_with_segments", lambda *a, **kw: fake_result)

    enqueued = []
    real_enqueue = app._job_queue.enqueue
    def spy_enqueue(**kw):
        enqueued.append(kw)
        return real_enqueue(**kw)
    monkeypatch.setattr(app._job_queue, "enqueue", spy_enqueue)

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    app._asr_handler(job)
    assert any(e["job_type"] == "translate" and e["file_id"] == fake_file_in_registry
               for e in enqueued)


def test_asr_handler_marks_status_error_on_exception(fake_file_in_registry, monkeypatch):
    import app
    def explode(*a, **kw): raise RuntimeError("whisper boom")
    monkeypatch.setattr(app, "transcribe_with_segments", explode)

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    with pytest.raises(RuntimeError, match="whisper boom"):
        app._asr_handler(job)
    with app._registry_lock:
        entry = app._file_registry[fake_file_in_registry]
    assert entry["status"] == "error"
    assert "whisper boom" in (entry.get("error") or "")


@pytest.fixture
def client_with_admin():
    """Real logged-in admin client against the global app.

    R5 Phase 2 — needed for tests that hit routes which read `current_user.id`
    inside the handler body. The conftest LOGIN_DISABLED + R5_AUTH_BYPASS
    flags bypass auth decorators but don't inject a logged-in user; we need
    a real session so `current_user` resolves to our test admin.
    """
    import app as app_module
    from auth.users import init_db, create_user

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_phase2", "secret", is_admin=True)
    except ValueError:
        pass  # user already exists from a prior test run — fine

    client = app_module.app.test_client()
    r = client.post("/login", json={"username": "alice_phase2", "password": "secret"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield client


def test_re_transcribe_enqueues_job_returns_202(client_with_admin, tmp_path):
    """Re-transcribe endpoint matches /api/transcribe contract (202 + job_id).

    Currently returns 200 with status='processing' (legacy do_transcribe
    inline thread). After B4 this returns 202 with job_id from the queue.
    """
    import app
    fake_id = "rt-test-1"
    fake_path = str(tmp_path / "rt_fake.wav")
    open(fake_path, "wb").close()
    with app._registry_lock:
        app._file_registry[fake_id] = {
            "id": fake_id, "user_id": 1, "stored_name": "rt_fake.wav",
            "file_path": fake_path, "status": "done",
            "original_name": "rt_fake.wav", "size": 0, "uploaded_at": 0.0,
            "segments": [{"start": 0, "end": 1, "text": "old"}],
            "text": "old",
        }
    try:
        r = client_with_admin.post(f"/api/files/{fake_id}/transcribe", json={})
        assert r.status_code == 202, f"got {r.status_code}: {r.data!r}"
        body = r.get_json()
        assert "job_id" in body
        assert body["status"] == "queued"
    finally:
        with app._registry_lock:
            app._file_registry.pop(fake_id, None)
