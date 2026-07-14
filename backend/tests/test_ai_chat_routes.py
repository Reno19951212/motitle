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


# ---------- /ai-chat/apply ----------

def _apply(client, fid, items, approve=False):
    return client.post(f"/api/files/{fid}/ai-chat/apply",
                       json={"items": items, "approve": approve})


def _item(idx=0, lang="zh", after="今朝有早操。", expected="今朝有晨操。",
          start=0.0, end=2.0, **kw):
    d = {"idx": idx, "lang": lang, "after": after, "expected_text": expected,
         "start": start, "end": end}
    d.update(kw)
    return d


def test_apply_writes_four_stores_keep_status_and_audit(client_entry):
    client, fid, app_module = client_entry
    r = _apply(client, fid, [_item()])
    assert r.status_code == 200, r.get_data(as_text=True)
    b = r.get_json()
    assert b["applied"] == [{"idx": 0, "lang": "zh",
                             "prev_status": {"row": "pending", "by_lang": "pending"}}]
    with app_module._registry_lock:
        e = app_module._file_registry[fid]
        row = e["translations"][0]
    assert row["by_lang"]["zh"]["text"] == "今朝有早操。"
    assert row["zh_text"] == "今朝有早操。"
    assert e["aligned_bilingual"][0]["by_lang"]["zh"] == "今朝有早操。"
    assert row["status"] == "pending"                       # keep_status 預設
    ch = row["glossary_changes"][-1]
    assert ch["source"] == "AI 助手" and ch["before"] == "今朝有晨操。" \
        and ch["after"] == "今朝有早操。" and ch["lang"] == "zh"


def test_apply_conflict_and_idempotent_partial(client_entry):
    client, fid, app_module = client_entry
    items = [
        _item(),                                             # OK
        _item(idx=1, after="晨操之後休息。", expected="晨操之後休息。",
              start=1.0, end=3.0),                           # current==after → skipped
        _item(idx=1, lang="en", after="x", expected="WRONG", start=1.0, end=3.0),
    ]
    r = _apply(client, fid, items)
    b = r.get_json()
    assert len(b["applied"]) == 1 and b["skipped"] == [{"idx": 1, "lang": "zh"}]
    assert b["failed"][0]["idx"] == 1 and "段落已被修改" in b["failed"][0]["error"]


def test_apply_timing_drift_fails_item(client_entry):
    client, fid, _ = client_entry
    r = _apply(client, fid, [_item(start=0.5)])              # start 唔符 → mechanical split trap
    assert r.get_json()["failed"][0]["idx"] == 0


def test_apply_approve_and_status_after_restore(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    # approve 模式
    r = _apply(client, fid, [_item()], approve=True)
    assert r.get_json()["applied"][0]["prev_status"]["row"] == "pending"
    with app_module._registry_lock:
        row = app_module._file_registry[fid]["translations"][0]
        assert row["status"] == "approved" and row["by_lang"]["zh"]["status"] == "approved"
    # undo：status_after 還原 + expected_text = 已套用文字
    r = _apply(client, fid, [_item(after="今朝有晨操。", expected="今朝有早操。",
                                   status_after="pending")])
    assert r.get_json()["applied"], r.get_data(as_text=True)
    with app_module._registry_lock:
        row = app_module._file_registry[fid]["translations"][0]
        assert row["zh_text"] == "今朝有晨操。" and row["status"] == "pending"


def test_apply_rerun_409_and_gates(client_entry, monkeypatch):
    client, fid, app_module = client_entry
    monkeypatch.setattr(app_module, "_file_has_active_rerun", lambda f: True)
    r = _apply(client, fid, [_item()])
    assert r.status_code == 409
    monkeypatch.undo()
    # bogus lang / bool idx / 冇 after / 壞 status_after → 400
    assert _apply(client, fid, [_item(lang="ja")]).status_code == 400
    assert _apply(client, fid, [_item(idx=True)]).status_code == 400
    bad = _item(); bad.pop("after")
    assert _apply(client, fid, [bad]).status_code == 400
    assert _apply(client, fid, [_item(status_after="weird")]).status_code == 400
    assert _apply(client, fid, []).status_code == 400
