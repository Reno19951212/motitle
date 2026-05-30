# Project bug audit — 2026-05-31

Multi-agent workflow (8 read-only finders → dedup → adversarial per-candidate verification). Stats: {"raw": 30, "deduped": 30, "verified": 30, "confirmed": 25, "refuted": 5}

## Confirmed (25)

### 1. [HIGH] LLMRefiner JSON unwrap accepts non-string text values
- **File**: backend/engines/refiner/llm_refiner.py:87
- **Symptom**: When LLM responds with JSON containing a non-string "text" field (e.g., {"text": 123} or {"text": ["a", "b"]}), the code converts it to string using str(), resulting in nonsensical output like "123" or "['a', 'b']" instead of treating it as a malformed response.
- **Root cause**: Line 87 uses `str(_parsed.get("text") or "").strip()` which stringifies any truthy value. Should check `isinstance(_parsed.get("text"), str)` before using the value.
- **Trigger**: 1. Configure LLM to return JSON with numeric or array text field, 2. Run V6 pipeline with refiner stage, 3. Observe subtitle text contains string representations of non-string objects (e.g., "123" or "['item']")
- **Evidence**: File: backend/engines/refiner/llm_refiner.py, Line 87: `refined = str(_parsed.get("text") or "").strip()`. Demonstrated defect: When input JSON is `{"action": "keep", "text": 123}`, output text becomes "123" instead of falling back to source. When input is `{"action": "keep", "text": ["a", "b"]}`, output becomes "['a', 'b']". No isinstance guard exists before the str() call. Test file backend/tests/test_v6_refiner_json_unwrap.py contains 11 tests but none cover non-string text values in JSON responses.
- **Fix**: File: backend/engines/refiner/llm_refiner.py, Line 87. Replace `refined = str(_parsed.get("text") or "").strip()` with: `text_value = _parsed.get("text"); refined = text_value.strip() if isinstance(text_value, str) else ""`. This preserves the existing empty-string fallback logic at lines 90-91 while rejecting non-string "text" fields as malformed responses that should fall back to source.

### 2. [HIGH] split_v6_aligned creates fallback source with None start/end when refined lacks timing
- **File**: backend/stages/v6/clause_split.py:122-123
- **Symptom**: If refined_segs lacks start/end fields, the fallback dict created for missing source segments has None values for start/end instead of defaults, resulting in malformed subtitle timing data.
- **Root cause**: Line 122-123 uses `refined.get("start")` and `refined.get("end")` without providing default values (should be `refined.get("start", 0.0)`).
- **Trigger**: 1. Pass refined_segs with missing start/end to split_v6_aligned, 2. Have fewer source_segs than refined_segs, 3. Observe returned timing has None instead of numeric values
- **Evidence**: File: backend/stages/v6/clause_split.py, lines 122-123. Current code: `"start": refined.get("start"), "end": refined.get("end")` produces None when keys missing. Contrast with defensive pattern at lines 100-101 in same file: `start = float(seg.get("start") or 0.0)` which uses defaults. Concrete bug reproduction: source_segs=[{start:0.0, end:5.0, text:"abc"}], refined_segs=[{start:0.0, end:5.0, text:"short", flags:[]}, {text:"...", flags:[]}] → produces segment with start=None, end=None.
- **Fix**: File: backend/stages/v6/clause_split.py, lines 122-123. Change: Replace `"start": refined.get("start"), "end": refined.get("end")` with `"start": refined.get("start") or 0.0, "end": refined.get("end") or 0.0` to match the defensive pattern used in clause_split_segment (lines 100-101).

### 3. [HIGH] clause_split_segment returns original dict reference when text <= char_cap, violating immutability contract
- **File**: backend/stages/v6/clause_split.py:103
- **Symptom**: When segment text is short (≤char_cap), the function returns [dict(seg)] which is a shallow copy. If caller later mutates fields in the returned dict, the original segment is affected since dicts with complex values share references.
- **Root cause**: Line 103 returns `[dict(seg)]` but if seg contains nested dicts or lists, they are shared between original and copy. The project mandates NEVER mutating shared objects. Line 106 has the same issue.
- **Trigger**: 1. Call clause_split_segment with a short segment, 2. Mutate a nested structure in returned piece (e.g., piece[0]['flags'].append(...)), 3. Observe original segment's flags were also mutated
- **Evidence**: Lines 103 and 106 in backend/stages/v6/clause_split.py both use `[dict(seg)]` which creates a shallow copy. There is NO guard that converts nested structures to deep copies. Concrete trigger: (1) Call clause_split_segment({"start": 0.0, "end": 3.0, "text": "短句", "flags": ["f1"]}, char_cap=24) (2) Append to result[0]['flags'] (3) Original seg['flags'] is mutated. The test suite's immutability checks only verify top-level equality, not deep structure protection.
- **Fix**: Replace lines 103 and 106 with deep copies. Change `return [dict(seg)]` to `return [copy.deepcopy(seg)]` (requires adding `import copy` at the top of the file). This ensures nested structures like flags lists and dicts are completely independent from the original segment, preventing accidental mutations from affecting the input.

### 4. [HIGH] Glossary entry missing 'target' field causes KeyError in _enrich_batch
- **File**: backend/translation/ollama_engine.py:506
- **Symptom**: Pass 2 enrichment fails with KeyError when glossary entry has 'source' but missing 'target' field
- **Root cause**: Line 239 filters glossary entries by checking only `e.get('source')` is truthy, but does not validate `e.get('target')` exists. Later, line 506 accesses `entry['target']` directly without .get(), causing KeyError on malformed entries.
- **Trigger**: (1) Profile has glossary_id configured with EN→ZH glossary; (2) Glossary contains entry with 'source' field but missing 'target' field (data model drift or corruption); (3) Translation executed with translation_passes >= 2; (4) Enriched segment's source text contains a glossary term; Result: KeyError in _enrich_batch line 506
- **Evidence**: File: backend/translation/ollama_engine.py
Line 239 (filter check): if e.get("source") and e["source"].lower() in joined  -- only validates 'source' exists, no check for 'target'
Line 506 (first KeyError site): f'- {entry["source"]} → {entry["target"]}' -- direct bracket access, no .get()
Lines 619 and 716: Same pattern in _translate_single() and _build_system_prompt()

File: backend/glossary.py
Line 261-276 (get method): Loads glossary from disk without validating entries. Only validates source_lang/target_lang.
This means corrupted glossary files are returned untouched to the translation engine.

