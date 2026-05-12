"""Tests for glossary-scan and glossary-apply endpoints.

Field names updated for v3.x multilingual refactor:
  - entry payload: "source"/"target" (was "en"/"zh")
  - violation payload: "term_source"/"term_target" (was "term_en"/"term_zh")
  - applied_terms dict: "term_source"/"term_target"
  - baseline: "baseline_target" (was "baseline_zh")
  - scan response: "strict_violations"/"loose_violations" (was flat "violations")
  - apply response: "applied_count"/"failed_count" (no longer returns "results" array)
  - glossary fixtures: include "source_lang"/"target_lang"
"""
import json
import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def reset_managers(tmp_path):
    """Reinitialize _glossary_manager and _profile_manager with a fresh tmp_path
    before each test so state left by other test files doesn't cause failures."""
    from app import _init_profile_manager, _init_glossary_manager
    _init_profile_manager(tmp_path)
    _init_glossary_manager(tmp_path)
    yield


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
    """Create a glossary with test entries (v3.x multilingual schema)."""
    c, app_module = client
    glossary_id = f"test-glossary-{uuid.uuid4().hex[:8]}"
    app_module._glossary_manager._write_glossary(glossary_id, {
        "id": glossary_id,
        "name": "Test Glossary",
        "description": "For testing",
        "source_lang": "en",
        "target_lang": "zh",
        "entries": [
            {"id": "e1", "source": "broadcast", "target": "廣播"},
            {"id": "e2", "source": "anchor", "target": "主播"},
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


def _all_violations(data):
    """Helper: combine strict + loose violations into a single flat list."""
    return data.get("strict_violations", []) + data.get("loose_violations", [])


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
    violations = _all_violations(data)
    # Segment 0 has "anchor" and "broadcast" in EN, ZH lacks "主播" and "廣播"
    # Segment 2 has "broadcast" in EN, ZH has "直播" not "廣播"
    term_pairs = [(v["seg_idx"], v["term_source"]) for v in violations]
    assert (0, "broadcast") in term_pairs
    assert (0, "anchor") in term_pairs
    assert (2, "broadcast") in term_pairs
    total = data["strict_violation_count"] + data["loose_violation_count"]
    assert total == len(violations)


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
    seg0_violations = [v for v in _all_violations(data) if v["seg_idx"] == 0]
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


def test_glossary_apply_calls_ollama_and_updates(file_with_translations, glossary_with_entries, monkeypatch):
    """Apply should call LLM via apply_glossary_term and update zh_text."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Mock apply_glossary_term in ollama_engine (the function the route calls)
    call_log = []
    from translation import ollama_engine

    def fake_apply(**kwargs):
        call_log.append(kwargs)
        return "主播現場報導了廣播內容"

    monkeypatch.setattr(ollama_engine, "apply_glossary_term", fake_apply)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [
                          {"seg_idx": 0, "term_source": "broadcast", "term_target": "廣播"},
                      ]
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["applied_count"] == 1

    # Verify file registry was updated
    updated_zh = app_module._file_registry[file_id]["translations"][0]["zh_text"]
    assert updated_zh == "主播現場報導了廣播內容"
    assert len(call_log) == 1


def test_glossary_apply_missing_file(client, glossary_with_entries):
    """Should return 404 for nonexistent file."""
    c, _ = client
    glossary_id, _, _ = glossary_with_entries
    resp = c.post("/api/files/nonexistent/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [{"seg_idx": 0, "term_source": "x", "term_target": "y"}]
                  }),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_apply_empty_violations(file_with_translations, glossary_with_entries):
    """Should return 400 when violations array is empty."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries
    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": []
                  }),
                  content_type="application/json")
    assert resp.status_code == 400


