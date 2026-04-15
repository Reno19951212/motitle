# Language Configuration System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-language configuration for ASR segmentation (max words, max duration) and translation (batch size, temperature), referenced by profiles and applied during the pipeline.

**Architecture:** A `language_config.py` module manages JSON language config files in `config/languages/`. A new `split_segments()` function post-processes ASR output. The translation engine's `translate()` method accepts `batch_size` and `temperature` as optional parameters. Profiles reference a language config by `language_config_id`.

**Tech Stack:** Python 3.8+, JSON file storage, Flask.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/language_config.py` | LanguageConfigManager — get, list, update with validation |
| Create | `backend/config/languages/en.json` | English language defaults |
| Create | `backend/config/languages/zh.json` | Chinese language defaults |
| Create | `backend/asr/segment_utils.py` | `split_segments()` post-processing function |
| Create | `backend/tests/test_language_config.py` | Tests for LanguageConfigManager + API |
| Create | `backend/tests/test_segment_utils.py` | Tests for split_segments |
| Modify | `backend/translation/ollama_engine.py` | Accept batch_size/temperature params in translate() |
| Modify | `backend/translation/mock_engine.py` | Accept batch_size/temperature params (ignore) |
| Modify | `backend/translation/__init__.py` | Update ABC translate() signature |
| Modify | `backend/app.py` | Language config endpoints + integrate into pipeline |

---

### Task 1: Create LanguageConfigManager

**Files:**
- Create: `backend/language_config.py`
- Create: `backend/config/languages/en.json`
- Create: `backend/config/languages/zh.json`
- Create: `backend/tests/test_language_config.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_language_config.py`:

```python
import pytest
import json
from pathlib import Path


@pytest.fixture
def config_dir(tmp_path):
    lang_dir = tmp_path / "languages"
    lang_dir.mkdir()
    # Create a test language config
    en = {
        "id": "en",
        "name": "English",
        "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0},
        "translation": {"batch_size": 10, "temperature": 0.1},
    }
    (lang_dir / "en.json").write_text(json.dumps(en, indent=2))
    zh = {
        "id": "zh",
        "name": "Chinese",
        "asr": {"max_words_per_segment": 25, "max_segment_duration": 8.0},
        "translation": {"batch_size": 8, "temperature": 0.1},
    }
    (lang_dir / "zh.json").write_text(json.dumps(zh, indent=2))
    return tmp_path


def test_get_existing(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    cfg = mgr.get("en")
    assert cfg is not None
    assert cfg["id"] == "en"
    assert cfg["asr"]["max_words_per_segment"] == 40
    assert cfg["translation"]["batch_size"] == 10


def test_get_nonexistent(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    assert mgr.get("fr") is None


def test_list_all(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    configs = mgr.list_all()
    assert len(configs) == 2
    names = [c["name"] for c in configs]
    assert "English" in names
    assert "Chinese" in names


def test_update_asr_param(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    updated = mgr.update("en", {"asr": {"max_words_per_segment": 30, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}})
    assert updated["asr"]["max_words_per_segment"] == 30
    # Verify persisted
    reloaded = mgr.get("en")
    assert reloaded["asr"]["max_words_per_segment"] == 30


def test_update_translation_param(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    updated = mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 5, "temperature": 0.3}})
    assert updated["translation"]["batch_size"] == 5
    assert updated["translation"]["temperature"] == 0.3


def test_update_nonexistent(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    assert mgr.update("fr", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}}) is None


def test_update_invalid_max_words(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 3, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 0.1}})


def test_update_invalid_max_duration(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 0.5}, "translation": {"batch_size": 10, "temperature": 0.1}})


def test_update_invalid_batch_size(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 0, "temperature": 0.1}})


