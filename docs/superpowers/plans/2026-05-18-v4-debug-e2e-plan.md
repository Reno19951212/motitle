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

## Phase 3b — Targeted fix

### Updated 2026-05-18: Phase 3b task list per Phase 3a decisions (BUG triage + Ambitious close target + Real E2E inline)

Phase 2 triage outcome: 0 P0 / 0 P1 / 8 P2 / 20 P3. Phase 3a user decision: Ambitious close (P2 100% + 純 bug fix P3 100%) + Real E2E inline.

**17 actionable Phase 3b items** sorted by group dependency:

---

### Task 16: BUG-001 — Add test fixture media file

**Files:**
- Create: `frontend/tests-e2e/fixtures/sample.mp3`
- Modify: `frontend/.gitignore` (if needed, ensure fixtures/ not excluded)

- [ ] **Step 1: Generate 5-second silent MP3**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
mkdir -p frontend/tests-e2e/fixtures
ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 5 -q:a 9 -acodec libmp3lame frontend/tests-e2e/fixtures/sample.mp3
ls -la frontend/tests-e2e/fixtures/sample.mp3
```

Expected: file ~10-30 KB created.

- [ ] **Step 2: Verify .gitignore does not exclude it**

```bash
cd frontend
cat .gitignore | grep -i "fixture\|\.mp3\|\.mp4"
```

If excluded, add explicit allow: `!tests-e2e/fixtures/*.mp3` (or remove the over-broad exclusion).

- [ ] **Step 3: Update tracker entry**

Edit `docs/superpowers/debug/v4-bug-tracker.md` BUG-001 summary table row: `Status: Open → Fixed`. Add Linked commit SHA after Step 4.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests-e2e/fixtures/sample.mp3 docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): add test fixture media file

Fixes: BUG-001"
```

---

### Task 17: BUG-002 — global-setup.ts seed idempotency

**Files:**
- Modify: `frontend/tests-e2e/global-setup.ts`

- [ ] **Step 1: Read existing global-setup.ts**

```bash
cat frontend/tests-e2e/global-setup.ts
```

Identify where `seedPost()` is called for each entity (ASR / MT / Glossary / Pipeline) and where 409 is currently swallowed silently.

- [ ] **Step 2: Add getOrCreate helper**

Add helper function (use Edit tool on existing global-setup.ts):

```typescript
async function getOrCreate(
  listPath: string,
  matchKey: 'name' | 'title',
  matchValue: string,
  createBody: Record<string, unknown>,
  cookie: string
): Promise<string | null> {
  // Try POST first
  const postRes = await fetch(`${BASE_URL}${listPath}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Cookie': cookie },
    body: JSON.stringify(createBody),
  });
  if (postRes.ok) {
    const data = await postRes.json();
    return data.id ?? null;
  }
  if (postRes.status === 409) {
    // GET the list and find the existing entry by name
    const listRes = await fetch(`${BASE_URL}${listPath}`, {
      headers: { 'Cookie': cookie },
    });
    if (!listRes.ok) return null;
    const list = await listRes.json() as Array<Record<string, unknown>>;
    const found = list.find((e) => e[matchKey] === matchValue);
    return (found?.id as string) ?? null;
  }
  return null;
}
```

- [ ] **Step 3: Replace existing seedPost calls with getOrCreate**

For each of ASR profile / MT profile / Glossary creation, call `getOrCreate(...)` instead. Use the returned id for the dependent Pipeline create.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 5: Update tracker + commit**

```bash
git add frontend/tests-e2e/global-setup.ts docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): seed bootstrap idempotency via getOrCreate

Fixes: BUG-002"
```

---

### Task 18: BUG-003 — cross-env for Windows compat

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install cross-env**

```bash
cd frontend
npm install --save-dev cross-env
```

- [ ] **Step 2: Update test:e2e:seeded script**

Use Edit tool on `frontend/package.json`:

Old: `"test:e2e:seeded": "E2E_REQUIRE_SEED=1 playwright test --global-setup=./tests-e2e/global-setup.ts"`

New: `"test:e2e:seeded": "cross-env E2E_REQUIRE_SEED=1 playwright test --global-setup=./tests-e2e/global-setup.ts"`

- [ ] **Step 3: Verify**

```bash
cd frontend
grep "test:e2e:seeded" package.json
```

Expected: `cross-env` prefix present.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): cross-env for test:e2e:seeded Windows compat

Fixes: BUG-003"
```

---

### Task 19: BUG-010 — request_id propagation to werkzeug logger

**Files:**
- Modify: `backend/logging_setup.py` (the RequestIdFilter)
- Test: `backend/tests/test_logging_and_errors.py` (add assertion)

- [ ] **Step 1: Inspect current RequestIdFilter**

```bash
cat backend/logging_setup.py
```

Identify the filter that does `flask.has_request_context()` check.

- [ ] **Step 2: Write failing test**

Add to `backend/tests/test_logging_and_errors.py`:

```python
def test_werkzeug_log_lines_carry_request_id(client, caplog):
    """werkzeug access logger should emit request_id in its log lines."""
    import logging
    caplog.set_level(logging.INFO, logger='werkzeug')
    resp = client.get('/api/health', headers={'X-Request-ID': 'test-trace-werkzeug-1'})
    assert resp.status_code == 200
    # Find werkzeug access log lines for this request
    werkzeug_lines = [r for r in caplog.records if r.name == 'werkzeug']
    assert any(getattr(r, 'request_id', None) == 'test-trace-werkzeug-1'
               for r in werkzeug_lines), \
        "werkzeug logger lines did not carry inbound X-Request-ID"
```

- [ ] **Step 3: Run test, verify it fails**

```bash
cd backend && source venv/bin/activate
pytest tests/test_logging_and_errors.py::test_werkzeug_log_lines_carry_request_id -v
```

Expected: FAIL with "werkzeug logger lines did not carry inbound X-Request-ID".

- [ ] **Step 4: Implement fix**

Modify `backend/logging_setup.py` to use a thread-local fallback. The RequestIdFilter should read from a contextvar / threadlocal that's set by middleware in addition to flask.g:

```python
import contextvars

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'request_id', default=None
)

def set_request_id(request_id: str | None) -> None:
    _request_id_var.set(request_id)

def get_request_id() -> str | None:
    return _request_id_var.get()

class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Try contextvar first (works across threads via copy_context if propagated)
        rid = _request_id_var.get()
        if rid is None:
            # Fall back to flask.g if in request context
            try:
                from flask import has_request_context, g
                if has_request_context():
                    rid = getattr(g, 'request_id', None)
            except Exception:
                rid = None
        record.request_id = rid
        return True
```

Then modify `backend/middleware.py` `before_request` to also call `set_request_id(g.request_id)`, and `after_request` (or teardown) to clear via `set_request_id(None)`.

- [ ] **Step 5: Run test, verify it passes**

```bash
pytest tests/test_logging_and_errors.py::test_werkzeug_log_lines_carry_request_id -v
```

Expected: PASS.

- [ ] **Step 6: Full regression**

```bash
pytest tests/test_logging_and_errors.py -v
pytest tests/ -k "not test_e2e_render and not test_phase5_security and not test_queue_routes and not test_ass_filter" 2>&1 | tail -10
```

Expected: 794 still pass (or +1 with the new test).

- [ ] **Step 7: Commit**

```bash
git add backend/logging_setup.py backend/middleware.py backend/tests/test_logging_and_errors.py docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): propagate request_id via contextvar to werkzeug logger

Fixes: BUG-010"
```

---

### Task 20: BUG-011 — Replace 20+ print() with logger calls

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Locate all print() calls in app.py**

```bash
grep -n "^\s*print(" backend/app.py
```

Expected: 20+ matches.

- [ ] **Step 2: Categorize each by intent**

Walk through each line. Categorize: INFO (banner / startup status), WARNING (non-fatal degraded path), DEBUG (verbose diagnostic).

- [ ] **Step 3: Replace each print()**

Use Edit tool with `replace_all=false` per line (each replacement unique). Pattern:

- `print(f"... {var}")` → `logger.info("... %s", var)` (preferred — lazy format)
- `print(f"Warning: ...")` → `logger.warning(...)`
- `print(f"[DEBUG] ...")` → `logger.debug(...)`

Ensure `logger = logging.getLogger(__name__)` exists near top of app.py.

- [ ] **Step 4: Verify with grep**

```bash
grep -c "^\s*print(" backend/app.py
```

Expected: 0 (excluding any in __main__ block if intentional).

- [ ] **Step 5: Smoke test backend boot**

```bash
cd backend && source venv/bin/activate
LOG_JSON=1 python app.py > /tmp/post-fix-startup.log 2>&1 &
PID=$!
sleep 5
kill $PID
# Verify startup log is all JSON
python3 -c "import json,sys; [json.loads(l) for l in open('/tmp/post-fix-startup.log') if l.strip()]"
```

Expected: no JSON parse error.

- [ ] **Step 6: Run pytest regression**

```bash
pytest tests/ 2>&1 | tail -5
```

Expected: 794 pass baseline preserved.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): replace 20+ print() with logger calls in app.py

Fixes: BUG-011"
```

---

### Task 21: BUG-004 — PromptOverridesDrawer Save disable when no pipeline_id

**Files:**
- Modify: `frontend/src/pages/Proofread/PromptOverridesDrawer.tsx`
- Test: add Vitest spec at `frontend/src/pages/Proofread/PromptOverridesDrawer.test.tsx` (or extend existing)

- [ ] **Step 1: Read existing component**

```bash
cat frontend/src/pages/Proofread/PromptOverridesDrawer.tsx
```

Locate line 53: `if (!file || !file.pipeline_id) return;`

- [ ] **Step 2: Write failing test**

Add to a Vitest spec file (extend existing if present):

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PromptOverridesDrawer } from './PromptOverridesDrawer';

describe('PromptOverridesDrawer Save behavior', () => {
  it('disables Save button when file.pipeline_id is null', () => {
    const file = { id: 'f1', pipeline_id: null, /* other fields */ } as any;
    render(<PromptOverridesDrawer file={file} open={true} onClose={() => {}} />);
    const save = screen.getByRole('button', { name: /save/i });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute('title', expect.stringContaining('pipeline'));
  });
});
```

- [ ] **Step 3: Run test, verify it fails**

```bash
cd frontend && npx vitest run PromptOverridesDrawer.test.tsx
```

Expected: FAIL (Save not disabled).

- [ ] **Step 4: Implement fix**

In `PromptOverridesDrawer.tsx`, locate the Save `<Button>`. Add `disabled={!file?.pipeline_id}` and `title="File has no pipeline — overrides cannot be saved"`.

- [ ] **Step 5: Run test, verify it passes**

```bash
cd frontend && npx vitest run PromptOverridesDrawer.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Full Vitest run**

