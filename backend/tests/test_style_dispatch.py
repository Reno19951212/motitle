import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_cross_first_pass_threads_mt_style(monkeypatch):
    fid = "f-style1"
    base = [{"start": 0, "end": 1, "text": "the boys played well"}]
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    seen = {}
    def fake_llm():
        def call(sysp, user):
            seen["sysp"] = sysp
            return "X"
        return call
    monkeypatch.setattr(_app, "_make_ollama_llm_call", fake_llm)
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: None)
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "en",
                                    "script": "trad", "output_languages": ["en", "zh"], "mt_style": "racing"}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert "賽馬" in seen["sysp"]   # racing style threaded into the en->zh MT prompt
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_cross_first_pass_default_style_no_racing(monkeypatch):
    fid = "f-style2"
    base = [{"start": 0, "end": 1, "text": "the boys played well"}]
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    seen = {}
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda sysp, u: seen.__setitem__("sysp", sysp) or "X"))
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: None)
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "en",
                                    "script": "trad", "output_languages": ["en", "zh"]}  # no mt_style
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert "賽馬" not in seen["sysp"]   # default generic
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_register_file_stores_mt_style():
    fid = "f-reg-style"
    try:
        e = _app._register_file(fid, "x.mp4", "x.mp4", 100, user_id=1,
                                output_languages=["en", "zh"], source_language="en",
                                script="trad", mt_style="sportsnews")
        assert _app._file_registry[fid]["mt_style"] == "sportsnews"
        # default when omitted
        fid2 = "f-reg-style2"
        _app._register_file(fid2, "y.mp4", "y.mp4", 100, user_id=1,
                            output_languages=["en", "zh"], source_language="en", script="trad")
        assert _app._file_registry[fid2]["mt_style"] == "generic"
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None); _app._file_registry.pop("f-reg-style2", None)


def test_second_pass_cross_threads_mt_style(monkeypatch):
    fid = "f-style-2nd"
    base = [{"start": 0, "end": 1, "text": "the boys"}]
    seen = {}
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda sysp, u: seen.__setitem__("sysp", sysp) or "X"))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "en",
                                    "script": "trad", "output_languages": ["en", "zh"], "mt_style": "racing",
                                    "content_asr_segments": base,
                                    "translations": [{"idx": 0, "start": 0, "end": 1,
                                                      "by_lang": {"en": {"text": "the boys"}}, "en_text": "the boys"}],
                                    "aligned_bilingual": [{"start": 0, "end": 1, "by_lang": {"en": "the boys"}}]}
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "zh"}, "a.wav", None)
        assert "賽馬" in seen["sysp"]   # racing style threaded into the on-demand 2nd-pass en->zh MT
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
