# Stage-Event Field-Name Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the frontend reducer + SocketProvider with the backend's actual stage-event payload shape (`stage_index`), and narrow `BULK_FILES` recovery so `status='queued'` files keep the「已排隊」chip after reload instead of being preempted by a false `stageStatus='running'` seed.

**Architecture:** Single-source rename — backend emits `stage_index` consistently; only the frontend's `StageProgressEvent` / `StageCompleteEvent` / `PipelineFailedEvent` interfaces (and their reducer + listener consumers) used the wrong `stage_idx` name. After this fix, every payload key flows end-to-end through correctly-named state, so real pipeline events resume promoting the optimistic `'queued'` phase through `'starting'` → `'running NN%'` → `'done'`.

**Tech Stack:** TypeScript 5 strict + Vitest 2 + React 18 (Bold Dashboard reducer pattern under `SocketProvider`).

**Spec:** [`docs/superpowers/specs/2026-05-27-stage-event-field-name-fix-design.md`](../specs/2026-05-27-stage-event-field-name-fix-design.md)

---

## File Structure

**Modified files (5):**
- `frontend/src/lib/socket-events.ts` — 3 interface renames + 3 reducer destructure renames + BULK_FILES narrow
- `frontend/src/lib/socket-events.test.ts` — +5 new vitest cases
- `frontend/src/providers/SocketProvider.tsx` — 3 listener type annotations
- `frontend/src/providers/SocketProvider.test.tsx` — ~6 fixture renames
- `frontend/src/pages/Dashboard.tsx` — 1 comment update (cosmetic)
- `frontend/src/pages/Dashboard-to-design-file.test.ts` — 1 test description update (cosmetic)

No new files. No backend changes.

---

## Task 1: Rename stage_idx → stage_index across all stage events

This is the primary bug fix. Three interfaces, three reducer cases, three listener annotations, six test fixtures all change in one coordinated commit (partial rename would break tsc mid-edit).

**Files:**
- Modify: `frontend/src/lib/socket-events.ts` — interfaces (lines 20-29, 35-39) + reducer cases (lines 193-203, 207-208, 223-224)
- Modify: `frontend/src/providers/SocketProvider.tsx` — listener annotations (lines 73, 76, 82)
- Modify: `frontend/src/providers/SocketProvider.test.tsx` — fixtures (lines 65, 101, 110, 135, 147, 232)
- Test:   `frontend/src/lib/socket-events.test.ts` — append 3 new vitest cases

- [ ] **Step 1: Write the failing test (in `socket-events.test.ts`)**

Open `frontend/src/lib/socket-events.test.ts`. At the **end of the file** (after the existing `STAGE_START` describe block), append:

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
```

- [ ] **Step 2: Run tests to verify they FAIL**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx vitest run src/lib/socket-events.test.ts 2>&1 | tail -15
```

Expected: TypeScript compile error — `Object literal may only specify known properties, and 'stage_index' does not exist in type 'StageProgressEvent'`. Or if vitest's transformer is permissive: tests run but **fail** because reducer destructures `stage_idx` from `ev`, gets undefined, writes to `[undefined]` key, leaving `stageProgress.fid1?.[0]` undefined.

This proves the bug — tests assert real backend payload shape but reducer disagrees.

- [ ] **Step 3: Rename 3 interfaces in `socket-events.ts`**

Find `StageProgressEvent` (currently lines ~20-23):

```ts
export interface StageProgressEvent {
  file_id: string;
  stage_idx: number;
  percent: number;
}
```

Replace with:

```ts
export interface StageProgressEvent {
  file_id: string;
  stage_index: number;
  percent: number;
}
```

Find `StageCompleteEvent` (currently lines ~26-29):

```ts
export interface StageCompleteEvent {
  file_id: string;
  stage_idx: number;
}
```

Replace with:

```ts
export interface StageCompleteEvent {
  file_id: string;
  stage_index: number;
}
```

Find `PipelineFailedEvent` (currently lines ~35-39). The shape is:

```ts
export interface PipelineFailedEvent {
  file_id: string;
  stage_idx?: number;
  error: string;
}
```

Replace with:

```ts
export interface PipelineFailedEvent {
  file_id: string;
  stage_index?: number;
  error: string;
}
```

- [ ] **Step 4: Rename destructures in 3 reducer cases**

In `socket-events.ts`, find the `STAGE_PROGRESS` case (currently around lines 192-204):

