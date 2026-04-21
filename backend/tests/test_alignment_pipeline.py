"""Tests for alignment pipeline — LLM-marker-based redistribution.

Phase 6 Step 2: Uses gpt-oss-120b [N] markers to align a sentence-level
Chinese translation back to the original ASR segment boundaries, so merged
translations keep correct time alignment.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ────────────────────────────── parse_markers ──────────────────────────────


def test_parse_markers_extracts_positions_and_clean_text():
    """Markers [N] are stripped and their positions recorded."""
    from translation.alignment_pipeline import parse_markers
    annotated = "阿拉巴與盧迪加[3]傷病纏身[6]，令皇馬後防告急。"
    positions, clean = parse_markers(annotated)
    # Markers are at char positions corresponding to their insertion points
    assert clean == "阿拉巴與盧迪加傷病纏身，令皇馬後防告急。"
    assert positions == {3: 7, 6: 11}  # map from marker N to char position in clean text


def test_parse_markers_returns_empty_when_no_markers():
    from translation.alignment_pipeline import parse_markers
    positions, clean = parse_markers("沒有標記嘅中文字幕")
    assert positions == {}
    assert clean == "沒有標記嘅中文字幕"


def test_parse_markers_ignores_non_numeric_brackets():
    """Brackets containing non-digits (e.g., actual text like [備註]) are left alone."""
    from translation.alignment_pipeline import parse_markers
    annotated = "阿拉巴[3]受傷[備註]詳情[6]"
    positions, clean = parse_markers(annotated)
    assert "[備註]" in clean  # non-numeric brackets preserved
    assert 3 in positions and 6 in positions


def test_parse_markers_handles_multi_digit_indices():
    from translation.alignment_pipeline import parse_markers
    annotated = "短句[10]另一段[25]結尾"
    positions, clean = parse_markers(annotated)
    assert clean == "短句另一段結尾"
    assert positions == {10: 2, 25: 5}


# ─────────────────────────── build_anchor_prompt ───────────────────────────


def test_build_anchor_prompt_lists_boundaries():
    """The prompt must contain the specific boundary indices we ask for."""
    from translation.alignment_pipeline import build_anchor_prompt
    en_words = ["Alaba", "and", "Rudiger", "are", "hurt"]
    boundaries = [2]  # after word index 2
    prompt = build_anchor_prompt(en_words, boundaries, glossary=[])
    assert "[2]" in prompt
    assert "Alaba" in prompt and "Rudiger" in prompt
    # Word count instruction so LLM knows how many markers to produce
    assert "1" in prompt  # one marker expected


def test_build_anchor_prompt_injects_glossary():
    from translation.alignment_pipeline import build_anchor_prompt
    glossary = [{"en": "Alaba", "zh": "阿拉巴"}]
    prompt = build_anchor_prompt(["Alaba", "left"], boundaries=[0], glossary=glossary)
    assert "阿拉巴" in prompt
    assert "Alaba" in prompt


# ─────────────────── time_proportion_fallback ───────────────────


def test_time_proportion_fallback_splits_by_duration():
    """Fallback splits ZH text proportional to each segment's duration."""
    from translation.alignment_pipeline import time_proportion_fallback
    # 2 segments: [0-2s] + [2-6s] → 2s + 4s → 33%/67%
    # 30-char ZH → split at char 10 (33% * 30)
    zh = "一二三四五六七八九十十一十二十三十四十五十六十七十八十九二十二一二二二三二四二五二六二七二八二九三十"
    segments = [
        {"start": 0.0, "end": 2.0},
        {"start": 2.0, "end": 6.0},
    ]
    merged = {
        "seg_indices": [0, 1],
        "start": 0.0,
        "end": 6.0,
    }
    positions = time_proportion_fallback(merged, zh, segments)
    assert len(positions) == 1  # one split for two segments
    # Position should be ~33% of len(zh)
    assert abs(positions[0] - round(len(zh) * 2 / 6)) <= 5  # ±5 for punct snap tolerance


