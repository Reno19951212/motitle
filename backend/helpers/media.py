"""Media helpers — Whisper model cache + ffprobe + audio extraction.

Extracted from ``app.py`` for v4 A6 C2 T13a. The two model-cache dicts
(``_openai_model_cache`` / ``_faster_model_cache``) plus the protecting
``_model_lock`` still live on ``app`` so existing tests + the legacy
``/api/models`` endpoint observe the same singletons. This module reaches
through ``app`` at call time to mutate them.
"""
from __future__ import annotations

import json
import subprocess


def get_model(model_size: str = "small", backend: str = "auto"):
    """Load and cache a Whisper model.

    ``backend``: ``'auto' | 'openai' | 'faster'``.
    Returns ``(model_instance, backend_name)``.
    """
    import app as _app
    import whisper

    use_faster = (
        backend == "faster" or
        (backend == "auto" and _app.FASTER_WHISPER_AVAILABLE)
    )

    with _app._model_lock:
        if use_faster and _app.FASTER_WHISPER_AVAILABLE:
            if model_size not in _app._faster_model_cache:
                print(f"Loading faster-whisper model: {model_size}")
                from faster_whisper import WhisperModel as FasterWhisperModel
                _app._faster_model_cache[model_size] = FasterWhisperModel(
                    model_size, device="auto", compute_type="int8"
                )
                print(f"faster-whisper model {model_size} loaded")
            return _app._faster_model_cache[model_size], "faster"
        else:
            if model_size not in _app._openai_model_cache:
                print(f"Loading openai-whisper model: {model_size}")
                _app._openai_model_cache[model_size] = whisper.load_model(model_size)
                print(f"openai-whisper model {model_size} loaded")
            return _app._openai_model_cache[model_size], "openai"


def get_media_duration(file_path: str) -> float:
    """Get media duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return float(info.get("format", {}).get("duration", 0))
    except Exception as e:
        print(f"Error getting duration: {e}")
    return 0


def probe_duration_seconds(path: str) -> float | None:
    """Run ffprobe on `path`, return duration in seconds or None on failure.

    Coexists with `get_media_duration()`: the latter returns 0 on failure
    (legacy callers), this one returns None so callers can distinguish
    "0-second file" from "ffprobe failed". Used by the upload route to
    populate `FileRecord.duration_seconds`.

    On failure (timeout, non-zero exit, malformed JSON, missing duration
    field, OS error) logs a warning via `print` and returns None.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"[probe_duration_seconds] ffprobe nonzero exit for {path}: {result.stderr.strip()[:200]}")
            return None
        data = json.loads(result.stdout)
        d = data.get("format", {}).get("duration")
        return float(d) if d is not None else None
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            ValueError, KeyError, OSError) as e:
        print(f"[probe_duration_seconds] ffprobe error for {path}: {type(e).__name__}")
        return None


def extract_audio(video_path: str, output_path: str) -> bool:
    """Extract audio from video file using ffmpeg (mono 16 kHz PCM)."""
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn",                  # No video
            "-acodec", "pcm_s16le",  # PCM 16-bit
            "-ar", "16000",         # 16 kHz sample rate (Whisper requirement)
            "-ac", "1",             # Mono
            "-y",                   # Overwrite
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False
