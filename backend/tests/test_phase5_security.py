"""Phase 5 — security/correctness fixes from investigation findings."""
import pytest

# All tests in this module exercise real auth (no LOGIN_DISABLED / AUTH_BYPASS).
# This module-level mark replaces the legacy _REAL_AUTH_MODULES tuple entry.
pytestmark = pytest.mark.real_auth


@pytest.fixture
def client_with_admin_db(tmp_path, monkeypatch):
    """Per-test admin user in an isolated AUTH_DB. Idempotent."""
    import app as app_module
    from auth.users import init_db, create_user

    db = str(tmp_path / "users_b1.db")
    monkeypatch.setitem(app_module.app.config, "AUTH_DB_PATH", db)
    init_db(db)
    try:
        create_user(db, "admin_p5_b1", "TestPass1!", is_admin=True)
    except ValueError:
        from auth.users import update_password as _upw
        _upw(db, "admin_p5_b1", "TestPass1!")
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


# ---------------------------------------------------------------------------
# T1.2 — SocketIO LAN-only CORS + connect-time auth
# ---------------------------------------------------------------------------


def test_socketio_cors_origins_uses_lan_regex():
    """T1.2 — SocketIO CORS must NOT be wildcard (was '*' pre-Phase-5)."""
    import app as app_module
    cors_cfg = app_module.socketio.server.eio.cors_allowed_origins
    assert cors_cfg != "*", "SocketIO must use LAN-only CORS (T1.2)"
    # Should be the same regex string the Flask CORS layer uses
    assert cors_cfg == app_module._LAN_ORIGIN_REGEX, \
        f"T1.2 — SocketIO CORS must reuse _LAN_ORIGIN_REGEX, got {cors_cfg!r}"


def test_socketio_connect_handler_registered():
    """T1.2 — a @socketio.on('connect') handler must exist."""
    import app as app_module
    handlers = app_module.socketio.server.handlers.get('/', {})
    assert 'connect' in handlers, \
        "T1.2 — must register @socketio.on('connect') for auth gate"


# ---------------------------------------------------------------------------
# T1.3 — FLASK_SECRET_KEY required at boot
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_app_module():
    """Snapshot sys.modules['app'] (and a couple of related modules) so that
    tests which `del sys.modules['app']` to force re-import don't poison
    every downstream test that uses ``from app import ...``."""
    import sys
    snapshot = {}
    for name in ("app", "auth.decorators", "auth.routes", "auth.admin", "auth.audit",
                 "jobqueue.routes"):
        if name in sys.modules:
            snapshot[name] = sys.modules[name]
    yield
    # Restore originals; drop any new entries the test may have created.
    for name in list(sys.modules.keys()):
        if name == "app" or name.startswith("auth.") or name.startswith("jobqueue."):
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


def test_app_refuses_to_boot_without_flask_secret_key(monkeypatch, _restore_app_module):
    """T1.3 — must raise RuntimeError if FLASK_SECRET_KEY env not set."""
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    import sys
    sys.modules.pop("app", None)
    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        import importlib
        importlib.import_module("app")


def test_app_refuses_placeholder_secret(monkeypatch, _restore_app_module):
    """T1.3 — placeholder string is treated as missing."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "change-me-on-first-deploy")
    import sys
    sys.modules.pop("app", None)
    with pytest.raises(RuntimeError, match="change-me"):
        import importlib
        importlib.import_module("app")


def test_socketio_connect_rejects_unauthenticated(monkeypatch):
    """T1.2 — anonymous SocketIO client must be rejected at connect time.

    Uses flask_socketio's test_client which routes through the actual
    connect handler. With no logged-in user, the handler must abort the
    connection (test_client.is_connected() returns False).
    """
    import app as app_module

    monkeypatch.setitem(app_module.app.config, "LOGIN_DISABLED", False)
    monkeypatch.setitem(app_module.app.config, "R5_AUTH_BYPASS", False)

    flask_test_client = app_module.app.test_client()
    sio_client = app_module.socketio.test_client(
        app_module.app, flask_test_client=flask_test_client,
    )
    try:
        assert sio_client.is_connected() is False, \
            "T1.2 — anonymous SocketIO connect must be rejected"
    finally:
        if sio_client.is_connected():
            sio_client.disconnect()
