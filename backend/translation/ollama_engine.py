"""Ollama-based translation engine using local LLMs."""
from typing import List, Optional
from . import TranslationEngine, TranslatedSegment

ENGINE_TO_MODEL = {
    "qwen2.5-3b": "qwen2.5:3b",
    "qwen2.5-7b": "qwen2.5:7b",
    "qwen2.5-72b": "qwen2.5:72b",
    "qwen3-235b": "qwen3:235b",
}


class OllamaTranslationEngine(TranslationEngine):
    def __init__(self, config: dict):
        self._config = config
        self._engine_name = config.get("engine", "qwen2.5-3b")
        self._model = ENGINE_TO_MODEL.get(self._engine_name, "qwen2.5:3b")
        self._temperature = config.get("temperature", 0.1)
        self._base_url = config.get("ollama_url", "http://localhost:11434")

    def translate(self, segments: List[dict], glossary: Optional[List[dict]] = None, style: str = "formal") -> List[TranslatedSegment]:
        raise NotImplementedError("OllamaTranslationEngine.translate not yet implemented")

    def get_info(self) -> dict:
        return {"engine": self._engine_name, "model": self._model, "available": self._check_available(), "styles": ["formal", "cantonese"]}

    def _check_available(self) -> bool:
        try:
            import urllib.request
            import json
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                return self._model in models
        except Exception:
            return False
