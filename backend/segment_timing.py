"""Segment timing trim — pure planner (no I/O, no Flask).

Roll-on-contact：butt-joined 邊界一齊郁（兩段各受 min_dur clamp）；
有 gap 時自由移動、clamp 喺鄰段邊界（永不重疊、唔 roll）。
Spec: docs/superpowers/specs/2026-06-11-segment-timing-design.md
"""
from typing import List, Optional, Tuple

MIN_DUR_SEC = 0.4   # 同 segment_split 嘅 0.4s floor 一致
_EPS = 1e-6


def plan_timing_change(rows: List[dict], pos: int,
                       new_start: Optional[float] = None,
                       new_end: Optional[float] = None,
                       min_dur: float = MIN_DUR_SEC) -> Tuple[List[tuple], bool]:
    """計劃一個 cue 嘅 In/Out 變更（秒，float）。

    rows: [{'start','end'}, …] snapshot（只讀）。
    回 (changes, clamped)：changes = [(idx, start, end), …] 按 idx 排序，
    包含被 roll 嘅鄰段；clamped = 有冇任何目標值被限制。

    雙邊同時改時 END 行先（用現有 start 做下限 clamp），跟住 start 用
    「已 clamp 嘅 end」做上限 — 否則 start 嘅上限會用未 clamp 嘅請求值計，
    單一請求可以寫出 <min_dur 嘅 cue／拖郁唔應該郁嘅鄰段（review 2026-06-11
    用 [0-2][2-4][4-6] grid 實證過兩個違規 case）。
    """
    if not (0 <= pos < len(rows)):
        raise ValueError("pos out of range")
    if new_start is None and new_end is None:
        raise ValueError("nothing to change")

    cur_start = float(rows[pos]["start"])
    cur_end = float(rows[pos]["end"])
    out = {}        # idx -> [start, end]
    clamped = False

    def _get(idx):
        if idx in out:
            return out[idx]
        return [float(rows[idx]["start"]), float(rows[idx]["end"])]

    if new_end is not None:
        nxt = rows[pos + 1] if pos + 1 < len(rows) else None
        butt = nxt is not None and abs(float(nxt["start"]) - cur_end) <= _EPS
        lo = cur_start + min_dur
        if butt:
            hi = float(nxt["end"]) - min_dur
        elif nxt is not None:
            hi = float(nxt["start"])
        else:
            hi = float("inf")
        v = min(hi, max(lo, float(new_end)))
        if abs(v - float(new_end)) > _EPS:
            clamped = True
        cur = _get(pos); cur[1] = v; out[pos] = cur
        if butt:
            n = _get(pos + 1); n[0] = v; out[pos + 1] = n
        cur_end = v

    if new_start is not None:
        prev = rows[pos - 1] if pos > 0 else None
        butt = prev is not None and abs(float(prev["end"]) - cur_start) <= _EPS
        hi = cur_end - min_dur          # cur_end 已係 clamp 後嘅值
        if butt:
            lo = float(prev["start"]) + min_dur
        elif prev is not None:
            lo = float(prev["end"])
        else:
            lo = 0.0
        v = min(hi, max(lo, float(new_start)))
        if abs(v - float(new_start)) > _EPS:
            clamped = True
        cur = _get(pos); cur[0] = v; out[pos] = cur
        if butt:
            p = _get(pos - 1); p[1] = v; out[pos - 1] = p

    changes = [(i, round(se[0], 3), round(se[1], 3)) for i, se in sorted(out.items())]

    # 防禦性最終驗證 — planner 嘅輸出永遠唔可以破壞 grid invariant
    # （min_dur floor + 唔可以重疊/倒轉）。理論上 end-first 排序已保證；
    # 呢度係 fail-fast 後盾（route 會將 ValueError 變 400）。
    merged = {i: (s, e) for i, s, e in changes}
    for i, (s, e) in merged.items():
        if e - s < min_dur - _EPS:
            raise ValueError("invalid range: cue would drop below minimum duration")
        prev_end = merged[i - 1][1] if (i - 1) in merged else (
            float(rows[i - 1]["end"]) if i > 0 else None)
        if prev_end is not None and s < prev_end - _EPS:
            raise ValueError("invalid range: cues would overlap")
    return changes, clamped
