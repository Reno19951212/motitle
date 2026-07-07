# backend/tests/test_en_correction.py
"""英文詞彙糾錯 pure module（spec §4.1；dry-run V1 實證 case 全入 regression）。"""
import pytest
import en_correction as ec


def _gloss(entries):
    return [{"id": "g1", "name": "賽馬", "source_lang": "en", "target_lang": "zh",
             "entries": entries}]

G_BASIC = _gloss([
    {"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十 (K001)"},
    {"id": "e2", "source": "SUPERB GUY", "target": "巴閉佬 (K323)"},
    {"id": "e3", "source": "ONE MORE", "target": "百威多贏 (H001)"},      # 全常用詞 → demote
    {"id": "e4", "source": "NUMBERS", "target": "數字天文 (H002)"},        # 單字常用詞 → 完全排除
    {"id": "e5", "source": "ACE", "target": "大魔法師 (H003)"},            # 單字非常用 → AUTO
    {"id": "e6", "source": "ACE POWER", "target": "太陽威力 (H004)"},
])


def test_fold_collapses_case_space_punct():
    assert ec._fold("Golden  Sixty’s") == ec._fold("GOLDEN SIXTY'S")


def test_index_classification():
    idx = {e["source"]: e for e in ec.build_index(G_BASIC)}
    assert not idx["GOLDEN SIXTY"]["all_common"]
    assert not idx["SUPERB GUY"]["all_common"]           # superb 唔喺常用表（V1：必須留 AUTO）
    assert idx["ONE MORE"]["all_common"]                 # V1 FP：one+more 全常用 → demote
    assert "NUMBERS" not in idx                          # 單字常用詞完全排除（V1 FP ×2）
    assert "ACE" in idx


def test_index_skips_non_en_glossary():
    g = [{"id": "g2", "name": "x", "source_lang": "yue", "target_lang": "en",
          "entries": [{"id": "e", "source": "ABC DEF", "target": "x"}]}]
    assert ec.build_index(g) == []


def test_auto_rewrites_case_and_space():
    segs = [{"start": 0, "end": 1, "text": "golden  sixty wins the race"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "GOLDEN SIXTY wins the race"
    assert ch[0][0]["before"] == "golden  sixty"
    assert ch[0][0]["after"] == "GOLDEN SIXTY"
    assert ch[0][0]["glossary"] == ec.AUTO_TAG
    assert ch[0][0]["entry_id"] == "e1"
    assert segs[0]["text"] == "golden  sixty wins the race"   # immutable


def test_auto_exact_form_is_noop_no_record():
    segs = [{"start": 0, "end": 1, "text": "GOLDEN SIXTY wins"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "GOLDEN SIXTY wins" and ch[0] == []


def test_auto_all_common_entry_not_applied():
    # V1 FP："And one more to look at" 唔可以變 ONE MORE
    segs = [{"start": 0, "end": 1, "text": "And one more to look at."}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "And one more to look at." and ch[0] == []


def test_auto_longest_first_substring_entries():
    # V1：'Ace Power' 只由 ACE POWER 改寫；ACE 子串唔好再郁佢
    segs = [{"start": 0, "end": 1, "text": "Ace Power likes his surface"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "ACE POWER likes his surface"
    assert len(ch[0]) == 1 and ch[0][0]["after"] == "ACE POWER"


def test_auto_multiple_matches_one_cue():
    segs = [{"start": 0, "end": 1, "text": "superb guy beats Golden Sixty"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "SUPERB GUY beats GOLDEN SIXTY"
    assert len(ch[0]) == 2


# --- JUDGE tier ---

G_JUDGE = _gloss([
    {"id": "j1", "source": "SPEEDY SMARTIE", "target": "醒目仔 (H010)"},
    {"id": "j2", "source": "ONLY U", "target": "銳一 (H011)"},
    {"id": "j3", "source": "GO GO GO", "target": "上市魅力 (H012)"},   # 全常用 → judge d0
    {"id": "j4", "source": "LOVERO", "target": "開心勇駒 (H013)"},     # 單 token
])


def test_judge_candidates_gates():
    idx = ec.build_index(G_JUDGE)
    segs = [
        {"start": 0, "end": 1, "text": "speedy smarty wins"},      # d1 多token → cand
        {"start": 1, "end": 2, "text": "went over the hill"},      # over↔LOVERO d2 單token → 拒
        {"start": 2, "end": 3, "text": "His number 12 is Go Go Go"},  # 全常用 d0 → cand
        {"start": 3, "end": 4, "text": "GO GO GO leads"},          # span==source → 跳過
    ]
    cands = ec.judge_candidates(segs, idx)
    got = {(c["idx"], c["source"]) for c in cands}
    assert (0, "SPEEDY SMARTIE") in got
    assert (2, "GO GO GO") in got
    assert (3, "GO GO GO") not in got
    assert all(c["source"] != "LOVERO" for c in cands)


def test_judge_tier_majority_apply_and_reject():
    idx = ec.build_index(G_JUDGE)
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    accept = lambda s, u: '{"accept": true}'
    reject = lambda s, u: '{"accept": false}'
    out, ch = ec.judge_tier(segs, idx, accept, votes=3)
    assert out[0]["text"] == "SPEEDY SMARTIE wins"
    assert ch[0][0]["glossary"] == ec.JUDGE_TAG and ch[0][0]["before"] == "speedy smarty"
    out2, ch2 = ec.judge_tier(segs, idx, reject, votes=3)
    assert out2[0]["text"] == "speedy smarty wins" and ch2[0] == []


def test_judge_llm_error_fail_open():
    def boom(s, u):
        raise RuntimeError("llm down")
    idx = ec.build_index(G_JUDGE)
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    out, ch = ec.judge_tier(segs, idx, boom, votes=3)
    assert out[0]["text"] == "speedy smarty wins" and ch[0] == []


def test_judge_cancel_check_called():
    calls = []
    idx = ec.build_index(G_JUDGE)
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    ec.judge_tier(segs, idx, lambda s, u: '{"accept": false}', votes=1,
                  cancel_check=lambda: calls.append(1))
    assert calls


def test_orchestrator_auto_plus_judge():
    segs = [{"start": 0, "end": 1, "text": "golden sixty and speedy smarty"}]
    gl = _gloss([{"id": "e1", "source": "GOLDEN SIXTY", "target": "金 (K1)"},
                 {"id": "j1", "source": "SPEEDY SMARTIE", "target": "醒 (H1)"}])
    out, ch = ec.correct_segments_en(segs, glossaries=gl,
                                     llm_call=lambda s, u: '{"accept": true}',
                                     use_llm=True, votes=1)
    assert out[0]["text"] == "GOLDEN SIXTY and SPEEDY SMARTIE"
    tags = {c["glossary"] for c in ch[0]}
    assert tags == {ec.AUTO_TAG, ec.JUDGE_TAG}


def test_orchestrator_use_llm_false_skips_judge():
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    out, ch = ec.correct_segments_en(segs, glossaries=G_JUDGE, llm_call=None,
                                     use_llm=False)
    assert out[0]["text"] == "speedy smarty wins" and ch[0] == []


def test_orchestrator_empty_glossaries_noop():
    segs = [{"start": 0, "end": 1, "text": "hello"}]
    out, ch = ec.correct_segments_en(segs, glossaries=None)
    assert out[0]["text"] == "hello" and ch == [[]]