No guard prevents the defect: GlossaryManager.validate_entry() (line 212-214) requires 'target' to exist, but this is only called during create/update/import, NOT during get().
- **Fix**: File: backend/translation/ollama_engine.py
Function: _filter_glossary_for_batch (line 226-240)
Change line 239 from:
    if e.get("source") and e["source"].lower() in joined
To:
    if e.get("source") and e.get("target") and e["source"].lower() in joined

Rationale: Add validation that 'target' field exists when filtering entries. This prevents malformed entries from reaching the downstream code that accesses entry['target'] directly.

Additional fix (defense in depth): File: backend/glossary.py
Function: get (line 261-276)
Add validation of entries before returning:
    glossary = self._read_glossary(path)
    if not is_supported_lang(glossary.get("source_lang")):
        return None
    if not is_supported_lang(glossary.get("target_lang")):
        return None
    # Validate entries to catch corrupted glossaries
    for entry in glossary.get("entries", []):
        if not entry.get("target"):
            return None  # Treat corrupted glossaries as not-found
    return glossary

### 5. [HIGH] Identical bug: glossary 'target' field access in _translate_single and _build_system_prompt
- **File**: backend/translation/ollama_engine.py:619,716
- **Symptom**: Single-segment translation or batch translation fails with KeyError when glossary entry lacks 'target' field
- **Root cause**: Same root cause as bug #1: _filter_glossary_for_batch only validates 'source' existence (line 239), not 'target'. Lines 619 and 716 access `entry['target']` directly, causing KeyError on malformed glossary entries.
- **Trigger**: Same as bug #1, but triggered during single-segment (batch_size=1) or normal batch translation instead of enrichment
- **Evidence**: File: backend/translation/ollama_engine.py

Line 239 filter condition: `if e.get("source") and e["source"].lower() in joined`
- Only checks for 'source' existence, no guard for 'target'

Vulnerable access points:
- Line 506: `f'- {entry["source"]} → {entry["target"]}' for entry in relevant_glossary`
- Line 619: `f'- {entry["source"]} → {entry["target"]}' for entry in relevant_glossary`  
- Line 716: `f'- {entry["source"]} → {entry["target"]}' for entry in glossary`

Demonstrated with test case: Entry `{"source": "world"}` (no target) passes filter but raises KeyError on access.
- **Fix**: File: backend/translation/ollama_engine.py, function `_filter_glossary_for_batch` (lines 237-240)

Change line 239 from:
```python
if e.get("source") and e["source"].lower() in joined
```

To:
```python
if e.get("source") and e.get("target") and e["source"].lower() in joined
```

This ensures only entries with BOTH 'source' AND 'target' fields are returned by the filter, preventing KeyError when accessing `entry["target"]` at lines 506, 619, and 716.

### 6. [HIGH] Off-by-one risk in redistribute_to_segments when final segment receives empty allocation
- **File**: backend/translation/sentence_pipeline.py:163-171
- **Symptom**: Final segment in a merged sentence may receive empty string if proportional split positions round down to exact boundary of previous segment
- **Root cause**: Lines 166-169: `target_end = char_offset + round(total_zh_chars * proportion)` may compute exactly `char_offset` if proportion is small and rounds to 0. When `break_at = max(char_offset, min(break_at, total_zh_chars))` forces no-op (line 169), allocated chunk is empty and char_offset stays unchanged. Final segment (line 164) then gets the remainder, which is correct, but intermediate segments could all consume text, leaving nothing for one segment.
- **Trigger**: Merged sentence with 4+ segments where first 3 have small word counts and last has large count; Chinese text evenly distributed; rounding causes early segments to claim most text, starving the middle segments
- **Evidence**: Lines 166-171 in backend/translation/sentence_pipeline.py: target_end = char_offset + round(total_zh_chars * proportion) can compute to exactly char_offset when proportion is small (e.g., 0.01), making break_at = max(char_offset, min(char_offset, total_zh_chars)) = char_offset. This results in allocated = zh_text[char_offset:char_offset] = "" with no advancing of char_offset, causing subsequent segments to repeat the same calculation. No guard prevents empty allocations except validate_batch's 3+ consecutive check, which fails for 2 empty segments.
- **Fix**: In redistribute_to_segments (line 134-186), after line 169 where break_at is computed, add a guard: if break_at == char_offset and i < len(merged["seg_indices"]) - 2 (not penultimate), ensure break_at advances by at least 1 character: break_at = max(char_offset + 1, break_at) to guarantee non-empty allocations for non-final segments.

### 7. [HIGH] Empty segment filtering contract mismatch between ASR engines
- **File**: backend/asr/mlx_whisper_engine.py:58-59
- **Symptom**: mlx_whisper_engine filters out segments where text.strip() == "", but faster-whisper and openai-whisper engines include all segments. Causes inconsistent segment counts and indices when switching between engines.
- **Root cause**: mlx_whisper_engine has a conditional filter (lines 58-59: if not text: continue) that is not present in whisper_engine.py (_transcribe_faster at lines 117-133 and _transcribe_openai at lines 150-166). Both whisper paths always append segments unconditionally.
- **Trigger**: Configure a profile to use mlx-whisper, transcribe audio that produces one or more segments with whitespace-only or empty text. Then reconfigure the same profile to use faster-whisper or openai-whisper and transcribe the same audio. The output segment lists will have different lengths and segment IDs will be misaligned.
- **Evidence**: backend/asr/mlx_whisper_engine.py:58-59 - if not text: continue (FILTERS OUT)
backend/asr/whisper_engine.py:117-134 (_transcribe_faster) - segments.append(entry) UNCONDITIONAL (NO FILTER)
backend/asr/whisper_engine.py:150-167 (_transcribe_openai) - segments.append(entry) UNCONDITIONAL (NO FILTER)
No guard exists in calling code (asr_stage.py:66-70 appends all segments unconditionally)
- **Fix**: File: backend/asr/mlx_whisper_engine.py
Function: MlxWhisperEngine.transcribe (lines 55-76)
Change: Remove lines 58-59 (if not text: continue) to match whisper_engine behavior. Replace with unconditional append of all segments, including empty ones. This ensures all three engines (mlx-whisper, faster-whisper, openai-whisper) return segment lists with consistent counts and indices.

