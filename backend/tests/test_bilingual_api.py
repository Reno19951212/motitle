"""Tests for Task 2a/2b: languages descriptor, role-aware render/export, PATCH role param."""
import json
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, _file_registry, _registry_lock
from subtitle_text import resolve_language_descriptor
from app import _role_fields_for  # type: ignore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Minimal client with auth bypass + isolated profile manager."""
    from profiles import ProfileManager
    new_prof_mgr = ProfileManager(tmp_path)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)
    app.config["TESTING"] = True
    app.config["R5_AUTH_BYPASS"] = True
    with app.test_client() as c:
        yield c
    app.config.pop("R5_AUTH_BYPASS", None)


def _make_profile_entry(file_id, en_text="Good evening.", zh_text="各位晚上好。",
                        extra_fields=None):
    """Build a minimal Profile-kind file registry entry."""
    entry = {
        "id": file_id,
        "original_name": "test.mp4",
        "stored_name": "test.mp4",
        "size": 1000,
        "status": "done",
        "uploaded_at": 1700000000,
        "active_kind": "profile",
        "active_id": None,
        "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": en_text}],
        "text": en_text,
        "error": None,
        "model": "large-v3",
        "backend": "mlx-whisper",
        "translations": [
            {
                "start": 0.0, "end": 2.5,
                "en_text": en_text, "zh_text": zh_text,
                "status": "approved", "flags": [],
            },
        ],
        "translation_status": "done",
    }
    if extra_fields:
        entry.update(extra_fields)
    return entry


def _make_v6_entry(file_id, zh_text="各位晚上好。", source_lang="zh",
                   extra_fields=None):
    """Build a minimal V6-kind file registry entry."""
    entry = {
        "id": file_id,
        "original_name": "test.mp4",
        "stored_name": "test.mp4",
        "size": 1000,
        "status": "done",
        "uploaded_at": 1700000000,
        "active_kind": "pipeline_v6",
        "active_id": None,
        "active_pipeline_snapshot": None,
        "segments": [],
        "text": zh_text,
        "error": None,
        "translations": [
            {
                "start": 0.0, "end": 2.5,
                "source_lang": source_lang,
                "source_text": zh_text,
                f"{source_lang}_text": zh_text,
                "zh_text": zh_text,
                "by_lang": {
                    source_lang: {"text": zh_text, "status": "approved"},
                },
                "status": "approved", "flags": [],
            },
        ],
        "translation_status": "done",
    }
    if extra_fields:
        entry.update(extra_fields)
    return entry


# ---------------------------------------------------------------------------
# TASK 2a — /api/files languages field
# ---------------------------------------------------------------------------

def test_list_files_includes_languages_for_profile(client):
    """GET /api/files includes 'languages' list for a Profile-kind file."""
    fid = "lang-desc-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid)
    try:
        resp = client.get("/api/files")
        assert resp.status_code == 200
        files = resp.get_json()["files"]
        entry = next((f for f in files if f["id"] == fid), None)
        assert entry is not None, "File not in response"
        langs = entry.get("languages")
        assert langs is not None, "languages key missing"
        assert isinstance(langs, list)
        # Profile: 2 roles — first (原文) + second (譯文/zh)
        assert len(langs) == 2
        roles = {d["role"] for d in langs}
        assert "first" in roles
        assert "second" in roles
        # second must be zh
        second = next(d for d in langs if d["role"] == "second")
        assert second["lang"] == "zh"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_list_files_includes_languages_for_v6_single_lang(client):
    """GET /api/files languages for V6 zh-source file — 1 role only."""
    fid = "lang-desc-v6-001"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, source_lang="zh")
    try:
        resp = client.get("/api/files")
        assert resp.status_code == 200
        files = resp.get_json()["files"]
        entry = next((f for f in files if f["id"] == fid), None)
        assert entry is not None
        langs = entry["languages"]
        assert len(langs) == 1
        assert langs[0]["role"] == "first"
        assert langs[0]["lang"] == "zh"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# TASK 2a — GET /api/files/<id>/languages endpoint
# ---------------------------------------------------------------------------

def test_get_file_languages_profile(client):
    """GET /api/files/<id>/languages returns 2-role descriptor for Profile file."""
    fid = "lang-ep-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid)
    try:
        resp = client.get(f"/api/files/{fid}/languages")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "languages" in data
        langs = data["languages"]
        assert len(langs) == 2
        assert langs[0]["role"] == "first"
        assert langs[1]["role"] == "second"
        assert langs[1]["lang"] == "zh"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_get_file_languages_v6(client):
    """GET /api/files/<id>/languages returns 1-role descriptor for V6 zh-source."""
    fid = "lang-ep-v6-001"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, source_lang="zh")
    try:
        resp = client.get(f"/api/files/{fid}/languages")
        assert resp.status_code == 200
        data = resp.get_json()
        langs = data["languages"]
        assert len(langs) == 1
        assert langs[0]["lang"] == "zh"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_get_file_languages_404(client):
    """GET /api/files/<missing>/languages returns 404."""
    resp = client.get("/api/files/no-such-file/languages")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TASK 2b — _role_fields_for helper
