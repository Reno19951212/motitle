# backend/tests/test_rerun_output_lang.py
# Regression: POST /api/files/<id>/transcribe (重試) must NOT clobber an
# output_lang file onto the currently-active V6/profile pipeline.
# Bug 2026-06-10: _resnapshot_active_for_rerun re-read settings.json's active
# (pipeline_v6) and overwrote active_kind + emptied output_languages, so a
# retry after an upload error silently changed the whole processing flow.
import os

os.environ.setdefault("R5_AUTH_BYPASS", "1")

import pytest

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client():
    """Real logged-in admin client — the 202 path reads current_user.id
    (mirrors test_crosslang_transcribe_api.py)."""
    from auth.users import init_db, create_user

    db_path = appmod.app.config["AUTH_DB_PATH"]
    init_db(db_path)
    try:
        create_user(db_path, "rerun_ol_t", "TestPass1!", is_admin=True)
    except ValueError:
        pass  # already exists from a prior run — fine
    c = appmod.app.test_client()
    r = c.post("/login", json={"username": "rerun_ol_t", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    return c


def _seed_errored_output_lang_file(tmp_path, fid="f-rerun-ol"):
    media = tmp_path / f"{fid}.mp4"
    media.write_bytes(b"\x00" * 64)
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "id": fid, "user_id": 1,
            "original_name": "clip.mp4", "stored_name": f"{fid}.mp4",
            "file_path": str(media),
            "status": "error", "error": "ffmpeg died",
            "active_kind": "output_lang", "active_id": "output_lang",
            "output_languages": ["yue", "en"],
            "source_language": "yue", "script": "trad", "mt_style": "generic",
            "glossary_ids": [], "glossary_llm": True,
            "segments": [], "translations": [],
        }
    return fid


def test_retry_preserves_output_lang_config(client, tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_errored_output_lang_file(tmp_path)
    monkeypatch.setattr(appmod._job_queue, "enqueue",
                        lambda **kw: "jid-test", raising=False)
    monkeypatch.setattr(appmod._job_queue, "position",
                        lambda jid: 0, raising=False)

    r = client.post(f"/api/files/{fid}/transcribe")
    assert r.status_code == 202, r.get_data(as_text=True)

    with appmod._registry_lock:
        entry = appmod._file_registry[fid]
        assert entry["active_kind"] == "output_lang"
        assert entry["output_languages"] == ["yue", "en"]
        assert entry["source_language"] == "yue"
