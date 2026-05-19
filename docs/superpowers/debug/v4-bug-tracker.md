# v4.0 Debug — Master Bug Tracker

**Consolidated:** 2026-05-18
**Branch:** debug/v4-e2e-bug-hunt
**Sources:** Track A (Playwright) + Track B (Manual matrix scoped) + Track C (Static analysis) + Track D (Known-issue harvest)

---

## Summary table

| BUG ID | Source | Severity | A-phase | Plan impact | Status | Title |
|---|---|---|---|---|---|---|
| BUG-001 | A | P2 | cross | 純 bug fix | Fixed | Test fixture media file missing → upload E2E specs auto-skip |
| BUG-002 | A | P2 | cross | 純 bug fix | Fixed | global-setup.ts seed idempotency (409 loses entity IDs) |
| BUG-003 | A | P3 | cross | 純 bug fix | Fixed | test:e2e:seeded script Unix env syntax (Windows incompatible) |
| BUG-004 | A | P2 | A4 | 純 bug fix | Fixed | PromptOverridesDrawer Save silently no-ops when `file.pipeline_id` null |
| BUG-005 | A | P3 | A4 | Defer | Deferred (backlog) | StageRerunMenu renders dropdown when `stage_outputs` empty |
| BUG-006 | B | P2 | A3/A6 | 純 bug fix | Fixed | SocketProvider does not expose connection state to UI |
| BUG-007 | B | P2 | A3/A6 | 純 bug fix | Fixed | Stage progress lost on page refresh (no HTTP recovery endpoint) |
| BUG-008 | B | P3 | A3/A6 | Defer | Deferred (backlog) | No WebSocket event sequence/dedup on reconnect (theoretical) |
| BUG-009 | B | P3 | A6 C1 | 純 bug fix | Fixed | Proofread page chunk named `index-*.js` not `Proofread-*.js` |
| BUG-010 | B | P2 | A6 C4 | 純 bug fix | Fixed | `request_id` always null in log lines (werkzeug context gap) |
| BUG-011 | B | P2 | A6 C4 | 純 bug fix | Fixed | 20+ `print()` calls in app.py bypass logger → mix into JSON log stream |
| BUG-012 | D | P3 | A6 | Confirmed out-of-scope | Open | StreamingSession class still inline in app.py |
| BUG-013 | D | P3 | cross | Confirmed out-of-scope | Open | Mac/Win packaging not done |
| BUG-014 | D | P3 | A3/A4 | Confirmed out-of-scope | Open | Mobile responsive layout not done |
| BUG-015 | D | P3 | A3 | Confirmed out-of-scope | Open | i18n framework not introduced |
| BUG-016 | D | P3 | A3/A4 | Confirmed out-of-scope | Open | Storybook not introduced |
| BUG-017 | D | P2 | cross | Confirmed out-of-scope | Open | CI/CD GitHub Actions not configured |
| BUG-018 | D | P3 | A5 | 純 bug fix | Fixed | Legacy Socket.IO emitter event names cleanup (docs + types) |
| BUG-019 | D | P3 | cross | Defer | Deferred (backlog) | faster-whisper BatchedInferencePipeline not tried |
| BUG-020 | D | P2 | cross | 純 bug fix | Fixed | `/api/translation/engines` Ollama probe missing timeout + memoization |
| BUG-021 | D | P3 | cross | Confirmed out-of-scope | Open | Domain context anchor (per-file subject prefix) |
| BUG-022 | D | P3 | cross | Confirmed out-of-scope | Open | Forbidden phrases list (negative vocabulary) |
| BUG-023 | D | P3 | cross | Confirmed out-of-scope | Open | User self-service prompt template publishing |
| BUG-024 | D | P3 | cross | Confirmed out-of-scope | Open | Glossary stacking (multi-glossary per pipeline) |
| BUG-025 | D | P3 | cross | Confirmed out-of-scope | Open | Per-file retry strategy config |
| BUG-026 | D | P3 | cross | Confirmed out-of-scope | Open | A/B prompt comparison feature |
| BUG-027 | D | P3 | cross | Confirmed out-of-scope | Open | s2hk simplified-Chinese leak MT-side post-process |
| BUG-028 | D | P3 | cross | Confirmed out-of-scope | Closed | ASR-side fragment merge Stage 1 (intentionally skipped) |
| BUG-029 | T27-T29 prep | P2 | A5 | Spec 假設錯 | Fixed | `DATA_DIR` / `UPLOAD_DIR` / `RENDERS_DIR` hardcoded in managers.py:55 — no env override → isolated boot impossible. Fixed: `R5_DATA_DIR` env var added; smoke verified upload_dir = isolated path. |
| BUG-030 | T27-T29 inline | P1 | A1/A5 | 純 bug fix | Fixed | PipelineRunner `stage_outputs` not bridged to legacy `segments`/`translations` fields — blocks all proofread + render after v4 pipeline run |
| BUG-031 | T29 inline | P2 | A4/routes | 純 bug fix | Fixed | Render status naming mismatch: backend uses `"done"`, frontend `useRenderJob` polls for `"completed"` → download never triggered |
| BUG-032 | human-test 2026-05-19 | P2 | A3 | 純 bug fix | Fixed | Vite proxy missing `/login` + `/logout` entries → SPA login flow gets 404 from dev server (works fine in prod where Flask serves both). Also stale compiled `vite.config.{js,d.ts}` was loaded instead of `.ts` source. |

