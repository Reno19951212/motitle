# Translation Missing Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-retry segments that get `[TRANSLATION MISSING]` placeholders, so the model has a second chance before the human reviewer sees the output.

**Architecture:** Inside `translate()`'s batch loop, after each `_translate_batch()` call, detect missing segments by checking `[TRANSLATION MISSING]` in `zh_text`. If any are found, call the new `_retry_missing()` method with only those segments and splice results back into position. `_retry_missing()` delegates entirely to `_translate_batch()` — no new prompt logic. If retry also fails, the placeholder survives to `PostProcessor.process()` where `validate_batch` marks it `[NEEDS REVIEW]`.

**Tech Stack:** Python 3.9+, `unittest.mock.patch.object`, pytest. No new dependencies.

---

## File Structure

| File | Change |
|------|--------|
| `backend/translation/ollama_engine.py` | Add `_retry_missing()` method; add retry block inside `translate()` loop |
| `backend/tests/test_translation.py` | Add 4 new tests at the end of the file |

---

### Task 1: Write 4 Failing Tests

**Files:**
- Modify: `backend/tests/test_translation.py` (append after line 547)

These tests call `_retry_missing` which doesn't exist yet — all 4 will fail with `AttributeError`.

- [ ] **Step 1: Append the 4 tests to `backend/tests/test_translation.py`**

Add the following block at the end of the file (after the last test at line 547):

```python


# ---------------------------------------------------------------------------
# Retry-missing tests
# ---------------------------------------------------------------------------
from unittest.mock import patch as _patch


def _make_seg(start, end, en, zh):
    """Helper: build a TranslatedSegment-like dict."""
    return {"start": start, "end": end, "en_text": en, "zh_text": zh}


def test_no_retry_when_no_missing():
    """When all segments translate successfully, _retry_missing is never called."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    good_batch = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "歡迎收看新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=good_batch), \
         _patch.object(engine, "_retry_missing") as mock_retry:
        engine.translate(SAMPLE_SEGMENTS)
    mock_retry.assert_not_called()


def test_retry_called_for_missing_segments():
    """When _translate_batch returns a missing segment, _retry_missing is called with
    only that segment (not the whole batch)."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    batch_with_missing = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    retry_result = [
        _make_seg(2.5, 5.0, "Welcome to the news.", "歡迎收看新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_result) as mock_retry:
        engine.translate(SAMPLE_SEGMENTS)
    mock_retry.assert_called_once()
    # First positional arg is the list of missing segments
    retried_segs = mock_retry.call_args[0][0]
    assert len(retried_segs) == 1
    assert retried_segs[0]["text"] == "Welcome to the news."


def test_retry_success_replaces_missing():
    """When retry returns a real translation, the final output contains it — not the
    placeholder."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    batch_with_missing = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    retry_result = [
        _make_seg(2.5, 5.0, "Welcome to the news.", "歡迎收看新聞。"),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_result):
        result = engine.translate(SAMPLE_SEGMENTS)
    assert "[TRANSLATION MISSING]" not in result[1]["zh_text"]
    assert "歡迎收看新聞" in result[1]["zh_text"]


def test_retry_failure_keeps_missing_flagged():
    """When retry also fails (placeholder survives), PostProcessor marks it
    [NEEDS REVIEW] so the human reviewer sees it."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})
    batch_with_missing = [
        _make_seg(0.0, 2.5, "Good evening everyone.", "各位晚上好。"),
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    retry_still_missing = [
        _make_seg(2.5, 5.0, "Welcome to the news.", "[TRANSLATION MISSING] Welcome to the news."),
    ]
    with _patch.object(engine, "_translate_batch", return_value=batch_with_missing), \
         _patch.object(engine, "_retry_missing", return_value=retry_still_missing):
        result = engine.translate(SAMPLE_SEGMENTS)
    # PostProcessor's validate_batch turns [TRANSLATION MISSING] → [NEEDS REVIEW]
    assert "[NEEDS REVIEW]" in result[1]["zh_text"]
    assert "[TRANSLATION MISSING]" in result[1]["zh_text"]
```

