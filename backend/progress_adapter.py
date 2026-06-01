"""Pipeline Progress Adapter — unified contract for all pipeline kinds.

Subscribes to pipeline-kind-native events (Profile's subtitle_segment /
translation_progress; V6's pipeline_stage_*) and emits the single
`pipeline_progress` event, caching the latest snapshot per file_id so
that /api/queue can return cold-start values.

v3.22+: per-kind ORDERED stage list + stage_index so the frontend can
render a generic ✓/●/○ step-diagram without any kind-specific branching.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProgressSnapshot:
    file_id: str
    job_id: str
    pct: Optional[int]          # 0-100; None = idle
    stage_label: str
    stage_state: str            # 'idle' | 'active' | 'done'
    pipeline_kind: str
    stages: list                # ordered [{key, label}] for this kind
    stage_index: int            # current 0-based index
    updated_at: float


# ── Per-kind stage definitions ────────────────────────────────────────────────

PIPELINE_STAGES: Dict[str, List[Dict[str, str]]] = {
    "profile": [
        {"key": "transcribe", "label": "轉錄"},
        {"key": "translate",  "label": "翻譯"},
        {"key": "proofread",  "label": "校對"},
    ],
    "pipeline_v6": [
        {"key": "vad",     "label": "VAD 切段"},
        {"key": "qwen3",   "label": "Qwen3 識別"},
        {"key": "mlx",     "label": "mlx 對齊"},
        {"key": "merge",   "label": "時間合併"},
        {"key": "refiner", "label": "Refiner 校對"},
    ],
    "output_lang": [
        {"key": "asr_first",  "label": "轉錄第一語言"},
        {"key": "asr_second", "label": "轉錄第二語言"},
    ],
}

_V6_STAGE_INDEX: Dict[str, int] = {
    "vad":                  0,
    "qwen3_per_region":     1,
    "asr_primary":          2,
    "time_anchored_merge":  3,
}


def _v6_stage_index(stage_type: str) -> int:
    """Map a V6 stage_type string to a 0-based index in PIPELINE_STAGES['pipeline_v6']."""
    if (stage_type or "").startswith("refiner"):
        return 4
    return _V6_STAGE_INDEX.get(stage_type, 0)


# ── ProgressAdapter ───────────────────────────────────────────────────────────

class ProgressAdapter:
    def __init__(self, emit_fn=None, throttle_seconds: float = 0.5):
        """
        emit_fn: callable(event_name, payload_dict). In production this is
                 socketio.emit; in tests pass a list-appender.
        throttle_seconds: minimum gap between successive emits per file_id
                          during 'active' state. 'idle' and 'done' bypass.
        """
        self._emit_fn = emit_fn or (lambda evt, payload: None)
        self._cache: Dict[str, ProgressSnapshot] = {}
        self._last_emit_at: Dict[str, float] = {}
        self._throttle = throttle_seconds
        self._lock = threading.RLock()

    def report(self, *, file_id: str, job_id: str, pct: Optional[int],
               stage_state: str, pipeline_kind: str,
               stage_index: int = 0,
               stage_label: Optional[str] = None) -> None:
        stages = PIPELINE_STAGES.get(pipeline_kind, [])
        if stage_label is None:
            stage_label = (stages[stage_index]["label"]
                           if 0 <= stage_index < len(stages)
                           else f"Stage {stage_index + 1}")
        now = time.monotonic()
        snap = ProgressSnapshot(
            file_id=file_id, job_id=job_id, pct=pct,
            stage_label=stage_label, stage_state=stage_state,
            pipeline_kind=pipeline_kind, stages=stages,
            stage_index=stage_index, updated_at=now,
        )
        with self._lock:
            self._cache[file_id] = snap
            # float('-inf') sentinel means never-emitted; guarantees first emit
            last = self._last_emit_at.get(file_id, float('-inf'))
            should_emit = (
                stage_state != "active"   # idle / done always emit
                or pct is None
                or (now - last) >= self._throttle
            )
            if should_emit:
                self._last_emit_at[file_id] = now
        if should_emit:
            self._emit_fn("pipeline_progress", {
                "file_id": file_id, "job_id": job_id, "pct": pct,
                "stage_label": stage_label, "stage_state": stage_state,
                "pipeline_kind": pipeline_kind,
                "stages": stages, "stage_index": stage_index,
            })

    def get_snapshot(self, file_id: str) -> Optional[ProgressSnapshot]:
        with self._lock:
            return self._cache.get(file_id)

    def clear(self, file_id: str) -> None:
        with self._lock:
            self._cache.pop(file_id, None)
            self._last_emit_at.pop(file_id, None)


# ── Profile shim helpers ──────────────────────────────────────────────────────

def report_from_subtitle_segment(adapter: ProgressAdapter, *,
                                  file_id: str, job_id: str,
                                  segment_payload: dict) -> None:
    """Profile-mode shim: subtitle_segment → pipeline_progress (stage 0 = 轉錄)."""
    progress = segment_payload.get("progress", 0)
    pct = max(0, min(100, int(round(progress * 100))))
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_state="active", pipeline_kind="profile", stage_index=0,
    )


def report_from_translation_progress(adapter: ProgressAdapter, *,
                                      file_id: str, job_id: str,
                                      translation_payload: dict) -> None:
    """Profile-mode shim: translation_progress → pipeline_progress (stage 1 = 翻譯)."""
    pct = max(0, min(100, int(translation_payload.get("percent", 0))))
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_state="active", pipeline_kind="profile", stage_index=1,
    )


# ── V6 shim helper ────────────────────────────────────────────────────────────

def report_from_v6_stage(adapter: ProgressAdapter, *,
                         file_id: str, job_id: str,
                         stage_index: int, stage_type: str,
                         stage_percent: int,
                         total_stages: int = 5) -> None:
    """V6-mode shim: pipeline_stage_progress → pipeline_progress.

    Derives the correct stage index from stage_type (fixes the label bug where
    the caller-supplied stage_index from pipeline_runner was a sequential counter
    rather than the PIPELINE_STAGES index). stage_percent is the within-stage pct.
    """
    idx = _v6_stage_index(stage_type)
    pct = max(0, min(100, int(round(stage_percent))))
    state = "done" if (idx == 4 and pct >= 100) else "active"
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_state=state, pipeline_kind="pipeline_v6", stage_index=idx,
    )


# ── Module-level singleton ────────────────────────────────────────────────────

_adapter_instance: Optional[ProgressAdapter] = None


def get_adapter() -> ProgressAdapter:
    """Lazy singleton — app.py initialises by calling init_adapter(socketio)."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ProgressAdapter()
    return _adapter_instance


def init_adapter(socketio) -> ProgressAdapter:
    """Re-initialise singleton with the real socketio.emit. Idempotent."""
    global _adapter_instance
    _adapter_instance = ProgressAdapter(emit_fn=socketio.emit)
    return _adapter_instance


def reset_adapter() -> None:
    """For tests only."""
    global _adapter_instance
    _adapter_instance = None
