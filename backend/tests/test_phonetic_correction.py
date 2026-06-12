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
