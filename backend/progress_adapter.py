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
