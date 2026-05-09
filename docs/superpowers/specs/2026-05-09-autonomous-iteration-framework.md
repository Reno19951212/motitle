# Autonomous Iteration Framework — Ralph Loop × Agent Teams × Superpowers

**Date:** 2026-05-09
**Branch:** chore/roadmap-2026-may
**Status:** Draft（first-pass，用戶 review 緊）
**Driver for:** [R5 Server Mode](2026-05-09-r5-server-mode-design.md) implementation

---

## Goal

畀 user 喺呢個 brainstorming session 定咗 R5 vision 之後，**喺後續 Claude Code session 入面用 `/ralph-loop` 啟動，token 用盡前自動跑 verify→fix→close→re-verify 循環**，直至 R5 全部 task 完成 OR token quota 耗盡。

---

## 設計原則

### 核心 insight（web research 來源）

> **「Is the output machine-verifiable? If yes, loop. If no, get a human.」**
> — Meag Tessmann, *When Agent Teams Meet the Ralph Wiggum Loop*

R5 implementation 同時有兩類工作：

| 類型 | 例子 | 適合工具 |
|---|---|---|
| 機械驗證（machine-verifiable） | pytest 通過、server boot 成功、auth flow 跑通 | **Ralph loop**（autonomous mechanical iteration） |
| 判斷類（judgment-heavy） | multi-user UX 點設計、job queue 顯示方式、login page 視覺 | **Agent Teams**（parallel exploration + 人類 review） |
| 跨層整合 | API contract 一致、frontend↔backend 對 type | **Shared Contracts**（防 mismatch） |

### 防失敗 pattern（同樣來自 web research）

1. **Shared Contracts file** — 所有 teammate 強制 read，確保 API signatures、DB schema、component IDs 一致
2. **4-stage quality gates** — 每個 sub-task done 之前必過 3 個 blocking gate
3. **Validation agent** — 獨立 reviewer 喺 task 完成後 cross-cut check
4. **Bounded iteration** — `max-iterations` + token threshold 強制 graceful exit

---

## Stack

| 工具 | 角色 | 狀態 |
|---|---|---|
| **Anthropic Agent Teams** | Parallel teammate orchestration | Experimental，需 Claude Code v2.1.32+ + `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |
| **Ralph Loop** | Master driver loop | 已驗證喺呢個 project 用過（v3.8 ZH ASR investigation） |
| **superpowers:brainstorming** | Vision/design phase | 已 install — 而家 session 跑緊 |
| **superpowers:writing-plans** | Spec → task list breakdown | 已 install — 下一步用 |
| **superpowers:systematic-debugging** | Phase 1 root cause analysis when failures hit | 已 install |
| **superpowers:test-driven-development** | RED-GREEN-REFACTOR | 已 install |
| **superpowers:verification-before-completion** | Last-check before commit | 已 install |

---

## Roles — 5 specialised teammate

| Teammate | Scope | Read | Write | 主要職責 |
|---|---|---|---|---|
| `ralph-architect` | Design decisions、Shared Contracts maintenance | All | `docs/superpowers/`、Shared Contracts | 釐清 architecture decision、update contracts |
| `ralph-backend` | Flask routes、auth、queue、SQLite | All | `backend/` (除 tests) | 寫 production code |
| `ralph-frontend` | Login UI、dashboard、queue panel | All | `frontend/` | 寫 UI |
| `ralph-tester` | Pytest + Playwright + 寫 RED test | All | `backend/tests/`、`frontend/tests/` | TDD enforcer |
| `ralph-validator` | Cross-cut review、integration check | All | Read-only | Quality gates、reject task 唔合 contracts |

**Anti-conflict rule：** 同一個 file 唔好 2 個 teammate 同時改。Task list 必須 partition cleanly by directory。

---

## Coordination Layer — Shared Contracts

**位置：** `docs/superpowers/r5-shared-contracts.md`

**內容：**

```markdown
# R5 Shared Contracts

## API Endpoint Signatures
| Method | Path | Auth | Body | Response | Owner |
|---|---|---|---|---|---|
| POST | /login | none | {username, password} | 200 + session cookie / 401 | ralph-backend |
| POST | /logout | session | - | 200 | ralph-backend |
| GET | /api/me | session | - | {id, username, is_admin} | ralph-backend |
| GET | /api/queue | session | - | [{id, file_id, status, position, eta_seconds}] | ralph-backend |
...

## Database Schema
（mirror 自 R5 design D2）

