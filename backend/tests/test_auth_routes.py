"""Tests for /login, /logout, /api/me routes."""
import pytest
import json


@pytest.fixture
def app_with_user(tmp_path):
    """Build a Flask app bound to a fresh per-test SQLite DB with one user."""
    import sys
    # Ensure backend dir on path; pytest conftest should set this
    from auth.users import init_db, create_user

    from auth.audit import init_audit_log
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    init_audit_log(db_path)
    create_user(db_path, username="alice", password="TestPass1!")

    from flask import Flask
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["AUTH_DB_PATH"] = db_path

    from auth.routes import bp as auth_bp
    from flask_login import LoginManager
    from auth.users import get_user_by_id
    from auth.limiter import limiter

    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)

    lm = LoginManager()
    lm.init_app(app)

    class _U:
        def __init__(self, d):
            self.id, self.username, self.is_admin = d["id"], d["username"], d["is_admin"]
            self.is_authenticated = True
            self.is_active = True
            self.is_anonymous = False
        def get_id(self):
            return str(self.id)

    @lm.user_loader
    def load(uid):
        u = get_user_by_id(db_path, int(uid))
        return _U(u) if u else None

    app.register_blueprint(auth_bp)
    return app


def test_login_with_valid_credentials_sets_session(app_with_user):
    client = app_with_user.test_client()
    r = client.post("/login",
                    json={"username": "alice", "password": "TestPass1!"})
    assert r.status_code == 200
    # session cookie set (werkzeug 3 API: get_cookie returns Cookie | None)
    assert client.get_cookie("session") is not None


def test_login_with_invalid_credentials_returns_401(app_with_user):
    client = app_with_user.test_client()
    r = client.post("/login",
                    json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401
    body = json.loads(r.data)
    assert "error" in body


def test_login_with_missing_fields_returns_400(app_with_user):
    client = app_with_user.test_client()
    r = client.post("/login", json={"username": "alice"})
    assert r.status_code == 400


def test_logout_clears_session(app_with_user):
    client = app_with_user.test_client()
    client.post("/login", json={"username": "alice", "password": "TestPass1!"})
    r = client.post("/logout")
    assert r.status_code == 200
    # /api/me now returns 401
    me = client.get("/api/me")
    assert me.status_code == 401


def test_api_me_returns_user_info_when_logged_in(app_with_user):
    client = app_with_user.test_client()
    client.post("/login", json={"username": "alice", "password": "TestPass1!"})
    r = client.get("/api/me")
    assert r.status_code == 200
    body = json.loads(r.data)
    assert body["username"] == "alice"
    assert "password_hash" not in body  # never leak