### 8. [HIGH] warning_missing_zh hardcodes zh_text field check instead of using actual second-role field
- **File**: backend/app.py:3140-3146
- **Symptom**: For V6 files with non-Cantonese second language (e.g., ja_text), the warning_missing_zh counter checks the hardcoded zh_text field which does not exist, causing all segments to be incorrectly flagged as missing translations.
- **Root cause**: The warning logic at line 3145 checks `t.get("zh_text")` unconditionally, but for V6 files, the second-role field is determined dynamically by _role_fields_for() and stored in _render_second_field. This field can be None or something like "ja_text", not always "zh_text".
- **Trigger**: 1) Create V6 file with source_lang='en' and by_lang containing 'en' and 'ja' translations. 2) Call POST /api/render with subtitle_source='bilingual'. 3) The response will include warning_missing_zh equal to the segment count (all segments marked as missing ZH) even though all have complete 'ja' translations.
- **Evidence**: File: backend/app.py
Lines 3103-3146:
- Line 3103: _render_first_field, _render_second_field = _role_fields_for(entry) — correctly resolves dynamic second field
- Lines 3143-3146: if subtitle_source in ("zh", "bilingual"): for t in translations: if not (t.get("zh_text") or "").strip(): — hardcoded check of "zh_text" field
- No guard prevents this: _role_fields_for() can return second_field=None or "ja_text", but warning always checks "zh_text"
- Contrast with line 3197: second_field=_render_sf_snap, which correctly uses the resolved field for actual rendering
- **Fix**: File: backend/app.py (and /backend/routes/render.py which has identical bug)
Function: api_start_render() (around line 3033)
Change lines 3143-3146 from:
```python
if subtitle_source in ("zh", "bilingual"):
    for t in translations:
        if not (t.get("zh_text") or "").strip():
            warning_missing_zh += 1
```
To:
```python
if subtitle_source in ("zh", "bilingual"):
    for t in translations:
        if not (_resolve_role_text(t, _render_second_field, ["zh_text"]) or "").strip():
            warning_missing_zh += 1
```
Or more simply, use the same fallback pattern used elsewhere:
```python
if subtitle_source in ("zh", "bilingual"):
    for t in translations:
        field_value = t.get(_render_second_field) if _render_second_field else (t.get("zh_text") or "")
        if not (field_value or "").strip():
            warning_missing_zh += 1
```

### 9. [HIGH] seconds_to_ass_time centiseconds rounding can produce invalid values >99
- **File**: backend/renderer.py:71-78
- **Symptom**: ASS subtitle timestamps with fractional seconds ending in .XX95+ round centiseconds to 100, producing invalid timestamps like '0:00:01.100' instead of '0:00:02.00'. ASS parsers may reject or misinterpret these timestamps.
- **Root cause**: Line 76 computes `cs = int(round((seconds % 1) * 100))` without capping at 99. When the fractional part is 0.995 or higher, rounding produces 100, which violates ASS time format (centiseconds must be 0-99).
- **Trigger**: Call generate_ass() with a segment having start or end time with fractional seconds >= .995 (e.g., start=1.995). The ASS output will contain invalid timestamp like '0:00:01.100'.
- **Evidence**: File: backend/renderer.py, lines 71-77. The buggy code:
```python
def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))  # Line 76: no capping at 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
```

When called with seconds=1.995, this produces: h=0, m=0, s=1, cs=100, resulting in output "0:00:01.100" (invalid ASS timestamp). The function is called at lines 151-152 in generate_ass() with no prior validation or normalization of segment timestamps.
- **Fix**: File: backend/renderer.py, function seconds_to_ass_time (lines 71-77). Replace the centiseconds computation with rounding at the total centiseconds level to ensure proper carry propagation. Minimal fix:

```python
def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc (centiseconds)."""
    # Round at centiseconds level to handle carries correctly
    total_cs = int(round(seconds * 100))
    h = total_cs // 360000  # 3600 seconds * 100 centiseconds
    total_cs %= 360000
    m = total_cs // 6000    # 60 seconds * 100 centiseconds
    total_cs %= 6000
    s = total_cs // 100
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
```

This approach rounds once at the total centiseconds level, then distributes into time components, ensuring centiseconds never exceed 99.

### 10. [HIGH] V6 bilingual_order default 'en_top' creates semantically incorrect stacking for non-English source_lang
- **File**: backend/subtitle_text.py:106-122
- **Symptom**: For V6 files with non-English source_lang (e.g., source='ja'), render requests without explicit bilingual_order default to 'en_top', which causes the resolver to interpret this as '(first, second) stacking' where first is Japanese. The output stacks Japanese on top, but the setting name 'en_top' implies English should be on top, violating broadcast convention.
- **Root cause**: resolve_bilingual_order() at line 121 returns hardcoded 'en_top' as fallback default, assuming the first-role language is always English (true for Profile, false for V6 pipelines). The order name semantically encodes 'English=first', but resolve_segment_text uses it only to determine (first, second) vs (second, first) stacking regardless of actual language.
- **Trigger**: 1) Create V6 file with source_lang='ja' and a second language 'en' in by_lang. 2) POST /api/render with subtitle_source='bilingual' and no bilingual_order override. 3) The rendered subtitles will stack Japanese on top and English below, contradicting 'en_top' which should put English on top.
- **Evidence**: File: backend/subtitle_text.py, lines 106-121. resolve_bilingual_order() returns hardcoded "en_top" default at line 121. No logic checks file.active_kind or source_lang. Verified with concrete test: V6 file entry with source_lang='ja', second lang='en', no override → bilingual_order='en_top' → resolve_segment_text with order='en_top' and first_field='ja_text', second_field='en_text' → result='こんにちは\\nHello' (Japanese on top, English below), violating semantic meaning of 'en_top'.
- **Fix**: File: backend/subtitle_text.py, function resolve_bilingual_order() around line 119-121. Before the final `return "en_top"`, add language-aware logic: Check if file_entry.active_kind == 'pipeline_v6' and source_lang is non-English (from translations[0].source_lang). If true, return 'zh_top' instead to invert stacking and put the second language on top. This preserves the semantic meaning of 'en_top' for non-English V6 sources.

