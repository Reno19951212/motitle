# Translation Pipeline Design (Phase 3)

## Purpose

Translate English transcript segments into Traditional Chinese (Cantonese or formal) using local open-source LLMs via Ollama. A mock engine is provided for development and testing without a running LLM.

## File Structure

```
backend/
├── translation/
│   ├── __init__.py              # TranslationEngine ABC, TranslatedSegment, factory
│   ├── ollama_engine.py         # Ollama HTTP API engine (Qwen2.5-3B/7B/72B/Qwen3-235B)
│   └── mock_engine.py           # Mock engine for dev/testing
├── profiles.py                  # Modified: add "mock" to VALID_TRANSLATION_ENGINES
├── app.py                       # Modified: wire translation into transcription pipeline
```

## Interface

```python
from abc import ABC, abstractmethod
from typing import TypedDict


class TranslatedSegment(TypedDict):
    start: float
    end: float
    en_text: str
    zh_text: str


class TranslationEngine(ABC):
    @abstractmethod
    def translate(
        self,
        segments: list[dict],
        glossary: list[dict] | None = None,
        style: str = "formal",
    ) -> list[TranslatedSegment]:
        """Translate English segments to Chinese.

        Args:
            segments: list of {"start": float, "end": float, "text": str}
            glossary: list of {"en": str, "zh": str, "context": str} (empty = no glossary)
            style: "formal" (書面繁體中文) or "cantonese" (口語粵語)

        Returns:
            list of TranslatedSegment with both en_text and zh_text.
        """

    @abstractmethod
    def get_info(self) -> dict:
        """Return engine metadata: engine, model, available, styles."""
```

## Factory

```python
def create_translation_engine(translation_config: dict) -> TranslationEngine:
    engine_name = translation_config.get("engine", "")

    if engine_name == "mock":
        from .mock_engine import MockTranslationEngine
        return MockTranslationEngine(translation_config)
    elif engine_name in {"qwen3-235b", "qwen2.5-72b", "qwen2.5-7b", "qwen2.5-3b"}:
        from .ollama_engine import OllamaTranslationEngine
        return OllamaTranslationEngine(translation_config)
    else:
        raise ValueError(f"Unknown translation engine: {engine_name}")
```

## MockTranslationEngine

For development and CI testing. No dependencies.

```python
class MockTranslationEngine(TranslationEngine):
    def __init__(self, config: dict):
        self._config = config

    def translate(self, segments, glossary=None, style="formal"):
        return [
            TranslatedSegment(
                start=seg["start"],
                end=seg["end"],
                en_text=seg["text"],
                zh_text=f"[EN→ZH] {seg['text']}",
            )
            for seg in segments
        ]

    def get_info(self):
        return {
            "engine": "mock",
            "model": "mock",
            "available": True,
            "styles": ["formal", "cantonese"],
        }
```

## OllamaTranslationEngine

Calls Ollama's local HTTP API to translate using a Qwen model.

### Ollama API

```
POST http://localhost:11434/api/chat
{
  "model": "qwen2.5:3b",
  "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
  "stream": false,
  "options": {"temperature": 0.1}
}
```

### Model name mapping

| Profile engine value | Ollama model name |
|---|---|
| qwen2.5-3b | qwen2.5:3b |
| qwen2.5-7b | qwen2.5:7b |
| qwen2.5-72b | qwen2.5:72b |
| qwen3-235b | qwen3:235b |

### Translation strategy

1. **Batch segments** into groups of 10 for context coherence
2. **Construct prompt** per batch:
   - System message: translation instructions + style directive
   - Glossary terms injected as few-shot examples (if any)
   - Numbered English segments as user message
3. **Parse response**: expect numbered Chinese translations matching input
4. **Validate**: each input segment must have exactly one output translation
5. **Fallback**: if parsing fails, translate segments one-by-one

### System prompt templates

**Formal style:**
```
You are a professional translator. Translate the following English text into formal Traditional Chinese (繁體中文書面語). Maintain the meaning and tone. Output ONLY the translations, numbered to match the input.
```

**Cantonese style:**
```
You are a professional translator. Translate the following English text into Cantonese Traditional Chinese (繁體中文粵語口語). Use natural spoken Cantonese expressions. Output ONLY the translations, numbered to match the input.
```

### Glossary injection

If glossary entries are provided, append to system prompt:
```
IMPORTANT — Use these specific translations for the following terms:
- "Legislative Council" → "立法會"
- "Chief Executive" → "行政長官"
```

### Availability check

`get_info()` calls `GET http://localhost:11434/api/tags` to check if Ollama is running and the target model is pulled. Returns `available: True/False` accordingly.

### Error handling

- Ollama not running → raise `ConnectionError` with clear message
- Model not pulled → raise `RuntimeError` with `ollama pull <model>` instruction
- Parse failure → fall back to single-segment translation
- Timeout (30s per batch) → raise `TimeoutError`

## Profile schema change

Add `style` field and `mock` as valid engine:

```json
"translation": {
    "engine": "qwen2.5-3b",
    "style": "cantonese",
    "temperature": 0.1,
    "glossary_id": null
}
```

Update `profiles.py`:
- Add `"mock"` to `VALID_TRANSLATION_ENGINES`

## Integration with app.py

### New endpoint: POST /api/translate

Accepts a file_id, runs translation on its segments using the active profile's translation engine:

```
POST /api/translate
{
  "file_id": "abc123",
  "style": "cantonese"  // optional, overrides profile default
}
```

Returns translated segments. Does NOT replace original segments — stores translations alongside them.

### New endpoint: GET /api/translation/engines

Similar to `/api/asr/engines`:
```json
{
  "engines": [
    {"engine": "mock", "available": true, "description": "Mock translator (development)"},
    {"engine": "qwen2.5-3b", "available": false, "description": "Qwen 2.5 3B (Ollama)"},
    ...
  ]
}
```

## Testing

- Unit tests for MockTranslationEngine: verify segment format, style parameter ignored
- Unit tests for OllamaTranslationEngine: mock HTTP calls, verify prompt construction, batch logic, parse logic
- Unit tests for factory: correct engine instantiated per config
- API test for /api/translation/engines

## What Does NOT Change

- ASR pipeline (Phase 2) — runs independently before translation
- Live transcription mode — not affected
- Existing file upload/playback flows
- Profile system structure (only add "mock" to valid engines)
