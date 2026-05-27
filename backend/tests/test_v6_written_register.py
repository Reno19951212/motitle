"""Tests for the v6 賽馬廣播 (書面語) chained refiner pipeline configuration.

This is a config-only feature — 3 new JSON files. These tests assert each
file exists at its expected path, parses as valid JSON, and references the
correct upstream identifiers. No real LLM calls.
"""
import json
from pathlib import Path

CONFIG_ROOT = Path(__file__).parent.parent / "config"

# Pre-generated identifiers from the plan (see plan §"Pre-Generated Identifiers")
REFINER_UUID = "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa"
PIPELINE_UUID = "1443afcb-198b-4821-8e64-47d02bf877f3"
EXISTING_CANTONESE_REFINER = "f7f72bd9-3f27-47a4-92bd-5727f336916a"
SHARED_LLM_PROFILE = "9402593c-184d-4a4d-a160-ebdf55e678e8"
SHARED_TRANSCRIBE_PROFILE = "82338761-e6ed-47eb-b153-64789ed7327e"


def test_zh_written_register_prompt_template_loads():
    """The new prompt template file exists and references key register
    conversion mappings (粵語 → 書面語) in its system_prompt."""
    path = CONFIG_ROOT / "prompt_templates_v5" / "refiner" / "zh_written_register_v6.json"
    assert path.exists(), f"Prompt template missing: {path}"
    template = json.loads(path.read_text())
    assert template["id"] == "refiner/zh_written_register_v6"
    assert template["lang"] == "zh"
    assert template["style"] == "written_register_v6"
    assert template["version"] == 6
    assert "system_prompt" in template
    # Spot-check the prompt documents at least the 2 most common register markers
    sp = template["system_prompt"]
    assert "嘅" in sp, "Prompt must reference 嘅 → 的 mapping"
    assert "的" in sp
    assert "係" in sp, "Prompt must reference 係 → 是 mapping"
    assert "是" in sp


def test_zh_written_register_refiner_profile_loads():
    """The new refiner profile exists, references the new template, and
    reuses the same LLM profile as the existing Cantonese refiner."""
    path = CONFIG_ROOT / "refiner_profiles" / f"{REFINER_UUID}.json"
    assert path.exists(), f"Refiner profile missing: {path}"
    profile = json.loads(path.read_text())
    assert profile["id"] == REFINER_UUID
    assert profile["lang"] == "zh"
    assert profile["style"] == "written_register_v6"
    assert profile["prompt_template_id"] == "refiner/zh_written_register_v6"
    # Reuses same LLM as the existing Cantonese refiner — no new LLM stack
    assert profile["llm_profile_id"] == SHARED_LLM_PROFILE
    # Sanity: name + ownership fields present
    assert "書面語" in profile["name"] or "written" in profile["name"].lower()
    assert profile["shared"] is False
    assert isinstance(profile["user_id"], int)


def test_v6_written_pipeline_has_chained_refiners():
    """The new pipeline file exists, clones the v6 Cantonese pipeline shape,
    and chains the existing Cantonese refiner BEFORE the new written refiner."""
    path = CONFIG_ROOT / "pipelines" / f"{PIPELINE_UUID}.json"
    assert path.exists(), f"Pipeline missing: {path}"
    pipeline = json.loads(path.read_text())
    assert pipeline["id"] == PIPELINE_UUID
    assert pipeline["pipeline_type"] == "v6_vad_dual_asr"
    assert pipeline["version"] == 6
    assert pipeline["source_lang"] == "zh"
    assert pipeline["target_languages"] == ["zh"]
    # Same ASR primary + qwen3 config as 4696bbaa (sanity — must use the same
    # transcribe profile so quality is identical to the Cantonese variant).
    assert pipeline["asr_primary"]["transcribe_profile_id"] == SHARED_TRANSCRIBE_PROFILE
    assert pipeline["qwen3_asr"]["language"] == "Chinese"
    # Chain order is significant — Cantonese refiner FIRST, written refiner SECOND
    refiners = pipeline["refinements"]["zh"]
    assert len(refiners) == 2, "Pipeline must chain exactly 2 refiners (Cantonese + written)"
    assert refiners[0]["refiner_profile_id"] == EXISTING_CANTONESE_REFINER
    assert refiners[1]["refiner_profile_id"] == REFINER_UUID
    # Name distinguishes from the Cantonese variant
    assert "書面語" in pipeline["name"]
