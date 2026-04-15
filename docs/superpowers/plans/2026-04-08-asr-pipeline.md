# ASR Pipeline Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a unified ASR engine interface with Whisper fully implemented and Qwen3-ASR/FLG-ASR as stubs, integrated with the profile system from Phase 1.

**Architecture:** An `asr/` package defines the `ASREngine` ABC and a factory function. `WhisperEngine` encapsulates the existing Whisper logic (extracted from app.py). Stubs for Qwen3 and FLG raise `NotImplementedError`. `transcribe_with_segments()` in app.py delegates to the engine from the active profile, with a legacy fallback.

**Tech Stack:** Python 3.8+, faster-whisper, openai-whisper, ABC, Flask.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/asr/__init__.py` | ASREngine ABC, Segment TypedDict, create_asr_engine() factory |
| Create | `backend/asr/whisper_engine.py` | WhisperEngine — full implementation with model caching |
| Create | `backend/asr/qwen3_engine.py` | Qwen3ASREngine stub |
| Create | `backend/asr/flg_engine.py` | FLGASREngine stub |
| Create | `backend/tests/test_asr.py` | Tests for ASR interface, factory, stubs, and WhisperEngine |
| Modify | `backend/app.py` | Integrate ASR engine into transcribe_with_segments, add /api/asr/engines |

---

### Task 1: Create ASR interface and factory

**Files:**
- Create: `backend/asr/__init__.py`
- Create: `backend/tests/test_asr.py`

- [ ] **Step 1: Write failing tests for interface and factory**

Create `backend/tests/test_asr.py`:

```python
import pytest


def test_create_whisper_engine():
    from asr import create_asr_engine
    config = {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"}
    engine = create_asr_engine(config)
    assert engine is not None
    info = engine.get_info()
    assert info["engine"] == "whisper"


def test_create_qwen3_engine():
    from asr import create_asr_engine
    config = {"engine": "qwen3-asr", "model_size": "large", "language": "en", "device": "cuda"}
    engine = create_asr_engine(config)
    info = engine.get_info()
    assert info["engine"] == "qwen3-asr"
    assert info["available"] is False


def test_create_flg_engine():
    from asr import create_asr_engine
    config = {"engine": "flg-asr", "model_size": "large", "language": "en", "device": "cuda"}
    engine = create_asr_engine(config)
    info = engine.get_info()
    assert info["engine"] == "flg-asr"
    assert info["available"] is False


def test_create_unknown_engine_raises():
    from asr import create_asr_engine
    with pytest.raises(ValueError, match="Unknown ASR engine"):
        create_asr_engine({"engine": "nonexistent"})


def test_stub_transcribe_raises():
    from asr import create_asr_engine
    engine = create_asr_engine({"engine": "qwen3-asr", "model_size": "large", "language": "en"})
    with pytest.raises(NotImplementedError):
        engine.transcribe("/tmp/test.wav", language="en")


def test_flg_stub_transcribe_raises():
    from asr import create_asr_engine
    engine = create_asr_engine({"engine": "flg-asr", "model_size": "large", "language": "en"})
    with pytest.raises(NotImplementedError):
        engine.transcribe("/tmp/test.wav", language="en")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_asr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'asr'`

- [ ] **Step 3: Create asr/__init__.py with ABC and factory**

Create `backend/asr/__init__.py`:

```python
"""ASR Pipeline — unified interface for speech recognition engines."""

from abc import ABC, abstractmethod
from typing import TypedDict


class Segment(TypedDict):
    start: float
    end: float
    text: str


class ASREngine(ABC):
    """Abstract base class for ASR engines."""

    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        """Transcribe audio file to text segments with timestamps."""

    @abstractmethod
    def get_info(self) -> dict:
        """Return engine metadata.

        Returns dict with keys: engine (str), model_size (str),
        languages (list[str]), available (bool).
        """


def create_asr_engine(asr_config: dict) -> ASREngine:
    """Create an ASR engine from a profile's asr config block.

    Args:
        asr_config: dict with at least {"engine": str, "model_size": str}

    Returns:
        An ASREngine instance.

    Raises:
        ValueError: If engine name is not recognized.
    """
    engine_name = asr_config.get("engine", "")

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

- [ ] **Step 4: Create stubs and WhisperEngine skeleton so factory works**

Create `backend/asr/qwen3_engine.py`:

```python
"""Qwen3-ASR engine stub — not available in dev environment."""

from . import ASREngine, Segment


class Qwen3ASREngine(ASREngine):
    def __init__(self, config: dict):
        self._config = config

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

Create `backend/asr/flg_engine.py`:

```python
"""FLG-ASR engine stub — not available in dev environment."""

from . import ASREngine, Segment


class FLGASREngine(ASREngine):
    def __init__(self, config: dict):
        self._config = config

    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        raise NotImplementedError(
            "FLG-ASR is not available in this environment. "
            "Use the 'whisper' engine or deploy on production hardware."
        )

    def get_info(self) -> dict:
        return {
            "engine": "flg-asr",
            "model_size": self._config.get("model_size", "unknown"),
            "languages": ["en", "zh"],
            "available": False,
        }
```

Create a minimal `backend/asr/whisper_engine.py` (skeleton only — full impl in Task 2):

```python
"""Whisper ASR engine — full implementation using faster-whisper or openai-whisper."""

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
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_asr.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/asr/ backend/tests/test_asr.py
git commit -m "feat: add ASR interface, factory, and engine stubs"
```

---

### Task 2: Implement WhisperEngine

**Files:**
- Modify: `backend/asr/whisper_engine.py`
- Modify: `backend/tests/test_asr.py`

- [ ] **Step 1: Add WhisperEngine test**

Append to `backend/tests/test_asr.py`:

```python
from unittest.mock import patch, MagicMock
from collections import namedtuple


def test_whisper_engine_transcribe_faster():
    """Test WhisperEngine with mocked faster-whisper."""
    from asr.whisper_engine import WhisperEngine

    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"})

    # Mock a faster-whisper segment
    MockSeg = namedtuple("MockSeg", ["start", "end", "text", "words"])
    mock_segments = [
        MockSeg(start=0.0, end=2.5, text=" Hello world", words=None),
        MockSeg(start=2.5, end=5.0, text=" Testing one two", words=None),
    ]
    MockInfo = namedtuple("MockInfo", ["language"])
    mock_info = MockInfo(language="en")

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(mock_segments), mock_info)

    with patch.object(engine, '_get_model', return_value=(mock_model, 'faster')):
        result = engine.transcribe("/tmp/test.wav", language="en")

    assert len(result) == 2
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.5
    assert result[0]["text"] == "Hello world"
    assert result[1]["text"] == "Testing one two"


