import pytest
import tempfile
from pathlib import Path
from llm_profiles import LLMProfileManager, validate_llm_profile


def test_validate_llm_profile_minimal():
    data = {
        "name": "Ollama Qwen3.5",
        "backend": "ollama",
        "model": "qwen3.5:35b-a3b-mlx-bf16",
        "base_url": "http://localhost:11434",
        "temperature": 0.2,
    }
    assert validate_llm_profile(data) == []


def test_validate_llm_profile_missing_backend():
    data = {"name": "x", "model": "m", "base_url": "http://localhost"}
    errors = validate_llm_profile(data)
    assert any("backend" in e for e in errors)


def test_llm_profile_manager_create_then_get(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "Test Ollama",
        "backend": "ollama",
        "model": "qwen3.5:9b",
        "base_url": "http://localhost:11434",
    }, user_id=1)
    profile = mgr.get(pid)
    assert profile["name"] == "Test Ollama"
    assert profile["user_id"] == 1


def test_llm_profile_update_if_owned(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "n1", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    updated = mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"name": "n2"})
    assert updated["name"] == "n2"
    # Non-owner cannot update
    blocked = mgr.update_if_owned(pid, user_id=2, is_admin=False, patch={"name": "x"})
    assert blocked is None


def test_llm_profile_delete_if_owned(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "n", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    # Non-owner cannot delete
    assert mgr.delete_if_owned(pid, user_id=2, is_admin=False) is False
    # Owner can
    assert mgr.delete_if_owned(pid, user_id=1, is_admin=False) is True
    assert mgr.get(pid) is None


def test_llm_profile_can_view(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "private", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    # Owner sees
    assert mgr.can_view(pid, user_id=1, is_admin=False) is True
    # Admin sees
    assert mgr.can_view(pid, user_id=999, is_admin=True) is True
    # Non-owner non-admin cannot see (not shared)
    assert mgr.can_view(pid, user_id=2, is_admin=False) is False
    # After share, non-owner can see
    mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"shared": True})
    assert mgr.can_view(pid, user_id=2, is_admin=False) is True
    # Unknown id
    assert mgr.can_view("not-a-real-id", user_id=1, is_admin=True) is False


def test_llm_profile_immutable_id_user_id_after_update(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "n", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    # Malicious patch trying to claim ownership
    updated = mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={
        "user_id": 2,         # ← attempt ownership escalation
        "id": "evil-id",       # ← attempt id swap
        "created_at": 0,       # ← attempt audit forge
    })
    assert updated is not None
    assert updated["user_id"] == 1, "user_id must be immutable through patch"
    assert updated["id"] == pid, "id must be immutable through patch"
    assert updated["created_at"] != 0, "created_at must be immutable through patch"


def test_llm_profile_strips_name_whitespace(tmp_path):
    mgr = LLMProfileManager(tmp_path)
    pid = mgr.create({
        "name": "  spaced  ", "backend": "ollama", "model": "m", "base_url": "http://x",
    }, user_id=1)
    assert mgr.get(pid)["name"] == "spaced"
    mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"name": "  renamed  "})
    assert mgr.get(pid)["name"] == "renamed"


# ============================================================
# TranscribeProfile manager tests (T5)
# ============================================================


def test_transcribe_profile_accepts_qwen3_asr(tmp_path):
    from transcribe_profiles import TranscribeProfileManager
    mgr = TranscribeProfileManager(tmp_path)
    pid = mgr.create({
        "name": "Qwen3-ASR 1.7B",
        "engine": "qwen3-asr",
        "model_size": "1.7B",
        "language": "zh",
    }, user_id=1)
    p = mgr.get(pid)
    assert p["engine"] == "qwen3-asr"
    assert p["model_size"] == "1.7B"


def test_transcribe_profile_accepts_whisper(tmp_path):
    from transcribe_profiles import TranscribeProfileManager
    mgr = TranscribeProfileManager(tmp_path)
    pid = mgr.create({
        "name": "Whisper L3",
        "engine": "whisper",
        "model_size": "large-v3",
        "language": "en",
    }, user_id=1)
    assert mgr.get(pid)["engine"] == "whisper"


def test_transcribe_profile_rejects_unknown_engine(tmp_path):
    from transcribe_profiles import validate_transcribe_profile
    errors = validate_transcribe_profile({
        "name": "x", "engine": "bogus", "language": "en",
    })
    assert any("engine" in e for e in errors)


def test_transcribe_profile_rejects_unknown_language(tmp_path):
    from transcribe_profiles import validate_transcribe_profile
    errors = validate_transcribe_profile({
        "name": "x", "engine": "whisper", "language": "klingon",
    })
    assert any("language" in e for e in errors)


def test_transcribe_profile_initial_prompt_max_512(tmp_path):
    from transcribe_profiles import validate_transcribe_profile
    errors = validate_transcribe_profile({
        "name": "x", "engine": "whisper", "language": "en",
        "initial_prompt": "x" * 600,
    })
    assert any("initial_prompt" in e for e in errors)


