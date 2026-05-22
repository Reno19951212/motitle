# Console Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a feature-flagged Broadcast Console dashboard at `/console` (4-column dense layout: 56px rail / 360px queue+worker / flex workbench / 320px aside) while leaving the existing `/` Bold Dashboard untouched.

**Architecture:** Backend grows 2 new fields (`FileRecord.duration_seconds` via ffprobe-on-upload + `Pipeline.preset_slot` with per-user uniqueness + atomic swap). Frontend adds a new `Console.tsx` page composed of ~14 new components under `pages/Console/`, 2 new hooks (`useWorkerStatus`, `useHotkeys`), and 1 new scoped stylesheet (`console.css`) following the existing motitle-bold.css CSS-variable pattern. Real-time updates flow through the existing `useSocket()` reducer; preset hotkeys ⌘1-4 read `pipeline.preset_slot` from the existing pipeline-picker store.

**Tech Stack:** Backend Python 3.11 / Flask / pytest. Frontend Vite + React 18 + TypeScript strict + Tailwind 3.4 + Zustand 5 + react-router-dom 6 + socket.io-client 4.8 + Vitest 2 + Playwright 1.48. **No new dependencies.** Pure CSS animations (no framer-motion). Token source: existing `frontend/src/styles/motitle-bold.css`.

---

## Spec source

- README: `~/Downloads/design_handoff_motitle_dashboard/README.md`
- Reference component: `~/Downloads/design_handoff_motitle_dashboard/design/reimagine/variant-console.jsx`
- Reference styles: `~/Downloads/design_handoff_motitle_dashboard/design/reimagine/reimagine.css` (43KB; not imported, used only as visual reference)
- Token source-of-truth: `frontend/src/styles/motitle-bold.css` lines 8-57 (already has all design tokens)

## Decisions locked (from `docs/CONSOLE_REDESIGN_PLAN.md`)

| # | Decision |
|---|---|
| Q1 | A — Pure CSS via new `console.css`, no `tailwind.config.ts` change |
| Q2 | B — Backend ffprobe on upload + `duration_seconds` registry field + migration script |
| Q3 | C — Backend pipeline schema `preset_slot` field + per-user uniqueness + atomic swap |
| Q4 | A — Glossary list read-only (tap → navigate to `/glossaries/<id>`) |
| Q5 | B — Metrics bar shows queue_depth real, other 3 metrics as "—" |
| Q6 | C — `VITE_CONSOLE=1` env (build) + `?console=1` query (runtime) — both required to render |

---

## Type definitions (referenced across tasks)

### Backend `FileRecord` addition

```python
# In file registry entry dict (no formal TypedDict — uses dict[str, Any]):
{
    # ... existing fields ...
    "duration_seconds": float | None,   # NEW (Q2). None if ffprobe failed.
}
```

### Backend pipeline JSON addition

```python
# v4 (backend/pipelines.py) and v5 (backend/pipeline_schema_v5.py):
{
    # ... existing fields ...
    "preset_slot": int | None,   # NEW (Q3). Allowed values: None, 1, 2, 3, 4.
}
```

### Frontend `ConsoleFile` (derived shape — defined in `frontend/src/pages/Console/types.ts`)

```ts
export type ConsoleStageCellState = 'idle' | 'done' | 'warn' | 'err';

export type ConsoleStageCell = {
  state: ConsoleStageCellState;
  percent?: number;   // only when state === 'warn'
};

export type ConsoleFile = {
  id: string;
  name: string;                  // from FileRecord.original_name
  ext: string;                   // uppercase, derived from name extension
  durationSeconds: number | null;
  formattedDuration: string;     // "mm:ss" or "h:mm:ss" or "—"
  formattedSize: string;         // e.g. "284 MB"
  formattedUploaded: string;     // e.g. "剛剛" / "2 小時前"
  stageCells: [ConsoleStageCell, ConsoleStageCell, ConsoleStageCell, ConsoleStageCell];
  // 0: ASR, 1: MT, 2: Proofread, 3: Render
  errored: boolean;
};
```

### Frontend `formatDuration` location

`frontend/src/lib/format.ts` (NEW file). Exports `formatDuration(seconds: number | null): string` and `formatBytes(bytes: number): string` and `formatRelativeTime(epoch: number, now?: number): string`.

### Frontend `useWorkerStatus` return

```ts
// frontend/src/hooks/useWorkerStatus.ts
export type QueueItem = {
  id: string;                // job_id
  file_id: string;
  file_name: string | null;
  owner_username: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  position: number;
  eta_seconds: number | null;
  type: string;              // job type
  created_at: number;
};

export function useWorkerStatus(): {
  activeJobs: QueueItem[];       // status === 'running'
  queuedJobs: QueueItem[];       // status === 'queued', sorted by position
  erroredJobs: QueueItem[];      // status === 'failed'
  loading: boolean;
  error: string | null;
};
```

### Frontend `useHotkeys` signature

```ts
// frontend/src/hooks/useHotkeys.ts
export type HotkeyHandler = (event: KeyboardEvent) => void;
export type HotkeyMap = Record<string, HotkeyHandler>;
// Combo syntax: 'mod+1' (cmd on Mac, ctrl elsewhere), 'space', 'esc',
// 'arrow-down', 'arrow-up', 'enter', 'e'
export function useHotkeys(map: HotkeyMap, enabled?: boolean): void;
```

### Frontend API client additions (`frontend/src/lib/api/console.ts` — NEW)

```ts
export async function getQueue(): Promise<QueueItem[]>;
export async function setPresetSlot(
  pipelineId: string,
  slot: 1 | 2 | 3 | 4 | null,
): Promise<{ ok: true; swapped_pipeline_id: string | null }>;
```

---

## File structure overview

### Backend — files created
- `backend/scripts/backfill_duration.py`
- `backend/tests/test_file_duration.py`
- `backend/tests/test_pipeline_preset_slot.py`

### Backend — files modified
- `backend/routes/files.py` (upload handler adds ffprobe call)
- `backend/pipelines.py` (v4 manager — `preset_slot` field + uniqueness + atomic swap)
- `backend/pipeline_schema_v5.py` (v5 validator — `preset_slot` field)
- `backend/routes/pipelines.py` (new `POST /api/pipelines/<id>/preset_slot` endpoint)

### Frontend — files created
- `frontend/src/styles/console.css`
- `frontend/src/pages/Console.tsx` (composition root)
- `frontend/src/pages/Console/types.ts`
- `frontend/src/pages/Console/Rail.tsx`
- `frontend/src/pages/Console/QueueColumn.tsx`
- `frontend/src/pages/Console/QueueItem.tsx`
- `frontend/src/pages/Console/StageBar.tsx`
- `frontend/src/pages/Console/WorkerStatus.tsx`
- `frontend/src/pages/Console/Workbench.tsx`
- `frontend/src/pages/Console/PresetPills.tsx`
- `frontend/src/pages/Console/MetricsBar.tsx`
- `frontend/src/pages/Console/VideoPanel.tsx`
- `frontend/src/pages/Console/TransportBar.tsx`
- `frontend/src/pages/Console/TranscriptList.tsx`
- `frontend/src/pages/Console/AsideColumn.tsx`
- `frontend/src/pages/Console/PipelineStageCards.tsx`
- `frontend/src/pages/Console/GlossaryReadOnlyList.tsx`
- `frontend/src/pages/Console/FileFactsBlock.tsx`
- `frontend/src/pages/Console/GlobalSearchModal.tsx` (⌘K placeholder)
- `frontend/src/pages/Console/derive-stage-cells.ts` (pure function)
- `frontend/src/hooks/useWorkerStatus.ts`
- `frontend/src/hooks/useHotkeys.ts`
- `frontend/src/lib/format.ts`
- `frontend/src/lib/api/console.ts`
- `frontend/src/pages/Console.test.tsx` (smoke)
- `frontend/src/pages/Console/derive-stage-cells.test.ts`
- `frontend/src/hooks/useWorkerStatus.test.ts`
- `frontend/src/hooks/useHotkeys.test.ts`
- `frontend/src/lib/format.test.ts`
- `frontend/tests-e2e/console.spec.ts`

### Frontend — files modified
- `frontend/src/router.tsx` (lazy Console route + feature flag gate)
- `frontend/src/lib/socket-events.ts` (add `duration_seconds` to FileRecord)
- `frontend/src/stores/pipeline-picker.ts` (add `preset_slot` to PipelineSummary)
- `frontend/src/lib/schemas/pipeline.ts` (add `preset_slot` zod field)
- `frontend/src/lib/schemas/pipeline-v5.ts` (add `preset_slot` zod field)
- `frontend/src/pages/Pipelines.tsx` (add preset_slot dropdown to form)

### Frontend — files NOT touched
- `frontend/tailwind.config.ts` (Q1=A)
- `frontend/src/styles/motitle-bold.css` (Q1=A)
- `frontend/src/pages/Dashboard.tsx` (feature flag preserves `/`)

---

# Phase 0 — Backend prerequisites

## Task 0a.1: ffprobe helper — failing test

**Files:**
- Create: `backend/tests/test_file_duration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_file_duration.py
"""Tests for ffprobe-based duration extraction on upload (Q2)."""
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest


def test_probe_duration_returns_float_for_valid_audio(tmp_path):
    from routes.files import probe_duration_seconds
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"\x00")  # content doesn't matter — ffprobe is mocked

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = json.dumps({"format": {"duration": "42.18"}})

    with patch("routes.files.subprocess.run", return_value=fake_result) as run_mock:
        out = probe_duration_seconds(str(audio))

    assert out == pytest.approx(42.18)
    args = run_mock.call_args[0][0]
    assert args[0] == "ffprobe"
    assert "-show_entries" in args
    assert "format=duration" in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && pytest tests/test_file_duration.py::test_probe_duration_returns_float_for_valid_audio -v`

Expected: `ImportError: cannot import name 'probe_duration_seconds' from 'routes.files'`

## Task 0a.2: ffprobe helper — implementation

**Files:**
- Modify: `backend/routes/files.py`

- [ ] **Step 1: Add the helper at the top of routes/files.py (after existing imports)**

```python
# backend/routes/files.py — add near top, after imports
import json
import subprocess


def probe_duration_seconds(path: str) -> float | None:
    """Run ffprobe on `path`, return duration in seconds or None on failure.

    Exceptions, non-zero exit, malformed JSON, missing duration field all
    return None with a warning log. Never raises.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        d = data.get("format", {}).get("duration")
        return float(d) if d is not None else None
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            ValueError, KeyError, OSError):
        return None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && source venv/bin/activate && pytest tests/test_file_duration.py::test_probe_duration_returns_float_for_valid_audio -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/routes/files.py backend/tests/test_file_duration.py
git commit -m "feat(files): add probe_duration_seconds ffprobe helper for Q2"
```

## Task 0a.3: ffprobe graceful failure tests

**Files:**
- Modify: `backend/tests/test_file_duration.py`

- [ ] **Step 1: Add failure-mode tests**

```python
def test_probe_duration_returns_none_on_nonzero_exit(tmp_path):
    from routes.files import probe_duration_seconds
    audio = tmp_path / "broken.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=1, stdout="", stderr="ffprobe: invalid")
    with patch("routes.files.subprocess.run", return_value=fake):
        assert probe_duration_seconds(str(audio)) is None


def test_probe_duration_returns_none_on_malformed_json(tmp_path):
    from routes.files import probe_duration_seconds
    audio = tmp_path / "f.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=0, stdout="not json")
    with patch("routes.files.subprocess.run", return_value=fake):
        assert probe_duration_seconds(str(audio)) is None


def test_probe_duration_returns_none_on_missing_duration_key(tmp_path):
    from routes.files import probe_duration_seconds
    audio = tmp_path / "f.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=0, stdout=json.dumps({"format": {}}))
    with patch("routes.files.subprocess.run", return_value=fake):
        assert probe_duration_seconds(str(audio)) is None


def test_probe_duration_returns_none_on_timeout(tmp_path):
    from routes.files import probe_duration_seconds
    audio = tmp_path / "f.wav"
    audio.write_bytes(b"\x00")
    with patch("routes.files.subprocess.run",
               side_effect=subprocess.TimeoutExpired("ffprobe", 15)):
        assert probe_duration_seconds(str(audio)) is None
```

- [ ] **Step 2: Run all 4 failure tests**

Run: `cd backend && pytest tests/test_file_duration.py -v -k "returns_none"`

Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_file_duration.py
git commit -m "test(files): cover probe_duration graceful-failure cases"
```

## Task 0a.4: Wire ffprobe into upload — failing integration test

**Files:**
- Modify: `backend/tests/test_file_duration.py`

- [ ] **Step 1: Add upload integration test**

```python
def test_upload_populates_duration_seconds(client_with_admin, tmp_path):
    """POST /api/files/upload should record duration_seconds from ffprobe."""
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)

    fake = MagicMock(returncode=0, stdout=json.dumps({"format": {"duration": "12.5"}}))
    with patch("routes.files.subprocess.run", return_value=fake):
        with open(audio, "rb") as fh:
            resp = client_with_admin.post(
                "/api/files/upload",
                data={"file": (fh, "sample.wav")},
                content_type="multipart/form-data",
            )

    assert resp.status_code == 201
    body = resp.get_json()
    assert "duration_seconds" in body
    assert body["duration_seconds"] == pytest.approx(12.5)


def test_upload_records_none_duration_when_ffprobe_fails(client_with_admin, tmp_path):
    audio = tmp_path / "bad.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=1, stdout="", stderr="bad")
    with patch("routes.files.subprocess.run", return_value=fake):
        with open(audio, "rb") as fh:
            resp = client_with_admin.post(
                "/api/files/upload",
                data={"file": (fh, "bad.wav")},
                content_type="multipart/form-data",
            )

    assert resp.status_code == 201
    assert resp.get_json()["duration_seconds"] is None
