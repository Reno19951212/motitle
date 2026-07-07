# backend/tests/test_en_correction_hook.py
"""bound_base + produce 掛鈎：en base 糾正 + glossary_changes 記錄落 rows。"""
import pytest

pytest.importorskip("flask")
import app as appmod


GLOSS = {"id": "g1", "name": "賽馬", "source_lang": "en", "target_lang": "zh",
         "entries": [{"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十 (K001)"}]}


def test_bound_base_corrects_en_and_records(monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "transcribe_with_segments", lambda *a, **k: {
        "segments": [{"start": 0.0, "end": 2.0, "text": "golden  sixty takes the lead"}]})
    monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    fid = "f-en-hook"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "user_id": "u1", "status": "transcribing",
                                      "active_kind": "output_lang", "output_languages": ["en"],
                                      "source_language": "en", "script": "trad"}
    appmod._run_output_lang_bound_base(fid, {"id": "j1"}, "/fake/audio.wav", None, ["en"],
                                       "en", "trad", mt_style="generic",
                                       do_clause_split=False, glossaries=[GLOSS],
                                       glossary_llm=False)
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        assert e["translations"][0]["en_text"] == "GOLDEN SIXTY takes the lead"
        assert e["segments"][0]["text"] == "GOLDEN SIXTY takes the lead"
        gc = e["translations"][0].get("glossary_changes") or []
        assert any(c.get("after") == "GOLDEN SIXTY" and "英文糾正" in c.get("glossary", "")
                   for c in gc)


def test_bound_base_yue_path_unaffected(monkeypatch):
    """en hook 唔可以搞亂 yue gate（phonetic hook regression 錨）。"""
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "transcribe_with_segments", lambda *a, **k: {
        "segments": [{"start": 0.0, "end": 2.0, "text": "golden sixty 上位"}]})
    monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    fid = "f-en-hook-yue"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "user_id": "u1", "status": "transcribing",
                                      "active_kind": "output_lang", "output_languages": ["yue"],
                                      "source_language": "yue", "script": "trad"}
    appmod._run_output_lang_bound_base(fid, {"id": "j2"}, "/fake/audio.wav", None, ["yue"],
                                       "yue", "trad", mt_style="generic",
                                       do_clause_split=False, glossaries=[GLOSS],
                                       glossary_llm=False)
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        # yue base 唔會被 en 糾錯改寫成全大寫
        assert "golden sixty" in e["segments"][0]["text"]
