import pytest


def test_no_splitting_needed():
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 3.0, "text": "Hello world this is a test."}]
    result = split_segments(segments, max_words=40, max_duration=10.0)
    assert len(result) == 1
    assert result[0]["text"] == "Hello world this is a test."


def test_split_by_word_count():
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 6.0, "text": "one two three four five six seven eight nine ten eleven twelve"}]
    result = split_segments(segments, max_words=5, max_duration=60.0)
    assert len(result) >= 2
    for seg in result:
        assert len(seg["text"].split()) <= 5


def test_split_by_duration():
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 10.0, "text": "one two three four five six seven eight nine ten"}]
    result = split_segments(segments, max_words=200, max_duration=3.0)
    assert len(result) >= 3
    for seg in result:
        duration = seg["end"] - seg["start"]
        assert duration <= 3.5


def test_split_preserves_timing():
    from asr.segment_utils import split_segments
    segments = [{"start": 10.0, "end": 20.0, "text": "one two three four five six seven eight nine ten"}]
    result = split_segments(segments, max_words=5, max_duration=60.0)
    assert result[0]["start"] == 10.0
    assert result[-1]["end"] == 20.0
    for i in range(len(result) - 1):
        assert abs(result[i]["end"] - result[i + 1]["start"]) < 0.01


def test_empty_segments():
    from asr.segment_utils import split_segments
    assert split_segments([], max_words=40, max_duration=10.0) == []


def test_single_word_segment():
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
    result = split_segments(segments, max_words=40, max_duration=10.0)
    assert len(result) == 1


def test_multiple_segments_mixed():
    from asr.segment_utils import split_segments
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Short sentence."},
        {"start": 2.0, "end": 12.0, "text": "This is a very long sentence that has way too many words for a single subtitle segment to display properly on screen"},
    ]
    result = split_segments(segments, max_words=10, max_duration=10.0)
    assert len(result) >= 3
    assert result[0]["text"] == "Short sentence."


def test_sentence_boundary_splitting():
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 8.0, "text": "Hello world. This is great. And more text here for testing."}]
    result = split_segments(segments, max_words=5, max_duration=60.0)
    assert len(result) >= 2
    for seg in result:
        assert len(seg["text"].split()) <= 5


# ── Phase 6 Step 1: word timestamps preservation through split_segments ──────


def test_split_preserves_words_when_no_split_needed():
    """A short segment with words should pass them through unchanged."""
    from asr.segment_utils import split_segments
    words = [
        {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.9},
        {"word": "world", "start": 0.5, "end": 1.0, "probability": 0.8},
    ]
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello world", "words": words}]
    result = split_segments(segments, max_words=25, max_duration=40.0)
    assert len(result) == 1
    assert result[0]["words"] == words


def test_split_omits_words_when_not_provided():
    """Segments without words should produce results without words field."""
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello world"}]
    result = split_segments(segments, max_words=25, max_duration=40.0)
    assert "words" not in result[0]


def test_split_partitions_words_across_sub_segments():
    """When splitting, each sub-segment gets its slice of word timestamps."""
    from asr.segment_utils import split_segments
    words = [
        {"word": w, "start": float(i), "end": float(i) + 0.5, "probability": 0.9}
        for i, w in enumerate(["one", "two", "three", "four", "five", "six."])
    ]
    segments = [{"start": 0.0, "end": 6.0,
                 "text": "one two three four five six.",
                 "words": words}]
    result = split_segments(segments, max_words=3, max_duration=60.0)
    assert len(result) == 2
    # First 3 words → first sub-segment, last 3 → second
    assert len(result[0]["words"]) == 3
    assert len(result[1]["words"]) == 3
    assert result[0]["words"][0]["word"] == "one"
    assert result[1]["words"][0]["word"] == "four"


def test_split_skips_words_on_count_mismatch():
    """If engine words count doesn't match text.split() count, skip rather than corrupt."""
    from asr.segment_utils import split_segments
    # 2 words in engine list but 3 words in text (punctuation quirk)
    words = [
        {"word": "Hello", "start": 0.0, "end": 0.4, "probability": 0.9},
        {"word": "world.", "start": 0.4, "end": 1.0, "probability": 0.9},
    ]
    segments = [{"start": 0.0, "end": 2.0, "text": "Hello beautiful world.", "words": words}]
    result = split_segments(segments, max_words=1, max_duration=60.0)
    # Split happens, but words not partitioned (count mismatch safe-fallback)
    for seg in result:
        assert "words" not in seg


def test_split_by_max_chars_en():
    """max_chars constraint splits long EN text without word-count or duration trigger."""
    from asr.segment_utils import split_segments
    text = ("There were three areas in particular that were highlighted as "
            "needing an overhaul of the squad and coaching philosophy")  # 117 chars, 19 words
    segments = [{"start": 0.0, "end": 5.0, "text": text}]
    # max_words=20 (won't trigger), max_duration=60 (won't trigger), max_chars=88 (triggers)
    result = split_segments(segments, max_words=20, max_duration=60.0, max_chars=88)
    assert len(result) >= 2
    # Each chunk fits cap+tail (within Netflix budget)
    for seg in result:
        assert len(seg["text"]) <= 88, f"chunk over 88c: {seg['text']!r}"
    # No data loss
    assert " ".join(s["text"] for s in result).split() == text.split()


def test_max_chars_inert_on_zh_text():
    """max_chars must NOT split Chinese text (no spaces) — would create chunks
    without internal punct, making wrap_zh hard-cut worse, not better."""
    from asr.segment_utils import split_segments
    text = "在後防方面大衛阿拉巴與安東尼奧呂迪格的傷病纏身令皇馬後防嚴重告急"  # 30 chars, no spaces
    segments = [{"start": 0.0, "end": 3.0, "text": text}]
    result = split_segments(segments, max_words=30, max_duration=60.0, max_chars=15)
    # ZH path: max_chars must NOT trigger (would be destructive)
    assert len(result) == 1
    assert result[0]["text"] == text


def test_max_chars_default_none_preserves_legacy_behavior():
    """Without max_chars param, behavior matches v3.8.x — backward compat."""
    from asr.segment_utils import split_segments
    text = "a " * 50  # 100 chars, 50 words
    segments = [{"start": 0.0, "end": 5.0, "text": text.strip()}]
    legacy = split_segments(segments, max_words=200, max_duration=60.0)
    new_default = split_segments(segments, max_words=200, max_duration=60.0, max_chars=None)
    assert legacy == new_default
