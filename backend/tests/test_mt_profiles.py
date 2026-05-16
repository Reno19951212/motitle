import pytest
from mt_profiles import validate_mt_profile, MTProfileManager


VALID_MIN_MT = {
    "name": "粵語廣播風格",
    "engine": "qwen3.5-35b-a3b",
    "input_lang": "zh",
    "output_lang": "zh",
    "system_prompt": "你係香港電視廣播嘅字幕編輯員。",
    "user_message_template": "請將以下文字轉粵語廣播風格：\n{text}",
}


def test_valid_minimum_returns_empty_errors():
    assert validate_mt_profile(VALID_MIN_MT) == []


def test_engine_locked_to_qwen():
    data = {**VALID_MIN_MT, "engine": "claude-opus-4.5"}
    errors = validate_mt_profile(data)
    assert any("engine" in e.lower() for e in errors)


def test_input_must_equal_output_lang():
    data = {**VALID_MIN_MT, "input_lang": "en", "output_lang": "zh"}
    errors = validate_mt_profile(data)
    assert any("same-lang" in e.lower() or "must equal" in e.lower() for e in errors)


def test_user_message_template_must_contain_text_placeholder():
    data = {**VALID_MIN_MT, "user_message_template": "請翻譯。"}
    errors = validate_mt_profile(data)
    assert any("{text}" in e for e in errors)


def test_system_prompt_length_cap():
    data = {**VALID_MIN_MT, "system_prompt": "x" * 5000}
    errors = validate_mt_profile(data)
    assert any("4096" in e for e in errors)


def test_batch_size_range():
    data = {**VALID_MIN_MT, "batch_size": 0}
    errors = validate_mt_profile(data)
    assert any("batch_size" in e for e in errors)
    data = {**VALID_MIN_MT, "batch_size": 999}
    errors = validate_mt_profile(data)
    assert any("batch_size" in e for e in errors)


def test_temperature_range():
    data = {**VALID_MIN_MT, "temperature": -0.1}
    errors = validate_mt_profile(data)
    assert any("temperature" in e for e in errors)
    data = {**VALID_MIN_MT, "temperature": 3.0}
    errors = validate_mt_profile(data)
    assert any("temperature" in e for e in errors)


def test_parallel_batches_range():
    data = {**VALID_MIN_MT, "parallel_batches": 0}
    errors = validate_mt_profile(data)
    assert any("parallel_batches" in e for e in errors)


@pytest.fixture
def manager(tmp_path):
    return MTProfileManager(tmp_path)


def _make(manager, name="test", user_id=None):
    data = {**VALID_MIN_MT, "name": name}
    return manager.create(data, user_id=user_id)


def test_manager_create_and_get(manager):
    p = _make(manager)
    assert manager.get(p["id"])["system_prompt"] == VALID_MIN_MT["system_prompt"]


def test_manager_list_visible_ownership(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)
    visible = manager.list_visible(user_id=1, is_admin=False)
    assert sorted(p["name"] for p in visible) == ["a", "c"]


def test_manager_update_if_owned_validates(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=5, is_admin=False, patch={"input_lang": "ja", "output_lang": "zh"}
    )
    assert ok is False  # cross-lang rejected
    assert any("same-lang" in e.lower() for e in errors)


def test_manager_delete_if_owned(manager):
    p = _make(manager, user_id=5)
    assert manager.delete_if_owned(p["id"], user_id=5, is_admin=False) is True
    assert manager.get(p["id"]) is None


def test_manager_persists_across_init(manager, tmp_path):
    p = _make(manager, name="persisted")
    manager2 = MTProfileManager(tmp_path)
    assert manager2.get(p["id"])["name"] == "persisted"
