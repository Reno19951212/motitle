# v4.0 Debug Branch — E2E Bug Hunt + Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Systematically discover, triage, and (in scope) fix bugs across v4.0 P1+A1+A3+A4+A5+A6 surface on a dedicated `debug/v4-e2e-bug-hunt` branch, with parallel-safe sub-tracker files, env-gated manual matrix, abort gate, and explicit decision ritual before any fix code lands.

**Architecture:** Four phases (0 Setup → 1 Discovery 4 tracks → 2 Triage → 3a Decision → 3b Fix). Phase 1 三條 track 由獨立 fresh subagent 並行跑、Track D 主 session 跑。每 track 寫獨立 sub-tracker file 避免 git conflict。Phase 3b 任務內容由 Phase 2 triage 結果決定，呢個 plan 喺 Phase 3a 之後 amend 加入 concrete fix task。

**Tech Stack:** Bash + git + pytest + Vitest + Playwright + npm + ffmpeg + Ollama + mlx-whisper（Track B 視 env 可用）。Subagent dispatch via Agent tool。Markdown tracker file（無 code framework）。

**Spec reference:** [docs/superpowers/specs/2026-05-18-v4-debug-e2e-design.md](../specs/2026-05-18-v4-debug-e2e-design.md) v2 @ commit `e773865`

---

## File Structure

新文件全部喺 `docs/superpowers/debug/`（新 directory）：

| File | 用途 | 寫者 |
|---|---|---|
| `v4-debug-baseline.md` | Phase 0 capture：pytest / build / vitest / tsc / playwright / TODO baseline | Phase 0 主 session |
| `v4-bug-tracker-trackA-playwright.md` | Track A finding | Track A subagent |
| `v4-bug-tracker-trackB-manual.md` | Track B finding | Track B subagent |
| `v4-bug-tracker-trackC-static.md` | Track C finding | Track C subagent |
| `v4-bug-tracker-trackD-known.md` | Track D finding | 主 session（Phase 1） |
| `v4-bug-tracker.md` | Master tracker（Phase 2 consolidate sub-tracker 入呢度） | Phase 2 主 session |
| `v4-e2e-matrix.md` | Track B manual checklist source-of-truth | Phase 0 主 session（template）+ Track B subagent（fill execution result） |
| `v4-phase3-decisions.md` | Phase 3a 每條 bug disposition record | Phase 3a 主 session |
| `v4-deferred-backlog.md` | 「Defer 入 backlog」bucket 嘅 finding 收集處 | Phase 2 + Phase 3a 主 session |

新 frontend file（Track A 用）：
- `frontend/tests-e2e/seed-e2e.sh` 或 `frontend/tests-e2e/global-setup.ts`（bootstrap fixture）

修改：
- `frontend/package.json` — 加 `test:e2e:seeded` script
- 視 Phase 3b decision，可能改 spec / production code

---

## Phase 0 — Setup（~45 min，6 task）

### Task 1: Cut debug branch from parent

**Files:**
- Modify: git working tree only

- [ ] **Step 1: Verify parent branch state**

```bash
git status
git rev-parse HEAD
```

Expected output: clean tree, HEAD on `chore/asr-mt-rearchitecture-research` at `e773865` 或更新（spec v2 commit）。

- [ ] **Step 2: Pull latest from origin**

```bash
git checkout chore/asr-mt-rearchitecture-research
git pull --ff-only
```

Expected: `Already up to date.` 或 fast-forward 成功。

- [ ] **Step 3: Cut debug branch**

```bash
git checkout -b debug/v4-e2e-bug-hunt
```

Expected: `Switched to a new branch 'debug/v4-e2e-bug-hunt'`

- [ ] **Step 4: Create debug doc directory**

```bash
mkdir -p docs/superpowers/debug
ls -la docs/superpowers/debug/
```

Expected: 空 directory 創建成功。

---

### Task 2: Capture backend baseline

**Files:**
- Create: `/tmp/baseline-pytest.log`

- [ ] **Step 1: Activate backend venv + run full pytest**

```bash
cd backend && source venv/bin/activate
pytest tests/ 2>&1 | tee /tmp/baseline-pytest.log
```

Expected: tail 顯示 `794 passed, 14 failed`（CLAUDE.md v4.0 A6 entry 確認過嘅 baseline）。如果 numbers 偏離（例如新增/減少），記低喺 Task 5。

- [ ] **Step 2: Extract failure list**

```bash
grep "FAILED" /tmp/baseline-pytest.log | head -20
```

Expected: 14 行 `FAILED tests/test_*.py::test_name` — 主要係 11 Playwright E2E + 1 v3.3 macOS tmpdir + 1 phase5 SocketIO CORS + 1 queue routes。

- [ ] **Step 3: Save summary to /tmp for Task 5 consolidation**

```bash
tail -50 /tmp/baseline-pytest.log > /tmp/baseline-pytest-summary.txt
```

Expected: 50 行 tail 包含 final summary line。

---

### Task 3: Capture frontend baseline

**Files:**
- Create: `/tmp/baseline-build.log`, `/tmp/baseline-vitest.log`, `/tmp/baseline-tsc.log`, `/tmp/baseline-pw.log`

- [ ] **Step 1: Frontend build**

```bash
cd frontend
npm run build 2>&1 | tee /tmp/baseline-build.log
```

Expected: 無 error，輸出顯示 main chunk ~31KB（gzip ~11KB）+ 8 page chunk + 7 vendor chunk + Vite 無 chunkSizeWarning。

- [ ] **Step 2: Vitest run**

```bash
cd frontend
npx vitest run 2>&1 | tee /tmp/baseline-vitest.log
```

Expected: tail 顯示 `Tests  184 passed` 跨 ~28 test file。

- [ ] **Step 3: TypeScript strict check**

