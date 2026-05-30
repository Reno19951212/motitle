"""Tests for progress_pct / stage_label / stage_state fields on /api/queue rows.

B1 TDD: three cases required by Phase B Task B1.
"""
import json
import pytest


@pytest.fixture
def app_with_queue_and_adapter(tmp_path):
    """Minimal Flask app wiring queue + auth, reset adapter before/after each test."""
    from auth.users import init_db, create_user
    from jobqueue.db import init_jobs_table, insert_job, update_job_status
    from flask import Flask
    from flask_login import LoginManager
    from auth.users import get_user_by_id
    from auth.routes import bp as auth_bp, _LoginUser
    from jobqueue.routes import bp as queue_bp, set_db_path
    import progress_adapter as pa

    db = str(tmp_path / "app.db")
    init_db(db)
    init_jobs_table(db)
    create_user(db, "alice", "TestPass1!")

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    app.config["AUTH_DB_PATH"] = db
    set_db_path(db)
    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def _load(uid):
        u = get_user_by_id(db, int(uid))
        return _LoginUser(u) if u else None

    app.register_blueprint(auth_bp)
    app.register_blueprint(queue_bp)

    # Reset adapter before the test so no stale snapshots bleed in
    pa.reset_adapter()

    yield app, db, insert_job, update_job_status

    # Cleanup adapter after test
    pa.reset_adapter()


def test_api_queue_attaches_progress_for_active_file(app_with_queue_and_adapter):
    """When the adapter has a snapshot, /api/queue row carries pct + label + state."""
    import progress_adapter as pa

    app, db, insert_job, update_job_status = app_with_queue_and_adapter

    fid = "f-progress-active"
    jid = insert_job(db, user_id=1, file_id=fid, job_type="asr")
    # Simulate a running job (as the worker would set it)
    update_job_status(db, jid, "running")

    # Pre-populate adapter cache for that file_id
    pa.get_adapter().report(
        file_id=fid,
        job_id=jid,
        pct=42,
        stage_label="轉錄中",
        stage_state="active",
        pipeline_kind="profile",
    )

    c = app.test_client()
    c.post("/login", json={"username": "alice", "password": "TestPass1!"})
    r = c.get("/api/queue")
    assert r.status_code == 200

    rows = json.loads(r.data)
    row = next((j for j in rows if j["file_id"] == fid), None)
    assert row is not None, f"file_id={fid} not found in queue rows: {rows}"
    assert row["progress_pct"] == 42
    assert row["stage_state"] == "active"
    # v3.22 new fields
    assert isinstance(row["stages"], list)
    assert isinstance(row["stage_index"], int)
    assert isinstance(row["pipeline_kind"], str)


def test_api_queue_returns_null_pct_idle_for_queued_no_snapshot(app_with_queue_and_adapter):
    """A queued job with no adapter snapshot returns progress_pct=null, stage_state='idle'."""
    import progress_adapter as pa

    app, db, insert_job, _ = app_with_queue_and_adapter

    fid = "f-no-snapshot"
    insert_job(db, user_id=1, file_id=fid, job_type="asr")
    # No adapter.report() call — cache is empty for this file_id
    pa.reset_adapter()  # Make absolutely sure

    c = app.test_client()
    c.post("/login", json={"username": "alice", "password": "TestPass1!"})
    r = c.get("/api/queue")
    assert r.status_code == 200

    rows = json.loads(r.data)
    row = next((j for j in rows if j["file_id"] == fid), None)
    assert row is not None, f"file_id={fid} not found in queue rows: {rows}"
    assert row["progress_pct"] is None
    assert row["stage_state"] == "idle"
    # stage_label should be None or empty string when no snapshot
    assert row.get("stage_label") in (None, "")
    # v3.22 new fields — cold-start defaults
    assert isinstance(row["stages"], list)
    assert row["stage_index"] == 0
    assert isinstance(row["pipeline_kind"], str)


def test_api_queue_existing_fields_preserved(app_with_queue_and_adapter):
    """The new 3 fields are additive — all existing fields still present."""
    app, db, insert_job, _ = app_with_queue_and_adapter

    insert_job(db, user_id=1, file_id="f-fields-check", job_type="asr")

    c = app.test_client()
    c.post("/login", json={"username": "alice", "password": "TestPass1!"})
    r = c.get("/api/queue")
    assert r.status_code == 200

    rows = json.loads(r.data)
    assert len(rows) > 0, "Expected at least 1 job in queue"
    row = rows[0]

    # Existing fields per Phase 1 queue_db schema + _annotate helper
    for k in ("id", "file_id", "type", "status", "position",
              "file_name", "owner_username"):
        assert k in row, f"existing field '{k}' missing from row: {row}"

    # New additive fields must also be present (Phase B + v3.22)
    for k in ("progress_pct", "stage_label", "stage_state",
              "stages", "stage_index", "pipeline_kind"):
        assert k in row, f"new field '{k}' missing from row: {row}"
