"""Tests for translation post-processor."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_validate_batch_no_issues():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "Hello.", "zh_text": "你好。"},
        {"en_text": "Goodbye.", "zh_text": "再見。"},
    ]
    assert validate_batch(results) == []


def test_validate_batch_detects_repetition():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "A", "zh_text": "重複"},
        {"en_text": "B", "zh_text": "重複"},
        {"en_text": "C", "zh_text": "重複"},
    ]
    bad = validate_batch(results)
    assert 0 in bad and 1 in bad and 2 in bad


def test_validate_batch_detects_missing():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "Hello.", "zh_text": "[TRANSLATION MISSING] Hello."},
    ]
    assert 0 in validate_batch(results)


def test_validate_batch_detects_hallucination():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "Hi", "zh_text": "你好，今天天氣很好，我很開心，希望大家都過得好。"},
    ]
    # zh len >> en len * 3
    assert 0 in validate_batch(results)


def test_validate_batch_two_repetitions_not_flagged():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "A", "zh_text": "重複"},
        {"en_text": "B", "zh_text": "重複"},
        {"en_text": "C", "zh_text": "不同"},
    ]
    # Only 2 consecutive identical — below threshold of 3
    assert validate_batch(results) == []
