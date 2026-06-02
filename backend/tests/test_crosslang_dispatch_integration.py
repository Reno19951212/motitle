import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_run_output_lang_routes_each_output(monkeypatch):
    produced = []
    monkeypatch.setattr(_app, "_produce_output_lang",
                        lambda audio, src, out, script, ce, cache: produced.append((src, out, script)) or
                        [{"start": 0, "end": 1, "text": f"{out}-text"}])
    monkeypatch.setattr(_app, "_update_file", lambda *a, **k: None)
    enq = []
    monkeypatch.setattr(_app, "_job_queue", type("Q", (), {"enqueue": lambda self, **k: enq.append(k)})())
    fid = "f-cl"
    _app._file_registry[fid] = {"id": fid, "source_language": "yue",
                                "output_languages": ["yue", "en"], "script": "trad"}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "audio.wav", None)
    finally:
        _app._file_registry.pop(fid, None)
    assert ("yue", "yue", "trad") in produced
    assert any(k.get("job_type") == "asr_output" and k.get("output_language") == "en" for k in enq)
