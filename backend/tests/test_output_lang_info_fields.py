"""output_lang 資訊 tab — /api/files exposes processing-time + language fields.

The home-page 資訊 (info) tab shows, for output_lang files only, the first/second
output language + per-pass Whisper processing time. The backend must surface:
  - asr_seconds                  (first-language pass wall-clock)
  - asr_output_second_seconds    (second-language pass wall-clock; null if single)
  - languages                    (role descriptor with human labels)
on each /api/files row. This test injects a finished dual-language output_lang
entry and asserts the row carries those fields.
"""
import os
import sqlite3

import pytest


@pytest.fixture
def alice_with_output_lang_file(request):
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username, update_password

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_ol", "TestPass1!", is_admin=False)
    except ValueError:
        update_password(db, "alice_ol", "TestPass1!")
    uid = get_user_by_username(db, "alice_ol")["id"]

    fake_id = "file-ol-info"
    dual = request.param  # True = dual language, False = single
    out_langs = ["yue", "en"] if dual else ["yue"]
    entry = {
        "id": fake_id, "user_id": uid, "stored_name": "x.wav",
        "file_path": "/tmp/ol_info_fake.wav", "status": "done",
        "original_name": "x.wav", "size": 0, "uploaded_at": 0.0,
        "segments": [], "text": "",
        "active_kind": "output_lang", "active_id": "output_lang",
        "output_languages": out_langs,
        "translation_status": "done", "translation_kind": "output_lang",
        "asr_seconds": 42.5,
    }
    if dual:
        entry["asr_output_second_seconds"] = 18.3
    with app_module._registry_lock:
        app_module._file_registry[fake_id] = entry
    open("/tmp/ol_info_fake.wav", "wb").close()

    c = app_module.app.test_client()
    assert c.post("/login", json={"username": "alice_ol", "password": "TestPass1!"}).status_code == 200
    yield c, fake_id, dual

    with app_module._registry_lock:
        app_module._file_registry.pop(fake_id, None)
    if os.path.exists("/tmp/ol_info_fake.wav"):
        os.remove("/tmp/ol_info_fake.wav")


def _row(client, file_id):
    r = client.get("/api/files")
    assert r.status_code == 200
    files = r.get_json().get("files", [])
    row = next((f for f in files if f["id"] == file_id), None)
    assert row is not None, f"file {file_id} not in /api/files"
    return row


@pytest.mark.parametrize("alice_with_output_lang_file", [True], indirect=True)
def test_dual_output_lang_row_has_timing_and_languages(alice_with_output_lang_file):
    client, fid, _ = alice_with_output_lang_file
    row = _row(client, fid)
    assert row["active_kind"] == "output_lang"
    assert row["asr_seconds"] == 42.5
    assert row["asr_output_second_seconds"] == 18.3
    langs = row["languages"]
    assert [l["role"] for l in langs] == ["first", "second"]
    assert langs[0]["lang"] == "yue" and langs[0]["label"] == "口語廣東話"
    assert langs[1]["lang"] == "en" and langs[1]["label"] == "英文"


@pytest.mark.parametrize("alice_with_output_lang_file", [False], indirect=True)
def test_single_output_lang_row_second_seconds_null(alice_with_output_lang_file):
    client, fid, _ = alice_with_output_lang_file
    row = _row(client, fid)
    assert row["asr_seconds"] == 42.5
    assert row["asr_output_second_seconds"] is None     # no 2nd pass for single
    assert len(row["languages"]) == 1
    assert row["languages"][0]["label"] == "口語廣東話"
