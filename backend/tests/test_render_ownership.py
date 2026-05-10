"""Phase 5 T2.5 — render GET/download/DELETE require file owner."""
import pytest


@pytest.fixture
def two_users_one_render(monkeypatch):
    """Alice owns file + render; bob exists but doesn't own them."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username, delete_user

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    for u in ("alice_c5", "bob_c5"):
        try:
            create_user(db, u, "pw", is_admin=False)
        except ValueError:
            pass
    alice_id = get_user_by_username(db, "alice_c5")["id"]

    fid = "file-c5"
    rid = "render-c5"
    with app_module._registry_lock:
        app_module._file_registry[fid] = {
            "id": fid, "user_id": alice_id, "stored_name": "x.mp4",
            "file_path": "/tmp/c5_fake.mp4", "status": "done",
            "original_name": "x.mp4", "size": 0, "uploaded_at": 0.0,
            "segments": [], "text": "", "translations": [],
        }
    app_module._render_jobs[rid] = {
        "render_id": rid, "file_id": fid, "format": "mp4",
        "status": "done", "output_path": "/tmp/c5_out.mp4",
        "output_filename": "x_subtitled.mp4",
    }
    yield app_module, fid, rid
    with app_module._registry_lock:
        app_module._file_registry.pop(fid, None)
    app_module._render_jobs.pop(rid, None)
    for u in ("alice_c5", "bob_c5"):
        try:
            delete_user(db, u)
        except Exception:
            pass


def _login(app_module, username):
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": username, "password": "pw"})
    assert r.status_code == 200, r.data
    return c


def test_get_render_403_for_non_owner(two_users_one_render):
    app_module, _fid, rid = two_users_one_render
    bob = _login(app_module, "bob_c5")
    r = bob.get(f"/api/renders/{rid}")
    assert r.status_code == 403, f"got {r.status_code}: {r.data!r}"


def test_download_render_403_for_non_owner(two_users_one_render):
    app_module, _fid, rid = two_users_one_render
    bob = _login(app_module, "bob_c5")
    r = bob.get(f"/api/renders/{rid}/download")
    assert r.status_code == 403


def test_delete_render_403_for_non_owner(two_users_one_render):
    app_module, _fid, rid = two_users_one_render
    bob = _login(app_module, "bob_c5")
    r = bob.delete(f"/api/renders/{rid}")
    assert r.status_code == 403


def test_get_render_200_for_owner(two_users_one_render):
    app_module, _fid, rid = two_users_one_render
    alice = _login(app_module, "alice_c5")
    r = alice.get(f"/api/renders/{rid}")
    assert r.status_code == 200


def test_get_unknown_render_404(monkeypatch):
    """Non-existent render id still returns 404 (not 403) for any user."""
    import app as app_module
    from auth.users import init_db, create_user, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "carol_c5", "pw", is_admin=False)
    except ValueError:
        pass
    try:
        c = _login(app_module, "carol_c5")
        r = c.get("/api/renders/does-not-exist")
        assert r.status_code == 404
    finally:
        try:
            delete_user(db, "carol_c5")
        except Exception:
            pass
