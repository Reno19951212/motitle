# v4.0 Debug Branch — E2E Bug Hunt + Triage Design

**Date:** 2026-05-18
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
Phase 0: Setup       (~30 min)  ─ 創 branch + bug tracker + matrix doc
Phase 1: Discovery   (3 並行 track) ─ Playwright 補洞 / Manual matrix / 靜態掃描
Phase 2: Triage      ─ 全部 bug 入 tracker，分 P0-P3 + plan impact
Phase 3: Re-brainstorm + Targeted fix ─ 同 user 對 triage 結果決定走向
```

## 4. Phase 0 — Setup

### 4.1 Branch checkout

```
git checkout chore/asr-mt-rearchitecture-research
git pull --ff-only
git checkout -b debug/v4-e2e-bug-hunt
```

### 4.2 Bug tracker doc

新 `docs/superpowers/debug/v4-bug-tracker.md` — 每條 bug 一個 H2 section，schema：

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
- **Plan impact**:
  - [ ] 純 bug fix（落入呢個 branch 即可）
  - [ ] Spec 假設錯（需更新原 A?-design.md，列明哪個 §）
  - [ ] 需開新 sub-phase（A7/A8）
  - [ ] Defer 入 backlog
- **Suggested fix**: <approach>
- **Linked commit**: (填寫修復 commit SHA)
```

### 4.3 E2E matrix doc

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

## 5. Phase 1 — Discovery（3 條並行 track）

每條 track 由獨立 fresh subagent 跑（context 隔離 + 真並行 + 唔污染主 session）。

### 5.1 Track A — Playwright suite 補洞 + 啟用 graceful-skip

**現狀**：A6 C3 加入 5 個新 spec，全部用 graceful-skip pattern（admin password 唔啱 / seed data 缺 → `test.skip`）。實際 CI / dev 環境多數 skip 多過 run。

**動作**：
1. 加 fixture 自動 bootstrap：admin user `e2e-admin` / password `TestPass1!` + seed 1 個 ASR profile + 1 個 MT profile + 1 個 glossary + 1 個 pipeline
2. 移除全部 `test.skip` graceful guard，spec 必須 actually assert
3. 補種未 cover 嘅 critical path scenario：
   - **happy-path-pipeline.spec.ts**：upload → pipeline_run → ASR done → MT done → glossary scan → render（end-to-end E2E）
   - **pipeline-broken-refs.spec.ts**：刪 ASR profile 後 pipeline 顯示 `broken_refs` badge
   - **proofread-stage-rerun.spec.ts**：edit segment → rerun stage → stage history sidebar 顯示新 version
   - **proofread-prompt-override.spec.ts**：save override → re-translate → 新 prompt actually 入 LLM call
   - **multi-user-isolation.spec.ts**：user A 開 file，user B login 唔睇到
   - **cancel-running-job.spec.ts**：long pipeline → click cancel → UI 顯示 cancelling → status flip cancelled
4. 跑全 suite，所有新 spec 必須真 pass，所有 bug 入 tracker

### 5.2 Track B — Manual E2E matrix

Playwright 難覆蓋嘅高風險場景，由真實 model + binary 跑：

**真實 ASR**
- mlx-whisper medium model 跑一段廣東話 + 一段英文 + 一段中英混合
- 確認 cn_convert s2hk flag 真正 trigger，輸出全繁體
- 確認 `merge_short_segments` 唔再產 1-word fragment
- 確認 `initial_prompt` 真正 bias decoder

**真實 MT**
- Ollama + qwen3.5-35b-a3b：跑 single-segment mode（`batch_size=1`）+ batched mode + parallel_batches=4
- OpenRouter（如有 API key）：跑 claude-sonnet + gpt-4o-mini 比較
- prompt override 真正 inject 入 LLM payload 確認
- translation_passes=2 enrich pass 真正 trigger 確認

**真實 FFmpeg render**
- MP4：CRF / CBR / 2-pass 三 mode 各燒一條，verify pixel_format + profile + level cross-field validation
- MXF ProRes：6 個 profile（Proxy/LT/Standard/HQ/4444/4444XQ）各燒一條
- XDCAM HD 422：10 / 50 / 100 Mbps 各燒一條
- 全部用 ffprobe 確認 metadata correct

**WebSocket reliability**
- 跑 pipeline 中段 toggle network（DevTools throttle / kill server / refresh page）
- Verify stage progress event 唔丟失 / 重連後 state restore

**Bundle code-split runtime**
- 跑 `npm run build` + serve dist
- DevTools Network tab：first paint 只 load entry + vendor-react + Login chunk
- Navigate 去 /pipelines → vendor-dnd lazy load
- 慢 3G throttle 體驗確認 PageLoader fallback 唔閃

**Structured logging**
- `LOG_JSON=1 LOG_LEVEL=DEBUG python app.py` 跑完整 pipeline
- 確認 X-Request-ID 由 inbound HTTP → log line → 子 thread 都貫穿
- 確認 ApiError exception 真正 render 做 JSON 唔係 HTML 500 page

### 5.3 Track C — 靜態掃描

A5 大手術後嘅遺留檢查：

```bash
# Dead reference 掃描
grep -rn "from translation.alignment_pipeline" backend/
grep -rn "from translation.sentence_pipeline" backend/
grep -rn "from translation.post_processor" backend/
grep -rn "from profiles import" backend/
grep -rn "_auto_translate\|transcribe_with_segments\|_asr_handler\|_mt_handler" backend/
grep -rn "frontend.old" .

# Type checking
cd frontend && npx tsc --noEmit
cd backend && python -m mypy . --ignore-missing-imports || true

# Dead code
cd backend && python -m vulture . --min-confidence 80 || true
cd frontend && npx ts-prune || true

# ESLint
cd frontend && npm run lint
```

任何 warning / dead reference 入 tracker。

## 6. Phase 2 — Triage

每條 bug 入 tracker 之後依 schema 填 severity + plan impact。Severity 標準：

| Severity | 標準 |
|---|---|
| **P0 blocker** | 阻 ship 入 main：data loss / auth bypass / 完全 crash / 主流程行唔通 |
| **P1 high** | 用戶實際會撞：核心功能壞但唔崩 / 數據 incorrect / UX 嚴重壞 |
| **P2 medium** | Edge case：少數 path / 特定 config / 警告但唔阻 |
| **P3 nice-to-fix** | Code smell / refactor opp / docs typo |

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

## 11. 成功標準

- 全部 A1-A6 surface 經過 E2E 真正 assert（Playwright 唔再 skip / manual matrix 行齊）
- 全部 finding 入 tracker doc，分類完整
- Re-brainstorm 完用戶確認每條 bug 嘅 disposition
- P0 + P1 bug 全部 fix（commit 入 debug branch）或 spec update / 新 sub-phase decision 落實
- Debug branch ready 之後可 fast-forward merge 返 parent
- 任何 spec update commit 留低 audit trail（明確 "Updated 2026-05-XX" header）
