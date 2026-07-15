# backend/tests/test_lexicon_routes.py — 依現有 route test 的 client fixture idiom
import os, sys, json, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture(autouse=True)
def _isolate_lexicon(tmp_path, monkeypatch):
    """Isolate lexicon_manager.LEXICON_DIR to a tmp dir seeded with a
    racing_terms.json fixture, so these route tests never mutate the tracked
    config/phonetic_lexicons/racing_terms.json (mirrors
    test_glossary_add_alias.py::test_add_lexicon_variant). set_lexicon
    re-serialises and would otherwise silently reformat/truncate the real
    file even with a best-effort PUT-restore."""
    import lexicon_manager
    d = tmp_path / "lex"
    d.mkdir()
    (d / "racing_terms.json").write_text(
        json.dumps({"style": "racing", "comment": "test fixture",
                    "terms": ["內欄位置", {"term": "殿後", "variants": ["電流位"]}]},
                   ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(lexicon_manager, "LEXICON_DIR", pathlib.Path(d))


def test_get_lexicon(client):
    r = client.get("/api/lexicons/racing")
    assert r.status_code == 200
    body = r.get_json()
    assert body["style"] == "racing"
    assert isinstance(body["terms"], list)
    assert all("term" in t and "variants" in t for t in body["terms"])


def test_get_unknown_lexicon_404(client):
    assert client.get("/api/lexicons/nope").status_code == 404


def test_put_lexicon_admin_bulk(client):
    # R5_AUTH_BYPASS in conftest → treated as admin
    cur = client.get("/api/lexicons/racing").get_json()["terms"]
    payload = {"terms": cur + [{"term": "後上測試", "variants": ["後尚測試"]}]}
    r = client.put("/api/lexicons/racing", json=payload)
    assert r.status_code == 200
    terms = {t["term"]: t["variants"] for t in r.get_json()["terms"]}
    assert terms.get("後上測試") == ["後尚測試"]
    # 還原（唔污染真檔）
    client.put("/api/lexicons/racing", json={"terms": cur})


def test_put_bad_body_400(client):
    assert client.put("/api/lexicons/racing", json={"terms": "oops"}).status_code == 400
