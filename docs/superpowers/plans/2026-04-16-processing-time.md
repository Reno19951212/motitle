# Processing Time Visibility + Parallel Batch Translation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface per-stage elapsed time in the UI and enable parallel batch translation to reduce total pipeline time, especially for cloud models.

**Architecture:** `parallel_batches` validation added to `profiles.py`; `OllamaTranslationEngine.translate()` gains a `ThreadPoolExecutor` path when `parallel_batches > 1`; `app.py` tracks and emits timing data via extended `translation_progress` and new `pipeline_timing` events; `index.html` consumes both events for live elapsed display and a completion toast.

**Tech Stack:** Python 3.9, Flask-SocketIO, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, Vanilla JS

---

## File Map

| File | Change |
|------|--------|
| `backend/profiles.py` | Add `parallel_batches` validation in `_validate_translation()` |
| `backend/translation/__init__.py` | Add `parallel_batches: int = 1` to ABC `translate()` signature |
| `backend/translation/mock_engine.py` | Add `parallel_batches: int = 1` to accept and ignore |
| `backend/translation/ollama_engine.py` | `ThreadPoolExecutor` parallel path + `threading` import |
| `backend/app.py` | `asr_seconds` in registry; `elapsed_seconds` in `translation_progress`; `pipeline_timing` event; pass `parallel_batches` to engine |
| `frontend/index.html` | Elapsed counter in translation label; `pipeline_timing` toast; `parallel_batches` profile form field |
| `README.md` | 效能調校 section |

---

### Task 1: `parallel_batches` Profile Validation

**Files:**
- Modify: `backend/profiles.py` — `_validate_translation()` at line 302
- Test: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_profiles.py` and add at the end:

```python
# ===== parallel_batches validation =====

def _make_valid_data():
    return {
        "name": "Test",
        "asr": {"engine": "whisper", "language": "en"},
        "translation": {"engine": "mock"},
    }


def test_parallel_batches_absent_is_valid(tmp_path):
    """parallel_batches is optional — absent profile must validate cleanly."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    errors = pm.validate(_make_valid_data())
    assert errors == []


def test_parallel_batches_valid_range(tmp_path):
    """parallel_batches 1–8 are all valid."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    for n in [1, 2, 4, 8]:
        data = _make_valid_data()
        data["translation"]["parallel_batches"] = n
        assert pm.validate(data) == [], f"Expected no errors for parallel_batches={n}"


