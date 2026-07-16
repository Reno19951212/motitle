"""Real-login (non-bypass) authz tests for the alias write paths — F7(b).

test_glossary_add_alias.py / test_lexicon_routes.py cover the happy paths under
R5_AUTH_BYPASS, which short-circuits EVERY ownership/admin gate — so the 403
branches in ``PUT /api/lexicons/<style>`` and
``POST /api/files/<id>/glossary-add-alias`` had zero coverage. These tests use
real sessions (@pytest.mark.real_auth, modeled on test_per_user_glossaries.py)
so the actual authz code executes:

* non-admin  PUT /api/lexicons/racing                       → 403
* non-admin  add-alias kind='lexicon'                       → 403
* non-owner  add-alias kind='source' on a SHARED glossary
  (user_id=None — editable only by admins)                  → 403

Each 403 must also be side-effect free: the lexicon file / glossary JSON is
asserted byte-identical afterwards.

Run:
    cd backend && ./venv/bin/python -m pytest tests/test_alias_authz_real_login.py -v
"""
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.real_auth


@pytest.fixture
def lexicon_file(tmp_path, monkeypatch):
    """Isolate lexicon_manager.LEXICON_DIR to a tmp dir (never touch the
    tracked config/phonetic_lexicons/racing_terms.json). Returns the file path
    so tests can assert byte-identity after a 403."""
    import lexicon_manager
    d = tmp_path / "lex"
    d.mkdir()
    path = d / "racing_terms.json"
    path.write_text(
        json.dumps({"style": "racing", "comment": "authz fixture",
                    "terms": [{"term": "殿後", "variants": ["電流位"]}]},
                   ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(lexicon_manager, "LEXICON_DIR", Path(d))
    return path


@pytest.fixture
def alice(monkeypatch, tmp_path):
    """Logged-in NON-admin user with a per-test GlossaryManager (real auth).

    Yields (client, glossary_manager, app_module, alice_user_id).
    """
    import app as app_module
    from auth.users import init_db, create_user
    from glossary import GlossaryManager

    gm = GlossaryManager(tmp_path / "glossaries")
    monkeypatch.setattr(app_module, "_glossary_manager", gm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_aliasauthz", "TestPass1!", is_admin=False)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "alice_aliasauthz", "TestPass1!")
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_aliasauthz",
                               "password": "TestPass1!"})
    assert r.status_code == 200, r.get_data(as_text=True)
    me = c.get("/api/me").get_json()
    yield c, gm, app_module, me["id"]


def _seed_owned_file(app_module, user_id):
    """Minimal output_lang registry entry OWNED by the caller, so
    @require_file_owner passes and the kind-specific authz branch is reached."""
    fid = f"aliasauthz-{uuid.uuid4().hex[:8]}"
    with app_module._registry_lock:
        app_module._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "user_id": user_id,
            "source_language": "yue", "output_languages": ["yue", "en"],
        }
    return fid


def _pop_file(app_module, fid):
    with app_module._registry_lock:
        app_module._file_registry.pop(fid, None)


def test_put_lexicon_non_admin_403_and_unchanged(alice, lexicon_file):
    """系統行話表 bulk 覆寫係管理員專屬 — 非管理員真登入 → 403，檔案零變。"""
    client, _gm, _app, _uid = alice
    raw_before = lexicon_file.read_text(encoding="utf-8")
    view_before = client.get("/api/lexicons/racing").get_json()  # 登入即可讀
    r = client.put("/api/lexicons/racing", json={
        "terms": view_before["terms"] + [{"term": "新詞測試", "variants": []}]})
    assert r.status_code == 403, r.get_data(as_text=True)
    assert lexicon_file.read_text(encoding="utf-8") == raw_before
    assert client.get("/api/lexicons/racing").get_json() == view_before


def test_add_alias_kind_lexicon_non_admin_403_and_unchanged(alice, lexicon_file):
    """add-alias kind='lexicon' 寫全局行話表 — 非管理員（就算擁有檔案）→ 403。"""
    client, _gm, app_module, uid = alice
    fid = _seed_owned_file(app_module, uid)
    raw_before = lexicon_file.read_text(encoding="utf-8")
    try:
        r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
            "kind": "lexicon", "variant": "電流位置測試", "canonical": "殿後",
            "style": "racing"})
        assert r.status_code == 403, r.get_data(as_text=True)
        assert "管理員" in (r.get_json() or {}).get("error", "")
        assert lexicon_file.read_text(encoding="utf-8") == raw_before
    finally:
        _pop_file(app_module, fid)


def test_add_alias_kind_source_shared_glossary_non_owner_403_and_unchanged(alice):
    """共享詞彙表（user_id=None）只有管理員可改 — 非管理員 add-alias
    kind='source' → 403，詞彙表 JSON 零變（source_variants 冇被 append）。"""
    client, gm, app_module, uid = alice
    shared = gm.create({
        "name": "SharedAuthz", "user_id": None,
        "source_lang": "en", "target_lang": "zh",
        "entries": [{"id": "e-s1", "source": "SPEEDY SMARTIE",
                     "target": "伶俐驫駒 (H108)"}],
    })
    gid = shared["id"]
    before = json.dumps(gm.get(gid), sort_keys=True, ensure_ascii=False)
    fid = _seed_owned_file(app_module, uid)
    try:
        r = client.post(f"/api/files/{fid}/glossary-add-alias", json={
            "kind": "source", "variant": "Speedy Smarty",
            "canonical": "SPEEDY SMARTIE",
            "glossary_id": gid, "entry_id": "e-s1"})
        assert r.status_code == 403, r.get_data(as_text=True)
        after = json.dumps(gm.get(gid), sort_keys=True, ensure_ascii=False)
        assert after == before
        entry = gm.get(gid)["entries"][0]
        assert "Speedy Smarty" not in (entry.get("source_variants") or [])
    finally:
        _pop_file(app_module, fid)
