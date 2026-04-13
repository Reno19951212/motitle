# Translation Quality Improvement — Design Spec

**Date:** 2026-04-13
**Branch:** ImproveTranslationQuality
**Status:** Approved

---

## Problem Statement

Current translation pipeline has three quality issues:

1. **Simplified Chinese leakage** — system prompt does not explicitly forbid simplified characters; Ollama models occasionally output 简体字.
2. **Unnatural subtitle length** — no per-sentence character limit enforced; outputs often exceed broadcast standards.
3. **No inter-batch context** — each batch is translated independently; the model has no knowledge of the preceding sentences, causing topic inconsistency across batch boundaries.

Post-processing is partially implemented in `sentence_pipeline.py` (`validate_batch`) but that pipeline is marked experimental and not active. The live `ollama_engine.py` path does no validation or correction.

---

## Goals

| Goal | Mechanism |
|------|-----------|
| Output formal Traditional Chinese only (RTHK news style) | Prompt rewrite |
| Zero simplified Chinese in output | opencc `s2twp` post-conversion |
| Each subtitle ≤ 16 Chinese characters | Prompt instruction + length flag in post-processor |
| Inter-batch topic coherence | Sliding window context (default 3 previous pairs) |
| Validate and flag bad translations | Integrate `validate_batch` into shared post-processor |

---

## Architecture

### Approach: Separate PostProcessor + Enhanced Engine

```
OllamaTranslationEngine.translate()
    │
    ├── for each batch:
    │     ├── build sliding window context (last N translated pairs)
    │     ├── _build_system_prompt()   ← new RTHK-style prompt
    │     ├── _build_user_message()    ← prepend context block
    │     └── _call_ollama()
    │
    └── PostProcessor.process(all_results)
          ├── Step 1: opencc s2twp (simplified → traditional)
          ├── Step 2: length flag  (zh_text > 16 chars → prepend [LONG])
          └── Step 3: validate_batch (repetition, missing, hallucination)
```

---

## Section 1: Prompt Engineering

### New `SYSTEM_PROMPT_FORMAL`

```
You are a professional broadcast subtitle translator for Hong Kong news (RTHK style).

Rules:
1. Translate English into formal Traditional Chinese (繁體中文書面語).
2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.
3. Each translation must be ≤16 Chinese characters. Be concise.
4. Use neutral, journalistic tone. No colloquialisms.
5. Output ONLY numbered translations. No explanations, no brackets, no notes.

Example:
1. The typhoon is approaching Hong Kong.
→ 1. 颱風正逼近香港。
```

### Glossary injection (unchanged)

Appended to system prompt when glossary entries exist:

```
IMPORTANT — Use these specific translations for the following terms:
- "Legislative Council" → "立法會"
```

### `SYSTEM_PROMPT_CANTONESE`

Similar rewrite — add Traditional Chinese enforcement and ≤16 char rule, keep Cantonese tone instruction.

---

## Section 2: Sliding Window Context

### Parameter

`context_window: int = 3` — number of preceding translated pairs to include as context. Range: 0–10. 0 disables the feature (backward compatible).

Exposed via `get_params_schema()` as a new optional integer field. Profile JSONs do not need updating (defaults to 3 if absent).

### User Message Format

```
[Context - previous translations for reference:]
1. The government announced new measures. → 政府宣布新措施。
2. Officials confirmed the decision today. → 官員今日確認決定。

[Translate the following:]
1. The policy will take effect next month.
2. Citizens are urged to stay informed.
```

Context is placed in the **user message**, not the system prompt, to avoid polluting the instruction layer. The model is not expected to re-translate the context lines — they are reference only.

### Implementation

In `OllamaTranslationEngine.translate()`, maintain a rolling list `context_pairs: list[tuple[str, str]]` (en, zh). After each batch succeeds, append its results to the list and trim to last `context_window` pairs. Pass `context_pairs` to `_build_user_message()`.

