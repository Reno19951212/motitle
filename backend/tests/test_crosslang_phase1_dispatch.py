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


def test_same_family_first_pass_uses_legacy(monkeypatch):
    fid = "f-same1"
    seg = [{"start": 0, "end": 1, "text": "今晚好高興"}]
    monkeypatch.setattr(_app, "_produce_output_lang", lambda *a, **k: seg)
    enqueued = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enqueued.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "yue"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert enqueued and enqueued[0].get("job_type") == "asr_output"
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
