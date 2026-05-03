"""Fine-grained ASR segmentation via Silero VAD pre-segment + word-gap refine.

Pipeline:
  audio.wav
    → Silero VAD pre-segment (speech spans)
    → sub-cap chunks ≤ vad_chunk_max_s
    → mlx-whisper transcribe per chunk (temperature=0.0, word_timestamps=True,
       condition_on_previous_text=False); shift offsets back to file timeline
    → concat
    → word_gap_split (recursive split at largest inter-word gap above threshold)
    → final List[Segment] with words[] preserved

Activated by profile asr.fine_segmentation=true. Engine must be mlx-whisper.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class FineSegmentationError(Exception):
    """Raised for setup-level failures (missing silero-vad, missing mlx-whisper)."""


# Public API — implementations added in subsequent tasks
def transcribe_fine_seg(audio_path: str, profile: dict, ws_emit: Optional[Callable[[str, str], None]] = None):
    """Full pipeline; returns List[Segment] with words[]."""
    raise NotImplementedError("transcribe_fine_seg implemented in Task B5/B6")


def word_gap_split(segments, *, max_dur: float = 4.0, gap_thresh: float = 0.10,
                   min_dur: float = 1.5, safety_max_dur: float = 9.0):
    """Recursive split of long segments at largest inter-word gap."""
    raise NotImplementedError("word_gap_split implemented in Task B2")
