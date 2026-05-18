# Bug Tracker — Track A (Playwright suite)

**Track:** A
**Owner:** Track A subagent (authoring phase 2026-05-18)
**Start:** 2026-05-18
**Status:** Authoring complete — 6 spec files + helpers.ts + global-setup.ts written. Execution deferred to T7b.

---

## Schema

Each finding is one H2 section:

```
## BUG-NNN: <短描述>
- **Status**: Open / In progress / Fixed / Wontfix / Deferred
- **Severity**: P0 / P1 / P2 / P3 (will triage in Phase 2)
- **A-phase origin**: P1 / A1 / A3 / A4 / A5 / A6 / cross-phase
- **Layer**: backend / frontend / E2E / docs / config / build
- **Discovery source**: Track A
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

(Track A subagent adds findings below as separate H2 sections)

## BUG-001: No media fixture file in repo — upload-path E2E specs auto-skip
- **Status**: Open
- **Severity**: P2
- **A-phase origin**: cross-phase
- **Layer**: E2E
- **Discovery source**: Track A authoring
- **Repro steps**: Run `npm run test:e2e:seeded`. The `happy-path-pipeline.spec.ts` upload scenario and `cancel-running-job.spec.ts` inflight cancel scenario auto-skip with "No fixture file at tests-e2e/fixtures/sample.{mp4,mp3,wav}".
- **Expected**: A small sample media file (≤5 MB, e.g., 5-second silence .mp4 or .mp3) exists at `frontend/tests-e2e/fixtures/` so upload-path tests can run without manual setup.
- **Actual**: Directory `frontend/tests-e2e/fixtures/` does not exist. All upload-dependent specs degrade gracefully to skip — no hard failure.
- **Plan impact**:
  - [x] 需開新 sub-phase
- **Suggested fix**: Add `frontend/tests-e2e/fixtures/sample.mp3` (5s silence, mono 16kHz WAV or any tiny valid media file) via `ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 5 -q:a 9 -acodec libmp3lame sample.mp3` and commit it. Update `frontend/tests-e2e/.gitignore` to NOT ignore `.mp3` / `.mp4` in fixtures/. Then the upload+pipeline E2E tests gain real coverage.
- **Linked commit**: (Phase 3b 填寫)

## BUG-002: global-setup.ts seed idempotency limitation — 409 on existing seed loses entity IDs
- **Status**: Open
- **Severity**: P2
- **A-phase origin**: cross-phase
- **Layer**: E2E
- **Discovery source**: Track A authoring
- **Repro steps**: Run `npm run test:e2e:seeded` twice. On second run, `POST /api/asr_profiles` returns 409 (already exists). `seedPost()` returns `{}` — no `id` — so pipeline creation is skipped with a warning.
- **Expected**: Idempotent seed that recovers entity IDs from a GET /api/asr_profiles list when POST returns 409, so pipeline creation always succeeds.
- **Actual**: `global-setup.ts` logs a warning and skips pipeline creation on second run. Only the first run creates the full seed (ASR + MT + Glossary + Pipeline all linked). The `pipeline-broken-refs.spec.ts` depends on the linked pipeline existing.
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: After a 409, call `GET /api/asr_profiles` and find the entry by name ("E2E Whisper Profile") to recover its ID. Same pattern for MT profiles. Implement a `getOrCreate(listPath, name, createBody)` helper in `global-setup.ts`.
- **Linked commit**: (Phase 3b 填寫)

## BUG-003: `test:e2e:seeded` script uses `E2E_REQUIRE_SEED=1` env var syntax which requires bash — Windows npm scripts may fail
- **Status**: Open
- **Severity**: P3
- **A-phase origin**: cross-phase
- **Layer**: build
- **Discovery source**: Track A authoring
- **Repro steps**: On Windows, run `npm run test:e2e:seeded`. The script `"E2E_REQUIRE_SEED=1 playwright test ..."` uses Unix inline env syntax not supported by `cmd.exe`.
- **Expected**: Script works on Windows (the project supports Windows per CLAUDE.md).
- **Actual**: Windows npm will fail with "E2E_REQUIRE_SEED=1" not recognized as a command.
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: Use `cross-env` package: `"test:e2e:seeded": "cross-env E2E_REQUIRE_SEED=1 playwright test --global-setup=./tests-e2e/global-setup.ts"`. Add `cross-env` to devDependencies. (Alternative: use a `.env` file + `dotenv-cli`.)
- **Linked commit**: (Phase 3b 填寫)

## BUG-004: PromptOverridesDrawer Save button only works if `file.pipeline_id` is non-null — files without pipeline_id silently no-op
- **Status**: Open
- **Severity**: P2
- **A-phase origin**: A4
- **Layer**: frontend
- **Discovery source**: Track A authoring (reading PromptOverridesDrawer.tsx line 53: `if (!file || !file.pipeline_id) return;`)
- **Repro steps**: Open a file on /proofread that was uploaded without a pipeline_id (e.g., legacy files or files uploaded before A5 forced pipeline_id). Click "⚙ Overrides", fill a textarea, click Save. Nothing is POSTed. No error shown to user.
- **Expected**: Either (a) Save button is disabled with a tooltip "No pipeline attached to this file", or (b) user sees a toast error explaining the save was a no-op.
- **Actual**: Save() returns silently if `!file.pipeline_id`. User gets no feedback.
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: In `PromptOverridesDrawer.tsx`, disable the Save button when `!file?.pipeline_id` and add a `title="File has no pipeline — overrides cannot be saved"` tooltip. Or throw/toast on the early return.
- **Linked commit**: (Phase 3b 填寫)

## BUG-005: StageRerunMenu renders inside SegmentRow but spec 4a targets it via `summary` locator — may not find it if file has no stage_outputs yet
- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A4
- **Layer**: E2E
- **Discovery source**: Track A authoring (StageRerunMenu.tsx line 25: `const stages = file.stage_outputs ?? []`)
- **Repro steps**: Open /proofread/<id> for a file where ASR has run but no stage_outputs array is populated in FileDetail (e.g., older files with legacy transcription path). The Re-run dropdown shows "No stages yet." and the `summary` with "Re-run" text does exist, but clicking it shows no stage buttons.
- **Expected**: When `stage_outputs` is empty, the Re-run dropdown should either be hidden or clearly disabled to prevent user confusion.
- **Actual**: `<summary>Re-run</summary>` is rendered even when `stages.length === 0` — the dropdown opens but shows "No stages yet." without any actionable buttons.
- **Plan impact**:
  - [x] Defer 入 backlog
- **Suggested fix**: In `StageRerunMenu.tsx`, conditionally render the entire `<details>` only when `stages.length > 0`. Or keep it but style the summary button as disabled.
- **Linked commit**: (Phase 3b 填寫)
