# Pipeline Progress Contract (v3.20+)

## Status

Production. Implemented v3.20 on finalize-debug branch (commits 226077a → 3bcf782).

---

## Why this exists

Each pipeline kind in this codebase emits its own native progress events. The Profile pipeline emits `subtitle_segment` (with a `progress` float) for ASR and `translation_progress` (with a `percent` int) for MT. The V6 Dual-ASR pipeline emits `pipeline_stage_start`, `pipeline_stage_progress`, and `pipeline_stage_done` for each of its five internal stages. Without a unified layer, the frontend `queue-panel.js` would need a `case` branch for every pipeline kind, and every future pipeline addition would require a frontend PR.

The solution is a single canonical socket event `pipeline_progress` plus three new fields on the `/api/queue` row schema. A backend adapter module (`backend/progress_adapter.py`) provides shim helpers that translate each pipeline's native events into this unified contract. The adapter also maintains an in-memory cache so that cold-starting clients (page reload mid-job) can read the latest snapshot from `/api/queue` without needing a live socket event.

The outcome: adding a new pipeline kind costs **zero frontend lines**. The implementer writes a backend shim (or calls `get_adapter().report(...)` directly in the handler), and the queue panel renders the bar and label correctly with no changes to `queue-panel.js`.

---

## Architecture diagram

```
  Backend — per-pipeline native events
  ─────────────────────────────────────────────────────────────────
  Profile handler:
    subtitle_segment {progress: 0.0–1.0}  ──────┐
    translation_progress {percent: 0–100} ──────┤
                                                 │
  V6 pipeline_runner:                            │
    pipeline_stage_start   {stage_type, ...} ───┤
    pipeline_stage_progress {stage_index, ...} ─┤
    pipeline_stage_done    {stage_type, ...} ───┤
                                                 │
  Future pipeline kind:                          │
    <any native event>  ────────────────────────┤
                                                 ▼
                              ┌─────────────────────────────┐
                              │     progress_adapter.py      │
                              │  ProgressAdapter singleton   │
                              │                             │
                              │  shim helpers:              │
                              │  - report_from_subtitle_seg  │
                              │  - report_from_trans_prog    │
                              │  - report_from_v6_stage      │
                              │  - (future shims here)       │
                              │                             │
                              │  core: adapter.report(...)   │
                              │    writes _progress_cache    │
                              │    throttles emit (500ms)    │
                              └──────────────┬──────────────┘
                                             │
                          ┌──────────────────┴──────────────────┐
                          │                                      │
                          ▼                                      ▼
              socket.emit("pipeline_progress",...)    GET /api/queue
              (live push to all connected tabs)      row["progress_pct"]
                          │                          row["stage_label"]
                          │                          row["stage_state"]
                          ▼                                      │
              frontend queue-panel.js                            │
                socket.on("pipeline_progress")                   │
                _progressCache[file_id] = snap                   │
                re-render bar + label                            │
                                                                 │
              (page reload / cold-start) ◄───────────────────────┘
              queue-panel polls /api/queue every 3s
              reads progress_pct / stage_label / stage_state
```

---

## The unified contract

### 5.1 `pipeline_progress` socket event

Payload schema (TypeScript-style notation):

```typescript
type PipelineProgress = {
  file_id:       string;           // file registry key, e.g. "d159d9dbd309"
  job_id:        string;           // job queue row id, e.g. "job-abc123"
  pct:           number | null;    // 0–100 integer; null means idle/not-yet-started
  stage_label:   string;           // human-readable stage name, e.g. "轉錄中", "Qwen3 識別中"
  stage_state:   'idle' | 'active' | 'done';
  pipeline_kind: string;           // 'profile' | 'pipeline_v6' | <future>
}
```

Field semantics:

