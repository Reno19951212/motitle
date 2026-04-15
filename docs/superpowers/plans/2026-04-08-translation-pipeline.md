# Translation Pipeline Implementation Plan (Phase 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a translation pipeline that converts English transcript segments into Traditional Chinese (formal or Cantonese style) using local LLMs via Ollama, with a mock engine for development.

**Architecture:** A `translation/` package mirrors the `asr/` pattern: ABC interface, factory function, two engine implementations (Mock + Ollama). The mock engine returns placeholder translations for dev/testing. The Ollama engine calls the local Ollama HTTP API with batched prompts. Both accept a glossary parameter (list of term mappings) for future Phase 4 integration.

**Tech Stack:** Python 3.8+, Ollama HTTP API, urllib.request (no new dependencies), Flask.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/translation/__init__.py` | TranslationEngine ABC, TranslatedSegment, factory |
| Create | `backend/translation/mock_engine.py` | MockTranslationEngine for dev/testing |
| Create | `backend/translation/ollama_engine.py` | OllamaTranslationEngine with batch translation |
| Create | `backend/tests/test_translation.py` | Tests for translation interface, factory, engines |
| Modify | `backend/profiles.py` | Add "mock" to VALID_TRANSLATION_ENGINES |
| Modify | `backend/app.py` | Add /api/translate and /api/translation/engines endpoints |

---

### Task 1: Create translation interface, factory, and mock engine

**Files:**
- Create: `backend/translation/__init__.py`
- Create: `backend/translation/mock_engine.py`
- Create: `backend/tests/test_translation.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_translation.py`:

```python
import pytest


SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "Good evening everyone."},
    {"start": 2.5, "end": 5.0, "text": "Welcome to the news."},
]


def test_create_mock_engine():
    from translation import create_translation_engine
    config = {"engine": "mock"}
    engine = create_translation_engine(config)
    assert engine is not None
    info = engine.get_info()
    assert info["engine"] == "mock"
    assert info["available"] is True


def test_mock_translate():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")
    assert len(result) == 2
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["zh_text"] == "[EN→ZH] Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.5
    assert result[1]["en_text"] == "Welcome to the news."


def test_mock_translate_cantonese_style():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="cantonese")
    assert len(result) == 2
    # Mock engine returns same format regardless of style
    assert "[EN→ZH]" in result[0]["zh_text"]


def test_mock_translate_empty_segments():
    from translation import create_translation_engine
    engine = create_translation_engine({"engine": "mock"})
    result = engine.translate([], glossary=[], style="formal")
    assert result == []


def test_create_ollama_engine():
    from translation import create_translation_engine
    config = {"engine": "qwen2.5-3b", "temperature": 0.1}
    engine = create_translation_engine(config)
    assert engine is not None
    info = engine.get_info()
    assert info["engine"] == "qwen2.5-3b"


def test_create_unknown_engine_raises():
    from translation import create_translation_engine
    with pytest.raises(ValueError, match="Unknown translation engine"):
        create_translation_engine({"engine": "nonexistent"})


def test_factory_routes_all_qwen_engines():
    from translation import create_translation_engine
    for engine_name in ["qwen2.5-3b", "qwen2.5-7b", "qwen2.5-72b", "qwen3-235b"]:
        engine = create_translation_engine({"engine": engine_name})
        assert engine.get_info()["engine"] == engine_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_translation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'translation'`

- [ ] **Step 3: Create translation/__init__.py**

Create `backend/translation/__init__.py`:

```python
"""Translation Pipeline — unified interface for text translation engines."""

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
            glossary: list of {"en": str, "zh": str} term mappings
            style: "formal" (書面繁體中文) or "cantonese" (口語粵語)

        Returns:
            list of TranslatedSegment with en_text and zh_text.
        """

    @abstractmethod
    def get_info(self) -> dict:
        """Return engine metadata: engine, model, available, styles."""


def create_translation_engine(translation_config: dict) -> TranslationEngine:
    """Create a translation engine from a profile's translation config block."""
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

- [ ] **Step 4: Create mock_engine.py**

