"""Tests for pipeline preset_slot field (Q3)."""
import pytest


@pytest.mark.parametrize("slot", [None, 1, 2, 3, 4])
def test_v4_pipeline_accepts_valid_preset_slot(slot):
    from pipelines import validate_pipeline
    pipeline = {
        "name": "test",
        "asr_profile_id": "asr-1",
        "mt_stages": [],
        "preset_slot": slot,
    }
    errors = validate_pipeline(pipeline)
    assert "preset_slot" not in str(errors), f"slot={slot} should be valid: {errors}"


@pytest.mark.parametrize("bad", [0, 5, -1, "1", 1.5, True])
def test_v4_pipeline_rejects_invalid_preset_slot(bad):
    from pipelines import validate_pipeline
    pipeline = {
        "name": "test",
        "asr_profile_id": "asr-1",
        "mt_stages": [],
        "preset_slot": bad,
    }
    errors = validate_pipeline(pipeline)
    assert any("preset_slot" in e for e in errors), f"slot={bad!r} should be rejected"


@pytest.mark.parametrize("slot", [None, 1, 2, 3, 4])
def test_v5_pipeline_accepts_valid_preset_slot(slot):
    from pipeline_schema_v5 import validate_v5_pipeline
    pipeline = {
        "version": 5,
        "name": "test",
        "source_lang": "en",
        "target_languages": ["en"],
        "asr_primary": {"transcribe_profile_id": "t-1"},
        "preset_slot": slot,
    }
    errors, _warnings = validate_v5_pipeline(pipeline)
    assert not any("preset_slot" in e for e in errors), f"slot={slot}: {errors}"


@pytest.mark.parametrize("bad", [0, 5, "1", 1.5, True])
def test_v5_pipeline_rejects_invalid_preset_slot(bad):
    from pipeline_schema_v5 import validate_v5_pipeline
    pipeline = {
        "version": 5,
        "name": "test",
        "source_lang": "en",
        "target_languages": ["en"],
        "asr_primary": {"transcribe_profile_id": "t-1"},
        "preset_slot": bad,
    }
    errors, _ = validate_v5_pipeline(pipeline)
    assert any("preset_slot" in e for e in errors)
