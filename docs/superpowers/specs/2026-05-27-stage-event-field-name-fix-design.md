# Stage-Event Field-Name Fix — Design

**Date**: 2026-05-27
**Author**: brainstorming session (Reno + Claude Opus 4.7)
**Status**: Design approved, pending implementation plan
**Branch**: `feat/phase-1-frontend-design`

---

## 1. Problem

Two user-visible bugs in the queue execution feedback flow shipped earlier today (`f4f1ced`):

**Bug 2 (primary):** After clicking 「執行」, the cyan「已排隊」chip appears but **never** transitions to amber「準備中」/「N%」/「完成」green — it is stuck forever. Reload brings the user out of this state via the file-status fallback, but live updates never arrive.

**Bug 1 (secondary):** If the user reloads the browser between clicking 「執行」 and the pipeline finishing, the「已排隊」chip disappears and is replaced with「0%」amber (or similar), losing the queued visual state.

## 2. Root Cause

### Bug 2 — silent field-name mismatch

Backend `pipeline_runner.py` emits all stage events with the field name `stage_index`:

```python
_socketio_emit("pipeline_stage_progress", {
    "file_id": file_id,
    "stage_index": stage_index,            # ← "_index"
    "percent": milestone,
    ...
})
```

Frontend `socket-events.ts` reducer destructures `stage_idx`:

```ts
case 'STAGE_PROGRESS': {
  const { file_id, stage_idx, percent } = action.ev;   // ← "_idx"
  const fileProg = { ...(state.stageProgress[file_id] ?? {}), [stage_idx]: percent };
```

`stage_idx` is **undefined** in the real payload. The reducer then writes
`stageProgress[fid][undefined] = percent` — the key becomes the literal
string `'undefined'`. Lookups via `stageProgress[fid][0]` return undefined
forever.

Result: every `STAGE_PROGRESS`, `STAGE_COMPLETE`, and `PIPELINE_FAILED`
event is silently dropped. The optimistic `stagePhase[fid][0]='queued'`
written by Task 7's click handler is never overridden.

`STAGE_START` already uses `stage_index` correctly (matches backend), which
is why the initial「已排隊」/「準備中」transition works as designed for the
backend's pipeline_stage_start event. The cascade breaks at the first
progress event.

### Bug 1 — BULK_FILES over-seeds for queued status

`socket-events.ts:119`:

```ts
const IN_PROGRESS_STATUSES = new Set(['running', 'queued']);
...
if (IN_PROGRESS_STATUSES.has(f.status) && !state.stageStatus[f.id]) {
  recoveredStatus[f.id] = { [stageIdx]: 'running' };
}
// Later in the same loop:
const isPending = f.status === 'queued' || f.status === 'uploaded';
if (isPending && hasPipeline && noStageOutputs && !state.stagePhase[f.id]) {
  recoveredPhase[f.id] = { 0: 'queued' };
}
```

For a file with `status='queued'` (sitting in the worker queue, not yet
picked up): both branches fire. The first writes
`stageStatus[fid][0]='running'`; the second writes
`stagePhase[fid][0]='queued'`. `deriveStagePhase` precedence
(`stageStatus` terminal/running wins over `stagePhase`) returns `'running'`.

Pill renders as「0%」amber instead of「已排隊」cyan. Combined with Bug 2,
the「0%」then stays forever because progress events never arrive to
update the percent.

## 3. Goal

Live pipeline progress reaches the UI within ~5 seconds of backend emit,
without requiring a reload. Reload preserves the「已排隊」state when the
backend still says `status='queued'`.

## 4. Non-Goals

- Defensive payload normalization at the SocketProvider boundary
  (e.g., `stage_index ?? stage_idx` adapter) — backend has emitted
  `stage_index` consistently since v4.0 A1; the discrepancy was a
  one-time interface drift that should be fixed at source, not hidden
  behind an adapter.
- Backend changes. Backend is correct.
- New Playwright lifecycle smoke (acceptance verified manually for now;
  unit-test coverage of the reducer is the primary contract).
- Visual treatment changes — phase chips already render correctly when
  the reducer state is correct.

## 5. Architecture — wire alignment

### 5.1 `frontend/src/lib/socket-events.ts`

Three interfaces gain the renamed field `stage_index`:

