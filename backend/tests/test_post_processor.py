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


def test_opencc_converts_simplified():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 0.0, "end": 1.0, "en_text": "software", "zh_text": "软件"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["zh_text"] == "軟體"


def test_opencc_converts_simplified_phrase():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 0.0, "end": 1.0, "en_text": "information", "zh_text": "信息技术"}]
    processed = processor._convert_to_traditional(results)
    # s2twp: 信息→資訊, 技术→科技 (Taiwan standard vocabulary)
    assert processed[0]["zh_text"] == "資訊科技"


def test_opencc_idempotent_on_traditional():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    # Use text that is already correct Traditional Chinese and unchanged by s2twp
    results = [{"start": 0.0, "end": 1.0, "en_text": "weather", "zh_text": "今天天氣很好。"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["zh_text"] == "今天天氣很好。"


def test_opencc_preserves_other_fields():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 1.5, "end": 3.0, "en_text": "test", "zh_text": "软件"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["start"] == 1.5
    assert processed[0]["end"] == 3.0
    assert processed[0]["en_text"] == "test"
