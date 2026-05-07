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


# ---------------------------------------------------------------------------
# merge_short_segments — sentence-punctuation heuristic post-processor
# ---------------------------------------------------------------------------

def test_merge_short_backward_with_period():
    """Short segment ending with sentence punctuation merges into PREVIOUS."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 4.0, "text": "this is a perfectly normal segment"},
        {"start": 4.0, "end": 4.3, "text": "okay."},
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    assert len(result) == 1
    assert result[0]["text"] == "this is a perfectly normal segment okay."
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 4.3


def test_merge_short_forward_no_period():
    """Short segment WITHOUT sentence punctuation merges into NEXT."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 0.3, "text": "a"},
        {"start": 0.3, "end": 4.0, "text": "normal segment after the lonely a"},
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    assert len(result) == 1
    assert result[0]["text"] == "a normal segment after the lonely a"
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 4.0


def test_merge_skips_when_gap_too_large():
    """Gap > max_gap_sec → leave segment alone (no merge)."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 4.0, "text": "first segment ends here"},
        {"start": 5.5, "end": 5.8, "text": "okay."},  # 1.5s gap > 0.5s
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    assert len(result) == 2
    assert result[1]["text"] == "okay."


def test_merge_skips_when_cap_exceeded():
    """Merge that would exceed max_words_cap is skipped."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 5.0,
         "text": "one two three four five six seven eight nine ten eleven"},  # 11 words
        {"start": 5.0, "end": 5.3, "text": "foo bar."},  # 2 words, ends with period
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    # 11 + 2 = 13 > 12 → skip merge
    assert len(result) == 2
    assert result[0]["text"].split() == ["one", "two", "three", "four", "five",
                                          "six", "seven", "eight", "nine", "ten", "eleven"]
    assert result[1]["text"] == "foo bar."


def test_merge_chained_shorts_loops_until_stable():
    """Multiple consecutive short segments all get merged via iterative passes."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 3.0, "text": "first segment that is long enough"},
        {"start": 3.0, "end": 3.3, "text": "a"},
        {"start": 3.3, "end": 3.6, "text": "b."},
        {"start": 3.6, "end": 3.9, "text": "c"},
        {"start": 3.9, "end": 7.0, "text": "finally another long segment here"},
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    # All shorts must be folded; no remaining ≤2-word segments.
    short_remaining = [s for s in result if len(s["text"].split()) <= 2]
    assert short_remaining == []


def test_merge_short_at_start_no_prev():
    """Short at very start (no prev) without period merges forward."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 0.3, "text": "a"},
        {"start": 0.3, "end": 4.0, "text": "normal segment"},
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    assert len(result) == 1
    assert result[0]["text"] == "a normal segment"


def test_merge_short_at_end_no_next():
    """Short at very end (no next) WITH period merges backward."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 4.0, "text": "normal segment here before tail"},
        {"start": 4.0, "end": 4.3, "text": "okay."},
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    assert len(result) == 1
    assert result[0]["text"] == "normal segment here before tail okay."


def test_merge_disabled_when_max_words_zero():
    """max_words_short=0 disables merge entirely → no-op."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 3.0, "text": "first long segment here"},
        {"start": 3.0, "end": 3.3, "text": "okay."},
    ]
    result = merge_short_segments(segments, max_words_short=0, max_gap_sec=0.5,
                                   max_words_cap=12)
    assert len(result) == 2  # nothing merged
    assert result[1]["text"] == "okay."


def test_merge_preserves_word_timestamps():
    """When word-level timestamps exist, merge concatenates them."""
    from asr.segment_utils import merge_short_segments
    prev_words = [
        {"word": "long", "start": 0.0, "end": 0.5, "probability": 0.9},
        {"word": "stretch", "start": 0.5, "end": 1.0, "probability": 0.9},
    ]
    short_words = [
        {"word": "okay.", "start": 1.0, "end": 1.3, "probability": 0.9},
    ]
    segments = [
        {"start": 0.0, "end": 1.0, "text": "long stretch", "words": prev_words},
        {"start": 1.0, "end": 1.3, "text": "okay.", "words": short_words},
    ]
    result = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                   max_words_cap=12)
    # Wait — "long stretch" is 2 words, treated as short with no period → forward merge
    # would target "okay." which is also short. After loop iteration, both fold.
    # The test design here picks max_words_short=1 to make "long stretch" non-short.
    # Re-do with cleaner setup.
    segments2 = [
        {"start": 0.0, "end": 2.0, "text": "this is a longer prev", "words": [
            {"word": "this", "start": 0.0, "end": 0.5},
            {"word": "is", "start": 0.5, "end": 0.8},
            {"word": "a", "start": 0.8, "end": 1.0},
            {"word": "longer", "start": 1.0, "end": 1.5},
            {"word": "prev", "start": 1.5, "end": 2.0},
        ]},
        {"start": 2.0, "end": 2.3, "text": "okay.", "words": [
            {"word": "okay.", "start": 2.0, "end": 2.3},
        ]},
    ]
    result2 = merge_short_segments(segments2, max_words_short=2, max_gap_sec=0.5,
                                    max_words_cap=12)
    assert len(result2) == 1
    assert "words" in result2[0]
    assert len(result2[0]["words"]) == 6
    assert result2[0]["words"][-1]["word"] == "okay."


def test_merge_idempotent():
    """Running on already-merged output produces no further changes."""
    from asr.segment_utils import merge_short_segments
    segments = [
        {"start": 0.0, "end": 4.0, "text": "a normal long segment"},
        {"start": 4.0, "end": 4.3, "text": "okay."},
    ]
    once = merge_short_segments(segments, max_words_short=2, max_gap_sec=0.5,
                                 max_words_cap=12)
    twice = merge_short_segments(once, max_words_short=2, max_gap_sec=0.5,
                                  max_words_cap=12)
    assert once == twice


def test_merge_no_input_no_crash():
    """Empty input → empty output, no exceptions."""
    from asr.segment_utils import merge_short_segments
    assert merge_short_segments([], max_words_short=2, max_gap_sec=0.5,
                                 max_words_cap=12) == []