## Frontend Component IDs
| ID | Purpose | Used by |
|---|---|---|
| `loginForm` | Login page form | ralph-frontend |
| `userChip` | Top bar user display | ralph-frontend |
| `queuePanel` | Job queue panel | ralph-frontend |
...

## Test IDs (for Playwright)
| Selector | Purpose |
|---|---|
| `[data-testid="login-submit"]` | Login button |
| `[data-testid="queue-row"]` | Each queue row |
...
```

**Mutation rule：** 只有 `ralph-architect` 可以改呢個 file。其他 teammate 改任何嘢前讀返呢個 file 確認 signature。

---

## 4-Stage Quality Gates

每個 sub-task `git commit` 之前必過 3 個 blocking gate（gate 4 advisory）：

| Gate | 工具 | 通過條件 | Blocking? |
|---|---|---|---|
| 1. Correctness | `pytest tests/` | 全綠（除已知 baseline failure） | ✅ Yes |
| 2. Quality | type check（無新增 hardcode、debug print） | grep 確認 + spot review | ✅ Yes |
| 3. Security | gitleaks + 手動 secrets scan | 0 finding | ✅ Yes |
| 4. Consistency | lint advisory（PEP8、CSS naming） | warning only | ⚠️ Advisory |

Gate 失敗 → 唔 commit；ralph-tester 寫 reproducer test，feed back 去 ralph-backend / ralph-frontend 修。

---

## 6-Step Cycle（用戶 spec 對應實作）

```
┌─────────────────────────────────────────────────────────────────┐
│  Master Ralph Loop（max-iterations 50）                          │
│                                                                  │
│  [1. 驗證測試 (Verify)]                                           │
│     - read docs/superpowers/r5-task-list.md → pick next pending  │
│     - run pytest backend/tests/ + relevant Playwright            │
│     - if all pass + task already done → mark done, advance       │
│                                                                  │
│             ↓                                                    │
│  [2. 修筆 (Fix)]                                                 │
│     - if no failing test for current task → ralph-tester writes  │
│       RED test (TDD)                                              │
│     - ralph-backend / ralph-frontend implement to pass           │
│     - 必要時 ralph-architect 先 update Shared Contracts          │
│                                                                  │
│             ↓                                                    │
│  [3. 完成閉環 (Close)]                                            │
│     - run 4-stage quality gates                                  │
│     - if pass: git commit task-specific message                  │
│     - update task list (mark done)                               │
│                                                                  │
│             ↓                                                    │
│  [4. 重新檢查 (Re-check)]                                         │
│     - ralph-validator runs full pytest + Playwright              │
│     - diff against Shared Contracts — any mismatch?              │
│     - check for unintended changes outside task scope            │
│                                                                  │
│             ↓                                                    │
│  [5. 再驗證+Debug (Re-verify + Debug)]                            │
│     - if regression: invoke superpowers:systematic-debugging     │
│       Phase 1 — gather evidence, identify root cause             │
│     - feedback → step 2 with specific failure context            │
│     - max 3 retry per task；3+ failure → flag to user            │
│                                                                  │
│             ↓                                                    │
│  [6. 最後閉環 (Final close)]                                      │
│     - merge sub-task → working branch                            │
│     - advance to next pending task in task list                  │
│     - ↺ back to step 1                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

Exit conditions:
  - All task list items marked done AND all gates green AND
    ralph-validator gives green light → <promise>ALL_DONE</promise>
  - Iteration count > 50 → write progress report, exit
  - Token usage > 80% → write progress report, exit
```

---

## Setup Steps

### 1. Enable Agent Teams（如可用）

```bash
# Check Claude Code version (≥ 2.1.32)
claude --version

# Enable in settings.json
echo '{"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": 1}' >> ~/.claude/settings.json
```

如果 Agent Teams 暫時不可用，loop 會 degrade 到 single-session + 內建 `Agent` tool（Explore / Plan / general-purpose）— 仍 work，只係多 token cost。

### 2. 建立 teammate config files

```bash
mkdir -p .claude/teammates
# 每個 teammate 一個 .md file，裡面寫 scope、permission、constraints
# Template 喺 implementation plan 度提供
```

### 3. 建立 Shared Contracts skeleton

```bash
mkdir -p docs/superpowers
cat > docs/superpowers/r5-shared-contracts.md <<'EOF'
# R5 Shared Contracts
（initial version 由 ralph-architect 喺 first iteration 建立）
EOF
```

### 4. 由 R5 design spec 生成 task list

呢一步用 **superpowers:writing-plans** skill：

```
/superpowers
> writing-plans
> Input: docs/superpowers/specs/2026-05-09-r5-server-mode-design.md
> Output: docs/superpowers/r5-task-list.md
```

預期 output：30-50 個 atomic task，partition by teammate scope（backend / frontend / tester / architect）。

### 5. Fire Master Ralph Loop

```bash
/ralph-loop "<<MASTER_PROMPT below>>" --max-iterations 50 --completion-promise "ALL_DONE"
```

---

## Master Ralph Loop Prompt Template

```markdown
任務：autonomous implement R5 Server Mode（self-hosted multi-client）。

