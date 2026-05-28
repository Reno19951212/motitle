"""Tests for v6 pipeline JSON config files.

T9: Verify the v6 pipeline JSON configs for 賽馬 Cantonese broadcast and
Winning Factor English pipelines are well-formed and contain required fields.
"""
import json
import os
import glob
from pathlib import Path

# Config dir relative to this test file
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PIPELINES_DIR = _BACKEND_DIR / "config" / "pipelines"
_REFINER_PROFILES_DIR = _BACKEND_DIR / "config" / "refiner_profiles"


def _find_pipeline_by_name(name_substring: str) -> dict:
    """Find a pipeline JSON whose name contains the given substring."""
    for filepath in _PIPELINES_DIR.glob("*.json"):
        with open(filepath) as f:
            data = json.load(f)
        if name_substring in data.get("name", ""):
            return data
    return {}


def _find_refiner_profile_by_template(template_id: str) -> dict:
    """Find a refiner profile JSON whose prompt_template_id matches."""
    for filepath in _REFINER_PROFILES_DIR.glob("*.json"):
        with open(filepath) as f:
            data = json.load(f)
        if data.get("prompt_template_id") == template_id:
            return data
    return {}


class TestV6ZhPipelineJson:
    """Tests for the [v6] 賽馬廣播 (Cantonese) pipeline JSON."""

    def _load(self) -> dict:
        data = _find_pipeline_by_name("[v6] 賽馬廣播")
        assert data, "No pipeline found with '[v6] 賽馬廣播' in name"
        return data

    def test_v6_zh_pipeline_json_loads(self):
        """File parses and has all required top-level fields."""
        data = self._load()
        required_fields = [
            "id", "name", "pipeline_type", "source_lang", "target_languages",
            "vad", "asr_primary", "qwen3_asr", "refinements",
            "translators", "glossary_stages", "font_config",
            "user_id", "created_at", "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_v6_zh_pipeline_has_pipeline_type(self):
        """pipeline_type must be 'v6_vad_dual_asr' for v6 dispatch."""
        data = self._load()
        assert data["pipeline_type"] == "v6_vad_dual_asr"

    def test_v6_zh_pipeline_vad_params_valid(self):
        """VAD dict must contain all 5 required parameters."""
        data = self._load()
        vad = data["vad"]
        required_vad_fields = [
            "threshold",
            "min_speech_duration_ms",
            "max_speech_duration_s",
            "min_silence_duration_ms",
            "speech_pad_ms",
        ]
        for field in required_vad_fields:
            assert field in vad, f"Missing VAD field: {field}"
        # Sanity check values
        assert 0 < vad["threshold"] < 1
        assert vad["min_speech_duration_ms"] > 0
        assert vad["max_speech_duration_s"] > 0
        assert vad["min_silence_duration_ms"] > 0
        assert vad["speech_pad_ms"] >= 0

    def test_v6_zh_pipeline_qwen3_context_has_entities(self):
        """qwen3_asr.context must contain the racing entity '袁幸堯'."""
        data = self._load()
        qwen3 = data["qwen3_asr"]
        assert "context" in qwen3
        assert "袁幸堯" in qwen3["context"], (
            "qwen3_asr.context should contain '袁幸堯' (racing entity)"
        )

    def test_v6_zh_pipeline_source_lang(self):
        """source_lang must be 'zh' for Cantonese pipeline."""
        data = self._load()
        assert data["source_lang"] == "zh"

    def test_v6_zh_pipeline_target_languages_contains_zh(self):
        """target_languages must include 'zh'."""
        data = self._load()
        assert "zh" in data["target_languages"]

    def test_v6_zh_pipeline_asr_primary_references_mlx_whisper_zh(self):
        """asr_primary.transcribe_profile_id must reference the mlx-whisper ZH profile."""
        data = self._load()
        assert data["asr_primary"]["transcribe_profile_id"] == "82338761-e6ed-47eb-b153-64789ed7327e"

    def test_v6_zh_pipeline_qwen3_language_is_chinese(self):
        """qwen3_asr.language must be 'Chinese' (capital C — Qwen3-ASR format)."""
        data = self._load()
        assert data["qwen3_asr"]["language"] == "Chinese"

    def test_v6_zh_pipeline_qwen3_post_s2hk_true(self):
        """qwen3_asr.post_s2hk must be True for Cantonese pipeline."""
        data = self._load()
        assert data["qwen3_asr"]["post_s2hk"] is True

    def test_v6_zh_pipeline_refinements_zh_has_entry(self):
        """refinements.zh must contain at least one refiner profile entry."""
        data = self._load()
        assert "zh" in data["refinements"]
        assert len(data["refinements"]["zh"]) >= 1
        assert "refiner_profile_id" in data["refinements"]["zh"][0]

    def test_v6_zh_pipeline_translators_empty(self):
        """translators must be {} since source == target (ZH → ZH)."""
        data = self._load()
        assert data["translators"] == {}


class TestV6RefinerProfile:
    """Tests for the v6 ZH refiner profile that points to zh_broadcast_hk_v6 template."""

    def _load(self) -> dict:
        data = _find_refiner_profile_by_template("refiner/zh_broadcast_hk_v6")
        assert data, "No refiner profile found with prompt_template_id='refiner/zh_broadcast_hk_v6'"
        return data

    def test_v6_refiner_profile_points_to_v6_template(self):
        """refiner profile's prompt_template_id must be 'refiner/zh_broadcast_hk_v6'."""
        data = self._load()
        assert data["prompt_template_id"] == "refiner/zh_broadcast_hk_v6"

    def test_v6_refiner_profile_lang_is_zh(self):
        """refiner profile lang must be 'zh'."""
        data = self._load()
        assert data["lang"] == "zh"

    def test_v6_refiner_profile_has_llm_profile_id(self):
        """refiner profile must reference a valid LLM profile."""
        data = self._load()
        assert "llm_profile_id" in data
        assert data["llm_profile_id"]  # non-empty

    def test_v6_refiner_profile_has_required_fields(self):
        """refiner profile must have all required fields."""
        data = self._load()
        for field in ["id", "name", "lang", "llm_profile_id", "prompt_template_id",
                      "user_id", "created_at", "updated_at"]:
            assert field in data, f"Missing field: {field}"


class TestV6EnPipelineJson:
    """Tests for the optional [v6] Winning Factor (English) pipeline JSON."""

    def _load(self) -> dict:
        data = _find_pipeline_by_name("[v6] Winning Factor")
        assert data, "No pipeline found with '[v6] Winning Factor' in name"
        return data

    def test_v6_en_pipeline_json_loads(self):
        """EN pipeline file parses and has required fields."""
        data = self._load()
        for field in ["id", "name", "pipeline_type", "source_lang", "target_languages",
                      "vad", "asr_primary", "qwen3_asr", "refinements",
                      "translators", "glossary_stages", "font_config"]:
            assert field in data, f"Missing field: {field}"

    def test_v6_en_pipeline_has_pipeline_type(self):
        """EN pipeline_type must be 'v6_vad_dual_asr'."""
        data = self._load()
        assert data["pipeline_type"] == "v6_vad_dual_asr"

    def test_v6_en_pipeline_source_lang(self):
        """EN pipeline source_lang must be 'en'."""
        data = self._load()
        assert data["source_lang"] == "en"

    def test_v6_en_pipeline_qwen3_post_s2hk_false(self):
        """EN pipeline qwen3_asr.post_s2hk must be False (no s2hk for English)."""
        data = self._load()
        assert data["qwen3_asr"]["post_s2hk"] is False
