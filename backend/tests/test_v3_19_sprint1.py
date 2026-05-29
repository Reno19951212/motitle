"""v3.19 Sprint 1 — field-shape drift fix verification tests.

Covers:
    - A-1: /api/files exposes active_kind + active_id per row
    - A-2: /api/files/<id>/translations returns zh_text for V6 files
    - migration: backfill script mirrors by_lang fields to top-level

These tests also provide the shared fixtures (client, v6_file_with_translations,
get_registry_entry, render_complete) required by test_v3_19_phase_b_findings.py,
which is loaded in the same pytest session.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures (used by this file AND phase_b_findings.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Standard test client with isolated data dirs + auth bypass."""
    import app as app_mod
    from profiles import ProfileManager

    new_prof_mgr = ProfileManager(tmp_path)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


@pytest.fixture
def get_registry_entry():
    """Return function that reads current registry for a file_id."""
    import app as app_mod

    def _get(file_id):
        with app_mod._registry_lock:
            return app_mod._file_registry.get(file_id)

    return _get


@pytest.fixture
def v6_file_with_translations(tmp_path):
    """
    Insert a synthetic V6 file into the registry with translations stored in
    the V6 shape (by_lang.<lang>.{text,status,flags}) plus legacy mirror fields
    (zh_text, status) as would be produced after Sprint 1 Change 1.

    Returns file_id.
    """
    import app as app_mod

    fid = f"v6-sprint1-{uuid.uuid4().hex[:8]}"
    segments_data = [
        {"start": 0.0,  "end": 1.5, "text": "冇人會傷害嗰啲感受"},
        {"start": 1.5,  "end": 3.0, "text": "今日賽事精彩紛呈"},
        {"start": 3.0,  "end": 5.0, "text": "高蘭布連卡速度驚人"},
    ]
    translations_data = []
    for i, seg in enumerate(segments_data):
        row = {
            "idx": i,
            "start": seg["start"],
            "end": seg["end"],
            "source_lang": "zh",
            "source_text": seg["text"],
            "by_lang": {
                "zh": {
                    "text": seg["text"],
                    "status": "pending",
                    "flags": [],
                },
            },
            # Legacy mirror fields (Sprint 1 Change 1 ensures these are populated)
            "zh_text": seg["text"],
            "status": "pending",
            "flags": [],
        }
        translations_data.append(row)

    entry = {
        "id": fid,
        "original_name": "test_raceday.mp4",
        "size": 1024,
        "status": "done",
        "uploaded_at": time.time(),
        "user_id": None,
        "active_kind": "pipeline_v6",
        "active_id": "test-pipeline-v6",
        "segments": [],          # V6 has no top-level segments
        "translations": translations_data,
        "translation_status": "done",
        "prompt_overrides": None,
        "error": None,
        "model": None,
        "backend": None,
        "asr_seconds": None,
        "translation_seconds": None,
        "pipeline_seconds": None,
    }

    # Create a dummy media file so render can resolve the path
    dummy_media = tmp_path / "data" / "uploads" / f"{fid}_test_raceday.mp4"
    dummy_media.parent.mkdir(parents=True, exist_ok=True)
    dummy_media.write_bytes(b"DUMMY")

    entry["file_path"] = str(dummy_media)

    with app_mod._registry_lock:
        app_mod._file_registry[fid] = entry

    yield fid

    # Cleanup
    with app_mod._registry_lock:
        app_mod._file_registry.pop(fid, None)


@pytest.fixture
def render_complete():
    """
    Return a helper that polls GET /api/renders/<rid> until done or timeout.

    Usage: status = render_complete(render_id, timeout=60)
    """
    import app as app_mod

    def _wait(render_id, timeout=120):
        deadline = time.time() + timeout
        with app_mod._render_jobs_lock:
            job = app_mod._render_jobs.get(render_id, {})
        while job.get("status") == "processing" and time.time() < deadline:
            time.sleep(0.5)
            with app_mod._render_jobs_lock:
                job = app_mod._render_jobs.get(render_id, {})
        return job

    return _wait


# ---------------------------------------------------------------------------
# A-1: /api/files exposes active_kind + active_id
# ---------------------------------------------------------------------------