| Field | Notes |
|---|---|
| `file_id` | Matches `_file_registry` key and all existing per-file events. |
| `job_id` | Matches `jobqueue` row. Used by frontend to correlate with queue row. |
| `pct` | Percentage complete within the current stage (Profile) or across all stages (V6). `null` while job is `queued` (not yet started). |
| `stage_label` | Short human label for display. Frontend renders as-is — no mapping required. |
| `stage_state` | `'idle'` = job queued, not started. `'active'` = currently running. `'done'` = finished (triggers auto-hide after 2 s). |
| `pipeline_kind` | Informational only. Frontend does NOT branch on this value. |

Emission frequency: during `stage_state='active'`, the adapter throttles to at most one emit per 500 ms per `file_id`. `'idle'` and `'done'` states always emit immediately (bypass throttle).

### 5.2 `/api/queue` row additions

Every row returned by `GET /api/queue` gains three new fields:

```typescript
{
  // ...existing fields (id, type, status, file_id, file_name, owner, position)...
  progress_pct:  number | null,          // from _progress_cache; null if no snapshot
  stage_label:   string | null,          // from _progress_cache; null if no snapshot
  stage_state:   'idle' | 'active' | 'done',  // default 'idle' if no snapshot
}
```

These fields are populated by looking up `get_adapter().get_snapshot(file_id)` in the `/api/queue` handler. If no snapshot exists (job freshly queued, server restarted), defaults are `progress_pct: null`, `stage_label: null`, `stage_state: 'idle'`.

---

## Backend module: `backend/progress_adapter.py`

### Public API

| Name | Kind | Description |
|---|---|---|
| `ProgressSnapshot` | dataclass | Immutable snapshot: `file_id`, `job_id`, `pct`, `stage_label`, `stage_state`, `pipeline_kind`, `updated_at`. |
| `ProgressAdapter` | class | Owns `_progress_cache` dict + throttle state. Thread-safe via `threading.RLock`. |
| `ProgressAdapter.report(...)` | method | Core write path. Accepts all `ProgressSnapshot` fields as kwargs. Updates cache; conditionally emits `pipeline_progress`. |
| `ProgressAdapter.get_snapshot(file_id)` | method | Read-only cache lookup. Returns `Optional[ProgressSnapshot]`. |
| `ProgressAdapter.clear(file_id)` | method | Removes cache entry + throttle state for a file. Available for explicit cleanup; not yet called automatically. |
| `get_adapter()` | function | Lazy singleton accessor. Returns the module-level `ProgressAdapter` instance; creates one (no-op emit) if not yet initialised. |
| `init_adapter(socketio)` | function | Re-initialises singleton with `socketio.emit` as the real emit function. Called once at app boot. Idempotent. |
| `reset_adapter()` | function | Resets singleton to `None`. For tests only. |
| `report_from_subtitle_segment(adapter, *, file_id, job_id, segment_payload)` | function | Profile-mode shim. Reads `segment_payload["progress"]` (0.0–1.0) → `pct` int → calls `adapter.report(stage_label="轉錄中", ...)`. |
| `report_from_translation_progress(adapter, *, file_id, job_id, translation_payload)` | function | Profile-mode shim. Reads `translation_payload["percent"]` (0–100) → calls `adapter.report(stage_label="翻譯中", ...)`. |
| `report_from_v6_stage(adapter, *, file_id, job_id, stage_index, stage_type, stage_percent, total_stages)` | function | V6-mode shim. Maps `stage_index + stage_percent` onto a single 0–100% across all V6 stages. Looks up label in `V6_STAGE_LABELS`. |
| `V6_STAGE_LABELS` | dict | Maps V6 `stage_type` strings to display labels. See Stage label conventions section. |

Thread-safety: all reads and writes to `_cache` and `_last_emit_at` are guarded by `threading.RLock`. The emit call itself occurs outside the lock to avoid holding it during I/O.

---

## Stage label conventions

### Profile pipeline defaults

| Native event | `stage_label` emitted |
|---|---|
| `subtitle_segment` (ASR progress) | `"轉錄中"` |
| `translation_progress` (MT progress) | `"翻譯中"` |

### V6 pipeline (`V6_STAGE_LABELS`)