def test_whisper_engine_transcribe_openai():
    """Test WhisperEngine with mocked openai-whisper."""
    from asr.whisper_engine import WhisperEngine

    engine = WhisperEngine({"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"})

    mock_result = {
        "text": "Hello world",
        "language": "en",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "text": " Hello world"},
            {"id": 1, "start": 2.5, "end": 5.0, "text": " Testing"},
        ]
    }

    mock_model = MagicMock()
    mock_model.transcribe.return_value = mock_result

    with patch.object(engine, '_get_model', return_value=(mock_model, 'openai')):
        result = engine.transcribe("/tmp/test.wav", language="en")

    assert len(result) == 2
    assert result[0]["text"] == "Hello world"
    assert result[1]["text"] == "Testing"


def test_whisper_engine_get_info():
    from asr.whisper_engine import WhisperEngine
    engine = WhisperEngine({"engine": "whisper", "model_size": "small", "language": "en", "device": "auto"})
    info = engine.get_info()
    assert info["engine"] == "whisper"
    assert info["model_size"] == "small"
    assert info["available"] is True
    assert "en" in info["languages"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_asr.py::test_whisper_engine_transcribe_faster -v`
Expected: FAIL — `NotImplementedError` or `AttributeError` (_get_model doesn't exist)

- [ ] **Step 3: Implement WhisperEngine**

Replace `backend/asr/whisper_engine.py` with:

```python
"""Whisper ASR engine — full implementation using faster-whisper or openai-whisper."""

import threading

from . import ASREngine, Segment

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

# Try to import openai-whisper
try:
    import whisper as openai_whisper
    OPENAI_WHISPER_AVAILABLE = True
except ImportError:
    OPENAI_WHISPER_AVAILABLE = False

# Module-level model caches (shared across all WhisperEngine instances)
_faster_model_cache: dict = {}
_openai_model_cache: dict = {}
_model_lock = threading.Lock()


class WhisperEngine(ASREngine):
    """ASR engine backed by faster-whisper (preferred) or openai-whisper."""

    def __init__(self, config: dict):
        self._config = config
        self._model_size = config.get("model_size", "small")
        self._device = config.get("device", "auto")

    def _get_model(self):
        """Load and cache the Whisper model. Returns (model, backend_name)."""
        with _model_lock:
            if FASTER_WHISPER_AVAILABLE:
                if self._model_size not in _faster_model_cache:
                    print(f"Loading faster-whisper model: {self._model_size}")
                    _faster_model_cache[self._model_size] = FasterWhisperModel(
                        self._model_size, device=self._device, compute_type="int8"
                    )
                    print(f"faster-whisper model {self._model_size} loaded")
                return _faster_model_cache[self._model_size], "faster"
            elif OPENAI_WHISPER_AVAILABLE:
                if self._model_size not in _openai_model_cache:
                    print(f"Loading openai-whisper model: {self._model_size}")
                    _openai_model_cache[self._model_size] = openai_whisper.load_model(
                        self._model_size
                    )
                    print(f"openai-whisper model {self._model_size} loaded")
                return _openai_model_cache[self._model_size], "openai"
            else:
                raise RuntimeError("Neither faster-whisper nor openai-whisper is installed")

    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        """Transcribe audio file. Returns list of Segment dicts."""
        model, backend = self._get_model()

        if backend == "faster":
            return self._transcribe_faster(model, audio_path, language)
        else:
            return self._transcribe_openai(model, audio_path, language)

    def _transcribe_faster(self, model, audio_path: str, language: str) -> list[Segment]:
        """Transcribe using faster-whisper."""
        seg_iter, _info = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
        )
        segments = []
        for seg in seg_iter:
            segments.append(Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
            ))
        return segments

    def _transcribe_openai(self, model, audio_path: str, language: str) -> list[Segment]:
        """Transcribe using openai-whisper."""
        result = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            verbose=False,
            fp16=False,
        )
        segments = []
        for seg in result.get("segments", []):
            segments.append(Segment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
            ))
        return segments

    def get_info(self) -> dict:
        return {
            "engine": "whisper",
            "model_size": self._model_size,
            "languages": ["en", "zh", "ja", "ko", "fr", "de", "es"],
            "available": True,
        }
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_asr.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/asr/whisper_engine.py backend/tests/test_asr.py
git commit -m "feat: implement WhisperEngine with faster-whisper and openai-whisper support"
```

---

### Task 3: Integrate ASR engine into app.py

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Add /api/asr/engines endpoint**

After the profile routes in `backend/app.py`, add:

```python
# ============================================================
# ASR Engine Info
# ============================================================

