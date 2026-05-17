"""Tests for /api/queue and /api/queue/<id>.

Package renamed from `queue` (plan) to `jobqueue` to keep stdlib `queue` accessible.
"""
import pytest
import json


@pytest.fixture
def app_with_queue(tmp_path):
    from auth.users import init_db, create_user
    from jobqueue.db import init_jobs_table, insert_job
    from flask import Flask
    from flask_login import LoginManager
    from auth.users import get_user_by_id
    from auth.routes import bp as auth_bp, _LoginUser
    from jobqueue.routes import bp as queue_bp, set_db_path

    db = str(tmp_path / "app.db")
    init_db(db)
    init_jobs_table(db)
    create_user(db, "alice", "TestPass1!")
    create_user(db, "bob", "TestPass1!")

    # Pre-seed jobs
    insert_job(db, user_id=1, file_id="f-alice-1", job_type="pipeline_run")
    insert_job(db, user_id=2, file_id="f-bob-1", job_type="pipeline_run")

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
    return app


def test_queue_requires_login(app_with_queue):
    c = app_with_queue.test_client()
    r = c.get("/api/queue")
    assert r.status_code == 401


def test_queue_returns_only_own_jobs_for_user(app_with_queue):
    c = app_with_queue.test_client()
    c.post("/login", json={"username": "alice", "password": "TestPass1!"})
    r = c.get("/api/queue")
    assert r.status_code == 200
    body = json.loads(r.data)
    assert all(j["owner_username"] == "alice" for j in body)
    assert len(body) == 1
