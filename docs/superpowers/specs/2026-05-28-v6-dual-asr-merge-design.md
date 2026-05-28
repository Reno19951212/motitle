# V6 Dual-ASR Merge to dev — Design Spec

**Date:** 2026-05-28
**Source branch:** `feat/frontend-redesign` (V6 work merged via 95d6f67)
**Target branch:** `dev`
**Status:** DESIGN READY — awaiting implementation

---

## 1. Problem Motivation

The V6 VAD + Dual-ASR + Refiner architecture was developed on `feat/frontend-redesign` and operator-validated against:
- 賽馬 4-min Cantonese broadcast (100% entity name accuracy, zero cascade hallucinations)
- Winning Factor 14-min English newscast

V6's hypothesis — "clean ASR at source" — directly addresses the Cantonese broadcast failure modes that v3.x cannot solve:
- Cascade hallucinations at silence boundaries (Whisper artifact)
- Cantonese entity name misrecognition (袁幸堯, 史滕雷, HIGHLAND BLINK)
- Tail orphan English fragments
- Cantonese particle preservation (嘅/咗/啦/喺/嘢)

`dev` continues to ship v3.x Profile-based ASR + MT with iterative improvements (v3.17 preset trim, v3.18 MT prompt override). The two branches have diverged significantly:
- `feat/frontend-redesign` adds 485 files, +109k / −25k lines (includes React rewrite)
- `dev` cannot adopt the full feat branch (would lose v3.17-v3.18 work + React introduces frontend rewrite burden)

**Goal:** graft only the V6 **backend** architecture onto `dev`, preserving dev's vanilla HTML/JS frontend and all v3.17-v3.18 features. Users gain a second category in the Pipeline strip — `Dual-ASR Pipeline (V6)` — alongside the existing `Profile` category, with one-click switching and per-file override support.

---

## 2. Scope

**In scope:**
- All V6 backend modules (`stages/`, `engines/`, `pipelines.py`, `pipeline_runner.py`, V6 routes, V6 tests, V6 config)
- Settings.json schema upgrade (`active_kind` + `active_id`, backward-compat with `active_profile`)
- File registry `active_kind` snapshot for race-condition-free dispatch
- Dispatch hooks in `app.py` (`_asr_handler` + `_mt_handler`)
- Frontend Pipeline strip categorized preset menu (2 sections: Profile / V6)
- Frontend Pipeline strip V6-specific columns (VAD / Qwen3 Context / Refiner) when V6 active
- Proofread page 自訂 Prompt panel mode-aware (V6 file → qwen3_context + refiner_prompt textareas)
- Dashboard inline prompt panel reachable from V6 strip columns
- v3.18 `prompt_overrides` whitelist extension (add `qwen3_context` + `refiner_prompt`)
- 2 V6 pipeline configs (賽馬廣播 Cantonese + Winning Factor EN) + supporting refiner/transcribe/llm profile JSONs
- Operator validation parity with feat branch v6-validation report

**Out of scope:**
- V5 dual-ASR pipeline path (`asr_primary + secondary + verifier + refiner + translator`) — V5 stages imported but no entry point wired
- React frontend (user explicitly preserved vanilla)
- Per-file VAD threshold override (inline panel only edits Qwen3 context + refiner prompt)
- V6 over OpenRouter (first ship uses Ollama qwen3.5:35b-a3b-mlx-bf16 only)
- Parallel Stage 1A ∥ 1B execution (sequential as in feat branch)
- v3.18 MT `prompt_overrides` ↔ V6 `refiner_prompt` auto-translation (different layers, kept independent)

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Active selection (settings.json)                                │
│   active_kind:  "profile"  | "pipeline_v6"                      │
│   active_id:    <profile_id or pipeline_id>                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
               ┌─────────────┴────────────┐
               ▼                          ▼
       ┌───────────────┐          ┌────────────────┐
       │  Profile path │          │ V6 Pipeline    │
       │  (existing)   │          │ path (NEW)     │
       │               │          │                │
       │ transcribe    │          │ PipelineRunner │
       │ _with_segs    │          │   ._run_v6()   │
       │       ↓       │          │     Stage 0    │
       │ _auto_        │          │     Stage 1A   │
       │ translate     │          │     Stage 1B   │
       │       ↓       │          │     Stage 2    │
       │  registry     │          │     Stage 3    │
       │               │          │     ↓ persist  │
       └───────────────┘          └────────────────┘
                    \\           //
                     File registry (shared)
                          ↓
              Proofread / Render (shared)
