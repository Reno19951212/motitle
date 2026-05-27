# Queue Execution Feedback — Design

**Date**: 2026-05-27
**Author**: brainstorming session (Reno + Claude Opus 4.7)
**Status**: Design approved, pending implementation plan
**Branch**: `feat/phase-1-frontend-design`

---

## 1. Problem

User uploads a file → queue row appears with `stage='idle'` (ASR pill `—` /
MT pill `—`). User clicks **「執行」**. Backend returns 200, frontend pushes
a 3-second toast **「✅ 已排隊」** in the bottom-right corner.

After the toast disappears the queue row's visual state stays **completely
unchanged** until the worker actually picks up the job — typically 0.5–30
seconds later. During that window users have no way to know:

- Whether the click was registered.
- Whether the backend accepted the request.
- Whether the pipeline has started.

End result: users repeatedly press **「執行」** or assume the app is broken.

## 2. Goal

Make every state transition in the pipeline lifecycle visible **inline on
the queue row itself** (and the stage badge), with zero perceptual gap
between click and feedback. User direction: *Progress-first* — show every
step, not just an acknowledgement chip.

## 3. Non-Goals

- Queue position display (`已排隊 (第 N 位)`).
- Per-MT-stage breakdown when a pipeline has multiple MT stages.
- Glossary stage chip in queue row (kept off to preserve 2-pill layout).
- Job retry / cancel buttons (already exist via separate UI).

## 4. Architecture — State Machine

Per stage index (0 = ASR, 1..N = MT, optional N+1 = Glossary):

```
idle ──[file uploaded]── 撳「執行」(optimistic dispatch) ──┐
                                                          ▼
                                                       queued ──[backend pickup]──> starting
                                                                                       │
                                                                                       ▼
                                                                                 running (5..95%)
                                                                                       │
                                                                  ┌─────success────────┤
                                                                  ▼                    ▼
                                                                done                 failed
```

### Data sources (all already wired in the reducer)

| Phase | Source field | Set by |
|---|---|---|
| `idle` | nothing set | initial state |
| `queued` | `state.stagePhase[fid][idx] == 'queued'` | `STAGE_START` action dispatched optimistically on click; OR seeded by `FILE_ADDED` when backend stamps `status='queued'` |
| `starting` | `state.stagePhase[fid][idx] == 'starting'` | socket event `pipeline_stage_start` |
| `running` + `%` | `state.stagePhase[fid][idx] == 'running'` plus `state.stageProgress[fid][idx]` | socket event `pipeline_stage_progress` (5% milestones) |
| `done` | `state.stageStatus[fid][idx] == 'done'` | socket event `pipeline_stage_done` (existing path) |
| `failed` | `state.stageStatus[fid][idx] == 'failed'` | socket event `pipeline_stage_failed` (existing path) |

The reducer was originally wired during the Console UI experiment; Console
has been removed but the reducer side (action types, state shape, socket
listeners) was intentionally preserved. **No backend or reducer change is
required.**

### Optimistic dispatch (the 0-second-window fix)

```ts
// Dashboard handleRunFile / handleRun
await apiFetch(`/api/pipelines/${pipelineId}/run`, ...);
dispatch({ type: 'STAGE_START', ev: { file_id: fileId, stage_idx: 0 } });
//   ^^^^ writes stagePhase[fid][0]='queued' synchronously in the reducer
pushToast({ title: '✅ 已排隊' });
```

The reducer's `STAGE_START` handler already sets phase to `'starting'` by
default; per Section 1 design, the action will accept an optional
`phase` field defaulting to `'queued'` for this optimistic case. The real
backend `pipeline_stage_start` event will then promote it to `'starting'`.

## 5. Components — Wire Plan

### 5.1 `DesignFile` shape extension

```ts
interface DesignFile {
  // ...existing fields
  asrPhase:   'idle' | 'queued' | 'starting' | 'running' | 'done' | 'failed';
  asrPercent: number;       // 0 unless running
  mtPhase:    'idle' | 'queued' | 'starting' | 'running' | 'done' | 'failed';
  mtPercent:  number;
}
```

