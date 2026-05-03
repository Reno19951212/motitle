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
def transcribe_fine_seg(audio_path: str, profile: dict,
                        ws_emit: Optional[Callable[[str, str], None]] = None):
    """Full pipeline: VAD pre-seg → per-chunk mlx transcribe → word-gap refine.

    Args:
        audio_path: 16kHz mono WAV path
        profile: full active profile dict (reads asr.* fields)
        ws_emit: optional callback (kind, message) for runtime warnings

    Raises:
        FineSegmentationError: setup-level (missing silero-vad or mlx-whisper)

    Returns:
        List[Segment] dicts with words[] preserved
    """
    # F1 strict — setup errors raise immediately
    try:
        from silero_vad import load_silero_vad, get_speech_timestamps, read_audio
    except ImportError as e:
        raise FineSegmentationError(
            "silero-vad not installed; run: pip install silero-vad"
        ) from e

    try:
        import mlx_whisper
    except ImportError as e:
        raise FineSegmentationError("mlx-whisper not installed") from e

    # Pipeline implementation completed in Task B6
    raise NotImplementedError("Pipeline body in Task B6")


def word_gap_split(segments, *, max_dur: float = 4.0, gap_thresh: float = 0.10,
                   min_dur: float = 1.5, safety_max_dur: float = 9.0):
    """Recursively split segments > max_dur at largest inter-word gap.

    Behavior:
      - Segment with duration ≤ max_dur or < 4 words → kept as-is
      - Segment with duration > max_dur:
          1. Find candidate gaps (must respect min_dur on both sides)
          2. Take largest gap
          3. If best gap ≥ gap_thresh: split, recurse on both halves
          4. If best gap < gap_thresh AND duration ≤ safety_max_dur: keep as-is
          5. If duration > safety_max_dur: force split at largest gap regardless
    """
    out = []
    for s in segments:
        out.extend(_split_one(s, max_dur, gap_thresh, min_dur, safety_max_dur))
    return out


def _split_one(seg, max_dur, gap_thresh, min_dur, safety_max_dur):
    duration = seg["end"] - seg["start"]
    words = seg.get("words") or []
    if duration <= max_dur or len(words) < 4:
        return [seg]

    seg_start, seg_end = seg["start"], seg["end"]
    candidates = []
    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i - 1]["end"]
        left_dur = words[i - 1]["end"] - seg_start
        right_dur = seg_end - words[i]["start"]
        if left_dur >= min_dur and right_dur >= min_dur:
            candidates.append((i, gap))

    if not candidates:
        return [seg]

    candidates.sort(key=lambda x: -x[1])
    best_i, best_gap = candidates[0]

    force_split = duration > safety_max_dur
    if best_gap < gap_thresh and not force_split:
        return [seg]

    left_words = words[:best_i]
    right_words = words[best_i:]
    left = {
        **seg,
        "text": " ".join(w["word"].strip() for w in left_words).strip(),
        "start": left_words[0]["start"],
        "end": left_words[-1]["end"],
        "words": left_words,
    }
    right = {
        **seg,
        "text": " ".join(w["word"].strip() for w in right_words).strip(),
        "start": right_words[0]["start"],
        "end": right_words[-1]["end"],
        "words": right_words,
    }

    result = []
    for c in (left, right):
        result.extend(_split_one(c, max_dur, gap_thresh, min_dur, safety_max_dur))
    return result


# Sample rate for Silero VAD + mlx-whisper
_SR = 16000


def _subcap_chunks(spans, max_s: int):
    """Sub-cap any span > max_s seconds into ≤ max_s sub-chunks (sample-indexed)."""
    chunk_max = max_s * _SR
    out = []
    for cs, ce in spans:
        if (ce - cs) <= chunk_max:
            out.append((cs, ce))
        else:
            cur = cs
            while cur < ce:
                out.append((cur, min(cur + chunk_max, ce)))
                cur += chunk_max
    return out
