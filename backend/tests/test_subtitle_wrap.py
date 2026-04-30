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


def test_break_at_hard_punctuation():
    # 31 char text. ！ at index 9, 。 at index 17.
    # Tiebreaker (score += i) → 。at 17 wins (117 > 109).
    text = "歡迎收聽體育新聞！政府宣布新措施。今晚紅魔曼聯主場迎戰兵工廠！"
    assert len(text) == 31
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    assert result.lines[0] == "歡迎收聽體育新聞！政府宣布新措施。"  # locks tiebreaker behavior
    assert result.hard_cut is False


def test_break_at_soft_punctuation_when_no_hard():
    text = "據接近球會的消息，球隊士氣跌至歷史新低，球員表現失準"  # 26 char
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    # 26 > 23+3=26? Actually equal, single line
    # Make it longer
    text = "據接近球會的消息，球隊士氣跌至歷史新低，球員表現失準令教練震怒"  # 30 char
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    assert len(result.lines) >= 2
    assert result.lines[0].endswith("，")
    assert result.hard_cut is False


def test_hard_cut_when_no_natural_break():
    # 30-char string with no punctuation in first 23 chars
    text = "當沙比阿朗素於某年某月遭皇家馬德里解僱據悉接近教練團隊"  # 27 char, no punct
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    # First line forced to 23 chars, hard_cut flagged
    assert len(result.lines[0]) <= 23
    assert result.hard_cut is True


def test_three_line_wrap():
    text = (
        "在後防方面，"  # 6
        + "大衛·阿拉巴與安東尼奧·盧迪加持續受傷，"  # 20
        + "令皇馬兵力嚴重告急。"  # 10
    )
    assert len(text) == 36
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    assert len(result.lines) == 3
    assert result.lines[0] == "在後防方面，"
    assert result.lines[1] == "大衛·阿拉巴與安東尼奧·盧迪加持續受傷，"
    assert result.lines[2] == "令皇馬兵力嚴重告急。"


def test_tail_tolerance_absorbs_trailing_period():
    text = "雖然皇馬中場堆滿了技術精湛且體能充沛的優秀球員。"  # 24 char
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    # 24 ≤ 23+3 → single line
    assert result.lines == [text]


def test_max_lines_overflow_appended_to_last_line():
    # Construct text that needs 4+ lines if no overflow handling
    text = "甲乙丙，丁戊己，庚辛壬，癸子丑，寅卯辰巳，午未申酉戌亥，A1B2C3D4E5"  # over 4 segments
    result = wrap_zh(text, cap=10, max_lines=2, tail_tolerance=0)
    assert len(result.lines) == 2
    # All content present (last line absorbs leftover)
    assert "".join(result.lines).replace(" ", "") == text.replace(" ", "")


def test_look_ahead_extends_to_punctuation_just_past_cap():
    # Punctuation at position 24 (cap+1), text length 33
    text = "theathletic.com 將讓您身臨其境，直擊足球世界核心。"
    assert len(text) == 33
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    # Look-ahead picks position 24 「，」, line 1 = 24 char ending in 「，」
    assert result.lines[0].endswith("，")
    assert len(result.lines[0]) == 24
    assert result.hard_cut is False


def test_look_ahead_does_not_extend_beyond_cap_plus_tolerance():
    # Punctuation only at position 30 (cap+7), should hard-cut at 23
    text = "abcdefghijklmnopqrstuvwxyzABCD,efghi"  # 36 char, comma at 30
    assert len(text) == 36
    result = wrap_zh(text, cap=23, max_lines=3, tail_tolerance=3)
    # Look-ahead range is [cap+1, cap+tol] = [24, 26]; comma at 30 is out of range
    assert len(result.lines[0]) == 23
    assert result.hard_cut is True


def test_preset_netflix_originals():
    from subtitle_wrap import resolve_wrap_config, PRESETS
    cfg = resolve_wrap_config({"subtitle_standard": "netflix_originals"})
    assert cfg["line_cap"] == 16
    assert cfg["max_lines"] == 2
    assert cfg["tail_tolerance"] == 2


def test_preset_netflix_general():
    from subtitle_wrap import resolve_wrap_config
    cfg = resolve_wrap_config({"subtitle_standard": "netflix_general"})
    assert cfg["line_cap"] == 23
    assert cfg["max_lines"] == 2
    assert cfg["tail_tolerance"] == 3


def test_preset_broadcast():
    from subtitle_wrap import resolve_wrap_config
    cfg = resolve_wrap_config({"subtitle_standard": "broadcast"})
    assert cfg["line_cap"] == 28
    assert cfg["max_lines"] == 3
    assert cfg["tail_tolerance"] == 3


def test_explicit_line_wrap_overrides_preset():
    from subtitle_wrap import resolve_wrap_config
    cfg = resolve_wrap_config({
        "subtitle_standard": "netflix_originals",
        "line_wrap": {"line_cap": 30, "max_lines": 1, "tail_tolerance": 0}
    })
    # Explicit overrides preset
    assert cfg["line_cap"] == 30
    assert cfg["max_lines"] == 1
    assert cfg["tail_tolerance"] == 0


def test_no_config_returns_broadcast_default():
    from subtitle_wrap import resolve_wrap_config
    cfg = resolve_wrap_config({})
    assert cfg["line_cap"] == 28
    assert cfg["max_lines"] == 3
    assert cfg["tail_tolerance"] == 3


def test_disabled_returns_passthrough_config():
    from subtitle_wrap import resolve_wrap_config
    cfg = resolve_wrap_config({"line_wrap": {"enabled": False}})
    assert cfg["enabled"] is False
