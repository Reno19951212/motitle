# Console UX Completion — Design Spec

**Date:** 2026-05-22
**Branch:** `feat/phase-1-frontend-design`
**Status:** Brainstormed, pending user review before plan handoff
**Scope:** Close the 3 remaining ⚠ partial UX gaps surfaced by the live `_user-workflow.spec.ts` E2E run on the 賽馬 fixture file.

## Goal

After this work lands, every operation a user attempts in the Console produces an immediate, accurate visual response — no silent UI states, no UI-only fakes, no permanent placeholders. Specifically:

1. Pressing **Space** with a selected file actually plays/pauses the video element, not just swaps the icon.
2. The **4th stage cell (Render)** of every queue item reflects real render-job state, and active renders appear in WorkerStatus alongside ASR/MT jobs.
3. The **first stage cell (ASR)** of a newly-uploaded file animates immediately on enqueue, instead of staying idle for the 10-30 seconds between `pipeline_stage_start` and first `pipeline_stage_progress` (v6 VAD pre-processing latency).

The 3 bugs are independent in implementation but share the same UX philosophy: **state visibility is owed within ~1 second of user action**.

## Architecture

Three coordinated changes across both stacks:

- **Frontend `VideoControlContext`** (new) — a Workbench-scoped React context that lifts video play/pause/seek state out of TransportBar local state and binds it to the actual `<video>` DOM element. Both the Space hotkey (in Workbench) and the scrub bar (in TransportBar) dispatch through this context. The element itself is registered by VideoPanel on mount.
- **Backend render socket events** — `renderer.py` and `routes/render.py` emit `render_start` / `render_progress` / `render_done` socket events mirroring the existing `pipeline_stage_*` pattern. The frontend `useSocket()` reducer adds `renderProgress` + `renderStatus` maps, and `deriveStageCells()` finally wires the 4th cell. `useWorkerStatus()` additionally polls `/api/renders/in-progress` and merges those into `activeJobs` so the WorkerStatus "處理中" panel shows render jobs alongside pipeline_run jobs.
- **4-state stage lifecycle** — the `ConsoleStageCellState` enum gains `queued` and `starting` states. Socket reducer tracks `stagePhase[file_id][idx]` separately from `stageProgress`/`stageStatus`. `deriveStageCells()` returns the appropriate state, and `console.css` paints `queued` and `starting` cells with a pulse animation so users see immediate feedback on enqueue.

These changes are layered: VideoControlContext is purely frontend, render socket events span both stacks, and stage lifecycle is mostly frontend but depends on `pipeline_stage_start` already firing (which it does — verified during the live E2E run).

## Tech Stack

- Frontend: React 18 + TypeScript strict + Vite 5 + Vitest 2 + Playwright 1.48
- Backend: Python 3.11 + Flask + Flask-SocketIO + pytest
- No new dependencies introduced.

---

# Section 1 — VideoControlContext (Bug 1: Space play)

## Problem

`Workbench.tsx` registers `useHotkeys({ space: () => setPlaying(p => !p) })` and threads `playing` as a prop into `TransportBar`. The TransportBar visually flips between play/pause icons, but `<video>` element is rendered independently inside `VideoPanel` and **no code path calls `videoEl.play()` / `videoEl.pause()`**. Result: Space toggles UI state but never controls the actual video. Verified in the workflow E2E (Step 14): transport icon swaps, but `videoEl.paused` remains `true`.

## Solution

Lift video control state into a dedicated React context that owns the imperative `HTMLVideoElement` ref and exposes declarative actions (`play` / `pause` / `toggle` / `seek` / `seekPercent`). VideoPanel registers its `<video>` element with the context on mount; TransportBar consumes state for icon + scrub bar; Workbench's Space hotkey dispatches the toggle action.

This pattern is future-extensible: adding ⌘← / ⌘→ seek, ⌘↑ / ⌘↓ volume, or playback-rate hotkeys later means adding handlers to the context — no further plumbing through 3 components.

## Interface