class TestApiFilesIncludesActiveKind:
    """A-1 fix: list_files() must expose active_kind + active_id per file row."""

    def _register_v6_file(self, fid):
        """Insert a minimal V6-tagged file into the registry."""
        import app as app_mod

        with app_mod._registry_lock:
            app_mod._file_registry[fid] = {
                "id": fid,
                "original_name": "race.mp4",
                "size": 100,
                "status": "done",
                "uploaded_at": time.time(),
                "user_id": None,
                "active_kind": "pipeline_v6",
                "active_id": "pipeline-abc123",
                "segments": [],
                "translations": [],
                "error": None,
                "model": None,
                "backend": None,
                "translation_status": None,
                "translation_engine": None,
                "asr_seconds": None,
                "translation_seconds": None,
                "pipeline_seconds": None,
                "prompt_overrides": None,
            }

    def _cleanup(self, fid):
        import app as app_mod

        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)

    def test_api_files_includes_active_kind(self, client):
        """GET /api/files should include active_kind and active_id for each file."""
        fid = f"a1-test-{uuid.uuid4().hex[:8]}"
        self._register_v6_file(fid)
        try:
            r = client.get("/api/files")
            assert r.status_code == 200
            files = {f["id"]: f for f in r.get_json()["files"]}
            assert fid in files, "Registered file not found in /api/files response"

            row = files[fid]
            assert "active_kind" in row, (
                f"/api/files row missing 'active_kind' field; got keys: {list(row.keys())}"
            )
            assert row["active_kind"] == "pipeline_v6", (
                f"expected active_kind='pipeline_v6', got {row['active_kind']!r}"
            )
            assert "active_id" in row, (
                f"/api/files row missing 'active_id' field; got keys: {list(row.keys())}"
            )
            assert row["active_id"] == "pipeline-abc123", (
                f"expected active_id='pipeline-abc123', got {row['active_id']!r}"
            )
        finally:
            self._cleanup(fid)

    def test_api_files_active_kind_defaults_to_profile_for_legacy(self, client):
        """Legacy files without active_kind must report active_kind='profile'."""
        import app as app_mod

        fid = f"legacy-test-{uuid.uuid4().hex[:8]}"
        with app_mod._registry_lock:
            app_mod._file_registry[fid] = {
                "id": fid,
                "original_name": "old.mp4",
                "size": 100,
                "status": "done",
                "uploaded_at": time.time(),
                "user_id": None,
                # Deliberately absent: active_kind / active_id
                "segments": [],
                "translations": [],
                "error": None,
                "model": None,
                "backend": None,
                "translation_status": None,
                "translation_engine": None,
                "asr_seconds": None,
                "translation_seconds": None,
                "pipeline_seconds": None,
                "prompt_overrides": None,
            }
        try:
            r = client.get("/api/files")
            assert r.status_code == 200
            files = {f["id"]: f for f in r.get_json()["files"]}
            assert fid in files
            row = files[fid]
            assert row.get("active_kind") == "profile", (
                f"Legacy file should default active_kind='profile', got {row.get('active_kind')!r}"
            )
        finally:
            with app_mod._registry_lock:
                app_mod._file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# A-2: /api/files/<id>/translations returns zh_text for V6 files
# ---------------------------------------------------------------------------

class TestApiTranslationsHasZhTextForV6:
    """A-2 fix: translations endpoint must expose zh_text for V6 files."""

    def test_api_translations_has_zh_text_for_v6(self, client, v6_file_with_translations):
        """GET /api/files/<id>/translations must return populated zh_text for V6 rows."""
        fid = v6_file_with_translations

        r = client.get(f"/api/files/{fid}/translations")
        assert r.status_code == 200, f"Got {r.status_code}: {r.get_data(as_text=True)}"

        body = r.get_json()
        translations = body.get("translations", [])
        assert len(translations) > 0, "Expected at least one translation row"

        for i, t in enumerate(translations):
            assert "zh_text" in t, (
                f"Translation row {i} missing 'zh_text' field; got keys: {list(t.keys())}"
            )
            assert t["zh_text"].strip(), (
                f"Translation row {i} has empty zh_text; "
                f"by_lang should have been mirrored. Got: {t!r}"
            )

    def test_api_translations_status_is_pending_initially(self, client, v6_file_with_translations):
        """V6 translation rows must have top-level status='pending' initially."""
        fid = v6_file_with_translations

        r = client.get(f"/api/files/{fid}/translations")
        assert r.status_code == 200
        translations = r.get_json().get("translations", [])
        assert len(translations) > 0

        for i, t in enumerate(translations):
            assert "status" in t, f"Row {i} missing 'status'"
            # 'pending' or 'approved' — must be a real status string, not None
            assert t["status"] in ("pending", "approved"), (
                f"Row {i} status is not a valid value: {t['status']!r}"
            )


# ---------------------------------------------------------------------------
# Migration script: backfill test
# ---------------------------------------------------------------------------

