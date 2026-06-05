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
    # Reset in-memory rate limiter so accumulated login attempts from earlier
    # tests in the same run do not cause this login to be rejected with 429.
    app_module._limiter.reset()
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


def test_admin_users_reset_password_weak_returns_400_not_500(admin_client):
    # Regression: a weak password made update_password raise ValueError which was
    # uncaught -> raw 500. It must now be a clean 400 with a JSON error message.
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rpw_p3", "OldPass1!", is_admin=False)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "rpw_p3", "OldPass1!")
    target = get_user_by_username(db, "rpw_p3")
    try:
        r = admin_client.post(f"/api/admin/users/{target['id']}/reset-password",
                              json={"new_password": "123"})
        assert r.status_code == 400
        assert r.get_json().get("error")  # a human-facing message, not an empty body
    finally:
        delete_user(db, "rpw_p3")


def test_admin_users_create_weak_password_returns_400_not_409(admin_client):
    # Weak password on create must be 400 (validation), not 409 (collision).
    from auth.users import delete_user, get_user_by_username
    import app as app_module
    db = app_module.app.config["AUTH_DB_PATH"]
    r = admin_client.post("/api/admin/users",
                          json={"username": "cw_weak_p3", "password": "123"})
    assert r.status_code == 400
    assert r.get_json().get("error")
    # ensure no user leaked
    if get_user_by_username(db, "cw_weak_p3"):
        delete_user(db, "cw_weak_p3")


def test_new_user_has_empty_remarks(db_path):
    from auth.users import list_all_users
    users = list_all_users(db_path)
    assert users[0]["remarks"] == ""


def test_update_remarks_persists(db_path):
    from auth.users import update_remarks, get_user_by_username, list_all_users
    uid = get_user_by_username(db_path, "alice")["id"]
    update_remarks(db_path, uid, "夜更校對員")
    assert get_user_by_username(db_path, "alice")["remarks"] == "夜更校對員"
    listed = {u["username"]: u for u in list_all_users(db_path)}
    assert listed["alice"]["remarks"] == "夜更校對員"


def test_update_remarks_trims_and_caps_length(db_path):
    from auth.users import update_remarks, get_user_by_username
    uid = get_user_by_username(db_path, "alice")["id"]
    update_remarks(db_path, uid, "  hi  ")
    assert get_user_by_username(db_path, "alice")["remarks"] == "hi"
    update_remarks(db_path, uid, "x" * 500)  # exactly at the cap — must not raise
    assert get_user_by_username(db_path, "alice")["remarks"] == "x" * 500
    with pytest.raises(ValueError):
        update_remarks(db_path, uid, "x" * 501)


def test_update_remarks_unknown_user_raises(db_path):
    from auth.users import update_remarks
    with pytest.raises(ValueError):
        update_remarks(db_path, 999999, "x")


def test_init_db_migrates_existing_db_idempotently(tmp_path):
    # An older DB created before the remarks column must gain it on init_db re-run.
    import sqlite3
    from auth.users import init_db, create_user, get_user_by_username
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, "
        "password_hash TEXT NOT NULL, created_at REAL NOT NULL, is_admin INTEGER DEFAULT 0, "
        "settings_json TEXT DEFAULT '{}')"
    )
    conn.commit(); conn.close()
    init_db(p)            # should ALTER TABLE ADD COLUMN remarks
    init_db(p)            # idempotent — must not raise
    create_user(p, "old_user", "TestPass1!")
    assert get_user_by_username(p, "old_user")["remarks"] == ""


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


def test_admin_update_remarks_happy_path(admin_client):
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rm_p3", "TestPass1!", is_admin=False)
    except ValueError:
        pass
    target = get_user_by_username(db, "rm_p3")
    r = admin_client.patch(f"/api/admin/users/{target['id']}/remarks",
                           json={"remarks": "外判翻譯員"})
    assert r.status_code == 200
    assert r.get_json()["remarks"] == "外判翻譯員"
    assert get_user_by_username(db, "rm_p3")["remarks"] == "外判翻譯員"
    delete_user(db, "rm_p3")


def test_admin_update_remarks_too_long_returns_400(admin_client):
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rml_p3", "TestPass1!", is_admin=False)
    except ValueError:
        pass
    target = get_user_by_username(db, "rml_p3")
    r = admin_client.patch(f"/api/admin/users/{target['id']}/remarks",
                           json={"remarks": "x" * 501})
    assert r.status_code == 400
    assert r.get_json().get("error")
    delete_user(db, "rml_p3")


def test_admin_update_remarks_missing_user_returns_404(admin_client):
    r = admin_client.patch("/api/admin/users/999999/remarks", json={"remarks": "x"})
    assert r.status_code == 404


def test_update_remarks_requires_admin():
    # Non-admin gets 403.
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "na_rm_p3", "TestPass1!", is_admin=False)
    except ValueError:
        pass
    # Reset rate-limiter storage so accumulated login attempts from earlier
    # tests in the same run do not block this login with a 429.
    app_module._limiter.reset()
    c = app_module.app.test_client()
    c.post("/login", json={"username": "na_rm_p3", "password": "TestPass1!"})
    target = get_user_by_username(db, "na_rm_p3")
    r = c.patch(f"/api/admin/users/{target['id']}/remarks", json={"remarks": "x"})
    assert r.status_code == 403
    delete_user(db, "na_rm_p3")


def test_api_me_includes_remarks(admin_client):
    # admin_p3 sees its own remarks via /api/me after an admin sets them.
    import app as app_module
    from auth.users import get_user_by_username, update_remarks
    db = app_module.app.config["AUTH_DB_PATH"]
    me = get_user_by_username(db, "admin_p3")
    update_remarks(db, me["id"], "系統主帳戶")
    r = admin_client.get("/api/me")
    assert r.status_code == 200
    assert r.get_json().get("remarks") == "系統主帳戶"