| `stage_type` | `stage_label` | Stage index |
|---|---|---|
| `"vad"` | `"VAD 切段中"` | 0 |
| `"asr_primary"` | `"Qwen3 識別中"` | 1 |
| `"asr_align"` | `"mlx 對齊中"` | 2 |
| `"merge"` | `"Merge 中"` | 3 |
| `"refiner"` | `"Refiner 校對中"` | 4 |

Unknown `stage_type` values fall back to `f"Stage {stage_index + 1}"`.

### Future pipelines

Free to use any string. The frontend renders `stage_label` as-is — no predefined list required. Choose short, human-readable labels (e.g. `"分析中"`, `"合成中"`).

---

## Cache lifecycle

**Cold-start (server boot):** The `_progress_cache` is empty. No rebuild occurs. `/api/queue` returns `progress_pct: null, stage_state: 'idle'` for all jobs until the first `pipeline_progress` event is emitted by the running job. The frontend queue panel will show a spinner (idle state) until the first live event arrives.

**During job:** Every shim call invokes `adapter.report(...)`, which updates `_cache[file_id]` unconditionally (always stores latest). The emit is throttled to 500 ms for `'active'` state; `'idle'` and `'done'` bypass throttle. The 3-second polling of `/api/queue` picks up the cached snapshot for any tab that missed live events.

**Job completion:** The final shim call sets `stage_state='done', pct=100`. This snapshot is preserved in the cache indefinitely (the adapter does NOT prune automatically). The frontend auto-hides the queue row ~2 s after receiving `'done'`. The `/api/queue` endpoint will still serve `pct=100, stage_state='done'` for any late cold-start client; the frontend handles `'done'` by not rendering the row.

**Explicit cleanup:** `ProgressAdapter.clear(file_id)` removes the cache entry. Not currently wired to any automatic trigger. Acceptable: the cache is in-memory; a server restart clears all state.

---

## Adding a new pipeline kind — step-by-step recipe

This section is the most important for future readers. Adding a new pipeline kind requires **backend changes only**.

**Step 1: Emit a native event from your handler (optional)**

Your handler or pipeline may emit any native socket events it needs for other listeners (e.g. the dashboard subtitle overlay). These can have any payload shape. Native events are entirely separate from the progress contract.

**Step 2: Write a shim or call `report()` directly**

Option A — write a shim helper in `backend/progress_adapter.py`:

```python
def report_from_v7_stage(adapter: ProgressAdapter, *,
                          file_id: str, job_id: str,
                          my_payload: dict) -> None:
    """V7-mode shim: my_native_event -> pipeline_progress."""
    pct = int(my_payload.get("completion_pct", 0))
    label = MY_STAGE_LABELS.get(my_payload.get("stage"), "處理中")
    state = "done" if pct >= 100 else "active"
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label=label, stage_state=state,
        pipeline_kind="pipeline_v7",
    )
```

Option B — call `report()` inline in your handler:

```python
from progress_adapter import get_adapter

get_adapter().report(
    file_id=file_id, job_id=job_id,
    pct=my_pct, stage_label="My Stage",
    stage_state="active", pipeline_kind="pipeline_v7",
)
```

Use Option A when your pipeline has multiple internal stages with stable type identifiers (like V6). Use Option B for simple single-stage pipelines.

**Step 3: Wire the shim call**

Either:
- (a) Call your shim right after your native `emit()` call in the handler — see the Profile shim calls in `backend/app.py` after every `emit("subtitle_segment", ...)` and `emit("translation_progress", ...)`.
- (b) Wrap your emit funnel — see `pipeline_runner.py::_socketio_emit` which intercepts all V6 native events and routes `pipeline_stage_*` events through `report_from_v6_stage`.

**Step 4: Frontend changes — zero**

The queue panel listens to `pipeline_progress` and renders `pct` + `stage_label` regardless of `pipeline_kind`. No frontend changes are needed. The dummy `pipeline_v99` Playwright test (`frontend/tests/test_queue_progress.spec.js`) verifies this forward-compat guarantee.

