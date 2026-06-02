import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_make_ollama_llm_call_returns_callable():
    fn = _app._make_ollama_llm_call()
    assert callable(fn)
    import inspect
    assert len(inspect.signature(fn).parameters) == 2


def _stub_transcribe(monkeypatch, recorded):
    def fake(audio_path, **kw):
        recorded.append(kw)
        lang = kw.get("lang_override")
        txt = {"yue": "今晚我好高興同埋好榮幸，多謝各位蒞臨", "zh": "今晚我很高興和很榮幸，感謝各位蒞臨",
               "en": "I am very happy tonight", "ja": "今夜はとても嬉しいです"}.get(lang, "x")
        return {"segments": [{"start": 0.0, "end": 5.0, "text": txt}], "text": txt,
                "model": "m", "backend": "b"}
    monkeypatch.setattr(_app, "transcribe_with_segments", fake)


def test_produce_whisper_direct_same_dialect(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (_ for _ in ()).throw(AssertionError("MT not used")))
    segs = _app._produce_output_lang("audio.wav", "yue", "yue", "trad", None, {})
    assert rec[0]["lang_override"] == "yue"
    assert segs and "今晚" in segs[0]["text"]


def test_produce_cross_uses_asr_mt(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda system, user: "translated"))
    segs = _app._produce_output_lang("audio.wav", "yue", "en", "trad", None, {})
    assert rec[0]["lang_override"] == "yue"
    assert all(s["text"] == "translated" for s in segs)


def test_produce_zh_output_applies_refiner(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    calls = {"refine": 0}

    def fake_llm(system, user):
        if "書面" in system:
            calls["refine"] += 1
            return '{"action":"rewrite","text":"已書面化"}'
        return "mt"
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: fake_llm)
    segs = _app._produce_output_lang("audio.wav", "cmn", "zh", "trad", None, {})
    assert calls["refine"] >= 1
    assert segs[0]["text"] == "已書面化"


def test_produce_cmn_output_no_refiner(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    calls = {"refine": 0}

    def fake_llm(system, user):
        if "書面" in system:
            calls["refine"] += 1
        return '{"text":"x"}'
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: fake_llm)
    _app._produce_output_lang("audio.wav", "cmn", "cmn", "trad", None, {})
    assert calls["refine"] == 0


def test_produce_reuses_content_asr_cache(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: "t"))
    cache = {}
    _app._produce_output_lang("audio.wav", "yue", "en", "trad", None, cache)
    n1 = len(rec)
    _app._produce_output_lang("audio.wav", "yue", "ja", "trad", None, cache)
    assert len(rec) == n1
