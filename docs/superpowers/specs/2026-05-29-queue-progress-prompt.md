# /goal Prompt — Right-side Queue Panel Per-state Progress Bar with Forward-Compatible Pipeline Contract

> **使用方法**：直接 copy `# Goal` 開始至 `# Out of Scope` 完整內容，paste 入 `/goal` 即可。
>
> **建立時間**：2026-05-29
> **架構作者**：Reno + Claude (brainstorming)
> **目標 deliverable**：右側 queue panel 嘅 per-state 0–100% progress bar + 統一 pipeline progress contract + canonical architecture doc

---

# Goal

主頁右側 queue panel 每個 row，根據佢對應 file 嘅處理階段（per-pipeline 自己定義）顯示接近實時嘅 0–100% 進度條，令 user 一眼睇到 video 處理到邊一個 stage、stage 內仲剩幾耐。

**Architecture 必須兼容**：(a) 舊有 Profile 模式、(b) V6 Dual-ASR Pipeline、(c) 未來新增嘅 pipeline kind — frontend 對 pipeline 內部結構 **零** awareness，全部新 pipeline 只需要 emit 一個 unified event 就可以 plug-in。

# Execution Approach

呢個 prompt 入面所有實作工作必須用 **subagent-driven development**（`plugin:superpowers:subagent-driven-development`），由 controller agent 派 task 畀 subagent 去寫。

**Model 分配**：

| Role | Model | 原因 |
|---|---|---|
| Controller（plan + dispatch + integration） | Opus 4.7 | 全局 architecture awareness、coordination |
| Implementer subagent | **Sonnet 4.6** | Spec 清楚、屬於 mechanical implementation；cost / speed 平衡 |
| Spec compliance reviewer | Opus 4.7 | 確保 spec gap 一個都唔走甩 |
| Code quality reviewer | Opus 4.7 | Architecture invariant + future-compat 守門 |

**Per-task flow**（subagent-driven-development skill 標準）：
1. Controller 抽 task → 派畀 Implementer subagent (Sonnet 4.6)
2. Implementer TDD → commit
3. Spec reviewer (Opus) 對 spec
4. Code quality reviewer (Opus) 對架構
5. Fix loop 直到兩個 review 都綠
6. 下一 task

**Continuous execution**：除非 BLOCKED、要 clarification、或者全部 task 完成，唔好停低問 user「要唔要繼續」。

# Project Context

whisper-subtitle-ai 廣播字幕 pipeline。技術棧：Flask + Flask-SocketIO backend、vanilla HTML/JS frontend、faster-whisper/mlx-whisper ASR、Ollama/OpenRouter 翻譯。

## 現有兩種 pipeline kind

| Kind | Backend handler | File state lifecycle | Native socket events |
|---|---|---|---|
| `profile`（舊） | `_asr_handler` → `_mt_handler`（兩個 job） | `uploaded → transcribing → done(asr) → translating → done` | `subtitle_segment {progress}`, `transcription_progress {elapsed}`, `translation_progress {percent}` |
| `pipeline_v6`（新） | `_asr_handler` → `PipelineRunner._run_v6`（單 job、5 內部 stage：VAD → Qwen3-ASR ∥ mlx-whisper → time-anchored merge → Refiner LLM → persist） | `uploaded → transcribing → done`（無 translating） | `pipeline_stage_start`, `pipeline_stage_progress`, `pipeline_stage_done`, `pipeline_complete_v5` |
| `<future>` | TBD | TBD | TBD |

**問題**：而家 frontend queue-panel 對任何一個 kind 都唔知個 progress 點計，更加唔可能識別 V6 嘅 internal stage 進度。

## 現有右側 queue panel

`frontend/js/queue-panel.js`：3s polling `/api/queue` + listen `queue_changed`（zero-payload trigger 純為 refetch）。Row schema：`#位置 類型 file_name owner status [×]`，**冇 % bar、冇 stage label**。

# Unified Progress Contract（架構核心）

## 新 socket event：`pipeline_progress`

每個 pipeline kind 都必須 emit 呢個 event；frontend 只 listen 呢一個。

```typescript
type PipelineProgress = {
  file_id: string;
  job_id: string;
  pct: number | null;              // 0-100; null = idle/queued
  stage_label: string;             // pipeline kind 自己定: 「轉錄中」/「Qwen3 識別中」/「Refiner 校對中」
  stage_state: 'idle' | 'active' | 'done';
  pipeline_kind: string;           // 'profile' | 'pipeline_v6' | <future>
}
```

**Backend emission frequency**：active stage 每 ≥ 500ms 一次或 pct 變化 ≥ 1% 時 emit。