Create `backend/translation/mock_engine.py`:

```python
"""Mock translation engine for development and testing."""

from . import TranslationEngine, TranslatedSegment


class MockTranslationEngine(TranslationEngine):
    """Returns placeholder translations without any ML model."""

    def __init__(self, config: dict):
        self._config = config

    def translate(
        self,
        segments: list[dict],
        glossary: list[dict] | None = None,
        style: str = "formal",
    ) -> list[TranslatedSegment]:
        return [
            TranslatedSegment(
                start=seg["start"],
                end=seg["end"],
                en_text=seg["text"],
                zh_text=f"[EN→ZH] {seg['text']}",
            )
            for seg in segments
        ]

    def get_info(self) -> dict:
        return {
            "engine": "mock",
            "model": "mock",
            "available": True,
            "styles": ["formal", "cantonese"],
        }
```

- [ ] **Step 5: Create ollama_engine.py skeleton**

Create `backend/translation/ollama_engine.py` (skeleton — full impl in Task 2):

```python
"""Ollama-based translation engine using local LLMs."""

from . import TranslationEngine, TranslatedSegment

# Profile engine name → Ollama model name
ENGINE_TO_MODEL = {
    "qwen2.5-3b": "qwen2.5:3b",
    "qwen2.5-7b": "qwen2.5:7b",
    "qwen2.5-72b": "qwen2.5:72b",
    "qwen3-235b": "qwen3:235b",
}


class OllamaTranslationEngine(TranslationEngine):
    """Translation engine that calls Ollama's local HTTP API."""

    def __init__(self, config: dict):
        self._config = config
        self._engine_name = config.get("engine", "qwen2.5-3b")
        self._model = ENGINE_TO_MODEL.get(self._engine_name, "qwen2.5:3b")
        self._temperature = config.get("temperature", 0.1)
        self._base_url = config.get("ollama_url", "http://localhost:11434")

    def translate(
        self,
        segments: list[dict],
        glossary: list[dict] | None = None,
        style: str = "formal",
    ) -> list[TranslatedSegment]:
        raise NotImplementedError("OllamaTranslationEngine.translate not yet implemented")

    def get_info(self) -> dict:
        return {
            "engine": self._engine_name,
            "model": self._model,
            "available": self._check_available(),
            "styles": ["formal", "cantonese"],
        }

    def _check_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                import json
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                return self._model in models
        except Exception:
            return False
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_translation.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/translation/ backend/tests/test_translation.py
git commit -m "feat: add translation interface, factory, mock engine, and Ollama skeleton"
```

---

### Task 2: Implement OllamaTranslationEngine

**Files:**
- Modify: `backend/translation/ollama_engine.py`
- Modify: `backend/tests/test_translation.py`

- [ ] **Step 1: Add Ollama engine tests**

Append to `backend/tests/test_translation.py`:

```python
from unittest.mock import patch, MagicMock
import json


SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "Good evening everyone."},
    {"start": 2.5, "end": 5.0, "text": "Welcome to the news."},
]


def test_ollama_build_system_prompt_formal():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "繁體中文書面語" in prompt
    assert "粵語" not in prompt


def test_ollama_build_system_prompt_cantonese():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "粵語" in prompt


def test_ollama_build_system_prompt_with_glossary():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    glossary = [
        {"en": "Legislative Council", "zh": "立法會"},
        {"en": "Chief Executive", "zh": "行政長官"},
    ]
    prompt = engine._build_system_prompt(style="formal", glossary=glossary)
    assert "Legislative Council" in prompt
    assert "立法會" in prompt
    assert "Chief Executive" in prompt


def test_ollama_build_user_message():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    msg = engine._build_user_message(SAMPLE_SEGMENTS)
    assert "1. Good evening everyone." in msg
    assert "2. Welcome to the news." in msg


def test_ollama_parse_response_numbered():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    response_text = "1. 各位晚上好。\n2. 歡迎收看新聞。"
    result = engine._parse_response(response_text, SAMPLE_SEGMENTS)
    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[1]["zh_text"] == "歡迎收看新聞。"


def test_ollama_parse_response_fallback_lines():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    # No numbering, just lines
    response_text = "各位晚上好。\n歡迎收看新聞。"
    result = engine._parse_response(response_text, SAMPLE_SEGMENTS)
    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"


def test_ollama_translate_mocked_http():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    mock_response_body = json.dumps({
        "message": {"content": "1. 各位晚上好。\n2. 歡迎收看新聞。"}
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert len(result) == 2
    assert result[0]["zh_text"] == "各位晚上好。"
    assert result[0]["en_text"] == "Good evening everyone."
    assert result[0]["start"] == 0.0
    assert result[1]["zh_text"] == "歡迎收看新聞。"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_translation.py::test_ollama_build_system_prompt_formal -v`