```bash
cd frontend
npx tsc --noEmit 2>&1 | tee /tmp/baseline-tsc.log
```

Expected: clean（無輸出 = 0 error）。任何 error 入 Task 5 baseline doc 標 `pre-existing TS issue`。

- [ ] **Step 4: Playwright spec list**

```bash
cd frontend
npx playwright test --list 2>&1 | tee /tmp/baseline-pw.log
```

Expected: `Total: 14 tests in 11 files`（A6 C3 之後嘅 baseline）。

---

### Task 4: Capture TODO / FIXME baseline

**Files:**
- Create: `/tmp/baseline-todos.txt`

- [ ] **Step 1: Grep TODO/FIXME/XXX/HACK 全 codebase**

```bash
grep -rn "TODO\|FIXME\|XXX\|HACK\|defer to" backend/ frontend/src/ \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  | grep -v "node_modules\|\.test\.\|\.spec\." > /tmp/baseline-todos.txt
wc -l /tmp/baseline-todos.txt
```

Expected: 顯示 count（呢個係 baseline，Track D 將會逐條 review）。

- [ ] **Step 2: Quick categorize sample**

```bash
head -30 /tmp/baseline-todos.txt
```

Expected: 睇下有冇明顯 grouping（例如成堆 `# TODO: deprecate after vX`）— 純 informational，記 mental note，唔需要動作。

---

### Task 5: Write baseline summary doc

**Files:**
- Create: `docs/superpowers/debug/v4-debug-baseline.md`

- [ ] **Step 1: Write baseline doc**

Content：

```markdown
# v4.0 Debug — Baseline Capture

**Captured:** 2026-05-18
**Branch:** debug/v4-e2e-bug-hunt @ <git rev-parse HEAD short>
**Parent:** chore/asr-mt-rearchitecture-research @ e773865

## Backend (pytest)

- Pass: 794
- Fail: 14 (all pre-existing baseline)
- Total: 808

### Pre-existing baseline failures (14)

<paste from /tmp/baseline-pytest-summary.txt — 14 個 FAILED lines>

Known causes (per CLAUDE.md v4.0 A6 entry):
- 11 Playwright E2E specs require browser runtime
- 1 v3.3 macOS tmpdir colon-escape baseline
- 1 phase5_security SocketIO CORS regex
- 1 queue_routes per-user filter

## Frontend

### Build (npm run build)
- Status: clean
- Main chunk: 31KB raw / 11KB gz
- Vendor chunks: 7
- Page chunks: 8

### Vitest (npx vitest run)
- Pass: 184
- Files: 28

### TypeScript (npx tsc --noEmit)
- Status: clean (0 error)

### Playwright (npx playwright test --list)
- Specs: 11 files / 14 cases

## Static

### TODO/FIXME count
- Total lines: <wc output>

### Sample
<paste top 10 from /tmp/baseline-todos.txt>

## Notes

任何 Phase 1 discovery 揾到嘅 finding，先對比呢份 baseline 確定係 v4.0 引入定 pre-existing。
```

填寫實際數字，唔留 `<placeholder>`。

- [ ] **Step 2: Verify doc**

```bash
ls -la docs/superpowers/debug/v4-debug-baseline.md
wc -l docs/superpowers/debug/v4-debug-baseline.md
```

Expected: file exists, ~50 lines。

---

### Task 6: Initialize tracker + matrix template files

**Files:**
- Create: `docs/superpowers/debug/v4-bug-tracker-trackA-playwright.md`
- Create: `docs/superpowers/debug/v4-bug-tracker-trackB-manual.md`
- Create: `docs/superpowers/debug/v4-bug-tracker-trackC-static.md`
- Create: `docs/superpowers/debug/v4-bug-tracker-trackD-known.md`
- Create: `docs/superpowers/debug/v4-e2e-matrix.md`
- Create: `docs/superpowers/debug/v4-deferred-backlog.md`

- [ ] **Step 1: Write 4 sub-tracker templates**

每個 sub-tracker file 開頭加 header：

```markdown
# Bug Tracker — Track X (<Track Name>)

**Track:** A / B / C / D
**Owner:** <subagent ID or "main session">
**Start:** 2026-05-18
**Status:** In progress / Complete

---

## BUG-NNN: <短描述>
- **Status**: Open / In progress / Fixed / Wontfix / Deferred
- **Severity**: P0 / P1 / P2 / P3
- **A-phase origin**: P1 / A1 / A3 / A4 / A5 / A6 / cross-phase
- **Layer**: backend / frontend / E2E / docs / config / build
- **Discovery source**: Track A / B / C / D
- **Repro steps**: ...
- **Expected**: ...
- **Actual**: ...
- **Plan impact** (必選一個):
  - [ ] 純 bug fix（落入呢個 branch 即可）
  - [ ] Spec 假設錯（需更新原 A?-design.md，列明哪個 §）
  - [ ] 需開新 sub-phase（A7/A8）
  - [ ] Defer 入 backlog
  - [ ] Confirmed out-of-scope
- **Suggested fix**: <approach>
- **Linked commit**: (Phase 3b 填寫)

(repeat per bug)
```

- [ ] **Step 2: Write v4-e2e-matrix.md template**

按 spec §5.2 嘅 6 個 section 寫 checklist template（每 section 開頭列 prerequisite）：