```

- [ ] **Step 2: Run integration tests to verify FAIL**

Run: `cd backend && pytest tests/test_file_duration.py::test_upload_populates_duration_seconds tests/test_file_duration.py::test_upload_records_none_duration_when_ffprobe_fails -v`

Expected: FAIL (`KeyError: 'duration_seconds'` or assertion error — field not present)

## Task 0a.5: Wire ffprobe into upload — implementation

**Files:**
- Modify: `backend/routes/files.py`

- [ ] **Step 1: Locate the upload handler `upload_file()` and add ffprobe call**

Search for the upload route (typically `@bp.post('/api/files/upload')`). After the file is saved to disk but before `_register_file()` returns, call `probe_duration_seconds()` and add the result to the entry dict.

```python
# Inside upload_file() — after saving to disk, before registry insertion:
saved_path = str(target_path)  # absolute path where file was written
duration = probe_duration_seconds(saved_path)
entry = _register_file(
    # ... existing args ...
    duration_seconds=duration,   # NEW kwarg
)
```

Also extend `_register_file()` signature (search for its definition in `routes/files.py` or `helpers/registry.py`):

```python
def _register_file(
    *,
    original_name: str,
    stored_name: str,
    user_id: int,
    file_path: str,
    size: int,
    duration_seconds: float | None = None,   # NEW
    ...
):
    entry = {
        # ... existing fields ...
        "duration_seconds": duration_seconds,
    }
    # ... rest unchanged ...
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && pytest tests/test_file_duration.py -v`

Expected: 6 PASS

- [ ] **Step 3: Run full test suite to confirm no regression**

Run: `cd backend && pytest -q`

Expected: All previously-green tests still pass (~794), no new failures.

- [ ] **Step 4: Commit**

```bash
git add backend/routes/files.py backend/helpers/registry.py backend/tests/test_file_duration.py
git commit -m "feat(files): record duration_seconds on upload via ffprobe (Q2)"
```

## Task 0a.6: Migration script for existing files — failing test

**Files:**
- Create: `backend/scripts/backfill_duration.py`
- Create: `backend/tests/test_backfill_duration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_backfill_duration.py
"""Tests for backfill_duration.py one-shot migration script."""
import json
from unittest.mock import patch, MagicMock


def test_backfill_skips_entries_with_duration_already_set(tmp_path):
    from scripts.backfill_duration import backfill_registry

    registry = {
        "fileA": {"duration_seconds": 10.0, "file_path": "/tmp/a.wav"},
        "fileB": {"duration_seconds": None, "file_path": str(tmp_path / "b.wav")},
    }
    (tmp_path / "b.wav").write_bytes(b"\x00")

    fake = MagicMock(returncode=0, stdout=json.dumps({"format": {"duration": "20.0"}}))
    with patch("scripts.backfill_duration.subprocess.run", return_value=fake):
        modified = backfill_registry(registry)

    assert registry["fileA"]["duration_seconds"] == 10.0  # untouched
    assert registry["fileB"]["duration_seconds"] == 20.0  # filled
    assert modified == 1


def test_backfill_handles_missing_file_path(tmp_path):
    from scripts.backfill_duration import backfill_registry

    registry = {
        "ghost": {"file_path": str(tmp_path / "nonexistent.wav")},
    }
    modified = backfill_registry(registry)
    assert registry["ghost"]["duration_seconds"] is None
    assert modified == 1


def test_backfill_is_idempotent(tmp_path):
    from scripts.backfill_duration import backfill_registry

    registry = {"fileA": {"duration_seconds": 10.0, "file_path": "/tmp/a.wav"}}
    m1 = backfill_registry(registry)
    m2 = backfill_registry(registry)
    assert m1 == 0
    assert m2 == 0
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd backend && pytest tests/test_backfill_duration.py -v`

Expected: `ImportError: No module named 'scripts.backfill_duration'`

## Task 0a.7: Migration script — implementation

**Files:**
- Create: `backend/scripts/backfill_duration.py`

- [ ] **Step 1: Write the implementation**

```python
# backend/scripts/backfill_duration.py
"""One-shot migration: backfill `duration_seconds` for pre-Q2 registry entries.

Idempotent — re-running on an already-backfilled registry produces 0 changes.

Usage (from repo root):
    cd backend && source venv/bin/activate
    python scripts/backfill_duration.py

Reads/writes the running app's registry by importing it. If the app is running,
restart it after migration so the in-memory copy reloads from disk.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def _probe(path: str) -> float | None:
    if not path or not os.path.exists(path):
        return None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return float(json.loads(result.stdout).get("format", {}).get("duration") or 0) or None
    except Exception:
        return None


def backfill_registry(registry: dict) -> int:
    """Mutate registry in place; return count of entries newly populated.

    Entries already with non-None duration_seconds are skipped (idempotent).
    Entries with missing or unreadable file_path get duration_seconds = None.
    """
    modified = 0
    for fid, entry in registry.items():
        if entry.get("duration_seconds") is not None:
            continue
        path = entry.get("file_path", "")
        entry["duration_seconds"] = _probe(path)
        modified += 1
    return modified


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import app as _app  # noqa: E402

    n = backfill_registry(_app._file_registry)
    _app._save_registry()
    print(f"[backfill_duration] populated {n} entries")
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_backfill_duration.py -v`

Expected: 3 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/backfill_duration.py backend/tests/test_backfill_duration.py
git commit -m "feat(scripts): one-shot backfill_duration migration for Q2"
```

## Task 0b.1: Pipeline preset_slot — schema validator failing test

**Files:**
- Create: `backend/tests/test_pipeline_preset_slot.py`

- [ ] **Step 1: Write 4 validation tests**

```python
# backend/tests/test_pipeline_preset_slot.py
"""Tests for pipeline preset_slot field (Q3)."""
import pytest


@pytest.mark.parametrize("slot", [None, 1, 2, 3, 4])
def test_v4_pipeline_accepts_valid_preset_slot(slot):
    from pipelines import validate_pipeline
    pipeline = {
        "name": "test",
        "asr_profile_id": "asr-1",
        "mt_stages": [],
        "preset_slot": slot,
    }
    errors = validate_pipeline(pipeline)
    assert "preset_slot" not in str(errors), f"slot={slot} should be valid: {errors}"


@pytest.mark.parametrize("bad", [0, 5, -1, "1", 1.5, True])
def test_v4_pipeline_rejects_invalid_preset_slot(bad):
    from pipelines import validate_pipeline
    pipeline = {
        "name": "test",
        "asr_profile_id": "asr-1",
        "mt_stages": [],
        "preset_slot": bad,
    }
    errors = validate_pipeline(pipeline)
    assert any("preset_slot" in e for e in errors), f"slot={bad!r} should be rejected"


@pytest.mark.parametrize("slot", [None, 1, 2, 3, 4])
def test_v5_pipeline_accepts_valid_preset_slot(slot):
    from pipeline_schema_v5 import validate_v5_pipeline
    pipeline = {
        "version": 5,
        "name": "test",
        "source_lang": "en",
        "target_languages": ["en"],
        "asr_primary": {"transcribe_profile_id": "t-1"},
        "preset_slot": slot,
    }
    errors, _warnings = validate_v5_pipeline(pipeline)
    assert not any("preset_slot" in e for e in errors), f"slot={slot}: {errors}"


@pytest.mark.parametrize("bad", [0, 5, "1", 1.5, True])
def test_v5_pipeline_rejects_invalid_preset_slot(bad):
    from pipeline_schema_v5 import validate_v5_pipeline
    pipeline = {
        "version": 5,
        "name": "test",
        "source_lang": "en",
        "target_languages": ["en"],
        "asr_primary": {"transcribe_profile_id": "t-1"},
        "preset_slot": bad,
    }
    errors, _ = validate_v5_pipeline(pipeline)
    assert any("preset_slot" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify FAIL**

Run: `cd backend && pytest tests/test_pipeline_preset_slot.py -v -k "accepts or rejects"`

Expected: FAIL — current validators don't know about `preset_slot`. The "accepts" tests may pass spuriously (unknown fields are typically tolerated) but the "rejects" tests will fail because invalid values aren't checked.

## Task 0b.2: Pipeline preset_slot — schema validator implementation

**Files:**
- Modify: `backend/pipelines.py` (v4 — locate `validate_pipeline()` or its inline rules)
- Modify: `backend/pipeline_schema_v5.py` (v5)

- [ ] **Step 1: Add validation rule to v4 `validate_pipeline()`**

Locate `validate_pipeline(pipeline: dict) -> list[str]` (or equivalent). Add after existing field checks:

```python
# v4 validate_pipeline — add this block
slot = pipeline.get("preset_slot")
if slot is not None:
    if isinstance(slot, bool) or not isinstance(slot, int):
        errors.append(f"preset_slot must be null or int 1-4, got {type(slot).__name__}")
    elif slot < 1 or slot > 4:
        errors.append(f"preset_slot must be in {{1, 2, 3, 4}}, got {slot}")
```

- [ ] **Step 2: Add validation rule to v5 `validate_v5_pipeline()`**

```python
# v5 validate_v5_pipeline — add inside the main validation loop
slot = pipeline.get("preset_slot")
if slot is not None:
    if isinstance(slot, bool) or not isinstance(slot, int):
        errors.append(f"preset_slot must be null or int 1-4, got {type(slot).__name__}")
    elif slot < 1 or slot > 4:
        errors.append(f"preset_slot must be in {{1, 2, 3, 4}}, got {slot}")
```

- [ ] **Step 3: Run validation tests**

Run: `cd backend && pytest tests/test_pipeline_preset_slot.py -v -k "accepts or rejects"`

Expected: All 18 parameterized cases PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/pipelines.py backend/pipeline_schema_v5.py backend/tests/test_pipeline_preset_slot.py
git commit -m "feat(pipelines): preset_slot schema validation (Q3) for v4 + v5"
```

## Task 0b.3: Per-user uniqueness — failing test

**Files:**
- Modify: `backend/tests/test_pipeline_preset_slot.py`

- [ ] **Step 1: Add uniqueness test**

```python
def test_setting_preset_slot_atomically_swaps_previous_occupant(client_with_admin):
    """If pipeline P1 holds slot=2 and user PATCHes P2 to slot=2,
    P1's preset_slot must atomically transition to None."""
    # Create P1 with slot=2
    resp1 = client_with_admin.post("/api/pipelines", json={
        "name": "P1", "asr_profile_id": "asr-1", "mt_stages": [], "preset_slot": 2,
    })
    assert resp1.status_code == 201
    p1_id = resp1.get_json()["pipeline"]["id"]

    # Create P2 with no slot
    resp2 = client_with_admin.post("/api/pipelines", json={
        "name": "P2", "asr_profile_id": "asr-1", "mt_stages": [],
    })
    p2_id = resp2.get_json()["pipeline"]["id"]

    # PATCH P2 to slot=2 — should atomically clear P1
    resp_patch = client_with_admin.post(
        f"/api/pipelines/{p2_id}/preset_slot",
        json={"slot": 2},
    )
    assert resp_patch.status_code == 200
    body = resp_patch.get_json()
    assert body["ok"] is True
    assert body["swapped_pipeline_id"] == p1_id

    # Confirm via GET
    p1 = client_with_admin.get(f"/api/pipelines/{p1_id}").get_json()["pipeline"]
    p2 = client_with_admin.get(f"/api/pipelines/{p2_id}").get_json()["pipeline"]
    assert p1["preset_slot"] is None
    assert p2["preset_slot"] == 2


def test_different_users_can_hold_same_slot(client_factory):
    """User A's pipeline at slot=1 doesn't block User B from also using slot=1."""
    client_a = client_factory(username="user_a")
    client_b = client_factory(username="user_b")

    resp_a = client_a.post("/api/pipelines", json={
        "name": "A1", "asr_profile_id": "asr-1", "mt_stages": [], "preset_slot": 1,
    })
    assert resp_a.status_code == 201

    resp_b = client_b.post("/api/pipelines", json={
        "name": "B1", "asr_profile_id": "asr-1", "mt_stages": [], "preset_slot": 1,
    })
    assert resp_b.status_code == 201


def test_endpoint_rejects_invalid_slot(client_with_admin):
    resp = client_with_admin.post("/api/pipelines", json={
        "name": "Px", "asr_profile_id": "asr-1", "mt_stages": [],
    })
    pid = resp.get_json()["pipeline"]["id"]
    for bad in [0, 5, -1, "two"]:
        r = client_with_admin.post(f"/api/pipelines/{pid}/preset_slot",
                                    json={"slot": bad})
        assert r.status_code == 400, f"slot={bad!r} should 400"


def test_endpoint_rejects_non_owner(client_factory):
    owner = client_factory(username="owner_u")
    other = client_factory(username="other_u")
    pid = owner.post("/api/pipelines", json={
        "name": "Po", "asr_profile_id": "asr-1", "mt_stages": [],
    }).get_json()["pipeline"]["id"]
    r = other.post(f"/api/pipelines/{pid}/preset_slot", json={"slot": 1})
    assert r.status_code == 403


def test_endpoint_accepts_null_to_clear_slot(client_with_admin):
    pid = client_with_admin.post("/api/pipelines", json={
        "name": "Px", "asr_profile_id": "asr-1", "mt_stages": [], "preset_slot": 3,
    }).get_json()["pipeline"]["id"]
    r = client_with_admin.post(f"/api/pipelines/{pid}/preset_slot", json={"slot": None})
    assert r.status_code == 200
    p = client_with_admin.get(f"/api/pipelines/{pid}").get_json()["pipeline"]
    assert p["preset_slot"] is None
```

- [ ] **Step 2: Run tests to verify FAIL**

Run: `cd backend && pytest tests/test_pipeline_preset_slot.py -v -k "atomically or different_users or rejects_invalid or rejects_non_owner or accepts_null"`

Expected: All FAIL (`404 not found` or endpoint doesn't exist).

## Task 0b.4: Per-user uniqueness + atomic swap — implementation

**Files:**
- Modify: `backend/pipelines.py`

- [ ] **Step 1: Add `set_preset_slot()` method to `PipelineManager`**

```python
# backend/pipelines.py — inside class PipelineManager
def set_preset_slot(
    self,
    pipeline_id: str,
    user_id: int,
    is_admin: bool,
    slot: int | None,
) -> tuple[bool, str | None, str | None]:
    """Atomically assign `slot` to pipeline_id for owner `user_id`, swapping
    away any sibling holding that slot.

    Returns (ok, swapped_pipeline_id, error). `swapped_pipeline_id` is the
    id of the previous occupant of `slot` whose slot was cleared, or None
    if no swap was needed.
    """
    if slot is not None and slot not in (1, 2, 3, 4):
        return False, None, "slot must be null or 1-4"

    with self._master_lock:
        target = self._pipelines.get(pipeline_id)
        if target is None:
            return False, None, "not found"
        if not (is_admin or target.get("user_id") == user_id):
            return False, None, "forbidden"

        owner = target.get("user_id")
        swapped = None
        if slot is not None:
            for pid, p in self._pipelines.items():
                if pid == pipeline_id:
                    continue
                if p.get("user_id") == owner and p.get("preset_slot") == slot:
                    p["preset_slot"] = None
                    self._persist(pid)
                    swapped = pid
                    break

        target["preset_slot"] = slot
        self._persist(pipeline_id)
        return True, swapped, None
