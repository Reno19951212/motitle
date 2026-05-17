# v4.0 A5 — Legacy Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Each task carries 🎯 Goal + ✅ Acceptance.

**Goal:** Retire all legacy code paths replaced by v4.0 Pipeline/Stage architecture, add fixture isolation for tests, then push branch for Big Bang merge to main.

**Architecture:** Sequential deletion in phases (frontend → Flask routes → backend Python → test cleanup → docs). Each task ends with a green test suite before the next begins. No new code — only deletions + 2 small modifications (useActiveProfile signature + conftest fixture isolation).

**Parent spec:** [2026-05-17-v4-A5-legacy-cleanup-design.md](../specs/2026-05-17-v4-A5-legacy-cleanup-design.md)

---

## File Structure Summary (deletions)

```
DELETE:
  frontend.old/                                       (entire directory)
  backend/profiles.py
  backend/translation/alignment_pipeline.py
  backend/translation/sentence_pipeline.py
  backend/translation/post_processor.py
  backend/tests/test_profiles.py
  backend/tests/test_sentence_pipeline.py
  backend/tests/test_alignment_pipeline.py
  backend/tests/test_post_processor.py  (if exists)

MODIFY:
  frontend/src/pages/Proofread/hooks/useActiveProfile.ts  (sig + impl change)
  frontend/src/pages/Proofread/index.tsx                  (pass pipelineId)
  frontend/src/pages/Proofread/VideoPanel.tsx             (consume new font type)
  frontend/src/pages/Proofread/SubtitleSettingsPanel.tsx  (PATCH pipeline instead of profile)
  frontend/src/pages/Proofread/SubtitleOverlay.tsx        (consume FontConfig type)
  frontend/src/pages/Proofread/GlossaryPanel.tsx          (use pipeline.glossary_stage)
  backend/app.py                                          (route + function deletions)
  backend/translation/__init__.py                         (remove deleted module imports)
  backend/tests/conftest.py                               (add R5_CONFIG_DIR fixture)
  backend/tests/test_translation.py                       (trim to OllamaTranslationEngine cases)
  CLAUDE.md                                               (add A5 entry, refresh REST table)

DELETE (test pollution):
  backend/config/asr_profiles/*.json   (untracked test leftovers)
  backend/config/mt_profiles/*.json    (untracked test leftovers)
  backend/config/pipelines/*.json      (untracked test leftovers)
  backend/.coverage                    (untracked coverage file)
```

---

## Task 1: Pre-flight baseline snapshot

🎯 **Goal:** Capture baseline test counts (backend + frontend) so we can detect unintended regressions vs intended deletions.

✅ **Acceptance:**
- `docs/superpowers/validation/v4-A5-baseline.md` records:
  - Backend pytest pass/fail count at HEAD
  - Frontend Vitest pass count at HEAD
  - Untracked file count in `backend/config/*_profiles/`
- Single commit

- [ ] **Step 1: Record backend baseline**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/ -q --no-header 2>&1 | tail -5
```

- [ ] **Step 2: Record frontend baseline**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npm test -- --run 2>&1 | tail -3
```

- [ ] **Step 3: Count untracked test pollution**

```bash
ls backend/config/asr_profiles/*.json 2>/dev/null | wc -l
ls backend/config/mt_profiles/*.json 2>/dev/null | wc -l
ls backend/config/pipelines/*.json 2>/dev/null | wc -l
```

