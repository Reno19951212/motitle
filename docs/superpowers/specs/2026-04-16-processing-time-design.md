# Processing Time Visibility + Parallel Batch Translation — Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Branch:** dev (implement on new branch)

---

## Problem

The pipeline (ASR → Translation) has no elapsed-time visibility for the user, and translation runs in fully sequential batches. For local Ollama this is acceptable, but for cloud models it leaves significant throughput on the table. Users also cannot verify whether the <15-minute SLA is being met.

---

## Goal

1. Surface per-stage elapsed time in the UI so users can see where time is spent.
2. Allow parallel batch translation to reduce total translation time, especially for cloud models.
3. Document the setup in README.md.

No new backend routes required. All changes use existing WebSocket events (extended) plus one new event.

---

## Scope

**In scope:**
- Elapsed time tracking for ASR and translation stages
- `elapsed_seconds` added to existing `translation_progress` WebSocket event
- New `pipeline_timing` WebSocket event emitted on pipeline completion
- Frontend elapsed-time counter during translation and summary toast on completion
- `parallel_batches` parameter in `OllamaTranslationEngine.translate()`
- `parallel_batches` field in Profile `translation` block (optional, 1–8)
- Profile form UI field with contextual hint
- README.md performance-tuning section

**Out of scope:**
- Parallelising ASR (already streams per-segment)
- Mock/stub translation engine parallelism (mock is instant)
- `index.html` transcript panel timing (transcription already has ETA)
- Undo/redo or segment-level editing

---

## Architecture

### Files Changed

| File | Change |
|------|--------|
| `backend/app.py` | Store `asr_seconds` in file registry; add `elapsed_seconds` to `translation_progress` emit; emit `pipeline_timing` on completion |
| `backend/translation/ollama_engine.py` | `parallel_batches` param + `ThreadPoolExecutor` path + thread-safe progress counter |
| `backend/profiles.py` | Validate `parallel_batches` in `_validate_translation()` |
| `frontend/index.html` | Elapsed counter in translation progress text; `pipeline_timing` toast |
| `README.md` | 效能調校 section: `parallel_batches` usage + `OLLAMA_NUM_PARALLEL` setup |

---

## Feature Details

### Part 1 — Timing Tracking

#### Backend (`app.py`)

**ASR timing:**
- `transcribe_with_segments()` already has `transcribe_start_time = time.time()` (line 389).
- On transcription complete, compute `asr_seconds = time.time() - transcribe_start_time` and store in `file_registry[file_id]['asr_seconds']`.

**Translation timing:**
- `_auto_translate()` records `translation_start = time.time()` before calling the engine.
- The existing `translation_progress` callback (which emits `{'completed': n, 'total': m, 'percent': p}`) is extended to also include `elapsed_seconds: round(time.time() - translation_start, 1)`.
- On translation complete, emit new event:

```python
socketio.emit('pipeline_timing', {
    'asr_seconds': file_registry[file_id].get('asr_seconds'),
    'translation_seconds': round(time.time() - translation_start, 1),
    'total_seconds': round(
        time.time() - translation_start
        + (file_registry[file_id].get('asr_seconds') or 0),
        1,
    ),
}, room=sid)
```

#### Frontend (`index.html`)

**During translation:**
- `translation_progress` handler already updates a progress label. Extend it to also append elapsed:
  - Before: `翻譯中... 43%`
  - After: `翻譯中... 43% — 已用 12s`

**On completion:**
- Listen for `pipeline_timing` event.
- Show toast (re-use existing `showToast`):
  - `ASR: 8s ｜ 翻譯: 34s ｜ 總計: 42s`
- If `asr_seconds` is null (translation triggered manually without fresh ASR), omit ASR line: `翻譯: 34s`

---

### Part 2 — Parallel Batch Translation

#### `OllamaTranslationEngine.translate()` (`ollama_engine.py`)

New parameter: `parallel_batches: int = 1`

**When `parallel_batches == 1` (default):**
- Behaviour identical to current implementation. No code path changes.

