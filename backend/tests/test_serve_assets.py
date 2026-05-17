"""v4.0 A3 T3 — Flask serves Vite-built hashed assets from /assets/<path>."""
import pytest


@pytest.fixture
def client_with_admin():
    """Logged-in admin client against the global app."""
    import app as app_module
    from auth.users import init_db, create_user, update_password

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_a3_assets", "TestPass1!", is_admin=True)
    except ValueError:
        update_password(db_path, "alice_a3_assets", "TestPass1!")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_a3_assets", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield c


def test_serve_assets_returns_js(tmp_path, monkeypatch, client_with_admin):
    fake_frontend = tmp_path / "frontend"
    assets_dir = fake_frontend / "dist" / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "index-abc123.js").write_text("console.log(1)")
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client_with_admin.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert (
        "application/javascript" in response.content_type
        or "text/javascript" in response.content_type
    )
    assert b"console.log" in response.data


def test_serve_assets_404_when_missing(tmp_path, monkeypatch, client_with_admin):
    fake_frontend = tmp_path / "frontend"
    (fake_frontend / "dist" / "assets").mkdir(parents=True)
    monkeypatch.setattr("app._FRONTEND_DIR", str(fake_frontend))
    response = client_with_admin.get("/assets/does-not-exist.js")
    assert response.status_code == 404
