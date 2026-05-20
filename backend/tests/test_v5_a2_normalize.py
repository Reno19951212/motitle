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


# ============================================================
# downgrade_translations_to_v4 — v5 by_lang → v4 en_text/zh_text
# for backward compat with live v4 React frontend.
# ============================================================


def test_downgrade_v5_translations_to_v4_shape():
    """v5 [{by_lang: {zh: {text}, en: {text}}}] → v4 [{en_text, zh_text}]."""
    from translations_normalize_v5 import downgrade_translations_to_v4
    v5 = [
        {
            "idx": 0, "start": 0.0, "end": 1.0,
            "source_lang": "zh", "source_text": "中文原文",
            "by_lang": {
                "zh": {"text": "潤色中文", "status": "approved", "flags": ["review"]},
                "en": {"text": "english translation", "status": "pending", "flags": []},
            },
        },
    ]
    v4 = downgrade_translations_to_v4(v5)
    assert len(v4) == 1
    assert v4[0]["en_text"] == "english translation"
    assert v4[0]["zh_text"] == "潤色中文"
    assert v4[0]["status"] == "approved"
    assert v4[0]["flags"] == ["review"]
    # by_lang stripped; v5 extras kept as harmless fields
    assert "by_lang" not in v4[0]
    assert v4[0]["source_text"] == "中文原文"  # extras preserved


def test_downgrade_v4_passthrough():
    """v4-shaped input passes through unchanged (no by_lang to flatten)."""
    from translations_normalize_v5 import downgrade_translations_to_v4
    v4_in = [{"idx": 0, "en_text": "x", "zh_text": "y", "status": "pending", "flags": []}]
    out = downgrade_translations_to_v4(v4_in)
    assert out == v4_in


def test_downgrade_uses_source_text_when_by_lang_missing_for_source():
    """If by_lang doesn't have source_lang entry, use source_text for that side."""
    from translations_normalize_v5 import downgrade_translations_to_v4
    # ZH source but by_lang only has EN
    v5 = [
        {
            "idx": 0, "source_lang": "zh", "source_text": "中文",
            "by_lang": {"en": {"text": "english", "status": "pending", "flags": []}},
        },
    ]
    v4 = downgrade_translations_to_v4(v5)
    assert v4[0]["zh_text"] == "中文"  # falls back to source_text
    assert v4[0]["en_text"] == "english"


def test_downgrade_empty_list():
    from translations_normalize_v5 import downgrade_translations_to_v4
    assert downgrade_translations_to_v4([]) == []


def test_downgrade_handles_empty_by_lang_safely():
    """Entry with empty by_lang dict shouldn't crash."""
    from translations_normalize_v5 import downgrade_translations_to_v4
    v5 = [{"idx": 0, "source_lang": "en", "source_text": "hi", "by_lang": {}}]
    v4 = downgrade_translations_to_v4(v5)
    assert v4[0]["en_text"] == "hi"  # source_text fallback (en source)
    assert v4[0]["zh_text"] == ""  # no zh in by_lang, no zh source → empty


def test_downgrade_preserves_idx_start_end():
    from translations_normalize_v5 import downgrade_translations_to_v4
    v5 = [
        {
            "idx": 42, "start": 10.0, "end": 12.5,
            "source_lang": "zh", "source_text": "src",
            "by_lang": {"zh": {"text": "polished", "status": "pending", "flags": []}},
        },
    ]
    v4 = downgrade_translations_to_v4(v5)
    assert v4[0]["idx"] == 42
    assert v4[0]["start"] == 10.0
    assert v4[0]["end"] == 12.5
