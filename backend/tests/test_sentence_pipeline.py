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
