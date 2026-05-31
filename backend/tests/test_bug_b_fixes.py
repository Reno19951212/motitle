"""TDD tests for Bug B fixes (B-1, B-2, B-3).

B-1: resolve_language_descriptor fresh V6 file uses pipeline config source_lang,
     and exposes second_lang_preselect as second role.
B-2: POST /api/files/<id>/translate-second handles unprocessed V6 files:
     - stores preselection instead of enqueueing when no refiner output yet
     - validates template + source_lang from pipeline snapshot
     - existing processed path unchanged
B-3: _asr_handler auto-triggers second-lang translate job after V6 completion
     when second_lang_preselect is set.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from subtitle_text import resolve_language_descriptor
from app import (
    app,
    _file_registry,
    _registry_lock,
    _asr_handler,
    _save_registry,
)


# ===========================================================================
# B-1: resolve_language_descriptor — fresh V6 file uses active_cfg source_lang
# ===========================================================================

class TestB1LanguageDescriptorFreshV6:
    """B-1: fresh V6 file (translations=[]) should show pipeline's source_lang."""

    def test_fresh_v6_uses_active_cfg_source_lang(self):
        """Fresh V6 file with translations=[] and active_cfg.source_lang='en'
        should return first.lang='en', not default 'zh'."""
        entry = {
            "id": "b1-test-001",
            "active_kind": "pipeline_v6",
            "translations": [],
        }
        active_cfg = {"source_lang": "en"}
        desc = resolve_language_descriptor(entry, active_cfg)
        first = next((d for d in desc if d["role"] == "first"), None)
        assert first is not None, "descriptor must have a 'first' role"
        assert first["lang"] == "en", (
            f"fresh V6 with active_cfg.source_lang='en' should show 'en', got '{first['lang']}'"
        )

    def test_fresh_v6_no_active_cfg_still_defaults_zh(self):
        """Fresh V6 file with no translations AND no active_cfg → default 'zh' (unchanged)."""
        entry = {
            "id": "b1-test-002",
            "active_kind": "pipeline_v6",
            "translations": [],
        }
        desc = resolve_language_descriptor(entry, None)
        first = next((d for d in desc if d["role"] == "first"), None)
        assert first is not None
        assert first["lang"] == "zh"

    def test_fresh_v6_with_preselect_surfaces_second_role(self):
        """Fresh V6 file with second_lang_preselect='en' → descriptor has second role lang='en'."""
        entry = {
            "id": "b1-test-003",
            "active_kind": "pipeline_v6",
            "translations": [],
            "second_lang_preselect": "en",
        }
        active_cfg = {"source_lang": "zh"}
        desc = resolve_language_descriptor(entry, active_cfg)
        second = next((d for d in desc if d["role"] == "second"), None)
        assert second is not None, (
            "descriptor must expose second_lang_preselect as a 'second' role"
        )
        assert second["lang"] == "en"

    def test_processed_v6_preselect_ignored_when_by_lang_exists(self):
        """Processed V6 file with by_lang already set: preselect should NOT override
        the real by_lang second lang (existing behavior preserved)."""
        entry = {
            "id": "b1-test-004",
            "active_kind": "pipeline_v6",
            "translations": [
                {
                    "source_lang": "zh",
                    "by_lang": {
                        "zh": {"text": "各位晚上好。", "status": "approved"},
                        "en": {"text": "Good evening everyone.", "status": "pending"},
                    },
                }
            ],
            "second_lang_preselect": "fr",  # preselect that conflicts with real by_lang
        }
        desc = resolve_language_descriptor(entry, None)
        second = next((d for d in desc if d["role"] == "second"), None)
        assert second is not None
        # Should use the real by_lang key 'en', not preselect 'fr'
        assert second["lang"] == "en"

    def test_profile_kind_unchanged(self):
        """Profile kind must not be affected by any B-1 changes."""
        entry = {
            "id": "b1-test-005",
            "active_kind": "profile",
            "translations": [],
        }
        active_cfg = {"asr": {"language": "en"}}
        desc = resolve_language_descriptor(entry, active_cfg)
        first = next((d for d in desc if d["role"] == "first"), None)
        second = next((d for d in desc if d["role"] == "second"), None)
        assert first is not None and first["lang"] == "en"
        assert second is not None and second["lang"] == "zh"

    def test_fresh_v6_preselect_same_as_src_not_shown(self):
        """If second_lang_preselect == source_lang, do NOT surface it as second role."""
        entry = {
            "id": "b1-test-006",
            "active_kind": "pipeline_v6",
            "translations": [],
            "second_lang_preselect": "zh",  # same as source_lang
        }
        active_cfg = {"source_lang": "zh"}
        desc = resolve_language_descriptor(entry, active_cfg)
        second = next((d for d in desc if d["role"] == "second"), None)
        assert second is None, (
            "preselect equal to source_lang must NOT be surfaced as second role"
        )