```bash
cd frontend && npx vitest run
```

Expected: 184 + N new tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Proofread/PromptOverridesDrawer.tsx frontend/src/pages/Proofread/PromptOverridesDrawer.test.tsx docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): PromptOverridesDrawer disable Save when no pipeline_id

Fixes: BUG-004"
```

---

### Task 22: BUG-006 — SocketProvider connected state + handlers

**Files:**
- Modify: `frontend/src/providers/SocketProvider.tsx`
- Modify: `frontend/src/lib/socket-events.ts` (add action types)
- Test: extend `frontend/src/providers/SocketProvider.test.tsx` (if present) or create

- [ ] **Step 1: Read existing SocketProvider + socket-events**

```bash
cat frontend/src/providers/SocketProvider.tsx
cat frontend/src/lib/socket-events.ts
```

- [ ] **Step 2: Write failing test**

```tsx
import { renderHook, act } from '@testing-library/react';
import { SocketProvider, useSocket } from './SocketProvider';

it('connected state flips on connect/disconnect', async () => {
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    <SocketProvider>{children}</SocketProvider>;
  const { result } = renderHook(() => useSocket(), { wrapper });
  expect(result.current.state.connected).toBe(false); // initial
  // ... simulate socket emit 'connect' / 'disconnect' via mock
  // assert state.connected flips
});
```

- [ ] **Step 3: Implement fix**

In `socket-events.ts`:
```ts
export type SocketAction =
  | { type: 'SOCKET_CONNECTED' }
  | { type: 'SOCKET_DISCONNECTED' }
  | ...; // existing types
