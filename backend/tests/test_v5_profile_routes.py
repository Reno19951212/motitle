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


# ============================================================
# TranscribeProfile REST blueprint tests (T6)
# ============================================================


def _make_app_with_bp(bp, user_id=1, is_admin=False):
    """Mirror of _make_app but for an arbitrary blueprint (T6 helper)."""
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.register_blueprint(bp)

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


def test_transcribe_profiles_create_get(monkeypatch, tmp_path):
    from routes.transcribe_profiles import bp as tr_bp
    from transcribe_profiles import TranscribeProfileManager
    import app as _app
    mgr = TranscribeProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_transcribe_profile_manager", mgr, raising=False)
    app = _make_app_with_bp(tr_bp, user_id=1, is_admin=False)
    client = app.test_client()
    resp = client.post("/api/transcribe_profiles", json={
        "name": "qwen3", "engine": "qwen3-asr", "language": "zh",
    })
    assert resp.status_code == 201
    assert resp.json["engine"] == "qwen3-asr"
    pid = resp.json["id"]
    resp2 = client.get(f"/api/transcribe_profiles/{pid}")
    assert resp2.status_code == 200
    assert resp2.json["name"] == "qwen3"


def test_asr_profiles_returns_deprecation_header(monkeypatch, tmp_path):
    """Legacy /api/asr_profiles still responds + sets Deprecation header per spec §7."""
    import app as _app
    from routes.asr_profiles import bp as asr_bp
    # Wire a fake asr_profile_manager so the route doesn't crash
    from asr_profiles import ASRProfileManager
    monkeypatch.setattr(_app, "_asr_profile_manager", ASRProfileManager(tmp_path), raising=False)
    app = _make_app_with_bp(asr_bp, user_id=1, is_admin=False)
    client = app.test_client()
    resp = client.get("/api/asr_profiles")
    assert resp.headers.get("Deprecation") == "true"
    assert "/api/transcribe_profiles" in resp.headers.get("Link", "")


# ============================================================
# TranslatorProfile REST blueprint tests (T8)
# ============================================================


def test_translator_profiles_create_get(monkeypatch, tmp_path):
    from routes.translator_profiles import bp as tr_bp
    from translator_profiles import TranslatorProfileManager
    import app as _app
    mgr = TranslatorProfileManager(tmp_path)
    monkeypatch.setattr(_app, "_translator_profile_manager", mgr, raising=False)
    app = _make_app_with_bp(tr_bp, user_id=1, is_admin=False)
    client = app.test_client()
    resp = client.post("/api/translator_profiles", json={
        "name": "zh->en",
        "source_lang": "zh", "target_lang": "en",
        "llm_profile_id": "llm1",
        "prompt_template_id": "translator/zh_to_en_default",
    })
    assert resp.status_code == 201
    assert resp.json["source_lang"] == "zh"


def test_translator_profiles_rejects_same_lang(monkeypatch, tmp_path):
    from routes.translator_profiles import bp as tr_bp
    from translator_profiles import TranslatorProfileManager
    import app as _app
    monkeypatch.setattr(_app, "_translator_profile_manager", TranslatorProfileManager(tmp_path), raising=False)
    app = _make_app_with_bp(tr_bp, user_id=1)
    resp = app.test_client().post("/api/translator_profiles", json={
        "name": "bad", "source_lang": "zh", "target_lang": "zh",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert resp.status_code == 400


# ============================================================
# RefinerProfile REST blueprint tests (T10)
# ============================================================


def test_refiner_profiles_create(monkeypatch, tmp_path):
    from routes.refiner_profiles import bp as ref_bp
    from refiner_profiles import RefinerProfileManager
    import app as _app
    monkeypatch.setattr(_app, "_refiner_profile_manager", RefinerProfileManager(tmp_path), raising=False)
    app = _make_app_with_bp(ref_bp, user_id=1, is_admin=False)
    client = app.test_client()
    resp = client.post("/api/refiner_profiles", json={
        "name": "zh-bc",
        "lang": "zh", "style": "broadcast-hk",
        "llm_profile_id": "x",
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    })
    assert resp.status_code == 201
    assert resp.json["lang"] == "zh"


def test_mt_profiles_returns_deprecation_header(monkeypatch, tmp_path):
    from flask import Flask
    from flask_login import LoginManager
    from routes.mt_profiles import bp as mt_bp
    import app as _app
    # Wire mt_profile_manager (v4 class is MTProfileManager — capital M-T)
    from mt_profiles import MTProfileManager
    monkeypatch.setattr(_app, "_mt_profile_manager", MTProfileManager(tmp_path), raising=False)
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.register_blueprint(mt_bp)
    lm = LoginManager()
    lm.init_app(app)

    class _U:
        def __init__(self):
            self.id = 1
            self.is_admin = False
            self.is_authenticated = True
            self.is_active = True
            self.is_anonymous = False

        def get_id(self):
            return "1"

    @lm.request_loader
    def _load(req):
        return _U()

    client = app.test_client()
    resp = client.get("/api/mt_profiles")
    assert resp.headers.get("Deprecation") == "true"
    assert "/api/refiner_profiles" in resp.headers.get("Link", "")
