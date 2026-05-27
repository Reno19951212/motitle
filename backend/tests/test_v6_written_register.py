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