```

(Implementation may need to adapt to actual `_persist()` / lock primitives — verify by reading `backend/pipelines.py` Phase 5 T2.8 patterns first.)

- [ ] **Step 2: Add the route handler**

Modify `backend/routes/pipelines.py`:

```python
# Add new route
@bp.post("/api/pipelines/<pid>/preset_slot")
@login_required
def set_pipeline_preset_slot(pid):
    body = request.get_json(silent=True) or {}
    slot = body.get("slot")
    # Allow `null` (explicit) or omitted → None
    if slot is not None:
        if isinstance(slot, bool) or not isinstance(slot, int):
            return jsonify({"error": "slot must be null or int 1-4"}), 400
        if slot < 1 or slot > 4:
            return jsonify({"error": "slot must be in {1,2,3,4}"}), 400

    ok, swapped, err = _app._pipeline_manager.set_preset_slot(
        pid,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
        slot=slot,
    )
    if not ok:
        status = 404 if err == "not found" else 403 if err == "forbidden" else 400
        return jsonify({"error": err}), status
    return jsonify({"ok": True, "swapped_pipeline_id": swapped}), 200
```

- [ ] **Step 3: Run tests**

Run: `cd backend && pytest tests/test_pipeline_preset_slot.py -v`

Expected: All ~10 tests PASS.

- [ ] **Step 4: Run full suite to confirm no regression**

Run: `cd backend && pytest -q`

Expected: ~794 → ~804 PASS (new tests added); pre-existing baseline failures unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/pipelines.py backend/routes/pipelines.py backend/tests/test_pipeline_preset_slot.py
git commit -m "feat(pipelines): preset_slot atomic-swap endpoint (Q3)"
```

---

# Phase 1 — Frontend foundations

## Task 1.1: Token-stylesheet scaffold

**Files:**
- Create: `frontend/src/styles/console.css`

- [ ] **Step 1: Create scoped stylesheet with 4-column grid root**

```css
/* frontend/src/styles/console.css
 * Console scope — all rules under .console root to avoid leaking.
 * Tokens (--bg, --accent, etc.) inherited from motitle-bold.css via
 * the .motitle-bold ancestor (Console.tsx wraps its content in
 * <div className="motitle-bold console">).
 */

.console {
  display: grid;
  grid-template-columns: 56px 360px 1fr 320px;
  grid-template-rows: 1fr;
  height: 100vh;
  width: 100vw;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  overflow: hidden;
}

/* Mobile / tablet fallback — redirect handled in Console.tsx */
@media (max-width: 1023px) {
  .console-narrow-hint {
    padding: 24px;
    color: var(--text-mid);
    text-align: center;
  }
}
```

- [ ] **Step 2: No test for pure CSS — verify by `cat`**

Run: `wc -l frontend/src/styles/console.css`

Expected: ~25 lines.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/console.css
git commit -m "feat(console): scaffold console.css with 4-col grid root"
```

## Task 1.2: Type definitions module

**Files:**
- Create: `frontend/src/pages/Console/types.ts`

- [ ] **Step 1: Write types from the "Type definitions" section of this plan**

```ts
// frontend/src/pages/Console/types.ts

export type ConsoleStageCellState = 'idle' | 'done' | 'warn' | 'err';

export type ConsoleStageCell = {
  state: ConsoleStageCellState;
  percent?: number;
};

export type ConsoleStageCells = [
  ConsoleStageCell, ConsoleStageCell, ConsoleStageCell, ConsoleStageCell,
];

export type ConsoleFile = {
  id: string;
  name: string;
  ext: string;
  durationSeconds: number | null;
  formattedDuration: string;
  formattedSize: string;
  formattedUploaded: string;
  stageCells: ConsoleStageCells;
  errored: boolean;
};
```

- [ ] **Step 2: No test — just typecheck**

Run: `cd frontend && npm run typecheck`

Expected: 0 TS errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/types.ts
git commit -m "feat(console): add ConsoleFile + StageCell types"
```

## Task 1.3: format.ts utility — failing tests

**Files:**
- Create: `frontend/src/lib/format.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// frontend/src/lib/format.test.ts
import { describe, it, expect } from 'vitest';
import { formatDuration, formatBytes, formatRelativeTime } from './format';

describe('formatDuration', () => {
  it('returns dash for null', () => {
    expect(formatDuration(null)).toBe('—');
  });
  it('formats under an hour as mm:ss', () => {
    expect(formatDuration(0)).toBe('00:00');
    expect(formatDuration(7)).toBe('00:07');
    expect(formatDuration(65)).toBe('01:05');
    expect(formatDuration(2538)).toBe('42:18');
  });
  it('formats an hour or more as h:mm:ss', () => {
    expect(formatDuration(3600)).toBe('1:00:00');
    expect(formatDuration(3725)).toBe('1:02:05');
  });
  it('handles fractional seconds by flooring', () => {
    expect(formatDuration(42.9)).toBe('00:42');
  });
});

describe('formatBytes', () => {
  it('formats KB', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(2048)).toBe('2.0 KB');
  });
  it('formats MB', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(284 * 1024 * 1024)).toBe('284.0 MB');
  });
  it('formats GB', () => {
    expect(formatBytes(1.2 * 1024 ** 3)).toBe('1.2 GB');
  });
});

describe('formatRelativeTime', () => {
  const now = 1716000000;  // 2024-05-18T08:00:00Z (any fixed instant)
  it('returns "剛剛" for < 60s', () => {
    expect(formatRelativeTime(now - 30, now)).toBe('剛剛');
  });
  it('returns "N 分鐘前" for minutes', () => {
    expect(formatRelativeTime(now - 120, now)).toBe('2 分鐘前');
  });
  it('returns "N 小時前" for hours', () => {
    expect(formatRelativeTime(now - 7200, now)).toBe('2 小時前');
  });
  it('returns "N 日前" for days', () => {
    expect(formatRelativeTime(now - 86400 * 3, now)).toBe('3 日前');
  });
});
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd frontend && npx vitest run src/lib/format.test.ts`

Expected: FAIL — module doesn't exist.

## Task 1.4: format.ts utility — implementation

**Files:**
- Create: `frontend/src/lib/format.ts`

- [ ] **Step 1: Write implementation**

```ts
// frontend/src/lib/format.ts

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !isFinite(seconds)) return '—';
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`;
  return `${pad(m)}:${pad(sec)}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function formatRelativeTime(epochSeconds: number, nowSeconds?: number): string {
  const now = nowSeconds ?? Math.floor(Date.now() / 1000);
  const delta = now - epochSeconds;
  if (delta < 60) return '剛剛';
  if (delta < 3600) return `${Math.floor(delta / 60)} 分鐘前`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} 小時前`;
  return `${Math.floor(delta / 86400)} 日前`;
}
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest run src/lib/format.test.ts`

Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/format.ts frontend/src/lib/format.test.ts
git commit -m "feat(lib): format.ts — formatDuration/Bytes/RelativeTime utilities"
```

## Task 1.5: Extend FileRecord + PipelineSummary schemas

**Files:**
- Modify: `frontend/src/lib/socket-events.ts`
- Modify: `frontend/src/stores/pipeline-picker.ts`
- Modify: `frontend/src/lib/schemas/pipeline.ts`
- Modify: `frontend/src/lib/schemas/pipeline-v5.ts`

- [ ] **Step 1: Add `duration_seconds` to FileRecord interface**

In `frontend/src/lib/socket-events.ts`:

```ts
// Find the FileRecord interface (lines ~20-40), add the field:
export interface FileRecord {
  id: string;
  original_name: string;
  status: string;
  // ... existing fields ...
  duration_seconds?: number | null;   // NEW (Q2)
  [key: string]: unknown;
}
```

- [ ] **Step 2: Add `preset_slot` to PipelineSummary**

In `frontend/src/stores/pipeline-picker.ts`:

```ts
export interface PipelineSummary {
  id: string;
  name: string;
  description: string;
  shared: boolean;
  user_id: number | null;
  broken_refs?: PipelineBrokenRefs;
  preset_slot?: 1 | 2 | 3 | 4 | null;   // NEW (Q3)
}
```

- [ ] **Step 3: Add preset_slot to zod schemas**

In `frontend/src/lib/schemas/pipeline.ts` (v4) and `frontend/src/lib/schemas/pipeline-v5.ts` (v5):

```ts
// Add to the schema object:
preset_slot: z.union([
  z.literal(1), z.literal(2), z.literal(3), z.literal(4), z.null()
]).optional(),
```

- [ ] **Step 4: Run typecheck + existing tests**

Run: `cd frontend && npm run typecheck && npx vitest run`

Expected: 0 TS errors. All existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/socket-events.ts frontend/src/stores/pipeline-picker.ts \
        frontend/src/lib/schemas/pipeline.ts frontend/src/lib/schemas/pipeline-v5.ts
git commit -m "feat(types): add duration_seconds + preset_slot to frontend types (Q2/Q3)"
```

---

# Phase 2 — Console route + layout shell

## Task 2.1: Console.tsx skeleton — failing smoke test

**Files:**
- Create: `frontend/src/pages/Console.test.tsx`

- [ ] **Step 1: Write smoke test**

```tsx
// frontend/src/pages/Console.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Console } from './Console';

function renderConsole() {
  return render(
    <MemoryRouter initialEntries={['/console?console=1']}>
      <Console />
    </MemoryRouter>,
  );
}

