"""Integration tests for v4 entity REST endpoints (ASR profile / MT profile /
Pipeline). Uses Flask test_client with LOGIN_DISABLED + R5_AUTH_BYPASS so
ownership checks short-circuit (admin-equivalent)."""

import json
import pytest


@pytest.fixture
def client():
    """Reuses the existing app.py boot path. R5_AUTH_BYPASS=True turns the
    @require_*_owner decorators into no-ops so we can hit endpoints without
    setting up real auth."""
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["R5_AUTH_BYPASS"] = True
    with app_module.app.test_client() as c:
        yield c


VALID_ASR = {
    "name": "test-asr",
    "engine": "mlx-whisper",
    "model_size": "large-v3",
    "mode": "emergent-translate",
    "language": "zh",
}


def test_create_asr_profile_201(client):
    resp = client.post("/api/asr_profiles",
                       data=json.dumps(VALID_ASR),
                       content_type="application/json")
    assert resp.status_code == 201
    body = resp.get_json()
    assert len(body["id"]) == 36
    assert body["name"] == "test-asr"


def test_create_asr_profile_400_on_invalid(client):
    bad = {**VALID_ASR, "mode": "garbage"}
    resp = client.post("/api/asr_profiles",
                       data=json.dumps(bad),
                       content_type="application/json")
    assert resp.status_code == 400
    assert "errors" in resp.get_json()


def test_get_asr_profile_404_when_missing(client):
    resp = client.get("/api/asr_profiles/nonexistent")
    assert resp.status_code == 404


def test_list_asr_profiles(client):
    client.post("/api/asr_profiles",
                data=json.dumps(VALID_ASR),
                content_type="application/json")
    resp = client.get("/api/asr_profiles")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body["asr_profiles"], list)
    assert any(p["name"] == "test-asr" for p in body["asr_profiles"])


def test_patch_asr_profile(client):
    create = client.post("/api/asr_profiles",
                         data=json.dumps(VALID_ASR),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.patch(f"/api/asr_profiles/{pid}",
                        data=json.dumps({"name": "renamed"}),
                        content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "renamed"


def test_delete_asr_profile(client):
    create = client.post("/api/asr_profiles",
                         data=json.dumps(VALID_ASR),
                         content_type="application/json")
    pid = create.get_json()["id"]
    resp = client.delete(f"/api/asr_profiles/{pid}")
    assert resp.status_code == 204
    follow = client.get(f"/api/asr_profiles/{pid}")
    assert follow.status_code == 404
