"""Phase 5 — security/correctness fixes from investigation findings."""
import pytest


@pytest.fixture
def client_with_admin_db(tmp_path, monkeypatch):
    """Per-test admin user in an isolated AUTH_DB. Idempotent."""
    import app as app_module
    from auth.users import init_db, create_user

    db = str(tmp_path / "users_b1.db")
    monkeypatch.setitem(app_module.app.config, "AUTH_DB_PATH", db)
    init_db(db)
    try:
        create_user(db, "admin_p5_b1", "secret", is_admin=True)
    except ValueError:
        pass
    yield app_module.app.test_client()


def test_login_with_null_username_returns_400_not_500(client_with_admin_db):
    """Phase 5 T1.1 — JSON null in username field must not crash with NoneType.strip()."""
    client = client_with_admin_db
    r = client.post("/login", json={"username": None, "password": None})
    assert r.status_code == 400, f"got {r.status_code}: {r.data!r}"
    body = r.get_json()
    assert "error" in body


def test_login_with_null_password_only_returns_400(client_with_admin_db):
    client = client_with_admin_db
    r = client.post("/login", json={"username": "admin", "password": None})
    assert r.status_code == 400


def test_login_with_missing_keys_still_returns_400(client_with_admin_db):
    """Existing behavior preserved — missing keys (vs null values) also 400."""
    client = client_with_admin_db
    r = client.post("/login", json={})
    assert r.status_code == 400
