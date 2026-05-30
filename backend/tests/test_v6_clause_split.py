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
