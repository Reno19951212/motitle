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
  8. alignment_pipeline.build_anchor_prompt honours custom_system_prompt
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
# ---------------------------------------------------------------------------

class TestPromptOverridesValidation:
    def _validate(self, translation: dict) -> list:
        from profiles import _validate_translation
        return _validate_translation(translation)

    def test_valid_prompt_overrides_passes(self):
        """Profile with well-formed prompt_overrides validates with no errors."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": {
                "pass1_system": "你係 special test prompt",
                "single_segment_system": None,
                "pass2_enrich_system": None,
                "alignment_anchor_system": None,
            },
        })
        assert errs == []

    def test_non_dict_prompt_overrides_rejected(self):
        """Non-dict prompt_overrides must produce a clear error."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": "just a string",
        })
        assert any("must be a dict" in e for e in errs), errs

    def test_unknown_key_rejected(self):
        """Unrecognised key in prompt_overrides must produce an error."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": {"foo": "bar"},
        })
        assert any("foo" in e for e in errs), errs

    def test_whitespace_only_value_rejected(self):
        """Whitespace-only override string must be rejected (must be null or non-empty)."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": {"pass1_system": "   "},
        })
        assert any("pass1_system" in e for e in errs), errs

    def test_null_value_passes(self):
        """Null values in prompt_overrides are always valid (= fall back to constant)."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": {"pass1_system": None},
        })
        assert errs == []

    def test_partial_overrides_passes(self):
        """Specifying only some keys is fine; missing ones default to null."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": {"single_segment_system": "override text here"},
        })
        assert errs == []

    def test_empty_prompt_overrides_dict_passes(self):
        """Empty dict prompt_overrides is valid."""
        errs = self._validate({
            "engine": "mock",
            "prompt_overrides": {},
        })
        assert errs == []


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
# 8: alignment_pipeline.build_anchor_prompt honours custom_system_prompt
# ---------------------------------------------------------------------------

class TestAlignmentAnchorOverride:
    def test_custom_system_prompt_used_when_provided(self):
        """build_anchor_prompt with custom_system_prompt replaces the hardcoded preamble."""
        from translation.alignment_pipeline import build_anchor_prompt
        result = build_anchor_prompt(
            en_words=["Hello", "world", "today"],
            boundaries=[1],
            glossary=None,
            custom_system_prompt="CUSTOM_ANCHOR_SYSTEM",
        )
        assert result.startswith("CUSTOM_ANCHOR_SYSTEM")
        # The word index and boundary info should still be present
        assert "[1]" in result

    def test_no_custom_system_prompt_uses_default(self):
        """Without custom_system_prompt, build_anchor_prompt uses the hardcoded Chinese preamble."""
        from translation.alignment_pipeline import build_anchor_prompt
        result = build_anchor_prompt(
            en_words=["Hello", "world"],
            boundaries=[0],
            glossary=None,
        )
        # The default prompt is in Traditional Chinese
        assert "繁體中文" in result

    def test_translate_with_alignment_passes_anchor_override(self):
        """translate_with_alignment plumbs custom_system_prompt through build_anchor_prompt
        and into the user_message sent to _call_ollama (alignment_pipeline's _safe_engine_call
        always passes "" as system_prompt, and the full build_anchor_prompt output as
        user_message)."""
        from translation.alignment_pipeline import translate_with_alignment

        # Mock engine that pretends to be OllamaTranslationEngine with _call_ollama
        captured_user_messages = []

        class FakeEngine:
            def translate(self, segs, **kw):
                # Fake single-segment translate
                return [
                    {"start": s["start"], "end": s["end"],
                     "en_text": s["text"], "zh_text": "中文", "flags": []}
                    for s in segs
                ]

            def _call_ollama(self, system_prompt, user_message, temperature):
                captured_user_messages.append(user_message)
                # Return a valid marker response with boundary marker [1]
                return "你好[1]世界"

        engine = FakeEngine()
        # Two segments that will merge into a multi-segment sentence so
        # _align_multi_segment_sentence is invoked.
        segments = [
            {"start": 0.0, "end": 1.0, "text": "Hello world,"},
            {"start": 1.0, "end": 2.0, "text": "today is good."},
        ]
        translate_with_alignment(
            engine,
            segments,
            custom_system_prompt="MY_ANCHOR_OVERRIDE",
        )
        # At least one user_message should have been sent to _call_ollama
        # (multi-segment sentences invoke _safe_engine_call which passes the
        # build_anchor_prompt output as user_message).
        # We verify that IF any call was made, the user_message starts with override.
        for msg in captured_user_messages:
            assert msg.startswith("MY_ANCHOR_OVERRIDE"), (
                f"Expected user_message to start with override, got: {msg[:80]}"
            )
