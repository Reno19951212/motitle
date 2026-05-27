# Queue Execution Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the reducer's `stagePhase` + `stageProgress` state into Dashboard's queue row + stage badge so every pipeline lifecycle state (queued / starting / running NN% / done / failed) renders inline, and dispatch an optimistic `STAGE_START` on click so there is zero visual gap between pressing 「執行」 and the row turning cyan.

**Architecture:** Pure data-flow wire — the reducer state and backend socket events already exist (originally added for the retired Console UI; preserved on revert). Dashboard's `toDesignFile()` derive function is extended with a 5-phase state machine, `<QueueRow>`'s stage-pill JSX is replaced with two pure helper functions, `MoTitleStageBadge` gains 2 new cases, and the click handlers dispatch `STAGE_START` with an optional `phase='queued'` before the backend confirms.

**Tech Stack:** React 18, TypeScript strict (`noUncheckedIndexedAccess: true`), Vitest 2 + @testing-library/react, existing Zustand-free reducer pattern under `SocketProvider`.

**Spec:** [`docs/superpowers/specs/2026-05-27-queue-execution-feedback-design.md`](../specs/2026-05-27-queue-execution-feedback-design.md)

---

## File Structure

**New files (5):**
- `frontend/src/pages/Dashboard-pill-helpers.ts` — pure `pillClass()` + `pillLabel()` functions
- `frontend/src/pages/Dashboard-pill-helpers.test.ts` — unit tests
- `frontend/src/pages/Dashboard-to-design-file.test.ts` — unit tests for `toDesignFile()` derive
- `frontend/src/lib/motitle-icons.test.tsx` — unit tests for `<MoTitleStageBadge>` new cases
- `frontend/src/lib/socket-events.test.ts` — unit tests for `STAGE_START` optional `phase` field

**Modified files (4):**
- `frontend/src/lib/socket-events.ts` — extend `StageStartEvent` + `STAGE_START` reducer case
- `frontend/src/lib/motitle-icons.tsx` — add `queued` + `starting` switch cases + extend `StageBadgeFile`
- `frontend/src/styles/motitle-bold.css` — add `.stage-pill.queued` + `.stage-pill.starting` classes
- `frontend/src/pages/Dashboard.tsx` — extend `DesignFile` + `toDesignFile()`, replace `<QueueRow>` pill JSX, drop legacy `stageForStagePill()`, dispatch optimistic `STAGE_START` in `handleRun*`

**Field-name note (gotcha):** `StageStartEvent.stage_index` and `StageProgressEvent.stage_idx` use different field names — the existing reducer matches each. Plan code blocks below honour the existing names. Do not rename either.

---

## Task 1: pillClass + pillLabel pure helpers

**Files:**
- Create: `frontend/src/pages/Dashboard-pill-helpers.ts`
- Test:   `frontend/src/pages/Dashboard-pill-helpers.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/pages/Dashboard-pill-helpers.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { pillClass, pillLabel, type StagePhase } from './Dashboard-pill-helpers';

describe('pillClass', () => {
  const cases: Array<[StagePhase, string]> = [
    ['idle',     'idle'],
    ['queued',   'queued'],
    ['starting', 'starting'],
    ['running',  'warn'],
    ['done',     'ok'],
    ['failed',   'err'],
  ];
  it.each(cases)('phase %s → class %s', (phase, expected) => {
    expect(pillClass(phase)).toBe(expected);
  });
});

describe('pillLabel', () => {
  it('idle ignores percent', () => {
    expect(pillLabel('idle', 0)).toBe('—');
    expect(pillLabel('idle', 27)).toBe('—');
  });
  it('queued / starting / done / failed ignore percent', () => {
    expect(pillLabel('queued',   0)).toBe('已排隊');
    expect(pillLabel('queued',   27)).toBe('已排隊');
    expect(pillLabel('starting', 0)).toBe('準備中');
    expect(pillLabel('done',     100)).toBe('完成');
    expect(pillLabel('failed',   50)).toBe('失敗');
  });
  it('running formats percent as integer + % sign', () => {
    expect(pillLabel('running', 0)).toBe('0%');
    expect(pillLabel('running', 27)).toBe('27%');
    expect(pillLabel('running', 100)).toBe('100%');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
cd frontend
npx vitest run src/pages/Dashboard-pill-helpers.test.ts
```

