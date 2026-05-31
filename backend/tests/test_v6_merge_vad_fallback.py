"""D2 — TimeAnchoredMergeStage coarse-block VAD fallback (V6 mlx timing fix)."""
from types import SimpleNamespace
from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage


def _ctx(qwen3_chars, vad_regions=None):
    ov = {"__qwen3_chars": qwen3_chars}
    if vad_regions is not None:
        ov["__vad_regions"] = vad_regions
    return SimpleNamespace(pipeline_overrides=ov)


def _chars(spec):
    return [{"start": s, "end": e, "text": t} for (s, e, t) in spec]


def test_coarse_block_resegmented_by_vad():
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara.org 社群提供"}]
    vad = [{"start": 7.8, "end": 10.8}, {"start": 12.3, "end": 27.2}, {"start": 27.2, "end": 30.0}]
    chars = _chars([(7.9, 8.0, "今"), (8.1, 8.2, "晚"),
                    (13.0, 13.1, "佢"), (20.0, 20.1, "望"), (28.0, 28.1, "尾")])
    out = stage.transform(mlx, _ctx(chars, vad))
    assert out, "expected re-segmented output"
    assert abs(out[0]["start"] - 7.8) < 0.01, f"first seg should start at VAD start, got {out[0]['start']}"
    assert out[0]["start"] != 0.0
    assert all((s["end"] - s["start"]) < 25 for s in out)
    joined = "".join(s["text"] for s in out)
    for ch in "今晚佢望尾":
        assert ch in joined


def test_healthy_blocks_unchanged():
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 3.0, "text": "x"}, {"start": 3.0, "end": 6.0, "text": "y"}]
    chars = _chars([(0.5, 0.6, "甲"), (1.5, 1.6, "乙"), (4.0, 4.1, "丙")])
    vad = [{"start": 0.0, "end": 3.0}, {"start": 3.0, "end": 6.0}]
    with_vad = stage.transform(mlx, _ctx(chars, vad))
    without_vad = stage.transform(mlx, _ctx(chars, None))
    assert with_vad == without_vad
    assert [s["text"] for s in with_vad] == ["甲乙", "丙"]


def test_no_vad_coverage_falls_back_to_qwen3_span():
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara"}]
    chars = _chars([(7.9, 8.0, "今"), (28.0, 28.1, "尾")])
    out = stage.transform(mlx, _ctx(chars, vad_regions=[{"start": 100.0, "end": 110.0}]))
    assert len(out) == 1
    assert abs(out[0]["start"] - 7.9) < 0.01 and abs(out[0]["end"] - 28.1) < 0.01


def test_vad_regions_missing_no_crash():
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara"}]
    chars = _chars([(7.9, 8.0, "今"), (28.0, 28.1, "尾")])
    out = stage.transform(mlx, _ctx(chars, vad_regions=None))
    assert len(out) == 1 and abs(out[0]["start"] - 7.9) < 0.01


def test_chars_outside_slots_assigned_nearest():
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara"}]
    vad = [{"start": 7.8, "end": 10.8}, {"start": 20.0, "end": 25.0}]
    chars = _chars([(9.0, 9.1, "甲"), (15.0, 15.1, "乙"), (22.0, 22.1, "丙")])
    out = stage.transform(mlx, _ctx(chars, vad))
    joined = "".join(s["text"] for s in out)
    assert "甲" in joined and "乙" in joined and "丙" in joined
