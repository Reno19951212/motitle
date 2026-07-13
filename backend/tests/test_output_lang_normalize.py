"""確定性正規化：單位 pass（spec §5.1）。"""
import output_lang_normalize as oln


def test_gongchi_to_mi():
    segs = [{"start": 0, "end": 1, "text": "二千公尺又是另一程。"}]
    out, ch = oln.normalize_units(segs)
    assert out[0]["text"] == "二千米又是另一程。"
    assert ch[0][0]["before"] == "公尺" and ch[0][0]["after"] == "米"
    assert ch[0][0]["glossary"] == oln.UNIT_TAG
    assert segs[0]["text"] == "二千公尺又是另一程。"   # immutable


def test_number_prefixed_gongchi():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "1600公尺賽事"}])
    assert out[0]["text"] == "1600米賽事"


def test_gongli_variant_normalized():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "跑了兩公裏"}])
    assert out[0]["text"] == "跑了兩公里"


def test_gongli_kept():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "距離三公里"}])
    assert out[0]["text"] == "距離三公里" and ch[0] == []


def test_no_unit_unchanged():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "他表現出色。"}])
    assert out[0]["text"] == "他表現出色。" and ch[0] == []


def test_multiple_segments():
    out, ch = oln.normalize_units([
        {"start": 0, "end": 1, "text": "二千公尺"},
        {"start": 1, "end": 2, "text": "冇單位"}])
    assert out[0]["text"] == "二千米" and out[1]["text"] == "冇單位"
    assert len(ch) == 2 and ch[1] == []


def test_load_jockeys_has_luke():
    js = oln.load_jockeys()
    luke = next((j for j in js if j["canonical"] == "霍宏聲"), None)
    assert luke and "Luke" in luke["variants"] and "盧克" in luke["variants"]


def test_load_jockeys_missing_file_failopen(monkeypatch):
    monkeypatch.setattr(oln, "_JOCKEYS_PATH", "/nonexistent/x.json")
    assert oln.load_jockeys() == []


_ROSTER = [{"canonical": "霍宏聲", "variants": ["Luke Ferraris", "Luke", "盧克"]}]


def test_name_english_kept_replaced():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Luke 已策騎他"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲 已策騎他"
    assert ch[0][0]["after"] == "霍宏聲" and ch[0][0]["glossary"] == oln.NAME_TAG


def test_name_translit_error_replaced():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "盧克表現出色"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲表現出色"


def test_name_longest_first():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Luke Ferraris 上馬"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲 上馬"
    assert len(ch[0]) == 1 and ch[0][0]["before"] == "Luke Ferraris"


def test_name_word_boundary_no_partial():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "It was lukewarm today"}], _ROSTER)
    assert out[0]["text"] == "It was lukewarm today" and ch[0] == []


def test_name_already_canonical_noop():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "霍宏聲 策騎"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲 策騎" and ch[0] == []


def test_name_immutable():
    segs = [{"start": 0, "end": 1, "text": "Luke 上馬"}]
    oln.normalize_names(segs, _ROSTER)
    assert segs[0]["text"] == "Luke 上馬"


def test_name_empty_roster_noop():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Luke 上馬"}], [])
    assert out[0]["text"] == "Luke 上馬" and ch[0] == []


def test_stage_zh_racing_both():
    segs = [{"start": 0, "end": 1, "text": "Luke 跑二千公尺"}]
    out, ch = oln.normalize_stage(segs, "zh", "racing")
    assert "霍宏聲" in out[0]["text"] and "二千米" in out[0]["text"]
    tags = {c["glossary"] for c in ch[0]}
    assert oln.UNIT_TAG in tags and oln.NAME_TAG in tags


def test_stage_zh_generic_units_only():
    segs = [{"start": 0, "end": 1, "text": "Luke 跑二千公尺"}]
    out, ch = oln.normalize_stage(segs, "zh", "generic")
    assert "二千米" in out[0]["text"]           # 單位有做
    assert "Luke" in out[0]["text"]             # 騎師唔郁（非賽馬）


def test_stage_en_track_noop():
    segs = [{"start": 0, "end": 1, "text": "Luke ran 2000m"}]
    out, ch = oln.normalize_stage(segs, "en", "racing")
    assert out[0]["text"] == "Luke ran 2000m" and ch[0] == []


def test_stage_lang_stamp_absent_until_caller():
    # normalize_stage 唔加 lang（由 caller 蓋，同 glossary_stage 一致）
    out, ch = oln.normalize_stage([{"start": 0, "end": 1, "text": "二千公尺"}], "zh", "racing")
    assert "lang" not in ch[0][0]


# --- review fixes 2026-07-09 ---

def test_roster_no_bare_ambiguous_names():
    """review MEDIUM：roster 唔可以有裸名/裸姓（Vincent/Purton 會誤中普通文本）。"""
    js = oln.load_jockeys()
    variants = {v for j in js for v in j["variants"]}
    # 全英文 variant 至少兩個 token（全名），除咗有據可循嘅裸 Luke（賽馬 gate 保護）
    for v in variants:
        if v.isascii() and v != "Luke":
            assert " " in v, f"裸英文名有誤中風險: {v}"
    assert "Vincent" not in variants and "Purton" not in variants


def test_names_no_falsepositive_on_common_text():
    """review MEDIUM 回歸：Vincent van Gogh 唔會變 何澤堯。"""
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Vincent van Gogh 畫作"}])
    assert out[0]["text"] == "Vincent van Gogh 畫作" and ch[0] == []