def test_time_proportion_fallback_snaps_to_punctuation():
    """Split position snaps to nearest Chinese punctuation within a window."""
    from translation.alignment_pipeline import time_proportion_fallback
    zh = "阿拉巴盧迪加受傷。米利淘亦遭重創"  # punct at index 9
    segments = [
        {"start": 0.0, "end": 2.5},
        {"start": 2.5, "end": 5.0},
    ]
    merged = {"seg_indices": [0, 1], "start": 0.0, "end": 5.0}
    positions = time_proportion_fallback(merged, zh, segments)
    # Raw 50% would land at index 8; snapped to 9 (after '。')
    assert positions == [9]


def test_time_proportion_fallback_three_segments():
    """Splits into N-1 positions for N segments."""
    from translation.alignment_pipeline import time_proportion_fallback
    zh = "一二三四五六七八九十一二三四五六七八九十"
    segments = [
        {"start": 0.0, "end": 1.0},
        {"start": 1.0, "end": 2.0},
        {"start": 2.0, "end": 3.0},
    ]
    merged = {"seg_indices": [0, 1, 2], "start": 0.0, "end": 3.0}
    positions = time_proportion_fallback(merged, zh, segments)
    assert len(positions) == 2  # N-1 = 2 splits
    assert positions[0] < positions[1]


# ────────────────────────── split_at_positions ──────────────────────────


def test_split_at_positions_basic():
    from translation.alignment_pipeline import split_at_positions
    parts = split_at_positions("abcdefghij", [3, 6])
    assert parts == ["abc", "def", "ghij"]


def test_split_at_positions_empty_positions():
    from translation.alignment_pipeline import split_at_positions
    assert split_at_positions("abcde", []) == ["abcde"]


def test_split_at_positions_handles_out_of_range():
    """Positions beyond string length should clamp to string end."""
    from translation.alignment_pipeline import split_at_positions
    parts = split_at_positions("abc", [5])
    assert parts == ["abc", ""]


# ──────────────────── translate_with_alignment (integration) ────────────────────


def test_translate_with_alignment_empty_input():
    from translation.alignment_pipeline import translate_with_alignment
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    assert translate_with_alignment(engine, []) == []


def test_translate_with_alignment_single_segment_sentences_use_normal_flow():
    """If every sentence fits in one segment, no marker alignment is attempted."""
    from translation.alignment_pipeline import translate_with_alignment
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({})
    # Two separate sentences, each self-contained
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello world."},
        {"start": 3.0, "end": 4.0, "text": "Goodbye everyone."},
    ]
    result = translate_with_alignment(engine, segments)
    assert len(result) == 2
    # Mock engine returns something non-empty
    assert result[0]["zh_text"]
    assert result[1]["zh_text"]


def test_translate_with_alignment_falls_back_when_markers_wrong(monkeypatch):
    """When LLM returns wrong marker count, fall back to time-proportion split."""
    from translation.alignment_pipeline import translate_with_alignment
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    # Mock the marker call to return ZH with no markers → triggers fallback
    # And the normal translate to return something
    def fake_call(system, user, temp):
        return "阿拉巴與盧迪加受傷。米利淘亦遭重創"  # no markers

    monkeypatch.setattr(engine, "_call_ollama", fake_call)

    segments = [
        {"start": 0.0, "end": 2.0, "text": "Alaba and Rudiger are"},
        {"start": 2.0, "end": 4.0, "text": "injured. Militao also suffered."},
    ]
    result = translate_with_alignment(engine, segments)
    # Both segments should get non-empty zh_text from the fallback split
    assert len(result) == 2
    assert result[0]["zh_text"]
    assert result[1]["zh_text"]
    # Verify no content overlap (split happened)
    assert result[0]["zh_text"] != result[1]["zh_text"]
