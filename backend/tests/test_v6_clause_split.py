import copy
from stages.v6.clause_split import (
    _atomic_clauses, _pack_lines, _apply_min_dur_guard,
    clause_split_segment, split_v6_aligned,
    DEFAULT_CHAR_CAP, DEFAULT_MIN_DUR,
)


def test_atomic_clauses_keeps_trailing_punct():
    assert _atomic_clauses("甲，乙。丙") == ["甲，", "乙。", "丙"]


def test_pack_lines_respects_cap():
    lines = _pack_lines(["甲乙，", "丙丁，", "戊己庚辛壬癸"], char_cap=6)
    assert lines == ["甲乙，丙丁，", "戊己庚辛壬癸"]


def test_short_segment_not_split():
    seg = {"start": 0.0, "end": 3.0, "text": "下個月有新騎師登場"}
    assert clause_split_segment(seg) == [seg]


def test_long_segment_splits_at_punctuation_lossless_monotonic():
    seg = {"start": 12.0, "end": 25.0,
           "text": "打鼓嶺警署係香港最具代表性嘅邊境警署之一，至今仍然保留住二戰前嘅建築設計原貌，滿載歲月痕跡，現已被評為三級歷史建築"}
    pieces = clause_split_segment(seg, char_cap=24, min_dur=1.0)
    assert len(pieces) >= 3
    assert "".join(p["text"] for p in pieces) == seg["text"]
    assert pieces[0]["start"] == 12.0
    assert abs(pieces[-1]["end"] - 25.0) < 0.01
    for a, b in zip(pieces, pieces[1:]):
        assert a["end"] <= b["start"] + 1e-6


def test_single_overcap_clause_not_broken():
    seg = {"start": 0.0, "end": 6.0,
           "text": "今集嘅區區有警就等我哋帶大家深入了解打鼓嶺分區嘅警務工作同埋"}
    assert clause_split_segment(seg, char_cap=24) == [seg]


def test_guard_merges_short_piece_forward():
    pieces = [
        {"start": 0.0, "end": 0.5, "text": "甲，"},
        {"start": 0.5, "end": 4.0, "text": "乙丙丁"},
    ]
    out = _apply_min_dur_guard(pieces, 1.0)
    assert out == [{"start": 0.0, "end": 4.0, "text": "甲，乙丙丁"}]


def test_guard_merges_last_piece_backward():
    pieces = [
        {"start": 0.0, "end": 4.0, "text": "甲乙丙"},
        {"start": 4.0, "end": 4.4, "text": "丁。"},
    ]
    out = _apply_min_dur_guard(pieces, 1.0)
    assert out == [{"start": 0.0, "end": 4.4, "text": "甲乙丙丁。"}]


def test_split_then_guard_no_subsecond_piece():
    seg = {"start": 5.0, "end": 6.0,
           "text": "大家好，今集區區有警，帶大家了解打鼓嶺分區警務工作"}
    pieces = clause_split_segment(seg, char_cap=24, min_dur=1.0)
    for p in pieces:
        assert (p["end"] - p["start"]) >= 1.0 - 1e-6


def test_immutability():
    seg = {"start": 0.0, "end": 10.0, "text": "甲，乙，丙，丁，戊，己，庚，辛，壬，癸，子，丑，寅"}
    snap = copy.deepcopy(seg)
    clause_split_segment(seg)
    assert seg == snap


def test_empty_text_passthrough():
    seg = {"start": 0.0, "end": 1.0, "text": ""}
    assert clause_split_segment(seg) == [seg]


def test_split_v6_aligned_passthrough_when_short():
    source = [{"start": 0.0, "end": 3.0, "text": "短句原文"}]
    refined = [{"start": 0.0, "end": 3.0, "text": "短句", "flags": []}]
    ns, nr = split_v6_aligned(source, refined, char_cap=24)
    assert len(ns) == 1 and len(nr) == 1
    assert ns[0]["text"] == "短句原文" and nr[0]["text"] == "短句"


def test_split_v6_aligned_expands_and_aligns():
    source = [{"start": 0.0, "end": 10.0,
               "text": "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥一二三四"}]
    refined = [{"start": 0.0, "end": 10.0,
                "text": "甲乙丙丁，戊己庚辛壬癸，子丑寅卯辰巳午未申酉戌亥一二三四", "flags": []}]
    ns, nr = split_v6_aligned(source, refined, char_cap=12, min_dur=1.0)
    assert len(ns) == len(nr) >= 2
    assert "".join(p["text"] for p in nr) == refined[0]["text"]
    assert "".join(p["text"] for p in ns) == source[0]["text"]
    for s, r in zip(ns, nr):
        assert s["start"] == r["start"] and s["end"] == r["end"]
    for a, b in zip(ns, ns[1:]):
        assert a["end"] <= b["start"] + 1e-6
    assert all("flags" in r for r in nr)


def test_split_v6_aligned_does_not_mutate_inputs():
    source = [{"start": 0.0, "end": 10.0, "text": "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥一二三四"}]
    refined = [{"start": 0.0, "end": 10.0, "text": "甲乙丙丁，戊己庚辛，壬癸子丑寅卯辰巳午未申酉戌亥", "flags": []}]
    s_snap, r_snap = copy.deepcopy(source), copy.deepcopy(refined)
    split_v6_aligned(source, refined, char_cap=12)
    assert source == s_snap and refined == r_snap


