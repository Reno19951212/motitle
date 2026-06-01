"""Tests for role-based subtitle text resolver and language descriptor."""
import sys
import os

# Ensure backend package root is on the path for direct imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subtitle_text import resolve_segment_text, resolve_language_descriptor


# ---------------------------------------------------------------------------
# Legacy en/zh/bilingual/auto behavior — must be UNCHANGED
# ---------------------------------------------------------------------------

def test_legacy_en_zh_unchanged():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "en") == "Hello"
    assert resolve_segment_text(seg, "zh") == "你好"


def test_legacy_auto_prefers_zh():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "auto") == "你好"


def test_legacy_auto_falls_back_to_en():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": ""}
    assert resolve_segment_text(seg, "auto") == "Hello"


def test_legacy_zh_falls_back_to_en():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": ""}
    assert resolve_segment_text(seg, "zh") == "Hello"


def test_legacy_bilingual_en_top():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": "你好"}
    # Default line_break is \\N (ASS)
    assert resolve_segment_text(seg, "bilingual", "en_top") == "Hello\\N你好"


def test_legacy_bilingual_zh_top():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "bilingual", "zh_top") == "你好\\NHello"


def test_legacy_bilingual_empty_zh_returns_en():
    seg = {"text": "Hello", "en_text": "Hello", "zh_text": ""}
    assert resolve_segment_text(seg, "bilingual") == "Hello"


def test_legacy_bilingual_empty_en_returns_zh():
    seg = {"text": "", "en_text": "", "zh_text": "你好"}
    assert resolve_segment_text(seg, "bilingual") == "你好"


def test_legacy_strips_qa_prefixes_on_zh():
    seg = {"text": "hi", "en_text": "hi", "zh_text": "[long] [review] 你好"}
    assert resolve_segment_text(seg, "zh") == "你好"
    assert resolve_segment_text(seg, "auto") == "你好"


def test_legacy_line_break_param():
    seg = {"text": "hi", "zh_text": "你好"}
    assert resolve_segment_text(seg, "bilingual", "en_top", "\n") == "hi\n你好"
    assert resolve_segment_text(seg, "bilingual", "en_top", "\\N") == "hi\\N你好"


def test_legacy_default_mode_is_auto():
    seg = {"text": "hi", "zh_text": "你好"}
    # Calling without mode arg should behave as auto
    assert resolve_segment_text(seg) == "你好"


# ---------------------------------------------------------------------------
# New first/second modes
# ---------------------------------------------------------------------------

