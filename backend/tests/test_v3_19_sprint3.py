"""v3.19 Sprint 3 — regression tests for bugs A-3, B-7, B-8, B-9, B-10.

Each test was introduced with the bug fix and must stay GREEN forever.
"""
from __future__ import annotations

import threading
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# A-3: OpenRouter empty api_key surfaced as translation_status skipped
# ---------------------------------------------------------------------------

def test_a3_openrouter_empty_key_skips_with_status(client, monkeypatch, tmp_path):
    """A-3: _auto_translate with openrouter engine and empty api_key must
    set translation_status='skipped_missing_credentials' and emit
    'translation_skipped' SocketIO event instead of silently returning.
    """
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    # Build a fake profile with openrouter + empty api_key
    class FakeProfileManager:
        def get_active(self):
            return {
                "translation": {
                    "engine": "openrouter",
                    "api_key": "",  # empty — the triggering condition
                    "model": "openai/gpt-4o",
                    "style": "formal",
                },
                "asr": {"language": "en"},
            }

    monkeypatch.setattr(app_mod, "_profile_manager", FakeProfileManager())

    # Register a minimal file with segments so auto-translate has something to run
    fid = f"a3-{uuid.uuid4().hex[:8]}"
    dummy_media = tmp_path / f"{fid}_test.mp4"
    dummy_media.write_bytes(b"DUMMY")
    entry = {
        "id": fid,
        "original_name": "test.mp4",
        "size": 1024,
        "status": "done",
        "uploaded_at": time.time(),
        "user_id": None,
        "active_kind": "profile",
        "active_id": None,
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "Hello world"},
        ],
        "translations": [],
        "translation_status": None,
        "translation_error": None,
        "prompt_overrides": None,
        "error": None,
        "model": None,
        "backend": None,
        "asr_seconds": None,
        "translation_seconds": None,
        "pipeline_seconds": None,
        "file_path": str(dummy_media),
    }
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = entry

    try:
        # Call _auto_translate directly (synchronous in test context)
        app_mod._auto_translate(fid)

        with app_mod._registry_lock:
            e = app_mod._file_registry.get(fid)
        assert e is not None
        assert e["translation_status"] == "skipped_missing_credentials", (
            f"Expected 'skipped_missing_credentials', got {e['translation_status']!r}"
        )
        assert e.get("translation_error"), "translation_error should be populated with a reason"
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# B-9: approved_count in /api/files reflects V6 post-approve state
# ---------------------------------------------------------------------------

def test_b9_approved_count_v6_correct(client, v6_file_with_translations):
    """B-9: /api/files approved_count must reflect approved translations for V6
    files. After approve-all, approved_count should equal the total row count.
    """
    fid = v6_file_with_translations

    # Approve all translations
    r = client.post(f"/api/files/{fid}/translations/approve-all")
    assert r.status_code == 200
    body = r.get_json()
    total_approved = body["approved_count"]
    assert total_approved > 0, "Fixture should have pending translations"

    # /api/files must reflect the count
    r = client.get("/api/files")
    assert r.status_code == 200
    files_by_id = {f["id"]: f for f in r.get_json()["files"]}
    assert fid in files_by_id, "V6 file should appear in /api/files"
    actual = files_by_id[fid]["approved_count"]
    assert actual == total_approved, (
        f"approved_count in /api/files should be {total_approved}, got {actual}"
    )


# ---------------------------------------------------------------------------
# B-7: render source=en for zh-source V6 file → 400 or warning
# ---------------------------------------------------------------------------

def test_b7_render_source_en_for_zh_v6_rejected(client, v6_zh_source_file):
    """B-7: POST /api/render with subtitle_source=en for a V6 file whose
    source_lang is 'zh' must either:
      (a) return 400 with error mentioning 'source', or
      (b) accept but include warning_missing_en or warning_source_mismatch.
    Either way it must NOT silently burn Qwen3-packed nonsense.
    """
    fid = v6_zh_source_file
    r = client.post(
        "/api/render",
        json={"file_id": fid, "format": "mp4", "subtitle_source": "en"},
    )
    # Option A: reject
    if r.status_code == 400:
        assert "source" in r.get_json().get("error", "").lower(), (
            f"400 error message should mention 'source', got {r.get_json()}"
        )
        return
    # Option B: accept but warn
    assert r.status_code in (200, 202), f"Unexpected status {r.status_code}"
    body = r.get_json()
    assert "warning_missing_en" in body or "warning_source_mismatch" in body, (
        f"V6 zh-source rendered as source=en should emit warning, got {body}"
    )


# ---------------------------------------------------------------------------
# B-8: Qwen3 subprocess respects cancel_event via Popen + polling
# ---------------------------------------------------------------------------

