# v4.0 Debug Branch — E2E Bug Hunt + Triage Design

**Date:** 2026-05-18
**Revision:** v2 (2026-05-18) — applied 8 P0+P1 spec self-review fixes (per-track sub-file split, Track B env-gating, Playwright skip dual-script, baseline capture, Track D known-issue harvest, P0 severity clarification, 5th plan-impact bucket, branch close criteria split)
**Branch:** `debug/v4-e2e-bug-hunt` (to be cut from `chore/asr-mt-rearchitecture-research` @ `77a24de`)
**Parent phases covered:** A1 (stage executor) + A3 (frontend foundation) + A4 (proofread page) + A5 (legacy cleanup) + A6 (production polish) + P1 (entity foundation)

## 1. 目標

由於 v4.0 rearchitecture 由 P1 → A1 → A3 → A4 → A5 → A6 跨咗 73+ commit、動咗成個 frontend stack（vanilla → React/Vite/TS）、砍咗 ~1600 行 legacy backend code、refactor 咗 app.py 3499→768 行，我哋需要系統性發掘並 triage 所有遺留 bug，再決定每條 bug 嘅處理路徑（fix vs spec update vs 新 sub-phase vs defer），然後先動手。

明確 **唔係**「揾到 bug 就 fix」— 因為當中部分問題可能反映原 A1-A6 spec 嘅 design gap（例如 cancel_event contract 喺長 inference call 中段嘅 propagation 未明確、StreamingSession 仍 inline 喺 app.py、R5_CONFIG_DIR fixture 跨 OS robustness 未驗），呢類問題需要更新原 spec，唔係 patch。

## 2. Non-goals

- **唔做**主動 refactor／feature work — 純 discovery + triage + targeted fix
- **唔做**未喺 v4.0 計劃內嘅優化（Mac/Win packaging、mobile responsive、i18n、CI/CD、Storybook — 全部留將來 sub-phase）
- **唔做**StreamingSession 抽離 — 屬於 future housekeeping，除非 discovery 揾到 P0 連帶 bug 才會 inline 處理
- **唔做**主分支 merge — 呢條 branch 完成後最終 merge 入 `chore/asr-mt-rearchitecture-research`，再由 parent branch 統一上 main

## 3. 四階段架構

```
Phase 0: Setup       (~45 min)  ─ 創 branch + capture baseline + bug tracker + matrix doc
Phase 1: Discovery   (4 並行 track) ─ Playwright / Manual (env-gated) / Static / Known-issue harvest
Phase 2: Triage      ─ Consolidate sub-trackers → master tracker，分 P0-P3 + 5 plan-impact buckets
Phase 3a: Decision gate ─ 同 user 對 triage 結果決定走向（可能 abort if P0 count > threshold）
Phase 3b: Targeted fix ─ 執行決定（fix / spec update / 新 sub-phase / defer）
```

**Effort estimate**（粗略）：
- Phase 0: ~45 min
- Phase 1: Track A ~2-4 hr / Track B ~3-6 hr (gated, 可 N/A) / Track C ~1 hr / Track D ~30 min
- Phase 2: ~1 hr triage consolidation
- Phase 3a: ~1 session decision
- Phase 3b: 視 bug count，可能跨多個 session

## 4. Phase 0 — Setup

### 4.1 Branch checkout

```
git checkout chore/asr-mt-rearchitecture-research
git pull --ff-only
git checkout -b debug/v4-e2e-bug-hunt
```

### 4.2 Baseline capture（**重要 — 對比 anchor**）

寫 `docs/superpowers/debug/v4-debug-baseline.md`，記低 branch cut 嗰刻嘅 ground truth，畀後續 finding 對比「v4.0 引入 vs v3.x 就有」：

