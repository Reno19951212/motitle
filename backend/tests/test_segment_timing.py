# backend/tests/test_segment_timing.py
import pytest

import segment_timing as st


ROWS = [
    {"start": 0.0, "end": 2.0},
    {"start": 2.0, "end": 4.0},    # pos 1 — butt-joined 兩邊
    {"start": 4.0, "end": 6.0},
]
GAP_ROWS = [
    {"start": 0.0, "end": 1.5},
    {"start": 2.0, "end": 4.0},    # pos 1 — 前面有 0.5s gap
    {"start": 4.5, "end": 6.0},    # 後面有 0.5s gap
]


def test_move_in_rolls_butt_joined_prev():
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=2.3)
    assert changes == [(0, 0.0, 2.3), (1, 2.3, 4.0)]
    assert clamped is False

def test_move_out_rolls_butt_joined_next():
    changes, clamped = st.plan_timing_change(ROWS, 1, new_end=4.5)
    assert changes == [(1, 2.0, 4.5), (2, 4.5, 6.0)]
    assert clamped is False

def test_gap_clamps_at_neighbour_no_roll():
    # 想拖到 1.0（入咗 prev 範圍）→ clamp 喺 prev.end=1.5，prev 不變
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.0)
    assert changes == [(1, 1.5, 4.0)]
    assert clamped is True

def test_gap_free_move_within_gap():
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.8)
    assert changes == [(1, 1.8, 4.0)]
    assert clamped is False

def test_min_dur_clamps_self():
    # In 推到 3.9 → 自己得 0.1s → clamp 喺 4.0-0.4=3.6
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=3.9)
    assert changes == [(0, 0.0, 3.6), (1, 3.6, 4.0)]
    assert clamped is True

def test_min_dur_clamps_rolled_neighbour():
    # In 拉到 0.1 → prev 得 0.1s → clamp 喺 prev.start+0.4=0.4
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=0.1)
    assert changes == [(0, 0.0, 0.4), (1, 0.4, 4.0)]
    assert clamped is True

def test_first_cue_in_clamps_at_zero():
    changes, clamped = st.plan_timing_change(ROWS, 0, new_start=-1.0)
    assert changes == [(0, 0.0, 2.0)]
    assert clamped is True

def test_last_cue_out_unbounded():
    changes, clamped = st.plan_timing_change(ROWS, 2, new_end=9.0)
    assert changes == [(2, 4.0, 9.0)]
    assert clamped is False

def test_both_edges_in_one_call():
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.8, new_end=4.2)
    assert changes == [(1, 1.8, 4.2)]
    assert clamped is False

def test_errors():
    with pytest.raises(ValueError):
        st.plan_timing_change(ROWS, 9, new_start=1.0)
    with pytest.raises(ValueError):
        st.plan_timing_change(ROWS, 1)
