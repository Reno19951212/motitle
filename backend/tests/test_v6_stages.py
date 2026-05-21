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


# ---------------------------------------------------------------------------
# Stage 1A — Qwen3VadEngine (T3)
# ---------------------------------------------------------------------------

class TestQwen3VadEngine:
    """Tests for Qwen3VadEngine (Stage 1A engine wrapper)."""

    def test_transcribe_regions_returns_flat_list(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="", post_s2hk=False)
        vad_regions = [{"start": 0.5, "end": 3.0}, {"start": 5.0, "end": 8.5}]

        # Fake subprocess result — two regions, each with word-level segments
        fake_subprocess_result = {
            "regions": [
                {
                    "region_idx": 0, "region_start": 0.5, "region_end": 3.0,
                    "full_text": "你好世界", "chunks": [],
                    "segments": [
                        {"start": 0.1, "end": 0.5, "text": "你好"},
                        {"start": 0.5, "end": 0.9, "text": "世界"},
                    ],
                    "runtime_sec": 0.8, "error": None,
                },
                {
                    "region_idx": 1, "region_start": 5.0, "region_end": 8.5,
                    "full_text": "測試成功", "chunks": [],
                    "segments": [
                        {"start": 0.2, "end": 0.5, "text": "測試"},
                        {"start": 0.5, "end": 0.8, "text": "成功"},
                    ],
                    "runtime_sec": 1.2, "error": None,
                },
            ]
        }
        with patch.object(engine, "_call_subprocess", return_value=fake_subprocess_result):
            result = engine.transcribe_regions("/fake/audio.mp4", vad_regions)

        # Flat list — absolute time adjusted
        assert len(result) == 4
        assert result[0]["text"] == "你好"
        assert result[0]["start"] == pytest.approx(0.5 + 0.1)  # region_start + relative
        assert result[2]["text"] == "測試"
        assert result[2]["start"] == pytest.approx(5.0 + 0.2)  # region 1 offset

    def test_region_with_error_skipped(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="", post_s2hk=False)
        fake = {
            "regions": [
                {
                    "region_idx": 0, "region_start": 0.0, "region_end": 2.0,
                    "full_text": "", "chunks": [], "segments": [],
                    "runtime_sec": 0.5, "error": "mlx_qwen3_asr import failed",
                },
            ]
        }
        with patch.object(engine, "_call_subprocess", return_value=fake):
            result = engine.transcribe_regions("/fake/audio.mp4", [{"start": 0.0, "end": 2.0}])
        assert result == []

    def test_empty_segments_falls_back_to_full_text_as_one_chunk(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="", post_s2hk=False)
        fake = {
            "regions": [
                {
                    "region_idx": 0, "region_start": 1.0, "region_end": 4.0,
                    "full_text": "一段話", "chunks": [], "segments": [],
                    "runtime_sec": 0.3, "error": None,
                },
            ]
        }
        with patch.object(engine, "_call_subprocess", return_value=fake):
            result = engine.transcribe_regions("/fake/audio.mp4", [{"start": 1.0, "end": 4.0}])
        assert len(result) == 1
        assert result[0]["text"] == "一段話"
        assert result[0]["start"] == pytest.approx(1.0)
        assert result[0]["end"] == pytest.approx(4.0)

    def test_subprocess_called_with_correct_payload_shape(self):
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        engine = Qwen3VadEngine(language="Chinese", context="袁幸堯", post_s2hk=True)
        vad_regions = [{"start": 2.0, "end": 5.0}]
        fake = {"regions": [
            {"region_idx": 0, "region_start": 2.0, "region_end": 5.0,
             "full_text": "", "chunks": [], "segments": [], "runtime_sec": 0.1, "error": None}
        ]}
        captured = {}
        def capture_payload(audio_path, wav_paths, payload):
            captured.update(payload)
            return fake
        with patch.object(engine, "_call_subprocess", side_effect=capture_payload):
            engine.transcribe_regions("/fake/audio.mp4", vad_regions)
        assert captured["config"]["language"] == "Chinese"
        assert "袁幸堯" in captured["config"]["context"]
        assert captured["config"]["post_s2hk"] is True


# ---------------------------------------------------------------------------
# Stage 2 — TimeAnchoredMergeStage
# ---------------------------------------------------------------------------

