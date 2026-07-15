# backend/tests/test_alias_rewrite.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import alias_rewrite as ar


def _seg(t):
    return {"start": 0.0, "end": 1.0, "text": t}


def test_en_declared_variant_rewrites_to_canonical():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)",
                     "source_variants": ["Speedy Smarty", "Speedy Smart"]}],
    }]
    rules = ar.collect_en_rules(glossaries)
    out, changes = ar.apply_latin([_seg("Speedy Smarty leads the field")], rules)
    assert out[0]["text"] == "SPEEDY SMARTIE leads the field"
    assert changes[0][0]["after"] == "SPEEDY SMARTIE"
    assert changes[0][0]["before"] == "Speedy Smarty"
    assert changes[0][0]["glossary"] == "宣告別名"
    assert changes[0][0]["entry_id"] == "e1"


def test_en_variant_word_boundary_no_midword_corruption():
    # 'ACE' 宣告變體唔可以咬入 'RACE'
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "ACE POWER", "target": "愛司力",
                     "source_variants": ["ACE"]}],
    }]
    rules = ar.collect_en_rules(glossaries)
    out, changes = ar.apply_latin([_seg("THE RACE IS ON")], rules)
    assert out[0]["text"] == "THE RACE IS ON"      # 未改
    assert changes[0] == []


def test_en_variant_below_fold_len_gate_skipped():
    # fold 長度 < 3 嘅英文別名唔生成 rule（Tom 類短名靠 canonical 長度，唔怕；
    # 但 2 字元別名如 'AB' 太危險，排除）
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "AB CENTRAL", "target": "中央",
                     "source_variants": ["AB"]}],
    }]
    rules = ar.collect_en_rules(glossaries)
    assert all(r["variant"] != "AB" for r in rules)


def test_en_non_en_glossary_skipped():
    glossaries = [{
        "source_lang": "yue", "target_lang": "en", "name": "x", "id": "g1",
        "entries": [{"id": "e1", "source": "好友心得", "target": "GOOD FRIEND",
                     "source_variants": ["GOOD FREND"]}],
    }]
    assert ar.collect_en_rules(glossaries) == []


def test_apply_latin_immutable():
    seg = _seg("Speedy Smarty")
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "x",
                     "source_variants": ["Speedy Smarty"]}],
    }]
    ar.apply_latin([seg], ar.collect_en_rules(glossaries))
    assert seg["text"] == "Speedy Smarty"   # 入參未被 mutate


def test_zh_declared_alias_rewrites_to_canonical():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "GOOD FRIEND", "target": "好友心得 (K263)",
                     "target_aliases": ["好有心得"]}],
    }]
    rules = ar.collect_zh_rules(glossaries)
    out, changes = ar.apply_cjk([_seg("好有心得今仗跑第三")], rules)
    assert out[0]["text"] == "好友心得今仗跑第三"          # canonical 去咗 horse id
    assert changes[0][0]["after"] == "好友心得"
    assert changes[0][0]["before"] == "好有心得"
    assert changes[0][0]["glossary"] == "宣告別名"


def test_zh_alias_below_len_gate_skipped():
    # 2 字別名（電流/尾指/標誌/段處）一律跳過 — 實證 FP 元兇
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "殿後",
                     "target_aliases": ["電流"]}],
    }]
    rules = ar.collect_zh_rules(glossaries)
    assert all(r["variant"] != "電流" for r in rules)
    out, changes = ar.apply_cjk([_seg("呢條電流好強")], rules)
    assert out[0]["text"] == "呢條電流好強"                # 未改（防 FP）
    assert changes[0] == []


def test_zh_lexicon_variants_rewrite():
    lex = [{"term": "殿後", "variants": ["店後嘅位置"]}]  # ≥3 字合法別名
    rules = ar.collect_zh_rules([], lexicon_variants=lex)
    out, changes = ar.apply_cjk([_seg("佢一直店後嘅位置")], rules)
    assert out[0]["text"] == "佢一直殿後"
    assert changes[0][0]["glossary"] == "宣告別名"


def test_zh_longest_first_no_partial_overlap():
    # 長別名優先，短別名唔可以喺長別名內部再命中
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "A", "target": "星際快車",
             "target_aliases": ["升制快車"]},
            {"id": "e2", "source": "B", "target": "快車手",
             "target_aliases": ["快車手仔"]},
        ],
    }]
    rules = ar.collect_zh_rules(glossaries)
    out, _ = ar.apply_cjk([_seg("升制快車今日出賽")], rules)
    assert out[0]["text"] == "星際快車今日出賽"


def test_zh_apply_immutable():
    seg = _seg("好有心得")
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "x", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "好友心得",
                     "target_aliases": ["好有心得"]}],
    }]
    ar.apply_cjk([seg], ar.collect_zh_rules(glossaries))
    assert seg["text"] == "好有心得"
