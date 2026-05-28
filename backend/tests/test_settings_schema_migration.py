"""Test settings.json schema migration: active_kind + active_id with
backward-compat mirror to active_profile."""
import json
import pytest
from pathlib import Path
from profiles import ProfileManager

VALID_PROFILE = {
    "name": "Test", "description": "",
    "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
    "translation": {"engine": "mock", "glossary_id": None, "temperature": 0.1},
}


def test_set_active_writes_all_three_fields(tmp_path):
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    mgr.set_active(p["id"])
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["active_kind"] == "profile"
    assert settings["active_id"] == p["id"]
    assert settings["active_profile"] == p["id"]


def test_get_active_reads_new_schema(tmp_path):
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({
        "active_kind": "profile", "active_id": p["id"], "active_profile": p["id"]
    }))
    assert mgr.get_active()["id"] == p["id"]


def test_get_active_legacy_only_field_still_works(tmp_path):
    """Old install with only active_profile set: must still load active."""
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({"active_profile": p["id"]}))
    assert mgr.get_active()["id"] == p["id"]


def test_get_active_returns_none_when_active_kind_is_pipeline(tmp_path):
    """When active_kind=pipeline_v6, ProfileManager.get_active returns None
    (it's not its responsibility — PipelineManager handles it)."""
    mgr = ProfileManager(tmp_path)
    mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({
        "active_kind": "pipeline_v6", "active_id": "4696bbaa-...",
    }))
    assert mgr.get_active() is None


def test_set_active_does_not_drop_other_settings(tmp_path):
    mgr = ProfileManager(tmp_path)
    p = mgr.create(VALID_PROFILE)
    (tmp_path / "settings.json").write_text(json.dumps({
        "active_profile": None, "other_key": "preserved"
    }))
    mgr.set_active(p["id"])
    settings = json.loads((tmp_path / "settings.json").read_text())
    assert settings["other_key"] == "preserved"


def test_set_active_to_unknown_id_returns_none(tmp_path):
    mgr = ProfileManager(tmp_path)
    assert mgr.set_active("nonexistent") is None
    settings = json.loads((tmp_path / "settings.json").read_text())
    # should NOT have overwritten settings with bogus id
    assert settings.get("active_id") != "nonexistent"
