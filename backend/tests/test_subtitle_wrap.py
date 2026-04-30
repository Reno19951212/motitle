from subtitle_wrap import wrap_zh, WrapResult


def test_empty_string_returns_no_lines():
    result = wrap_zh("")
    assert isinstance(result, WrapResult)
    assert result.lines == []
    assert result.hard_cut is False


def test_whitespace_only_returns_no_lines():
    result = wrap_zh("   \n\t  ")
    assert result.lines == []
    assert result.hard_cut is False


def test_short_text_within_cap_returns_one_line():
    result = wrap_zh("你好世界", cap=23)
    assert result.lines == ["你好世界"]
    assert result.hard_cut is False


def test_text_within_cap_plus_tolerance_returns_one_line():
    # 24 chars, cap=23, tail_tolerance=3 → should fit in single line
    text = "雖然皇馬中場堆滿了技術精湛且體能充沛的優秀球員。"  # 24 char
    assert len(text) == 24
    result = wrap_zh(text, cap=23, tail_tolerance=3)
    assert result.lines == [text]
    assert result.hard_cut is False
