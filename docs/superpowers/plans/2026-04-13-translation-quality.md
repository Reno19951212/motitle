# Translation Quality Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve translation output quality via RTHK-style prompt rewrite, sliding window inter-batch context, and a post-processing pipeline (opencc Traditional Chinese conversion + length flagging + bad-segment detection).

**Architecture:** New `translation/post_processor.py` module holds `validate_batch()` (moved from `sentence_pipeline.py`) and `TranslationPostProcessor` class. `OllamaTranslationEngine` gains a rewritten system prompt, sliding window context between batches, and calls `TranslationPostProcessor.process()` after all batches complete.

**Tech Stack:** Python 3.9+, `opencc-python-reimplemented` (pip), pytest, existing Ollama engine infrastructure.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/requirements.txt` | Modify | Add opencc dependency |
| `backend/translation/post_processor.py` | **Create** | `validate_batch()` + `TranslationPostProcessor` class |
| `backend/translation/sentence_pipeline.py` | Modify | Import `validate_batch` from `post_processor` |
| `backend/translation/ollama_engine.py` | Modify | New prompts, sliding window, PostProcessor call |
| `backend/tests/test_post_processor.py` | **Create** | Unit tests for PostProcessor |
| `backend/tests/test_translation.py` | Modify | Tests for new prompt content, sliding window, PostProcessor integration |

---

## Task 1: Add opencc Dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add opencc to requirements.txt**

Open `backend/requirements.txt` and add one line at the end:

```
opencc-python-reimplemented>=0.1.7
```

Full file after edit:
```
openai-whisper>=20231117
faster-whisper>=1.0.0
flask>=3.0.0
flask-cors>=4.0.0
flask-socketio>=5.3.6
werkzeug>=3.0.0
eventlet>=0.35.0
numpy>=1.24.0
torch>=2.0.0
torchaudio>=2.0.0
ffmpeg-python>=0.2.0
python-socketio>=5.10.0
gevent>=23.9.0
gevent-websocket>=0.10.1
pysbd>=0.3.4
opencc-python-reimplemented>=0.1.7
```

- [ ] **Step 2: Install the dependency**

```bash
cd backend && source venv/bin/activate && pip install opencc-python-reimplemented
```

Expected output: `Successfully installed opencc-python-reimplemented-...`

- [ ] **Step 3: Verify import works**

```bash
python -c "import opencc; c = opencc.OpenCC('s2twp'); print(c.convert('软件'))"
```

Expected output: `軟體`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add opencc-python-reimplemented dependency"
```

---

## Task 2: Create post_processor.py with validate_batch

**Files:**
- Create: `backend/translation/post_processor.py`
- Modify: `backend/translation/sentence_pipeline.py`
- Create: `backend/tests/test_post_processor.py`

- [ ] **Step 1: Write failing tests for validate_batch**

Create `backend/tests/test_post_processor.py`:

```python
def test_validate_batch_no_issues():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "Hello.", "zh_text": "你好。"},
        {"en_text": "Goodbye.", "zh_text": "再見。"},
    ]
    assert validate_batch(results) == []


def test_validate_batch_detects_repetition():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "A", "zh_text": "重複"},
        {"en_text": "B", "zh_text": "重複"},
        {"en_text": "C", "zh_text": "重複"},
    ]
    bad = validate_batch(results)
    assert 0 in bad and 1 in bad and 2 in bad


def test_validate_batch_detects_missing():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "Hello.", "zh_text": "[TRANSLATION MISSING] Hello."},
    ]
    assert 0 in validate_batch(results)


def test_validate_batch_detects_hallucination():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "Hi", "zh_text": "你好，今天天氣很好，我很開心，希望大家都過得好。"},
    ]
    # zh len >> en len * 3
    assert 0 in validate_batch(results)


def test_validate_batch_two_repetitions_not_flagged():
    from translation.post_processor import validate_batch
    results = [
        {"en_text": "A", "zh_text": "重複"},
        {"en_text": "B", "zh_text": "重複"},
        {"en_text": "C", "zh_text": "不同"},
    ]
    # Only 2 consecutive identical — below threshold of 3
    assert validate_batch(results) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -v
```

Expected: `ModuleNotFoundError: No module named 'translation.post_processor'`

- [ ] **Step 3: Create post_processor.py with validate_batch**

