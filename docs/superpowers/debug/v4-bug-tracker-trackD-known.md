# Bug Tracker — Track D (Known-issue harvest)

**Track:** D
**Owner:** Main session (Phase 1 T10)
**Start:** 2026-05-18
**Status:** Complete — 4 sources harvested

---

## Schema

Each finding is one H2 section:

```
## BUG-NNN: <短描述>
- **Status**: Open / In progress / Fixed / Wontfix / Deferred
- **Severity**: P0 / P1 / P2 / P3 (will triage in Phase 2)
- **A-phase origin**: P1 / A1 / A3 / A4 / A5 / A6 / cross-phase
- **Layer**: backend / frontend / E2E / docs / config / build
- **Discovery source**: Track D
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

## Source 1: TODO/FIXME grep summary

Phase 0 baseline grep result: **0 actionable findings** in v4.0 production code (all 3 hits were "XXX" inside Chinese comment examples of Whisper training-data hallucination strings — not real TODO markers).

Conclusion: codebase is TODO/FIXME-clean. No tracker entries from this source.

---

## Source 2-A: v4.0 A6 explicit out-of-scope (CLAUDE.md A6 entry末段)

### BUG-D001: StreamingSession class仍 inline 喺 app.py (~150 行)

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A6
- **Layer**: backend
- **Discovery source**: Track D — CLAUDE.md A6 entry "Out-of-A6 scope" list
- **Repro steps**: `grep -n "class StreamingSession" backend/app.py` — confirms 仍 inline 約 150 行
- **Expected**: StreamingSession 抽離成獨立 module（例如 `backend/streaming.py`），由 bootstrap conditionally wire when `WHISPER_STREAMING_AVAILABLE`
- **Actual**: 仍 inline 喺 `app.py`，係 A6 C2 multi-file refactor 後唯一冇拆出嘅 class
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Suggested fix**: A7+ housekeeping branch 抽離；非阻 v4.0 ship
- **Linked commit**: (N/A — out-of-scope)

### BUG-D002: Mac/Win packaging 未做

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: cross-phase
- **Layer**: build
- **Discovery source**: Track D — CLAUDE.md A6 entry "Out-of-A6 scope"
- **Repro steps**: 冇 macOS .dmg / Windows .msi 或 PyInstaller spec
- **Expected**: 用戶可一鍵安裝（PyInstaller / py2app / electron-builder 等）
- **Actual**: 仍要手動 `./setup.sh` + `./start.sh`
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Suggested fix**: 獨立 release engineering phase；非阻 LAN deployment
- **Linked commit**: (N/A — out-of-scope)

### BUG-D003: Mobile responsive layout 未做

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A3 / A4
- **Layer**: frontend
- **Discovery source**: Track D — CLAUDE.md A6 entry "Out-of-A6 scope"
- **Repro steps**: Frontend Tailwind config 用 default breakpoint，但 Proofread page + Pipelines drag-sort 同 video panel layout 都係 desktop-only
- **Expected**: ≤768px viewport 可用嘅 stacked / drawer layout
- **Actual**: 細螢幕無 responsive 處理
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Suggested fix**: 獨立 mobile UX phase；v3.12 Phase 4 落咗 vanilla CSS responsive，A3 React 重寫之後 reset 返做未做
- **Linked commit**: (N/A — out-of-scope)

### BUG-D004: i18n framework 未引入

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A3
- **Layer**: frontend
- **Discovery source**: Track D — CLAUDE.md A6 entry "Out-of-A6 scope"
- **Repro steps**: 冇 react-i18next / next-intl / 任何 i18n lib；所有 UI string hardcoded 廣東話 / 繁體
- **Expected**: 廣東話 / 繁體中文 / 英文三語 toggle
- **Actual**: hardcoded
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Suggested fix**: 獨立 phase；目標用戶為香港廣播專業，廣東話 default 可接受
- **Linked commit**: (N/A — out-of-scope)

### BUG-D005: Storybook 未引入

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A3 / A4
- **Layer**: frontend
- **Discovery source**: Track D — CLAUDE.md A6 entry "Out-of-A6 scope"
- **Repro steps**: 冇 `.storybook/` directory；冇 `*.stories.tsx` file
- **Expected**: shadcn primitives + Proofread 14 components 有 Storybook for visual regression / isolated dev
- **Actual**: 冇
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Suggested fix**: 獨立 phase；當 component lib 穩定再加
- **Linked commit**: (N/A — out-of-scope)

### BUG-D006: CI/CD GitHub Actions 未配置

- **Status**: Open
- **Severity**: P2
- **A-phase origin**: cross-phase
- **Layer**: build
- **Discovery source**: Track D — CLAUDE.md A6 entry "Out-of-A6 scope"
- **Repro steps**: 冇 `.github/workflows/*.yml`；commit / PR 無自動 pytest + vitest + playwright + build gate
- **Expected**: Push to PR → run backend pytest + frontend vitest + tsc + playwright suite + build；fail prevents merge
- **Actual**: 純人手跑 + 上 main 之前要記住 verify
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Suggested fix**: 獨立 CI/CD phase；v4.0 ship 之後做。**Note**: 呢個係 6 個 confirmed-out-of-scope 入面最影響 production safety 嘅一條（無 CI gate = regression risk）— 但 spec §10 明確排除 v4.0 範圍。
- **Linked commit**: (N/A — out-of-scope)

---

## Source 2-B: v4.0 A5 deferred (CLAUDE.md A5 entry末段)

### BUG-D007: Legacy Socket.IO emitter event names cleanup

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: A5
- **Layer**: backend
- **Discovery source**: Track D — CLAUDE.md A5 "Out-of-scope" — "legacy Socket.IO `subtitle_segment` / `translation_progress` / `pipeline_timing` event emitters"
- **Repro steps**: `grep -rn "subtitle_segment\|translation_progress\|pipeline_timing" backend/` — 確認 emitter 已被刪
- **Expected**: CLAUDE.md "WebSocket events" table 移除呢三個 dead event 行
- **Actual**: A5 commit 已刪 emitter，但 docs 仲列住三個 dead event；frontend `socket-events.ts` 內 type union 可能仲含住相關 type
- **Plan impact**:
  - [x] 純 bug fix (docs cleanup)
- **Suggested fix**: 更新 CLAUDE.md "WebSocket events (server → client)" table；grep frontend type union 順手刪 dead type
- **Linked commit**: (Phase 3b 填寫)

---

## Source 2-C: v3.14 Phase 6 backlog（CLAUDE.md v3.14 entry 末段 audit 2026-05-13）

### BUG-D008: faster-whisper BatchedInferencePipeline 未試

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: cross-phase（v3.x 遺留，A1 stage executor 用緊舊 API）
- **Layer**: backend
- **Discovery source**: Track D — CLAUDE.md v3.14 末段 "📋 Still backlog"
- **Repro steps**: `backend/asr/whisper_engine.py` 仍用 `WhisperModel().transcribe()` 序列 API；faster-whisper 4.0+ 加入 `BatchedInferencePipeline` 可一次過跑 multi-segment
- **Expected**: 大型 audio file ASR 速度提升（benchmark 報 30-50%）
- **Actual**: 仍序列；需驗證新 API 喺 real-audio quality 同等
- **Plan impact**:
  - [x] Defer 入 backlog
- **Suggested fix**: 獨立 ASR perf optimization phase；需 real-audio validation 因為 batched 同 sequential 可能有 quality drift
- **Linked commit**: (Phase 3b 填寫)

### BUG-D009: `/api/translation/engines` Ollama probe timeout 缺 HTTP timeout + memoization

- **Status**: Open
- **Severity**: P2
- **A-phase origin**: cross-phase（v3.x 遺留）
- **Layer**: backend
- **Discovery source**: Track D — CLAUDE.md v3.14 末段 "📋 Still backlog" — "994ms outlier observed"
- **Repro steps**: `time curl http://localhost:5001/api/translation/engines` — 第一次 hit 觸發 Ollama API probe，無 HTTP timeout 限制可以 hang
- **Expected**: probe 有 1-2s timeout + 60s memoization cache
- **Actual**: 每次 endpoint hit 都打 Ollama；Ollama down 時 endpoint 可能 hang 數十秒
- **Plan impact**:
  - [x] 純 bug fix
- **Suggested fix**: `engines.py` blueprint 加 `requests.get(..., timeout=2)` + `functools.lru_cache(maxsize=1)` 並用 ttl_cache
- **Linked commit**: (Phase 3b 填寫)

---

## Source 2-D: v3.18 Stage 3+ deferred features（CLAUDE.md v3.18 entry "Out-of-scope"）

呢個 source 嘅 entries 全部係**Confirmed out-of-scope**（未來 stage 3+ 計劃，唔關 v4.0 ship 事）：

### BUG-D010: Domain context anchor (per-file 1-2 sentence subject prefix)

- **Status**: Open
- **Severity**: P3
- **A-phase origin**: cross-phase（v3.18 Stage 3+）
- **Layer**: backend
- **Discovery source**: Track D — CLAUDE.md v3.18 末段 "Out-of-scope (deferred to Stage 3+)"
- **Repro steps**: 無
- **Expected**: 每個 file 可以加 1-2 句 domain context 作為 MT prompt prefix，幫 LLM 識別主題（例：「呢段係2026 NBA Finals 第3場」）
- **Actual**: 只有 per-pipeline prompt override，冇 per-file context anchor
- **Plan impact**:
  - [x] Confirmed out-of-scope
- **Linked commit**: (N/A)

### BUG-D011: Forbidden phrases list (negative vocabulary constraint)

- **Status**: Open / **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend
- **Discovery**: CLAUDE.md v3.18 Stage 3+ deferred
- **Plan impact**: [x] Confirmed out-of-scope
- **Note**: Stage 2 已做 anti-formulaic 規則；Stage 3+ 加 explicit forbidden list

### BUG-D012: User self-service prompt template publishing (admin-only in Stage 2)

- **Status**: Open / **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend
- **Discovery**: CLAUDE.md v3.18 Stage 3+ deferred
- **Plan impact**: [x] Confirmed out-of-scope

### BUG-D013: Glossary stacking (multi-glossary per pipeline)

- **Status**: Open / **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend
- **Discovery**: CLAUDE.md v3.18 Stage 3+ deferred
- **Plan impact**: [x] Confirmed out-of-scope

### BUG-D014: Per-file retry strategy (empty / over-cap fallback config)

- **Status**: Open / **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend
- **Discovery**: CLAUDE.md v3.18 Stage 3+ deferred
- **Plan impact**: [x] Confirmed out-of-scope

### BUG-D015: A/B prompt comparison (run same file with 2 prompts side-by-side)

- **Status**: Open / **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend + frontend
- **Discovery**: CLAUDE.md v3.18 Stage 3+ deferred
- **Plan impact**: [x] Confirmed out-of-scope

### BUG-D016: s2hk simplified-Chinese leak post-process

- **Status**: Open / **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend
- **Discovery**: CLAUDE.md v3.18 Stage 3+ deferred
- **Note**: v3.8 已做 ASR s2hk via cn_convert；呢個 entry 係 **MT side** 嘅 s2hk leak detection（LLM 偶然輸出簡體字嘅 post-fix）。獨立於 ASR side。
- **Plan impact**: [x] Confirmed out-of-scope

### BUG-D017: ASR-side fragment merge (Stage 1, intentionally skipped per user direction)

- **Status**: Closed (intentionally skipped)
- **Severity**: P3 / **A-phase**: cross-phase / **Layer**: backend
- **Discovery**: CLAUDE.md v3.18 末段 — "explicitly skipped per user direction"
- **Note**: v3.8 已落 `merge_short_segments`，但呢個 Stage 1 feature 係更激進嘅 sentence-level merge；user 已決定 skip
- **Plan impact**: [x] Confirmed out-of-scope

---

## Source 3: Recent commit messages

`git log --since="2026-05-15" --grep="TODO|FIXME|defer|known issue|out-of-scope|留將來"` — 0 escape-hatch wording 喺非-debug commits（只 match 到呢個 branch 自己嘅 commit）。

Conclusion: v4.0 implementer commits gunzhing，冇遺留 inline TODO comment 喺 commit message 度。

---

## Source 4: v4.0 backlog enumerated

已喺 Source 2-A 全部 cover（6 items：StreamingSession / packaging / mobile / i18n / Storybook / CI/CD）。

---

## Track D Summary

- **Total entries**: 17
- **Confirmed out-of-scope** (informational audit trail): 12 (D001-D006, D010-D016)
- **Defer 入 backlog**: 1 (D008 faster-whisper batched)
- **純 bug fix**: 2 (D007 docs cleanup, D009 Ollama probe timeout)
- **Closed (intentionally skipped)**: 1 (D017)
- **Cross-reference**: 1 P2 entry (D006 CI/CD) flagged as most production-impact among out-of-scope items, but still out-of-scope per spec §10

呢 17 entries 唔係新發現嘅 bug — 係已 documented 嘅 deferral，列入 tracker 提供 audit trail，避免 Phase 1 其他 track 重複發現嘅時候要從頭評。