```ts
// frontend/src/pages/Console/video-control-context.tsx
import { createContext, useContext, useRef, useState, useCallback, useEffect, type ReactNode } from 'react';

type VideoControlValue = {
  // State (synced from <video> events)
  playing: boolean;
  currentTime: number;   // seconds
  duration: number;      // seconds, NaN until loadedmetadata
  // Element registration (called by VideoPanel)
  setVideoEl: (el: HTMLVideoElement | null) => void;
  // Actions (called by Workbench hotkeys + TransportBar UI)
  play: () => Promise<void>;
  pause: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  seekPercent: (pct: number) => void;  // pct in [0, 1]
};

const VideoControlCtx = createContext<VideoControlValue | null>(null);

export function useVideoControl(): VideoControlValue {
  const v = useContext(VideoControlCtx);
  if (!v) throw new Error('useVideoControl must be used inside <VideoControlProvider>');
  return v;
}

export function VideoControlProvider({ children }: { children: ReactNode }) { ... }
```

The provider maintains a ref to the current `HTMLVideoElement` and three pieces of state (`playing`, `currentTime`, `duration`). When `setVideoEl(el)` is called with a non-null element, the provider attaches event listeners for `play`, `pause`, `timeupdate`, `loadedmetadata` and updates state accordingly. Old listeners are cleaned up. When called with `null`, all state resets and listeners detach.

## Data flow

1. `Workbench.tsx` wraps its `<div className="con-stage">` body with `<VideoControlProvider>`.
2. `VideoPanel.tsx` uses `useVideoControl()` to get `setVideoEl`. Its `<video ref={...}>` is bound to a local `useRef`; a `useEffect` calls `setVideoEl(ref.current)` on mount, `setVideoEl(null)` on cleanup. When `fileId` changes, the `<video key={fileId}>` already forces a remount, so the cleanup→register sequence runs naturally.
3. `TransportBar.tsx` consumes `{playing, currentTime, duration}` and renders the icon + scrub. The scrub `<input type="range">`'s `onInput` calls `seekPercent(value / 100)`. Drop the existing `playing` / `onTogglePlay` / `totalTime` props from the component (they're now context-driven).
4. `Workbench.tsx` `useHotkeys({ space: e => { e.preventDefault(); toggle(); } })`. The local `playing` state is removed entirely.

## Error handling

- `videoRef.current` null when `play/pause/seek` invoked → silently return (file not selected, or VideoPanel not yet mounted). No throw, no toast.
- `videoEl.play()` returns a rejected promise (browser autoplay policy, file not ready) → caught + `console.warn`; `playing` state stays `false` via the `pause` event listener.
- `seek(seconds)` outside `[0, duration]` → clamped to `[0, duration || 0]`.
- File switch: `<video key={fileId}>` unmounts old element → cleanup fires `setVideoEl(null)` → state resets → new element mounts → `setVideoEl(newEl)` → fresh listeners attached. Race-free because React commits cleanup before mount.

## Testing