### 5.2 `toDesignFile()` extension

Function signature gains the `stagePhase` map argument:

```ts
function toDesignFile(
  f: FileRecord,
  stageProgress: Record<number, number> | undefined,
  stageStatus:   Record<number, StageStatus> | undefined,
  stagePhase:    Record<number, 'queued'|'starting'|'running'> | undefined,
): DesignFile { ... }
```

**Derivation rules** (run for ASR stage_idx=0 then aggregate MT stage_idx≥1):

```
phase = match (stageStatus[idx], stagePhase[idx]):
  'done'      → done
  'failed'    → failed
  'running'   → running                            (when stageStatus says running)
  _           → stagePhase[idx]  if defined        (queued | starting | running)
  _           → idle                                (everything else)

percent = stageProgress[idx] ?? 0                  (only meaningful in 'running')
```

For MT, "representative phase" = the highest-numbered active stage_idx ≥ 1.
If multiple are running, we surface the active one's percent. If one is
done and a later one is running, surface the running one's phase + percent.

### 5.3 `<QueueRow>` rendering

Replace the existing `stageForStagePill(stage)` driven block with:

```tsx
<div className={`stage-pill ${pillClass(f.asrPhase)}`}>
  <span className="lb">ASR</span>
  <span>{pillLabel(f.asrPhase, f.asrPercent)}</span>
</div>
<div className={`stage-pill ${pillClass(f.mtPhase)}`}>
  <span className="lb">MT</span>
  <span>{pillLabel(f.mtPhase, f.mtPercent)}</span>
</div>
```

**Helpers** (extracted to sibling file `frontend/src/pages/Dashboard-pill-helpers.ts`; sibling pattern avoids creating a new `Dashboard/` folder for a single helper):

```ts
export function pillClass(phase): string {
  switch (phase) {
    case 'idle':     return 'idle';
    case 'queued':   return 'queued';     // NEW CSS class
    case 'starting': return 'starting';   // NEW CSS class
    case 'running':  return 'warn';       // reuse existing
    case 'done':     return 'ok';         // reuse existing
    case 'failed':   return 'err';        // reuse existing
  }
}

export function pillLabel(phase, pct): string {
  switch (phase) {
    case 'idle':     return '—';
    case 'queued':   return '已排隊';
    case 'starting': return '準備中';
    case 'running':  return `${pct}%`;
    case 'done':     return '完成';
    case 'failed':   return '失敗';
  }
}
```

The legacy `stageForStagePill()` helper is removed.

### 5.4 `MoTitleStageBadge` extension

Add 2 new cases in `frontend/src/lib/motitle-icons.tsx`:

```tsx
// New input prop — already covered by extended DesignFile
interface StageBadgeFile {
  asrPhase?: 'idle' | 'queued' | 'starting' | 'running' | 'done' | 'failed';
  asrPercent?: number;
  // ... existing fields kept for compat
}

// Inside MoTitleStageBadge switch:
if (file.asrPhase === 'queued') {
  return (
    <span className="badge badge--queued">
      <span className="dot" style={{ animation: 'pulse 1.3s infinite' }} />
      排隊中
    </span>
  );
}
if (file.asrPhase === 'starting') {
  return (
    <span className="badge badge--processing">
      <span className="dot" style={{ animation: 'pulse 1.3s infinite' }} />
      準備中
    </span>
  );
}
// existing transcribing / translating / done / etc cases unchanged
```

The existing `transcribing` case continues to fire when
`stageStatus[0]='running'` (`file.stage === 'transcribing'`) and shows
`轉錄中 NN%`.

### 5.5 Reducer change — optional `phase` on STAGE_START

```ts
type StageStartAction = {
  type: 'STAGE_START';
  ev: { file_id: string; stage_idx: number; phase?: 'queued' | 'starting' };
};
```