### 11. [HIGH] _pending_second_lang collision on concurrent translate_second_language requests
- **File**: backend/app.py:3796
- **Symptom**: When two concurrent POST /api/files/<file_id>/translate-second requests with different target languages are issued, the second request overwrites _pending_second_lang. Both jobs may then translate to the wrong language depending on worker scheduling.
- **Root cause**: translate_second_language route calls _update_file(file_id, _pending_second_lang=lang) at line 3796 without checking if _pending_second_lang is already set. A second concurrent request overwrites the value before the first job's _mt_handler reads it, causing both jobs to see the same (wrong) target language.
- **Trigger**: 1. POST /api/files/file1/translate-second {"lang": "en"} → returns job_A
2. (concurrently, before job_A runs) POST /api/files/file1/translate-second {"lang": "fr"} → returns job_B
3. Worker picks up job_A
4. _mt_handler reads _pending_second_lang="fr" (overwritten by step 2)
5. _translate_second_handler translates job_A to 'fr' instead of 'en'
- **Evidence**: backend/app.py:3797 (_update_file called without checking if _pending_second_lang already set) + backend/app.py:509-512 (_mt_handler checks LIVE _pending_second_lang without job-level language tracking) + backend/app.py:3800-3804 (job enqueued without target_lang parameter). No guard prevents concurrent requests from overwriting _pending_second_lang before worker reads it.
- **Fix**: Store target language in the job object itself. Modify line 3800-3804 to pass target_lang in enqueue params: _job_queue.enqueue(user_id=uid, file_id=file_id, job_type='translate', target_lang=lang). Then in _translate_second_handler (line 407), read from job["target_lang"] instead of entry.get("_pending_second_lang"). Remove the _pending_second_lang workaround entirely or use it only as a dispatch flag in _mt_handler, not as the authoritative source for target language.

### 12. [HIGH] _pending_second_lang not cleared on handler failure leads to infinite retry loop
- **File**: backend/app.py:386
- **Symptom**: If _translate_second_handler raises an exception during processing (e.g., LLM API timeout, llm_profile not found, stage.transform failure), the _pending_second_lang flag is never cleared. The job fails and when retried, _mt_handler dispatches to _translate_second_handler again infinitely until attempt_count exceeds R5_MAX_JOB_RETRY cap, wasting retries.
- **Root cause**: _translate_second_handler has no try/finally block to clean up _pending_second_lang on failure. The flag is only cleared at line 485 in the success path inside the final lock block. If any exception is raised (lines 409, 438, 470), the handler exits without cleanup.
- **Trigger**: 1. POST /api/files/file1/translate-second {"lang": "en"}
2. Job starts, _translate_second_handler calls stage.transform at line 470
3. stage.transform raises exception (API timeout, network error, etc.)
4. Handler exits, JobQueue marks status='failed', line 485 never executes
5. User calls retry via POST /api/queue/<job_id>/retry
6. New job created with parent_job_id
7. _mt_handler sees _pending_second_lang still set, calls _translate_second_handler again
8. Handler fails again, loop repeats until attempt_count >= R5_MAX_JOB_RETRY
- **Evidence**: File: backend/app.py Lines 386-486: _translate_second_handler function. Buggy lines: 468 (stage.transform can raise), 405/409/413/436 (validation raises), and 485 (cleanup only in success path). Missing guard: No try/finally wraps the handler. Cleanup code (line 485) is only reachable on successful completion; lines 471-486 are part of the normal success flow with zero exception handling.
- **Fix**: File: backend/app.py, function: _translate_second_handler (lines 386-486). Minimal fix: Wrap lines 467-486 in a try block, and add a finally block after line 486 that unconditionally clears _pending_second_lang. Alternatively (cleaner): Extract the cleanup into a dedicated try/finally at the end of the function:

```python
def _translate_second_handler(job, cancel_event=None):
    # ... existing code lines 397-467 ...
    
    try:
        stage = TranslatorStage(translator_profile=translator_profile, llm_profile=llm_profile)
        out = stage.transform(refined, ctx)

        # Write back by_lang[target] + <target>_text mirror
        with _registry_lock:
            live_translations = _file_registry.get(file_id, {}).get("translations") or []
            for i, row in enumerate(live_translations):
                if i >= len(out):
                    break
                translated_text = out[i].get("text", "")
                row.setdefault("by_lang", {})[target] = {
                    "text": translated_text,
                    "status": "pending",
                    "flags": out[i].get("flags", []),
                }
                row[f"{target}_text"] = translated_text
            _save_registry()
    finally:
        # Always clear the pending flag so _mt_handler won't re-dispatch on retry
        with _registry_lock:
            if file_id in _file_registry:
                _file_registry[file_id].pop("_pending_second_lang", None)
            _save_registry()
```

This ensures cleanup occurs on both success AND failure paths.

### 13. [HIGH] Race condition: registry mutation outside lock in _auto_translate
- **File**: backend/app.py:3426-3431
- **Symptom**: File entry is read inside registry lock, lock is released, then entry is mutated and _save_registry() called without holding the lock. This allows concurrent threads to modify the same entry, causing lost updates or stale state.
- **Root cause**: Lines 3426-3427 acquire lock, read entry, then immediately release lock (with block ends). Lines 3428-3431 then mutate entry and call _save_registry() without holding the lock. Between lock release and mutation, another thread could delete the file or modify it, causing race condition.
- **Trigger**: 1. Configure OpenRouter without api_key. 2. Upload two files simultaneously, both triggering _auto_translate. 3. Both threads enter _auto_translate, both hit the api_key check. 4. First thread reads entry (locked), second thread also reads entry (locked). 5. Both release lock and try to mutate entry['translation_status'] concurrently → data race.
- **Evidence**: File: backend/app.py, Lines 3426-3431. The with _registry_lock block ends at line 3427 (after entry = _file_registry.get(fid)). Lines 3428-3431 then mutate entry["translation_status"] and entry["translation_error"] and call _save_registry() WITHOUT holding the lock. Meanwhile, the JobQueue has _MT_CONCURRENCY=3 (line 31 of backend/jobqueue/queue.py), allowing up to 3 concurrent _auto_translate calls. A second thread could acquire the lock, get the same entry reference, release the lock, and mutate the same dict concurrently with the first thread, resulting in lost updates.
- **Fix**: File: backend/app.py, function _auto_translate(). Move lines 3428-3431 inside the with _registry_lock block. Change from: "with _registry_lock: entry = _file_registry.get(fid) / if entry: entry["translation_status"] = ..." to: "with _registry_lock: entry = _file_registry.get(fid) / if entry: entry["translation_status"] = ...; _save_registry()". Same fix applies to lines 3436-3444 which has the identical pattern.

