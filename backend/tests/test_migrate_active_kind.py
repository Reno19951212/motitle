"""Test the file registry active_kind backfill migration."""
import json
import pytest
from pathlib import Path


def test_migration_backfills_legacy_entries(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "fid_legacy": {"id": "fid_legacy", "original_name": "old.mp4", "user_id": 1},
        "fid_modern": {"id": "fid_modern", "original_name": "new.mp4",
                       "user_id": 1, "active_kind": "profile", "active_id": "dev-default"},
    }))
    from scripts.migrate_active_kind import migrate_registry
    migrate_registry(registry_path, default_profile_id="prod-default")
    after = json.loads(registry_path.read_text())
    # Legacy entry gets backfilled
    assert after["fid_legacy"]["active_kind"] == "profile"
    assert after["fid_legacy"]["active_id"] == "prod-default"
    # Modern entry untouched
    assert after["fid_modern"]["active_kind"] == "profile"
    assert after["fid_modern"]["active_id"] == "dev-default"


def test_migration_is_idempotent(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "f1": {"id": "f1", "active_kind": "profile", "active_id": "dev-default"}
    }))
    from scripts.migrate_active_kind import migrate_registry
    migrate_registry(registry_path, default_profile_id="prod-default")
    migrate_registry(registry_path, default_profile_id="prod-default")
    after = json.loads(registry_path.read_text())
    assert after["f1"]["active_id"] == "dev-default"


def test_migration_prefers_profile_id_field_when_present(tmp_path):
    """v3.10 R5 Phase 2 stored profile_id on file entries; migration should use it."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({
        "f1": {"id": "f1", "user_id": 1, "profile_id": "custom-xyz"},
    }))
    from scripts.migrate_active_kind import migrate_registry
    migrate_registry(registry_path, default_profile_id="prod-default")
    after = json.loads(registry_path.read_text())
    assert after["f1"]["active_id"] == "custom-xyz"


def test_migration_no_op_when_registry_missing(tmp_path):
    """If registry.json doesn't exist, migration returns 0 without error."""
    from scripts.migrate_active_kind import migrate_registry
    n = migrate_registry(tmp_path / "nonexistent.json", default_profile_id="prod-default")
    assert n == 0
