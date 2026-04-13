# Translation Missing Retry — Design Spec

**Date:** 2026-04-13
**Branch:** FixBug
**Status:** Approved

---

## Problem Statement

`_parse_response()` emits `[TRANSLATION MISSING] <en_text>` when the Ollama model returns fewer translations than segments in the batch. This happens when:

1. The model silently skips a segment (non-numbered output gap).
2. The model produces fewer numbered lines than the batch size.

Currently these segments fall through to `validate_batch()` which flags them as `[NEEDS REVIEW]`, but there is no automatic recovery. The human reviewer must manually re-translate every missing segment.

---

## Goals

| Goal | Mechanism |
|------|-----------|
| Automatically recover missing segments without human intervention | Per-batch retry in `translate()` |
| Retry only the missing segments, not the full batch | `_retry_missing()` takes only missing segs |
| Preserve inter-batch context during retry | Pass `context_pairs` to `_retry_missing()` |
| Limit cost: maximum 1 retry attempt | Single retry call per batch |
| Remaining missing after retry → flagged for human | PostProcessor `validate_batch` adds `[NEEDS REVIEW]` |

---

## Architecture

```
translate()
    ├── for each batch:
    │     ├── _translate_batch()           → translated_batch
    │     ├── check [TRANSLATION MISSING]
    │     │     └── if missing:
    │     │           _retry_missing(missing_segs, context_pairs)
    │     │           merge retried results back into translated_batch
    │     └── update context_pairs
    └── PostProcessor.process(all_translated)
          └── validate_batch flags any remaining [TRANSLATION MISSING] as [NEEDS REVIEW]
```

`_retry_missing()` has a single responsibility: re-translate a list of segments by calling `_translate_batch()`. No new logic — no retry counter, no exponential back-off.

---

## Detailed Implementation

### `translate()` — retry block (added inside the batch loop)

```python
missing_indices = [
    j for j, r in enumerate(translated_batch)
    if "[TRANSLATION MISSING]" in r.get("zh_text", "")
]
if missing_indices:
    missing_segs = [batch[j] for j in missing_indices]
    retried = self._retry_missing(missing_segs, glossary, style, effective_temp, context_pairs)
    translated_batch = [
        retried.pop(0) if j in missing_indices else r
        for j, r in enumerate(translated_batch)
    ]
```

- Uses index list + list comprehension to splice retried results back into position.
- `retried.pop(0)` consumes retried segments in order — safe because `missing_indices` is sorted.
- Immutable pattern: assigns new list rather than mutating `translated_batch` in place.

### New `_retry_missing()` method

```python
def _retry_missing(
    self,
    segments: List[dict],
    glossary: List[dict],
    style: str,
    temperature: float,
    context_pairs: list,
) -> List[TranslatedSegment]:
    return self._translate_batch(segments, glossary, style, temperature, context_pairs)
```

Thin delegation only. All prompt building, API call, and parsing logic remain in `_translate_batch()` and `_parse_response()`.

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `translation/ollama_engine.py` | Modified | Add retry block in `translate()`; add `_retry_missing()` method |
| `tests/test_translation.py` | Modified | 4 new tests |

---

## Testing Plan

All 4 tests go in `tests/test_translation.py`:

1. **`test_retry_called_for_missing_segments`** — When `_translate_batch` returns a segment with `[TRANSLATION MISSING]`, verify `_retry_missing` is called with that segment.

2. **`test_retry_success_replaces_missing`** — When retry succeeds (returns a real translation), verify the missing entry in the final output is replaced.

3. **`test_retry_failure_keeps_missing`** — When retry also fails (still `[TRANSLATION MISSING]`), verify the placeholder is preserved for PostProcessor to flag.

4. **`test_no_retry_when_no_missing`** — When all segments translate successfully, verify `_retry_missing` is never called.

---

## Out of Scope

- Multiple retry attempts (exponential back-off) — one retry is sufficient; further retries indicate a systemic prompt issue.
- Retry with modified prompt — this would complicate the design without clear benefit at this stage.
- Frontend visibility of retry attempts — internal engine behavior, not user-facing.
