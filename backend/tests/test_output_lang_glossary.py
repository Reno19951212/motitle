"""Tests for backend/output_lang_glossary.py — pure glossary stage (Task 1.1 + 1.2).

Run:
    cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_glossary.py -q
"""
import sys, os

# Ensure backend/ is on path so bare `import output_lang_glossary` works
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import output_lang_glossary as G


# ---------------------------------------------------------------------------
# strip_horse_id
# ---------------------------------------------------------------------------

def test_strip_horse_id_with_suffix():
    assert G.strip_horse_id("火悟空 (K335)") == "火悟空"


def test_strip_horse_id_uppercase_suffix():
    assert G.strip_horse_id("Blazing Wukong (H123)") == "Blazing Wukong"


def test_strip_horse_id_no_suffix():
    assert G.strip_horse_id("活力拍檔") == "活力拍檔"


def test_strip_horse_id_empty():
    assert G.strip_horse_id("") == ""


def test_strip_horse_id_none_safe():
    assert G.strip_horse_id(None) == ""


# ---------------------------------------------------------------------------
# is_name_candidate
# ---------------------------------------------------------------------------

def test_is_name_candidate_multiword_true():
    assert G.is_name_candidate("AMAZING PARTNERS") is True


def test_is_name_candidate_uncommon_single_true():
    assert G.is_name_candidate("HYMNBOOK") is True


def test_is_name_candidate_common_class_false():
    assert G.is_name_candidate("CLASS") is False


def test_is_name_candidate_common_dash_false():
    assert G.is_name_candidate("DASH") is False


def test_is_name_candidate_case_insensitive_common():
    assert G.is_name_candidate("class") is False
    assert G.is_name_candidate("Win") is False


def test_is_name_candidate_two_words_always_true():
    # Even "class race" — two words → True (distinctive enough)
    assert G.is_name_candidate("class race") is True


# ---------------------------------------------------------------------------
# build_merged_index — first-wins priority
# ---------------------------------------------------------------------------

def _make_glossary(id_, name, src_lang, tgt_lang, entries):
    return {"id": id_, "name": name, "source_lang": src_lang, "target_lang": tgt_lang, "entries": entries}


def test_build_merged_index_first_wins():
    g1 = _make_glossary("a", "A", "en", "zh", [{"source": "X", "target": "甲"}])
    g2 = _make_glossary("b", "B", "en", "zh", [{"source": "X", "target": "乙"}])
    idx = G.build_merged_index([g1, g2])
    assert idx["source"]["X"]["target"] == "甲"  # first-wins; g2 does NOT override


def test_build_merged_index_second_unique_key_present():
    g1 = _make_glossary("a", "A", "en", "zh", [{"source": "X", "target": "甲"}])
    g2 = _make_glossary("b", "B", "en", "zh", [{"source": "Y", "target": "乙"}])
    idx = G.build_merged_index([g1, g2])
    assert idx["source"]["X"]["target"] == "甲"
    assert idx["source"]["Y"]["target"] == "乙"  # non-conflicting key present


def test_build_merged_index_strips_suffix_in_target():
    g = _make_glossary("a", "A", "en", "zh",
                       [{"source": "Blazing Wukong", "target": "火悟空 (K335)"}])
    idx = G.build_merged_index([g])
    assert idx["source"]["BLAZING WUKONG"]["target"] == "火悟空"


def test_build_merged_index_empty_glossaries():
    assert G.build_merged_index([]) == {"source": {}, "target": {}}


def test_build_merged_index_target_side_populated():
    g = _make_glossary("a", "A", "en", "zh",
                       [{"source": "Blazing Wukong", "target": "火悟空 (K335)"}])
    idx = G.build_merged_index([g])
    assert "火悟空" in idx["target"]


# ---------------------------------------------------------------------------
# route_for_output
# ---------------------------------------------------------------------------

def test_route_source_for_mt_en_to_zh():
    g = {"source_lang": "en", "target_lang": "zh"}
    assert G.route_for_output(g, output_lang="zh", content_lang="en", derive_mode="mt") == "source"


def test_route_target_for_refine_yue_to_zh():
    g = {"source_lang": "yue", "target_lang": "zh"}
    assert G.route_for_output(g, output_lang="zh", content_lang="yue", derive_mode="refine") == "target"


def test_route_none_when_target_lang_family_mismatch():
    # glossary is en→zh but output_lang is ja: target family zh != ja → None
    g = {"source_lang": "en", "target_lang": "zh"}
    assert G.route_for_output(g, output_lang="ja", content_lang="en", derive_mode="mt") is None


def test_route_target_for_pass_cmn_to_zh():
    g = {"source_lang": "cmn", "target_lang": "zh"}
    assert G.route_for_output(g, output_lang="cmn", content_lang="cmn", derive_mode="pass") == "target"


