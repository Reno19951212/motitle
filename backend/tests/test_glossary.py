"""
Tests for GlossaryManager CRUD and validation.

Follows the same pattern as test_profiles.py.
"""

import pytest
import json
from pathlib import Path


@pytest.fixture
def glossary_dir(tmp_path):
    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    return tmp_path


VALID_GLOSSARY = {
    "name": "Test Glossary",
    "description": "For testing",
    "source_lang": "en",
    "target_lang": "zh",
    "entries": [
        {"source": "Legislative Council", "target": "立法會"},
        {"source": "Chief Executive", "target": "行政長官"},
    ],
}


def test_validate_valid(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.validate(VALID_GLOSSARY) == []


def test_validate_missing_name(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert "name is required" in mgr.validate({"description": "no name", "source_lang": "en", "target_lang": "zh"})


def test_validate_entry_valid(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.validate_entry({"source": "hello", "target": "你好"}) == []


def test_validate_entry_missing_source(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert any("source" in e for e in mgr.validate_entry({"target": "你好"}))


def test_validate_entry_empty_target(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert any("target" in e for e in mgr.validate_entry({"source": "hello", "target": ""}))


def test_create_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    result = mgr.create(VALID_GLOSSARY)
    assert result["id"]
    assert result["name"] == "Test Glossary"
    assert len(result["entries"]) == 2
    assert result["created_at"] > 0


def test_create_without_entries(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    result = mgr.create({"name": "Empty", "source_lang": "en", "target_lang": "zh"})
    assert result["entries"] == []


def test_create_invalid_raises(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    with pytest.raises(ValueError):
        mgr.create({"name": ""})


def test_get_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    fetched = mgr.get(created["id"])
    assert fetched["id"] == created["id"]
    assert len(fetched["entries"]) == 2


def test_get_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.get("nonexistent") is None


def test_list_all(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    mgr.create({**VALID_GLOSSARY, "name": "Bravo"})
    mgr.create({**VALID_GLOSSARY, "name": "Alpha"})
    result = mgr.list_all()
    assert len(result) == 2
    assert result[0]["name"] == "Alpha"
    assert result[1]["name"] == "Bravo"
    assert "entry_count" in result[0]
    assert "entries" not in result[0]


def test_update_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    updated = mgr.update(created["id"], {"name": "Updated Name"})
    assert updated["name"] == "Updated Name"
    assert len(updated["entries"]) == 2


def test_update_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.update("nonexistent", {"name": "X"}) is None


def test_delete_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    assert mgr.delete(created["id"]) is True
    assert mgr.get(created["id"]) is None


def test_delete_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.delete("nonexistent") is False


def test_add_entry(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": "hello", "target": "你好"})
    assert len(updated["entries"]) == 1
    assert updated["entries"][0]["source"] == "hello"

def test_add_entry_invalid_raises(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh"})
    with pytest.raises(ValueError):
        mgr.add_entry(created["id"], {"source": "", "target": "你好"})

def test_add_entry_nonexistent_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.add_entry("nonexistent", {"source": "hi", "target": "嗨"}) is None


# ----------------------------------------------------------------------
# Quote-stripping normalisation — guards against decorated paste artifacts
# (e.g. `"烈焰悟空"`) that would otherwise survive into glossary entries
# and break the substring-based glossary-scan in app.py.
# ----------------------------------------------------------------------

def test_add_entry_strips_ascii_double_quotes(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": "Blazing Wukong", "target": '"烈焰悟空"'})
    assert updated["entries"][0]["target"] == "烈焰悟空"


def test_add_entry_strips_curly_quotes(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": "Foo", "target": "“測試”"})
    assert updated["entries"][0]["target"] == "測試"


def test_add_entry_strips_chinese_book_brackets(glossary_dir):
    """《 》 should not be stored on the term — broadcast renderers add
    them at output time. Storing them inflates the substring needle."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": "Apple Daily", "target": "《蘋果日報》"})
    assert updated["entries"][0]["target"] == "蘋果日報"


def test_add_entry_strips_corner_brackets(glossary_dir):
    """「 」 is the most common Chinese quote; same reason as 《 》."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": "Hong Kong", "target": "「香港」"})
    assert updated["entries"][0]["target"] == "香港"


def test_add_entry_preserves_inner_quotes(glossary_dir):
    """Only WRAPPING quotes are stripped — inner quotes around a part of
    the term must survive (e.g. a name that legitimately contains them)."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": 'Mr. "Q" Smith', "target": "Q先生"})
    # source keeps the inner "Q" — they're not wrapping the whole term.
    assert updated["entries"][0]["source"] == 'Mr. "Q" Smith'


def test_add_entry_strips_source_field_too(glossary_dir):
    """Same normalisation applies to the source-language field."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    updated = mgr.add_entry(created["id"], {"source": '"Blazing Wukong"', "target": "烈焰悟空"})
    assert updated["entries"][0]["source"] == "Blazing Wukong"


def test_update_entry_strips_quotes_in_patch(glossary_dir):
    """A partial PATCH that re-introduces wrapping quotes should also
    be normalised — not just full add_entry."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    with_entry = mgr.add_entry(created["id"], {"source": "X", "target": "原"})
    eid = with_entry["entries"][0]["id"]
    updated = mgr.update_entry(created["id"], eid, {"target": '"新譯"'})
    assert updated["entries"][0]["target"] == "新譯"


def test_import_csv_strips_quotes(glossary_dir):
    """CSV import is a major paste vector — apply the same stripping."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    # Hand-crafted CSV with bare values (no csv-level quoting) so we
    # exercise our _normalize_entry path directly, not csv-module quote
    # rules.
    csv_text = "source,target\nDaily,《日報》\nHK,「香港」\n"
    updated, added = mgr.import_csv(created["id"], csv_text)
    by_source = {e["source"]: e for e in updated["entries"]}
    assert by_source["Daily"]["target"] == "日報"
    assert by_source["HK"]["target"] == "香港"


def test_strip_wrapping_quotes_idempotent_on_clean_input(glossary_dir):
    """No quotes → no change."""
    from glossary import _strip_wrapping_quotes
    assert _strip_wrapping_quotes("烈焰悟空") == "烈焰悟空"
    assert _strip_wrapping_quotes("Hello World") == "Hello World"


def test_strip_wrapping_quotes_handles_one_layer_only(glossary_dir):
    """Nested same-pair gets only outer layer stripped per call."""
    from glossary import _strip_wrapping_quotes
    assert _strip_wrapping_quotes('""x""') == '"x"'

def test_update_entry(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    # Use add_entry so the entry gets a UUID id assigned
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    with_entry = mgr.add_entry(created["id"], {"source": "Legislative Council", "target": "立法會"})
    first_entry_id = with_entry["entries"][0]["id"]
    updated = mgr.update_entry(created["id"], first_entry_id, {"source": "LegCo", "target": "立法會"})
    assert updated["entries"][0]["source"] == "LegCo"
    assert updated["entries"][0]["target"] == "立法會"

def test_update_entry_out_of_range(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    assert mgr.update_entry(created["id"], "nonexistent-entry-id", {"source": "x", "target": "y"}) is None

def test_delete_entry(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    # Use add_entry so entries have UUID ids assigned
    created = mgr.create({"name": "Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    mgr.add_entry(created["id"], {"source": "Legislative Council", "target": "立法會"})
    with_two = mgr.add_entry(created["id"], {"source": "Chief Executive", "target": "行政長官"})
    first_entry_id = with_two["entries"][0]["id"]
    updated = mgr.delete_entry(created["id"], first_entry_id)
    assert len(updated["entries"]) == 1
    assert updated["entries"][0]["source"] == "Chief Executive"

def test_delete_entry_out_of_range(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    # delete_entry with unknown id returns glossary unchanged (not None)
    result = mgr.delete_entry(created["id"], "nonexistent-entry-id")
    assert result is not None
    assert len(result["entries"]) == 2

def test_import_csv(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "CSV Test", "source_lang": "en", "target_lang": "zh", "entries": []})
    csv_content = "source,target\nhello,你好\nworld,世界\n,skip_empty\n"
    result, added = mgr.import_csv(created["id"], csv_content)
    assert result is not None
    assert len(result["entries"]) == 2
    assert result["entries"][0]["source"] == "hello"
    assert added == 2

def test_import_csv_appends(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    csv_content = "source,target\nnew term,新詞\n"
    result, added = mgr.import_csv(created["id"], csv_content)
    assert result is not None
    assert len(result["entries"]) == 3
    assert added == 1

def test_import_csv_nonexistent_raises(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    # import_csv returns (None, 0) when glossary not found
    result, added = mgr.import_csv("nonexistent", "source,target\nhello,你好\n")
    assert result is None
    assert added == 0

def test_export_csv(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    csv_str = mgr.export_csv(created["id"])
    assert "source,target" in csv_str
    assert "Legislative Council" in csv_str
    assert "立法會" in csv_str

def test_export_csv_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.export_csv("nonexistent") is None


def test_api_list_glossaries():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app, _init_glossary_manager
    import tempfile
    import json as json_mod
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        glossaries_dir = tmp_path / "glossaries"
        glossaries_dir.mkdir()
        _init_glossary_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post("/api/glossaries", json={
                "name": "Test",
                "source_lang": "en",
                "target_lang": "zh",
                "entries": [{"source": "hi", "target": "嗨"}],
            })
            assert resp.status_code == 201

            resp = client.get("/api/glossaries")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data["glossaries"]) == 1
            assert data["glossaries"][0]["entry_count"] == 1


# ----------------------------------------------------------------------
# Old per-language validation rules (letter / CJK requirements) were
# DROPPED in v3.x multilingual refactor (T3). Tests below that relied on
# those rules are kept here for documentation but skipped.
# ----------------------------------------------------------------------

@pytest.mark.skip(reason="Old CJK-in-target rule dropped in v3.x multilingual refactor (T3)")
def test_validate_entry_rejects_numeric_zh(glossary_dir):
    """ZH field containing only digits/ASCII should be rejected as invalid."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate_entry({"source": "Michael", "target": "23468"})
    assert any("target" in e for e in errors), f"Expected target error, got: {errors}"


@pytest.mark.skip(reason="Old CJK-in-target rule dropped in v3.x multilingual refactor (T3)")
def test_validate_entry_rejects_ascii_only_zh(glossary_dir):
    """ZH field with only Latin letters should be rejected."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate_entry({"source": "hello", "target": "hello world"})
    assert any("target" in e for e in errors), f"Expected target error, got: {errors}"


def test_validate_entry_accepts_mixed_target_with_cjk(glossary_dir):
    """Target field with at least one CJK character is allowed (mixed input is common)."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.validate_entry({"source": "Hong Kong", "target": "香港 HK"}) == []
    assert mgr.validate_entry({"source": "typhoon", "target": "颱風"}) == []


@pytest.mark.skip(reason="Old ASCII-letter-in-source rule dropped in v3.x multilingual refactor (T3)")
def test_validate_entry_rejects_source_without_letters(glossary_dir):
    """Source field must contain at least one ASCII letter (pure punctuation/numbers is invalid)."""
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate_entry({"source": "12345", "target": "一二三四五"})
    assert any("source" in e for e in errors), f"Expected source error, got: {errors}"
    errors = mgr.validate_entry({"source": "!!!", "target": "驚嘆"})
    assert any("source" in e for e in errors), f"Expected source error, got: {errors}"
