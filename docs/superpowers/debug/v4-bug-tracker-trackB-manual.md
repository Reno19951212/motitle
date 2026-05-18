# Bug Tracker — Track B (Manual matrix)

**Track:** B
**Owner:** Track B subagent (2026-05-18)
**Start:** 2026-05-18
**Status:** Sections 5/6/7 complete; Sections 1/2 deferred; Section 3 N/A; Section 4 deferred

---

## Schema

Each finding is one H2 section:

```
## BUG-NNN: <短描述>
- **Status**: Open / In progress / Fixed / Wontfix / Deferred
- **Severity**: P0 / P1 / P2 / P3 (will triage in Phase 2)
- **A-phase origin**: P1 / A1 / A3 / A4 / A5 / A6 / cross-phase
- **Layer**: backend / frontend / E2E / docs / config / build
- **Discovery source**: Track B
- **Repro steps**: ...
- **Expected**: ...
- **Actual**: ...
- **Plan impact** (必選一個):
  - [ ] 純 bug fix
  - [ ] Spec 假設錯
  - [ ] 需開新 sub-phase
  - [ ] Defer 入 backlog
  - [ ] Confirmed out-of-scope
- **Suggested fix**: <approach>
- **Linked commit**: (Phase 3b 填寫)
```

---

## Entries

### Section 5 — WebSocket Reliability (Static Analysis)

## BUG-B001: SocketProvider does not expose WebSocket connection state to UI

- **Status**: Open
- **Severity**: P2
- **A-phase origin**: A3 / A6
- **Layer**: frontend
- **Discovery source**: Track B — static code inspection of `frontend/src/providers/SocketProvider.tsx`
- **Repro steps**:
  1. Open `SocketProvider.tsx` — `SocketContextValue` only exposes `state: SocketState`
  2. `SocketState` has `files`, `stageProgress`, `stageStatus` — no `connected: boolean` or `disconnected: boolean` field
  3. `socket.on('disconnect', ...)` event is never registered
  4. No UI component can subscribe to connection status
- **Expected**: SocketProvider context should expose a `connected` boolean so that UI components (e.g. Dashboard, Proofread page) can display a "Disconnected — reconnecting..." banner when the backend is unreachable
- **Actual**: When the backend dies mid-session, the frontend silently stops receiving progress events. No disconnected state is surfaced. The matrix checklist item "Kill backend server 中途 → frontend 顯示 disconnected" cannot pass.
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: Add `connected: boolean` to `SocketState` and `initialSocketState`. Register `socket.on('connect', ...)` and `socket.on('disconnect', ...)` handlers that dispatch a `SOCKET_CONNECTED` / `SOCKET_DISCONNECTED` action. Expose `connected` from `SocketContextValue`. Any page can then read `const { state } = useSocket(); state.connected`.
- **Linked commit**: (Phase 3b 填寫)

---

## BUG-B002: Stage progress / status lost on page refresh — no HTTP recovery endpoint for in-progress state

- **Status**: Open
- **Severity**: P2
- **A-phase origin**: A3 / A6
- **Layer**: frontend / backend
- **Discovery source**: Track B — static code inspection
- **Repro steps**:
  1. Start a pipeline run for a file
  2. While pipeline is running (stage 1 at 60%), hard-refresh the page
  3. `SocketProvider.tsx` re-mounts, calls `apiFetch('/api/files')` → dispatches `BULK_FILES`
  4. `BULK_FILES` only restores `files: Record<string, FileRecord>` — `stageProgress` and `stageStatus` are reset to `{}` (from `initialSocketState`)
  5. The file shows as "running" (from `file.status` field in the file record), but stage-level progress % is gone
  6. Future `pipeline_stage_progress` WebSocket events will fill it back in — but only going forward, not recovering the current %
- **Expected**: After page refresh, if a pipeline is still running, the UI should recover the current stage progress from the server (e.g. via a dedicated API endpoint or the file detail endpoint returning `stage_outputs` with current progress)
- **Actual**: `stageProgress` and `stageStatus` are purely in-memory WebSocket-derived state. A page refresh zeroes them. The user sees no progress bar for the currently running stage.
- **Note**: The `stage_outputs` field on `FileRecord` carries completed stage outputs but not in-progress stage % — it's a different concern.
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: Two options: (A) backend `GET /api/files/<id>` response includes a `current_stage_progress: { stage_idx: int, percent: float } | null` field that the active job runner updates; (B) frontend re-subscribes to WebSocket on mount and calls `GET /api/files` — accepting that progress % starts from 0 until next WebSocket event (acceptable degraded UX). Option B is simpler, already partially done. The real fix for "exact % recovery" requires server-side state.
- **Linked commit**: (Phase 3b 填寫)

---

