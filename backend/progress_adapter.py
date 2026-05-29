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
