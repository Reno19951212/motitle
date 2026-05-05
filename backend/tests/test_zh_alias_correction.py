"""Tests for backend.asr.zh_alias_correction (Phase 1)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# correct_zh_segment
# ---------------------------------------------------------------------------

def test_correct_zh_segment_single_alias():
    from asr.zh_alias_correction import correct_zh_segment
    out, applied = correct_zh_segment(
        "拉爾馬德里今晚比賽",
        {"拉爾馬德里": "皇家馬德里"},
    )
    assert out == "皇家馬德里今晚比賽"
    assert applied == ["拉爾馬德里"]


def test_correct_zh_segment_multiple_aliases():
    from asr.zh_alias_correction import correct_zh_segment
    out, applied = correct_zh_segment(
        "拉爾馬德里 對 巴塞隆拿",
        {"拉爾馬德里": "皇家馬德里", "巴塞隆拿": "巴塞隆納"},
    )
    assert out == "皇家馬德里 對 巴塞隆納"
    # Both aliases applied (order-insensitive set membership)
    assert set(applied) == {"拉爾馬德里", "巴塞隆拿"}


def test_correct_zh_segment_no_match():
    from asr.zh_alias_correction import correct_zh_segment
    out, applied = correct_zh_segment(
        "今晚天氣很好",
        {"拉爾馬德里": "皇家馬德里"},
    )
    assert out == "今晚天氣很好"
    assert applied == []


def test_correct_zh_segment_longest_first():
    """When two aliases overlap, the longer one must replace first.

    Without length-DESC sort, the inner short alias ("皇馬") would corrupt
    the longer alias ("皇馬球迷") before its own substitution could happen.
    """
    from asr.zh_alias_correction import correct_zh_segment
    out, applied = correct_zh_segment(
        "皇馬球迷今晚到場",
        {"皇馬": "皇家馬德里", "皇馬球迷": "皇家馬德里支持者"},
    )
    # Longer alias wins
    assert out == "皇家馬德里支持者今晚到場"
    assert "皇馬球迷" in applied


def test_correct_zh_segment_empty_text_returns_unchanged():
    from asr.zh_alias_correction import correct_zh_segment
    out, applied = correct_zh_segment("", {"x": "y"})
    assert out == ""
    assert applied == []


def test_correct_zh_segment_empty_map_returns_unchanged():
    from asr.zh_alias_correction import correct_zh_segment
    out, applied = correct_zh_segment("拉爾馬德里", {})
    assert out == "拉爾馬德里"
    assert applied == []


# ---------------------------------------------------------------------------
# build_alias_map
# ---------------------------------------------------------------------------

def test_build_alias_map_basic():
    from asr.zh_alias_correction import build_alias_map
    out = build_alias_map([
        {"en": "Real Madrid", "zh": "皇家馬德里",
         "zh_aliases": ["拉爾馬德里", "里阿馬德里"]},
    ])
    assert out == {"拉爾馬德里": "皇家馬德里", "里阿馬德里": "皇家馬德里"}


def test_build_alias_map_skips_empty_entries():
    from asr.zh_alias_correction import build_alias_map
    out = build_alias_map([
        {"en": "Real Madrid", "zh": "", "zh_aliases": ["拉爾馬德里"]},  # empty zh
        {"en": "Barcelona", "zh": "巴塞隆納"},                           # no aliases
        {"en": "Liverpool", "zh": "利物浦", "zh_aliases": []},            # empty list
    ])
    assert out == {}


def test_build_alias_map_skips_alias_equal_canonical():
    """Alias identical to canonical zh is a no-op replacement → exclude."""
    from asr.zh_alias_correction import build_alias_map
    out = build_alias_map([
        {"en": "Real Madrid", "zh": "皇家馬德里",
         "zh_aliases": ["皇家馬德里", "拉爾馬德里"]},
    ])
    assert out == {"拉爾馬德里": "皇家馬德里"}


def test_build_alias_map_skips_non_string_aliases():
    from asr.zh_alias_correction import build_alias_map
    out = build_alias_map([
        {"en": "Real Madrid", "zh": "皇家馬德里",
         "zh_aliases": [None, 123, "  ", "拉爾馬德里"]},
    ])
    assert out == {"拉爾馬德里": "皇家馬德里"}


# ---------------------------------------------------------------------------
# correct_segments
# ---------------------------------------------------------------------------

def test_correct_segments_in_place_returns_corrected():
    from asr.zh_alias_correction import correct_segments
    segs = [
        {"start": 0.0, "end": 1.0, "text": "拉爾馬德里今晚比賽"},
        {"start": 1.0, "end": 2.0, "text": "今晚天氣很好"},  # untouched
    ]
    glossary = [
        {"en": "Real Madrid", "zh": "皇家馬德里",
         "zh_aliases": ["拉爾馬德里"]},
    ]
    out = correct_segments(segs, glossary)
    assert out is segs  # in-place
    assert segs[0]["text"] == "皇家馬德里今晚比賽"
    assert segs[1]["text"] == "今晚天氣很好"


def test_correct_segments_rewrites_words_array():
    from asr.zh_alias_correction import correct_segments
    segs = [{
        "start": 0.0, "end": 1.0,
        "text": "拉爾馬德里 今晚",
        "words": [
            {"word": "拉爾馬德里", "start": 0.0, "end": 0.5, "probability": 0.9},
            {"word": "今晚",       "start": 0.5, "end": 1.0, "probability": 0.9},
        ],
    }]
    glossary = [
        {"en": "Real Madrid", "zh": "皇家馬德里",
         "zh_aliases": ["拉爾馬德里"]},
    ]
    correct_segments(segs, glossary)
    assert segs[0]["words"][0]["word"] == "皇家馬德里"
    assert segs[0]["words"][1]["word"] == "今晚"


def test_correct_segments_emits_telemetry_when_corrected():
    from asr.zh_alias_correction import correct_segments
    captured = []

    def emit(kind, msg):
        captured.append((kind, msg))

    segs = [{"start": 0, "end": 1, "text": "拉爾馬德里"}]
    glossary = [{"en": "Real Madrid", "zh": "皇家馬德里",
                 "zh_aliases": ["拉爾馬德里"]}]
    correct_segments(segs, glossary, ws_emit=emit)
    assert len(captured) == 1
    assert captured[0][0] == "zh_alias_corrected"


def test_correct_segments_no_emit_when_no_corrections():
    from asr.zh_alias_correction import correct_segments
    captured = []
    segs = [{"start": 0, "end": 1, "text": "今晚天氣很好"}]
    glossary = [{"en": "Real Madrid", "zh": "皇家馬德里",
                 "zh_aliases": ["拉爾馬德里"]}]
    correct_segments(segs, glossary, ws_emit=lambda k, m: captured.append((k, m)))
    assert captured == []


def test_correct_segments_empty_glossary_is_noop():
    from asr.zh_alias_correction import correct_segments
    segs = [{"start": 0, "end": 1, "text": "拉爾馬德里"}]
    out = correct_segments(segs, [])
    assert out[0]["text"] == "拉爾馬德里"


def test_correct_segments_emit_failure_does_not_break():
    """A broken ws_emit must not bubble exceptions out of the corrector."""
    from asr.zh_alias_correction import correct_segments

    def boom(kind, msg):
        raise RuntimeError("emit boom")

    segs = [{"start": 0, "end": 1, "text": "拉爾馬德里"}]
    glossary = [{"en": "Real Madrid", "zh": "皇家馬德里",
                 "zh_aliases": ["拉爾馬德里"]}]
    out = correct_segments(segs, glossary, ws_emit=boom)
    assert out[0]["text"] == "皇家馬德里"
