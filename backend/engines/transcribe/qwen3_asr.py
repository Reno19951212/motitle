"""Qwen3AsrTranscribeEngine — main-process (py3.9) wrapper for Qwen3-ASR.

mlx-qwen3-asr requires Python 3.10+, but the project backend runs on
Python 3.9 for compatibility. This wrapper bridges the gap via
subprocess: it invokes `backend/engines/transcribe/qwen3_subprocess.py`
in a Python 3.11 venv (located under `backend/scripts/v5_prototype/venv_qwen/`)
with JSON stdin/stdout.

Output is converted from word-level tokens (Qwen3's native granularity)
into segment-level (preferring chunk-level sentence boundaries when present).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional


_LANG_MAP = {
    "zh": "Cantonese",
    "yue": "Cantonese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}


def _qwen3_language_name(source_lang: str) -> str:
    """Map ISO-639-1 code → Qwen3's language label. Unknown defaults to Cantonese."""
    return _LANG_MAP.get(source_lang, "Cantonese")


class Qwen3AsrTranscribeEngine:
    """v5-A1 TranscribeEngine implementation wrapping mlx-qwen3-asr via subprocess."""

    def __init__(self, profile: dict):
        self.profile = profile
        self.model_size = profile.get("model_size") or "1.7B"
        repo_root = Path(__file__).resolve().parents[3]
        venv_python = repo_root / "backend" / "scripts" / "v5_prototype" / "venv_qwen" / "bin" / "python"
        self.subprocess_python = str(venv_python) if venv_python.exists() else "python3.11"
        self.subprocess_script = str(
            repo_root / "backend" / "engines" / "transcribe" / "qwen3_subprocess.py"
        )

    def transcribe(
        self,
        audio_path: str,
        source_lang: str,
        *,
        context: str = "",
        return_timestamps: bool = True,
        timeout_sec: float = 600.0,
        progress=None,
    ) -> list:
        """Returns list of {start, end, text} segments.

        Prefers chunk-level (sentence-boundary) output; falls back to
        word-level if chunks are empty.
        """
        language = _qwen3_language_name(source_lang)
        model_full = f"Qwen/Qwen3-ASR-{self.model_size}"
        args = {
            "audio_path": audio_path,
            "model": model_full,
            "language": language,
            "context": context,
            "return_timestamps": return_timestamps,
            "return_chunks": True,
        }
        result = subprocess.run(
            [self.subprocess_python, self.subprocess_script],
            input=json.dumps(args),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Qwen3-ASR subprocess failed (returncode={result.returncode}): "
                f"{result.stderr.strip()}"
            )
        data = json.loads(result.stdout)
        # Prefer chunk-level (sentence boundaries); fall back to word-level
        if data.get("chunks"):
            return [
                {"start": c["start"], "end": c["end"], "text": c["text"]}
                for c in data["chunks"]
            ]
        return [
            {"start": w["start"], "end": w["end"], "text": w["text"]}
            for w in data.get("words", [])
        ]
