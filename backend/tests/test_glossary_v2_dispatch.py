"""Tests for glossary-v2 Task 2.1 + 2.2 — wiring glossary_stage into the
output_lang derive chain + dispatch + transcribe-handler glossary_ids entry.

Run:
    cd backend && FLASK_SECRET_KEY=test-secret-only-for-pytest-do-not-deploy \
        R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_glossary_v2_dispatch.py -q
"""
import importlib
import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Shared fixtures / fakes
# ---------------------------------------------------------------------------

# Tiny inline glossary used across the suite (en→zh racing).
_RACING_GLOSSARY = {
    "id": "racing-1",
    "name": "R",
    "source_lang": "en",
    "target_lang": "zh",
    "entries": [{"source": "BLAZING WUKONG", "target": "火悟空 (K335)"}],
}


def _mock_llm(system, user):
    """Mock LLM: canonicalize Blazing Wukong → 火悟空, echo otherwise."""
    if "BLAZING WUKONG" in user.upper():
        return '{"text": "火悟空"}'
    return '{"text": "' + user.split("中文：")[-1].strip() + '"}'


# ===========================================================================
# Task 2.1 — derive_aligned_output threads glossary_stage after OpenCC
# ===========================================================================

def test_derive_aligned_output_with_glossary_canonicalizes():
    """en→zh derive (mode='mt') with a racing glossary canonicalizes the
    horse name in the zh output and records glossary_changes on the segment."""
    import output_lang_aligned as ola

    base = [{"start": 0.0, "end": 2.0, "text": "Blazing Wukong shoots ahead"}]

    # MT path: crosslang_mt translate then glossary stage. We inject an LLM that
    # (a) translates EN→ZH (leaving the English name) and (b) canonicalizes it.
    def _llm(system, user):
        # crosslang_mt segment translation: emit Chinese keeping the name verbatim
        if "Blazing Wukong shoots ahead" in user and "對照表" not in user:
            return "Blazing Wukong 衝前"
        # glossary review prompt
        if "對照表" in user or "BLAZING WUKONG" in user.upper():
            return '{"text": "火悟空 衝前"}'
        return user

    out = ola.derive_aligned_output(
        base, "en", "zh", "trad", _llm, glossaries=[_RACING_GLOSSARY])

    assert len(out) == 1
    assert "火悟空" in out[0]["text"]
    changes = out[0].get("glossary_changes")
    assert isinstance(changes, list)
    assert len(changes) >= 1
    ch = changes[0]
    assert {"source", "before", "after", "glossary"} <= set(ch.keys())
    assert ch["after"] == "火悟空" or "火悟空" in ch["after"]


def test_derive_aligned_output_no_glossary_is_regression():
    """glossaries=None → byte-identical to the no-glossary path (backward-compat)."""
    import output_lang_aligned as ola

    base = [{"start": 0.0, "end": 2.0, "text": "Blazing Wukong shoots ahead"}]

    def _llm(system, user):
        return "火悟空 衝前"

    without = ola.derive_aligned_output(base, "en", "zh", "trad", _llm)
    with_none = ola.derive_aligned_output(base, "en", "zh", "trad", _llm, glossaries=None)

    assert without == with_none
    # No glossary_changes injected when glossaries not supplied.
    assert "glossary_changes" not in without[0]


def test_derive_aligned_output_empty_glossary_list_is_regression():
    """glossaries=[] (empty list) behaves like no glossary — no canonicalization,
    no glossary_changes key (regression with the None path)."""
    import output_lang_aligned as ola

    base = [{"start": 0.0, "end": 2.0, "text": "Blazing Wukong shoots ahead"}]

    def _llm(system, user):
        return "火悟空 衝前"

    none_out = ola.derive_aligned_output(base, "en", "zh", "trad", _llm)
    empty_out = ola.derive_aligned_output(base, "en", "zh", "trad", _llm, glossaries=[])
    assert none_out == empty_out


def test_build_aligned_bilingual_threads_glossary():
    """build_aligned_bilingual passes glossaries through to derive_aligned_output."""
    import output_lang_aligned as ola

    base = [{"start": 0.0, "end": 2.0, "text": "Blazing Wukong"}]

    def _llm(system, user):
        if "對照表" in user or "BLAZING WUKONG" in user.upper():
            return '{"text": "火悟空"}'
        if "Blazing Wukong" in user:
            return "Blazing Wukong"
        return user

    aligned = ola.build_aligned_bilingual(
        base, ["zh"], "en", "trad", _llm, glossaries=[_RACING_GLOSSARY])
    assert len(aligned) == 1
    assert "火悟空" in aligned[0]["by_lang"]["zh"]


# ===========================================================================
# Task 2.2 — dispatch loads glossaries + entry field + transcribe handler
# ===========================================================================

@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-only-for-pytest-do-not-deploy")
    import app as _a
    importlib.reload(_a)
    return _a