```bash
# Backend baseline
cd backend && source venv/bin/activate
pytest tests/ 2>&1 | tee /tmp/baseline-pytest.log
# 期望：794 pass / 14 baseline failure（CLAUDE.md A6 entry 確認過）

# Frontend baseline
cd frontend
npm run build 2>&1 | tee /tmp/baseline-build.log   # 期望：clean，main chunk ~31KB
npx vitest run 2>&1 | tee /tmp/baseline-vitest.log  # 期望：184 pass
npx tsc --noEmit 2>&1 | tee /tmp/baseline-tsc.log   # 期望：clean
npx playwright test --list 2>&1 | tee /tmp/baseline-pw.log  # 期望：11 specs / 14 cases parse clean

# Static checks
grep -rn "TODO\|FIXME\|XXX\|HACK" backend/ frontend/src/ > /tmp/baseline-todos.txt
```

Baseline doc 入面記低：
- 4 個命令輸出嘅 summary line（不 paste 全部，只記 numbers + 失敗清單）
- 14 個 backend baseline failure 嘅 test name + 已知原因（CLAUDE.md A6 entry 有列）
- TODO/FIXME count baseline（畀 Track D 對比）

### 4.3 Bug tracker — split-per-track schema

避免 Phase 1 並行 subagent 寫同一 file 衝突，每條 track 寫獨立 sub-file，Phase 2 由主 session consolidate：

- `docs/superpowers/debug/v4-bug-tracker-trackA-playwright.md`
- `docs/superpowers/debug/v4-bug-tracker-trackB-manual.md`
- `docs/superpowers/debug/v4-bug-tracker-trackC-static.md`
- `docs/superpowers/debug/v4-bug-tracker-trackD-known.md`
- `docs/superpowers/debug/v4-bug-tracker.md`（master，Phase 2 由 sub-tracker 合併）

每條 bug 一個 H2 section，schema：

```markdown
## BUG-NNN: <短描述>
- **Status**: Open / In progress / Fixed / Wontfix / Deferred
- **Severity**: P0 blocker / P1 high / P2 medium / P3 nice-to-fix
- **A-phase origin**: P1 / A1 / A3 / A4 / A5 / A6 / cross-phase
- **Layer**: backend / frontend / E2E / docs / config / build
- **Discovery source**: Track A (Playwright) / Track B (Manual) / Track C (Static)
- **Repro steps**: ...
- **Expected**: ...
- **Actual**: ...
- **Plan impact**（必選一個）:
  - [ ] 純 bug fix（落入呢個 branch 即可）
  - [ ] Spec 假設錯（需更新原 A?-design.md，列明哪個 §）
  - [ ] 需開新 sub-phase（A7/A8）
  - [ ] Defer 入 backlog
  - [ ] Confirmed out-of-scope（撞到 §10 列為 out-of-scope 嘅 area — log 但唔處理）
- **Suggested fix**: <approach>
- **Linked commit**: (填寫修復 commit SHA)
```

### 4.4 E2E matrix doc

新 `docs/superpowers/debug/v4-e2e-matrix.md` — Phase 1 Track B 嘅 manual checklist，按 A-phase 分區：

```markdown
## A1 — Stage executor
- [ ] Upload audio → enqueue pipeline_run → ASR 完成 → MT 完成 → glossary scan ...
- [ ] cancel_event 喺 ASR Whisper inference 中段 abort ...
- [ ] cancel_event 喺 MT Ollama batch 中段 abort ...
- ...

## A3 — Frontend foundation
- [ ] Login flow（admin + non-admin）
- [ ] Pipeline picker localStorage persist 後 reload 仲保留 ...
- ...
```

## 5. Phase 1 — Discovery（4 條並行 track）

Track A/B/C 由獨立 fresh subagent 跑（context 隔離 + 真並行）；Track D 由主 session 做（cheap，半小時就完）。

### 5.1 Track A — Playwright suite 補洞 + 雙 script 分流

**現狀**：A6 C3 加入 5 個新 spec，全部用 graceful-skip pattern（admin password 唔啱 / seed data 缺 → `test.skip`）。實際 CI / dev 環境多數 skip 多過 run。

**唔可以單純移除 skip** — 會打爛 CI（fresh checkout 冇 seed data 就硬失敗）。要分兩條 npm script：