class TestTimeAnchoredMergeStage:
    """Tests for Stage 2: time-anchored merge algorithm."""

    # Pure algorithm tests (no context needed — test via static method)

    def _make_stage(self):
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        return TimeAnchoredMergeStage({})

    def test_single_mlx_slot_absorbs_all_chars(self):
        stage = self._make_stage()
        mlx_segs = [{"start": 0.0, "end": 5.0, "text": "ignored"}]
        qwen3_chars = [
            {"start": 0.5, "end": 1.0, "text": "你"},
            {"start": 1.0, "end": 1.5, "text": "好"},
            {"start": 1.5, "end": 2.0, "text": "世"},
            {"start": 2.0, "end": 2.5, "text": "界"},
        ]
        result = stage._time_anchored_merge(mlx_segs, qwen3_chars)
        assert len(result) == 1
        assert result[0]["text"] == "你好世界"
        assert result[0]["start"] == pytest.approx(0.0)
        assert result[0]["end"] == pytest.approx(5.0)

    def test_chars_assigned_by_midpoint(self):
        """Char with midpoint in [1.0, 2.0) goes to slot [1.0, 2.0)."""
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 1.0, "text": "x"},
            {"start": 1.0, "end": 2.0, "text": "x"},
        ]
        qwen3_chars = [
            {"start": 0.8, "end": 1.2, "text": "字"},  # midpoint=1.0 → slot 1
        ]
        result = stage._time_anchored_merge(mlx_segs, qwen3_chars)
        # midpoint = (0.8+1.2)/2 = 1.0 → slot1 [1.0, 2.0) since 1.0 <= 1.0 < 2.0
        assert result[0]["text"] == ""
        assert result[1]["text"] == "字"

    def test_empty_slot_collapsed_into_prev(self):
        """Empty mlx slots are dropped; prev slot absorbs their end time."""
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 2.0, "text": "x"},
            {"start": 2.0, "end": 4.0, "text": "x"},  # empty — no qwen3 chars
            {"start": 4.0, "end": 6.0, "text": "x"},
        ]
        qwen3_chars = [
            {"start": 0.5, "end": 1.0, "text": "前"},
            {"start": 5.0, "end": 5.5, "text": "後"},
        ]
        result = stage._collapse_empty_slots(
            stage._time_anchored_merge(mlx_segs, qwen3_chars)
        )
        assert len(result) == 2
        assert result[0]["text"] == "前"
        assert result[0]["end"] == pytest.approx(4.0)  # absorbed empty slot's end
        assert result[1]["text"] == "後"

    def test_trailing_empty_slots_absorbed_by_last_keep(self):
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 2.0, "text": "x"},
            {"start": 2.0, "end": 4.0, "text": "x"},  # empty trailing
        ]
        qwen3_chars = [{"start": 0.5, "end": 1.0, "text": "文字"}]
        result = stage._collapse_empty_slots(
            stage._time_anchored_merge(mlx_segs, qwen3_chars)
        )
        assert len(result) == 1
        assert result[0]["end"] == pytest.approx(4.0)

    def test_no_chars_returns_empty(self):
        stage = self._make_stage()
        mlx_segs = [{"start": 0.0, "end": 5.0, "text": "x"}]
        result = stage._collapse_empty_slots(
            stage._time_anchored_merge(mlx_segs, [])
        )
        assert result == []

    def test_multiple_mlx_slots_chars_split_correctly(self):
        stage = self._make_stage()
        mlx_segs = [
            {"start": 0.0, "end": 3.0, "text": "x"},
            {"start": 3.0, "end": 6.0, "text": "x"},
        ]
        qwen3_chars = [
            {"start": 0.5, "end": 1.0, "text": "甲"},  # mid=0.75 → slot 0
            {"start": 2.5, "end": 3.5, "text": "乙"},  # mid=3.0 → slot 1 (3.0 <= 3.0 < 6.0)
            {"start": 4.0, "end": 4.5, "text": "丙"},  # mid=4.25 → slot 1
        ]
        result = stage._time_anchored_merge(mlx_segs, qwen3_chars)
        assert result[0]["text"] == "甲"
        assert result[1]["text"] == "乙丙"

    def test_stage_type(self):
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        stage = TimeAnchoredMergeStage({})
        assert stage.stage_type == "time_anchored_merge"

    def test_transform_reads_qwen3_from_overrides(self):
        """transform() reads qwen3 chars from context.pipeline_overrides['__qwen3_chars']."""
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        stage = TimeAnchoredMergeStage({})
        mlx_segs = [{"start": 0.0, "end": 3.0, "text": "x"}]
        qwen3_chars = [{"start": 0.5, "end": 1.5, "text": "測試"}]
        ctx = _make_context({"__qwen3_chars": qwen3_chars})
        result = stage.transform(mlx_segs, ctx)
        assert len(result) == 1
        assert result[0]["text"] == "測試"


