# Sentence-Aware Translation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix translation repetition by merging ASR fragments into complete sentences before translation, then redistributing Chinese text back to original segment timestamps.

**Architecture:** A new `sentence_pipeline.py` module wraps the existing `TranslationEngine` with three phases: merge fragments → translate sentences → redistribute + validate. Two call sites in `app.py` switch from `engine.translate()` to `translate_with_sentences()`.

**Tech Stack:** Python 3.9, pySBD (sentence boundary detection), existing Ollama/Mock translation engines

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/translation/sentence_pipeline.py` | Create | merge, redistribute, validate, orchestrate |
| `backend/tests/test_sentence_pipeline.py` | Create | Unit + integration tests |
| `backend/translation/ollama_engine.py` | Modify | Improved system prompts |
| `backend/app.py` | Modify | Switch 2 call sites to pipeline |
| `backend/requirements.txt` | Modify | Add pysbd |

---

### Task 1: Add pySBD dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add pysbd to requirements.txt**

Add this line at the end of `backend/requirements.txt`:

```
pysbd>=0.3.4
```

- [ ] **Step 2: Install the dependency**

Run: `cd backend && ../backend/venv/bin/pip install pysbd`

Expected: Successfully installed pysbd

- [ ] **Step 3: Verify pySBD works**

Run: `cd backend && ../backend/venv/bin/python -c "import pysbd; s = pysbd.Segmenter(language='en', clean=False); print(s.segment('Hello world. How are you?'))"`

Expected: `['Hello world. ', 'How are you?']`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add pysbd dependency for sentence boundary detection"
```

---

### Task 2: merge_to_sentences()

**Files:**
- Create: `backend/translation/sentence_pipeline.py`
- Create: `backend/tests/test_sentence_pipeline.py`

- [ ] **Step 1: Write failing tests for merge_to_sentences**

Create `backend/tests/test_sentence_pipeline.py`:

```python
"""Tests for sentence-aware translation pipeline."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_merge_empty_segments():
    from translation.sentence_pipeline import merge_to_sentences

    result = merge_to_sentences([])
    assert result == []


def test_merge_single_complete_sentence():
    from translation.sentence_pipeline import merge_to_sentences

    segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello world."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 1
    assert result[0]["text"] == "Hello world."
    assert result[0]["seg_indices"] == [0]
    assert result[0]["seg_word_counts"] == {0: 2}
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 3.0


def test_merge_fragments_into_two_sentences():
    from translation.sentence_pipeline import merge_to_sentences

    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 4.0, "text": "the mat. The dog"},
        {"start": 4.0, "end": 6.0, "text": "ran away quickly."},
    ]
    result = merge_to_sentences(segments)
    assert len(result) == 2

    # First sentence: "The cat sat on the mat."
    assert "The cat sat on the mat." in result[0]["text"]
    assert 0 in result[0]["seg_indices"]
    assert 1 in result[0]["seg_indices"]
    assert result[0]["start"] == 0.0

    # Second sentence: "The dog ran away quickly."
    assert "The dog ran away quickly." in result[1]["text"]
    assert 1 in result[1]["seg_indices"]
    assert 2 in result[1]["seg_indices"]
    assert result[1]["end"] == 6.0


def test_merge_shared_segment():
    """A segment that contains end of one sentence and start of another."""
    from translation.sentence_pipeline import merge_to_sentences

    segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence here."},
        {"start": 3.0, "end": 6.0, "text": "Second one. Third starts"},
        {"start": 6.0, "end": 9.0, "text": "and finishes here."},
    ]
    result = merge_to_sentences(segments)

    # Should produce 3 sentences
    assert len(result) == 3

    # Segment 1 (index 1) is shared between sentence 1 and sentence 2
    sent_0_segs = result[0]["seg_indices"]
    sent_1_segs = result[1]["seg_indices"]
    assert 0 in sent_0_segs
    assert 1 in sent_1_segs or 1 in sent_0_segs

    # Word counts for shared segment should be split correctly
    total_seg1_words = sum(
        s["seg_word_counts"].get(1, 0) for s in result
    )
    assert total_seg1_words == 4  # "Second one. Third starts" = 4 words
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'translation.sentence_pipeline'`