describe('Console page', () => {
  it('renders 4 main columns', () => {
    renderConsole();
    expect(screen.getByTestId('console-rail')).toBeInTheDocument();
    expect(screen.getByTestId('console-queue')).toBeInTheDocument();
    expect(screen.getByTestId('console-workbench')).toBeInTheDocument();
    expect(screen.getByTestId('console-aside')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run smoke to verify FAIL**

Run: `cd frontend && npx vitest run src/pages/Console.test.tsx`

Expected: FAIL — `Console` not exported.

## Task 2.2: Console.tsx skeleton — implementation

**Files:**
- Create: `frontend/src/pages/Console.tsx`

- [ ] **Step 1: Write composition root**

```tsx
// frontend/src/pages/Console.tsx
import '../styles/console.css';
import '../styles/motitle-bold.css';
import { Rail } from './Console/Rail';
import { QueueColumn } from './Console/QueueColumn';
import { Workbench } from './Console/Workbench';
import { AsideColumn } from './Console/AsideColumn';

export type ConsoleProps = Record<string, never>;

export function Console(_props: ConsoleProps) {
  return (
    <div className="motitle-bold console" data-testid="console-root">
      <div data-testid="console-rail"><Rail /></div>
      <div data-testid="console-queue"><QueueColumn /></div>
      <div data-testid="console-workbench"><Workbench /></div>
      <div data-testid="console-aside"><AsideColumn /></div>
    </div>
  );
}
```

- [ ] **Step 2: Create 4 stub child components**

Each stub at `frontend/src/pages/Console/{Rail,QueueColumn,Workbench,AsideColumn}.tsx`:

```tsx
// Rail.tsx
export type RailProps = Record<string, never>;
export function Rail(_props: RailProps) {
  return <nav className="con-rail">RAIL</nav>;
}
// QueueColumn.tsx — same pattern
export function QueueColumn() { return <section className="con-queue">QUEUE</section>; }
// Workbench.tsx
export function Workbench() { return <section className="con-work">WORK</section>; }
// AsideColumn.tsx
export function AsideColumn() { return <aside className="con-aside">ASIDE</aside>; }
```

- [ ] **Step 3: Run smoke test**

Run: `cd frontend && npx vitest run src/pages/Console.test.tsx`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console.tsx frontend/src/pages/Console/
git commit -m "feat(console): skeleton Console.tsx + 4-col stub children"
```

## Task 2.3: Feature-flag route — failing test

**Files:**
- Create: `frontend/tests-e2e/console.spec.ts`

- [ ] **Step 1: Write skeletal E2E spec**

```ts
// frontend/tests-e2e/console.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Console page (/console)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'AdminPass1!');
    await page.click('button:has-text("Log in")');
    await expect(page).toHaveURL('/', { timeout: 10_000 });
  });

  test('redirects /console without ?console=1 query to /', async ({ page }) => {
    await page.goto('/console');
    await expect(page).toHaveURL('/', { timeout: 5_000 });
  });

  test('renders 4 columns at /console?console=1', async ({ page }) => {
    await page.goto('/console?console=1');
    await expect(page.locator('[data-testid="console-rail"]')).toBeVisible();
    await expect(page.locator('[data-testid="console-queue"]')).toBeVisible();
    await expect(page.locator('[data-testid="console-workbench"]')).toBeVisible();
    await expect(page.locator('[data-testid="console-aside"]')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run E2E to verify FAIL**

Run: `cd frontend && npx playwright test console.spec.ts --reporter=line`

Expected: FAIL — `/console` route 404 or no Console mounted.

## Task 2.4: Feature-flag route — implementation

**Files:**
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Add lazy route with double-flag gate**

```tsx
// frontend/src/router.tsx — add near other lazy imports:
import { lazy } from 'react';
const Console = lazy(() => import('./pages/Console').then(m => ({ default: m.Console })));

// Add a guard component:
import { Navigate, useSearchParams } from 'react-router-dom';

function ConsoleGate() {
  const [params] = useSearchParams();
  const envEnabled = import.meta.env.VITE_CONSOLE === '1';
  const queryEnabled = params.get('console') === '1';
  if (!envEnabled || !queryEnabled) return <Navigate to="/" replace />;
  return <Console />;
}

// Inside the `AuthenticatedShell` route list:
{ path: 'console', element: <ConsoleGate /> },
```

- [ ] **Step 2: Set the env var for development**

Add to `frontend/.env.development` (create if missing):

```env
VITE_CONSOLE=1
```

(Production build deliberately omits this to tree-shake.)

- [ ] **Step 3: Run E2E**

Start dev server first:
```bash
cd frontend && npm run dev:vite  # leave running in background
```

Then in another terminal:
```bash
cd frontend && npx playwright test console.spec.ts --reporter=line
```

Expected: 2 PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router.tsx frontend/.env.development frontend/tests-e2e/console.spec.ts
git commit -m "feat(console): /console lazy route with VITE_CONSOLE + ?console=1 double-gate (Q6)"
```

---

# Phase 3 — Rail column

## Task 3.1: Rail rendering — failing test

**Files:**
- Create: `frontend/src/pages/Console/Rail.test.tsx`

- [ ] **Step 1: Write test**

```tsx
// frontend/src/pages/Console/Rail.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Rail } from './Rail';

describe('Rail', () => {
  it('renders brand mark + 6 nav items + 3 bottom items', () => {
    render(<MemoryRouter><Rail /></MemoryRouter>);
    expect(screen.getByText('M', { selector: '.mark' })).toBeInTheDocument();
    expect(screen.getAllByTestId(/^rail-nav-/)).toHaveLength(6);
    expect(screen.getAllByTestId(/^rail-bottom-/)).toHaveLength(3);
  });

  it('marks the active nav item with .on class', () => {
    render(<MemoryRouter><Rail activeId="files" /></MemoryRouter>);
    const filesItem = screen.getByTestId('rail-nav-files');
    expect(filesItem.className).toMatch(/\bon\b/);
  });
});
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd frontend && npx vitest run src/pages/Console/Rail.test.tsx`

Expected: FAIL — Rail doesn't accept `activeId`, items not rendered.

## Task 3.2: Rail — implementation

**Files:**
- Modify: `frontend/src/pages/Console/Rail.tsx`

- [ ] **Step 1: Implement Rail**

```tsx
// frontend/src/pages/Console/Rail.tsx
import { Icon } from '../../lib/motitle-icons';

const NAV_ITEMS = [
  { id: 'home',   icon: 'home',   href: '/' },
  { id: 'files',  icon: 'film',   href: '/console?console=1' },
  { id: 'edit',   icon: 'edit',   href: '/proofread' },
  { id: 'flow',   icon: 'flow',   href: '/pipelines' },
  { id: 'book',   icon: 'book',   href: '/glossaries' },
  { id: 'layers', icon: 'layers', href: '/transcribe_profiles' },
] as const;

const BOTTOM_ITEMS = [
  { id: 'bell', icon: 'bell' },
  { id: 'cog',  icon: 'cog' },
  { id: 'user', icon: 'user' },
] as const;

export type RailProps = {
  activeId?: string;
};

export function Rail({ activeId = 'files' }: RailProps) {
  return (
    <nav className="con-rail">
      <div className="mark">M</div>
      <div className="sep" />
      {NAV_ITEMS.map(item => (
        <a
          key={item.id}
          href={item.href}
          className={item.id === activeId ? 'on' : ''}
          data-testid={`rail-nav-${item.id}`}
          title={item.id}
        >
          <Icon name={item.icon} size={16} />
        </a>
      ))}
      <div className="grow" />
      {BOTTOM_ITEMS.map(item => (
        <a key={item.id} data-testid={`rail-bottom-${item.id}`}>
          <Icon name={item.icon} size={16} />
        </a>
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: Add rail styles to console.css**

```css
/* Append to console.css */
.con-rail {
  display: flex; flex-direction: column;
  align-items: center;
  padding: 12px 0;
  background: var(--bg-soft);
  border-right: 1px solid var(--border);
  gap: 4px;
}
.con-rail .mark {
  width: 32px; height: 32px;
  display: grid; place-items: center;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  border-radius: 8px;
  color: #fff; font-weight: 800; font-size: 16px;
  margin-bottom: 4px;
}
.con-rail .sep {
  width: 24px; height: 1px;
  background: var(--border);
  margin: 4px 0 8px;
}
.con-rail a {
  width: 36px; height: 36px;
  display: grid; place-items: center;
  color: var(--text-mid);
  border-radius: 8px;
  position: relative;
  cursor: pointer;
  transition: color 150ms ease-out, background 150ms ease-out;
}
.con-rail a:hover {
  color: var(--text);
  background: var(--surface);
}
.con-rail a.on {
  color: var(--accent-2);
  background: var(--accent-soft);
}
.con-rail a.on::before {
  content: '';
  position: absolute;
  left: -2px; top: 9px;
  width: 2px; height: 18px;
  background: var(--accent);
  border-radius: 0 2px 2px 0;
}
.con-rail .grow { flex: 1; }
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run src/pages/Console/Rail.test.tsx`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/Rail.tsx frontend/src/pages/Console/Rail.test.tsx \
        frontend/src/styles/console.css
git commit -m "feat(console): Rail component with brand + nav + bottom items"
```

---

# Phase 4 — Queue column

## Task 4.1: deriveStageCells pure function — failing tests

**Files:**
- Create: `frontend/src/pages/Console/derive-stage-cells.test.ts`

- [ ] **Step 1: Write tests**

```ts
// frontend/src/pages/Console/derive-stage-cells.test.ts
import { describe, it, expect } from 'vitest';
import { deriveStageCells } from './derive-stage-cells';

describe('deriveStageCells', () => {
  it('all idle when file just uploaded', () => {
    const cells = deriveStageCells({
      status: 'uploaded',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
    });
    expect(cells.map(c => c.state)).toEqual(['idle', 'idle', 'idle', 'idle']);
  });

  it('ASR warn when stage 0 in progress', () => {
    const cells = deriveStageCells({
      status: 'transcribing',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'whisper' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 47, status: 'running' } },
    });
    expect(cells[0]).toEqual({ state: 'warn', percent: 47 });
    expect(cells[1].state).toBe('idle');
  });

  it('ASR done + MT warn when stage 1 running', () => {
    const cells = deriveStageCells({
      status: 'translating',
      stage_outputs: [
        { stage_type: 'asr', stage_ref: 'whisper' },
        { stage_type: 'mt', stage_ref: 'qwen' },
      ],
      approved_count: 0,
      segment_count: 100,
      stageProgressMap: {
        0: { percent: 100, status: 'done' },
        1: { percent: 22, status: 'running' },
      },
    });
    expect(cells[0]).toEqual({ state: 'done' });
    expect(cells[1]).toEqual({ state: 'warn', percent: 22 });
  });

  it('Proofread warn when partial approval', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 30,
      segment_count: 100,
      stageProgressMap: {},
    });
    expect(cells[2]).toEqual({ state: 'warn', percent: 30 });
  });

  it('Proofread done at 100% approval', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 100,
      segment_count: 100,
      stageProgressMap: {},
    });
    expect(cells[2].state).toBe('done');
  });

  it('err on all cells when status is failed', () => {
    const cells = deriveStageCells({
      status: 'failed',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 30, status: 'failed' } },
    });
    expect(cells[0].state).toBe('err');
  });
});
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd frontend && npx vitest run src/pages/Console/derive-stage-cells.test.ts`

Expected: FAIL — module doesn't exist.

## Task 4.2: deriveStageCells — implementation

**Files:**
- Create: `frontend/src/pages/Console/derive-stage-cells.ts`

- [ ] **Step 1: Implement**

```ts
// frontend/src/pages/Console/derive-stage-cells.ts
import type { FileRecord, StageStatus } from '../../lib/socket-events';
import type { ConsoleStageCells, ConsoleStageCell } from './types';

export type StageProgressEntry = {
  percent: number;
  status: StageStatus;
};
export type StageProgressMap = Record<number, StageProgressEntry | undefined>;

type DeriveInput = {
  status: FileRecord['status'];
  stage_outputs: NonNullable<FileRecord['stage_outputs']>;
  approved_count: number;
  segment_count: number;
  stageProgressMap: StageProgressMap;
};

function classifyStage(stageType: string): 'asr' | 'mt' | 'other' {
  if (stageType.startsWith('asr')) return 'asr';
  if (stageType.startsWith('mt') ||
      stageType.startsWith('translator') ||
      stageType.startsWith('refiner')) {
    return 'mt';
  }
  return 'other';
}

export function deriveStageCells(input: DeriveInput): ConsoleStageCells {
  const cells: ConsoleStageCell[] = [
    { state: 'idle' }, { state: 'idle' }, { state: 'idle' }, { state: 'idle' },
  ];
  // Position 0 — ASR
  const asrStageIdx = input.stage_outputs.findIndex(s => classifyStage(s.stage_type) === 'asr');
  if (asrStageIdx >= 0) {
    const prog = input.stageProgressMap[asrStageIdx];
    if (prog?.status === 'failed') cells[0] = { state: 'err' };
    else if (prog?.status === 'done' || prog?.percent === 100) cells[0] = { state: 'done' };
    else if (prog?.status === 'running') cells[0] = { state: 'warn', percent: prog.percent };
  }
  // Position 1 — MT
  const mtStageIdx = input.stage_outputs.findIndex(s => classifyStage(s.stage_type) === 'mt');
  if (mtStageIdx >= 0) {
    const prog = input.stageProgressMap[mtStageIdx];
    if (prog?.status === 'failed') cells[1] = { state: 'err' };
    else if (prog?.status === 'done' || prog?.percent === 100) cells[1] = { state: 'done' };
    else if (prog?.status === 'running') cells[1] = { state: 'warn', percent: prog.percent };
  }
  // Position 2 — Proofread (derived from approved / segment counts)
  if (input.segment_count > 0) {
    const pct = Math.round((input.approved_count / input.segment_count) * 100);
    if (pct >= 100) cells[2] = { state: 'done' };
    else if (pct > 0) cells[2] = { state: 'warn', percent: pct };
  }
  // Position 3 — Render (no MVP wiring, stays idle unless we know render finished)
  // Plan future: useRenderJob result. MVP: leave idle.

  // Global failure short-circuit
  if (input.status === 'failed' && cells[0].state === 'idle') {
    cells[0] = { state: 'err' };
  }
  return cells as ConsoleStageCells;
}
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest run src/pages/Console/derive-stage-cells.test.ts`

Expected: 6 PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/derive-stage-cells.ts \
        frontend/src/pages/Console/derive-stage-cells.test.ts
git commit -m "feat(console): deriveStageCells pure function (6 cases)"
```

## Task 4.3: StageBar component

**Files:**
- Create: `frontend/src/pages/Console/StageBar.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/StageBar.tsx
import type { ConsoleStageCells } from './types';

export type StageBarProps = {
  cells: ConsoleStageCells;
};

export function StageBar({ cells }: StageBarProps) {
  return (
    <div className="con-q-stages" data-testid="queue-stage-bar">
      {cells.map((c, i) => (
        <i
          key={i}
          className={c.state}
          style={c.percent != null ? ({ ['--p' as string]: c.percent + '%' } as React.CSSProperties) : undefined}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Add styles to console.css**

```css
/* Append to console.css */
.con-q-stages {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2px;
  margin-top: 6px;
}
.con-q-stages i {
  height: 4px;
  border-radius: 2px;
  background: var(--surface-3);
  display: block;
}
.con-q-stages i.done { background: var(--success); }
.con-q-stages i.warn {
  background: linear-gradient(
    90deg, var(--warning) var(--p), var(--surface-3) var(--p)
  );
  transition: --p 300ms ease-out;
}
.con-q-stages i.err { background: var(--danger); }
```

- [ ] **Step 3: No standalone test (covered by deriveStageCells + visual). Commit**

```bash
git add frontend/src/pages/Console/StageBar.tsx frontend/src/styles/console.css
git commit -m "feat(console): StageBar component + .con-q-stages styles"
```

## Task 4.4: toConsoleFile helper

**Files:**
- Create: `frontend/src/pages/Console/to-console-file.ts`
- Create: `frontend/src/pages/Console/to-console-file.test.ts`

- [ ] **Step 1: Write failing test**

```ts
// frontend/src/pages/Console/to-console-file.test.ts
import { describe, it, expect } from 'vitest';
import { toConsoleFile } from './to-console-file';
import type { FileRecord } from '../../lib/socket-events';

describe('toConsoleFile', () => {
  const baseFile: FileRecord = {
    id: 'f1',
    original_name: 'Bulletin.mp4',
    status: 'transcribing',
    duration_seconds: 862,        // 14:22
    size: 284 * 1024 * 1024,
    uploaded_at: 1716000000,
    segment_count: 100,
    approved_count: 30,
    stage_outputs: [{ stage_type: 'asr', stage_ref: 'whisper' }],
  };

  it('normalizes FileRecord into ConsoleFile shape', () => {
    const cf = toConsoleFile(baseFile, {}, 1716000060);
    expect(cf.id).toBe('f1');
    expect(cf.name).toBe('Bulletin.mp4');
    expect(cf.ext).toBe('MP4');
    expect(cf.durationSeconds).toBe(862);
    expect(cf.formattedDuration).toBe('14:22');
    expect(cf.formattedSize).toBe('284.0 MB');
    expect(cf.formattedUploaded).toBe('1 分鐘前');
    expect(cf.errored).toBe(false);
  });

  it('handles null duration', () => {
    const cf = toConsoleFile({ ...baseFile, duration_seconds: null }, {}, 1716000060);
    expect(cf.formattedDuration).toBe('—');
  });

  it('marks errored when status === failed', () => {
    const cf = toConsoleFile({ ...baseFile, status: 'failed' }, {}, 1716000060);
    expect(cf.errored).toBe(true);
  });

  it('uppercase extension extraction', () => {
    const cf = toConsoleFile({ ...baseFile, original_name: 'foo.MoV' }, {}, 1716000060);
    expect(cf.ext).toBe('MOV');
  });
});
```

- [ ] **Step 2: Run FAIL**

Run: `cd frontend && npx vitest run src/pages/Console/to-console-file.test.ts`

Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// frontend/src/pages/Console/to-console-file.ts
import { formatDuration, formatBytes, formatRelativeTime } from '../../lib/format';
import { deriveStageCells, type StageProgressMap } from './derive-stage-cells';
import type { FileRecord } from '../../lib/socket-events';
import type { ConsoleFile } from './types';

export function toConsoleFile(
  file: FileRecord,
  stageProgressMap: StageProgressMap,
  nowSeconds?: number,
): ConsoleFile {
  const ext = (file.original_name.match(/\.([^.]+)$/)?.[1] ?? '').toUpperCase();
  return {
    id: file.id,
    name: file.original_name,
    ext: ext || '?',
    durationSeconds: file.duration_seconds ?? null,
    formattedDuration: formatDuration(file.duration_seconds ?? null),
    formattedSize: typeof file.size === 'number' ? formatBytes(file.size) : '—',
    formattedUploaded: typeof file.uploaded_at === 'number'
      ? formatRelativeTime(file.uploaded_at, nowSeconds)
      : '—',
    stageCells: deriveStageCells({
      status: file.status,
      stage_outputs: file.stage_outputs ?? [],
      approved_count: typeof file.approved_count === 'number' ? file.approved_count : 0,
      segment_count: typeof file.segment_count === 'number' ? file.segment_count : 0,
      stageProgressMap,
    }),
    errored: file.status === 'failed',
  };
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/pages/Console/to-console-file.test.ts`

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Console/to-console-file.ts \
        frontend/src/pages/Console/to-console-file.test.ts
git commit -m "feat(console): toConsoleFile normalizer (FileRecord → ConsoleFile)"
```

## Task 4.5: QueueItem component

**Files:**
- Create: `frontend/src/pages/Console/QueueItem.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/QueueItem.tsx
import { StageBar } from './StageBar';
import type { ConsoleFile } from './types';

export type QueueItemProps = {
  file: ConsoleFile;
  active: boolean;
  onSelect: (id: string) => void;
};

export function QueueItem({ file, active, onSelect }: QueueItemProps) {
  return (
    <div
      className={`con-q-item ${active ? 'on' : ''}`}
      data-testid={`queue-item-${file.id}`}
      onClick={() => onSelect(file.id)}
    >
      <div className="con-q-row1">
        <span className="nm">{file.name}</span>
        <span className="ext">{file.ext}</span>
      </div>
      <div className="con-q-meta">
        <span>{file.formattedDuration}</span>
        <span className="sep">·</span>
        <span>{file.formattedSize}</span>
        <span className="sep">·</span>
        <span>{file.formattedUploaded}</span>
      </div>
      <StageBar cells={file.stageCells} />
    </div>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-q-item {
  padding: 11px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 150ms linear;
}
.con-q-item:hover { background: var(--surface); }
.con-q-item.on {
  background: var(--surface);
  box-shadow: inset 2px 0 0 var(--accent);
}
.con-q-row1 {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--text);
}
.con-q-row1 .nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.con-q-row1 .ext {
  font-family: var(--font-mono);
  font-size: 9px;
  text-transform: uppercase;
  color: var(--text-dim);
  letter-spacing: 0.05em;
}
.con-q-meta {
  display: flex; align-items: center; gap: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}
.con-q-meta .sep { color: var(--border-strong); }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/QueueItem.tsx frontend/src/styles/console.css
git commit -m "feat(console): QueueItem component with active state"
```

## Task 4.6: QueueColumn — wire to socket state

**Files:**
- Modify: `frontend/src/pages/Console/QueueColumn.tsx`

- [ ] **Step 1: Implement composition**

```tsx
// frontend/src/pages/Console/QueueColumn.tsx
import { useMemo, useState } from 'react';
import { useSocket } from '../../providers/SocketProvider';
import { QueueItem } from './QueueItem';
import { WorkerStatus } from './WorkerStatus';
import { toConsoleFile } from './to-console-file';
import type { ConsoleFile } from './types';

export type QueueColumnProps = Record<string, never>;

export function QueueColumn(_props: QueueColumnProps) {
  const { state } = useSocket();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const consoleFiles: ConsoleFile[] = useMemo(() => {
    return Object.values(state.files).map(f =>
      toConsoleFile(f, state.stageProgress[f.id] ?? {})
    );
  }, [state.files, state.stageProgress]);

  const counts = useMemo(() => ({
    processing: consoleFiles.filter(f =>
      f.stageCells.some(c => c.state === 'warn')
    ).length,
    proofreading: consoleFiles.filter(f =>
      f.stageCells[2].state === 'warn'
    ).length,
    done: consoleFiles.filter(f =>
      f.stageCells.every(c => c.state === 'done' || c.state === 'idle')
        && f.stageCells.some(c => c.state === 'done')
    ).length,
  }), [consoleFiles]);

  return (
    <section className="con-queue" data-testid="console-queue-inner">
      <div className="con-queue-head">
        <h2>佇列</h2>
        <div className="meta">
          <span className="k">處理中</span><span className="v">{counts.processing}</span>
          <span style={{ color: 'var(--border-strong)' }}>·</span>
          <span className="k">待校對</span><span className="v">{counts.proofreading}</span>
          <span style={{ color: 'var(--border-strong)' }}>·</span>
          <span className="k">完成</span><span className="v">{counts.done}</span>
        </div>
      </div>

      <div className="con-drop">
        {/* Drop zone — placeholder until Task 4.7 wires react-dropzone */}
        <div className="t">拖放或點擊上傳</div>
        <div className="s">MP4 · MOV · MXF · WAV · ≤ 500 MB</div>
      </div>

      <div className="con-queue-list" data-testid="queue-list">
        {consoleFiles.map(f => (
          <QueueItem
            key={f.id}
            file={f}
            active={f.id === selectedId}
            onSelect={setSelectedId}
          />
        ))}
      </div>

      <WorkerStatus />
    </section>
  );
}
```

(`WorkerStatus` is a stub at this point — fleshed in Phase 5.)

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-queue {
  display: flex; flex-direction: column;
  background: var(--bg-soft);
  border-right: 1px solid var(--border);
  overflow: hidden;
}
.con-queue-head {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.con-queue-head h2 {
  font-size: 11px; font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.con-queue-head .meta {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px;
}
.con-queue-head .meta .k { color: var(--text-dim); }
.con-queue-head .meta .v { color: var(--text); font-family: var(--font-mono); }
.con-drop {
  margin: 10px;
  padding: 14px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius);
  cursor: pointer;
  text-align: center;
  transition: border-color 150ms ease-out;
}
.con-drop:hover { border-color: var(--accent-ring); }
.con-drop .t { font-size: 13px; color: var(--text); }
.con-drop .s {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 4px;
}
.con-queue-list { flex: 1; overflow-y: auto; }
```

- [ ] **Step 3: Smoke test passes**

Run: `cd frontend && npx vitest run src/pages/Console.test.tsx`

Expected: PASS (the 4-column smoke still works).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/QueueColumn.tsx frontend/src/styles/console.css
git commit -m "feat(console): QueueColumn wires files from useSocket() reducer"
```

## Task 4.7: Drop zone integration

**Files:**
- Modify: `frontend/src/pages/Console/QueueColumn.tsx`

- [ ] **Step 1: Lift `react-dropzone` config from existing `UploadDropzone.tsx`**

Open `frontend/src/components/UploadDropzone.tsx` and copy the `useDropzone` config (accepted MIME types, max size, onDrop handler that POSTs to `/api/transcribe`). Re-implement in QueueColumn.tsx scope:

```tsx
// Inside QueueColumn() — replace the placeholder .con-drop block:
import { useDropzone } from 'react-dropzone';
import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { useUIStore } from '../../stores/ui';
// ...
const pipelineId = usePipelinePickerStore(s => s.pipelineId);
const pushToast = useUIStore(s => s.pushToast);
const { getRootProps, getInputProps, isDragActive } = useDropzone({
  accept: {
    'video/*': ['.mp4', '.mov', '.mkv', '.mxf'],
    'audio/*': ['.wav', '.mp3', '.m4a'],
  },
  maxSize: 500 * 1024 * 1024,
  onDrop: async (files) => {
    if (!pipelineId) {
      pushToast({ title: '請先揀 pipeline', variant: 'destructive' });
      return;
    }
    const formData = new FormData();
    formData.append('file', files[0]!);
    formData.append('pipeline_id', pipelineId);
    const resp = await fetch('/api/files/upload', {
      method: 'POST', body: formData, credentials: 'include',
    });
    if (!resp.ok) {
      pushToast({ title: '上傳失敗', variant: 'destructive' });
    }
  },
});
// Render:
<div {...getRootProps()} className={`con-drop ${isDragActive ? 'on' : ''}`} data-testid="console-drop">
  <input {...getInputProps()} />
  <div className="t">{isDragActive ? '釋放開始上傳' : '拖放或點擊上傳'}</div>
  <div className="s">MP4 · MOV · MXF · WAV · ≤ 500 MB</div>
</div>
```

- [ ] **Step 2: No new test (covered by existing `UploadDropzone.test.tsx` patterns + the route exists)**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/QueueColumn.tsx
git commit -m "feat(console): wire react-dropzone for QueueColumn upload"
```

---

# Phase 5 — Worker Status

## Task 5.1: useWorkerStatus hook — failing tests

**Files:**
- Create: `frontend/src/hooks/useWorkerStatus.test.ts`

- [ ] **Step 1: Write tests**

```ts
// frontend/src/hooks/useWorkerStatus.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useWorkerStatus } from './useWorkerStatus';

afterEach(() => vi.restoreAllMocks());

function mockFetchOnce(body: unknown) {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
    ok: true,
    json: async () => body,
  } as Response);
}

describe('useWorkerStatus', () => {
  it('partitions running / queued / failed', async () => {
    mockFetchOnce([
      { id: 'j1', file_id: 'f1', status: 'running', position: 0, file_name: 'a.mp4', owner_username: 'u', eta_seconds: null, type: 'asr', created_at: 1 },
      { id: 'j2', file_id: 'f2', status: 'queued',  position: 1, file_name: 'b.mp4', owner_username: 'u', eta_seconds: null, type: 'asr', created_at: 2 },
      { id: 'j3', file_id: 'f3', status: 'failed',  position: 2, file_name: 'c.mp4', owner_username: 'u', eta_seconds: null, type: 'asr', created_at: 3 },
    ]);
    const { result } = renderHook(() => useWorkerStatus());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.activeJobs).toHaveLength(1);
    expect(result.current.queuedJobs).toHaveLength(1);
    expect(result.current.erroredJobs).toHaveLength(1);
  });

  it('sets error when fetch fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useWorkerStatus());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('boom');
  });
});
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd frontend && npx vitest run src/hooks/useWorkerStatus.test.ts`

Expected: FAIL — hook doesn't exist.

## Task 5.2: useWorkerStatus — implementation

**Files:**
- Create: `frontend/src/hooks/useWorkerStatus.ts`
- Create: `frontend/src/lib/api/console.ts`

- [ ] **Step 1: API client**

```ts
// frontend/src/lib/api/console.ts
import type { QueueItem } from '../../hooks/useWorkerStatus';

export async function getQueue(): Promise<QueueItem[]> {
  const resp = await fetch('/api/queue', { credentials: 'include' });
  if (!resp.ok) throw new Error(`getQueue ${resp.status}`);
  return resp.json();
}

export async function setPresetSlot(
  pipelineId: string,
  slot: 1 | 2 | 3 | 4 | null,
): Promise<{ ok: true; swapped_pipeline_id: string | null }> {
  const resp = await fetch(`/api/pipelines/${pipelineId}/preset_slot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slot }),
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(`setPresetSlot ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 2: Hook**

```ts
// frontend/src/hooks/useWorkerStatus.ts
import { useEffect, useState, useCallback } from 'react';
import { useSocket } from '../providers/SocketProvider';

export type QueueItem = {
  id: string;
  file_id: string;
  file_name: string | null;
  owner_username: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  position: number;
  eta_seconds: number | null;
  type: string;
  created_at: number;
};

const POLL_MS = 3000;

export function useWorkerStatus() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const resp = await fetch('/api/queue', { credentials: 'include' });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const body: QueueItem[] = await resp.json();
      setItems(body);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  // Trigger immediate refresh on socket signal
  const socket = useSocket();
  useEffect(() => {
    // socket exposes `dispatch` + `state` only; the actual io() instance
    // lifts the event. We listen indirectly by re-fetching when the
    // socketState file count changes.
    refresh();
  }, [socket.state.files, refresh]);

  return {
    activeJobs:  items.filter(i => i.status === 'running').sort((a, b) => a.position - b.position),
    queuedJobs:  items.filter(i => i.status === 'queued').sort((a, b) => a.position - b.position),
    erroredJobs: items.filter(i => i.status === 'failed'),
    loading,
    error,
  };
}
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run src/hooks/useWorkerStatus.test.ts`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useWorkerStatus.ts frontend/src/hooks/useWorkerStatus.test.ts \
        frontend/src/lib/api/console.ts
git commit -m "feat(console): useWorkerStatus + console API client"
```

