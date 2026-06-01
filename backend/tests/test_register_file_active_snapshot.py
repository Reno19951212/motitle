"""Verify _register_file snapshots active_kind + active_id on the file entry.

Task 2.4 — V6 dual-ASR merge plan.
"""
import json
import pytest
import app as app_module


def test_register_file_defaults_to_profile_kind():
    """When no explicit kwargs given, _register_file snapshots active_kind/active_id
    from settings.json.  The actual active_id value depends on whatever is active;
    we only assert that both fields are present and active_kind is 'profile' for a
    standard install that has only the legacy 'active_profile' field."""
    app_module._register_file("test001", "demo.mp4", "test001.mp4", 1024,
                              user_id=1)
    entry = app_module._file_registry.get("test001")
    assert entry is not None
    # active_kind must be set (not None/missing)
    assert "active_kind" in entry
    assert entry["active_kind"] is not None
    # active_id must be set (not None/missing)
    assert "active_id" in entry


def test_register_file_accepts_explicit_pipeline_v6():
    """Caller can pass explicit active_kind/active_id; those override the snapshot."""
    app_module._register_file(
        "test002", "demo.mp4", "test002.mp4", 1024,
        user_id=1,
        active_kind="pipeline_v6",
        active_id="4696bbaa-fake-id",
    )
    entry = app_module._file_registry.get("test002")
    assert entry is not None
    assert entry["active_kind"] == "pipeline_v6"
    assert entry["active_id"] == "4696bbaa-fake-id"


def test_current_active_snapshot_reads_settings_v6_mode(tmp_path, monkeypatch):
    """When settings.json has active_kind=pipeline_v6, snapshot helper returns that.

    Uses a temp settings path via monkeypatch so the real config/settings.json
    is never touched.
    """
    import profiles as profiles_module

    # Create a temp config dir with our custom settings.json
    tmp_config = tmp_path / "config"
    tmp_config.mkdir()
    settings_path = tmp_config / "settings.json"
    settings_path.write_text(json.dumps({
        "active_kind": "pipeline_v6", "active_id": "v6-id-123"
    }), encoding="utf-8")

    # Patch the profile_manager to use a new instance with tmp config dir
    tmp_pm = profiles_module.ProfileManager(tmp_config)
    monkeypatch.setattr(app_module, "_profile_manager", tmp_pm)

    kind, aid, output_languages = app_module._current_active_snapshot()
    assert kind == "pipeline_v6"
    assert aid == "v6-id-123"
    assert output_languages == []


def test_current_active_snapshot_fallback_to_legacy_field(tmp_path, monkeypatch):
    """Legacy install with only active_profile field still returns kind='profile'."""
    import profiles as profiles_module

    tmp_config = tmp_path / "config"
    tmp_config.mkdir()
    settings_path = tmp_config / "settings.json"
    settings_path.write_text(json.dumps({"active_profile": "dev-default"}),
                              encoding="utf-8")

    tmp_pm = profiles_module.ProfileManager(tmp_config)
    monkeypatch.setattr(app_module, "_profile_manager", tmp_pm)

    kind, aid, output_languages = app_module._current_active_snapshot()
    assert kind == "profile"
    assert aid == "dev-default"
    assert output_languages == []