Expected: FAIL — `AttributeError: 'OllamaTranslationEngine' object has no attribute '_build_system_prompt'`

- [ ] **Step 3: Implement OllamaTranslationEngine**

Replace `backend/translation/ollama_engine.py` with:

```python
"""Ollama-based translation engine using local LLMs."""

import json
import re
import urllib.request
import urllib.error

from . import TranslationEngine, TranslatedSegment

ENGINE_TO_MODEL = {
    "qwen2.5-3b": "qwen2.5:3b",
    "qwen2.5-7b": "qwen2.5:7b",
    "qwen2.5-72b": "qwen2.5:72b",
    "qwen3-235b": "qwen3:235b",
}

BATCH_SIZE = 10

SYSTEM_PROMPT_FORMAL = (
    "You are a professional translator. Translate the following English text "
    "into formal Traditional Chinese (繁體中文書面語). Maintain the meaning and tone. "
    "Output ONLY the translations, numbered to match the input."
)

SYSTEM_PROMPT_CANTONESE = (
    "You are a professional translator. Translate the following English text "
    "into Cantonese Traditional Chinese (繁體中文粵語口語). Use natural spoken "
    "Cantonese expressions. Output ONLY the translations, numbered to match the input."
)


class OllamaTranslationEngine(TranslationEngine):
    """Translation engine that calls Ollama's local HTTP API."""

    def __init__(self, config: dict):
        self._config = config
        self._engine_name = config.get("engine", "qwen2.5-3b")
        self._model = ENGINE_TO_MODEL.get(self._engine_name, "qwen2.5:3b")
        self._temperature = config.get("temperature", 0.1)
        self._base_url = config.get("ollama_url", "http://localhost:11434")

    def translate(
        self,
        segments: list[dict],
        glossary: list[dict] | None = None,
        style: str = "formal",
    ) -> list[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        all_translated = []

        # Process in batches for context coherence
        for i in range(0, len(segments), BATCH_SIZE):
            batch = segments[i : i + BATCH_SIZE]
            translated_batch = self._translate_batch(batch, glossary, style)
            all_translated.extend(translated_batch)

        return all_translated

    def _translate_batch(
        self, segments: list[dict], glossary: list[dict], style: str
    ) -> list[TranslatedSegment]:
        """Translate a batch of segments via one Ollama API call."""
        system_prompt = self._build_system_prompt(style, glossary)
        user_message = self._build_user_message(segments)

        response_text = self._call_ollama(system_prompt, user_message)
        return self._parse_response(response_text, segments)

    def _build_system_prompt(self, style: str, glossary: list[dict]) -> str:
        """Build the system prompt with style and glossary."""
        if style == "cantonese":
            prompt = SYSTEM_PROMPT_CANTONESE
        else:
            prompt = SYSTEM_PROMPT_FORMAL

        if glossary:
            terms = "\n".join(
                f'- "{entry["en"]}" → "{entry["zh"]}"' for entry in glossary
            )
            prompt += (
                f"\n\nIMPORTANT — Use these specific translations for "
                f"the following terms:\n{terms}"
            )

        return prompt

    def _build_user_message(self, segments: list[dict]) -> str:
        """Build numbered list of segments for translation."""
        lines = []
        for i, seg in enumerate(segments, 1):
            lines.append(f"{i}. {seg['text']}")
        return "\n".join(lines)

    def _call_ollama(self, system_prompt: str, user_message: str) -> str:
        """Call Ollama chat API and return the assistant's response text."""
        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "options": {"temperature": self._temperature},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "")
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Is Ollama running? Error: {e}"
            )
        except TimeoutError:
            raise TimeoutError(
                f"Ollama request timed out after 30s. "
                f"The model may be too large for this hardware."
            )

    def _parse_response(
        self, response_text: str, segments: list[dict]
    ) -> list[TranslatedSegment]:
        """Parse numbered translations from LLM response.

        Tries numbered format first (e.g. '1. 翻譯文本').
        Falls back to line-by-line if numbering doesn't match.
        """
        lines = [ln.strip() for ln in response_text.strip().split("\n") if ln.strip()]

        # Try numbered format: "1. text" or "1) text"
        numbered = {}
        for line in lines:
            match = re.match(r"^(\d+)[.)]\s*(.+)", line)
            if match:
                idx = int(match.group(1))
                numbered[idx] = match.group(2).strip()

        if len(numbered) == len(segments):
            return [
                TranslatedSegment(
                    start=seg["start"],
                    end=seg["end"],
                    en_text=seg["text"],
                    zh_text=numbered[i + 1],
                )
                for i, seg in enumerate(segments)
            ]

        # Fallback: line-by-line (strip any numbering)
        clean_lines = []
        for line in lines:
            cleaned = re.sub(r"^\d+[.)]\s*", "", line).strip()
            if cleaned:
                clean_lines.append(cleaned)

        results = []
        for i, seg in enumerate(segments):
            zh = clean_lines[i] if i < len(clean_lines) else f"[TRANSLATION MISSING] {seg['text']}"
            results.append(
                TranslatedSegment(
                    start=seg["start"],
                    end=seg["end"],
                    en_text=seg["text"],
                    zh_text=zh,
                )
            )
        return results

    def get_info(self) -> dict:
        return {
            "engine": self._engine_name,
            "model": self._model,
            "available": self._check_available(),
            "styles": ["formal", "cantonese"],
        }

    def _check_available(self) -> bool:
        """Check if Ollama is running and the target model is pulled."""
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                return self._model in models
        except Exception:
            return False
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_translation.py -v`
Expected: All 14 tests PASS (7 from Task 1 + 7 new)

