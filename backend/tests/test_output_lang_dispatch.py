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
    fid = "t-ol-run"

    def fake_tws(audio, **kw):
        assert kw["asr_profile_override"]["asr"]["engine"] == "mlx-whisper"
        assert kw["lang_override"] == "yue" and kw["task_override"] == "transcribe" and kw["s2hk_override"] is True
        return {"text": "今晚", "segments": [{"id": 0, "start": 0, "end": 1, "text": "今晚嘅賽事"}],
                "model": "large-v3", "backend": "mlx"}

    monkeypatch.setattr(app_mod, "transcribe_with_segments", fake_tws)
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    enq = []
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: enq.append(k))
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "output_languages": ["yue", "en"]}
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done"
        assert e["translations"][0]["by_lang"]["yue"]["text"] == "今晚嘅賽事"
        assert e["translations"][0]["yue_text"] == "今晚嘅賽事"
        assert any(k.get("job_type") == "asr_output" and k.get("output_language") == "en" for k in enq)
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_asr_handler_output_lang_second_pass_merges(app_mod, monkeypatch):
    fid = "t-ol-run2"

    def fake_tws(audio, **kw):
        assert kw["task_override"] == "translate"   # en → translate
        return {"text": "Tonight", "segments": [{"id": 0, "start": 0, "end": 1, "text": "Tonight's race"}],
                "model": "large-v3", "backend": "mlx"}

    monkeypatch.setattr(app_mod, "transcribe_with_segments", fake_tws)
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "output_languages": ["yue", "en"],
            "translations": [{"idx": 0, "start": 0, "end": 1,
                              "by_lang": {"yue": {"text": "今晚嘅賽事", "status": "pending", "flags": []}},
                              "yue_text": "今晚嘅賽事", "status": "pending"}]}
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j2", "user_id": 1, "type": "asr_output", "output_language": "en"})
        r = app_mod._file_registry[fid]["translations"][0]
        assert r["by_lang"]["en"]["text"] == "Tonight's race" and r["en_text"] == "Tonight's race"
        assert r["by_lang"]["yue"]["text"] == "今晚嘅賽事"   # first preserved
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)
