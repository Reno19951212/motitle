"""Phase 3D — per-user Glossary mirror of D1-D4 for profiles."""
import pytest


@pytest.fixture
def gm(tmp_path):
    """Per-test GlossaryManager with 3 entries: 1 shared + 1 alice + 1 bob."""
    from glossary import GlossaryManager
    gm = GlossaryManager(tmp_path)
    shared = gm.create({"name": "Shared", "user_id": None, "source_lang": "en", "target_lang": "zh"})
    a = gm.create({"name": "Alice", "user_id": 1, "source_lang": "en", "target_lang": "zh"})
    b = gm.create({"name": "Bob", "user_id": 2, "source_lang": "en", "target_lang": "zh"})
    return gm, shared["id"], a["id"], b["id"]


def test_list_visible_for_alice_returns_shared_plus_own(gm):
    manager, sid, aid, bid = gm
    visible = manager.list_visible(user_id=1, is_admin=False)
    ids = {g["id"] for g in visible}
    assert sid in ids and aid in ids
    assert bid not in ids


def test_list_visible_for_admin_returns_all(gm):
    manager, sid, aid, bid = gm
    visible = manager.list_visible(user_id=999, is_admin=True)
    ids = {g["id"] for g in visible}
    assert sid in ids and aid in ids and bid in ids


def test_can_edit_own_glossary(gm):
    manager, sid, aid, bid = gm
    assert manager.can_edit(aid, user_id=1, is_admin=False) is True


def test_cannot_edit_others_glossary(gm):
    manager, sid, aid, bid = gm
    assert manager.can_edit(bid, user_id=1, is_admin=False) is False


def test_admin_can_edit_anything(gm):
    manager, sid, aid, bid = gm
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True
    assert manager.can_edit(aid, user_id=999, is_admin=True) is True


def test_can_edit_shared_only_by_admin(gm):
    """Shared glossaries (user_id=None) editable only by admins."""
    manager, sid, aid, bid = gm
    assert manager.can_edit(sid, user_id=1, is_admin=False) is False
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True


@pytest.fixture
def alice_client(monkeypatch, tmp_path):
    """Logged-in non-admin alice with a fresh GlossaryManager."""
    import app as app_module
    from auth.users import init_db, create_user
    from glossary import GlossaryManager

    # Replace global glossary manager with a per-test instance
    gm = GlossaryManager(tmp_path)
    monkeypatch.setattr(app_module, "_glossary_manager", gm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_d5", "TestPass1!", is_admin=False)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "alice_d5", "TestPass1!")
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_d5", "password": "TestPass1!"})
    assert r.status_code == 200
    yield c, gm


def test_api_glossaries_get_filters_by_owner(alice_client):
    client, gm = alice_client
    gm.create({"name": "S", "user_id": None, "source_lang": "en", "target_lang": "zh"})
    # Alice's user_id depends on insertion order; resolve via /api/me
    me = client.get("/api/me").get_json()
    gm.create({"name": "A", "user_id": me["id"], "source_lang": "en", "target_lang": "zh"})
    gm.create({"name": "B", "user_id": me["id"] + 999, "source_lang": "en", "target_lang": "zh"})  # someone else

    r = client.get("/api/glossaries")
    assert r.status_code == 200
    # Existing response shape: {"glossaries": [...]} — preserve envelope for
    # backward-compat with frontend.
    names = {g["name"] for g in r.get_json()["glossaries"]}
    assert names == {"S", "A"}  # bob's glossary NOT visible
