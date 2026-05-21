"""Integration tests for PipelineRunner._run_v6() DAG dispatch — Task 8."""
import pytest
import threading
from unittest.mock import patch, MagicMock, call

from pipeline_runner import PipelineRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_v6_pipeline():
    return {
        "id": "test-v6-pipe",
        "pipeline_type": "v6_vad_dual_asr",
        "source_lang": "zh",
        "target_languages": ["zh"],
        "vad": {"vad_threshold": 0.5},
        "qwen3_asr": {"language": "Chinese", "context": "", "post_s2hk": True},
        "asr_primary": {
            "transcribe_profile_id": "mlx-profile-1",
            "source_lang": "zh",
        },
        "refinements": {
            "zh": [{"refiner_profile_id": "refiner-1"}]
        },
        "translators": {},
        "glossary_stages": {},
        "font_config": {},
    }


def _fake_managers():
    transcribe_mgr = MagicMock()
    transcribe_mgr.get.return_value = {
        "id": "mlx-profile-1", "engine": "mlx-whisper",
        "language": "zh", "model_size": "large-v3",
    }
    refiner_mgr = MagicMock()
    refiner_mgr.get.return_value = {
        "id": "refiner-1", "lang": "zh", "style": "broadcast_hk_v6",
        "llm_profile_id": "llm-1",
        "prompt_template_id": "refiner/zh_broadcast_hk_v6",
    }
    llm_mgr = MagicMock()
    llm_mgr.get.return_value = {
        "id": "llm-1", "backend": "ollama", "model": "qwen3.5:35b",
    }
    return {
        "transcribe_profile_manager": transcribe_mgr,
        "refiner_profile_manager": refiner_mgr,
        "llm_profile_manager": llm_mgr,
        "asr_manager": MagicMock(),
        "mt_manager": MagicMock(),
        "glossary_manager": MagicMock(),
        "translator_profile_manager": MagicMock(),
        "verifier_profile_manager": MagicMock(),
    }


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------

