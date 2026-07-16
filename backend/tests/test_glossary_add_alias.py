"""Route tests for POST /api/files/<id>/glossary-add-alias (Plan B Task 3).

One-click writes a "疑似聽錯" into a permanent alias via three paths:
  * kind='source'  → entry.source_variants
  * kind='target'  → entry.target_aliases (entry_id 無就靠 canonical 反查)
  * kind='lexicon' → 系統行話表 variants（管理員）

Fixture idiom (recorded in deviations):
  * No `conftest_helpers` module exists, so `_mk_file` inline-seeds a minimal
    output_lang registry entry the caller owns (mirrors the review-route
    tests' inline seeding). The autouse `_isolate_app_data` fixture clears the
    registry after each test, so no explicit teardown is needed.
  * The glossary is created through the real CRUD API — conftest isolates
    `_glossary_manager` to a tmp dir, so nothing leaks into config/glossaries/.
  * The lexicon test isolates `lexicon_manager.LEXICON_DIR` to a tmp dir so the
    tracked config/phonetic_lexicons/racing_terms.json is never mutated (the
    plan's version wrote+restored the real file; isolation is byte-safe).

Run:
    cd backend && ./venv/bin/python -m pytest tests/test_glossary_add_alias.py -v
"""
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _mk_glossary(client):
    r = client.post("/api/glossaries", json={"name": "aliastest",
                    "source_lang": "en", "target_lang": "zh"})
    gid = r.get_json()["id"]
    g = client.post(f"/api/glossaries/{gid}/entries",
                    json={"source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)"}).get_json()
    eid = g["entries"][-1]["id"]
    return gid, eid


def _mk_file(client):
    """Inline-seed a minimal output_lang registry entry the caller owns.

    We only need a file_id the caller owns (@require_file_owner short-circuits
    under R5_AUTH_BYPASS). The autouse _isolate_app_data fixture clears the
    registry after the test, so no explicit teardown is needed.
    """
    import app as _app
    fid = f"aliastest-{uuid.uuid4().hex[:8]}"
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "user_id": 1,
            "source_language": "yue", "output_languages": ["yue", "en"],
        }
    return fid


def test_add_source_variant(client):
    gid, eid = _mk_glossary(client)
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "source", "variant": "Speedy Smarty", "canonical": "SPEEDY SMARTIE",
        "glossary_id": gid, "entry_id": eid})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["field"] == "source_variants"
    g = client.get(f"/api/glossaries/{gid}").get_json()
    e = [x for x in g["entries"] if x["id"] == eid][0]
    assert "Speedy Smarty" in e["source_variants"]


def test_add_target_alias_by_canonical_lookup(client):
    gid, eid = _mk_glossary(client)
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "target", "variant": "伶俐飄駒", "canonical": "伶俐驫駒",
        "glossary_id": gid})   # 無 entry_id → 靠 canonical 反查
    assert r.status_code == 200, r.get_data(as_text=True)
    g = client.get(f"/api/glossaries/{gid}").get_json()
    e = [x for x in g["entries"] if x["id"] == eid][0]
    assert "伶俐飄駒" in e["target_aliases"]


def test_add_lexicon_variant(client, tmp_path, monkeypatch):
    import lexicon_manager
    d = tmp_path / "lex"
    d.mkdir()
    (d / "racing_terms.json").write_text(
        json.dumps({"style": "racing", "comment": "x",
                    "terms": [{"term": "殿後", "variants": []}]}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(lexicon_manager, "LEXICON_DIR", Path(d))
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "lexicon", "variant": "電流位測試", "canonical": "殿後", "style": "racing"})
    assert r.status_code == 200, r.get_data(as_text=True)
    terms = {t["term"]: t["variants"]
             for t in client.get("/api/lexicons/racing").get_json()["terms"]}
    assert "電流位測試" in terms.get("殿後", [])


def test_bad_kind_400(client):
    fid = _mk_file(client)
    assert client.post(f"/api/files/{fid}/glossary-add-alias",
                       json={"kind": "bogus", "variant": "x", "canonical": "y"}).status_code == 400


def test_add_target_alias_loose_parenthetical_reverse_lookup(client):
    """Target 尾帶非馬匹編號括號（strip_horse_id 唔剝）都要反查得中 —
    phonetic build_index 用鬆規則剝任何尾括號，canonical 冇括號。"""
    r = client.post("/api/glossaries", json={"name": "loosetest",
                    "source_lang": "en", "target_lang": "zh"})
    gid = r.get_json()["id"]
    g = client.post(f"/api/glossaries/{gid}/entries",
                    json={"source": "NEW STAR", "target": "新星 (新馬)"}).get_json()
    eid = g["entries"][-1]["id"]
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "target", "variant": "辛星測試", "canonical": "新星",
        "glossary_id": gid})   # 無 entry_id → 反查；嚴格 strip 唔中 → 鬆規則
    assert r.status_code == 200, r.get_data(as_text=True)
    g = client.get(f"/api/glossaries/{gid}").get_json()
    e = [x for x in g["entries"] if x["id"] == eid][0]
    assert "辛星測試" in e["target_aliases"]


def test_add_alias_response_includes_warnings(client):
    """成功 response 帶 add-only `warnings`（§4.2b 安全網）。"""
    gid, eid = _mk_glossary(client)
    fid = _mk_file(client)
    # 乾淨別名 → warnings == []
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "source", "variant": "Speedy Smartee", "canonical": "SPEEDY SMARTIE",
        "glossary_id": gid, "entry_id": eid})
    assert r.status_code == 200
    assert r.get_json()["warnings"] == []
    # 常用詞別名 → 照加（非阻斷）但 warnings 有提示
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "source", "variant": "one more", "canonical": "SPEEDY SMARTIE",
        "glossary_id": gid, "entry_id": eid})
    assert r.status_code == 200
    body = r.get_json()
    assert any("常用英文詞" in w for w in body["warnings"])
    g = client.get(f"/api/glossaries/{gid}").get_json()
    e = [x for x in g["entries"] if x["id"] == eid][0]
    assert "one more" in e["source_variants"]     # 照儲存 — 唔阻止


def test_add_lexicon_response_includes_warnings(client, tmp_path, monkeypatch):
    import lexicon_manager
    d = tmp_path / "lex2"
    d.mkdir()
    (d / "racing_terms.json").write_text(
        json.dumps({"style": "racing", "comment": "x",
                    "terms": [{"term": "殿後", "variants": []}]}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(lexicon_manager, "LEXICON_DIR", Path(d))
    fid = _mk_file(client)
    r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
        "kind": "lexicon", "variant": "電流", "canonical": "殿後", "style": "racing"})
    assert r.status_code == 200
    assert any("太短" in w for w in r.get_json()["warnings"])
