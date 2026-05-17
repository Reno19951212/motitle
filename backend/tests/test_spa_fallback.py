"""v4.0 A3 T3 — Flask serves React SPA index.html for / and SPA routes."""
import pytest


@pytest.fixture
def client_with_admin():
    """Logged-in admin client against the global app — mirrors the pattern in
    test_mt_handler_pipeline.py / test_asr_handler_pipeline.py.

    Uses a unique username so it can coexist with other test fixtures sharing
    the global app's AUTH_DB_PATH without colliding on UNIQUE(username).
    """
    import app as app_module
    from auth.users import init_db, create_user, update_password

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_a3_spa", "TestPass1!", is_admin=True)
    except ValueError:
        update_password(db_path, "alice_a3_spa", "TestPass1!")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_a3_spa", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield c


@pytest.fixture
def client():
    """Public (unauthenticated) test client."""
    import app as app_module
    with app_module.app.test_client() as c:
        yield c


def test_root_serves_react_index(tmp_path, monkeypatch, client_with_admin):
    """When frontend/dist/index.html exists, GET / serves it."""
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist").mkdir(parents=True)
    (fake_frontend / "dist" / "index.html").write_text("<html>React</html>")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client_with_admin.get("/")
    assert response.status_code == 200
    assert b"React" in response.data


def test_unmatched_spa_route_serves_index(tmp_path, monkeypatch, client_with_admin):
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist").mkdir(parents=True)
    (fake_frontend / "dist" / "index.html").write_text("<html>SPA</html>")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    for route in [
        "/pipelines",
        "/asr_profiles",
        "/mt_profiles",
        "/glossaries",
        "/admin",
        "/proofread/abc123",
    ]:
        response = client_with_admin.get(route)
        assert response.status_code == 200, route
        assert b"SPA" in response.data, route


def test_login_route_serves_react_index_when_unauthenticated(tmp_path, monkeypatch, client):
    """`/login` is SPA route — must NOT require auth (React app handles login form)."""
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist").mkdir(parents=True)
    (fake_frontend / "dist" / "index.html").write_text("<html>LoginSPA</html>")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client.get("/login")
    assert response.status_code == 200
    assert b"LoginSPA" in response.data


def test_api_route_not_caught_by_fallback(client_with_admin):
    """API 404 must remain 404, not fall through to index.html."""
    response = client_with_admin.get("/api/this-does-not-exist")
    assert response.status_code == 404
    assert b"<html" not in response.data
