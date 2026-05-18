# T27-T29 Real E2E Findings

**Date:** 2026-05-18
**Backend:** isolated boot via R5_DATA_DIR=/tmp/v4-t27-29-data R5_CONFIG_DIR=/tmp/v4-t27-29-config on port 5097
**Backend health:** Confirmed isolated (BUG-029 fix verified end-to-end — upload_dir = `/private/tmp/v4-t27-29-data/uploads`)
**Branch:** `debug/v4-e2e-bug-hunt` at `2dce3d4`

---

## Setup notes

- ASR profile: `whisper` / `large-v3` / `cpu` / `int8` / `beam_size=1` / `condition_on_previous_text=false`
- MT profile: `qwen3.5-35b-a3b` / system_prompt = translate EN → Traditional Chinese / `en`→`en` same-lang constraint
- Pipeline: ASR → MT (1 stage) → Glossary disabled
- Test audio: `/tmp/v4-debug-media/test-en.mp3` (3.7s, English speech)
- Test video: `/tmp/v4-debug-media/test-video.mp4` (15s, mostly silent with 1 utterance)
- Ollama running locally with `qwen3.5:35b-a3b-mlx-bf16` available

---

## T27 — Real ASR (faster-whisper large-v3, CPU int8)

- **Status: PASS** — ASR stage produced correct output
- **Segment count:** 1
- **Sample segment text:** `"Hello World This is a test of the broadcast subtitle pipeline."`
- **ASR duration:** 7.61s for 3.7s audio (2× realtime — expected for CPU int8 large-v3)
- **faster-whisper log:** `Processing audio with duration 00:03.727` — confirmed 3.7s clip processed
- **Numpy warnings observed:** `divide by zero` / `overflow` / `invalid value` in `feature_extractor.py` matmul during mel spectrogram. Non-fatal — ASR still succeeded. Likely triggered by the very short/quiet audio content. Not a blocker.
- **Stage output storage:** Stored in `registry.stage_outputs["0"]` ✓

---

## T28 — Real MT (Ollama qwen3.5:35b-a3b-mlx-bf16)

- **Status: PASS** — MT stage produced correct Chinese translation
- **Translation count vs segment count:** 1 vs 1 (match ✓)
- **Sample input:** `"Hello World This is a test of the broadcast subtitle pipeline."`
- **Sample translation:** `"你好世界 這是廣播字幕管線的測試。"` — accurate Traditional Chinese
- **MT duration:** 20.15s (Ollama local inference, expected latency for 35B model)
- **Total pipeline duration (ASR + MT):** 27.77s for 3.7s audio
- **Stage output storage:** Stored in `registry.stage_outputs["1"]` ✓

**Video pipeline (T28b — test-video.mp4 with 1 silent utterance "Thank you."):**
- ASR: `"Thank you."` in 4.8s
- MT: `"多謝。"` in 17.37s — correct Cantonese/Traditional Chinese

---

## Critical architectural gap discovered (BUG-030)

**CRITICAL FINDING:** The v4 PipelineRunner stores stage outputs exclusively in `registry.stage_outputs[{idx}]` but the entire downstream stack — `/api/files/<id>/segments`, `/api/files/<id>/translations`, `POST /api/render`, Proofread page — reads from the legacy `entry["segments"]` and `entry["translations"]` fields which are NEVER populated by the v4 pipeline.

**Confirmed consequences:**
1. `GET /api/files/<id>/segments` → `{"segments": [], "status": "uploaded"}` even after successful pipeline run
2. `GET /api/files/<id>/translations` → `{"translations": []}` even after successful MT
3. `GET /api/files` → `{"segment_count": 0, "status": "uploaded"}` — file appears untouched
4. `POST /api/render` → `{"error": "File has no translations to render"}` — render blocked

**Registry also missing `pipeline_id` field** — `_register_file()` does not persist it, and `GET /api/files` does not return it. The Proofread page `FileDetail` type includes `pipeline_id?: string | null` but the backend never populates it.

**Workaround used for T29:** Manually injected translations from `stage_outputs` into legacy `entry["segments"]` / `entry["translations"]` fields by editing the registry JSON and restarting the backend.

---

## T29 — FFmpeg renders (3 representative formats)

*Tested with manually injected translations (workaround for BUG-030). FFmpeg render pipeline itself operates correctly.*

### T29a — MP4 CRF mode

- **Status: PASS**
- **render_id:** `28f1de1c2227`
- **Output file:** `renders/28f1de1c2227.mp4` — 21,927 bytes
- **ffprobe metadata:**
  - Video: `h264`, 640×360, 25fps
  - Audio: `aac`
  - Frames: 375 (15s × 25fps ✓)
- **Render API status field:** `done` (not `completed` — see BUG-031)
- **Subtitle content:** `"Thank you."` / `"多謝。"` correctly selected by `subtitle_source: "auto"` → shows ZH target

### T29b — MXF ProRes HQ (profile 3)

- **Status: PASS**
- **render_id:** `d61d2676e8f5`
- **Output file:** `renders/d61d2676e8f5.mxf` — 4,621,893 bytes (~4.6MB)
- **ffprobe metadata:**
  - Video: `prores`, 640×360, 25fps
  - Audio: `pcm_s16le`
- **ProRes profile verified:** codec_name=prores ✓

### T29c — MXF XDCAM HD 422 @ 50 Mbps

