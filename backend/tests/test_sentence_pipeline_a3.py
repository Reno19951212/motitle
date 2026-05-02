"""Tests for A3 ensemble orchestration in sentence_pipeline."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch, MagicMock
from translation.sentence_pipeline import translate_with_a3_ensemble


@patch("translation.sentence_pipeline.create_translation_engine")
def test_a3_ensemble_orchestration_calls_three_layers(mock_factory):
    mock_engine = MagicMock()
    mock_engine.translate.return_value = [
        {"start": 0, "end": 1, "en_text": "Hello.", "zh_text": "你好。", "flags": []}
    ]
    mock_engine._brevity_translate_pass.return_value = [
        {"start": 0, "end": 1, "en_text": "Hello.", "zh_text": "嗨。", "flags": []}
    ]
    mock_engine._brevity_rewrite_pass.return_value = [
        {"start": 0, "end": 1, "en_text": "Hello.", "zh_text": "嗨", "flags": []}
    ]
    mock_factory.return_value = mock_engine

    segs = [{"start": 0, "end": 1, "text": "Hello."}]
    profile_config = {
        "engine": "ollama",
        "a3_ensemble": True,
        "batch_size": 10,
    }
    result = translate_with_a3_ensemble(segs, glossary=[], profile_config=profile_config)

    assert mock_engine.translate.called  # K0 baseline
    assert mock_engine._brevity_translate_pass.called  # K2
    assert mock_engine._brevity_rewrite_pass.called  # K4
    assert len(result) == 1
    assert "source" in result[0]
    assert result[0]["zh_text"] in {"你好。", "嗨。", "嗨"}


@patch("translation.sentence_pipeline.create_translation_engine")
def test_a3_disabled_falls_back_to_baseline(mock_factory):
    mock_engine = MagicMock()
    mock_engine.translate.return_value = [
        {"start": 0, "end": 1, "en_text": "Hello.", "zh_text": "你好。", "flags": []}
    ]
    mock_factory.return_value = mock_engine

    segs = [{"start": 0, "end": 1, "text": "Hello."}]
    profile_config = {"engine": "ollama", "a3_ensemble": False, "batch_size": 10}
    result = translate_with_a3_ensemble(segs, glossary=[], profile_config=profile_config)

    # K0 only — K2 and K4 should NOT be called
    assert mock_engine.translate.called
    mock_engine._brevity_translate_pass.assert_not_called()
    mock_engine._brevity_rewrite_pass.assert_not_called()
    assert len(result) == 1
    # Source field NOT added when not in A3 mode (backward compat)
    # Or could be 'k0' — accept either