```

In reducer, add:
```ts
case 'SOCKET_CONNECTED':
  return { ...state, connected: true };
case 'SOCKET_DISCONNECTED':
  return { ...state, connected: false };
```

Add `connected: false` to `initialSocketState`.

In `SocketProvider.tsx` `useEffect` where `socket.on(...)` handlers register, add:
```ts
socket.on('connect', () => dispatch({ type: 'SOCKET_CONNECTED' }));
socket.on('disconnect', () => dispatch({ type: 'SOCKET_DISCONNECTED' }));
```

- [ ] **Step 4: Verify test passes + Vitest full run**

```bash
cd frontend && npx vitest run
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/providers/SocketProvider.tsx frontend/src/lib/socket-events.ts frontend/src/providers/SocketProvider.test.tsx docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): SocketProvider exposes connected state to UI

Fixes: BUG-006"
```

---

### Task 23: BUG-007 — Stage progress recovery on page refresh

**Files:**
- Modify: `frontend/src/providers/SocketProvider.tsx` (mount-time recovery)
- Alternative: backend `GET /api/files/<id>` to expose `current_stage_progress`

- [ ] **Step 1: Decide approach**

Two options:
- **(A) Frontend-only degraded UX**: on mount, after BULK_FILES, immediately query for any "running" file and set `stageStatus[fileId] = 'running'` to show indeterminate indicator. Progress % starts at 0 until next event fills.
- **(B) Backend authoritative state**: add `current_stage_progress: {stage_idx, percent} | null` to file detail response, frontend hydrates from it.

For simplicity + minimum change, do **(A)**. Document in BUG-007 fix commit that exact % recovery requires (B) future work.

- [ ] **Step 2: Modify SocketProvider mount hook**

In `useEffect` after `apiFetch('/api/files')` returns, dispatch a `RECOVER_RUNNING_STATUS` action that scans files and sets `stageStatus[id] = 'running'` for any file with `status: 'running'`.

Add reducer case:
```ts
case 'RECOVER_RUNNING_STATUS':
  return {
    ...state,
    stageStatus: {
      ...state.stageStatus,
      ...Object.fromEntries(action.runningFileIds.map((id) => [id, 'running'])),
    },
  };