### 14. [HIGH] TOCTOU race condition: translate-second endpoint checks entry fields without lock
- **File**: backend/app.py:3769-3783
- **Symptom**: Entry is read inside lock, lock released, then entry.get('active_kind'), entry.get('translations') accessed without lock. Another thread could delete or modify file between lock release and access.
- **Root cause**: Lines 3769-3770 acquire lock and read entry. Lock released at end of with block. Lines 3774-3783 check entry.get('active_kind') and entry.get('translations') without re-acquiring lock. Another thread could modify or delete the file between lines 3770 and 3774.
- **Trigger**: 1. Make POST /api/files/<id>/translate-second request. 2. Handler acquires lock, reads entry at line 3770, releases lock. 3. Concurrently, DELETE /api/files/<id> or re-transcribe endpoint calls _update_file with translations=[]. 4. Request thread checks stale entry.get('translations') → processes with stale data or incorrect validation.
- **Evidence**: backend/app.py:3769-3783. Lock acquired at 3769-3770, released at end of with block. Lines 3774 and 3777 access entry fields without lock. Another thread can call _update_file() at line 3797 or any other endpoint with _update_file(file_id, translations=...) or entry deletion, modifying the dict between lock release and these accesses. Demonstrated with Python test: entry dict reference is mutable, translations list reference reflects concurrent modifications.
- **Fix**: backend/app.py, translate_second_language function: Extend the lock scope. Move the closing of the `with _registry_lock:` block to after line 3783 (after all validations complete). This ensures all entry field accesses stay protected. Minimal change: change line 3770's `with _registry_lock:` block to include lines up through 3783, so validations happen within the lock.

