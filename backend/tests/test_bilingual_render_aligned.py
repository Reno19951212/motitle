import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_render_bilingual_passes_aligned_rows(monkeypatch):
    fid = "f-rnd-al"
    captured = {}
    def fake_generate_ass(rows, font, **kw):
        captured["rows"] = rows; captured["kw"] = kw
        return "[ass]"
    monkeypatch.setattr(_app._subtitle_renderer, "generate_ass", fake_generate_ass)
    monkeypatch.setattr(_app._subtitle_renderer, "render", lambda *a, **k: (True, None))
    monkeypatch.setattr(_app, "_resolve_file_path", lambda e: "/tmp/x.mp4")
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "status": "done", "active_kind": "output_lang",
            "source_language": "en", "script": "trad", "output_languages": ["en", "zh"],
            "original_name": "x.mp4",
            "translations": [{"idx": 0, "start": 0, "end": 1, "status": "approved",
                              "by_lang": {"en": {"text": "Hello", "status": "approved"}, "zh": {"text": "(WRONG)", "status": "approved"}},
                              "en_text": "Hello", "zh_text": "(WRONG)"}],
            "aligned_bilingual": [
                {"start": 0.0, "end": 1.0, "by_lang": {"en": "Hello", "zh": "你好"}},
                {"start": 1.0, "end": 2.0, "by_lang": {"en": "World", "zh": "世界"}}]}
    try:
        c = _app.app.test_client(); _app.app.config["R5_AUTH_BYPASS"] = True
        r = c.post(f"/api/render", json={"file_id": fid, "format": "mp4", "subtitle_source": "bilingual"})
        assert r.status_code in (200, 202)
        import time as _t
        for _ in range(50):
            if "rows" in captured: break
            _t.sleep(0.05)
        rows = captured.get("rows") or []
        texts = " ".join((row.get("zh_text", "") + row.get("en_text", "")) for row in rows)
        assert "你好" in texts and "世界" in texts
        assert "(WRONG)" not in texts
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
