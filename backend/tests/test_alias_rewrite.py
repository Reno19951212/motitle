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
