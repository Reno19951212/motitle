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


def test_validate_entry_requires_source(tmp_path):
    errors = _gm(tmp_path).validate_entry({"target": "x"})
    assert any("source" in e for e in errors)


def test_validate_entry_requires_target(tmp_path):
    errors = _gm(tmp_path).validate_entry({"source": "x"})
    assert any("target" in e for e in errors)


def test_validate_entry_accepts_pure_numbers(tmp_path):
    # The user's reported bug: "en must contain at least one letter" rejected
    # legitimate use cases like { source: "2024", target: "二零二四" }.
    errors = _gm(tmp_path).validate_entry({"source": "2024", "target": "二零二四"})
    assert errors == []


def test_validate_entry_accepts_japanese_source(tmp_path):
    errors = _gm(tmp_path).validate_entry({"source": "ニュース", "target": "新聞"})
    assert errors == []


def test_validate_entry_rejects_self_translation_when_same_lang(tmp_path):
    errors = _gm(tmp_path).validate_entry(
        {"source": "廣播", "target": "廣播"}, same_lang=True,
    )
    assert any("identical" in e for e in errors)


def test_validate_entry_rejects_alias_equal_to_source_when_same_lang(tmp_path):
    errors = _gm(tmp_path).validate_entry(
        {"source": "廣播", "target": "無線電", "target_aliases": ["廣播"]},
        same_lang=True,
    )
    assert any("identical" in e for e in errors)


def test_validate_entry_accepts_identical_text_when_different_lang(tmp_path):
    # source_lang=en, target_lang=ja, source="USA", target="USA" is meaningful
    # (cross-language proper noun preservation).
    errors = _gm(tmp_path).validate_entry(
        {"source": "USA", "target": "USA"}, same_lang=False,
    )
    assert errors == []


def test_normalize_entry_strips_quotes_from_source_target_aliases(tmp_path):
    from glossary import _normalize_entry
    entry = {
        "source": '"hello"',
        "target": "「廣播」",
        "target_aliases": ["《主播》", "no_quotes"],
    }
    out = _normalize_entry(entry)
    assert out["source"] == "hello"
    assert out["target"] == "廣播"
    assert out["target_aliases"] == ["主播", "no_quotes"]


def test_normalize_entry_preserves_unchanged_fields(tmp_path):
    from glossary import _normalize_entry
    entry = {
        "id": "abc",
        "source": "broadcast",
        "target": "廣播",
    }
    out = _normalize_entry(entry)
    assert out["id"] == "abc"
    assert out["source"] == "broadcast"
    assert out["target"] == "廣播"


def test_create_persists_source_target_lang(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({
        "name": "Anime", "source_lang": "ja", "target_lang": "zh",
    })
    assert g["source_lang"] == "ja"
    assert g["target_lang"] == "zh"
    # Round-trip
    g2 = gm.get(g["id"])
    assert g2["source_lang"] == "ja"
    assert g2["target_lang"] == "zh"


def test_create_rejects_missing_source_lang(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    with pytest.raises(ValueError, match="source_lang"):
        gm.create({"name": "X", "target_lang": "zh"})


def test_add_entry_uses_new_field_names(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({
        "name": "T", "source_lang": "en", "target_lang": "zh",
    })
    updated = gm.add_entry(g["id"], {"source": "broadcast", "target": "廣播"})
    assert updated["entries"][0]["source"] == "broadcast"
    assert updated["entries"][0]["target"] == "廣播"


def test_add_entry_rejects_old_en_zh_keys(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    g = gm.create({
        "name": "T", "source_lang": "en", "target_lang": "zh",
    })
    with pytest.raises(ValueError, match="source"):
        gm.add_entry(g["id"], {"en": "broadcast", "zh": "廣播"})


def test_list_all_ignores_old_schema_files(tmp_path):
    """A leftover glossary file from before the cutover (no source_lang) is
    silently skipped from list_all. The file still sits on disk; we don't
    delete it automatically."""
    import json
    gm = _gm(tmp_path)
    old_path = gm._glossaries_dir / "legacy.json"
    old_path.write_text(json.dumps({
        "id": "legacy",
        "name": "Old",
        "entries": [{"en": "x", "zh": "X"}],
    }))
    new = gm.create({
        "name": "New", "source_lang": "en", "target_lang": "zh",
    })
    summaries = gm.list_all()
    ids = [s["id"] for s in summaries]
    assert "legacy" not in ids
    assert new["id"] in ids


def test_update_metadata_can_change_langs(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    updated = gm.update(g["id"], {
        "name": "T2", "source_lang": "ja", "target_lang": "zh",
    })
    assert updated["source_lang"] == "ja"
    assert updated["name"] == "T2"


def test_csv_export_new_format(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    gm.add_entry(g["id"], {"source": "broadcast", "target": "廣播"})
    gm.add_entry(g["id"], {
        "source": "anchor", "target": "主播",
        "target_aliases": ["主持", "新聞主播"],
    })
    csv_text = gm.export_csv(g["id"])
    assert csv_text.splitlines()[0] == "source,target,target_aliases"
    assert "broadcast,廣播," in csv_text
    assert "anchor,主播,主持;新聞主播" in csv_text


def test_csv_import_new_format_accepts_3col(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = (
        "source,target,target_aliases\n"
        "broadcast,廣播,\n"
        "anchor,主播,主持;新聞主播\n"
    )
    updated, added = gm.import_csv(g["id"], csv_text)
    assert added == 2
    sources = [e["source"] for e in updated["entries"]]
    assert "broadcast" in sources
    assert "anchor" in sources
    anchor = next(e for e in updated["entries"] if e["source"] == "anchor")
    assert anchor["target_aliases"] == ["主持", "新聞主播"]


def test_csv_import_2col_no_aliases_ok(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = "source,target\nbroadcast,廣播\n"
    updated, added = gm.import_csv(g["id"], csv_text)
    assert added == 1


def test_csv_import_old_en_zh_header_rejected(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = "en,zh\nbroadcast,廣播\n"
    with pytest.raises(ValueError, match="source, target"):
        gm.import_csv(g["id"], csv_text)


def test_csv_import_unknown_header_rejected(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = "foo,bar\nx,y\n"
    with pytest.raises(ValueError, match="source, target"):
        gm.import_csv(g["id"], csv_text)


@pytest.fixture
def client_with_admin():
    """Minimal Flask test client for API route tests in this module.

    Relies on the autouse _isolate_app_data fixture (conftest.py) which sets
    LOGIN_DISABLED=True and R5_AUTH_BYPASS=True, so no real auth session is
    needed. Yields (client, None) to match the canonical tuple-fixture pattern
    used across the test suite.
    """
    import app as app_module
    with app_module.app.test_client() as c:
        yield c, None


def test_api_glossaries_languages_returns_whitelist(client_with_admin):
    client, _ = client_with_admin
    r = client.get("/api/glossaries/languages")
    assert r.status_code == 200
    body = r.get_json()
    assert "languages" in body
    codes = [lang["code"] for lang in body["languages"]]
    assert set(codes) == {"en", "zh", "ja", "ko", "es", "fr", "de", "th"}
    en = next(lang for lang in body["languages"] if lang["code"] == "en")
    assert en["english_name"] == "English"
    assert "display_name" in en
