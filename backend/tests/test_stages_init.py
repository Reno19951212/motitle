"""Tests for PipelineStage ABC, StageContext, StageOutput — v4.0 A1."""
import pytest
from stages import PipelineStage, StageContext, StageOutput


def test_pipeline_stage_is_abstract():
    """PipelineStage cannot be instantiated directly."""
    with pytest.raises(TypeError):
        PipelineStage()


def test_stage_context_required_fields():
    """StageContext holds all required fields."""
    ctx = StageContext(
        file_id="abc",
        user_id=1,
        pipeline_id="p1",
        stage_index=0,
        cancel_event=None,
        progress_callback=None,
        pipeline_overrides={}
    )
    assert ctx.file_id == "abc"
    assert ctx.user_id == 1
    assert ctx.pipeline_id == "p1"
    assert ctx.stage_index == 0
    assert ctx.cancel_event is None
    assert ctx.progress_callback is None
    assert ctx.pipeline_overrides == {}


def test_stage_context_default_overrides():
    """StageContext.pipeline_overrides defaults to empty dict."""
    ctx = StageContext(
        file_id="abc",
        user_id=1,
        pipeline_id="p1",
        stage_index=0,
        cancel_event=None,
        progress_callback=None
    )
    assert ctx.pipeline_overrides == {}


def test_stage_output_typed_dict_shape():
    """StageOutput has all required keys."""
    out: StageOutput = {
        "stage_index": 0,
        "stage_type": "asr",
        "stage_ref": "asr-uuid",
        "status": "done",
        "ran_at": 1234567890.0,
        "duration_seconds": 5.0,
        "segments": [],
        "quality_flags": [],
    }
    assert out["stage_index"] == 0
    assert out["stage_type"] == "asr"
    assert out["stage_ref"] == "asr-uuid"
    assert out["status"] == "done"
    assert out["ran_at"] == 1234567890.0
    assert out["duration_seconds"] == 5.0
    assert out["segments"] == []
    assert out["quality_flags"] == []