---

## Severity breakdown

| Severity | Count | % |
|---|---|---|
| **P0** | **0** | 0% |
| **P1** | **1** | 3% |
| **P2** | **10** | 32% |
| **P3** | **20** | 65% |
| **Total** | **31** | 100% |

> +1 P2 (BUG-029) discovered Phase 3b during T27 prep — DATA_DIR isolation gap. Confirms Phase 2 hypothesis §8 row "A5 R5_CONFIG_DIR fixture robustness".
> +1 P1 + 1 P2 (BUG-030, BUG-031) discovered T27-T29 inline validation — stage_outputs bridge gap + render status naming mismatch.

## Plan impact breakdown

| Bucket | Count | BUG IDs |
|---|---|---|
| 純 bug fix | 13 | BUG-001, 002, 003, 004, 006, 007, 009, 010, 011, 018, 020, 030, 031 |
| Spec 假設錯 | 1 | BUG-029 |
| 需開新 sub-phase | 0 | — |
| Defer 入 backlog | 3 | BUG-005, 008, 019 |
| Confirmed out-of-scope | 14 | BUG-012, 013, 014, 015, 016, 017, 021–028 (incl. 028 Closed) |
| **Total** | **31** | |

---

## Abort gate evaluation

- **P0 count: 0** vs threshold 5 (spec §6)
- **P1 count: 0** (BUG-030 Fixed — targeted bridge function, no sub-phase needed)
- **Status: NOT TRIGGERED** — all P0/P1 bugs resolved
- BUG-030 turned out to be a pure targeted bridge fix, not an architectural sub-phase

---

## Discovery source

- Track A (Playwright authoring): 5 entries — full detail in [v4-bug-tracker-trackA-playwright.md](v4-bug-tracker-trackA-playwright.md)
- Track B (Manual matrix scoped §5/6/7): 6 entries — full detail in [v4-bug-tracker-trackB-manual.md](v4-bug-tracker-trackB-manual.md)
- Track C (Static analysis): 0 entries (1 AUDIT pass) — see [v4-bug-tracker-trackC-static.md](v4-bug-tracker-trackC-static.md)
- Track D (Known-issue harvest): 17 entries — full detail in [v4-bug-tracker-trackD-known.md](v4-bug-tracker-trackD-known.md)

---

## Active findings — full content

Full repro / expected / actual / suggested fix for each Open entry below. Order: P2 first (8) then P3 active (6). Confirmed out-of-scope items get a 1-line reference to sub-tracker only.

### BUG-001 [P2 / Track A / cross / 純 bug fix]: Test fixture media file missing

- **Repro**: `npm run test:e2e:seeded` — happy-path-pipeline.spec.ts and cancel-running-job.spec.ts auto-skip with "No fixture file at tests-e2e/fixtures/sample.{mp4,mp3,wav}"
- **Expected**: Small (≤5MB) sample media file committed at `frontend/tests-e2e/fixtures/`
- **Actual**: Directory does not exist, upload-dependent specs degrade-skip
- **Suggested fix**: `ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 5 -q:a 9 -acodec libmp3lame frontend/tests-e2e/fixtures/sample.mp3`. Update gitignore to NOT exclude this fixture path.

