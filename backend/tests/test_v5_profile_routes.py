import pytest
from flask import Flask
from routes.llm_profiles import bp as llm_bp


def _make_app(user_id=1, is_admin=False):
    """Build a minimal Flask app stub with the blueprint registered.

    Stubs flask-login current_user; doesn't actually run @login_required
    (skipped via LOGIN_DISABLED config + monkeypatch on current_user where needed).
    """
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.register_blueprint(llm_bp)

    from flask_login import LoginManager
    lm = LoginManager()
    lm.init_app(app)

    class _User:
        def __init__(self, uid, admin):
            self.id = uid
            self.is_admin = admin
            self.is_authenticated = True
            self.is_active = True
            self.is_anonymous = False
            def get_id(): return str(uid)
            self.get_id = get_id

    @lm.request_loader
    def _load(request):
        return _User(user_id, is_admin)

    return app


def test_llm_profiles_list_empty(monkeypatch, tmp_path):
    import app as _app
    from llm_profiles import LLMProfileManager
    mgr = LLMProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_llm_profile_manager", mgr, raising=False)
    app = _make_app(user_id=1, is_admin=False)
    client = app.test_client()
    resp = client.get("/api/llm_profiles")
    assert resp.status_code == 200
    assert resp.json == {"profiles": []}


def test_llm_profiles_create_then_get(monkeypatch, tmp_path):
    import app as _app
    from llm_profiles import LLMProfileManager
    mgr = LLMProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_llm_profile_manager", mgr, raising=False)
    app = _make_app(user_id=1, is_admin=False)
    client = app.test_client()
    resp = client.post("/api/llm_profiles", json={
        "name": "test", "backend": "ollama", "model": "m", "base_url": "http://x",
    })
    assert resp.status_code == 201
    pid = resp.json["id"]
    assert resp.json["user_id"] == 1
    resp2 = client.get(f"/api/llm_profiles/{pid}")
    assert resp2.status_code == 200
    assert resp2.json["name"] == "test"


def test_llm_profiles_invalid_payload_400(monkeypatch, tmp_path):
    import app as _app
    from llm_profiles import LLMProfileManager
    monkeypatch.setattr(_app, "_llm_profile_manager", LLMProfileManager(tmp_path), raising=False)
    app = _make_app(user_id=1)
    client = app.test_client()
    resp = client.post("/api/llm_profiles", json={"name": ""})
    assert resp.status_code == 400
    assert "error" in resp.json


def test_llm_profiles_get_forbidden_for_non_owner(monkeypatch, tmp_path):
    import app as _app
    from llm_profiles import LLMProfileManager
    mgr = LLMProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_llm_profile_manager", mgr, raising=False)
    pid = mgr.create({
        "name": "private", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    # User 2 (non-admin) cannot view
    app = _make_app(user_id=2, is_admin=False)
    resp = app.test_client().get(f"/api/llm_profiles/{pid}")
    assert resp.status_code == 403


def test_llm_profiles_404_for_admin_only(monkeypatch, tmp_path):
    import app as _app
    from llm_profiles import LLMProfileManager
    monkeypatch.setattr(_app, "_llm_profile_manager", LLMProfileManager(tmp_path), raising=False)
    # Admin requesting nonexistent → 404
    app = _make_app(user_id=999, is_admin=True)
    resp = app.test_client().get("/api/llm_profiles/missing-id")
    assert resp.status_code == 404


def test_llm_profiles_delete_only_owner(monkeypatch, tmp_path):
    import app as _app
    from llm_profiles import LLMProfileManager
    mgr = LLMProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_llm_profile_manager", mgr, raising=False)
    pid = mgr.create({
        "name": "n", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    # User 2 cannot delete
    app2 = _make_app(user_id=2, is_admin=False)
    resp = app2.test_client().delete(f"/api/llm_profiles/{pid}")
    assert resp.status_code == 403
    # Owner can
    app1 = _make_app(user_id=1, is_admin=False)
    resp = app1.test_client().delete(f"/api/llm_profiles/{pid}")
    assert resp.status_code == 200
    assert resp.json["deleted"] == pid
