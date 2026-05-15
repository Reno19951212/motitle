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