Vision spec: docs/superpowers/specs/2026-05-09-r5-server-mode-design.md
Task list: docs/superpowers/r5-task-list.md
Shared contracts: docs/superpowers/r5-shared-contracts.md

每 iteration:

1. READ task list → pick ONE next-pending task（top of list 優先）
2. READ shared contracts → confirm signatures still consistent
3. PICK appropriate teammate(s) for the task layer:
   - Backend task → ralph-tester (write RED test) → ralph-backend (implement)
   - Frontend task → ralph-tester (Playwright RED) → ralph-frontend (implement)
   - Cross-cut → ralph-architect (update contracts FIRST) → relevant teammate
4. RUN 4-stage quality gates:
   - Gate 1 Correctness: pytest must pass
   - Gate 2 Quality: no new hardcode / debug print
   - Gate 3 Security: gitleaks scan, no plaintext secret
5. ralph-validator REVIEW integration:
   - Run full suite (pytest + Playwright)
   - Diff against shared contracts
   - Check no unintended changes outside task scope
6. IF pass:
     git commit (task-specific message)
     mark task done in task list
   IF fail:
     invoke superpowers:systematic-debugging Phase 1
     feedback to step 2
     retry max 3 times；3+ failure → write blocker report and skip task

If task list 100% done AND all gates green AND validator green:
  → <promise>ALL_DONE</promise>

If iterations > 50 OR token consumption > 80%:
  Write status to docs/superpowers/r5-progress-report.md
  → <promise>ALL_DONE</promise>

Anti-pattern guards:
- DO NOT skip writing tests — RED first always
- DO NOT batch multiple tasks per iteration — one task = one cycle
- DO NOT modify Shared Contracts without ralph-architect explicit step
- DO NOT proceed past gate failures — retry / debug
- DO NOT make architecture decisions inside ralph-backend/frontend — escalate to ralph-architect
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Agent Teams 暫時不可用 | Degrade 到 built-in Agent tool（Explore / Plan）— 慢啲但 functional |
| Teammate 改重疊 file → conflict | Task list 強制 partition by directory；ralph-validator 偵測 |
| Loop 不停 retry 同一 failure | Max 3 retry per task，第 4 次 escalate 到 user |
| Token 用爆 | `--max-iterations 50` + 80% threshold check 強制 exit；progress report 保證可 resume |
| Shared Contracts drift | 只 ralph-architect 可改；其他 teammate 違規由 ralph-validator block |
| ralph-validator 自己漏 catch | 4-stage gates 獨立於 validator；any gate fail = task fail |
| 開發中 user 想 intervene | Ralph loop 喺同一個 chat session 跑，user 可隨時打字介入 |

---

## Open Questions（畀 user review）

1. **Agent Teams enable：** 你部 Claude Code 而家 v 幾多？要唔要我 setup `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`？
2. **Token threshold：** 80% 算唔算 conservative？想 90%？
3. **Iteration cap：** 50 適合嗎？R5 大概 30-50 atomic task，1:1 ratio 應該勉強夠。如果預估會超，要拆 R5 phase。
4. **Validator 嚴度：** 4-stage gates 嘅 Quality + Security gate 想 block 定 advisory？

---

## Sequencing — 從 brainstorming 到 autonomous loop

```
[NOW] brainstorming session ← we are here
   ↓
[next 1] User review 兩份 spec → 修改 → 確認
   ↓
[next 2] Invoke superpowers:writing-plans
   → 由 R5 design spec 生成 task list（30-50 atomic task）
   → Partition by teammate scope
   ↓
[next 3] Setup teammate config files
   → .claude/teammates/ralph-architect.md 等
   ↓
[next 4] Initialize Shared Contracts skeleton
   ↓
[next 5] Fire Master Ralph Loop
   → /ralph-loop "<<TEMPLATE>>" --max-iterations 50 --completion-promise "ALL_DONE"
   ↓
[autonomous] 6-step cycle 跑直至 ALL_DONE 或 token exhausted
   ↓
[final] Progress report → user review → next session continue if not done
```
