"""Phase 3D — per-user Profile override."""
import pytest


@pytest.fixture
def pm(tmp_path):
    """Per-test ProfileManager with 3 entries: 1 shared + 1 alice + 1 bob."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    shared = pm.create({"name": "Shared", "asr": {"engine": "whisper"},
                        "translation": {"engine": "mock"}, "user_id": None})
    a = pm.create({"name": "Alice", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 1})
    b = pm.create({"name": "Bob", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 2})
    return pm, shared["id"], a["id"], b["id"]


def test_list_visible_for_alice_returns_shared_plus_own(pm):
    manager, sid, aid, bid = pm
    visible = manager.list_visible(user_id=1, is_admin=False)
    ids = {p["id"] for p in visible}
    assert sid in ids and aid in ids
    assert bid not in ids


def test_list_visible_for_admin_returns_all(pm):
    manager, sid, aid, bid = pm
    visible = manager.list_visible(user_id=999, is_admin=True)
    ids = {p["id"] for p in visible}
    assert sid in ids and aid in ids and bid in ids


def test_can_edit_own_profile(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(aid, user_id=1, is_admin=False) is True


def test_cannot_edit_others_profile(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(bid, user_id=1, is_admin=False) is False


def test_admin_can_edit_anything(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True
    assert manager.can_edit(aid, user_id=999, is_admin=True) is True


def test_can_edit_shared_only_by_admin(pm):
    """Shared profiles (user_id=None) editable only by admins."""
    manager, sid, aid, bid = pm
    assert manager.can_edit(sid, user_id=1, is_admin=False) is False
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True


@pytest.fixture
def alice_client(monkeypatch, tmp_path):
    """Logged-in non-admin alice with a fresh ProfileManager."""
    import app as app_module
    from auth.users import init_db, create_user
    from profiles import ProfileManager

    # Replace global profile manager with a per-test instance
    pm = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", pm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_d3", "secret", is_admin=False)
    except ValueError:
        pass
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_d3", "password": "secret"})
    assert r.status_code == 200
    yield c, pm


def test_api_profiles_get_filters_by_owner(alice_client):
    client, pm = alice_client
    pm.create({"name": "S", "asr": {"engine": "whisper"},
               "translation": {"engine": "mock"}, "user_id": None})
    # Alice's user_id depends on insertion order; resolve via /api/me
    me = client.get("/api/me").get_json()
    pm.create({"name": "A", "asr": {"engine": "whisper"},
               "translation": {"engine": "mock"}, "user_id": me["id"]})
    pm.create({"name": "B", "asr": {"engine": "whisper"},
               "translation": {"engine": "mock"}, "user_id": me["id"] + 999})  # someone else

    r = client.get("/api/profiles")
    assert r.status_code == 200
    # Existing response shape: {"profiles": [...]} — Phase 1 envelope kept for
    # backward-compat with frontend (index.html line ~4232 reads data.profiles).
    names = {p["name"] for p in r.get_json()["profiles"]}
    assert names == {"S", "A"}  # bob's profile NOT visible