### 15. [HIGH] KeyError possible when V6 file has null active_id during error reporting
- **File**: backend/app.py:326
- **Symptom**: Error message tries to access f['active_id'] in the error string even if active_id is None, causing KeyError in error handling.
- **Root cause**: Line 326 uses f['active_id'] in the error message. If active_id is None (from bug #1), the code will try to display it in the error message—but the KeyError happens at line 323 before reaching line 326. However, the code should use f.get('active_id') defensively.
- **Trigger**: Same trigger as bug #1, though error occurs at line 323 before reaching line 326.
- **Evidence**: backend/app.py:323 uses f["active_id"] (direct key access, no guard). Line 633-638 shows _load_registry() just loads JSON without field migration. Line 318-320 shows a V6 file can exist with active_kind="pipeline_v6". No migration code backfills active_id for legacy entries.
- **Fix**: In backend/app.py, lines 323 and 326: Replace f["active_id"] with f.get("active_id"). Specifically: Line 323 should be: pipeline = f.get("active_pipeline_snapshot") or _pipeline_manager.get(f.get("active_id")). Line 326 should use f.get("active_id") in the error message. Optionally add migration logic in _load_registry() or at boot-time to backfill missing active_id fields on legacy entries.

### 16. [HIGH] step-diagram null stageIndex breaks done-state rendering
- **File**: frontend/js/step-diagram.js:8
- **Symptom**: When pipeline_progress event contains stage_index=null with stage_state='done', all pipeline steps render as 'pending' instead of showing completed checkmarks. Users see no visual indication that the pipeline finished.
- **Root cause**: Line 8 checks 'stageIndex >= stages.length - 1' which evaluates to 'null >= 4' = false. Line 11's 'i < stageIndex' check also fails when stageIndex is null, preventing any step from being marked as 'done'.
- **Trigger**: 1. Start a V6 pipeline. 2. Backend sends pipeline_progress event with stage_state='done', stage_index=null, pct=100. 3. Observe the step-diagram in the queue item - all steps appear pending/unhighlighted instead of showing completion.
- **Evidence**: frontend/js/step-diagram.js:8 — Line 8 checks 'stageIndex >= stages.length - 1' which evaluates to 'null >= 4' = false. Line 11 checks 'i < stageIndex' which evaluates to 'i < null' = false. No guard prevents null. Frontend code at index.html:5232 and queue-panel.js:20 explicitly accepts null via '?: null' pattern. Verified with Node.js test: when stageIndex=null and stageState='done', all steps render as sd-pending (0 done steps, 5 pending steps) instead of expected sd-done (5 done steps, 0 pending steps).
- **Fix**: File: frontend/js/step-diagram.js, Line 8. Change: const allDone = stageState === 'done' && stageIndex != null && stageIndex >= stages.length - 1; This adds a null guard so allDone is false when stageIndex is null, causing the function to fall through to the cold-start render path (all steps pending) rather than attempting null comparisons. Alternatively, modify the frontend event handlers at index.html:5232 and queue-panel.js:20 to pass stageIndex=stages.length-1 instead of null when stage_index is missing, which would mark all steps as complete.

### 17. [HIGH] Find-replace auto-approves segments incorrectly
- **File**: frontend/proofread.html:2528, 2569
- **Symptom**: When user does find-replace (single or all), the affected segments are automatically marked as approved even though the user did not explicitly approve them
- **Root cause**: Both fbReplaceCurrent() and fbReplaceAll() set approved: true in the segs.map() call after successful PATCH: `segs = segs.map((seg, i) => i === s.idx ? { ...seg, zh: newZh, approved: true, edited: true } : seg)`
- **Trigger**: (1) Open proofread page for V6 or Profile file with pending segments. (2) Use Find & Replace to replace text in a ZH field. (3) Observe: segment shows checkmark (approved) without user clicking Approve button. (4) Verify: renderProgress() now counts it as approved.
- **Evidence**: frontend/proofread.html line 2528 (fbReplaceCurrent): `segs = segs.map((seg, i) => i === s.idx ? { ...seg, zh: newZh, approved: true, edited: true } : seg)`. Line 2569 (fbReplaceAll): identical code. No guards validate user approval intent. The unconditional `approved: true` assignment with no user confirmation check causes the bug symptom. PATCH response is checked with `if (!r.ok)` but response body is never parsed; auto-approval happens without sync from backend.
- **Fix**: Remove manual `approved: true` from lines 2528 and 2569. Instead parse the PATCH response body via `const data = await r.json()` and update segment state from backend's authoritative `status` field: `segs = segs.map((seg, i) => i === s.idx ? { ...seg, zh: newZh, approved: data.translation?.status === 'approved', edited: true } : seg)`. This eliminates implicit auto-approval and ensures frontend respects explicit user approval workflows.

### 18. [MEDIUM] TypedDict mutability violation in sentence_pipeline and ollama_engine
- **File**: backend/translation/sentence_pipeline.py:269
- **Symptom**: Post-processor modifies TranslatedSegment TypedDict in-place using `{**results[idx], 'flags': existing_flags}` assignment, violating project immutability mandate
- **Root cause**: TranslatedSegment is defined as TypedDict (immutable contract) at translation/__init__.py:6. Code at line 269 constructs a new dict via unpacking (`{**results[idx], ...}`) but this pattern appears throughout post-processor, violating the stated 'NEVER mutate shared objects' requirement
- **Trigger**: translate_with_sentences called with segments that fail validate_batch checks (repetition, hallucination, missing translation); code attempts to append 'review' flag to results[idx]
- **Evidence**: sentence_pipeline.py:269 - `results[idx] = {**results[idx], "flags": existing_flags}` mutates the list by replacing elements. The unpacking creates a new dict, but the list assignment mutates the containing list. No guard prevents this; the pattern is simply inconsistent with post_processor.py:97-103 which correctly returns a new list via list comprehension. ollama_engine.py:465 has identical anti-pattern.
- **Fix**: In sentence_pipeline.py, replace the in-place mutation loop (lines 265-269) with a functional pattern matching post_processor._mark_bad_segments: return a new list via list comprehension filtering by bad_set. Same fix needed in ollama_engine.py:464-468 (_enrich_pass method) - return a new list instead of mutating enriched_total.

### 19. [MEDIUM] Concurrent requests to retry_job can bypass attempt_count cap via TOCTOU race
- **File**: backend/jobqueue/routes.py:176
- **Symptom**: Two concurrent POST /api/queue/<job_id>/retry requests on the same failed job can both pass the attempt_count check and create separate retry jobs, effectively allowing one extra execution beyond the R5_MAX_JOB_RETRY cap.
- **Root cause**: retry_job checks attempt_count at line 176 but does not acquire a transaction lock. Between the check and the enqueue at line 181, another request can check the same job and both will pass the check. When they both call enqueue with the same parent_job_id, both new jobs will have attempt_count = parent + 1, allowing both to execute.
- **Trigger**: 1. Job J has status='failed', attempt_count=2, cap=3
2. Request A calls retry_job(J), reaches line 176, check (2 >= 3) = False, passes
3. Request B calls retry_job(J), reaches line 176, check (2 >= 3) = False, passes (both read stale attempt_count)
4. Request A executes enqueue (parent_job_id=J), creates job with attempt_count=3
5. Request B executes enqueue (parent_job_id=J), creates another job with attempt_count=3
6. Both new jobs with attempt_count=3 can execute (3 >= 3 cap check passes only on NEXT retry)
- **Evidence**: backend/jobqueue/routes.py:166-187 (retry_job) - line 176 checks attempt_count without a lock; line 181 calls enqueue which re-reads the parent at db.py:63. No transaction isolation or explicit locking guards the TOCTOU window. Confirmed with concurrent test: two POST /api/queue/job_id/retry on job with attempt_count=2, cap=3 both create jobs with attempt_count=3. See also db.py:50-71 (insert_job) which reads parent outside transaction.
- **Fix**: Move the cap check into insert_job (db.py) as an atomic operation: pass max_retry to insert_job, and perform both the parent read and cap check within a single transaction with isolation. Alternatively, use SELECT ... FOR UPDATE in SQLite to lock the parent row during the check-and-insert window. In routes.py:retry_job, remove the attempt_count check and rely on insert_job to return an error if the cap is violated.

### 20. [MEDIUM] _translate_second_handler mutates shared registry objects in violation of immutability mandate
- **File**: backend/app.py:477
- **Symptom**: The handler directly mutates row objects that are references into the live _file_registry using row.setdefault() and row[f"{target}_text"] = ... at lines 477-481. While the lock is held, this violates the project's mandate to 'NEVER mutate shared objects' and could cause issues with concurrent API reads of the same registry entry.
- **Root cause**: The handler re-acquires the lock at line 471 and then directly mutates row dicts in the live_translations list using row.setdefault()[target] = {...} and row[f"{target}_text"] = ..., modifying the shared objects in place instead of rebuilding immutable structures.
- **Trigger**: 1. POST /api/files/file1/translate-second {"lang": "en"} enqueues job
2. Job runs _translate_second_handler, reaches line 471
3. Handler mutates row objects via setdefault() and direct assignment (lines 477-481)
4. Concurrently, API endpoint (e.g., GET /api/files/file1) reads _file_registry[file1]["translations"]
5. API sees partially-mutated row objects due to lack of deep copying
- **Evidence**: File: backend/app.py, lines 471-486. The handler code: live_translations = _file_registry.get(file_id, {}).get("translations") or [] (line 472 - gets reference, not copy); then row.setdefault("by_lang", {})[target] = {...} (line 477) and row[f"{target}_text"] = translated_text (line 482) directly mutate shared row dicts. No guard creates new dict objects. Contrast with _auto_translate at line 3606 which calls _update_file(fid, translations=translated, ...) to replace the entire list, and with api_glossary_apply at line 2423 which does new_translations = list(translations) before modifying (line 2423). The API endpoint at lines 2612-2620 acquires lock at 2615, releases it at 2617 (end of with), then accesses entry.get("translations", []) at line 2619 WITHOUT lock, calling {**t, ...} at line 2609 which iterates the dict.
- **Fix**: In backend/app.py function _translate_second_handler (starting line 386), replace the direct mutation pattern at lines 471-486. Instead of mutating live_translations rows in place, create new_translations with deep-copied rows: Build new_translations as a list where each row is a new dict copy with the translation fields updated (by_lang[target] and <target>_text), then replace the registry entry's translations list via _file_registry[file_id]["translations"] = new_translations. This matches the pattern used in _auto_translate and other handlers that safely rebuild immutable structures.

### 21. [MEDIUM] KeyError when V6 file has null active_id at ASR dispatch
- **File**: backend/app.py:323
- **Symptom**: ASR handler crashes with KeyError when processing V6 files that have active_kind='pipeline_v6' but active_id is None
- **Root cause**: _register_file calls _current_active_snapshot() which returns (active_kind, active_id) where active_id can be None if no profile/pipeline is active. Line 816 assigns this None to active_id. Later at line 323, the code tries to access f["active_id"] with bracket notation instead of .get(), causing KeyError when active_id is None.
- **Trigger**: 1. Start system with no active profile/pipeline in settings.json (active_id=null). 2. Upload a media file—_register_file sets active_id=None. 3. Wait for ASR job to execute—_asr_handler reads kind='pipeline_v6' from registry. 4. Line 323 tries f["active_id"] → KeyError.
- **Evidence**: File: backend/app.py - Line 323 calls _pipeline_manager.get(f["active_id"]) without checking if f["active_id"] is None. This can occur when settings.json has active_kind="pipeline_v6" with missing/null active_id. The key exists in the dict (created at line 836), but its value can be None. No guard validates the precondition that active_id is non-null when kind=="pipeline_v6". Similar code at lines 3881, 3928 uses proper .get() with checks, showing this pattern is known in codebase.
- **Fix**: In backend/app.py at line 320-323, add validation before accessing active_id. Change from: `if kind == "pipeline_v6": pipeline = f.get("active_pipeline_snapshot") or _pipeline_manager.get(f["active_id"])` to: `if kind == "pipeline_v6": pipeline_id = f.get("active_id"); if not pipeline_id: raise RuntimeError(f"V6 file {file_id} has no active_id (active_kind=pipeline_v6, active_id={pipeline_id})"); pipeline = f.get("active_pipeline_snapshot") or _pipeline_manager.get(pipeline_id)`. Alternatively, use defensive pattern: `_pipeline_manager.get(f.get("active_id"))` as in lines 3881, 3928.

### 22. [MEDIUM] TOCTOU race condition: _mt_handler reads entry without holding lock across decisions
- **File**: backend/app.py:510-517
- **Symptom**: Registry entry is read while holding lock, lock is released, then entry is used for critical dispatch decisions without lock protection. Another thread could delete file or change active_kind between check and use.
- **Root cause**: Lines 510-511 acquire lock and read entry. Lock is released at end of with block. Lines 512-517 use entry to check _pending_second_lang and active_kind without re-acquiring lock. Between release and check, entry could be deleted or modified by another thread (e.g., _delete_file_entry, concurrent re-transcribe).
- **Trigger**: 1. Start a translation job for a file (sets entry._pending_second_lang or active_kind). 2. Simultaneously delete the file or change its active_kind via API. 3. _mt_handler releases lock after line 511. 4. Thread A deletes file, thread B checks entry.get('_pending_second_lang') on now-stale reference. 5. Entry object still exists in memory but registry is out of sync.
- **Evidence**: File: backend/app.py, Lines 510-517: Lock acquired and entry read at line 511, lock released at end of with block (line 511). Lines 512 and 517 then use entry.get() WITHOUT lock protection. The stale read can be demonstrated by: (1) Multiple MT jobs can be enqueued for the same file (confirmed at lines 382, 1954, 3803), (2) _translate_second_handler modifies _pending_second_lang at line 485 while holding lock, (3) Between line 511 release and line 512 check, entry._pending_second_lang could be cleared, causing wrong dispatch. Additionally, _auto_translate at line 3606 writes to registry without holding lock during the translation process, allowing concurrent modification. No guard exists to prevent multiple concurrent translation jobs from both reading and writing to the same file's registry entry.
- **Fix**: Minimal fix in _mt_handler: Hold _registry_lock across both dispatch decision checks (lines 512-517). Replace lines 510-524 to: (1) Acquire lock once at line 510, (2) Read entry and check _pending_second_lang, (3) If true, call _translate_second_handler then release lock and return, (4) Check active_kind, (5) If pipeline_v6, update registry (already holding lock), release lock and return, (6) Release lock before calling _auto_translate. This ensures entry state is consistent between check and use. Alternative: Re-acquire lock immediately before each use (lines 512 and 516) to reverify conditions, or copy entry.get() inline within lock to avoid stale reference issues.

### 23. [MEDIUM] Missing active_id cleanup in ProfileManager.delete()
- **File**: backend/profiles.py:292-293
- **Symptom**: When a profile is deleted, only legacy 'active_profile' field is cleared in settings.json, not the new 'active_id' field. If profile was set via active_id, stale reference remains.
- **Root cause**: ProfileManager.delete() on line 292 checks only settings.get('active_profile') == profile_id, not also checking and clearing settings.get('active_id'). When V6 mode uses active_id (not active_profile) and a profile is deleted, the stale active_id persists in settings.json.
- **Trigger**: 1. Set active_kind='profile', active_id='profile-123'. 2. Call delete('profile-123'). 3. Check settings.json—active_id='profile-123' still present. 4. Next get_active() call succeeds because get_active() has fallback (lines 345-349), but inconsistent state exists.
- **Evidence**: File: backend/profiles.py, lines 278-295 (delete method). Line 292 checks: if settings.get("active_profile") == profile_id, then clears only active_profile (line 293). Missing: check for and clear settings.get("active_id"). The set_active() method (lines 376-380) demonstrates both fields should be synchronized: it sets both "active_id" and "active_profile" to the same value. Proof of defect: Running test shows after delete(), settings.json contains stale active_id pointing to deleted profile. No guard exists elsewhere in delete() or delete_if_owned() to clean active_id.
- **Fix**: File: backend/profiles.py, method delete() (lines 292-293). Change: if settings.get("active_profile") == profile_id or settings.get("active_id") == profile_id: to check both fields, then clear both: self._write_settings({**settings, "active_profile": None, "active_id": None})

### 24. [MEDIUM] translation_progress at 100% never sets translation_status='done'
- **File**: frontend/index.html:5206
- **Symptom**: When translation completes and translation_progress event arrives with percent=100, the code fails to set translation_status='done'. The file card continues showing 'translating' status or displays no status until pipeline_timing event arrives. This causes out-of-order state transitions and stale UI.
- **Root cause**: Line 5206 only executes 'f.translation_status = translating' when 'd.percent < 100' is TRUE. When percent reaches 100, the condition is false and translation_status is never updated. The status is only set by pipeline_timing event on line 5215, creating a gap.
- **Trigger**: 1. Start translation on a file. 2. Monitor the file card as translation reaches 100%. 3. Observe that the badge does not show translation_status='done' or may show incomplete progress state until pipeline_timing fires.
- **Evidence**: File: frontend/index.html, lines 5202-5209. The buggy code: if (d.percent < 100) f.translation_status = 'translating'; only executes when percent < 100. When percent=100, no code path updates translation_status='done'. Confirmed via: (1) backend/app.py line 3599-3605 shows progress_callback is called with (total, total) before pipeline_timing is emitted, (2) fileStatusCategory (line 1988) returns 'translating' when f.status==='done' && f.translation_status==='translating', and (3) stageBadgeHtml case 'translating' (line 2000-2003) displays the badge as "翻譯中 {percent}%" instead of "✓ 完成".
- **Fix**: File: frontend/index.html, line 5206. Change: if (d.percent < 100) f.translation_status = 'translating'; to: if (d.percent < 100) f.translation_status = 'translating'; else if (d.percent === 100) f.translation_status = 'done'; This ensures that when translation_progress reaches 100%, translation_status is immediately set to 'done', eliminating the visual state gap before pipeline_timing arrives.

### 25. [MEDIUM] unapproveSegment uses s.idx to index segs array instead of array position
- **File**: frontend/proofread.html:2390
- **Symptom**: When user clicks 'Unapprove' button on a segment, the local state update silently fails if segment's s.idx does not equal its array position. The backend call succeeds, but frontend segs array is not updated, creating state mismatch.
- **Root cause**: unapproveSegment(idx) is called with s.idx parameter from renderDetail() (line 2079), but then tries to access segs[idx] assuming idx is the array position. In V6 mode where idx might differ from array position, `segs[idx]` returns undefined and the if guard prevents update: `if (segs[idx]) segs[idx].approved = false;`
- **Trigger**: (1) Open V6 file where translation.idx does not equal array position (if backend ever supports reordering). (2) Click Unapprove on any segment. (3) Observe: segment still shows approved checkmark in UI despite backend unapprove succeeding. (4) Verify with renderProgress() showing outdated count.
- **Evidence**: File: frontend/proofread.html, Lines 2079 and 2390-2392. Line 2079 passes `${s.idx}` to `unapproveSegment()`. Line 2392 does `if (segs[idx]) segs[idx].approved = false;` treating idx as array position. Contrast with lines 2528 and 2569 which use `segs.map((seg, i) => i === s.idx ? ...)` to safely handle potential idx/position divergence. Backend review confirms app.py never includes idx in translated API responses, so currently s.idx always equals array position. No guard exists to detect if idx != array position.
- **Fix**: File: frontend/proofread.html, function unapproveSegment (line 2389-2398). Change line 2392 from `if (segs[idx]) segs[idx].approved = false;` to `segs = segs.map((seg, i) => i === idx ? { ...seg, approved: false } : seg);` to consistently match the pattern used in fbReplaceCurrent/fbReplaceAll and properly handle any future idx != array position scenario.

## Refuted / false positive (5)
- **Field access inconsistency in alignment_pipeline: glossary 'source'/'target' without fallback** [backend/translation/alignment_pipeline.py:84] — The candidate bug is a false positive. While the claim identifies that _filter_glossary_for_batch only validates 'source' field existence (not 'target'), this is not actually a defect because: (1) The glossary validation layer in GlossaryManager.validate_entry() (glossary.py:184-230) REQUIRES both 'source' and 'target' to be non-empty strings; (2) All entry creation/update paths (add_entry, update_entry, import_csv, create) call validate_entry and reject invalid entries; (3) Glossary files are stored as validated JSON with no code path that could create entries missing 'target'; (4) Old schema files (en/zh fields) are explicitly ignored on load. The asymmetric validation in _filter_glossary_for_batch is safe because upstream validation guarantees any entry with 'source' also has 'target'. The fallback to old field names in build_anchor_prompt line 84-85 is defensive programming for backwards compatibility, not a bug fix.
- **_lastActiveTranscriptIdx variable shadowing causes stale active-row tracking** [frontend/index.html:4315] — The candidate's claim of variable shadowing is incorrect. In JavaScript, let/const declarations at the top level of a script scope are hoisted, meaning the variable _lastActiveTranscriptIdx exists throughout the entire script scope even though its declaration appears at line 4315. The earlier uses at lines 3975, 3998, and 4035 access this same top-level variable, not separate shadowed variables. All functions (wireTranscriptScrollListener, renderTranscriptTab, syncActiveTranscriptRow) are defined at the same indentation level (4 spaces) within the main script scope and access the identical variable. Additionally, the code flow is intentionally designed to reset _lastActiveTranscriptIdx to -1 after rendering the HTML but before syncing with the current video time, which is correct behavior. No guard is needed because no shadowing exists.
- **Direct mutation of segment object properties violates immutability mandate** [frontend/proofread.html:2252-2255] — The mutation in saveEditIfDirty (lines 2249-2255) is NOT a real bug. While the code does mutate the segment object directly (s.zh, s.edited, s.cps, s.flags), this causes no functional problems because: (1) The mutations happen within the same JavaScript reference context where s === segs[cursorIdx] throughout the async operation; (2) All rendering functions (renderSegList, renderProgress, etc.) are called immediately after the mutation and correctly read the updated values from the same segs array; (3) This is vanilla JavaScript with direct DOM manipulation, not a state-managed framework like React that relies on immutability to detect changes. The candidate's claim of "violating the project mandate to NEVER mutate shared objects" is unsupported—no such mandate exists in the codebase. While other parts of the code (find-and-replace at lines 2528, 2569) use immutable patterns, saveEditIfDirty's mutations don't cause stale references or state inconsistency. The data flows correctly from mutation to re-render.
- **Inconsistent index mapping in find-replace segs.map() callback** [frontend/proofread.html:2528, 2569] — While the code is fragile and relies on an implicit assumption that segment idx property always equals array position, this assumption holds in the current implementation because: (1) fbMatches stores array indices directly from fbSearch line 2479, (2) segs.idx is always initialized to match array position (either t.idx which backend sets to i, or directly to i), (3) the segs array is never reordered or filtered before fbReplaceCurrent is called, (4) the backend translation store maintains insertion order. The code works correctly today, though it is defensive-coding-smell territory. No actual bug can be triggered without changes to backend data ordering or frontend filtering logic.
- **saveEditIfDirty mutates segment flags array in-place** [frontend/proofread.html:2254-2255] — The candidate claims the code "mutates the original array object rather than creating a new one". This is technically incorrect. Line 2254 uses `.filter()` which creates a NEW array, not an in-place mutation. Line 2255 then mutates this NEW array via `.push()`. No other code holds a reference to the old flags array, and all rendering functions read `s.flags` after the update, so they correctly see the updated array. The code pattern is not idiomatic but does not constitute a functional defect.