Expected: FAIL with "Cannot find module './Dashboard-pill-helpers'".

- [ ] **Step 3: Write minimal implementation**

`frontend/src/pages/Dashboard-pill-helpers.ts`:

```ts
// Pure helpers shared by Dashboard.tsx's <QueueRow>. Extracted to a sibling
// file so vitest can exercise the phase→class and phase→label contracts
// without rendering Dashboard (which depends on SocketProvider, Router, etc).
//
// 5-state phase machine + idle = 6 phases total. See
// docs/superpowers/specs/2026-05-27-queue-execution-feedback-design.md §4.
export type StagePhase =
  | 'idle'
  | 'queued'
  | 'starting'
  | 'running'
  | 'done'
  | 'failed';

export function pillClass(phase: StagePhase): string {
  switch (phase) {
    case 'idle':     return 'idle';
    case 'queued':   return 'queued';
    case 'starting': return 'starting';
    case 'running':  return 'warn';
    case 'done':     return 'ok';
    case 'failed':   return 'err';
  }
}

export function pillLabel(phase: StagePhase, percent: number): string {
  switch (phase) {
    case 'idle':     return '—';
    case 'queued':   return '已排隊';
    case 'starting': return '準備中';
    case 'running':  return `${percent}%`;
    case 'done':     return '完成';
    case 'failed':   return '失敗';
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```
npx vitest run src/pages/Dashboard-pill-helpers.test.ts
```

Expected: PASS — 3 describe blocks, ~14 cases.

- [ ] **Step 5: Run tsc**

```
npx tsc --noEmit
```

Expected: No new errors in Dashboard-pill-helpers.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard-pill-helpers.ts \
        frontend/src/pages/Dashboard-pill-helpers.test.ts
git commit -m "feat(dashboard): pillClass + pillLabel pure helpers (6-phase contract)"
```

---

## Task 2: STAGE_START accepts optional phase

**Files:**
- Modify: `frontend/src/lib/socket-events.ts` — interface `StageStartEvent` lines 41–46; reducer `STAGE_START` case lines 176–186
- Test:   `frontend/src/lib/socket-events.test.ts` (new file)

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/socket-events.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { socketReducer, initialSocketState } from './socket-events';

describe('socketReducer / STAGE_START', () => {
  it('without phase, defaults to "starting" (backward-compat)', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr' },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('starting');
  });

  it('with phase="queued", writes "queued" (optimistic click path)', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr', phase: 'queued' },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
  });

  it('with phase="starting" explicit, writes "starting"', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr', phase: 'starting' },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('starting');
  });

  it('does not clobber other files / stages', () => {
    const seeded = {
      ...initialSocketState,
      stagePhase: { other: { 0: 'running' as const }, fid1: { 1: 'done' as const } },
    };
    const next = socketReducer(seeded, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr', phase: 'queued' },
    });
    expect(next.stagePhase.other?.[0]).toBe('running');
    expect(next.stagePhase.fid1?.[1]).toBe('done');
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npx vitest run src/lib/socket-events.test.ts
```

Expected: 3 of 4 PASS (the default-starting test will pass against current code), the explicit-phase tests FAIL because `phase` field is not yet accepted.

- [ ] **Step 3: Extend the interface**

In `frontend/src/lib/socket-events.ts`, update `StageStartEvent` (currently lines 41–46):

```ts
export interface StageStartEvent {
  file_id: string;
  stage_index: number;
  stage_type: string;
  stage_ref?: string;
  /** Optional override for the phase to write into reducer state.
   *  Default 'starting' (backend pipeline_stage_start event path).
   *  Set to 'queued' for the optimistic click-handler path in Dashboard so
   *  the queue row turns cyan with zero delay between click and feedback. */
  phase?: 'queued' | 'starting';
}
```

- [ ] **Step 4: Update the STAGE_START reducer case**

In the same file, replace the existing `STAGE_START` case (lines 176–186):

```ts
case 'STAGE_START': {
  const { file_id, stage_index, phase = 'starting' } = action.ev;
  const prev = state.stagePhase[file_id] ?? {};
  return {
    ...state,
    stagePhase: {
      ...state.stagePhase,
      [file_id]: { ...prev, [stage_index]: phase },
    },
  };
}
```

- [ ] **Step 5: Run test to verify it passes**

```
npx vitest run src/lib/socket-events.test.ts
```

Expected: PASS — all 4 cases.

- [ ] **Step 6: Run tsc + full vitest to confirm no regression**

```
npx tsc --noEmit
npx vitest run
```

Expected: tsc clean (pre-existing v6-pipeline-smoke errors permitted). Vitest: 269 + 4 new = 273 pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/socket-events.ts \
        frontend/src/lib/socket-events.test.ts
git commit -m "feat(reducer): STAGE_START accepts optional phase ('queued' | 'starting')"
```

---

## Task 3: MoTitleStageBadge — queued + starting cases

**Files:**
- Modify: `frontend/src/lib/motitle-icons.tsx` — `StageBadgeFile` interface lines 91–95, `MoTitleStageBadge` switch lines 97–...
- Test:   `frontend/src/lib/motitle-icons.test.tsx` (new file)

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/motitle-icons.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MoTitleStageBadge } from './motitle-icons';

