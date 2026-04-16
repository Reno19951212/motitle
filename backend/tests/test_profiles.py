import pytest
import json
from pathlib import Path


@pytest.fixture
def config_dir(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"active_profile": None}))
    return tmp_path


def test_validate_profile_valid(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Test Profile",
        "description": "For testing",
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert errors == []


def test_validate_profile_missing_name(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "description": "No name",
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert "name is required" in errors


def test_validate_profile_invalid_asr_engine(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Bad Engine",
        "description": "",
        "asr": {"engine": "nonexistent", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert any("asr.engine" in e for e in errors)


def test_validate_profile_accepts_cloud_translation_engines(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    for cloud_engine in ("glm-4.6-cloud", "qwen3.5-397b-cloud", "gpt-oss-120b-cloud"):
        profile_data = {
            "name": f"Cloud {cloud_engine}",
            "description": "",
            "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
            "translation": {"engine": cloud_engine, "temperature": 0.1, "glossary_id": None},
        }
        errors = mgr.validate(profile_data)
        engine_errors = [e for e in errors if "translation.engine" in e]
        assert engine_errors == [], f"{cloud_engine} rejected: {engine_errors}"


def test_validate_profile_missing_asr(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "No ASR",
        "description": "",
        "translation": {"engine": "qwen2.5-3b", "quantization": "q4", "temperature": 0.1, "glossary_id": None}
    }
    errors = mgr.validate(profile_data)
    assert "asr is required" in errors


VALID_PROFILE = {
    "name": "Dev Default",
    "description": "Development testing profile",
    "asr": {
        "engine": "whisper",
        "model_size": "tiny",
        "language": "en",
        "device": "cpu"
    },
    "translation": {
        "engine": "qwen2.5-3b",
        "quantization": "q4",
        "temperature": 0.1,
        "glossary_id": None
    }
}


def test_create_profile(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile = mgr.create(VALID_PROFILE)
    assert profile["id"]
    assert profile["name"] == "Dev Default"
    assert profile["asr"]["engine"] == "whisper"
    assert profile["created_at"] > 0


def test_create_profile_invalid_raises(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    with pytest.raises(ValueError):
        mgr.create({"name": ""})


def test_get_profile(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    fetched = mgr.get(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Dev Default"


def test_get_nonexistent_returns_none(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    assert mgr.get("nonexistent") is None


def test_list_profiles(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    mgr.create({**VALID_PROFILE, "name": "Bravo"})
    mgr.create({**VALID_PROFILE, "name": "Alpha"})
    profiles = mgr.list_all()
    assert len(profiles) == 2
    assert profiles[0]["name"] == "Alpha"
    assert profiles[1]["name"] == "Bravo"


def test_update_profile(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    updated = mgr.update(created["id"], {
        "name": "Updated Name",
        "asr": {**VALID_PROFILE["asr"], "model_size": "base"},
        "translation": VALID_PROFILE["translation"],
    })
    assert updated["name"] == "Updated Name"
    assert updated["asr"]["model_size"] == "base"
    assert updated["id"] == created["id"]


def test_update_nonexistent_returns_none(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    assert mgr.update("nonexistent", VALID_PROFILE) is None


def test_delete_profile(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    assert mgr.delete(created["id"]) is True
    assert mgr.get(created["id"]) is None


def test_delete_nonexistent_returns_false(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    assert mgr.delete("nonexistent") is False


def test_set_and_get_active_profile(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    p1 = mgr.create({**VALID_PROFILE, "name": "Profile 1"})
    p2 = mgr.create({**VALID_PROFILE, "name": "Profile 2"})
    mgr.set_active(p1["id"])
    assert mgr.get_active()["id"] == p1["id"]
    mgr.set_active(p2["id"])
    assert mgr.get_active()["id"] == p2["id"]


def test_get_active_when_none_set(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    assert mgr.get_active() is None


def test_delete_active_profile_clears_active(config_dir):
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    created = mgr.create(VALID_PROFILE)
    mgr.set_active(created["id"])
    mgr.delete(created["id"])
    assert mgr.get_active() is None


# ============================================================
# API Integration Tests
# ============================================================

@pytest.fixture
def client(tmp_path):
    """Create a Flask test client with a temp config dir."""
    from app import app, _init_profile_manager
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_list_profiles_empty(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["profiles"] == []


def test_api_create_profile(client):
    resp = client.post("/api/profiles", json=VALID_PROFILE)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["profile"]["name"] == "Dev Default"
    assert data["profile"]["id"]


def test_api_create_invalid_returns_400(client):
    resp = client.post("/api/profiles", json={"name": ""})
    assert resp.status_code == 400
    assert "errors" in resp.get_json()


def test_api_get_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.get(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    assert resp.get_json()["profile"]["id"] == pid


def test_api_get_nonexistent_returns_404(client):
    resp = client.get("/api/profiles/nonexistent")
    assert resp.status_code == 404


def test_api_update_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.patch(f"/api/profiles/{pid}", json={
        "name": "Updated",
        "asr": VALID_PROFILE["asr"],
        "translation": VALID_PROFILE["translation"],
    })
    assert resp.status_code == 200
    assert resp.get_json()["profile"]["name"] == "Updated"


def test_api_delete_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.delete(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    resp2 = client.get(f"/api/profiles/{pid}")
    assert resp2.status_code == 404


def test_api_activate_profile(client):
    create_resp = client.post("/api/profiles", json=VALID_PROFILE)
    pid = create_resp.get_json()["profile"]["id"]
    resp = client.post(f"/api/profiles/{pid}/activate")
    assert resp.status_code == 200
    resp2 = client.get("/api/profiles/active")
    assert resp2.status_code == 200
    assert resp2.get_json()["profile"]["id"] == pid


def test_api_get_active_when_none(client):
    resp = client.get("/api/profiles/active")
    assert resp.status_code == 200
    assert resp.get_json()["profile"] is None


# ============================================================
# Bug regression tests
# ============================================================

def test_update_profile_partial_asr_preserves_other_fields(tmp_path):
    """PATCH {"asr": {"engine": "whisper"}} must preserve other asr fields like model_size."""
    from profiles import ProfileManager
    mgr = ProfileManager(tmp_path)

    full_asr = {"engine": "whisper", "model_size": "base", "language": "en", "device": "mps"}
    created = mgr.create({**VALID_PROFILE, "asr": full_asr})

    # Partial PATCH: only change the engine, leave everything else out
    updated = mgr.update(created["id"], {"asr": {"engine": "mlx-whisper"}})

    assert updated["asr"]["engine"] == "mlx-whisper"
    assert updated["asr"]["model_size"] == "base", "model_size was wiped by partial asr PATCH"
    assert updated["asr"]["language"] == "en", "language was wiped by partial asr PATCH"
    assert updated["asr"]["device"] == "mps", "device was wiped by partial asr PATCH"


def test_update_profile_partial_translation_preserves_other_fields(tmp_path):
    """PATCH {"translation": {"style": "casual"}} must preserve other translation fields."""
    from profiles import ProfileManager
    mgr = ProfileManager(tmp_path)

    full_translation = {
        "engine": "qwen2.5-7b",
        "quantization": "q8",
        "temperature": 0.3,
        "glossary_id": "glossary-abc",
        "style": "formal",
    }
    created = mgr.create({**VALID_PROFILE, "translation": full_translation})

    # Partial PATCH: only change style
    updated = mgr.update(created["id"], {"translation": {"style": "casual"}})

    assert updated["translation"]["style"] == "casual"
    assert updated["translation"]["engine"] == "qwen2.5-7b", "engine was wiped by partial translation PATCH"
    assert updated["translation"]["quantization"] == "q8", "quantization was wiped by partial translation PATCH"
    assert updated["translation"]["temperature"] == 0.3, "temperature was wiped by partial translation PATCH"
    assert updated["translation"]["glossary_id"] == "glossary-abc", "glossary_id was wiped by partial translation PATCH"


def test_update_profile_font_null_raises_value_error_not_type_error(tmp_path):
    """PATCH {"font": null} must raise ValueError (validation), not TypeError (crash).

    Regression test for: ProfileManager.update() performing font deep-merge
    ({**existing["font"], **None}) before calling validate(), causing a TypeError
    instead of a clean validation error.

    The bug only triggers when the existing profile already has a font dict set,
    because the deep-merge condition checks both "font" in data AND "font" in existing.
    """
    from profiles import ProfileManager
    mgr = ProfileManager(tmp_path)

    # Create a profile that already has a font block (this is the precondition
    # that makes the deep-merge path execute and crash with TypeError).
    profile_with_font = {**VALID_PROFILE, "font": {"family": "Arial", "size": 36}}
    created = mgr.create(profile_with_font)

    # Sending font=None should be rejected by validation (font must be a dict),
    # but must NOT crash with a TypeError from the deep-merge.
    with pytest.raises(ValueError):
        mgr.update(created["id"], {"font": None})