**When `parallel_batches > 1`:**
- `context_window` is forced to `0` (cannot maintain cross-batch context when order is non-deterministic).
- Batches are submitted concurrently using `ThreadPoolExecutor(max_workers=parallel_batches)`.
- Progress counter uses `threading.Lock` to accumulate completed segment count safely.
- Results are collected in submission order (futures list preserves order).
- If any batch raises an exception, the executor shuts down and the exception propagates (existing error handling in `app.py` catches it).

```python
if parallel_batches > 1:
    effective_context_window = 0  # disable: can't maintain order
    lock = threading.Lock()
    completed_count = [0]

    def run_batch(batch_segments):
        result = self._translate_batch(batch_segments, ...)
        with lock:
            completed_count[0] += len(result)
            if progress_callback:
                progress_callback(completed_count[0], total)
        return result

    with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
        futures = [executor.submit(run_batch, batch) for batch in batches]
        all_translated = []
        for future in futures:
            all_translated.extend(future.result())
```

#### Profile Schema (`profiles.py`)

`_validate_translation()` extended:

```python
parallel_batches = translation.get('parallel_batches')
if parallel_batches is not None:
    if not isinstance(parallel_batches, int) or not (1 <= parallel_batches <= 8):
        errors.append("translation.parallel_batches must be an integer between 1 and 8")
```

Absent field → treated as 1 (no change to existing profiles).

#### Frontend Profile Form (`index.html`)

Translation settings section gains a new row:

```
並發批次 (parallel_batches):  [_1_]  (1–8)
本地模型建議 1-2（需設定 OLLAMA_NUM_PARALLEL≥N）；雲端模型建議 3-5
```

Field type: integer input, min=1, max=8, step=1. Omitted from PATCH payload when empty (same pattern as other optional translation fields).

---

### Part 3 — README.md

New section added (繁體中文，after 翻譯引擎 section):

```markdown
## 效能調校

### parallel_batches — 並發批次翻譯

Profile 的翻譯設定支援 `parallel_batches`（預設 1）。設定後，翻譯引擎會同時發送多個 batch 請求，縮短總翻譯時間。

| 使用情境 | 建議值 |
|---------|--------|
| 本地 Ollama（3B/7B 模型） | 1–2 |
| 雲端模型（qwen3.5-397b-cloud 等） | 3–5 |

> **注意：** 使用本地 Ollama 時，需同時設定 `OLLAMA_NUM_PARALLEL` 環境變量，數值須 ≥ `parallel_batches`：
> ```bash
> OLLAMA_NUM_PARALLEL=2 ollama serve
> ```
> 16GB RAM 的 Mac 跑 7B 模型時，建議不超過 2，以免記憶體不足。
```

---

## WebSocket Events (Extended)

| Event | New Fields | When |
|-------|-----------|------|
| `translation_progress` | `elapsed_seconds: float` | Each batch completes |
| `pipeline_timing` (new) | `asr_seconds: float\|null, translation_seconds: float, total_seconds: float` | Translation completes |

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| `parallel_batches` > 1, one batch fails | Executor raises exception; existing `_auto_translate` error handler catches, emits `file_updated` with `translation_status='failed'` |
| `asr_seconds` absent (manual translate) | `pipeline_timing` sets `asr_seconds: null`; frontend omits ASR line in toast |
| Ollama returns 503 (queue full) | Existing retry logic in `_call_ollama` handles; not affected by parallel path |

---

## Testing

**Backend unit tests (no real Ollama needed — mock `_call_ollama`):**
1. `parallel_batches=2` produces same segment count and order as `parallel_batches=1`
2. `parallel_batches=2` forces `context_window=0`
3. Progress callback called correct number of times under parallel path
4. `parallel_batches` validation: rejects 0, 9, non-int; accepts 1–8; accepts absent
5. `translation_progress` events include `elapsed_seconds` field
6. `pipeline_timing` event emitted with correct structure after translation completes
7. `asr_seconds` stored in file registry after transcription

**Frontend smoke tests:**
1. Translation progress label shows `已用 Xs` suffix
2. `pipeline_timing` toast appears with correct stage breakdown
3. Profile form: `parallel_batches` field saves and loads correctly
4. Toast omits ASR line when `asr_seconds` is null