```markdown
# v4.0 Debug — Manual E2E Matrix

每個 section 開頭列 prerequisite。環境唔具備就 mark `[N/A — missing <X>]` 入 Track B tracker，唔當失敗。

## Section 1: 真實 ASR
**Prerequisite:** M-series Mac + mlx-whisper medium model (~3GB downloaded)

- [ ] mlx-whisper medium 跑廣東話樣本
- [ ] mlx-whisper medium 跑英文樣本
- [ ] mlx-whisper medium 跑中英混合樣本
- [ ] 確認 cn_convert s2hk flag 真正 trigger
- [ ] 確認 merge_short_segments 唔產 1-word fragment
- [ ] 確認 initial_prompt bias decoder

## Section 2: 真實 MT — Ollama
**Prerequisite:** Local Ollama + qwen3.5-35b-a3b (~22GB) + 32GB+ RAM

- [ ] batch_size=1 single-segment mode
- [ ] batch_size=10 batched mode
- [ ] parallel_batches=4
- [ ] prompt_overrides 真正 inject 入 LLM payload
- [ ] translation_passes=2 enrich pass trigger

## Section 3: 真實 MT — OpenRouter
**Prerequisite:** OPENROUTER_API_KEY env + paid credit

- [ ] claude-sonnet-4-5
- [ ] gpt-4o-mini
- [ ] custom model id 自訂 input

## Section 4: 真實 FFmpeg render
**Prerequisite:** FFmpeg installed + 30s test MP4 + 5GB free disk

- [ ] MP4 CRF mode + ffprobe metadata check
- [ ] MP4 CBR mode + ffprobe check
- [ ] MP4 2-pass mode + ffprobe check
- [ ] MXF ProRes profile 0 (Proxy)
- [ ] MXF ProRes profile 1 (LT)
- [ ] MXF ProRes profile 2 (Standard)
- [ ] MXF ProRes profile 3 (HQ)
- [ ] MXF ProRes profile 4 (4444)
- [ ] MXF ProRes profile 5 (4444 XQ)
- [ ] XDCAM HD 422 @ 10 Mbps
- [ ] XDCAM HD 422 @ 50 Mbps
- [ ] XDCAM HD 422 @ 100 Mbps

## Section 5: WebSocket reliability
**Prerequisite:** Chromium DevTools available

- [ ] Pipeline 中段 network throttle → progress event 保留
- [ ] Kill backend server 中途 → frontend 顯示 disconnected
- [ ] 刷新 page 中途 → 重連後 state restore
- [ ] WebSocket reconnect dedupe（spec §8 hypothesis）

## Section 6: Bundle code-split runtime
**Prerequisite:** npm run build + serve dist available

- [ ] First paint 只 load entry + vendor-react + Login chunk
- [ ] Navigate /pipelines → vendor-dnd lazy load
- [ ] Slow 3G throttle → PageLoader fallback 顯示 OK

## Section 7: Structured logging
**Prerequisite:** Backend runnable + full pipeline E2E

- [ ] LOG_JSON=1 LOG_LEVEL=DEBUG → JSON 輸出
- [ ] X-Request-ID 由 inbound HTTP → log line → 子 thread 都貫穿
- [ ] ApiError exception → JSON 422/4XX 而非 HTML 500
```

- [ ] **Step 3: Write v4-deferred-backlog.md template**

```markdown
# v4.0 Debug — Deferred Backlog

Findings marked `Defer 入 backlog` 或 `Confirmed out-of-scope` 收集處。

## Format

每條一個 H2，list source tracker BUG-NNN，原因 + future action。

## Entries

(Phase 2 + Phase 3a 填入)
```

- [ ] **Step 4: Commit Phase 0 artifacts**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add docs/superpowers/debug/
git status
git commit -m "$(cat <<'EOF'
docs(v4 debug): Phase 0 setup - baseline + tracker templates

- v4-debug-baseline.md: pytest 794/14, frontend build/vitest/tsc/pw clean,
  TODO/FIXME baseline count
- v4-bug-tracker-{A,B,C,D}.md: empty templates per track
- v4-e2e-matrix.md: manual checklist with env prerequisites per section
- v4-deferred-backlog.md: empty backlog
EOF
)"
```

Expected: 1 commit, 6 new file。

---

## Phase 1 — Discovery（4 並行 track，每條獨立 subagent / 主 session）

### Task 7: Dispatch Track A subagent — Playwright suite expansion

**Files:**
- Modify (by subagent): `frontend/package.json` (add `test:e2e:seeded` script)
- Create (by subagent): `frontend/tests-e2e/global-setup.ts` 或 `frontend/tests-e2e/seed-e2e.sh`
- Create (by subagent): 6 個新 Playwright spec file
- Modify (by subagent): 既有 spec file（replace `test.skip` with `requireSeedOrSkip()` helper）
- Update (by subagent): `docs/superpowers/debug/v4-bug-tracker-trackA-playwright.md`

- [ ] **Step 1: Read existing Playwright suite to understand pattern**

```bash
ls frontend/tests-e2e/
cat frontend/tests-e2e/auth.spec.ts | head -30
cat frontend/tests-e2e/dashboard.spec.ts | head -30
cat frontend/playwright.config.ts 2>/dev/null || cat frontend/playwright.config.js 2>/dev/null
```

Expected: 10 spec file，全部 import pattern + base URL config 確認。

- [ ] **Step 2: Dispatch Track A subagent**

Use Agent tool with `subagent_type: "general-purpose"`. Prompt:

```
You are the Track A subagent for v4.0 debug branch E2E bug hunt.

SCOPE: Playwright suite expansion + bug discovery.

SPEC REFERENCE: docs/superpowers/specs/2026-05-18-v4-debug-e2e-design.md §5.1

YOUR DELIVERABLES:
1. Write frontend/tests-e2e/global-setup.ts that bootstraps:
   - Admin user "e2e-admin" / "TestPass1!" (idempotent — if exists, skip create)
   - 1 ASR profile (any valid config)
   - 1 MT profile (engine=mock, model=any)
   - 1 Glossary (1 entry, source_lang=en, target_lang=zh)
   - 1 Pipeline referencing the above ASR/MT/Glossary
   Uses fetch() against http://localhost:5001/api/* with admin session.

