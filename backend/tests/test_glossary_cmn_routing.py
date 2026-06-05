"""Regression tests for the cmn-source glossary content-language divergence fix.

Bug (review HIGH + MEDIUM): the dispatch path passed the RAW source_language
('cmn') as the content_lang into derive/glossary/MT, but a Chinese glossary's
source_lang can only be 'zh' (no cmn/yue in the glossary whitelist). So
route_for_output gated on EXACT equality `gl_src == content_lang` →
'zh' != 'cmn' → returned None → glossary silently NOT applied on the upload
path. The reapply endpoint already passed content_asr_lang(source_language)
(cmn→'zh') → glossary DID apply → inconsistent + non-idempotent. The cmn ASR
base is transcribed with lang_override 'zh', so the canonical content language
IS 'zh'.

Fix: dispatch uses content_asr_lang(source_language) as the content arg
everywhere it currently passed raw source_language into derive/glossary/MT.
content_asr_lang maps ONLY cmn→zh; yue/en/ja are identity, so the validated
yue/en flows stay byte-identical.

Run:
    cd backend && FLASK_SECRET_KEY=test-secret-only-for-pytest-do-not-deploy \
        R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_glossary_cmn_routing.py -q
"""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# A Chinese glossary: its source_lang can only be 'zh' (whitelist has no cmn/yue).
# The entry's source is an English horse name (HK racing horses keep English names
# that appear romanized in the transcript) — matchable by the source-side \b filter,
# which is what the MT source-side path canonicalizes once routing is fixed.
_ZH_GLOSSARY = {
    "id": "zh-names-1",
    "name": "ZH",
    "source_lang": "zh",
    "target_lang": "zh",
    "entries": [{"source": "Romantic Warrior", "target": "浪漫勇士"}],
}


# ===========================================================================
# (a) Unit — route_for_output documents the bug + fix
# ===========================================================================

def test_route_for_output_cmn_raw_source_lang_does_not_route():
    """Documents the BUG: passing the raw 'cmn' content_lang for a zh-source
    glossary on the MT path (cmn→yue, mode='mt') returns None (no route)
    because the MT branch gates on `gl_src == content_lang` and 'zh' != 'cmn'."""
    import output_lang_glossary as G

    # MT path: cmn-source file deriving a yue output (cross-dialect, same zh
    # family target). gl_src='zh', content_lang='cmn' (raw) → 'zh' != 'cmn' → None.
    assert G.route_for_output(_ZH_GLOSSARY, output_lang="yue",
                              content_lang="cmn", derive_mode="mt") is None


def test_route_for_output_cmn_content_asr_lang_routes_source():
    """Documents the FIX: passing content_asr_lang('cmn')=='zh' as the
    content_lang makes the zh-source glossary route 'source' on the MT path
    (cmn→yue), matching the ASR base AND the reapply endpoint."""
    import output_lang_glossary as G
    from output_lang_router import content_asr_lang

    content_lang = content_asr_lang("cmn")
    assert content_lang == "zh"
    assert G.route_for_output(_ZH_GLOSSARY, output_lang="yue",
                              content_lang=content_lang, derive_mode="mt") == "source"


# ===========================================================================
# (b) Dispatch — cmn-source output_lang file WITH a zh glossary DOES apply
# ===========================================================================

@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-only-for-pytest-do-not-deploy")
    import app as _a
    importlib.reload(_a)
    return _a


def test_cmn_source_dispatch_applies_glossary(app_mod, monkeypatch):
    """A cmn-source output_lang file (cmn→yue, MT path) carrying a zh-source
    glossary must canonicalize the name + record glossary_changes on the row.

    Before the fix the dispatch passed raw 'cmn' as content_lang → route_for_output
    returned None on the source side → no glossary applied → no glossary_changes.
    After the fix it passes content_asr_lang('cmn')=='zh' → routes 'source' → applies.
    cmn→yue is the path that actually exercises the fix (same zh-family target,
    MT mode gated on gl_src == content_lang).
    """
    fid = "t-cmn-gl"
    # cmn ASR base transcribed as 'zh' — the content text the glossary matches on.
    # The English horse name is matchable by the source-side \b filter.
    base = [{"start": 0.0, "end": 1.0, "text": "今场 Romantic Warrior 领先"}]

    monkeypatch.setattr(app_mod, "transcribe_with_segments",
                        lambda *a, **k: {"segments": base})
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")

    def _llm(system, user):
        # glossary review prompt (carries the 對照表 mapping table) → canonicalize.
        if "對照表" in user:
            return '{"text": "今場浪漫勇士領先"}'
        # crosslang_mt zh→yue: translate the cue (leave the name verbatim).
        return "今場 Romantic Warrior 領先"

    monkeypatch.setattr(app_mod, "_make_ollama_llm_call", lambda: _llm)

    class _GM:
        def get(self, gid):
            return _ZH_GLOSSARY if gid == "zh-names-1" else None
    monkeypatch.setattr(app_mod, "_glossary_manager", _GM())
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: None)

    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang",
            "source_language": "cmn", "script": "trad",
            "output_languages": ["yue"],
            "glossary_ids": ["zh-names-1"], "glossary_llm": True,
        }
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done", e.get("error")
        rows = e["translations"]
        gc = rows[0].get("glossary_changes")
        assert isinstance(gc, list)
        assert len(gc) >= 1, "cmn-source glossary must apply (content_asr_lang='zh')"
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


def test_cmn_source_dispatch_no_glossary_still_runs(app_mod, monkeypatch):
    """Regression: cmn-source file with NO glossary still produces rows + empty
    glossary_changes (never crashes)."""
    fid = "t-cmn-nogl"
    base = [{"start": 0.0, "end": 1.0, "text": "今天天气很好"}]
    monkeypatch.setattr(app_mod, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    monkeypatch.setattr(app_mod, "_make_ollama_llm_call", lambda: (lambda s, u: "今日天氣好好"))
    monkeypatch.setattr(app_mod, "_resolve_file_path", lambda f: "/tmp/x.wav")
    monkeypatch.setattr(app_mod._job_queue, "enqueue", lambda **k: None)
    with app_mod._registry_lock:
        app_mod._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang",
            "source_language": "cmn", "script": "trad",
            "output_languages": ["yue"],
        }
    try:
        app_mod._asr_handler({"file_id": fid, "id": "j", "user_id": 1, "type": "asr"})
        e = app_mod._file_registry[fid]
        assert e["status"] == "done", e.get("error")
        assert e["translations"][0].get("glossary_changes", []) == []
    finally:
        with app_mod._registry_lock:
            app_mod._file_registry.pop(fid, None)


# ===========================================================================
# FIX 2 — crosslang_mt._SRC_NAME has a descriptive label for 'zh'
# ===========================================================================

def test_crosslang_mt_src_name_has_zh_label():
    """After the content_lang swap, cmn-source MT passes 'zh' to
    build_mt_system_prompt. _SRC_NAME must carry a descriptive 'zh' label so the
    prompt stays meaningful (not a bare 'zh' fallback)."""
    from translation import crosslang_mt
    assert "zh" in crosslang_mt._SRC_NAME
    # The descriptive label must not be the bare code.
    assert crosslang_mt._SRC_NAME["zh"] != "zh"
    # The system prompt for zh→en must embed the descriptive source label.
    sysp = crosslang_mt.build_mt_system_prompt("zh", "en")
    assert crosslang_mt._SRC_NAME["zh"] in sysp
    # yue label still present (yue→en cross-lang uses it).
    assert "yue" in crosslang_mt._SRC_NAME