@app.route('/api/asr/engines', methods=['GET'])
def api_list_asr_engines():
    """List available ASR engines with status."""
    from asr import create_asr_engine
    engines_info = []
    for engine_name, desc in [
        ("whisper", "OpenAI Whisper (local)"),
        ("qwen3-asr", "Qwen3-ASR (stub — production only)"),
        ("flg-asr", "FLG-ASR (stub — production only)"),
    ]:
        try:
            engine = create_asr_engine({"engine": engine_name, "model_size": "unknown"})
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

- [ ] **Step 2: Modify transcribe_with_segments to use ASR engine when profile is active**

In `backend/app.py`, find `transcribe_with_segments()` (around line 194). The function currently starts with:

```python
def transcribe_with_segments(file_path: str, model_size: str = 'small', sid: str = None):
    model, backend = get_model(model_size, backend='auto')
```

Change it to check for an active profile first. Replace the function signature and the first few lines (up to and including the audio extraction block) with:

```python
def transcribe_with_segments(file_path: str, model_size: str = 'small', sid: str = None):
    """
    Transcribe audio/video file and emit segments with timestamps.
    If an active profile exists, uses the profile's ASR engine.
    Otherwise falls back to legacy direct Whisper path.
    """
    # Check if we should use the profile-based ASR engine
    profile = _profile_manager.get_active()
    use_profile_engine = (
        profile is not None
        and profile.get("asr", {}).get("engine") == "whisper"
    )

    if not use_profile_engine:
        # Legacy path: use get_model() directly
        model, backend = get_model(model_size, backend='auto')
    
    # Check if it's a video file - extract audio first
    suffix = Path(file_path).suffix.lower()
    audio_path = file_path
    temp_audio = None

    if suffix in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.mxf'}:
        temp_audio = str(UPLOAD_DIR / f"audio_{uuid.uuid4().hex}.wav")
        if sid:
            socketio.emit('transcription_status',
                         {'status': 'extracting', 'message': '正在提取音頻...'},
                         room=sid)

        if not extract_audio(file_path, temp_audio):
            if sid:
                socketio.emit('transcription_error',
                             {'error': '無法提取音頻，請確保 ffmpeg 已安裝'},
                             room=sid)
            return None
        audio_path = temp_audio

    try:
        # Get total media duration for progress tracking
        total_duration = get_media_duration(audio_path)
        transcribe_start_time = time.time()

        if sid:
            socketio.emit('transcription_status', {
                'status': 'transcribing',
                'message': '正在轉錄中...',
                'total_duration': total_duration,
            }, room=sid)

        segments = []

        def emit_segment_with_progress(segment, sid):
            """Emit a segment along with progress info"""
            if not sid:
                return
            progress = 0
            eta = None
            if total_duration > 0:
                progress = min(segment['end'] / total_duration, 1.0)
                elapsed = time.time() - transcribe_start_time
                if progress > 0.01:
                    total_est = elapsed / progress
                    eta = max(0, total_est - elapsed)
            socketio.emit('subtitle_segment', {
                **segment,
                'progress': round(progress, 4),
                'eta_seconds': round(eta, 1) if eta is not None else None,
                'total_duration': total_duration,
            }, room=sid)

        # === Profile-based ASR engine path ===
        if use_profile_engine:
            from asr import create_asr_engine
            engine = create_asr_engine(profile["asr"])
            language = profile["asr"].get("language", "en")
            raw_segments = engine.transcribe(audio_path, language=language)

            for i, seg in enumerate(raw_segments):
                segment = {
                    'id': i,
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': seg['text'],
                    'words': [],
                }
                segments.append(segment)
                emit_segment_with_progress(segment, sid)

            return {
                'text': ' '.join(s['text'] for s in segments),
                'language': language,
                'segments': segments,
                'backend': engine.get_info().get('engine', 'whisper'),
            }

        # === Legacy path (no profile or non-whisper engine) ===
```