2. Update frontend/package.json:
   - Existing "test:e2e" script: keep current behavior (graceful skip allowed)
   - New "test:e2e:seeded" script: "E2E_REQUIRE_SEED=1 playwright test --global-setup=./tests-e2e/global-setup.ts"

3. Refactor existing test.skip patterns in 10 existing spec files:
   - Replace bare test.skip with helper requireSeedOrSkip()
   - Helper reads E2E_REQUIRE_SEED env: if true, throw Error (hard fail); if false/unset, test.skip()
   - Helper file: frontend/tests-e2e/helpers.ts

4. Write 6 new spec files (prioritized by spec §8 hypothesis):
   a. proofread-stage-rerun.spec.ts — edit segment → rerun stage → stage history sidebar updates
   b. proofread-prompt-override.spec.ts — save override → re-translate → new prompt visible in stage history
   c. pipeline-broken-refs.spec.ts — delete ASR profile → pipeline shows broken_refs badge
   d. multi-user-isolation.spec.ts — user A uploads file, user B login can't see it
   e. cancel-running-job.spec.ts — long pipeline → click cancel → UI shows cancelling → status=cancelled
   f. happy-path-pipeline.spec.ts — upload → pipeline_run → ASR done → MT done → glossary scan → render

5. Run npm run test:e2e:seeded locally (you have access).
   - Backend must be running on localhost:5001
   - If you can't start backend, document blocker in tracker and skip execution

6. For EACH bug discovered (test fails revealing real issue, not flaky test),
   add a BUG-NNN entry to docs/superpowers/debug/v4-bug-tracker-trackA-playwright.md
   using the schema in the existing template.

CONSTRAINTS:
- DO NOT modify any backend code
- DO NOT modify any frontend production code (only tests-e2e/ + package.json)
- DO NOT fix any bugs found — only log them in tracker
- If a test reveals a bug, mark the test .skip with comment "// Skipped: BUG-NNN" and continue

REPORT BACK:
- How many new spec files created
- How many test cases pass / fail / skip in test:e2e:seeded
- How many BUG-NNN entries logged
- Any blockers (e.g., backend not runnable)
```

Wait for subagent to complete. Read returned report.

- [ ] **Step 3: Spot-check Track A subagent output**

```bash
ls frontend/tests-e2e/
cat docs/superpowers/debug/v4-bug-tracker-trackA-playwright.md | head -100
git status
```

Expected: 6 new spec file + global-setup.ts + helpers.ts + package.json modified. Tracker file populated.

- [ ] **Step 4: Commit Track A artifacts**

```bash
git add frontend/tests-e2e/ frontend/package.json docs/superpowers/debug/v4-bug-tracker-trackA-playwright.md
git commit -m "$(cat <<'EOF'
test(v4 debug Track A): Playwright suite expansion + seed bootstrap

Per docs/superpowers/specs/2026-05-18-v4-debug-e2e-design.md §5.1.

- global-setup.ts: bootstrap e2e-admin + 1 ASR/MT profile + glossary + pipeline
- package.json: new test:e2e:seeded script (hard fail) alongside test:e2e (graceful skip)
- helpers.ts: requireSeedOrSkip() reads E2E_REQUIRE_SEED env
- 6 new spec files: proofread-stage-rerun, proofread-prompt-override,
  pipeline-broken-refs, multi-user-isolation, cancel-running-job,
  happy-path-pipeline
- v4-bug-tracker-trackA-playwright.md: <N> BUG entries logged
EOF
)"
```

Expected: 1 commit。

---

### Task 8: Dispatch Track B subagent — Manual E2E matrix

**Files:**
- Update (by subagent): `docs/superpowers/debug/v4-e2e-matrix.md` (mark checklist items pass/fail/N/A)
- Update (by subagent): `docs/superpowers/debug/v4-bug-tracker-trackB-manual.md`

- [ ] **Step 1: Pre-check environment availability**

```bash
which ffmpeg
which ffprobe
ls -la ~/.cache/mlx-whisper/ 2>/dev/null || echo "no mlx-whisper cache"
curl -s http://localhost:11434/api/tags 2>/dev/null || echo "no Ollama"
echo "OPENROUTER_API_KEY set: ${OPENROUTER_API_KEY:+yes}${OPENROUTER_API_KEY:-no}"
ls -la /tmp/test-video*.mp4 2>/dev/null || echo "no test video"
df -h | head -2
```

Expected: 列出咩 prerequisite 有 / 冇。如果好多 prerequisite 都唔具備，Track B 大部分 section 會 `[N/A]`，提早確認預期。

- [ ] **Step 2: Dispatch Track B subagent**

Use Agent tool with `subagent_type: "general-purpose"`. Prompt:

```
You are the Track B subagent for v4.0 debug branch E2E bug hunt.

SCOPE: Manual matrix execution — real ASR / MT / FFmpeg / WebSocket / bundle / logging.

SPEC REFERENCE: docs/superpowers/specs/2026-05-18-v4-debug-e2e-design.md §5.2

MATRIX FILE: docs/superpowers/debug/v4-e2e-matrix.md (7 sections, each with prerequisites)

YOUR APPROACH:
For each section:
1. Check prerequisites listed at section top
2. If any prereq missing: mark every checklist item in that section as
   [N/A — missing <X>] in the matrix file, log a single tracker entry
   noting which section was skipped + which prereq missing, MOVE ON
3. If prereq satisfied: execute each checklist item one by one
   - PASS: mark checkbox checked in matrix file
   - FAIL (real bug): mark checkbox with [FAIL — see BUG-NNN], log full
     BUG entry to v4-bug-tracker-trackB-manual.md with repro steps + expected vs actual
   - Inconclusive: mark [INCONCLUSIVE — <reason>], log lightweight tracker note