### BUG-002 [P2 / Track A / cross / 純 bug fix]: global-setup.ts seed idempotency

- **Repro**: Run `npm run test:e2e:seeded` twice. Second run `POST /api/asr_profiles` returns 409 (already exists), `seedPost()` returns `{}` without id, pipeline creation skipped.
- **Expected**: Idempotent seed recovers entity IDs via GET on 409
- **Actual**: Pipeline creation skipped on rerun → pipeline-broken-refs.spec.ts depends on linked pipeline, may falsely pass
- **Suggested fix**: Implement `getOrCreate(listPath, name, createBody)` helper that GETs the list on 409 and matches by name.

### BUG-003 [P3 / Track A / cross / 純 bug fix]: Windows env syntax

- **Repro**: On Windows `npm run test:e2e:seeded` fails (`E2E_REQUIRE_SEED=1` not recognized in cmd.exe)
- **Expected**: Cross-platform script
- **Suggested fix**: `npm install -D cross-env` + update package.json script to `cross-env E2E_REQUIRE_SEED=1 playwright test ...`

### BUG-004 [P2 / Track A / A4 / 純 bug fix]: PromptOverridesDrawer silent no-op

- **Repro**: Open /proofread on a file without `pipeline_id`. Click "⚙ Overrides", fill textarea, click Save. Save returns silently (`if (!file || !file.pipeline_id) return;` at PromptOverridesDrawer.tsx line 53). User gets no feedback.
- **Expected**: Save button disabled (with tooltip) OR toast error explaining no pipeline attached
- **Actual**: Silent no-op
- **Suggested fix**: Disable Save when `!file?.pipeline_id` with title attribute, or replace early-return with toast.error()

### BUG-005 [P3 / Track A / A4 / Defer]: StageRerunMenu empty dropdown

- **Repro**: Open /proofread on file with empty `stage_outputs`. `<summary>Re-run</summary>` renders, click opens dropdown showing "No stages yet."
- **Suggested fix**: Conditionally render `<details>` only when `stages.length > 0`

### BUG-006 [P2 / Track B / A3/A6 / 純 bug fix]: SocketProvider no connection state ✅ Fixed

- **Repro**: Read `SocketProvider.tsx` — no `socket.on('disconnect', ...)`, no `connected: boolean` in SocketContextValue. UI cannot show "Disconnected — reconnecting..." banner.
- **Expected**: SocketState gains `connected: boolean`, register connect/disconnect handlers
- **Fix**: Added `SOCKET_CONNECTED` / `SOCKET_DISCONNECTED` action types + `connected: boolean` to `SocketState` (default `false`). Registered `socket.on('connect')` + `socket.on('disconnect')` in `useEffect`; cleanup includes `socket.off('connect')` + `socket.off('disconnect')`. 4 new tests in `SocketProvider.test.tsx`.

### BUG-007 [P2 / Track B / A3/A6 / 純 bug fix]: Stage progress lost on refresh ✅ Fixed (Option A — degraded)

- **Repro**: Start pipeline (stage 1 @ 60%). Hard refresh. `stageProgress` reducer state resets to `{}`. File still shows "running" status, but no progress bar.
- **Expected**: Page mount restores in-progress stage % from server
- **Fix (Option A)**: `BULK_FILES` reducer now scans files for `status in {'running', 'queued'}`. For each in-flight file without existing `stageStatus`, marks `stageStatus[fileId][stageIdx] = 'running'` where `stageIdx = stage_outputs.length` (current stage inferred from completed outputs). Existing live-event state is preserved (recovered entries only written when `!state.stageStatus[f.id]`). UI shows indeterminate running indicator until next `pipeline_stage_progress` event delivers exact %. 3 new tests.
- **Note**: Exact % not recoverable without backend `GET /api/files/<id>` exposing `current_stage_progress` — deferred per Phase 3b scope.

### BUG-008 [P3 / Track B / A3/A6 / Defer]: No WebSocket event dedup

- **Repro**: Theoretical — Socket.IO reconnect could replay old `pipeline_stage_progress` event regressing progress bar
- **Severity note**: Socket.IO at-most-once delivery makes this rare; defer until observed in practice
- **Suggested fix**: Add `seq: int` to backend stage_progress events, reducer tracks `lastSeq` per file

