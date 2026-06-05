import importlib
import pytest


@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _a
    importlib.reload(_a)
    return _a


def test_whisper_params_mapping(app_mod):
    f = app_mod._whisper_params_for_lang
    assert f("yue") == {"lang_override": "yue", "task_override": "transcribe", "s2hk_override": True}
    assert f("zh") == {"lang_override": "zh", "task_override": "transcribe", "s2hk_override": True}
    assert f("ja") == {"lang_override": "ja", "task_override": "transcribe", "s2hk_override": None}
    assert f("en") == {"lang_override": None, "task_override": "translate", "s2hk_override": None}


def test_mt_handler_short_circuits_output_lang(app_mod, monkeypatch):
    called = {"auto": False}
    monkeypatch.setattr(app_mod, "_auto_translate", lambda *a, **k: called.__setitem__("auto", True))
    fid = "t-ol-mt"
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "output_languages": ["yue"]}
    try:
        app_mod._mt_handler({"file_id": fid, "id": "j"})
        assert called["auto"] is False
        assert app_mod._file_registry[fid]["translation_status"] == "done"
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_asr_handler_output_lang_first_pass(app_mod, monkeypatch):
    # 2026-06-04: yue same-family first pass now uses the bound-base single-grid path —
    # ONE Whisper-yue ASR, derive yue (passthrough) + zh (refine) from it, persist one
    # grid, enqueue NO asr_output job. (Was: per-output _produce_output_lang + 2nd job.)
    fid = "t-ol-run"
    base = [{"start": 0, "end": 1, "text": "今晚嘅賽事"}]
    n = {"tx": 0}
    monkeypatch.setattr(app_mod, "transcribe_with_segments",
                        lambda *a, **k: (n.__setitem__("tx", n["tx"] + 1) or {"segments": base}))
    monkeypatch.setattr(app_mod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    enq = []
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: enq.append(k))
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                       "source_language": "yue", "script": "trad",
                                       "output_languages": ["yue", "zh"]}
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done"
        assert n["tx"] == 1                                              # ONE shared yue ASR
        assert e["translations"][0]["by_lang"]["yue"]["text"] == "今晚嘅賽事"
        assert e["translations"][0]["yue_text"] == "今晚嘅賽事"
        assert "zh" in e["translations"][0]["by_lang"]                  # 書面 derived in same pass
        assert not enq                                                  # no asr_output job
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_asr_handler_output_lang_first_pass_cross_single_grid(app_mod, monkeypatch):
    # Cross-language (yue -> en) first pass: new bound-base single-grid path
    # transcribes the content language ONCE, derives every output 1:1, persists
    # one shared grid, and enqueues NO asr_output job.
    fid = "t-ol-run-cross"
    base = [{"start": 0, "end": 1, "text": "今晚嘅賽事"}]
    monkeypatch.setattr(app_mod, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    monkeypatch.setattr(app_mod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"今晚嘅賽事": "Tonight's race"}.get(u, u)))
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    enq = []
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: enq.append(k))
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                       "source_language": "yue", "script": "trad",
                                       "output_languages": ["yue", "en"]}
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done"
        tr = e["translations"]
        assert len(tr) == len(base)
        assert "yue" in tr[0]["by_lang"] and "en" in tr[0]["by_lang"]
        assert tr[0]["en_text"] == "Tonight's race"
        assert e.get("content_asr_segments")
        assert not enq
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_run_output_lang_first_pass_error_marks_status_error(app_mod, monkeypatch):
    fid = "t-ol-err"

    def boom(audio, **kw):
        raise RuntimeError("mlx engine crashed")

    monkeypatch.setattr(app_mod, "transcribe_with_segments", boom)
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "output_languages": ["yue"]}
    try:
        import pytest as _pt
        with _pt.raises(RuntimeError):
            app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        assert app_mod._file_registry[fid]["status"] == "error"
        assert "mlx engine crashed" in (app_mod._file_registry[fid].get("error") or "")
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_asr_handler_output_lang_second_pass_merges(app_mod, monkeypatch):
    # Same-family input (yue source, zh second) keeps the LEGACY index-merge
    # second-pass path. Cross-language inputs now route to the derive-from-base
    # branch (covered in test_crosslang_phase1_dispatch).
    fid = "t-ol-run2"
    monkeypatch.setattr(app_mod, "_produce_output_lang",
                        lambda audio, src, out, script, ce, cache, **kw: [{"start": 0, "end": 1, "text": "今晚的賽事"}])
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "yue", "script": "trad",
            "output_languages": ["yue", "zh"],
            "translations": [{"idx": 0, "start": 0, "end": 1,
                              "by_lang": {"yue": {"text": "今晚嘅賽事", "status": "pending", "flags": []}},
                              "yue_text": "今晚嘅賽事", "status": "pending"}]}
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j2", "user_id": 1, "type": "asr_output", "output_language": "zh"})
        r = app_mod._file_registry[fid]["translations"][0]
        assert r["by_lang"]["zh"]["text"] == "今晚的賽事" and r["zh_text"] == "今晚的賽事"
        assert r["by_lang"]["yue"]["text"] == "今晚嘅賽事"   # first preserved
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)
