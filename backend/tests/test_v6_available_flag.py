"""Test that V6_AVAILABLE is set correctly based on venv_qwen presence."""
import pytest


def test_v6_available_flag_set_at_boot():
    import app
    assert "V6_AVAILABLE" in app.app.config
    assert isinstance(app.app.config["V6_AVAILABLE"], bool)


def test_api_me_includes_v6_available(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import importlib, app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    _app.app.config["LOGIN_DISABLED"] = True
    client = _app.app.test_client()
    r = client.get("/api/me")
    body = r.get_json()
    assert "v6_available" in body
    assert isinstance(body["v6_available"], bool)
