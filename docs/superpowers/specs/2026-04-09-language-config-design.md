# Language Configuration System Design

## Purpose

Allow per-language configuration of ASR segmentation parameters (max words per segment, max segment duration) and translation parameters (batch size, temperature). Profiles reference a language config by ID. This replaces hardcoded values in the ASR and translation engines.

## File Structure

```
backend/
├── language_config.py               # LanguageConfigManager — get, list, update
├── config/languages/
│   ├── en.json                      # English defaults
│   └── zh.json                      # Chinese defaults
├── asr/whisper_engine.py            # Modified: post-process segments using language config
├── translation/ollama_engine.py     # Modified: read batch_size and temperature from language config
├── app.py                           # Modified: language config endpoints + pass config to engines
```

## Language Config Schema

```json
{
  "id": "en",
  "name": "English",
  "asr": {
    "max_words_per_segment": 40,
    "max_segment_duration": 10.0
  },
  "translation": {
    "batch_size": 10,
    "temperature": 0.1
  }
}
```

All fields required. `id` matches the language code used in profiles (e.g. "en", "zh").

## Default Language Configs

### en.json (English)

```json
{
  "id": "en",
  "name": "English",
  "asr": {
    "max_words_per_segment": 40,
    "max_segment_duration": 10.0
  },
  "translation": {
    "batch_size": 10,
    "temperature": 0.1
  }
}
```

### zh.json (Chinese)

```json
{
  "id": "zh",
  "name": "Chinese",
  "asr": {
    "max_words_per_segment": 25,
    "max_segment_duration": 8.0
  },
  "translation": {
    "batch_size": 8,
    "temperature": 0.1
  }
}
```

Chinese uses fewer words per segment (higher character density) and shorter segment duration.

## Profile Integration

Profile's `asr` block gains an optional `language_config_id` field:

```json
{
  "asr": {
    "engine": "whisper",
    "model_size": "small",
    "language": "en",
    "language_config_id": "en"
  }
}
```

If `language_config_id` is absent or the referenced config is not found, hardcoded defaults are used:
```python
DEFAULT_ASR_CONFIG = {"max_words_per_segment": 40, "max_segment_duration": 10.0}
DEFAULT_TRANSLATION_CONFIG = {"batch_size": 10, "temperature": 0.1}
```

## LanguageConfigManager

Follows the same pattern as ProfileManager/GlossaryManager (JSON file storage, atomic writes). But simpler — no create/delete, only get/list/update.

```python
class LanguageConfigManager:
    def __init__(self, config_dir: Path):
        """Sets up languages/ directory under config_dir."""

    def get(self, lang_id: str) -> dict | None:
        """Get a language config by ID."""

    def list_all(self) -> list[dict]:
        """List all language configs."""

    def update(self, lang_id: str, data: dict) -> dict | None:
        """Update parameters of an existing language config. Returns updated config or None."""
```

Validation on update:
- `asr.max_words_per_segment`: int, 5–200
- `asr.max_segment_duration`: float, 1.0–60.0
- `translation.batch_size`: int, 1–50
- `translation.temperature`: float, 0.0–2.0

## How Parameters Are Used

### ASR: Segment Post-Processing

Whisper produces segments of varying length. After transcription, a post-processing step splits oversized segments:

1. `WhisperEngine.transcribe()` returns raw segments from Whisper
2. New function `split_segments(segments, max_words, max_duration)` post-processes:
   - If a segment has more than `max_words_per_segment` words → split at sentence boundaries (periods, commas) or at the word limit
   - If a segment is longer than `max_segment_duration` seconds → split proportionally by word count
3. Returns the refined segment list

This is a **post-processing step**, not a Whisper parameter — Whisper itself controls its own segmentation internally. We refine the output.

### Translation: Batch Size and Temperature

`OllamaTranslationEngine.translate()` currently uses:
- `BATCH_SIZE = 10` (hardcoded module constant)
- `self._temperature` (from profile's translation config)

After this change:
- `batch_size` read from language config (falls back to 10)
- `temperature` read from language config (falls back to 0.1), overridden by profile if set

Priority: language config provides defaults → profile overrides if explicitly set.

## Pipeline Integration

In `app.py`, when transcription runs:

```python
# Load language config
lang_config = _language_config_manager.get(profile["asr"].get("language_config_id", "en"))

# ASR transcribe
raw_segments = engine.transcribe(audio_path, language=language)

# Post-process with language config
asr_params = lang_config["asr"] if lang_config else DEFAULT_ASR_CONFIG
segments = split_segments(raw_segments, asr_params["max_words_per_segment"], asr_params["max_segment_duration"])

# Translation with language config
trans_params = lang_config["translation"] if lang_config else DEFAULT_TRANSLATION_CONFIG
translated = engine.translate(segments, glossary=glossary, style=style,
                              batch_size=trans_params["batch_size"],
                              temperature=trans_params["temperature"])
```

## REST Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/languages` | List all language configs |
| GET | `/api/languages/:id` | Get a language config |
| PATCH | `/api/languages/:id` | Update language config parameters |

No create/delete — language configs are pre-defined. Users only adjust parameters.

## Testing

- Unit tests for LanguageConfigManager: get, list, update, validation
- Unit tests for `split_segments()`: word splitting, duration splitting, edge cases
- API tests for all 3 endpoints
- Integration: verify language config params flow through to ASR post-processing and translation

## What Does NOT Change

- Profile schema (only adds optional `language_config_id` field)
- ASR engine interface (post-processing happens outside the engine)
- Translation engine interface (batch_size/temperature passed as parameters)
- Frontend (no UI changes — config via API or JSON files only)
- Glossary, renderer, proof-reading editor
