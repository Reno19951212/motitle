"""Tests for v6 stage classes."""
import pytest
from unittest.mock import patch, MagicMock
from stages import StageContext

# ---------------------------------------------------------------------------
# Stage 0 — SileroVadStage
# ---------------------------------------------------------------------------

def _make_context(overrides=None):
    # StageContext dataclass does not have an audio_path field;
    # pass audio_path via pipeline_overrides so transform() can find it.
    _overrides = {"audio_path": "/fake/audio.mp4"}
    if overrides:
        _overrides.update(overrides)
    return StageContext(
        file_id="test_file", user_id=1,
        pipeline_id="test_pipe", stage_index=0,
        cancel_event=None, progress_callback=None,
        pipeline_overrides=_overrides,
    )


class TestSileroVadStage:
    def test_stage_type(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        assert stage.stage_type == "vad"

    def test_stage_ref_uses_profile_id(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"id": "vad-profile-1", "vad_threshold": 0.5})
        assert stage.stage_ref == "vad-profile-1"

    def test_returns_list_of_region_dicts(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        fake_regions = [{"start": 0.5, "end": 3.2}, {"start": 5.1, "end": 8.7}]

        with patch.object(stage, "_run_vad", return_value=fake_regions):
            result = stage.transform([], _make_context())

        assert len(result) == 2
        assert result[0]["start"] == pytest.approx(0.5)
        assert result[1]["end"] == pytest.approx(8.7)

    def test_each_region_has_start_end_float(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        fake = [{"start": "1.0", "end": "2.0"}]  # string input → float output
        with patch.object(stage, "_run_vad", return_value=fake):
            result = stage.transform([], _make_context())
        assert isinstance(result[0]["start"], float)
        assert isinstance(result[0]["end"], float)

    def test_vad_params_passed_to_silero(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        profile = {
            "vad_threshold": 0.6,
            "min_speech_duration_ms": 300,
            "max_speech_duration_s": 10,
            "min_silence_duration_ms": 400,
            "speech_pad_ms": 150,
        }
        stage = SileroVadStage(profile)
        captured = {}
        def fake_run_vad(audio_path):
            # Verify params are accessible on stage
            captured["threshold"] = stage._params["threshold"]
            captured["min_speech_duration_ms"] = stage._params["min_speech_duration_ms"]
            return []
        with patch.object(stage, "_run_vad", side_effect=fake_run_vad):
            stage.transform([], _make_context())
        assert captured["threshold"] == pytest.approx(0.6)
        assert captured["min_speech_duration_ms"] == 300

    def test_empty_audio_returns_empty_list(self):
        from stages.v6.silero_vad_stage import SileroVadStage
        stage = SileroVadStage({"vad_threshold": 0.5})
        with patch.object(stage, "_run_vad", return_value=[]):
            result = stage.transform([], _make_context())
        assert result == []