def test_run_output_lang_loads_and_threads_glossary(app_mod, monkeypatch):
    """A cross-language file entry carrying glossary_ids loads the glossary via
    _glossary_manager.get and threads it into the derive chain so the resulting
    translation row carries glossary_changes."""
    fid = "t-gl-run"
    base = [{"start": 0.0, "end": 1.0, "text": "Blazing Wukong leads"}]

    monkeypatch.setattr(app_mod, "transcribe_with_segments",
                        lambda *a, **k: {"segments": base})
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")

    def _llm(system, user):
        # crosslang_mt: leave name; glossary review: canonicalize
        if "對照表" in user or "BLAZING WUKONG" in user.upper():
            return '{"text": "火悟空 領先"}'
        if "Blazing Wukong leads" in user:
            return "Blazing Wukong 領先"
        return user

    monkeypatch.setattr(app_mod, "_make_ollama_llm_call", lambda: _llm)

    # Mock the glossary manager so glossary_ids resolve to our inline glossary.
    class _GM:
        def get(self, gid):
            return _RACING_GLOSSARY if gid == "racing-1" else None
    monkeypatch.setattr(app_mod, "_glossary_manager", _GM())

    enq = []
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: enq.append(k))

    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang",
            "source_language": "en", "script": "trad",
            "output_languages": ["zh"],
            "glossary_ids": ["racing-1"], "glossary_llm": True,
        }
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done"
        rows = e["translations"]
        assert "火悟空" in rows[0]["by_lang"]["zh"]["text"]
        # glossary_changes carried onto the row
        assert isinstance(rows[0].get("glossary_changes"), list)
        assert len(rows[0]["glossary_changes"]) >= 1
        assert rows[0]["glossary_changes"][0]["after"].startswith("火悟空") \
            or "火悟空" in rows[0]["glossary_changes"][0]["after"]
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_run_output_lang_no_glossary_ids_row_has_empty_changes(app_mod, monkeypatch):
    """No glossary_ids on the entry → translation rows still produced (regression);
    glossary_changes, if present, is an empty list — never crashes."""
    fid = "t-gl-run-none"
    base = [{"start": 0.0, "end": 1.0, "text": "今晚嘅賽事"}]
    monkeypatch.setattr(app_mod, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    monkeypatch.setattr(app_mod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: None)
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang",
            "source_language": "yue", "script": "trad",
            "output_languages": ["yue", "zh"],
        }
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done"
        assert e["translations"][0]["by_lang"]["yue"]["text"] == "今晚嘅賽事"
        gc = e["translations"][0].get("glossary_changes", [])
        assert gc == []
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


# ---------------------------------------------------------------------------
# Transcribe handler — glossary_ids validation + entry storage
#
# The 202 success path reads current_user.id, so we authenticate a real admin
# session (mirroring test_crosslang_transcribe_api.py) rather than relying on
# LOGIN_DISABLED, under which current_user is anonymous and has no .id.
# ---------------------------------------------------------------------------

@pytest.fixture
def http_client(monkeypatch):
    os.environ.setdefault("R5_AUTH_BYPASS", "1")
    os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-only-for-pytest-do-not-deploy")
    import app as _app
    from auth.users import init_db, create_user

    db_path = _app.app.config["AUTH_DB_PATH"]
    init_db(db_path)
    try:
        create_user(db_path, "glossary_v2_t2", "TestPass1!", is_admin=True)
    except ValueError:
        pass
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    monkeypatch.setattr(_app._job_queue, "position", lambda jid: 0)
    c = _app.app.test_client()
    r = c.post("/login", json={"username": "glossary_v2_t2", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    return _app, c


def _multipart(**form):
    data = {"file": (io.BytesIO(b"fake video bytes"), "clip.mp4")}
    data.update(form)
    return data


def test_transcribe_handler_rejects_unknown_glossary_id(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return None
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    resp = c.post(
        "/api/transcribe",
        data=_multipart(output_languages='["zh"]', source_language="en",
                        glossary_ids='["badid"]'),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "badid" in (body.get("error") or "")


def test_transcribe_handler_stores_valid_glossary_ids(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return _RACING_GLOSSARY if gid == "racing-1" else None
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    resp = c.post(
        "/api/transcribe",
        data=_multipart(output_languages='["zh"]', source_language="en",
                        glossary_ids='["racing-1"]', glossary_llm="1"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202, resp.get_data(as_text=True)
    fid = resp.get_json()["file_id"]
    try:
        entry = _app._file_registry[fid]
        assert entry["glossary_ids"] == ["racing-1"]
        assert entry["glossary_llm"] is True
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_transcribe_handler_glossary_llm_default_on(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return _RACING_GLOSSARY
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    resp = c.post(
        "/api/transcribe",
        data=_multipart(output_languages='["zh"]', source_language="en",
                        glossary_ids='["racing-1"]'),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202, resp.get_data(as_text=True)
    fid = resp.get_json()["file_id"]
    try:
        assert _app._file_registry[fid]["glossary_llm"] is True  # default ON
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_transcribe_handler_glossary_llm_off(http_client, monkeypatch):
    _app, c = http_client

    class _GM:
        def get(self, gid):
            return _RACING_GLOSSARY
    monkeypatch.setattr(_app, "_glossary_manager", _GM())
    resp = c.post(
        "/api/transcribe",
        data=_multipart(output_languages='["zh"]', source_language="en",
                        glossary_ids='["racing-1"]', glossary_llm="0"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202, resp.get_data(as_text=True)
    fid = resp.get_json()["file_id"]
    try:
        assert _app._file_registry[fid]["glossary_llm"] is False
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_transcribe_handler_no_glossary_ids_defaults_empty(http_client, monkeypatch):
    """No glossary_ids form field → entry stores [] (regression: non-glossary upload)."""
    _app, c = http_client
    resp = c.post(
        "/api/transcribe",
        data=_multipart(output_languages='["yue"]', source_language="yue"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202, resp.get_data(as_text=True)
    fid = resp.get_json()["file_id"]
    try:
        assert _app._file_registry[fid].get("glossary_ids") == []
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
