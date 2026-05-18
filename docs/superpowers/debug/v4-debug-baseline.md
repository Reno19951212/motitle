# v4.0 Debug — Baseline Capture

**Captured:** 2026-05-18
**Branch:** debug/v4-e2e-bug-hunt (cut from parent immediately after capture)
**Parent:** chore/asr-mt-rearchitecture-research @ ca5b110

## Backend (pytest)

- Pass: **794**
- Fail: **14** (all pre-existing baseline)
- Skipped: 4
- Total: 812
- Runtime: 1m 45s

### Pre-existing baseline failures (14)

```
FAILED tests/test_e2e_render.py::test_render_button_enabled_when_all_approved
FAILED tests/test_e2e_render.py::test_render_button_disabled_when_unapproved_segments
FAILED tests/test_e2e_render.py::test_render_modal_opens_on_button_click
FAILED tests/test_e2e_render.py::test_render_modal_cancel_closes_modal
FAILED tests/test_e2e_render.py::test_render_modal_format_defaults_to_mp4
FAILED tests/test_e2e_render.py::test_render_modal_has_mxf_option
FAILED tests/test_e2e_render.py::test_render_modal_switching_to_mxf_shows_prores_section
FAILED tests/test_e2e_render.py::test_render_mp4_triggers_download_with_correct_filename
FAILED tests/test_e2e_render.py::test_render_mxf_triggers_download_with_correct_filename
FAILED tests/test_e2e_render.py::test_render_error_shows_toast_with_message
FAILED tests/test_e2e_render.py::test_render_modal_crf_slider_updates_label
FAILED tests/test_phase5_security.py::test_socketio_cors_origins_uses_lan_regex
FAILED tests/test_queue_routes.py::test_queue_returns_only_own_jobs_for_user
FAILED tests/test_renderer.py::test_ass_filter_escapes_colon_in_path
```

Known causes (per CLAUDE.md v4.0 A6 entry):
- 11 Playwright E2E specs require browser runtime (test_e2e_render.py)
- 1 v3.3 macOS tmpdir colon-escape baseline (test_renderer.py)
- 1 phase5_security SocketIO CORS regex (test_phase5_security.py)
- 1 queue_routes per-user filter (test_queue_routes.py)

## Frontend

### Build (npm run build)
- Status: **clean** (no errors, no chunkSizeWarning)
- Main entry chunk: 31.08 KB raw / 10.89 KB gzip
- Vendor chunks: 7 (`vendor-react` 165KB / `vendor-forms` 90KB / `vendor-ui` 74KB / `vendor-router` 65KB / `vendor-dnd` 44KB / `vendor-socket` 42KB / `vendor-state` ~3KB)
- Page chunks: 8 (Dashboard 67KB / Proofread 39KB / Pipelines / MtProfiles / Glossaries / AsrProfiles / Admin / Login)
- Build time: 1.16s

### Vitest (npx vitest run)
- Pass: **184**
- Files: **28**
- Duration: 1.24s (transform 631ms, setup 1.27s, tests 1.68s)

### TypeScript (npx tsc --noEmit)
- Status: **clean (0 error)**

### Playwright (npx playwright test --list)
- Specs: **14 tests in 10 files**
- Note: CLAUDE.md A6 entry mentions "11 specs / 14 cases" — actual count shows 10 files. **Discrepancy logged for Track A subagent to investigate** (may be that one spec was removed or the count was inaccurate in CLAUDE.md A6 entry).

## Static

### TODO/FIXME baseline
- Total lines (after excluding `backend/venv/` site-packages + `node_modules` + test files): **3**
- All 3 are false positives — matching "XXX" inside Chinese comments documenting Whisper training-data hallucination examples (e.g., "中文字幕由 XXX 提供")
- **Effective TODO/FIXME count in v4.0 production code: 0**

### Sample (all false positives)
```
backend/asr/whisper_engine.py:218: "...例如「中文字幕由 XXX 提供」..."
backend/asr/mlx_whisper_engine.py:45: # ...e.g., "中文字幕由 XXX 提供"...
backend/asr/mlx_whisper_engine.py:115: "...例如「中文字幕由 XXX 提供」..."
```

## Notes

- Any Phase 1 discovery finding should be compared against this baseline to determine "introduced by v4.0" vs "pre-existing in v3.x".
- Backend tree at capture time was clean before branch cut.
- Frontend `node_modules` already installed (no install needed during baseline).
- Backend `venv` healthy, all 794 tests run without env error.