# ---------------------------------------------------------------------------

def test_role_fields_for_profile():
    """Profile entry → (None, 'zh_text')."""
    entry = {"active_kind": "profile"}
    first, second = _role_fields_for(entry)
    assert first is None
    assert second == "zh_text"


def test_role_fields_for_v6_zh_source():
    """V6 zh-source with no second lang → ('zh_text', None)."""
    entry = {
        "active_kind": "pipeline_v6",
        "translations": [
            {
                "source_lang": "zh",
                "by_lang": {"zh": {"text": "你好", "status": "approved"}},
            }
        ],
    }
    first, second = _role_fields_for(entry)
    assert first == "zh_text"
    assert second is None


def test_role_fields_for_v6_en_source_with_zh_second():
    """V6 en-source with zh by_lang → ('en_text', 'zh_text')."""
    entry = {
        "active_kind": "pipeline_v6",
        "translations": [
            {
                "source_lang": "en",
                "by_lang": {
                    "en": {"text": "Hello", "status": "approved"},
                    "zh": {"text": "你好", "status": "approved"},
                },
            }
        ],
    }
    first, second = _role_fields_for(entry)
    assert first == "en_text"
    assert second == "zh_text"


def test_role_fields_for_empty_entry():
    """Empty/None entry falls back to Profile defaults."""
    first, second = _role_fields_for({})
    assert first is None
    assert second == "zh_text"

    first2, second2 = _role_fields_for(None)
    assert first2 is None
    assert second2 == "zh_text"


# ---------------------------------------------------------------------------
# TASK 2b — export subtitle with first/second mode
# ---------------------------------------------------------------------------

def test_export_srt_with_source_first_profile(client):
    """Export SRT source=first for Profile file returns en_text (first role)."""
    fid = "export-first-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, en_text="Good evening.", zh_text="各位晚上好。")
    try:
        resp = client.get(f"/api/files/{fid}/subtitle.srt?source=first")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Good evening." in body
        assert "各位晚上好。" not in body
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_export_srt_with_source_second_profile(client):
    """Export SRT source=second for Profile file returns zh_text (second role)."""
    fid = "export-second-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, en_text="Good evening.", zh_text="各位晚上好。")
    try:
        resp = client.get(f"/api/files/{fid}/subtitle.srt?source=second")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "各位晚上好。" in body
        assert "Good evening." not in body
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_export_srt_with_source_first_v6(client):
    """Export SRT source=first for V6 zh-source returns zh_text (first/refiner role)."""
    fid = "export-first-v6-001"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, zh_text="各位晚上好。", source_lang="zh")
    try:
        resp = client.get(f"/api/files/{fid}/subtitle.srt?source=first")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "各位晚上好。" in body
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_export_srt_legacy_en_still_works(client):
    """Export SRT source=en (legacy) still returns en_text."""
    fid = "export-legacy-en-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, en_text="Good evening.", zh_text="各位晚上好。")
    try:
        resp = client.get(f"/api/files/{fid}/subtitle.srt?source=en")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Good evening." in body
        assert "各位晚上好。" not in body
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_export_srt_legacy_zh_still_works(client):
    """Export SRT source=zh (legacy) still returns zh_text."""
    fid = "export-legacy-zh-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, en_text="Good evening.", zh_text="各位晚上好。")
    try:
        resp = client.get(f"/api/files/{fid}/subtitle.srt?source=zh")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "各位晚上好。" in body
        assert "Good evening." not in body
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# TASK 2b — render with source=first/second accepted (no 400 from role guard)
# ---------------------------------------------------------------------------