**Step 5: Optional — add a stage label table**

If your pipeline has multiple internal stages with stable string identifiers, add a `MY_STAGE_LABELS: Dict[str, str]` dict in `progress_adapter.py` (following the `V6_STAGE_LABELS` pattern) and document it in the Stage label conventions section of this file.

---

## Invariants — DO NOT BREAK

1. **Native event payload shapes are frozen.** `subtitle_segment`, `translation_progress`, `pipeline_stage_start`, `pipeline_stage_progress`, and `pipeline_stage_done` payloads must not have fields renamed or removed. Fields may be added. Other listeners (dashboard subtitle overlay, proofread page, V6 stage indicator) depend on current field names.

2. **`queue_changed` is always zero-payload.** This event is a pure "go refetch `/api/queue`" trigger. Never add a payload to it. Clients ignore any payload, but adding one signals intent to carry data — that path leads to duplication with `pipeline_progress`.

3. **`queue-panel.js` contains no pipeline-kind branching.** A grep for `pipeline_v6`, `profile`, or any `pipeline_kind` value in `frontend/js/queue-panel.js` must return zero hits. Adding a new pipeline kind is a backend-only PR.

4. **`pipeline_progress` payload schema is backward-compatible.** The six fields (`file_id`, `job_id`, `pct`, `stage_label`, `stage_state`, `pipeline_kind`) must always be present and retain their current types. New fields may be added. Renaming or removing any field breaks all connected clients without a coordinated deploy.

5. **Throttle applies only to `'active'` state.** `'idle'` and `'done'` transitions always emit immediately. This ensures that job-completion and job-start events are never silently dropped.

---

## Test references

- `backend/tests/test_progress_adapter.py` — 11 pytest cases covering: `ProgressSnapshot` construction, `ProgressAdapter.report()` with throttle, Profile shim (`subtitle_segment` → `"轉錄中"`, `translation_progress` → `"翻譯中"`), V6 shim (5 stages → monotonic 0–100%, label mapping), singleton lifecycle (`init_adapter` / `reset_adapter`), and forward-compat dummy `pipeline_v99` direct `report()` call.

- `backend/tests/test_queue_progress_pct.py` — 3 pytest cases covering: `/api/queue` row includes `progress_pct` / `stage_label` / `stage_state` fields; active file returns non-null `progress_pct`; freshly queued file (no snapshot) returns `progress_pct: null, stage_state: 'idle'`.

- `frontend/tests/test_queue_progress.spec.js` — 5 Playwright cases covering: Profile ASR bar 0→100%, Profile MT `stage_label` flip to `"翻譯中"` + bar reset, V6 five-stage monotonic bar, cold-start page reload mid-job shows non-zero bar immediately, and dummy `pipeline_v99` (mock socket emit) renders bar with zero frontend code changes.

---

## Commit history

All commits for this feature (v3.20, finalize-debug branch):

| Commit | Description |
|---|---|
| `226077a` | feat(adapter): ProgressSnapshot dataclass + module skeleton |
| `f0da910` | feat(adapter): ProgressAdapter class with cache + throttled emit |
| `99371cb` | feat(adapter): Profile shims (subtitle_segment + translation_progress) |
| `fae9170` | feat(adapter): V6 shim + V6_STAGE_LABELS mapping |
| `57aa191` | feat(adapter): module-level singleton (get_adapter / init_adapter / reset_adapter) |
| `a99f713` | feat(backend): wire Profile shim calls in app.py + init_adapter at boot |
| `168c61b` | feat(backend): wire V6 shim inside pipeline_runner._socketio_emit |
| `be07c32` | feat(api): /api/queue rows attach progress_pct / stage_label / stage_state |
| `a497040` | feat(frontend): queue-panel.js pipeline_progress listener + bar/spinner render |
| `3bcf782` | test: 11 + 3 pytest + 5 Playwright for progress contract GREEN |
