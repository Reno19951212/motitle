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


# ---------------------------------------------------------------------------
# Task 12: qwen3_context 3-level resolution tests
# ---------------------------------------------------------------------------

class TestRunV6ContextResolution:
    """Verify qwen3 context 3-level resolution in _run_v6."""

    def _run_and_capture_context(self, file_context=None, pipeline_context=None):
        pipeline = _make_v6_pipeline()
        if pipeline_context is not None:
            pipeline["qwen3_asr"]["context"] = pipeline_context

        captured = {}

        def fake_run_stage(stage, segments_in, stage_index, stage_type, **kwargs):
            return (
                {"stage_index": stage_index, "stage_type": stage_type,
                 "stage_ref": "fake", "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "test"}],
            )

        def fake_run_stage_v5(stage, segments_in, stage_index, stage_type,
                              cancel_event, user_id, extra_overrides):
            if stage_type == "qwen3_per_region":
                # Capture the context from the stage's engine config
                captured["context"] = getattr(stage._engine, "_context", None)
            return (
                {"stage_index": stage_index, "stage_type": stage_type,
                 "stage_ref": "fake", "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "test"}],
            )

        file_entry = {"prompt_overrides": {}}
        if file_context is not None:
            file_entry["prompt_overrides"]["qwen3_context"] = file_context

        runner = PipelineRunner(
            pipeline=pipeline, file_id="test-file-v6",
            audio_path="/fake/audio.mp4", managers=_fake_managers(),
        )
        with patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._file_registry", {"test-file-v6": file_entry}), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        return captured.get("context", "")

    def test_file_context_overrides_pipeline_context(self):
        """File-level qwen3_context wins over pipeline default."""
        ctx = self._run_and_capture_context(
            file_context="file entity names",
            pipeline_context="pipeline entity names",
        )
        assert ctx == "file entity names"

    def test_pipeline_context_used_when_no_file_override(self):
        """Pipeline-level context used when no file override."""
        ctx = self._run_and_capture_context(
            file_context=None,
            pipeline_context="pipeline entity names",
        )
        assert ctx == "pipeline entity names"

    def test_empty_string_when_neither_set(self):
        """Empty string returned when neither file override nor pipeline default set."""
        ctx = self._run_and_capture_context(file_context=None, pipeline_context=None)
        assert ctx == ""


class TestPromptOverrideValidatorQwen3Context:
    def test_qwen3_context_is_accepted_key(self):
        """prompt_override_validator accepts qwen3_context as a known key."""
        from translation.prompt_override_validator import validate_prompt_overrides
        errors = validate_prompt_overrides(
            {"qwen3_context": "袁幸堯 史滕雷"}, field_path="prompt_overrides"
        )
        assert errors == [], f"Expected no errors but got: {errors}"

    def test_qwen3_context_too_long_is_rejected(self):
        """qwen3_context > 2000 chars is rejected."""
        from translation.prompt_override_validator import validate_prompt_overrides
        long_val = "a" * 2001
        errors = validate_prompt_overrides(
            {"qwen3_context": long_val}, field_path="prompt_overrides"
        )
        assert len(errors) > 0, "Expected an error for qwen3_context > 2000 chars"
        assert any("2000" in e or "qwen3_context" in e for e in errors)


# ---------------------------------------------------------------------------
# Task 11: refiner_prompt_override — PipelineManager + _run_v6 resolution
# ---------------------------------------------------------------------------

class TestRunV6RefinerPromptResolution:
    """Verify 3-level refiner prompt resolution in _run_v6."""

    def _run_with_overrides(self, file_prompt=None, pipeline_prompt=None):
        """Helper: build runner with specified override levels, capture resolved prompt."""
        pipeline = _make_v6_pipeline()
        if pipeline_prompt is not None:
            pipeline["refiner_prompt_override"] = {"zh": pipeline_prompt}

        captured = {}

        def fake_run_stage_v5(stage, segments_in, stage_index, stage_type,
                              cancel_event=None, user_id=None, extra_overrides=None):
            if "refiner" in (stage_type or ""):
                captured["runtime_overrides"] = extra_overrides or {}
            return (
                {"stage_index": stage_index, "stage_type": stage_type, "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "test"}],
            )

        def fake_run_stage(stage, segments_in, stage_index, stage_type, **kwargs):
            return (
                {"stage_index": stage_index, "stage_type": stage_type, "status": "done",
                 "ran_at": 0, "duration_seconds": 0, "segments": [], "quality_flags": []},
                [{"start": 0.0, "end": 1.0, "text": "test"}],
            )

        file_entry = {"prompt_overrides": {}}
        if file_prompt is not None:
            file_entry["prompt_overrides"]["refiners.zh"] = file_prompt

        runner = PipelineRunner(
            pipeline=pipeline, file_id="test-file-v6",
            audio_path="/fake/audio.mp4", managers=_fake_managers(),
        )
        with patch.object(runner, "_run_stage_v5", side_effect=fake_run_stage_v5), \
             patch.object(runner, "_run_stage", side_effect=fake_run_stage), \
             patch.object(runner, "_persist_by_lang"), \
             patch("pipeline_runner._file_registry", {"test-file-v6": file_entry}), \
             patch("pipeline_runner._persist_stage_output"), \
             patch("pipeline_runner._socketio_emit"):
            runner._run_v6(user_id=1)

        return captured.get("runtime_overrides", {})

    def test_file_prompt_overrides_pipeline_and_template(self):
        overrides = self._run_with_overrides(
            file_prompt="per-file custom prompt",
            pipeline_prompt="pipeline custom prompt",
        )
        assert overrides.get("refiners.zh") == "per-file custom prompt"

    def test_pipeline_prompt_overrides_template_when_no_file_override(self):
        overrides = self._run_with_overrides(
            file_prompt=None,
            pipeline_prompt="pipeline custom prompt",
        )
        assert overrides.get("refiners.zh") == "pipeline custom prompt"

    def test_empty_override_falls_through_to_template(self):
        overrides = self._run_with_overrides(file_prompt=None, pipeline_prompt=None)
        # When no override set, runtime_overrides for refiner.zh should be empty/absent
        assert not overrides.get("refiners.zh")


class TestPipelineManagerRefinerPromptOverride:
    def test_update_if_owned_accepts_refiner_prompt_override(self):
        """PipelineManager.update_if_owned accepts refiner_prompt_override patch field."""
        from pipelines import PipelineManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PipelineManager(config_dir=tmpdir)
            pipeline = _make_v6_pipeline()
            pipeline["user_id"] = 1
            pipeline["shared"] = False
            mgr._save(pipeline)
            # Inject into cache manually (bypasses validation)
            mgr._cache[pipeline["id"]] = pipeline

            mgr.update_if_owned(
                pipeline_id=pipeline["id"],
                user_id=1,
                is_admin=False,
                patch={"refiner_prompt_override": {"zh": "custom prompt text"}},
            )
            updated = mgr.get(pipeline["id"])
            assert updated["refiner_prompt_override"]["zh"] == "custom prompt text"

    def test_update_if_owned_clears_refiner_prompt_override_with_null(self):
        from pipelines import PipelineManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PipelineManager(config_dir=tmpdir)
            pipeline = _make_v6_pipeline()
            pipeline["user_id"] = 1
            pipeline["shared"] = False
            pipeline["refiner_prompt_override"] = {"zh": "old prompt"}
            mgr._save(pipeline)
            # Inject into cache manually
            mgr._cache[pipeline["id"]] = pipeline

            mgr.update_if_owned(
                pipeline_id=pipeline["id"],
                user_id=1, is_admin=False,
                patch={"refiner_prompt_override": {"zh": None}},
            )
            updated = mgr.get(pipeline["id"])
            assert not updated.get("refiner_prompt_override", {}).get("zh")