```

**Core principle: two paths coexist, dispatched by `settings.json.active_kind` for new jobs.** Uploaded files snapshot `active_kind` so in-flight jobs are immune to user mode switches mid-job.

**Boundary cleanness:**
- All V6 backend lives in new folders (`stages/`, `engines/`, `pipelines.py`, `pipeline_runner.py`).
- Dev's `profiles.py`, `transcribe_with_segments`, `_auto_translate` are not modified.
- `app.py` gains ~15 hook lines (blueprint register + dispatch).

---

## 4. Data Model

### 4.1 `config/settings.json` schema

**Existing:**
```json
{ "active_profile": "dev-default" }
```

**Post-merge:**
```json
{
  "active_kind": "profile",
  "active_id":   "dev-default",
  "active_profile": "dev-default"
}
```

Read order: prefer new fields; fall back to `active_profile` for backward compat. Write: always set all three in lock-step (no drift).

### 4.2 V6 pipeline JSON shape

```json
{
  "id": "4696bbaa-...",
  "name": "[v6] 賽馬廣播 (Cantonese)",
  "pipeline_type": "v6_vad_dual_asr",
  "version": 6,
  "source_lang": "zh",
  "target_languages": ["zh"],
  "vad": {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": 15,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200
  },
  "qwen3_asr": {
    "language": "Chinese",
    "context": "袁幸堯 史滕雷 HIGHLAND BLINK ...",
    "post_s2hk": true
  },
  "asr_primary": {
    "transcribe_profile_id": "82338761-...",
    "source_lang": "zh"
  },
  "refinements": {
    "zh": [{ "refiner_profile_id": "f7f72bd9-..." }]
  },
  "translators": {},
  "font_config": { "family": "Noto Sans TC", "color": "white", "outline_color": "black" },
  "user_id": null,
  "created_at": 1748390400.0,
  "updated_at": 1748390400.0
}
```

`transcribe_profile_id` / `refiner_profile_id` / `llm_profile_id` are reference-by-id pointing to child JSONs in their own folders, so multiple pipelines share LLM/ASR configs.

### 4.3 File registry per-entry snapshot

Each file entry adds:
```json
{
  "active_kind": "pipeline_v6",
  "active_id":   "4696bbaa-..."
}
```

Set once at upload. All downstream handlers (`_asr_handler`, `_mt_handler`, re-transcribe, re-translate, retry) dispatch on the file entry's snapshot, NOT on `settings.json`. This guards against user switching active mid-job.

### 4.4 `prompt_overrides` whitelist extension

v3.18 keys preserved: `anchor`, `single`, `enrich`, `pass1`.
V6 adds: `qwen3_context`, `refiner_prompt`.

Validator in `backend/translation/prompt_override_validator.py` extends `ALLOWED_KEYS` from 4 → 6. Per-key validation rules unchanged (string, max length, not null when present).

Resolution (3-level fallthrough, mode-aware):
- Profile mode: `_resolve_prompt_override(key)` walks **file > active profile > None** over keys `{anchor, single, enrich, pass1}`.
- V6 mode: `_resolve_prompt_override(key)` walks **file > active pipeline > None** over keys `{qwen3_context, refiner_prompt}`. The pipeline-level default for `qwen3_context` lives in `pipeline.qwen3_asr.context`; the pipeline-level `refiner_prompt` default lives in the referenced `refiner_profile.prompt_template`.

The 3-level pattern matches v3.18's existing resolver shape — only the source of the middle level (profile vs pipeline) and the key whitelist differ per mode.

---

## 5. Backend Changes

### 5.1 New files (zero conflict — pure graft from feat branch)

| Path | LOC | Purpose |
|---|---|---|
| `backend/stages/__init__.py` | ~80 | PipelineStage ABC + StageContext |
| `backend/stages/asr_stage.py`, `mt_stage.py`, `glossary_stage.py` | ~370 | Stage wrappers for dev engines (V5 use) |
| `backend/stages/v5/*.py` | ~600 | V5 stages (imported, not wired) |
| `backend/stages/v6/silero_vad_stage.py` | ~140 | Stage 0 — Silero VAD |
| `backend/stages/v6/qwen3_per_region_stage.py` | ~80 | Stage 1A — per-region Qwen3-ASR |
| `backend/stages/v6/time_anchored_merge_stage.py` | ~210 | Stage 2 — merge Qwen3 text + mlx timestamps |
| `backend/engines/factory.py`, `_quality_flags.py` | ~140 | Engine factory + QA flags |
| `backend/engines/llm/{ollama,openrouter}.py` | ~250 | LLM clients |
| `backend/engines/refiner/llm_refiner.py` | ~220 | Stage 3 refiner LLM wrapper |
| `backend/engines/transcribe/qwen3_*.py` | ~380 | 3 files for Qwen3 subprocess bridge |
| `backend/engines/translator/llm_translator.py` | ~180 | V5 translator |
| `backend/engines/verifier/llm_verifier.py` | ~160 | V5 verifier (imported, not used in V6) |
| `backend/pipelines.py` | ~280 | PipelineManager CRUD |
| `backend/pipeline_runner.py` | ~620 | `_run_v5` + `_run_v6` dispatch |
| `backend/pipeline_schema_v5.py` | ~180 | Pipeline JSON validation |
| `backend/transcribe_profiles.py` | ~140 | TranscribeProfileManager |
| `backend/llm_profiles.py` | ~140 | LLMProfileManager |
| `backend/refiner_profiles.py` | ~150 | RefinerProfileManager |
| `backend/asr_profiles.py` | ~220 | V5 legacy (imported; evaluate dropping) |
| `backend/routes/pipelines.py` | ~310 | 8 V6 pipeline endpoints |
| `backend/routes/{refiner,transcribe,llm}_profiles.py` | ~840 | Child profile endpoints |
| `backend/scripts/v5_prototype/qwen3_vad_subprocess.py` | ~120 | py3.11 subprocess entry |

**Total: ~5,500 LOC backend code, zero conflict with dev files.**

### 5.2 New config files (pure graft)

| Path | Count | Content |
|---|---|---|
| `config/pipelines/*.json` | 2 | 賽馬廣播 Cantonese + Winning Factor EN |
| `config/refiner_profiles/*.json` | 2 | zh broadcast HK + en newscast |
| `config/transcribe_profiles/*.json` | 4 | mlx-whisper configs |
| `config/llm_profiles/*.json` | 1 | Ollama qwen3.5:35b-a3b |
| `config/prompt_templates_v5/refiner/*.json` | 3 | zh_broadcast_hk_default, zh_broadcast_hk_v6, en_newscast |

`user_id` of imported pipelines rewritten to `null` (shared) by migration script.

### 5.3 Modified files

#### `backend/app.py` (~60 LOC added across 7 hook points)

1. Import + manager initialization (~10 LOC)
2. Blueprint register (~6 LOC)
3. `_register_file` accepts `active_kind` + `active_id` kwargs (~6 LOC)
4. `_asr_handler` dispatch on `active_kind` (~10 LOC)
5. `_mt_handler` short-circuit when `active_kind == "pipeline_v6"` (~10 LOC)
6. `/api/me` response includes `active_kind` + `active_id` (~3 LOC)
7. New `POST /api/active` unified set-active endpoint (~20 LOC)

#### `backend/profiles.py` (~10 LOC)

`ProfileManager.set_active` writes all three fields (`active_kind="profile"`, `active_id`, `active_profile`).
`ProfileManager.get_active` reads `active_kind`; returns None if not `"profile"`.

#### `backend/translation/prompt_override_validator.py` (~5 LOC)

`ALLOWED_KEYS = {"anchor", "single", "enrich", "pass1", "qwen3_context", "refiner_prompt"}`.

### 5.4 New tests

| Test file | Cases | Coverage |
|---|---|---|
| `tests/test_v6_stages.py` | 55 | Stage 0 / 1A / 1B / 2 behavior + StageContext fields |
| `tests/test_v6_runner.py` | 18 | `_run_v6` dispatch + 3-level override resolution |
| `tests/test_v6_refiner_json_unwrap.py` | 14 | JSON unwrap, short-input bypass, max_tokens=300 |
| `tests/test_v6_pipeline_config.py` | 7 | Pipeline JSON validity |
| `tests/test_active_kind_dispatch.py` | 10 | `_asr_handler` / `_mt_handler` dispatch, registry snapshot, MT short-circuit |
| `tests/test_settings_schema_migration.py` | 6 | Old-schema lazy promote, dual-write no drift, legacy fallback |

**Total: ~110 new backend test cases.**

### 5.5 New requirements

```
silero-vad>=6.2.1
soundfile>=0.13.0
```

`mlx_qwen3_asr` lives only in `scripts/v5_prototype/venv_qwen/` (py3.11 subprocess venv, not in main venv).

---

## 6. Frontend Changes

### 6.1 `frontend/index.html` (~200 LOC added)

**State:** new globals `activePipeline`, `activeKind`, `availablePipelines`.

**Fetch:** `fetchActivePipeline`, `fetchPipelines` added to init chain.

**Preset menu:** two sections — `舊有 Profile 組合` (existing) + `Dual-ASR Pipeline (V6)` (new).

**Strip layout switches on `activeKind`:**
- Profile mode: existing 4 columns (ASR / MT / 輸出 / 術語表) — unchanged.
- V6 mode: 4 columns (VAD / Qwen3 Context / 輸出 / Refiner) — new.

**New functions:** `activatePipeline(id)`, `renderPipelineStripV6(el)`, `openPromptPanelInline(key)`, `commitInlinePrompt()`, `closeInlinePromptPanel()`.

**Inline prompt panel:** floating panel reachable by clicking V6 Qwen3 Context or Refiner column. Edits **pipeline JSON** (global) or **refiner_profile JSON** (refiner case) — not per-file override.

**Existing functions unchanged:** `applyAsrModel`, `applyMtEngine`, `applyGlossary`, `applyLanguageConfig`, `applyOutputFormat`, profile manage modals, glossary CRUD, file upload, render modal.

### 6.2 `frontend/proofread.html` (~60 LOC added)

自訂 Prompt panel becomes mode-aware:
- Profile file → show 4 textareas (anchor / single / enrich / pass1) — existing v3.18 behavior.
- V6 file → show 2 textareas (qwen3_context / refiner_prompt) — new.

`commitOverrides()` branches on `activeFile.active_kind` and PATCHes the correct shape to `/api/files/<id>`.

「📝 自訂 Prompt」chip logic on dashboard file card is unchanged — works for any non-null `prompt_overrides` regardless of key set.

### 6.3 New CSS (~50 LOC)

V6-specific column accent border (`--accent-2`) + floating inline panel styles.

### 6.4 New Playwright tests

`frontend/tests/test_v6_pipeline_strip.spec.js`:

| Test | Verifies |
|---|---|
| `presetMenuShowsBothSections` | Dropdown shows both `舊有 Profile 組合` + `Dual-ASR Pipeline (V6)` headers |
| `activateV6PipelineRendersV6Columns` | Selecting V6 pipeline swaps ASR/MT → VAD/Qwen3/Refiner columns |
| `clickQwen3ContextOpensInlinePanel` | Click Qwen3 column → inline panel opens, textarea preloaded with `pipeline.qwen3_asr.context` |
| `commitInlinePanelPatchesPipeline` | Commit inline panel → PATCH `/api/pipelines/<id>` receives correct payload |
| `switchBackToProfileRestoresProfileColumns` | V6 → Profile switch restores ASR/MT/glossary column rendering |
| `proofreadPanelShowsV6FieldsForV6File` | Opening V6 file in Proofread → panel shows only qwen3_context + refiner_prompt textareas |
| `proofreadCommitV6OverridesPatchesFile` | Commit V6 file override → PATCH `/api/files/<id>` receives correct shape |

---

## 7. Job Dispatch + Concurrency

### 7.1 End-to-end flow

```
Upload → _current_active_snapshot() → _register_file(active_kind, active_id)
       → enqueue "asr" job → worker picks up _asr_handler(job)
       → dispatch on file.active_kind:
         ├── profile     → transcribe_with_segments(...) → enqueue "translate" → _auto_translate
         └── pipeline_v6 → PipelineRunner(pl)._run_v6(...) → Stage 0 → 1A → 1B → 2 → 3 → persist
                          → _mt_handler short-circuits (V6 refiner is inline)
```

### 7.2 `_mt_handler` short-circuit

When `file.active_kind == "pipeline_v6"`, MT handler returns immediately with `translation_status='completed'` because V6 Stage 3 refiner already serves the MT role. No double-translation.

### 7.3 Cancel + retry

Cancel: `cancel_event` threaded into `PipelineRunner._run_v6(cancel_event=...)`. V6 stages already cooperate (feat branch verified).
Retry: file's `active_kind` snapshot drives retry path — V6 file retries through V6, Profile file retries through Profile.

### 7.4 Concurrency model

| Resource | Profile path | V6 path |
|---|---|---|
| ASR worker pool | 1 worker (existing) | Same pool, jobs queue together |
| MT worker pool | 3 workers (R5 Phase 1) | V6 short-circuits, doesn't consume |
| Qwen3 subprocess | N/A | Single subprocess per Stage 1A invocation (ephemeral, not daemon) |
| Ollama daemon | translation engines | refiner stage — shares same Ollama HTTP queue |

No new worker pool added.

### 7.5 Crash recovery

`recover_orphaned_running` + `attempt_count` cap (v3.13 R5 Phase 5) applies uniformly. Qwen3 subprocess crash → `subprocess.run(check=True)` raises → V6 stage `transform()` propagates → PipelineRunner catches → job marked failed with traceback.

### 7.6 Race condition guards

`PipelineRunner` receives pipeline dict (snapshot), not ID. If `PipelineManager.get()` returns None at dispatch time (pipeline deleted mid-job), `_asr_handler` marks job failed with explicit error.

`PipelineManager.delete()` rejects deletion when in-flight jobs reference the pipeline.

---

## 8. Migration

### 8.1 Settings.json

Lazy promote: `_read_settings` detects old schema (no `active_kind`) → upgrades to new schema on first write. No manual step.

### 8.2 File registry

`backend/scripts/migrate_active_kind.py` — idempotent script run at boot:
```python
for fid, entry in registry.items():
    if 'active_kind' not in entry:
        entry['active_kind'] = 'profile'
        entry['active_id'] = entry.get('profile_id') \
                          or _profile_manager._read_settings().get('active_profile') \
                          or 'prod-default'
```

### 8.3 Qwen3 venv

`backend/scripts/setup_v6.sh`:
```bash
cd backend/scripts/v5_prototype
python3.11 -m venv venv_qwen
venv_qwen/bin/pip install mlx_qwen3_asr==0.3.5 soundfile numpy
```

Optional — if `venv_qwen/` missing at boot, `app.config["V6_AVAILABLE"]=False`; frontend grays out V6 section with tooltip.

### 8.4 Imported pipeline ownership

Pre-existing `user_id=627` (admin_p3 on feat branch) rewritten to `null` (shared) on import, so any dev user sees V6 pipelines.

---

## 9. Testing Strategy

### 9.1 Acceptance gates (merge to main)

1. ✅ All new backend unit + integration tests green (~110 cases).
2. ✅ All new frontend Playwright tests green (7 cases).
3. ✅ Dev's existing 813-pass / 14-fail baseline preserved — proves Profile path unbroken.
4. ✅ Operator validation on 賽馬 4-min Cantonese clip — metrics align with feat branch's [v6-validation.md](../validation/v6-validation.md):
   - Stage 0 VAD: ~28 regions, 91% speech ratio, < 1s runtime
   - Stage 1A: 100% entity name accuracy (袁幸堯, 史滕雷, HIGHLAND BLINK)
   - Stage 2: ~84 final segments
   - Stage 3 refiner: < 5% drops, 0 cascade artifacts.

### 9.2 Coverage layers

| Layer | Test | Cases |
|---|---|---|
| Settings migration | `test_settings_schema_migration.py` | 6 |
| Dispatch hooks | `test_active_kind_dispatch.py` | 10 |
| V6 stages | `test_v6_stages.py` (graft) | 55 |
| V6 runner | `test_v6_runner.py` (graft) | 18 |
| V6 refiner | `test_v6_refiner_json_unwrap.py` (graft) | 14 |
| V6 config | `test_v6_pipeline_config.py` (graft) | 7 |
| V6 e2e handler | `test_v6_e2e_handler.py` (new) | 4 |
| Frontend strip | `test_v6_pipeline_strip.spec.js` | 7 |

---

## 10. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| silero-vad py3.9 incompatibility | Low | High | Pin `silero-vad>=6.2.1`. Feat branch operator-validated on py3.9. Boot smoke test. |
| Qwen3 venv missing on deploy | Med | Med (V6 unavailable, Profile still works) | `V6_AVAILABLE` flag → frontend grays V6 section. `setup_v6.sh` < 5 min. |
| v3.18 `prompt_overrides` shape conflict | Low | Low | Whitelist purely extends; 4 legacy keys validation unchanged. Tests cover V6 key ignored in Profile mode. |
| `_mt_handler` short-circuit drift | Med | High (V6 file stuck "pending") | Dedicated tests in `test_active_kind_dispatch.py`. Boot smoke test runs the V6 short-circuit path. |
| Concurrent set_active conflict | Low | Med | ProfileManager + PipelineManager share `_write_settings` file lock. Concurrent-thread test verifies final state. |
| Imported pipelines orphaned (`user_id=627`) | High | Med | Migration script rewrites `user_id=null` on import. |
| Silero VAD false positive on pure music | Low | Low | feat branch validated `threshold=0.5` cleanly suppresses pure music. Threshold remains user-tunable. |
| Inline panel + Proofread panel collision | Low | Low | Different storage layers — inline = pipeline JSON (global), Proofread = file overrides (per-file). No race. |

### Rollback path

```bash
git rm -r backend/stages backend/engines
git rm backend/pipelines.py backend/pipeline_runner.py backend/pipeline_schema_v5.py
git rm backend/{transcribe,llm,refiner,asr}_profiles.py
git rm -r backend/routes/{pipelines,refiner_profiles,transcribe_profiles,llm_profiles}.py
git rm -r backend/config/{pipelines,refiner_profiles,transcribe_profiles,llm_profiles}
git rm -r backend/tests/test_v6_*.py backend/tests/test_active_kind_dispatch.py backend/tests/test_settings_schema_migration.py
git checkout HEAD~ -- backend/app.py backend/profiles.py backend/translation/prompt_override_validator.py
git checkout HEAD~ -- frontend/index.html frontend/proofread.html
echo '{"active_profile":"dev-default"}' > backend/config/settings.json
```

All V6 code lives in new folders. Rollback never touches dev's existing logic.

---

## 11. Implementation Plan (commit-by-commit)

| Phase | Description | LOC + tests | Commits |
|---|---|---|---|
| 1 | Backend graft (V6 modules + config + tests) | +5500 / +94 tests | 1 |
| 2 | Hook integration (`app.py` + `profiles.py` + validator) + unit tests | +60 / +16 tests | 2 |
| 3 | Frontend rewiring (`index.html` + `proofread.html`) | +260 | 1 |
| 4 | Frontend Playwright tests | +7 cases | 1 |
| 5 | Migration script + setup_v6.sh | +50 | 1 |
| 6 | CLAUDE.md v3.19 + README + setup docs | +200 docs | 1 |
| 7 | Operator validation (賽馬 + Winning Factor) | — | 1 |
| | | | **8 total** |

---

## 12. Open Questions

None at design time. All major decisions resolved during brainstorm:
- Scope: backend-only graft, vanilla HTML/JS frontend preserved ✅
- Coexistence: 2-section Pipeline preset menu (Profile / V6) ✅
- V6 strip layout: 4 columns swap (VAD / Qwen3 Context / 輸出 / Refiner) ✅
- Override integration: extend v3.18 `prompt_overrides` whitelist + mode-aware Proofread panel ✅
- Override access: inline panel on Dashboard V6 columns + existing Proofread panel ✅
- Merge method: branch graft (single import commit + manual hook commit) ✅

---

## 13. References

- V6 original design: [`feat/frontend-redesign:docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md`](../../../../docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md)
- V6 implementation plan: [`feat/frontend-redesign:docs/superpowers/plans/2026-05-21-v6-vad-dual-asr-refiner-plan.md`](../../../../docs/superpowers/plans/2026-05-21-v6-vad-dual-asr-refiner-plan.md)
- V6 operator validation report: [`feat/frontend-redesign:docs/superpowers/validation/v6-validation.md`](../../../../docs/superpowers/validation/v6-validation.md)
- Source merge commit on feat branch: 95d6f67 (Merge feat/v6-vad-dual-asr-refiner: VAD + dual-ASR + simplified refiner)
- Dev current state: v3.18 (MT prompt override), Pipeline fix for missing `dev-default.json` (current session, uncommitted)