ENVIRONMENT PROBE (run first):
- mlx-whisper: check if M-series Mac + model downloaded
- Ollama qwen3.5-35b-a3b: curl http://localhost:11434/api/tags
- OpenRouter: check $OPENROUTER_API_KEY env
- FFmpeg + ffprobe: check which
- Test video: check /tmp/test-video*.mp4 or ask if user has one
- 5GB free disk: df -h

OUTPUT:
1. docs/superpowers/debug/v4-e2e-matrix.md updated with PASS/FAIL/N/A per item
2. docs/superpowers/debug/v4-bug-tracker-trackB-manual.md with BUG entries

CONSTRAINTS:
- DO NOT modify any production code
- DO NOT fix bugs found
- Real model inference is expensive — be efficient, don't re-run sections
  that already passed
- If backend / Ollama / etc. need to be started, you can start them
  but document any startup blocker

REPORT BACK:
- Section-by-section status: PASS / FAIL / N/A count
- Total BUG-NNN entries logged
- Total time spent
- Any unresolvable blocker
```

Wait for subagent to complete. Read returned report.

- [ ] **Step 3: Verify Track B output**

```bash
grep -c "BUG-" docs/superpowers/debug/v4-bug-tracker-trackB-manual.md
grep -c "\[N/A\|\[FAIL\|\[ \]" docs/superpowers/debug/v4-e2e-matrix.md
```

Expected: BUG count + matrix status confirmed.

- [ ] **Step 4: Commit Track B artifacts**

```bash
git add docs/superpowers/debug/v4-e2e-matrix.md docs/superpowers/debug/v4-bug-tracker-trackB-manual.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Track B): manual E2E matrix execution + findings

Per spec §5.2. Env-gated checklist: ASR/MT/FFmpeg/WebSocket/bundle/logging.

- v4-e2e-matrix.md: <X> PASS / <Y> FAIL / <Z> N/A
- v4-bug-tracker-trackB-manual.md: <N> BUG entries logged
- Env summary: <list of which sections N/A and why>
EOF
)"
```

Expected: 1 commit.

---

### Task 9: Dispatch Track C subagent — Static analysis

**Files:**
- Update (by subagent): `docs/superpowers/debug/v4-bug-tracker-trackC-static.md`

- [ ] **Step 1: Dispatch Track C subagent**

Use Agent tool with `subagent_type: "Explore"` (read-only search agent fit for this). Prompt:

```
You are the Track C subagent for v4.0 debug branch E2E bug hunt.

SCOPE: Static analysis — dead reference, type error, lint warning.
NOT included: vulture / ts-prune (false-positive too high per spec §5.3).

SPEC REFERENCE: docs/superpowers/specs/2026-05-18-v4-debug-e2e-design.md §5.3

EXECUTE these greps (note exact commands, save outputs to /tmp/track-c-*.txt):

1. Dead references to A5-deleted modules:
   grep -rn "from translation.alignment_pipeline" backend/
   grep -rn "from translation.sentence_pipeline" backend/
   grep -rn "from translation.post_processor" backend/
   grep -rn "from profiles import" backend/
   grep -rn "_auto_translate\|transcribe_with_segments\|_asr_handler\|_mt_handler" backend/

2. Frontend legacy residue:
   grep -rn "frontend.old" .
   grep -rn "useActiveProfile" frontend/src/

3. TypeScript strict:
   cd frontend && npx tsc --noEmit 2>&1

4. Frontend lint:
   cd frontend && npm run lint 2>&1 || true

EXPECTED outputs:
- (1) ALL 5 greps should return ZERO matches (A5 cleanup invariant).
  Any match = dead reference = BUG entry
- (2) ALL 2 greps zero matches. Any match = BUG entry
- (3) Clean per baseline. Any error = BUG entry
- (4) Per baseline. Any new lint error = BUG entry

For EACH unexpected finding:
- Log BUG entry to docs/superpowers/debug/v4-bug-tracker-trackC-static.md
- Include exact grep / tsc / lint output line as repro
- Mark severity tentatively (will be triaged in Phase 2)

CONSTRAINTS:
- DO NOT modify any code
- DO NOT fix anything
- ONLY surface findings

REPORT BACK:
- Dead reference grep: count per pattern (expected 0 each)
- Frontend residue grep: count per pattern (expected 0 each)
- tsc error count
- lint warning/error count
- Total BUG-NNN entries logged
```

Wait for subagent. Read returned report.

- [ ] **Step 2: Verify Track C output**

```bash
cat docs/superpowers/debug/v4-bug-tracker-trackC-static.md | head -100
grep -c "BUG-" docs/superpowers/debug/v4-bug-tracker-trackC-static.md
```

- [ ] **Step 3: Commit Track C**

```bash
git add docs/superpowers/debug/v4-bug-tracker-trackC-static.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Track C): static analysis findings

Per spec §5.3 (surgical grep only, vulture/ts-prune excluded).

- Dead reference greps: <total findings>
- Frontend legacy residue greps: <total findings>
- tsc errors: <count>
- Lint errors/warnings: <count>
- v4-bug-tracker-trackC-static.md: <N> BUG entries logged
EOF
)"
```

Expected: 1 commit.

---

### Task 10: Execute Track D — Known-issue harvest (主 session)

**Files:**
- Update: `docs/superpowers/debug/v4-bug-tracker-trackD-known.md`

主 session 跑（唔 dispatch subagent — context 已有 CLAUDE.md + 全 history，effective 半小時就完）。

- [ ] **Step 1: Harvest from TODO/FIXME grep**

```bash
cat /tmp/baseline-todos.txt
```

逐行 review。每條判斷：
- Actionable TODO 仍未做 → BUG entry
- 已過時 / 已做但 comment 冇 update → BUG entry (severity P3)
- 純設計 note 唔需要 action → 跳

- [ ] **Step 2: Harvest from CLAUDE.md out-of-scope section**

Open `CLAUDE.md`，jump 去每個 v4.0 phase entry 嘅末段「Out-of-scope」/「Out-of-A?」section：
- v4.0 A3 (in `### v4.0 A3` section)
- v4.0 A4 (in `### v4.0 A4`)
- v4.0 A5 (in `### v4.0 A5`)
- v4.0 A6 (in `### v4.0 A6`)

