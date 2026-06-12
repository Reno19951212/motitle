"""Route tests for the proofread glossary-review feature (spec 2026-06-12 §4).

Covers (this file grows across Tasks 4-6):
* Task 4 — POST /api/files/<id>/glossary-preview (pure dry-run scan).

Run:
    cd backend && FLASK_SECRET_KEY=test-secret R5_AUTH_BYPASS=1 \
        ./venv/bin/python -m pytest tests/test_glossary_review_routes.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Inline glossary used across the suite. source_lang=en, target_lang=zh so it
# routes 'target' on a yue (pass) track via the canonical/alias on the zh side,
# and 'source' on an en-content mt track.
# ---------------------------------------------------------------------------
_GLOSSARY = {
    "id": "g-1",
    "name": "賽馬",
    "source_lang": "en",
    "target_lang": "zh",
    "entries": [
        {"id": "e-1", "source": "Happy Valley", "target": "跑馬地",
         "target_aliases": ["快活谷"]},
    ],
}


class _GM:
    """Minimal glossary-manager stub: .get(id) -> glossary dict or None."""

    def __init__(self, glossaries):
        self._by_id = {g["id"]: g for g in glossaries}

    def get(self, gid):
        return self._by_id.get(gid)


def _output_lang_entry(fid):
    """Build a yue→[yue,en] output_lang registry entry.

    The yue track carries the alias 「快活谷」 (a fix → should canonicalize to
    「跑馬地」); the en track is mt with no source-term hit (no fix).
    """
    return {
        "id": fid,
        "active_kind": "output_lang",
        "source_language": "yue",
        "script": "trad",
        "output_languages": ["yue", "en"],
        "content_asr_segments": [
            {"start": 0.0, "end": 2.0, "text": "快活谷今晚有賽事。"},
        ],
        "glossary_ids": ["g-1"],
        "glossary_llm": True,
        "translations": [
            {
                "idx": 0,
                "start": 0.0,
                "end": 2.0,
                "status": "pending",
                "by_lang": {
                    "yue": {"text": "快活谷今晚有賽事。", "status": "pending", "flags": []},
                    "en": {"text": "Races at Happy Valley tonight.", "status": "pending", "flags": []},
                },
                "yue_text": "快活谷今晚有賽事。",
                "en_text": "Races at Happy Valley tonight.",
                "glossary_changes": [],
            },
        ],
        "aligned_bilingual": [
            {"start": 0.0, "end": 2.0,
             "by_lang": {"yue": "快活谷今晚有賽事。", "en": "Races at Happy Valley tonight."}},
        ],
        "user_id": 1,
    }


@pytest.fixture
def client_with_entry(monkeypatch):
    """(client, fid, app_module) with a yue→[yue,en] output_lang entry seeded
    + a glossary manager stub. The autouse conftest fixture already enables
    R5_AUTH_BYPASS so @require_file_owner short-circuits."""
    import app as _app
    monkeypatch.setattr(_app, "_glossary_manager", _GM([_GLOSSARY]))
    fid = "glreview-ol"
    with _app._registry_lock:
        _app._file_registry[fid] = _output_lang_entry(fid)
    try:
        yield _app.app.test_client(), fid, _app
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


@pytest.fixture
def client_with_profile_entry(monkeypatch):
    """(client, fid) with a non-output_lang (profile) entry — exercises the
    active_kind gate (400)."""
    import app as _app
    monkeypatch.setattr(_app, "_glossary_manager", _GM([_GLOSSARY]))
    fid = "glreview-profile"
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "profile", "user_id": 1,
        }
    try:
        yield _app.app.test_client(), fid
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


# ===========================================================================
# Task 4 — POST /api/files/<id>/glossary-preview
# ===========================================================================

def test_preview_returns_tracks_and_is_pure(client_with_entry):
    client, fid, app_module = client_with_entry
    import json as _json
    before = _json.dumps(app_module._file_registry[fid], sort_keys=True, ensure_ascii=False)
    r = client.post(f"/api/files/{fid}/glossary-preview", json={})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert {t["lang"] for t in body["tracks"]} == {"yue", "en"}
    yue = next(t for t in body["tracks"] if t["lang"] == "yue")
    fixes = [i for i in yue["items"] if i["kind"] == "fix"]
    assert fixes and fixes[0]["alias"] == "快活谷" and fixes[0]["canonical"] == "跑馬地"
    assert fixes[0]["entry_id"] == "e-1" and fixes[0]["glossary_id"] == "g-1"
    assert fixes[0]["idx"] == 0 and fixes[0]["start"] == 0.0
    assert fixes[0]["approved"] is False
    assert "totals" in body
    assert body["totals"]["fix"] >= 1
    after = _json.dumps(app_module._file_registry[fid], sort_keys=True, ensure_ascii=False)
    assert before == after   # 零副作用


def test_preview_rejects_non_output_lang(client_with_profile_entry):
    client, fid = client_with_profile_entry
    r = client.post(f"/api/files/{fid}/glossary-preview", json={})
    assert r.status_code == 400


def test_preview_unknown_glossary_override_400(client_with_entry):
    client, fid, _ = client_with_entry
    r = client.post(f"/api/files/{fid}/glossary-preview",
                    json={"glossary_ids": ["no-such-id"]})
    assert r.status_code == 400


def test_preview_missing_file_404(client_with_entry):
    client, _fid, _ = client_with_entry
    r = client.post("/api/files/does-not-exist/glossary-preview", json={})
    assert r.status_code == 404


def test_preview_approved_row_flag_passthrough(client_with_entry):
    client, fid, app_module = client_with_entry
    with app_module._registry_lock:
        app_module._file_registry[fid]["translations"][0]["status"] = "approved"
    r = client.post(f"/api/files/{fid}/glossary-preview", json={})
    assert r.status_code == 200
    yue = next(t for t in r.get_json()["tracks"] if t["lang"] == "yue")
    fixes = [i for i in yue["items"] if i["kind"] == "fix"]
    assert fixes and fixes[0]["approved"] is True