- **Vitest unit** (`video-control-context.test.tsx`): 5 cases
  - Provider initializes with `{playing:false, currentTime:0, duration:NaN}`
  - `setVideoEl(el)` attaches listeners; firing `play` event flips `playing` to true
  - `setVideoEl(null)` detaches and resets state
  - `toggle()` on paused video → calls `el.play()`; on playing → calls `el.pause()`
  - Action methods no-op (don't throw) when no element registered
- **Playwright** (`_user-workflow.spec.ts` Step 14): assert `videoEl.paused === false` 500ms after `Space` press. This is the test that already exists and currently surfaces the bug as ⚠ partial.

## Files

| File | Change | LOC |
|---|---|---|
| `frontend/src/pages/Console/video-control-context.tsx` | **NEW** | ~90 |
| `frontend/src/pages/Console/VideoPanel.tsx` | useEffect register/unregister via context | +10 |
| `frontend/src/pages/Console/TransportBar.tsx` | consume context, drop props, wire scrub | -10 / +15 |
| `frontend/src/pages/Console/Workbench.tsx` | wrap provider, simplify Space handler | +5 / -8 |
| `frontend/src/pages/Console/video-control-context.test.tsx` | **NEW** | ~50 |
| `frontend/tests-e2e/_user-workflow.spec.ts` | Step 14 assertion sharpened | +3 |

---

# Section 2 — Backend render socket events + WorkerStatus integration (Bug 2)

## Problem

Render workflow runs out-of-band from `JobQueue`. `POST /api/render` puts a job dict into `_render_jobs` (in-memory map) and spawns a daemon thread that runs FFmpeg via `subprocess.Popen` with `-progress pipe:1` parsed line-by-line. Clients poll `GET /api/renders/<id>` every 2s for `status`/`progress`. There are zero socket events from this lifecycle.

Consequences in Console:
- The 4th stage cell (Render) of every file is hardcoded `idle` in `deriveStageCells.ts` with the comment "MVP: stays idle". Users see no render progress.
- WorkerStatus's "處理中" section only shows `pipeline_run` jobs from `/api/queue`. Active renders are invisible.

## Solution

Two coordinated changes:

1. **Backend emits `render_start` / `render_progress` / `render_done` socket events** at the same lifecycle points as `pipeline_stage_*`. The events follow the existing `_socketio_emit()` pattern from `pipeline_runner.py`.
2. **Frontend `useWorkerStatus()` additionally polls `/api/renders/in-progress`** and merges its results into the `activeJobs` list as synthetic `QueueItem` entries with `type: 'render'`. This is purely additive — `/api/queue` continues to return pipeline jobs only, and the merge happens client-side.

`deriveStageCells.ts` consumes the new `renderProgress` and `renderStatus` maps from the socket reducer state to drive the 4th cell.

## Backend interface

```python
# backend/renderer.py — new module-level helper, after existing imports
def _emit_render_event(event: str, payload: dict) -> None:
    """Thin wrapper, swallows errors. Same pattern as pipeline_runner._socketio_emit."""
    try:
        import app as _app
        _app.socketio.emit(event, payload)
    except Exception:
        pass

# Inside the render daemon thread (currently in routes/render.py _run_render_job):
# At job start, just before FFmpeg subprocess launches:
_emit_render_event('render_start', {
    'render_id': job_id,
    'file_id': job['file_id'],
    'format': job['format'],
    'output_filename': job.get('output_filename'),
})

# Inside the existing FFmpeg progress-line parser, throttle to 5% delta:
last_emitted_pct = -5
for line in process.stdout:  # existing -progress pipe parsing
    pct = _parse_ffmpeg_progress(line, total_frames)
    if pct - last_emitted_pct >= 5:
        _emit_render_event('render_progress', {
            'render_id': job_id,
            'file_id': job['file_id'],
            'percent': pct,
        })
        last_emitted_pct = pct
    job['progress'] = pct

# In the finally: block:
_emit_render_event('render_done', {
    'render_id': job_id,
    'file_id': job['file_id'],
    'status': job['status'],          # 'done' | 'failed' | 'cancelled'
    'output_path': job.get('output_path'),
    'error': job.get('error'),
})
```

Throttling at 5% delta mirrors the existing pipeline progress cadence and prevents the render thread from saturating socketio with one emit per frame.

## Frontend interface — socket reducer

```ts
// frontend/src/lib/socket-events.ts — additions

export interface RenderStartEvent {
  render_id: string;
  file_id: string;
  format: string;
  output_filename?: string | null;
}
export interface RenderProgressEvent {
  render_id: string;
  file_id: string;
  percent: number;
}
export interface RenderDoneEvent {
  render_id: string;
  file_id: string;
  status: 'done' | 'failed' | 'cancelled';
  output_path?: string | null;
  error?: string | null;
}

export type SocketAction =
  | { type: 'BULK_FILES'; files: FileRecord[] }
  | { type: 'FILE_ADDED'; file: FileRecord }
  | { type: 'FILE_UPDATED'; file: FileRecord }
  | { type: 'FILE_REMOVED'; file_id: string }
  | { type: 'STAGE_PROGRESS'; ev: StageProgressEvent }
  | { type: 'STAGE_COMPLETE'; ev: StageCompleteEvent }
  | { type: 'PIPELINE_COMPLETE'; ev: PipelineCompleteEvent }
  | { type: 'PIPELINE_FAILED'; ev: PipelineFailedEvent }
  | { type: 'SOCKET_CONNECTED' }
  | { type: 'SOCKET_DISCONNECTED' }
  | { type: 'RENDER_START'; ev: RenderStartEvent }       // NEW
  | { type: 'RENDER_PROGRESS'; ev: RenderProgressEvent } // NEW
  | { type: 'RENDER_DONE'; ev: RenderDoneEvent };        // NEW

export interface SocketState {
  ... existing fields ...
  renderProgress: Record<string, number>;
  renderStatus: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
}
```

The reducer handles RENDER_START by setting `renderStatus[file_id] = 'running'` and `renderProgress[file_id] = 0`. RENDER_PROGRESS updates the percent. RENDER_DONE sets status + clears progress (or sets to 100 if status === 'done').

`SocketProvider.tsx` registers 3 new `socket.on()` listeners that dispatch the matching action.

## Frontend interface — `deriveStageCells` position 3

```ts
// Inside deriveStageCells(input):
// Position 3 — Render
const rStatus = input.renderStatus?.[input.fileId];
const rPercent = input.renderProgress?.[input.fileId];
if (rStatus === 'failed' || rStatus === 'cancelled') {
  cells[3] = { state: 'err' };
} else if (rStatus === 'done') {
  cells[3] = { state: 'done' };
} else if (rStatus === 'running') {
  cells[3] = { state: 'warn', percent: rPercent ?? 0 };
}
```

`DeriveInput` gains 3 fields: `fileId: string`, `renderStatus: Record<string, 'running'|'done'|'failed'|'cancelled'> | undefined`, `renderProgress: Record<string, number> | undefined`. `to-console-file.ts` passes them through from the socket state.

## Frontend interface — `useWorkerStatus` merge

```ts
// useWorkerStatus.ts
type RenderInProgress = {
  id: string;          // render_id
  file_id: string;
  file_name: string | null;
  status: 'running';
  percent: number;
  format: string;
  started_at: number;
};

// Inside the hook's refresh():
const [queue, renders] = await Promise.all([
  fetch('/api/queue').then(r => r.json()),
  fetch('/api/renders/in-progress').then(r => r.json()).then(arr => arr as RenderInProgress[]).catch(() => []),
]);
// Merge renders into items as synthetic QueueItem records:
const renderItems: QueueItem[] = renders.map(r => ({
  id: r.id,
  file_id: r.file_id,
  file_name: r.file_name,
  owner_username: '—',
  status: 'running',
  position: queue.length + 1,  // append after pipeline jobs
  eta_seconds: null,
  type: 'render',
  created_at: r.started_at,
}));
setItems([...queue, ...renderItems]);
```

`WorkerStatus.tsx`'s existing render of `activeJobs` already shows `j.type` as the stage tag, so render jobs naturally appear with tag `render`. To make the tag user-friendly, map `type: 'render'` → display label `燒字` and `type: 'pipeline_run'` → existing default.

## Error handling

- Render thread crashes before FFmpeg launch → no `render_start` emitted, but the existing `finally:` block guarantees `render_done` with `status='failed'` fires anyway.
- `subprocess.Popen` exits non-zero → existing code sets `job['status'] = 'failed'` and `job['error'] = stderr_tail`; the finally emit carries these.
- `/api/renders/in-progress` 401 or network error → the `.catch(() => [])` ensures the merge degrades to "no render jobs visible" rather than blowing up the hook.
- Concurrent renders for the same file (shouldn't happen normally) → `renderStatus[file_id]` is keyed on file_id, so the last event wins. If a stricter contract is needed, switch the key to `render_id` and have `deriveStageCells` look up the latest by max timestamp — but that's YAGNI for v1.

## Testing

- **Backend pytest** (`tests/test_render_socket.py`, **NEW**, 3 cases):
  - Mock subprocess + simulate one progress line → assert `_emit_render_event('render_progress', ...)` is called with throttled cadence
  - Simulate normal completion → assert `render_done` with `status='done'`
  - Simulate subprocess crash → assert `render_done` with `status='failed'` and `error` populated
- **Vitest unit** (`SocketProvider.test.tsx` extension): 3 cases for the 3 new action types — reducer correctly updates `renderProgress` / `renderStatus`.
- **Vitest unit** (`derive-stage-cells.test.ts` extension): 4 cases — running mid-render, done, failed, cancelled.
- **Playwright** (manual local — already in `_user-workflow.spec.ts`, sharpen Step 15): trigger a render via API mock (or skip if no real render runs in CI), assert 4th stage cell flips from idle through warn to done within timeout.

## Files

| File | Change | LOC |
|---|---|---|
| `backend/renderer.py` | `_emit_render_event` helper + 3 emit calls inside render thread | +30 |
| `backend/routes/render.py` | If emit calls live here (depending on where `_run_render_job` resides), wire as above | varies |
| `backend/tests/test_render_socket.py` | **NEW** 3 tests | ~80 |
| `frontend/src/lib/socket-events.ts` | 3 event types + 2 state fields + 3 reducer cases | +40 |
| `frontend/src/providers/SocketProvider.tsx` | 3 new `socket.on()` listeners | +12 |
| `frontend/src/providers/SocketProvider.test.tsx` | + 3 reducer cases | +30 |
| `frontend/src/hooks/useWorkerStatus.ts` | Parallel-fetch `/api/renders/in-progress` and merge | +20 |
| `frontend/src/pages/Console/derive-stage-cells.ts` | Position 3 logic + `DeriveInput` field additions | +15 |
| `frontend/src/pages/Console/derive-stage-cells.test.ts` | + 4 render cases | +40 |
| `frontend/src/pages/Console/to-console-file.ts` | Forward renderStatus + renderProgress | +5 |
| `frontend/src/pages/Console/WorkerStatus.tsx` | Stage-tag mapping `render` → `燒字` | +3 |

---

# Section 3 — 4-state stage lifecycle (Bug 3: 8s idle)

## Problem

A file enqueued via `/api/transcribe` shows `idle` (grey) on its ASR cell until `pipeline_stage_progress` fires with a non-zero `percent`. For v6 VAD pipelines, the Silero VAD pass processes the entire audio file before yielding its first progress callback — typically 10-30 seconds for a 4-minute clip. During this window the user sees a stationary grey bar and concludes "stuck", as reported during live testing.

The underlying `pipeline_stage_start` event already fires at the moment the stage begins. The `useSocket()` reducer simply doesn't expose this signal to `deriveStageCells`, and the derive function treats `status === 'running'` with `percent === 0` as effectively idle.

## Solution

Extend the cell state enum from 4 values to 6, adding `queued` (in JobQueue but not yet picked up) and `starting` (stage start fired but no progress yet). Track these via a new `stagePhase` field in `SocketState` that's distinct from `stageProgress` and `stageStatus`. Drive a CSS pulse animation on both new states so the cell shows visible motion the instant a job is enqueued.

```
T+0   User drops file
      file_added (FILE_ADDED reducer)
      → stagePhase[fid][0] = 'queued'              cell: queued (pulse)
T+1   Worker picks up job, starts ASR stage
      pipeline_stage_start (STAGE_START reducer)
      → stagePhase[fid][0] = 'starting'            cell: starting (pulse + 5% fill hint)
T+8   First pipeline_stage_progress percent=12
      → stagePhase[fid][0] = 'running'             cell: warn 12% (solid fill)
T+30  Last pipeline_stage_progress percent=100 or pipeline_stage_done
      → stagePhase[fid][0] removed/cleared         cell: done
```

Each transition is driven by a real socket event already emitted by `pipeline_runner.py` — no backend changes required for this section.

## Type changes

```ts
// frontend/src/pages/Console/types.ts
export type ConsoleStageCellState =
  | 'idle'      // never ran (default)
  | 'queued'    // job in queue, worker hasn't started — pulse
  | 'starting'  // pipeline_stage_start fired, no progress yet — pulse + faint fill hint
  | 'warn'      // running with percent > 0 — solid fill, percent-driven width
  | 'done'      // pipeline_stage_done with status='done', or percent === 100
  | 'err';      // pipeline_stage_done with status='failed', or file.status === 'failed' early
```

```ts
// frontend/src/lib/socket-events.ts
export interface SocketState {
  ... existing ...
  // NEW: per file_id, per stage index, current lifecycle phase.
  // Distinct from stageStatus which tracks pipeline_stage_progress-derived state.
  // Phases progress: queued → starting → running → (cleared on done/failed)
  stagePhase: Record<string, Record<number, 'queued' | 'starting' | 'running'>>;
}
```

## Reducer transitions

```ts
// FILE_ADDED with status === 'queued' or 'uploaded' and a pipeline_id set:
state.stagePhase[file.id] = { 0: 'queued' };

// STAGE_PROGRESS_START (new derived action from pipeline_stage_start socket event):
state.stagePhase[file_id][stage_index] = 'starting';

// STAGE_PROGRESS with percent > 0:
state.stagePhase[file_id][stage_index] = 'running';

// STAGE_COMPLETE with status='done':
delete state.stagePhase[file_id][stage_index];  // cleared, next stage will set itself

// PIPELINE_COMPLETE / PIPELINE_FAILED:
delete state.stagePhase[file_id];  // entire entry cleared
```

`SocketProvider.tsx` needs to add a listener for `pipeline_stage_start` (currently only `pipeline_stage_progress` and `pipeline_stage_complete` are listened to — verified via inventory). The new listener dispatches the new `STAGE_START` action.

## `deriveStageCells` logic update

```ts
function deriveCellForStage(idx: number, input: DeriveInput): ConsoleStageCell {
  const phase = input.stagePhaseMap[idx];
  const prog = input.stageProgressMap[idx];

  // Terminal states win
  if (prog?.status === 'failed') return { state: 'err' };
  if (prog?.status === 'done' || prog?.percent === 100) return { state: 'done' };

  // Lifecycle phase trumps absence of progress
  if (phase === 'queued') return { state: 'queued' };
  if (phase === 'starting') return { state: 'starting' };
  if (phase === 'running') {
    return { state: 'warn', percent: prog?.percent ?? 0 };
  }
  // Fallback to progress-status detection (for files seen via BULK_FILES before any new events arrive)
  if (prog?.status === 'running') return { state: 'warn', percent: prog.percent };
  return { state: 'idle' };
}
```

The function preserves the existing behavior for files that arrive via `BULK_FILES` from `/api/files` (which doesn't carry stage phase info) by falling through to `prog.status === 'running'`. Only files seen via live socket events benefit from the queued/starting states, which is fine — those are the only ones for which the bug is observable.

Position 0 (ASR), 1 (MT) and 3 (Render — after Section 2 wiring) all use this helper. Position 2 (Proofread) is approval-derived and does not gain new states; it stays `idle` / `warn(pct)` / `done`.

## CSS animations

```css
/* Append to frontend/src/styles/console.css */
@keyframes con-cell-pulse {
  0%, 100% { opacity: 0.4; }
  50%      { opacity: 1; }
}

.con-q-stages i.queued {
  background: var(--accent-soft);
  animation: con-cell-pulse 1.4s ease-in-out infinite;
}

.con-q-stages i.starting {
  background: linear-gradient(90deg, var(--warning) 5%, var(--surface-3) 5%);
  animation: con-cell-pulse 1.4s ease-in-out infinite;
}
```

The keyframe is shared with the existing `r-dot--pulse` cadence (1.4s) for visual coherence — every "active, indeterminate" UI surface in the Console pulses on the same beat.

## Error handling

- Stage index out of `[0, 3]` → `deriveCellForStage` short-circuits via the position-N caller; never indexed past 3.
- `stagePhase[fid]` missing → `phase` is `undefined`, falls through to the legacy progress-status path. No throw.
- Stage transitions out of order (e.g. `STAGE_PROGRESS` arrives before `STAGE_START`) → the reducer's `STAGE_PROGRESS` handler also sets `stagePhase[fid][idx]` to `'running'`, so the missing `starting` phase doesn't strand the cell.
- File deleted mid-pipeline (`FILE_REMOVED`) → existing reducer case already cleans up `stageProgress` / `stageStatus`; extend it to also clean `stagePhase[file_id]`.

## Testing

- **Vitest unit** (`derive-stage-cells.test.ts` extension), 6 new cases:
  - `queued` phase → cell state `queued`
  - `starting` phase → cell state `starting`
  - `running` phase with `percent: 0` → cell state `warn` (percent 0)
  - `running` phase with `percent: 47` → cell state `warn` (percent 47)
  - Phase missing + `prog.status: 'running'` → falls through to `warn`
  - `prog.status: 'failed'` short-circuits regardless of phase → `err`
- **Vitest unit** (`SocketProvider.test.tsx`): 2 new cases — `STAGE_START` action sets `stagePhase[fid][idx] = 'starting'`, `FILE_REMOVED` clears `stagePhase[fid]`.
- **Playwright**: extend `_user-workflow.spec.ts` Step 12 to assert that within 2 seconds of upload, the first stage cell's className includes `queued` or `starting` (not `idle`). This converts the current ⚠ partial to a real assertion.

## Files

| File | Change | LOC |
|---|---|---|
| `frontend/src/pages/Console/types.ts` | 2 new enum literals | +2 |
| `frontend/src/lib/socket-events.ts` | `stagePhase` state field + 1 new action + 3 reducer cases + cleanup paths | +30 |
| `frontend/src/providers/SocketProvider.tsx` | `pipeline_stage_start` listener | +5 |
| `frontend/src/pages/Console/derive-stage-cells.ts` | Lifecycle-aware `deriveCellForStage` helper, position 0/1/3 use it | +30 / -10 |
| `frontend/src/pages/Console/to-console-file.ts` | Pass `stagePhaseMap` | +3 |
| `frontend/src/styles/console.css` | 2 keyframes + 2 selector rules | +20 |
| `frontend/src/pages/Console/derive-stage-cells.test.ts` | + 6 cases | +60 |
| `frontend/src/providers/SocketProvider.test.tsx` | + 2 cases | +20 |
| `frontend/tests-e2e/_user-workflow.spec.ts` | Step 12 sharpened to real assertion | +5 |

---

# Cross-cutting concerns

## Backwards compatibility

- Existing dashboard at `/` (Bold variant) does not consume any of the new context / state fields. Unchanged.
- v4 / v5 / v6 pipelines all already emit `pipeline_stage_start` (verified in `backend/pipeline_runner.py`). No backend changes required for Section 3.
- `/api/renders/in-progress` exists per CLAUDE.md; if its response shape doesn't match the `RenderInProgress` type assumed in Section 2's merge code, the implementation plan must adapt (verify before coding).

## Performance

- Socket reducer state grows by 2 new maps (`renderProgress`, `renderStatus`) and 1 new nested map (`stagePhase`). Each is keyed on file_id (~dozens of entries max in normal use). Memory is negligible.
- VideoControlContext adds 4 React event listeners to the active `<video>` element. The `timeupdate` event fires ~4 times/second during playback; `setCurrentTime` is called the same rate but only re-renders TransportBar (one component). Acceptable.
- Render `/api/renders/in-progress` polling: piggybacks on the existing 3-second `useWorkerStatus` cadence. No additional poll loop introduced.

## Failure modes documented

- VideoControlContext: covered in Section 1's "Error handling".
- Render socket events: covered in Section 2's "Error handling".
- Stage lifecycle: covered in Section 3's "Error handling".

The common thread: every action is null-safe and degrades to the existing pre-spec behavior rather than throwing.

---

# Out of scope

- ⌘← / ⌘→ seek hotkeys, ⌘↑ / ⌘↓ volume — VideoControlContext makes them trivial to add but they're deferred to a follow-up.
- Refactoring render workflow into JobQueue (would let renders share the entire pipeline_run pipeline). The plan chose Section 2 Option C precisely to avoid this large refactor.
- Backend `pipeline_stage_progress` cadence tuning. Current ~5% delta is fine for visual feedback.
- Updates to the legacy `/` Bold Dashboard. It will not benefit from these changes, by design (Console-only scope).

# Open questions (none blocking)

- Whether `pipeline_stage_start` is currently registered as a socket.on listener in `SocketProvider.tsx`. Spec assumes no, implementation step 1 verifies via grep.
- Whether `_render_jobs` map in `routes/render.py` is keyed on render_id or file_id. Spec assumes render_id; check during implementation.

---

# Acceptance criteria

When this spec is implemented, the following must all be true:

1. ✅ Pressing Space with a queue item selected and a video loaded → `videoEl.paused` flips true ↔ false within 100ms (verifiable via Playwright).
2. ✅ Starting a render via `POST /api/render` → the 4th stage cell of the matching queue item transitions through `idle` → `warn(0%)` → `warn(N%)` → `done` (or `err`) without page reload.
3. ✅ Starting a render → an active card appears in WorkerStatus with tag `燒字` and percent progress.
4. ✅ Uploading a new file → ASR cell shows `queued` (pulsing) within 1 second of dropzone confirmation.
5. ✅ Backend `pipeline_stage_start` fires before first `pipeline_stage_progress` → ASR cell transitions through `queued` → `starting` (pulse + faint fill) → `warn(N%)` (solid fill).
6. ✅ Existing `console.spec.ts` (10 tests) still passes; existing `dashboard.spec.ts` / `bold-dashboard.spec.ts` still pass (unchanged).
7. ✅ All vitest tests still pass; backend `1047 PASS / 23 baseline failed` unchanged + 3 new render-event tests pass.