def test_glossary_apply_no_translations(client, glossary_with_entries):
    """File with no translations: violations out of range are silently skipped; route returns 200."""
    c, app_module = client
    glossary_id, _, _ = glossary_with_entries
    file_id = f"test-empty-{uuid.uuid4().hex[:8]}"
    app_module._file_registry[file_id] = {
        "id": file_id, "original_name": "empty.mp4",
        "status": "done", "segments": [], "translations": [],
    }
    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [{"seg_idx": 0, "term_source": "x", "term_target": "y"}]
                  }),
                  content_type="application/json")
    # New route: term-pair validation fires first → 400 (x/y not in glossary)
    assert resp.status_code == 400
    app_module._file_registry.pop(file_id, None)


def test_glossary_apply_term_not_in_glossary(file_with_translations, glossary_with_entries):
    """Violations referencing a term not in the glossary should return 400."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [
                          {"seg_idx": 0, "term_source": "nonexistent_term", "term_target": "不存在"},
                      ]
                  }),
                  content_type="application/json")
    # New route: term-pair validation returns 400 before making any LLM calls
    assert resp.status_code == 400


def test_glossary_apply_missing_glossary(file_with_translations):
    """Should return 404 when glossary_id does not exist."""
    file_id, c, _ = file_with_translations
    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": "nonexistent-glossary",
                      "violations": [{"seg_idx": 0, "term_source": "x", "term_target": "y"}]
                  }),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_apply_sequential_violations_same_segment(file_with_translations, glossary_with_entries, monkeypatch):
    """Multiple violations for the same segment should be processed sequentially — each LLM call sees the previous correction."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Set initial zh_text with both wrong terms
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "主持人現場報導了播出內容"

    call_count = [0]
    call_inputs = []

    from translation import ollama_engine

    def fake_apply(**kwargs):
        call_inputs.append(kwargs["current_target"])
        call_count[0] += 1
        # First call: fix "broadcast" → "廣播"
        # Second call: fix "anchor" → "主播", receiving the zh from first call
        if call_count[0] == 1:
            return "主持人現場報導了廣播內容"
        else:
            return "主播現場報導了廣播內容"

    monkeypatch.setattr(ollama_engine, "apply_glossary_term", fake_apply)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [
                          {"seg_idx": 0, "term_source": "broadcast", "term_target": "廣播"},
                          {"seg_idx": 0, "term_source": "anchor", "term_target": "主播"},
                      ]
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["applied_count"] == 2
    assert call_count[0] == 2
    # Second call's current_target must contain the first call's output
    assert "主持人現場報導了廣播內容" in call_inputs[1]
    # Final zh_text in registry is the chained result
    final_zh = app_module._file_registry[file_id]["translations"][0]["zh_text"]
    assert final_zh == "主播現場報導了廣播內容"


def test_glossary_apply_preserves_approval_status(file_with_translations, glossary_with_entries, monkeypatch):
    """Apply should NOT change the segment's approval status."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Set segment 0 to approved
    app_module._file_registry[file_id]["translations"][0]["status"] = "approved"

    from translation import ollama_engine

    def fake_apply(**kwargs):
        return "主播現場報導了廣播內容"

    monkeypatch.setattr(ollama_engine, "apply_glossary_term", fake_apply)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [
                          {"seg_idx": 0, "term_source": "broadcast", "term_target": "廣播"},
                      ]
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    # Status should remain "approved" — not changed
    assert app_module._file_registry[file_id]["translations"][0]["status"] == "approved"


def test_glossary_scan_returns_matches_array(file_with_translations, glossary_with_entries):
    """Response must include `matches` array and `match_count` field."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Patch segment 2 ZH so "broadcast" is correctly translated as "廣播" → 1 match.
    app_module._file_registry[file_id]["translations"][2]["zh_text"] = "廣播繼續進行"

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "matches" in data, "response missing 'matches' array"
    assert "match_count" in data, "response missing 'match_count'"
    assert isinstance(data["matches"], list)
    assert data["match_count"] == len(data["matches"])

    # Both legacy and new field names should be present in match rows
    for m in data["matches"]:
        assert set(m.keys()) >= {"seg_idx", "en_text", "zh_text", "term_source", "term_target", "approved"}


