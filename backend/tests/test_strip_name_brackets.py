"""Tests for strip_name_brackets helper and its integration into glossary_stage.

Run:
    cd backend && FLASK_SECRET_KEY=test-secret-only-for-pytest-do-not-deploy R5_AUTH_BYPASS=1 \
        ./venv/bin/python -m pytest tests/test_strip_name_brackets.py -q
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import output_lang_glossary as G


# ---------------------------------------------------------------------------
# strip_name_brackets — unit tests
# ---------------------------------------------------------------------------

def test_strip_both_names():
    """Both bracketed names are stripped."""
    result = G.strip_name_brackets("「火悟空」與「活力拍檔」", ["火悟空", "活力拍檔"])
    assert result == "火悟空與活力拍檔"


def test_idempotent_already_bare():
    """If the name is already bare, calling the function is a no-op."""
    result = G.strip_name_brackets("火悟空", ["火悟空"])
    assert result == "火悟空"


def test_idempotent_double_call():
    """Running twice yields the same result as running once."""
    text = "「火悟空」出閘"
    names = ["火悟空"]
    once = G.strip_name_brackets(text, names)
    twice = G.strip_name_brackets(once, names)
    assert once == twice


def test_non_name_brackets_preserved():
    """Corner brackets around non-name content must NOT be stripped."""
    result = G.strip_name_brackets("他說「你好」火悟空", ["火悟空"])
    # 「你好」 is preserved; bare 火悟空 is already bare → unchanged
    assert result == "他說「你好」火悟空"


def test_non_name_brackets_preserved_bare_name_unchanged():
    """When the name appears bare AND there are non-name brackets, both are correct."""
    result = G.strip_name_brackets("「你好」火悟空", ["火悟空"])
    assert result == "「你好」火悟空"


def test_substring_safety():
    """A name that is a substring of another must not be partially unwrapped.

    Given names ["火悟空", "火悟空B"]:
    - 「火悟空B」 → fire悟空B  (longer match wins; bare 火悟空 is not a partial fragment)
    - 「火悟空」  → 火悟空     (exact match)
    """
    names = ["火悟空", "火悟空B"]
    # Longer name 火悟空B should be processed first (longest first sorting)
    text = "「火悟空B」同「火悟空」"
    result = G.strip_name_brackets(text, names)
    # Both stripped to bare names, not partially unwrapped
    assert result == "火悟空B同火悟空"


def test_empty_names_list():
    """Empty names list → text unchanged."""
    text = "「火悟空」出閘"
    result = G.strip_name_brackets(text, [])
    assert result == "「火悟空」出閘"


def test_empty_text():
    """Empty text → empty string returned."""
    result = G.strip_name_brackets("", ["火悟空"])
    assert result == ""


def test_none_in_names_ignored():
    """None values in names list are skipped without error."""
    result = G.strip_name_brackets("「火悟空」", ["火悟空", None])
    assert result == "火悟空"


# ---------------------------------------------------------------------------
# glossary_stage integration — bracket stripping
# ---------------------------------------------------------------------------

def _make_glossary(id_, name, src_lang, tgt_lang, entries):
    return {
        "id": id_, "name": name,
        "source_lang": src_lang, "target_lang": tgt_lang,
        "entries": entries,
    }


_RACING_GLOSSARY = _make_glossary(
    "racing", "Racing 1350", "en", "zh",
    [
        {"source": "Blazing Wukong", "target": "火悟空 (K335)"},
        {"source": "Amazing Partners", "target": "活力拍檔"},
    ]
)

_REFINE_GLOSSARY = _make_glossary(
    "refine", "Racing 1350", "yue", "zh",
    [
        {"source": "Blazing Wukong", "target": "火悟空 (K335)"},
    ]
)


def _mock_llm_no_change(system, user):
    """Mock that returns text unchanged (no name correction by LLM)."""
    zh = user.split("中文：")[-1].strip()
    return '{"text": "' + zh + '"}'


def test_glossary_stage_strips_brackets_even_when_llm_makes_no_change():
    """A segment whose text is 「火悟空」順利出閘 with 火悟空 as applicable glossary target
    → after glossary_stage the text is 火悟空順利出閘 even if llm_review reports no name change."""
    segs = [
        {
            "text": "「火悟空」順利出閘",
            "src_text": "Blazing Wukong broke well",
            "start": 0.0, "end": 2.0,
        }
    ]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm_no_change, use_llm=True,
    )
    assert result[0]["text"] == "火悟空順利出閘"


def test_glossary_stage_strips_brackets_target_side():
    """Refine/pass mode: target-side candidate 火悟空 already in text as 「火悟空」 → stripped."""
    segs = [
        {
            "text": "「火悟空」衝線",
            "start": 0.0, "end": 2.0,
        }
    ]
    result = G.glossary_stage(
        segs, [_REFINE_GLOSSARY],
        output_lang="zh", content_lang="yue", derive_mode="refine",
        llm_call=_mock_llm_no_change, use_llm=False,
    )
    assert result[0]["text"] == "火悟空衝線"


def test_glossary_stage_no_candidates_text_unchanged():
    """A segment with no applicable candidates is byte-identical (no bracket stripping either)."""
    segs = [
        {
            "text": "「你好」今天天氣不錯",
            "src_text": "Good day today",
            "start": 0.0, "end": 2.0,
        }
    ]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm_no_change, use_llm=True,
    )
    # "Good day today" does not match Blazing Wukong or Amazing Partners
    assert result[0]["text"] == "「你好」今天天氣不錯"


def test_glossary_stage_bracket_strip_does_not_add_glossary_changes():
    """Bracket stripping alone must NOT add entries to glossary_changes."""
    segs = [
        {
            "text": "「火悟空」順利出閘",
            "src_text": "Blazing Wukong broke well",
            "start": 0.0, "end": 2.0,
        }
    ]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm_no_change, use_llm=True,
    )
    # Only bracket strip happened (LLM returned unchanged text), so glossary_changes is empty
    assert result[0]["glossary_changes"] == []


def test_glossary_stage_no_glossaries_brackets_untouched():
    """With empty glossaries list, brackets around any text are left as-is."""
    segs = [
        {
            "text": "「火悟空」出閘",
            "start": 0.0, "end": 2.0,
        }
    ]
    result = G.glossary_stage(
        segs, [],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm_no_change, use_llm=True,
    )
    # No glossaries → fast path, text must be byte-identical
    assert result[0]["text"] == "「火悟空」出閘"