- [ ] **Step 3: Implement merge_to_sentences**

Create `backend/translation/sentence_pipeline.py`:

```python
"""Sentence-aware translation pipeline.

Merges ASR sentence fragments into complete sentences before translation,
then redistributes Chinese text back to original segment timestamps.
"""
import pysbd
from typing import Dict, List, Optional, TypedDict

from . import TranslatedSegment, TranslationEngine


class MergedSentence(TypedDict):
    text: str
    seg_indices: List[int]
    seg_word_counts: Dict[int, int]
    start: float
    end: float


_EN_SEGMENTER = pysbd.Segmenter(language="en", clean=False)


def merge_to_sentences(segments: List[dict]) -> List[MergedSentence]:
    """Merge ASR segment fragments into complete English sentences.

    Uses pySBD to detect sentence boundaries in the concatenated text,
    then maps each sentence back to its source segments.
    """
    if not segments:
        return []

    # Build word-to-segment index
    word_to_seg: List[int] = []
    for seg_idx, seg in enumerate(segments):
        words = seg["text"].split()
        for _ in words:
            word_to_seg.append(seg_idx)

    full_text = " ".join(seg["text"] for seg in segments)
    sentences = _EN_SEGMENTER.segment(full_text)

    result: List[MergedSentence] = []
    word_offset = 0

    for sent in sentences:
        sent_text = sent.strip()
        if not sent_text:
            continue

        sent_words = sent_text.split()
        sent_word_count = len(sent_words)

        seg_indices: List[int] = []
        seg_word_counts: Dict[int, int] = {}

        for j in range(word_offset, min(word_offset + sent_word_count, len(word_to_seg))):
            sid = word_to_seg[j]
            if sid not in seg_indices:
                seg_indices.append(sid)
            seg_word_counts[sid] = seg_word_counts.get(sid, 0) + 1

        if seg_indices:
            result.append(MergedSentence(
                text=sent_text,
                seg_indices=seg_indices,
                seg_word_counts=seg_word_counts,
                start=segments[seg_indices[0]]["start"],
                end=segments[seg_indices[-1]]["end"],
            ))

        word_offset += sent_word_count

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py -v`

Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/sentence_pipeline.py backend/tests/test_sentence_pipeline.py
git commit -m "feat: add merge_to_sentences for sentence boundary detection"
```

---

### Task 3: redistribute_to_segments()

**Files:**
- Modify: `backend/translation/sentence_pipeline.py`
- Modify: `backend/tests/test_sentence_pipeline.py`

- [ ] **Step 1: Write failing tests for redistribute_to_segments**

Add to `backend/tests/test_sentence_pipeline.py`:

```python
def test_redistribute_single_sentence_three_segments():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments

    original_segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 5.0, "text": "the mat and then"},
        {"start": 5.0, "end": 7.0, "text": "went to sleep."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["貓坐在墊子上，然後去睡覺了。"]

    result = redistribute_to_segments(merged, zh_sentences, original_segments)

    assert len(result) == 3
    # All zh_text concatenated should equal the full Chinese sentence
    combined = "".join(r["zh_text"] for r in result)
    assert combined == "貓坐在墊子上，然後去睡覺了。"
    # Timestamps preserved
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 2.0
    assert result[1]["start"] == 2.0
    assert result[1]["end"] == 5.0
    assert result[2]["start"] == 5.0
    assert result[2]["end"] == 7.0
    # en_text preserved
    assert result[0]["en_text"] == "The cat sat on"
    assert result[2]["en_text"] == "went to sleep."


def test_redistribute_prefers_punctuation_break():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments

    original_segments = [
        {"start": 0.0, "end": 3.0, "text": "Hello there my friend"},
        {"start": 3.0, "end": 6.0, "text": "how are you doing today."},
    ]
    merged = merge_to_sentences(original_segments)
    # Chinese with a comma near the split point
    zh_sentences = ["你好啊，我的朋友你今天怎麼樣。"]

    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 2
    # Should break at the comma
    assert result[0]["zh_text"].endswith("，") or "，" in result[0]["zh_text"]


def test_redistribute_shared_segment_merged():
    from translation.sentence_pipeline import merge_to_sentences, redistribute_to_segments

    original_segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence."},
        {"start": 3.0, "end": 6.0, "text": "Second sentence."},
    ]
    merged = merge_to_sentences(original_segments)
    zh_sentences = ["第一句話。", "第二句話。"]

    result = redistribute_to_segments(merged, zh_sentences, original_segments)
    assert len(result) == 2
    assert result[0]["zh_text"] == "第一句話。"
    assert result[1]["zh_text"] == "第二句話。"
    assert result[0]["start"] == 0.0
    assert result[1]["start"] == 3.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py::test_redistribute_single_sentence_three_segments -v`

Expected: FAIL — `ImportError: cannot import name 'redistribute_to_segments'`

- [ ] **Step 3: Implement redistribute_to_segments**

Add to `backend/translation/sentence_pipeline.py` after `merge_to_sentences`:

```python
_ZH_PUNCTUATION = set("。，、！？；：）」』】")