```ts
case 'STAGE_PROGRESS': {
  const { file_id, stage_idx, percent } = action.ev;
  const fileProg = { ...(state.stageProgress[file_id] ?? {}), [stage_idx]: percent };
  const fileStatus = { ...(state.stageStatus[file_id] ?? {}), [stage_idx]: 'running' as const };
  const prevPhase = state.stagePhase[file_id] ?? {};
  return {
    ...state,
    stageProgress: { ...state.stageProgress, [file_id]: fileProg },
    stageStatus: { ...state.stageStatus, [file_id]: fileStatus },
    stagePhase: percent > 0
      ? { ...state.stagePhase, [file_id]: { ...prevPhase, [stage_idx]: 'running' } }
      : state.stagePhase,
  };
}
```

Replace with:

```ts
case 'STAGE_PROGRESS': {
  const { file_id, stage_index, percent } = action.ev;
  const fileProg = { ...(state.stageProgress[file_id] ?? {}), [stage_index]: percent };
  const fileStatus = { ...(state.stageStatus[file_id] ?? {}), [stage_index]: 'running' as const };
  const prevPhase = state.stagePhase[file_id] ?? {};
  return {
    ...state,
    stageProgress: { ...state.stageProgress, [file_id]: fileProg },
    stageStatus: { ...state.stageStatus, [file_id]: fileStatus },
    stagePhase: percent > 0
      ? { ...state.stagePhase, [file_id]: { ...prevPhase, [stage_index]: 'running' } }
      : state.stagePhase,
  };
}
```

Find the `STAGE_COMPLETE` case (currently around lines 206-212):

```ts
case 'STAGE_COMPLETE': {
  const fileProg = { ...(state.stageProgress[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 100 };
  const fileStatus = { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'done' as const };
  return {
    ...state,
    stageProgress: { ...state.stageProgress, [action.ev.file_id]: fileProg },
    stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
  };
}
```

Replace with:

```ts
case 'STAGE_COMPLETE': {
  const fileProg = { ...(state.stageProgress[action.ev.file_id] ?? {}), [action.ev.stage_index]: 100 };
  const fileStatus = { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_index]: 'done' as const };
  return {
    ...state,
    stageProgress: { ...state.stageProgress, [action.ev.file_id]: fileProg },
    stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
  };
}
```

Find the `PIPELINE_FAILED` case (currently around lines 219-229):

```ts
case 'PIPELINE_FAILED': {
  return {
    ...state,
    stageStatus: action.ev.stage_idx != null
      ? { ...state.stageStatus, [action.ev.file_id]: { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'failed' as const } }
      : state.stageStatus,
  };
}
```

(Lines may be slightly different — read the file to confirm. The pattern is `action.ev.stage_idx != null` guard and a `[action.ev.stage_idx]: 'failed'` write.)

Replace with:

```ts
case 'PIPELINE_FAILED': {
  return {
    ...state,
    stageStatus: action.ev.stage_index != null
      ? { ...state.stageStatus, [action.ev.file_id]: { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_index]: 'failed' as const } }
      : state.stageStatus,
  };
}
```

- [ ] **Step 5: Update SocketProvider listener type annotations**

Open `frontend/src/providers/SocketProvider.tsx`. Find the 3 listener registrations (around lines 73, 76, 82):

```ts
socket.on('pipeline_stage_progress', (ev: { file_id: string; stage_idx: number; percent: number }) =>
  dispatch({ type: 'STAGE_PROGRESS', ev })
);
socket.on('pipeline_stage_complete', (ev: { file_id: string; stage_idx: number }) =>
  dispatch({ type: 'STAGE_COMPLETE', ev })
);
socket.on('pipeline_failed', (ev: { file_id: string; stage_idx?: number; error: string }) =>
  dispatch({ type: 'PIPELINE_FAILED', ev })
);
```

Replace each `stage_idx` with `stage_index`:

```ts
socket.on('pipeline_stage_progress', (ev: { file_id: string; stage_index: number; percent: number }) =>
  dispatch({ type: 'STAGE_PROGRESS', ev })
);
socket.on('pipeline_stage_complete', (ev: { file_id: string; stage_index: number }) =>
  dispatch({ type: 'STAGE_COMPLETE', ev })
);
socket.on('pipeline_failed', (ev: { file_id: string; stage_index?: number; error: string }) =>
  dispatch({ type: 'PIPELINE_FAILED', ev })
);
```

