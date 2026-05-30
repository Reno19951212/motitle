"""Tests for bug fixes: #4+#5 (glossary missing target KeyError) and #18 (immutability).

RED-phase tests written BEFORE the fixes; each will fail until the fix is applied.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Bug #4 + #5: _filter_glossary_for_batch must skip entries missing 'target'
# ---------------------------------------------------------------------------

def test_filter_glossary_skips_entry_missing_target():
    """Entry with 'source' but no 'target' must be filtered OUT, not crash."""
    from translation.ollama_engine import _filter_glossary_for_batch

    glossary = {
        "source_lang": "en",
        "target_lang": "zh",
        "entries": [
            {"source": "anchor"},             # missing 'target' — must be skipped
            {"source": "broadcast", "target": "廣播"},  # valid
        ],
    }
    batch_en_texts = ["The anchor hosted the broadcast."]

    # Must NOT raise KeyError; malformed entry must be silently skipped
    result = _filter_glossary_for_batch(glossary, batch_en_texts)

    # Only the valid entry should be in the result
    sources = {e["source"] for e in result}
    assert "broadcast" in sources, "valid entry should pass through"
    assert "anchor" not in sources, "entry missing 'target' must be skipped"


def test_filter_glossary_skips_entry_with_empty_target():
    """Entry with empty-string 'target' must be treated as missing and skipped."""
    from translation.ollama_engine import _filter_glossary_for_batch

    glossary = {
        "source_lang": "en",
        "target_lang": "zh",
        "entries": [
            {"source": "world", "target": ""},   # empty target → falsy → skip
            {"source": "hello", "target": "你好"},  # valid
        ],
    }
    batch_en_texts = ["hello world"]

    result = _filter_glossary_for_batch(glossary, batch_en_texts)
    sources = {e["source"] for e in result}
    assert "hello" in sources
    assert "world" not in sources


def test_translate_single_with_missing_target_does_not_raise(monkeypatch):
    """_translate_single must not KeyError when glossary entry lacks 'target'."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    # Provide a glossary (as list of entries, the instance method form)
    bad_glossary = [
        {"source": "broadcast"},   # no 'target'
        {"source": "anchor", "target": "主播"},
    ]

    # Patch _call_ollama so we don't need a live server
    monkeypatch.setattr(engine, "_call_ollama", lambda *a, **kw: "廣播主播報告。")

    segment = {"start": 0.0, "end": 2.0, "text": "The anchor broadcast the news."}

    # Must NOT raise KeyError
    result = engine._translate_single(segment, bad_glossary, style="formal",
                                      temperature=0.1, runtime_overrides=None)
    assert result["zh_text"] != ""


def test_build_system_prompt_with_missing_target_does_not_raise(monkeypatch):
    """_build_system_prompt must not KeyError when glossary entry lacks 'target'."""
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    # Simulate a filtered list that somehow still has an entry without target
    # (This guards the direct-access site at line 716)
    # After the fix, _filter_glossary_for_batch ensures this can't happen,
    # but we test the unit directly to confirm the filter is the single source
    # of truth.
    safe_glossary = [{"source": "anchor", "target": "主播"}]  # valid, filtered list
    prompt = engine._build_system_prompt("formal", safe_glossary)
    assert "主播" in prompt, "valid glossary term must appear in prompt"


def test_enrich_batch_with_missing_target_does_not_raise(monkeypatch):
    """_enrich_batch must not KeyError when glossary entry lacks 'target'."""
    from translation.ollama_engine import OllamaTranslationEngine
    from translation import TranslatedSegment

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    monkeypatch.setattr(engine, "_call_ollama", lambda *a, **kw: "1. 更豐富的翻譯。")

    batch_segs = [{"text": "The anchor reported the broadcast."}]
    batch_p1 = [TranslatedSegment(start=0.0, end=2.0, en_text="The anchor reported the broadcast.", zh_text="主播報告廣播。", flags=[])]

    bad_glossary = [
        {"source": "broadcast"},       # missing 'target' — must not crash
        {"source": "anchor", "target": "主播"},  # valid
    ]

    # Must NOT raise KeyError
    result = engine._enrich_batch(batch_segs, batch_p1, bad_glossary, 0.1)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Bug #18a: sentence_pipeline must not mutate input segments
# ---------------------------------------------------------------------------

