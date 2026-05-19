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
