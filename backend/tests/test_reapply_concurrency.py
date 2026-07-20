"""glossary-reapply must not silently clobber a cue write that lands during its
30-47s LLM window. Bug-sweep #24: optimistic-concurrency signature check.
"""
import json


def _seed(app_module, fid):
    base = [{"start": 0, "end": 1, "text": "今晚嘅賽事"}]
    app_module._file_registry[fid] = {
        "id": fid, "active_kind": "output_lang", "user_id": 0,
        "source_language": "yue", "script": "trad", "output_languages": ["zh"],
        "content_asr_segments": base,
        "translations": [{
            "idx": 0, "start": 0, "end": 1,
            "by_lang": {"zh": {"text": "今晚嘅賽事", "status": "pending", "flags": []}},
            "zh_text": "今晚嘅賽事", "status": "pending"}],
        "glossary_ids": [], "glossary_llm": False,
    }


def test_reapply_409_when_translations_change_mid_window(client, monkeypatch):
    import app as A
    fid = "bugsweep_reapply_race"
    _seed(A, fid)

    # LLM that mutates this file's translations mid-derive — models a concurrent
    # ai-chat/apply landing during reapply's out-of-lock LLM window.
    def racing_llm():
        def _call(sysp, user):
            A._file_registry[fid]["translations"][0]["by_lang"]["zh"]["text"] = "被並發改咗"
            return json.dumps({"action": "keep", "text": "今晚嘅賽事"}, ensure_ascii=False)
        return _call
    monkeypatch.setattr(A, "_make_ollama_llm_call", racing_llm)
    try:
        r = client.post(f"/api/files/{fid}/glossary-reapply", json={"glossary_llm": False})
        assert r.status_code == 409, r.get_data(as_text=True)[:150]
    finally:
        A._file_registry.pop(fid, None)


def test_reapply_200_when_no_concurrent_write(client, monkeypatch):
    import app as A
    fid = "bugsweep_reapply_ok"
    _seed(A, fid)

    def quiet_llm():
        return lambda sysp, user: json.dumps({"action": "keep", "text": "今晚嘅賽事"},
                                             ensure_ascii=False)
    monkeypatch.setattr(A, "_make_ollama_llm_call", quiet_llm)
    try:
        r = client.post(f"/api/files/{fid}/glossary-reapply", json={"glossary_llm": False})
        assert r.status_code == 200, r.get_data(as_text=True)[:150]
    finally:
        A._file_registry.pop(fid, None)
