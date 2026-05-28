"""TranscribeEngine ABC + factory — v5-A1.

Aliases v4 `asr.ASREngine` as the v5 `TranscribeEngine`. v4 Whisper and
mlx-whisper engines are reused as-is via the v4 factory. The new
Qwen3-ASR engine has its own factory branch (subprocess wrapper to
py3.11 mlx-qwen3-asr).
"""
from __future__ import annotations

from asr import ASREngine, create_asr_engine as _create_v4_engine

TranscribeEngine = ASREngine


def create_transcribe_engine(profile: dict):
    """Create a TranscribeEngine instance from a TranscribeProfile dict.

    Dispatches:
      - engine: 'whisper' or 'mlx-whisper' → v4 ASR factory (asr.create_asr_engine)
      - engine: 'qwen3-asr' → Qwen3AsrTranscribeEngine (subprocess wrapper, py3.11)
    """
    engine = profile.get("engine")
    if engine == "qwen3-asr":
        from engines.transcribe.qwen3_asr import Qwen3AsrTranscribeEngine
        return Qwen3AsrTranscribeEngine(profile)
    return _create_v4_engine(profile)
