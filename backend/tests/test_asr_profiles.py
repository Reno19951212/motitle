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


def test_translate_to_en_mode_forces_language_en():
    data = {**VALID_MIN_ASR, "mode": "translate-to-en", "language": "zh"}
    errors = validate_asr_profile(data)
    assert any("translate-to-en" in e.lower() and "language" in e.lower() for e in errors)


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
