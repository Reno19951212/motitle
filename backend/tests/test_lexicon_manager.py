import os, sys, json, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lexicon_manager as lm


def _seed(tmp_path, monkeypatch, terms):
    d = tmp_path / "lex"
    d.mkdir()
    (d / "racing_terms.json").write_text(
        json.dumps({"style": "racing", "comment": "x", "terms": terms}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(lm, "LEXICON_DIR", pathlib.Path(d))


def test_get_lexicon_normalizes_both_shapes(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["內欄位置", {"term": "殿後", "variants": ["電流位"]}])
    view = lm.get_lexicon("racing")
    terms = {t["term"]: t["variants"] for t in view["terms"]}
    assert terms["內欄位置"] == []           # bare string → variants []
    assert terms["殿後"] == ["電流位"]


def test_add_term_variant_dedupes_and_upgrades_shape(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["殿後"])   # bare string
    lm.add_term_variant("racing", "殿後", "電流位")
    lm.add_term_variant("racing", "殿後", "電流位")  # dup → no-op
    view = lm.get_lexicon("racing")
    dh = [t for t in view["terms"] if t["term"] == "殿後"][0]
    assert dh["variants"] == ["電流位"]
    # 原始檔真係變咗 object shape，load_lexicon 仍抽到 term
    import phonetic_correction as pc
    monkeypatch.setattr(pc, "LEXICON_DIR", lm.LEXICON_DIR)
    assert "殿後" in pc.load_lexicon("racing")
    assert lm.get_lexicon("racing")  # 檔案合法


def test_add_term_variant_creates_missing_term(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["內欄位置"])
    lm.add_term_variant("racing", "後上", "後尚")
    view = lm.get_lexicon("racing")
    assert any(t["term"] == "後上" and t["variants"] == ["後尚"] for t in view["terms"])


def test_set_lexicon_empty_variants_writes_bare_string(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [{"term": "殿後", "variants": ["x"]}])
    lm.set_lexicon("racing", [{"term": "殿後", "variants": []},
                              {"term": "尾二", "variants": ["尾指位置"]}])
    raw = json.loads((lm.LEXICON_DIR / "racing_terms.json").read_text(encoding="utf-8"))
    assert "殿後" in raw["terms"]                       # bare string（空 variants）
    assert {"term": "尾二", "variants": ["尾指位置"]} in raw["terms"]


def test_bad_style_returns_none(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, ["x"])
    assert lm.get_lexicon("../etc") is None
    assert lm.get_lexicon("nonexistent") is None
