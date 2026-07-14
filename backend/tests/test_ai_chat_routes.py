"""AI 助手 routes tests（Task 7-8）.

Run:
    cd backend && FLASK_SECRET_KEY=test-secret R5_AUTH_BYPASS=1 \
        ./venv/bin/python -m pytest tests/test_ai_chat_routes.py -q
LLM 一律 monkeypatch — 唔打真 Ollama。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _entry(fid):
    def row(i, zh, en, status="pending"):
        return {"idx": i, "start": float(i), "end": float(i) + 2.0, "status": status,
                "by_lang": {"zh": {"text": zh, "status": status, "flags": []},
                            "en": {"text": en, "status": "pending", "flags": []}},
                "zh_text": zh, "en_text": en, "glossary_changes": []}
    return {
        "id": fid, "active_kind": "output_lang", "user_id": 1,
        "source_language": "yue", "script": "trad",
        "output_languages": ["zh", "en"],
        "languages": [{"role": "first", "lang": "zh", "label": "中文（書面語）"},
                      {"role": "second", "lang": "en", "label": "英文"}],
        "translations": [row(0, "今朝有晨操。", "Track work this morning."),
                         row(1, "晨操之後休息。", "Rest after track work.", "approved")],
        "aligned_bilingual": [
            {"start": 0.0, "end": 2.0, "by_lang": {"zh": "今朝有晨操。", "en": "Track work this morning."}},
            {"start": 1.0, "end": 3.0, "by_lang": {"zh": "晨操之後休息。", "en": "Rest after track work."}}],
        "content_asr_segments": [{"start": 0.0, "end": 2.0, "text": "src0"},
                                 {"start": 1.0, "end": 3.0, "text": "src1"}],
    }


@pytest.fixture
def client_entry(monkeypatch):
    import app as _app
    fid = "aichat-ol"
    with _app._registry_lock:
        _app._file_registry[fid] = _entry(fid)
    monkeypatch.setattr(_app, "_save_registry", lambda: None)
    try:
        yield _app.app.test_client(), fid, _app
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def _mock_llm(monkeypatch, app_module, payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(app_module, "_make_ollama_llm_call",
                        lambda: (lambda s, u: raw))


# ---------- /ai-chat/parse ----------

def test_parse_replace_term_expands_mechanically(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    _mock_llm(monkeypatch, app_module, {"reply": "改晒佢", "ops": [
        {"op": "replace_term", "from": "晨操", "to": "早操", "langs": ["zh"]}]})
    r = client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": "把所有晨操改成早操"})
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()
    assert b["reply"] == "改晒佢" and b["grid_len"] == 2
    assert b["rerun_active"] is False and b["render_active"] is False
    items = b["proposal"]["items"]
    assert [i["idx"] for i in items] == [0, 1]
    assert items[1]["approved"] is True and items[1]["after"] == "早操之後休息。"


def test_parse_errors(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    r = client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": ""})
    assert r.status_code == 400
    r = client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": "x" * 501})
    assert r.status_code == 400
    r = client.post("/api/files/no-such/ai-chat/parse", json={"message": "改嘢"})
    assert r.status_code == 404
    # 非 output_lang
    with app_module._registry_lock:
        app_module._file_registry["aichat-prof"] = {"id": "aichat-prof",
                                                    "active_kind": "profile", "user_id": 1}
    try:
        r = client.post("/api/files/aichat-prof/ai-chat/parse", json={"message": "改嘢"})
        assert r.status_code == 400
    finally:
        with app_module._registry_lock:
            app_module._file_registry.pop("aichat-prof", None)
    # LLM 爆 → 502；輸出無法解析 → 422 + 澄清 reply
    monkeypatch.setattr(app_module, "_make_ollama_llm_call",
                        lambda: (lambda s, u: (_ for _ in ()).throw(ConnectionError("down"))))
    r = client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": "改嘢"})
    assert r.status_code == 502
    _mock_llm(monkeypatch, app_module, "我係一個聊天機械人！")
    r = client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": "改嘢"})
    assert r.status_code == 422 and "reply" in r.get_json()


def test_parse_validate_ops_maps_to_422(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    _mock_llm(monkeypatch, app_module, {"reply": "x", "ops": [
        {"op": "rewrite_cue", "seg_no": 99, "lang_role": "first", "instruction": "i"}]})
    r = client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": "改第99段"})
    assert r.status_code == 422


def test_parse_transcript_never_in_prompt(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    seen = {}
    def fake_llm():
        def call(system, user):
            seen["system"], seen["user"] = system, user
            return json.dumps({"reply": "ok", "ops": []}, ensure_ascii=False)
        return call
    monkeypatch.setattr(app_module, "_make_ollama_llm_call", fake_llm)
    client.post(f"/api/files/{fid}/ai-chat/parse", json={"message": "hi改嘢"})
    joined = seen["system"] + seen["user"]
    assert "晨操" not in joined and "Track work" not in joined


# ---------- /ai-chat/expand ----------

def test_expand_zero_llm_rescan(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    monkeypatch.setattr(app_module, "_make_ollama_llm_call",
                        lambda: (_ for _ in ()).throw(AssertionError("must not call LLM")))
    r = client.post(f"/api/files/{fid}/ai-chat/expand", json={"ops": [
        {"op": "replace_term", "from": "晨操", "to": "早操", "langs": "all"}]})
    assert r.status_code == 200
    assert len(r.get_json()["proposal"]["items"]) == 2   # zh×2（en 冇「晨操」）


def test_expand_rejects_bad_ops(client_entry):
    client, fid, _ = client_entry
    r = client.post(f"/api/files/{fid}/ai-chat/expand", json={"ops": [{"op": "nuke"}]})
    assert r.status_code == 400
    r = client.post(f"/api/files/{fid}/ai-chat/expand", json={"ops": "x"})
    assert r.status_code == 400
