import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_second_pass_builds_aligned_bilingual(monkeypatch):
    # 2026-06-04: yue source same-family second pass now derives `target` 1:1 from the
    # cached yue base (refine) via _run_output_lang_second_cross, which builds the aligned
    # grid from the merged rows when the file has none yet (legacy-shaped here).
    fid = "f-al"
    base = [{"start": 0, "end": 1, "text": "今晚嘅賽事"}, {"start": 1, "end": 2, "text": "多謝大家"}]
    # Identity LLM — yue→zh refine returns text unchanged (so zh == the yue base text).
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: u))
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "yue", "script": "trad",
            "output_languages": ["yue", "zh"], "content_asr_segments": base,
            "translations": [
                {"idx": 0, "start": 0, "end": 1, "by_lang": {"yue": {"text": "今晚嘅賽事", "status": "pending", "flags": []}}, "yue_text": "今晚嘅賽事", "status": "pending"},
                {"idx": 1, "start": 1, "end": 2, "by_lang": {"yue": {"text": "多謝大家", "status": "pending", "flags": []}}, "yue_text": "多謝大家", "status": "pending"}]}
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "zh"}, "a.wav", None)
        al = _app._file_registry[fid].get("aligned_bilingual")
        assert al and len(al) == 2
        assert al[0]["by_lang"]["yue"] == "今晚嘅賽事" and al[0]["by_lang"]["zh"] == "今晚嘅賽事"
        assert al[0]["start"] == 0 and al[0]["end"] == 1
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
