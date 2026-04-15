# Test Isolation + Registry Recovery + Retry Verification — Design Spec

**Date:** 2026-04-15
**Status:** Approved (brainstorming phase complete)
**Context:** Disaster recovery from a test-isolation bug that wiped `backend/data/registry.json` during a pytest run. Combines prevention (isolate tests), recovery (rebuild registry from files on disk), and verification (confirm cloud retry logic works end-to-end).

---

## 1. Background

When `pytest tests/` runs, the fixtures in `test_proofreading.py` and `test_render_api.py` import the module-level `_file_registry` dict from `app.py` and inject test data. Any API call inside the test that invokes `_save_registry()` writes the (mostly-empty) in-memory state to the real `backend/data/registry.json`, overwriting user data. Subtitle segments, translations, and proof-reading edits for ~12 uploaded files were permanently lost. The MP4 files themselves remain on disk in `data/uploads/`.

This spec covers three related sub-tasks:

1. **Prevention** — auto-isolate all future pytest runs so the real `DATA_DIR` is never touched
2. **Recovery** — rebuild minimal registry entries from files on disk so the user can re-trigger transcription via the UI
3. **Verification** — manual end-to-end smoke test that confirms the Ollama Cloud retry logic (already merged on `feature/ollama-cloud-models`) handles transient 502/503/504 errors correctly

## 2. Non-Goals

- No recovery of lost subtitle segments, translations, or edits (they were never persisted outside `registry.json`)
- No refactor of `_file_registry` into an `AppState` class — too broad for this fix
- No new UI for triggering the rebuild — a CLI script is sufficient for a one-shot recovery
- No change to `retry_on_5xx` logic itself (already implemented and unit-tested)

## 3. Part A — Test Isolation Fix

### 3.1 Root cause

`app.py:46` defines `DATA_DIR = Path(__file__).parent / "data"` as a module-level constant. `_save_registry()` writes to `DATA_DIR / "registry.json"`. Tests that import `_file_registry` and trigger any API endpoint that calls `_save_registry()` end up writing the test's view of the dict to the real path on disk.

### 3.2 Fix — autouse fixture in `backend/tests/conftest.py`

Extend `conftest.py` with an autouse fixture that monkey-patches `app.DATA_DIR` (and its downstream `UPLOAD_DIR`, `RENDERS_DIR`, `RESULTS_DIR`) to a pytest `tmp_path`, clears `_file_registry`, and restores both on teardown.

```python
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _isolate_app_data(tmp_path, monkeypatch):
    """Auto-isolate every test from the real DATA_DIR.

    Prevents tests from overwriting backend/data/registry.json when they
    call API endpoints that invoke _save_registry(). Applies to every test
    in the suite without requiring opt-in from individual fixtures.
    """
    import app

    test_data_dir = tmp_path / "data"
    (test_data_dir / "uploads").mkdir(parents=True)
    (test_data_dir / "renders").mkdir()
    (test_data_dir / "results").mkdir()

    monkeypatch.setattr(app, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(app, "UPLOAD_DIR", test_data_dir / "uploads")
    monkeypatch.setattr(app, "RENDERS_DIR", test_data_dir / "renders")
    monkeypatch.setattr(app, "RESULTS_DIR", test_data_dir / "results")

    original_registry = app._file_registry.copy()
    app._file_registry.clear()

    yield

    app._file_registry.clear()
    app._file_registry.update(original_registry)
```

### 3.3 Why autouse

- **Defense in depth.** New tests get isolated automatically without any opt-in.
- **Zero change to existing test fixtures.** `test_proofreading.py`, `test_render_api.py`, and all others continue to mutate `_file_registry` directly — the fixture just redirects where the writes land.
- **Deterministic teardown.** `monkeypatch` auto-restores the patched attributes; the `try/yield/cleanup` pattern restores `_file_registry` even on test failure.

### 3.4 Verification

- Add a new test `test_isolate_fixture_redirects_registry_writes` that:
  1. Mutates `_file_registry`
  2. Calls `_save_registry()`
  3. Asserts the real `backend/data/registry.json` is unchanged
  4. Asserts the temp `registry.json` in `tmp_path` contains the test entry
- Run the existing 226-test suite to confirm no regressions.
- Before committing, git-check `backend/data/registry.json` — it must not appear in `git status`.

## 4. Part B — Registry Rebuild Script

### 4.1 Script location and interface

File: `backend/tools/rebuild_registry.py`

```
python tools/rebuild_registry.py              # rebuild (overwrites current registry)
python tools/rebuild_registry.py --dry-run    # preview only, no write
python tools/rebuild_registry.py --merge      # keep existing entries, add missing
```

### 4.2 Reconstructable fields

| Field | Source | Notes |
|---|---|---|
| `id` | filename stem | matches `^[0-9a-f]{12}$` |
| `stored_name` | filename | `bbd1b34cb2ca.mp4` |
| `original_name` | = `stored_name` | **PERMANENTLY LOST** — fallback only |
| `size` | `path.stat().st_size` | |
| `uploaded_at` | `path.stat().st_mtime` | approximate; mtime may be after upload |
| `status` | `"uploaded"` | frontend surfaces "待轉譯" |
| `segments` | `[]` | empty; requires re-transcription |
| `text` | `""` | empty |
| `error` | `None` | |
| `model` | `None` | |
| `backend` | `None` | |