def test_parallel_batches_zero_invalid(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    data = _make_valid_data()
    data["translation"]["parallel_batches"] = 0
    errors = pm.validate(data)
    assert any("parallel_batches" in e for e in errors)


def test_parallel_batches_nine_invalid(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    data = _make_valid_data()
    data["translation"]["parallel_batches"] = 9
    errors = pm.validate(data)
    assert any("parallel_batches" in e for e in errors)


def test_parallel_batches_non_int_invalid(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    data = _make_valid_data()
    data["translation"]["parallel_batches"] = "2"
    errors = pm.validate(data)
    assert any("parallel_batches" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_profiles.py::test_parallel_batches_zero_invalid tests/test_profiles.py::test_parallel_batches_nine_invalid tests/test_profiles.py::test_parallel_batches_non_int_invalid -v
```

Expected: FAIL — `_validate_translation` does not yet check `parallel_batches`.

- [ ] **Step 3: Implement validation**

In `backend/profiles.py`, replace `_validate_translation()` (lines 302–314):

```python
def _validate_translation(translation: dict) -> list:
    errors = []

    engine = translation.get("engine")
    if not engine:
        errors.append("translation.engine is required")
    elif engine not in VALID_TRANSLATION_ENGINES:
        errors.append(
            f"translation.engine '{engine}' is not valid; "
            f"must be one of {sorted(VALID_TRANSLATION_ENGINES)}"
        )

    parallel_batches = translation.get("parallel_batches")
    if parallel_batches is not None:
        if not isinstance(parallel_batches, int) or not (1 <= parallel_batches <= 8):
            errors.append(
                "translation.parallel_batches must be an integer between 1 and 8"
            )

    return errors
```

- [ ] **Step 4: Run all new tests and full suite**

```bash
pytest tests/test_profiles.py -v
pytest tests/ -q
```

Expected: all new tests PASS; 292 tests total PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/profiles.py backend/tests/test_profiles.py
git commit -m "feat: validate parallel_batches in translation profile block"
```

---

### Task 2: Engine ABC + Mock Accept `parallel_batches`

**Files:**
- Modify: `backend/translation/__init__.py` — `TranslationEngine.translate()` at line 17
- Modify: `backend/translation/mock_engine.py` — `MockTranslationEngine.translate()`

No new tests needed — the full test suite passing after this change is the verification.

- [ ] **Step 1: Update ABC signature**

In `backend/translation/__init__.py`, add `parallel_batches: int = 1` to the abstract `translate()` method. The current signature (lines 17–27) becomes:

```python
    @abstractmethod
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
        progress_callback: Optional[ProgressCallback] = None,
        parallel_batches: int = 1,
    ) -> List[TranslatedSegment]:
```

- [ ] **Step 2: Update MockTranslationEngine signature**

In `backend/translation/mock_engine.py`, add `parallel_batches: int = 1` to the `translate()` method signature (after `progress_callback`). The mock body is unchanged — it ignores the parameter:

```python
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
        progress_callback=None,
        parallel_batches: int = 1,
    ) -> List[TranslatedSegment]:
```

- [ ] **Step 3: Run full suite to verify nothing is broken**

```bash
pytest tests/ -q
```

Expected: 292 PASS (same as before).

- [ ] **Step 4: Commit**

```bash
git add backend/translation/__init__.py backend/translation/mock_engine.py
git commit -m "feat: add parallel_batches param to TranslationEngine ABC and MockEngine"
```

---

### Task 3: Parallel Batch Implementation in OllamaTranslationEngine

**Files:**
- Modify: `backend/translation/ollama_engine.py`
- Test: `backend/tests/test_translation.py`

- [ ] **Step 1: Write the failing tests**

Add at the end of `backend/tests/test_translation.py`:

```python
# ===== parallel_batches =====

def _make_fake_call_ollama(responses):
    """Return a side-effect function that pops from responses list in order."""
    calls = list(responses)
    def fake_call(prompt, system_prompt, temperature):
        return calls.pop(0) if calls else ""
    return fake_call


def test_parallel_batches_returns_same_segment_count(monkeypatch):
    """parallel_batches=2 must return the same number of segments as parallel_batches=1."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"segment {i}"}
        for i in range(6)
    ]

    # Each batch of 3 needs one Ollama call returning 3 numbered translations
    def fake_call(prompt, system_prompt, temperature):
        # Count how many numbered items the prompt contains and echo them back
        import re
        nums = re.findall(r"^\d+\.", prompt, re.MULTILINE)
        lines = [f"{n[:-1]}. 翻譯 {n[:-1]}" for n in nums]
        return "\n".join(lines)

    engine = OllamaTranslationEngine({"engine": "mock-ollama"})
    monkeypatch.setattr(engine, "_call_ollama", fake_call)

    seq_result = engine.translate(segments, batch_size=3, parallel_batches=1)
    par_result = engine.translate(segments, batch_size=3, parallel_batches=2)

    assert len(par_result) == len(seq_result) == 6


def test_parallel_batches_disables_context_window(monkeypatch):
    """When parallel_batches > 1, _translate_batch must be called with empty context_pairs."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"seg {i}"}
        for i in range(4)
    ]
    captured_contexts = []

    original_translate_batch = OllamaTranslationEngine._translate_batch

    def spy_translate_batch(self, batch, glossary, style, temperature, context_pairs):
        captured_contexts.append(list(context_pairs))
        return [
            {"start": s["start"], "end": s["end"], "en_text": s["text"], "zh_text": f"譯 {s['text']}"}
            for s in batch
        ]

    monkeypatch.setattr(OllamaTranslationEngine, "_translate_batch", spy_translate_batch)

    engine = OllamaTranslationEngine({"engine": "mock-ollama", "context_window": 3})
    engine.translate(segments, batch_size=2, parallel_batches=2)

    assert all(ctx == [] for ctx in captured_contexts), (
        "parallel path must call _translate_batch with empty context_pairs"
    )


def test_parallel_batches_progress_callback_called(monkeypatch):
    """progress_callback must be called for each batch and counts must be thread-safe."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"seg {i}"}
        for i in range(6)
    ]

    def spy_translate_batch(self, batch, glossary, style, temperature, context_pairs):
        return [
            {"start": s["start"], "end": s["end"], "en_text": s["text"], "zh_text": f"譯 {s['text']}"}
            for s in batch
        ]

    monkeypatch.setattr(OllamaTranslationEngine, "_translate_batch", spy_translate_batch)

    calls = []
    def on_progress(completed, total):
        calls.append((completed, total))

    engine = OllamaTranslationEngine({"engine": "mock-ollama"})
    engine.translate(segments, batch_size=3, parallel_batches=2, progress_callback=on_progress)

    assert len(calls) == 2, "progress_callback must be called once per batch"
    assert calls[-1][0] == 6, "final completed count must equal total segments"
    assert all(total == 6 for _, total in calls)


def test_parallel_batches_one_uses_sequential_path(monkeypatch):
    """parallel_batches=1 must preserve context_window behaviour (non-empty context_pairs)."""
    from translation.ollama_engine import OllamaTranslationEngine

    segments = [
        {"start": float(i), "end": float(i+1), "text": f"seg {i}"}
        for i in range(4)
    ]
    captured_contexts = []

    def spy_translate_batch(self, batch, glossary, style, temperature, context_pairs):
        captured_contexts.append(list(context_pairs))
        return [
            {"start": s["start"], "end": s["end"], "en_text": s["text"], "zh_text": f"譯 {s['text']}"}
            for s in batch
        ]

    monkeypatch.setattr(OllamaTranslationEngine, "_translate_batch", spy_translate_batch)

    engine = OllamaTranslationEngine({"engine": "mock-ollama", "context_window": 2})
    engine.translate(segments, batch_size=2, parallel_batches=1)

    # Second batch should receive context from first batch
    assert captured_contexts[0] == [], "first batch always has empty context"
    assert len(captured_contexts[1]) > 0, "sequential path: second batch must receive context from first"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_translation.py::test_parallel_batches_returns_same_segment_count tests/test_translation.py::test_parallel_batches_disables_context_window -v
```

Expected: FAIL — `translate()` does not yet accept `parallel_batches`.

- [ ] **Step 3: Add imports to `ollama_engine.py`**

At the top of `backend/translation/ollama_engine.py`, add two imports after the existing stdlib imports:

```python
import threading
from concurrent.futures import ThreadPoolExecutor
```

- [ ] **Step 4: Replace `translate()` with parallel-capable version**

Replace the entire `translate()` method in `backend/translation/ollama_engine.py` (lines 135–187) with:

```python
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
        progress_callback=None,
        parallel_batches: int = 1,
    ) -> List[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        total = len(segments)
        batches = [
            segments[i : i + effective_batch]
            for i in range(0, len(segments), effective_batch)
        ]

        if parallel_batches <= 1:
            # Sequential path — identical to original behaviour
            all_translated = []
            context_pairs: list = []
            for batch in batches:
                translated_batch = self._translate_batch(
                    batch, glossary, style, effective_temp, context_pairs
                )
                missing_indices = [
                    j for j, r in enumerate(translated_batch)
                    if "[TRANSLATION MISSING]" in r.get("zh_text", "")
                ]
                if missing_indices:
                    missing_segs = [batch[j] for j in missing_indices]
                    retried = list(self._retry_missing(
                        missing_segs, glossary, style, effective_temp, context_pairs
                    ))
                    retried_iter = iter(retried)
                    translated_batch = [
                        next(retried_iter, r) if j in missing_indices else r
                        for j, r in enumerate(translated_batch)
                    ]
                all_translated.extend(translated_batch)
                if self._context_window > 0:
                    new_pairs = [
                        (seg["text"], t["zh_text"])
                        for seg, t in zip(batch, translated_batch)
                    ]
                    context_pairs = (context_pairs + new_pairs)[-self._context_window:]
                if progress_callback is not None:
                    try:
                        progress_callback(len(all_translated), total)
                    except Exception:
                        pass
        else:
            # Parallel path — context_window disabled (order non-deterministic)
            lock = threading.Lock()
            completed_count = [0]

            def _run_batch(batch):
                result = self._translate_batch(
                    batch, glossary, style, effective_temp, []
                )
                missing_indices = [
                    j for j, r in enumerate(result)
                    if "[TRANSLATION MISSING]" in r.get("zh_text", "")
                ]
                if missing_indices:
                    missing_segs = [batch[j] for j in missing_indices]
                    retried = list(self._retry_missing(
                        missing_segs, glossary, style, effective_temp, []
                    ))
                    retried_iter = iter(retried)
                    result = [
                        next(retried_iter, r) if j in missing_indices else r
                        for j, r in enumerate(result)
                    ]
                with lock:
                    completed_count[0] += len(result)
                    if progress_callback is not None:
                        try:
                            progress_callback(completed_count[0], total)
                        except Exception:
                            pass
                return result

            with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
                futures = [executor.submit(_run_batch, batch) for batch in batches]
                all_translated = []
                for future in futures:
                    all_translated.extend(future.result())

        processor = TranslationPostProcessor(max_chars=MAX_SUBTITLE_CHARS)
        return processor.process(all_translated)
```

- [ ] **Step 5: Run all new tests and full suite**

```bash
pytest tests/test_translation.py -v
pytest tests/ -q
```

Expected: all 4 new tests PASS; full suite 292+ PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_translation.py
git commit -m "feat: parallel batch translation via ThreadPoolExecutor in OllamaTranslationEngine"
```

---

### Task 4: Timing Tracking in `app.py` + Pass `parallel_batches`

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_translation.py` (append timing emit tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_translation.py`:

```python
# ===== pipeline timing — app._auto_translate =====

def test_translation_progress_includes_elapsed_seconds(tmp_path, monkeypatch):
    """_auto_translate must include elapsed_seconds in every translation_progress emit."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import app as _app

    # Patch profile manager to return a profile with mock engine
    class FakeProfileManager:
        def get_active(self):
            return {
                "translation": {"engine": "mock"},
                "asr": {"language": "en"},
            }

    class FakeLanguageConfigManager:
        def get(self, _):
            return None

    class FakeGlossaryManager:
        def get(self, _):
            return None

    monkeypatch.setattr(_app, "_profile_manager", FakeProfileManager())
    monkeypatch.setattr(_app, "_language_config_manager", FakeLanguageConfigManager())
    monkeypatch.setattr(_app, "_glossary_manager", FakeGlossaryManager())
    monkeypatch.setattr(_app, "_update_file", lambda *a, **kw: None)

    emitted = []
    monkeypatch.setattr(_app.socketio, "emit", lambda event, data=None, **kw: emitted.append((event, data)))

    segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    _app._auto_translate("fake-id", segments, None)

    progress_events = [d for e, d in emitted if e == "translation_progress"]
    assert len(progress_events) > 0, "translation_progress must be emitted"
    for evt in progress_events:
        assert "elapsed_seconds" in evt, f"elapsed_seconds missing from translation_progress: {evt}"
        assert isinstance(evt["elapsed_seconds"], float)


def test_pipeline_timing_event_emitted(tmp_path, monkeypatch):
    """_auto_translate must emit pipeline_timing after translation completes."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import app as _app

    class FakeProfileManager:
        def get_active(self):
            return {
                "translation": {"engine": "mock"},
                "asr": {"language": "en"},
            }

    class FakeLanguageConfigManager:
        def get(self, _):
            return None

    class FakeGlossaryManager:
        def get(self, _):
            return None

    monkeypatch.setattr(_app, "_profile_manager", FakeProfileManager())
    monkeypatch.setattr(_app, "_language_config_manager", FakeLanguageConfigManager())
    monkeypatch.setattr(_app, "_glossary_manager", FakeGlossaryManager())
    monkeypatch.setattr(_app, "_update_file", lambda *a, **kw: None)
    monkeypatch.setattr(_app, "_file_registry", {"fake-id": {}})

    emitted = []
    monkeypatch.setattr(_app.socketio, "emit", lambda event, data=None, **kw: emitted.append((event, data)))

    segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    _app._auto_translate("fake-id", segments, "fake-sid")

    timing_events = [d for e, d in emitted if e == "pipeline_timing"]
    assert len(timing_events) == 1, "pipeline_timing must be emitted exactly once"
    evt = timing_events[0]
    assert "translation_seconds" in evt
    assert "total_seconds" in evt
    assert "asr_seconds" in evt
    assert isinstance(evt["translation_seconds"], float)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_translation.py::test_translation_progress_includes_elapsed_seconds tests/test_translation.py::test_pipeline_timing_event_emitted -v
```

Expected: FAIL — `elapsed_seconds` not yet in emit, `pipeline_timing` event not yet emitted.

- [ ] **Step 3: Store `asr_seconds` after transcription**

In `backend/app.py`, find the block where `transcription_complete` is emitted (around line 1526). Just **before** that `socketio.emit('transcription_complete', ...)` call, add:

```python
                _update_file(file_id, asr_seconds=round(time.time() - transcribe_start_time, 1))
```

- [ ] **Step 4: Add `translation_start` and `elapsed_seconds` in `_auto_translate`**

In `backend/app.py`, inside `_auto_translate()`, make these three changes:

**4a.** Right after `try:` (before `profile = _profile_manager.get_active()`), add:
```python
        translation_start = time.time()
```

**4b.** Replace the `_emit_auto_progress` closure (which currently emits without elapsed) with:
```python
            def _emit_auto_progress(completed: int, total: int) -> None:
                socketio.emit('translation_progress', {
                    'file_id': fid,
                    'completed': completed,
                    'total': total,
                    'percent': int((completed / total) * 100) if total else 0,
                    'elapsed_seconds': round(time.time() - translation_start, 1),
                })
```

**4c.** After `_update_file(fid, translations=translated, ...)` and before the `if session_id: socketio.emit('file_updated', ...)` block, add:
```python
            translation_seconds = round(time.time() - translation_start, 1)
            asr_s = _file_registry.get(fid, {}).get('asr_seconds')
            if session_id:
                socketio.emit('pipeline_timing', {
                    'file_id': fid,
                    'asr_seconds': asr_s,
                    'translation_seconds': translation_seconds,
                    'total_seconds': round(translation_seconds + (asr_s or 0.0), 1),
                }, room=session_id)
```

- [ ] **Step 5: Pass `parallel_batches` from profile config to engine**

In `backend/app.py`, find the `engine.translate(...)` call inside `_auto_translate()`. Add `parallel_batches` to the call:

```python
            parallel_batches = int(translation_config.get("parallel_batches", 1))
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
```

- [ ] **Step 6: Run all new tests and full suite**

```bash
pytest tests/test_translation.py -v
pytest tests/ -q
```

Expected: both new timing tests PASS; full suite 292+ PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py
git commit -m "feat: add pipeline timing tracking and pass parallel_batches to translation engine"
```

---

### Task 5: Frontend — Elapsed Counter, `pipeline_timing` Toast, Profile Form Field

**Files:**
- Modify: `frontend/index.html`

No automated tests — verify via smoke tests listed at the end of this task.

- [ ] **Step 1: Update `translation_progress` handler to show elapsed time**

In `frontend/index.html`, find the `socket.on('translation_progress', ...)` handler (line ~1486). Replace the `info.textContent` line:

Before:
```javascript
      if (info) info.textContent = `翻譯中 ${data.completed} / ${data.total} 段 · ${data.percent}%`;
```

After:
```javascript
      const elapsed = data.elapsed_seconds != null ? ` — 已用 ${data.elapsed_seconds}s` : '';
      if (info) info.textContent = `翻譯中 ${data.completed} / ${data.total} 段 · ${data.percent}%${elapsed}`;
```

- [ ] **Step 2: Add `pipeline_timing` socket handler**

In `frontend/index.html`, after the `socket.on('translation_progress', ...)` handler, add:

```javascript
  socket.on('pipeline_timing', (data) => {
    if (!data) return;
    const parts = [];
    if (data.asr_seconds != null) parts.push(`ASR: ${data.asr_seconds}s`);
    parts.push(`翻譯: ${data.translation_seconds}s`);
    parts.push(`總計: ${data.total_seconds}s`);
    showToast(parts.join(' ｜ '), 'success');
  });
```

- [ ] **Step 3: Add `parallel_batches` field to profile form**

In `frontend/index.html`, find the translation settings section of the profile form. Locate the glossary dropdown row (search for `pf-tr-glossary`). Insert the following **before** the glossary row:

```html
<div class="pf-row">
  <label for="pf-tr-parallel">並發批次</label>
  <input type="number" id="pf-tr-parallel" min="1" max="8" step="1" placeholder="1">
  <p class="pf-hint">本地模型建議 1–2（需設定 OLLAMA_NUM_PARALLEL≥N）；雲端模型建議 3–5</p>
</div>
```

- [ ] **Step 4: Wire `parallel_batches` into profile save/load**

In `frontend/index.html`, find the function that reads the profile form and builds the PATCH payload (search for `pf-tr-engine` or `buildProfilePayload` or where the translation object is assembled for saving). Add `parallel_batches` to the translation object:

```javascript
const parallelBatchesVal = document.getElementById('pf-tr-parallel').value;
const parallelBatches = parallelBatchesVal ? parseInt(parallelBatchesVal, 10) : undefined;

// In the translation object:
const translation = {
  engine: ...,
  // ... existing fields ...
  ...(parallelBatches !== undefined && !isNaN(parallelBatches) ? { parallel_batches: parallelBatches } : {}),
};
```

Find the function that populates the profile form from a loaded profile (search for `pf-tr-engine` value assignment). Add:

```javascript
document.getElementById('pf-tr-parallel').value =
  profile.translation?.parallel_batches ?? '';
```

- [ ] **Step 5: Smoke tests**

Start the server: `./start.sh`

1. Upload a short video file. Observe translation progress label — should show `翻譯中 N / M 段 · X% — 已用 Ys`
2. After translation completes, a success toast appears: `ASR: Xs ｜ 翻譯: Ys ｜ 總計: Zs`
3. When triggered via manual translate button (no fresh ASR), toast shows only `翻譯: Ys` (no ASR line)
4. Open Profile editor → Translation section → confirm `並發批次` field is present
5. Set `parallel_batches = 2`, save profile, reload — field shows `2`

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html
git commit -m "feat: elapsed time display, pipeline_timing toast, parallel_batches profile field"
```

---

### Task 6: README.md Performance Section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add 效能調校 section**

In `README.md`, find an appropriate location after the translation/engine section. Add the following section (in Traditional Chinese, consistent with the rest of README.md):

```markdown
## 效能調校

### 並發批次翻譯（parallel_batches）

Profile 的翻譯設定支援 `parallel_batches`（預設 1）。設定後，翻譯引擎會同時發送多個 batch 請求，縮短總翻譯時間。

| 使用情境 | 建議值 |
|---------|--------|
| 本地 Ollama（3B/7B 模型） | 1–2 |
| 雲端模型（qwen3.5-397b-cloud 等） | 3–5 |

在 Profile 編輯器的「翻譯設定」區塊設定「並發批次」欄位即可。

> **注意：** 使用本地 Ollama 時，需同時設定 `OLLAMA_NUM_PARALLEL` 環境變量，數值須 ≥ `parallel_batches`：
>
> ```bash
> OLLAMA_NUM_PARALLEL=2 ollama serve
> ```
>
> 16 GB RAM 的 Apple Silicon Mac 跑 7B 模型時，建議不超過 2，以免記憶體不足。  
> 雲端模型（`ollama signin` 後使用）無此限制，可設至 3–5。

### 處理時間顯示

每次翻譯完成後，介面會顯示各階段耗時：

```
ASR: 8s ｜ 翻譯: 34s ｜ 總計: 42s
```

翻譯進行中也會即時顯示已用時間，方便確認處理速度是否符合預期。
```

- [ ] **Step 2: Run full test suite one final time**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q
```

Expected: 292+ PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add performance tuning section for parallel_batches and timing display"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `elapsed_seconds` in `translation_progress` → Task 4 step 4b
- ✅ `pipeline_timing` event → Task 4 step 4c
- ✅ `asr_seconds` stored in registry → Task 4 step 3
- ✅ Frontend elapsed counter → Task 5 step 1
- ✅ Frontend pipeline_timing toast → Task 5 step 2
- ✅ `parallel_batches` validation → Task 1
- ✅ ABC + mock signature update → Task 2
- ✅ ThreadPoolExecutor parallel path → Task 3
- ✅ Context window disabled when parallel > 1 → Task 3 step 4
- ✅ Profile form field → Task 5 step 3/4
- ✅ README 效能調校 section → Task 6
- ✅ `pipeline_timing` omits ASR line when `asr_seconds` is null → Task 5 step 2 (JS checks `!= null`)

**Placeholder scan:** No TBD, no "handle edge cases", no "similar to Task N".

**Type consistency:** `parallel_batches: int = 1` used consistently across ABC, mock, ollama, profiles validation, and app.py call site. `elapsed_seconds: float` consistent across backend emit and frontend handler.