### BUG-009 [P3 / Track B / A6 C1 / 純 bug fix]: Proofread chunk naming

- **Repro**: `ls frontend/dist/assets/` — no `Proofread-*.js`. Instead `index-CWuXN8y6.js` (39KB) IS the Proofread chunk (rollup names it after `src/pages/Proofread/index.tsx`).
- **Expected**: Recognizable chunk name for debuggability
- **Suggested fix**: Add to vite.config.ts manualChunks: `if (id.includes('/pages/Proofread/')) return 'Proofread';`. Or rename `Proofread/index.tsx` → `Proofread/Proofread.tsx`.

### BUG-010 [P2 / Track B / A6 C4 / 純 bug fix]: request_id null in log lines

- **Repro**: `LOG_JSON=1 python app.py`, hit any endpoint. All log lines including werkzeug access lines show `"request_id": null`. Response header `X-Request-ID` IS set correctly. Root cause: `RequestIdFilter.has_request_context()` returns False for werkzeug logger (fires outside Flask context).
- **Expected**: All log lines during HTTP request handling carry the inbound request_id
- **Actual**: Only response header set, log lines lose context
- **Suggested fix**: Replace werkzeug request logger via `logging.getLogger('werkzeug')` propagation control, OR wrap werkzeug's WSGI middleware to push Flask app context before logging. Alternatively use `flask.g.request_id` via Flask `before_request` hook that also pushes to a thread-local that the filter reads.

### BUG-011 [P2 / Track B / A6 C4 / 純 bug fix]: print() calls in app.py

- **Repro**: `grep -c "^[[:space:]]*print(" backend/app.py` — 20+ matches across lines 41-762. Under `LOG_JSON=1`, they emit plain text mixed into JSON stream → log aggregator chokes.
- **Expected**: All app.py output via `app.logger.info()` / `logger.debug()` etc.
- **Suggested fix**: Replace each `print()` with `logger.info()`. Most are startup banner / CUDA DLL init diagnostics — appropriate as INFO level.

### BUG-018 [P3 / Track D / A5 / 純 bug fix]: Legacy Socket.IO emitter docs cleanup

- **Repro**: CLAUDE.md "WebSocket events" table still lists `subtitle_segment`, `translation_progress`, `pipeline_timing` — emitters deleted in A5 commits
- **Suggested fix**: Remove 3 dead rows from CLAUDE.md table. Grep frontend `socket-events.ts` type union for these names, delete if unused.

### BUG-019 [P3 / Track D / cross / Defer]: faster-whisper BatchedInferencePipeline

- **Repro**: `backend/asr/whisper_engine.py` uses sequential `WhisperModel().transcribe()` API. faster-whisper 4.0+ adds `BatchedInferencePipeline` claiming 30-50% speedup.
- **Defer reason**: Requires real-audio quality validation before swap. Adopt in dedicated ASR-perf optimization phase post-v4.0.

### BUG-020 [P2 / Track D / cross / 純 bug fix]: Ollama probe timeout

- **Repro**: `time curl http://localhost:5001/api/translation/engines` — when Ollama down, request hangs (no HTTP timeout). v3.14 audit observed 994ms outlier.
- **Suggested fix**: `engines.py` blueprint adds `requests.get(..., timeout=2)` + ttl_cache memoization (60s TTL).

### BUG-030 [P1 / T27-T29 inline / A1+A5 / 需開新 sub-phase]: PipelineRunner stage_outputs not bridged to legacy fields

- **Repro:**
  1. Upload file → `POST /api/transcribe?pipeline_id=X` → 202 with `job_id`
  2. Poll until job `status: done` in DB
  3. `GET /api/files/<id>/segments` → `{"segments": [], "status": "uploaded"}` — 0 segments
  4. `GET /api/files/<id>/translations` → `{"translations": []}` — 0 translations
  5. `GET /api/files` → `"segment_count": 0, "status": "uploaded"` — looks untouched
  6. `POST /api/render` → `{"error": "File has no translations to render"}`
  7. But registry.json shows `stage_outputs: {"0": {segments: [{...}]}, "1": {segments: [{...}]}}` with correct data