- [ ] **Step 4: Write `docs/superpowers/validation/v4-A5-baseline.md`** capturing the numbers

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/validation/v4-A5-baseline.md
git commit -m "docs(v4 A5): baseline test snapshot before cleanup"
```

---

## Task 2: Update Proofread to read font from pipeline (not profile)

🎯 **Goal:** Decouple Proofread from legacy `/api/profiles/active`. Read font_config from `pipeline.font_config`. Glossary_id similarly from `pipeline.glossary_stage.glossary_ids[0]`.

✅ **Acceptance:**
- `useActiveProfile.ts` deleted; new `useFilePipeline.ts` returns `{font, glossaryId, refresh}` keyed by `file.pipeline_id`
- Proofread + VideoPanel + SubtitleOverlay + SubtitleSettingsPanel + GlossaryPanel use the new hook
- SubtitleSettingsPanel PATCHes `/api/pipelines/<pid>` body `{font_config}` instead of `/api/profiles/<pid>`
- GlossaryPanel reads `pipeline.glossary_stage.glossary_ids[0]` (or empty)
- Frontend Vitest stays green (existing tests may need props updates)
- `npm run build` 0 TS errors

**Files:**
- Delete: `frontend/src/pages/Proofread/hooks/useActiveProfile.ts` + `useActiveProfile.test.ts`
- Create: `frontend/src/pages/Proofread/hooks/useFilePipeline.ts` + `useFilePipeline.test.ts`
- Modify: `index.tsx`, `VideoPanel.tsx`, `SubtitleOverlay.tsx`, `SubtitleSettingsPanel.tsx`, `GlossaryPanel.tsx`

- [ ] **Step 1: Create useFilePipeline hook**

```ts
// src/pages/Proofread/hooks/useFilePipeline.ts
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FontConfig } from '@/lib/schemas/pipeline';

export interface PipelineSummary {
  id: string;
  name: string;
  asr_profile_id: string;
  mt_stages: string[];
  glossary_stage: {
    enabled: boolean;
    glossary_ids: string[];
    apply_order: string;
    apply_method: string;
  };
  font_config: FontConfig;
}

export function useFilePipeline(pipelineId: string | null | undefined) {
  const [pipeline, setPipeline] = useState<PipelineSummary | null>(null);

  const refresh = useCallback(async () => {
    if (!pipelineId) {
      setPipeline(null);
      return;
    }
    try {
      const p = await apiFetch<PipelineSummary>(`/api/pipelines/${pipelineId}`);
      setPipeline(p);
    } catch {
      setPipeline(null);
    }
  }, [pipelineId]);

  useEffect(() => { refresh(); }, [refresh]);

  const font = pipeline?.font_config ?? null;
  const glossaryId = pipeline?.glossary_stage.glossary_ids[0] ?? null;
  return { pipeline, font, glossaryId, refresh };
}
```

- [ ] **Step 2: Update SubtitleOverlay.tsx to accept FontConfig directly**

```tsx
// Change props from `profile: ActiveProfile | null` to `font: FontConfig | null`
import type { FontConfig } from '@/lib/schemas/pipeline';

interface Props {
  text: string;
  font: FontConfig | null;
}

export function SubtitleOverlay({ text, font }: Props) {
  // ... rest unchanged, replace profile.font with font
  if (!font || !text) return null;
  const f = font;
  // ... no other changes
}
```

- [ ] **Step 3: Update VideoPanel + SubtitleSettingsPanel + GlossaryPanel signatures**

- VideoPanel: change `profile` prop to `font`
- SubtitleSettingsPanel: change `profile` to `pipelineId`; PATCH `/api/pipelines/<pid>` body `{font_config: next}`
- GlossaryPanel: change `profile` to `glossaryId`; fetch `/api/glossaries/<gid>` if non-null

- [ ] **Step 4: Update index.tsx to wire useFilePipeline**

Replace `useActiveProfile` import + usage:
```tsx
const { font, glossaryId, refresh: refreshPipeline } = useFilePipeline(file.pipeline_id);
// pass `font` to VideoPanel/SubtitleOverlay
// pass `pipelineId={file.pipeline_id}` + `onSaved={refreshPipeline}` to SubtitleSettingsPanel
// pass `glossaryId={glossaryId}` to GlossaryPanel
```

- [ ] **Step 5: Update tests**

- Delete `useActiveProfile.test.ts`
- Write `useFilePipeline.test.ts` (3 tests: fetches pipeline on mount, null pipelineId returns null, refresh refetches)
- Update `SubtitleOverlay.test.tsx` to use new `font` prop
- Update any other test that mocked `profile`

- [ ] **Step 6: Verify + commit**

```bash
cd frontend && npm test -- --run && npm run build
git add frontend/src/pages/Proofread/
git commit -m "feat(v4 A5): Proofread reads font/glossary from pipeline (not legacy profile)"
```

---

## Task 3: Delete frontend.old/

🎯 **Goal:** Remove the entire `frontend.old/` directory.

✅ **Acceptance:**
- `frontend.old/` no longer in working tree
- `git rm -r` recorded
- All references to `frontend.old` removed from codebase (grep yields nothing in source — backend code still references `_FRONTEND_LEGACY_DIR` until T4)
- Frontend Vitest still green (the React app doesn't depend on frontend.old/)
- `npm run build` clean

- [ ] **Step 1: Verify no live code imports from frontend.old/**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
grep -rn 'frontend.old' frontend/src backend --include='*.ts' --include='*.tsx' --include='*.py' || echo "clean"
```

