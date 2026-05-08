import pytest
import json
from pathlib import Path

@pytest.fixture
def config_dir(tmp_path):
    lang_dir = tmp_path / "languages"
    lang_dir.mkdir()
    en = {"id": "en", "name": "English", "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}}
    (lang_dir / "en.json").write_text(json.dumps(en, indent=2))
    zh = {"id": "zh", "name": "Chinese", "asr": {"max_words_per_segment": 25, "max_segment_duration": 8.0}, "translation": {"batch_size": 8, "temperature": 0.1}}
    (lang_dir / "zh.json").write_text(json.dumps(zh, indent=2))
    return tmp_path

def test_get_existing(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    cfg = mgr.get("en")
    assert cfg is not None
    assert cfg["id"] == "en"
    assert cfg["asr"]["max_words_per_segment"] == 40

def test_get_nonexistent(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    assert mgr.get("fr") is None

def test_list_all(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    configs = mgr.list_all()
    assert len(configs) == 2
    names = [c["name"] for c in configs]
    assert "English" in names and "Chinese" in names

def test_update_asr_param(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    updated = mgr.update("en", {"asr": {"max_words_per_segment": 30, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}})
    assert updated["asr"]["max_words_per_segment"] == 30
    assert mgr.get("en")["asr"]["max_words_per_segment"] == 30

def test_update_translation_param(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    updated = mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 5, "temperature": 0.3}})
    assert updated["translation"]["batch_size"] == 5

def test_update_nonexistent(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    assert mgr.update("fr", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}}) is None

def test_update_invalid_max_words(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 3, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}})

def test_update_invalid_max_duration(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 0.5}, "translation": {"batch_size": 10, "temperature": 0.1}})

def test_update_invalid_batch_size(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 0, "temperature": 0.1}})

def test_update_invalid_temperature(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 3.0}})

def test_update_invalid_simplified_to_traditional(config_dir):
    """asr.simplified_to_traditional must be a boolean."""
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("zh", {
            "asr": {
                "max_words_per_segment": 16, "max_segment_duration": 8,
                "simplified_to_traditional": "yes",  # str not bool
            },
            "translation": {"batch_size": 8, "temperature": 0.1},
        })

def test_update_valid_simplified_to_traditional(config_dir):
    """Boolean true / false both accepted; flag persists."""
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    mgr.update("zh", {
        "asr": {
            "max_words_per_segment": 16, "max_segment_duration": 8,
            "simplified_to_traditional": True,
        },
        "translation": {"batch_size": 8, "temperature": 0.1},
    })
    cfg = mgr.get("zh")
    assert cfg["asr"]["simplified_to_traditional"] is True

    mgr.update("zh", {
        "asr": {
            "max_words_per_segment": 16, "max_segment_duration": 8,
            "simplified_to_traditional": False,
        },
        "translation": {"batch_size": 8, "temperature": 0.1},
    })
    assert mgr.get("zh")["asr"]["simplified_to_traditional"] is False


import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_api_list_languages():
    from app import app, _init_language_config_manager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lang_dir = tmp_path / "languages"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({"id": "en", "name": "English", "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}}))
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/languages")
            assert resp.status_code == 200
            assert len(resp.get_json()["languages"]) == 1

def test_api_get_language():
    from app import app, _init_language_config_manager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lang_dir = tmp_path / "languages"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({"id": "en", "name": "English", "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}}))
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/languages/en")
            assert resp.status_code == 200
            assert resp.get_json()["language"]["id"] == "en"

def test_api_get_language_not_found():
    from app import app, _init_language_config_manager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "languages").mkdir()
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/languages/fr")
            assert resp.status_code == 404

def test_api_update_language():
    from app import app, _init_language_config_manager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lang_dir = tmp_path / "languages"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({"id": "en", "name": "English", "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}}))
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.patch("/api/languages/en", json={"asr": {"max_words_per_segment": 30, "max_segment_duration": 8.0}, "translation": {"batch_size": 5, "temperature": 0.2}})
            assert resp.status_code == 200
            assert resp.get_json()["language"]["asr"]["max_words_per_segment"] == 30