describe('<MoTitleStageBadge>', () => {
  it('asrPhase="queued" → 排隊中 badge with pulsing dot', () => {
    render(<MoTitleStageBadge file={{ stage: 'idle', asrPhase: 'queued' }} />);
    const badge = screen.getByText(/排隊中/);
    expect(badge).toBeInTheDocument();
    expect(badge.closest('.badge')).toHaveClass('badge--queued');
    expect(badge.closest('.badge')?.querySelector('.dot')).not.toBeNull();
  });

  it('asrPhase="starting" → 準備中 badge with pulsing dot', () => {
    render(<MoTitleStageBadge file={{ stage: 'idle', asrPhase: 'starting' }} />);
    const badge = screen.getByText(/準備中/);
    expect(badge).toBeInTheDocument();
    expect(badge.closest('.badge')).toHaveClass('badge--processing');
    expect(badge.closest('.badge')?.querySelector('.dot')).not.toBeNull();
  });

  it('asrPhase="queued" takes precedence over legacy file.stage="idle"', () => {
    render(<MoTitleStageBadge file={{ stage: 'idle', asrPhase: 'queued' }} />);
    expect(screen.getByText(/排隊中/)).toBeInTheDocument();
  });

  it('no asrPhase → falls through to legacy file.stage switch', () => {
    render(<MoTitleStageBadge file={{ stage: 'transcribing', transcribeProgress: 42 }} />);
    expect(screen.getByText(/轉錄中/)).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npx vitest run src/lib/motitle-icons.test.tsx
```

Expected: FAIL on first 3 cases — `asrPhase` field not in `StageBadgeFile`; TypeScript error or runtime fall-through to default case.

- [ ] **Step 3: Extend StageBadgeFile interface**

In `frontend/src/lib/motitle-icons.tsx`, replace lines 91–95:

```tsx
export interface StageBadgeFile {
  stage: string;
  transcribeProgress?: number;
  renderProgress?: number;
  /** Phase of stage 0 (ASR). When set, takes precedence over the legacy
   *  `stage` field. New 6-phase model — see Dashboard-pill-helpers.ts. */
  asrPhase?: 'idle' | 'queued' | 'starting' | 'running' | 'done' | 'failed';
  asrPercent?: number;
}
```

- [ ] **Step 4: Prepend new cases inside MoTitleStageBadge switch**

In `frontend/src/lib/motitle-icons.tsx`, immediately after `export function MoTitleStageBadge({ file }: { file: StageBadgeFile }) {` (around line 97), insert the precedence guard before the existing `switch (file.stage)`:

```tsx
export function MoTitleStageBadge({ file }: { file: StageBadgeFile }) {
  // New 6-phase model takes precedence when asrPhase is set. Legacy
  // file.stage fall-through still serves Dashboard rows that haven't been
  // re-derived through the new toDesignFile() (graceful migration).
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

  switch (file.stage) {
    // ...existing transcribing / translating / proofreading / rendering /
    // done / error cases unchanged
```

(All existing switch cases below stay byte-for-byte identical. Do not edit them in this task.)

- [ ] **Step 5: Run test to verify it passes**

```
npx vitest run src/lib/motitle-icons.test.tsx
```

Expected: PASS — 4 cases.

- [ ] **Step 6: Run full vitest + tsc**

```
npx vitest run
npx tsc --noEmit
```

Expected: 269 + 4 (Task 2) + 4 = 277 pass; tsc clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/motitle-icons.tsx \
        frontend/src/lib/motitle-icons.test.tsx
git commit -m "feat(badge): MoTitleStageBadge 排隊中 + 準備中 cases via asrPhase"
```

---

## Task 4: CSS for queued + starting pills

**Files:**
- Modify: `frontend/src/styles/motitle-bold.css` — insert after the existing `.stage-pill.err` rule (currently line 677)

- [ ] **Step 1: Append the 2 new rules**

After the existing block (lines 664–677), append:

```css
/* Phase: queued — waiting for backend worker pickup. Cyan border with
 * a slow pulse so the row clearly signals "the request was accepted, the
 * worker just hasn't started yet". Wired by Dashboard-pill-helpers.ts. */
.motitle-bold .stage-pill.queued {
  border-color: rgba(56,189,248,0.35);
  color: var(--info);
  animation: pulse 1.3s infinite;
}
/* Phase: starting — backend picked the job up, model loading / first
 * segment not yet emitted. Amber pulsing transitional state before the
 * first pipeline_stage_progress event flips this to plain .warn. */
.motitle-bold .stage-pill.starting {
  border-color: rgba(245,158,11,0.35);
  color: var(--warning);
  animation: pulse 1.3s infinite;
}
```

- [ ] **Step 2: Verify CSS lints clean**

```
npx tsc --noEmit
```

(No vitest test for pure CSS rules — visual verification happens at the end of Task 7.)

Expected: tsc clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/motitle-bold.css
git commit -m "style(dashboard): .stage-pill.queued + .stage-pill.starting (pulse animation)"
```

---

## Task 5: DesignFile + toDesignFile derive 5-phase

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` — `DesignFile` interface lines 94–106; `toDesignFile` lines 114–...
- Test:   `frontend/src/pages/Dashboard-to-design-file.test.ts` (new file)

- [ ] **Step 1: Write the failing test**

`frontend/src/pages/Dashboard-to-design-file.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { toDesignFile } from './Dashboard';
import type { FileRecord, StageStatus } from '@/lib/socket-events';

const baseFile: FileRecord = {
  id: 'fid1',
  original_name: 'video.mp4',
  status: 'uploaded',
  uploaded_at: 1000,
};

describe('toDesignFile — phase derivation', () => {
  it('idle: no stagePhase, no stageStatus → asrPhase="idle"', () => {
    const d = toDesignFile(baseFile, undefined, undefined, undefined);
    expect(d.asrPhase).toBe('idle');
    expect(d.asrPercent).toBe(0);
    expect(d.mtPhase).toBe('idle');
    expect(d.mtPercent).toBe(0);
  });

  it('queued: stagePhase[0]="queued", no stageStatus → asrPhase="queued"', () => {
    const d = toDesignFile(baseFile, undefined, undefined, { 0: 'queued' });
    expect(d.asrPhase).toBe('queued');
    expect(d.asrPercent).toBe(0);
    expect(d.mtPhase).toBe('idle');
  });

  it('starting: stagePhase[0]="starting"', () => {
    const d = toDesignFile(baseFile, undefined, undefined, { 0: 'starting' });
    expect(d.asrPhase).toBe('starting');
    expect(d.asrPercent).toBe(0);
  });

  it('running 27%: stageProgress[0]=27 + stagePhase[0]="running" → asrPercent=27', () => {
    const d = toDesignFile(
      baseFile,
      { 0: 27 },
      { 0: 'running' as StageStatus },
      { 0: 'running' },
    );
    expect(d.asrPhase).toBe('running');
    expect(d.asrPercent).toBe(27);
  });

  it('ASR done + MT stage_idx=1 running 50%', () => {
    const d = toDesignFile(
      baseFile,
      { 0: 100, 1: 50 },
      { 0: 'done' as StageStatus, 1: 'running' as StageStatus },
      { 0: 'running', 1: 'running' },
    );
    expect(d.asrPhase).toBe('done');
    expect(d.asrPercent).toBe(100);
    expect(d.mtPhase).toBe('running');
    expect(d.mtPercent).toBe(50);
  });

  it('ASR failed → asrPhase="failed", ignores stagePhase', () => {
    const d = toDesignFile(
      baseFile,
      { 0: 80 },
      { 0: 'failed' as StageStatus },
      { 0: 'running' },
    );
    expect(d.asrPhase).toBe('failed');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npx vitest run src/pages/Dashboard-to-design-file.test.ts
```

Expected: FAIL — `toDesignFile` is not exported / signature has 3 args / `DesignFile` lacks `asrPhase` etc.

- [ ] **Step 3: Extend the DesignFile interface**

In `frontend/src/pages/Dashboard.tsx`, replace lines 94–106:

```tsx
import type { StagePhase } from './Dashboard-pill-helpers';

interface DesignFile {
  id: string;
  name: string;
  duration: string;
  segments: number;
  approved: number;
  uploaded: string;
  /** derived stage string for display — kept for legacy badge / inspector */
  stage: string;
  transcribeProgress: number;
  renderProgress: number;
  size: string;
  // New 6-phase fields — see docs/superpowers/specs/2026-05-27-queue-execution-feedback-design.md
  asrPhase:   StagePhase;
  asrPercent: number;
  mtPhase:    StagePhase;
  mtPercent:  number;
}
```

- [ ] **Step 4: Extend toDesignFile signature + derive**

In `frontend/src/pages/Dashboard.tsx`, replace the existing `function toDesignFile(...)` signature and body. The function is currently at line 114 and ends near line ~180 (returns the DesignFile object). Find the existing function and replace **only the signature line + insert the new derive helper above it + add the 4 new fields to the returned object**. Pseudo-shape after edit:

```tsx
function deriveStagePhase(
  idx: number,
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, StageStatus> | undefined,
  stagePhase: Record<number, 'queued' | 'starting' | 'running'> | undefined,
): { phase: StagePhase; percent: number } {
  const status = stageStatus?.[idx];
  // Terminal states win — backend told us done / failed, ignore phase.
  if (status === 'done')   return { phase: 'done',   percent: 100 };
  if (status === 'failed') return { phase: 'failed', percent: stageProgress?.[idx] ?? 0 };
  // Otherwise consult phase (queued / starting / running).
  const phase = stagePhase?.[idx];
  if (phase === 'queued')   return { phase: 'queued',   percent: 0 };
  if (phase === 'starting') return { phase: 'starting', percent: 0 };
  if (phase === 'running')  return { phase: 'running',  percent: stageProgress?.[idx] ?? 0 };
  return { phase: 'idle', percent: 0 };
}

// MT representative phase: highest stage_idx (>=1) with any phase or status set;
// if none, fall back to idle. The intent is "show the latest active MT stage";
// when multiple MT stages are scheduled sequentially, only one is non-idle at a
// time so this trivially picks the right one.
function deriveMtPhase(
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, StageStatus> | undefined,
  stagePhase: Record<number, 'queued' | 'starting' | 'running'> | undefined,
): { phase: StagePhase; percent: number } {
  const indices = new Set<number>();
  for (const k of Object.keys(stageProgress ?? {})) indices.add(Number(k));
  for (const k of Object.keys(stageStatus ?? {}))   indices.add(Number(k));
  for (const k of Object.keys(stagePhase ?? {}))    indices.add(Number(k));
  const mtIndices = Array.from(indices).filter(i => i >= 1).sort((a, b) => b - a);
  for (const i of mtIndices) {
    const d = deriveStagePhase(i, stageProgress, stageStatus, stagePhase);
    if (d.phase !== 'idle') return d;
  }
  return { phase: 'idle', percent: 0 };
}

export function toDesignFile(
  f: FileRecord,
  stageProgress: Record<number, number> | undefined,
  stageStatus: Record<number, StageStatus> | undefined,
  stagePhase: Record<number, 'queued' | 'starting' | 'running'> | undefined,
): DesignFile {
  // ...existing derive logic for stage / transcribeProgress / renderProgress /
  //    duration / uploaded / size — keep unchanged ...

  const asr = deriveStagePhase(0, stageProgress, stageStatus, stagePhase);
  const mt  = deriveMtPhase(stageProgress, stageStatus, stagePhase);

  return {
    // ...existing fields unchanged
    asrPhase:   asr.phase,
    asrPercent: asr.percent,
    mtPhase:    mt.phase,
    mtPercent:  mt.percent,
  };
}
```

**Important:** preserve every existing field in the returned object. Only **add** the 4 new fields (`asrPhase`, `asrPercent`, `mtPhase`, `mtPercent`) and **add** the `stagePhase` parameter to the signature.

The `export` keyword on `toDesignFile` is new — required so the test can import it. The function was previously module-private.

- [ ] **Step 5: Update the only caller of toDesignFile**

In `frontend/src/pages/Dashboard.tsx`, the only caller is currently around line 1974–1975:

```tsx
const files: DesignFile[] = useMemo(
  () => filesRaw.map((f) => toDesignFile(f, state.stageProgress[f.id], state.stageStatus[f.id])),
```

Replace with:

```tsx
const files: DesignFile[] = useMemo(
  () => filesRaw.map((f) =>
    toDesignFile(f, state.stageProgress[f.id], state.stageStatus[f.id], state.stagePhase[f.id])),
```

Add `state.stagePhase` to the `useMemo` dep array (it's `[state]` so already covered, but verify).

- [ ] **Step 6: Run test to verify it passes**

```
npx vitest run src/pages/Dashboard-to-design-file.test.ts
```

Expected: PASS — 6 cases.

- [ ] **Step 7: Run full vitest + tsc**

```
npx vitest run
npx tsc --noEmit
```

Expected: tsc clean. Full vitest: 277 + 6 = 283 pass. `Dashboard.test.tsx` and existing tests that build off `DesignFile` keep passing because new fields are additive.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx \
        frontend/src/pages/Dashboard-to-design-file.test.ts
git commit -m "feat(dashboard): DesignFile.{asrPhase,mtPhase} derived from stagePhase + stageStatus"
```

---

## Task 6: QueueRow JSX uses new helpers + fields

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` — `stageForStagePill()` (line 195–201), QueueRow JSX (lines 906–931)

- [ ] **Step 1: Import pill-helpers**

Near the top of `frontend/src/pages/Dashboard.tsx`, add:

```tsx
import { pillClass, pillLabel } from './Dashboard-pill-helpers';
```

- [ ] **Step 2: Delete the legacy stageForStagePill function**

In `frontend/src/pages/Dashboard.tsx`, delete lines 195–201:

```tsx
function stageForStagePill(stage: string): { asr: string; mt: string } {
  if (stage === 'error') return { asr: 'err', mt: 'err' };
  if (stage === 'transcribing') return { asr: 'warn', mt: 'idle' };
  if (stage === 'translating') return { asr: 'ok', mt: 'warn' };
  if (stage === 'proofreading' || stage === 'rendering' || stage === 'done') return { asr: 'ok', mt: 'ok' };
  return { asr: 'idle', mt: 'idle' };
}
```

- [ ] **Step 3: Delete the `const stages` line inside QueueRow**

Find the line inside the QueueRow component (currently around line 860):

```tsx
const stages = stageForStagePill(f.stage);
```

Delete it.

- [ ] **Step 4: Replace QueueRow stage-pill JSX**

Replace the existing block (currently lines 906–931):

```tsx
      <div className="stage">
        <div className={`stage-pill ${stages.asr}`}>
          <span className="lb">ASR</span>
          <span>
            {f.stage === 'transcribing'
              ? `${f.transcribeProgress}%`
              : stages.asr === 'ok'
              ? '完成'
              : stages.asr === 'err'
              ? '失敗'
              : '—'}
          </span>
        </div>
        <div className={`stage-pill ${stages.mt}`}>
          <span className="lb">MT</span>
          <span>
            {f.stage === 'translating'
              ? '翻譯中'
              : stages.mt === 'ok'
              ? '完成'
              : stages.mt === 'err'
              ? '失敗'
              : '—'}
          </span>
        </div>
      </div>
```

With:

```tsx
      <div className="stage">
        <div className={`stage-pill ${pillClass(f.asrPhase)}`}>
          <span className="lb">ASR</span>
          <span>{pillLabel(f.asrPhase, f.asrPercent)}</span>
        </div>
        <div className={`stage-pill ${pillClass(f.mtPhase)}`}>
          <span className="lb">MT</span>
          <span>{pillLabel(f.mtPhase, f.mtPercent)}</span>
        </div>
      </div>
```

- [ ] **Step 5: Pass new phase fields to MoTitleStageBadge**

QueueRow currently renders `<MoTitleStageBadge file={f} />` (line 875). `f` is a `DesignFile` which now includes `asrPhase` + `asrPercent`; `MoTitleStageBadge`'s `StageBadgeFile` interface (Task 3) accepts both optionally. **No JSX change needed** — TypeScript will accept the wider object via structural subtyping.

Verify by grepping that QueueRow still passes `file={f}`:

```
grep -n 'MoTitleStageBadge file={f}' frontend/src/pages/Dashboard.tsx
```

Expected: one match in QueueRow.

- [ ] **Step 6: Run full vitest + tsc**

```
npx vitest run
npx tsc --noEmit
```

Expected: All 283 tests still pass; tsc clean.

- [ ] **Step 7: Manual visual verify in Vite dev**

Start Vite + Flask if not already running:

```
cd frontend
npx vite --force &   # background
```

Open Chrome to `http://localhost:5173/`, log in, observe the queue panel on the left. A file with `stage='idle'` should now show ASR pill `—` (grey, no animation) and MT pill `—` (grey). Files mid-pipeline should show their current phase chip.

Acceptance: zero TypeScript / runtime errors, queue rows render at least as well as before.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "refactor(dashboard): QueueRow renders 6-phase pills via pill-helpers"
```

---

## Task 7: Optimistic STAGE_START on click

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` — `handleRun()` (lines 2050–2069) and `handleRunFile()` (lines 2071–2086)

- [ ] **Step 1: Read dispatch from useSocket**

Inside the Dashboard component (where `useSocket()` is already called — search for `useSocket(`), capture `dispatch` alongside the existing destructure:

```tsx
const { state, dispatch, refresh } = useSocket();  // dispatch already exposed in SocketContextValue
```

(If `state` is destructured separately and `dispatch` is not yet on the line, add it. If `useSocket()` is called twice, consolidate.)

- [ ] **Step 2: Update handleRun to dispatch optimistic STAGE_START**

Replace lines 2050–2069 (the current `handleRun` callback) with:

```tsx
const handleRun = useCallback(async () => {
  if (!selectedFileId) {
    pushToast({ title: '請先揀檔案', variant: 'destructive' });
    return;
  }
  if (!pipelineId) {
    pushToast({ title: '請先揀 Pipeline', variant: 'destructive' });
    return;
  }
  try {
    await apiFetch<{ job_id: string }>(`/api/pipelines/${pipelineId}/run`, {
      method: 'POST',
      body: JSON.stringify({ file_id: selectedFileId }),
    });
    // Optimistic — flip the row to 'queued' immediately so the user gets
    // sub-100ms visual confirmation of the click before backend pickup.
    dispatch({
      type: 'STAGE_START',
      ev: { file_id: selectedFileId, stage_index: 0, stage_type: 'asr', phase: 'queued' },
    });
    pushToast({ title: '✅ 已排隊' });
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : String(e);
    pushToast({ title: '排隊失敗', description: msg, variant: 'destructive' });
  }
}, [selectedFileId, pipelineId, pushToast, dispatch]);
```

- [ ] **Step 3: Update handleRunFile to dispatch optimistic STAGE_START**

Replace lines 2071–2086 (the current `handleRunFile` callback) with:

```tsx
const handleRunFile = useCallback(async (fileId: string) => {
  if (!pipelineId) {
    pushToast({ title: '請先揀 Pipeline', variant: 'destructive' });
    return;
  }
  try {
    await apiFetch<{ job_id: string }>(`/api/pipelines/${pipelineId}/run`, {
      method: 'POST',
      body: JSON.stringify({ file_id: fileId }),
    });
    dispatch({
      type: 'STAGE_START',
      ev: { file_id: fileId, stage_index: 0, stage_type: 'asr', phase: 'queued' },
    });
    pushToast({ title: '✅ 已排隊' });
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : String(e);
    pushToast({ title: '排隊失敗', description: msg, variant: 'destructive' });
  }
}, [pipelineId, pushToast, dispatch]);
```

- [ ] **Step 4: Run full vitest + tsc**

```
npx vitest run
npx tsc --noEmit
```

Expected: All tests still pass; tsc clean.

- [ ] **Step 5: Playwright smoke verification**

Save this script at `/tmp/probe-queue-feedback.mjs`:

```js
import { chromium } from '/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/node_modules/playwright/index.mjs';
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ baseURL: 'http://localhost:5173', viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto('/login');
await page.fill('#username', 'admin_p3');
await page.fill('#password', 'AdminPass1!');
await Promise.all([page.waitForResponse(r => r.url().includes('/api/login')), page.click('button[type="submit"]')]);
await page.goto('/');
await page.waitForTimeout(1500);
// Find a queue row with the 「執行」 button (stage idle + pipeline picked).
const runBtn = page.locator('.qi-run').first();
const count = await runBtn.count();
if (count === 0) {
  console.log('No idle file with a pipeline selected — pick a pipeline first or upload one. Skipping.');
} else {
  // Capture pre-click pill state of the row that the button is in.
  const row = runBtn.locator('xpath=ancestor::*[contains(@class,"queue-item")][1]');
  await runBtn.click();
  // Within 500ms, the ASR pill should carry .queued class.
  await page.waitForFunction((el) => {
    const pill = el.querySelector('.stage-pill');
    return pill && pill.classList.contains('queued');
  }, await row.elementHandle(), { timeout: 500 });
  const text = await row.locator('.stage-pill').first().innerText();
  console.log(`PASS — ASR pill flipped to .queued within 500ms; text="${text}"`);
}
await browser.close();
```

Run:

```
cd frontend
node /tmp/probe-queue-feedback.mjs
```

Expected: `PASS — ASR pill flipped to .queued within 500ms; text="ASR 已排隊"`.

If no idle file is available (all already running), upload a new file via the dropzone first, or test manually in the browser.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): optimistic STAGE_START on 「執行」 click — 0s visual feedback"
```

---

## Task 8: Final regression sweep + acceptance checklist

**Files:** none modified — verification only

- [ ] **Step 1: Full vitest run**

```
cd frontend
npx vitest run
```

Expected: 283 tests pass (269 baseline + 14 new across Tasks 1/2/3/5).

- [ ] **Step 2: TypeScript strict check**

```
npx tsc --noEmit
```

Expected: zero new errors. Pre-existing errors in `tests-e2e/v6-pipeline-smoke.spec.ts` are acceptable.

- [ ] **Step 3: Playwright Dashboard smoke**

Run the existing snap script:

```
node /tmp/snap-dashboard.mjs
```

Open `/tmp/dashboard-only.png`. Expected:
- Bold Dashboard renders
- Video preview shows subtitle overlay
- Queue rows render with phase pills
- No console errors related to Dashboard

- [ ] **Step 4: Acceptance criteria checklist (manual)**

Verify each item from the spec's §10:

- [ ] Vitest passes: 283 pass
- [ ] `tsc --noEmit` strict: zero new errors
- [ ] Manual smoke: 0-second visual gap between click and `已排隊` chip (verified Task 7 Step 5)
- [ ] Bold Dashboard zero-regression on: subtitle overlay, video preview, glossary panel, render modal, queue row click → file select, delete button, file detail inspector

- [ ] **Step 5 (optional): Push branch**

If all acceptance items check, push:

```bash
git push -u origin feat/phase-1-frontend-design
```

(Do NOT force-push; just `-u`.)

---

## Self-Review Notes (in-plan, no separate doc)

**Spec coverage:**
- §4 state machine → Tasks 2, 5
- §5.1 DesignFile shape → Task 5
- §5.2 toDesignFile derive → Task 5
- §5.3 QueueRow rendering → Task 6
- §5.4 MoTitleStageBadge new cases → Task 3
- §5.5 STAGE_START optional phase → Task 2
- §6 CSS → Task 4
- §7 data flow → covered implicitly by Tasks 5 + 7
- §8 error handling → handled by existing `pipeline_stage_failed` path (no plan change needed) + Task 2 reducer guards + Task 7 try/catch
- §9 testing matrix → Tasks 1, 2, 3, 5 each include their test file
- §10 acceptance criteria → Task 8

**Type consistency:** `StagePhase` defined once in `Dashboard-pill-helpers.ts` (Task 1) and imported everywhere else (Task 5). `asrPhase` field name consistent across `DesignFile` (Task 5) and `StageBadgeFile` (Task 3). `phase` field name on `StageStartEvent` consistent in Task 2 plan code and Task 7 dispatch site.

**Placeholder scan:** no TBD / TODO / "add appropriate validation" / "similar to Task N". All code blocks contain the actual code.

**Field-name gotcha verified:** `StageStartEvent.stage_index` (with `_index`) used in Tasks 2, 7 — matches existing reducer. Do not use `stage_idx` (which is `StageProgressEvent`'s field).
