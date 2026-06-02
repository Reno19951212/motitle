import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def _client():
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app.app.test_client()


def test_bilingual_srt_uses_aligned(monkeypatch):
    fid = "f-exp-al"
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "status": "done", "active_kind": "output_lang",
            "source_language": "en", "script": "trad", "output_languages": ["en", "zh"],
            "original_name": "x.mp4", "subtitle_source": "bilingual", "bilingual_order": "en_top",
            "segments": [], "translations": [
                {"idx": 0, "start": 0, "end": 1, "by_lang": {"en": {"text": "Hello"}, "zh": {"text": "(WRONG-misaligned)"}}, "en_text": "Hello", "zh_text": "(WRONG-misaligned)"}],
            "aligned_bilingual": [
                {"start": 0.0, "end": 1.0, "by_lang": {"en": "Hello", "zh": "你好"}},
                {"start": 1.0, "end": 2.0, "by_lang": {"en": "World", "zh": "世界"}}]}
    try:
        c = _client()
        r = c.get(f"/api/files/{fid}/subtitle.srt?source=bilingual")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Hello" in body and "你好" in body
        assert "World" in body and "世界" in body
        assert "(WRONG-misaligned)" not in body
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