- [ ] **Step 6: Update SocketProvider test fixtures**

Open `frontend/src/providers/SocketProvider.test.tsx`. Search for `stage_idx` — there are ~6 occurrences at lines 65, 101, 110, 135, 147, 232 (line numbers may have drifted; trust the grep). Each occurrence is inside an `ev: { ... }` object literal:

```bash
grep -n "stage_idx" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/src/providers/SocketProvider.test.tsx"
```

For each line returned, replace `stage_idx:` with `stage_index:` (preserve everything else).

You can do this with sed for atomicity:

```
sed -i '' 's/stage_idx:/stage_index:/g' "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/src/providers/SocketProvider.test.tsx"
```

Then re-grep to confirm zero `stage_idx:` remain in that file.

- [ ] **Step 7: Run tests to verify all pass**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx vitest run src/lib/socket-events.test.ts src/providers/SocketProvider.test.tsx 2>&1 | tail -8
npx vitest run
npx tsc --noEmit 2>&1 | grep -v "v6-pipeline-smoke" | head -5
```

Expected:
- socket-events.test.ts: 4 + 3 = 7 cases pass (4 original + 3 new from Step 1)
- SocketProvider.test.tsx: all existing cases still pass (fixtures match reducer)
- Full vitest: 295 + 3 new = 298 pass
- tsc: pre-existing v6-pipeline-smoke errors only; no new errors

- [ ] **Step 8: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/lib/socket-events.ts \
        frontend/src/lib/socket-events.test.ts \
        frontend/src/providers/SocketProvider.tsx \
        frontend/src/providers/SocketProvider.test.tsx
git commit -m "fix(socket): rename stage_idx → stage_index to match backend emit"
```

---

## Task 2: Narrow BULK_FILES IN_PROGRESS_STATUSES to {'running'}

After Task 1, the live event flow works. This task fixes the reload edge case where `status='queued'` files were incorrectly preempted with `stageStatus[0]='running'` instead of getting `stagePhase[0]='queued'`.

**Files:**
- Modify: `frontend/src/lib/socket-events.ts` — line 119 `IN_PROGRESS_STATUSES` set literal
- Test:   `frontend/src/lib/socket-events.test.ts` — append 2 new vitest cases

- [ ] **Step 1: Write the failing tests**

Open `frontend/src/lib/socket-events.test.ts`. At the end of the file, **append** (after the STAGE_COMPLETE describe block):

```ts
describe('socketReducer / BULK_FILES', () => {
  it('status="queued" → seeds stagePhase[0]="queued", NOT stageStatus[0]="running"', () => {
    const next = socketReducer(initialSocketState, {
      type: 'BULK_FILES',
      files: [
        {
          id: 'fid1',
          original_name: 'a.mp4',
          status: 'queued',
          pipeline_id: 'p1',
          uploaded_at: 0,
        } as FileRecord,
      ],
    });
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
    expect(next.stageStatus.fid1).toBeUndefined();
  });

  it('status="running" → seeds stageStatus[0]="running" (unchanged)', () => {
    const next = socketReducer(initialSocketState, {
      type: 'BULK_FILES',
      files: [
        {
          id: 'fid1',
          original_name: 'a.mp4',
          status: 'running',
          pipeline_id: 'p1',
          uploaded_at: 0,
        } as FileRecord,
      ],
    });
    expect(next.stageStatus.fid1?.[0]).toBe('running');
  });
});
```

The `FileRecord` type needs to be imported. Check the existing imports at the top of `socket-events.test.ts`. If `FileRecord` is not already imported, **prepend this import** alongside the existing one:

```ts
import { socketReducer, initialSocketState, type FileRecord } from './socket-events';
```

(If the existing import has a different shape — e.g. `import { socketReducer, initialSocketState } from './socket-events';` — extend it with `, type FileRecord`.)