```

- [ ] **Step 3: Update test**

Add Vitest spec asserting after BULK_FILES with a "running" file, stageStatus has that file marked running.

- [ ] **Step 4: Verify + commit**

```bash
cd frontend && npx vitest run
git add ...
git commit -m "fix(v4 debug): recover running-status on SocketProvider mount

Implements degraded recovery UX (option A). Exact % recovery requires
backend GET /api/files/<id> to expose current_stage_progress — deferred.

Fixes: BUG-007"
```

---

### Task 24: BUG-009 — Proofread chunk naming via manualChunks

**Files:**
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Read current vite.config.ts**

Locate `manualChunks` callback.

- [ ] **Step 2: Add Proofread case**

Use Edit tool:

Old (locate the current callback):
```ts
manualChunks: (id) => {
  if (id.includes('node_modules')) {
    if (id.includes('react-router')) return 'vendor-router';
    // ...existing vendor cases
  }
  return undefined;
},
```

New: add a top-level page case BEFORE the node_modules block:
```ts
manualChunks: (id) => {
  if (id.includes('/pages/Proofread/')) return 'Proofread';
  if (id.includes('node_modules')) {
    if (id.includes('react-router')) return 'vendor-router';
    // ...existing
  }
  return undefined;
},
```

- [ ] **Step 3: Rebuild + verify**

```bash
cd frontend && npm run build
ls dist/assets/ | grep -i proofread
```

Expected: `Proofread-<hash>.js` exists (no longer `index-<hash>.js`).

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.ts docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): Vite manualChunks named Proofread chunk

Fixes: BUG-009"
```

---

### Task 25: BUG-018 — Legacy Socket.IO emitter docs cleanup

