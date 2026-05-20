"""Tests for v5 segment-bloat hardening (R1-R6)."""
import pytest
from unittest.mock import Mock


# ---- R2: max_tokens cap on all three engines ----

def test_refiner_passes_max_tokens_200():
    """LLMRefiner.refine() must cap LLM output at 200 tokens per segment."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "polished"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    rf.refine([{"start": 0, "end": 1, "text": "input"}])
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 200, \
        f"Refiner must call llm.call(max_tokens=200), got {kwargs}"


def test_translator_passes_max_tokens_300():
    """LLMTranslator.translate() must cap LLM output at 300 tokens per segment."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "translated"
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="en", target_lang="zh")
    tr.translate([{"start": 0, "end": 1, "text": "input"}])
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 300, \
        f"Translator must call llm.call(max_tokens=300), got {kwargs}"


def test_verifier_passes_max_tokens_150():
    """LLMVerifier.verify() must cap LLM judge output at 150 tokens per segment."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "chosen"
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="zh")
    primary = [{"start": 0, "end": 5, "text": "primary text"}]
    # Secondary words covering 0-5s with text different from primary so LLM gets invoked
    secondary_words = [
        {"start": 0.5, "end": 1.0, "text": "different"},
        {"start": 1.5, "end": 2.0, "text": "secondary"},
    ]
    vf.verify(primary, secondary_words)
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 150, \
        f"Verifier must call llm.call(max_tokens=150), got {kwargs}"
