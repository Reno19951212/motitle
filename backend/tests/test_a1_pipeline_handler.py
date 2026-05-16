"""Tests for _pipeline_run_handler — JobQueue dispatch to PipelineRunner."""
import pytest
from unittest.mock import MagicMock, patch


def test_pipeline_run_handler_dispatches_to_runner(monkeypatch):
    """_pipeline_run_handler creates PipelineRunner + calls run()."""
    import app as app_mod

    # Stub managers + registry
    monkeypatch.setattr(app_mod, "_pipeline_manager", MagicMock(get=MagicMock(return_value={
        "id": "p1", "asr_profile_id": "asr-1", "mt_stages": [],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": {},
    })))
    monkeypatch.setitem(app_mod._file_registry, "f1",
                        {"id": "f1", "file_path": "/tmp/x.wav"})

    fake_runner_run = MagicMock(return_value=[
        {"stage_index": 0, "stage_type": "asr", "stage_ref": "asr-1",
         "status": "done", "ran_at": 1.0, "duration_seconds": 0.1,
         "segments": [], "quality_flags": []},
    ])

    with patch("app.PipelineRunner") as MockPR:
        MockPR.return_value.run = fake_runner_run
        job = MagicMock(payload={"pipeline_id": "p1", "file_id": "f1"},
                        file_id="f1", user_id=1)
        app_mod._pipeline_run_handler(job, cancel_event=None)
        fake_runner_run.assert_called_once()


def test_pipeline_run_handler_raises_on_missing_pipeline(monkeypatch):
    import app as app_mod
    monkeypatch.setattr(app_mod, "_pipeline_manager", MagicMock(get=MagicMock(return_value=None)))

    job = MagicMock(payload={"pipeline_id": "ghost", "file_id": "f1"},
                    file_id="f1", user_id=1)
    with pytest.raises(ValueError, match="not found"):
        app_mod._pipeline_run_handler(job, cancel_event=None)


def test_pipeline_run_handler_raises_on_missing_file(monkeypatch):
    import app as app_mod
    monkeypatch.setattr(app_mod, "_pipeline_manager", MagicMock(get=MagicMock(return_value={
        "id": "p1", "asr_profile_id": "asr-1", "mt_stages": [],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": {},
    })))
    # Remove f-ghost from registry if it exists
    with app_mod._registry_lock:
        app_mod._file_registry.pop("f-ghost", None)
    job = MagicMock(payload={"pipeline_id": "p1", "file_id": "f-ghost"},
                    file_id="f-ghost", user_id=1)
    with pytest.raises(ValueError, match="not found"):
        app_mod._pipeline_run_handler(job, cancel_event=None)