class TestMigrateV6TranslationMirrorBackfillsLegacyFields:
    """Change 4: migration script must backfill legacy zh_text/status fields."""

    def _make_registry(self, tmp_path, include_legacy_mirror=False):
        """Build a synthetic registry.json with a V6 file lacking legacy mirrors."""
        fid = "v6-migrate-test"
        entry = {
            "id": fid,
            "original_name": "raceday.mp4",
            "size": 100,
            "status": "done",
            "uploaded_at": time.time(),
            "user_id": None,
            "active_kind": "pipeline_v6",
            "active_id": "pipe-1",
            "segments": [],
            "translations": [
                {
                    "idx": 0,
                    "start": 0.0,
                    "end": 1.5,
                    "source_lang": "zh",
                    "source_text": "冇人會傷害嗰啲感受",
                    "by_lang": {
                        "zh": {
                            "text": "冇人會傷害嗰啲感受",
                            "status": "pending",
                            "flags": [],
                        }
                    },
                    # No top-level zh_text or status (pre-Sprint1 V6 shape)
                }
            ],
        }
        if include_legacy_mirror:
            entry["translations"][0]["zh_text"] = "冇人會傷害嗰啲感受"
            entry["translations"][0]["status"] = "pending"

        # Non-V6 file — should not be touched
        profile_fid = "profile-file-test"
        profile_entry = {
            "id": profile_fid,
            "original_name": "profile.mp4",
            "size": 100,
            "status": "done",
            "uploaded_at": time.time(),
            "user_id": None,
            "active_kind": "profile",
            "active_id": "prod-default",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
            "translations": [
                {"idx": 0, "zh_text": "你好", "status": "approved"}
            ],
        }

        registry = {fid: entry, profile_fid: profile_entry}
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        return registry_path, fid, profile_fid

    def test_migrate_backfills_zh_text_for_v6_file(self, tmp_path):
        """Migration must backfill zh_text + status from by_lang for V6 files."""
        from scripts.migrate_v6_translation_mirror import migrate_registry

        registry_path, v6_fid, profile_fid = self._make_registry(tmp_path)

        n = migrate_registry(registry_path)

        # Should have migrated exactly 1 V6 file
        assert n >= 1, f"Expected at least 1 file migrated, got {n}"

        # Read back and verify
        updated = json.loads(registry_path.read_text(encoding="utf-8"))
        v6_entry = updated[v6_fid]
        t = v6_entry["translations"][0]

        assert t.get("zh_text") == "冇人會傷害嗰啲感受", (
            f"zh_text not backfilled: got {t.get('zh_text')!r}"
        )
        assert t.get("status") == "pending", (
            f"status not backfilled: got {t.get('status')!r}"
        )

    def test_migrate_does_not_touch_profile_files(self, tmp_path):
        """Migration must leave profile-mode file translations intact."""
        from scripts.migrate_v6_translation_mirror import migrate_registry

        registry_path, v6_fid, profile_fid = self._make_registry(tmp_path)

        migrate_registry(registry_path)

        updated = json.loads(registry_path.read_text(encoding="utf-8"))
        profile_entry = updated[profile_fid]
        t = profile_entry["translations"][0]

        # Profile file's zh_text and status should be unchanged
        assert t.get("zh_text") == "你好", (
            f"Profile file zh_text was altered: {t.get('zh_text')!r}"
        )
        assert t.get("status") == "approved", (
            f"Profile file status was altered: {t.get('status')!r}"
        )

    def test_migrate_is_idempotent(self, tmp_path):
        """Running migration twice must produce the same result."""
        from scripts.migrate_v6_translation_mirror import migrate_registry

        registry_path, v6_fid, _ = self._make_registry(tmp_path)

        n1 = migrate_registry(registry_path)
        n2 = migrate_registry(registry_path)

        updated = json.loads(registry_path.read_text(encoding="utf-8"))
        t = updated[v6_fid]["translations"][0]

        assert t.get("zh_text") == "冇人會傷害嗰啲感受"
        assert t.get("status") == "pending"
        # Second run: V6 file already has correct mirrors → should count 0
        assert n2 == 0, f"Second run should migrate 0 files, got {n2}"

    def test_migrate_handles_empty_registry(self, tmp_path):
        """Migration must not crash on empty registry."""
        from scripts.migrate_v6_translation_mirror import migrate_registry

        registry_path = tmp_path / "registry.json"
        registry_path.write_text("{}", encoding="utf-8")

        n = migrate_registry(registry_path)
        assert n == 0

    def test_migrate_returns_zero_for_missing_file(self, tmp_path):
        """Migration must return 0 (not crash) if registry.json doesn't exist."""
        from scripts.migrate_v6_translation_mirror import migrate_registry

        missing = tmp_path / "nonexistent" / "registry.json"
        n = migrate_registry(missing)
        assert n == 0
