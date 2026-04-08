# ASR Pipeline Design (Phase 2)

## Purpose

Provide a unified ASR interface that abstracts over multiple speech recognition engines. The active profile (from Phase 1) determines which engine is used. Whisper is fully implemented; Qwen3-ASR and FLG-ASR are stubs for future implementation on production hardware.

## File Structure

```
backend/
├── asr/
│   ├── __init__.py          # ASREngine ABC, Segment TypedDict, create_asr_engine() factory
│   ├── whisper_engine.py    # Full Whisper implementation (faster-whisper + openai-whisper)
│   ├── qwen3_engine.py      # Stub — raises NotImplementedError on transcribe()
│   └── flg_engine.py        # Stub — raises NotImplementedError on transcribe()
├── app.py                   # Modified: transcribe_with_segments uses ASR engine from profile
```

## Interface

```python
from abc import ABC, abstractmethod
from typing import TypedDict


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
        """Return engine metadata: {"engine": str, "model_size": str, "languages": list[str]}"""
```

## Factory

```python
def create_asr_engine(asr_config: dict) -> ASREngine:
    """Create an ASR engine from a profile's asr config block."""
    engine_name = asr_config["engine"]
    if engine_name == "whisper":
        from .whisper_engine import WhisperEngine
        return WhisperEngine(asr_config)
    elif engine_name == "qwen3-asr":
        from .qwen3_engine import Qwen3ASREngine
        return Qwen3ASREngine(asr_config)
    elif engine_name == "flg-asr":
        from .flg_engine import FLGASREngine
        return FLGASREngine(asr_config)
    else:
        raise ValueError(f"Unknown ASR engine: {engine_name}")
```

Lazy imports prevent loading heavy ML libraries until needed.

## WhisperEngine

Extracts and encapsulates the existing Whisper logic from `app.py`:

- `__init__(config)` — stores model_size, device, language; does NOT pre-load model (lazy load on first transcribe)
- `transcribe(audio_path, language)` — loads model via faster-whisper (preferred) or openai-whisper fallback, runs transcription, returns `list[Segment]`
- `get_info()` — returns engine name, model size, available languages
- Reuses the existing `_faster_model_cache` and `_openai_model_cache` pattern for model caching
- Reuses the existing inference lock pattern (`_get_inference_lock`) for thread safety
- Supports configurable `language` parameter (current code hardcodes "zh"; this engine accepts any language)

### What moves out of app.py

- `get_model()` function → becomes internal to WhisperEngine
- `_faster_model_cache`, `_openai_model_cache`, `_model_lock` → move to whisper_engine.py
- `_get_inference_lock`, `_inference_locks` → move to whisper_engine.py
- `FASTER_WHISPER_AVAILABLE` check → moves to whisper_engine.py

### What stays in app.py

- `transcribe_with_segments()` — remains but now delegates to `ASREngine.transcribe()` instead of calling `get_model()` directly
- `transcribe_chunk()` — remains for live mode (not part of the broadcast pipeline yet)
- Audio extraction (`extract_audio()`) — remains, called before passing audio_path to engine
- All WebSocket/REST route handlers — remain

## Stubs (Qwen3-ASR, FLG-ASR)

Both follow the same pattern:

```python
class Qwen3ASREngine(ASREngine):
    def __init__(self, config: dict):
        self._config = config
        print(f"WARNING: Qwen3-ASR engine is a stub. Not available in dev environment.")

    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        raise NotImplementedError(
            "Qwen3-ASR is not available in this environment. "
            "Use the 'whisper' engine or deploy on production hardware."
        )

    def get_info(self) -> dict:
        return {
            "engine": "qwen3-asr",
            "model_size": self._config.get("model_size", "unknown"),
            "languages": ["en", "zh"],
            "available": False,
        }
```

FLG-ASR stub is identical in structure, with "flg-asr" as the engine name.

## Integration with app.py

### transcribe_with_segments() change

Before (current):
```python
model, backend = get_model(model_size, backend='auto')
# ... use model directly
```

After:
```python
from asr import create_asr_engine

# Use profile if available, fallback to legacy behavior
profile = _profile_manager.get_active()
if profile:
    engine = create_asr_engine(profile["asr"])
    segments = engine.transcribe(audio_path, language=profile["asr"].get("language", "zh"))
else:
    # Legacy path: use get_model() directly (backward compat)
    segments = _legacy_transcribe(audio_path, model_size, sid)
```

The legacy path preserves existing behavior (streaming emit per segment, progress tracking). The new engine path returns all segments at once; the caller handles progress emission.

### New REST endpoint

`GET /api/asr/engines` — returns available ASR engines with their status:
```json
{
  "engines": [
    {"engine": "whisper", "available": true, "description": "OpenAI Whisper (local)"},
    {"engine": "qwen3-asr", "available": false, "description": "Qwen3-ASR (stub)"},
    {"engine": "flg-asr", "available": false, "description": "FLG-ASR (stub)"}
  ]
}
```

## Testing

- Unit tests for WhisperEngine: mock the underlying model, verify correct segment format returned
- Unit tests for factory: verify correct engine class instantiated per config
- Unit tests for stubs: verify NotImplementedError raised, get_info returns available=false
- Integration test: active profile with whisper engine → transcribe a short audio file → verify segments returned

## What Does NOT Change

- Live transcription mode (chunk-based and streaming) — continues using existing code paths
- Frontend file upload flow — continues working, now routed through profile if active
- The profile system from Phase 1
