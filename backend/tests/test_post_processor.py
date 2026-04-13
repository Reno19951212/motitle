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


def test_length_flag_applied_when_over_limit():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    long_text = "政府宣布將於下月推出一系列新的經濟振興措施"  # 21 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": long_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"].startswith("[LONG] ")
    assert long_text in processed[0]["zh_text"]


def test_length_flag_not_applied_when_within_limit():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    short_text = "颱風正逼近香港。"  # 8 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": short_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"] == short_text


def test_length_flag_at_exact_limit_not_flagged():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    exact_text = "一二三四五六七八九十一二三四五六"  # exactly 16 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": exact_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"] == exact_text


def test_length_flag_preserves_original_text():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=5)
    original = "超過字數限制的句子"
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": original}]
    processed = processor._flag_long_segments(results)
    # Original text is preserved, not truncated
    assert original in processed[0]["zh_text"]


def test_process_converts_simplified_and_flags_long():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "software", "zh_text": "软件"},
        {"start": 1.0, "end": 2.0, "en_text": "x", "zh_text": "政府宣布將於下月推出一系列新的經濟振興措施"},
    ]
    processed = processor.process(results)
    assert processed[0]["zh_text"] == "軟體"          # simplified converted
    assert "[LONG]" in processed[1]["zh_text"]  # long flagged


def test_process_opencc_runs_before_length_check():
    """opencc conversion happens before length check so length is measured on traditional text."""
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=3)
    # "软件测试" = 4 simplified chars → "軟體測試" = 4 traditional chars → flagged as LONG
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": "软件测试"}]
    processed = processor.process(results)
    assert "軟體測試" in processed[0]["zh_text"]
    assert "[LONG]" in processed[0]["zh_text"]


def test_process_marks_bad_segments_needs_review():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"en_text": "A", "zh_text": "重複", "start": 0.0, "end": 1.0},
        {"en_text": "B", "zh_text": "重複", "start": 1.0, "end": 2.0},
        {"en_text": "C", "zh_text": "重複", "start": 2.0, "end": 3.0},
    ]
    processed = processor.process(results)
    for r in processed:
        assert r["zh_text"].startswith("[NEEDS REVIEW]")


def test_process_clean_input_unchanged():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "Good evening.", "zh_text": "各位晚上好。"},
        {"start": 1.0, "end": 2.0, "en_text": "Welcome.", "zh_text": "歡迎收看。"},
    ]
    processed = processor.process(results)
    assert processed[0]["zh_text"] == "各位晚上好。"
    assert processed[1]["zh_text"] == "歡迎收看。"


def test_validate_batch_not_double_flagged_after_long_prefix():
    """validate_batch should not flag a segment solely because [LONG] prefix inflates its length."""
    from translation.post_processor import validate_batch
    # zh_text has [LONG] prefix already applied (26-char original → 33 chars with prefix)
    # Should NOT trigger the too-long check — the original text is only moderately over limit
    zh_26_chars = "一二三四五六七八九十一二三四五六七八九十一二三四五六"  # 26 chars
    results = [{"en_text": "x" * 20, "zh_text": f"[LONG] {zh_26_chars}"}]
    bad = validate_batch(results)
    assert bad == [], f"Expected no bad indices, got {bad} (double-flagging bug)"


def test_validate_batch_prefix_stripped_for_hallucination_check():
    """Hallucination check should not count [LONG] prefix chars against zh length."""
    from translation.post_processor import validate_batch
    # Short en_text (2 chars), zh is 6 chars after stripping [LONG] prefix (8 chars)
    # Without stripping: 15 chars "[LONG] 六個字。" > 2*3=6 → flagged as hallucination
    # With stripping: 6 chars "六個字。" is not > 2*3=6 → not flagged
    results = [{"en_text": "Hi", "zh_text": "[LONG] 六個字。"}]
    bad = validate_batch(results)
    assert bad == [], f"Expected no bad indices, got {bad} ([LONG] prefix inflated hallucination check)"
