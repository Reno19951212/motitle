"""Phase 5 T1.4 — single-resource GET ownership for profiles + glossaries."""
import pytest


@pytest.fixture
def two_users():
    """Provision Alice + Bob in the global app's existing AUTH_DB.

    Phase 3 admin tests follow the same pattern (cf. test_admin_users.py:64):
    don't override AUTH_DB_PATH because the login_manager.user_loader
    closure captures the module-level path at boot. Cleanup deletes the
    test users so reruns are idempotent.
    """
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username, delete_user

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    for u in ("alice_b4", "bob_b4"):
        try:
            create_user(db, u, "TestPass1!", is_admin=False)
        except ValueError:
            from auth.users import update_password
            update_password(db, u, "TestPass1!")
    alice_id = get_user_by_username(db, "alice_b4")["id"]
    bob_id = get_user_by_username(db, "bob_b4")["id"]
    yield app_module, alice_id, bob_id
    for u in ("alice_b4", "bob_b4"):
        try:
            delete_user(db, u)
        except Exception:
            pass


@pytest.fixture
def fresh_profile_manager(tmp_path, monkeypatch):
    from profiles import ProfileManager
    import app as app_module
    pm = ProfileManager(tmp_path / "profiles")
    monkeypatch.setattr(app_module, "_profile_manager", pm)
    return pm


@pytest.fixture
def fresh_glossary_manager(tmp_path, monkeypatch):
    from glossary import GlossaryManager
    import app as app_module
    gm = GlossaryManager(tmp_path / "glossaries")
    monkeypatch.setattr(app_module, "_glossary_manager", gm)
    return gm


def _login(app_module, username):
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": username, "password": "TestPass1!"})
    assert r.status_code == 200, r.data
    return c


def test_get_single_profile_403_for_non_owner(two_users, fresh_profile_manager):
    app_module, alice_id, _ = two_users
    pm = fresh_profile_manager

    # Alice owns a private profile.
    private = pm.create({
        "name": "alice's private",
        "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"},
        "user_id": alice_id,
    })

    bob = _login(app_module, "bob_b4")
    r = bob.get(f"/api/profiles/{private['id']}")
    assert r.status_code == 403, f"got {r.status_code}: {r.data!r}"


def test_get_shared_profile_200_for_anyone(two_users, fresh_profile_manager):
    """Shared profile (user_id=None) is visible to all authenticated users."""
    app_module, _, _ = two_users
    pm = fresh_profile_manager

    shared = pm.create({
        "name": "shared",
        "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"},
        "user_id": None,
    })

    bob = _login(app_module, "bob_b4")
    r = bob.get(f"/api/profiles/{shared['id']}")
    assert r.status_code == 200, r.data


def test_get_own_private_profile_200_for_owner(two_users, fresh_profile_manager):
    app_module, alice_id, _ = two_users
    pm = fresh_profile_manager

    private = pm.create({
        "name": "alice's",
        "asr": {"engine": "whisper", "model": "tiny"},
        "translation": {"engine": "mock"},
        "user_id": alice_id,
    })

    alice = _login(app_module, "alice_b4")
    r = alice.get(f"/api/profiles/{private['id']}")
    assert r.status_code == 200


def test_get_single_glossary_403_for_non_owner(two_users, fresh_glossary_manager):
    app_module, alice_id, _ = two_users
    gm = fresh_glossary_manager

    private = gm.create({
        "name": "alice's terms",
        "description": "",
        "user_id": alice_id,
        "source_lang": "en",
        "target_lang": "zh",
    })

    bob = _login(app_module, "bob_b4")
    r = bob.get(f"/api/glossaries/{private['id']}")
    assert r.status_code == 403, f"got {r.status_code}: {r.data!r}"


def test_get_shared_glossary_200_for_anyone(two_users, fresh_glossary_manager):
    app_module, _, _ = two_users
    gm = fresh_glossary_manager

    shared = gm.create({
        "name": "shared terms",
        "description": "",
        "user_id": None,
        "source_lang": "en",
        "target_lang": "zh",
    })

    bob = _login(app_module, "bob_b4")
    r = bob.get(f"/api/glossaries/{shared['id']}")
    assert r.status_code == 200
