"""Phase 3B — admin user CRUD backend."""
import pytest


@pytest.fixture
def db_path(tmp_path):
    from auth.users import init_db, create_user
    p = str(tmp_path / "u.db")
    init_db(p)
    create_user(p, "admin0", "TestPass1!", is_admin=True)
    create_user(p, "alice", "TestPass1!", is_admin=False)
    return p


def test_list_all_users_returns_all_in_id_order(db_path):
    from auth.users import list_all_users
    users = list_all_users(db_path)
    assert len(users) == 2
    assert users[0]["username"] == "admin0"
    assert users[1]["username"] == "alice"
    # Hash MUST NOT be exposed in this listing
    assert "password_hash" not in users[0]


def test_update_password_changes_hash(db_path):
    from auth.users import update_password, verify_credentials
    update_password(db_path, "alice", "NewPass1!")
    assert verify_credentials(db_path, "alice", "NewPass1!") is not None
    assert verify_credentials(db_path, "alice", "TestPass1!") is None


def test_set_admin_flips_flag(db_path):
    from auth.users import set_admin, get_user_by_username
    set_admin(db_path, "alice", True)
    assert get_user_by_username(db_path, "alice")["is_admin"] is True
    set_admin(db_path, "alice", False)
    assert get_user_by_username(db_path, "alice")["is_admin"] is False


def test_delete_user_removes_row(db_path):
    from auth.users import delete_user, get_user_by_username
    delete_user(db_path, "alice")
    assert get_user_by_username(db_path, "alice") is None


def test_count_admins(db_path):
    from auth.users import count_admins, set_admin
    assert count_admins(db_path) == 1
    set_admin(db_path, "alice", True)
    assert count_admins(db_path) == 2


@pytest.fixture
def admin_client():
    """Real logged-in admin client against the global app — same pattern as
    test_asr_handler_pipeline.py.

    Creates `admin_p3` user (idempotent for re-runs) and returns a logged-in
    test_client. Conftest's R5_AUTH_BYPASS is irrelevant here because we want
    real session for current_user.id resolution downstream of @admin_required.
    """
    import app as app_module
    from auth.users import init_db, create_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "admin_p3", "TestPass1!", is_admin=True)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "admin_p3", "TestPass1!")
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "admin_p3", "password": "TestPass1!"})
    assert r.status_code == 200
    yield c


def test_admin_users_list_requires_admin(admin_client):
    """Non-admin user gets 403 from admin route."""
    import app as app_module
    from auth.users import init_db, create_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "non_admin_p3", "TestPass1!", is_admin=False)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "non_admin_p3", "TestPass1!")
    c = app_module.app.test_client()
    c.post("/login", json={"username": "non_admin_p3", "password": "TestPass1!"})
    r = c.get("/api/admin/users")
    assert r.status_code == 403


def test_admin_users_create_returns_201(admin_client):
    r = admin_client.post("/api/admin/users",
                          json={"username": "bob_p3", "password": "TestPass1!"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["username"] == "bob_p3" and body["is_admin"] is False
    # Cleanup
    import app as app_module
    from auth.users import delete_user
    delete_user(app_module.app.config["AUTH_DB_PATH"], "bob_p3")


def test_admin_users_create_duplicate_returns_409(admin_client):
    admin_client.post("/api/admin/users",
                      json={"username": "dupe_p3", "password": "TestPass1!"})
    r = admin_client.post("/api/admin/users",
                          json={"username": "dupe_p3", "password": "TestPass1!"})
    assert r.status_code == 409
    import app as app_module
    from auth.users import delete_user
    delete_user(app_module.app.config["AUTH_DB_PATH"], "dupe_p3")


def test_admin_users_delete_self_returns_403(admin_client):
    """Admin can't delete the user they're currently logged in as."""
    import app as app_module
    from auth.users import get_user_by_username
    me = get_user_by_username(app_module.app.config["AUTH_DB_PATH"], "admin_p3")
    r = admin_client.delete(f"/api/admin/users/{me['id']}")
    assert r.status_code == 403


def test_admin_users_delete_last_admin_returns_403(admin_client):
    """Cannot delete the only remaining admin."""
    import app as app_module
    from auth.users import get_user_by_username, count_admins, list_all_users, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    # Cleanup any other admins so admin_p3 is the only one
    for u in list_all_users(db):
        if u["is_admin"] and u["username"] != "admin_p3":
            delete_user(db, u["username"])
    assert count_admins(db) == 1
    me = get_user_by_username(db, "admin_p3")
    r = admin_client.delete(f"/api/admin/users/{me['id']}")
    # Hits "last admin" guard before "self" guard, but either 403 is acceptable
    assert r.status_code == 403


def test_admin_users_reset_password_changes_hash(admin_client):
    import app as app_module
    from auth.users import create_user, verify_credentials, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rp_p3", "OldPass1!", is_admin=False)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "rp_p3", "OldPass1!")
    target = get_user_by_username(db, "rp_p3")
    r = admin_client.post(f"/api/admin/users/{target['id']}/reset-password",
                          json={"new_password": "FreshPass1!"})
    assert r.status_code == 200
    assert verify_credentials(db, "rp_p3", "FreshPass1!") is not None
    delete_user(db, "rp_p3")


def test_admin_users_toggle_admin_flips_flag(admin_client):
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "ta_p3", "TestPass1!", is_admin=False)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "ta_p3", "TestPass1!")
    target = get_user_by_username(db, "ta_p3")
    r = admin_client.post(f"/api/admin/users/{target['id']}/toggle-admin")
    assert r.status_code == 200
    assert r.get_json()["is_admin"] is True
    assert get_user_by_username(db, "ta_p3")["is_admin"] is True
    delete_user(db, "ta_p3")
