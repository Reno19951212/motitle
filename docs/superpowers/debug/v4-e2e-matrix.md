# v4.0 Debug — Manual E2E Matrix

每個 section 開頭列 prerequisite。環境唔具備就 mark `[N/A — missing <X>]` 入 Track B tracker，唔當失敗。

## Section 1: 真實 ASR
**Prerequisite:** M-series Mac + mlx-whisper medium model (~3GB downloaded)

- [DEFER — see DEFERRED-S1] mlx-whisper medium 跑廣東話樣本
- [DEFER — see DEFERRED-S1] mlx-whisper medium 跑英文樣本
- [DEFER — see DEFERRED-S1] mlx-whisper medium 跑中英混合樣本
- [DEFER — see DEFERRED-S1] 確認 cn_convert s2hk flag 真正 trigger
- [DEFER — see DEFERRED-S1] 確認 merge_short_segments 唔產 1-word fragment
- [DEFER — see DEFERRED-S1] 確認 initial_prompt bias decoder

## Section 2: 真實 MT — Ollama
**Prerequisite:** Local Ollama + qwen3.5-35b-a3b (~22GB) + 32GB+ RAM

- [DEFER — see DEFERRED-S2] batch_size=1 single-segment mode
- [DEFER — see DEFERRED-S2] batch_size=10 batched mode
- [DEFER — see DEFERRED-S2] parallel_batches=4
- [DEFER — see DEFERRED-S2] prompt_overrides 真正 inject 入 LLM payload
- [DEFER — see DEFERRED-S2] translation_passes=2 enrich pass trigger

## Section 3: 真實 MT — OpenRouter
**Prerequisite:** OPENROUTER_API_KEY env + paid credit

- [N/A — no OPENROUTER_API_KEY] claude-sonnet-4-5
- [N/A — no OPENROUTER_API_KEY] gpt-4o-mini
- [N/A — no OPENROUTER_API_KEY] custom model id 自訂 input

## Section 4: 真實 FFmpeg render
**Prerequisite:** FFmpeg installed + 30s test MP4 + 5GB free disk

- [DEFER — see DEFERRED-S4] MP4 CRF mode + ffprobe metadata check
- [DEFER — see DEFERRED-S4] MP4 CBR mode + ffprobe check
- [DEFER — see DEFERRED-S4] MP4 2-pass mode + ffprobe check
- [DEFER — see DEFERRED-S4] MXF ProRes profile 0 (Proxy)
- [DEFER — see DEFERRED-S4] MXF ProRes profile 1 (LT)
- [DEFER — see DEFERRED-S4] MXF ProRes profile 2 (Standard)
- [DEFER — see DEFERRED-S4] MXF ProRes profile 3 (HQ)
- [DEFER — see DEFERRED-S4] MXF ProRes profile 4 (4444)
- [DEFER — see DEFERRED-S4] MXF ProRes profile 5 (4444 XQ)
- [DEFER — see DEFERRED-S4] XDCAM HD 422 @ 10 Mbps
- [DEFER — see DEFERRED-S4] XDCAM HD 422 @ 50 Mbps
- [DEFER — see DEFERRED-S4] XDCAM HD 422 @ 100 Mbps

## Section 5: WebSocket reliability
**Prerequisite:** Chromium DevTools available
**Method used:** Static code inspection of `frontend/src/providers/SocketProvider.tsx` + `frontend/src/lib/socket-events.ts`

- [FAIL — see BUG-B001] Pipeline 中段 network throttle → progress event 保留
  - Note: Progress accumulation (STAGE_PROGRESS reducer spreads per stage_idx) is correct. But no connection state is surfaced → UI cannot show disconnected banner.
- [FAIL — see BUG-B001] Kill backend server 中途 → frontend 顯示 disconnected
  - No `connected` field in SocketState, no `socket.on('disconnect', ...)` registered
- [FAIL — see BUG-B002] 刷新 page 中途 → 重連後 state restore
  - `apiFetch('/api/files')` on mount restores file list only. `stageProgress`/`stageStatus` reset to `{}`. In-progress stage % not recoverable from any HTTP endpoint.
- [FAIL — see BUG-B003] WebSocket reconnect dedupe（spec §8 hypothesis）
  - No event sequence number in any SocketAction payload. Old progress events replayed on reconnect could regress progress bar.

## Section 6: Bundle code-split runtime
**Prerequisite:** npm run build + serve dist available
**Method used:** `ls frontend/dist/assets/` + chunk size inspection + manifest inspection

- [PASS — verified by dist inspection] First paint 只 load entry + vendor-react + Login chunk
  - Entry chunk `index-BtQ4dy0R.js`: 31KB ✓ (well under 50KB target). All 8 page chunks are separate lazy files. Login chunk `Login-DNVub5yw.js`: 2.1KB ✓
- [INCONCLUSIVE — requires live browser] Navigate /pipelines → vendor-dnd lazy load
  - `vendor-dnd-DkAakUdu.js` (44KB) exists as separate chunk ✓. Runtime lazy loading requires browser DevTools Network tab to verify.
- [INCONCLUSIVE — requires live browser] Slow 3G throttle → PageLoader fallback 顯示 OK
  - Requires browser DevTools throttling. Cannot verify by static analysis.

**Additional finding:** Proofread page chunk is named `index-CWuXN8y6.js` (39KB) instead of `Proofread-*.js` — see BUG-B004. Functionally correct, debuggability gap.

**Chunk inventory (all ≤200KB raw — PASS):**
- vendor-react: 165KB ✓
- vendor-forms: 90KB ✓
- vendor-ui: 75KB ✓
- vendor-router: 65KB ✓
- Dashboard: 68KB ✓
- vendor-dnd: 44KB ✓
- vendor-socket: 42KB ✓
- index-CWuXN8y6 (Proofread): 39KB ✓
- entry (index-BtQ4dy0R): 31KB ✓
- Pipelines: 10KB ✓
- MtProfiles: 6KB ✓
- Glossaries: 5KB ✓
- AsrProfiles: 5KB ✓
- Admin: 5KB ✓
- vendor-state: 3KB ✓
- Login: 2KB ✓

## Section 7: Structured logging
**Prerequisite:** Backend runnable + LOG_JSON=1
**Method used:** Live backend run on port 5099 + curl probes + log inspection

- [PASS] LOG_JSON=1 LOG_LEVEL=DEBUG → JSON 輸出
  - JSON format valid for all Python-logger lines. `python3 -c "json.loads(line)"` parses all 16 JSON log lines with no errors. ✓
  - Caveat: 20 plain-text lines also present (print() calls bypass logger) — see BUG-B006
- [FAIL — see BUG-B005] X-Request-ID 由 inbound HTTP → log line → 子 thread 都貫穿
  - Response header `X-Request-ID` IS correctly generated per request ✓
  - But ALL log lines show `"request_id": null` including werkzeug access lines fired during HTTP requests
  - `RequestIdFilter.has_request_context()` returns False for werkzeug logger (fires outside Flask app context)
  - No `app.logger` calls during normal route handling → cannot confirm whether in-route log lines would carry request_id
- [PASS] ApiError exception → JSON 422/4XX 而非 HTML 500
  - `/api/nonexistent` → `{"error":"not found"}` JSON 404 ✓
  - `/api/files` unauthenticated → `{"error":"unauthorized"}` JSON 401 ✓
  - `/api/transcribe` without file → JSON 400 ✓
  - All error responses are JSON, no HTML ✓
