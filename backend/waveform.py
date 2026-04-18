"""
Waveform peak computation for the media player strip.

Pipes the media file through ffmpeg → raw 16-bit PCM mono @ 8kHz on stdout,
then downsamples to `bins` buckets (max absolute amplitude per bucket)
and normalizes to [0.0, 1.0]. Result is a list of floats cheap to JSON-encode
(200 bins ≈ 1-2 KB on the wire).

8kHz is enough for a visual peak envelope — we don't need ASR-grade 16kHz
and the half-rate halves the memory + decode time for long files.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


_SAMPLE_RATE = 8000


def compute_waveform_peaks(
    media_path: str | Path,
    bins: int = 200,
    timeout: int = 600,
) -> Tuple[List[float], Optional[float]]:
    """
    Compute downsampled waveform peaks from any ffmpeg-readable media file.

    Args:
        media_path: path to source video/audio
        bins: number of peak buckets (typical UI: 120-300)
        timeout: ffmpeg timeout in seconds

    Returns:
        (peaks, duration_seconds). `peaks` is a list of floats in [0.0, 1.0]
        of length `bins`. `duration_seconds` is None if ffmpeg didn't surface
        a duration.

    Raises:
        RuntimeError if ffmpeg fails or produces no audio.
    """
    media_path = str(media_path)
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-i", media_path,
        "-vn",                # strip video
        "-f", "s16le",        # raw signed 16-bit little-endian
        "-acodec", "pcm_s16le",
        "-ac", "1",           # mono
        "-ar", str(_SAMPLE_RATE),
        "-",
    ]

    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        raise RuntimeError("ffmpeg failed: " + " | ".join(err))

    raw = proc.stdout
    if not raw:
        raise RuntimeError("ffmpeg produced no audio samples")

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    n = samples.shape[0]
    if n == 0:
        raise RuntimeError("no audio samples")

    # Downsample: split into `bins` roughly equal buckets, take max(abs).
    if bins < 1:
        bins = 1
    if bins > n:
        bins = n
    # np.array_split handles uneven split cleanly.
    chunks = np.array_split(np.abs(samples), bins)
    peaks = np.array([float(c.max()) if c.size else 0.0 for c in chunks], dtype=np.float32)

    max_val = float(peaks.max()) if peaks.size else 0.0
    if max_val > 0:
        peaks = peaks / max_val  # normalize to [0,1]

    duration_seconds = n / float(_SAMPLE_RATE)
    return peaks.tolist(), duration_seconds
