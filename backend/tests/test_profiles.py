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


def test_get_active_clears_stale_id_when_file_deleted_externally(tmp_path):
    """L13: get_active() must clear settings.json when profile file is missing externally.

    If the active profile JSON is deleted without going through delete(), get_active()
    must both return None AND clear the stale active_profile ID from settings.json so
    subsequent reads do not waste a file-read on a known-missing file.
    """
    from profiles import ProfileManager
    mgr = ProfileManager(tmp_path)

    created = mgr.create(VALID_PROFILE)
    mgr.set_active(created["id"])

    # Verify the active profile is correctly set
    assert mgr.get_active() is not None

    # Delete the profile file externally (bypassing ProfileManager.delete())
    profile_file = tmp_path / "profiles" / f"{created['id']}.json"
    profile_file.unlink()

    # get_active() must return None
    result = mgr.get_active()
    assert result is None, "get_active() should return None when profile file is missing"

    # AND the stale ID must be cleared from settings.json
    settings = mgr._read_settings()
    assert settings.get("active_profile") is None, (
        "get_active() should clear stale active_profile from settings.json "
        "when the profile file no longer exists"
    )


def test_create_and_update_profile_sets_updated_at(tmp_path):
    """L14: create() and update() must write updated_at to the profile.

    After create(): updated_at must equal created_at.
    After update(): updated_at must be >= created_at (monotonically non-decreasing).
    """
    import time as _time
    from profiles import ProfileManager
    mgr = ProfileManager(tmp_path)

    before_create = _time.time()
    created = mgr.create(VALID_PROFILE)
    after_create = _time.time()

    assert "updated_at" in created, "create() must set updated_at on the profile"
    assert created["updated_at"] == created["created_at"], (
        "create() must set updated_at == created_at on initial creation"
    )
    assert before_create <= created["updated_at"] <= after_create

    # Re-read from disk to confirm persistence
    on_disk = mgr.get(created["id"])
    assert "updated_at" in on_disk, "updated_at must be persisted to disk by create()"
    assert on_disk["updated_at"] == on_disk["created_at"]

    # Allow a small sleep so update timestamp is measurably different
    _time.sleep(0.01)

    before_update = _time.time()
    updated = mgr.update(created["id"], {"name": "Updated Name",
                                          "asr": VALID_PROFILE["asr"],
                                          "translation": VALID_PROFILE["translation"]})
    after_update = _time.time()

    assert "updated_at" in updated, "update() must set updated_at on the profile"
    assert updated["updated_at"] >= created["created_at"], (
        "updated_at must be >= created_at after an update"
    )
    assert before_update <= updated["updated_at"] <= after_update, (
        "updated_at must reflect the time of the update call"
    )

    # Re-read from disk to confirm persistence
    on_disk_after = mgr.get(created["id"])
    assert "updated_at" in on_disk_after, "updated_at must be persisted to disk by update()"
    assert on_disk_after["updated_at"] == updated["updated_at"]


# ============================================================
# parallel_batches validation
# ============================================================

def _make_valid_data():
    return {
        "name": "Test",
        "asr": {"engine": "whisper", "language": "en"},
        "translation": {"engine": "mock"},
    }


def test_parallel_batches_absent_is_valid(tmp_path):
    """parallel_batches is optional — absent profile must validate cleanly."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    errors = pm.validate(_make_valid_data())
    assert errors == []


def test_parallel_batches_valid_range(tmp_path):
    """parallel_batches 1–8 are all valid."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    for n in [1, 2, 4, 8]:
        data = _make_valid_data()
        data["translation"]["parallel_batches"] = n
        assert pm.validate(data) == [], f"Expected no errors for parallel_batches={n}"


