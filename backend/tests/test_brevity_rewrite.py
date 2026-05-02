"""Tests for OllamaTranslationEngine brevity translate + rewrite passes (Task 9)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch, MagicMock
from translation.ollama_engine import (
    OllamaTranslationEngine,
    SYSTEM_PROMPT_BREVITY_TC,
)


@patch("translation.ollama_engine.OllamaTranslationEngine._call_ollama")
def test_brevity_translate_pass_uses_brevity_prompt(mock_call):
    mock_call.return_value = "1. 短譯文"
    engine = OllamaTranslationEngine({"engine": "ollama"})
    segs = [{"start": 0.0, "end": 1.0, "text": "Hello world"}]
    result = engine._brevity_translate_pass(segs, glossary=[], temperature=0.1)
    args, kwargs = mock_call.call_args
    system_prompt = args[0]
    assert SYSTEM_PROMPT_BREVITY_TC in system_prompt
    assert len(result) == 1


@patch("translation.ollama_engine.OllamaTranslationEngine._call_ollama")
def test_brevity_rewrite_skips_short_segments(mock_call):
    """zh ≤ cap should not be rewritten."""
    mock_call.return_value = "短"
    engine = OllamaTranslationEngine({"engine": "ollama"})
    segs = [{"start": 0.0, "end": 1.0, "en_text": "X", "zh_text": "短"}]  # 1c, ≤14
    result = engine._brevity_rewrite_pass(segs, must_keep_per_seg=[[]], cap=14, temperature=0.1)
    mock_call.assert_not_called()
    assert result[0]["zh_text"] == "短"


@patch("translation.ollama_engine.OllamaTranslationEngine._call_ollama")
def test_brevity_rewrite_keeps_original_if_must_keep_dropped(mock_call):
    """If LLM rewrite drops a must-keep entity, fall back to original zh_text."""
    mock_call.return_value = "球隊重建"  # missing 阿拉巴
    engine = OllamaTranslationEngine({"engine": "ollama"})
    segs = [{"start": 0.0, "end": 1.0, "en_text": "Alaba injured",
             "zh_text": "阿拉巴受傷令皇馬陣容極度告急堪憂"}]  # 16c
    result = engine._brevity_rewrite_pass(
        segs, must_keep_per_seg=[["阿拉巴"]], cap=14, temperature=0.1
    )
    assert result[0]["zh_text"] == "阿拉巴受傷令皇馬陣容極度告急堪憂"  # unchanged