- [ ] **Step 2: Run the 4 tests to verify they all fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_translation.py::test_no_retry_when_no_missing \
       tests/test_translation.py::test_retry_called_for_missing_segments \
       tests/test_translation.py::test_retry_success_replaces_missing \
       tests/test_translation.py::test_retry_failure_keeps_missing_flagged -v
```

Expected: 4 FAILED — `AttributeError: <OllamaTranslationEngine ...> does not have the attribute '_retry_missing'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add backend/tests/test_translation.py
git commit -m "test: add failing tests for translation missing retry"
```

---

### Task 2: Implement `_retry_missing()` and Retry Block

**Files:**
- Modify: `backend/translation/ollama_engine.py:82-93` (`translate()` loop) and `ollama_engine.py:95-106` (add new method after `_translate_batch`)

- [ ] **Step 1: Add the retry block inside `translate()`, replacing lines 82–93**

Current code (lines 82–93):

```python
        for i in range(0, len(segments), effective_batch):
            batch = segments[i : i + effective_batch]
            translated_batch = self._translate_batch(
                batch, glossary, style, effective_temp, context_pairs
            )
            all_translated.extend(translated_batch)
            if self._context_window > 0:
                new_pairs = [(seg["text"], t["zh_text"]) for seg, t in zip(batch, translated_batch)]
                context_pairs = (context_pairs + new_pairs)[-self._context_window:]
```

Replace with:

```python
        for i in range(0, len(segments), effective_batch):
            batch = segments[i : i + effective_batch]
            translated_batch = self._translate_batch(
                batch, glossary, style, effective_temp, context_pairs
            )
            missing_indices = [
                j for j, r in enumerate(translated_batch)
                if "[TRANSLATION MISSING]" in r.get("zh_text", "")
            ]
            if missing_indices:
                missing_segs = [batch[j] for j in missing_indices]
                retried = self._retry_missing(
                    missing_segs, glossary, style, effective_temp, context_pairs
                )
                translated_batch = [
                    retried.pop(0) if j in missing_indices else r
                    for j, r in enumerate(translated_batch)
                ]
            all_translated.extend(translated_batch)
            if self._context_window > 0:
                new_pairs = [(seg["text"], t["zh_text"]) for seg, t in zip(batch, translated_batch)]
                context_pairs = (context_pairs + new_pairs)[-self._context_window:]
```

- [ ] **Step 2: Add `_retry_missing()` method after `_translate_batch()` (after line 106)**

After the closing line of `_translate_batch()` (line 106: `return self._parse_response(response_text, segments)`), insert:

```python

    def _retry_missing(
        self,
        segments: List[dict],
        glossary: List[dict],
        style: str,
        temperature: float,
        context_pairs: list,
    ) -> List[TranslatedSegment]:
        """Re-translate segments that got [TRANSLATION MISSING] placeholders.

        Delegates to _translate_batch — no new prompt logic. Called at most once
        per batch. Remaining missing segments are flagged by PostProcessor."""
        return self._translate_batch(segments, glossary, style, temperature, context_pairs)
```

- [ ] **Step 3: Run the 4 new tests to verify they all pass**

```bash
cd backend && source venv/bin/activate
pytest tests/test_translation.py::test_no_retry_when_no_missing \
       tests/test_translation.py::test_retry_called_for_missing_segments \
       tests/test_translation.py::test_retry_success_replaces_missing \
       tests/test_translation.py::test_retry_failure_keeps_missing_flagged -v
```

Expected: 4 PASSED

- [ ] **Step 4: Run the full test suite to check for regressions**

```bash
cd backend && source venv/bin/activate
pytest tests/ -v
```

Expected: All tests PASSED (no regressions). If any fail, read the error — do not add workarounds, fix the root cause.

- [ ] **Step 5: Commit the implementation**

```bash
git add backend/translation/ollama_engine.py
git commit -m "feat: auto-retry [TRANSLATION MISSING] segments within each batch"
```