Create `backend/translation/post_processor.py`:

```python
"""Translation post-processor: opencc conversion, length flagging, quality validation."""

from typing import List


def validate_batch(results: List[dict]) -> List[int]:
    """Check translated segments for quality issues.

    Returns sorted list of problematic segment indices (empty = all valid).
    Checks: repetition (>=3 consecutive identical), missing translations,
    hallucination (zh > en*3 length).
    """
    bad_indices: List[int] = []

    # Check repetition: 3+ consecutive identical zh_text
    run_start = 0
    for i in range(1, len(results) + 1):
        if i < len(results) and results[i]["zh_text"] == results[run_start]["zh_text"]:
            continue
        run_length = i - run_start
        if run_length >= 3:
            for j in range(run_start, i):
                if j not in bad_indices:
                    bad_indices.append(j)
        run_start = i

    # Check individual segments
    for i, r in enumerate(results):
        zh = r.get("zh_text", "")
        en = r.get("en_text", "")
        if "[TRANSLATION MISSING]" in zh:
            if i not in bad_indices:
                bad_indices.append(i)
            continue
        if len(en) > 0 and len(zh) > len(en) * 3:
            if i not in bad_indices:
                bad_indices.append(i)

    return sorted(bad_indices)


class TranslationPostProcessor:
    """Apply post-processing steps to translated segments."""

    def __init__(self, max_chars: int = 16):
        self._max_chars = max_chars

    def process(self, results: List[dict]) -> List[dict]:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Update sentence_pipeline.py to import validate_batch from post_processor**

Open `backend/translation/sentence_pipeline.py`. Replace the existing `validate_batch` function definition with an import:

Find and remove this block (lines ~204–240):
```python
def validate_batch(results: List[dict]) -> List[int]:
    """Check translated segments for quality issues.
    ...
    """
    bad_indices: List[int] = []
    ...
    return sorted(bad_indices)
```

Add this import at the top of the file (after existing imports):
```python
from .post_processor import validate_batch
```

The file's `translate_with_sentences()` and other callers of `validate_batch` remain unchanged — they now use the imported version.

- [ ] **Step 6: Verify sentence_pipeline tests still pass**

```bash
cd backend && source venv/bin/activate && pytest tests/ -k "sentence" -v
```

Expected: all sentence pipeline tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/translation/post_processor.py backend/translation/sentence_pipeline.py backend/tests/test_post_processor.py
git commit -m "refactor: move validate_batch to post_processor.py, add test_post_processor.py"
```

---

## Task 3: Implement opencc Conversion

**Files:**
- Modify: `backend/translation/post_processor.py`
- Modify: `backend/tests/test_post_processor.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_post_processor.py`:

```python
def test_opencc_converts_simplified():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 0.0, "end": 1.0, "en_text": "software", "zh_text": "软件"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["zh_text"] == "軟體"


def test_opencc_converts_simplified_phrase():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 0.0, "end": 1.0, "en_text": "information", "zh_text": "信息技术"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["zh_text"] == "資訊技術"


def test_opencc_idempotent_on_traditional():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 0.0, "end": 1.0, "en_text": "government", "zh_text": "政府宣布新措施。"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["zh_text"] == "政府宣布新措施。"


def test_opencc_preserves_other_fields():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor()
    results = [{"start": 1.5, "end": 3.0, "en_text": "test", "zh_text": "软件"}]
    processed = processor._convert_to_traditional(results)
    assert processed[0]["start"] == 1.5
    assert processed[0]["end"] == 3.0
    assert processed[0]["en_text"] == "test"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py::test_opencc_converts_simplified -v
```

Expected: `NotImplementedError` or `AttributeError`

- [ ] **Step 3: Implement _convert_to_traditional**

Open `backend/translation/post_processor.py`. Add `import opencc` at the top. Update `TranslationPostProcessor.__init__` and add `_convert_to_traditional`:

```python
"""Translation post-processor: opencc conversion, length flagging, quality validation."""

import opencc
from typing import List


def validate_batch(results: List[dict]) -> List[int]:
    # ... (unchanged)


class TranslationPostProcessor:
    """Apply post-processing steps to translated segments."""

    def __init__(self, max_chars: int = 16):
        self._converter = opencc.OpenCC('s2twp')
        self._max_chars = max_chars

    def _convert_to_traditional(self, results: List[dict]) -> List[dict]:
        """Convert any simplified Chinese characters to Traditional Chinese."""
        return [
            {**r, 'zh_text': self._converter.convert(r['zh_text'])}
            for r in results
        ]

    def process(self, results: List[dict]) -> List[dict]:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -k "opencc" -v
```