- **Status: PASS**
- **render_id:** `bd711730949a`
- **Output file:** `renders/bd711730949a.mxf` — 96,040,517 bytes (~96MB)
- **ffprobe metadata:**
  - Video: `mpeg2video`, 640×360, 25fps, **bit_rate: 50000000** (exactly 50Mbps ✓)
  - Audio: `pcm_s16le`, 1536000 bps
- **CBR bitrate enforcement verified** ✓

---

## New BUGs discovered

### BUG-030 [P1] — PipelineRunner stage outputs not bridged to legacy segments/translations fields

- **Source:** T27-T29 inline validation
- **Severity:** P1 — blocks ALL proofread + render functionality post-v4 pipeline run
- **Repro:**
  1. Upload file, trigger `POST /api/transcribe` with `pipeline_id`
  2. Wait for pipeline_run job to complete (`status: done` in jobs DB)
  3. `GET /api/files/<id>/segments` → `{"segments": [], "status": "uploaded"}`
  4. `GET /api/files/<id>/translations` → `{"translations": []}`
  5. `POST /api/render` → `{"error": "File has no translations to render"}`
- **Root cause:**
  - `_pipeline_run_handler` → `PipelineRunner.run()` → `_persist_stage_output()` → writes to `entry["stage_outputs"][str(idx)]`
  - No code path writes to `entry["segments"]`, `entry["translations"]`, `entry["status"]`, `entry["asr_seconds"]`, `entry["translation_seconds"]`, `entry["pipeline_seconds"]`
  - `_register_file()` does not store `pipeline_id` → `GET /api/files` never returns it
  - `GET /api/files/<id>/segments` → `helpers/files.py` reads `entry["segments"]` (legacy)
  - `GET /api/files/<id>/translations` → `routes/files.py:493` reads `entry["translations"]` (legacy)
  - `POST /api/render` → `routes/render.py:115` reads `entry["translations"]` (legacy)
- **Suggested fix:**
  - Option A (recommended): After `PipelineRunner.run()` completes, call a bridge function that reads `stage_outputs[-1]["segments"]` (last MT stage) and populates:
    - `entry["segments"]` from stage 0 (ASR) segments
    - `entry["translations"]` from paired ASR+MT segments (en_text = stage 0, zh_text = last MT stage)
    - `entry["status"] = "done"`
    - `entry["asr_seconds"]` from stage 0 duration
    - `entry["translation_seconds"]` from stage 1 duration
    - `entry["pipeline_seconds"]` from total
    - `entry["pipeline_id"]` = pipeline_id from job payload
  - Option B: Update all downstream read paths to look at `stage_outputs` first, falling back to legacy fields for pre-v4 data

### BUG-031 [P2] — Render status naming mismatch: backend uses `"done"`, frontend polls for `"completed"`

- **Source:** T29 inline validation
- **Severity:** P2 — render job completes successfully but frontend Proofread page never triggers download
- **Repro:**
  1. Submit render job via `POST /api/render`
  2. Poll `GET /api/renders/<id>` — returns `{"status": "done"}` when complete
  3. Frontend `useRenderJob` hook polls for `status === "completed"` (line 42 of `useRenderJob.ts`)
  4. Result: polling never terminates, download never triggered despite render succeeding
- **Root cause:**
  - `backend/routes/render.py:197`: `_app._render_jobs[render_id] = {**job_state, "status": "done"}`
  - `frontend/src/pages/Proofread/hooks/useRenderJob.ts:42`: `updated.status === 'completed'`
  - Mismatch: `"done"` vs `"completed"`
- **Suggested fix:** Either:
  - Change backend to emit `"status": "completed"` on success (update `routes/render.py` lines 197, 273); OR
  - Change frontend to accept `"done"` as terminal status (update `useRenderJob.ts`)
  - Recommend: align to `"done"` (consistent with jobs table `status CHECK(... 'done' ...)`) and update frontend

---

## Notes

- Test video was silent/black 15s with one detected utterance "Thank you." → expected ASR behavior for near-silent media
- All 3 render formats (MP4 H.264, MXF ProRes HQ, MXF XDCAM HD 422) FFmpeg output verified valid by ffprobe
- XDCAM bitrate enforcement exact at 50Mbps ✓
- Render API response uses `render_id` (not `id`) — confirmed correct
- The backend render status value `"done"` is internally consistent (jobs table uses `done` for all job types) but inconsistent with the frontend type definition `'completed'`
- Isolation: R5_DATA_DIR env override confirmed working end-to-end (BUG-029 fix validated)
- No production data contamination — all operations on isolated /tmp path

---

## Summary

| Task | Result | Key metric |
|---|---|---|
| T27 ASR (faster-whisper large-v3) | PASS | 1 segment, correct text, 7.61s |
| T28 MT (Ollama qwen3.5:35b-a3b) | PASS | 1 translation, correct ZH, 20.15s |
| T28b Video pipeline | PASS | "Thank you." → "多謝。" |
| T29a MP4 CRF render | PASS (with workaround) | 22KB, h264, 640×360, 25fps |
| T29b MXF ProRes HQ | PASS (with workaround) | 4.6MB, prores, 25fps |
| T29c XDCAM HD 422 | PASS (with workaround) | 96MB, mpeg2video, 50Mbps ✓ |
| BUG-030 discovered | CRITICAL | stage_outputs not bridged to legacy fields — blocks proofread + render |
| BUG-031 discovered | P2 | render status "done" vs "completed" mismatch |

**Overall: ASR, MT, and FFmpeg render paths all function correctly in isolation. BUG-030 is a P1 architectural gap that must be fixed before the v4 pipeline is usable end-to-end through the UI.**
