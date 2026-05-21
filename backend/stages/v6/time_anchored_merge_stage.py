"""TimeAnchoredMergeStage — v6 Stage 2.

Algorithm: for each mlx slot [start, end), collect qwen3 chars whose
midpoint falls in [start, end), concatenate as that slot's text.
Empty slots (mlx hallucinations / cascade dups) collapse into the
preceding kept slot (extending its end time).

Input via transform():
  segments_in:  mlx-whisper segs [{start, end, text}] (~90)
  context.pipeline_overrides["__qwen3_chars"]: qwen3 flat chars [{start, end, text}]

Output: merged subtitle-sized segments [{start, end, text}] (~84)
"""
from __future__ import annotations
from typing import List, Optional
from stages import PipelineStage, StageContext


def _midpoint(c: dict) -> float:
    s, e = float(c.get("start") or 0), float(c.get("end") or 0)
    return (s + e) / 2.0 if e > s else s


class TimeAnchoredMergeStage(PipelineStage):
    def __init__(self, profile: dict):
        self._profile = profile

    @property
    def stage_type(self) -> str:
        return "time_anchored_merge"

    @property
    def stage_ref(self) -> str:
        return self._profile.get("id", "time_anchored_merge")

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """segments_in = mlx-whisper segs. qwen3 chars from context overrides."""
        qwen3_chars = list(context.pipeline_overrides.get("__qwen3_chars") or [])
        merged = self._time_anchored_merge(segments_in, qwen3_chars)
        return self._collapse_empty_slots(merged)

    def _time_anchored_merge(
        self, mlx_segs: List[dict], qwen3_chars: List[dict]
    ) -> List[dict]:
        out = []
        for m in mlx_segs:
            ws = float(m["start"])
            we = float(m["end"])
            chars_in = [c for c in qwen3_chars if ws <= _midpoint(c) < we]
            out.append({
                "start": ws,
                "end": we,
                "text": "".join(c.get("text", "") for c in chars_in).strip(),
            })
        return out

    def _collapse_empty_slots(self, merged: List[dict]) -> List[dict]:
        """Drop empty slots; extend prev keep's end to absorb their timecode."""
        final: List[dict] = []
        pending_end: Optional[float] = None
        for s in merged:
            if not s["text"]:
                pending_end = float(s["end"])
                continue
            seg = {k: v for k, v in s.items()}
            if pending_end is not None and final:
                final[-1]["end"] = max(float(final[-1]["end"]), pending_end)
                pending_end = None
            elif pending_end is not None:
                # pending before first kept seg — discard (head silence)
                pending_end = None
            final.append(seg)
        # Trailing empty slots: extend last kept slot
        if pending_end is not None and final:
            final[-1]["end"] = max(float(final[-1]["end"]), pending_end)
        return final