def test_glossary_scan_segment_with_correct_zh_goes_to_matches(file_with_translations, glossary_with_entries):
    """When EN contains term and ZH already contains correct term, row goes to matches not violations."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    app_module._file_registry[file_id]["translations"][2]["zh_text"] = "廣播繼續進行"

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()

    seg2_violations_for_broadcast = [
        v for v in _all_violations(data) if v["seg_idx"] == 2 and v["term_source"] == "broadcast"
    ]
    assert seg2_violations_for_broadcast == [], "broadcast on seg 2 should not be a violation when ZH has 廣播"

    seg2_matches_for_broadcast = [
        m for m in data["matches"] if m["seg_idx"] == 2 and m["term_source"] == "broadcast"
    ]
    assert len(seg2_matches_for_broadcast) == 1, "expected 1 match for broadcast on seg 2"
    assert seg2_matches_for_broadcast[0]["term_target"] == "廣播"


def test_glossary_scan_violations_unchanged_when_zh_incorrect(file_with_translations, glossary_with_entries):
    """Existing violation behaviour preserved — when ZH lacks term, row goes to violations."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()

    seg0_violations = [v for v in _all_violations(data) if v["seg_idx"] == 0]
    seg0_terms = sorted(v["term_source"] for v in seg0_violations)
    assert seg0_terms == ["anchor", "broadcast"]


def test_glossary_scan_returns_reverted_count_field(file_with_translations, glossary_with_entries):
    """Response must include reverted_count field, default 0 when no stale applied_terms."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reverted_count" in data
    assert data["reverted_count"] == 0


def test_glossary_apply_appends_to_applied_terms(file_with_translations, glossary_with_entries, monkeypatch):
    """After a successful LLM apply, the (term_source, term_target) tuple appears in applied_terms."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    from translation import ollama_engine

    def fake_apply(**kwargs):
        return "主播現場報導了廣播內容"

    monkeypatch.setattr(ollama_engine, "apply_glossary_term", fake_apply)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [{"seg_idx": 0, "term_source": "broadcast", "term_target": "廣播"}],
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0.get("applied_terms"), f"applied_terms missing or empty: {seg0}"
    assert {"term_source": "broadcast", "term_target": "廣播"} in seg0["applied_terms"]


def test_manual_edit_resets_baseline_and_clears_applied_terms(file_with_translations):
    """PATCH translations/<idx> must set baseline_zh = new zh_text and clear applied_terms."""
    file_id, c, app_module = file_with_translations

    # Pre-state: segment has prior applied terms (simulating earlier glossary apply)
    app_module._file_registry[file_id]["translations"][0]["applied_terms"] = [
        {"term_source": "broadcast", "term_target": "廣播"}
    ]
    app_module._file_registry[file_id]["translations"][0]["baseline_zh"] = "原來嘅譯文"

    resp = c.patch(f"/api/files/{file_id}/translations/0",
                   data=json.dumps({"zh_text": "用戶手動改嘅譯文"}),
                   content_type="application/json")
    assert resp.status_code == 200
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0["zh_text"] == "用戶手動改嘅譯文"
    assert seg0["baseline_zh"] == "用戶手動改嘅譯文", "manual edit must become new baseline"
    assert seg0["applied_terms"] == [], "applied_terms must reset on manual edit"


def test_scan_reverts_segments_with_stale_applied_terms(file_with_translations, glossary_with_entries):
    """Segment whose applied_terms contains an entry not in current glossary reverts to baseline_target."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Pre-state: segment 0 was previously modified by a glossary entry that has since been deleted
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "已被詞彙修改過嘅譯文"
    app_module._file_registry[file_id]["translations"][0]["baseline_target"] = "原始譯文"
    app_module._file_registry[file_id]["translations"][0]["applied_terms"] = [
        {"term_source": "DeletedTerm", "term_target": "刪除咗嘅"}  # not in glossary_with_entries
    ]

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reverted_count"] == 1

    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0["zh_text"] == "原始譯文"
    assert seg0["applied_terms"] == []


def test_scan_does_not_revert_when_all_applied_still_present(file_with_translations, glossary_with_entries):
    """Segment whose applied_terms all exist in current glossary stays untouched."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "現有譯文"
    app_module._file_registry[file_id]["translations"][0]["baseline_target"] = "原始譯文"
    app_module._file_registry[file_id]["translations"][0]["applied_terms"] = [
        {"term_source": "broadcast", "term_target": "廣播"}  # exists in glossary_with_entries
    ]

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()
    assert data["reverted_count"] == 0
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0["zh_text"] == "現有譯文", "untouched when applied_terms still valid"