```ts
export interface StageProgressEvent {
  file_id: string;
  stage_index: number;       // was stage_idx
  percent: number;
}
export interface StageCompleteEvent {
  file_id: string;
  stage_index: number;       // was stage_idx
}
export interface PipelineFailedEvent {
  file_id: string;
  stage_index?: number;      // was stage_idx
  error: string;
}
```

Reducer cases destructure the new name in 3 places:
- `STAGE_PROGRESS` (lines 193, 194, 195, 202)
- `STAGE_COMPLETE` (lines 207, 208)
- `PIPELINE_FAILED` (lines 223, 224)

`STAGE_START` already destructures `stage_index` — no change.

### 5.2 BULK_FILES narrow

```ts
const IN_PROGRESS_STATUSES = new Set(['running']);    // was ['running', 'queued']
```

`status='queued'` is the worker-queue state; the file's stage 0 has not
actually started running. The second recovery branch (which seeds
`stagePhase[0]='queued'`) is the correct path for queued files.

### 5.3 `frontend/src/providers/SocketProvider.tsx`

Three listener type annotations gain `stage_index`:

```ts
socket.on('pipeline_stage_progress',
  (ev: { file_id: string; stage_index: number; percent: number }) =>
    dispatch({ type: 'STAGE_PROGRESS', ev }));

socket.on('pipeline_stage_complete',
  (ev: { file_id: string; stage_index: number }) =>
    dispatch({ type: 'STAGE_COMPLETE', ev }));

socket.on('pipeline_failed',
  (ev: { file_id: string; stage_index?: number; error: string }) =>
    dispatch({ type: 'PIPELINE_FAILED', ev }));
```

These are pure TS annotations — no runtime change. They mirror the
backend payload shape and the new interfaces.

### 5.4 `frontend/src/providers/SocketProvider.test.tsx`

Fixture data in 6 places renames `stage_idx` → `stage_index`. The tests
keep passing because both sides agree on the same key now (currently
they pass because both sides agree on the *wrong* key — `stage_idx`).

## 6. Data Flow After Fix

```
User clicks 「執行」
  │
  ├─ POST /api/pipelines/<pid>/run → 200
  ├─ dispatch STAGE_START {stage_index:0, phase:'queued'}        [optimistic]
  │     → stagePhase[fid][0]='queued', pill 「已排隊」cyan
  │
  └─ pushToast '✅ 已排隊'

  (... worker pickup ...)

Backend emits pipeline_stage_start (stage_index:0)
  → reducer STAGE_START                                            [existing path]
  → stagePhase[fid][0]='starting', pill 「準備中」amber pulse

Backend emits pipeline_stage_progress {stage_index:0, percent:5}   [FIXED]
  → reducer STAGE_PROGRESS
  → stageProgress[fid][0]=5, stageStatus[fid][0]='running', stagePhase[fid][0]='running'
  → pill 「5%」amber

... 5..95 milestones ...

Backend emits pipeline_stage_complete {stage_index:0}              [FIXED]
  → reducer STAGE_COMPLETE
  → stageStatus[fid][0]='done', stageProgress[fid][0]=100
  → pill 「完成」green

(MT stage runs through same cycle for stage_index >= 1.)
```

## 7. Reload Behaviour After Fix

```
status='queued' (worker hasn't picked up yet)
  → BULK_FILES no longer matches IN_PROGRESS_STATUSES               [FIXED]
  → second recovery branch seeds stagePhase[0]='queued'
  → pill 「已排隊」cyan ✓

status='running' (worker actively processing)
  → BULK_FILES seeds stageStatus[0]='running'
  → derive returns running, percent=0 until next progress event arrives
  → pill 「0%」amber (briefly), then ticks via progress events       [FIXED]

status='completed' (already terminal)
  → BULK_FILES does not seed stage state
  → hotfix file-status fallback returns done
  → pill 「完成」green ✓ (unchanged from f4f1ced)

status='failed' (already terminal)
  → BULK_FILES does not seed stage state
  → hotfix file-status fallback returns failed
  → pill 「失敗」red ✓ (unchanged from f4f1ced)
```

## 8. Testing

### 8.1 New vitest cases (extend existing `socket-events.test.ts`)

Five new cases covering the contract:

```ts
describe('socketReducer / STAGE_PROGRESS', () => {
  it('uses stage_index — writes stageProgress + stageStatus + stagePhase', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'fid1', stage_index: 0, percent: 27 },
    });
    expect(next.stageProgress.fid1?.[0]).toBe(27);
    expect(next.stageStatus.fid1?.[0]).toBe('running');
    expect(next.stagePhase.fid1?.[0]).toBe('running');
  });
  it('percent=0 leaves stagePhase untouched (optimistic queued persists)', () => {
    const seeded = { ...initialSocketState, stagePhase: { fid1: { 0: 'queued' as const } } };
    const next = socketReducer(seeded, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'fid1', stage_index: 0, percent: 0 },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
  });
});

describe('socketReducer / STAGE_COMPLETE', () => {
  it('uses stage_index — sets stageStatus[idx]=done + progress=100', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_COMPLETE',
      ev: { file_id: 'fid1', stage_index: 0 },
    });
    expect(next.stageStatus.fid1?.[0]).toBe('done');
    expect(next.stageProgress.fid1?.[0]).toBe(100);
  });
});

describe('socketReducer / BULK_FILES', () => {
  it('status="queued" → seeds stagePhase[0]="queued", NOT stageStatus[0]="running"', () => {
    const next = socketReducer(initialSocketState, {
      type: 'BULK_FILES',
      files: [{ id: 'fid1', original_name: 'a.mp4', status: 'queued', pipeline_id: 'p1', uploaded_at: 0 } as FileRecord],
    });
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
    expect(next.stageStatus.fid1).toBeUndefined();
  });
  it('status="running" → seeds stageStatus[0]="running" (unchanged)', () => {
    const next = socketReducer(initialSocketState, {
      type: 'BULK_FILES',
      files: [{ id: 'fid1', original_name: 'a.mp4', status: 'running', pipeline_id: 'p1', uploaded_at: 0 } as FileRecord],
    });
    expect(next.stageStatus.fid1?.[0]).toBe('running');
  });
});
```

### 8.2 Existing test updates

`SocketProvider.test.tsx` fixtures (~6 lines) rename `stage_idx` → `stage_index`. No expectation changes.

`Dashboard-to-design-file.test.ts` test description at line 45 (`'ASR done + MT stage_idx=1 running 50%'`) — comment-only update for consistency.

`Dashboard.tsx:201` comment update for consistency.

## 9. Acceptance Criteria

- [ ] Vitest passes: existing 295 + 5 new = ≥300 pass
- [ ] `tsc --noEmit` strict: zero new errors
- [ ] **Manual smoke (live click)**: 揀有 pipeline 嘅 file → 撳「執行」→ pill sequence renders as:
  - `已排隊` (cyan) immediately
  - `準備中` (amber pulse) within ~5s
  - `N%` (amber, no pulse) ticks 5 → 100
  - `完成` (green) on stage done
  - No reload needed throughout
- [ ] **Manual smoke (reload)**: 撳完「執行」之後即時 reload — pill state matches `file.status`:
  - `queued` → `已排隊` (cyan)
  - `running` → `0%` amber then ticks
  - `completed` → `完成` green
  - `failed` → `失敗` red

## 10. Out of Scope

- Backend changes (backend is correct)
- SocketProvider payload-normalization adapter
- Playwright lifecycle E2E spec
- Dashboard.tsx changes (none needed — derive logic already correct)

## 11. File Inventory

**Modified files (3):**
- `frontend/src/lib/socket-events.ts`
  - 3 interface renames (StageProgressEvent / StageCompleteEvent / PipelineFailedEvent)
  - 3 reducer case destructure renames (STAGE_PROGRESS / STAGE_COMPLETE / PIPELINE_FAILED)
  - 1 BULK_FILES narrow (IN_PROGRESS_STATUSES = {'running'})
- `frontend/src/providers/SocketProvider.tsx`
  - 3 listener type annotations
- `frontend/src/providers/SocketProvider.test.tsx`
  - ~6 fixture renames

**Test updates (1):**
- `frontend/src/lib/socket-events.test.ts`
  - +5 new cases (STAGE_PROGRESS × 2 + STAGE_COMPLETE × 1 + BULK_FILES × 2)

**Cosmetic updates (2):**
- `frontend/src/pages/Dashboard.tsx:201` comment
- `frontend/src/pages/Dashboard-to-design-file.test.ts:45` test description

Estimated total: ~30 lines net change.