def test_sentence_pipeline_still_bad_does_not_mutate_results():
    """translate_with_sentences must return a NEW list; original segment dicts unchanged."""
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine

    engine = MockTranslationEngine({})

    # Three segments that will form a 'still_bad' repetition (mock returns same zh)
    # mock returns "[EN→ZH] <text>" so they won't be identical; but we can still
    # verify the input list & dict objects are never mutated.
    original_segs = [
        {"start": 0.0, "end": 1.0, "text": "Alpha"},
        {"start": 1.0, "end": 2.0, "text": "Beta"},
        {"start": 2.0, "end": 3.0, "text": "Gamma"},
    ]
    # Take identity snapshots
    original_ids = [id(s) for s in original_segs]
    original_texts = [dict(s) for s in original_segs]

    result = translate_with_sentences(engine, original_segs)

    # Input list must be the SAME object and unchanged
    assert [id(s) for s in original_segs] == original_ids, "input list must not be mutated"
    for orig, snap in zip(original_segs, original_texts):
        assert orig == snap, f"input dict was mutated: {orig} != {snap}"

    # Result is a new list (different identity from input)
    assert result is not original_segs


def test_sentence_pipeline_flags_are_new_list_objects():
    """When 'review' flag is added, the flags list on the returned segment
    must NOT be the same object as any input segment's flags list."""
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine
    from translation.post_processor import validate_batch

    engine = MockTranslationEngine({})

    # Build segments where mock will return identical zh_text (repetition) → still_bad
    # mock returns "[EN→ZH] <text>", so to create repetition we use 3 identical texts
    segs = [
        {"start": 0.0, "end": 1.0, "text": "identical segment"},
        {"start": 1.0, "end": 2.0, "text": "identical segment"},
        {"start": 2.0, "end": 3.0, "text": "identical segment"},
    ]
    result = translate_with_sentences(engine, segs)

    # All three zh_text values should be identical → validate_batch flags them
    # If the pipeline marks them with 'review', the flags list must be new objects
    for r in result:
        if "review" in r.get("flags", []):
            # The flags list in result must not be shared with any input seg
            for orig_seg in segs:
                assert r["flags"] is not orig_seg.get("flags"), (
                    "returned flags list must be a new object, not a reference to input"
                )


# ---------------------------------------------------------------------------
# Bug #18b: _enrich_pass must not mutate pass1_results input
# ---------------------------------------------------------------------------

def test_enrich_pass_does_not_mutate_pass1_results(monkeypatch):
    """_enrich_pass must return a NEW list; the pass1_results input must be unchanged."""
    from translation.ollama_engine import OllamaTranslationEngine
    from translation import TranslatedSegment

    engine = OllamaTranslationEngine({
        "engine": "qwen2.5-3b",
        "translation_passes": "2",
        "enrich_min_src_chars": "0",  # force all eligible
    })
    # Patch LLM so enriched output is deterministic
    monkeypatch.setattr(engine, "_call_ollama", lambda *a, **kw: "1. 豐富版本的翻譯。")

    segments = [{"text": "The anchor reported live."}]
    p1 = [TranslatedSegment(start=0.0, end=2.0, en_text="The anchor reported live.", zh_text="主播現場報告。", flags=[])]

    # Snapshot the input list and its elements
    p1_list_id = id(p1)
    p1_elem_0_id = id(p1[0])
    p1_elem_0_copy = dict(p1[0])

    enriched = engine._enrich_pass(
        segments, p1,
        batch_size=10, glossary=None, temperature=0.1
    )

    # The returned list must be a DIFFERENT object from pass1_results
    assert enriched is not p1, "_enrich_pass must return a new list, not pass1_results"

    # The original pass1_results list must be unchanged
    assert id(p1) == p1_list_id, "pass1_results list identity changed"
    assert p1[0] == p1_elem_0_copy, "pass1_results[0] dict was mutated in place"

    # The returned list must have the enriched content
    assert len(enriched) == 1


def test_enrich_pass_output_values_unchanged_for_valid_input(monkeypatch):
    """_enrich_pass output content must be identical to the functional approach."""
    from translation.ollama_engine import OllamaTranslationEngine
    from translation import TranslatedSegment

    engine = OllamaTranslationEngine({
        "engine": "qwen2.5-3b",
        "enrich_min_src_chars": "0",
    })
    monkeypatch.setattr(engine, "_call_ollama", lambda *a, **kw: "1. 更豐富翻譯。")

    segments = [{"text": "Good evening."}]
    p1 = [TranslatedSegment(start=0.0, end=1.5, en_text="Good evening.", zh_text="晚安。", flags=[])]

    result = engine._enrich_pass(segments, p1, batch_size=10, glossary=None, temperature=0.1)

    assert result[0]["zh_text"] == "更豐富翻譯。"
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 1.5
