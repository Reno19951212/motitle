# backend/tests/test_admin_beta_mode.py
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test")   # app.py requires it at import time
import json
import pytest

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    flask_app = app_module.app
    flask_app.config["R5_AUTH_BYPASS"] = True            # skip @admin_required
    flask_app.config["TESTING"] = True
    # isolate settings + env from the real machine
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    flask_app.config["PROFILE_MANAGER"] = pm
    monkeypatch.setattr(app_module, "_profile_manager", pm, raising=False)
    import beta_mode
    monkeypatch.setattr(beta_mode, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return flask_app.test_client()


def test_get_beta_mode_default(client):
    r = client.get("/api/admin/beta-mode")
    assert r.status_code == 200
    data = r.get_json()
    assert data["enabled"] is False
    assert data["key_configured"] is False
    assert data["llm_model"] == "qwen/qwen3.5-35b-a3b"


def test_enable_without_key_is_400(client):
    r = client.put("/api/admin/beta-mode", json={"enabled": True})
    assert r.status_code == 400


def test_set_key_then_enable(client):
    r1 = client.put("/api/admin/beta-mode", json={"api_key": "sk-or-x", "enabled": True})
    assert r1.status_code == 200
    body = r1.get_json()
    assert body["enabled"] is True
    assert body["key_configured"] is True
    # GET reflects the persisted flag
    assert client.get("/api/admin/beta-mode").get_json()["enabled"] is True


def test_empty_key_is_400(client):
    r = client.put("/api/admin/beta-mode", json={"api_key": "   "})
    assert r.status_code == 400