class TestRunV6Dispatch:
    def test_pipeline_type_v6_dispatches_to_run_v6(self):
        """PipelineRunner.run() with pipeline_type='v6_vad_dual_asr' calls _run_v6."""
        runner = PipelineRunner(
            pipeline=_make_v6_pipeline(),
            file_id="test-file",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )
        with patch.object(runner, "_run_v6", return_value=[]) as mock_v6:
            runner.run(user_id=1)
        mock_v6.assert_called_once()

    def test_no_pipeline_type_does_not_dispatch_to_run_v6(self):
        """Pipeline without pipeline_type field falls through to v4/v5 path."""
        pipe = _make_v6_pipeline()
        del pipe["pipeline_type"]  # Absent → legacy path
        pipe["version"] = 5
        pipe["asr_secondary"] = None
        runner = PipelineRunner(
            pipeline=pipe, file_id="test-file",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )
        with patch.object(runner, "_run_v6") as mock_v6, \
             patch.object(runner, "_run_v5", return_value=[]) as mock_v5:
            runner.run(user_id=1)
        mock_v6.assert_not_called()
        mock_v5.assert_called_once()

    def test_run_v6_start_from_stage_raises_not_implemented(self):
        """v6 pipelines reject start_from_stage > 0 (resume not supported)."""
        runner = PipelineRunner(
            pipeline=_make_v6_pipeline(),
            file_id="test-file",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )
        with pytest.raises(NotImplementedError):
            runner.run(user_id=1, start_from_stage=2)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestRunV6Integration:
    """Integration tests with mocked _run_stage / _run_stage_v5."""

    def _build_runner(self):
        return PipelineRunner(
            pipeline=_make_v6_pipeline(),
            file_id="test-file-v6",
            audio_path="/fake/audio.mp4",
            managers=_fake_managers(),
        )

    def test_run_v6_calls_stages_in_order(self):
        """VAD → qwen3_per_region → asr_primary (mlx) → time_anchored_merge → refiner."""
        runner = self._build_runner()
        stage_types_called = []

        def fake_run_stage(stage, segments_in, stage_index, stage_type, **kwargs):
            stage_types_called.append(stage_type)
            return (
                {
                    "stage_index": stage_index, "stage_type": stage_type,
                    "stage_ref": "fake", "status": "done",
                    "ran_at": 0.0, "duration_seconds": 0.0,
                    "segments": [], "quality_flags": [],
                },
                [{"start": 0.0, "end": 1.0, "text": "測試"}],
            )

        def fake_run_stage_v5(stage, segments_in, stage_index, stage_type,
                              cancel_event, user_id, extra_overrides):
            stage_types_called.append(stage_type)
            return (
                {
                    "stage_index": stage_index, "stage_type": stage_type,
                    "stage_ref": "fake", "status": "done",
                    "ran_at": 0.0, "duration_seconds": 0.0,
                    "segments": [], "quality_flags": [],
                },
                [{"start": 0.0, "end": 1.0, "text": "測試"}],
            )

        with patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        # All expected stage types must appear
        assert "vad" in stage_types_called, f"vad missing from {stage_types_called}"
        assert "qwen3_per_region" in stage_types_called, f"qwen3_per_region missing"
        assert "asr_primary" in stage_types_called, f"asr_primary missing"
        assert "time_anchored_merge" in stage_types_called, f"time_anchored_merge missing"
        assert any("refiner" in t for t in stage_types_called), f"refiner missing"

        # Order: vad < qwen3_per_region < asr_primary < time_anchored_merge
        vad_idx = stage_types_called.index("vad")
        qwen_idx = stage_types_called.index("qwen3_per_region")
        mlx_idx = stage_types_called.index("asr_primary")
        merge_idx = stage_types_called.index("time_anchored_merge")
        assert vad_idx < qwen_idx, "VAD must come before qwen3"
        assert qwen_idx < mlx_idx, "qwen3 must come before mlx"
        assert mlx_idx < merge_idx, "mlx must come before merge"

    def test_run_v6_stashes_qwen3_chars_in_context(self):
        """TimeAnchoredMergeStage must receive __qwen3_chars via extra_overrides.

        VAD, qwen3_per_region, merge, and refiner all go through _run_stage_v5.
        Only the mlx asr_primary stage uses _run_stage (constructor takes audio_path).
        So qwen3_result must come from fake_run_stage_v5 for qwen3_per_region.
        """
        runner = self._build_runner()
        qwen3_result = [{"start": 0.0, "end": 0.5, "text": "測"}]
        merge_extra_overrides_seen = {}

        def fake_run_stage(stage, segments_in, stage_index, stage_type, **kwargs):
            # Only asr_primary (mlx) goes through _run_stage
            return (
                {"stage_index": stage_index, "stage_type": stage_type,
                 "stage_ref": "f", "status": "done", "ran_at": 0, "duration_seconds": 0,
                 "segments": [], "quality_flags": []},
                [],  # mlx segments (used as segments_in for merge)
            )

        def fake_run_stage_v5(stage, segments_in, stage_index, stage_type,
                              cancel_event, user_id, extra_overrides):
            if stage_type == "time_anchored_merge":
                merge_extra_overrides_seen.update(extra_overrides)
            # Return qwen3_result for qwen3_per_region so it propagates to merge
            segs_out = qwen3_result if stage_type == "qwen3_per_region" else []
            return (
                {"stage_index": stage_index, "stage_type": stage_type,
                 "stage_ref": "f", "status": "done", "ran_at": 0, "duration_seconds": 0,
                 "segments": segs_out, "quality_flags": []},
                segs_out,
            )

        with patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        assert "__qwen3_chars" in merge_extra_overrides_seen, (
            "TimeAnchoredMergeStage must receive __qwen3_chars in extra_overrides"
        )
        assert merge_extra_overrides_seen["__qwen3_chars"] == qwen3_result

    def test_run_v6_audio_path_passed_to_vad_and_qwen3(self):
        """SileroVadStage and Qwen3PerRegionStage must receive audio_path."""
        runner = self._build_runner()
        audio_path_seen = {}

        def fake_run_stage(stage, segments_in, stage_index, stage_type, **kwargs):
            # capture audio_path from kwargs (extra_overrides or audio_path kwarg)
            extra = kwargs.get("extra_overrides", {})
            if stage_type in ("vad", "qwen3_per_region", "asr_primary"):
                audio_path_seen[stage_type] = extra.get("audio_path") or kwargs.get("audio_path")
            return (
                {"stage_index": stage_index, "stage_type": stage_type,
                 "stage_ref": "f", "status": "done", "ran_at": 0, "duration_seconds": 0,
                 "segments": [], "quality_flags": []},
                [],
            )

        def fake_run_stage_v5(stage, segments_in, stage_index, stage_type,
                              cancel_event, user_id, extra_overrides):
            if stage_type in ("vad", "qwen3_per_region"):
                audio_path_seen[stage_type] = extra_overrides.get("audio_path")
            return (
                {"stage_index": stage_index, "stage_type": stage_type,
                 "stage_ref": "f", "status": "done", "ran_at": 0, "duration_seconds": 0,
                 "segments": [], "quality_flags": []},
                [],
            )

        with patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        # Stages that need audio_path must have it set somewhere accessible
        for stage_type in ("vad", "qwen3_per_region"):
            assert audio_path_seen.get(stage_type) == "/fake/audio.mp4", (
                f"{stage_type} must receive audio_path='/fake/audio.mp4', "
                f"got {audio_path_seen.get(stage_type)!r}"
            )