## BUG-B003: No WebSocket event deduplication on reconnect

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A3 / A6
- **Layer**: frontend
- **Discovery source**: Track B — static code inspection of `frontend/src/lib/socket-events.ts` and `SocketProvider.tsx`
- **Repro steps**:
  1. Inspect `socketReducer` in `socket-events.ts` — no event id or sequence number in any action payload
  2. Socket.IO client reconnects automatically on network interruption
  3. Backend may re-emit in-flight events after reconnect (or events may fire twice during the reconnect window)
  4. `STAGE_PROGRESS` reducer does a simple overwrite `{ ...fileProg, [stage_idx]: percent }` — replaying an old progress % would silently regress the progress bar
  5. `PIPELINE_COMPLETE` dispatching twice would be a no-op (idempotent status set) — low impact
  6. `FILE_ADDED` duplicated would do a spread-merge — effectively idempotent
- **Expected**: Events should include a monotonic sequence number or UUID so the reducer can skip already-seen events
- **Actual**: No deduplication. A reconnect-replay of `pipeline_stage_progress` with a lower percent (e.g., replaying an old 20% after the UI shows 80%) would regress the visible progress bar.
- **Severity note**: Socket.IO's at-most-once delivery guarantees reduce the practical impact — this is a theoretical race, not a confirmed regression. Severity set P3 (low).
- **Plan impact**:
  - [x] Defer 入 backlog
- **Suggested fix**: Add `seq: int` to backend `pipeline_stage_progress` and `pipeline_stage_done` event payloads. Reducer tracks `lastSeq` per file and skips events with `seq <= lastSeq`.
- **Linked commit**: (Phase 3b 填寫)

---

### Section 6 — Bundle Code-Split Runtime (dist/ Inspection)

## BUG-B004: Proofread page chunk named `index-*.js` instead of `Proofread-*.js` — non-obvious but functionally correct

- **Status**: Open (documentation gap)
- **Severity**: P3
- **A-phase origin**: A6 C1
- **Layer**: build
- **Discovery source**: Track B — `ls frontend/dist/assets/` shows no `Proofread-*.js` chunk
- **Repro steps**:
  1. `ls frontend/dist/assets/*.js` — shows `Login-*.js`, `Dashboard-*.js`, `Pipelines-*.js`, etc., but no `Proofread-*.js`
  2. Two `index-*.js` files exist: `index-BtQ4dy0R.js` (31KB, main entry/router) and `index-CWuXN8y6.js` (39KB)
  3. Inspecting `index-CWuXN8y6.js` reveals it imports Proofread-page code — it IS the Proofread lazy chunk
  4. Root cause: `src/pages/Proofread/` is a directory; React.lazy imports `@/pages/Proofread` which resolves to `Proofread/index.tsx`. Rollup names the chunk after the file, which is `index.tsx` → `index-[hash].js`
  5. All other pages are single files (`Login.tsx`, `Dashboard.tsx` etc.) → named after the file
- **Expected**: All lazy page chunks should have recognizable names in dist for debuggability. The v4.0 A6 C1 bundle report baseline references "8 page chunks" without noting the naming discrepancy.
- **Actual**: Proofread chunk is named `index-CWuXN8y6.js` (39KB). Functionally equivalent — lazy loading works correctly. Only affects debuggability.
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: In `vite.config.ts` `manualChunks` callback, add a case for the Proofread index path:
  ```ts
  if (id.includes('/pages/Proofread/')) return 'Proofread';
  ```
  Or rename `src/pages/Proofread/index.tsx` to `src/pages/Proofread/Proofread.tsx` and update the barrel import.
- **Linked commit**: (Phase 3b 填寫)

---

### Section 7 — Structured Logging

## BUG-B005: `request_id` always `null` in all log lines including during HTTP request handling

- **Status**: Open
- **Severity**: P2
- **A-phase origin**: A6 C4
- **Layer**: backend
- **Discovery source**: Track B — live backend run with `LOG_JSON=1`, inspected `/tmp/track-b-server.log`
- **Repro steps**:
  1. Start backend: `LOG_JSON=1 LOG_LEVEL=DEBUG FLASK_PORT=5099 ... python app.py`
  2. Make HTTP requests to `/api/health`, `/api/files`, `/login`, etc.
  3. Inspect log output: every JSON line shows `"request_id": null`
  4. Confirmed across 19 werkzeug access log lines and all app-level log lines during requests
  5. `RequestIdFilter.filter()` in `logging_setup.py` sets `record.request_id = None` when `has_request_context()` returns False
  6. Werkzeug's access logger (`werkzeug` logger) fires from outside Flask's application context — `has_request_context()` returns False at that point
  7. App-level route handlers do not emit any `app.logger.info/warning/error` calls during normal GET/POST handling (only in error/exception paths), so no evidence of whether `app.logger` lines WOULD carry the request_id
- **Expected**: Log lines emitted during HTTP request processing (especially `app.logger` calls from within route handlers) should carry the `request_id` matching the `X-Request-ID` response header
- **Actual**: All log lines show `request_id: null`. The `RequestIdFilter` never finds a non-null value because:
  - Werkzeug access log fires outside Flask request context
  - Startup/background log lines are outside request context (expected null)
  - No route handler emits `app.logger` lines on normal requests, so we cannot confirm whether `app.logger` within a route would correctly carry the request_id
