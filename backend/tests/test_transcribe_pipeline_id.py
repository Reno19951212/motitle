"""v4.0 A3 T4 — POST /api/transcribe accepts optional pipeline_id form field.

When present and valid, the upload enqueues a `pipeline_run` job (using A1
handler) instead of the legacy ASR-then-MT auto-translate flow.
"""
import io
import pytest


@pytest.fixture
def client_with_admin():
    """Logged-in admin client against the global app.

    Matches the pattern used in test_serve_assets.py — the fixture creates
    (or resets) an admin user, logs in, and yields the test client. The
    autouse `_isolate_app_data` conftest fixture still leaves
    LOGIN_DISABLED=True + R5_AUTH_BYPASS=True active (unless the test is
    marked `real_auth`) so the request layer uses the real session
    established by /login.
    """
    import app as app_module
    from auth.users import init_db, create_user, update_password
    from auth.limiter import limiter

    # Reset rate-limiter so accumulated /login calls from earlier tests in
    # the suite don't trigger 429s. Pattern borrowed from
    # test_v4_cascade_visibility.three_users.
    _limiter_enabled_saved = getattr(limiter, "enabled", True)
    try:
        limiter.reset()
        limiter.enabled = False
    except Exception:
        pass

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_a3_t4", "TestPass1!", is_admin=True)
    except ValueError:
        update_password(db_path, "alice_a3_t4", "TestPass1!")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_a3_t4", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield c

    try:
        limiter.enabled = _limiter_enabled_saved
    except Exception:
        pass


@pytest.fixture
def fake_pipeline(client_with_admin):
    """Create a minimal pipeline visible to admin for testing."""
    asr_resp = client_with_admin.post("/api/asr_profiles", json={
        "name": "t4-asr",
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "mode": "same-lang",
        "language": "en",
    })
    assert asr_resp.status_code in (200, 201), asr_resp.data
    asr_id = asr_resp.get_json()["id"]

    mt_resp = client_with_admin.post("/api/mt_profiles", json={
        "name": "t4-mt",
        "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh",
        "output_lang": "zh",
        "system_prompt": "polish",
        "user_message_template": "polish: {text}",
    })
    assert mt_resp.status_code in (200, 201), mt_resp.data
    mt_id = mt_resp.get_json()["id"]

    pipe_resp = client_with_admin.post("/api/pipelines", json={
        "name": "t4-pipe",
        "asr_profile_id": asr_id,
        "mt_stages": [mt_id],
        "glossary_stage": {
            "enabled": False,
            "glossary_ids": [],
            "apply_order": "explicit",
            "apply_method": "string-match-then-llm",
        },
        "font_config": {
            "family": "Noto Sans TC",
            "size": 35,
            "color": "#ffffff",
            "outline_color": "#000000",
            "outline_width": 2,
            "margin_bottom": 40,
            "subtitle_source": "auto",
            "bilingual_order": "target_top",
        },
    })
    assert pipe_resp.status_code in (200, 201), pipe_resp.data
    pipeline = pipe_resp.get_json()
    yield pipeline
    client_with_admin.delete(f"/api/pipelines/{pipeline['id']}")
    client_with_admin.delete(f"/api/mt_profiles/{mt_id}")
    client_with_admin.delete(f"/api/asr_profiles/{asr_id}")


def _upload_minimal_wav(client, **form_extras):
    data = {
        "file": (io.BytesIO(b"RIFF\x00\x00\x00\x00WAVE"), "tiny.wav"),
        **form_extras,
    }
    return client.post("/api/transcribe", data=data, content_type="multipart/form-data")


def _lookup_job(job_id):
    """Read a job row directly from the SQLite jobs DB."""
    import app as app_module
    from jobqueue.db import get_job
    return get_job(app_module._job_queue._db_path, job_id)


def test_transcribe_with_pipeline_id_enqueues_pipeline_run(client_with_admin, fake_pipeline):
    response = _upload_minimal_wav(client_with_admin, pipeline_id=fake_pipeline["id"])
    assert response.status_code == 202, response.data
    body = response.get_json()
    assert "file_id" in body and "job_id" in body
    job = _lookup_job(body["job_id"])
    assert job is not None, f"job {body['job_id']} not found in queue DB"
    assert job["type"] == "pipeline_run", f"expected pipeline_run, got {job['type']}"
    assert (job.get("payload") or {}).get("pipeline_id") == fake_pipeline["id"]


def test_transcribe_without_pipeline_id_uses_legacy_flow(client_with_admin):
    response = _upload_minimal_wav(client_with_admin)
    assert response.status_code == 202, response.data
    body = response.get_json()
    job = _lookup_job(body["job_id"])
    assert job is not None
    assert job["type"] == "asr", f"expected legacy asr, got {job['type']}"


def test_transcribe_with_invalid_pipeline_id_returns_400(client_with_admin):
    response = _upload_minimal_wav(client_with_admin, pipeline_id="does-not-exist")
    assert response.status_code == 400, response.data
    body = response.get_json()
    assert "pipeline" in (body.get("error") or "").lower(), body


@pytest.mark.real_auth
def test_transcribe_with_pipeline_id_not_visible_returns_403_or_400(
    client_with_admin, fake_pipeline
):
    """A non-owner non-admin user cannot upload against an unshared pipeline
    they do not own. Requires real auth (no R5_AUTH_BYPASS) so the
    pipeline_manager.can_view ownership check has bite."""
    import app as app_module
    from auth.users import init_db, create_user, update_password, delete_user

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "bob_a3_t4", "OtherPass1!", is_admin=False)
    except ValueError:
        update_password(db_path, "bob_a3_t4", "OtherPass1!")

    # The pipeline created by the fake_pipeline fixture is owned by
    # alice_a3_t4 (admin). Bob is non-admin and not the owner, so the
    # pipeline must not be visible to him.
    #
    # Move pipeline to a private state explicitly: PipelineManager.create
    # stores user_id from the caller. We patch the on-disk record to ensure
    # user_id is the admin's id (not None), so it is not "shared".
    pipe = app_module._pipeline_manager.get(fake_pipeline["id"])
    assert pipe is not None
    if pipe.get("user_id") is None:
        # Force private ownership so visibility check has bite.
        from auth.users import get_user_by_username
        alice = get_user_by_username(db_path, "alice_a3_t4")
        app_module._pipeline_manager.update_if_owned(
            fake_pipeline["id"], alice["id"], True, {"user_id": alice["id"]}
        )

    try:
        # Log out admin, log in as bob.
        client_with_admin.post("/logout")
        login_resp = client_with_admin.post(
            "/login",
            json={"username": "bob_a3_t4", "password": "OtherPass1!"},
        )
        assert login_resp.status_code == 200, login_resp.data
        response = _upload_minimal_wav(client_with_admin, pipeline_id=fake_pipeline["id"])
        assert response.status_code in (400, 403), response.data
    finally:
        # Restore admin login so the fake_pipeline teardown can delete.
        client_with_admin.post("/logout")
        client_with_admin.post(
            "/login",
            json={"username": "alice_a3_t4", "password": "TestPass1!"},
        )
        try:
            delete_user(db_path, "bob_a3_t4")
        except Exception:
            pass
