"""Task 7 — /api/transcribe accepts source_language + script (authoritative
cross-language routing fields), stored on the file registry entry.

These fields are only meaningful in output_lang mode (i.e. when output_languages
is supplied).  The 202 success path reads current_user.id, so we authenticate a
real admin session (mirroring client_with_admin in test_asr_handler_pipeline.py)
rather than relying on LOGIN_DISABLED, under which current_user is anonymous and
has no .id.
"""
import io
import os
import json

os.environ.setdefault("R5_AUTH_BYPASS", "1")

import pytest

import app as _app


@pytest.fixture
def client():
    """Real logged-in admin client so current_user.id resolves on the 202 path."""
    from auth.users import init_db, create_user

    db_path = _app.app.config["AUTH_DB_PATH"]
    init_db(db_path)
    try:
        create_user(db_path, "crosslang_t7", "TestPass1!", is_admin=True)
    except ValueError:
        pass  # already exists from a prior run — fine
    c = _app.app.test_client()
    r = c.post("/login", json={"username": "crosslang_t7", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    return c


def test_transcribe_stores_source_language_and_script(client, monkeypatch):
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    data = {"output_languages": json.dumps(["yue", "en"]), "source_language": "yue", "script": "simp",
            "file": (io.BytesIO(b"x"), "clip.mp4")}
    r = client.post("/api/transcribe", data=data, content_type="multipart/form-data")
    assert r.status_code == 202, r.get_data(as_text=True)
    fid = r.get_json()["file_id"]
    entry = _app._file_registry[fid]
    assert entry["source_language"] == "yue"
    assert entry["script"] == "simp"
    assert entry["output_languages"] == ["yue", "en"]


def test_transcribe_rejects_bad_source_language(client, monkeypatch):
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    data = {"output_languages": json.dumps(["yue"]), "source_language": "klingon",
            "file": (io.BytesIO(b"x"), "clip.mp4")}
    r = client.post("/api/transcribe", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_transcribe_defaults_script_trad(client, monkeypatch):
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    data = {"output_languages": json.dumps(["zh"]), "source_language": "cmn",
            "file": (io.BytesIO(b"x"), "clip.mp4")}
    r = client.post("/api/transcribe", data=data, content_type="multipart/form-data")
    fid = r.get_json()["file_id"]
    assert _app._file_registry[fid]["script"] == "trad"