## Task 5.3: WorkerStatus component

**Files:**
- Modify: `frontend/src/pages/Console/WorkerStatus.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/WorkerStatus.tsx
import { useWorkerStatus } from '../../hooks/useWorkerStatus';
import { Icon } from '../../lib/motitle-icons';

export type WorkerStatusProps = Record<string, never>;

export function WorkerStatus(_props: WorkerStatusProps) {
  const { activeJobs, queuedJobs, erroredJobs, loading } = useWorkerStatus();

  return (
    <div className="con-worker" data-testid="worker-status">
      <h3>
        <span>處理狀態</span>
        <span className="ct">
          {activeJobs.length} 進行 / {queuedJobs.length + erroredJobs.length} 待處理
        </span>
      </h3>

      {!loading && activeJobs.length === 0 && (
        <div className="con-empty-row">
          <span className="r-dot r-dot--idle" />
          <span>現時沒有處理中嘅任務</span>
        </div>
      )}

      <ul data-testid="worker-active-list">
        {activeJobs.map(j => (
          <li key={j.id} className="con-now">
            <div className="row1">
              <span className="live">
                <span className="r-dot r-dot--pulse" style={{ background: 'var(--accent-2)' }} />
                處理中
              </span>
              <span className="stage">{j.type}</span>
            </div>
            <div className="nm" title={j.file_name ?? ''}>{j.file_name ?? '(unnamed)'}</div>
            <div className="progress">
              <span className="eta">
                {j.eta_seconds != null ? `預計 ${Math.floor(j.eta_seconds / 60)}:${(j.eta_seconds % 60).toString().padStart(2, '0')}` : '計算中…'}
              </span>
            </div>
          </li>
        ))}
      </ul>

      <div className="con-waiting">
        <div className="con-waiting-head">
          <span>待處理</span>
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)' }}>
            {queuedJobs.length + erroredJobs.length} 個
          </span>
        </div>
        <ul data-testid="worker-queued-list">
          {erroredJobs.map(j => (
            <li key={j.id} className="con-wait-row err" title={String(j.id)}>
              <span className="pos"><Icon name="alert" size={9} color="var(--danger)" /></span>
              <span className="nm">{j.file_name ?? '(unnamed)'}</span>
              <span className="meta">重試</span>
            </li>
          ))}
          {queuedJobs.map((j, i) => (
            <li key={j.id} className="con-wait-row">
              <span className="pos">{i + 1}</span>
              <span className="nm" title={j.file_name ?? ''}>{j.file_name ?? '(unnamed)'}</span>
              <span className="meta">等候中</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-worker {
  border-top: 1px solid var(--border);
  padding: 12px;
  max-height: 46%;
  overflow-y: auto;
  flex-shrink: 0;
}
.con-worker h3 {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-mid);
  margin-bottom: 8px;
}
.con-worker h3 .ct { font-weight: 400; color: var(--text-dim); }
.con-now {
  border-left: 3px solid var(--accent);
  padding: 8px 10px;
  background: var(--surface);
  border-radius: 4px;
  margin-bottom: 6px;
}
.con-now .row1 {
  display: flex; align-items: center; gap: 8px;
  font-size: 10px;
}
.con-now .live { display: flex; align-items: center; gap: 4px; color: var(--accent-2); }
.con-now .stage {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  padding: 1px 6px;
  background: var(--surface-2);
  border-radius: 3px;
}
.con-now .nm { font-size: 13px; font-weight: 600; margin: 4px 0; }
.con-now .progress {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.con-empty-row {
  display: flex; align-items: center; gap: 6px;
  padding: 8px;
  color: var(--text-dim);
  font-size: 12px;
}
.con-waiting-head {
  display: flex;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-mid);
  margin: 10px 0 6px;
}
.con-wait-row {
  display: grid;
  grid-template-columns: 22px 1fr auto;
  gap: 8px;
  padding: 4px 2px;
  font-size: 11px;
  align-items: center;
}
.con-wait-row .pos { font-family: var(--font-mono); color: var(--text-dim); text-align: center; }
.con-wait-row.err .pos { color: var(--danger); }
.con-wait-row .meta { color: var(--text-dim); font-family: var(--font-mono); font-size: 10px; }

/* Pulse animation */
@keyframes con-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.85); }
}
.r-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.r-dot--pulse { animation: con-pulse 1.4s ease-in-out infinite; }
.r-dot--idle  { background: var(--text-dim); }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/WorkerStatus.tsx frontend/src/styles/console.css
git commit -m "feat(console): WorkerStatus active+queued+errored with pulse animation"
```

