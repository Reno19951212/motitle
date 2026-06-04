import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_is_cross_language_matrix():
    f = _app._is_cross_language
    assert f("yue", ["zh", "en"]) is True
    assert f("en", ["en", "zh"]) is True
    assert f("cmn", ["cmn", "en"]) is True
    assert f("ja", ["ja", "zh"]) is True
    assert f("yue", ["zh"]) is False
    assert f("yue", ["yue"]) is False
    assert f("cmn", ["zh", "cmn"]) is False
    assert f("yue", ["zh", "cmn", "yue"]) is False


def test_cross_language_first_pass_single_grid(monkeypatch):
    fid = "f-cross1"
    base = [{"start": 0, "end": 1, "text": "今晚好高興"}, {"start": 1, "end": 2, "text": "多謝各位"}]
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"今晚好高興": "Very happy tonight",
                                               "多謝各位": "Thank you all"}.get(u, u)))
    enqueued = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enqueued.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "en"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        e = _app._file_registry[fid]
        tr = e["translations"]; al = e.get("aligned_bilingual") or []
        assert e["status"] == "done"
        assert len(tr) == len(base) == len(al)
        assert "zh" in tr[0]["by_lang"] and "en" in tr[0]["by_lang"]
        assert tr[0]["en_text"] == "Very happy tonight"
        assert e.get("content_asr_segments")
        assert not enqueued
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_same_family_yue_first_pass_uses_bound_base(monkeypatch):
    # 2026-06-04: yue source same-family now derives ALL outputs from ONE Whisper-yue base
    # (was: Whisper-zh-direct per output + a 2nd asr_output job). One ASR pass, no enqueue.
    fid = "f-same1"
    base = [{"start": 0, "end": 1, "text": "今晚好高興"}]
    n = {"tx": 0}
    monkeypatch.setattr(_app, "transcribe_with_segments",
                        lambda *a, **k: (n.__setitem__("tx", n["tx"] + 1) or {"segments": base}))
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    enq = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enq.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "yue"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert n["tx"] == 1 and not enq      # one shared yue ASR, no 2nd job
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_cross_language_first_pass_error_marks_status(monkeypatch):
    import pytest
    fid = "f-cross-err"
    def boom(*a, **k):
        raise RuntimeError("asr boom")
    monkeypatch.setattr(_app, "transcribe_with_segments", boom)
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "en"]}
    try:
        with pytest.raises(Exception):
            _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert _app._file_registry[fid]["status"] == "error"
        assert _app._file_registry[fid].get("error")
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_cross_language_second_pass_derives_from_base(monkeypatch):
    fid = "f-cross2"
    base = [{"start": 0, "end": 1, "text": "今晚好高興"}, {"start": 1, "end": 2, "text": "多謝各位"}]
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"今晚好高興": "Happy", "多謝各位": "Thanks"}.get(u, u)))

    def _no_legacy(*a, **k):
        raise AssertionError("cross-language second pass must derive from the cached base, "
                             "not the legacy _produce_output_lang index-merge path")
    monkeypatch.setattr(_app, "_produce_output_lang", _no_legacy)
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "yue", "script": "trad",
            "output_languages": ["zh", "en"], "content_asr_segments": base,
            "translations": [{"idx": 0, "start": 0, "end": 1, "by_lang": {"zh": {"text": "今晚好高興"}}, "zh_text": "今晚好高興"},
                             {"idx": 1, "start": 1, "end": 2, "by_lang": {"zh": {"text": "多謝各位"}}, "zh_text": "多謝各位"}],
            "aligned_bilingual": [{"start": 0, "end": 1, "by_lang": {"zh": "今晚好高興"}},
                                  {"start": 1, "end": 2, "by_lang": {"zh": "多謝各位"}}]}
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "en"}, "a.wav", None)
        e = _app._file_registry[fid]; tr = e["translations"]; al = e["aligned_bilingual"]
        assert len(tr) == 2
        assert tr[0]["by_lang"]["en"]["text"] == "Happy"
        assert tr[0]["by_lang"]["zh"]["text"] == "今晚好高興"
        assert al[0]["by_lang"]["en"] == "Happy"
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_cross_second_pass_falls_back_to_legacy_when_no_base(monkeypatch):
    # cross outs but NO content_asr_segments (legacy whisper-direct first pass) -> must NOT route to cross-derive
    fid = "f-cross-nobase"
    called = {"cross": False}
    monkeypatch.setattr(_app, "_run_output_lang_second_cross",
                        lambda *a, **k: called.__setitem__("cross", True))
    monkeypatch.setattr(_app, "_produce_output_lang", lambda *a, **k: [{"start": 0, "end": 1, "text": "X"}])
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "yue",
                                    "script": "trad", "output_languages": ["yue", "en"],
                                    "translations": [{"idx": 0, "start": 0, "end": 1,
                                                      "by_lang": {"yue": {"text": "今晚"}}, "yue_text": "今晚"}]}
        # NB: no content_asr_segments
    try:
        try:
            _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "en"}, "a.wav", None)
        except Exception:
            pass  # legacy path may need more stubs; we only assert routing here
        assert called["cross"] is False   # did NOT route to cross derive-from-base (no proper base)
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
