import json

import segment_split as ss


def test_normalize_strips_space_punct_and_lowercases_latin():
    assert ss.normalize("Hello,  World!") == "helloworld"


def test_normalize_cjk_drops_punct_keeps_chars():
    assert ss.normalize("你好，世界。") == ss.normalize("你好世界")


def test_normalize_trad_simp_equal_via_t2s():
    # 「實」(trad) vs 「实」(simp) normalize to the same simplified form
    assert ss.normalize("實時") == ss.normalize("实时")


def test_merge_text_joins_with_single_space_trimmed():
    assert ss.merge_text("你好", "世界") == "你好 世界"
    assert ss.merge_text("  a ", " b  ") == "a b"
    assert ss.merge_text("", "x") == "x"


def test_compute_split_ratio_basic():
    assert ss.compute_split_ratio("12345", "1234567890") == 0.5


def test_compute_split_ratio_clamped_low_and_high():
    assert ss.compute_split_ratio("x", "x" * 100) == 0.15      # 0.01 -> clamp 0.15
    assert ss.compute_split_ratio("x" * 99, "x" * 100) == 0.85  # 0.99 -> clamp 0.85


def test_compute_split_ratio_empty_full_is_half():
    assert ss.compute_split_ratio("", "") == 0.5


def test_mechanical_parts_duplicates_each_language():
    out = ss.mechanical_parts({"yue": "你好世界", "en": "hello world"})
    assert out == {"yue": ("你好世界", "你好世界"), "en": ("hello world", "hello world")}


def test_mechanical_parts_handles_empty():
    assert ss.mechanical_parts({"yue": ""}) == {"yue": ("", "")}
