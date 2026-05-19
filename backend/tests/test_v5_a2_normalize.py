"""T7 — translations_normalize_v5 helper tests.

v4 [{en_text, zh_text}] → v5 [{by_lang}] at read time. v5 input passes through.
"""
import pytest


def test_normalize_v4_translations_to_v5_shape():
    """v4 [{idx, en_text, zh_text, status, flags}] → v5 [{by_lang: {...}}]."""
    from translations_normalize_v5 import normalize_translations_for_v5
    v4 = [
        {"idx": 0, "en_text": "hello", "zh_text": "你好", "status": "approved", "flags": []},
        {"idx": 1, "en_text": "world", "zh_text": "世界", "status": "pending", "flags": ["long"]},
    ]
    v5 = normalize_translations_for_v5(v4)
    assert len(v5) == 2
    assert v5[0]["idx"] == 0
    assert v5[0]["source_lang"] == "en"  # v4 assumed EN source
    assert v5[0]["source_text"] == "hello"
    assert v5[0]["by_lang"]["zh"]["text"] == "你好"
    assert v5[0]["by_lang"]["zh"]["status"] == "approved"
    assert v5[1]["by_lang"]["zh"]["flags"] == ["long"]


def test_normalize_passthrough_when_already_v5():
    """v5-shaped input passes through unchanged."""
    from translations_normalize_v5 import normalize_translations_for_v5
    v5_in = [
        {"idx": 0, "start": 0.0, "end": 1.0,
         "source_lang": "zh", "source_text": "中文",
         "by_lang": {"en": {"text": "english", "status": "pending", "flags": []}}},
    ]
    out = normalize_translations_for_v5(v5_in)
    assert out == v5_in


def test_normalize_empty_list():
    from translations_normalize_v5 import normalize_translations_for_v5
    assert normalize_translations_for_v5([]) == []


def test_normalize_handles_missing_fields_defensively():
    """v4 entries with missing fields shouldn't crash; use sensible defaults."""
    from translations_normalize_v5 import normalize_translations_for_v5
    v4 = [{"idx": 0}]
    v5 = normalize_translations_for_v5(v4)
    assert v5[0]["source_lang"] == "en"
    assert v5[0]["source_text"] == ""
    assert v5[0]["by_lang"] == {"zh": {"text": "", "status": "pending", "flags": []}}