逐條 item 評估：仍係 out-of-scope (log `Confirmed out-of-scope`) vs 實際 v4.0 surface bug (升 active finding)。

- [ ] **Step 3: Harvest from recent commit message**

```bash
git log --since="2026-05-15" --all --oneline | head -100
git log --since="2026-05-15" --all --grep="TODO\|FIXME\|defer\|known issue\|留將來\|out-of-scope" --oneline
```

逐條 commit subject 評估。

- [ ] **Step 4: Add v4.0 backlog item 入 tracker**

Per spec §10，明確 confirmed-out-of-scope 嘅 list（StreamingSession / Mac/Win 打包 / mobile responsive / i18n / Storybook / CI/CD）— 每條一個 entry，全部 `Confirmed out-of-scope` bucket，提供 audit trail。

- [ ] **Step 5: Save tracker doc**

每條 finding 用 schema 寫入 `docs/superpowers/debug/v4-bug-tracker-trackD-known.md`，最少包括：
- Source 1: TODO/FIXME 全部 listed
- Source 2: CLAUDE.md out-of-scope item 各一 entry
- Source 3: 任何 commit-level 已知問題
- Source 4: v4.0 backlog item 6 條

- [ ] **Step 6: Commit Track D**

```bash
git add docs/superpowers/debug/v4-bug-tracker-trackD-known.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Track D): known-issue harvest

Per spec §5.4. Main session execution (no subagent).

Sources:
- TODO/FIXME grep: <count> actionable entries
- CLAUDE.md out-of-scope sections: <count> entries (A3/A4/A5/A6)
- Recent commit messages: <count> escape-hatch wording
- v4.0 backlog items (Streaming, packaging, mobile, i18n, Storybook, CI/CD): 6

Total: <N> BUG entries logged. Majority marked Confirmed out-of-scope
to provide audit trail and prevent Phase 1 re-discovery.
EOF
)"
```

Expected: 1 commit.

---

## Phase 2 — Triage（~1 hr，3 task）

### Task 11: Consolidate 4 sub-tracker → master tracker

**Files:**
- Create: `docs/superpowers/debug/v4-bug-tracker.md`

- [ ] **Step 1: Read all 4 sub-trackers**

```bash
wc -l docs/superpowers/debug/v4-bug-tracker-track*.md
grep -c "## BUG-" docs/superpowers/debug/v4-bug-tracker-track*.md
```

Expected: 各 sub-tracker BUG count。

- [ ] **Step 2: Write master tracker template**

```markdown
# v4.0 Debug — Master Bug Tracker

**Consolidated:** 2026-05-18
**Sources:** Track A (Playwright) + Track B (Manual) + Track C (Static) + Track D (Known)

## Summary table

| BUG ID | Source | Severity | A-phase | Plan impact | Status |
|---|---|---|---|---|---|
| BUG-001 | A | P0 | A4 | 純 bug fix | Open |
| ... | | | | | |

## Entries

(逐條 paste 入面，按 BUG-NNN sequence renumber)
```

- [ ] **Step 3: Consolidate entries with de-dup**

逐個 sub-tracker 過：
- 將每條 BUG entry copy 入 master
- 重新 number BUG-NNN（從 1 開始順序）
- 同一條 bug 喺多 track 出現嘅情況：合併做一 entry，`Discovery source` field list 多個 track
- 填寫 summary table

- [ ] **Step 4: Verify consolidation completeness**

```bash
total_in_subs=$(grep -c "## BUG-" docs/superpowers/debug/v4-bug-tracker-track*.md | awk -F: '{s+=$2} END {print s}')
total_in_master=$(grep -c "^## BUG-" docs/superpowers/debug/v4-bug-tracker.md)
echo "Sub-tracker total: $total_in_subs"
echo "Master total: $total_in_master (after de-dup)"
```

Expected: master count ≤ sub-tracker sum（duplicate 已合併）。

- [ ] **Step 5: Commit master tracker**

```bash
git add docs/superpowers/debug/v4-bug-tracker.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Phase 2): consolidate 4 sub-trackers into master

Per spec §6.

Sources:
- Track A: <X> entries
- Track B: <Y> entries
- Track C: <Z> entries
- Track D: <W> entries

After de-dup: <N> unique BUG-NNN in master tracker.
EOF
)"
```

Expected: 1 commit.

---

### Task 12: Triage each finding (severity + plan impact)

**Files:**
- Modify: `docs/superpowers/debug/v4-bug-tracker.md`

- [ ] **Step 1: Set up triage criteria reference**

開另一 terminal / 副本 spec §6 嘅 P0-P3 table + 5 個 plan impact bucket reference。

- [ ] **Step 2: Triage each BUG entry**

逐條 master tracker BUG，喺 entry 入面填齊：
- `Severity`: P0 / P1 / P2 / P3 per criteria
- `Plan impact`: 揀一個 5 個 bucket
- `Suggested fix`: 一句 actionable approach

P0 標準（spec §6 table）：
1. 完全 crash / 主流程行唔通
2. Auth bypass / privilege escalation
3. Silent data corruption (status=success 但 output 錯)
4. Cross-user 數據洩漏
5. 工作成果不可恢復