def test_parallel_batches_zero_invalid(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    data = _make_valid_data()
    data["translation"]["parallel_batches"] = 0
    errors = pm.validate(data)
    assert any("parallel_batches" in e for e in errors)


def test_parallel_batches_nine_invalid(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    data = _make_valid_data()
    data["translation"]["parallel_batches"] = 9
    errors = pm.validate(data)
    assert any("parallel_batches" in e for e in errors)


def test_parallel_batches_non_int_invalid(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    data = _make_valid_data()
    data["translation"]["parallel_batches"] = "2"
    errors = pm.validate(data)
    assert any("parallel_batches" in e for e in errors)


def test_profile_validates_fine_segmentation_bool(config_dir):
    """fine_segmentation must be bool when present."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Bad fine_seg type",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "fine_segmentation": "yes"},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(profile_data)
    assert any("fine_segmentation" in e and "bool" in e for e in errors), errors


def test_profile_rejects_fine_segmentation_with_non_mlx_engine(config_dir):
    """fine_segmentation=true requires engine=mlx-whisper."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    profile_data = {
        "name": "Bad engine combo",
        "asr": {"engine": "whisper", "model_size": "tiny", "fine_segmentation": True},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(profile_data)
    assert any("fine_segmentation" in e and "mlx-whisper" in e for e in errors), errors


def test_profile_validates_temperature_range(config_dir):
    """asr.temperature must be float in [0.0, 1.0] or null."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)

    # Out of range high
    high = {
        "name": "Temp too high",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": 1.5},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(high)
    assert any("temperature" in e and "0.0" in e for e in errors), errors

    # Out of range low
    low = {
        "name": "Temp too low",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": -0.1},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(low)
    assert any("temperature" in e and "0.0" in e for e in errors), errors

    # Boolean rejected (must be float|null)
    bool_temp = {
        "name": "Temp bool",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": True},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(bool_temp)
    assert any("temperature" in e for e in errors), errors

    # Valid 0.0 + null accepted
    for valid_t in (0.0, 0.5, 1.0, None):
        ok = {
            "name": f"Valid temp {valid_t}",
            "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "temperature": valid_t},
            "translation": {"engine": "mock"},
        }
        errors = mgr.validate(ok)
        temp_errors = [e for e in errors if "temperature" in e]
        assert temp_errors == [], f"unexpected errors for temp={valid_t}: {temp_errors}"


# ============================================================
# VAD + refine field validation (Task A4, added 2026-05-03)
# ============================================================

def test_profile_validates_vad_chunk_max_s_range(config_dir):
    """asr.vad_chunk_max_s must be int in [10, 30]."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    for bad in (5, 35):
        cfg = {
            "name": f"vad_chunk_max_s={bad}",
            "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "vad_chunk_max_s": bad},
            "translation": {"engine": "mock"},
        }
        errors = mgr.validate(cfg)
        assert any("vad_chunk_max_s" in e for e in errors), f"bad={bad}: {errors}"


def test_profile_validates_refine_min_lt_max(config_dir):
    """refine_min_dur must be < refine_max_dur."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "Bad refine pair",
        "asr": {
            "engine": "mlx-whisper", "model_size": "large-v3",
            "refine_min_dur": 5.0, "refine_max_dur": 4.0,
        },
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(cfg)
    assert any("refine_min_dur" in e and "refine_max_dur" in e for e in errors), errors


def test_profile_validates_vad_threshold_range(config_dir):
    """asr.vad_threshold must be float in [0.0, 1.0]."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "vad_threshold out of range",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "vad_threshold": 1.5},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(cfg)
    assert any("vad_threshold" in e for e in errors), errors


def test_profile_backward_compat_no_new_fields(config_dir):
    """Profile without any new v3.8 fields validates cleanly (defaults applied)."""
    from profiles import ProfileManager
    mgr = ProfileManager(config_dir)
    cfg = {
        "name": "Legacy profile",
        "asr": {"engine": "mlx-whisper", "model_size": "large-v3", "language": "en"},
        "translation": {"engine": "mock"},
    }
    errors = mgr.validate(cfg)
    assert errors == [], f"unexpected errors: {errors}"
