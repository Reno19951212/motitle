"""Regression test: V6 child profile managers must be initialized with
their full subdir path, not the parent CONFIG_DIR.

Bug found 2026-05-28 (post-merge Phase 7 lite): Task 2.3 wired
TranscribeProfileManager(CONFIG_DIR) etc. — but those 3 managers store
``self.dir = config_dir`` *without* appending a subdir name. So
``get(id)`` looked up ``config/<id>.json`` instead of
``config/transcribe_profiles/<id>.json`` and returned None for every id.

This broke any V6 pipeline run with ``v6: asr_primary transcribe profile
not found`` immediately at Stage 1B.
"""
import pytest


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import importlib
    import app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_transcribe_profile_manager_finds_seasoned_profile(admin_app):
    """The 賽馬廣播 pipeline references transcribe_profile_id
    82338761-e6ed-47eb-b153-64789ed7327e (mlx-whisper ZH).
    Manager must find it after app.py boot."""
    pid = "82338761-e6ed-47eb-b153-64789ed7327e"
    result = admin_app._transcribe_profile_manager.get(pid)
    assert result is not None, (
        f"TranscribeProfileManager.get({pid!r}) returned None — "
        f"likely subdir path mismatch (got mgr.dir={admin_app._transcribe_profile_manager.dir})"
    )
    assert result["id"] == pid


def test_refiner_profile_manager_finds_v6_refiner(admin_app):
    """V6 賽馬 pipeline references refiner_profile_id
    f7f72bd9-3f27-47a4-92bd-5727f336916a."""
    rid = "f7f72bd9-3f27-47a4-92bd-5727f336916a"
    result = admin_app._refiner_profile_manager.get(rid)
    assert result is not None
    assert result["id"] == rid


def test_llm_profile_manager_lists_v6_llm(admin_app):
    """At least 1 LLM profile must be loadable (the Ollama qwen3.5 one)."""
    mgr = admin_app._llm_profile_manager
    files = list(mgr.dir.glob("*.json"))
    assert len(files) >= 1, (
        f"LLMProfileManager.dir={mgr.dir} found 0 JSONs — "
        f"likely pointing at parent CONFIG_DIR instead of llm_profiles/"
    )


def test_manager_dirs_point_at_correct_subdirs(admin_app):
    """Each child manager's .dir must end with its respective subdir name,
    not the bare CONFIG_DIR."""
    assert admin_app._transcribe_profile_manager.dir.name == "transcribe_profiles"
    assert admin_app._llm_profile_manager.dir.name == "llm_profiles"
    assert admin_app._refiner_profile_manager.dir.name == "refiner_profiles"
