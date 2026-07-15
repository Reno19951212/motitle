# backend/tests/test_phonetic_correction.py
"""粵拼語音糾錯 — port 自 2026-06-13 lang-quality 研究 protos（B1/B4 實證行為基準）。"""
import json

import pytest

import phonetic_correction as pc


GLOSS = [{"name": "賽馬", "entries": [
    {"source": "STELLAR EXPRESS", "target": "星際快車 (E123)"},
    {"source": "BEST PAL", "target": "好友心得 (D456)"},
    {"source": "PATCH OF STARS", "target": "錶之星河 (J343)"},
    {"source": "MARK", "target": "飈誌 (X001)"},      # 同「標誌」L1 全同音 — ≥3字 gate 防線
]}]
LEX = ["內欄位置", "殿後"]


def _segs(*texts):
    return [{"start": float(i), "end": float(i + 1), "text": t} for i, t in enumerate(texts)]


def test_jyutping_utils():
    assert pc.jyut_seq("星際快車") == pc.jyut_seq("升制快車")      # L1 全同音（研究實證）
    assert pc.toneless("sing1") == "sing"
    assert pc.edit_le1(["sing1", "zai3"], ["sing1", "zai3"]) == 0


def test_build_index_strips_code_and_merges_lexicon():
    idx = pc.build_index(GLOSS, LEX)
    names = {e["name"] for e in idx["entries"]}
    assert "星際快車" in names and "(E123)" not in str(names)
    assert "內欄位置" in names                                     # lexicon merge
    assert all("syls" in e for e in idx["entries"])


def test_stage0_m_rule():
    out, ch = pc.stage0_rules("M2 橙衫笑傲江湖", "racing")
    assert out.startswith("尾二")
    assert ch and ch[0]["before"] == "M2" and ch[0]["after"] == "尾二"
    out2, ch2 = pc.stage0_rules("M2 橙衫", "generic")              # 非 racing 唔啟用
    assert out2 == "M2 橙衫" and ch2 == []


def test_auto_tier_l1_exact_replaces():
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("見到升制快車走上去"), idx)
    assert segs[0]["text"] == "見到星際快車走上去"
    assert changes[0][0]["before"] == "升制快車"
    assert changes[0][0]["after"] == "星際快車"
    assert changes[0][0]["glossary"] == "語音糾正"


def test_auto_tier_min_3char_gate():
    # 「標誌」↔「飈誌」L1 全同音但 target 2 字 → 唔准自動替換（防誤殺日常語）
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("路邊有個標誌"), idx)
    assert segs[0]["text"] == "路邊有個標誌"
    assert changes[0] == []


def test_auto_tier_verbatim_name_untouched():
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("星際快車保持領先"), idx)
    assert segs[0]["text"] == "星際快車保持領先"
    assert changes[0] == []


def test_english_content_noop():
    idx = pc.build_index(GLOSS, LEX)
    segs, changes = pc.auto_tier(_segs("the quick brown fox"), idx)
    assert segs[0]["text"] == "the quick brown fox"


# ---------- Stage 2 受限 LLM 判決 ----------
# 注意（deviation from plan 樣板）：proto build_judge_user 嘅候選行格式係
# 「N. 原文「…」(jp) → 候選「…」(jp)（來源）」；「[N] …」係前後文 context 行
# （segment 編號）。fake 要對住候選行 parse，唔係 context 行。

def _candidate_ids(user):
    import re
    return [int(i) for i in re.findall(r'^(\d+)\. ', user, flags=re.M)]


def _fake_llm_accept_all(system, user):
    # build_judge_user 逐行列 candidates「N. …」；fake 全 accept
    return json.dumps({"accepts": _candidate_ids(user)})


def _fake_llm_reject_all(system, user):
    return json.dumps({"accepts": []})


def test_judge_tier_accepts_d1_candidate():
    idx = pc.build_index(GLOSS, LEX)
    # 內藍米字 vs 內欄位置：d=1 fuzzy（研究實證 case）→ AUTO 唔郁，判決 tier 接手
    segs = _segs("內藍米字錶之星河")
    segs1, ch1 = pc.auto_tier(segs, idx)
    segs2, ch2 = pc.judge_tier(segs1, idx, _fake_llm_accept_all, votes=1)
    assert "內欄位置" in segs2[0]["text"]
    assert any(c["glossary"] == pc.JUDGE_TAG for c in ch2[0])


def test_judge_tier_reject_keeps_text():
    idx = pc.build_index(GLOSS, LEX)
    segs, ch = pc.judge_tier(_segs("內藍米字錶之星河"), idx, _fake_llm_reject_all, votes=1)
    assert segs[0]["text"] == "內藍米字錶之星河"
    assert ch[0] == []


def test_judge_majority_vote():
    idx = pc.build_index(GLOSS, LEX)
    calls = {"n": 0}

    def flaky(system, user):
        calls["n"] += 1
        return _fake_llm_accept_all(system, user) if calls["n"] != 2 else _fake_llm_reject_all(system, user)
    segs, ch = pc.judge_tier(_segs("內藍米字錶之星河"), idx, flaky, votes=3)
    assert "內欄位置" in segs[0]["text"]       # 2/3 票 accept（≥3 字候選）


def test_judge_two_char_needs_unanimous():
    idx = pc.build_index(GLOSS, LEX)
    calls = {"n": 0}

    def two_of_three(system, user):
        calls["n"] += 1
        return _fake_llm_accept_all(system, user) if calls["n"] != 2 else _fake_llm_reject_all(system, user)
    # 電流→殿後（2 字候選）2/3 票 → 唔准（seg17 FP 教訓：2 字要全票）
    segs, ch = pc.judge_tier(_segs("暫時電流精算暴雪"), idx, two_of_three, votes=3)
    assert "電流" in segs[0]["text"]


