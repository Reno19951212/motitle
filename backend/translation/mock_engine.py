"""Mock translation engine for development and testing."""
from typing import List, Optional
from . import TranslationEngine, TranslatedSegment


class MockTranslationEngine(TranslationEngine):
    def __init__(self, config: dict):
        self._config = config

    def translate(self, segments: List[dict], glossary: Optional[List[dict]] = None, style: str = "formal") -> List[TranslatedSegment]:
        return [
            TranslatedSegment(start=seg["start"], end=seg["end"], en_text=seg["text"], zh_text=f"[EN\u2192ZH] {seg['text']}")
            for seg in segments
        ]

    def get_info(self) -> dict:
        return {"engine": "mock", "model": "mock", "available": True, "styles": ["formal", "cantonese"]}
