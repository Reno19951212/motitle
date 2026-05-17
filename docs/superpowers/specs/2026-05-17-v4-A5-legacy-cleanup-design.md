# v4.0 A5 — Legacy Cleanup Design

> **Status**: Design (2026-05-17). Final sub-phase of v4.0 rearchitecture.
> **Parent spec**: [2026-05-16-asr-mt-emergent-pipeline-design.md](2026-05-16-asr-mt-emergent-pipeline-design.md)
> **Sister sub-phases**: A1 (backend foundation) + A3 (frontend foundation) + A4 (proofread page) — all done.
> **Goal**: Retire all legacy code paths replaced by v4.0's Pipeline / Stage architecture, then Big Bang merge `chore/asr-mt-rearchitecture-research` → `main`.

## 1. Overview

A5 finishes the v4.0 transition by deleting the legacy code that A1+A3+A4 made obsolete. The user picked **aggressive cleanup** — retire the full legacy MT chain (`_auto_translate`, `alignment_pipeline.py`, `sentence_pipeline.py`, `post_processor.py`, `ProfileManager`), the legacy Flask static routes for vanilla HTML, and all related tests. Test fixture isolation is added so future tests don't leak JSON into `backend/config/`.

After A5, the codebase contains exactly one path for transcription + translation: file upload → enqueue `pipeline_run` job → PipelineRunner walks ASRStage → MTStage(s) → GlossaryStage → emits Socket.IO progress → completes. No legacy fallback.

## 2. Goals

| # | Goal |
|---|------|
| G1 | Delete `frontend.old/` directory and all references |
| G2 | Retire 5 legacy Flask `*.html` routes + `/js/` + `/css/` + `_FRONTEND_LEGACY_DIR` |
| G3 | Make `pipeline_id` mandatory on `POST /api/transcribe`; kill legacy `asr` job fallback |
| G4 | Retire legacy `/api/translate` endpoint |
| G5 | Retire legacy `/api/profiles*` endpoints (7 routes) + `backend/profiles.py` module |
| G6 | Retire legacy `_auto_translate` function + `transcribe_with_segments` from app.py |
| G7 | Retire legacy translation modules: `alignment_pipeline.py`, `sentence_pipeline.py`, `post_processor.py` + their tests |
| G8 | Replace Proofread page's `/api/profiles/active` dependency with `pipeline.font_config` lookup |
| G9 | Clean test pollution + add fixture isolation so future tests don't leak JSON into `backend/config/` |
| G10 | Update CLAUDE.md (delete legacy sections, add A5 entry, refresh REST endpoint table) |
| G11 | Final regression: all remaining backend tests + 183 frontend Vitest + Playwright smoke pass |

## 3. Out of Scope

| Item | Phase |
|------|-------|
| Whisper engine refactor | Future — engine code unchanged |
| MT engine refactor | Future — `OllamaTranslationEngine` stays (stages use it) |
| Frontend overlay font asset bundling | Already done in v3.6 |
| Mobile responsive design | Backlog |
| Deletion of `backend/profiles.py` glossary-related code | Stays — glossary is separate from profiles |

## 4. Architecture Changes

### 4.1 Frontend changes

**Delete:**
- `frontend.old/` (entire directory ≈ 2833-line `proofread.html` + 5 other HTML files + `js/` + `css/` + `node_modules/` + `tests/`)

**Modify:**
- `frontend/src/pages/Proofread/hooks/useActiveProfile.ts` — signature changes from `useActiveProfile()` to `useActiveProfile(pipelineId)`; reads `pipeline.font_config` instead of `/api/profiles/active`. Returns `{font, refresh}` (no longer wraps full ActiveProfile, just font).
- Anything that imported `ActiveProfile` type now imports `FontConfig` from `@/lib/schemas/pipeline` (existing type from A3).

### 4.2 Backend route deletions

From `backend/app.py`:

| Route | Reason |
|-------|--------|
| `GET /login.html` | Legacy vanilla HTML page (A4 ships React `/login`) |
| `GET /proofread.html` | Legacy (A4 ships React `/proofread/<id>`) |
| `GET /admin.html` | Legacy (A3 ships React `/admin`) |
| `GET /Glossary.html` | Legacy (A3 ships React `/glossaries`) |
| `GET /index.html` | Legacy (A3 ships React `/`) |
| `GET /js/<path>` | Legacy static serving from `frontend.old/js/` |
| `GET /css/<path>` | Legacy static serving from `frontend.old/css/` |
| `GET /api/profiles` | Legacy bundled ProfileManager |
| `POST /api/profiles` | Legacy |
| `GET /api/profiles/active` | Legacy (Proofread now reads pipeline.font_config) |
| `GET /api/profiles/<id>` | Legacy |
| `PATCH /api/profiles/<id>` | Legacy |
| `DELETE /api/profiles/<id>` | Legacy |
| `POST /api/profiles/<id>/activate` | Legacy |
| `POST /api/translate` | Legacy MT trigger (A1 added pipeline_run) |

`POST /api/transcribe` modified: `pipeline_id` becomes **required**. Missing field → 400. The legacy `asr` job fallback path deleted.

`_FRONTEND_LEGACY_DIR` constant + helper deleted.

### 4.3 Backend code deletions

| File / function | Reason |
|---|---|
| `backend/profiles.py` (entire file) | Legacy `ProfileManager` — replaced by ASRProfileManager + MTProfileManager + PipelineManager in P1 |
| `backend/translation/alignment_pipeline.py` | Legacy LLM-marker alignment — replaced by MTStage |
| `backend/translation/sentence_pipeline.py` | Legacy sentence-merge — replaced by MTStage |
| `backend/translation/post_processor.py` | Legacy `[LONG]` / `[NEEDS REVIEW]` flags — replaced by stage `quality_flags` |
| `app._auto_translate` | Legacy MT trigger — replaced by `_pipeline_run_handler` |
| `app.transcribe_with_segments` | Legacy in-process Whisper pipeline — replaced by ASRStage |
| `app._profile_manager` instance | Legacy singleton |

Legacy Socket.IO events (still emitted by deleted code paths) — incidentally removed:
- `subtitle_segment` (was emitted per ASR segment during transcribe)
- `translation_progress` (per-batch MT progress)
- `pipeline_timing` (post-MT timing summary)

The v4.0 events that remain: `file_added`, `file_updated`, `pipeline_stage_progress`, `pipeline_stage_complete`, `pipeline_complete`, `pipeline_failed`, `model_loading`, `model_ready`, `model_error`.

### 4.4 Test pollution + fixture isolation

**Delete (one-time):**
- `backend/config/asr_profiles/*.json` (test leftovers — ~50+ files)
- `backend/config/mt_profiles/*.json`
- `backend/config/pipelines/*.json`
- `backend/.coverage`

> Preserve: any glossary in `backend/config/glossaries/` that's referenced by a real (non-test) workflow. If the user has real glossary data here, leave it. If everything is test debris, also delete.

**Fixture isolation:** add `_CONFIG_DIR_OVERRIDE` env var to `app.py`:

```python
_CONFIG_DIR = os.environ.get("R5_CONFIG_DIR") or os.path.join(os.path.dirname(__file__), "config")
```

Then `backend/tests/conftest.py` sets `R5_CONFIG_DIR` to a per-test `tmp_path` directory via fixture. All managers (`ASRProfileManager`, `MTProfileManager`, `PipelineManager`, `GlossaryManager`) read this so tests are fully isolated from each other AND from the real config dir.

### 4.5 Test deletions

After legacy code is removed, these test files lose their target:

| Test file | Action |
|-----------|--------|
| `backend/tests/test_profiles.py` | DELETE (tests `ProfileManager`) |
| `backend/tests/test_sentence_pipeline.py` | DELETE |
| `backend/tests/test_alignment_pipeline.py` | DELETE |
| `backend/tests/test_translation.py` (legacy MT engine tests) | KEEP only the tests for `OllamaTranslationEngine` which stages still use; delete `_auto_translate` related cases |
| `backend/tests/test_v317_validation.py` | KEEP (validation helpers may still be useful) — but delete cases that call `_auto_translate` |
| `backend/tests/test_phase5_security.py::test_profile_*` etc. | KEEP if testing ASR/MT/Pipeline ownership (P1 work); DELETE if testing legacy `/api/profiles*` |
| `backend/tests/test_admin_users.py` | KEEP (still relevant) |

Approach: run full backend suite after each deletion; identify newly-failing tests; either fix to use v4.0 endpoints (preferred) or delete if redundant. Document the deletions in commit messages.

## 5. Approach

A5 is a deletion-heavy phase. Each task removes a slice and ensures the suite is GREEN before moving on. Order matters: delete frontend assets first (no risk), then frontend dependencies, then backend code in increasing-risk order, then tests, then fixture isolation, then docs.

### 5.1 Phasing

1. **Pre-flight**: snapshot current test state (count baseline)
2. **Frontend cleanup** (low risk):
   - T1: Update `useActiveProfile(pipelineId)` to read from pipeline
   - T2: Delete `frontend.old/`
3. **Backend Flask routes** (medium risk):
   - T3: Delete legacy `*.html` + static routes
   - T4: Make `pipeline_id` mandatory on `/api/transcribe`
4. **Backend MT chain** (higher risk):
   - T5: Delete `_auto_translate` + `transcribe_with_segments` from `app.py`
   - T6: Delete `/api/translate` endpoint
   - T7: Delete `/api/profiles*` endpoints + `backend/profiles.py`
   - T8: Delete `alignment_pipeline.py` + `sentence_pipeline.py` + `post_processor.py`
5. **Test cleanup**:
   - T9: Delete tests for now-removed code; rewrite reachable ones
   - T10: Add fixture isolation (R5_CONFIG_DIR env)
   - T11: Delete leftover JSON pollution from `backend/config/*_profiles/`
6. **Docs + final regression**:
   - T12: Update CLAUDE.md
   - T13: Final regression sweep + push for Big Bang merge

### 5.2 Risk Mitigation

- After each deletion, run `pytest -x --tb=short` to catch regressions immediately
- If a deletion breaks tests for code we still want to keep, REVERT and re-scope
- For Proofread `useActiveProfile` rewrite: ship before deleting `/api/profiles/active` so Proofread keeps working through the transition
- After all deletions: run full `pytest tests/ -q` to confirm regression numbers
- Frontend `npm test` should stay 183 PASS throughout
- Build sanity: `npm run build` must succeed after every commit
- Don't push to origin until A5 fully green and merged into local branch

## 6. Acceptance Criteria

- [ ] `frontend.old/` no longer in tree
- [ ] No file in repo references `_FRONTEND_LEGACY_DIR`
- [ ] `POST /api/transcribe` without `pipeline_id` returns 400
- [ ] All routes from §4.2 return 404
- [ ] All Python files from §4.3 deleted
- [ ] Backend tests: count is reasonable (some will be deleted; the rest stay green)
- [ ] Frontend tests: 183 Vitest PASS preserved
- [ ] `npm run build` clean
- [ ] CLAUDE.md updated (A5 entry + legacy sections removed from REST endpoint table)
- [ ] Branch pushed to origin; ready for `gh pr create` Big Bang merge

## 7. Approval

- [x] Design self-reviewed
- [x] Scope: aggressive cleanup + fixture isolation (user-confirmed)
- [ ] Plan written (next step)

---

**Next**: invoke `superpowers:writing-plans` → `docs/superpowers/plans/2026-05-17-v4-A5-legacy-cleanup-plan.md`. Tasks carry 🎯 Goal + ✅ Acceptance markers consistent with A1/A3/A4 plan format. ~13 tasks total.