- [ ] **Step 5: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_translation.py
git commit -m "feat: implement OllamaTranslationEngine with batch translation and prompt building"
```

---

### Task 3: Update profiles.py and default profiles

**Files:**
- Modify: `backend/profiles.py`
- Modify: `backend/config/profiles/dev-default.json`

- [ ] **Step 1: Add "mock" to VALID_TRANSLATION_ENGINES in profiles.py**

In `backend/profiles.py`, find line:
```python
VALID_TRANSLATION_ENGINES = {"qwen3-235b", "qwen2.5-72b", "qwen2.5-7b", "qwen2.5-3b"}
```

Replace with:
```python
VALID_TRANSLATION_ENGINES = {"qwen3-235b", "qwen2.5-72b", "qwen2.5-7b", "qwen2.5-3b", "mock"}
```

- [ ] **Step 2: Update dev-default profile to use mock engine**

In `backend/config/profiles/dev-default.json`, change the translation section from:
```json
"translation": {
    "engine": "qwen2.5-3b",
    "quantization": "q4",
    "temperature": 0.1,
    "glossary_id": null
}
```

To:
```json
"translation": {
    "engine": "mock",
    "style": "formal",
    "temperature": 0.1,
    "glossary_id": null
}
```

- [ ] **Step 3: Run all profile tests**

Run: `cd backend && python -m pytest tests/test_profiles.py -v`
Expected: All 25 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/profiles.py backend/config/profiles/dev-default.json
git commit -m "feat: add mock to valid translation engines, update dev profile"
```

---

