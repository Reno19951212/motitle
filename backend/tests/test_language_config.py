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