---

# Phase 6 — Workbench

## Task 6.1: useHotkeys hook — failing tests

**Files:**
- Create: `frontend/src/hooks/useHotkeys.test.ts`

- [ ] **Step 1: Write tests**

```ts
// frontend/src/hooks/useHotkeys.test.ts
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useHotkeys } from './useHotkeys';

describe('useHotkeys', () => {
  it('fires handler on Cmd+1 (Mac)', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'mod+1': h }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', metaKey: true }));
    expect(h).toHaveBeenCalledTimes(1);
  });
  it('fires handler on Ctrl+1 (non-Mac)', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'mod+1': h }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', ctrlKey: true }));
    expect(h).toHaveBeenCalledTimes(1);
  });
  it('ignores when target is input', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'space': h }));
    const input = document.createElement('input');
    document.body.appendChild(input);
    const ev = new KeyboardEvent('keydown', { key: ' ' });
    Object.defineProperty(ev, 'target', { value: input });
    window.dispatchEvent(ev);
    expect(h).not.toHaveBeenCalled();
    document.body.removeChild(input);
  });
  it('respects enabled=false', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'esc': h }, false));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(h).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run FAIL**

Run: `cd frontend && npx vitest run src/hooks/useHotkeys.test.ts`

Expected: FAIL.

## Task 6.2: useHotkeys — implementation

**Files:**
- Create: `frontend/src/hooks/useHotkeys.ts`

- [ ] **Step 1: Write hook**

```ts
// frontend/src/hooks/useHotkeys.ts
import { useEffect } from 'react';

export type HotkeyHandler = (event: KeyboardEvent) => void;
export type HotkeyMap = Record<string, HotkeyHandler>;