def test_route_source_requires_correct_content_lang():
    # glossary source_lang=en but content is yue (MT) → doesn't match
    g = {"source_lang": "en", "target_lang": "zh"}
    assert G.route_for_output(g, output_lang="zh", content_lang="yue", derive_mode="mt") is None


# ---------------------------------------------------------------------------
# deterministic_apply
# ---------------------------------------------------------------------------

def test_deterministic_apply_verbatim_target_no_change():
    # Target already in text → no change
    cands = [{"source": "Blazing Wukong", "target": "火悟空", "glossary": "racing", "side": "target"}]
    new_text, changes = G.deterministic_apply("火悟空衝線奪冠", cands)
    # Already correct, verbatim confirm → no changes needed
    assert new_text == "火悟空衝線奪冠"
    assert changes == []


def test_deterministic_apply_alias_replace():
    # Alias "火悟空B" should be replaced with canonical "火悟空"
    cands = [{"source": "Blazing Wukong", "target": "火悟空", "glossary": "racing",
              "side": "target", "aliases": ["火悟空B", "悟空"]}]
    new_text, changes = G.deterministic_apply("火悟空B好勁", cands)
    assert "火悟空" in new_text
    # changes recorded
    assert len(changes) >= 1


def test_deterministic_apply_immutable():
    # Input text is a string; original not mutated (strings are immutable, just ensure no side-effect)
    cands = [{"source": "Amazing", "target": "活力", "glossary": "A", "side": "target"}]
    original = "活力十足"
    new_text, _ = G.deterministic_apply(original, cands)
    assert original == "活力十足"  # unchanged


# ---------------------------------------------------------------------------
# glossary_stage — full integration with mock llm_call
# ---------------------------------------------------------------------------

def _mock_llm(system, user):
    """Mock llm_call: returns canonical JSON with known replacements."""
    if "Blazing Wukong" in user and "Amazing Partners" in user:
        return '{"text": "火悟空與活力拍檔爭奪錦標"}'
    if "Blazing Wukong" in user:
        return '{"text": "火悟空衝線奪冠"}'
    if "Amazing Partners" in user:
        return '{"text": "活力拍檔奪冠"}'
    return '{"text": "' + user.split("中文：")[-1].strip() + '"}'


_RACING_GLOSSARY = _make_glossary(
    "racing", "Racing 1350", "en", "zh",
    [
        {"source": "Blazing Wukong", "target": "火悟空 (K335)"},
        {"source": "Amazing Partners", "target": "活力拍檔"},
    ]
)


def test_glossary_stage_blazing_wukong_replaced():
    segs = [
        {"text": "Blazing Wukong shoots ahead", "src_text": "Blazing Wukong shoots ahead",
         "start": 0.0, "end": 2.0}
    ]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    assert len(result) == 1
    new_seg = result[0]
    # text should be modified (Chinese canonical name)
    assert "火悟空" in new_seg["text"]
    # glossary_changes should be populated
    assert isinstance(new_seg["glossary_changes"], list)
    assert len(new_seg["glossary_changes"]) >= 1
    change = new_seg["glossary_changes"][0]
    assert "source" in change
    assert "before" in change
    assert "after" in change
    assert "glossary" in change
    assert change["after"] == "火悟空衝線奪冠" or "火悟空" in change["after"]


def test_glossary_stage_amazing_partners_and_blazing_wukong():
    segs = [
        {"text": "Amazing Partners and Blazing Wukong race hard",
         "src_text": "Amazing Partners and Blazing Wukong race hard",
         "start": 0.0, "end": 3.0}
    ]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    new_seg = result[0]
    assert "火悟空" in new_seg["text"] or "活力拍檔" in new_seg["text"]
    assert len(new_seg["glossary_changes"]) >= 1


