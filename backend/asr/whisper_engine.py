"""Whisper ASR engine — full implementation in Task 2."""

from . import ASREngine, Segment


class WhisperEngine(ASREngine):
    def __init__(self, config: dict):
        self._config = config
        self._model_size = config.get("model_size", "small")
        self._device = config.get("device", "auto")

    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        raise NotImplementedError("WhisperEngine.transcribe not yet implemented")

    def get_info(self) -> dict:
        return {
            "engine": "whisper",
            "model_size": self._model_size,
            "languages": ["en", "zh", "ja", "ko", "fr", "de", "es"],
            "available": True,
        }
