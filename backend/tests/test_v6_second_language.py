"""Tests for V6 on-demand second-language translation.

POST /api/files/<file_id>/translate-second enqueues a translate job
that calls _translate_second_handler, which uses TranslatorStage (v5
infra) to add by_lang[target] + <target>_text to each translation row.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, _file_registry, _registry_lock, _translate_second_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_v6_entry(file_id, source_lang="zh"):
    """Minimal V6 file registry entry with one refined translation row."""
    zh_text = "各位晚上好。"
    return {
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
                "start": 0.0,
                "end": 2.5,
                "source_lang": source_lang,
                "source_text": zh_text,
                f"{source_lang}_text": zh_text,
                "by_lang": {
                    source_lang: {"text": zh_text, "status": "approved"},
                },
                "status": "approved",
                "flags": [],
            },
        ],
        "translation_status": "done",
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with auth bypass + isolated profile manager."""
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    app.config["TESTING"] = True
    app.config["R5_AUTH_BYPASS"] = True
    with app.test_client() as c:
        yield c
    app.config.pop("R5_AUTH_BYPASS", None)


# ---------------------------------------------------------------------------
# Test 1 — POST translate-second on a V6 zh-source file → 202 with job_id
# ---------------------------------------------------------------------------

def test_translate_second_enqueues_job(client):
    """POST translate-second with lang=en on a zh-source V6 file → 202."""
    fid = "ts-test-001"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, source_lang="zh")
    try:
        resp = client.post(
            f"/api/files/{fid}/translate-second",
            json={"lang": "en"},
            content_type="application/json",
        )
        assert resp.status_code == 202, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["file_id"] == fid
        assert "job_id" in body
        assert body["job_id"]  # non-empty
        assert body["target_lang"] == "en"
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# Test 2 — Handler writes by_lang.en + en_text with stubbed TranslatorStage
# ---------------------------------------------------------------------------

def test_translate_second_handler_writes_bylang(monkeypatch):
    """_translate_second_handler writes by_lang[en] + en_text on translations."""
    fid = "ts-test-002"
    entry = _make_v6_entry(fid, source_lang="zh")
    entry["_pending_second_lang"] = "en"

    with _registry_lock:
        _file_registry[fid] = entry

    # Stub TranslatorStage.transform to return EN prefixed text
    def fake_transform(self, segments_in, context):
        return [
            {"start": s["start"], "end": s["end"], "text": "EN:" + s["text"], "flags": []}
            for s in segments_in
        ]

    # Stub llm_profile manager to return a minimal profile so the handler
    # doesn't fail on the real FS lookup in test environments.
    fake_llm_profile = {
        "id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
        "name": "stub",
        "backend": "ollama",
        "model": "qwen3.5:35b-a3b-mlx-bf16",
        "base_url": "http://localhost:11434",
        "temperature": 0.2,
    }

    try:
        with patch(
            "stages.v5.translator_stage.TranslatorStage.transform",
            fake_transform,
        ), patch("app._llm_profile_manager") as mock_lpm:
            mock_lpm.get.return_value = fake_llm_profile
            fake_job = {"file_id": fid, "id": "fake-job-id", "user_id": 1}
            _translate_second_handler(fake_job, cancel_event=None)

        with _registry_lock:
            updated = _file_registry.get(fid, {})

        translations = updated.get("translations", [])
        assert len(translations) == 1

        row = translations[0]
        # by_lang[en] must exist
        by_lang = row.get("by_lang", {})
        assert "en" in by_lang, f"by_lang missing 'en' key: {by_lang}"
        assert by_lang["en"]["text"].startswith("EN:")
        assert by_lang["en"]["status"] == "pending"

        # en_text mirror must exist
        assert "en_text" in row, f"en_text mirror missing: {row.keys()}"
        assert row["en_text"].startswith("EN:")

        # _pending_second_lang must be cleared
        assert "_pending_second_lang" not in updated, (
            "_pending_second_lang should be cleared after handler completes"
        )
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# Test 3 — lang == source_lang → 400
# ---------------------------------------------------------------------------

def test_translate_second_same_lang_rejected(client):
    """POST translate-second with lang == source_lang → 400."""
    fid = "ts-test-003"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, source_lang="zh")
    try:
        resp = client.post(
            f"/api/files/{fid}/translate-second",
            json={"lang": "zh"},
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "same as source_lang" in body.get("error", "")
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# Test 4 — unsupported direction (no template) → 400
# ---------------------------------------------------------------------------

def test_translate_second_unsupported_direction(client):
    """POST translate-second with lang=ja (no template) → 400."""
    fid = "ts-test-004"
    with _registry_lock:
        _file_registry[fid] = _make_v6_entry(fid, source_lang="zh")
    try:
        resp = client.post(
            f"/api/files/{fid}/translate-second",
            json={"lang": "ja"},
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "未支援嘅語言方向" in body.get("error", "")
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# Test 5 — Profile-kind file → 400
# ---------------------------------------------------------------------------

def test_translate_second_rejects_profile_file(client):
    """POST translate-second on a Profile (non-V6) file → 400."""
    fid = "ts-test-005"
    profile_entry = {
        "id": fid,
        "original_name": "test.mp4",
        "stored_name": "test.mp4",
        "size": 1000,
        "status": "done",
        "uploaded_at": 1700000000,
        "active_kind": "profile",
        "active_id": None,
        "segments": [{"id": 0, "start": 0.0, "end": 2.0, "text": "Hello."}],
        "translations": [
            {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。",
             "status": "approved", "flags": []},
        ],
        "translation_status": "done",
    }
    with _registry_lock:
        _file_registry[fid] = profile_entry
    try:
        resp = client.post(
            f"/api/files/{fid}/translate-second",
            json={"lang": "en"},
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "V6" in body.get("error", "")
    finally:
        with _registry_lock:
            _file_registry.pop(fid, None)
