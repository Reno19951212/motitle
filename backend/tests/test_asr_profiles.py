import pytest
from asr_profiles import validate_asr_profile


VALID_MIN_ASR = {
    "name": "粵語廣播 (emergent)",
    "engine": "mlx-whisper",
    "model_size": "large-v3",
    "mode": "emergent-translate",
    "language": "zh",
}


def test_valid_minimum_profile_returns_empty_errors():
    assert validate_asr_profile(VALID_MIN_ASR) == []


def test_missing_name_rejected():
    data = {**VALID_MIN_ASR, "name": ""}
    errors = validate_asr_profile(data)
    assert any("name" in e.lower() for e in errors)


def test_unknown_engine_rejected():
    data = {**VALID_MIN_ASR, "engine": "openai-realtime"}
    errors = validate_asr_profile(data)
    assert any("engine" in e.lower() for e in errors)


def test_unknown_mode_rejected():
    data = {**VALID_MIN_ASR, "mode": "auto-detect"}
    errors = validate_asr_profile(data)
    assert any("mode" in e.lower() for e in errors)


def test_translate_to_en_mode_accepts_any_audio_language():
    """translate-to-en mode means 'audio is X, output English'.
    The language field is the AUDIO source hint, so it must accept
    non-English values (e.g., language=zh for Cantonese-to-English).
    Whisper's translate task always outputs English regardless of hint."""
    for audio_lang in ("zh", "ja", "ko", "fr", "de", "es"):
        data = {**VALID_MIN_ASR, "mode": "translate-to-en", "language": audio_lang}
        assert validate_asr_profile(data) == [], f"translate-to-en + language={audio_lang} should be accepted"
    # Also language="en" is still valid (English audio → English output, identity)
    data = {**VALID_MIN_ASR, "mode": "translate-to-en", "language": "en"}
    assert validate_asr_profile(data) == []


def test_unknown_language_rejected():
    data = {**VALID_MIN_ASR, "language": "tlh"}  # Klingon
    errors = validate_asr_profile(data)
    assert any("language" in e.lower() for e in errors)


def test_boolean_field_type_check():
    data = {**VALID_MIN_ASR, "word_timestamps": "yes"}
    errors = validate_asr_profile(data)
    assert any("word_timestamps" in e.lower() and "bool" in e.lower() for e in errors)


def test_initial_prompt_length_cap():
    data = {**VALID_MIN_ASR, "initial_prompt": "x" * 600}
    errors = validate_asr_profile(data)
    assert any("initial_prompt" in e.lower() and "512" in e for e in errors)


def test_non_dict_payload_rejected():
    errors = validate_asr_profile([1, 2, 3])
    assert any("object" in e.lower() for e in errors)


def test_name_length_cap():
    data = {**VALID_MIN_ASR, "name": "x" * 100}
    errors = validate_asr_profile(data)
    assert any("name" in e.lower() and "64" in e for e in errors)


def test_description_length_cap():
    data = {**VALID_MIN_ASR, "description": "x" * 300}
    errors = validate_asr_profile(data)
    assert any("description" in e.lower() and "256" in e for e in errors)


def test_invalid_model_size_rejected():
    data = {**VALID_MIN_ASR, "model_size": "small"}
    errors = validate_asr_profile(data)
    assert any("model_size" in e.lower() for e in errors)


def test_invalid_device_rejected():
    data = {**VALID_MIN_ASR, "device": "gpu"}
    errors = validate_asr_profile(data)
    assert any("device" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# ASRProfileManager tests (T3)
# ---------------------------------------------------------------------------

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from asr_profiles import ASRProfileManager


@pytest.fixture
def manager(tmp_path):
    return ASRProfileManager(tmp_path)


def _make(manager, name="test", user_id=None):
    data = {
        "name": name,
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "mode": "emergent-translate",
        "language": "zh",
    }
    return manager.create(data, user_id=user_id)


def test_create_assigns_uuid_and_timestamps(manager):
    p = _make(manager)
    assert len(p["id"]) == 36
    assert p["created_at"] > 0
    assert p["updated_at"] == p["created_at"]
    assert p["user_id"] is None


def test_create_with_user_id_records_owner(manager):
    p = _make(manager, user_id=42)
    assert p["user_id"] == 42


def test_create_persists_to_json_file(manager, tmp_path):
    p = _make(manager)
    fpath = tmp_path / "asr_profiles" / f"{p['id']}.json"
    assert fpath.exists()
    loaded = json.loads(fpath.read_text())
    assert loaded["id"] == p["id"]


def test_create_rejects_invalid(manager):
    with pytest.raises(ValueError):
        manager.create({"name": ""}, user_id=None)


def test_get_returns_none_for_missing(manager):
    assert manager.get("nonexistent-id") is None


def test_list_all_returns_all_regardless_of_owner(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)
    assert len(manager.list_all()) == 3


def test_list_visible_admin_sees_all(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)
    visible = manager.list_visible(user_id=99, is_admin=True)
    assert len(visible) == 3


def test_list_visible_user_sees_own_plus_shared(manager):
    _make(manager, name="a", user_id=1)
    _make(manager, name="b", user_id=2)
    _make(manager, name="c", user_id=None)  # shared
    visible = manager.list_visible(user_id=1, is_admin=False)
    names = sorted(p["name"] for p in visible)
    assert names == ["a", "c"]


def test_can_view_owner(manager):
    p = _make(manager, user_id=5)
    assert manager.can_view(p["id"], user_id=5, is_admin=False) is True


def test_can_view_non_owner(manager):
    p = _make(manager, user_id=5)
    assert manager.can_view(p["id"], user_id=6, is_admin=False) is False


def test_can_view_shared(manager):
    p = _make(manager, user_id=None)
    assert manager.can_view(p["id"], user_id=99, is_admin=False) is True


def test_can_view_admin(manager):
    p = _make(manager, user_id=5)
    assert manager.can_view(p["id"], user_id=99, is_admin=True) is True


def test_update_if_owned_success(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=5, is_admin=False, patch={"name": "renamed"}
    )
    assert ok is True
    assert errors == []
    assert manager.get(p["id"])["name"] == "renamed"


def test_update_if_owned_rejects_non_owner(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=6, is_admin=False, patch={"name": "x"}
    )
    assert ok is False
    assert any("permission" in e.lower() or "forbid" in e.lower() for e in errors)


def test_update_if_owned_validates(manager):
    p = _make(manager, user_id=5)
    ok, errors = manager.update_if_owned(
        p["id"], user_id=5, is_admin=False, patch={"engine": "fake"}
    )
    assert ok is False
    assert errors  # validator picked it up


def test_delete_if_owned_success(manager):
    p = _make(manager, user_id=5)
    assert manager.delete_if_owned(p["id"], user_id=5, is_admin=False) is True
    assert manager.get(p["id"]) is None


def test_delete_if_owned_rejects_non_owner(manager):
    p = _make(manager, user_id=5)
    assert manager.delete_if_owned(p["id"], user_id=6, is_admin=False) is False


def test_manager_reloads_from_disk_on_init(manager, tmp_path):
    p = _make(manager, name="persisted")
    manager2 = ASRProfileManager(tmp_path)
    assert manager2.get(p["id"])["name"] == "persisted"