**Files:**
- Modify: `CLAUDE.md` (remove 3 dead event rows from WebSocket events table)
- Modify: `frontend/src/lib/socket-events.ts` (remove dead type union members if any)

- [ ] **Step 1: Grep CLAUDE.md for dead events**

```bash
grep -n "subtitle_segment\|translation_progress\|pipeline_timing" CLAUDE.md
```

- [ ] **Step 2: Remove those rows from WebSocket events table**

Use Edit tool to delete each matching row.

- [ ] **Step 3: Grep frontend types**

```bash
grep -rn "subtitle_segment\|translation_progress\|pipeline_timing" frontend/src/
```

If type members exist, remove via Edit.

- [ ] **Step 4: Verify tsc still clean**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md frontend/src/lib/socket-events.ts docs/superpowers/debug/v4-bug-tracker.md
git commit -m "docs(v4 debug): remove dead Socket.IO emitter docs + types

Fixes: BUG-018"
```

---

### Task 26: BUG-020 — Ollama probe timeout + memoization

**Files:**
- Modify: `backend/routes/engines.py` (or wherever `/api/translation/engines` lives)
- Test: extend `backend/tests/test_translation.py`

- [ ] **Step 1: Locate Ollama probe code**

```bash
grep -rn "ollama" backend/routes/engines.py | head -20
```

Identify the `requests.get(...)` call hitting Ollama.

- [ ] **Step 2: Write failing test**

```python
def test_ollama_probe_has_timeout(monkeypatch):
    """Ollama probe should pass a timeout kwarg to requests.get."""
    captured = {}
    def fake_get(*args, **kwargs):
        captured['timeout'] = kwargs.get('timeout')
        from unittest.mock import MagicMock
        r = MagicMock(); r.ok = False; return r
    import requests
    monkeypatch.setattr(requests, 'get', fake_get)
    from routes.engines import probe_ollama  # or however imported
    probe_ollama()
    assert captured['timeout'] is not None and captured['timeout'] <= 5
```

- [ ] **Step 3: Implement timeout + cache**

```python
from functools import lru_cache
import time

_PROBE_CACHE: dict[str, tuple[float, dict]] = {}
_PROBE_TTL = 60  # seconds

def probe_ollama() -> dict:
    now = time.monotonic()
    cached = _PROBE_CACHE.get('result')
    if cached and (now - cached[0]) < _PROBE_TTL:
        return cached[1]
    try:
        r = requests.get('http://localhost:11434/api/tags', timeout=2)
        result = {'available': r.ok, 'models': r.json().get('models', []) if r.ok else []}
    except (requests.RequestException, ValueError):
        result = {'available': False, 'models': []}
    _PROBE_CACHE['result'] = (now, result)
    return result
```

- [ ] **Step 4: Verify test passes + integration smoke**

```bash
pytest tests/test_translation.py::test_ollama_probe_has_timeout -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/engines.py backend/tests/test_translation.py docs/superpowers/debug/v4-bug-tracker.md
git commit -m "fix(v4 debug): Ollama probe timeout + 60s memoization

Fixes: BUG-020"
```

---

### Task 27: Track B S1 — Real mlx-whisper ASR validation

**Manual task — user-driven.** Requires backend running + mlx-whisper medium model downloaded + 3 audio samples (en/zh/mixed).

- [ ] **Step 1: Confirm mlx-whisper medium model**

```bash
python3 -c "from mlx_whisper import load_models; load_models.load_model('mlx-community/whisper-medium-mlx')"
```

Expected: model downloads if missing (~3GB) then loads.

- [ ] **Step 2: Prepare 3 audio samples**

Either user-provided real broadcast samples, OR generate test samples:
- `/tmp/test-en.mp3` — 30s English speech (TTS or recorded)
- `/tmp/test-zh.mp3` — 30s Cantonese
- `/tmp/test-mixed.mp3` — 30s code-switched

- [ ] **Step 3: Run via backend pipeline**

For each sample:
1. Start backend (if not running)
2. Login as e2e-admin in browser
3. Upload audio file via dashboard
4. Verify pipeline_run kicks off
5. Wait for ASR stage done
6. Inspect output segments — check fragments / s2hk conversion / initial_prompt effect

- [ ] **Step 4: Update e2e-matrix.md checkboxes**

Mark each Section 1 item per result: PASS / FAIL — see BUG-NNN.

- [ ] **Step 5: Log any new BUG findings to Track B tracker + master tracker**

If real-audio testing reveals new bugs (e.g., merge_short_segments misses a case), add BUG entries and update master tracker summary table. Severity tentative.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/debug/v4-e2e-matrix.md docs/superpowers/debug/v4-bug-tracker-trackB-manual.md docs/superpowers/debug/v4-bug-tracker.md
git commit -m "test(v4 debug): Track B S1 real mlx-whisper ASR validation"
```

