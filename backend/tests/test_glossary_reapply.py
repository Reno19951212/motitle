"""Tests for glossary-v2 Task 2.3 — POST /api/files/<id>/glossary-reapply.

Re-derives every output language from the cached content base (no ASR) so that
glossary before/after is meaningful + idempotent.

Run:
    cd backend && FLASK_SECRET_KEY=test-secret-only-for-pytest-do-not-deploy \
        R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_glossary_reapply.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# Inline en→zh racing glossary used across the suite.
_RACING_GLOSSARY = {
    "id": "racing-1",
    "name": "R",
    "source_lang": "en",
    "target_lang": "zh",
    "entries": [{"source": "BLAZING WUKONG", "target": "火悟空 (K335)"}],
}


def _glossary_llm(system, user):
    """Deterministic glossary-review LLM: canonicalize Blazing Wukong → 火悟空."""
    if "對照表" in user or "BLAZING WUKONG" in user.upper():
        return '{"text": "火悟空 領先"}'
    # crosslang_mt segment translation (en→zh): leave the name verbatim.
    if "Blazing Wukong leads" in user:
        return "Blazing Wukong 領先"
    return user


@pytest.fixture
def http_client(monkeypatch):
    # The autouse conftest fixture (_isolate_app_data) already sets
    # LOGIN_DISABLED + R5_AUTH_BYPASS on the imported app, so @require_file_owner
    # short-circuits without a real session. Use that same app instance (no
    # reload) so the bypass config stays applied.
    import app as _app
    # The reapply endpoint never enqueues, but guard the queue anyway.
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    monkeypatch.setattr(_app._job_queue, "position", lambda jid: 0)
    c = _app.app.test_client()
    return _app, c


def _seed(_app, fid, **overrides):
    entry = {
        "id": fid,
        "active_kind": "output_lang",
        "source_language": "en",
        "script": "trad",
        "output_languages": ["zh"],
        "content_asr_segments": [{"start": 0.0, "end": 1.0, "text": "Blazing Wukong leads"}],
        "glossary_ids": ["racing-1"],
        "glossary_llm": True,
        "translations": [],
        "user_id": 1,
    }
    entry.update(overrides)
    with _app._registry_lock:
        _app._file_registry[fid] = entry


def _cleanup(_app, fid):
    with _app._registry_lock:
        _app._file_registry.pop(fid, None)


# ===========================================================================
# Happy path — reapply re-derives from cached base + records fresh changes
# ===========================================================================

def test_reapply_rederives_and_records_changes(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return _RACING_GLOSSARY if gid == "racing-1" else None
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: _glossary_llm)

    fid = "reapply-ok"
    _seed(_app, fid)
    try:
        resp = c.post(f"/api/files/{fid}/glossary-reapply",
                      json={"glossary_ids": ["racing-1"], "glossary_llm": True})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["ok"] is True
        assert body["file_id"] == fid
        assert body["languages"] == ["zh"]
        assert body["changed_count"] >= 1

        entry = _app._file_registry[fid]
        rows = entry["translations"]
        assert len(rows) == 1
        # by_lang + {lang}_text mirror both updated with the canonical name.
        assert "火悟空" in rows[0]["by_lang"]["zh"]["text"]
        assert "火悟空" in rows[0]["zh_text"]
        # Fresh glossary_changes carried onto the row.
        assert isinstance(rows[0].get("glossary_changes"), list)
        assert len(rows[0]["glossary_changes"]) >= 1
        # Persisted glossary settings echo the request.
        assert entry["glossary_ids"] == ["racing-1"]
        assert entry["glossary_llm"] is True
    finally:
        _cleanup(_app, fid)


def test_reapply_defaults_to_stored_glossary_settings(http_client, monkeypatch):
    """Body omits glossary_ids/glossary_llm → fall back to the entry's stored values."""
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return _RACING_GLOSSARY if gid == "racing-1" else None
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: _glossary_llm)

    fid = "reapply-default"
    _seed(_app, fid)
    try:
        resp = c.post(f"/api/files/{fid}/glossary-reapply", json={})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["ok"] is True
        assert body["changed_count"] >= 1
        assert _app._file_registry[fid]["translations"][0]["by_lang"]["zh"]["text"].startswith("火悟空") \
            or "火悟空" in _app._file_registry[fid]["translations"][0]["by_lang"]["zh"]["text"]
    finally:
        _cleanup(_app, fid)


# ===========================================================================
# Empty glossary_ids → derives cleanly, no crash, no changes
# ===========================================================================

def test_reapply_empty_glossary_ids_derives_cleanly(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return None
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    # MT en→zh (no glossary stage): leave name verbatim.
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: "Blazing Wukong 領先"))

    fid = "reapply-empty"
    _seed(_app, fid, glossary_ids=[])
    try:
        resp = c.post(f"/api/files/{fid}/glossary-reapply",
                      json={"glossary_ids": []})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["ok"] is True
        assert body["changed_count"] == 0
        rows = _app._file_registry[fid]["translations"]
        assert len(rows) == 1
        # Clean re-derive: no glossary changes recorded.
        assert rows[0].get("glossary_changes", []) == []
        # Output still produced.
        assert rows[0]["by_lang"]["zh"]["text"] != ""
    finally:
        _cleanup(_app, fid)


# ===========================================================================
# Error envelopes
# ===========================================================================

def test_reapply_non_output_lang_file_400(http_client, monkeypatch):
    _app, c = http_client
    fid = "reapply-not-ol"
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "profile", "user_id": 1,
        }
    try:
        resp = c.post(f"/api/files/{fid}/glossary-reapply", json={})
        assert resp.status_code == 400, resp.get_data(as_text=True)
        assert "output_lang" in (resp.get_json().get("error") or "")
    finally:
        _cleanup(_app, fid)


def test_reapply_no_content_base_400(http_client, monkeypatch):
    _app, c = http_client
    fid = "reapply-no-base"
    _seed(_app, fid, content_asr_segments=None)
    try:
        resp = c.post(f"/api/files/{fid}/glossary-reapply", json={})
        assert resp.status_code == 400, resp.get_data(as_text=True)
        assert "內容語音快取" in (resp.get_json().get("error") or "")
    finally:
        _cleanup(_app, fid)


def test_reapply_unknown_glossary_id_400(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return None
    monkeypatch.setattr(_app, "_glossary_manager", _GM())

    fid = "reapply-bad-gid"
    _seed(_app, fid)
    try:
        resp = c.post(f"/api/files/{fid}/glossary-reapply",
                      json={"glossary_ids": ["badid"]})
        assert resp.status_code == 400, resp.get_data(as_text=True)
        assert "badid" in (resp.get_json().get("error") or "")
    finally:
        _cleanup(_app, fid)