Default remains `'starting'` (current behaviour, backend-driven path).
The Dashboard click path passes `phase: 'queued'`. This is the only
reducer change.

## 6. CSS — Visual Treatment

Add to `frontend/src/styles/motitle-bold.css` after the existing
`.stage-pill.idle / .ok / .warn / .err` rules:

```css
/* Phase: queued — waiting for worker pickup */
.motitle-bold .stage-pill.queued {
  border-color: rgba(56,189,248,0.35);
  color: var(--info);
  animation: pulse 1.3s infinite;
}
/* Phase: starting — backend picked up, awaiting first progress event */
.motitle-bold .stage-pill.starting {
  border-color: rgba(245,158,11,0.35);
  color: var(--warning);
  animation: pulse 1.3s infinite;
}
```

`@keyframes pulse` already exists at line 772 of motitle-bold.css.

### Visual summary

| Phase | Border colour | Text | Pulse |
|---|---|---|---|
| `idle` | none | `—` | — |
| `queued` | cyan (info) | `已排隊` | yes |
| `starting` | amber (warning) | `準備中` | yes |
| `running` | amber (warning) | `27%` | no |
| `done` | green (success) | `完成` | no |
| `failed` | red (danger) | `失敗` | no |

## 7. Data Flow Summary

```
User clicks 「執行」
   │
   ├─ POST /api/pipelines/<pid>/run                                            (existing)
   │
   ├─ dispatch STAGE_START {fid, stage_idx:0, phase:'queued'}                   (NEW optimistic)
   │   └─ reducer: stagePhase[fid][0] = 'queued'                                (NEW value path)
   │
   └─ pushToast '✅ 已排隊'                                                       (existing)

   (... 0.5–30s wait ...)

Backend worker pickup
   │
   └─ socket emit pipeline_stage_start {fid, stage_idx:0}
       └─ reducer: stagePhase[fid][0] = 'starting'                              (existing)

   (... ~1s of model load ...)

Backend first progress event
   │
   └─ socket emit pipeline_stage_progress {fid, stage_idx:0, percent:5}
       ├─ reducer: stagePhase[fid][0] = 'running'                               (existing)
       └─ reducer: stageProgress[fid][0] = 5                                    (existing)

   (... 5..95% milestones ...)

   └─ socket emit pipeline_stage_done {fid, stage_idx:0}
       └─ reducer: stageStatus[fid][0] = 'done'                                 (existing)

   (... MT stage_idx=1 lifecycle repeats: starting → running → done ...)

   └─ socket emit pipeline_complete {fid}
       └─ reducer: file.status = 'completed'                                    (existing)
```

Throughout the lifecycle, `toDesignFile()` re-derives `asrPhase` /
`asrPercent` / `mtPhase` / `mtPercent` from the reducer state, and
`<QueueRow>` re-renders. React reconciliation ensures the chip text + CSS
class update in-place without re-mount, so the pulse animation continues
smoothly across phase transitions.

## 8. Error Handling

| Scenario | Behaviour |
|---|---|
| `POST /run` returns non-200 | Existing path: toast `排隊失敗`; **no** optimistic STAGE_START dispatched (gated on `await apiFetch(...)` success) |
| Socket disconnect during `queued` state | Row stuck on `已排隊` until reconnect; `SocketProvider` already auto-refetches `/api/files` on reconnect → `file.status='running'` → phase derive picks up via stageStatus → row resumes |
| Backend `pipeline_stage_failed` fires | Existing `stageStatus[fid][idx]='failed'` path; derive returns `failed` → red chip `失敗` |
| User clicks 「執行」twice rapidly | First click sets `queued`; second click also dispatches but reducer is idempotent on same (fid, idx, phase). Button is hidden once `canRun=false` (phase ≠ 'idle'), so second click only possible in race-window. Benign. |
| Stage progress event arrives before `stage_start` (out-of-order) | Reducer's `STAGE_PROGRESS` handler should set phase to `'running'` (already does — line ~190 in socket-events.ts). Confirmed not regressed. |

