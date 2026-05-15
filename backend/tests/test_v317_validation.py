"""Unit tests for v3.17 validation metric helpers on dummy snapshot data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import v317_validation as v


def _mk_snapshot(segments, translations, file_extras=None, glossary_scan=None):
    return {
        "captured_at": "2026-05-15T00:00:00Z",
        "file": {"id": "test", "duration_seconds": 60.0, "asr_seconds": 30.0, "translation_seconds": 10.0, **(file_extras or {})},
        "segments": segments,
        "translations": translations,
        "profile_snapshot": None,
        "glossary_scan": glossary_scan,
    }


def test_latency_delta_basic():
    b = _mk_snapshot([], [])
    p = _mk_snapshot([], [], file_extras={"asr_seconds": 25.0, "translation_seconds": 12.0})
    out = v.latency_delta(b, p)
    assert out["baseline_asr_seconds"] == 30.0
    assert out["post_asr_seconds"] == 25.0
    assert out["baseline_asr_sec_per_min"] == 30.0
    assert out["post_asr_sec_per_min"] == 25.0


def test_segmentation_delta_count():
    b = _mk_snapshot([{"start": 0, "end": 2.0, "text": "hello world"}], [])
    p = _mk_snapshot([{"start": 0, "end": 2.0, "text": "hello world"}, {"start": 2.5, "end": 4.0, "text": "again"}], [])
    out = v.segmentation_delta(b, p)
    assert out["baseline"]["count"] == 1
    assert out["post"]["count"] == 2


def test_asr_text_delta_identical_changed_new_dropped():
    b_segs = [
        {"start": 0.0, "end": 1.0, "text": "A"},
        {"start": 1.0, "end": 2.0, "text": "B"},
        {"start": 5.0, "end": 6.0, "text": "DROPPED"},
    ]
    p_segs = [
        {"start": 0.0, "end": 1.0, "text": "A"},        # identical
        {"start": 1.05, "end": 2.0, "text": "B2"},      # changed (within tolerance)
        {"start": 7.0, "end": 8.0, "text": "NEW"},      # new
    ]
    out = v.asr_text_delta(_mk_snapshot(b_segs, []), _mk_snapshot(p_segs, []))
    assert out["identical"] == 1
    assert out["changed_count"] == 1
    assert out["new_count"] == 1
    assert out["dropped_count"] == 1


def test_mt_text_delta_paired_by_index():
    b_t = [{"en_text": "x", "zh_text": "甲"}, {"en_text": "y", "zh_text": "乙"}]
    p_t = [{"en_text": "x", "zh_text": "甲"}, {"en_text": "y", "zh_text": "丙"}]
    out = v.mt_text_delta(_mk_snapshot([], b_t), _mk_snapshot([], p_t))
    assert out["identical"] == 1
    assert out["changed_count"] == 1


def test_glossary_scan_delta_skipped_when_no_data():
    b = _mk_snapshot([], [], glossary_scan=None)
    p = _mk_snapshot([], [], glossary_scan=None)
    out = v.glossary_scan_delta(b, p)
    assert out["skipped"] is True


def test_glossary_scan_delta_counts():
    b = _mk_snapshot([], [], glossary_scan={"strict_violation_count": 5, "loose_violation_count": 2, "strict_violations": [], "loose_violations": []})
    p = _mk_snapshot([], [], glossary_scan={"strict_violation_count": 1, "loose_violation_count": 0, "strict_violations": [], "loose_violations": []})
    out = v.glossary_scan_delta(b, p)
    assert out["baseline_strict_count"] == 5
    assert out["post_strict_count"] == 1


def test_subtitle_length_distribution_buckets():
    t = [{"zh_text": "短"}, {"zh_text": "中等長度的字幕內容文字"}, {"zh_text": "x" * 35}, {"zh_text": "y" * 50}]
    out = v.subtitle_length_distribution(t)
    assert out["0-10"] == 1
    assert out["11-15"] == 1
    assert out["29-40"] == 1
    assert out[">40"] == 1


def test_reading_speed_cps_band():
    # seg0: 30 chars / 1s = 30 CPS → too_fast (>20)
    # seg1: 1 char / 2s = 0.5 CPS → too_slow (<8)
    # seg2: 10 ascii chars / 1s = 10 CPS → in band (8-20)
    segs = [{"start": 0, "end": 1.0}, {"start": 1.0, "end": 3.0}, {"start": 3.0, "end": 4.0}]
    trans = [{"zh_text": "甲乙丙丁戊己庚辛壬癸甲乙丙丁戊己庚辛壬癸甲乙丙丁戊己庚辛壬癸"}, {"zh_text": "短"}, {"zh_text": "abcdefghij"}]
    out = v.reading_speed_cps(trans, segs)
    assert out["too_fast_count"] >= 1
    assert out["too_slow_count"] >= 1


def test_language_consistency_en_with_cjk():
    segs = [{"start": 0, "end": 1, "text": "Hello 世界 world"}, {"start": 1, "end": 2, "text": "no cjk here"}]
    trans = [{"zh_text": "純中文"}]
    out = v.language_consistency(segs, trans)
    assert out["en_with_cjk_count"] == 1


def test_language_consistency_zh_with_latin_brand_excluded():
    segs = []
    trans = [{"zh_text": "佢喺 NBA 比賽中"}, {"zh_text": "佢喺 random English 比賽中"}]
    out = v.language_consistency(segs, trans)
    assert out["zh_with_latin_count"] == 1  # NBA excluded by whitelist, "random English" detected


def test_repetition_detect_substring_match():
    trans = [{"zh_text": "甲乙丙丁戊"}, {"zh_text": "甲乙丙丁戊己"}, {"zh_text": "完全不同的內容"}]
    out = v.repetition_detect(trans, min_overlap_ratio=0.5)
    assert len(out) >= 1
    assert out[0]["index"] == 0


def test_segment_timing_health_short_and_long():
    segs = [
        {"start": 0, "end": 0.2, "text": "tiny"},   # too short
        {"start": 0.2, "end": 8.5, "text": "long"}, # too long
        {"start": 9.0, "end": 11.0, "text": "ok"},
    ]
    out = v.segment_timing_health(segs)
    assert out["too_short_count"] == 1
    assert out["too_long_count"] == 1


def test_flag_rates_counts():
    trans = [
        {"zh_text": "短", "flags": []},
        {"zh_text": "x" * 50, "flags": ["long"]},
        {"zh_text": "y", "flags": ["review"]},
    ]
    out = v.flag_rates(trans)
    assert out["long_flag_count"] == 1
    assert out["review_flag_count"] == 1
    assert out["hallucination_count"] == 1


def test_batch_boundary_check_repetition():
    trans = [
        {"zh_text": "段一"}, {"zh_text": "段二"}, {"zh_text": "段二"},  # boundary at index 2; repetition!
        {"zh_text": "段四"}, {"zh_text": "段五"}, {"zh_text": "段六"},
    ]
    out = v.batch_boundary_check(trans, batch_size=2)
    assert out["edge_repetition_count"] >= 1


def test_batch_boundary_check_skipped_when_batch1():
    out = v.batch_boundary_check([{"zh_text": "x"}], batch_size=1)
    assert out["skipped"] is True


def test_word_level_alignment_pct():
    segs = [{"words": [{"word": "a"}]}, {"words": []}, {"words": [{"word": "b"}, {"word": "c"}]}]
    out = v.word_level_alignment(segs)
    # [] is falsy so second segment filtered out; first + third counted
    assert out["with_words_count"] == 2
    assert out["total_segments"] == 3


def test_approval_state_note_present():
    b = [{"status": "approved"}, {"status": "approved"}, {"status": "pending"}]
    p = [{"status": "pending"}, {"status": "pending"}, {"status": "pending"}]
    out = v.approval_state(b, p)
    assert out["baseline"]["approved"] == 2
    assert out["post"]["approved"] == 0
    assert "Post re-run resets" in out["note"]