def test_b8_qwen3_cancel_terminates_subprocess(monkeypatch):
    """B-8: Qwen3VadEngine._call_subprocess honours cancel_event by
    terminating the subprocess via Popen polling. Cancel must complete
    within 10 seconds (not wait for the full 1800s timeout).
    """
    import subprocess as _subprocess

    try:
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
    except ImportError:
        pytest.skip("qwen3_vad_engine not available")

    # Mock Popen to simulate a long-running subprocess that never exits.
    class FakeProc:
        def __init__(self):
            self.returncode = None
            self.stdin = type("FakeStdin", (), {
                "write": lambda s, d: None,
                "close": lambda s: None,
            })()
            self._terminated = threading.Event()

        def poll(self):
            # Never exits naturally
            return None

        def terminate(self):
            self.returncode = -15
            self._terminated.set()

        def kill(self):
            self.returncode = -9
            self._terminated.set()

        def wait(self, timeout=None):
            self._terminated.wait(timeout=timeout)

        @property
        def stdout(self):
            class _FakeStdout:
                def read(self_inner):
                    return b'{}'
            return _FakeStdout()

        @property
        def stderr(self):
            class _FakeStderr:
                def read(self_inner):
                    return b''
            return _FakeStderr()

    fake_proc = FakeProc()
    monkeypatch.setattr(_subprocess, "Popen", lambda *a, **kw: fake_proc)
    # Also mock _load_audio_ffmpeg and related helpers
    import numpy as np
    monkeypatch.setattr(
        "engines.transcribe.qwen3_vad_engine._load_audio_ffmpeg",
        lambda *a, **kw: np.zeros(16000, dtype=np.float32),
    )
    import tempfile as _tempfile
    monkeypatch.setattr(_tempfile, "mkdtemp", lambda **kw: "/tmp/fake_vad")

    engine = Qwen3VadEngine()

    cancel_event = threading.Event()

    # Fire cancel after 0.5 s
    def _fire():
        time.sleep(0.5)
        cancel_event.set()
    threading.Thread(target=_fire, daemon=True).start()

    start = time.time()
    from jobqueue.queue import JobCancelled
    with pytest.raises((JobCancelled, Exception)):
        engine.transcribe_regions(
            audio_path="/tmp/fake.wav",
            vad_regions=[{"start": 0.0, "end": 1.0, "idx": 0}],
            cancel_event=cancel_event,
        )
    elapsed = time.time() - start
    assert elapsed < 10, f"Cancel should terminate within 10s, took {elapsed:.1f}s"
    # Verify the mock proc was actually terminated
    assert fake_proc._terminated.is_set(), "FakeProc.terminate() should have been called"


# ---------------------------------------------------------------------------
# B-10: pipeline snapshot at upload time (race condition guard)
# ---------------------------------------------------------------------------

def test_b10_pipeline_snapshot_stored_at_upload(client, monkeypatch, tmp_path):
    """B-10: When a V6 file is uploaded, the active pipeline JSON must be
    snapshot into the file registry entry as 'active_pipeline_snapshot' so
    that a subsequent PATCH of the pipeline does not affect in-flight jobs.
    """
    try:
        import app as app_mod
    except ImportError:
        pytest.skip("app module not available")

    pipeline_id = f"test-pipe-{uuid.uuid4().hex[:6]}"
    original_pipeline = {
        "id": pipeline_id,
        "name": "Test Pipeline",
        "qwen3_asr": {"context": "ORIGINAL-CONTEXT"},
    }

    class FakePipelineManager:
        def get(self, pid):
            return original_pipeline if pid == pipeline_id else None
        def get_active(self):
            return original_pipeline
        def list_visible(self, *a, **kw):
            return [original_pipeline]
        def can_view(self, *a, **kw):
            return True

    monkeypatch.setattr(app_mod, "_pipeline_manager", FakePipelineManager())

    # Inject a dummy file entry directly (simulating what upload + register would do)
    fid = f"b10-{uuid.uuid4().hex[:8]}"
    dummy_media = tmp_path / f"{fid}.mp4"
    dummy_media.write_bytes(b"DUMMY")

    entry = {
        "id": fid,
        "original_name": "test.mp4",
        "size": 1024,
        "status": "uploaded",
        "uploaded_at": time.time(),
        "user_id": None,
        "active_kind": "pipeline_v6",
        "active_id": pipeline_id,
        "segments": [],
        "translations": [],
        "translation_status": None,
        "prompt_overrides": None,
        "error": None,
        "model": None,
        "backend": None,
        "asr_seconds": None,
        "translation_seconds": None,
        "pipeline_seconds": None,
        "file_path": str(dummy_media),
    }

    # Simulate the upload: use _register_file which should snapshot the pipeline
    # OR manually inject + check the snapshot is stored
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = entry
        # Simulate the snapshot being written at upload time
        app_mod._snapshot_pipeline_at_upload(fid)

    try:
        with app_mod._registry_lock:
            e = app_mod._file_registry.get(fid)
        snapshot = e.get("active_pipeline_snapshot")
        assert snapshot is not None, "Pipeline snapshot should be stored at upload time"
        assert snapshot.get("qwen3_asr", {}).get("context") == "ORIGINAL-CONTEXT", (
            f"Snapshot should capture original context, got {snapshot}"
        )
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)
