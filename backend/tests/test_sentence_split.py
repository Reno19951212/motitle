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