> Expect to see references in `backend/app.py` (still has `_FRONTEND_LEGACY_DIR`) — those go in T4. Frontend should be clean.

- [ ] **Step 2: Delete directory**

```bash
git rm -r frontend.old/
```

- [ ] **Step 3: Verify**

```bash
ls frontend.old 2>&1   # should say no such file
cd frontend && npm test -- --run && npm run build
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git commit -m "chore(v4 A5): delete frontend.old/ legacy vanilla HTML directory"
```

---

## Task 4: Delete legacy Flask static routes + `_FRONTEND_LEGACY_DIR`

🎯 **Goal:** Remove `/login.html`, `/proofread.html`, `/admin.html`, `/Glossary.html`, `/index.html`, `/js/<path>`, `/css/<path>` from `backend/app.py`. Delete `_FRONTEND_LEGACY_DIR` constant.

✅ **Acceptance:**
- 7 route handlers deleted from `app.py`
- `_FRONTEND_LEGACY_DIR` constant deleted
- Backend tests still pass (some test_spa_fallback.py tests may need adjusting — verify)
- `npm run build` clean

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Locate routes**

```bash
grep -n '\.html\|_FRONTEND_LEGACY_DIR\|/js/\|/css/' backend/app.py | head -30
```

- [ ] **Step 2: Delete routes + constant**

Remove each `@app.route(".../something.html")` def + the `_FRONTEND_LEGACY_DIR` line.

- [ ] **Step 3: Run backend tests**

```bash
cd backend && source venv/bin/activate
pytest tests/ -q --no-header 2>&1 | tail -10
```

Expect: similar pass/fail count to baseline. If new failures appear, identify which test referenced the deleted routes and remove/update them.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "chore(v4 A5): delete legacy *.html + /js/ + /css/ static routes"
```

---

## Task 5: Make pipeline_id required on /api/transcribe

🎯 **Goal:** `POST /api/transcribe` without `pipeline_id` returns 400. Legacy `asr` job fallback deleted.

✅ **Acceptance:**
- Existing test `test_transcribe_without_pipeline_id_uses_legacy_flow` is **deleted** (legacy flow gone)
- New test (or update existing) asserts 400 when `pipeline_id` missing
- `test_transcribe_with_pipeline_id_*` tests still pass
- Backend regression: only the deleted-by-design test count drops

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_transcribe_pipeline_id.py`

- [ ] **Step 1: Update handler — remove the else branch**

```python
# In /api/transcribe handler:
pipeline_id = (request.form.get("pipeline_id") or "").strip() or None
if not pipeline_id:
    return jsonify({"error": "pipeline_id is required"}), 400
# (delete the else branch that enqueued legacy 'asr' job)
```

- [ ] **Step 2: Update test**

Delete `test_transcribe_without_pipeline_id_uses_legacy_flow`. Add `test_transcribe_without_pipeline_id_returns_400`.

- [ ] **Step 3: Verify + commit**

