# v4.0 A5 Cleanup — Baseline Snapshot

**Captured:** 2026-05-17
**Branch:** chore/asr-mt-rearchitecture-research
**Git SHA:** 056f6e454ea2ae229e013407bb17a1ebbf896b28

## Backend pytest

```
FAILED tests/test_e2e_render.py::test_render_modal_has_mxf_option - playwrigh...
FAILED tests/test_e2e_render.py::test_render_modal_switching_to_mxf_shows_prores_section
FAILED tests/test_e2e_render.py::test_render_mp4_triggers_download_with_correct_filename
FAILED tests/test_e2e_render.py::test_render_mxf_triggers_download_with_correct_filename
FAILED tests/test_e2e_render.py::test_render_error_shows_toast_with_message
FAILED tests/test_e2e_render.py::test_render_modal_crf_slider_updates_label
FAILED tests/test_phase5_security.py::test_socketio_cors_origins_uses_lan_regex
FAILED tests/test_queue_routes.py::test_queue_returns_only_own_jobs_for_user
FAILED tests/test_renderer.py::test_ass_filter_escapes_colon_in_path - Assert...
14 failed, 946 passed, 4 skipped, 12 warnings in 106.67s (0:01:46)
```

## Frontend Vitest

```
 Test Files  29 passed (29)
      Tests  186 passed (186)
   Start at  12:04:39
   Duration  1.22s (transform 515ms, setup 1.19s, collect 2.15s, tests 1.41s, environment 7.39s, prepare 1.20s)
```

## Test pollution (untracked JSON in backend/config/)

| Subdir | Count |
|---|---|
| asr_profiles | 271 |
| mt_profiles | 271 |
| pipelines | 171 |
| glossaries | 5 |

## Notes

A5 deletes the following surface areas (counts will drop accordingly post-cleanup):
- `backend/profiles.py` + `test_profiles.py` (~?? tests)
- `backend/translation/alignment_pipeline.py` + `test_alignment_pipeline.py` (~?? tests)
- `backend/translation/sentence_pipeline.py` + `test_sentence_pipeline.py` (~?? tests)
- `backend/translation/post_processor.py` (if exists) + tests
- Legacy `_auto_translate` + `transcribe_with_segments` related test cases
- Legacy `/api/profiles*` route tests (~?? tests)
- Legacy `/api/translate` route tests (~?? tests)
- Legacy `/api/transcribe` no-pipeline-id fallback test (1 case)

Expected post-A5 backend test count: baseline minus ~80-100 deleted tests.
Frontend Vitest expected stable at 186 (only Proofread `useActiveProfile` swap → `useFilePipeline`, same test count).

Pre-existing failures (14) — none related to A5 surface area:
- 11 Playwright E2E (`test_e2e_render.py`, etc.) — need browser
- 1 macOS tmpdir colon-escape baseline (`test_ass_filter_escapes_colon_in_path`)
- 1 SocketIO CORS regex (`test_socketio_cors_origins_uses_lan_regex`)
- 1 queue routes isolation (`test_queue_returns_only_own_jobs_for_user`)