- [ ] **Step 2: Run tests to verify the first one FAILS**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx vitest run src/lib/socket-events.test.ts 2>&1 | tail -15
```

Expected: the **first** new test fails (`expect(next.stageStatus.fid1).toBeUndefined()` will be **defined** because current code seeds `stageStatus[0]='running'` for queued files). The **second** new test passes (running case unchanged). This proves the over-seeding bug.

- [ ] **Step 3: Narrow `IN_PROGRESS_STATUSES`**

Open `frontend/src/lib/socket-events.ts`. Find line ~119:

```ts
const IN_PROGRESS_STATUSES = new Set(['running', 'queued']);
```

Replace with:

```ts
// 'queued' deliberately excluded — files in the worker queue (not yet
// picked up) should keep the cyan 「已排隊」 pulse via the stagePhase
// recovery branch below, not be falsely marked as stageStatus='running'.
const IN_PROGRESS_STATUSES = new Set(['running']);
```

- [ ] **Step 4: Run tests to verify all pass**

```
npx vitest run src/lib/socket-events.test.ts 2>&1 | tail -10
npx vitest run
npx tsc --noEmit 2>&1 | grep -v "v6-pipeline-smoke" | head -5
```

Expected:
- socket-events.test.ts: 7 + 2 = 9 cases pass
- Full vitest: 298 + 2 = 300 pass
- tsc clean

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/lib/socket-events.ts frontend/src/lib/socket-events.test.ts
git commit -m "fix(socket): BULK_FILES — queued status keeps stagePhase, not stageStatus"
```

---

## Task 3: Cosmetic cleanup + manual smoke verification

After Tasks 1 + 2, the bugs are fixed. This task aligns leftover stale comments and verifies the lifecycle end-to-end.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx:201` — comment text
- Modify: `frontend/src/pages/Dashboard-to-design-file.test.ts:45` — test description

- [ ] **Step 1: Update Dashboard comment**

In `frontend/src/pages/Dashboard.tsx`, find line ~201. The current comment mentions `stage_idx`:

```tsx
  // Note: if any MT stage_idx > 0 is 'running', we still surface 'translating'
```

Replace with:

```tsx
  // Note: if any MT stage_index > 0 is 'running', we still surface 'translating'
