"""Test that _asr_handler and _mt_handler dispatch correctly based on
file_entry.active_kind. Profile path → existing transcribe_with_segments;
V6 path → PipelineRunner._run_v6. _mt_handler short-circuits for V6
because the V6 refiner stage is inline.

Note: job is a dict (from jobqueue.db._row_to_job), not an object.
Keys: file_id, user_id, type, status, id, created_at, etc.
"""
import threading
from unittest.mock import patch, MagicMock
import pytest
import os


@pytest.fixture(autouse=True)
def _auth_bypass(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")


@pytest.fixture
def app_mod(monkeypatch):
    """Import app module with auth bypass and return it."""
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _app
    return _app


def _make_job(file_id: str, user_id: int = 1) -> dict:
    """Build a minimal job dict matching jobqueue.db._row_to_job shape."""
    return {
        "id": "test-job-id",
        "user_id": user_id,
        "file_id": file_id,
        "type": "asr",
        "status": "running",
        "created_at": 0.0,
        "started_at": 0.0,
        "finished_at": None,
        "error_msg": None,
        "attempt_count": 1,
    }


# ──────────────────────────────────────────────────────────────
# _asr_handler tests
# ──────────────────────────────────────────────────────────────

def test_asr_handler_profile_path_calls_existing_transcribe(app_mod):
    """Profile path should delegate to transcribe_with_segments."""
    fid = "dispatch-asr-001"
    app_mod._file_registry[fid] = {
        "id": fid,
        "active_kind": "profile",
        "active_id": "dev-default",
        "user_id": 1,
        "file_path": "/tmp/fake-dispatch-asr-001.mp4",
    }
    cancel_ev = threading.Event()
    job = _make_job(fid)

    with patch.object(app_mod, "_resolve_file_path", return_value="/tmp/fake-dispatch-asr-001.mp4"), \
         patch.object(app_mod, "transcribe_with_segments") as mock_t:
        mock_t.return_value = {
            "text": "hello",
            "segments": [{"start": 0, "end": 1, "text": "hello"}],
            "model": "large-v3",
            "backend": "mlx-whisper",
        }
        # Suppress the follow-up enqueue so handler completes cleanly
        with patch.object(app_mod._job_queue, "enqueue"):
            app_mod._asr_handler(job, cancel_event=cancel_ev)

    mock_t.assert_called_once()
    # Cleanup
    app_mod._file_registry.pop(fid, None)


def test_asr_handler_v6_path_calls_pipeline_runner(app_mod):
    """V6 path should construct PipelineRunner and call _run_v6."""
    fid = "dispatch-asr-002"
    pipeline_id = "4696bbaa-0000-0000-0000-000000000000"
    app_mod._file_registry[fid] = {
        "id": fid,
        "active_kind": "pipeline_v6",
        "active_id": pipeline_id,
        "user_id": 1,
        "file_path": "/tmp/fake.mp4",
    }
    fake_pipeline = {
        "id": pipeline_id,
        "pipeline_type": "v6_vad_dual_asr",
        "version": 6,
        "source_lang": "zh",
    }
    cancel_ev = threading.Event()
    job = _make_job(fid)

    mock_runner_instance = MagicMock()
    mock_runner_instance._run_v6.return_value = []

    with patch.object(app_mod, "_resolve_file_path", return_value="/tmp/fake-dispatch-asr-002.mp4"), \
         patch.object(app_mod._pipeline_manager, "get", return_value=fake_pipeline), \
         patch("pipeline_runner.PipelineRunner", return_value=mock_runner_instance) as MockRunner:
        app_mod._asr_handler(job, cancel_event=cancel_ev)

    MockRunner.assert_called_once()
    mock_runner_instance._run_v6.assert_called_once()
    # Cleanup
    app_mod._file_registry.pop(fid, None)


def test_asr_handler_v6_pipeline_missing_raises(app_mod):
    """V6 path with missing pipeline should raise RuntimeError."""
    fid = "dispatch-asr-003"
    app_mod._file_registry[fid] = {
        "id": fid,
        "active_kind": "pipeline_v6",
        "active_id": "nonexistent-id",
        "user_id": 1,
        "file_path": "/tmp/fake.mp4",
    }
    cancel_ev = threading.Event()
    job = _make_job(fid)

    with patch.object(app_mod, "_resolve_file_path", return_value="/tmp/fake-dispatch-asr-003.mp4"), \
         patch.object(app_mod._pipeline_manager, "get", return_value=None):
        with pytest.raises(RuntimeError, match="Pipeline"):
            app_mod._asr_handler(job, cancel_event=cancel_ev)

    # Cleanup
    app_mod._file_registry.pop(fid, None)


# ──────────────────────────────────────────────────────────────
# _mt_handler tests
# ──────────────────────────────────────────────────────────────

def test_mt_handler_v6_short_circuits(app_mod):
    """V6 files should short-circuit _mt_handler without calling _auto_translate."""
    fid = "dispatch-mt-004"
    app_mod._file_registry[fid] = {
        "id": fid,
        "active_kind": "pipeline_v6",
        "active_id": "4696bbaa-0000-0000-0000-000000000000",
        "user_id": 1,
    }
    cancel_ev = threading.Event()
    job = _make_job(fid)
    job["type"] = "translate"

    with patch.object(app_mod, "_auto_translate") as mock_at:
        app_mod._mt_handler(job, cancel_event=cancel_ev)

    mock_at.assert_not_called()
    assert app_mod._file_registry[fid].get("translation_status") == "completed"
    # Cleanup
    app_mod._file_registry.pop(fid, None)


def test_mt_handler_profile_path_calls_auto_translate(app_mod):
    """Profile path should call _auto_translate."""
    fid = "dispatch-mt-005"
    app_mod._file_registry[fid] = {
        "id": fid,
        "active_kind": "profile",
        "active_id": "dev-default",
        "user_id": 1,
    }
    cancel_ev = threading.Event()
    job = _make_job(fid)
    job["type"] = "translate"

    with patch.object(app_mod, "_auto_translate") as mock_at:
        app_mod._mt_handler(job, cancel_event=cancel_ev)

    mock_at.assert_called_once()
    # Cleanup
    app_mod._file_registry.pop(fid, None)