def test_render_source_first_profile_accepted(client, tmp_path, monkeypatch):
    """POST /api/render with subtitle_source=first on Profile file returns 202."""
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"\x00" * 64)
    fid = "render-first-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid)
        _file_registry[fid]["stored_name"] = "test.mp4"
    try:
        resp = client.post("/api/render", json={
            "file_id": fid,
            "format": "mp4",
            "subtitle_source": "first",
        })
        assert resp.status_code == 202, resp.data
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_render_source_second_profile_accepted(client, tmp_path, monkeypatch):
    """POST /api/render with subtitle_source=second on Profile file returns 202."""
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"\x00" * 64)
    fid = "render-second-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid)
        _file_registry[fid]["stored_name"] = "test.mp4"
    try:
        resp = client.post("/api/render", json={
            "file_id": fid,
            "format": "mp4",
            "subtitle_source": "second",
        })
        assert resp.status_code == 202, resp.data
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_render_source_first_v6_zh_accepted(client, tmp_path, monkeypatch):
    """POST /api/render subtitle_source=first on V6 zh-source → 202 (first=zh_text)."""
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"\x00" * 64)
    fid = "render-first-v6-001"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, zh_text="各位晚上好。", source_lang="zh")
        _file_registry[fid]["stored_name"] = "test.mp4"
    try:
        resp = client.post("/api/render", json={
            "file_id": fid,
            "format": "mp4",
            "subtitle_source": "first",
        })
        assert resp.status_code == 202, resp.data
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_render_source_first_v6_no_content_rejected(client, tmp_path, monkeypatch):
    """POST /api/render subtitle_source=first on V6 file with empty first-role → 400."""
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"\x00" * 64)
    fid = "render-first-empty-v6-001"
    # V6 zh-source but zh_text is empty — first role has no content
    empty_entry = _make_v6_entry(fid, zh_text="", source_lang="zh")
    # Also blank out the by_lang text
    empty_entry["translations"][0]["zh_text"] = ""
    empty_entry["translations"][0]["zh_text"] = ""
    empty_entry["translations"][0]["by_lang"]["zh"]["text"] = ""
    empty_entry["stored_name"] = "test.mp4"
    with _registry_lock:
        _file_registry[fid] = empty_entry
    try:
        resp = client.post("/api/render", json={
            "file_id": fid,
            "format": "mp4",
            "subtitle_source": "first",
        })
        assert resp.status_code == 400, resp.data
        assert "first-role" in resp.get_json().get("error", "").lower() or "first" in resp.get_json().get("error", "")
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# TASK 2b — PATCH translations role param
# ---------------------------------------------------------------------------

def test_patch_translation_no_role_behaves_as_before(client):
    """No role → writes zh_text exactly as legacy behavior."""
    fid = "patch-no-role-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, zh_text="舊翻譯")
    try:
        resp = client.patch(
            f"/api/files/{fid}/translations/0",
            json={"zh_text": "新翻譯"},
        )
        assert resp.status_code == 200
        t = resp.get_json()["translation"]
        assert t["zh_text"] == "新翻譯"
        # flags cleared, status approved
        assert t["flags"] == []
        assert t["status"] == "approved"
        # registry updated
        with _registry_lock:
            stored = _file_registry[fid]["translations"][0]
        assert stored["zh_text"] == "新翻譯"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_patch_translation_role_second_behaves_as_no_role(client):
    """role='second' → same as no role: writes zh_text."""
    fid = "patch-second-role-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, zh_text="舊翻譯")
    try:
        resp = client.patch(
            f"/api/files/{fid}/translations/0",
            json={"zh_text": "新翻譯2", "role": "second"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["translation"]["zh_text"] == "新翻譯2"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_patch_translation_role_first_profile_writes_en_text(client):
    """role='first' on Profile file writes en_text."""
    fid = "patch-first-profile-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid, en_text="Good evening.")
    try:
        resp = client.patch(
            f"/api/files/{fid}/translations/0",
            json={"zh_text": "New EN text", "role": "first"},
        )
        assert resp.status_code == 200
        t = resp.get_json()["translation"]
        assert t["en_text"] == "New EN text"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_patch_translation_role_first_v6_writes_refiner_field(client):
    """role='first' on V6 zh-source writes zh_text (refiner field) + by_lang dual-write."""
    fid = "patch-first-v6-001"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, zh_text="舊細節", source_lang="zh")
    try:
        resp = client.patch(
            f"/api/files/{fid}/translations/0",
            json={"zh_text": "新細節", "role": "first"},
        )
        assert resp.status_code == 200
        t = resp.get_json()["translation"]
        assert t["zh_text"] == "新細節"
        # by_lang should also be updated
        with _registry_lock:
            stored = _file_registry[fid]["translations"][0]
        assert stored.get("by_lang", {}).get("zh", {}).get("text") == "新細節"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_patch_translation_invalid_role_returns_400(client):
    """Invalid role value returns 400."""
    fid = "patch-bad-role-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid)
    try:
        resp = client.patch(
            f"/api/files/{fid}/translations/0",
            json={"zh_text": "text", "role": "third"},
        )
        assert resp.status_code == 400
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


def test_patch_translation_missing_text_returns_400(client):
    """No zh_text or text field → 400 (unchanged from legacy)."""
    fid = "patch-missing-text-001"
    with _registry_lock:
        _file_registry[fid] = _make_profile_entry(fid)
    try:
        resp = client.patch(
            f"/api/files/{fid}/translations/0",
            json={"role": "second"},
        )
        assert resp.status_code == 400
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)
