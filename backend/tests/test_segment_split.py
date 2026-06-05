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
