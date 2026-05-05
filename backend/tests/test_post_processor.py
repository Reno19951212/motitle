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
    # Phase B: zh_text stays clean, "long" appears in flags list
    assert processed[0]["zh_text"] == long_text
    assert "long" in processed[0].get("flags", [])


def test_length_flag_not_applied_when_within_limit():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    short_text = "颱風正逼近香港。"  # 8 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": short_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"] == short_text
    assert "long" not in processed[0].get("flags", [])


def test_length_flag_at_exact_limit_not_flagged():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    exact_text = "一二三四五六七八九十一二三四五六"  # exactly 16 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": exact_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"] == exact_text
    assert "long" not in processed[0].get("flags", [])


def test_length_flag_preserves_original_text():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=5)
    original = "超過字數限制的句子"
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": original}]
    processed = processor._flag_long_segments(results)
    # zh_text untouched, flag added separately
    assert processed[0]["zh_text"] == original
    assert "long" in processed[0]["flags"]


def test_length_flag_idempotent():
    """Re-flagging an already-flagged segment must not duplicate the flag."""
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=5)
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": "超過字數限制的句子", "flags": ["long"]}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["flags"] == ["long"]


def test_process_converts_simplified_and_flags_long():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "software", "zh_text": "软件"},
        {"start": 1.0, "end": 2.0, "en_text": "x", "zh_text": "政府宣布將於下月推出一系列新的經濟振興措施"},
    ]
    processed = processor.process(results)
    assert processed[0]["zh_text"] == "軟體"
    assert "long" not in processed[0].get("flags", [])
    # Long segment: zh_text remains clean, "long" appears in flags
    assert "[LONG]" not in processed[1]["zh_text"]
    assert "long" in processed[1].get("flags", [])


def test_process_opencc_runs_before_length_check():
    """opencc conversion happens before length check so length is measured on traditional text."""
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=3)
    # "软件测试" = 4 simplified chars → "軟體測試" = 4 traditional chars → flagged as long
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": "软件测试"}]
    processed = processor.process(results)
    assert processed[0]["zh_text"] == "軟體測試"
    assert "long" in processed[0].get("flags", [])
    assert "[LONG]" not in processed[0]["zh_text"]


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
        # zh_text untouched; "review" flag carries the warning instead
        assert r["zh_text"] == "重複"
        assert "review" in r.get("flags", [])
        assert "[NEEDS REVIEW]" not in r["zh_text"]


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


def test_validate_batch_clean_zh_not_double_flagged():
    """Phase B: zh_text never carries prefixes, so validate_batch operates on raw length directly."""
    from translation.post_processor import validate_batch
    # 26 chars > 40-char hallucination cutoff is OK (only flags >40)
    zh_26_chars = "一二三四五六七八九十一二三四五六七八九十一二三四五六"
    results = [{"en_text": "x" * 20, "zh_text": zh_26_chars}]
    assert validate_batch(results) == []


def test_validate_batch_hallucination_counts_only_zh_text():
    """Hallucination check measures actual zh_text length, no prefix involved post-Phase-B."""
    from translation.post_processor import validate_batch
    # 6-char zh vs 2-char en → 6 not > 2*3=6 → not flagged
    results = [{"en_text": "Hi", "zh_text": "六個字。"}]
    assert validate_batch(results) == []


def test_process_emits_clean_zh_text_for_renderer():
    """Renderer relies on zh_text being free of QA tags after process()."""
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=5)
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "Hi", "zh_text": "你好"},  # clean, short
        {"start": 1.0, "end": 2.0, "en_text": "Hello world", "zh_text": "超過字數限制的長句子"},  # >5 → long
        {"start": 2.0, "end": 3.0, "en_text": "A", "zh_text": "重複"},
        {"start": 3.0, "end": 4.0, "en_text": "B", "zh_text": "重複"},
        {"start": 4.0, "end": 5.0, "en_text": "C", "zh_text": "重複"},  # 3 reps → review
    ]
    processed = processor.process(results)
    for r in processed:
        # zh_text MUST never contain QA tag prefixes (renderer guarantee)
        assert "[LONG]" not in r["zh_text"]
        assert "[NEEDS REVIEW]" not in r["zh_text"]
    # And the structured flags carry the same information
    assert "long" in processed[1]["flags"]
    for i in (2, 3, 4):
        assert "review" in processed[i]["flags"]


# ---------------------------------------------------------------------------
# Phase 0 — flag_low_confidence (Whisper avg_logprob / compression_ratio)
# ---------------------------------------------------------------------------


def test_post_processor_flags_low_confidence_when_logprob_low():
    """avg_logprob < -0.6 → 'low_confidence' flag added."""
    from translation.post_processor import flag_low_confidence
    out = flag_low_confidence([
        {"en_text": "Hello", "zh_text": "你好", "asr_avg_logprob": -0.85},
    ])
    assert "low_confidence" in out[0]["flags"]


def test_post_processor_flags_low_confidence_when_compression_ratio_high():
    """compression_ratio > 2.4 → 'low_confidence' flag (Whisper's own threshold)."""
    from translation.post_processor import flag_low_confidence
    out = flag_low_confidence([
        {"en_text": "Hi", "zh_text": "你好", "asr_compression_ratio": 2.7},
    ])
    assert "low_confidence" in out[0]["flags"]


def test_post_processor_no_low_confidence_when_metrics_clean():
    """Healthy metrics → no flag added."""
    from translation.post_processor import flag_low_confidence
    out = flag_low_confidence([
        {
            "en_text": "Hi", "zh_text": "你好",
            "asr_avg_logprob": -0.30,
            "asr_compression_ratio": 1.5,
        },
    ])
    assert "low_confidence" not in out[0].get("flags", [])


def test_post_processor_no_low_confidence_when_metrics_absent():
    """Missing metrics treated as no-signal (no flag)."""
    from translation.post_processor import flag_low_confidence
    out = flag_low_confidence([
        {"en_text": "Hi", "zh_text": "你好"},
    ])
    assert "low_confidence" not in out[0].get("flags", [])


def test_flag_low_confidence_preserves_existing_flags():
    """Adding 'low_confidence' must not clobber pre-existing 'long' or 'review'."""
    from translation.post_processor import flag_low_confidence
    out = flag_low_confidence([
        {
            "en_text": "Hi", "zh_text": "x" * 30,
            "flags": ["long"],
            "asr_avg_logprob": -0.95,
        },
    ])
    assert "long" in out[0]["flags"]
    assert "low_confidence" in out[0]["flags"]


def test_flag_low_confidence_does_not_mutate_input():
    """Pure-function semantics: input list and dicts untouched."""
    from translation.post_processor import flag_low_confidence
    inp = [{"en_text": "Hi", "zh_text": "你好", "asr_avg_logprob": -0.95}]
    out = flag_low_confidence(inp)
    assert "flags" not in inp[0]
    assert "low_confidence" in out[0]["flags"]