def test_update_invalid_temperature(config_dir):
    from language_config import LanguageConfigManager
    mgr = LanguageConfigManager(config_dir)
    with pytest.raises(ValueError):
        mgr.update("en", {"asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0}, "translation": {"batch_size": 10, "temperature": 3.0}})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_language_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'language_config'`

- [ ] **Step 3: Implement LanguageConfigManager**

Create `backend/language_config.py`:

```python
"""Language configuration manager for per-language ASR and translation parameters."""

import json
import os
from pathlib import Path
from typing import Optional, List

LANGUAGES_DIRNAME = "languages"

DEFAULT_ASR_CONFIG = {"max_words_per_segment": 40, "max_segment_duration": 10.0}
DEFAULT_TRANSLATION_CONFIG = {"batch_size": 10, "temperature": 0.1}


class LanguageConfigManager:
    """Manages per-language configuration files (get, list, update only)."""

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._languages_dir = self._config_dir / LANGUAGES_DIRNAME
        self._languages_dir.mkdir(parents=True, exist_ok=True)

    def _lang_path(self, lang_id: str) -> Path:
        return self._languages_dir / f"{lang_id}.json"

    def get(self, lang_id: str) -> Optional[dict]:
        """Get a language config by ID. Returns None if not found."""
        path = self._lang_path(lang_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> List[dict]:
        """List all language configs, sorted by name."""
        configs = []
        for path in self._languages_dir.glob("*.json"):
            try:
                configs.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(configs, key=lambda c: c.get("name", ""))

    def update(self, lang_id: str, data: dict) -> Optional[dict]:
        """Update a language config's parameters. Returns updated config or None."""
        existing = self.get(lang_id)
        if not existing:
            return None

        errors = self._validate(data)
        if errors:
            raise ValueError(errors)

        updated = {
            **existing,
            "asr": data.get("asr", existing.get("asr", DEFAULT_ASR_CONFIG)),
            "translation": data.get("translation", existing.get("translation", DEFAULT_TRANSLATION_CONFIG)),
        }

        path = self._lang_path(lang_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, path)

        return updated

    def _validate(self, data: dict) -> List[str]:
        """Validate language config parameters."""
        errors = []
        asr = data.get("asr", {})
        trans = data.get("translation", {})

        mw = asr.get("max_words_per_segment")
        if mw is not None:
            if not isinstance(mw, int) or mw < 5 or mw > 200:
                errors.append("asr.max_words_per_segment must be an integer between 5 and 200")

        md = asr.get("max_segment_duration")
        if md is not None:
            if not isinstance(md, (int, float)) or md < 1.0 or md > 60.0:
                errors.append("asr.max_segment_duration must be a number between 1.0 and 60.0")

        bs = trans.get("batch_size")
        if bs is not None:
            if not isinstance(bs, int) or bs < 1 or bs > 50:
                errors.append("translation.batch_size must be an integer between 1 and 50")

        temp = trans.get("temperature")
        if temp is not None:
            if not isinstance(temp, (int, float)) or temp < 0.0 or temp > 2.0:
                errors.append("translation.temperature must be a number between 0.0 and 2.0")

        return errors
```

- [ ] **Step 4: Create default language config files**

Create `backend/config/languages/en.json`:
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

Create `backend/config/languages/zh.json`:
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

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_language_config.py -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/language_config.py backend/config/languages/ backend/tests/test_language_config.py
git commit -m "feat: add LanguageConfigManager with en/zh defaults and validation"
```

---

### Task 2: Create split_segments post-processing

**Files:**
- Create: `backend/asr/segment_utils.py`
- Create: `backend/tests/test_segment_utils.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_segment_utils.py`:

```python
import pytest


def test_no_splitting_needed():
    from asr.segment_utils import split_segments
    segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello world this is a test."},
    ]
    result = split_segments(segments, max_words=40, max_duration=10.0)
    assert len(result) == 1
    assert result[0]["text"] == "Hello world this is a test."


def test_split_by_word_count():
    from asr.segment_utils import split_segments
    # 12 words, max 5 per segment → should split into 3
    segments = [
        {"start": 0.0, "end": 6.0, "text": "one two three four five six seven eight nine ten eleven twelve"},
    ]
    result = split_segments(segments, max_words=5, max_duration=60.0)
    assert len(result) >= 2
    for seg in result:
        word_count = len(seg["text"].split())
        assert word_count <= 5


def test_split_by_duration():
    from asr.segment_utils import split_segments
    # 10 second segment, max 3 seconds → should split
    segments = [
        {"start": 0.0, "end": 10.0, "text": "one two three four five six seven eight nine ten"},
    ]
    result = split_segments(segments, max_words=200, max_duration=3.0)
    assert len(result) >= 3
    for seg in result:
        duration = seg["end"] - seg["start"]
        assert duration <= 3.5  # small tolerance for rounding


def test_split_preserves_timing():
    from asr.segment_utils import split_segments
    segments = [
        {"start": 10.0, "end": 20.0, "text": "one two three four five six seven eight nine ten"},
    ]
    result = split_segments(segments, max_words=5, max_duration=60.0)
    # First segment should start at 10.0
    assert result[0]["start"] == 10.0
    # Last segment should end at 20.0
    assert result[-1]["end"] == 20.0
    # Segments should be contiguous
    for i in range(len(result) - 1):
        assert abs(result[i]["end"] - result[i + 1]["start"]) < 0.01


def test_empty_segments():
    from asr.segment_utils import split_segments
    result = split_segments([], max_words=40, max_duration=10.0)
    assert result == []


def test_single_word_segment():
    from asr.segment_utils import split_segments
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
    result = split_segments(segments, max_words=40, max_duration=10.0)
    assert len(result) == 1
    assert result[0]["text"] == "Hello"


def test_multiple_segments_mixed():
    from asr.segment_utils import split_segments
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Short sentence."},
        {"start": 2.0, "end": 12.0, "text": "This is a very long sentence that has way too many words for a single subtitle segment to display properly on screen"},
    ]
    result = split_segments(segments, max_words=10, max_duration=10.0)
    assert len(result) >= 3  # first stays, second splits
    assert result[0]["text"] == "Short sentence."


