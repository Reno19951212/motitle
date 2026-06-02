import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_second_pass_builds_aligned_bilingual(monkeypatch):
    fid = "f-al"
    base = [{"start": 0, "end": 1, "text": "Hello world"}, {"start": 1, "end": 2, "text": "Goodbye"}]
    monkeypatch.setattr(_app, "_produce_output_lang",
                        lambda *a, **k: [{"start": 0, "end": 1, "text": "你好世界"}, {"start": 1, "end": 2, "text": "再見"}])
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"Hello world": "你好世界", "Goodbye": "再見"}.get(u, u)))
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "en", "script": "trad",
            "output_languages": ["en", "zh"], "content_asr_segments": base,
            "translations": [
                {"idx": 0, "start": 0, "end": 1, "by_lang": {"en": {"text": "Hello world", "status": "pending", "flags": []}}, "en_text": "Hello world", "status": "pending"},
                {"idx": 1, "start": 1, "end": 2, "by_lang": {"en": {"text": "Goodbye", "status": "pending", "flags": []}}, "en_text": "Goodbye", "status": "pending"}]}
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "zh"}, "a.wav", None)
        al = _app._file_registry[fid].get("aligned_bilingual")
        assert al and len(al) == 2
        assert al[0]["by_lang"]["en"] == "Hello world" and al[0]["by_lang"]["zh"] == "你好世界"
        assert al[0]["start"] == 0 and al[0]["end"] == 1
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
