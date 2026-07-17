# backend/tests/test_glossary_preview_suspects.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# 用一個 helper：直接測 suspect 生成純函數，避免 seed 成個 registry。


def test_en_suspect_generation():
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "MALPENSA", "target": "賢知友您"}],
    }]
    texts = ["It's Malpenza with a wide draw"]
    starts = [1.0]
    sus = app._suspects_for_track("en", texts, starts, glossaries, "en", "racing")
    assert any(s["canonical"] == "MALPENSA" and s["span"].lower().startswith("malpen")
               and s["side"] == "source" and s["entry_id"] == "e1" for s in sus)


def test_zh_suspect_lexicon_side():
    import app
    # 殿後 係 lexicon supplement term；聽錯 "電流位置" 應成 suspect side=lexicon
    texts = ["佢一直電流位置"]
    starts = [1.0]
    sus = app._suspects_for_track("yue", texts, starts, [], "yue", "racing")
    # 只驗 helper 唔炒 + 若有命中 side/source_index 正確
    for s in sus:
        assert s["side"] in ("target", "lexicon")
        if s["source_index"] == "supplement":
            assert s["side"] == "lexicon"


def test_non_yue_non_en_content_no_suspects():
    import app
    assert app._suspects_for_track("ja", ["x"], [1.0], [], "ja", "generic") == []


# ---- 已宣告別名喺掃描嘅反饋（閉環）----

def test_declared_en_source_variant_surfaced():
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)",
                     "source_variants": ["Speedy Smarty"]}],
    }]
    texts = ["Speedy Smarty leads the field"]
    dec = app._declared_for_track("en", texts, [1.0], glossaries, "en", "racing")
    assert any(d["kind"] == "declared" and d["span"] == "Speedy Smarty"
               and d["canonical"] == "SPEEDY SMARTIE" and d["side"] == "source"
               and d["entry_id"] == "e1" for d in dec)


def test_declared_zh_target_alias_surfaced():
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "好友心得 (K263)",
                     "target_aliases": ["好有心得"]}],
    }]
    texts = ["好有心得今仗跑第三"]
    dec = app._declared_for_track("yue", texts, [1.0], glossaries, "yue", "racing")
    assert any(d["kind"] == "declared" and d["span"] == "好有心得"
               and d["canonical"] == "好友心得" and d["side"] == "target"
               and d["entry_id"] == "e1" for d in dec)


def test_declared_scan_covers_beyond_400_cues():
    """declared 掃描係 cheap regex pass — 唔可以被 fuzzy 掃描嘅 400 cue 上限封頂。

    >400 段檔案，別名喺第 441 段（index 440）都必須搵到（否則用戶加咗別名
    掃描見唔到 → 「冇反應」）。
    """
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)",
                     "source_variants": ["Speedy Smarty"]}],
    }]
    texts = ["filler line"] * 450
    texts[440] = "Speedy Smarty leads the field"
    starts = [float(i) for i in range(450)]
    dec = app._declared_for_track("en", texts, starts, glossaries, "en", "racing")
    assert any(d["kind"] == "declared" and d["idx"] == 440
               and d["span"] == "Speedy Smarty" and d["start"] == 440.0
               for d in dec)


def test_declared_none_when_no_variant():
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "伶俐驫駒"}],
    }]
    assert app._declared_for_track("en", ["Speedy Smarty leads"], [1.0],
                                   glossaries, "en", "racing") == []


def test_declared_blocked_surfaced_with_flag():
    """被正名保護壓制嘅宣告別名要 surface（blocked:true），唔可以靜默消失。"""
    import app
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "A", "target": "馬會盃",
             "target_aliases": ["馬會盃賽"]},
            {"id": "e2", "source": "B", "target": "盃賽"},
        ],
    }]
    dec = app._declared_for_track("yue", ["今日馬會盃賽開跑"], [1.0],
                                  glossaries, "yue", "racing")
    blocked = [d for d in dec if d.get("blocked")]
    assert blocked, "blocked 宣告別名必須出現喺 declared feedback"
    assert blocked[0]["span"] == "馬會盃賽"
    assert blocked[0]["blocked_by"] == "盃賽"
    assert blocked[0]["kind"] == "declared"