def test_sentence_boundary_splitting():
    from asr.segment_utils import split_segments
    segments = [
        {"start": 0.0, "end": 8.0, "text": "Hello world. This is great. And more text here for testing."},
    ]
    result = split_segments(segments, max_words=5, max_duration=60.0)
    assert len(result) >= 2
    # Should try to split at sentence boundaries
    for seg in result:
        assert len(seg["text"].split()) <= 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_segment_utils.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement split_segments**

Create `backend/asr/segment_utils.py`:

```python
"""Post-processing utilities for ASR segments."""

import re
from typing import List


def split_segments(
    segments: List[dict],
    max_words: int = 40,
    max_duration: float = 10.0,
) -> List[dict]:
    """Split oversized segments by word count and duration.

    Args:
        segments: list of {"start": float, "end": float, "text": str}
        max_words: maximum words per segment
        max_duration: maximum duration in seconds per segment

    Returns:
        New list of segments with splits applied.
    """
    result = []
    for seg in segments:
        words = seg["text"].split()
        duration = seg["end"] - seg["start"]

        if len(words) <= max_words and duration <= max_duration:
            result.append(seg)
            continue

        # Determine how many chunks we need
        chunks_by_words = max(1, -(-len(words) // max_words))  # ceil division
        chunks_by_duration = max(1, int(duration / max_duration) + (1 if duration % max_duration > 0.01 else 0))
        num_chunks = max(chunks_by_words, chunks_by_duration)

        # Try sentence boundary splitting first
        sub_segments = _split_at_boundaries(seg, words, num_chunks, max_words)
        result.extend(sub_segments)

    return result


def _split_at_boundaries(
    seg: dict, words: List[str], num_chunks: int, max_words: int
) -> List[dict]:
    """Split a segment into chunks, preferring sentence boundaries."""
    if len(words) <= 1:
        return [seg]

    total_duration = seg["end"] - seg["start"]
    total_words = len(words)

    # Find sentence boundaries (after periods, question marks, exclamation marks)
    boundary_indices = []
    running_text = ""
    for i, word in enumerate(words):
        running_text += word
        if re.search(r'[.!?]$', word) and i < total_words - 1:
            boundary_indices.append(i + 1)
        running_text = ""

    # Build split points: prefer boundaries, fall back to even splits
    target_size = max(1, total_words // num_chunks)
    split_points = []
    pos = 0

    for _ in range(num_chunks - 1):
        target = pos + target_size
        # Find nearest boundary
        best = target
        if boundary_indices:
            candidates = [b for b in boundary_indices if pos < b <= min(target + target_size // 2, pos + max_words)]
            if candidates:
                best = min(candidates, key=lambda b: abs(b - target))
            else:
                best = min(target, pos + max_words)
        else:
            best = min(target, pos + max_words)

        if best <= pos:
            best = min(pos + max_words, total_words)
        if best >= total_words:
            break

        split_points.append(best)
        pos = best

    # Build sub-segments
    split_points = [0] + split_points + [total_words]
    sub_segments = []

    for i in range(len(split_points) - 1):
        chunk_start_idx = split_points[i]
        chunk_end_idx = split_points[i + 1]
        chunk_words = words[chunk_start_idx:chunk_end_idx]

        if not chunk_words:
            continue

        # Proportional timing
        frac_start = chunk_start_idx / total_words
        frac_end = chunk_end_idx / total_words
        chunk_start = seg["start"] + frac_start * total_duration
        chunk_end = seg["start"] + frac_end * total_duration

        sub_segments.append({
            "start": round(chunk_start, 2),
            "end": round(chunk_end, 2),
            "text": " ".join(chunk_words),
        })

    return sub_segments if sub_segments else [seg]
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_segment_utils.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/asr/segment_utils.py backend/tests/test_segment_utils.py
git commit -m "feat: add split_segments post-processing for ASR output"
```

