import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_run_output_lang_routes_each_output(monkeypatch):
    # 2026-06-04: yue source uses ONE Whisper-yue base + derive each output 1:1
    # (yue=passthrough, zh=refine). No per-output _produce_output_lang, no 2nd job.
    base = [{"start": 0, "end": 1, "text": "今晚嘅賽事"}]
    n = {"tx": 0}
    monkeypatch.setattr(_app, "transcribe_with_segments",
                        lambda *a, **k: (n.__setitem__("tx", n["tx"] + 1) or {"segments": base}))
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    enq = []
    monkeypatch.setattr(_app, "_job_queue", type("Q", (), {"enqueue": lambda self, **k: enq.append(k)})())
    fid = "f-cl"
    _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "yue",
                                "output_languages": ["yue", "zh"], "script": "trad"}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "audio.wav", None)
        e = _app._file_registry[fid]
        assert n["tx"] == 1                                          # ONE shared yue ASR
        assert "yue" in e["translations"][0]["by_lang"] and "zh" in e["translations"][0]["by_lang"]
        assert not enq                                              # no asr_output job
    finally:
        _app._file_registry.pop(fid, None)
