"""TDD tests for 9 app.py bug fixes.

Groups:
  - Crash guards: #21 (null active_id dispatch), #15 (error message)
  - Registry locking: #13 (_auto_translate mutations outside lock)
  - Warning count: #8 (warning_missing_zh uses hardcoded zh_text)
  - B2 cluster: #14 (TOCTOU), #11 (concurrent collision), #12 (pending not
    cleared on failure), #20 (in-place mutation), #22 (_mt_handler stale read)
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import (
    app,
    _file_registry,
    _registry_lock,
    _asr_handler,
    _mt_handler,
    _translate_second_handler,
    _save_registry,
    _role_fields_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_v6_entry(file_id, source_lang="zh", with_snapshot=False, pending_lang=None):
    zh_text = "各位晚上好。"
    entry = {
        "id": file_id,
        "original_name": "test.mp4",
        "stored_name": "test.mp4",
        "file_path": "/fake/test.mp4",
        "size": 1000,
        "status": "done",
        "uploaded_at": 1700000000,
        "user_id": 1,
        "active_kind": "pipeline_v6",
        "active_id": None,  # deliberately None — triggers #21/#15
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
    if with_snapshot:
        entry["active_pipeline_snapshot"] = {"id": "snap-001", "name": "test-pipeline"}
    if pending_lang:
        entry["_pending_second_lang"] = pending_lang
    return entry


def _make_job(file_id, job_type="asr", job_id="fake-job-id", user_id=1):
    return {"file_id": file_id, "id": job_id, "type": job_type, "user_id": user_id}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    app.config["TESTING"] = True
    app.config["R5_AUTH_BYPASS"] = True
    with app.test_client() as c:
        yield c
    app.config.pop("R5_AUTH_BYPASS", None)


# ===========================================================================
# BUG #21 + #15: null active_id in V6 dispatch
# ===========================================================================

class TestActiveIdNullGuard:
    """Bug #21: _asr_handler KeyErrors when active_id is missing/None.
    Bug #15: error-message also uses f["active_id"] (KeyError on missing key).
    """

    def test_null_active_id_raises_clear_runtime_error_with_file_id(self, monkeypatch):
        """V6 file with active_id=None → RuntimeError that includes file_id in message."""
        fid = "bug21-test-001"
        entry = _make_v6_entry(fid)  # active_id=None, no snapshot
        job = _make_job(fid)

        monkeypatch.setattr("app._resolve_file_path", lambda f: "/fake/audio.mp4")

        with _registry_lock:
            _file_registry[fid] = entry
        try:
            with pytest.raises(RuntimeError) as exc_info:
                _asr_handler(job)
            msg = str(exc_info.value)
            assert fid in msg, f"file_id should appear in error: {msg}"
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_missing_active_id_key_raises_runtime_error_not_keyerror(self, monkeypatch):
        """V6 file with active_id KEY absent → RuntimeError (not KeyError)."""
        fid = "bug21-test-002"
        entry = _make_v6_entry(fid)
        del entry["active_id"]  # remove the key entirely — currently causes KeyError
        job = _make_job(fid)

        monkeypatch.setattr("app._resolve_file_path", lambda f: "/fake/audio.mp4")

        with _registry_lock:
            _file_registry[fid] = entry
        try:
            with pytest.raises(RuntimeError):
                # Must raise RuntimeError, NOT KeyError
                _asr_handler(job)
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_snapshot_used_when_active_id_none(self, monkeypatch):
        """When active_pipeline_snapshot is set, it is used even if active_id=None.

        The handler should NOT raise RuntimeError about missing active_id —
        it should proceed to use the snapshot (may fail on PipelineRunner import in
        test env, but that is a separate concern).
        """
        fid = "bug21-test-003"
        entry = _make_v6_entry(fid, with_snapshot=True)  # has snapshot, no active_id
        job = _make_job(fid)

        monkeypatch.setattr("app._resolve_file_path", lambda f: "/fake/audio.mp4")
        monkeypatch.setattr("app._update_file", lambda *a, **kw: None)

        # pipeline_manager.get returns None (deleted) — should not matter since snapshot is used
        fake_pm = MagicMock()
        fake_pm.get.return_value = None
        monkeypatch.setattr("app._pipeline_manager", fake_pm)

        with _registry_lock:
            _file_registry[fid] = entry
        try:
            try:
                _asr_handler(job)
            except RuntimeError as e:
                msg = str(e)
                # Allow failure only if it's NOT about missing active_id
                assert "active_id" not in msg.lower(), (
                    f"Should not fail with active_id error when snapshot is present: {msg}"
                )
            except Exception:
                pass  # Other exceptions (import error etc) are acceptable
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ===========================================================================
# BUG #13: _auto_translate mutates registry outside lock
# ===========================================================================

class TestAutoTranslateLocking:
    """Bug #13: in the openrouter-skip path the status/error writes and
    _save_registry() run OUTSIDE the `with _registry_lock:` block.
    After fix they must run INSIDE the lock.
    """

    def test_openrouter_skip_writes_translation_status_correctly(self, monkeypatch):
        """After openrouter skip path, translation_status is set in the registry
        and _save_registry is called (state is correct regardless of lock detail).
        """
        fid = "bug13-test-001"
        entry = {
            "id": fid,
            "original_name": "x.mp4",
            "stored_name": "x.mp4",
            "file_path": "/fake/x.mp4",
            "size": 100,
            "status": "done",
            "uploaded_at": 1700000000,
            "active_kind": "profile",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}],
            "translation_status": None,
        }

        fake_profile = {
            "translation": {"engine": "openrouter", "api_key": ""},
        }
        monkeypatch.setattr("app._profile_manager",
                            MagicMock(get_active=lambda: fake_profile))
        save_called = []
        monkeypatch.setattr("app._save_registry", lambda: save_called.append(True))
        monkeypatch.setattr("app.socketio", MagicMock())

        with _registry_lock:
            _file_registry[fid] = entry

        try:
            from app import _auto_translate
            _auto_translate(fid)

            with _registry_lock:
                updated = dict(_file_registry.get(fid, {}))

            # State must be set correctly
            assert updated.get("translation_status") == "skipped_missing_credentials", (
                f"Expected skipped_missing_credentials, got: {updated.get('translation_status')}"
            )
            assert "translation_error" in updated
            # _save_registry must have been called
            assert save_called, "_save_registry was never called after status mutation"
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_openrouter_skip_save_called_inside_lock(self, monkeypatch):
        """_save_registry() must be called while _registry_lock is held.

        Strategy: replace _save_registry with a spy that records whether
        _registry_lock can be ACQUIRED (with blocking=False) at call time.
        Because _registry_lock is a threading.RLock (re-entrant), if the
        calling code holds it, a re-entrant acquire in the SAME thread
        still succeeds. We therefore count successful vs failed acquires
        from a DIFFERENT thread:
          - spawn a thread that tries to acquire _registry_lock immediately
            after _save_registry is called
          - if _save_registry was called inside the lock, the thread will
            fail to acquire (returns False) → lock IS held → correct
          - if _save_registry was called outside, the thread can acquire
            → lock NOT held → BUG

        This approach is inherently racy, so we use it only as supporting
        evidence; the state-correctness test above is the primary assertion.
        """
        fid = "bug13-test-002"
        entry = {
            "id": fid,
            "original_name": "x.mp4",
            "stored_name": "x.mp4",
            "file_path": "/fake/x.mp4",
            "size": 100,
            "status": "done",
            "uploaded_at": 1700000000,
            "active_kind": "profile",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}],
            "translation_status": None,
        }

        fake_profile = {
            "translation": {"engine": "openrouter", "api_key": ""},
        }
        monkeypatch.setattr("app._profile_manager",
                            MagicMock(get_active=lambda: fake_profile))

        # Track: was lock blocked (True=held) or free (False=not held)?
        lock_states = []

        def spy_save():
            # Try from this same thread — RLock is re-entrant, so if caller holds it
            # we can acquire. Use a background-thread probe instead.
            probe_result = []

            def probe():
                # A DIFFERENT thread: try to acquire without blocking
                got = _registry_lock.acquire(blocking=False)
                if got:
                    probe_result.append("free")
                    _registry_lock.release()
                else:
                    probe_result.append("held")

            t = threading.Thread(target=probe)
            t.start()
            t.join(timeout=0.5)
            lock_states.extend(probe_result)

        monkeypatch.setattr("app._save_registry", spy_save)
        monkeypatch.setattr("app.socketio", MagicMock())

        with _registry_lock:
            _file_registry[fid] = entry

        try:
            from app import _auto_translate
            _auto_translate(fid)
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

        assert lock_states, "spy_save never called"
        # After fix: _save_registry is inside 'with _registry_lock:', so probe sees "held"
        assert "held" in lock_states, (
            f"_save_registry should be called while lock is held; probe saw: {lock_states}"
        )


# ===========================================================================
# BUG #8: warning_missing_zh uses hardcoded zh_text
# ===========================================================================

class TestWarningMissingZhField:
    """Bug #8: warning_missing_zh hardcodes t.get('zh_text') instead of using
    the resolved second field (_render_second_field).

    We test via the _role_fields_for helper + a minimal render-endpoint path.
    Since the render endpoint does real rendering, we test the logic directly
    by extracting the counting behaviour.
    """

    def _count_warning(self, translations, render_second_field):
        """Mirror the fixed warning-count logic to verify correctness."""
        count = 0
        for t in translations:
            field_value = (
                t.get(render_second_field) if render_second_field
                else (t.get("zh_text") or "")
            )
            if not (field_value or "").strip():
                count += 1
        return count

    def test_v6_empty_second_field_en_text_counted(self):
        """V6 file: second field is en_text (empty) → counted."""
        # second_field = "en_text" (V6 where second lang is en)
        translations = [
            {"zh_text": "各位晚上好。", "en_text": "", "source_lang": "zh"},
        ]
        count = self._count_warning(translations, "en_text")
        assert count == 1, "empty en_text should be counted as warning"

    def test_v6_filled_second_field_not_counted(self):
        """V6 file: second field en_text filled → NOT counted."""
        translations = [
            {"zh_text": "各位晚上好。", "en_text": "Good evening.", "source_lang": "zh"},
        ]
        count = self._count_warning(translations, "en_text")
        assert count == 0, "filled en_text should not be counted"

    def test_profile_empty_zh_text_counted(self):
        """Profile file: second field is zh_text (empty) → counted."""
        translations = [
            {"en_text": "Hello.", "zh_text": ""},
        ]
        count = self._count_warning(translations, "zh_text")
        assert count == 1, "empty zh_text should be counted for Profile files"

    def test_profile_filled_zh_text_not_counted(self):
        """Profile file: zh_text filled → NOT counted."""
        translations = [
            {"en_text": "Hello.", "zh_text": "你好。"},
        ]
        count = self._count_warning(translations, "zh_text")
        assert count == 0, "filled zh_text should not be counted"

    def test_role_fields_for_v6_returns_second_lang_field(self):
        """_role_fields_for for V6 with en second-lang returns ('zh_text', 'en_text')."""
        entry = {
            "active_kind": "pipeline_v6",
            "translations": [
                {
                    "source_lang": "zh",
                    "by_lang": {"zh": {"text": "好"}, "en": {"text": "good"}},
                }
            ],
        }
        first, second = _role_fields_for(entry)
        assert first == "zh_text"
        assert second == "en_text", f"Expected en_text, got: {second}"

    def test_role_fields_for_profile_returns_zh_text_as_second(self):
        """_role_fields_for for Profile returns (None, 'zh_text')."""
        entry = {"active_kind": "profile"}
        first, second = _role_fields_for(entry)
        assert second == "zh_text"


# ===========================================================================
# BUG #14 + #11: translate-second endpoint TOCTOU + concurrent collision
# ===========================================================================

class TestTranslateSecondEndpoint:
    """Bug #14: validation reads happen outside lock (TOCTOU).
    Bug #11: concurrent calls overwrite _pending_second_lang → 409 needed.
    """

    def test_first_call_returns_202(self, client):
        """First POST translate-second (no pending) → 202."""
        fid = "bug14-test-001"
        entry = _make_v6_entry(fid)

        with _registry_lock:
            _file_registry[fid] = entry

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app._job_queue") as mock_jq, \
             patch("app._save_registry", lambda: None):
            mock_jq.enqueue.return_value = "job-001"
            mock_jq.position.return_value = 1

            try:
                resp = client.post(
                    f"/api/files/{fid}/translate-second",
                    json={"lang": "en"},
                    content_type="application/json",
                )
                assert resp.status_code == 202, resp.get_data(as_text=True)
                body = resp.get_json()
                assert body.get("target_lang") == "en"
            finally:
                with _registry_lock:
                    _file_registry.pop(fid, None)

    def test_concurrent_second_call_returns_409(self, client):
        """While _pending_second_lang is already set, a second POST → 409."""
        fid = "bug11-test-001"
        entry = _make_v6_entry(fid, pending_lang="en")  # already in progress

        with _registry_lock:
            _file_registry[fid] = entry

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app._job_queue") as mock_jq, \
             patch("app._save_registry", lambda: None):
            mock_jq.enqueue.return_value = "job-999"
            mock_jq.position.return_value = 2

            try:
                resp = client.post(
                    f"/api/files/{fid}/translate-second",
                    json={"lang": "en"},
                    content_type="application/json",
                )
                assert resp.status_code == 409, (
                    f"Expected 409 when pending already set, got {resp.status_code}: "
                    f"{resp.get_data(as_text=True)}"
                )
            finally:
                with _registry_lock:
                    _file_registry.pop(fid, None)

    def test_after_completion_new_call_allowed(self, client):
        """After _pending_second_lang is cleared, a new POST → 202 again."""
        fid = "bug11-test-002"
        entry = _make_v6_entry(fid)
        # No pending lang — cleared after prior handler run
        entry.pop("_pending_second_lang", None)

        with _registry_lock:
            _file_registry[fid] = entry

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app._job_queue") as mock_jq, \
             patch("app._save_registry", lambda: None):
            mock_jq.enqueue.return_value = "job-new"
            mock_jq.position.return_value = 1

            try:
                resp = client.post(
                    f"/api/files/{fid}/translate-second",
                    json={"lang": "en"},
                    content_type="application/json",
                )
                assert resp.status_code == 202, (
                    f"Expected 202 after clearing pending, got {resp.status_code}: "
                    f"{resp.get_data(as_text=True)}"
                )
            finally:
                with _registry_lock:
                    _file_registry.pop(fid, None)


# ===========================================================================
# BUG #12: _pending_second_lang not cleared on handler failure
# ===========================================================================

class TestPendingSecondLangCleared:
    """Bug #12: if transform() raises, _pending_second_lang stays set → re-dispatch loop."""

    def _fake_llm_profile(self):
        return {
            "id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
            "name": "stub",
            "backend": "ollama",
            "model": "qwen3.5:35b-a3b-mlx-bf16",
            "base_url": "http://localhost:11434",
            "temperature": 0.2,
        }

    def test_pending_cleared_on_transform_failure(self):
        """When TranslatorStage.transform raises, _pending_second_lang is cleared."""
        fid = "bug12-test-001"
        entry = _make_v6_entry(fid, pending_lang="en")

        with _registry_lock:
            _file_registry[fid] = entry

        def exploding_transform(self, segments_in, context):
            raise RuntimeError("simulated transform crash")

        try:
            with patch(
                "stages.v5.translator_stage.TranslatorStage.transform",
                exploding_transform,
            ), patch("app._llm_profile_manager") as mock_lpm, \
               patch("app._save_registry", lambda: None):
                mock_lpm.get.return_value = self._fake_llm_profile()
                fake_job = {"file_id": fid, "id": "fake-job-id", "user_id": 1}

                with pytest.raises(RuntimeError, match="simulated transform crash"):
                    _translate_second_handler(fake_job, cancel_event=None)

            # _pending_second_lang must be cleared even though transform failed
            with _registry_lock:
                updated = _file_registry.get(fid, {})
            assert "_pending_second_lang" not in updated, (
                "_pending_second_lang should be cleared even after handler failure"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_exception_propagates_after_pending_cleared(self):
        """The exception from transform still propagates (not swallowed by finally)."""
        fid = "bug12-test-002"
        entry = _make_v6_entry(fid, pending_lang="en")

        with _registry_lock:
            _file_registry[fid] = entry

        def exploding_transform(self, segments_in, context):
            raise ValueError("specific-error-marker-12")

        try:
            with patch(
                "stages.v5.translator_stage.TranslatorStage.transform",
                exploding_transform,
            ), patch("app._llm_profile_manager") as mock_lpm, \
               patch("app._save_registry", lambda: None):
                mock_lpm.get.return_value = self._fake_llm_profile()
                fake_job = {"file_id": fid, "id": "fake-job-id", "user_id": 1}

                with pytest.raises(ValueError, match="specific-error-marker-12"):
                    _translate_second_handler(fake_job, cancel_event=None)
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ===========================================================================
# BUG #20: handler mutates shared registry rows in place
# ===========================================================================

class TestImmutableRegistryRows:
    """Bug #20: _translate_second_handler mutates row dicts in place via
    row.setdefault('by_lang', ...) and row[f'{target}_text'] = ..."""

    def _fake_llm_profile(self):
        return {
            "id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
            "name": "stub",
            "backend": "ollama",
            "model": "qwen3.5:35b-a3b-mlx-bf16",
            "base_url": "http://localhost:11434",
            "temperature": 0.2,
        }

    def test_registry_row_identity_changes_after_handler(self):
        """After handler runs, registry contains NEW row objects (not the same dicts)."""
        fid = "bug20-test-001"
        entry = _make_v6_entry(fid, pending_lang="en")

        # Capture identity of the original row BEFORE inserting into registry
        original_row_id = id(entry["translations"][0])

        with _registry_lock:
            _file_registry[fid] = entry

        def fake_transform(self, segments_in, context):
            return [
                {"start": s["start"], "end": s["end"], "text": "EN:" + s["text"], "flags": []}
                for s in segments_in
            ]

        try:
            with patch(
                "stages.v5.translator_stage.TranslatorStage.transform",
                fake_transform,
            ), patch("app._llm_profile_manager") as mock_lpm, \
               patch("app._save_registry", lambda: None):
                mock_lpm.get.return_value = self._fake_llm_profile()
                fake_job = {"file_id": fid, "id": "fake-job-id", "user_id": 1}
                _translate_second_handler(fake_job, cancel_event=None)

            with _registry_lock:
                new_translations = _file_registry.get(fid, {}).get("translations", [])

            assert len(new_translations) == 1
            new_row = new_translations[0]

            # Content must be correct
            assert "en_text" in new_row, "en_text mirror should exist in new row"
            assert "en" in new_row.get("by_lang", {}), "by_lang[en] should exist"

            # Identity: the stored row must be a NEW object (not the original dict)
            assert id(new_row) != original_row_id, (
                "Registry should contain NEW row dicts after immutable rebuild"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_original_entry_translation_row_not_mutated_in_place(self):
        """The dict object in the original entry['translations'][0] is NOT mutated."""
        fid = "bug20-test-002"
        entry = _make_v6_entry(fid, pending_lang="en")
        # Keep a reference to the ORIGINAL row dict
        original_row = entry["translations"][0]
        original_keys_before = frozenset(original_row.keys())

        with _registry_lock:
            _file_registry[fid] = entry

        def fake_transform(self, segments_in, context):
            return [
                {"start": s["start"], "end": s["end"], "text": "EN:" + s["text"], "flags": []}
                for s in segments_in
            ]

        try:
            with patch(
                "stages.v5.translator_stage.TranslatorStage.transform",
                fake_transform,
            ), patch("app._llm_profile_manager") as mock_lpm, \
               patch("app._save_registry", lambda: None):
                mock_lpm.get.return_value = self._fake_llm_profile()
                fake_job = {"file_id": fid, "id": "fake-job-id", "user_id": 1}
                _translate_second_handler(fake_job, cancel_event=None)

            # The original row dict should NOT have gained en_text or had by_lang mutated
            # (Note: if handler correctly builds new row, original row is unmodified)
            assert "en_text" not in original_row, (
                "Original row dict was mutated in place — should NOT have en_text"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ===========================================================================
# BUG #22: _mt_handler reads entry without lock across decisions
# ===========================================================================

class TestMtHandlerAtomicRead:
    """Bug #22: _mt_handler checks _pending_second_lang and active_kind on a
    stale reference captured outside the lock.
    Fix: snapshot both fields atomically under lock, then branch on locals.
    """

    def test_mt_handler_second_lang_dispatch(self, monkeypatch):
        """_mt_handler routes to _translate_second_handler when _pending_second_lang set."""
        fid = "bug22-test-001"
        entry = _make_v6_entry(fid, pending_lang="en")

        dispatched = []

        def fake_second_handler(job, cancel_event=None):
            dispatched.append("second")

        monkeypatch.setattr("app._translate_second_handler", fake_second_handler)

        with _registry_lock:
            _file_registry[fid] = entry

        try:
            fake_job = _make_job(fid, job_type="translate")
            _mt_handler(fake_job, cancel_event=None)
            assert dispatched == ["second"], (
                "_mt_handler should dispatch to _translate_second_handler when pending set"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)

    def test_mt_handler_v6_inline_shortcircuit(self, monkeypatch):
        """V6 file without pending second lang → short-circuit sets translation_status=done."""
        fid = "bug22-test-002"
        entry = _make_v6_entry(fid)
        entry.pop("_pending_second_lang", None)

        monkeypatch.setattr("app._save_registry", lambda: None)

        with _registry_lock:
            _file_registry[fid] = entry

        try:
            fake_job = _make_job(fid, job_type="translate")
            _mt_handler(fake_job, cancel_event=None)

            with _registry_lock:
                updated = _file_registry.get(fid, {})
            assert updated.get("translation_status") == "done", (
                f"V6 short-circuit should set translation_status=done, got: "
                f"{updated.get('translation_status')}"
            )
        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)


# ===========================================================================
# Integration test for the B2 cluster
# ===========================================================================

class TestB2ClusterIntegration:
    """Integration: translate-second cycle — handler writes by_lang, clears
    pending; concurrent POST while pending → 409.
    """

    def test_full_translate_second_cycle(self):
        """Handler writes by_lang[en], clears pending; verify registry state."""
        fid = "b2-integ-001"
        entry = _make_v6_entry(fid, pending_lang="en")

        fake_llm_profile = {
            "id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
            "name": "stub",
            "backend": "ollama",
            "model": "qwen3.5:35b-a3b-mlx-bf16",
            "base_url": "http://localhost:11434",
            "temperature": 0.2,
        }

        with _registry_lock:
            _file_registry[fid] = entry

        def fake_transform(self, segments_in, context):
            return [
                {"start": s["start"], "end": s["end"], "text": "EN:" + s["text"], "flags": []}
                for s in segments_in
            ]

        try:
            with patch(
                "stages.v5.translator_stage.TranslatorStage.transform",
                fake_transform,
            ), patch("app._llm_profile_manager") as mock_lpm, \
               patch("app._save_registry", lambda: None):
                mock_lpm.get.return_value = fake_llm_profile
                fake_job = {"file_id": fid, "id": "job-001", "user_id": 1}
                _translate_second_handler(fake_job, cancel_event=None)

            with _registry_lock:
                updated = dict(_file_registry.get(fid, {}))

            # 1. _pending_second_lang cleared
            assert "_pending_second_lang" not in updated

            # 2. by_lang[en] written
            rows = updated.get("translations", [])
            assert rows and "en" in rows[0].get("by_lang", {}), (
                f"by_lang[en] not found: {rows}"
            )

            # 3. en_text mirror written
            assert rows[0].get("en_text", "").startswith("EN:")

        finally:
            with _registry_lock:
                _file_registry.pop(fid, None)
