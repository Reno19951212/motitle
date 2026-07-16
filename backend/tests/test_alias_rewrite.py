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


def test_en_no_cascade_rewrite_into_inserted_canonical():
    # 後 rule 嘅變體唔可以咬入前 rule 啱插入嘅 canonical（cascade 污染防線）。
    # A: 'golden 60' → 'GOLDEN SIXTY'；B: 'SIXTY' → 'SIXTY FOLD'。
    # 單 pass 改寫下，A 插入嘅 'GOLDEN SIXTY' 唔可以再被 B 咬成 'GOLDEN SIXTY FOLD'。
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十",
             "source_variants": ["golden 60"]},
            {"id": "e2", "source": "SIXTY FOLD", "target": "六十番",
             "source_variants": ["SIXTY"]},
        ],
    }]
    rules = ar.collect_en_rules(glossaries)
    out, changes = ar.apply_latin([_seg("the golden 60 wins today")], rules)
    assert out[0]["text"] == "the GOLDEN SIXTY wins today"
    # 只有一個真實宣告改動，冇 phantom 'SIXTY'→'SIXTY FOLD'
    assert len(changes[0]) == 1
    assert changes[0][0]["before"] == "golden 60"
    assert changes[0][0]["after"] == "GOLDEN SIXTY"


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
    # 同一起點：一個別名（快車手）係另一個（快車手仔）嘅前綴。長別名必須贏，
    # 否則短別名先命中 → 剩 '仔' 殘字。呢個 case 真正驗到 longest-first 排序。
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "A", "target": "手仔正名",
             "target_aliases": ["快車手仔"]},
            {"id": "e2", "source": "B", "target": "手正名",
             "target_aliases": ["快車手"]},
        ],
    }]
    rules = ar.collect_zh_rules(glossaries)
    # collect_zh_rules 必須 longest-variant-first（若 reverse/drop 排序，此斷言即爆）
    assert [r["variant"] for r in rules][:2] == ["快車手仔", "快車手"]
    out, _ = ar.apply_cjk([_seg("快車手仔今日出賽")], rules)
    assert out[0]["text"] == "手仔正名今日出賽"   # 長別名贏，冇 '仔' 殘字


def test_zh_apply_immutable():
    seg = _seg("好有心得")
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "x", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "好友心得",
                     "target_aliases": ["好有心得"]}],
    }]
    ar.apply_cjk([seg], ar.collect_zh_rules(glossaries))
    assert seg["text"] == "好有心得"


# ---------- ASCII 字界（apply_cjk）+ 宣告別名正名保護 ----------

def test_zh_ascii_alias_word_boundary_no_midword_corruption():
    # target_aliases ['ace'] 唔可以咬入 'Racecourse' → 'R愛司力course'
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "ACE POWER", "target": "愛司力 (H101)",
                     "target_aliases": ["ace"]}],
    }]
    rules = ar.collect_zh_rules(glossaries)
    out, changes = ar.apply_cjk([_seg("Sha Tin Racecourse today")], rules)
    assert out[0]["text"] == "Sha Tin Racecourse today"     # 未改
    assert changes[0] == []
    # 獨立 token 'ace' 照 fire（case-sensitive）
    out2, ch2 = ar.apply_cjk([_seg("the ace wins")], rules)
    assert out2[0]["text"] == "the 愛司力 wins"
    assert len(ch2[0]) == 1


def test_zh_protected_canonical_not_destroyed():
    # 宣告 '好友心'（entry A 別名）唔可以摧毀 entry B 嘅正名 '好友心得'
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "A", "target": "好友心水 (H101)",
             "target_aliases": ["好友心"]},
            {"id": "e2", "source": "B", "target": "好友心得 (K263)"},
        ],
    }]
    rules = ar.collect_zh_rules(glossaries)
    protected = ar.collect_protected_zh(glossaries)
    out, changes = ar.apply_cjk([_seg("好友心得今仗跑第三")], rules,
                                protected=protected)
    assert out[0]["text"] == "好友心得今仗跑第三"           # 正名唔郁
    assert changes[0] == []
    # 唔喺 protected 正名內嘅獨立出現照 fire
    out2, _ = ar.apply_cjk([_seg("好友心領放")], rules, protected=protected)
    assert out2[0]["text"] == "好友心水領放"


def test_zh_protection_embedded_own_canonical_exemption():
    # 內嵌名 exemption：protected 名（心得）完全落喺 match span（好有心得）之內、
    # 而且係本 rule canonical（好友心得）嘅 substring → 照 fire
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "GF", "target": "好友心得 (K263)",
             "target_aliases": ["好有心得"]},
            {"id": "e2", "source": "XD", "target": "心得"},
        ],
    }]
    rules = ar.collect_zh_rules(glossaries)
    protected = ar.collect_protected_zh(glossaries)
    out, changes = ar.apply_cjk([_seg("好有心得今仗跑第三")], rules,
                                protected=protected)
    assert out[0]["text"] == "好友心得今仗跑第三"
    assert len(changes[0]) == 1


def test_zh_lexicon_terms_protected():
    # lexicon term（行話正名）都要受保護：別名唔可以咬入行話正名
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "A", "target": "四早三",
                     "target_aliases": ["晨操快"]}],
    }]
    rules = ar.collect_zh_rules(glossaries)
    protected = ar.collect_protected_zh(glossaries, lexicon_terms=["晨操快圈"])
    out, changes = ar.apply_cjk([_seg("今朝晨操快圈表現好")], rules,
                                protected=protected)
    assert out[0]["text"] == "今朝晨操快圈表現好"           # 行話正名唔郁
    assert changes[0] == []


def test_en_protected_canonical_not_mangled():
    # source_variant 'GOLDEN'（entry A）唔可以咬入 entry B 正名 'GOLDEN SIXTY'
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "GOLDEN AGE", "target": "黃金歲月",
             "source_variants": ["GOLDEN"]},
            {"id": "e2", "source": "GOLDEN SIXTY", "target": "金鎗六十"},
        ],
    }]
    rules = ar.collect_en_rules(glossaries)
    protected = ar.collect_protected_en(glossaries)
    out, changes = ar.apply_latin([_seg("GOLDEN SIXTY wins the race")], rules,
                                  protected=protected)
    assert out[0]["text"] == "GOLDEN SIXTY wins the race"   # 正名唔郁
    assert changes[0] == []
    # 大小寫變體嘅正名出現一樣受保護（build_name_pattern IGNORECASE）
    out2, ch2 = ar.apply_latin([_seg("golden sixty runs")], rules,
                               protected=protected)
    assert out2[0]["text"] == "golden sixty runs"
    assert ch2[0] == []
    # 獨立出現照 fire
    out3, _ = ar.apply_latin([_seg("GOLDEN runs well")], rules,
                             protected=protected)
    assert out3[0]["text"] == "GOLDEN AGE runs well"
