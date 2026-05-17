"""Tests for per-profile inline prompt_overrides block (Architecture I).

Covers:
  1. Valid profile with prompt_overrides validates successfully
  2. Non-dict prompt_overrides rejected with clear error
  3. Unknown key rejected
  4. Whitespace-only override value rejected
  5. OllamaTranslationEngine._build_system_prompt returns override text when set,
     falls back to constant when null
  6. OllamaTranslationEngine._translate_single uses single_segment override
  7. OllamaTranslationEngine._enrich_batch uses pass2_enrich override
  8. (Removed in v4.0 A5 T9 — alignment_pipeline retired)
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helper: minimal valid profile dict
# ---------------------------------------------------------------------------

def _minimal_profile(extra_translation=None):
    t = {"engine": "mock"}
    if extra_translation:
        t.update(extra_translation)
    return {
        "name": "Test",
        "asr": {
            "engine": "whisper",
            "model_size": "tiny",
            "language": "en",
            "device": "cpu",
        },
        "translation": t,
    }


# ---------------------------------------------------------------------------
# 1–4: Validation in profiles.py
# v4.0 A5 T8: TestPromptOverridesValidation (7 tests) deleted — exercised
# profiles._validate_translation which is gone with the legacy ProfileManager.
# prompt_overrides validation for the v4 layer lives in
# translation/prompt_override_validator.py + test_file_prompt_overrides.py.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 5: _build_system_prompt honours pass1_system override
# ---------------------------------------------------------------------------

class TestBuildSystemPromptOverride:
    def _make_engine(self, overrides: dict):
        from translation.ollama_engine import OllamaTranslationEngine
        cfg = {"engine": "qwen2.5-3b", "prompt_overrides": overrides}
        return OllamaTranslationEngine(cfg)

    def test_pass1_override_used_when_set(self):
        engine = self._make_engine({"pass1_system": "你係 special test prompt"})
        result = engine._build_system_prompt(style="formal", glossary=[])
        assert result == "你係 special test prompt"

    def test_pass1_override_used_for_cantonese_style_too(self):
        """Override replaces style selection entirely."""
        engine = self._make_engine({"pass1_system": "override for cantonese test"})
        result = engine._build_system_prompt(style="cantonese", glossary=[])
        assert result == "override for cantonese test"

    def test_pass1_null_falls_back_to_formal_constant(self):
        from translation.ollama_engine import SYSTEM_PROMPT_FORMAL
        engine = self._make_engine({"pass1_system": None})
        result = engine._build_system_prompt(style="formal", glossary=[])
        assert result.startswith(SYSTEM_PROMPT_FORMAL[:20])

    def test_pass1_null_falls_back_to_cantonese_constant(self):
        from translation.ollama_engine import SYSTEM_PROMPT_CANTONESE
        engine = self._make_engine({"pass1_system": None})
        result = engine._build_system_prompt(style="cantonese", glossary=[])
        assert result.startswith(SYSTEM_PROMPT_CANTONESE[:20])

    def test_no_overrides_key_falls_back(self):
        """Engine with no prompt_overrides key uses constants normally."""
        from translation.ollama_engine import OllamaTranslationEngine, SYSTEM_PROMPT_FORMAL
        engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
        result = engine._build_system_prompt(style="formal", glossary=[])
        assert result.startswith(SYSTEM_PROMPT_FORMAL[:20])

    def test_pass1_override_with_glossary_appended(self):
        """Glossary terms are still appended after the override base prompt."""
        engine = self._make_engine({"pass1_system": "My custom base"})
        glossary = [{"source": "Chelsea", "target": "車路士"}]
        result = engine._build_system_prompt(style="formal", glossary=glossary)
        assert "My custom base" in result
        assert "Chelsea" in result
        assert "車路士" in result


# ---------------------------------------------------------------------------
# 6: _translate_single uses single_segment_system override
# ---------------------------------------------------------------------------

class TestTranslateSingleOverride:
    def test_single_segment_override_passed_to_ollama(self):
        """_translate_single should use single_segment_system override as system prompt."""
        from translation.ollama_engine import OllamaTranslationEngine
        cfg = {
            "engine": "qwen2.5-3b",
            "prompt_overrides": {"single_segment_system": "CUSTOM_SINGLE_PROMPT"},
        }
        engine = OllamaTranslationEngine(cfg)
        captured = {}

        def fake_call_ollama(system_prompt, user_message, temperature):
            captured["system_prompt"] = system_prompt
            return "翻譯結果"

        engine._call_ollama = fake_call_ollama
        seg = {"start": 0.0, "end": 1.0, "text": "Hello world."}
        engine._translate_single(seg, glossary=[], style="formal", temperature=0.1)
        assert captured.get("system_prompt", "").startswith("CUSTOM_SINGLE_PROMPT")

    def test_single_segment_null_falls_back_to_constant(self):
        """When single_segment_system is null, falls back to SINGLE_SEGMENT_SYSTEM_PROMPT."""
        from translation.ollama_engine import OllamaTranslationEngine, SINGLE_SEGMENT_SYSTEM_PROMPT
        cfg = {
            "engine": "qwen2.5-3b",
            "prompt_overrides": {"single_segment_system": None},
        }
        engine = OllamaTranslationEngine(cfg)
        captured = {}

        def fake_call_ollama(system_prompt, user_message, temperature):
            captured["system_prompt"] = system_prompt
            return "翻譯結果"

        engine._call_ollama = fake_call_ollama
        seg = {"start": 0.0, "end": 1.0, "text": "Hello world."}
        engine._translate_single(seg, glossary=[], style="formal", temperature=0.1)
        assert captured["system_prompt"].startswith(SINGLE_SEGMENT_SYSTEM_PROMPT[:20])


# ---------------------------------------------------------------------------
# 7: _enrich_batch uses pass2_enrich_system override
# ---------------------------------------------------------------------------

class TestEnrichBatchOverride:
    def test_pass2_override_used_in_enrich_batch(self):
        """_enrich_batch should use pass2_enrich_system override as system prompt."""
        from translation.ollama_engine import OllamaTranslationEngine
        cfg = {
            "engine": "qwen2.5-3b",
            "prompt_overrides": {"pass2_enrich_system": "CUSTOM_ENRICH_PROMPT"},
        }
        engine = OllamaTranslationEngine(cfg)
        captured = {}

        def fake_call_ollama(system_prompt, user_message, temperature):
            captured["system_prompt"] = system_prompt
            return "1. 翻譯結果"

        engine._call_ollama = fake_call_ollama
        segs = [{"start": 0.0, "end": 1.0, "text": "Hello world."}]
        p1 = [{"start": 0.0, "end": 1.0, "zh_text": "你好世界", "en_text": "Hello world.", "flags": []}]
        engine._enrich_batch(segs, p1, glossary=[], temperature=0.1)
        assert captured.get("system_prompt", "").startswith("CUSTOM_ENRICH_PROMPT")

    def test_pass2_null_falls_back_to_constant(self):
        """When pass2_enrich_system is null, falls back to ENRICH_SYSTEM_PROMPT."""
        from translation.ollama_engine import OllamaTranslationEngine, ENRICH_SYSTEM_PROMPT
        cfg = {
            "engine": "qwen2.5-3b",
            "prompt_overrides": {"pass2_enrich_system": None},
        }
        engine = OllamaTranslationEngine(cfg)
        captured = {}

        def fake_call_ollama(system_prompt, user_message, temperature):
            captured["system_prompt"] = system_prompt
            return "1. 翻譯結果"

        engine._call_ollama = fake_call_ollama
        segs = [{"start": 0.0, "end": 1.0, "text": "Hello world."}]
        p1 = [{"start": 0.0, "end": 1.0, "zh_text": "你好世界", "en_text": "Hello world.", "flags": []}]
        engine._enrich_batch(segs, p1, glossary=[], temperature=0.1)
        assert captured["system_prompt"].startswith(ENRICH_SYSTEM_PROMPT[:20])


# ---------------------------------------------------------------------------
# 8: v4.0 A5 T9 — TestAlignmentAnchorOverride (3 tests) deleted along with
# translation.alignment_pipeline (LLM-marker alignment retired; MTStage from
# A1 does not invoke it). build_anchor_prompt no longer exists.
# ---------------------------------------------------------------------------