---

### Task 28: Track B S2 — Real Ollama MT validation

**Manual task — user-driven.** Requires backend + Ollama running (qwen3.5-mlx confirmed available per Phase 0 env probe).

- [ ] **Step 1: Prepare** — Need ASR output from Task 27 (3 files with ASR done)
- [ ] **Step 2: Run MT** — In dashboard, trigger MT stage on each file. Try `batch_size=1`, `batch_size=10`, `parallel_batches=4`
- [ ] **Step 3: Test prompt_overrides** — On one file, set prompt override via PromptOverridesDrawer, re-translate, verify in stage history
- [ ] **Step 4: Test translation_passes=2** — Edit pipeline to use Pass-2 enrichment, re-translate
- [ ] **Step 5: Update matrix + log findings**
- [ ] **Step 6: Commit**

---

### Task 29: Track B S4 — Real FFmpeg render validation (12 sub-formats)

**Manual task — user-driven.** Requires test video as render source (use one of Task 27 files if it's MP4, or generate a 30s test MP4).

- [ ] **Step 1: Render MP4** — CRF, CBR, 2-pass modes; ffprobe each output
- [ ] **Step 2: Render MXF ProRes** — 6 profiles (0/1/2/3/4/5)
- [ ] **Step 3: Render XDCAM HD 422** — 10 / 50 / 100 Mbps
- [ ] **Step 4: Verify metadata via ffprobe**
- [ ] **Step 5: Update matrix + log findings**
- [ ] **Step 6: Commit**

---

### Task 30: Confirm-defer entries (BUG-005, BUG-008, BUG-019)

**Files:**
- Modify: `docs/superpowers/debug/v4-deferred-backlog.md`

- [ ] **Step 1: Append 3 backlog entries**

For each (BUG-005, BUG-008, BUG-019), write:

```markdown
## BUG-NNN: <title> [deferred Phase 3a]

- **Source**: master tracker BUG-NNN
- **Reason**: <e.g., theoretical race condition, no observed regression>
- **Future action**: Re-evaluate if Socket.IO reconnect issue observed in production; or when faster-whisper batch API gains real-audio validation
```

- [ ] **Step 2: Update master tracker entries Status → Deferred**

Edit `v4-bug-tracker.md` BUG-005 / BUG-008 / BUG-019 Status from "Open" to "Deferred (backlog)".

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/debug/v4-deferred-backlog.md docs/superpowers/debug/v4-bug-tracker.md
git commit -m "docs(v4 debug): confirm defer BUG-005, BUG-008, BUG-019 to backlog

Per Phase 3a decisions (v4-phase3-decisions.md)."
```

---

## Phase 3b execution order recommendation

Sequential execution per group:

1. **Group 1 (Tasks 16-18)** — Test infra (BUG-001/002/003) — quick, unblocks future testing
2. **Group 2 (Tasks 19-20)** — A6 C4 logging (BUG-010/011) — highest production impact
3. **Group 3 (Task 21)** — A4 UX (BUG-004)
4. **Group 4 (Tasks 22-23)** — Socket reliability (BUG-006/007)
5. **Group 5 (Tasks 24-26)** — Bundle + cleanup (BUG-009/018/020)
6. **Task 30** — Defer confirmations (lightweight)
7. **Tasks 27-29** — Real E2E validation (user-driven, 3-4 hr)


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
