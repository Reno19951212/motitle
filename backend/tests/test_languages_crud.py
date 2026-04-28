"""Tests for language config CRUD: LanguageConfigManager.create()/delete() + POST/DELETE routes."""
import json
import pytest
from pathlib import Path

from app import app, _language_config_manager, _profile_manager


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client with isolated language_config + profile dirs."""
    # Re-point both managers to a temp dir so we don't touch real config
    from language_config import LanguageConfigManager
    from profiles import ProfileManager

    # Seed built-ins so delete-builtin tests have real targets
    lang_dir = tmp_path / "languages"
    lang_dir.mkdir()
    (lang_dir / "en.json").write_text(json.dumps({
        "id": "en", "name": "English",
        "asr": {"max_words_per_segment": 25, "max_segment_duration": 40},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }))
    (lang_dir / "zh.json").write_text(json.dumps({
        "id": "zh", "name": "Chinese",
        "asr": {"max_words_per_segment": 30, "max_segment_duration": 8},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }))

    new_lc_mgr = LanguageConfigManager(tmp_path)
    new_prof_mgr = ProfileManager(tmp_path)

    monkeypatch.setattr("app._language_config_manager", new_lc_mgr)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _valid_body(lc_id="zh-news", name="中文 · 新聞"):
    return {
        "id": lc_id,
        "name": name,
        "asr": {"max_words_per_segment": 20, "max_segment_duration": 5},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }


def test_create_language_config_success(client):
    """POST with valid body returns 200 and creates the file."""
    resp = client.post("/api/languages", json=_valid_body())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["config"]["id"] == "zh-news"
    assert data["config"]["name"] == "中文 · 新聞"
    assert data["config"]["asr"]["max_words_per_segment"] == 20


def test_create_id_collision(client):
    """POST with id that already exists returns 409."""
    client.post("/api/languages", json=_valid_body("zh-news"))
    resp = client.post("/api/languages", json=_valid_body("zh-news", "Different name"))
    assert resp.status_code == 409
    assert "already exists" in resp.get_json()["error"].lower()


def test_create_invalid_id_format(client):
    """POST with id containing illegal chars (slash, space, uppercase) returns 400."""
    for bad_id in ["my/lang", "zh news", "ZH-NEWS", "中文", ""]:
        resp = client.post("/api/languages", json=_valid_body(bad_id))
        assert resp.status_code == 400, f"id={bad_id!r} should be rejected, got {resp.status_code}"


def test_create_out_of_range_value(client):
    """POST with numeric values outside the validation ranges returns 400."""
    body = _valid_body()
    body["asr"]["max_words_per_segment"] = 500  # over 200 max
    resp = client.post("/api/languages", json=body)
    assert resp.status_code == 400


def test_delete_built_in_blocked(client):
    """DELETE /api/languages/en (built-in) returns 400."""
    resp = client.delete("/api/languages/en")
    assert resp.status_code == 400
    assert "built-in" in resp.get_json()["error"].lower()


def test_delete_in_use_blocked(client):
    """DELETE config used by a profile returns 400 with profile names."""
    # Create a custom config
    client.post("/api/languages", json=_valid_body("zh-news"))
    # Create a profile that uses it
    profile = _profile_manager.create({
        "id": "test-profile",
        "name": "Test Profile",
        "asr": {"engine": "mlx-whisper", "language_config_id": "zh-news"},
        "translation": {"engine": "mock"},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#fff",
                 "outline_color": "#000", "outline_width": 2, "margin_bottom": 40},
    })
    resp = client.delete("/api/languages/zh-news")
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "Test Profile" in error or "test-profile" in error


def test_delete_unused_succeeds(client, tmp_path):
    """DELETE custom config with no referencing profile returns 200 + file gone."""
    client.post("/api/languages", json=_valid_body("zh-news"))
    resp = client.delete("/api/languages/zh-news")
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True
    # Verify GET returns 404 now
    get_resp = client.get("/api/languages/zh-news")
    assert get_resp.status_code == 404


def test_delete_nonexistent(client):
    """DELETE id that never existed returns 404."""
    resp = client.delete("/api/languages/never-existed")
    assert resp.status_code == 404