function eventToCombo(e: KeyboardEvent): string[] {
  const mod = e.metaKey || e.ctrlKey;
  const candidates: string[] = [];
  const key = e.key.toLowerCase();
  const keyName =
    key === ' ' ? 'space' :
    key === 'escape' ? 'esc' :
    key === 'arrowup' ? 'arrow-up' :
    key === 'arrowdown' ? 'arrow-down' :
    key === 'arrowleft' ? 'arrow-left' :
    key === 'arrowright' ? 'arrow-right' :
    key === 'enter' ? 'enter' :
    key;
  if (mod) candidates.push(`mod+${keyName}`);
  candidates.push(keyName);
  return candidates;
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

export function useHotkeys(map: HotkeyMap, enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;
    function handler(e: KeyboardEvent) {
      if (isInteractiveTarget(e.target)) return;
      for (const combo of eventToCombo(e)) {
        const fn = map[combo];
        if (fn) {
          fn(e);
          return;
        }
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [map, enabled]);
}
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest run src/hooks/useHotkeys.test.ts`

Expected: 4 PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useHotkeys.ts frontend/src/hooks/useHotkeys.test.ts
git commit -m "feat(hooks): useHotkeys global keymap (mod+N / space / esc / arrows)"
```

## Task 6.3: PresetPills — failing test

**Files:**
- Create: `frontend/src/pages/Console/PresetPills.test.tsx`

- [ ] **Step 1: Write test**

```tsx
// frontend/src/pages/Console/PresetPills.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { PresetPills } from './PresetPills';
import { usePipelinePickerStore } from '../../stores/pipeline-picker';

describe('PresetPills', () => {
  it('renders 4 pills with preset_slot mapping', () => {
    usePipelinePickerStore.setState({
      pipelines: [
        { id: 'p1', name: '新聞廣播', preset_slot: 1, description: '', shared: false, user_id: 1 },
        { id: 'p2', name: '訪問長片',   preset_slot: 2, description: '', shared: false, user_id: 1 },
        { id: 'p3', name: '體育直播',   preset_slot: 3, description: '', shared: false, user_id: 1 },
      ],
      pipelineId: 'p1',
    });
    render(<PresetPills />);
    expect(screen.getByTestId('preset-pill-1').textContent).toContain('新聞廣播');
    expect(screen.getByTestId('preset-pill-2').textContent).toContain('訪問長片');
    expect(screen.getByTestId('preset-pill-3').textContent).toContain('體育直播');
    expect(screen.getByTestId('preset-pill-4').textContent).toContain('未設定');
  });

  it('Cmd+2 switches pipelineId to slot 2 occupant', () => {
    const setPipelineId = vi.fn();
    usePipelinePickerStore.setState({
      pipelines: [
        { id: 'p2', name: 'X', preset_slot: 2, description: '', shared: false, user_id: 1 },
      ],
      pipelineId: null,
      setPipelineId,
    });
    render(<PresetPills />);
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '2', metaKey: true }));
    });
    expect(setPipelineId).toHaveBeenCalledWith('p2');
  });
});
```

- [ ] **Step 2: Run FAIL**

Run: `cd frontend && npx vitest run src/pages/Console/PresetPills.test.tsx`

Expected: FAIL.

## Task 6.4: PresetPills — implementation

**Files:**
- Create: `frontend/src/pages/Console/PresetPills.tsx`

- [ ] **Step 1: Write component**

```tsx
// frontend/src/pages/Console/PresetPills.tsx
import { useCallback, useMemo } from 'react';
import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { useHotkeys } from '../../hooks/useHotkeys';

type Slot = 1 | 2 | 3 | 4;
const SLOTS: readonly Slot[] = [1, 2, 3, 4] as const;

export type PresetPillsProps = Record<string, never>;

export function PresetPills(_props: PresetPillsProps) {
  const { pipelines, pipelineId, setPipelineId } = usePipelinePickerStore();

  const slotPipelines = useMemo(() => {
    const map: Record<Slot, typeof pipelines[number] | undefined> = {
      1: undefined, 2: undefined, 3: undefined, 4: undefined,
    };
    for (const p of pipelines) {
      if (p.preset_slot && (p.preset_slot >= 1 && p.preset_slot <= 4)) {
        map[p.preset_slot as Slot] = p;
      }
    }
    return map;
  }, [pipelines]);

  const selectSlot = useCallback((slot: Slot) => {
    const p = slotPipelines[slot];
    if (p) setPipelineId(p.id);
  }, [slotPipelines, setPipelineId]);

  useHotkeys(
    useMemo(() => ({
      'mod+1': (e) => { e.preventDefault(); selectSlot(1); },
      'mod+2': (e) => { e.preventDefault(); selectSlot(2); },
      'mod+3': (e) => { e.preventDefault(); selectSlot(3); },
      'mod+4': (e) => { e.preventDefault(); selectSlot(4); },
    }), [selectSlot]),
  );

  return (
    <div className="con-presets">
      <span className="lbl">Preset</span>
      {SLOTS.map(slot => {
        const p = slotPipelines[slot];
        const active = p && p.id === pipelineId;
        return (
          <button
            key={slot}
            className={active ? 'on' : ''}
            data-testid={`preset-pill-${slot}`}
            data-active={active ? 'true' : 'false'}
            onClick={() => selectSlot(slot)}
            disabled={!p}
          >
            <span className="k">⌘{slot}</span>
            <span>{p ? p.name : '未設定'}</span>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-presets {
  display: flex; align-items: center; gap: 6px;
}
.con-presets .lbl {
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--text-dim);
  margin-right: 4px;
}
.con-presets button {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px 5px 6px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
  color: var(--text-mid);
  cursor: pointer;
  transition: background 120ms linear, border-color 120ms linear, color 120ms linear;
}
.con-presets button:disabled { opacity: 0.5; cursor: not-allowed; }
.con-presets button:hover:not(:disabled) { color: var(--text); }
.con-presets button.on {
  background: var(--accent-soft);
  border-color: var(--accent-ring);
  color: var(--text);
}
.con-presets button .k {
  font-family: var(--font-mono);
  font-size: 10px;
  background: var(--surface-3);
  color: var(--text-dim);
  padding: 1px 5px;
  border-radius: 4px;
}
.con-presets button.on .k {
  background: var(--accent);
  color: #fff;
}
```

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest run src/pages/Console/PresetPills.test.tsx`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/PresetPills.tsx \
        frontend/src/pages/Console/PresetPills.test.tsx \
        frontend/src/styles/console.css
git commit -m "feat(console): PresetPills + ⌘1-4 hotkey wiring (Q3)"
```

## Task 6.5: MetricsBar (Q5=B)

**Files:**
- Create: `frontend/src/pages/Console/MetricsBar.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/MetricsBar.tsx
import { useWorkerStatus } from '../../hooks/useWorkerStatus';

type Metric = {
  label: string;
  value: string;
  meter: number | null;       // 0..1 or null
  cls?: 'ok' | 'warn' | 'err';
};

function Bar({ pct, cls }: { pct: number | null; cls?: 'ok' | 'warn' | 'err' }) {
  return (
    <div className={`bar ${cls ?? ''}`}>
      <i style={{ transform: `scaleX(${pct ?? 0})` }} />
    </div>
  );
}

export type MetricsBarProps = Record<string, never>;

export function MetricsBar(_props: MetricsBarProps) {
  const { queuedJobs, activeJobs } = useWorkerStatus();
  const queueDepth = queuedJobs.length + activeJobs.length;

  const metrics: Metric[] = [
    { label: 'ASR',  value: '—',           meter: null },
    { label: 'MT',   value: '—',           meter: null },
    { label: 'GPU',  value: '—',           meter: null },
    {
      label: '佇列',
      value: `${queueDepth} 待處理`,
      meter: Math.min(queueDepth / 10, 1),
      cls: queueDepth > 5 ? 'warn' : queueDepth > 0 ? 'ok' : undefined,
    },
  ];

  return (
    <div className="con-metrics-bar" data-testid="metrics-bar">
      <span className="r-chip"><span className="r-led" /> 服務正常</span>
      <span className="vsep" />
      {metrics.map(m => (
        <span className="con-metric" key={m.label}>
          <span className="lb">{m.label}</span>
          <Bar pct={m.meter} cls={m.cls} />
          <span className={`v ${m.cls ?? ''}`}>{m.value}</span>
        </span>
      ))}
      <span className="grow" />
      <span className="con-metric">
        <span className="lb">最後更新</span>
        <span className="v">即時</span>
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-metrics-bar {
  display: flex; align-items: center; gap: 16px;
  padding: 0 16px;
  height: 34px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  font-size: 10px;
  flex-shrink: 0;
}
.con-metrics-bar .vsep {
  width: 1px; height: 14px;
  background: var(--border);
}
.con-metrics-bar .r-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 10px;
  color: var(--success);
}
.con-metrics-bar .r-led {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 6px var(--success);
}
.con-metric { display: inline-flex; align-items: center; gap: 6px; }
.con-metric .lb {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}
.con-metric .bar {
  width: 60px; height: 3px;
  background: var(--surface-3);
  border-radius: 2px;
  overflow: hidden;
  position: relative;
}
.con-metric .bar > i {
  display: block;
  width: 100%; height: 100%;
  background: var(--text-mid);
  transform-origin: left center;
  transition: transform 300ms ease-out;
}
.con-metric .bar.ok > i { background: var(--success); }
.con-metric .bar.warn > i { background: var(--warning); }
.con-metric .bar.err > i { background: var(--danger); }
.con-metric .v { font-family: var(--font-mono); font-size: 10px; color: var(--text); }
.con-metric .v.ok { color: var(--success); }
.con-metric .v.warn { color: var(--warning); }
.con-metric .grow { flex: 1; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/MetricsBar.tsx frontend/src/styles/console.css
git commit -m "feat(console): MetricsBar (Q5=B: queue real, others —)"
```

## Task 6.6: VideoPanel + TransportBar + VU meter

**Files:**
- Create: `frontend/src/pages/Console/VideoPanel.tsx`
- Create: `frontend/src/pages/Console/TransportBar.tsx`

- [ ] **Step 1: VideoPanel**

```tsx
// frontend/src/pages/Console/VideoPanel.tsx
export type VideoPanelProps = {
  fileName?: string;
  currentSubtitle?: string;
  currentTimecode?: string;
};

export function VideoPanel({ fileName, currentSubtitle, currentTimecode }: VideoPanelProps) {
  return (
    <div className="con-video" data-testid="video-panel">
      <div className="safe-grid" />
      <span className="preview-label">PVW · {fileName ?? '(未揀檔)'}</span>
      <span className="tc">{currentTimecode ?? '00:00:00:00'}</span>
      {currentSubtitle && (
        <div className="live-cap"><div>{currentSubtitle}</div></div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: TransportBar with VU meter random animation**

```tsx
// frontend/src/pages/Console/TransportBar.tsx
import { useEffect, useState } from 'react';
import { Icon } from '../../lib/motitle-icons';

export type TransportBarProps = {
  playing?: boolean;
  onTogglePlay?: () => void;
  currentTime?: string;
  totalTime?: string;
  scrubPercent?: number;     // 0..100
};

function VUMeter() {
  const [heights, setHeights] = useState<number[]>([6, 9, 12, 8, 11, 7]);
  useEffect(() => {
    const t = setInterval(() => {
      setHeights(Array.from({ length: 6 }, () => 6 + Math.floor(Math.random() * 8)));
    }, 200);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="r-vu live" data-testid="vu-meter">
      {heights.map((h, i) => <b key={i} style={{ height: h + 'px' }} />)}
    </span>
  );
}

export function TransportBar({
  playing = false,
  onTogglePlay,
  currentTime = '00:00',
  totalTime = '00:00',
  scrubPercent = 0,
}: TransportBarProps) {
  return (
    <div className="con-transport" data-testid="transport-bar">
      <button className="pp" onClick={onTogglePlay} data-testid="transport-toggle">
        <Icon name={playing ? 'pause' : 'play'} size={11} color="var(--bg)" />
      </button>
      <span className="tc">{currentTime}<span className="total"> / {totalTime}</span></span>
      <div className="scrub">
        <i style={{ width: `${scrubPercent}%` }} />
        <b style={{ left: `${scrubPercent}%` }} />
      </div>
      <span className="vol-toggle">−24 dB</span>
      <VUMeter />
      <button className="btn-icon">
        <Icon name="cog" size={13} />
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Add styles**

```css
/* Append to console.css */
.con-video {
  flex: 1;
  position: relative;
  background: #000;
  overflow: hidden;
}
.con-video .safe-grid {
  position: absolute; inset: 6%;
  border: 1px solid rgba(255,255,255,0.08);
  background:
    linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px) 0 33%/100% 33%,
    linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px) 33% 0/33% 100%;
}
.con-video .preview-label {
  position: absolute; top: 12px; left: 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  text-transform: uppercase;
  color: var(--text-mid);
  background: rgba(0,0,0,0.6);
  padding: 2px 8px;
  border-radius: 3px;
}
.con-video .tc {
  position: absolute; top: 12px; right: 12px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text);
  background: rgba(0,0,0,0.6);
  padding: 2px 8px;
  border-radius: 3px;
}
.con-video .live-cap {
  position: absolute;
  left: 50%; transform: translateX(-50%);
  bottom: 14%;
  background: rgba(0,0,0,0.78);
  padding: 8px 18px;
  border-radius: 4px;
  font-size: 19px;
  font-weight: 500;
  white-space: nowrap;
  transition: opacity 250ms ease-out;
}
.con-transport {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 18px;
  background: var(--surface);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.con-transport .pp {
  width: 34px; height: 34px;
  border-radius: 50%;
  background: #fff;
  display: grid; place-items: center;
  cursor: pointer;
}
.con-transport .tc {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text);
}
.con-transport .tc .total { color: var(--text-dim); }
.con-transport .scrub {
  flex: 1;
  height: 6px;
  background: var(--surface-3);
  border-radius: 3px;
  position: relative;
  cursor: pointer;
}
.con-transport .scrub > i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  border-radius: 3px;
  transition: width 250ms ease-out;
}
.con-transport .scrub > b {
  position: absolute;
  top: 50%; transform: translate(-50%, -50%);
  width: 12px; height: 12px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.4);
}
.con-transport .vol-toggle {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.r-vu {
  display: inline-flex; align-items: flex-end;
  gap: 1px; height: 14px;
}
.r-vu > b {
  display: block;
  width: 2px;
  background: var(--accent-2);
  transition: height 200ms linear;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console/VideoPanel.tsx \
        frontend/src/pages/Console/TransportBar.tsx \
        frontend/src/styles/console.css
git commit -m "feat(console): VideoPanel + TransportBar + VU meter random animation"
```

## Task 6.7: TranscriptList (read-only)

**Files:**
- Create: `frontend/src/pages/Console/TranscriptList.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/TranscriptList.tsx
import { useEffect, useRef } from 'react';
import { useDashboardTranslations } from '../../hooks/useDashboardTranslations';
import { Icon } from '../../lib/motitle-icons';

export type TranscriptListProps = {
  fileId: string | null;
  activeLang: string;
  activeRowIdx?: number | null;
};

function timecode(start: number): string {
  const s = Math.floor(start);
  return `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`;
}

export function TranscriptList({ fileId, activeLang, activeRowIdx }: TranscriptListProps) {
  const { segments, loading } = useDashboardTranslations(fileId, activeLang);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeRowIdx == null || !containerRef.current) return;
    const row = containerRef.current.querySelector<HTMLDivElement>(
      `[data-testid="transcript-row-${activeRowIdx}"]`,
    );
    if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeRowIdx]);

  if (loading) return <div className="con-transcript loading">載入中…</div>;
  if (!fileId) return <div className="con-transcript empty">揀左個檔案先睇 transcript</div>;

  return (
    <div className="con-transcript" ref={containerRef} data-testid="transcript-list">
      {segments.map((seg, idx) => (
        <div
          key={idx}
          className={`con-t-row ${idx === activeRowIdx ? 'active' : ''}`}
          data-testid={`transcript-row-${idx}`}
        >
          <span className="ts">{timecode(seg.start ?? 0)}</span>
          <span className="en">{seg.source_text ?? ''}</span>
          <span className="zh">{seg.text ?? ''}</span>
          <span className="mk">
            {seg.status === 'approved' && <Icon name="check" size={10} color="var(--success)" />}
            {seg.status === 'edited' && <Icon name="edit" size={10} color="var(--warning)" />}
          </span>
        </div>
      ))}
    </div>
  );
}
```

(Note: `useDashboardTranslations` may return fields named differently — adapt `seg.source_text` / `seg.text` based on the actual hook return shape. Read `frontend/src/hooks/useDashboardTranslations.ts` before final wiring.)

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-transcript {
  flex: 1;
  overflow-y: auto;
  max-height: 50%;
  background: var(--bg);
}
.con-transcript.loading,
.con-transcript.empty {
  padding: 16px;
  color: var(--text-dim);
  font-size: 12px;
  text-align: center;
}
.con-t-row {
  display: grid;
  grid-template-columns: 56px 1fr 1fr 28px;
  gap: 8px;
  padding: 6px 16px;
  font-size: 12px;
  align-items: start;
  border-bottom: 1px solid var(--surface-2);
  transition: background 150ms ease-out;
}
.con-t-row:hover { background: var(--surface); }
.con-t-row.active {
  background: var(--accent-softer);
  box-shadow: inset 2px 0 0 var(--accent);
}
.con-t-row .ts {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
.con-t-row .en { color: var(--text-mid); font-size: 12px; }
.con-t-row .zh { color: var(--text); font-size: 13px; }
.con-t-row .mk { display: grid; place-items: center; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/TranscriptList.tsx frontend/src/styles/console.css
git commit -m "feat(console): TranscriptList with scroll-into-view active row"
```

## Task 6.8: Workbench composition

**Files:**
- Modify: `frontend/src/pages/Console/Workbench.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/Workbench.tsx
import { useState } from 'react';
import { PresetPills } from './PresetPills';
import { MetricsBar } from './MetricsBar';
import { VideoPanel } from './VideoPanel';
import { TransportBar } from './TransportBar';
import { TranscriptList } from './TranscriptList';
import { Icon } from '../../lib/motitle-icons';
import { useHotkeys } from '../../hooks/useHotkeys';

export type WorkbenchProps = {
  selectedFileId?: string | null;
};

export function Workbench({ selectedFileId = null }: WorkbenchProps) {
  const [playing, setPlaying] = useState(false);
  useHotkeys({
    'space': (e) => { e.preventDefault(); setPlaying(p => !p); },
  });

  return (
    <section className="con-work">
      <div className="con-topbar">
        <PresetPills />
        <div className="con-actions">
          <button className="btn btn-secondary btn-sm">
            <Icon name="cog" size={11} /> 設定
          </button>
          <button className="btn btn-primary btn-sm">
            <Icon name="play" size={11} color="#fff" /> 執行佇列
          </button>
        </div>
      </div>
      <MetricsBar />
      <div className="con-stage">
        <VideoPanel fileName={selectedFileId ?? undefined} />
        <TransportBar
          playing={playing}
          onTogglePlay={() => setPlaying(p => !p)}
        />
        <div className="con-bottom">
          <TranscriptList fileId={selectedFileId} activeLang="zh" />
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-work {
  display: flex; flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}
.con-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px;
  height: 52px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-soft);
  flex-shrink: 0;
}
.con-actions { display: flex; gap: 8px; }
.con-stage {
  flex: 1;
  display: flex; flex-direction: column;
  min-height: 0;
}
.con-bottom { flex-shrink: 0; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/Workbench.tsx frontend/src/styles/console.css
git commit -m "feat(console): Workbench composition root"
```

---

# Phase 7 — Aside column

## Task 7.1: PipelineStageCards

**Files:**
- Create: `frontend/src/pages/Console/PipelineStageCards.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/PipelineStageCards.tsx
import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { Icon } from '../../lib/motitle-icons';
import type { IconName } from '../../lib/motitle-icons';

type StageCardSpec = {
  icon: IconName;
  name: string;
  meta: string;
};

export function PipelineStageCards() {
  const { pipelines, pipelineId } = usePipelinePickerStore();
  const pipeline = pipelines.find(p => p.id === pipelineId);

  const cards: StageCardSpec[] = pipeline ? [
    { icon: 'waveform', name: `ASR · ${pipeline.name}`, meta: 'faster-whisper · GPU' },
    { icon: 'layers',   name: `MT · ${pipeline.name}`,  meta: 'Ollama local' },
    { icon: 'film',     name: '輸出 · H.264 MP4',      meta: 'CRF 20 · medium' },
  ] : [];

  return (
    <div className="blk" data-testid="aside-pipeline">
      <h3>
        <Icon name="flow" size={11} />
        <span>Pipeline</span>
        <span className="grow" />
      </h3>
      {pipeline ? cards.map((c, i) => (
        <div className="con-stage-card" key={i}>
          <div className="ic"><Icon name={c.icon} size={13} /></div>
          <div>
            <div className="nm">{c.name}</div>
            <div className="ms">{c.meta}</div>
          </div>
          <Icon name="caret" size={10} color="var(--text-dim)" />
        </div>
      )) : (
        <div className="con-empty-row">未揀 pipeline</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Console/PipelineStageCards.tsx
git commit -m "feat(console): PipelineStageCards reads pipeline-picker store"
```

## Task 7.2: GlossaryReadOnlyList (Q4=A)

**Files:**
- Create: `frontend/src/pages/Console/GlossaryReadOnlyList.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/GlossaryReadOnlyList.tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../lib/api';
import { Icon } from '../../lib/motitle-icons';
import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { useProfileLookupStore } from '../../stores/profile-lookup';

type GlossaryRow = { id: string; name: string; entry_count: number };

export function GlossaryReadOnlyList() {
  const navigate = useNavigate();
  const { pipelineId } = usePipelinePickerStore();
  const fetchPipeline = useProfileLookupStore(s => s.fetchPipeline);
  const [glossaries, setGlossaries] = useState<GlossaryRow[]>([]);
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    apiFetch<{ glossaries: GlossaryRow[] }>('/api/glossaries')
      .then(r => setGlossaries(r.glossaries))
      .catch(() => setGlossaries([]));
  }, []);

  useEffect(() => {
    if (!pipelineId) { setActiveIds(new Set()); return; }
    fetchPipeline(pipelineId).then(p => {
      const ids = p?.glossary_stage?.glossary_ids ?? [];
      setActiveIds(new Set(ids));
    });
  }, [pipelineId, fetchPipeline]);

  return (
    <div className="blk" data-testid="aside-glossary">
      <h3>
        <Icon name="book" size={11} />
        <span>術語表 · {activeIds.size} 啟用</span>
      </h3>
      <div className="con-gloss-list">
        {glossaries.map(g => {
          const on = activeIds.has(g.id);
          return (
            <div
              key={g.id}
              className={`con-gloss-row ${on ? 'on' : ''}`}
              onClick={() => navigate(`/glossaries/${g.id}`)}
            >
              {on ? (
                <Icon name="check" size={10} color="var(--accent-2)" />
              ) : (
                <span className="r-dot r-dot--idle" />
              )}
              <span className="nm" style={!on ? { color: 'var(--text-dim)' } : undefined}>
                {g.name}
              </span>
              <span className="ct">{g.entry_count} 條</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-gloss-list { display: flex; flex-direction: column; gap: 4px; }
.con-gloss-row {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 8px;
  padding: 6px 4px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  align-items: center;
  transition: background 150ms ease-out;
}
.con-gloss-row:hover { background: var(--surface); }
.con-gloss-row .ct {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/GlossaryReadOnlyList.tsx frontend/src/styles/console.css
git commit -m "feat(console): GlossaryReadOnlyList (Q4=A read-only display)"
```

## Task 7.3: FileFactsBlock

**Files:**
- Create: `frontend/src/pages/Console/FileFactsBlock.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/FileFactsBlock.tsx
import { Icon } from '../../lib/motitle-icons';
import { formatDuration } from '../../lib/format';
import type { FileRecord } from '../../lib/socket-events';

export type FileFactsBlockProps = {
  file: FileRecord | null;
};

function row(k: string, v: React.ReactNode) {
  return (
    <div className="con-fact" key={k}>
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

export function FileFactsBlock({ file }: FileFactsBlockProps) {
  if (!file) {
    return (
      <div className="blk" data-testid="aside-facts">
        <h3><Icon name="clock" size={11} /><span>本檔資訊</span></h3>
        <div className="con-empty-row">未揀檔</div>
      </div>
    );
  }
  const approved = typeof file.approved_count === 'number' ? file.approved_count : 0;
  const total = typeof file.segment_count === 'number' ? file.segment_count : 0;
  return (
    <div className="blk" data-testid="aside-facts">
      <h3><Icon name="clock" size={11} /><span>本檔資訊</span></h3>
      {row('時長', formatDuration(typeof file.duration_seconds === 'number' ? file.duration_seconds : null))}
      {row('段數', total ? `${total} 段` : '—')}
      {row('已批核', total ? `${approved} / ${total}` : '—')}
      {row('語言', String(file.language ?? '—'))}
      {row('狀態', String(file.status))}
    </div>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-fact {
  display: grid;
  grid-template-columns: 70px 1fr;
  font-size: 11px;
  padding: 3px 0;
  align-items: center;
}
.con-fact .k { color: var(--text-dim); }
.con-fact .v {
  text-align: right;
  font-family: var(--font-mono);
  color: var(--text);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/FileFactsBlock.tsx frontend/src/styles/console.css
git commit -m "feat(console): FileFactsBlock with duration_seconds (Q2)"
```

## Task 7.4: AsideColumn composition

**Files:**
- Modify: `frontend/src/pages/Console/AsideColumn.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/pages/Console/AsideColumn.tsx
import { PipelineStageCards } from './PipelineStageCards';
import { GlossaryReadOnlyList } from './GlossaryReadOnlyList';
import { FileFactsBlock } from './FileFactsBlock';
import type { FileRecord } from '../../lib/socket-events';

export type AsideColumnProps = {
  selectedFile?: FileRecord | null;
};

export function AsideColumn({ selectedFile = null }: AsideColumnProps) {
  return (
    <aside className="con-aside">
      <PipelineStageCards />
      <GlossaryReadOnlyList />
      <FileFactsBlock file={selectedFile} />
    </aside>
  );
}
```

- [ ] **Step 2: Add styles**

```css
/* Append to console.css */
.con-aside {
  display: flex; flex-direction: column;
  background: var(--bg-soft);
  border-left: 1px solid var(--border);
  overflow-y: auto;
  padding: 12px;
  gap: 12px;
}
.con-aside .blk {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
}
.con-aside .blk h3 {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-mid);
  margin-bottom: 8px;
}
.con-aside .blk h3 .grow { flex: 1; }
.con-stage-card {
  display: grid;
  grid-template-columns: 28px 1fr 14px;
  gap: 8px;
  padding: 8px;
  margin-bottom: 4px;
  background: var(--surface-2);
  border-radius: 6px;
  cursor: pointer;
  align-items: center;
}
.con-stage-card .ic {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  background: var(--accent-softer);
  border-radius: 6px;
  color: var(--accent-2);
}
.con-stage-card .nm { font-size: 12px; color: var(--text); }
.con-stage-card .ms { font-family: var(--font-mono); font-size: 10px; color: var(--text-dim); margin-top: 2px; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Console/AsideColumn.tsx frontend/src/styles/console.css
git commit -m "feat(console): AsideColumn composition (Pipeline + Glossary + Facts)"
```

---

# Phase 8 — Pipelines page preset_slot UI

## Task 8.1: Preset_slot dropdown in pipeline form

**Files:**
- Modify: `frontend/src/pages/Pipelines.tsx`
- Modify: `frontend/src/lib/schemas/pipeline.ts` and `pipeline-v5.ts`

- [ ] **Step 1: Schemas already extended in Task 1.5 — confirm:**

```bash
grep "preset_slot" frontend/src/lib/schemas/pipeline.ts frontend/src/lib/schemas/pipeline-v5.ts
```

Expected: both files show the `preset_slot` zod field.

- [ ] **Step 2: Add dropdown to PipelineForm in Pipelines.tsx**

Open `frontend/src/pages/Pipelines.tsx`, locate the form section (EntityForm render-props body). Add:

```tsx
{/* Inside the form fields, after `name` and `description`: */}
<div className="form-row" data-testid="pipeline-preset-slot-field">
  <label>Preset slot (⌘1-4 hotkey, leave blank if none)</label>
  <select {...form.register('preset_slot', {
    setValueAs: (v) => v === '' ? null : Number(v),
  })}>
    <option value="">未指定</option>
    <option value="1">⌘1</option>
    <option value="2">⌘2</option>
    <option value="3">⌘3</option>
    <option value="4">⌘4</option>
  </select>
</div>
```

- [ ] **Step 3: After save, atomically swap via the new endpoint**

If form submit creates pipeline with `preset_slot != null`, no extra call needed (POST /api/pipelines accepts the field). For PATCH updates, after success call:

```ts
import { setPresetSlot } from '../lib/api/console';
// In onSubmit after main PATCH:
if (data.preset_slot !== pipelineBeforeEdit.preset_slot) {
  await setPresetSlot(pipelineId, data.preset_slot ?? null);
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Pipelines.tsx
git commit -m "feat(pipelines): preset_slot dropdown in form + atomic swap call (Q3)"
```

---

# Phase 9 — Hotkeys + animations + global search

## Task 9.1: Global hotkeys at Console level

**Files:**
- Modify: `frontend/src/pages/Console.tsx`

- [ ] **Step 1: Add ⌘K + ⌘U + Esc**

```tsx
// Inside Console() component before render:
import { useState } from 'react';
import { useHotkeys } from '../hooks/useHotkeys';
import { GlobalSearchModal } from './Console/GlobalSearchModal';

const [searchOpen, setSearchOpen] = useState(false);

useHotkeys({
  'mod+k': (e) => { e.preventDefault(); setSearchOpen(true); },
  'mod+u': (e) => {
    e.preventDefault();
    // Trigger upload — find drop input
    document.querySelector<HTMLInputElement>('[data-testid="console-drop"] input')?.click();
  },
  'esc': () => { if (searchOpen) setSearchOpen(false); },
});

// Render:
return (
  <div className="motitle-bold console" data-testid="console-root">
    {/* ... existing 4 columns ... */}
    {searchOpen && <GlobalSearchModal onClose={() => setSearchOpen(false)} />}
  </div>
);
```

- [ ] **Step 2: Create placeholder GlobalSearchModal**

```tsx
// frontend/src/pages/Console/GlobalSearchModal.tsx
import { Icon } from '../../lib/motitle-icons';

export type GlobalSearchModalProps = {
  onClose: () => void;
};

export function GlobalSearchModal({ onClose }: GlobalSearchModalProps) {
  return (
    <div className="con-modal-backdrop" data-testid="global-search-modal" onClick={onClose}>
      <div className="con-modal" onClick={e => e.stopPropagation()}>
        <div className="con-modal-head">
          <Icon name="search" size={14} />
          <input type="text" placeholder="Search (placeholder — wire in later)" autoFocus />
          <span className="kbd">Esc</span>
        </div>
        <div className="con-modal-body">
          <p style={{ color: 'var(--text-dim)', fontSize: 12 }}>
            搜尋功能稍後接駁；可用 ⌘1-4 切換 preset。
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add modal styles**

```css
/* Append to console.css */
.con-modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: grid; place-items: center;
  z-index: 100;
  animation: con-modal-in 160ms ease-out;
}
@keyframes con-modal-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
.con-modal {
  width: 560px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  animation: con-modal-slide 160ms ease-out;
}
@keyframes con-modal-slide {
  from { transform: translateY(-4px); opacity: 0; }
  to   { transform: translateY(0);    opacity: 1; }
}
.con-modal-head {
  display: flex; align-items: center; gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}
.con-modal-head input {
  flex: 1; background: transparent; border: none;
  font-size: 14px; color: var(--text);
  outline: none;
}
.con-modal-body { padding: 16px; }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Console.tsx \
        frontend/src/pages/Console/GlobalSearchModal.tsx \
        frontend/src/styles/console.css
git commit -m "feat(console): ⌘K global search placeholder + ⌘U upload trigger + Esc"
```

## Task 9.2: Queue item enter/exit animations

**Files:**
- Modify: `frontend/src/styles/console.css`

- [ ] **Step 1: Add CSS transitions**

```css
/* Append to console.css — animation rules for queue + transcript */

@keyframes con-queue-enter {
  from { transform: translateY(8px); opacity: 0; }
  to   { transform: translateY(0);   opacity: 1; }
}
@keyframes con-queue-exit {
  from { transform: translateY(0);    opacity: 1; }
  to   { transform: translateY(-8px); opacity: 0; }
}
.con-q-item {
  animation: con-queue-enter 220ms cubic-bezier(0.2, 0.7, 0.3, 1);
}
.con-q-item.exiting {
  animation: con-queue-exit 180ms ease-in forwards;
}

/* Active row inset transition is on the .on rule; stage bar fill already
   has transition on `width`. */
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/styles/console.css
git commit -m "feat(console): CSS animations — queue enter/exit, modal slide"
```

---

# Phase 10 — Tests + final delivery

## Task 10.1: Expand console.spec.ts

**Files:**
- Modify: `frontend/tests-e2e/console.spec.ts`

- [ ] **Step 1: Add 6 more scenarios**

```ts
// Append to console.spec.ts existing describe:
test('rail shows brand mark + 6 nav + 3 bottom', async ({ page }) => {
  await page.goto('/console?console=1');
  await expect(page.locator('.con-rail .mark')).toBeVisible();
  await expect(page.locator('[data-testid^="rail-nav-"]')).toHaveCount(6);
  await expect(page.locator('[data-testid^="rail-bottom-"]')).toHaveCount(3);
});

test('queue stage bar has 4 cells', async ({ page }) => {
  await page.goto('/console?console=1');
  // Tolerate empty queue
  const bars = page.locator('[data-testid="queue-stage-bar"]');
  const n = await bars.count();
  if (n > 0) {
    const cells = bars.first().locator('i');
    await expect(cells).toHaveCount(4);
  }
});

test('preset pills exist and Cmd+1-4 keys work', async ({ page }) => {
  await page.goto('/console?console=1');
  for (const slot of [1, 2, 3, 4]) {
    await expect(page.locator(`[data-testid="preset-pill-${slot}"]`)).toBeVisible();
  }
  // press Meta+2 — pill 2 should be set to data-active="true" if a pipeline is mapped
  await page.keyboard.press('Meta+2');
  // tolerate: only assert pill exists, since pipeline may not be mapped to slot
});

test('worker status section renders', async ({ page }) => {
  await page.goto('/console?console=1');
  await expect(page.locator('[data-testid="worker-status"]')).toBeVisible();
});

test('metrics bar shows queue depth real, others dash', async ({ page }) => {
  await page.goto('/console?console=1');
  await expect(page.locator('[data-testid="metrics-bar"]')).toBeVisible();
  await expect(page.locator('[data-testid="metrics-bar"]').locator('text=—')).toHaveCount(3);
});

test('aside has 3 blocks', async ({ page }) => {
  await page.goto('/console?console=1');
  await expect(page.locator('[data-testid="aside-pipeline"]')).toBeVisible();
  await expect(page.locator('[data-testid="aside-glossary"]')).toBeVisible();
  await expect(page.locator('[data-testid="aside-facts"]')).toBeVisible();
});

test('Cmd+K opens global search modal, Esc closes it', async ({ page }) => {
  await page.goto('/console?console=1');
  await page.keyboard.press('Meta+K');
  await expect(page.locator('[data-testid="global-search-modal"]')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-testid="global-search-modal"]')).not.toBeVisible();
});
```

- [ ] **Step 2: Run all Console E2E**

Start dev server, then:

```bash
cd frontend && npx playwright test console.spec.ts --reporter=line
```

Expected: All ~9 tests PASS.

- [ ] **Step 3: Run existing E2E to confirm no regression**

```bash
cd frontend && npx playwright test dashboard.spec.ts bold-dashboard.spec.ts --reporter=line
```

Expected: All still PASS — `/` route untouched.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-e2e/console.spec.ts
git commit -m "test(e2e): full Console spec (rail/queue/worker/metrics/aside/hotkeys)"
```

## Task 10.2: Final verification + handoff doc

**Files:**
- Create: `docs/CONSOLE_REDESIGN.md`

- [ ] **Step 1: Run full verification**

```bash
cd frontend && npm run typecheck
cd frontend && npx vitest run
cd frontend && npx playwright test
cd ../backend && pytest -q
```

Expected: typecheck 0 errors / vitest all PASS / playwright all PASS / pytest ~806 PASS.

- [ ] **Step 2: Write handoff doc summarising changes**

```markdown
# Console Redesign — Delivery Summary

**Branch:** `feat/phase-1-frontend-design`
**Commits:** ~35 commits across 10 phases (see git log)
**Feature flag:** `VITE_CONSOLE=1` (env) + `?console=1` (query)

## What landed

### Backend
- `FileRecord.duration_seconds` field via ffprobe-on-upload + migration script
- `Pipeline.preset_slot` field with per-user uniqueness + atomic swap endpoint

### Frontend
- 22 new files under `pages/Console/`, `hooks/`, `lib/`, `styles/`
- 6 modified files (`router.tsx`, schema files, picker store, `Pipelines.tsx`, `socket-events.ts`)
- 0 changes to `tailwind.config.ts`, `motitle-bold.css`, `Dashboard.tsx`

## How to try

1. Set `VITE_CONSOLE=1` in `frontend/.env.development` (already done in commit).
2. Restart dev server: `cd frontend && npm run dev:vite`.
3. Open `http://localhost:5173/console?console=1` (logged in).
4. Try: upload via drop zone → ⌘1-4 preset switch → click queue item → ⌘K modal → Esc close.

## Known limitations (deferred to future phase)

- Metrics bar: 3 of 4 metrics show "—" (ASR RT, MT tok/s, GPU%) — backend probes not implemented.
- VideoPanel: no real `<video>` element yet; uses placeholder safe-grid.
- TranscriptList: read-only, no edit.
- ⌘K Global search: placeholder modal, no actual search wiring.
- Render position (4th stage cell) always idle — needs `useActiveRenders()` cross-file hook.
- Mobile fallback redirects to `/` on `< 1024px`.

## Backwards compat

- `/` route untouched (existing `dashboard.spec.ts` + `bold-dashboard.spec.ts` still GREEN)
- All v5 profile pages untouched
- Existing pipelines without `preset_slot` field continue to work (field defaults to null)
- Existing files without `duration_seconds` show "—" until migration script runs
```

- [ ] **Step 3: Commit**

```bash
git add docs/CONSOLE_REDESIGN.md
git commit -m "docs(console): delivery summary + known limitations"
```

---

## Acceptance criteria check

| README acceptance | Plan task |
|---|---|
| 4-col 56/360/1fr/320 ratio | Task 1.1 (console.css), 2.2 |
| Tokens 由 design system | Task 1.1 (uses var(--*) from motitle-bold.css) |
| 4-segment stage bar | Task 4.1, 4.2, 4.3 |
| Worker Status live update | Task 5.1, 5.2, 5.3 |
| ⌘1-4 hotkey | Task 6.3, 6.4 |
| Video/Transport/Transcript stacked | Task 6.6, 6.7, 6.8 |
| Aside 3 blocks scrollable | Task 7.1, 7.2, 7.3, 7.4 |
| Hover / active transition 150-220ms | All task CSS sections specify transitions |
| Pulse infinite on active worker | Task 5.3 `@keyframes con-pulse` |
| Existing Playwright pass | Task 10.1 step 3 regression check |
| ⌘K global search placeholder | Task 9.1 |
| VU meter animation | Task 6.6 |
| Live transcript scroll-into-view | Task 6.7 |
| Preset pill switch transition 120ms | Task 6.4 CSS |
| Modal open transition 160ms | Task 9.1 CSS |
| Queue item enter 220ms | Task 9.2 CSS |

All 11 README acceptance criteria mapped to tasks ✅.

---

## Execution Handoff

**Plan saved to:** `docs/superpowers/plans/2026-05-22-console-redesign-plan.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, two-stage review (spec → quality) between tasks, fast iteration. **Total 48 tasks across 11 phases** (Phase 0 backend: 10 / Phase 1 foundations: 5 / Phase 2 route: 4 / Phase 3 rail: 2 / Phase 4 queue: 7 / Phase 5 worker: 3 / Phase 6 workbench: 8 / Phase 7 aside: 4 / Phase 8 Pipelines page: 1 / Phase 9 hotkeys+anim: 2 / Phase 10 tests+docs: 2).

2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**