The rest of the function (the `if backend == 'faster':` and `else:` blocks) stays unchanged as the legacy path.

Note: Also add `.mxf` to the video extensions set (line: `if suffix in {'.mp4', '.mov', ...}`).

- [ ] **Step 3: Test manually with curl**

Start backend and test:
```bash
# Test ASR engines endpoint
curl -s http://localhost:5001/api/asr/engines | python3 -m json.tool
```

Expected:
```json
{
  "engines": [
    {"engine": "whisper", "available": true, "description": "OpenAI Whisper (local)"},
    {"engine": "qwen3-asr", "available": false, "description": "Qwen3-ASR (stub — production only)"},
    {"engine": "flg-asr", "available": false, "description": "FLG-ASR (stub — production only)"}
  ]
}
```

- [ ] **Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS (25 profile tests + 9 ASR tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app.py
git commit -m "feat: integrate ASR engine into transcribe_with_segments and add /api/asr/engines"
```

---

### Task 4: Add API test for /api/asr/engines

**Files:**
- Modify: `backend/tests/test_asr.py`

- [ ] **Step 1: Add API test**

Append to `backend/tests/test_asr.py`:

```python
import json


def test_api_list_asr_engines():
    """Test the /api/asr/engines REST endpoint."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/asr/engines")
        assert resp.status_code == 200
        data = resp.get_json()
        engines = data["engines"]
        assert len(engines) == 3

        engine_names = [e["engine"] for e in engines]
        assert "whisper" in engine_names
        assert "qwen3-asr" in engine_names
        assert "flg-asr" in engine_names

        whisper_info = next(e for e in engines if e["engine"] == "whisper")
        assert whisper_info["available"] is True

        qwen_info = next(e for e in engines if e["engine"] == "qwen3-asr")
        assert qwen_info["available"] is False
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_asr.py
git commit -m "test: add API test for /api/asr/engines endpoint"
```

---

### Task 5: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Start backend and verify ASR engines endpoint**

```bash
curl -s http://localhost:5001/api/asr/engines | python3 -m json.tool
```

- [ ] **Step 3: Verify profile-based transcription works**

Upload a small audio file via the frontend with the "Development" profile active (Whisper tiny, English). Verify transcription completes and segments appear.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 2 — ASR Pipeline with unified engine interface"
```
