"""Tests for sentence-aware translation pipeline."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_merge_empty_segments():
    from translation.sentence_pipeline import merge_to_sentences
    result = merge_to_sentences([])
    assert result == []


def test_merge_single_complete_sentence():
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello world."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 1
    assert result[0]["text"] == "Hello world."
    assert result[0]["seg_indices"] == [0]
    assert result[0]["seg_word_counts"] == {0: 2}
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 3.0


def test_merge_fragments_into_two_sentences():
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 4.0, "text": "the mat. The dog"},
        {"start": 4.0, "end": 6.0, "text": "ran away quickly."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 2
    assert "The cat sat on the mat." in result[0]["text"]
    assert 0 in result[0]["seg_indices"]
    assert 1 in result[0]["seg_indices"]
    assert result[0]["start"] == 0.0
    assert "The dog ran away quickly." in result[1]["text"]
    assert 1 in result[1]["seg_indices"]
    assert 2 in result[1]["seg_indices"]
    assert result[1]["end"] == 6.0


def test_merge_shared_segment():
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence here."},
        {"start": 3.0, "end": 6.0, "text": "Second one. Third starts"},
        {"start": 6.0, "end": 9.0, "text": "and finishes here."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 3
    total_seg1_words = sum(
        s["seg_word_counts"].get(1, 0) for s in result
    )
    assert total_seg1_words == 4


def test_redistribute_single_sentence_three_segments():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 5.0, "text": "the mat and then"},
        {"start": 5.0, "end": 7.0, "text": "went to sleep."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["貓坐在墊子上，然後去睡覺了。"]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 3
    combined = "".join(r["zh_text"] for r in result)
    assert combined == "貓坐在墊子上，然後去睡覺了。"
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.0
    assert result[1]["start"] == 2.0
    assert result[1]["end"] == 5.0
    assert result[2]["start"] == 5.0
    assert result[2]["end"] == 7.0
    assert result[0]["en_text"] == "The cat sat on"
    assert result[2]["en_text"] == "went to sleep."


def test_redistribute_prefers_punctuation_break():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello there my friend"},
        {"start": 3.0, "end": 6.0, "text": "how are you doing today."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["你好啊，我的朋友你今天怎麼樣。"]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 2
    assert result[0]["zh_text"].endswith("，") or "，" in result[0]["zh_text"]


def test_redistribute_shared_segment_merged():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments
    original_segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence."},
        {"start": 3.0, "end": 6.0, "text": "Second sentence."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["第一句話。", "第二句話。"]
    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 2
    assert result[0]["zh_text"] == "第一句話。"
    assert result[1]["zh_text"] == "第二句話。"
    assert result[0]["start"] == 0.0
    assert result[1]["start"] == 3.0


def test_validate_all_valid():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。"},
        {"start": 2.0, "end": 4.0, "en_text": "World.", "zh_text": "世界。"},
    ]
    assert validate_batch(results) == []


def test_validate_repetition():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "A", "zh_text": "重複"},
        {"start": 1.0, "end": 2.0, "en_text": "B", "zh_text": "重複"},
        {"start": 2.0, "end": 3.0, "en_text": "C", "zh_text": "重複"},
        {"start": 3.0, "end": 4.0, "en_text": "D", "zh_text": "正常"},
    ]
    bad = validate_batch(results)
    assert 0 in bad
    assert 1 in bad
    assert 2 in bad
    assert 3 not in bad


def test_validate_missing():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。"},
        {"start": 2.0, "end": 4.0, "en_text": "World.", "zh_text": "[TRANSLATION MISSING] World."},
    ]
    bad = validate_batch(results)
    assert 1 in bad
    assert 0 not in bad


def test_validate_too_long():
    from translation.sentence_pipeline import validate_batch
    long_zh = "一" * 33
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Short.", "zh_text": long_zh},
    ]
    bad = validate_batch(results)
    assert 0 in bad


def test_validate_hallucination():
    from translation.sentence_pipeline import validate_batch
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hi", "zh_text": "一二三四五六七"},
    ]
    bad = validate_batch(results)
    assert 0 in bad


def test_translate_with_sentences_basic():
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 4.0, "text": "the mat."},
        {"start": 4.0, "end": 6.0, "text": "The dog ran."},
    ]
    result = translate_with_sentences(engine, segments)
    assert len(result) == 3
    for r in result:
        assert r["zh_text"] != ""
        assert r["en_text"] != ""
    assert result[0]["start"] == 0.0
    assert result[2]["end"] == 6.0


def test_translate_with_sentences_empty():
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    result = translate_with_sentences(engine, [])
    assert result == []


def test_merge_respects_time_gap_guard():
    """A gap larger than max_gap_sec forces a sentence boundary even if
    pySBD would otherwise merge the text."""
    from translation.sentence_pipeline import merge_to_sentences
    # Two fragments that would normally merge into one sentence, but the
    # 2.5-second gap between them exceeds the 1.5-second default threshold.
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 4.5, "end": 7.0, "text": "the mat yesterday."},
    ]
    result = merge_to_sentences(segments)
    # Gap (4.5 - 2.0 = 2.5s) > 1.5s → must produce two separate units
    assert len(result) == 2
    assert result[0]["seg_indices"] == [0]
    assert result[1]["seg_indices"] == [1]


def test_merge_allows_small_gap():
    """A gap smaller than max_gap_sec allows pySBD to merge across segments."""
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.3, "end": 4.0, "text": "the mat yesterday."},
    ]
    result = merge_to_sentences(segments)
    # Gap 0.3s < 1.5s → merged into one sentence
    assert len(result) == 1
    assert result[0]["seg_indices"] == [0, 1]


def test_merge_custom_max_gap():
    """max_gap_sec parameter controls the split threshold."""
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 3.0, "end": 5.0, "text": "the mat yesterday."},
    ]
    # Default 1.5s would NOT split (gap is 1.0s)
    assert len(merge_to_sentences(segments)) == 1
    # Strict 0.5s SHOULD split
    assert len(merge_to_sentences(segments, max_gap_sec=0.5)) == 2


def test_merge_preserves_timestamps_after_split():
    """After gap-split, each merged sentence gets correct start/end from its segments."""
    from translation.sentence_pipeline import merge_to_sentences
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello world."},
        {"start": 5.0, "end": 7.0, "text": "Goodbye."},  # gap=3s
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 2
    assert result[0]["start"] == 0.0 and result[0]["end"] == 2.0
    assert result[1]["start"] == 5.0 and result[1]["end"] == 7.0


def test_translate_with_sentences_progress_callback():
    """Progress callback is invoked with segment-scale counts, not sentence counts."""
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    # 3 segments that merge into 1 sentence
    segments = [
        {"start": 0.0, "end": 1.0, "text": "The cat"},
        {"start": 1.0, "end": 2.0, "text": "sat on"},
        {"start": 2.0, "end": 3.0, "text": "the mat."},
    ]
    calls = []
    def cb(done, total):
        calls.append((done, total))
    translate_with_sentences(engine, segments, progress_callback=cb)
    # Callback should report totals in units of original segments (3), not sentences (1)
    assert calls, "callback must be invoked at least once"
    for done, total in calls:
        assert total == 3, f"expected total=3 segments, got {total}"


def test_find_break_point_prefers_soft_over_hard():
    """SOFT 「，」at distance 5 should beat HARD 「。」at distance 11."""
    from translation.sentence_pipeline import _find_break_point
    text = "本賽季唯一上陣時間超過百分之七十五的皇馬後防四人組成員，僅有左閘阿爾瓦羅·卡雷拉斯一人。"
    # target = 33 (mid-name), 「，」at 28, 「。」at 44
    assert len(text) == 44
    assert text[27] == "，"
    assert text[43] == "。"
    pos = _find_break_point(text, target=33)
    assert pos == 28, f"Expected break at 「，」 (pos 28), got {pos}"


def test_find_break_point_max_pos_constraint():
    """max_pos limits search to prevent picking sentence-final 。 that empties next seg."""
    from translation.sentence_pipeline import _find_break_point
    text = "本賽季唯一上陣時間超過百分之七十五的皇馬後防四人組成員，僅有左閘阿爾瓦羅·卡雷拉斯一人。"
    # target = 33, max_pos = 35 (force search to skip the 「。」 at pos 44)
    pos = _find_break_point(text, target=33, max_pos=35)
    assert pos == 28, f"Expected 「，」 at 28, got {pos}"


def test_find_break_point_no_punct_falls_back_to_target():
    """When no punct in search range, returns target unchanged."""
    from translation.sentence_pipeline import _find_break_point
    text = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰"  # no punctuation
    pos = _find_break_point(text, target=8)
    assert pos == 8


def test_find_break_point_search_range_15():
    """Default search_range=15 should reach SOFT punct at distance 7 from target=18."""
    from translation.sentence_pipeline import _find_break_point
    # 「，」at pos 11 (index 10); text length = 21
    # target=18 is 7 chars away — within default search_range=15 → should find 「，」
    text = "甲乙丙丁戊己庚辛壬癸，甲乙丙丁戊己庚辛壬癸"  # 「，」at pos 11
    assert len(text) == 21
    assert text[10] == "，"
    pos = _find_break_point(text, target=18)  # distance 7 from 「，」
    assert pos == 11, f"Expected 「，」 at 11, got {pos}"


def test_redistribute_avoids_mid_name_cut():
    """Hybrid v2 redistribute should split at 「，」 not mid-name."""
    from translation.sentence_pipeline import redistribute_to_segments
    merged_sentences = [{
        "seg_indices": [0, 1],
        "seg_word_counts": {0: 18, 1: 6},
        "merged_text": "ignored",
    }]
    zh_sentences = ["本賽季唯一上陣時間超過七成比賽的皇馬後防四人組成員，僅有左閘阿爾瓦羅·卡雷拉斯一人。"]
    original_segments = [
        {"start": 0, "end": 5, "text": "The only member..."},
        {"start": 5, "end": 10, "text": "season is left back..."},
    ]
    results = redistribute_to_segments(merged_sentences, zh_sentences, original_segments)
    assert len(results) == 2
    seg0_zh = results[0]["zh_text"]
    seg1_zh = results[1]["zh_text"]
    # Seg 0 should end with 「，」, seg 1 should be non-empty and contain the name
    assert seg0_zh.endswith("，"), f"Seg 0 should end with 「，」, got: {seg0_zh!r}"
    assert seg1_zh.strip(), f"Seg 1 should not be empty, got: {seg1_zh!r}"
    assert "阿爾瓦羅" in seg1_zh, f"Name 阿爾瓦羅 should be in seg 1, got: {seg1_zh!r}"
    # Specifically the name should NOT be cut between segments
    assert not seg0_zh.endswith("阿"), f"Seg 0 should not end mid-name, got: {seg0_zh!r}"