class TestSplitV6AlignedMissingSourceTiming:
    """BUG #2: fallback source dict must use 0.0, not None, when refined lacks timing."""

    def test_no_typeerror_when_refined_lacks_timing(self):
        """Fewer source_segs than refined_segs AND refined lacks start/end
        → fallback source dict must use 0.0 not None → no TypeError in arithmetic."""
        source = []  # deliberately empty — triggers the fallback dict path
        refined = [{"text": "甲乙丙丁，戊己庚辛，壬癸子丑，寅卯辰巳，午未申酉，戌亥", "flags": []}]
        # This must NOT raise TypeError; without the fix it does because
        # p["end"] - p["start"] receives None - None.
        try:
            ns, nr = split_v6_aligned(source, refined, char_cap=12, min_dur=1.0)
        except TypeError as exc:
            raise AssertionError(f"split_v6_aligned raised TypeError: {exc}") from exc
        # All source pieces must have numeric (not None) start/end.
        # The bug was that the fallback source dict used None, causing TypeError
        # in _apply_min_dur_guard's arithmetic.
        for s in ns:
            assert s["start"] is not None and s["end"] is not None, \
                f"source piece has None timing: {s}"
            assert isinstance(s["start"], (int, float)), f"start not numeric: {s['start']}"
            assert isinstance(s["end"], (int, float)), f"end not numeric: {s['end']}"
        # Refined pieces that went through the split path have start/end from pieces;
        # passthrough (len==1) pieces mirror whatever the input had.
        for r in nr:
            if "start" in r:
                assert r["start"] is not None, f"refined piece has None start: {r}"
            if "end" in r:
                assert r["end"] is not None, f"refined piece has None end: {r}"

    def test_fallback_source_uses_zero_when_refined_has_no_timing(self):
        """Refined seg with no start/end keys → fallback source start==0.0, end==0.0."""
        source = []
        refined = [{"text": "短句", "flags": []}]  # len<=cap → no split → passes through
        ns, nr = split_v6_aligned(source, refined, char_cap=24)
        assert ns[0]["start"] == 0.0
        assert ns[0]["end"] == 0.0

    def test_fallback_source_uses_refined_timing_when_present(self):
        """Refined seg with valid timing → fallback source copies those values."""
        source = []
        refined = [{"start": 2.5, "end": 5.0, "text": "短句", "flags": []}]
        ns, nr = split_v6_aligned(source, refined, char_cap=24)
        assert ns[0]["start"] == 2.5
        assert ns[0]["end"] == 5.0


class TestClauseSplitSegmentMutability:
    """BUG #3: clause_split_segment must not share nested mutable state with input."""

    def test_short_path_does_not_share_flags_list(self):
        """Short segment (<=cap) returns [dict(seg)] shallow copy — flags list shared.
        After fix (deepcopy), mutating returned flags must NOT affect original."""
        seg = {"start": 0.0, "end": 2.0, "text": "短句", "flags": ["f1"]}
        result = clause_split_segment(seg, char_cap=24)
        assert len(result) == 1
        # Mutate the returned copy's flags
        result[0]["flags"].append("mutated")
        # Original must be unchanged
        assert seg["flags"] == ["f1"], \
            f"Original flags were mutated to {seg['flags']}"

    def test_no_split_path_does_not_share_flags_list(self):
        """Over-cap but no-split case (single clause, packs to 1 line) also must
        return a deep copy so its flags list is independent."""
        # This text is over cap but has no internal punctuation → packs to 1 line → no split
        long_no_punct = "今集嘅區區有警就等我哋帶大家深入了解打鼓嶺分區嘅警務工作同埋"
        seg = {"start": 0.0, "end": 6.0, "text": long_no_punct, "flags": ["orig"]}
        result = clause_split_segment(seg, char_cap=24)
        assert len(result) == 1
        result[0]["flags"].append("mutated")
        assert seg["flags"] == ["orig"], \
            f"Original flags mutated to {seg['flags']}"

    def test_words_list_not_shared(self):
        """Any 'words' list in the segment must also not be shared with the copy."""
        seg = {"start": 0.0, "end": 2.0, "text": "短句",
               "flags": [], "words": [{"word": "短", "start": 0.0, "end": 1.0}]}
        result = clause_split_segment(seg, char_cap=24)
        assert len(result) == 1
        if "words" in result[0]:
            result[0]["words"].append({"word": "extra"})
            assert len(seg["words"]) == 1, "Original words list was mutated"


import json
import os

_SEG_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts", "v6_prototype", "seg_data")


def _load_segs(name):
    d = json.load(open(os.path.join(_SEG_DIR, f"{name}.json")))
    items = d if isinstance(d, list) else (d.get("translations") or d.get("segments") or [])
    out = []
    for it in items:
        zh = (it.get("zh_text") or (it.get("by_lang", {}).get("zh", {}) or {}).get("text") or "").strip()
        out.append({"start": float(it["start"]), "end": float(it["end"]), "text": zh, "flags": []})
    return out


def test_regression_vtdown_improves_and_guards():
    segs = _load_segs("vtdown")
    total_pieces, over_cap = 0, 0
    for s in segs:
        pieces = clause_split_segment(s, char_cap=24, min_dur=1.0)
        total_pieces += len(pieces)
        if len(pieces) > 1:
            assert "".join(x["text"] for x in pieces) == s["text"]
            for p in pieces:
                assert (p["end"] - p["start"]) >= 1.0 - 1e-6
        over_cap += sum(1 for p in pieces if len(p["text"]) > 24)
    assert total_pieces > len(segs)
    assert over_cap <= 4


def test_regression_saima_low_churn():
    segs = _load_segs("saima")
    churn = sum(1 for s in segs if len(clause_split_segment(s, char_cap=24, min_dur=1.0)) > 1)
    assert churn <= 1