### Task 4: Add REST endpoints to app.py

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_translation.py`

- [ ] **Step 1: Add API test**

Append to `backend/tests/test_translation.py`:

```python
def test_api_list_translation_engines():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines")
        assert resp.status_code == 200
        data = resp.get_json()
        engines = data["engines"]
        assert len(engines) >= 2  # at least mock + one qwen

        engine_names = [e["engine"] for e in engines]
        assert "mock" in engine_names

        mock_info = next(e for e in engines if e["engine"] == "mock")
        assert mock_info["available"] is True
```

- [ ] **Step 2: Add /api/translation/engines endpoint to app.py**

After the ASR engines endpoint in `backend/app.py`, add:

```python
# ============================================================
# Translation Engine Info
# ============================================================

@app.route('/api/translation/engines', methods=['GET'])
def api_list_translation_engines():
    """List available translation engines with status."""
    from translation import create_translation_engine
    engines_info = []
    for engine_name, desc in [
        ("mock", "Mock translator (development)"),
        ("qwen2.5-3b", "Qwen 2.5 3B (Ollama)"),
        ("qwen2.5-7b", "Qwen 2.5 7B (Ollama)"),
        ("qwen2.5-72b", "Qwen 2.5 72B (Ollama)"),
        ("qwen3-235b", "Qwen3 235B MoE (Ollama)"),
    ]:
        try:
            engine = create_translation_engine({"engine": engine_name})
            info = engine.get_info()
            engines_info.append({
                "engine": engine_name,
                "available": info.get("available", False),
                "description": desc,
            })
        except Exception:
            engines_info.append({
                "engine": engine_name,
                "available": False,
                "description": desc,
            })
    return jsonify({"engines": engines_info})
```

- [ ] **Step 3: Add POST /api/translate endpoint to app.py**

After the translation engines endpoint, add:

```python
@app.route('/api/translate', methods=['POST'])
def api_translate_file():
    """Translate a file's transcription segments using the active profile's translation engine."""
    data = request.get_json()
    if not data or not data.get('file_id'):
        return jsonify({"error": "file_id is required"}), 400

    file_id = data['file_id']
    style_override = data.get('style')

    # Get file entry
    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    segments = entry.get('segments', [])
    if not segments:
        return jsonify({"error": "No segments to translate. Transcribe the file first."}), 400

    # Get active profile
    profile = _profile_manager.get_active()
    if not profile:
        return jsonify({"error": "No active profile. Set a profile first."}), 400

    translation_config = profile.get("translation", {})
    style = style_override or translation_config.get("style", "formal")

    try:
        from translation import create_translation_engine
        engine = create_translation_engine(translation_config)

        # Convert segments to the format expected by translation engine
        asr_segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in segments
        ]

        translated = engine.translate(asr_segments, glossary=[], style=style)

        # Store translations in registry alongside original segments
        _update_file(file_id, translations=translated, translation_status='done')

        return jsonify({
            "file_id": file_id,
            "segment_count": len(translated),
            "style": style,
            "engine": engine.get_info().get("engine"),
            "translations": translated,
        })

    except NotImplementedError as e:
        return jsonify({"error": str(e)}), 501
    except ConnectionError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500
```

- [ ] **Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_translation.py
git commit -m "feat: add /api/translate and /api/translation/engines endpoints"
```

---

### Task 5: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Start backend and test translation engines endpoint**

```bash
curl -s http://localhost:5001/api/translation/engines | python3 -m json.tool
```

Expected: mock shows available=true, qwen engines show available=false (Ollama not running).

- [ ] **Step 3: Test translate endpoint with mock engine**

First ensure dev-default profile is active (it uses mock engine):
```bash
curl -s http://localhost:5001/api/profiles/active | python3 -m json.tool
```

Then pick a file that has been transcribed and translate it:
```bash
curl -s -X POST http://localhost:5001/api/translate \
  -H "Content-Type: application/json" \
  -d '{"file_id": "<file_id_here>", "style": "cantonese"}' | python3 -m json.tool
```

Expected: Returns translated segments with `[EN→ZH]` prefix (mock output).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 3 — Translation Pipeline with mock and Ollama engines"
```
