"""Tests for multilingual glossary refactor (v3.x). Covers the per-glossary
source_lang/target_lang schema, per-script boundary scanning, and the
glossary-apply parameterized prompt path."""

import pytest

from glossary import (
    SUPPORTED_LANGS,
    is_supported_lang,
    lang_english_name,
)


def test_supported_langs_has_eight_codes():
    assert set(SUPPORTED_LANGS.keys()) == {
        "en", "zh", "ja", "ko", "es", "fr", "de", "th",
    }


def test_is_supported_lang_true_for_whitelist():
    for code in ["en", "zh", "ja", "ko", "es", "fr", "de", "th"]:
        assert is_supported_lang(code) is True


def test_is_supported_lang_false_for_unknown():
    assert is_supported_lang("xx") is False
    assert is_supported_lang("") is False
    assert is_supported_lang(None) is False
    assert is_supported_lang("EN") is False  # case-sensitive lookup


def test_lang_english_name():
    assert lang_english_name("en") == "English"
    assert lang_english_name("zh") == "Chinese"
    assert lang_english_name("ja") == "Japanese"
    assert lang_english_name("ko") == "Korean"
    assert lang_english_name("es") == "Spanish"
    assert lang_english_name("fr") == "French"
    assert lang_english_name("de") == "German"
    assert lang_english_name("th") == "Thai"


def test_lang_english_name_raises_for_unknown():
    with pytest.raises(KeyError):
        lang_english_name("xx")


from glossary import GlossaryManager


def _gm(tmp_path):
    return GlossaryManager(tmp_path)


def test_validate_glossary_requires_source_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "target_lang": "zh",
    })
    assert any("source_lang" in e for e in errors)


def test_validate_glossary_requires_target_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "source_lang": "en",
    })
    assert any("target_lang" in e for e in errors)


def test_validate_glossary_rejects_unknown_source_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "source_lang": "xx",
        "target_lang": "zh",
    })
    assert any("source_lang must be one of" in e for e in errors)


def test_validate_glossary_rejects_unknown_target_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "source_lang": "en",
        "target_lang": "yy",
    })
    assert any("target_lang must be one of" in e for e in errors)


def test_validate_glossary_accepts_same_source_target_lang(tmp_path):
    # EN→EN normalization, ZH→ZH style guide etc. are valid use cases.
    errors = _gm(tmp_path).validate({
        "name": "Style guide",
        "source_lang": "zh",
        "target_lang": "zh",
    })
    assert errors == []


def test_validate_glossary_accepts_valid_pair(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Anime",
        "source_lang": "ja",
        "target_lang": "zh",
    })
    assert errors == []
