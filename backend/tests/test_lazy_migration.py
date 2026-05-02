"""Test lazy A3 migration on render endpoint (Mod 6 / v3.9 Task 21).

When the active profile has ``translation.a3_ensemble == True`` but the cached
translations were produced before A3 (no per-segment ``source`` field), the
``POST /api/render`` endpoint must:

1. Spawn a background re-translation thread (via ``_run_a3_migrate_async``).
2. Return HTTP 202 with ``{status: "migrating"}`` so the client can show
   progress UI instead of blocking on the original render.
3. NOT proceed with the existing render path — the user retries after
   ``a3_migration_complete`` arrives.

When ``a3_ensemble`` is disabled (legacy clients), the lazy-migration check
must be a no-op and the existing render flow proceeds unchanged.

When translations already carry a ``source`` field (post-A3), the migration
also does not trigger.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _seed_profile(tmp_path, translation_overrides):
    """Create profile + activate, return profile id.

    translation_overrides: dict merged into profile.translation.
    """
    import app as appmod
    appmod._init_profile_manager(tmp_path)

    base_profile = {
        "name": "lazy-mig-test",
        "description": "",
        "asr": {"engine": "whisper", "model": "tiny", "language": "en"},
        "translation": {"engine": "mock", **translation_overrides},
        "font": {"family": "Noto Sans TC", "size": 36},
    }
    profile = appmod._profile_manager.create(base_profile)
    appmod._profile_manager.set_active(profile["id"])
    return profile["id"]


@pytest.fixture
def client_legacy_translations(tmp_path):
    """File with translations missing the ``source`` field + a3_ensemble profile."""
    from app import app, _init_glossary_manager, _file_registry, _registry_lock

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    _seed_profile(tmp_path, {"a3_ensemble": True})

    file_id = "lazy-mig-001"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": "Hello."}],
            "translations": [
                # legacy shape — note: no `source` field
                {"start": 0.0, "end": 2.5, "en_text": "Hello.", "zh_text": "你好。", "status": "approved"},
            ],
            "translation_status": "done",
            "status": "done",
        }

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, file_id

    with _registry_lock:
        _file_registry.pop(file_id, None)


@pytest.fixture
def client_a3_translations(tmp_path):
    """File with A3-format translations (with ``source``) + a3_ensemble profile."""
    from app import app, _init_glossary_manager, _file_registry, _registry_lock

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    _seed_profile(tmp_path, {"a3_ensemble": True})

    file_id = "lazy-mig-002"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": "Hello."}],
            "translations": [
                # A3 shape — has `source` field
                {"start": 0.0, "end": 2.5, "en_text": "Hello.", "zh_text": "你好。", "status": "approved", "source": "k4"},
            ],
            "translation_status": "done",
            "status": "done",
        }

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, file_id

    with _registry_lock:
        _file_registry.pop(file_id, None)


@pytest.fixture
def client_legacy_no_a3_profile(tmp_path):
    """Legacy translations + profile WITHOUT a3_ensemble (no migration should fire)."""
    from app import app, _init_glossary_manager, _file_registry, _registry_lock

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    _seed_profile(tmp_path, {"a3_ensemble": False})

    file_id = "lazy-mig-003"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": "Hello."}],
            "translations": [
                {"start": 0.0, "end": 2.5, "en_text": "Hello.", "zh_text": "你好。", "status": "approved"},
            ],
            "translation_status": "done",
            "status": "done",
        }

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, file_id

    with _registry_lock:
        _file_registry.pop(file_id, None)


def test_render_legacy_translations_triggers_migration(client_legacy_translations):
    """Legacy translations + a3_ensemble profile → 202 + background thread spawned."""
    client, file_id = client_legacy_translations

    # Patch the async migrator so the test doesn't actually re-translate.
    with patch("app._run_a3_migrate_async") as mock_migrate:
        resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})

    assert resp.status_code == 202
    data = resp.get_json()
    assert data.get("status") == "migrating"
    assert data.get("file_id") == file_id
    # Background thread target was invoked (started with file_id arg).
    assert mock_migrate.called
    args, _ = mock_migrate.call_args
    assert args[0] == file_id


def test_render_a3_translations_proceeds_normally(client_a3_translations):
    """Translations already in A3 format → no migration, proceeds to normal render."""
    client, file_id = client_a3_translations

    with patch("app._run_a3_migrate_async") as mock_migrate:
        resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})

    # Migrate must NOT be called.
    assert not mock_migrate.called
    # Normal render kickoff returns 202 with render_id (not the migrating shape).
    assert resp.status_code == 202
    data = resp.get_json()
    assert data.get("status") == "processing"
    assert "render_id" in data
    assert data.get("status") != "migrating"


def test_render_legacy_without_a3_profile_proceeds_normally(client_legacy_no_a3_profile):
    """a3_ensemble disabled → legacy render path runs even though translations lack `source`."""
    client, file_id = client_legacy_no_a3_profile

    with patch("app._run_a3_migrate_async") as mock_migrate:
        resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})

    assert not mock_migrate.called
    assert resp.status_code == 202
    data = resp.get_json()
    # Normal render path.
    assert data.get("status") == "processing"
    assert "render_id" in data
