# v4.0 Debug Branch — Closure Summary

**Branch:** `debug/v4-e2e-bug-hunt`
**Parent:** `chore/asr-mt-rearchitecture-research` @ `ca5b110`
**Closed:** 2026-05-18
**Total commits:** 23

## Outcome

✅ **Branch close target met** (Ambitious per spec §11.2 + Phase 3a decision).

- P0: 0
- P1: 0 (BUG-030 ship-blocker found mid-execution + fixed inline)
- P2 active: 10 → all Fixed
- P3 active 純 bug fix: 4 → all Fixed
- Deferred (backlog): 3
- Confirmed out-of-scope: 14
- **Total findings: 31**

v4.0 pipeline end-to-end validated REAL (not just unit-tested) via isolated backend E2E.

## Critical discoveries (would have blocked v4.0 ship)

1. **BUG-030 [P1]** — `PipelineRunner.stage_outputs` not bridged to legacy `entry["segments"]` / `entry["translations"]`. After every v4 pipeline run, ALL downstream consumers (/segments, /translations, /render) saw empty arrays. **The frontend would have shown "completed" files with no content.** Found via T27-T29 inline real E2E (which only became possible after BUG-029 fix).
2. **BUG-029 [P2]** — `DATA_DIR` / `UPLOAD_DIR` / `RENDERS_DIR` hardcoded in `managers.py:55`. Any test subagent that booted `python app.py` (not pytest) wrote into production data dir. **Track B subagent earlier in this session leaked an orphan backend that polluted production for hours.** Fixed by adding `R5_DATA_DIR` env override.
3. **BUG-031 [P2]** — Backend render status `"done"` vs frontend `useRenderJob.ts` polls for `"completed"`. Download never triggered. 1-line backend fix.
4. **BUG-010 [P2]** — `request_id` never propagated to log records (werkzeug logger fires outside Flask request context). A6 C4 implementation regression. Fixed via `contextvars.ContextVar`.
5. **BUG-011 [P2]** — 20+ `print()` calls in app.py bypassed structured logger → JSON log stream contamination under `LOG_JSON=1`. Fixed.

## Commit timeline

| # | Phase | SHA | Description |
|---|---|---|---|
| 1 | Phase 0 setup | `cc5b728` | baseline + tracker templates |
| 2 | Phase 1 Track A | `0593e8b` | Playwright suite expansion |
| 3 | Phase 1 Track C | `dec7447` | Static analysis audit pass |
| 4 | Phase 1 Track B | `e63fbd5` | Manual matrix scoped §5/6/7 |
| 5 | Phase 1 Track D | `ba605c1` | Known-issue harvest 17 entries |
| 6 | Phase 2 | `97511ca` | Consolidate + triage report |
| 7 | Phase 3a | `b519c5e` | Decisions locked + plan amended |
| 8-10 | Phase 3b G1 | `aca1a01`, `b307790`, `376edf7` | Test infra (BUG-001/002/003) |
| 11-12 | Phase 3b G2 | `b731d5d`, `97f59a4` | A6 C4 logging (BUG-010/011) |
| 13 | Phase 3b G3 | `f0eedf0` | A4 UX (BUG-004) |
| 14-15 | Phase 3b G4 | `d95e885`, `82f6a51` | SocketProvider reliability (BUG-006/007) |
| 16-18 | Phase 3b G5 | `7083765`, `7597ffb`, `1cece50` | Bundle + cleanup (BUG-009/018/020) |
| 19 | T30 | `70a98d2` | Defer confirmations (BUG-005/008/019) |
| 20 | BUG-029 fix | `2dce3d4` | R5_DATA_DIR env override (enables real E2E) |
| 21 | T27-T29 | `8bbfc30` | Real ASR + MT + render E2E validation |
| 22 | BUG-031 | `dcf35b7` | Render status naming alignment |
| 23 | BUG-030 | `9f98c7e` | stage_outputs → legacy fields bridge (ship blocker) |

## Test counts

| Metric | Baseline (parent) | Final (debug branch) | Delta |
|---|---|---|---|
| Backend pytest pass | 794 | 807 | +13 new |
| Backend baseline fail | 14 | 14 | preserved exactly |
| Frontend Vitest pass | 184 | 193 | +9 new |
| Frontend tsc | clean | clean | — |
| Frontend build | clean | clean (+ Proofread chunk) | improved |
| Playwright specs | 11 | 17 | +6 new (BUG-002 etc) |

## Real-binary E2E validation (T27-T29)

Performed against isolated backend (`R5_DATA_DIR=/tmp/v4-t27-29-data`, port 5097):

