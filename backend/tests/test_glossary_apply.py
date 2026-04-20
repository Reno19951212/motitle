"""Tests for glossary-scan and glossary-apply endpoints."""
import json
import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def client():
    """Create a Flask test client with a clean file registry."""
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c, app_module


@pytest.fixture
def file_with_translations(client):
    """Register a file with segments and translations for testing."""
    c, app_module = client
    file_id = f"test-{uuid.uuid4().hex[:8]}"
    app_module._file_registry[file_id] = {
        "id": file_id,
        "original_name": "test.mp4",
        "status": "done",
        "translation_status": "done",
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "The anchor reported the broadcast live"},
            {"start": 2.0, "end": 4.0, "text": "Good morning everyone"},
            {"start": 4.0, "end": 6.0, "text": "The live broadcast continues"},
        ],
        "translations": [
            {"zh_text": "主持人現場報導了播出內容", "status": "pending"},
            {"zh_text": "大家早上好", "status": "approved"},
            {"zh_text": "直播繼續進行", "status": "pending"},
        ],
    }
    yield file_id, c, app_module
    app_module._file_registry.pop(file_id, None)


@pytest.fixture
def glossary_with_entries(client):
    """Create a glossary with test entries."""
    c, app_module = client
    glossary_id = f"test-glossary-{uuid.uuid4().hex[:8]}"
    app_module._glossary_manager._write_glossary(glossary_id, {
        "id": glossary_id,
        "name": "Test Glossary",
        "description": "For testing",
        "entries": [
            {"id": "e1", "en": "broadcast", "zh": "廣播"},
            {"id": "e2", "en": "anchor", "zh": "主播"},
        ],
        "created_at": 0,
        "updated_at": 0,
    })
    yield glossary_id, c, app_module
    # Cleanup
    try:
        app_module._glossary_manager.delete(glossary_id)
    except Exception:
        pass


def test_glossary_scan_finds_violations(file_with_translations, glossary_with_entries):
    """Scan should detect segments where EN contains glossary term but ZH does not."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["scanned_count"] == 3
    violations = data["violations"]
    # Segment 0 has "anchor" and "broadcast" in EN, ZH lacks "主播" and "廣播"
    # Segment 2 has "broadcast" in EN, ZH has "直播" not "廣播"
    term_pairs = [(v["seg_idx"], v["term_en"]) for v in violations]
    assert (0, "broadcast") in term_pairs
    assert (0, "anchor") in term_pairs
    assert (2, "broadcast") in term_pairs
    assert data["violation_count"] == len(violations)


def test_glossary_scan_skips_matching_segments(file_with_translations, glossary_with_entries):
    """Segments where ZH already contains the correct term should not be violations."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Patch segment 0 to already have correct terms
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "主播現場報導了廣播內容"

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()
    # Segment 0 should no longer be a violation for either term
    seg0_violations = [v for v in data["violations"] if v["seg_idx"] == 0]
    assert len(seg0_violations) == 0


def test_glossary_scan_missing_glossary(file_with_translations):
    """Should return 404 for nonexistent glossary."""
    file_id, c, _ = file_with_translations
    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": "nonexistent"}),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_scan_missing_file(client, glossary_with_entries):
    """Should return 404 for nonexistent file."""
    c, _ = client
    glossary_id, _, _ = glossary_with_entries
    resp = c.post("/api/files/nonexistent/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_scan_missing_body(file_with_translations):
    """Should return 400 when glossary_id is missing."""
    file_id, c, _ = file_with_translations
    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({}),
                  content_type="application/json")
    assert resp.status_code == 400