| Script | 行為 | 用喺 |
|---|---|---|
| `npm run test:e2e` | 保留 graceful skip pattern | CI / 新 checkout / 冇 bootstrap 嘅 environment |
| `npm run test:e2e:seeded` | 跑前必執行 `seed-e2e.sh` bootstrap script；任何 skip → hard fail | 本地 dev / 真 assertion 場景 |

**動作**：
1. 寫 `frontend/tests-e2e/seed-e2e.sh`（或 Playwright `globalSetup`）：bootstrap admin user `e2e-admin` / `TestPass1!` + seed 1 ASR profile + 1 MT profile + 1 glossary + 1 pipeline
2. `package.json` 加 `test:e2e:seeded` script，runs `seed-e2e.sh && playwright test --grep-invert "@no-seed"`（或 env flag `E2E_REQUIRE_SEED=1` 控制 spec 入面 skip 行為）
3. Spec 入面 `test.skip` 改用 helper `requireSeedOrSkip()` — 讀 `E2E_REQUIRE_SEED` env，true 時 throw 而非 skip
4. 補種未 cover 嘅 critical path scenario（按 §8 hypothesis 排優先，proofread + cancel + multi-user 先寫）：
   - **happy-path-pipeline.spec.ts**：upload → pipeline_run → ASR done → MT done → glossary scan → render（end-to-end E2E）
   - **pipeline-broken-refs.spec.ts**：刪 ASR profile 後 pipeline 顯示 `broken_refs` badge
   - **proofread-stage-rerun.spec.ts**：edit segment → rerun stage → stage history sidebar 顯示新 version
   - **proofread-prompt-override.spec.ts**：save override → re-translate → 新 prompt actually 入 LLM call
   - **multi-user-isolation.spec.ts**：user A 開 file，user B login 唔睇到
   - **cancel-running-job.spec.ts**：long pipeline → click cancel → UI 顯示 cancelling → status flip cancelled
4. 跑全 suite，所有新 spec 必須真 pass，所有 bug 入 tracker

### 5.2 Track B — Manual E2E matrix（env-gated）

Playwright 難覆蓋嘅高風險場景，由真實 model + binary 跑。**每個 section 開頭列 prerequisite，環境唔具備就 mark `[N/A — missing <X>]` 入 tracker，唔當失敗**。

**真實 ASR**（prereq：M-series Mac + mlx-whisper medium model ~3GB downloaded）
- mlx-whisper medium model 跑一段廣東話 + 一段英文 + 一段中英混合
- 確認 cn_convert s2hk flag 真正 trigger，輸出全繁體
- 確認 `merge_short_segments` 唔再產 1-word fragment
- 確認 `initial_prompt` 真正 bias decoder

**真實 MT — Ollama**（prereq：本地 Ollama running + qwen3.5-35b-a3b ~22GB pulled + 32GB+ RAM）
- 跑 single-segment mode（`batch_size=1`）+ batched mode + parallel_batches=4
- prompt override 真正 inject 入 LLM payload 確認
- translation_passes=2 enrich pass 真正 trigger 確認

**真實 MT — OpenRouter**（prereq：OPENROUTER_API_KEY env var set + 有 paid credit）
- claude-sonnet-4-5 + gpt-4o-mini 各跑一條同 file 比較
- model dropdown 自訂 input 路徑工作

**真實 FFmpeg render**（prereq：FFmpeg installed + 一段測試 MP4 source ~30s + 5GB free disk）
- MP4：CRF / CBR / 2-pass 三 mode 各燒一條，verify pixel_format + profile + level cross-field validation
- MXF ProRes：6 個 profile（Proxy/LT/Standard/HQ/4444/4444XQ）各燒一條
- XDCAM HD 422：10 / 50 / 100 Mbps 各燒一條
- 全部用 ffprobe 確認 metadata correct

**WebSocket reliability**（prereq：Chromium DevTools available — 任何 dev environment 都得）
- 跑 pipeline 中段 toggle network（DevTools throttle / kill server / refresh page）
- Verify stage progress event 唔丟失 / 重連後 state restore

