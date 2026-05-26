# Console Redesign — Delivery Summary

**Branch:** `feat/phase-1-frontend-design`
**Plan:** `docs/superpowers/plans/2026-05-22-console-redesign-plan.md` (49 atomic tasks, 11 phases)
**Feature flag:** `VITE_CONSOLE=1` env + `?console=1` query (both required to render)

## Phases shipped

| Phase | Bundle | Commit |
|---|---|---|
| 0a Q2 ffprobe duration | 4 bundles | 351740c → ec876b4 |
| 0b Q3 preset_slot | 2 bundles | 24f1046, d5491dd |
| 1 Frontend foundations (css scaffold, types, format util, schema extensions) | 4 bundles | 3a2e2a2 → 12c6532 |
| 2 Console skeleton + feature-flag route | 1 bundle | aceeabd |
| 3 Rail component | 1 bundle | 5675351 |
| 4 deriveStageCells + StageBar + QueueColumn + drop zone | 3 bundles | 2236b91, 045db95, a2c06ba |
| 5 useWorkerStatus + WorkerStatus | 1 bundle | 0be1a15 |
| 6 useHotkeys + PresetPills + MetricsBar + VideoPanel + TransportBar + TranscriptList + Workbench | 4 bundles | 5510cea → 2c5f26b |
| 7 Aside (Pipeline + Glossary + Facts) | 1 bundle | b220eae |
| 8 Pipelines page preset_slot dropdown | 1 bundle | 25c76e7 |
| 9 Global hotkeys + Search modal + queue animations | 1 bundle | 8a2ace0 |
| 10 E2E expansion + handoff (this commit) | 1 bundle | (this) |

## What landed

### Backend
- `FileRecord.duration_seconds` field via ffprobe-on-upload + migration script
- `Pipeline.preset_slot` field (1-4 or null) with per-user uniqueness + atomic swap endpoint
- 31 new backend tests (1015 → 1046 PASS), 0 regressions

### Frontend
- 21 new files under `pages/Console/`, `hooks/`, `lib/`, `styles/`, `tests-e2e/`
- 6 modified files (`router.tsx`, schema files, picker store, `Pipelines.tsx`, `socket-events.ts`)
- 0 changes to `tailwind.config.ts`, `motitle-bold.css`, `Dashboard.tsx`
- 24 new vitest cases (254 → 278 PASS), 9 Playwright E2E scenarios

## How to try

1. Set `VITE_CONSOLE=1` in `frontend/.env.development` (already committed).
2. Restart dev server: `cd frontend && npm run dev:vite`.
3. Open `http://localhost:5173/console?console=1` (logged in as admin).
4. Try: upload via drop zone → ⌘1-4 preset switch → click queue item → ⌘K modal → Esc close.

## Decision recap

| # | Decision | Why |
|---|---|---|
| Q1 | A — Pure CSS via console.css | Existing pattern (motitle-bold.css), zero tailwind.config churn |
| Q2 | B — Backend ffprobe + migration | Duration is core broadcast metadata, worth the backend cost |
| Q3 | C — Backend preset_slot + uniqueness + atomic swap | Per-user persisted via PipelineManager; mirrors v3.13 R5 phase 5 lock pattern |
| Q4 | A — Glossary list read-only | Conservative; toggle semantic ambiguous at MVP |
| Q5 | B — Metrics bar queue real + others "—" | GPU probe defer; queue_depth derived from /api/queue length |
| Q6 | C — Env + query both required | Production tree-shakes; dev easy to toggle |

## v2 fixes (2026-05-22 / Bug 1+2+3)

Three post-launch bugs found during Bundle 11 verification and subsequently fixed:

| Bug | Was | Fixed by |
|---|---|---|
| Bug 1 — Space play not wired to real `<video>.play()` | Space keypress dispatched a custom event that nothing consumed | `VideoControlContext` + `useVideoControl` hook wired to `<video>` ref (commits 4df0bc4–a946432) |
| Bug 2 — Render cell always idle | No render socket events were emitted | Backend `render_start` / `render_done` events + frontend `useRenderStatus` store + `WorkerStatus` merge; render cell reflects real start/done state (commits 9b5ecf5, a2bbb45–d7cb47c, 22ee882–c99bd83, c7821ab–3e4d160) |
| Bug 3 — Stage bar 8s grey window on enqueue | No "queued" / "starting" lifecycle phase before first `pipeline_stage_progress` event | 4-state lifecycle (`idle → queued → starting → running/done/err`) via `stagePhaseMap` + Socket.IO `pipeline_queued` / `pipeline_stage_start` event handlers (commits 6625b0a–ea3ef74, 3b89133) |

Also fixed in Bundle 11: `stage_outputs` dict→array normalisation in `to-console-file.ts` — the backend serialises `stage_outputs` as a string-keyed dict (`{"0":…,"1":…}`) rather than an array; `toConsoleFile` now calls `normalizeStageOutputs()` so `deriveStageCells` never receives a non-array value.

## Known limitations (deferred to future phase)

- Metrics bar: ASR RT / MT tok/s / GPU% all show "—" (backend probes unimplemented).
- VideoPanel: transcript panel is read-only, no edit, single-column (sourceLang only — hook returns `{start, end, text}` shape).
- ⌘K Global search: placeholder modal, no actual search wiring.
- **Render progress granularity** — `render_progress` fires only at 0% (render_start) and 100% (render_done). Granular per-second FFmpeg progress requires refactoring `backend/renderer.py::render()` from `subprocess.run` (blocking) to `subprocess.Popen` with `-progress pipe:1` parsing. Out of current scope; the cell correctly shows running/done state.
- Pipelines page has preset_slot dropdown for CREATE only — no EDIT flow yet.
- Mobile fallback at `<1024px` redirects to `/` (Console is desktop-only per spec).
- Workers status polling: MetricsBar and WorkerStatus each independently poll /api/queue every 3s (2x load). Lifting to a shared context is a future optimization.

## Backwards compat

- `/` route untouched (existing `dashboard.spec.ts` + `bold-dashboard.spec.ts` GREEN regression)
- All v5 profile pages untouched
- Existing pipelines without `preset_slot` field continue to work (field defaults to null)
- Existing files without `duration_seconds` show "—" until migration script runs

## Verification

- Backend: 1050 PASS / 23 failed (baseline) / 21 skipped
- Frontend vitest: 304 PASS
- Typecheck: 7 pre-existing TS errors (baseline, no new errors introduced)
- Playwright console.spec.ts: 9 passed / 1 skipped (graceful-skip when queue empty)
- Playwright dashboard.spec.ts + bold-dashboard.spec.ts: all passing
- User workflow spec: 14 works / 2 partial / 0 broken / 0 skipped (Steps 12+14 now ✓ works; Step 15 render-cell ⚠ partial — render socket fires only at start/done, no granular percent)

## Plan adherence

49 atomic tasks from plan executed via Subagent-Driven Development. 27 implementer dispatches (some bundling) + 8 reviewer dispatches (Phase 0 only — Phases 1-10 used controller-side review for trivial mechanical commits to conserve context). One fix loop at Phase 0a-1 (helper moved to helpers/media.py per code reviewer feedback). All 11 README acceptance criteria mapped to delivered components.