def _find_break_point(text: str, target: int, search_range: int = 3) -> int:
    """Find a natural break point near the target character index.

    Searches +/- search_range characters around target for Chinese punctuation.
    Returns the index AFTER the punctuation character (so the break is after it).
    Falls back to target if no punctuation found.
    """
    best = target
    for offset in range(search_range + 1):
        for candidate in [target + offset, target - offset]:
            if 0 < candidate <= len(text) and text[candidate - 1] in _ZH_PUNCTUATION:
                return candidate
    return best


def redistribute_to_segments(
    merged_sentences: List[MergedSentence],
    zh_sentences: List[str],
    original_segments: List[dict],
) -> List[TranslatedSegment]:
    """Redistribute Chinese translations back to original segment timestamps.

    For each sentence, allocates Chinese characters proportionally based on
    the English word count contributed by each original segment.
    """
    # Collect partial zh_text per original segment index
    seg_parts: Dict[int, List[str]] = {}
    for seg_idx in range(len(original_segments)):
        seg_parts[seg_idx] = []

    for sent_idx, merged in enumerate(merged_sentences):
        zh_text = zh_sentences[sent_idx] if sent_idx < len(zh_sentences) else ""
        total_zh_chars = len(zh_text)
        total_en_words = sum(merged["seg_word_counts"].values())

        if total_en_words == 0 or total_zh_chars == 0:
            for sid in merged["seg_indices"]:
                seg_parts[sid].append("")
            continue

        # Single segment — no splitting needed
        if len(merged["seg_indices"]) == 1:
            seg_parts[merged["seg_indices"][0]].append(zh_text)
            continue

        # Allocate Chinese characters proportionally
        char_offset = 0
        for i, sid in enumerate(merged["seg_indices"]):
            en_words = merged["seg_word_counts"].get(sid, 0)
            proportion = en_words / total_en_words

            if i == len(merged["seg_indices"]) - 1:
                # Last segment gets all remaining characters
                allocated = zh_text[char_offset:]
            else:
                target_end = char_offset + round(total_zh_chars * proportion)
                target_end = min(target_end, total_zh_chars)
                # Try to break at natural Chinese punctuation
                break_at = _find_break_point(zh_text, target_end)
                break_at = max(char_offset, min(break_at, total_zh_chars))
                allocated = zh_text[char_offset:break_at]
                char_offset = break_at

            seg_parts[sid].append(allocated)

    # Build final TranslatedSegment list
    results: List[TranslatedSegment] = []
    for seg_idx, seg in enumerate(original_segments):
        zh_combined = "".join(seg_parts.get(seg_idx, []))
        results.append(TranslatedSegment(
            start=seg["start"],
            end=seg["end"],
            en_text=seg["text"],
            zh_text=zh_combined,
        ))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py -v`

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/sentence_pipeline.py backend/tests/test_sentence_pipeline.py
git commit -m "feat: add redistribute_to_segments for Chinese text re-splitting"
```

---

### Task 4: validate_batch()

**Files:**
- Modify: `backend/translation/sentence_pipeline.py`
- Modify: `backend/tests/test_sentence_pipeline.py`

- [ ] **Step 1: Write failing tests for validate_batch**