```

- [ ] **Step 2: Update Dashboard test description**

In `frontend/src/pages/Dashboard-to-design-file.test.ts`, find line ~45:

```ts
  it('ASR done + MT stage_idx=1 running 50%', () => {
```

Replace with:

```ts
  it('ASR done + MT stage_index=1 running 50%', () => {
```

(This is the test's description string only — the test body uses `{ 0: ..., 1: ... }` numeric keys which were never affected.)

- [ ] **Step 3: Run full vitest + tsc**

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx vitest run 2>&1 | tail -5
npx tsc --noEmit 2>&1 | grep -v "v6-pipeline-smoke" | head -5
```

Expected: 300 pass; tsc clean.

- [ ] **Step 4: Confirm dev servers are running**

```
curl -s -o /dev/null -w "backend:%{http_code}\n" http://localhost:5001/api/health
curl -s -o /dev/null -w "frontend:%{http_code}\n" http://localhost:5173/
```

Expected: `backend:200`, `frontend:200`. If either is down, start them:
- Backend: `cd backend && source venv/bin/activate && python app.py` (background)
- Vite: `cd frontend && npx vite` (background)

- [ ] **Step 5: Manual smoke — full lifecycle**

Run this Playwright probe at `/tmp/probe-lifecycle.mjs`:

```js
import { chromium } from '/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/node_modules/playwright/index.mjs';
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ baseURL: 'http://localhost:5173', viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const wsFrames = [];
page.on('websocket', ws => {
  if (!ws.url().includes('/socket.io/')) return;
  ws.on('framereceived', f => {
    const t = typeof f.payload === 'string' ? f.payload : '<bin>';
    if (t && (t.includes('pipeline_stage_progress') || t.includes('pipeline_stage_complete'))) {
      wsFrames.push(t.slice(0, 200));
    }
  });
});

await page.goto('/login');
await page.fill('#username', 'admin_p3'); await page.fill('#password', 'AdminPass1!');
await Promise.all([page.waitForResponse(r => r.url().includes('/api/login')), page.click('button[type="submit"]')]);
await page.goto('/');
await page.waitForTimeout(2000);

// Upload a fresh file to land in 'uploaded' status with a run button
const fileInput = page.locator('input[type="file"]').first();
await fileInput.setInputFiles('/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/uploads/8caaa3e5a78a.mp4');
await page.waitForTimeout(4000);

const runBtn = page.locator('.qi-run').first();
const runCount = await runBtn.count();
if (runCount === 0) {
  console.log('SKIP — no run button (file may have auto-started; verify manually instead)');
  await browser.close();
  process.exit(0);
}

const row = runBtn.locator('xpath=ancestor::*[contains(@class,"queue-item")][1]');
console.log('Clicking 「執行」...');
await runBtn.click();

// Sample pill state every 5s for 60s
for (let i = 1; i <= 12; i++) {
  await page.waitForTimeout(5000);
  const pill = await row.locator('.stage-pill').first().evaluate(el => ({
    cls: el.className, text: el.textContent?.trim(),
  }));
  console.log(`  t+${i*5}s pill=${JSON.stringify(pill)} ws_events=${wsFrames.length}`);
  if (pill.cls.includes('ok') || pill.cls.includes('err')) break;
}
console.log(`Total stage_progress / stage_complete frames captured: ${wsFrames.length}`);
await browser.close();
```

Run:

```
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
node /tmp/probe-lifecycle.mjs
```

Expected output shape (timings approximate, pipeline may differ):

```
Clicking 「執行」...
  t+5s pill={"cls":"stage-pill queued","text":"ASR已排隊"} ws_events=0
  t+10s pill={"cls":"stage-pill starting","text":"ASR準備中"} ws_events=0
  t+15s pill={"cls":"stage-pill warn","text":"ASR5%"} ws_events=1
  t+20s pill={"cls":"stage-pill warn","text":"ASR25%"} ws_events=4
  ... (progress ticks) ...
  t+55s pill={"cls":"stage-pill ok","text":"ASR完成"} ws_events=21
Total stage_progress / stage_complete frames captured: 21+
```

If the pill **stays at `queued`** (cyan) for the entire 60s and `ws_events` reaches 0 or stays low: Task 1 didn't fix the reducer (re-check field name renames). **Report BLOCKED.**

If the pill **flickers between numeric percent values** and eventually shows `ok` green: success.

If `SKIP — no run button`: the upload may have auto-started the pipeline. That's fine for this task — manually test in the browser at http://localhost:5173/ instead: refresh the page, click 「執行」 on any uploaded file, watch the ASR chip transition through queued → starting → percent → done.

- [ ] **Step 6: Manual smoke — reload preserves queued state**

In the running browser session (or open one fresh):
1. Click 「執行」 on a fresh upload
2. **Within 5 seconds** (before backend worker picks up), press **Cmd+Shift+R** (hard refresh) on the Dashboard tab
3. Observe: the same queue row should reappear with the `已排隊` cyan pulse chip — NOT `0%` amber

If the chip shows `0%` instead of `已排隊` immediately after reload: Task 2's narrow didn't apply (check the `IN_PROGRESS_STATUSES` literal in `socket-events.ts`).

If the timing is hard to hit (worker picks up too fast), it's acceptable to verify by intentionally pausing the worker — but that's beyond this task's scope. Best-effort smoke is enough.

- [ ] **Step 7: Commit cosmetic changes**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/pages/Dashboard.tsx \
        frontend/src/pages/Dashboard-to-design-file.test.ts
git commit -m "chore(dashboard): rename remaining stage_idx → stage_index in comments"
```

If there are no functional changes left to commit (cosmetic-only diff after Steps 5–6 verification), this commit is small but documents the rename completeness.

---

## Self-Review Notes

**Spec coverage:**
- §5.1 socket-events.ts changes → Task 1 (Steps 3-4)
- §5.2 BULK_FILES narrow → Task 2 (Step 3)
- §5.3 SocketProvider type annotations → Task 1 (Step 5)
- §5.4 SocketProvider.test.tsx fixtures → Task 1 (Step 6)
- §6 data flow (live updates) → verified by Task 3 Step 5
- §7 reload behaviour → verified by Task 3 Step 6
- §8.1 new vitest cases → Task 1 Step 1 (3 cases) + Task 2 Step 1 (2 cases) = 5 total ✓
- §8.2 existing test updates → Task 1 Step 6 + Task 3 Steps 1-2 ✓
- §9 acceptance criteria → Task 3 Steps 3, 5, 6 ✓
- §11 file inventory matches Task 1-3 file lists ✓

**Type consistency:** All new tests use `stage_index` in their `ev` literals; all reducer destructures and type annotations were renamed in lockstep within Task 1's atomic commit (so tsc never breaks mid-task).

**Placeholder scan:** No TBD / TODO / "add validation" / "similar to Task N". All code blocks contain real code. Exact file paths and line numbers throughout.

**No-Placeholders nit:** Step 6 uses `sed -i '' 's/stage_idx:/stage_index:/g'` which is the macOS BSD-sed form (works on the project's darwin host). Step 6's instruction also says to re-grep after, which is the verification step.