- **T27 ASR**: faster-whisper small, 3.7s English audio → 1 segment `"Hello World This is a test of the broadcast subtitle pipeline."`, 7.6s latency ✅
- **T28 MT**: Ollama `qwen3.5:35b-a3b-mlx-bf16`, 1 translation `"你好世界 這是廣播字幕管線的測試。"`, 20.2s ✅
- **T29 Render** (3 representative formats):
  - MP4 CRF: H.264 / 640×360 / 25fps / 22KB ✅
  - MXF ProRes HQ: prores / 640×360 / 4.6MB ✅
  - XDCAM HD 422 @ 50Mbps: mpeg2video / exact 50Mbps CBR / 96MB ✅

All renders produced valid binary outputs verified by `ffprobe`.

## Files changed (production code)

- `backend/managers.py` — `R5_DATA_DIR` env override (BUG-029)
- `backend/middleware.py` + `backend/logging_setup.py` — contextvar request_id propagation (BUG-010)
- `backend/app.py` — `_bridge_stage_outputs_to_legacy()` helper + `_pipeline_run_handler` integration + replaced 20+ print() with logger calls (BUG-011, BUG-030)
- `backend/routes/render.py` + `backend/helpers/render_options.py` — status naming `"done"` → `"completed"` (BUG-031)
- `backend/routes/engines.py` + ollama probe — timeout + memoization (BUG-020)
- `frontend/vite.config.ts` — Proofread chunk naming (BUG-009)
- `frontend/src/providers/SocketProvider.tsx` + `frontend/src/lib/socket-events.ts` — connected state + running recovery (BUG-006/BUG-007)
- `frontend/src/pages/Proofread/PromptOverridesDrawer.tsx` — disable Save when no pipeline_id (BUG-004)
- `frontend/package.json` + `frontend/tests-e2e/{global-setup,helpers,fixtures,*.spec}.ts` — test infra (BUG-001/002/003)
- `CLAUDE.md` — dead Socket.IO emitter row removal (BUG-018)

## Files changed (docs only)

- `docs/superpowers/specs/2026-05-18-v4-debug-e2e-design.md` (v2 amendment from self-review)
- `docs/superpowers/plans/2026-05-18-v4-debug-e2e-plan.md` (amended with Phase 3b tasks per Phase 3a)
- `docs/superpowers/debug/v4-debug-baseline.md`
- `docs/superpowers/debug/v4-bug-tracker.md` (master)
- `docs/superpowers/debug/v4-bug-tracker-track{A,B,C,D}-*.md` (sub-trackers)
- `docs/superpowers/debug/v4-e2e-matrix.md`
- `docs/superpowers/debug/v4-phase2-report.md`
- `docs/superpowers/debug/v4-phase3-decisions.md`
- `docs/superpowers/debug/v4-deferred-backlog.md`
- `docs/superpowers/debug/v4-t27-29-findings.md`

## Outstanding pollution

⚠️ User `id=4450 username=admin is_admin=1` was created in production `backend/data/app.db` at 14:50 on 2026-05-18 by an earlier failed isolated-backend startup attempt (before BUG-029 was identified + fixed). Permission system denied autonomous DELETE; user was given the SQL command to clean manually. **Status: user-action pending**.

## Deferred-by-design (3 entries — re-evaluate triggers in `v4-deferred-backlog.md`)

- BUG-005: StageRerunMenu empty-state cosmetic
- BUG-008: WebSocket event sequence/dedup (theoretical race)
- BUG-019: faster-whisper BatchedInferencePipeline (needs real-audio validation)

## Confirmed out-of-scope (14 entries — audit trail)

See `v4-bug-tracker-trackD-known.md`. Notably:
- BUG-017 (CI/CD GitHub Actions): P2 most-production-impact among OOS, but spec §10 excludes v4.0 scope
- StreamingSession抽離 / Mac-Win packaging / mobile responsive / i18n / Storybook (5 items)
- v3.18 Stage 3+ deferred features (8 items)

## Merge guidance

Recommend fast-forward merge into `chore/asr-mt-rearchitecture-research`:

```
git checkout chore/asr-mt-rearchitecture-research
git merge --ff-only debug/v4-e2e-bug-hunt
```

After merge, CLAUDE.md update is recommended (add v4.0 Debug branch entry to "Completed Features" section). Production data DELETE for stray admin user_id=4450 should be done manually.

## Spec amendment policy compliance

All amendments to original spec + plan tracked in:
- Spec v2 (commit `e773865`): 8 self-review fixes applied (P0+P1 from inline review)
- Plan amendment (commit `b519c5e`): Phase 3b tasks added per Phase 3a decisions
- No major-scope re-brainstorming required (per spec §12 amendment policy)
