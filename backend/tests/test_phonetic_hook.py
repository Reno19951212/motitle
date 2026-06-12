# backend/tests/test_phonetic_hook.py
"""bound_base 掛鈎：base 糾正 + glossary_changes 記錄落 rows。"""
import pytest

pytest.importorskip("flask")
import app as appmod


GLOSS = {"id": "g1", "name": "賽馬", "entries": [
    {"source": "STELLAR EXPRESS", "target": "星際快車 (E123)"}]}


def test_bound_base_corrects_and_records(monkeypatch, tmp_path):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "transcribe_with_segments", lambda *a, **k: {
        "segments": [{"start": 0.0, "end": 2.0, "text": "見到升制快車走上去"}]})
    monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    fid = "f-pc-hook"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "user_id": "u1", "status": "transcribing",
                                      "active_kind": "output_lang", "output_languages": ["yue"],
                                      "source_language": "yue", "script": "trad"}
    appmod._run_output_lang_bound_base(fid, {"id": "j1"}, "/fake/audio.wav", None, ["yue"],
                                       "yue", "trad", mt_style="racing",
                                       do_clause_split=False, glossaries=[GLOSS], glossary_llm=False)
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        assert e["translations"][0]["yue_text"] == "見到星際快車走上去"      # 口語 track 繼承
        assert e["segments"][0]["text"] == "見到星際快車走上去"             # base persist
        gc = e["translations"][0].get("glossary_changes") or []
        assert any(c.get("after") == "星際快車" and "語音糾正" in c.get("glossary", "") for c in gc)