如果同一條 bug 同時觸發多個 P0 criteria，仍係 P0（無「P-1」級別）。

- [ ] **Step 3: Update summary table at top**

逐條 entry update 完，head section 嘅 summary table fill 齊。

- [ ] **Step 4: Move Confirmed out-of-scope / Defer entries to backlog**

```bash
grep -B1 "Confirmed out-of-scope\|Defer 入 backlog" docs/superpowers/debug/v4-bug-tracker.md | grep "## BUG"
```

每條 marked confirmed-out-of-scope / deferred 嘅 entry，shorten 入 `docs/superpowers/debug/v4-deferred-backlog.md`（保留 BUG-NNN + 短 summary，full detail 留喺 master tracker），master tracker 入面留 stub 指返 backlog。

- [ ] **Step 5: Commit triage**

```bash
git add docs/superpowers/debug/v4-bug-tracker.md docs/superpowers/debug/v4-deferred-backlog.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Phase 2): triage all findings

Per spec §6.

Severity breakdown:
- P0: <count>
- P1: <count>
- P2: <count>
- P3: <count>

Plan impact breakdown:
- 純 bug fix: <count>
- Spec 假設錯: <count>
- 需開新 sub-phase: <count>
- Defer 入 backlog: <count>
- Confirmed out-of-scope: <count>
EOF
)"
```

Expected: 1 commit.

---

### Task 13: Evaluate abort gate (P0 count > 5?)

**Files:**
- Create: `docs/superpowers/debug/v4-phase2-report.md`

- [ ] **Step 1: Count P0**

```bash
p0_count=$(grep -A2 "## BUG-" docs/superpowers/debug/v4-bug-tracker.md | grep -c "Severity.*P0")
echo "P0 count: $p0_count"
```

- [ ] **Step 2: Write Phase 2 report**

`docs/superpowers/debug/v4-phase2-report.md` content：

```markdown
# v4.0 Debug — Phase 2 Triage Report

**Date:** 2026-05-18
**Branch:** debug/v4-e2e-bug-hunt

## Summary

| Severity | Count |
|---|---|
| P0 | <n0> |
| P1 | <n1> |
| P2 | <n2> |
| P3 | <n3> |
| **Total** | <total> |

| Plan impact | Count |
|---|---|
| 純 bug fix | <a> |
| Spec 假設錯 | <b> |
| 需開新 sub-phase | <c> |
| Defer 入 backlog | <d> |
| Confirmed out-of-scope | <e> |

## Abort gate evaluation

P0 count: <n0>
Threshold (spec §6): 5

**Decision required from user:**
- If P0 ≤ 5: proceed Phase 3a normally
- If P0 > 5: pause Phase 3a, user must choose:
  (a) continue Phase 3b fix-all
  (b) freeze v4.0 ship, rewrite affected phase
  (c) escalate part of P0 to new sub-phase (A7/A8)

## Top findings (preview)

(Top 5 P0 BUG-NNN with one-line summary，畀 user 一眼 read)

## Phase 1 effort

- Track A: <hours>
- Track B: <hours, mark how many sections N/A>
- Track C: <hours>
- Track D: <hours>

## Recommended Phase 3a focus

(Based on Severity x Plan impact crosstab, list which buckets need user
attention first)
```

- [ ] **Step 3: Commit Phase 2 report**

```bash
git add docs/superpowers/debug/v4-phase2-report.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Phase 2): triage report + abort gate evaluation

P0 count: <n0> (threshold 5)
Total findings: <total>

Decision required from user in Phase 3a.
EOF
)"
```

Expected: 1 commit.

---

## Phase 3a — Decision gate（~1 session，2 task）

### Task 14: Present Phase 2 report to user, collect decisions

**Files:**
- Create: `docs/superpowers/debug/v4-phase3-decisions.md`

- [ ] **Step 1: Surface Phase 2 report to user**

主 session 對 user 講：
- Phase 1 完成，Phase 2 triage done
- 引 v4-phase2-report.md
- 強調 P0 count vs abort threshold
- 列 top 10 finding (P0 first，descending by severity)

- [ ] **Step 2: Per-bug disposition with user**

Walk through 每條 P0 + P1 (P2/P3 batch confirm)，user 決定：
- 純 bug fix → 入 Phase 3b fix list
- Spec 假設錯 → 列出要 patch 嘅 spec doc + section
- 需開新 sub-phase → record 新 sub-phase name + scope
- Defer / out-of-scope → confirm 入 backlog

- [ ] **Step 3: Branch close target — baseline 或 ambitious**

Per spec §11，user 揀：
- **Baseline**：P0 100% + P1 ≥50% close
- **Ambitious**：P0 + P1 100% + P2 budget

如果 ambitious，user 設 P2 budget（例如 1 session / 3 bug count）。

- [ ] **Step 4: Write decisions doc**

```markdown
# v4.0 Debug — Phase 3a Decisions

**Date:** 2026-05-18
**User:** Reno
**Branch close target:** Baseline / Ambitious

## Per-bug disposition

| BUG ID | Severity | Decision | Notes |
|---|---|---|---|
| BUG-001 | P0 | Fix in Phase 3b | ... |
| BUG-002 | P0 | Spec update (A4 §3.2) | ... |
| BUG-003 | P1 | New sub-phase A7 | ... |
| ... | | | |

## Phase 3b scope

- Fix list: BUG-NNN, BUG-NNN, ...
- Spec update list: <files + sections>
- New sub-phase list: <names>
- Deferred (no Phase 3b action): <BUG-NNN>

## Estimated Phase 3b effort

<best estimate based on bug complexity>

## Sign-off

- [ ] User has reviewed
- [ ] User has approved Phase 3b scope
- [ ] User has set P2 budget (if ambitious)
```