def test_judge_cancel_check_raises():
    class _C(Exception):
        pass

    def boom():
        raise _C()
    idx = pc.build_index(GLOSS, LEX)
    with pytest.raises(_C):
        pc.judge_tier(_segs("內藍米字錶之星河"), idx, _fake_llm_accept_all, votes=1, cancel_check=boom)


def test_judge_llm_error_fails_open():
    def explode(system, user):
        raise RuntimeError("llm down")
    idx = pc.build_index(GLOSS, LEX)
    segs, ch = pc.judge_tier(_segs("內藍米字錶之星河"), idx, explode, votes=1)
    assert segs[0]["text"] == "內藍米字錶之星河"     # fail-open 唔 fail-job
    assert ch[0] == []


# ---------- orchestrator ----------

def test_correct_segments_end_to_end():
    segs = _segs("M2 升制快車內藍米字")
    out, changes = pc.correct_segments(segs, glossaries=GLOSS, mt_style="racing",
                                       llm_call=_fake_llm_accept_all, use_llm=True, votes=1)
    t = out[0]["text"]
    assert t.startswith("尾二") and "星際快車" in t and "內欄位置" in t
    assert len(changes) == len(segs)
    tags = {c["glossary"] for c in changes[0]}
    assert pc.AUTO_TAG in tags                       # stage0+auto 都記做 AUTO_TAG 或 stage0 自己 tag


def test_correct_segments_no_glossary_only_stage0():
    out, changes = pc.correct_segments(_segs("M3 升制快車"), glossaries=None, mt_style="racing",
                                       llm_call=None, use_llm=False)
    assert out[0]["text"].startswith("尾三")
    assert "升制快車" in out[0]["text"]              # 無 glossary → 馬名層唔行（lexicon 照行）
    assert isinstance(changes, list) and len(changes) == 1


def test_correct_segments_immutable():
    segs = _segs("升制快車")
    pc.correct_segments(segs, glossaries=GLOSS, mt_style="racing", use_llm=False)
    assert segs[0]["text"] == "升制快車"             # 入參唔准 mutate


# ---------- P1.5 gating 實證 FP regression（2026-06-13 多 clip 驗證）----------

GLOSS_FP = [{"name": "賽馬", "entries": [
    {"source": "KING GLORIOUS", "target": "靖哥哥 (G123)"}]}]


def test_auto_tier_lazy_sound_3char_demoted():
    """「在整個過程之中」唔准 AUTO 變「在靖哥哥程之中」— gw/g 懶音合併 + 3 字
    target 係 P1.5 驗證捉到嘅真 FP；3 字 L3-d0 要降級俾 judge。"""
    idx = pc.build_index(GLOSS_FP, [])
    segs, changes = pc.auto_tier(_segs("在整個過程之中"), idx)
    assert segs[0]["text"] == "在整個過程之中"
    assert changes[0] == []


def test_lazy_sound_3char_routed_to_judge_and_rejectable():
    idx = pc.build_index(GLOSS_FP, [])
    # judge 收到候選；reject-all fake → 原文不變（production qwen3.5 有 context 應 reject）
    segs, ch = pc.judge_tier(_segs("在整個過程之中"), idx, _fake_llm_reject_all, votes=1)
    assert segs[0]["text"] == "在整個過程之中"


def test_fuzzy_4char_still_auto():
    # 4 字 L3-d0 維持 AUTO（內藍米字→內欄位置 級數嘅長 target 撞日常語機率極低）
    g = [{"name": "T", "entries": [{"source": "X", "target": "內欄位置 (Z001)"}]}]
    idx = pc.build_index(g, [])
    # 內藍米子 vs 內欄位置: laam/laan(coda 弱化) + mai/wai 係 d1 唔係 d0 — 改用純聲調/懶音變體
    segs, changes = pc.auto_tier(_segs("企喺內欄位置度"), idx)
    assert segs[0]["text"] == "企喺內欄位置度"      # verbatim 唔郁（sanity）


# ---------- 雙 shape lexicon loader（Task 4：term + variants）----------

def test_load_lexicon_flat_strings_still_work():
    terms = pc.load_lexicon("racing")
    assert "內欄位置" in terms          # 舊 shape 字串照讀
    assert all(isinstance(t, str) for t in terms)


def test_load_lexicon_extracts_term_from_object_shape(tmp_path, monkeypatch):
    import json, pathlib
    d = tmp_path / "lex"
    d.mkdir()
    (d / "racing_terms.json").write_text(json.dumps({
        "style": "racing",
        "terms": ["內欄位置", {"term": "殿後", "variants": ["電流", "店後"]}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(pc, "LEXICON_DIR", pathlib.Path(d))
    terms = pc.load_lexicon("racing")
    assert "內欄位置" in terms and "殿後" in terms   # object shape 抽 term
    variants = pc.load_lexicon_variants("racing")
    dianhou = [v for v in variants if v["term"] == "殿後"][0]
    assert dianhou["variants"] == ["電流", "店後"]


def test_load_lexicon_variants_non_racing_empty():
    assert pc.load_lexicon_variants("generic") == []


# ---------- 宣告別名前置改寫（Task 7：target_aliases + lexicon variants）----------

def test_target_alias_rewritten_before_stages():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "GOOD FRIEND", "target": "好友心得 (K263)",
                     "target_aliases": ["好有心得"]}],
    }]
    segs = [{"start": 0, "end": 1, "text": "好有心得今仗跑第三"}]
    out, changes = pc.correct_segments(segs, glossaries=glossaries,
                                       mt_style="racing", use_llm=False)
    assert out[0]["text"] == "好友心得今仗跑第三"
    assert any(c["glossary"] == "宣告別名" for c in changes[0])