- **Partial mitigation**: The response header `X-Request-ID` IS correctly set (verified by curl `-D -`), so the request_id IS generated per request — it just never propagates into log lines
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: Two approaches:
  (A) Add `app.logger.debug("Request %s %s", request.method, request.path, extra={"endpoint": request.endpoint})` in a `@app.before_request` hook — this fires inside Flask request context and would correctly carry `request_id`. The werkzeug access log can then be suppressed.
  (B) Replace werkzeug access log with a Flask `@app.after_request` hook that calls `app.logger.info(...)` — this IS inside Flask request context.
  The root cause (werkzeug logger firing outside context) cannot be fixed by changing the filter.
- **Linked commit**: (Phase 3b 填寫)

---

## BUG-B006: Mixed plain-text and JSON lines in backend log output when LOG_JSON=1

- **Status**: Open
- **Severity**: P2
- **A-phase origin**: A6 C4
- **Layer**: backend
- **Discovery source**: Track B — live backend run with `LOG_JSON=1`, 20 plain-text lines among 16 JSON lines
- **Repro steps**:
  1. Start backend with `LOG_JSON=1`
  2. Backend stdout contains 20 plain-text lines and 16 JSON lines (46 total raw lines, 20 non-JSON)
  3. Plain-text lines come from `print()` calls in `app.py` lines 41, 43, 67, 70, 83, 86, 396, 408, 733–738, 749–750, 757, 760, 762
  4. Example non-JSON output: `"faster-whisper available — will use for live transcription"`, `"MoTitle - Backend Server"`, `"已載入 0 個已上傳文件"`
  5. Any log aggregation pipeline (e.g. Filebeat, fluentd, CloudWatch Logs Insights) that expects newline-delimited JSON will fail to parse these lines
- **Expected**: When `LOG_JSON=1`, ALL stdout output should be valid JSON. `print()` calls should be replaced with `logging.getLogger(__name__).info(...)` equivalents
- **Actual**: 20+ `print()` calls in `app.py` bypass the Python logging system entirely, producing unformatted plain-text startup messages mixed into the JSON stream
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: Replace all `print()` calls in `app.py` with `logger = logging.getLogger("app")` calls (or `current_app.logger` equivalents). The `logging_setup.configure_logging()` already configures the root logger — any module-level `logging.getLogger("app")` call will route through the JSON formatter automatically.
- **Linked commit**: (Phase 3b 填寫)

---

## Deferred Sections

## DEFERRED-S1: Real ASR validation (mlx-whisper medium model)

- **Reason**: Real-binary E2E pipeline exceeds subagent time budget. ASR runs take minutes per file and require downloading/loading models.
- **Prereq**: mlx-whisper package confirmed installed (arm64). Model download status unknown — `mlx-whisper` medium model (~3GB) may need to be downloaded first.
- **Env**: M-series Mac ✓, mlx-whisper installed ✓, FFmpeg 8.0.1 ✓
- **Suggested followup**: Dedicated mlx-whisper validation session. Test with 3 audio samples: (1) English broadcast clip, (2) Cantonese speech clip, (3) Mixed-language clip. Verify: cn_convert s2hk flag triggers for zh language config, merge_short_segments no 1-word fragments, initial_prompt bias decoder behavior.

## DEFERRED-S2: Real MT validation — Ollama (qwen3.5:35b-a3b-mlx-bf16)

- **Reason**: Real MT pipeline runs with a 70GB model exceed subagent time budget. Translation of 100+ segments takes 1-5 minutes per run.
- **Prereq**: Ollama confirmed running with `qwen3.5:35b-a3b-mlx-bf16` model ✓ (~70GB), 32GB+ RAM, Apple Silicon
- **Suggested followup**: Dedicated MT validation session. Test: batch_size=1 single-segment mode (verify 1:1 alignment), batch_size=10 (verify no cross-segment redistribution), parallel_batches=4, prompt_overrides injection verification, translation_passes=2 enrich pass.

## DEFERRED-S4: Real FFmpeg render validation

- **Reason**: Full render pipeline (upload video → ASR → MT → approve → render) exceeds subagent time budget. FFmpeg is available (8.0.1 confirmed), but a test video needs to be generated, a full pipeline run needs to complete first, and render jobs take 30s–2min each.
- **Prereq**: FFmpeg ✓, 1.3 TB disk ✓, but no test MP4 at expected paths. A synthetic test video can be generated with `ffmpeg -f lavfi -i testsrc=duration=30:size=1920x1080:rate=25 -f lavfi -i sine=frequency=440:duration=30 test.mp4`.
- **Suggested followup**: Dedicated render session. Generate synthetic 30s test MP4. Run full pipeline to get approved translations. Test all 12 render matrix items (MP4 CRF/CBR/2-pass, MXF ProRes 0-5, XDCAM 10/50/100 Mbps). Verify ffprobe metadata for each output.