def test_glossary_stage_common_word_class_not_changed():
    segs = [
        {"text": "In a class 3 sprint final",
         "src_text": "In a class 3 sprint final",
         "start": 0.0, "end": 2.0}
    ]
    # Add "class" as a glossary term (mirrors the false-positive scenario)
    g = _make_glossary("a", "FakeGlossary", "en", "zh",
                       [{"source": "class", "target": "大文豪"}])
    result = G.glossary_stage(
        segs, [g],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    new_seg = result[0]
    # Guard should reject — text unchanged
    assert new_seg["text"] == "In a class 3 sprint final"
    assert new_seg["glossary_changes"] == []


def test_glossary_stage_no_glossaries_unchanged():
    segs = [
        {"text": "Blazing Wukong wins the race", "start": 0.0, "end": 2.0}
    ]
    result = G.glossary_stage(
        segs, [],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    assert result[0]["text"] == "Blazing Wukong wins the race"
    assert result[0]["glossary_changes"] == []


def test_glossary_stage_immutable_inputs():
    """Original segments list and dicts must not be mutated."""
    segs = [
        {"text": "Blazing Wukong races", "src_text": "Blazing Wukong races",
         "start": 0.0, "end": 2.0}
    ]
    original_text = segs[0]["text"]
    G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    # Original segment must not be mutated
    assert segs[0]["text"] == original_text
    assert "glossary_changes" not in segs[0]


def test_glossary_stage_use_llm_false_no_llm_call():
    """With use_llm=False, llm_call should never be invoked."""
    def _fail_llm(system, user):
        raise AssertionError("llm_call should not be called when use_llm=False")

    segs = [
        {"text": "Blazing Wukong races", "src_text": "Blazing Wukong races",
         "start": 0.0, "end": 2.0}
    ]
    # Should not raise
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_fail_llm, use_llm=False
    )
    # glossary_changes still populated (empty since no deterministic change happened for src-side)
    assert isinstance(result[0]["glossary_changes"], list)


def test_glossary_stage_src_texts_param():
    """src_texts kwarg: source text for source-side filtering (separate from seg['text'])."""
    # seg["text"] is already the Chinese output; src_text is English for filtering
    segs = [
        {"text": "已轉為中文字幕", "start": 0.0, "end": 2.0}  # no src_text key
    ]
    src_texts = ["Blazing Wukong charges to the front"]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True,
        src_texts=src_texts
    )
    # Candidate should be found via src_texts; LLM should be called
    # The mock returns "火悟空衝線奪冠" for Blazing Wukong
    assert isinstance(result[0]["glossary_changes"], list)
    # text changed because Blazing Wukong was found in src_texts
    assert "火悟空" in result[0]["text"]


def test_glossary_stage_preserves_other_segment_fields():
    """All non-text fields in the segment dict are preserved unchanged."""
    segs = [
        {"text": "normal segment", "start": 1.5, "end": 3.0,
         "src_text": "normal segment", "some_extra": "preserved"}
    ]
    result = G.glossary_stage(
        segs, [],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    assert result[0]["start"] == 1.5
    assert result[0]["end"] == 3.0
    assert result[0]["some_extra"] == "preserved"


def test_glossary_stage_multiple_segments():
    segs = [
        {"text": "Blazing Wukong leads", "src_text": "Blazing Wukong leads",
         "start": 0.0, "end": 2.0},
        {"text": "Amazing Partners closes in", "src_text": "Amazing Partners closes in",
         "start": 2.0, "end": 4.0},
        {"text": "A normal segment with no terms", "src_text": "A normal segment with no terms",
         "start": 4.0, "end": 6.0},
    ]
    result = G.glossary_stage(
        segs, [_RACING_GLOSSARY],
        output_lang="zh", content_lang="en", derive_mode="mt",
        llm_call=_mock_llm, use_llm=True
    )
    assert len(result) == 3
    # First two segments should have changes; third should not
    assert result[0]["glossary_changes"] != [] or "火悟空" in result[0]["text"]
    assert result[2]["glossary_changes"] == []


# ---------------------------------------------------------------------------
# Task 1: candidates carry entry_id/glossary_id + changes carry lang (add-only)
# ---------------------------------------------------------------------------

def _gl(entries, name="測試表", gid="g-1", src="en", tgt="zh"):
    return {"id": gid, "name": name, "source_lang": src, "target_lang": tgt,
            "entries": entries}


def test_filter_candidates_carry_entry_and_glossary_ids():
    from output_lang_glossary import _filter_source_side, _filter_target_side
    g = _gl([{"id": "e-77", "source": "Happy Valley", "target": "跑馬地",
              "target_aliases": ["快活谷"]}])
    src_cands = _filter_source_side("Races at Happy Valley tonight.", [g],
                                    output_lang="zh", content_lang="en", derive_mode="mt")
    assert src_cands and src_cands[0]["entry_id"] == "e-77"
    assert src_cands[0]["glossary_id"] == "g-1"
    tgt_cands = _filter_target_side("快活谷今晚有賽事。", [g],
                                    output_lang="zh", content_lang="yue", derive_mode="refine")
    assert tgt_cands and tgt_cands[0]["entry_id"] == "e-77"
    assert tgt_cands[0]["glossary_id"] == "g-1"


def test_glossary_stage_changes_carry_lang():
    from output_lang_glossary import glossary_stage
    g = _gl([{"id": "e-1", "source": "Happy Valley", "target": "跑馬地",
              "target_aliases": ["快活谷"]}])
    segs = [{"text": "快活谷今晚有賽事。", "start": 0.0, "end": 2.0}]
    out = glossary_stage(segs, [g], output_lang="yue", content_lang="yue",
                         derive_mode="pass", llm_call=lambda s, u: "", use_llm=False)
    chs = out[0]["glossary_changes"]
    assert chs and chs[0]["lang"] == "yue"
    assert chs[0]["before"] == "快活谷" and chs[0]["after"] == "跑馬地"
