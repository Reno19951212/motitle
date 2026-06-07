# backend/tests/test_beta_mode.py
import json
import os
from pathlib import Path

import pytest

import beta_mode
from profiles import ProfileManager


def test_beta_model_constants_are_parity():
    assert beta_mode.BETA_ASR_MODEL == "openai/whisper-large-v3"
    assert beta_mode.BETA_LLM_MODEL == "qwen/qwen3.5-35b-a3b"


def test_profile_manager_beta_flag_roundtrip(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"active_profile": "p1", "beta_openrouter": false}', encoding="utf-8"
    )
    pm = ProfileManager(tmp_path)
    assert pm.get_beta_mode() is False           # default off
    assert pm.set_beta_mode(True) is True
    assert pm.get_beta_mode() is True
    # the immutable update must preserve sibling keys
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert raw["active_profile"] == "p1"
    pm.set_beta_mode(False)
    assert pm.get_beta_mode() is False


def test_set_key_writes_env_and_environ(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("FLASK_SECRET_KEY=abc\n", encoding="utf-8")
    monkeypatch.setattr(beta_mode, "_ENV_PATH", env_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert beta_mode.key_status() is False
    beta_mode.set_key("sk-or-test")
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-test"
    assert beta_mode.key_status() is True
    content = env_path.read_text(encoding="utf-8")
    assert "FLASK_SECRET_KEY=abc" in content          # other line preserved
    assert "OPENROUTER_API_KEY=sk-or-test" in content


def test_set_key_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(beta_mode, "_ENV_PATH", tmp_path / ".env")
    with pytest.raises(ValueError):
        beta_mode.set_key("   ")