Fields deliberately omitted (not set): `translations`, `translation_status`, `edited_at`. The frontend must handle their absence — it already does (treats missing `translation_status` as "待翻譯").

### 4.3 Scan pattern

Only match `^[0-9a-f]{12}\.(mp4|mov|mxf|mkv|webm)$` (case-insensitive). This excludes:

- `audio_*.wav` (intermediate extraction output)
- `chunk_*.webm` (live recording chunks from the old removed feature)
- Any filename that doesn't conform to the 12-hex-char file-ID convention

### 4.4 Merge vs overwrite semantics

- **Default (overwrite):** Any existing `registry.json` is replaced. Used when the registry is wiped and needs full rebuild.
- **`--merge`:** Existing entries take precedence over scanned ones (`{**scanned, **existing}`). Used to add new files without disturbing existing metadata.
- **`--dry-run`:** Prints the plan — scan count, existing count (if merging), final count, and one line per entry with `id`, `stored_name`, `size`. Writes nothing.

### 4.5 Safety

- Script writes to `Path(__file__).parent.parent / "data" / "registry.json"` — the real location.
- The autouse fixture from Part A does NOT apply here (this is a standalone script, not a test).
- Before overwriting, script does not back up the existing registry (the existing one is already wiped; if the user wants a snapshot, they can copy it before running).

### 4.6 Unit tests

New file `backend/tests/test_rebuild_registry.py` covering:

1. `test_scan_uploads_matches_file_id_pattern` — creates fake files in a tmp dir (valid IDs, invalid names, audio/chunk files, non-video extensions), asserts only the valid ones appear in the scan result with correct fields.
2. `test_dry_run_does_not_write` — invokes main with `--dry-run`, asserts `registry.json` is not created.
3. `test_overwrite_replaces_existing` — existing `registry.json` with one entry, scan yields different entries, after run the file has only scanned entries.
4. `test_merge_preserves_existing` — existing `registry.json` with one entry, scan yields a different entry, after `--merge` run the file has both entries, existing entry's fields are preserved.

These tests use `tmp_path` and invoke the script's functions directly (no subprocess) so they inherit the autouse isolation from Part A.

## 5. Part C — End-to-End Retry Verification

### 5.1 Pre-conditions

1. Part A merged and tests pass
2. Part B script executed, `registry.json` contains 12 entries
3. Backend restarted with `feature/ollama-cloud-models` branch code
4. Active profile is `dev-default`: `qwen3.5-397b-cloud` + cantonese style
5. User is signed in to Ollama Cloud (`ollama signin` previously run)

### 5.2 Manual test steps

| # | Action | Expected |
|---|---|---|
| 1 | Refresh frontend; verify 12 files appear with status "待轉譯" | File list populated from rebuilt registry |
| 2 | Pick one file, click "▶ 轉譯" | Transcription starts, progress bar shows ETA |
| 3 | Transcription completes; auto-translate runs | Translation status transitions `待翻譯 → 翻譯中 → 翻譯完成` |
| 4 | Open proof-reading editor for that file | Side-by-side video + Cantonese translation segments, each ≤16 chars |
| 5 | Check server log (`/tmp/app_server.log`) | No unhandled exceptions; if any `[ollama] retry` line appeared, a success followed it |

### 5.3 Observability improvement (recommended)

Add `print(f"[ollama] retry attempt {attempt + 1} after HTTP {e.code}", file=sys.stderr)` inside the existing retry loop in `_call_ollama`. This makes the retry behavior visible in the server log — without it, users seeing "slow translation" have no way to tell whether retries are happening or something else is wrong.

### 5.4 Success criteria

- At least one file completes the full `transcribe → auto-translate → proof-read` pipeline
- If any transient 502/503/504 occurred during the translation batches, the retry recovered and the overall translation succeeded
- If no 502/503/504 occurred, the happy-path pipeline still produced correct output (the retry code is dormant but harmless)

## 6. Acceptance Criteria (all parts)

- [ ] `backend/tests/conftest.py` has an autouse `_isolate_app_data` fixture
- [ ] New test `test_isolate_fixture_redirects_registry_writes` passes
- [ ] `pytest tests/` completes with 0 failures
- [ ] After running the full test suite, `git status backend/data/registry.json` shows no modification
- [ ] `backend/tools/rebuild_registry.py` exists with `--dry-run` and `--merge` flags
- [ ] `backend/tests/test_rebuild_registry.py` has 4 tests covering scan/dry-run/overwrite/merge, all passing
- [ ] Script executed against the real `uploads/` directory restores 12 registry entries
- [ ] `_call_ollama` prints `[ollama] retry` diagnostic lines to stderr when retrying
- [ ] Manual smoke test completes: one file runs transcribe → translate → proof-read successfully with cloud engine

## 7. Out of Scope

- Recovering lost segments, translations, or edits (unrecoverable)
- Backing up `registry.json` before the rebuild script runs (user can copy it manually if desired)
- Automatic registry corruption detection or repair at backend startup
- UI button for invoking the rebuild script
- Refactoring `_file_registry` into an injectable class
- Bulk-trigger script for re-transcribing all 12 files (user clicks through the UI)