**Bundle code-split runtime**（prereq：`npm run build` 完成 + 可 serve `dist/` — 全部 dev environment 都得）
- DevTools Network tab：first paint 只 load entry + vendor-react + Login chunk
- Navigate 去 /pipelines → vendor-dnd lazy load
- 慢 3G throttle 體驗確認 PageLoader fallback 唔閃

**Structured logging**（prereq：可起 backend 完整 pipeline — 同上）
- `LOG_JSON=1 LOG_LEVEL=DEBUG python app.py` 跑完整 pipeline
- 確認 X-Request-ID 由 inbound HTTP → log line → 子 thread 都貫穿
- 確認 ApiError exception 真正 render 做 JSON 唔係 HTML 500 page

### 5.3 Track C — 靜態掃描（surgical grep only）

A5 大手術後嘅遺留檢查。**剔除 vulture / ts-prune**（兩者 false-positive 高，pytest fixture / TS ambient declaration / dynamic import 一律當 dead，會浪費 hours triage 非 bug）。只保留 high signal 嘅 grep + type check：

```bash
# Dead reference 掃描（A5 砍走嘅 4 個 module + 4 個 function 嘅遺留）
grep -rn "from translation.alignment_pipeline" backend/
grep -rn "from translation.sentence_pipeline" backend/
grep -rn "from translation.post_processor" backend/
grep -rn "from profiles import" backend/
grep -rn "_auto_translate\|transcribe_with_segments\|_asr_handler\|_mt_handler" backend/

# Frontend legacy residue
grep -rn "frontend.old" .
grep -rn "useActiveProfile" frontend/src/  # A5 deleted hook

# Type checking
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
```

`mypy` 跑都得（`backend && python -m mypy . --ignore-missing-imports || true`）但呢個 codebase 唔係 strict-typed，預期會出大量 warning。如果跑就只當 informational reference，唔當 finding。

任何 dead reference / type error / lint error 入 tracker。

### 5.4 Track D — Known-issue harvest（主 session，~30 min，最高 signal-to-noise）

跳過 Playwright + manual + static 之前先做嘅 cheap 收割。Source of finding：

**Source 1：TODO / FIXME / XXX / HACK comment**
```bash
grep -rn "TODO\|FIXME\|XXX\|HACK\|defer to" backend/ frontend/src/ \
  --include="*.py" --include="*.ts" --include="*.tsx" \
  | grep -v "node_modules\|\.test\." > /tmp/track-d-todos.txt
```
逐條讀，每個 actionable TODO 入 tracker（reword 做 bug entry）。

**Source 2：CLAUDE.md 每個 phase 結尾「Out-of-scope」section**
- v4.0 A3 entry 末段「Out-of-A3 scope」
- v4.0 A4 entry 末段「Out-of-A4 scope」
- v4.0 A5 entry 末段「Out-of-scope」
- v4.0 A6 entry 末段「Out-of-A6 scope」
- v3.x phase entry 內任何「deferred」或「out of scope」字眼

逐條評估：仍然 out-of-scope（log 入 `Confirmed out-of-scope` bucket）vs 實際係 v4.0 surface bug（升做 active finding）。

**Source 3：近期 commit message 嘅 escape hatch wording**
```bash
git log --since="2026-05-15" --all --oneline | head -50
git log --since="2026-05-15" --all --grep="TODO\|FIXME\|defer\|known issue\|留將來\|out-of-scope"
```

**Source 4：CLAUDE.md 自己列嘅 v4.0 backlog item**
- StreamingSession 抽離
- Mac/Win 打包
- mobile responsive
- i18n
- Storybook
- CI/CD

呢類 confirmed out-of-scope，全部寫 entry 入 tracker（mark `Confirmed out-of-scope` bucket）— 用來提供 audit trail，避免 Phase 1 其他 track 重複發現嘅時候要從頭評。

