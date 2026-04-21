"""ASR Pipeline — unified interface for speech recognition engines."""

from abc import ABC, abstractmethod
from typing import List, TypedDict


class Word(TypedDict):
    """Word-level timestamp emitted by ASR engines that support it.

    start/end are audio seconds. probability is the model's confidence
    (0.0-1.0) — not all engines populate it; treat as best-effort.
    """
    word: str
    start: float
    end: float
    probability: float


# Segments are dicts with always-present start/end/text. Engines that run
# with word_timestamps=True ALSO include a `words: List[Word]` key. We keep
# the base TypedDict required-only (Python 3.9 lacks NotRequired) and treat
# `words` as a conventionally-present optional key that consumers probe for.
class Segment(TypedDict):
    start: float
    end: float
    text: str


class ASREngine(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        """Transcribe audio file to text segments with timestamps."""

    @abstractmethod
    def get_info(self) -> dict:
        """Return engine metadata: engine, model_size, languages, available."""

    @abstractmethod
    def get_params_schema(self) -> dict:
        """Return JSON schema describing configurable parameters for this engine."""


def create_asr_engine(asr_config: dict) -> ASREngine:
    engine_name = asr_config.get("engine", "")
    if engine_name == "whisper":
        from .whisper_engine import WhisperEngine
        return WhisperEngine(asr_config)
    elif engine_name == "mlx-whisper":
        from .mlx_whisper_engine import MlxWhisperEngine
        return MlxWhisperEngine(asr_config)
    elif engine_name == "qwen3-asr":
        from .qwen3_engine import Qwen3ASREngine
        return Qwen3ASREngine(asr_config)
    elif engine_name == "flg-asr":
        from .flg_engine import FLGASREngine
        return FLGASREngine(asr_config)
    else:
        raise ValueError(f"Unknown ASR engine: {engine_name}")
