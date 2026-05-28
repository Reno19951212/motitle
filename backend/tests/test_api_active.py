"""Test /api/me response includes active_kind/active_id, and new
POST /api/active unified set-active endpoint.

Uses the conftest _isolate_app_data autouse fixture (R5_AUTH_BYPASS=1,
LOGIN_DISABLED=True) so no explicit login is needed.
"""
import pytest


@pytest.fixture
def api_client():
    """Flask test client backed by the real app module."""
    import app as _app
    return _app.app.test_client()


@pytest.fixture(autouse=True)
def restore_settings():
    """Snapshot + restore config/settings.json around each test."""
    import app as _app
    settings_path = _app._profile_manager._settings_path
    original = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    yield
    if original is not None:
        settings_path.write_text(original, encoding="utf-8")


def test_api_me_includes_active_kind(api_client):
    r = api_client.get("/api/me")
    assert r.status_code == 200
    body = r.get_json()
    assert "active_kind" in body
    assert body["active_kind"] in ("profile", "pipeline_v6")
    assert "active_id" in body


def test_post_active_profile_kind(api_client):
    # First find an existing profile id to use
    profiles = api_client.get("/api/profiles").get_json().get("profiles", [])
    if not profiles:
        pytest.skip("no profiles available")
    pid = profiles[0]["id"]
    r = api_client.post("/api/active", json={"kind": "profile", "id": pid})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["active"]["kind"] == "profile"
    assert body["active"]["id"] == pid


def test_post_active_pipeline_v6_kind(api_client):
    import app as _app
    pls = _app._pipeline_manager.list_all()
    # Filter to only V6 pipelines
    v6 = [p for p in pls if p.get("pipeline_type") == "v6_vad_dual_asr"]
    if not v6:
        pytest.skip("no V6 pipelines imported")
    pid = v6[0]["id"]
    r = api_client.post("/api/active", json={"kind": "pipeline_v6", "id": pid})
    assert r.status_code == 200
    assert r.get_json()["active"]["kind"] == "pipeline_v6"


def test_post_active_invalid_kind_returns_400(api_client):
    r = api_client.post("/api/active", json={"kind": "bogus", "id": "x"})
    assert r.status_code == 400


def test_post_active_unknown_id_returns_404(api_client):
    r = api_client.post("/api/active", json={"kind": "profile", "id": "nonexistent-id-12345"})
    assert r.status_code == 404