Add to `backend/tests/test_sentence_pipeline.py`:

```python
def test_validate_all_valid():
    from translation.sentence_pipeline import validate_batch

    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。"},
        {"start": 2.0, "end": 4.0, "en_text": "World.", "zh_text": "世界。"},
    ]
    assert validate_batch(results) == []


def test_validate_repetition():
    from translation.sentence_pipeline import validate_batch

    results = [
        {"start": 0.0, "end": 1.0, "en_text": "A", "zh_text": "重複"},
        {"start": 1.0, "end": 2.0, "en_text": "B", "zh_text": "重複"},
        {"start": 2.0, "end": 3.0, "en_text": "C", "zh_text": "重複"},
        {"start": 3.0, "end": 4.0, "en_text": "D", "zh_text": "正常"},
    ]
    bad = validate_batch(results)
    assert 0 in bad
    assert 1 in bad
    assert 2 in bad
    assert 3 not in bad


def test_validate_missing():
    from translation.sentence_pipeline import validate_batch

    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hello.", "zh_text": "你好。"},
        {"start": 2.0, "end": 4.0, "en_text": "World.", "zh_text": "[TRANSLATION MISSING] World."},
    ]
    bad = validate_batch(results)
    assert 1 in bad
    assert 0 not in bad


def test_validate_too_long():
    from translation.sentence_pipeline import validate_batch

    long_zh = "一" * 33  # 33 chars > 32 threshold
    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Short.", "zh_text": long_zh},
    ]
    bad = validate_batch(results)
    assert 0 in bad


def test_validate_hallucination():
    from translation.sentence_pipeline import validate_batch

    results = [
        {"start": 0.0, "end": 2.0, "en_text": "Hi", "zh_text": "一二三四五六七"},  # 7 > 2*3=6
    ]
    bad = validate_batch(results)
    assert 0 in bad
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py::test_validate_all_valid -v`

Expected: FAIL — `ImportError: cannot import name 'validate_batch'`

- [ ] **Step 3: Implement validate_batch**

Add to `backend/translation/sentence_pipeline.py`:

```python
def validate_batch(results: List[dict]) -> List[int]:
    """Check translated segments for quality issues.

    Returns list of problematic segment indices (empty = all valid).
    Checks: repetition (>=3 consecutive identical), missing translations,
    too long (>32 Chinese chars), hallucination (zh > en*3 length).
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

        if len(zh) > 32:
            if i not in bad_indices:
                bad_indices.append(i)

        if len(en) > 0 and len(zh) > len(en) * 3:
            if i not in bad_indices:
                bad_indices.append(i)

    return sorted(bad_indices)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py -v`

Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/sentence_pipeline.py backend/tests/test_sentence_pipeline.py
git commit -m "feat: add validate_batch for translation quality checks"
```

---

### Task 5: translate_with_sentences() orchestrator

**Files:**
- Modify: `backend/translation/sentence_pipeline.py`
- Modify: `backend/tests/test_sentence_pipeline.py`

- [ ] **Step 1: Write failing tests for translate_with_sentences**

Add to `backend/tests/test_sentence_pipeline.py`:

```python
def test_translate_with_sentences_basic():
    """Full pipeline with MockTranslationEngine."""
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine

    engine = MockTranslationEngine({})
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The cat sat on"},
        {"start": 2.0, "end": 4.0, "text": "the mat."},
        {"start": 4.0, "end": 6.0, "text": "The dog ran."},
    ]

    result = translate_with_sentences(engine, segments)
    assert len(result) == 3
    # MockEngine returns "[EN→ZH] text" format — each segment should have zh_text
    for r in result:
        assert r["zh_text"] != ""
        assert r["en_text"] != ""
    # Timestamps preserved
    assert result[0]["start"] == 0.0
    assert result[2]["end"] == 6.0