---

### Task 3: Update translation engine to accept batch_size/temperature params

**Files:**
- Modify: `backend/translation/__init__.py`
- Modify: `backend/translation/ollama_engine.py`
- Modify: `backend/translation/mock_engine.py`
- Modify: `backend/tests/test_translation.py`

- [ ] **Step 1: Add test for parameterized translate**

Append to `backend/tests/test_translation.py`:

```python
def test_ollama_translate_custom_batch_size():
    from translation.ollama_engine import OllamaTranslationEngine
    from unittest.mock import patch, MagicMock
    import json as json_mod

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    # 5 segments with batch_size=2 → should make 3 API calls
    segs = [{"start": float(i), "end": float(i+1), "text": f"Sentence {i+1}."} for i in range(5)]

    call_count = [0]
    def mock_urlopen(req, **kwargs):
        call_count[0] += 1
        body = json.loads(req.data)
        lines = body["messages"][1]["content"].strip().split("\n")
        response_lines = "\n".join(f"{i+1}. 翻譯{i+1}" for i in range(len(lines)))
        mock_resp = MagicMock()
        mock_resp.read.return_value = json_mod.dumps({"message": {"content": response_lines}}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = engine.translate(segs, glossary=[], style="formal", batch_size=2, temperature=0.5)

    assert len(result) == 5
    assert call_count[0] == 3  # ceil(5/2) = 3 batches
```

- [ ] **Step 2: Update TranslationEngine ABC**

In `backend/translation/__init__.py`, update the `translate` method signature:

Change:
```python
    @abstractmethod
    def translate(self, segments: List[dict], glossary: Optional[List[dict]] = None, style: str = "formal") -> List[TranslatedSegment]:
```