**Output**：`v4-bug-tracker-trackD-known.md` 至少包含：
- TODO/FIXME 全部 listed
- CLAUDE.md 每個 out-of-scope item 一個 entry
- 任何 commit-level 已知問題

主 session 跑 Track D 比 subagent 高效 — context 已有 CLAUDE.md + 全 history，唔需要重新 bootstrap。

## 6. Phase 2 — Triage

每條 bug 入 tracker 之後依 schema 填 severity + plan impact。**Phase 2 開頭第一步**：主 session 將 4 個 sub-tracker（Track A/B/C/D）consolidate 入 `v4-bug-tracker.md` master，de-dup（同一條 bug 喺多 track 出現只算一次），再 triage。

Severity 標準：

| Severity | 標準 | 例子 |
|---|---|---|
| **P0 blocker** | 阻 ship 入 main | (1) 完全 crash / 主流程行唔通；(2) 認證繞過 / 任何 privilege escalation；(3) **silent data corruption**（render 出錯內容但 status=success；MT 寫錯 segment 但 UI 顯示 approved）；(4) **跨 user 數據洩漏**（即使無 auth bypass — 例如 list endpoint 漏 filter）；(5) **工作成果不可恢復**（誤刪用戶 file / pipeline 而無 confirmation） |
| **P1 high** | 用戶實際會撞 | 核心功能壞但唔崩 / 數據 incorrect 但 visible / UX 嚴重壞（例如 Save button click 後無反應） |
| **P2 medium** | Edge case | 少數 path / 特定 config / browser-specific / 警告但唔阻 |
| **P3 nice-to-fix** | Code smell | Refactor opp / docs typo / log message 唔對齊 |

**Abort gate**（Phase 2 結束）：如果 P0 count > 5，主 session 必須暫停 Phase 3，提交 alarming report 畀 user 決定：
- (a) 繼續 Phase 3b 全 fix 入 debug branch
- (b) 凍結 v4.0 ship 計劃，重新諗 A1-A6 部分 phase rewrite
- (c) 部分 P0 升做新 sub-phase（A7/A8）

Plan impact 標準（每條 bug 必選一個）：
1. **純 bug fix** — 行為偏離 spec，spec 本身冇問題 → 直接 fix 入 debug branch
2. **Spec 假設錯** — spec 寫嘅嘢前提錯 → 先更新原 design.md 留 audit trail，再 fix
3. **需開新 sub-phase** — 修復需大改 scope（例如要重設計 cancel contract）→ 開 A7/A8 落 plan
4. **Defer** — 已知問題但唔急 → 入 `docs/superpowers/debug/v4-deferred-backlog.md`

## 7. Phase 3 — Re-brainstorm + Targeted fix

帶住 triage 完嘅 tracker 返嚟搵 user，per-bug 決定走向。決定完之後：

- **純 bug fix bucket**：subagent-driven-development 派 fresh agent per bug 修，two-stage review 後 commit 入呢條 branch
- **Spec update bucket**：先寫 PATCH 到原 design.md（明確標 `### Updated 2026-05-XX: <reason>`），commit，再走 fix flow
- **新 sub-phase bucket**：跳出呢條 branch，行返 brainstorming → writing-plans 流程，呢條 debug branch 唔處理
- **Defer bucket**：純 documentation commit 記入 backlog doc

最終 debug branch ready 之後 merge 返入 `chore/asr-mt-rearchitecture-research`，由 parent branch 統一上 main。

## 8. 對 A1-A6 計劃嘅潛在影響（hypothesis — 要 Phase 1 驗證）

預測哪個 phase 最可能有 spec gap 而非單純 bug：