---

## Task 6: Delete `_auto_translate` + `transcribe_with_segments` from app.py

🎯 **Goal:** The two legacy in-process pipeline functions are no longer reachable after T5. Delete them.

✅ **Acceptance:**
- `_auto_translate` function gone from `app.py`
- `transcribe_with_segments` function gone from `app.py`
- All callers updated (only legacy code paths called these; should be all dead now)
- Backend tests pass with reduced count (test for the deleted functions also deleted)

**Files:**
- Modify: `backend/app.py`
- Modify: tests that directly imported/called these

- [ ] **Step 1: Find callers**

```bash
grep -rn '_auto_translate\|transcribe_with_segments' backend/ --include='*.py'
```

- [ ] **Step 2: Delete functions + update callers (likely the legacy `/api/transcribe/sync` admin endpoint if it still exists; delete that endpoint too if it does)**

- [ ] **Step 3: Verify + commit**

---

## Task 7: Delete `/api/translate` endpoint

🎯 **Goal:** Remove legacy MT trigger.

✅ **Acceptance:**
- `POST /api/translate` 404
- Related test deleted/updated

**Files:**
- Modify: `backend/app.py`
- Modify: any test that POSTed `/api/translate`

- [ ] **Steps 1-3** same pattern as Task 6.

---

## Task 8: Delete `/api/profiles*` endpoints + `backend/profiles.py`

🎯 **Goal:** Retire legacy bundled profile manager.

✅ **Acceptance:**
- 7 `/api/profiles*` routes deleted from `app.py`
- `backend/profiles.py` deleted
- `_profile_manager` instance deleted from `app.py`
- All references purged
- `backend/tests/test_profiles.py` deleted
- Any other test that imported `from profiles import ProfileManager` deleted or updated

**Files:**
- Delete: `backend/profiles.py`, `backend/tests/test_profiles.py`
- Modify: `backend/app.py`

- [ ] **Step 1: Map dependencies**

```bash
grep -rn 'from profiles\|import profiles\|_profile_manager\|ProfileManager' backend/ --include='*.py'
```

- [ ] **Step 2: Delete + verify + commit**

---

## Task 9: Delete legacy translation modules

🎯 **Goal:** Remove `alignment_pipeline.py`, `sentence_pipeline.py`, `post_processor.py` and their tests.

✅ **Acceptance:**
- 3 modules deleted
- 3+ test files deleted (`test_alignment_pipeline.py`, `test_sentence_pipeline.py`, `test_post_processor.py` if exists)
- `backend/translation/__init__.py` updated to not import deleted modules
- `OllamaTranslationEngine` kept — it's used by `MTStage`

**Files:**
- Delete: `backend/translation/{alignment_pipeline,sentence_pipeline,post_processor}.py` + matching tests
- Modify: `backend/translation/__init__.py`

- [ ] **Step 1: Verify nothing else imports them**

```bash
grep -rn 'alignment_pipeline\|sentence_pipeline\|post_processor' backend/ --include='*.py'
```

> Expect: only `__init__.py` imports + the modules themselves + their own tests.

- [ ] **Step 2: Delete + clean __init__ + verify + commit**

---

## Task 10: Add fixture isolation via R5_CONFIG_DIR

🎯 **Goal:** Tests use a `tmp_path` config dir instead of the real `backend/config/`.

✅ **Acceptance:**
- `app.py` reads `R5_CONFIG_DIR` env if set, else default `backend/config/`
- `conftest.py` has a fixture that sets `R5_CONFIG_DIR=<tmp_path>` per-test (autouse)
- Tests no longer leak JSON into real `backend/config/`
- Backend tests still pass

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Add env knob to app.py**

```python
_CONFIG_DIR = os.environ.get("R5_CONFIG_DIR") or os.path.join(os.path.dirname(__file__), "config")
```

Reference `_CONFIG_DIR` in all manager instantiations (`ASRProfileManager(_CONFIG_DIR)`, etc.).