def test_translate_with_sentences_empty():
    from translation.sentence_pipeline import translate_with_sentences
    from translation.mock_engine import MockTranslationEngine

    engine = MockTranslationEngine({})
    result = translate_with_sentences(engine, [])
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py::test_translate_with_sentences_basic -v`

Expected: FAIL — `ImportError: cannot import name 'translate_with_sentences'`

- [ ] **Step 3: Implement translate_with_sentences**

Add to `backend/translation/sentence_pipeline.py`:

```python
def translate_with_sentences(
    engine: TranslationEngine,
    segments: List[dict],
    glossary: Optional[List[dict]] = None,
    style: str = "formal",
    batch_size: Optional[int] = None,
    temperature: Optional[float] = None,
) -> List[TranslatedSegment]:
    """Orchestrate sentence-aware translation pipeline.

    1. Merge ASR fragments into complete sentences
    2. Translate complete sentences via the engine
    3. Redistribute Chinese text back to original segment timestamps
    4. Validate and retry problematic translations
    """
    if not segments:
        return []

    # Phase 1: Merge fragments into sentences
    merged = merge_to_sentences(segments)
    if not merged:
        return engine.translate(
            segments, glossary=glossary, style=style,
            batch_size=batch_size, temperature=temperature,
        )

    # Phase 2: Translate complete sentences
    sentence_segments = [
        {"start": m["start"], "end": m["end"], "text": m["text"]}
        for m in merged
    ]
    translated_sentences = engine.translate(
        sentence_segments, glossary=glossary, style=style,
        batch_size=batch_size, temperature=temperature,
    )
    zh_sentences = [t["zh_text"] for t in translated_sentences]

    # Phase 3: Redistribute to original segments
    results = redistribute_to_segments(merged, zh_sentences, segments)

    # Phase 4: Validate and retry
    bad_indices = validate_batch(results)
    if not bad_indices:
        return results

    # Find which merged sentences need retry
    retry_sent_indices = set()
    for bad_idx in bad_indices:
        for sent_idx, m in enumerate(merged):
            if bad_idx in m["seg_indices"]:
                retry_sent_indices.add(sent_idx)

    # Retry failed sentences one at a time
    for sent_idx in retry_sent_indices:
        retry_segments = [sentence_segments[sent_idx]]
        retry_result = engine.translate(
            retry_segments, glossary=glossary, style=style,
            batch_size=1, temperature=temperature,
        )
        if retry_result:
            zh_sentences[sent_idx] = retry_result[0]["zh_text"]

    # Re-redistribute with updated translations
    results = redistribute_to_segments(merged, zh_sentences, segments)

    # Final validation — mark remaining failures
    still_bad = validate_batch(results)
    for idx in still_bad:
        zh = results[idx]["zh_text"]
        if not zh.startswith("[NEEDS REVIEW]"):
            results[idx] = TranslatedSegment(
                start=results[idx]["start"],
                end=results[idx]["end"],
                en_text=results[idx]["en_text"],
                zh_text=f"[NEEDS REVIEW] {zh}",
            )

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py -v`

Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/translation/sentence_pipeline.py backend/tests/test_sentence_pipeline.py
git commit -m "feat: add translate_with_sentences orchestrator with retry logic"
```

---

### Task 6: Improve OllamaTranslationEngine prompts

**Files:**
- Modify: `backend/translation/ollama_engine.py`

- [ ] **Step 1: Write failing test for improved prompt**

Add to `backend/tests/test_sentence_pipeline.py`:

```python
def test_ollama_prompt_includes_sentence_instruction():
    from translation.ollama_engine import SYSTEM_PROMPT_FORMAL, SYSTEM_PROMPT_CANTONESE

    assert "COMPLETE sentence" in SYSTEM_PROMPT_FORMAL
    assert "Do NOT merge or split" in SYSTEM_PROMPT_FORMAL
    assert "COMPLETE sentence" in SYSTEM_PROMPT_CANTONESE
    assert "Do NOT merge or split" in SYSTEM_PROMPT_CANTONESE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/test_sentence_pipeline.py::test_ollama_prompt_includes_sentence_instruction -v`

Expected: FAIL — `AssertionError`

- [ ] **Step 3: Update the system prompts**

In `backend/translation/ollama_engine.py`, replace the two prompt constants:

```python
SYSTEM_PROMPT_FORMAL = (
    "You are a professional translator. Translate the following English text "
    "into formal Traditional Chinese (繁體中文書面語). Maintain the meaning and tone. "
    "Each numbered line is a COMPLETE sentence. Translate each into exactly one "
    "corresponding Traditional Chinese line. Do NOT merge or split lines. "
    "Output ONLY the translations, numbered to match the input."
)

SYSTEM_PROMPT_CANTONESE = (
    "You are a professional translator. Translate the following English text "
    "into Cantonese Traditional Chinese (繁體中文粵語口語). Use natural spoken "
    "Cantonese expressions. Each numbered line is a COMPLETE sentence. Translate "
    "each into exactly one corresponding Traditional Chinese line. Do NOT merge "
    "or split lines. Output ONLY the translations, numbered to match the input."
)
```

- [ ] **Step 4: Run all tests to verify**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/ -v --tb=short`

Expected: All tests PASS (131 existing + 15 new = 146)

- [ ] **Step 5: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_sentence_pipeline.py
git commit -m "feat: improve translation prompts for sentence-level accuracy"
```

---

### Task 7: Integrate pipeline into app.py

**Files:**
- Modify: `backend/app.py:665-668`
- Modify: `backend/app.py:1088-1091`

- [ ] **Step 1: Update api_translate_file()**

In `backend/app.py`, find the line (around line 665):

```python
        translated = engine.translate(
            asr_segments, glossary=glossary_entries, style=style,
            batch_size=trans_params["batch_size"],
            temperature=trans_params["temperature"],
        )
```

Replace with:

```python
        from translation.sentence_pipeline import translate_with_sentences
        translated = translate_with_sentences(
            engine, asr_segments, glossary=glossary_entries, style=style,
            batch_size=trans_params["batch_size"],
            temperature=trans_params["temperature"],
        )
```

- [ ] **Step 2: Update _auto_translate()**

In `backend/app.py`, find the line (around line 1088):

```python
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
            )
```

Replace with:

```python
            from translation.sentence_pipeline import translate_with_sentences
            translated = translate_with_sentences(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
            )
```

- [ ] **Step 3: Run all tests**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/ -v --tb=short`

Expected: All 146 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "feat: integrate sentence-aware pipeline into translation endpoints"
```

---

### Task 8: Manual verification with real video

**Files:** None (manual test only)

- [ ] **Step 1: Restart backend**

```bash
# Kill existing backend
lsof -iTCP:5001 -sTCP:LISTEN -P -n | awk 'NR>1{print $2}' | xargs kill -9 2>/dev/null
sleep 2

# Start with new code
cd backend && nohup ../backend/venv/bin/python app.py > /tmp/whisper-backend.log 2>&1 &
sleep 5
curl -s http://localhost:5001/api/health | python3 -m json.tool
```

Expected: `{"status": "ok", ...}`

- [ ] **Step 2: Re-translate FIFA video**

```bash
# Get file ID
FILE_ID=$(curl -s http://localhost:5001/api/files | python3 -c "import json,sys; files=json.load(sys.stdin)['files']; print(next(f['id'] for f in files if 'FIFA' in f['original_name']))")

# Trigger re-translation
curl -s -X POST http://localhost:5001/api/translate \
  -H 'Content-Type: application/json' \
  -d "{\"file_id\": \"$FILE_ID\"}" | python3 -m json.tool | head -5
```

Expected: `{"file_id": "...", "segment_count": 49, ...}`

- [ ] **Step 3: Check segments 40-48 for repetition**

```bash
curl -s http://localhost:5001/api/files/$FILE_ID/translations | python3 -c "
import json, sys
data = json.load(sys.stdin)
trans = data.get('translations', [])
for i, t in enumerate(trans[38:]):
    idx = i + 38
    print(f'{idx}: {t[\"zh_text\"][:50]}')
"
```

Expected: Each line should have DIFFERENT Chinese text (no repetition).

- [ ] **Step 4: Verify in browser**

Open `http://localhost:8080` in browser. Select the FIFA video. Expand transcript. Scroll to the bottom segments. Verify Chinese translations are unique and meaningful.

- [ ] **Step 5: Run full test suite one final time**

Run: `cd backend && ../backend/venv/bin/python -m pytest tests/ -v --tb=short`

Expected: All 146 tests PASS