- [ ] **Step 5: Commit decisions**

```bash
git add docs/superpowers/debug/v4-phase3-decisions.md
git commit -m "$(cat <<'EOF'
docs(v4 debug Phase 3a): decision gate — Phase 3b scope locked

Per spec §11.

- Branch close target: <baseline/ambitious>
- Phase 3b fix list: <N> bugs
- Spec update list: <M> spec docs
- New sub-phase list: <P> phases
- Deferred: <Q> bugs
EOF
)"
```

Expected: 1 commit.

---

### Task 15: Amend this plan with concrete Phase 3b tasks

**Files:**
- Modify: `docs/superpowers/plans/2026-05-18-v4-debug-e2e-plan.md`（即係呢個 plan 本身）

- [ ] **Step 1: Per amendment policy (spec §12)**

呢個係 minor scope tweak（基於 Phase 3a 嘅 decision 加入 Phase 3b 具體 task）— inline 改加 `### Updated 2026-05-XX: Phase 3b task list per Phase 3a decisions` header。

- [ ] **Step 2: Add Phase 3b tasks**

Per Phase 3a decisions doc，逐條 fix bug 寫 Task N：

```markdown
### Task 16: Fix BUG-NNN — <short title>

**Files:**
- (per BUG entry's "Suggested fix")

- [ ] Step 1: Read related spec / existing code
- [ ] Step 2: Write failing test (TDD)
- [ ] Step 3: Run test to verify fail
- [ ] Step 4: Implement fix
- [ ] Step 5: Run test to verify pass
- [ ] Step 6: Run related test suite for regression
- [ ] Step 7: Update BUG-NNN tracker entry Status=Fixed + Linked commit SHA
- [ ] Step 8: Commit (message: `fix(v4 debug): <title>\n\nFixes: BUG-NNN`)
```

每條 spec update bug 寫：

```markdown
### Task N: Spec update for BUG-NNN — <short title>

**Files:**
- Modify: docs/superpowers/specs/2026-05-17-v4-A?-design.md

- [ ] Step 1: Open spec, locate § identified in BUG entry
- [ ] Step 2: Add `### Updated 2026-05-XX: <reason> (BUG-NNN)` header
- [ ] Step 3: Update section content
- [ ] Step 4: Update BUG-NNN tracker Status=Fixed
- [ ] Step 5: Commit (`docs(v4 debug): spec update for BUG-NNN`)
```

每條新 sub-phase bug 寫 task 跳出呢條 branch，行返 brainstorming + writing-plans flow。

- [ ] **Step 3: Update plan task list at top**

呢個 plan 結尾原本只去到 Task 15。Amendment 之後 task count 變 15 + N。Update 文件 header 嘅 task count 提示（呢個 plan 嘅 「Task structure」section）。

- [ ] **Step 4: Commit plan amendment**

```bash
git add docs/superpowers/plans/2026-05-18-v4-debug-e2e-plan.md
git commit -m "$(cat <<'EOF'
docs(v4 debug): plan amendment - Phase 3b concrete tasks

Per spec §12 (minor scope tweak inline amendment).

Added <N> Phase 3b tasks per v4-phase3-decisions.md:
- <X> fix tasks
- <Y> spec update tasks
- <Z> new sub-phase scaffold tasks
EOF
)"
```

Expected: 1 commit. 之後 executing-plans / subagent-driven-development 接住跑 Phase 3b。

---

## Phase 3b — Targeted fix（Phase 3a 之後 amend，呢度只係 placeholder）

> **NOTE:** Phase 3b 嘅具體 task 內容由 Phase 2 triage 結果決定。Task 15 完成之後呢個 section 會有 Task 16+ 嘅具體 fix task。Phase 3b 開始之前唔可以預先估個數量。

### Task 16+: TBD pending Phase 2 + 3a

由 Task 15 amend 入。

---

## Completion criteria

呢個 plan 嘅 baseline completion：
- Task 1-15 全部完成
- Master tracker triage complete
- Phase 3a decisions sign off
- Plan amendment for Phase 3b

Plan 嘅 ambitious completion：
- 上面 + Task 16+ 全部完成
- Branch ready to merge 返 chore/asr-mt-rearchitecture-research

每個 fix commit message 包含 `Fixes: BUG-NNN`，tracker entry update `Linked commit` field。

---

## Self-review notes

✅ Spec §1 (目標) → Phase 0-3b 全 cover
✅ Spec §3 (4-phase architecture) → Task 1 (Phase 0 cut + dir) ... Task 13 (Phase 2 abort gate)
✅ Spec §4.2 (baseline capture) → Task 2-5
✅ Spec §4.3 (per-track sub-tracker) → Task 6 Step 1
✅ Spec §4.4 (matrix doc) → Task 6 Step 2
✅ Spec §5.1 (Track A dual script) → Task 7
✅ Spec §5.2 (Track B env-gated) → Task 8 Step 1 pre-check + Step 2 subagent prompt
✅ Spec §5.3 (Track C surgical greps only) → Task 9
✅ Spec §5.4 (Track D harvest) → Task 10
✅ Spec §6 (Phase 2 triage + abort gate) → Task 11-13
✅ Spec §11.1 / §11.2 (branch close baseline/ambitious) → Task 14 Step 3
✅ Spec §12 (amendment policy) → Task 15 Step 1
✅ Spec §6 (Confirmed out-of-scope bucket) → Task 6 Step 1 schema + Task 12 Step 4

Type consistency:
- BUG-NNN naming convention consistent across tasks
- Tracker file path consistent (`docs/superpowers/debug/...`)
- Branch name `debug/v4-e2e-bug-hunt` consistent
- Commit message prefix `docs(v4 debug Phase X)` / `fix(v4 debug)` consistent
