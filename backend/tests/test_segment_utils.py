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


# === α (sentence-first) tests ===


def test_alpha_preserves_sentence_boundary():
    """α should keep a complete sentence in one segment, not split mid-sentence."""
    from asr.segment_utils import split_segments
    # 17 words, fits in 88 chars. Soft cap=15 but sentence-end at word 17 within lookahead.
    text = "Yeah, it was a bit of a ricochet in the box and then the ball fell to me."
    segments = [{"start": 0.0, "end": 4.0, "text": text}]
    result = split_segments(segments, max_words=15, max_duration=40, max_chars=88,
                            min_words=4, sentence_lookahead_factor=1.5)
    # Should NOT split mid-sentence — single segment ending at "."
    assert len(result) == 1, f"expected 1 segment, got {len(result)}: {[s['text'] for s in result]}"
    assert result[0]["text"].rstrip().endswith("."), f"didn't end at sentence: {result[0]['text']!r}"


def test_alpha_clause_fallback_when_too_long():
    """When sentence won't fit char budget, α should split at clause boundary (,;:)."""
    from asr.segment_utils import split_segments
    text = ("But to be honest, when I was a bit young, I never really thought, "
            "you know, something like this would be achievable.")
    segments = [{"start": 0.0, "end": 8.0, "text": text}]
    result = split_segments(segments, max_words=15, max_duration=40, max_chars=88,
                            min_words=4, sentence_lookahead_factor=1.5)
    assert len(result) >= 2
    # At least one mid-cut should land on a comma (clause boundary)
    non_final_lines = [s["text"].rstrip() for s in result[:-1]]
    assert any(line.endswith((",", ";", ":")) for line in non_final_lines), \
        f"no clause-end in: {non_final_lines}"


def test_alpha_orphan_merged_into_neighbor():
    """A 2-word non-sentence-end fragment should merge with neighbor when merge_orphans=True."""
    from asr.segment_utils import split_segments
    # Construct a segment that would naturally produce an orphan
    # "Yeah, ok," (2 words) followed by "let's start the show now please everyone." (8 words)
    text = "Yeah, ok, let's start the show now please everyone."
    segments = [{"start": 0.0, "end": 4.0, "text": text}]
    # With min_words=4, "Yeah, ok," (2 words, ends in ',') should merge forward
    result = split_segments(segments, max_words=15, max_duration=40, max_chars=88,
                            min_words=4, sentence_lookahead_factor=1.5, merge_orphans=True)
    # No segment should have <4 words (unless ends with .!?)
    for seg in result:
        wc = len(seg["text"].split())
        ends = seg["text"].rstrip()
        assert wc >= 4 or ends[-1] in ".!?", \
            f"orphan not merged: {seg['text']!r} ({wc} words)"


def test_alpha_short_sentence_preserved():
    """A genuine 2-word sentence ending with `.` should NOT be merged."""
    from asr.segment_utils import split_segments
    # "Thank you." is a complete short sentence — should remain on its own
    text = "I am very grateful for your support today. Thank you."
    segments = [{"start": 0.0, "end": 5.0, "text": text}]
    result = split_segments(segments, max_words=15, max_duration=40, max_chars=88,
                            min_words=4, sentence_lookahead_factor=1.5, merge_orphans=True)
    # Should have at least 2 segments — "Thank you." kept separate (sentence-end)
    final_text = " ".join(s["text"] for s in result)
    assert "Thank you." in final_text


def test_alpha_disabled_when_kwargs_missing():
    """Without α kwargs, behavior must match v3.8.x legacy split."""
    from asr.segment_utils import split_segments
    text = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"
    segments = [{"start": 0.0, "end": 5.0, "text": text}]
    legacy = split_segments(segments, max_words=10, max_duration=60.0)
    explicit_no_alpha = split_segments(segments, max_words=10, max_duration=60.0, max_chars=None,
                                        min_words=None, sentence_lookahead_factor=None)
    assert legacy == explicit_no_alpha


def test_alpha_zh_text_falls_back_to_legacy():
    """ZH text (1 'word' due to no spaces) must NOT be re-routed to α path."""
    from asr.segment_utils import split_segments
    text = "你好世界這是一個測試"
    segments = [{"start": 0.0, "end": 3.0, "text": text}]
    result = split_segments(segments, max_words=15, max_duration=40, max_chars=88,
                            min_words=4, sentence_lookahead_factor=1.5)
    # ZH single-word — should pass through unchanged
    assert len(result) == 1
    assert result[0]["text"] == text


def test_alpha_no_data_loss():
    """α must preserve all words across the partition."""
    from asr.segment_utils import split_segments
    text = ("This is a test sentence with many words. Another sentence here, "
            "with a clause that continues for a while; and a final part.")
    segments = [{"start": 0.0, "end": 10.0, "text": text}]
    result = split_segments(segments, max_words=10, max_duration=40, max_chars=88,
                            min_words=4, sentence_lookahead_factor=1.5, merge_orphans=True)
    in_words = text.split()
    out_words = " ".join(s["text"] for s in result).split()
    assert in_words == out_words, f"word mismatch:\n  in:  {in_words}\n  out: {out_words}"
