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

# Cross-module dependency: shares the Apple Silicon Metal context lock with
# the mlx-whisper engine. Both must serialize transcribe() calls to avoid
# Metal context conflicts.
from asr import Word
from asr.mlx_whisper_engine import MODEL_REPO, _model_lock as _MLX_LOCK

logger = logging.getLogger(__name__)


class FineSegmentationError(Exception):
    """Raised for setup-level failures (missing silero-vad, missing mlx-whisper)."""


def transcribe_fine_seg(audio_path: str, profile: dict,
                        ws_emit: Optional[Callable[[str, str], None]] = None):
    """Full pipeline: VAD pre-seg → per-chunk mlx transcribe → word-gap refine.

    Args:
        audio_path: 16kHz mono WAV path
        profile: full active profile dict (reads asr.* fields)
        ws_emit: optional callback (kind, message) for runtime warnings

    Raises:
        FineSegmentationError: setup-level (silero-vad or mlx-whisper missing)

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

    asr_cfg = profile.get("asr") or {}

    # Stage 1: VAD pre-segment
    spans, wav = _vad_segment(
        audio_path, asr_cfg,
        load_fn=load_silero_vad, get_ts_fn=get_speech_timestamps, read_fn=read_audio,
    )

    # F2 permissive — VAD returns 0 chunks → fallback whole file
    if not spans:
        if ws_emit is not None:
            ws_emit("vad_zero",
                    "VAD detected 0 speech chunks; using whole-file transcribe")
        return _fallback_whole_file(audio_path, asr_cfg, mlx_whisper)

    # Stage 2: Sub-cap > vad_chunk_max_s
    chunks = _subcap_chunks(spans, asr_cfg.get("vad_chunk_max_s", 25))

    # Stage 3: Per-chunk mlx transcribe + offset shift
    raw = _transcribe_chunks(wav, chunks, asr_cfg, mlx_whisper, ws_emit)

    # F4 permissive — all chunks failed → fallback whole file
    if not raw:
        if ws_emit is not None:
            ws_emit("vad_fail",
                    "All chunks failed; using whole-file transcribe")
        return _fallback_whole_file(audio_path, asr_cfg, mlx_whisper)

    # Stage 4: Word-gap refine
    refined = word_gap_split(
        raw,
        max_dur=float(asr_cfg.get("refine_max_dur", 4.0)),
        gap_thresh=float(asr_cfg.get("refine_gap_thresh", 0.10)),
        min_dur=float(asr_cfg.get("refine_min_dur", 1.5)),
    )
    return refined


def word_gap_split(segments, *, max_dur: float = 4.0, gap_thresh: float = 0.10,
                   min_dur: float = 1.5, safety_max_dur: float = 6.0):
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

# Whisper hallucination guard kwargs (per mbotsu/mlx_speech2text reference).
# Lowers no_speech sensitivity + tightens compression-ratio + logprob filters
# so silent / low-information chunks don't get LLM-fabricated text like
# "Thanks for watching" / "Subscribe to my channel". Empirically validated
# across RealMadrid + Trump 5min fixtures (no regression on continuous-speech
# audio; expected to suppress hallucination on chunks with silence tail).
_HALLUCINATION_GUARDS = {
    "no_speech_threshold": 0.1,
    "compression_ratio_threshold": 1.4,
    "logprob_threshold": -1.0,
}


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


# Silero VAD model singleton (thread-safe lazy init)
_silero_model = None
_silero_lock = threading.Lock()


def _get_silero_model(load_fn):
    """Lazy-load Silero VAD ONNX model (thread-safe singleton)."""
    global _silero_model
    with _silero_lock:
        if _silero_model is None:
            _silero_model = load_fn(onnx=True)
    return _silero_model


def _build_segment(s: dict, offset: float = 0.0) -> dict:
    """Build a normalised segment dict from an mlx-whisper raw segment.

    Args:
        s: raw segment dict from mlx_whisper.transcribe() output
        offset: seconds to add to every timestamp (chunk start time in file
                timeline; 0.0 for whole-file transcriptions)

    Returns:
        dict with keys start, end, text, words — all timestamps offset-shifted.
    """
    words = [
        Word(
            word=w.get("word", ""),
            start=float(w.get("start", 0.0)) + offset,
            end=float(w.get("end", 0.0)) + offset,
            probability=float(w.get("probability", 0.0) or 0.0),
        )
        for w in (s.get("words") or [])
    ]
    return {
        "start": float(s["start"]) + offset,
        "end": float(s["end"]) + offset,
        "text": (s.get("text") or "").strip(),
        "words": words,
    }


def _vad_segment(audio_path: str, asr_cfg: dict, *, load_fn, get_ts_fn, read_fn):
    """Run Silero VAD; return list of (start_sample, end_sample) tuples + audio array."""
    model = _get_silero_model(load_fn)
    wav = read_fn(audio_path, sampling_rate=_SR)
    spans = get_ts_fn(
        wav, model,
        sampling_rate=_SR,
        threshold=asr_cfg.get("vad_threshold", 0.5),
        min_speech_duration_ms=asr_cfg.get("vad_min_speech_ms", 250),
        min_silence_duration_ms=asr_cfg.get("vad_min_silence_ms", 500),
        speech_pad_ms=asr_cfg.get("vad_speech_pad_ms", 300),
        return_seconds=False,
    )
    return [(s["start"], s["end"]) for s in spans], wav


def _transcribe_chunks(wav, chunks, asr_cfg, mlx_module, ws_emit):
    """Transcribe each chunk with mlx-whisper, shifting offsets to file timeline."""
    repo = MODEL_REPO.get(asr_cfg.get("model_size", "large-v3"), MODEL_REPO["large-v3"])
    out = []
    failed = 0

    for ci, (cs, ce) in enumerate(chunks):
        chunk_audio = wav[cs:ce]
        if hasattr(chunk_audio, "numpy"):  # torch.Tensor → numpy
            chunk_audio = chunk_audio.numpy()
        offset = cs / _SR
        try:
            with _MLX_LOCK:
                r = mlx_module.transcribe(
                    chunk_audio,
                    path_or_hf_repo=repo,
                    language=asr_cfg.get("language", "en"),
                    task="transcribe",
                    verbose=False,
                    condition_on_previous_text=False,  # chunk-isolated
                    word_timestamps=True,
                    temperature=float(asr_cfg.get("temperature") or 0.0),
                    **_HALLUCINATION_GUARDS,
                )
        except Exception as e:  # noqa: BLE001 — permissive runtime fallback
            failed += 1
            logger.warning(
                f"sentence_split: chunk {ci} ({cs/_SR:.1f}-{ce/_SR:.1f}s) failed: {e}"
            )
            continue

        for s in r.get("segments", []):
            seg = _build_segment(s, offset)
            if not seg["text"]:
                continue
            out.append(seg)

    if failed > 0 and ws_emit is not None:
        ws_emit("chunk_fail",
                f"{failed}/{len(chunks)} chunks failed; output may have gaps")
    return out


def _fallback_whole_file(audio_path: str, asr_cfg: dict, mlx_module):
    """Used when VAD returns 0 spans or all chunks fail. Baseline mlx transcribe."""
    repo = MODEL_REPO.get(asr_cfg.get("model_size", "large-v3"), MODEL_REPO["large-v3"])
    with _MLX_LOCK:
        r = mlx_module.transcribe(
            audio_path,
            path_or_hf_repo=repo,
            language=asr_cfg.get("language", "en"),
            task="transcribe",
            verbose=False,
            condition_on_previous_text=True,
            word_timestamps=True,
            temperature=float(asr_cfg.get("temperature") or 0.0),
            **_HALLUCINATION_GUARDS,
        )
    out = []
    for s in r.get("segments", []):
        seg = _build_segment(s)
        if not seg["text"]:
            continue
        out.append(seg)
    return out