def test_transcribe_profile_can_view_and_immutable_fields(tmp_path):
    """Verify the pattern-setter hardening from T3 also applies to TranscribeProfile."""
    from transcribe_profiles import TranscribeProfileManager
    mgr = TranscribeProfileManager(tmp_path)
    pid = mgr.create({
        "name": "  Whisper  ", "engine": "whisper", "language": "en",
    }, user_id=1)
    # name was stripped on create
    assert mgr.get(pid)["name"] == "Whisper"
    # updated_at set on create
    assert mgr.get(pid)["updated_at"] >= mgr.get(pid)["created_at"]
    # can_view honors admin/owner/shared
    assert mgr.can_view(pid, user_id=1, is_admin=False) is True
    assert mgr.can_view(pid, user_id=999, is_admin=True) is True
    assert mgr.can_view(pid, user_id=2, is_admin=False) is False
    # Malicious patch cannot escalate ownership
    updated = mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"user_id": 2, "id": "evil"})
    assert updated["user_id"] == 1
    assert updated["id"] == pid


# ============================================================
# TranslatorProfile manager tests (T7)
# ============================================================


def test_translator_profile_valid(tmp_path):
    from translator_profiles import TranslatorProfileManager, validate_translator_profile
    data = {
        "name": "ZH→EN broadcast",
        "source_lang": "zh",
        "target_lang": "en",
        "llm_profile_id": "some-uuid",
        "prompt_template_id": "translator/zh_to_en_default",
    }
    assert validate_translator_profile(data) == []
    mgr = TranslatorProfileManager(tmp_path)
    pid = mgr.create(data, user_id=1)
    assert mgr.get(pid)["source_lang"] == "zh"
    assert mgr.get(pid)["target_lang"] == "en"


def test_translator_profile_rejects_same_source_target(tmp_path):
    from translator_profiles import validate_translator_profile
    errors = validate_translator_profile({
        "name": "bad", "source_lang": "zh", "target_lang": "zh",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert any("source_lang and target_lang must differ" in e for e in errors)


def test_translator_profile_rejects_missing_llm_profile_id(tmp_path):
    from translator_profiles import validate_translator_profile
    errors = validate_translator_profile({
        "name": "x", "source_lang": "zh", "target_lang": "en",
        "prompt_template_id": "tpl",
    })
    assert any("llm_profile_id" in e for e in errors)


def test_translator_profile_rejects_unknown_lang(tmp_path):
    from translator_profiles import validate_translator_profile
    errors = validate_translator_profile({
        "name": "x", "source_lang": "klingon", "target_lang": "en",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert any("source_lang must be in" in e for e in errors)


def test_translator_profile_pattern_hardening(tmp_path):
    """Verify pattern-setter hardening (immutable fields, name strip, can_view, updated_at)."""
    from translator_profiles import TranslatorProfileManager
    mgr = TranslatorProfileManager(tmp_path)
    pid = mgr.create({
        "name": "  Test  ", "source_lang": "zh", "target_lang": "en",
        "llm_profile_id": "x", "prompt_template_id": "y",
    }, user_id=1)
    assert mgr.get(pid)["name"] == "Test"
    assert mgr.can_view(pid, user_id=1, is_admin=False) is True
    assert mgr.can_view(pid, user_id=2, is_admin=False) is False
    assert mgr.can_view(pid, user_id=999, is_admin=True) is True
    # Immutable id/user_id/created_at
    updated = mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"user_id": 2, "id": "evil"})
    assert updated["user_id"] == 1
    assert updated["id"] == pid


# ============================================================
# RefinerProfile manager tests (T9)
# ============================================================


def test_refiner_profile_valid(tmp_path):
    from refiner_profiles import RefinerProfileManager, validate_refiner_profile
    data = {
        "name": "ZH broadcast HK",
        "lang": "zh",
        "style": "broadcast-hk",
        "llm_profile_id": "llm1",
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }
    assert validate_refiner_profile(data) == []
    mgr = RefinerProfileManager(tmp_path)
    pid = mgr.create(data, user_id=1)
    assert mgr.get(pid)["style"] == "broadcast-hk"


def test_refiner_profile_rejects_missing_lang(tmp_path):
    from refiner_profiles import validate_refiner_profile
    errors = validate_refiner_profile({
        "name": "x", "style": "broadcast",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert any("lang" in e for e in errors)


def test_refiner_profile_rejects_missing_style(tmp_path):
    from refiner_profiles import validate_refiner_profile
    errors = validate_refiner_profile({
        "name": "x", "lang": "zh",
        "llm_profile_id": "x", "prompt_template_id": "y",
    })
    assert any("style" in e for e in errors)


def test_refiner_profile_pattern_hardening(tmp_path):
    """Verify pattern-setter hardening (immutable fields, name strip, can_view)."""
    from refiner_profiles import RefinerProfileManager
    mgr = RefinerProfileManager(tmp_path)
    pid = mgr.create({
        "name": "  Test  ", "lang": "zh", "style": "broadcast-hk",
        "llm_profile_id": "x", "prompt_template_id": "y",
    }, user_id=1)
    assert mgr.get(pid)["name"] == "Test"
    assert mgr.can_view(pid, user_id=1, is_admin=False) is True
    assert mgr.can_view(pid, user_id=2, is_admin=False) is False
    assert mgr.can_view(pid, user_id=999, is_admin=True) is True
    updated = mgr.update_if_owned(pid, user_id=1, is_admin=False, patch={"user_id": 2, "id": "evil"})
    assert updated["user_id"] == 1
    assert updated["id"] == pid
