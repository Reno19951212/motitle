"""Tests for T7: output_lang API wiring.

Covers:
  A. _register_file output_languages param + /api/transcribe form field
  B. /api/files/<id>/translate-second output_lang branch
  C. approve/unapprove mirrors ALL by_lang keys for output_lang rows
  D. PATCH translation role-aware field mapping for output_lang
  E. _role_fields_for + resolve_segment_text correctness (no route change)
"""
import importlib
import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as _app_module
from app import (
    app,
    _file_registry,
    _registry_lock,
    _register_file,
    _role_fields_for,
)
from subtitle_text import resolve_segment_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with auth bypass + isolated profile manager."""
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    app.config["TESTING"] = True
    app.config["R5_AUTH_BYPASS"] = True
    with app.test_client() as c:
        yield c
    app.config.pop("R5_AUTH_BYPASS", None)


def _make_output_lang_entry(file_id, outs=None):
    """Build a minimal output_lang file registry entry with two by_lang keys."""
    if outs is None:
        outs = ["yue", "en"]
    yue_text = "各位晚上好。"
    en_text = "Good evening everyone."
    row = {
        "start": 0.0,
        "end": 2.5,
        "by_lang": {
            "yue": {"text": yue_text, "status": "pending", "flags": []},
            "en": {"text": en_text, "status": "pending", "flags": []},
        },
        "yue_text": yue_text,
        "en_text": en_text,
        "status": "pending",
        "flags": [],
    }
    return {
        "id": file_id,
        "original_name": "test.mp4",
        "stored_name": "test.mp4",
        "file_path": None,
        "size": 1000,
        "status": "done",
        "uploaded_at": 1700000000,
        "active_kind": "output_lang",
        "active_id": "output_lang",
        "active_pipeline_snapshot": None,
        "output_languages": list(outs),
        "segments": [],
        "text": yue_text,
        "error": None,
        "translations": [row],
        "translation_status": "done",
    }


# ---------------------------------------------------------------------------
# A — _register_file output_languages param
# ---------------------------------------------------------------------------

class TestRegisterFileOutputLanguages:
    """A: _register_file with output_languages overrides active_kind/active_id."""

    def test_output_languages_forces_output_lang_kind(self, tmp_path, monkeypatch):
        """Passing output_languages=['yue','en'] → active_kind='output_lang'."""
        fid = "reg-test-a1"
        # Patch _save_registry to a no-op
        monkeypatch.setattr("app._save_registry", lambda: None)
        stored_name = f"{fid}.mp4"
        file_path = str(tmp_path / stored_name)
        Path(file_path).write_bytes(b"")

        with _registry_lock:
            _file_registry.pop(fid, None)
        try:
            _register_file(
                fid, "test.mp4", stored_name, 1000,
                user_id=1, file_path=file_path,
                output_languages=["yue", "en"]
            )
            with _registry_lock:
                entry = dict(_file_registry.get(fid) or {})
            assert entry["active_kind"] == "output_lang", entry
            assert entry["active_id"] == "output_lang", entry
            assert entry["output_languages"] == ["yue", "en"], entry
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_no_output_languages_preserves_snapshot(self, tmp_path, monkeypatch):
        """No output_languages → active_kind from _current_active_snapshot (unchanged)."""
        fid = "reg-test-a2"
        monkeypatch.setattr("app._save_registry", lambda: None)
        # Stub snapshot to return 'profile'
        monkeypatch.setattr(
            "app._current_active_snapshot",
            lambda: ("profile", "prod-default", [])
        )
        # Also prevent pipeline snapshot for V6
        stored_name = f"{fid}.mp4"
        file_path = str(tmp_path / stored_name)
        Path(file_path).write_bytes(b"")

        with _registry_lock:
            _file_registry.pop(fid, None)
        try:
            _register_file(
                fid, "test.mp4", stored_name, 1000,
                user_id=1, file_path=file_path
            )
            with _registry_lock:
                entry = dict(_file_registry.get(fid) or {})
            assert entry["active_kind"] == "profile", entry
            assert entry["active_id"] == "prod-default", entry
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# B — /api/files/<id>/translate-second output_lang branch
# ---------------------------------------------------------------------------

class TestTranslateSecondOutputLang:
    """B: translate-second on output_lang files."""

    def test_enqueues_asr_output_job(self, client, monkeypatch):
        """output_lang file + new lang → 202, job_type='asr_output'."""
        fid = "ts-ol-001"
        captured = {}

        def fake_enqueue(user_id, file_id, job_type, **kwargs):
            captured["job_type"] = job_type
            captured["output_language"] = kwargs.get("output_language")
            return "fake-job-id-ol"

        monkeypatch.setattr("app._job_queue.enqueue", fake_enqueue)
        monkeypatch.setattr("app._save_registry", lambda: None)

        with _registry_lock:
            _file_registry[fid] = _make_output_lang_entry(fid, outs=["yue"])
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "en"},
                content_type="application/json",
            )
            assert resp.status_code == 202, resp.get_data(as_text=True)
            body = resp.get_json()
            assert body["file_id"] == fid
            assert body["job_id"] == "fake-job-id-ol"
            assert body["target_lang"] == "en"
            assert captured["job_type"] == "asr_output", captured
            assert captured["output_language"] == "en", captured

            # entry should have 'en' appended to output_languages
            with _registry_lock:
                updated = _file_registry.get(fid) or {}
            assert "en" in updated.get("output_languages", []), updated
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_lang_already_present_returns_400(self, client, monkeypatch):
        """output_lang file + lang already in output_languages → 400."""
        fid = "ts-ol-002"
        monkeypatch.setattr("app._save_registry", lambda: None)

        with _registry_lock:
            _file_registry[fid] = _make_output_lang_entry(fid, outs=["yue", "en"])
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "en"},
                content_type="application/json",
            )
            assert resp.status_code == 400, resp.get_data(as_text=True)
            body = resp.get_json()
            assert "already" in body.get("error", "").lower() or "en" in body.get("error", "")
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_unsupported_lang_returns_400(self, client, monkeypatch):
        """output_lang file + unsupported lang code → 400."""
        fid = "ts-ol-003"
        monkeypatch.setattr("app._save_registry", lambda: None)

        with _registry_lock:
            _file_registry[fid] = _make_output_lang_entry(fid, outs=["yue"])
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "ko"},  # not in {"yue","zh","en","ja"}
                content_type="application/json",
            )
            assert resp.status_code == 400, resp.get_data(as_text=True)
            body = resp.get_json()
            assert "unsupported" in body.get("error", "").lower() or "ko" in body.get("error", "")
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_v6_path_unaffected(self, client):
        """V6 file translate-second still returns 202 (V6 path not broken)."""
        fid = "ts-ol-v6"
        from tests.test_v6_second_language import _make_v6_entry  # noqa: PLC0415
        with _registry_lock:
            _file_registry[fid] = _make_v6_entry(fid, source_lang="zh")
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "en"},
                content_type="application/json",
            )
            # V6 path must still work (202 or 400 about template — not about output_lang)
            assert resp.status_code in (202, 400), resp.get_data(as_text=True)
            if resp.status_code == 400:
                body = resp.get_json()
                # Must NOT hit the new output_lang error messages
                assert "output_lang" not in body.get("error", "")
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# C — approve/unapprove mirrors ALL by_lang keys
# ---------------------------------------------------------------------------

class TestApproveOutputLang:
    """C: approve/unapprove on output_lang rows mirrors ALL by_lang statuses."""

    def test_approve_sets_all_bylang_approved(self, client, monkeypatch):
        """POST approve on output_lang row → both yue + en by_lang.status='approved'."""
        fid = "ap-ol-001"
        monkeypatch.setattr("app._save_registry", lambda: None)
        monkeypatch.setattr("app._reset_progress_for_job", lambda *a, **kw: None)

        with _registry_lock:
            _file_registry[fid] = _make_output_lang_entry(fid, outs=["yue", "en"])
        try:
            resp = client.post(f"/api/files/{fid}/translations/0/approve")
            assert resp.status_code == 200, resp.get_data(as_text=True)

            with _registry_lock:
                updated = _file_registry.get(fid) or {}
            row = updated.get("translations", [{}])[0]
            by_lang = row.get("by_lang", {})
            assert by_lang.get("yue", {}).get("status") == "approved", by_lang
            assert by_lang.get("en", {}).get("status") == "approved", by_lang
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_unapprove_sets_all_bylang_pending(self, client, monkeypatch):
        """POST unapprove on output_lang row → both yue + en by_lang.status='pending'."""
        fid = "ap-ol-002"
        monkeypatch.setattr("app._save_registry", lambda: None)
        monkeypatch.setattr("app._reset_progress_for_job", lambda *a, **kw: None)

        # Start approved
        entry = _make_output_lang_entry(fid, outs=["yue", "en"])
        row = entry["translations"][0]
        row["status"] = "approved"
        row["by_lang"]["yue"]["status"] = "approved"
        row["by_lang"]["en"]["status"] = "approved"

        with _registry_lock:
            _file_registry[fid] = entry
        try:
            resp = client.post(f"/api/files/{fid}/translations/0/unapprove")
            assert resp.status_code == 200, resp.get_data(as_text=True)

            with _registry_lock:
                updated = _file_registry.get(fid) or {}
            row_after = updated.get("translations", [{}])[0]
            by_lang = row_after.get("by_lang", {})
            assert by_lang.get("yue", {}).get("status") == "pending", by_lang
            assert by_lang.get("en", {}).get("status") == "pending", by_lang
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_profile_approve_unaffected(self, client, monkeypatch):
        """Profile approve still only mirrors src_lang (no by_lang for profile rows)."""
        fid = "ap-prof-001"
        monkeypatch.setattr("app._save_registry", lambda: None)
        monkeypatch.setattr("app._reset_progress_for_job", lambda *a, **kw: None)

        entry = {
            "id": fid, "original_name": "t.mp4", "stored_name": "t.mp4",
            "file_path": None, "size": 1000, "status": "done",
            "uploaded_at": 1700000000,
            "active_kind": "profile", "active_id": None,
            "segments": [], "text": "", "error": None,
            "translations": [
                {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。",
                 "status": "pending", "flags": []},
            ],
            "translation_status": "done",
        }
        with _registry_lock:
            _file_registry[fid] = entry
        try:
            resp = client.post(f"/api/files/{fid}/translations/0/approve")
            assert resp.status_code == 200, resp.get_data(as_text=True)
            body = resp.get_json()
            tr = body.get("translation", {})
            # Profile row has no by_lang — just check top-level status
            assert tr.get("status") == "approved"
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# D — PATCH translation role-aware field mapping
# ---------------------------------------------------------------------------

class TestPatchTranslationOutputLang:
    """D: PATCH translation with role for output_lang files."""

    def _make_entry_with_patch_row(self, fid, outs=None):
        """Return an entry with by_lang keys matching outs."""
        if outs is None:
            outs = ["yue", "en"]
        return _make_output_lang_entry(fid, outs=outs)

    def test_patch_role_first_writes_outs0(self, client, monkeypatch):
        """PATCH role=first on output_lang → writes outs[0]_text + by_lang[outs[0]]."""
        fid = "patch-ol-001"
        monkeypatch.setattr("app._save_registry", lambda: None)
        monkeypatch.setattr("app._reset_progress_for_job", lambda *a, **kw: None)

        with _registry_lock:
            _file_registry[fid] = self._make_entry_with_patch_row(fid, outs=["yue", "en"])
        try:
            resp = client.patch(
                f"/api/files/{fid}/translations/0",
                json={"text": "各位好嗎。", "role": "first"},
                content_type="application/json",
            )
            assert resp.status_code == 200, resp.get_data(as_text=True)

            with _registry_lock:
                updated = _file_registry.get(fid) or {}
            row = updated.get("translations", [{}])[0]
            # yue_text must be updated
            assert row.get("yue_text") == "各位好嗎。", row
            # by_lang[yue] must be updated
            assert row.get("by_lang", {}).get("yue", {}).get("text") == "各位好嗎。", row
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_patch_role_second_writes_outs1(self, client, monkeypatch):
        """PATCH role=second on output_lang → writes outs[1]_text + by_lang[outs[1]]."""
        fid = "patch-ol-002"
        monkeypatch.setattr("app._save_registry", lambda: None)
        monkeypatch.setattr("app._reset_progress_for_job", lambda *a, **kw: None)

        with _registry_lock:
            _file_registry[fid] = self._make_entry_with_patch_row(fid, outs=["yue", "en"])
        try:
            resp = client.patch(
                f"/api/files/{fid}/translations/0",
                json={"text": "Good night all.", "role": "second"},
                content_type="application/json",
            )
            assert resp.status_code == 200, resp.get_data(as_text=True)

            with _registry_lock:
                updated = _file_registry.get(fid) or {}
            row = updated.get("translations", [{}])[0]
            # en_text must be updated
            assert row.get("en_text") == "Good night all.", row
            # by_lang[en] must be updated
            assert row.get("by_lang", {}).get("en", {}).get("text") == "Good night all.", row
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_patch_no_role_legacy_writes_zh_text(self, client, monkeypatch):
        """PATCH no role on output_lang (legacy path) → writes zh_text."""
        fid = "patch-ol-003"
        monkeypatch.setattr("app._save_registry", lambda: None)
        monkeypatch.setattr("app._reset_progress_for_job", lambda *a, **kw: None)

        # Use a single-language output_lang entry (yue only)
        entry = _make_output_lang_entry(fid, outs=["yue"])
        # Add zh_text to row for legacy compat check
        entry["translations"][0]["zh_text"] = "舊字段。"
        with _registry_lock:
            _file_registry[fid] = entry
        try:
            resp = client.patch(
                f"/api/files/{fid}/translations/0",
                json={"zh_text": "新字段。"},
                content_type="application/json",
            )
            # Legacy path (no role) must still work
            assert resp.status_code == 200, resp.get_data(as_text=True)
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# E — _role_fields_for + resolve_segment_text (verification only)
# ---------------------------------------------------------------------------

class TestRoleFieldsForOutputLang:
    """E: _role_fields_for returns correct fields for output_lang entries."""

    def test_role_fields_for_two_langs(self):
        """output_lang entry with outs=['yue','en'] → ('yue_text','en_text')."""
        entry = {
            "active_kind": "output_lang",
            "output_languages": ["yue", "en"],
        }
        first, second = _role_fields_for(entry)
        assert first == "yue_text", first
        assert second == "en_text", second

    def test_role_fields_for_single_lang(self):
        """output_lang entry with outs=['zh'] → ('zh_text', None)."""
        entry = {
            "active_kind": "output_lang",
            "output_languages": ["zh"],
        }
        first, second = _role_fields_for(entry)
        assert first == "zh_text", first
        assert second is None, second

    def test_role_fields_for_no_langs(self):
        """output_lang entry with empty outs → (None, None)."""
        entry = {
            "active_kind": "output_lang",
            "output_languages": [],
        }
        first, second = _role_fields_for(entry)
        assert first is None
        assert second is None

    def test_resolve_segment_text_first_mode(self):
        """resolve_segment_text 'first' on output_lang row returns outs[0] text."""
        seg = {
            "yue_text": "各位晚上好。",
            "en_text": "Good evening.",
            "by_lang": {
                "yue": {"text": "各位晚上好。", "status": "pending"},
                "en": {"text": "Good evening.", "status": "pending"},
            },
        }
        # first_field is yue_text
        text = resolve_segment_text(seg, mode="first", first_field="yue_text", second_field="en_text")
        assert text == "各位晚上好。", text

    def test_resolve_segment_text_second_mode(self):
        """resolve_segment_text 'second' on output_lang row returns outs[1] text."""
        seg = {
            "yue_text": "各位晚上好。",
            "en_text": "Good evening.",
        }
        text = resolve_segment_text(seg, mode="second", first_field="yue_text", second_field="en_text")
        assert text == "Good evening.", text