To:
```python
    @abstractmethod
    def translate(self, segments: List[dict], glossary: Optional[List[dict]] = None, style: str = "formal", batch_size: Optional[int] = None, temperature: Optional[float] = None) -> List[TranslatedSegment]:
```

- [ ] **Step 3: Update OllamaTranslationEngine**

In `backend/translation/ollama_engine.py`, update `translate()`:

Change:
```python
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
    ) -> List[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        all_translated = []

        for i in range(0, len(segments), BATCH_SIZE):
            batch = segments[i : i + BATCH_SIZE]
            translated_batch = self._translate_batch(batch, glossary, style)
            all_translated.extend(translated_batch)
```

To:
```python
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> List[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        all_translated = []

        for i in range(0, len(segments), effective_batch):
            batch = segments[i : i + effective_batch]
            translated_batch = self._translate_batch(batch, glossary, style, effective_temp)
            all_translated.extend(translated_batch)
```

Also update `_translate_batch` and `_call_ollama` to accept `temperature`:

Change `_translate_batch` signature:
```python
    def _translate_batch(self, segments, glossary, style, temperature):
```

Change `_call_ollama` to use the passed temperature:
```python
            "options": {"temperature": temperature},
```

And update the call in `_translate_batch`:
```python
        response_text = self._call_ollama(system_prompt, user_message, temperature)
```

And `_call_ollama` signature:
```python
    def _call_ollama(self, system_prompt: str, user_message: str, temperature: float) -> str:
```

- [ ] **Step 4: Update MockTranslationEngine**

In `backend/translation/mock_engine.py`, update `translate()` to accept the new params (ignore them):

```python
    def translate(self, segments: List[dict], glossary: Optional[List[dict]] = None, style: str = "formal", batch_size: Optional[int] = None, temperature: Optional[float] = None) -> List[TranslatedSegment]:
```

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/translation/ backend/tests/test_translation.py
git commit -m "feat: translation engine accepts batch_size and temperature parameters"
```

---

### Task 4: Add REST endpoints and integrate into pipeline

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_language_config.py`

- [ ] **Step 1: Add API tests**

Append to `backend/tests/test_language_config.py`:

```python
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_api_list_languages():
    from app import app, _init_language_config_manager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lang_dir = tmp_path / "languages"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({
            "id": "en", "name": "English",
            "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0},
            "translation": {"batch_size": 10, "temperature": 0.1},
        }))
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/languages")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data["languages"]) == 1
            assert data["languages"][0]["id"] == "en"


def test_api_get_language():
    from app import app, _init_language_config_manager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lang_dir = tmp_path / "languages"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({
            "id": "en", "name": "English",
            "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0},
            "translation": {"batch_size": 10, "temperature": 0.1},
        }))
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/languages/en")
            assert resp.status_code == 200
            assert resp.get_json()["language"]["id"] == "en"


def test_api_get_language_not_found():
    from app import app, _init_language_config_manager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "languages").mkdir()
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/languages/fr")
            assert resp.status_code == 404


def test_api_update_language():
    from app import app, _init_language_config_manager
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lang_dir = tmp_path / "languages"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({
            "id": "en", "name": "English",
            "asr": {"max_words_per_segment": 40, "max_segment_duration": 10.0},
            "translation": {"batch_size": 10, "temperature": 0.1},
        }))
        _init_language_config_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.patch("/api/languages/en", json={
                "asr": {"max_words_per_segment": 30, "max_segment_duration": 8.0},
                "translation": {"batch_size": 5, "temperature": 0.2},
            })
            assert resp.status_code == 200
            assert resp.get_json()["language"]["asr"]["max_words_per_segment"] == 30
```

- [ ] **Step 2: Add language config to app.py**

At the top of `backend/app.py`, after the glossary import, add:
```python
from language_config import LanguageConfigManager, DEFAULT_ASR_CONFIG, DEFAULT_TRANSLATION_CONFIG
```