def test_scan_legacy_segment_without_applied_terms_field_is_safe(file_with_translations, glossary_with_entries):
    """Segment that pre-dates the feature (no applied_terms field) must not error or revert."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Confirm the field genuinely is missing on a fresh fixture segment
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert "applied_terms" not in seg0
    original_zh = seg0["zh_text"]

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reverted_count"] == 0
    assert app_module._file_registry[file_id]["translations"][0]["zh_text"] == original_zh


# ============================================================
# Word-boundary matching (prevents "US" matching "must" etc.)
# ============================================================

@pytest.fixture
def file_with_us_segments(client):
    """File whose EN texts contain 'must' / 'trust' / 'the US' to test boundaries."""
    c, app_module = client
    file_id = f"test-{uuid.uuid4().hex[:8]}"
    app_module._file_registry[file_id] = {
        "id": file_id,
        "original_name": "us.mp4",
        "status": "done",
        "translation_status": "done",
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "We must trust the process"},   # 0: NO match (must, trust contain "us")
            {"start": 2.0, "end": 4.0, "text": "He has been in the US for days"},  # 1: match
            {"start": 4.0, "end": 6.0, "text": "USA is a country"},             # 2: NO match (USA contains "US")
            {"start": 6.0, "end": 8.0, "text": "Visit US."},                    # 3: match (period after)
        ],
        "translations": [
            {"zh_text": "我們必須相信這個過程", "status": "pending"},
            {"zh_text": "他已經在那裡好多日", "status": "pending"},
            {"zh_text": "美利堅合眾國係一個國家", "status": "pending"},
            {"zh_text": "去訪問。", "status": "pending"},
        ],
    }
    yield file_id, c, app_module
    app_module._file_registry.pop(file_id, None)


@pytest.fixture
def glossary_with_us(client):
    """Glossary with single 'US' entry (v3.x multilingual schema)."""
    c, app_module = client
    glossary_id = f"us-glossary-{uuid.uuid4().hex[:8]}"
    app_module._glossary_manager._write_glossary(glossary_id, {
        "id": glossary_id,
        "name": "US Glossary",
        "description": "Boundary test",
        "source_lang": "en",
        "target_lang": "zh",
        "entries": [{"id": "e1", "source": "US", "target": "美國"}],
        "created_at": 0,
        "updated_at": 0,
    })
    yield glossary_id, c, app_module
    try:
        app_module._glossary_manager.delete(glossary_id)
    except Exception:
        pass


def test_scan_us_does_not_match_inside_must_or_trust(file_with_us_segments, glossary_with_us):
    """'US' in glossary must NOT match the 'us' substring in 'must', 'trust', 'USA'."""
    file_id, c, _ = file_with_us_segments
    glossary_id, _, _ = glossary_with_us

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()

    all_hits = _all_violations(data) + data["matches"]

    # seg 0 ("We must trust the process") must NOT have any violation/match
    seg0_hits = [v for v in all_hits if v["seg_idx"] == 0]
    assert seg0_hits == [], f"'US' should not match 'must'/'trust', got: {seg0_hits}"

    # seg 2 ("USA is a country") must NOT match (USA contains US)
    seg2_hits = [v for v in all_hits if v["seg_idx"] == 2]
    assert seg2_hits == [], f"'US' should not match 'USA', got: {seg2_hits}"


def test_scan_us_matches_at_word_boundary(file_with_us_segments, glossary_with_us):
    """'US' must match 'the US for days' (surrounded by spaces) and 'Visit US.' (period after)."""
    file_id, c, _ = file_with_us_segments
    glossary_id, _, _ = glossary_with_us

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()

    all_hits = _all_violations(data) + data["matches"]
    seg_idxs_hit = sorted({h["seg_idx"] for h in all_hits})
    assert seg_idxs_hit == [1, 3], (
        f"expected matches on seg 1 (the US) and seg 3 (Visit US.), got: {seg_idxs_hit}"
    )


def test_scan_term_with_space_still_matches(file_with_translations, client):
    """Multi-word terms ('Real Madrid') must still work after the boundary fix."""
    file_id, c, app_module = file_with_translations
    glossary_id = f"rm-glossary-{uuid.uuid4().hex[:8]}"
    app_module._glossary_manager._write_glossary(glossary_id, {
        "id": glossary_id,
        "name": "RM Glossary",
        "description": "Multi-word test",
        "source_lang": "en",
        "target_lang": "zh",
        "entries": [{"id": "e1", "source": "Real Madrid", "target": "皇家馬德里"}],
        "created_at": 0,
        "updated_at": 0,
    })
    # Patch a segment to contain "Real Madrid"
    app_module._file_registry[file_id]["segments"][0]["text"] = "Real Madrid won the cup"
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "皇馬贏得了獎盃"

    try:
        resp = c.post(f"/api/files/{file_id}/glossary-scan",
                      data=json.dumps({"glossary_id": glossary_id}),
                      content_type="application/json")
        data = resp.get_json()
        seg0_violations = [v for v in _all_violations(data) if v["seg_idx"] == 0]
        assert len(seg0_violations) == 1
        assert seg0_violations[0]["term_source"] == "Real Madrid"
    finally:
        try:
            app_module._glossary_manager.delete(glossary_id)
        except Exception:
            pass


def test_scan_uppercase_term_does_not_match_lowercase_pronoun(file_with_us_segments, glossary_with_us):
    """'US' (acronym) must NOT match the pronoun 'us' (lowercase) — case-sensitive."""
    file_id, c, app_module = file_with_us_segments
    glossary_id, _, _ = glossary_with_us

    # Add a segment with the pronoun 'us'
    app_module._file_registry[file_id]["segments"].append(
        {"start": 8.0, "end": 10.0, "text": "give it to us"}
    )
    app_module._file_registry[file_id]["translations"].append(
        {"zh_text": "畀我哋", "status": "pending"}
    )

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()

    pronoun_seg_idx = 4
    all_hits = _all_violations(data) + data["matches"]
    pronoun_hits = [v for v in all_hits if v["seg_idx"] == pronoun_seg_idx]
    assert pronoun_hits == [], (
        f"'US' (uppercase) should NOT match 'us' (pronoun, lowercase), got: {pronoun_hits}"
    )


def test_scan_lowercase_term_is_case_insensitive(file_with_translations, client):
    """Lowercase terms ('broadcast') stay case-insensitive — 'Broadcast' must still match."""
    file_id, c, app_module = file_with_translations
    glossary_id = f"bc-glossary-{uuid.uuid4().hex[:8]}"
    app_module._glossary_manager._write_glossary(glossary_id, {
        "id": glossary_id,
        "name": "BC Glossary",
        "description": "Lowercase term test",
        "source_lang": "en",
        "target_lang": "zh",
        "entries": [{"id": "e1", "source": "broadcast", "target": "廣播"}],
        "created_at": 0,
        "updated_at": 0,
    })
    # Patch a segment to contain capitalised 'Broadcast'
    app_module._file_registry[file_id]["segments"][0]["text"] = "Broadcast continues live"
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "繼續直播"

    try:
        resp = c.post(f"/api/files/{file_id}/glossary-scan",
                      data=json.dumps({"glossary_id": glossary_id}),
                      content_type="application/json")
        data = resp.get_json()
        all_hits = _all_violations(data) + data["matches"]
        seg0_hits = [v for v in all_hits if v["seg_idx"] == 0]
        assert len(seg0_hits) == 1, (
            f"lowercase term 'broadcast' should match 'Broadcast' case-insensitively, got: {seg0_hits}"
        )
    finally:
        try:
            app_module._glossary_manager.delete(glossary_id)
        except Exception:
            pass