## `/api/queue` row schema 擴充（cold-start fallback）

每 row 新加 3 個 field：

```typescript
{
  ...existing fields,
  progress_pct: number | null,
  stage_label: string | null,
  stage_state: 'idle' | 'active' | 'done',
}
```

呢三個 field 由 backend 新 module `backend/progress_adapter.py` 嘅 `_progress_cache: Dict[file_id, ProgressSnapshot]` 提供（in-memory，server restart 後 cold-start 流程同其他 cache 一樣 rebuild）。

## Adapter shim（backend 新 module）

`backend/progress_adapter.py`：
- 訂閱 Profile native events (`subtitle_segment` 等) → 計算 pct → 寫入 `_progress_cache` → emit `pipeline_progress`
- 訂閱 V6 native events (`pipeline_stage_*`) → 將 5 個內部 stage 映射做 single 0–100% → emit `pipeline_progress`
- Profile 模式預設 stage label mapping（`transcribing → "轉錄中"`、`translating → "翻譯中"`）
- V6 模式 stage label 由 stage emit 自帶（`stage_id → label` 表喺 PipelineRunner）

# State→Display Mapping（frontend 用）

| `stage_state` | `pct` | Row 顯示 |
|---|---|---|
| `idle` | null | 動畫 spinner dot，label = `stage_label` 或預設「排隊中」 |
| `active` | 0–99 | Progress bar + pct 數字 + label |
| `active` | 100 | 滿 bar，等下個 event 或 `queue_changed` 移除 row |
| `done` | 100 | 滿 bar 顯示 ~2 秒後 auto-hide row |

# Acceptance Criteria

- [ ] Profile 模式跑 ASR：queue row 由 0% 升到 100% 全程可見
- [ ] Profile 模式跑 MT：queue row 由 0% 升到 100% 全程可見、stage_label 變「翻譯中」
- [ ] V6 模式跑：queue row 全程顯示 5 個內部 stage 嘅整合 0–100%，stage_label 反映當前內部 stage 名（VAD / Qwen3 / mlx-whisper / Merge / Refiner）
- [ ] Cold-start：reload page 時 row 即時 show backend cache 嘅 pct（非 0）
- [ ] 跨 tab 同步：tab A 跑緊 50% 時開 tab B，B 即時 show 50%
- [ ] 假新 pipeline 加入測試：寫一個 dummy `pipeline_v99` handler，**只** emit `pipeline_progress`、唔加任何 frontend code，row UI 一樣可以正常 render
- [ ] Phase A 24/24 regression 維持綠
- [ ] Documentation: `docs/superpowers/architecture/pipeline-progress-contract.md` 寫好；CLAUDE.md「Architecture」加新 sub-section + 「Completed Features」加版本條目；兩者同 code change 同 PR

# Implementation Constraints

**Backend 新加**：
- `backend/progress_adapter.py` — Adapter module + `_progress_cache` + 兩個 shim subscribers
- `backend/app.py` `/api/queue` handler — 每 row attach `progress_pct` / `stage_label` / `stage_state`
- `backend/pipeline_runner.py` — V6 native events 加多 `stage_label` field（如果未有）

**Backend 必須唔可以改**：
- Native events `subtitle_segment` / `translation_progress` / `pipeline_stage_*` 嘅 payload shape（其他 listener 包括 dashboard 字幕 overlay、proofread 即時更新依賴緊）
- `_file_registry` schema
- `queue_changed` event remains zero-payload trigger

**Frontend 改動**：
- `frontend/js/queue-panel.js` — 加 `socket.on('pipeline_progress')` listener、`_progressCache: Map<file_id, snapshot>`、render row 加 bar/spinner UI
- `frontend/index.html` — queue-panel CSS（bar/spinner 樣式），其他 dashboard 邏輯**不動**

**Forward-compat hard rule**：
- 加 V7（or any future pipeline kind）時，**只需** 改 backend：handler emit `pipeline_progress`（或者寫 V7 shim 訂閱 V7 native events）
- Frontend queue-panel.js **零修改**
- 呢個 invariant 寫入 acceptance criteria 嘅 dummy `pipeline_v99` 測試

# Documentation Deliverables

呢個架構嘅 canonical reference 同 future modification awareness 透過兩層文件保證：

## Layer 1：完整 contract spec（新檔）

**檔案**：`docs/superpowers/architecture/pipeline-progress-contract.md`

