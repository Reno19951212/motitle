"""Pipeline Progress Adapter — unified contract for all pipeline kinds.

Subscribes to pipeline-kind-native events (Profile's subtitle_segment /
translation_progress; V6's pipeline_stage_*) and emits the single
`pipeline_progress` event, caching the latest snapshot per file_id so
that /api/queue can return cold-start values.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ProgressSnapshot:
    file_id: str
    job_id: str
    pct: Optional[int]          # 0-100; None = idle
    stage_label: str
    stage_state: str            # 'idle' | 'active' | 'done'
    pipeline_kind: str
    updated_at: float


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
               stage_label: str, stage_state: str,
               pipeline_kind: str) -> None:
        now = time.monotonic()
        snap = ProgressSnapshot(
            file_id=file_id, job_id=job_id, pct=pct,
            stage_label=stage_label, stage_state=stage_state,
            pipeline_kind=pipeline_kind, updated_at=now,
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
    """Profile-mode shim: subtitle_segment → pipeline_progress."""
    progress = segment_payload.get("progress", 0)
    pct = max(0, min(100, int(round(progress * 100))))
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label="轉錄中", stage_state="active",
        pipeline_kind="profile",
    )


def report_from_translation_progress(adapter: ProgressAdapter, *,
                                      file_id: str, job_id: str,
                                      translation_payload: dict) -> None:
    """Profile-mode shim: translation_progress → pipeline_progress."""
    pct = max(0, min(100, int(translation_payload.get("percent", 0))))
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label="翻譯中", stage_state="active",
        pipeline_kind="profile",
    )


# ── V6 shim helper ────────────────────────────────────────────────────────────

V6_STAGE_LABELS: Dict[str, str] = {
    "vad": "VAD 切段中",
    "asr_primary": "Qwen3 識別中",
    "asr_align": "mlx 對齊中",
    "merge": "Merge 中",
    "refiner": "Refiner 校對中",
}


def report_from_v6_stage(adapter: ProgressAdapter, *,
                         file_id: str, job_id: str,
                         stage_index: int, stage_type: str,
                         stage_percent: int,
                         total_stages: int = 5) -> None:
    """V6-mode shim: pipeline_stage_progress → pipeline_progress.

    Maps stage_index + stage_percent into a single 0-100% across all
    V6 stages. Stage i contributes [i*100/N, (i+1)*100/N) range.
    """
    stage_slice = 100.0 / max(1, total_stages)
    base = stage_index * stage_slice
    contribution = (stage_percent / 100.0) * stage_slice
    pct = max(0, min(100, int(round(base + contribution))))
    label = V6_STAGE_LABELS.get(stage_type, f"Stage {stage_index + 1}")
    state = "done" if pct >= 100 else "active"
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label=label, stage_state=state,
        pipeline_kind="pipeline_v6",
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