- **Root cause:** `PipelineRunner._persist_stage_output()` writes only to `entry["stage_outputs"][str(idx)]`. No code path bridges this to `entry["segments"]`, `entry["translations"]`, `entry["status"]`, timing fields, or `entry["pipeline_id"]`.
- **All affected APIs:** `/segments`, `/translations`, `/translations/approve-all`, `/render`, `/api/files` list (`segment_count`, `status`), Proofread page (depends on translations)
- **Suggested fix (Option A — recommended):** After `runner.run()` in `_pipeline_run_handler`, call a `_bridge_stage_outputs(file_id, pipeline_id, stage_outputs)` function that:
  - Reads stage 0 (ASR) segments → writes to `entry["segments"]`
  - Pairs stage 0 + last MT stage segments → writes `entry["translations"]` as `[{seg_idx, start, end, en_text, zh_text, status: "pending", flags: []}]`
  - Sets `entry["status"] = "done"`, `entry["pipeline_id"] = pipeline_id`
  - Sets `entry["asr_seconds"]`, `entry["translation_seconds"]`, `entry["pipeline_seconds"]` from stage durations
- **Note:** Also add `pipeline_id` to `_register_file()` so it is present from upload time and returned in `GET /api/files`

### BUG-031 [P2 / T29 inline / A4/routes / 純 bug fix]: Render status `"done"` vs frontend expected `"completed"`

- **Repro:**
  1. Submit render via `POST /api/render`
  2. Poll `GET /api/renders/<id>` → returns `{"status": "done"}` when complete
  3. `useRenderJob.ts` line 42: `updated.status === 'completed'` — condition never true
  4. Download dialog never triggered; polling continues indefinitely
- **Root cause:**
  - `backend/routes/render.py:197`: `{**job_state, "status": "done"}`
  - `frontend/src/pages/Proofread/hooks/useRenderJob.ts:42`: checks `=== 'completed'`
  - Same mismatch at line 7 (type definition) and lines 99
- **Suggested fix:** Update backend to use `"status": "completed"` on success (aligns with frontend type), and `"status": "failed"` on error (already matches). Specifically change `render.py:197` from `"done"` to `"completed"`. Also update line 273 (`if job["status"] != "done"` → `!= "completed"`) and the `GET /api/renders/in-progress` filter if it also checks `"done"`.
- **Alternative:** Update frontend to accept `"done"` — but this requires updating type definitions in 3 places.

### Confirmed out-of-scope (audit trail, no fix expected)

- **BUG-012 — StreamingSession inline in app.py** (~150 lines, A6 C2 didn't extract)
- **BUG-013 — Mac/Win packaging not done** (PyInstaller / electron-builder)
- **BUG-014 — Mobile responsive layout** (Tailwind default breakpoints only)
- **BUG-015 — i18n framework absent** (hardcoded 廣東話 strings)
- **BUG-016 — Storybook absent**
- **BUG-017 — CI/CD GitHub Actions absent** (P2 most-production-impact among OOS, but spec §10 excludes)
- **BUG-021 — Domain context anchor per-file**
- **BUG-022 — Forbidden phrases list**
- **BUG-023 — User self-service prompt template publishing**
- **BUG-024 — Glossary stacking (multi-glossary)**
- **BUG-025 — Per-file retry strategy**
- **BUG-026 — A/B prompt comparison**
- **BUG-027 — MT-side s2hk leak post-process**
- **BUG-028 — ASR fragment merge Stage 1 (intentionally skipped)** [Closed]

Full content for these 14 entries in `v4-bug-tracker-trackD-known.md`.

---

## Notes for Phase 3a

- 0 P0 / 1 P1 → P1 abort gate NOT triggered (threshold: 3 P1s); BUG-030 is a critical architectural gap that blocks the full v4 user-facing flow
- **BUG-030 must be fixed before any user can complete the v4 pipeline → proofread → render workflow** — it is the highest-priority open item
- 9 P2 + 6 P3 active fixes (BUG-001 to BUG-011 active + BUG-018, BUG-020, BUG-031)
- Among P2s, BUG-010 (request_id) and BUG-011 (print bypass) are A6 C4 implementation-level fixes — should be done before any production deployment to ensure log aggregator compatibility
- Among P2s, BUG-004 (silent save no-op) and BUG-006 (no connection state) are A4 UX bugs that affect daily use
- BUG-031 (render status "done" vs "completed") is a 1-line backend fix — trivial once BUG-030 is fixed
- 14 Confirmed out-of-scope entries provide audit trail — no action needed in this debug branch
