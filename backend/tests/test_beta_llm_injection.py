# backend/tests/test_beta_llm_injection.py
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test")   # app.py requires it at import time
import pytest
import app as app_module
from profiles import ProfileManager


@pytest.fixture
def pm(tmp_path, monkeypatch):
    m = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", m, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    return m


def test_llm_call_uses_openrouter_when_beta_on(pm, monkeypatch):
    pm.set_beta_mode(True)
    captured = {}

    class FakeEng:
        def __init__(self, cfg): captured["cfg"] = cfg
        def _call_ollama(self, system, user, temp):
            captured["temp"] = temp
            return "OR-RESULT"

    import translation.openrouter_engine as ore
    monkeypatch.setattr(ore, "OpenRouterTranslationEngine", FakeEng)

    call = app_module._make_ollama_llm_call()
    assert call("sys", "usr") == "OR-RESULT"
    assert captured["cfg"]["openrouter_model"] == "qwen/qwen3.5-35b-a3b"
    assert captured["temp"] == 0.3


def test_llm_call_uses_ollama_when_beta_off(pm, monkeypatch):
    pm.set_beta_mode(False)
    monkeypatch.setattr(app_module, "_make_ollama_llm_call_engine",
                        lambda: type("E", (), {"_call_ollama": lambda self, s, u, t: "LOCAL"})())
    call = app_module._make_ollama_llm_call()
    assert call("sys", "usr") == "LOCAL"


def test_llm_call_raises_when_beta_on_key_missing(pm, monkeypatch):
    pm.set_beta_mode(True)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    call = app_module._make_ollama_llm_call()
    with pytest.raises(ConnectionError):
        call("sys", "usr")