After `_init_glossary_manager`, add:
```python
_language_config_manager = LanguageConfigManager(CONFIG_DIR)


def _init_language_config_manager(config_dir):
    """Re-initialize language config manager (used by tests)."""
    global _language_config_manager
    _language_config_manager = LanguageConfigManager(config_dir)
```

Add REST endpoints after glossary endpoints:
```python
# ============================================================
# Language Configuration API
# ============================================================

@app.route('/api/languages', methods=['GET'])
def api_list_languages():
    return jsonify({"languages": _language_config_manager.list_all()})


@app.route('/api/languages/<lang_id>', methods=['GET'])
def api_get_language(lang_id):
    config = _language_config_manager.get(lang_id)
    if not config:
        return jsonify({"error": "Language config not found"}), 404
    return jsonify({"language": config})


@app.route('/api/languages/<lang_id>', methods=['PATCH'])
def api_update_language(lang_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        config = _language_config_manager.update(lang_id, data)
        if not config:
            return jsonify({"error": "Language config not found"}), 404
        return jsonify({"language": config})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400
```

- [ ] **Step 3: Integrate language config into transcription pipeline**

In `app.py`, find the profile-based ASR engine path inside `transcribe_with_segments()` (the `if use_profile_engine:` block). After `raw_segments = engine.transcribe(...)`, add post-processing:

```python
            # Post-process segments with language config
            from asr.segment_utils import split_segments
            lang_config_id = profile["asr"].get("language_config_id", language)
            lang_config = _language_config_manager.get(lang_config_id)
            asr_params = lang_config["asr"] if lang_config else DEFAULT_ASR_CONFIG
            raw_segments = split_segments(
                raw_segments,
                max_words=asr_params["max_words_per_segment"],
                max_duration=asr_params["max_segment_duration"],
            )
```

- [ ] **Step 4: Integrate language config into translation**

In `_auto_translate()`, before `engine.translate(...)`, load language config and pass params:

Change:
```python
            translated = engine.translate(asr_segments, glossary=glossary_entries, style=style)
```

To:
```python
            # Load language config for translation params
            lang_config_id = profile.get("asr", {}).get("language_config_id", profile.get("asr", {}).get("language", "en"))
            lang_config = _language_config_manager.get(lang_config_id)
            trans_params = lang_config["translation"] if lang_config else DEFAULT_TRANSLATION_CONFIG

            translated = engine.translate(
                asr_segments,
                glossary=glossary_entries,
                style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
            )
```

Do the same in `api_translate_file()`.

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_language_config.py
git commit -m "feat: add language config REST endpoints and integrate into pipeline"
```

---

### Task 5: Update default profiles with language_config_id

**Files:**
- Modify: `backend/config/profiles/dev-default.json`
- Modify: `backend/config/profiles/prod-default.json`

- [ ] **Step 1: Add language_config_id to dev profile**

In `backend/config/profiles/dev-default.json`, add `"language_config_id": "en"` to the `asr` block.

- [ ] **Step 2: Add language_config_id to prod profile**

In `backend/config/profiles/prod-default.json`, add `"language_config_id": "en"` to the `asr` block.

- [ ] **Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/config/profiles/
git commit -m "feat: add language_config_id to default profiles"
```

---

### Task 6: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Test language config API**

```bash
# List languages
curl -s http://localhost:5001/api/languages | python3 -m json.tool

# Get English config
curl -s http://localhost:5001/api/languages/en | python3 -m json.tool

# Update English config
curl -s -X PATCH http://localhost:5001/api/languages/en \
  -H "Content-Type: application/json" \
  -d '{"asr": {"max_words_per_segment": 30, "max_segment_duration": 8.0}, "translation": {"batch_size": 5, "temperature": 0.2}}' | python3 -m json.tool
```

- [ ] **Step 3: Verify pipeline integration**

Upload a video, transcribe, verify segments are split according to language config params.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete language configuration system"
```