**內容**：
- Architecture diagram（mermaid 或 ASCII）— Backend native events → Adapter → unified contract → frontend
- `pipeline_progress` event 完整 TypeScript-style payload schema + field semantics
- `/api/queue` 新 fields 完整 schema
- Stage label convention — Profile / V6 各自嘅預設 mapping table、未來 pipeline 點樣定 stage_label
- Throttle / cache 行為（500ms、cache expire、cold-start 邏輯）
- **「點樣加新 pipeline kind」step-by-step recipe**：(1) handler 點 emit `pipeline_progress`（2）要唔要寫 shim（3）要唔要改 frontend → 答案永遠係「frontend 零修改」
- 已知 invariant（zero-payload `queue_changed`、native events 唔可以改 etc.）

## Layer 2：CLAUDE.md 入口（修改現有檔案）

`CLAUDE.md` 必須兩處改動：

**(a) 「Architecture」 section 加新 sub-section**：

```markdown
### Pipeline Progress Contract（v3.20+）

統一 progress 訊號 contract，畀所有 pipeline kind（Profile / V6 / 未來）共用。
詳見 [docs/superpowers/architecture/pipeline-progress-contract.md](docs/superpowers/architecture/pipeline-progress-contract.md)。

**核心 invariants**：
- 新增 pipeline kind 時，frontend `queue-panel.js` **零修改** — 全部變化集中喺 backend handler 或 adapter shim
- Native events (`subtitle_segment`, `pipeline_stage_*`) 唔可以改 payload，只可以加 field
- `queue_changed` 永遠 zero-payload，純 trigger refetch
```

**(b) 「Completed Features」 section 加新版本條目** describing 呢次 ship（用同其他 v3.x 條目一樣嘅 format）。

## 為何兩層

| 層 | 目的 | Load 時機 |
|---|---|---|
| Layer 1（architecture doc） | Canonical truth、深度 reference、recipe | On-demand（被 CLAUDE.md 引導去揾） |
| Layer 2（CLAUDE.md） | 永遠喺 Claude context；確保未來修改一定知有呢個 contract 存在；invariant 一眼睇到 | 每 session 自動 load |

# Test Plan

**Backend pytest**（`backend/tests/test_progress_adapter.py` 新檔，~10 case）：
1. Profile shim：emit `subtitle_segment progress=0.5` → `pipeline_progress pct=50, stage_label="轉錄中"` 出
2. Profile shim：emit `translation_progress percent=80` → `pipeline_progress pct=80, stage_label="翻譯中"` 出
3. V6 shim：5 個 stage emit 之後 pct 順序去 20/40/60/80/100
4. V6 shim：`stage_label` 跟 native event 走，Profile shim 用預設 mapping
5. `_progress_cache` 喺 stage_done 之後保留 pct=100 給 cold-start
6. `/api/queue` 對 active file 返 `progress_pct` 非 null
7. `/api/queue` 對 `uploaded` file 返 `progress_pct: null, stage_state: 'idle'`
8. Throttle：500ms 內多次 emit 只出最後一個 `pipeline_progress`
9. Dummy `pipeline_v99` 直接 emit `pipeline_progress` → cache + queue route 正常 work
10. `_progress_cache` cleanup：file done 後 ~30s expire

**Playwright**（`frontend/tests/test_queue_progress.spec.js` 新檔，5 case）：
1. Profile ASR：bar 由 0% → 100%
2. Profile MT：stage_label 切換「翻譯中」、bar reset 0% → 100%
3. V6：stage_label 5 個內部 stage 名依次出現、bar monotonic 上升
4. Cold-start：page reload 中段 → bar 立即非 0
5. Dummy `pipeline_v99`（mock socket emit）→ row 一樣 render bar，**frontend 零改動**

**Manual smoke**（PR description）：
- Profile 跑 1 條 video：「排隊中 dot → 轉錄中 0–100% → 待翻譯 dot → 翻譯中 0–100% → 完成 100%」
- V6 跑 1 條 video：「排隊中 dot → VAD 切段中 → Qwen3 識別中 → mlx 對齊中 → Merge → Refiner 校對中 → 完成」
- Reload page 中段：bar 即時非 0

# Out of Scope

- 左側 file card 嘅 progress（呢個 prompt 只 cover 右側 queue panel）
- Overall pipeline 0–100% 加權（per-state 模式已定）
- 重新設計 4 大 file state badge label（v3.10 已穩定）
- Render job 嘅 progress（render 有獨立 polling）
- 改 `queue_changed` payload（必須保持 zero-payload trigger）
- V6 5 個 internal stage 嘅 sub-bar（只 expose 整合 0–100%；想睇 sub-stage 嘅可以 hover stage_label tooltip — out of scope of MVP）
