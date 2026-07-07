"""名詞括號：wrap helper / brackets_enabled / source-display route / stage 整合（V6 修訂②）。"""
import output_lang_glossary as olg


def _g(name_brackets="off", source_lang="en", target_lang="zh", entries=None):
    return {"id": "g-" + name_brackets, "name": "賽馬", "source_lang": source_lang,
            "target_lang": target_lang, "name_brackets": name_brackets,
            "entries": entries or [
                {"id": "e1", "source": "SUPERB GUY", "target": "巴閉佬 (K323)"},
                {"id": "e2", "source": "my wish", "target": "祝願 (J256)"},   # 2 字名
            ]}


def test_wrap_matched_names_basic_and_idempotent():
    assert olg.wrap_matched_names("巴閉佬出色", ["巴閉佬"]) == "「巴閉佬」出色"
    assert olg.wrap_matched_names("「巴閉佬」出色", ["巴閉佬"]) == "「巴閉佬」出色"


def test_wrap_two_char_name():
    assert olg.wrap_matched_names("祝願勝出", ["祝願"]) == "「祝願」勝出"


def test_wrap_longest_first():
    out = olg.wrap_matched_names("上市魅力領先", ["上市魅力", "魅力"])
    assert out == "「上市魅力」領先"


def test_brackets_enabled_matrix():
    assert not olg.brackets_enabled(_g("off"), "zh")
    assert olg.brackets_enabled(_g("zh"), "zh")
    assert olg.brackets_enabled(_g("zh"), "yue")
    assert not olg.brackets_enabled(_g("zh"), "en")
    assert olg.brackets_enabled(_g("all"), "en")
    assert olg.brackets_enabled(_g("all"), "zh")
    assert not olg.brackets_enabled({}, "zh")            # 舊檔冇欄位 → off


def test_route_source_display_only_when_all():
    g_all, g_zh = _g("all"), _g("zh")
    assert olg.route_for_output(g_all, "en", "en", "pass") == "source-display"
    assert olg.route_for_output(g_zh, "en", "en", "pass") is None      # 現狀不變
    assert olg.route_for_output(g_all, "zh", "en", "mt") == "source"   # mt 路唔受影響


def test_stage_mt_track_wraps_matched_canonical():
    """zh mt 軌：source 命中 + canonical 在文 → wrap（本段命中先括，2 字名照括）。"""
    segs = [{"start": 0, "end": 1, "text": "祝願勝出"}]
    out = olg.glossary_stage(segs, [_g("zh")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["my wish wins"])
    assert out[0]["text"] == "「祝願」勝出"


def test_stage_mt_track_no_wrap_without_candidate():
    """巧合出現嘅名（本段源文冇命中）唔括 — V6「關鍵所在」case。"""
    segs = [{"start": 0, "end": 1, "text": "祝願大家好運"}]
    out = olg.glossary_stage(segs, [_g("zh")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["good luck everyone"])
    assert out[0]["text"] == "祝願大家好運"


def test_stage_off_still_strips():
    """off 詞彙表維持現行 strip 行為（regression）。"""
    segs = [{"start": 0, "end": 1, "text": "「巴閉佬」出色"}]
    out = olg.glossary_stage(segs, [_g("off")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["superb guy is good"])
    assert out[0]["text"] == "巴閉佬出色"


def test_stage_source_display_wraps_en_track():
    """en pass 軌 + all：詞彙表原樣名（base 已由 F1 正名）wrap。"""
    segs = [{"start": 0, "end": 1, "text": "SUPERB GUY takes the lead"}]
    out = olg.glossary_stage(segs, [_g("all")], "en", "en", "pass",
                             llm_call=lambda s, u: "", use_llm=False)
    assert out[0]["text"] == "「SUPERB GUY」 takes the lead"


def test_stage_wrap_not_recorded_in_changes():
    segs = [{"start": 0, "end": 1, "text": "祝願勝出"}]
    out = olg.glossary_stage(segs, [_g("zh")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["my wish wins"])
    assert out[0]["glossary_changes"] == []    # wrap 係 cosmetic，同 strip 一致唔記錄
