"""Tests for asr/cn_convert.py — Simplified to Traditional conversion."""

from asr.cn_convert import convert_segments_s2t


def test_basic_simplified_to_traditional_hk():
    """Real example from the user's failing horse-racing video."""
    segs = [
        {"start": 0.0, "end": 5.0, "text": "这天新10磅仔袁幸尧出席记者会"},
    ]
    out = convert_segments_s2t(segs, mode="s2hk")
    assert out[0]["text"] == "這天新10磅仔袁幸堯出席記者會"


def test_returns_new_list_does_not_mutate_input():
    """Immutability — coding-style requirement."""
    segs = [{"start": 0.0, "end": 1.0, "text": "中国"}]
    out = convert_segments_s2t(segs, mode="s2hk")
    assert segs[0]["text"] == "中国"  # original unchanged
    assert out[0]["text"] == "中國"
    assert out is not segs


def test_preserves_time_fields():
    """start/end and other fields are copied through."""
    segs = [
        {"start": 1.5, "end": 3.7, "text": "你好", "extra_field": "kept"},
    ]
    out = convert_segments_s2t(segs, mode="s2hk")
    assert out[0]["start"] == 1.5
    assert out[0]["end"] == 3.7
    assert out[0]["extra_field"] == "kept"


def test_empty_text_passes_through():
    """Empty / whitespace text is not converted (no-op)."""
    segs = [
        {"start": 0.0, "end": 1.0, "text": ""},
        {"start": 1.0, "end": 2.0, "text": "   "},
    ]
    out = convert_segments_s2t(segs, mode="s2hk")
    assert out[0]["text"] == ""
    assert out[1]["text"] == "   "


def test_word_level_timestamps_converted():
    """When segment has word_timestamps, each word.word is converted too."""
    segs = [
        {
            "start": 0.0, "end": 2.0, "text": "我爱中国",
            "words": [
                {"word": "我", "start": 0.0, "end": 0.5, "probability": 0.9},
                {"word": "爱", "start": 0.5, "end": 1.0, "probability": 0.9},
                {"word": "中国", "start": 1.0, "end": 2.0, "probability": 0.9},
            ],
        },
    ]
    out = convert_segments_s2t(segs, mode="s2hk")
    assert out[0]["text"] == "我愛中國"
    # 我 stays the same in s2hk
    assert out[0]["words"][1]["word"] == "愛"
    assert out[0]["words"][2]["word"] == "中國"
    # Timing preserved
    assert out[0]["words"][1]["start"] == 0.5
    assert out[0]["words"][1]["probability"] == 0.9


def test_s2hk_converts_common_glyphs():
    """Sanity check that s2hk performs ALL the standard s2t conversions —
    国→國, 们→們, 为→為 are all rock-solid in any s→t mode."""
    segs = [{"start": 0.0, "end": 1.0, "text": "我们为了国家"}]
    out = convert_segments_s2t(segs, mode="s2hk")
    assert out[0]["text"] == "我們為了國家"


def test_converter_caching():
    """Same mode reuses one converter — module-level cache."""
    from asr import cn_convert
    cn_convert._cc_cache.clear()
    convert_segments_s2t([{"start": 0, "end": 1, "text": "中国"}], mode="s2hk")
    convert_segments_s2t([{"start": 0, "end": 1, "text": "中国"}], mode="s2hk")
    assert "s2hk" in cn_convert._cc_cache
    assert len(cn_convert._cc_cache) == 1
