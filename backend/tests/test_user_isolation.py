"""Tests: file ownership + isolation across users."""
import pytest


@pytest.fixture
def two_users(tmp_path):
    from auth.users import init_db, create_user
    db = str(tmp_path / "app.db")
    init_db(db)
    create_user(db, "alice", "pw")  # uid 1
    create_user(db, "bob", "pw")    # uid 2
    return db


def test_list_files_filters_by_owner(two_users, tmp_path, monkeypatch):
    """alice's GET /api/files returns only alice's files (not bob's)."""
    from auth.routes import bp as auth_bp, _LoginUser
    from auth.users import get_user_by_id
    from flask import Flask
    from flask_login import LoginManager

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    app.config["AUTH_DB_PATH"] = two_users
    lm = LoginManager()
    lm.init_app(app)
    @lm.user_loader
    def _load(uid):
        u = get_user_by_id(two_users, int(uid))
        return _LoginUser(u) if u else None
    app.register_blueprint(auth_bp)

    # Mock registry
    fake_registry = {
        "f-alice-1": {"id": "f-alice-1", "user_id": 1, "original_name": "a.mp4"},
        "f-bob-1": {"id": "f-bob-1", "user_id": 2, "original_name": "b.mp4"},
    }
    import app as app_module
    monkeypatch.setattr(app_module, "_file_registry", fake_registry)

    # Add a /api/files-style route that uses the filter logic
    from flask_login import login_required, current_user

    @app.get("/api/files")
    @login_required
    def list_files():
        from app import _filter_files_by_owner
        files = _filter_files_by_owner(fake_registry, current_user)
        return list(files.values())

    client = app.test_client()
    client.post("/login", json={"username": "alice", "password": "pw"})
    rv = client.get("/api/files")
    files = rv.get_json()
    assert len(files) == 1
    assert files[0]["id"] == "f-alice-1"


def test_admin_sees_all_files(two_users, monkeypatch):
    from auth.users import get_user_by_username
    # promote alice to admin
    import sqlite3
    conn = sqlite3.connect(two_users)
    conn.execute("UPDATE users SET is_admin=1 WHERE username='alice'")
    conn.commit()
    conn.close()

    from app import _filter_files_by_owner

    class _Admin:
        is_admin = True
        id = 1

    fake_registry = {
        "f-alice-1": {"id": "f-alice-1", "user_id": 1},
        "f-bob-1": {"id": "f-bob-1", "user_id": 2},
    }
    out = _filter_files_by_owner(fake_registry, _Admin())
    assert len(out) == 2