# ---------------------------------------------------------------------------
# Stage 1A — Qwen3PerRegionStage (T4)
# ---------------------------------------------------------------------------

class TestQwen3PerRegionStage:
    def test_stage_type(self):
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        stage = Qwen3PerRegionStage({"id": "qwen3-1", "language": "Chinese"})
        assert stage.stage_type == "qwen3_per_region"

    def test_transform_takes_vad_regions_from_segments_in(self):
        """Stage 1A receives VAD regions as segments_in (from Stage 0)."""
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        stage = Qwen3PerRegionStage({"language": "Chinese", "context": ""})
        vad_regions = [{"start": 0.5, "end": 3.0}, {"start": 5.0, "end": 8.0}]
        expected_chars = [{"start": 0.6, "end": 0.9, "text": "你好"}]

        with patch.object(stage, "_engine") as mock_engine:
            mock_engine.transcribe_regions.return_value = expected_chars
            ctx = _make_context({"audio_path": "/fake/audio.mp4"})
            result = stage.transform(vad_regions, ctx)

        mock_engine.transcribe_regions.assert_called_once_with("/fake/audio.mp4", vad_regions)
        assert result == expected_chars

    def test_transform_returns_normalized_float_dicts(self):
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        stage = Qwen3PerRegionStage({"language": "Chinese"})
        raw_chars = [{"start": "1.0", "end": "1.5", "text": "測試"}]
        with patch.object(stage, "_engine") as mock_engine:
            mock_engine.transcribe_regions.return_value = raw_chars
            ctx = _make_context({"audio_path": "/fake/audio.mp4"})
            result = stage.transform([{"start": 0.5, "end": 2.0}], ctx)
        assert isinstance(result[0]["start"], float)
        assert isinstance(result[0]["end"], float)

    def test_engine_config_from_profile(self):
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine
        profile = {"language": "Chinese", "context": "袁幸堯", "post_s2hk": True}
        stage = Qwen3PerRegionStage(profile)
        assert isinstance(stage._engine, Qwen3VadEngine)
        assert stage._engine._language == "Chinese"
        assert stage._engine._context == "袁幸堯"
        assert stage._engine._post_s2hk is True


# ---------------------------------------------------------------------------
# Task 6 — TestV6RefinerPrompt
# ---------------------------------------------------------------------------

class TestV6RefinerPrompt:
    """Verify v6 refiner prompt does NOT contain cascade/orphan/hallucination drop rules."""

    def _load_prompt(self):
        import json
        from pathlib import Path
        p = (Path(__file__).resolve().parents[1] /
             "config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_prompt_file_exists(self):
        data = self._load_prompt()
        assert data["id"] == "refiner/zh_broadcast_hk_v6"

    def test_prompt_has_no_cascade_rule(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        assert "cascade" not in prompt.lower(), "v6 prompt must not contain cascade detection"

    def test_prompt_has_no_tail_orphan_rule(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        assert "tail_orphan" not in prompt.lower()
        assert "tail orphan" not in prompt.lower()

    def test_prompt_has_no_hallucination_phrase_list(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        # v5 prompt listed known bad phrases; v6 must not
        assert "粟米片" not in prompt
        assert "coffee shop" not in prompt

    def test_prompt_has_no_secondary_field_description(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        assert '"secondary"' not in prompt, "v6 prompt must not describe secondary field"

    def test_prompt_has_drop_only_for_empty_text(self):
        """v6 prompt: drop action only for empty/noise segs, not content judgments."""
        data = self._load_prompt()
        prompt = data["system_prompt"]
        # Must still support keep action
        assert '"action": "keep"' in prompt or "keep" in prompt.lower()

    def test_prompt_mentions_mid_word_cut_fix(self):
        data = self._load_prompt()
        prompt = data["system_prompt"]
        # Must contain mid-word cut fix instruction
        assert "截斷" in prompt or "mid-word" in prompt.lower() or "補全" in prompt
