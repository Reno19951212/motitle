"""yue-source unified ASR-base dispatch (2026-06-04).

Cantonese audio always transcribes with Whisper language='yue' (source-driven);
the output language only selects the downstream transform (passthrough/refine/MT).
Replaces the old output-driven Whisper-zh-direct for 書面語. See
docs/superpowers/specs/2026-06-04-yue-written-register-asr-base-design.md.
"""
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_bound_base_no_clause_split_keeps_segmentation(monkeypatch):
    fid = "f-bb-nosplit"
    # one long base seg that clause_split WOULD break at the comma if enabled
    base = [{"start": 0, "end": 6, "text": "佢今日好開心，因為買咗新車返屋企"}]
    calls = {"transcribe": 0}

    def fake_tx(*a, **k):
        calls["transcribe"] += 1
        return {"segments": base}

    monkeypatch.setattr(_app, "transcribe_with_segments", fake_tx)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))  # refine = identity
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["yue"]}
    try:
        _app._run_output_lang_bound_base(fid, {"user_id": 1, "id": "j"}, "a.wav", None,
                                         ["yue"], "yue", "trad", "generic", do_clause_split=False)
        e = _app._file_registry[fid]
        assert calls["transcribe"] == 1                 # ONE content ASR
        assert len(e["translations"]) == 1              # NOT split into clauses
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_yue_single_written_uses_yue_base_and_refine(monkeypatch):
    fid = "f-yue-zh"
    base = [{"start": 0, "end": 2, "text": "佢去咗東南亞叫雞"}]   # 口語 yue base
    seen = {"lang": None, "n": 0}

    def fake_tx(*a, **k):
        seen["lang"] = k.get("lang_override"); seen["n"] += 1
        return {"segments": base}

    monkeypatch.setattr(_app, "transcribe_with_segments", fake_tx)
    # refine maps the colloquial line to a written line
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"action":"keep","text":"他前往東南亞召妓"}'))
    enq = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enq.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j"}, "a.wav", None)
        e = _app._file_registry[fid]
        assert seen["lang"] == "yue" and seen["n"] == 1           # ASR = YUE, once
        assert "召妓" in e["translations"][0]["zh_text"]          # refined 書面
        assert e.get("content_asr_segments")                      # base cached for on-demand
        assert not enq                                            # no 2nd job (derived in one pass)
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_yue_written_plus_colloquial_one_pass(monkeypatch):
    fid = "f-yue-zh-yue"
    base = [{"start": 0, "end": 2, "text": "佢好開心"}]
    n = {"tx": 0}

    def fake_tx(*a, **k):
        n["tx"] += 1
        return {"segments": base}

    monkeypatch.setattr(_app, "transcribe_with_segments", fake_tx)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))  # identity
    enq = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enq.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "yue"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j"}, "a.wav", None)
        e = _app._file_registry[fid]
        assert n["tx"] == 1                                       # ONE shared yue ASR
        assert "zh" in e["translations"][0]["by_lang"] and "yue" in e["translations"][0]["by_lang"]
        assert not enq                                            # both derived, no 2nd job
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_second_language_yue_derives_from_cached_base(monkeypatch):
    fid = "f-yue-2nd"
    base = [{"start": 0, "end": 2, "text": "佢去咗東南亞叫雞"}]
    # existing file: 口語 first pass already done, base cached, 1 row on the base grid
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "yue",
            "script": "trad", "output_languages": ["yue", "zh"],
            "content_asr_segments": base,
            "translations": [{"start": 0, "end": 2,
                              "by_lang": {"yue": {"text": "佢去咗東南亞叫雞", "status": "pending", "flags": []}},
                              "yue_text": "佢去咗東南亞叫雞"}],
        }
    # if it (wrongly) re-transcribes, fail loudly
    monkeypatch.setattr(_app, "transcribe_with_segments",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must reuse cached yue base")))
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"action":"keep","text":"他前往東南亞召妓"}'))
    monkeypatch.setattr(_app, "_reset_progress_for_job", lambda *a, **k: None)
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "zh"}, "a.wav", None)
        row = _app._file_registry[fid]["translations"][0]
        assert "召妓" in row["zh_text"] and "zh" in row["by_lang"]   # refined from yue base
        assert row["yue_text"] == "佢去咗東南亞叫雞"                  # 口語 untouched
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