def test_first_second_modes():
    seg = {"text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "first") == "Hello"
    assert resolve_segment_text(seg, "second") == "你好"


def test_first_falls_back_to_second_when_empty():
    seg = {"text": "", "en_text": "", "zh_text": "你好"}
    assert resolve_segment_text(seg, "first") == "你好"


def test_second_falls_back_to_first_when_empty():
    seg = {"text": "Hello", "zh_text": ""}
    assert resolve_segment_text(seg, "second") == "Hello"


# ---------------------------------------------------------------------------
# Bilingual with first/second ordering
# ---------------------------------------------------------------------------

def test_bilingual_order_en_top():
    seg = {"text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "bilingual", "en_top", "\n") == "Hello\n你好"


def test_bilingual_order_zh_top():
    seg = {"text": "Hello", "zh_text": "你好"}
    assert resolve_segment_text(seg, "bilingual", "zh_top", "\n") == "你好\nHello"


# ---------------------------------------------------------------------------
# Custom first_field / second_field (V6-like usage)
# ---------------------------------------------------------------------------

def test_custom_first_field_v6_like():
    seg = {"zh_text": "粵語"}
    # V6 refiner output is in zh_text, treat as first role
    assert resolve_segment_text(seg, "first", first_field="zh_text") == "粵語"


def test_custom_second_field():
    seg = {"en_text": "Hello", "refined_zh": "精煉你好"}
    assert resolve_segment_text(seg, "second", second_field="refined_zh") == "精煉你好"


def test_custom_fields_bilingual():
    seg = {"source_text": "Hello", "refined_zh": "你好"}
    result = resolve_segment_text(
        seg, "bilingual", "en_top", "\n",
        first_field="source_text", second_field="refined_zh"
    )
    assert result == "Hello\n你好"


def test_custom_first_field_qa_strip_not_applied_to_first():
    """strip_qa_prefixes is only applied to the second (zh) role, not first."""
    seg = {"cantonese_raw": "[long] 賽馬新聞"}
    # first role does NOT get strip_qa_prefixes
    assert resolve_segment_text(seg, "first", first_field="cantonese_raw") == "[long] 賽馬新聞"


def test_custom_second_field_qa_strip_applied():
    """strip_qa_prefixes IS applied when reading the second role."""
    seg = {"refined": "[LONG] 長字幕內容"}
    assert resolve_segment_text(seg, "second", second_field="refined") == "長字幕內容"


# ---------------------------------------------------------------------------
# resolve_language_descriptor — Profile pipeline
# ---------------------------------------------------------------------------

def test_descriptor_profile_default_kind():
    """No active_kind → defaults to profile."""
    d = resolve_language_descriptor({}, {"asr": {"language": "en"}})
    assert [x["role"] for x in d] == ["first", "second"]
    assert d[0]["lang"] == "en"
    assert d[1]["lang"] == "zh"
    assert d[0]["label"] == "原文"
    assert d[1]["label"] == "譯文"


def test_descriptor_profile():
    d = resolve_language_descriptor(
        {"active_kind": "profile"},
        {"asr": {"language": "en"}}
    )
    assert [x["role"] for x in d] == ["first", "second"]
    assert d[0]["lang"] == "en" and d[1]["lang"] == "zh"


def test_descriptor_profile_no_active_cfg():
    """When no active_cfg, defaults to en/zh."""
    d = resolve_language_descriptor({"active_kind": "profile"})
    assert d[0]["lang"] == "en"
    assert d[1]["lang"] == "zh"


def test_descriptor_profile_zh_asr():
    """Cantonese/Chinese ASR profile → first lang is zh."""
    d = resolve_language_descriptor(
        {"active_kind": "profile"},
        {"asr": {"language": "zh"}}
    )
    assert d[0]["lang"] == "zh"
    assert d[1]["lang"] == "zh"


def test_descriptor_none_file_entry():
    """None file_entry handled gracefully."""
    d = resolve_language_descriptor(None)
    assert len(d) == 2
    assert d[0]["role"] == "first"


# ---------------------------------------------------------------------------
# resolve_language_descriptor — V6 pipeline
# ---------------------------------------------------------------------------

def test_descriptor_v6_single():
    """V6 with only one language in by_lang → single descriptor."""
    entry = {
        "active_kind": "pipeline_v6",
        "translations": [{"source_lang": "zh", "by_lang": {"zh": {}}}],
    }
    d = resolve_language_descriptor(entry)
    assert len(d) == 1
    assert d[0]["lang"] == "zh"
    assert d[0]["role"] == "first"


def test_descriptor_v6_with_second():
    """V6 with two by_lang keys → two descriptors."""
    entry = {
        "active_kind": "pipeline_v6",
        "translations": [{"source_lang": "zh", "by_lang": {"zh": {}, "en": {}}}],
    }
    d = resolve_language_descriptor(entry)
    assert len(d) == 2
    assert d[1]["lang"] == "en"
    assert d[1]["role"] == "second"


def test_descriptor_v6_no_translations():
    """V6 with empty translations → defaults src to zh."""
    entry = {"active_kind": "pipeline_v6", "translations": []}
    d = resolve_language_descriptor(entry)
    assert d[0]["lang"] == "zh"
    assert len(d) == 1


def test_descriptor_v6_multiple_rows_dedup_second():
    """V6 with multiple translation rows having same extra lang → deduplicated."""
    entry = {
        "active_kind": "pipeline_v6",
        "translations": [
            {"source_lang": "zh", "by_lang": {"zh": {}, "en": {}}},
            {"source_lang": "zh", "by_lang": {"zh": {}, "en": {}}},
        ],
    }
    d = resolve_language_descriptor(entry)
    # en should only appear once as second
    assert len(d) == 2
    assert d[1]["lang"] == "en"


def test_descriptor_v6_source_lang_fallback():
    """V6 translation row missing source_lang → falls back to zh."""
    entry = {
        "active_kind": "pipeline_v6",
        "translations": [{"by_lang": {"zh": {}}}],
    }
    d = resolve_language_descriptor(entry)
    assert d[0]["lang"] == "zh"


# resolve_language_descriptor — output_lang pipeline


def test_descriptor_output_lang_two():
    d = resolve_language_descriptor({"active_kind": "output_lang", "output_languages": ["yue", "en"]})
    assert d == [
        {"role": "first", "lang": "yue", "label": "口語廣東話"},
        {"role": "second", "lang": "en", "label": "英文"},
    ]


def test_descriptor_output_lang_first_only():
    d = resolve_language_descriptor({"active_kind": "output_lang", "output_languages": ["zh"]})
    assert d == [{"role": "first", "lang": "zh", "label": "中文書面語"}]


def test_descriptor_output_lang_ja():
    d = resolve_language_descriptor({"active_kind": "output_lang", "output_languages": ["ja", "en"]})
    assert d[0] == {"role": "first", "lang": "ja", "label": "日文"}


def test_descriptor_output_lang_empty_returns_empty():
    assert resolve_language_descriptor({"active_kind": "output_lang", "output_languages": []}) == []


def test_descriptor_profile_and_v6_unchanged():
    # Profile branch unchanged
    assert resolve_language_descriptor({"active_kind": "profile"})[0]["label"] == "原文"
    # V6 branch still derives 原文/譯文
    v6 = resolve_language_descriptor({
        "active_kind": "pipeline_v6",
        "translations": [{"source_lang": "zh", "by_lang": {"zh": {"text": "x"}, "en": {"text": "y"}}}],
    })
    assert v6[0]["label"] == "原文" and v6[1]["label"] == "譯文"
