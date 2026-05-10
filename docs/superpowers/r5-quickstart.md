# R5 Phase 1 — Master Ralph Loop Quick Start

> 由 terminal Claude Code CLI fire 個 autonomous loop（stop hook auto-fire）。

## Current state

- **Branch:** `chore/roadmap-2026-may`（已 push 上 origin）
- **Progress:** 2/37 tasks done（Task A1 + B1）
- **Latest commit:** `a90afc5 chore(r5): add Flask-Login + bcrypt dependencies (Task B1)`
- **Next pending task:** **B2** — ralph-tester writes RED test for `auth/passwords.py`

## Prerequisites

```bash
# 1. Confirm Claude Code CLI version ≥ 2.1.32
claude --version

# 2. (Optional) Enable Agent Teams experimental flag
echo '{"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": 1}' >> ~/.claude/settings.json

# 3. Working tree clean (only prod-default.json's API key as untracked diff)
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git status

# 4. On the right branch
git branch --show-current  # should be: chore/roadmap-2026-may
```

## Fire the loop

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
claude
```

然後喺 Claude Code prompt 入面 paste：

````
/ralph-loop "Master Ralph loop driving R5 Server Mode Phase 1 implementation autonomously.

References (read at start of each iteration):
- Plan: docs/superpowers/plans/2026-05-09-r5-server-mode-phase1-plan.md (37 atomic tasks; A1 + B1 done; resume at B2)
- Spec: docs/superpowers/specs/2026-05-09-r5-server-mode-design.md
- Framework: docs/superpowers/specs/2026-05-09-autonomous-iteration-framework.md
- Teammate configs: docs/superpowers/teammates/{ralph-architect,ralph-backend,ralph-frontend,ralph-tester,ralph-validator}.md
- Shared Contracts: docs/superpowers/r5-shared-contracts.md

Per-iteration cycle:

1. READ plan file — pick the next task with empty checkbox at top of file order
2. READ matching teammate config (e.g. backend task → ralph-backend.md)
3. READ shared contracts to confirm signatures
4. EXECUTE the task's 5 steps (write test / run-fail / implement / run-pass / commit) following teammate constraints
5. RUN 4-stage quality gates (Correctness pytest / Quality grep / Security gitleaks / Consistency advisory)
6. RALPH-VALIDATOR review:
   - Full pytest --ignore=tests/test_e2e_render.py
   - Diff against Shared Contracts
   - Spot-check curl on endpoint touched
   - REJECT if any blocking gate fails (Quality / Security / Correctness)
7. ON PASS: mark checkbox done in plan file, advance to next task
   ON FAIL: invoke superpowers:systematic-debugging Phase 1 to gather evidence, write feedback to docs/superpowers/r5-progress-report.md, retry up to 3 times. After 3 failures on same task, output ALL_DONE with blocker note.

Anti-patterns (DO NOT):
- Skip TDD RED step
- Batch multiple tasks per iteration
- Modify Shared Contracts outside of ralph-architect role
- Make architecture decisions inside backend/frontend tasks (escalate to architect)
- Commit secrets / API keys / passwords

Completion criteria for ALL_DONE:
- All 37 plan checkboxes marked done AND
- ralph-validator final smoke (Task H1) all green AND
- All quality gates green AND
- gitleaks clean

Graceful exit:
- If iteration count reaches 50 → write progress report, output ALL_DONE
- If 3+ consecutive validation failures on same task → write blocker report, output ALL_DONE with note 'Phase 1 incomplete: <task ID> blocker requires human review'

Output ALL_DONE only when GENUINELY TRUE per Ralph loop rules — never to escape." --max-iterations 50 --completion-promise "ALL_DONE"
````

## Monitoring（另開 terminal）

```bash
# Watch progress in real time
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
watch -n 5 'git log --oneline | head -10'

# Watch task list checkbox progress
watch -n 5 'grep -c "^- \[x\]" docs/superpowers/plans/2026-05-09-r5-server-mode-phase1-plan.md'

# Tail any progress report (created when failures hit)
tail -f docs/superpowers/r5-progress-report.md 2>/dev/null
```

## Stop the loop

- Wait for `<promise>ALL_DONE</promise>` (auto-stop on completion or 50 iterations / blocker)
- 或者手動 Ctrl+C 個 Claude Code CLI

## Resume after pause

如果 loop 中途停咗（token 用盡、Ctrl+C、blocker），下次再 fire 嗰陣 paste 同一個 master prompt。Loop 會：
1. Read plan file → 揾到下一個未打 ✅ 嘅 task
2. Resume from there

唔需要修改任何嘢 — plan checkboxes + git commit history 就係 single source of truth。