- [ ] **Step 2: Add conftest fixture**

```python
# backend/tests/conftest.py
@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for sub in ("asr_profiles", "mt_profiles", "pipelines", "glossaries"):
        (config_dir / sub).mkdir()
    monkeypatch.setenv("R5_CONFIG_DIR", str(config_dir))
    # Force app module reload so managers pick up the new path
    # (mirrors _restore_app_module pattern from R5 Phase 5)
    import importlib, app
    importlib.reload(app)
    yield config_dir
```

> Note: this is invasive. If full module reload breaks too many tests, fall back to: re-instantiate managers per-test via monkeypatch. Decision depends on test stability — escalate to user if stuck.

- [ ] **Step 3: Run full suite + iterate**

This task may require multiple commits if test breakage cascades. Each fix → commit → re-run.

- [ ] **Step 4: Final commit**

---

## Task 11: Delete test pollution

🎯 **Goal:** rm leftover JSONs in `backend/config/*_profiles/` (test debris from before fixture isolation).

✅ **Acceptance:**
- `backend/config/asr_profiles/`, `backend/config/mt_profiles/`, `backend/config/pipelines/` are empty (or contain only intentional seed data)
- `backend/.coverage` removed if present
- `git status` clean for these paths

- [ ] **Step 1: Inspect glossaries dir**

```bash
ls backend/config/glossaries/  # check if any real user data is here
```

If only test debris: delete. If real glossaries: preserve.

- [ ] **Step 2: Delete debris**

```bash
rm -f backend/config/asr_profiles/*.json
rm -f backend/config/mt_profiles/*.json
rm -f backend/config/pipelines/*.json
rm -f backend/.coverage
```

> Note: these files are typically untracked. If any are tracked (`git ls-files`), `git rm` them instead.

- [ ] **Step 3: Commit (if any tracked deletions)**

```bash
git status
# If tracked files deleted:
git commit -m "chore(v4 A5): remove test pollution JSON debris from backend/config/"
```

---

## Task 12: Update CLAUDE.md

🎯 **Goal:** Document A5 completion. Remove stale references to legacy routes/code from the REST endpoint table. Refresh Architecture section.

✅ **Acceptance:**
- `### v4.0 A5` entry inserted above A4 entry
- REST endpoint table: remove all `/api/profiles*` rows + `/api/translate` row + adjust `/api/transcribe` note
- Repository Structure tree: `frontend.old/` removed; legacy backend Python modules removed
- Voice matches existing entries
- Single commit

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Steps**: similar to A3/A4 CLAUDE.md updates.

---

## Task 13: Final regression sweep + push

🎯 **Goal:** Confirm backend + frontend + Playwright are all green; push branch; report PR-ready state.

✅ **Acceptance:**
- `pytest tests/ -q` reports expected pass count (baseline minus deletions)
- `npm test -- --run` reports 180+ pass (some tests may have been moved/deleted)
- `npm run build` clean
- Branch pushed to origin
- Plan + spec + this final commit visible

- [ ] **Step 1: Run all suites + capture output**

- [ ] **Step 2: Push**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git push origin chore/asr-mt-rearchitecture-research
```

- [ ] **Step 3: Optional — open PR via `gh pr create` if user confirms**

User must approve before opening PR. Do not auto-open.

---

## Execution Handoff

Dispatch via `superpowers:subagent-driven-development`. **Critical**: each task is a DELETION-DRIVEN change that can cascade test failures. Subagents should:
1. Run tests BEFORE changes (baseline)
2. Make changes
3. Run tests AFTER (compare)
4. Document deleted tests in commit message
5. Escalate to user via DONE_WITH_CONCERNS if test count drops more than expected

Tasks are **sequential**: T2 must finish before T3 (frontend Proofread before frontend.old delete), and T4-T9 should run in order to avoid touching `app.py` from multiple subagents. T1 (baseline), T11 (pollution), T12 (docs), T13 (push) are independent of the deletion chain.
