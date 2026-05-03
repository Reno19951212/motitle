"""Tests for sentence_split fine-segmentation module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_module_exports_public_api():
    """Module exposes transcribe_fine_seg, word_gap_split, FineSegmentationError."""
    from asr import sentence_split
    assert callable(sentence_split.transcribe_fine_seg)
    assert callable(sentence_split.word_gap_split)
    assert issubclass(sentence_split.FineSegmentationError, Exception)


def _word(text: str, start: float, end: float, prob: float = 1.0) -> dict:
    return {"word": text, "start": start, "end": end, "probability": prob}


def _seg(start: float, end: float, words: list[dict]) -> dict:
    text = " ".join(w["word"] for w in words).strip()
    return {"start": start, "end": end, "text": text, "words": words}


def test_word_gap_split_no_split_when_under_max_dur():
    """3.5s segment with max_dur=4.0 → not split."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 3.5, [_word("a", 0, 0.5), _word("b", 1, 1.5),
                        _word("c", 2, 2.5), _word("d", 3, 3.5)])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.1, min_dur=1.5)
    assert len(out) == 1
    assert out[0]["start"] == 0 and out[0]["end"] == 3.5


def test_word_gap_split_splits_at_largest_gap():
    """5s segment with one big 0.8s gap mid-way → split into 2 parts."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 5.0, [
        _word("one", 0.0, 0.4), _word("two", 0.5, 0.9), _word("three", 1.0, 1.7),
        _word("four", 2.5, 3.0), _word("five", 3.1, 3.5), _word("six", 3.6, 5.0),
    ])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.5, min_dur=1.5)
    assert len(out) == 2
    assert out[0]["text"].endswith("three")
    assert out[1]["text"].startswith("four")


def test_word_gap_split_too_few_words_keeps_seg():
    """Segment with < 4 words is never split, even if duration > max_dur."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 6.0, [_word("a", 0, 1), _word("b", 2, 3), _word("c", 4, 5)])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.1, min_dur=1.5)
    assert len(out) == 1


def test_word_gap_split_missing_words_keeps_seg():
    """Segment with empty words[] is never split."""
    from asr.sentence_split import word_gap_split
    seg = {"start": 0, "end": 6, "text": "a b c d e f", "words": []}
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.1, min_dur=1.5)
    assert len(out) == 1


def test_word_gap_split_respects_min_dur():
    """Big gap exists but split would violate min_dur → no split."""
    from asr.sentence_split import word_gap_split
    # 5s segment; only gap candidate is at index 1, but left side would be 0.5s < min_dur=1.5
    seg = _seg(0, 5.0, [
        _word("a", 0.0, 0.5),
        _word("b", 1.0, 1.5),  # gap 0.5 to next
        _word("c", 2.0, 2.5),
        _word("d", 3.0, 3.5),
        _word("e", 4.0, 5.0),
    ])
    # gap_thresh=0.4 would otherwise split at any gap; min_dur excludes index 1, 4
    # Index 2 left=1.5s OK, right=2.5s OK → can split there if gap qualifies
    # But all gaps are 0.5 → split at first acceptable index
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.4, min_dur=1.5)
    # split must respect min_dur — both halves should be ≥1.5s
    for piece in out:
        assert (piece["end"] - piece["start"]) >= 1.5, f"piece too short: {piece}"


def test_word_gap_split_safety_override_for_super_long():
    """No gap ≥ threshold but duration > safety_max_dur → force split anyway."""
    from asr.sentence_split import word_gap_split
    # 11s segment with all gaps 0.05s (below threshold 0.20)
    words = [_word(str(i), i * 1.05, i * 1.05 + 1.0) for i in range(11)]
    seg = _seg(0, 11.55, words)
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.20, min_dur=1.5,
                         safety_max_dur=9.0)
    assert len(out) >= 2, f"safety override should force split, got {len(out)}"


def test_word_gap_split_keeps_under_safety_max_dur():
    """No gap ≥ threshold and duration ≤ safety_max_dur → kept as-is."""
    from asr.sentence_split import word_gap_split
    # 6s segment, all gaps 0.05s
    words = [_word(str(i), i * 1.05, i * 1.05 + 1.0) for i in range(6)]
    seg = _seg(0, 6.3, words)
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.20, min_dur=1.5,
                         safety_max_dur=9.0)
    assert len(out) == 1, f"should keep, got {len(out)}"


def test_word_gap_split_recursive_chains():
    """12s segment with two big gaps → split into 3 pieces."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 12.0, [
        _word("a", 0.0, 0.4), _word("b", 0.5, 0.9), _word("c", 1.0, 1.5),
        # big gap 1.0s
        _word("d", 2.5, 2.9), _word("e", 3.0, 3.5), _word("f", 3.6, 4.0),
        _word("g", 4.1, 4.5), _word("h", 4.6, 5.0),
        # big gap 1.5s
        _word("i", 6.5, 7.0), _word("j", 7.1, 7.5), _word("k", 7.6, 8.0),
        _word("l", 8.1, 12.0),
    ])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.5, min_dur=1.5)
    assert len(out) == 3, f"expected 3 chunks, got {len(out)}"


def test_word_gap_split_preserves_text_content():
    """After split, joined children's text equals parent's text (no word loss)."""
    from asr.sentence_split import word_gap_split
    seg = _seg(0, 6.0, [_word("the", 0, 0.3), _word("quick", 0.4, 0.8),
                        _word("brown", 0.9, 1.4), _word("fox", 1.5, 2.0),
                        # gap
                        _word("jumps", 3.5, 4.0), _word("over", 4.1, 4.5),
                        _word("the", 4.6, 5.0), _word("dog", 5.1, 6.0)])
    out = word_gap_split([seg], max_dur=4.0, gap_thresh=0.5, min_dur=1.5)
    parent_text = seg["text"]
    children_text = " ".join(s["text"] for s in out)
    assert parent_text == children_text, f"parent={parent_text!r} vs children={children_text!r}"


def test_subcap_chunks_no_subcap_needed():
    """Spans all ≤ max_s → output identical to input."""
    from asr.sentence_split import _subcap_chunks
    SR = 16000
    spans = [(0, 10 * SR), (15 * SR, 25 * SR)]
    assert _subcap_chunks(spans, max_s=25) == spans


def test_subcap_chunks_splits_long_span():
    """60s span with max_s=25 → 3 sub-chunks (25 + 25 + 10)."""
    from asr.sentence_split import _subcap_chunks
    SR = 16000
    out = _subcap_chunks([(0, 60 * SR)], max_s=25)
    assert len(out) == 3
    assert out[0] == (0, 25 * SR)
    assert out[1] == (25 * SR, 50 * SR)
    assert out[2] == (50 * SR, 60 * SR)


def test_subcap_chunks_empty_input():
    from asr.sentence_split import _subcap_chunks
    assert _subcap_chunks([], max_s=25) == []


def test_subcap_chunks_exact_boundary():
    """Span exactly = max_s → single chunk."""
    from asr.sentence_split import _subcap_chunks
    SR = 16000
    out = _subcap_chunks([(0, 25 * SR)], max_s=25)
    assert len(out) == 1
    assert out[0] == (0, 25 * SR)
