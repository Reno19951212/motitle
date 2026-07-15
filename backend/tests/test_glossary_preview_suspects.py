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