Expected: all 4 opencc tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/post_processor.py backend/tests/test_post_processor.py
git commit -m "feat: implement opencc s2twp conversion in TranslationPostProcessor"
```

---

## Task 4: Implement Length Flagging

**Files:**
- Modify: `backend/translation/post_processor.py`
- Modify: `backend/tests/test_post_processor.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_post_processor.py`:

```python
def test_length_flag_applied_when_over_limit():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    long_text = "政府宣布將於下月推出一系列新的經濟振興措施"  # 21 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": long_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"].startswith("[LONG] ")
    assert long_text in processed[0]["zh_text"]


def test_length_flag_not_applied_when_within_limit():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    short_text = "颱風正逼近香港。"  # 8 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": short_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"] == short_text


def test_length_flag_at_exact_limit_not_flagged():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    exact_text = "一二三四五六七八九十一二三四五六"  # exactly 16 chars
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": exact_text}]
    processed = processor._flag_long_segments(results)
    assert processed[0]["zh_text"] == exact_text


def test_length_flag_preserves_original_text():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=5)
    original = "超過字數限制的句子"
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": original}]
    processed = processor._flag_long_segments(results)
    # Original text is preserved, not truncated
    assert original in processed[0]["zh_text"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -k "length_flag" -v
```

Expected: `AttributeError: 'TranslationPostProcessor' object has no attribute '_flag_long_segments'`

- [ ] **Step 3: Implement _flag_long_segments**

Add to `TranslationPostProcessor` in `backend/translation/post_processor.py`:

```python
    def _flag_long_segments(self, results: List[dict]) -> List[dict]:
        """Prepend [LONG] to segments exceeding max_chars. Preserves original text."""
        return [
            {**r, 'zh_text': f"[LONG] {r['zh_text']}"}
            if len(r['zh_text']) > self._max_chars
            else r
            for r in results
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -k "length_flag" -v
```

Expected: all 4 length flag tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/post_processor.py backend/tests/test_post_processor.py
git commit -m "feat: implement length flagging in TranslationPostProcessor"
```

---

## Task 5: Implement process() Method

**Files:**
- Modify: `backend/translation/post_processor.py`
- Modify: `backend/tests/test_post_processor.py`

- [ ] **Step 1: Write failing integration tests**

Append to `backend/tests/test_post_processor.py`:

```python
def test_process_converts_simplified_and_flags_long():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "software", "zh_text": "软件"},
        {"start": 1.0, "end": 2.0, "en_text": "x", "zh_text": "政府宣布將於下月推出一系列新的經濟振興措施"},
    ]
    processed = processor.process(results)
    assert processed[0]["zh_text"] == "軟體"          # simplified converted
    assert processed[1]["zh_text"].startswith("[LONG] ")  # long flagged


def test_process_opencc_runs_before_length_check():
    """opencc conversion happens before length check so length is measured on traditional text."""
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=3)
    # "软件测试" = 4 simplified chars → "軟體測試" = 4 traditional chars → flagged as LONG
    results = [{"start": 0.0, "end": 1.0, "en_text": "test", "zh_text": "软件测试"}]
    processed = processor.process(results)
    assert "軟體測試" in processed[0]["zh_text"]
    assert "[LONG]" in processed[0]["zh_text"]


def test_process_marks_bad_segments_needs_review():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"en_text": "A", "zh_text": "重複", "start": 0.0, "end": 1.0},
        {"en_text": "B", "zh_text": "重複", "start": 1.0, "end": 2.0},
        {"en_text": "C", "zh_text": "重複", "start": 2.0, "end": 3.0},
    ]
    processed = processor.process(results)
    for r in processed:
        assert r["zh_text"].startswith("[NEEDS REVIEW]")


def test_process_clean_input_unchanged():
    from translation.post_processor import TranslationPostProcessor
    processor = TranslationPostProcessor(max_chars=16)
    results = [
        {"start": 0.0, "end": 1.0, "en_text": "Good evening.", "zh_text": "各位晚上好。"},
        {"start": 1.0, "end": 2.0, "en_text": "Welcome.", "zh_text": "歡迎收看。"},
    ]
    processed = processor.process(results)
    assert processed[0]["zh_text"] == "各位晚上好。"
    assert processed[1]["zh_text"] == "歡迎收看。"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -k "process" -v
```

Expected: `NotImplementedError`

- [ ] **Step 3: Implement process()**

Replace the `process` stub in `backend/translation/post_processor.py`:

```python
    def process(self, results: List[dict]) -> List[dict]:
        """Run all post-processing steps in order."""
        results = self._convert_to_traditional(results)
        results = self._flag_long_segments(results)
        bad_indices = validate_batch(results)
        return self._mark_bad_segments(results, bad_indices)

    def _mark_bad_segments(self, results: List[dict], bad_indices: List[int]) -> List[dict]:
        """Prepend [NEEDS REVIEW] to segments flagged by validate_batch."""
        new_results = list(results)
        for idx in bad_indices:
            zh = new_results[idx]['zh_text']
            if not zh.startswith('[NEEDS REVIEW]'):
                new_results[idx] = {**new_results[idx], 'zh_text': f'[NEEDS REVIEW] {zh}'}
        return new_results
```

- [ ] **Step 4: Run full test_post_processor.py suite**

```bash
cd backend && source venv/bin/activate && pytest tests/test_post_processor.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/post_processor.py backend/tests/test_post_processor.py
git commit -m "feat: implement TranslationPostProcessor.process() pipeline"
```

---

## Task 6: Rewrite System Prompts

**Files:**
- Modify: `backend/translation/ollama_engine.py`
- Modify: `backend/tests/test_translation.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_translation.py`:

```python
def test_system_prompt_formal_forbids_simplified():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "NEVER use Simplified Chinese" in prompt or "Traditional Chinese ONLY" in prompt


def test_system_prompt_formal_has_char_limit():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "16" in prompt


def test_system_prompt_formal_has_rthk_context():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="formal", glossary=[])
    assert "繁體中文書面語" in prompt  # existing test still passes


def test_system_prompt_cantonese_forbids_simplified():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "NEVER use Simplified Chinese" in prompt or "Traditional Chinese ONLY" in prompt


def test_system_prompt_cantonese_has_char_limit():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    prompt = engine._build_system_prompt(style="cantonese", glossary=[])
    assert "16" in prompt
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -k "system_prompt_formal_forbids or system_prompt_formal_has_char or system_prompt_cantonese" -v
```

Expected: FAIL (current prompts lack these requirements)

- [ ] **Step 3: Replace prompt constants in ollama_engine.py**

Open `backend/translation/ollama_engine.py`. Replace the two prompt constants:

```python
SYSTEM_PROMPT_FORMAL = (
    "You are a professional broadcast subtitle translator for Hong Kong news (RTHK style).\n\n"
    "Rules:\n"
    "1. Translate English into formal Traditional Chinese (繁體中文書面語).\n"
    "2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.\n"
    "3. Each translation must be ≤16 Chinese characters. Be concise.\n"
    "4. Use neutral, journalistic tone. No colloquialisms.\n"
    "5. Output ONLY numbered translations. No explanations, no brackets, no notes.\n\n"
    "Example:\n"
    "1. The typhoon is approaching Hong Kong.\n"
    "→ 1. 颱風正逼近香港。"
)

SYSTEM_PROMPT_CANTONESE = (
    "You are a professional broadcast subtitle translator for Hong Kong news.\n\n"
    "Rules:\n"
    "1. Translate English into Cantonese Traditional Chinese (繁體中文粵語口語).\n"
    "2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.\n"
    "3. Each translation must be ≤16 Chinese characters. Be concise.\n"
    "4. Use natural spoken Cantonese expressions.\n"
    "5. Output ONLY numbered translations. No explanations, no brackets, no notes.\n\n"
    "Example:\n"
    "1. Good evening everyone.\n"
    "→ 1. 大家晚上好。"
)
```

- [ ] **Step 4: Run all translation tests**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -v
```

Expected: all tests PASS (existing tests check `"繁體中文書面語" in prompt` and `"粵語" in prompt` — both still satisfied by new prompts)

- [ ] **Step 5: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_translation.py
git commit -m "feat: rewrite system prompts with RTHK style, simplified Chinese ban, 16-char limit"
```

---

## Task 7: Implement Sliding Window Context

**Files:**
- Modify: `backend/translation/ollama_engine.py`
- Modify: `backend/tests/test_translation.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_translation.py`:

```python
def test_build_user_message_no_context():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    segs = [{"text": "Hello world."}]
    msg = engine._build_user_message(segs, context_pairs=[])
    assert "Context" not in msg
    assert "1. Hello world." in msg


def test_build_user_message_with_context():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    segs = [{"text": "The policy takes effect."}]
    context = [
        ("Officials announced today.", "官員今日宣布。"),
        ("Citizens should stay informed.", "市民應保持關注。"),
    ]
    msg = engine._build_user_message(segs, context_pairs=context)
    assert "Context" in msg
    assert "Officials announced today." in msg
    assert "官員今日宣布。" in msg
    assert "The policy takes effect." in msg
    assert "[Translate the following:]" in msg


def test_sliding_window_context_appears_in_second_batch():
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "context_window": 3})
    segments = [
        {"start": 0.0, "end": 1.0, "text": "First sentence."},
        {"start": 1.0, "end": 2.0, "text": "Second sentence."},
    ]
    captured_bodies = []

    def fake_urlopen(req, timeout=None):
        body = json_mod.loads(req.data.decode())
        captured_bodies.append(body)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json_mod.dumps({
            "message": {"content": f"1. 第{len(captured_bodies)}句。"}
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(segments, glossary=[], style="formal", batch_size=1)

    first_user_msg = captured_bodies[0]["messages"][1]["content"]
    assert "Context" not in first_user_msg

    second_user_msg = captured_bodies[1]["messages"][1]["content"]
    assert "Context" in second_user_msg
    assert "First sentence." in second_user_msg


def test_sliding_window_zero_disables_context():
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b", "context_window": 0})
    segments = [
        {"start": 0.0, "end": 1.0, "text": "First."},
        {"start": 1.0, "end": 2.0, "text": "Second."},
    ]
    captured_bodies = []

    def fake_urlopen(req, timeout=None):
        body = json_mod.loads(req.data.decode())
        captured_bodies.append(body)
        mock_resp = MagicMock()
        mock_resp.read.return_value = json_mod.dumps({
            "message": {"content": f"1. 第{len(captured_bodies)}句。"}
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(segments, glossary=[], style="formal", batch_size=1)

    second_user_msg = captured_bodies[1]["messages"][1]["content"]
    assert "Context" not in second_user_msg
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -k "context" -v
```

Expected: FAIL — `_build_user_message` doesn't accept `context_pairs`; `context_window` config key not used

- [ ] **Step 3: Add context_window to __init__ and update _build_user_message**

In `backend/translation/ollama_engine.py`, update `__init__`:

```python
    def __init__(self, config: dict):
        self._config = config
        self._engine_name = config.get("engine", "qwen2.5-3b")
        self._model = ENGINE_TO_MODEL.get(self._engine_name, "qwen2.5:3b")
        self._temperature = config.get("temperature", 0.1)
        self._base_url = config.get("ollama_url", "http://localhost:11434")
        self._context_window = config.get("context_window", 3)
```

Replace `_build_user_message`:

```python
    def _build_user_message(self, segments: List[dict], context_pairs: List[tuple] = None) -> str:
        lines = []
        if context_pairs:
            lines.append('[Context - previous translations for reference:]')
            for i, (en, zh) in enumerate(context_pairs, 1):
                lines.append(f'{i}. {en} → {zh}')
            lines.append('')
            lines.append('[Translate the following:]')
        for i, seg in enumerate(segments, 1):
            lines.append(f'{i}. {seg["text"]}')
        return '\n'.join(lines)
```

Update `_translate_batch` to accept and forward context_pairs:

```python
    def _translate_batch(
        self, segments: List[dict], glossary: List[dict], style: str, temperature: float,
        context_pairs: List[tuple] = None,
    ) -> List[TranslatedSegment]:
        system_prompt = self._build_system_prompt(style, glossary)
        user_message = self._build_user_message(segments, context_pairs or [])
        response_text = self._call_ollama(system_prompt, user_message, temperature)
        return self._parse_response(response_text, segments)
```

Update the batch loop in `translate()` to maintain rolling context_pairs:

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
        all_translated = []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        context_pairs: List[tuple] = []

        for i in range(0, len(segments), effective_batch):
            batch = segments[i : i + effective_batch]
            translated_batch = self._translate_batch(
                batch, glossary, style, effective_temp, context_pairs
            )
            all_translated.extend(translated_batch)
            if self._context_window > 0:
                for t in translated_batch:
                    context_pairs.append((t['en_text'], t['zh_text']))
                context_pairs = context_pairs[-self._context_window:]

        return all_translated
```

- [ ] **Step 4: Add context_window to get_params_schema()**

In `get_params_schema()`, add inside the `"params"` dict:

```python
                "context_window": {
                    "type": "integer",
                    "description": "Number of preceding translated pairs to include as context (0 = disabled)",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 3,
                },
```

- [ ] **Step 5: Run translation tests**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_translation.py
git commit -m "feat: add sliding window context (context_window=3) between translation batches"
```

---

## Task 8: Wire PostProcessor into translate()

**Files:**
- Modify: `backend/translation/ollama_engine.py`
- Modify: `backend/tests/test_translation.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_translation.py`:

```python
def test_translate_applies_opencc_postprocessing():
    """translate() runs opencc on all results — simplified Chinese is converted."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    mock_response_body = json_mod.dumps({
        "message": {"content": "1. 软件工程师。\n2. 信息技术。"}
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    segments = [
        {"start": 0.0, "end": 1.0, "text": "software engineer"},
        {"start": 1.0, "end": 2.0, "text": "information technology"},
    ]

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = engine.translate(segments, glossary=[], style="formal")

    assert "软" not in result[0]["zh_text"]   # 软件 → 軟體
    assert "信息" not in result[1]["zh_text"]  # 信息 → 資訊
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_translate_applies_opencc_postprocessing -v
```

Expected: FAIL — simplified characters still present in output

- [ ] **Step 3: Wire PostProcessor into translate()**

In `backend/translation/ollama_engine.py`, add the import at the top of the file:

```python
from .post_processor import TranslationPostProcessor
```

Update the `translate()` method — add `PostProcessor.process()` call after the batch loop (replace the final `return all_translated`):

```python
        processor = TranslationPostProcessor(max_chars=16)
        return processor.process(all_translated)
```

The complete updated `translate()` method:

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
        all_translated = []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        context_pairs: List[tuple] = []

        for i in range(0, len(segments), effective_batch):
            batch = segments[i : i + effective_batch]
            translated_batch = self._translate_batch(
                batch, glossary, style, effective_temp, context_pairs
            )
            all_translated.extend(translated_batch)
            if self._context_window > 0:
                for t in translated_batch:
                    context_pairs.append((t['en_text'], t['zh_text']))
                context_pairs = context_pairs[-self._context_window:]

        processor = TranslationPostProcessor(max_chars=16)
        return processor.process(all_translated)
```

- [ ] **Step 4: Run all tests**

```bash
cd backend && source venv/bin/activate && pytest tests/ -k "not api_" -v
```

Expected: all tests PASS. In particular, `test_ollama_translate_mocked_http` still passes because "各位晚上好。" (6 chars, already Traditional) is unchanged by PostProcessor.

- [ ] **Step 5: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_translation.py
git commit -m "feat: wire TranslationPostProcessor into OllamaTranslationEngine.translate()"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -k "not api_" -v
```

Expected: all tests PASS, no regressions.

- [ ] **Smoke check prompt**

```bash
python -c "
from translation.ollama_engine import OllamaTranslationEngine
e = OllamaTranslationEngine({'engine': 'qwen2.5-3b'})
print(e._build_system_prompt('formal', []))
print('---')
print(e._build_user_message([{'text': 'The typhoon is approaching.'}], context_pairs=[('Good evening.', '各位晚上好。')]))
"
```

Expected: RTHK-style prompt with Traditional Chinese rule + 16-char limit; user message shows context block then translate block.

- [ ] **Smoke check opencc**

```bash
python -c "
from translation.post_processor import TranslationPostProcessor
p = TranslationPostProcessor()
r = p.process([{'start':0,'end':1,'en_text':'software','zh_text':'软件工程师报告信息技术系统的最新状况'}])
print(r[0]['zh_text'])
"
```

Expected: Traditional Chinese output with `[LONG]` prefix (>16 chars).