First batch: `context_pairs` is empty — no context block rendered.

---

## Section 3: Post-processor (`translation/post_processor.py`)

### New module

```python
class TranslationPostProcessor:
    def __init__(self, max_chars: int = 16):
        self._converter = opencc.OpenCC('s2twp')
        self._max_chars = max_chars

    def process(self, results: List[TranslatedSegment]) -> List[TranslatedSegment]:
        results = self._convert_to_traditional(results)
        results = self._flag_long_segments(results)
        bad_indices = validate_batch(results)
        # mark still-bad segments with [NEEDS REVIEW]
        return results
```

### Step 1 — opencc conversion

Dependency: `opencc-python-reimplemented` (pure Python, no system install required).

Config: `s2twp` — Simplified → Traditional Taiwan Standard, including phrase-level vocabulary mapping (not just character substitution). This correctly handles cases like 软件→軟體, 信息→資訊.

Applied to every `zh_text` field unconditionally (idempotent on already-traditional text).

### Step 2 — Length flag

Segments where `len(zh_text) > max_chars` get `[LONG]` prepended. Original text is preserved — no truncation. Flagged segments are highlighted in the proof-reading editor for human review.

`max_chars` defaults to 16. Configurable per engine config (not exposed in profile UI for now — keep scope small).

### Step 3 — validate_batch integration

`validate_batch()` moved from `sentence_pipeline.py` to `post_processor.py`. `sentence_pipeline.py` imports it from `post_processor` to maintain backward compatibility.

Checks:
- 3+ consecutive identical `zh_text` → repetition flag
- `[TRANSLATION MISSING]` in output → missing flag
- `len(zh_text) > len(en_text) * 3` → hallucination flag

Bad segments get `[NEEDS REVIEW]` prefix.

### Integration point

In `OllamaTranslationEngine.translate()`, after all batches are collected:

```python
processor = TranslationPostProcessor(max_chars=16)
return processor.process(all_translated)
```

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `translation/ollama_engine.py` | Modified | New prompts, sliding window, PostProcessor call |
| `translation/post_processor.py` | **New** | opencc, length flag, validate_batch |
| `translation/sentence_pipeline.py` | Modified | Import `validate_batch` from `post_processor` |
| `backend/requirements.txt` | Modified | Add `opencc-python-reimplemented` |
| `tests/test_post_processor.py` | **New** | Unit tests for all PostProcessor steps |
| `tests/test_translation.py` | Modified | Tests for sliding window, new prompts |

`app.py`, frontend, profile JSONs — **no changes required**.

---

## Testing Plan

### `test_post_processor.py`

- `test_opencc_converts_simplified` — simplified input → traditional output
- `test_opencc_idempotent_on_traditional` — already-traditional input unchanged
- `test_length_flag_applied` — zh_text > 16 chars gets `[LONG]` prefix
- `test_length_flag_not_applied` — zh_text ≤ 16 chars unchanged
- `test_validate_batch_repetition` — 3 identical consecutive → flagged
- `test_validate_batch_missing` — `[TRANSLATION MISSING]` → flagged
- `test_validate_batch_hallucination` — zh > en*3 length → flagged
- `test_process_pipeline_ordering` — opencc runs before length check

### `test_translation.py` additions

- `test_sliding_window_context_in_user_message` — context block appears in user message after first batch
- `test_sliding_window_zero_disables_context` — `context_window=0` produces no context block
- `test_system_prompt_contains_traditional_chinese_rule` — new prompt includes Traditional Chinese instruction
- `test_system_prompt_contains_char_limit` — new prompt includes ≤16 char rule

---

## Out of Scope

- Sentence-aware merge/redistribute (`sentence_pipeline.py` main flow) — not activated
- Frontend UI changes for `[LONG]` / `[NEEDS REVIEW]` visual highlighting — separate task
- Automatic retry on `[LONG]` segments — post-processing only flags, human reviews
- `max_chars` exposed in profile UI — deferred