| Phase | Hypothesis | 風險 |
|---|---|---|
| **A1** | cancel_event 喺長 inference call 中段 propagation contract 未明確 | spec gap 可能 |
| **A1** | per-stage rerun 嘅 lock semantics（同時 rerun 同一 file 兩個 stage） | spec gap 可能 |
| **A3** | SocketProvider reconnect race / stage event 重連後 dedupe | bug 可能 |
| **A3** | Zustand pipeline-picker localStorage 喺 pipeline 被刪後 stale id | bug 可能 |
| **A4** | proofread 14 component 互動只 ~50 unit test，integration coverage 細 | bug 大量可能 |
| **A4** | render modal cross-field validation 喺 edge boundary（例 yuv422p + auto level）未充分 | edge bug 可能 |
| **A5** | R5_CONFIG_DIR fixture 喺 CI / Windows 邊界 robustness | infra bug 可能 |
| **A5** | 砍走 _auto_translate 後 subtitle export 路徑用 DEFAULT_FONT_CONFIG fallback 嘅副作用 | regression 可能 |
| **A6 C1** | vendor-react chunk 165KB 喺真實慢網點 lazy load | UX 可能 |
| **A6 C2** | blueprint lazy import 形成 circular dep / startup ordering 問題 | rare bug 可能 |
| **A6 C4** | request_id 喺 worker thread / Socket.IO event 點貫穿（middleware 只 hook HTTP） | logging gap 可能 |

呢個表 Phase 1 完成後會 update 變實際 finding。

## 9. Workflow 對齊 Superpowers

| 階段 | Skill |
|---|---|
| Phase 0 setup | 純手動 + git |
| Phase 1 Discovery | **subagent-driven-development** — Track A/B/C 各派 fresh agent 並行（context 隔離） |
| Phase 2 Triage | 純文檔工作，主 session 處理 |
| Phase 3 fix | 視 bug scope：簡單就 inline，複雜就 subagent-driven 派 fresh implementer + spec reviewer + code reviewer per bug |

## 10. Out-of-scope confirm

明確留將來 sub-phase（唔喺 debug branch 處理）：
- StreamingSession 抽離（除非 P0 連帶問題）
- Mac/Win 打包
- Mobile responsive layout
- i18n framework
- Storybook
- CI/CD GitHub Actions
- v4.0 backlog（CLAUDE.md 各 phase 結尾「Out-of-scope」section 列嘅嘢）

## 11. 成功標準（分兩級，user 喺 Phase 3a 揀）

### 11.1 Branch close — baseline（最低標準，預設目標）

- 4 sub-tracker 全部完成（Track A 真 assert / B env-gated 行齊或合理 N/A / C grep 結果 0 unintended residue / D harvest 完）
- Phase 2 master tracker consolidate 完成 + 全 finding 分類齊（severity + plan impact）
- **P0 100% close**（fix into debug branch / spec update commit / 新 sub-phase 開咗 plan / 確認 confirmed out-of-scope）
- **P1 至少 50% close** — 餘下 50% 入 deferred backlog 寫清楚 reason
- Debug branch fast-forward merge 返 `chore/asr-mt-rearchitecture-research`

### 11.2 Branch close — ambitious（拉高標）

- 上面所有 + **P1 100% close** + **P2 budget-driven**（user 設 budget，例如 1 個 session）

### 11.3 通用要求（兩級都需要）

- 每條 spec update commit 留低 audit trail：commit message 引用 BUG-NNN，被改 spec file 入面加 `### Updated 2026-05-XX: <reason> (BUG-NNN)` header
- 每條 fix commit message 包含 `Fixes: BUG-NNN`，tracker entry update `Linked commit` field
- Phase 3a decision 寫入 `docs/superpowers/debug/v4-phase3-decisions.md`，逐條 bug disposition 留 record

## 12. Spec amendment policy

呢個 spec 喺 debug branch 期間可能要 amend：

- **Minor scope tweak**（例如 Track A 補 1-2 個 scenario / severity 例子加多一條）：直接 inline 改加 `### Updated 2026-05-XX: <reason>` header，commit message `docs(v4 debug): spec amendment - <reason>`
- **Major scope change**（例如增 Track E / 改 4-phase 變 3-phase / abort gate threshold 大改）：返 brainstorming skill 重新諗，唔可以直接 inline 改

每次 amend bump revision 字眼（v2 → v3 ...）入 header。