# ===========================================================================
# B-2: POST /api/files/<id>/translate-second on unprocessed V6 file
# ===========================================================================

def _make_unprocessed_v6_entry(file_id, source_lang="zh"):
    """V6 entry with no translations (fresh upload, pipeline not yet run)."""
    return {
        "id": file_id,
        "original_name": "test.mp4",
        "stored_name": "test.mp4",
        "file_path": "/fake/test.mp4",
        "size": 1000,
        "status": "uploaded",
        "uploaded_at": 1700000000,
        "user_id": 1,
        "active_kind": "pipeline_v6",
        "active_id": "pipe-001",
        "active_pipeline_snapshot": {"id": "pipe-001", "source_lang": source_lang},
        "segments": [],
        "text": "",
        "error": None,
        "translations": [],   # no refiner output yet
        "translation_status": None,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    app.config["TESTING"] = True
    app.config["R5_AUTH_BYPASS"] = True
    with app.test_client() as c:
        yield c
    app.config.pop("R5_AUTH_BYPASS", None)


class TestB2TranslateSecondUnprocessed:
    """B-2: translate-second on unprocessed V6 file stores preselection."""

    def test_unprocessed_v6_stores_preselect_and_returns_202(self, client):
        """POST translate-second on unprocessed V6 (no translations) → 202 + preselected:true."""
        fid = "b2-test-001"
        with _registry_lock:
            _file_registry[fid] = _make_unprocessed_v6_entry(fid, source_lang="zh")
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "en"},
                content_type="application/json",
            )
            assert resp.status_code == 202, resp.get_data(as_text=True)
            body = resp.get_json()
            assert body.get("preselected") is True, (
                f"Expected preselected:true for unprocessed file, got: {body}"
            )
            assert body.get("target_lang") == "en"
            assert "job_id" not in body, "No job should be enqueued for unprocessed file"
            # Registry must have second_lang_preselect set
            with _registry_lock:
                entry = _file_registry.get(fid, {})
            assert entry.get("second_lang_preselect") == "en", (
                f"second_lang_preselect not set: {entry}"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_unprocessed_v6_unsupported_direction_returns_400(self, client):
        """Unsupported language direction on unprocessed file → 400."""
        fid = "b2-test-002"
        with _registry_lock:
            _file_registry[fid] = _make_unprocessed_v6_entry(fid, source_lang="zh")
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "ja"},   # no zh_to_ja template
                content_type="application/json",
            )
            assert resp.status_code == 400, resp.get_data(as_text=True)
            body = resp.get_json()
            assert "未支援嘅語言方向" in body.get("error", ""), body
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_unprocessed_v6_unknown_source_lang_returns_400(self, client):
        """Unprocessed V6 with no source_lang in snapshot → 400."""
        fid = "b2-test-003"
        entry = _make_unprocessed_v6_entry(fid, source_lang="zh")
        # Remove source_lang from snapshot so it cannot be determined
        entry["active_pipeline_snapshot"] = {"id": "pipe-001"}  # no source_lang
        entry["active_id"] = None
        with _registry_lock:
            _file_registry[fid] = entry
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "en"},
                content_type="application/json",
            )
            assert resp.status_code == 400, resp.get_data(as_text=True)
            body = resp.get_json()
            assert "source language unknown" in body.get("error", "").lower() or \
                   "source_lang" in body.get("error", ""), body
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_processed_path_unchanged(self, client):
        """Processed V6 file (has translations) → existing 202+job_id behavior unchanged."""
        fid = "b2-test-004"
        zh_text = "各位晚上好。"
        source_lang = "zh"
        processed_entry = {
            "id": fid,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "file_path": "/fake/test.mp4",
            "size": 1000,
            "status": "done",
            "uploaded_at": 1700000000,
            "user_id": 1,
            "active_kind": "pipeline_v6",
            "active_id": None,
            "active_pipeline_snapshot": None,
            "segments": [],
            "text": zh_text,
            "error": None,
            "translations": [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "source_lang": source_lang,
                    "source_text": zh_text,
                    f"{source_lang}_text": zh_text,
                    "by_lang": {
                        source_lang: {"text": zh_text, "status": "approved"},
                    },
                    "status": "approved",
                    "flags": [],
                },
            ],
            "translation_status": "done",
        }
        with _registry_lock:
            _file_registry[fid] = processed_entry
        try:
            resp = client.post(
                f"/api/files/{fid}/translate-second",
                json={"lang": "en"},
                content_type="application/json",
            )
            assert resp.status_code == 202, resp.get_data(as_text=True)
            body = resp.get_json()
            # Processed path returns job_id, NOT preselected
            assert "job_id" in body
            assert body.get("preselected") is not True, (
                f"Processed path should NOT return preselected:true, got: {body}"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ===========================================================================
# B-3: _asr_handler auto-triggers second-lang translate after V6 completion
# ===========================================================================

class TestB3AsrHandlerAutoTrigger:
    """B-3: when V6 completes and second_lang_preselect is set, _asr_handler
    must move it into _pending_second_lang and enqueue a translate job."""

    def test_preselect_triggers_translate_job_after_v6_done(self, monkeypatch):
        """V6 file with second_lang_preselect='en' → after completion,
        _pending_second_lang set, second_lang_preselect cleared, translate job enqueued."""
        fid = "b3-test-001"
        entry = {
            "id": fid,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "file_path": "/fake/test.mp4",
            "size": 1000,
            "status": "uploaded",
            "uploaded_at": 1700000000,
            "user_id": 1,
            "active_kind": "pipeline_v6",
            "active_id": None,
            "active_pipeline_snapshot": {"id": "snap-001", "name": "test-pipeline"},
            "segments": [],
            "text": "",
            "error": None,
            "translations": [],
            "translation_status": None,
            "second_lang_preselect": "en",  # user pre-selected before processing
        }
        job = {"file_id": fid, "id": "fake-job-id", "type": "asr", "user_id": 1}

        monkeypatch.setattr("app._resolve_file_path", lambda f: "/fake/audio.mp4")
        monkeypatch.setattr("app._update_file", lambda *a, **kw: None)

        # PipelineRunner is imported inline inside _asr_handler:
        #   from pipeline_runner import PipelineRunner
        # Use patch() context manager at the source module so the inline import
        # picks up the mock.
        fake_runner = MagicMock()
        fake_runner._run_v6.return_value = None

        # Track enqueue calls
        enqueue_calls = []
        fake_queue = MagicMock()
        fake_queue.enqueue.side_effect = lambda **kwargs: (
            enqueue_calls.append(kwargs) or "fake-translate-job-id"
        )
        monkeypatch.setattr("app._job_queue", fake_queue)

        with _registry_lock:
            _file_registry[fid] = entry
        try:
            with patch("pipeline_runner.PipelineRunner", return_value=fake_runner):
                _asr_handler(job, cancel_event=None)

            with _registry_lock:
                updated = _file_registry.get(fid, {})

            # second_lang_preselect must be cleared
            assert "second_lang_preselect" not in updated, (
                f"second_lang_preselect should be cleared, got: {updated}"
            )
            # _pending_second_lang must be set
            assert updated.get("_pending_second_lang") == "en", (
                f"_pending_second_lang should be 'en', got: {updated}"
            )
            # A translate job must have been enqueued
            assert len(enqueue_calls) >= 1, "Expected at least one enqueue call"
            translate_jobs = [c for c in enqueue_calls if c.get("job_type") == "translate"]
            assert translate_jobs, (
                f"Expected a 'translate' job to be enqueued, got: {enqueue_calls}"
            )
            assert translate_jobs[0]["file_id"] == fid

        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_no_preselect_no_extra_enqueue(self, monkeypatch):
        """V6 file with NO second_lang_preselect → no extra enqueue after completion."""
        fid = "b3-test-002"
        entry = {
            "id": fid,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "file_path": "/fake/test.mp4",
            "size": 1000,
            "status": "uploaded",
            "uploaded_at": 1700000000,
            "user_id": 1,
            "active_kind": "pipeline_v6",
            "active_id": None,
            "active_pipeline_snapshot": {"id": "snap-002", "name": "test-pipeline"},
            "segments": [],
            "text": "",
            "error": None,
            "translations": [],
            "translation_status": None,
            # NO second_lang_preselect
        }
        job = {"file_id": fid, "id": "fake-job-id-2", "type": "asr", "user_id": 1}

        monkeypatch.setattr("app._resolve_file_path", lambda f: "/fake/audio.mp4")
        monkeypatch.setattr("app._update_file", lambda *a, **kw: None)

        fake_runner = MagicMock()
        fake_runner._run_v6.return_value = None

        enqueue_calls = []
        fake_queue = MagicMock()
        fake_queue.enqueue.side_effect = lambda **kwargs: (
            enqueue_calls.append(kwargs) or "fake-translate-job-id-2"
        )
        monkeypatch.setattr("app._job_queue", fake_queue)

        with _registry_lock:
            _file_registry[fid] = entry
        try:
            with patch("pipeline_runner.PipelineRunner", return_value=fake_runner):
                _asr_handler(job, cancel_event=None)

            # No translate job should have been enqueued
            translate_jobs = [c for c in enqueue_calls if c.get("job_type") == "translate"]
            assert not translate_jobs, (
                f"No translate job should be enqueued when no preselect, got: {enqueue_calls}"
            )

        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)