## 9. Testing

### Unit tests (vitest)

| File | New cases | Why |
|---|---|---|
| `pages/Dashboard-pill-helpers.test.ts` (new) | `pillClass()` × 6 phase + `pillLabel()` × 6 phase × edge percents | Pure-function contract lock |
| `pages/Dashboard-to-design-file.test.ts` (new) | `toDesignFile()` × 5: idle, queued only, starting, running 27%, mixed ASR-done + MT-running 50% | Derive logic — highest regression risk; `toDesignFile` exported from Dashboard.tsx |
| `lib/motitle-icons.test.tsx` (new sibling to motitle-icons.tsx) | `asrPhase='queued'` → `排隊中` + pulse dot; `asrPhase='starting'` → `準備中` + pulse dot | Visual contract |
| `lib/socket-events.test.ts` (extend existing) | `STAGE_START` with `phase='queued'` sets `stagePhase[fid][0]='queued'`; default (no phase) still sets `'starting'` | Reducer backward-compat |

### Manual smoke (Playwright headless)

1. Login → upload existing file → 揀 pipeline
2. 撳「執行」on the file's queue-item row
3. **Within 0.5s**: assert `.stage-pill.queued` present, text `已排隊`
4. Within 30s: assert `.stage-pill.warn` (running) with non-zero percent
5. Within reasonable time: assert `.stage-pill.ok` + `完成`
6. Bold Dashboard subtitle overlay still renders during all states — no regression

## 10. Acceptance Criteria

Implementation is complete when **all** of these hold:

- [ ] Vitest passes: existing 269 + new ~12 cases
- [ ] `tsc --noEmit` strict: zero new errors (pre-existing v6-pipeline-smoke errors permitted)
- [ ] Manual smoke: 0-second visual gap between click and `已排隊` chip
- [ ] Bold Dashboard zero-regression on: subtitle overlay, video preview, glossary panel, render modal, queue row click → file select, delete button, file detail inspector

## 11. Out of Scope (Deferred)

- Queue position visibility (`已排隊 (第 2 位)`) — Approach 3.
- Per-MT-stage breakdown when pipeline has > 1 MT stage.
- Glossary stage chip in queue row.
- Job retry / cancel from queue row.
- Mobile responsive queue row layout.
- Persisting `stagePhase` across page reload via backend stamp (current
  behaviour: row resumes correct phase via existing `stageStatus` derive
  path on reload — reload not in the 30s timing-critical window).

## 12. File Inventory

**New files** (4):
- `frontend/src/pages/Dashboard-pill-helpers.ts`
- `frontend/src/pages/Dashboard-pill-helpers.test.ts`
- `frontend/src/pages/Dashboard-to-design-file.test.ts`
- `frontend/src/lib/motitle-icons.test.tsx`

**Modified files** (4):
- `frontend/src/pages/Dashboard.tsx`
  - `DesignFile` interface: add 4 fields
  - `toDesignFile()`: accept stagePhase arg + new derive logic
  - `<QueueRow>` JSX: use new pill helpers
  - `handleRunFile` / `handleRun`: optimistic STAGE_START dispatch
  - Extract `pillClass` / `pillLabel` to new helpers module
  - Remove legacy `stageForStagePill()`
- `frontend/src/lib/motitle-icons.tsx`
  - `MoTitleStageBadge`: 2 new cases (queued, starting)
  - `StageBadgeFile` interface: add `asrPhase` / `asrPercent` optional fields
- `frontend/src/lib/socket-events.ts`
  - `STAGE_START` action: optional `phase` field in payload
- `frontend/src/styles/motitle-bold.css`
  - Add `.stage-pill.queued` + `.stage-pill.starting` rules

**Test updates** (1):
- `frontend/src/lib/socket-events.test.ts` — add 2 cases for optional `phase` payload on `STAGE_START`

Estimated total: ~100 lines net additions + ~30 lines deletions.
