# Console Redesign — Implementation Plan

**Branch:** `feat/phase-1-frontend-design`
**Spec source:** `~/Downloads/design_handoff_motitle_dashboard/` (README + variant-console.jsx + reimagine.css + styles.css)
**Target route:** `/console` (feature-flagged, NOT replacing `/`)
**Status:** Decisions locked 2026-05-22 — Q1=A / Q2=B / Q3=C / Q4=A / Q5=B / Q6=C. Awaiting go-ahead to dispatch.

---

## Decisions locked

| # | Decision | Impact |
|---|---|---|
| **Q1** | **A** — 純 CSS, `console.css`, 唔郁 tailwind.config | Stage 1 NO-OP；Console class 用 `.con-*` 命名 mirror reimagine.css |
| **Q2** | **B** — Backend ffprobe on upload + `duration_seconds` registry field + one-shot migration | **+1.5hr backend**：upload handler / FileRecord schema / migration script / tests |
| **Q3** | **C** — Backend pipeline schema 加 `preset_slot: 1\|2\|3\|4\|null` + per-user uniqueness | **+2hr backend + frontend**：v4 & v5 schema / validation / atomic swap PATCH endpoint / `/pipelines` page UI / Console reads from picker store filtered by slot |
| **Q4** | **A** — Read-only glossary display（current pipeline's active list） | 0 backend；Console aside 顯示 + tap 跳 `/glossaries/<id>` detail |
| **Q5** | **B** — Queue depth real，其餘 "—" placeholder | 0 backend；UI 顯示 dash labelled correctly |
| **Q6** | **C** — `VITE_CONSOLE=1` env (build) + `?console=1` query (runtime) | 兩層 gate；production 預設 tree-shake 走 Console code |

**Revised scope vs original plan：**
- ❌ ~~Backend MVP: 零改動~~ → **Backend MVP: ~3.5hr 新加工作**（Q2 ffprobe + Q3 preset_slot schema）
- ❌ ~~`usePresetSlotsStore` (frontend store)~~ → **DELETED**（Q3=C 用 backend persist 代替；frontend 讀 `usePipelinePickerStore.pipelines` filter by `preset_slot`）
- ✅ Console aside Glossary 改為 read-only display（跟 Q4=A）
- ✅ Time estimate revised: ~11hr → **~15hr** ≈ 2 工作日

---

## 0. Executive summary

廣播 Console 係一個 **4-column dense layout**（56 / 360 / 1fr / 320），目標係將 dashboard 由「上傳 + 列表」嘅 metaphor 轉做「always-on 廣播控制室」。

呢個 plan 將 handoff spec 對齊現有 `whisper-subtitle-ai/frontend/` codebase，覆蓋：

- 9 個新 component + 1 個改造 component（rail）
- 2 個新 zustand store / hook
- 1 個 optional 新 backend endpoint（metrics — 可 defer）
- Tailwind / CSS 策略偏離 PROMPT 嘅建議（**有 reality gap，需要決定**）
- 3 個新 e2e spec；現有 spec 0 個受影響（feature flag 保護 `/`）

⚠️ **Plan 入面有 6 個 reality gap** 同 design handoff spec 唔對齊，**需要你 review 之後決定**。Section 1 列晒。

---

## 1. Reality gaps（spec vs codebase）

### Gap 1 — Socket event names 唔啱

**Spec 寫**（README §Interactions table）：
| Event | Purpose |
|---|---|
| `transcribe_progress` | ASR fill |
| `transcribe_done` | ASR done |
| `translate_progress` | MT fill |
| `translate_done` | MT done |
| `render_progress` | Render fill |
| `render_done` | Render done |

**Codebase 實際 emit**（`backend/pipeline_runner.py` + `backend/socket_events.py`）：
| Event | Payload |
|---|---|
| `file_added` | `{...FileRecord}` |
| `pipeline_stage_start` | `{file_id, stage_index, stage_type, stage_ref, ...}` |
| `pipeline_stage_progress` | `{file_id, stage_index, percent}` |
| `pipeline_stage_done` | `{file_id, stage_index, status, ...}` |
| `pipeline_complete_v5` | `{file_id, languages, segments_per_lang}` |
| `queue_changed` | `{}` (refresh trigger) |

**Implication：** Console 唔可以直接 listen `transcribe_progress` — 要 derive stage type from `pipeline_stage_progress.stage_type` field（值：`asr` / `asr_primary` / `asr_secondary` / `asr_verifier` / `refiner:<lang>` / `translator:<src>_to_<tgt>` / `glossary` / `mt`）。`render_progress` 完全唔存在 — render 經 `POST /api/render` + poll `GET /api/renders/<id>` 機制（睇 `useRenderJob` hook）。

**建議：** 喺 `useWorkerStatus()` hook 入面用 `useSocket()` reducer state 衍生 ASR / MT / Render 三個 conceptual stages — 簡單 mapping：
- `stage_type` 含 `asr` → ASR position
- `stage_type` 含 `refiner` / `translator` / `mt` → MT position
- 第 3 位 (Proofread) 由 `approved_count / segment_count` derive
- 第 4 位 (Render) 由 render job state 而非 socket 帶（要新做 `useActiveRenders()` 或將 `useRenderJob` 抽通用）

### Gap 2 — Design tokens 已喺 motitle-bold.css 入面，唔喺 tailwind.config

**Spec 寫**（PROMPT §Stage 1）：「將 design/styles.css 嘅 :root 寫入 tailwind.config.ts」

**Codebase 實際：**
- `tailwind.config.ts` 嘅 `theme.extend.colors` 用 `hsl(var(--*))` bridge（無 hex value）
- `frontend/src/styles/motitle-bold.css` lines 8-57 喺 `.motitle-bold` selector 已經有 design handoff styles.css 嘅 **全部** token，數值一字不差：`--bg #0a0a0f` / `--accent #6c63ff` / `--accent-2 #a78bfa` / 全部 surface / text / accent / semantic / radius / shadow。

**Implication：** Stage 1「寫 tokens 入 tailwind.config」係 **redundant work** — token 已經 available。

**建議（要你決定 A / B / C）：**
- **A.** 跟現有 pattern：新 `src/styles/console.css` import 喺 `Console.tsx` 頂部，內裏全部 `.con-*` class（同 design handoff 嘅 `reimagine.css` 鏡像）。`motitle-bold.css` 唔郁。tailwind.config 唔郁。**最低風險**。
- **B.** 跟 PROMPT 字面：將 token 寫入 `tailwind.config.ts` `theme.extend`，新 component 用 Tailwind utility (`bg-surface-2 text-text-dim` etc.)。但要喺 `tailwind.config` 加 hex value（破壞現有 CSS-var-bridge pattern）。**Stack 不一致**。
- **C.** Hybrid：`tailwind.config` 加 `bg-bg / bg-surface / text-text-dim` etc. 但 value 仍然 `var(--bg)` `var(--surface)`，token 由 `motitle-bold.css`（或新 `:root` block in `console.css`）提供。Component 用 Tailwind class，token 仲喺 CSS-var 層。**最 idiomatic 但 setup 複雜少少**。

**Plan default：** A（最直接，符合 codebase pattern）。

### Gap 3 — File shape 同 mock data.jsx 唔啱

**Spec 寫**（data.jsx）：`f.transcribeProgress`, `f.translateProgress`, `f.renderProgress`, `f.size: "284 MB"` (string), `f.duration: "14:22"` (string), `f.uploaded: "剛剛"` (string), `f.approved: 0` (count number), `f.segments: 186`.

**Codebase 實際**（`lib/socket-events.ts` `FileRecord`）：
- `original_name: string` (NOT `name`)
- `size: number` (bytes — needs `formatBytes()`)
- `uploaded_at: number` (Unix epoch float — needs `formatRelative()`)
- `segment_count: number`, `approved_count: number`
- NO `transcribeProgress` / `translateProgress` / `renderProgress` field — progress 由 `pipeline_stage_progress` event 帶
- NO `duration` — backend 唔記 audio duration（要 reach 入 video metadata 或 ffprobe — 暫時冇）

**Implication：**
- Helper `toConsoleFile(file: FileRecord, progress: StageProgressMap): ConsoleFile` 將 FileRecord normalize 為 design shape
- `duration` field：**冇 source**。Plan：display "—" placeholder。Future work: backend 可以 ffprobe audio 出 duration 寫入 registry。

### Gap 4 — Preset pills 嘅 mapping 模糊

**Spec 寫**（variant-console.jsx ConPresets）：4 個 hardcoded preset：「新聞廣播 / 訪問 · 長片 / 體育直播 / 快速預覽」，每個 ⌘1-4。

**Codebase 實際：**
- `usePipelinePickerStore` 有 `pipelines: PipelineSummary[]` 同 `pipelineId: string | null`
- Pipeline 由 user 喺 `/pipelines` page 自由建立，無 fixed slot
- 冇「preset → pipeline」嘅 binding 概念

**Implication：** 4 個 preset 要 map 去 4 個 pipeline ID 先有用。3 個 option：
- **A.** 取 `pipelines[0..3]`（最簡單，但用戶可能有 1 個或者 10 個 pipeline）
- **B.** 新 store `usePresetSlotsStore`：4 個 slot，每個 nullable pipeline_id，localStorage persist，⌘1-4 切換，user 可以 right-click 設定。
- **C.** Backend pipeline schema 加 `preset_slot: 1 | 2 | 3 | 4 | null` 欄位，由 `/pipelines` page UI 控制。

**Plan default：** **B**（純 frontend store，零 backend 改動，user 揀第幾個 pipeline 入第幾個 slot）。
首次使用：自動將前 4 個 pipeline 填入 slot 1-4 做 onboarding default，user 可以 reset。

### Gap 5 — Glossary toggle 嘅 semantic 唔清

**Spec 寫**（README §Column 4 §B）：「Click toggles 啟用」— implying global active state per glossary。

**Codebase 實際：** Glossary 喺 pipeline 入面係 `glossary_stage.glossary_ids[]` array — 每 pipeline 各自指定。冇「global active glossary」概念。

**Implication：** "Toggle on/off" 喺 Console 邊個層次操作？
- **A.** Read-only：右 aside 純顯示 current pipeline 嘅 active glossary IDs，無 toggle action
- **B.** Edit current pipeline：toggle 會 PATCH `current pipeline.glossary_stage.glossary_ids`，影響全部用嗰個 pipeline 嘅 user
- **C.** 本檔 override：toggle 設定 file-level prompt_overrides，只影響 selected file（要 backend 改 schema）

**Plan default：** **A**（read-only display）— spec 唔清就先做最 conservative，避免 unexpected mutation。

### Gap 6 — Metrics bar 數值無 backend source

**Spec 寫**（README §Workbench §B）：4 個 metric — ASR 0.42× RT / MT 142 tok/s / GPU 68% / 佇列 3 待處理。

**Codebase 實際：** 全部 placeholder。`/api/system/health` endpoint 唔存在。`asr_seconds` 喺 file registry 入面（per-file complete metric，唔係即時 throughput），冇 GPU monitoring。

**Plan default：**
- **MVP（Phase 1）：** 「佇列 X 待處理」**可以做**（由 `/api/queue` length derive）。其餘 3 個 metric 顯示 "—" placeholder 或者完全唔 render（feature flag）。
- **Phase 2（optional Stage 9）：** 新 `GET /api/system/health` endpoint return `{queue_depth, updated_at}`，ASR/MT/GPU 留 null 顯示 "—"。Backend 內收集 GPU usage 唔喺 Phase 1 scope。

---

## 2. Files to CREATE

| Path | Purpose | Notes |
|---|---|---|
| `frontend/src/pages/Console.tsx` | Console entry — 4-col grid composition root | imports `./Console/*` 子 component |
| `frontend/src/pages/Console/Rail.tsx` | 56px icon nav（Console scope） | 唔改造 `BoldRail.tsx`；新 component 用 `motitle-icons` 嘅 icon |
| `frontend/src/pages/Console/QueueColumn.tsx` | 360px col — Queue head + Drop + List + Worker Status | sub-composition |
| `frontend/src/pages/Console/QueueItem.tsx` | Single file row with 4-segment stage bar | named export `QueueItem` |
| `frontend/src/pages/Console/StageBar.tsx` | 4-cell stage bar primitive | derives cell states from `ConsoleFile` |
| `frontend/src/pages/Console/WorkerStatus.tsx` | 「處理中」cards + 「待處理」numbered list | consumes `useWorkerStatus()` hook |
| `frontend/src/pages/Console/Workbench.tsx` | Topbar + MetricsBar + Video + Transport + Transcript | sub-composition root |
| `frontend/src/pages/Console/PresetPills.tsx` | 4 pills `⌘1-4` + 「設定 / 執行佇列」action buttons | consumes `usePresetSlotsStore` + `useHotkeys` |
| `frontend/src/pages/Console/MetricsBar.tsx` | 服務正常 chip + 4 mini metric strips | MVP: queue_depth real, others "—" |
| `frontend/src/pages/Console/VideoPanel.tsx` | Black bg + safe grid + PVW label + timecode + live cap | reuse pattern from Proofread `VideoPanel.tsx` 但更精簡 |
| `frontend/src/pages/Console/TransportBar.tsx` | Play/pause / timecode / scrub / VU meter | new |
| `frontend/src/pages/Console/TranscriptList.tsx` | Read-only segments table with ts/en/zh/marker | derives from `useDashboardTranslations(fileId, activeLang)` |
| `frontend/src/pages/Console/AsideColumn.tsx` | 320px col — Pipeline cards + Glossary list + 本檔資訊 | sub-composition root |
| `frontend/src/pages/Console/PipelineStageCards.tsx` | 3 stacked cards: ASR / MT / Output | reads selected pipeline from picker store |
| `frontend/src/pages/Console/GlossaryToggleList.tsx` | Read-only list of glossaries（Gap 5 = option A） | `/api/glossaries` + show active state from current pipeline |
| `frontend/src/pages/Console/FileFactsBlock.tsx` | Key-value list — 時長 / 段數 / 已批核 / etc | derives from selected file (uses Q2's `duration_seconds`) |
| `frontend/src/hooks/useWorkerStatus.ts` | Derives `activeJobs` + `queuedJobs` + errored | poll `/api/queue` @ 3s + listen `queue_changed` event |
| `frontend/src/hooks/useHotkeys.ts` | Tiny global keymap hook | accepts `Record<string, () => void>`，cleanup on unmount |
| `frontend/src/styles/console.css` | All `.con-*` class scoped under `.console` root | mirror reimagine.css structure，唔修改 motitle-bold.css |
| `frontend/tests-e2e/console.spec.ts` | Playwright spec covering rail / queue / worker status / preset pills / transcript | data-testid based |
| `frontend/src/pages/Console.test.tsx` | Smoke vitest — renders without throw on empty state | minimal |

### Existing icons reused（no `motitle-icons.tsx` edits needed）
`home` / `film` / `edit` / `flow` / `book` / `layers` / `bell` / `cog` / `user` / `upload` / `play` / `pause` / `check` / `dots` / `caret` / `waveform` / `alert` / `clock`  — all already registered.

### New icons to ADD（要 edit `motitle-icons.tsx`）
None expected。手動 cross-check `variant-console.jsx` 嘅 ICON_CON name 全部已 cover。如果發現遺漏，會喺 implementation 之前 quick-grep 再 add。

---

## 3. Files to MODIFY

| Path | Change | Risk |
|---|---|---|
| `frontend/src/router.tsx` | Add lazy route `/console` (Q6=C: `VITE_CONSOLE=1` env + `?console=1` query both required to render；missing 任一→ redirect `/`) | low — additive |
| `frontend/src/lib/api.ts` 或 `lib/api/console.ts`（新檔） | Add typed wrapper `getQueue()` → `QueueItem[]` + `setPresetSlot(pipelineId, slot)` (Q3) | low — additive |
| `frontend/src/stores/pipeline-picker.ts` | Add `preset_slot` field to `PipelineSummary` interface (matches new backend field) | low — schema additive |
| `frontend/src/pages/Pipelines.tsx` | Add preset-slot picker UI (1-4 dropdown) per pipeline edit form | medium — new form field + zod schema update |
| `frontend/src/lib/schemas/pipeline.ts` 同 `pipeline-v5.ts` | Add `preset_slot: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4), z.null()]).optional()` | low |
| `frontend/src/lib/socket-events.ts` | Add `duration_seconds?: number` to `FileRecord` (Q2) | low — schema additive |
| `frontend/tailwind.config.ts` | **No change**（Q1=A） | n/a |
| `frontend/src/styles/motitle-bold.css` | **No change** | n/a |

**Existing pages 都唔郁：** Dashboard.tsx / Proofread / 5 個 v5 profile pages / Glossaries / Admin。`/` route 仍然係舊 Bold Dashboard，full backward-compat。**Pipelines.tsx 加多一個 form field（preset_slot picker）**，唔係 redesign。

---

## 4. Backend changes

### MVP（Q2 + Q3 locked in）

#### B1 — File `duration_seconds` 字段（Q2=B）
- **Schema：** `FileRecord` 加 `duration_seconds: float | null`
- **Upload route**（`backend/routes/files.py` upload handler）：成功儲存原檔之後 call `ffprobe -v error -show_entries format=duration -of json <path>`，parse `format.duration` 寫入 `entry["duration_seconds"]`。Exception graceful → set to `None` + warning log
- **Migration script** `backend/scripts/backfill_duration.py`：walk registry，對每個冇 `duration_seconds` 嘅 entry 跑 ffprobe，寫入 registry。Idempotent，重跑 0 操作。一次性，commit 入 repo 跟 v3.17 migrate_v317_asr_models.py pattern
- **Tests**（new file `backend/tests/test_file_duration.py`）：
  - Upload success → `duration_seconds` populated (mock ffprobe via subprocess.run patch)
  - Upload + ffprobe fail → `duration_seconds=None`，file 仍然 register OK
  - Migration script idempotent
  - `GET /api/files` response 含 `duration_seconds`
- **Estimate：** ~1.5 hr backend + frontend `formatDuration(seconds: number): string`（mm:ss / h:mm:ss）utility ~10 min

#### B2 — Pipeline `preset_slot` 字段（Q3=C）
- **Schema：** v4 `pipelines.py` 同 v5 `pipeline_schema_v5.py` 都加 `preset_slot: int | None`，允許 value `{None, 1, 2, 3, 4}`。Schema validator reject 其他 int
- **Per-user uniqueness：** PipelineManager `create()` + `update_if_owned()` 入面 check — 如果 patch 設 `preset_slot=N`，先 search 同一 user 已有冇 pipeline 持住 slot N。已有就：**atomic swap**（將舊 occupant set 為 None，新 occupant set 為 N），all in 同一個 `BEGIN IMMEDIATE` 嘅 transaction-equivalent（用 PipelineManager 嘅 lock pattern）
- **新 endpoint：** `POST /api/pipelines/<id>/preset_slot` body `{slot: int | null}` — 簡化 swap UX，唔需要 user 自己 PATCH 兩個 pipeline
- **Cross-user：** slot 係 per-user 唯一，唔同 user 之間 slot N 可以各自有自己嘅 pipeline。Admin 嘅 slot 唔影響其他 user
- **Migration：** 唔需要 — schema field optional + default None，舊 pipeline JSON 直接兼容
- **Tests**（new file `backend/tests/test_pipeline_preset_slot.py`）：
  - Validation: slot 5 reject；slot 0 reject；slot null OK；slot 1-4 OK
  - Per-user uniqueness: 設 slot=1 → 同 user 已有 slot=1 嘅 pipeline → atomic swap（舊嘅變 None）
  - Cross-user：user A slot=1 唔 prevent user B slot=1
  - `GET /api/pipelines` response 含 `preset_slot`
  - `POST /api/pipelines/<id>/preset_slot` happy path + 403 (non-owner) + 404 (missing) + 400 (bad slot)
- **Estimate：** ~2 hr backend + frontend `/pipelines` page 加 preset_slot dropdown ~30 min

### Optional (defer)
- ~~`GET /api/system/health`~~ — Q5=B 唔需要做 (queue_depth 由 `/api/queue` length derive，frontend 計就得)

### MVP backend test delta
- New: `test_file_duration.py` (4 cases) + `test_pipeline_preset_slot.py` (~8 cases) = ~12 new pytest
- Existing baseline preserved (794 pass + 14 known failures）— no regression expected

---

## 5. Stores / Hooks 新加

### `usePipelinePickerStore` (extend, NOT new)
Add `preset_slot?: 1 | 2 | 3 | 4 | null` to `PipelineSummary` interface to match Q3 backend field。Console reads slots by filtering：
```ts
function getPresetForSlot(slot: 1 | 2 | 3 | 4): PipelineSummary | undefined {
  return pipelines.find(p => p.preset_slot === slot);
}
```
No new store needed — backend is source of truth。⌘1-4 hotkey → `setPipelineId(getPresetForSlot(n)?.id ?? null)`。

### `useWorkerStatus` (new)
```ts
export function useWorkerStatus(): {
  activeJobs: QueueItem[];       // status === 'running'
  queuedJobs: QueueItem[];       // status === 'queued', sorted by position
  erroredJobs: QueueItem[];      // status === 'failed'
  loading: boolean;
}
```
Internal：`setInterval(() => fetch('/api/queue'), 3000)` + listen `queue_changed` socket event → re-fetch。Cleanup 對等 mount/unmount。

### `useHotkeys` (new — minimal, no library)
```ts
export function useHotkeys(map: Record<string, () => void>): void;
// Combo syntax: 'cmd+1', 'space', 'esc', 'cmd+k', 'arrow-down'
```
Listens `keydown` on `window`；ignores when `event.target` is `<input>` / `<textarea>` / `[contenteditable]`。

---

## 6. Tailwind config — 動詞與時態

按 Gap 2 default 為 **A**（保持 CSS-var pattern）→ `tailwind.config.ts` **零改動**。

如果你揀 **C**（hybrid），plan 加：
- `tailwind.config.ts.theme.extend.colors`：`bg: 'var(--bg)'`, `surface: { DEFAULT: 'var(--surface)', 2: 'var(--surface-2)', 3: 'var(--surface-3)' }`, `accent: { DEFAULT: 'var(--accent)', 2: 'var(--accent-2)', soft: 'var(--accent-soft)' }`, `text: { DEFAULT: 'var(--text)', mid: 'var(--text-mid)', dim: 'var(--text-dim)' }`
- `borderRadius`：`xs: '4px'`, `pill: '999px'`（README 提到但 source styles.css 無嘅 2 個 token — design system 設計者列入 README 表，code 入面冇用，所以 README 同 source code 之間有 minor inconsistency；我哋無 source-of-truth 就以 styles.css 為準）

**Plan default： A，唔郁 tailwind.config。** Component 用 `style={{ background: 'var(--surface-2)', color: 'var(--text-dim)' }}` inline 或者 `console.css` 嘅 semantic class。

---

## 7. Test impact

### 現有 spec：0 個 break
Console route 係 `/console`，feature-flagged，**唔 replace `/`**。`dashboard.spec.ts` + `bold-dashboard.spec.ts` + `happy-path-pipeline.spec.ts` 仲行去 `/`，全部 selector（`.b-rail`, `.b-topbar`, `.pipeline-strip`, `.drop-hero`, `.workbench`, `.inspector`, `.run-btn`）都喺現有 Bold Dashboard 入面，不受影響。

### 新加 spec：1 個
**`frontend/tests-e2e/console.spec.ts`** — 涵蓋（每個 case 加 `data-testid` selector）：
| Test | Assertion |
|---|---|
| Console renders at /console after login | grid 4-column visible，`[data-testid="console-rail"]` + `[data-testid="console-queue"]` + `[data-testid="console-workbench"]` + `[data-testid="console-aside"]` 全部 visible |
| Rail brand mark + 6 nav items + 3 bottom items | count = 1 + 6 + 3 |
| Queue list shows files when seeded | `[data-testid^="queue-item-"]` count > 0 |
| Queue item 4-segment stage bar present | `[data-testid="queue-stage-bar"] > i` count === 4 |
| Active queue item highlights workbench | click queue item → workbench filename matches |
| Preset pills count + ⌘1-4 hotkey switches active pill | press `Meta+1` → first pill has `[data-active="true"]`, `Meta+2` → second |
| Worker status section shows queued list | `[data-testid="worker-queued-list"] li` count >= 0 (tolerate empty) |
| Transcript list renders rows for selected file | `[data-testid="transcript-row"]` count >= 0 |
| Right aside 3 blocks present | `[data-testid="aside-pipeline"]` + `[data-testid="aside-glossary"]` + `[data-testid="aside-facts"]` visible |

Tolerate empty state per existing `bold-dashboard.spec.ts` 嘅 pattern（pipeline empty / file empty 都 OK）。

### Unit tests：3 個
- `Console.test.tsx` — renders, no throw on null file
- `stores/preset-slots.test.ts` — slot set / persist / reset
- `hooks/useWorkerStatus.test.ts` — fetch / re-fetch on `queue_changed` / cleanup

### Backend tests：0 個 break，0 個新加（MVP），5 個新加（如做 Phase 2 metrics endpoint）

---

## 8. 受影響嘅 e2e selector — 詳列

**現有 selector 完全唔郁** — 列喺度淨係作 reference confirm 唔 conflict：

| Spec | Selector | Still works? |
|---|---|---|
| `dashboard.spec.ts` | `.b-rail`, `.b-topbar`, `.pipeline-strip`, `.drop-hero` | ✅ at `/` |
| `bold-dashboard.spec.ts` | `.health-cluster .health-pill .hk`, `.workbench`, `.inspector`, `.run-btn` | ✅ at `/` |
| `happy-path-pipeline.spec.ts` | `label:has-text("Pipeline")`, `[role="combobox"]` | ✅ at `/pipelines` + `/` |
| `proofread*.spec.ts` | Proofread page selectors | ✅ untouched |
| `*-crud.spec.ts` | Profile / glossary page selectors | ✅ untouched |

Console **新 data-testid namespace**（避免同既有 Bold class collide）：
- `console-rail`, `console-queue`, `console-workbench`, `console-aside`
- `queue-item-<file_id>`, `queue-stage-bar`
- `worker-active-list`, `worker-queued-list`
- `preset-pill-1` ... `preset-pill-4`
- `transcript-row-<idx>`
- `aside-pipeline`, `aside-glossary`, `aside-facts`

---

## 9. 分階段實作（10 個 stage，逐個可 commit）

| Stage | Scope | Files touched | Time est |
|---|---|---|---|
| **S0a** Backend Q2 — duration | `routes/files.py` upload ffprobe + `FileRecord` schema + `scripts/backfill_duration.py` + tests | 2 mod, 1 new script, 1 new test | 90 min |
| **S0b** Backend Q3 — preset_slot | `pipelines.py` (v4) + `pipeline_schema_v5.py` 加 field + validator + per-user uniqueness + atomic swap + `POST /api/pipelines/<id>/preset_slot` endpoint + tests | 3 mod, 1 new test | 120 min |
| **S1** Design tokens | **NO-OP**（Q1=A）— tokens already in `motitle-bold.css` | 0 file | 0 min |
| **S2** Layout shell | New `Console.tsx` + `router.tsx` feature-flag (Q6=C: env `VITE_CONSOLE=1` + query `?console=1`) + 4-col CSS grid + empty 子 component stubs + new `console.css` 骨架 | 2 new files, 1 mod | 30 min |
| **S3** Rail | `Console/Rail.tsx`（6 nav + 3 bottom） + `console.css` rail styles | 1 new file, 1 mod (console.css) | 30 min |
| **S4** Queue column | `QueueColumn`, `QueueItem`, `StageBar` + integration with `useSocket()` reducer + drop zone (lift `react-dropzone` config from `UploadDropzone.tsx`) + `formatDuration()` util reads Q2 field | 3 new files + 1 util | 100 min |
| **S5** Worker Status | `WorkerStatus.tsx` + `useWorkerStatus.ts` hook + active/queued/errored render | 2 new files | 60 min |
| **S6** Workbench | `Workbench.tsx`, `PresetPills.tsx` (reads preset_slot from pipeline-picker store), `MetricsBar.tsx` (Q5=B：queue_depth real，其餘 dash), `VideoPanel.tsx`, `TransportBar.tsx`, `TranscriptList.tsx` | 6 new files | 180 min |
| **S6b** Pipelines page 加 preset_slot UI | `/pipelines` page form 加 preset_slot dropdown + zod schema update | 2 mod | 30 min |
| **S7** Aside (Q4=A read-only glossary) | `AsideColumn.tsx`, `PipelineStageCards.tsx`, `GlossaryToggleList.tsx` (read-only display + tap → navigate), `FileFactsBlock.tsx` | 4 new files | 80 min |
| **S8** Animations | Add CSS transitions per README table（pure CSS，no framer-motion）：stage-bar fill 300ms ease-out / pulsing dot 1.4s ease-in-out infinite / queue item enter 220ms cubic-bezier / preset pill switch 120ms linear / active row inset 150ms | `console.css` extension | 60 min |
| **S9** Keyboard shortcuts | `useHotkeys.ts` hook + wire ⌘1-4 (preset, reads pipeline-picker filtered by preset_slot) / ⌘K (placeholder) / ⌘U (upload) / Esc (cancel modal) / Space (play/pause) | 1 new file + 4-6 mods | 45 min |
| **S10** Tests + docs | 1 e2e spec + 3 unit + `docs/CONSOLE_REDESIGN.md` summary (separate from this plan) | 4 new files | 90 min |

**估計總時間：** ~15 hr 開發 + ~2 hr testing = **2 工作日**。

**Dispatch order：** S0a + S0b 必須先做（後續 frontend 依賴呢兩個 backend field）。然後 S1-S10 sequential。

---

## 10. Hard rule 對齊 confirm

| Rule | Compliance plan |
|---|---|
| No new styling library | ✅ Only Tailwind + new `console.css` extending motitle-bold pattern |
| No emoji in UI | ✅ All icons via `motitle-icons.tsx`，**唔加新 icon**（既有覆蓋齊） |
| No inline SVG | ✅ Same as above |
| No direct copy from design HTML | ✅ Re-implement TS + React idiomatic component |
| No tokens value change | ✅ Already verified — motitle-bold.css 同 styles.css 完全一樣 |
| Named export + `type Props` | ✅ All new components |
| Motion duration as literal number / CSS const | ✅ CSS transitions only |
| Console feature-flagged | ✅ `/console?` query OR `VITE_CONSOLE=1` env，`/` 唔郁 |

---

## 11. 6 個 Question — 全部 locked 2026-05-22

| # | Question | Decision | Implementation note |
|---|---|---|---|
| Q1 | CSS strategy | **A** | 新 `console.css`，token from motitle-bold.css，tailwind.config 唔郁 |
| Q2 | `duration` 字段 | **B** | ffprobe on upload + registry field + migration script + 4 tests |
| Q3 | Preset slot mapping | **C** | Backend `preset_slot` field on pipeline + per-user uniqueness + atomic swap + ~8 tests |
| Q4 | Glossary toggle semantic | **A** | Read-only display，tap → `/glossaries/<id>` detail |
| Q5 | Metrics bar | **B** | queue_depth derived from `/api/queue` length，其餘 4 metric "—" |
| Q6 | Feature flag | **C** | `VITE_CONSOLE=1` env (build) + `?console=1` query (runtime) — both required |

---

## 12. Open risk / 未決疑問

- **Pipeline schema 兼容性**：existing pipelines 有 v4 + v5 兩種 shape，`PipelineStageCards` 要 handle 兩種。Plan：用 `useProfileLookupStore.fetchPipeline()` 攞 normalized shape；如果 broken_refs 顯示 amber warning chip。
- **`/api/queue` polling cadence**：3s default。如果出現 240/min/user limiter 觸發 warning，調慢去 5s。Backend `limiter.limit("240 per minute")` 對單 user／每秒 4 次 — 3s polling 大約每分鐘 20 次，非常安全。
- **Render integration**：`useRenderJob` 目前 scoped 喺 Proofread 入面。Console 嘅 4th stage bar segment 要顯示 render state — option（a）抽 `useActiveRenders()` 出嚟 query 跨檔，或者（b）暫時 Render position 永遠 'idle' 跟 file.status 顯示。Plan default：**(b) MVP**。
- **Bilingual transcript display**：Spec 顯示 `ts / en / zh / marker` 但 v5 既有可能係 zh→zh / en→zh 等。Plan：sourceLang + activeLang 不同就顯示 bilingual，相同顯示單欄。
- **Mobile / Tablet fallback**：Per spec desktop-only 1280+；< 1024 用既有 BoldRail 同 layout。Plan：Console 加 `@media (max-width: 1023px)` → render `<RedirectToDashboard />`（小屏自動 fallback 去 `/`）。

---

## 13. Verification checklist（交付前）

完整實作完之後，必須：

- [ ] `cd frontend && npm run typecheck` ✅ no error
- [ ] `cd frontend && npm run test` ✅ all unit pass
- [ ] `cd frontend && npx playwright test console.spec.ts` ✅ GREEN
- [ ] `cd frontend && npx playwright test dashboard.spec.ts bold-dashboard.spec.ts` ✅ STILL GREEN（regression confirm）
- [ ] `cd backend && pytest -q` ✅ 794+ green，no regression
- [ ] 手動煙測 `http://localhost:5173/console?console=1`：
  - 上傳一個 audio file → queue item 即時出
  - 觸發 pipeline run → `pipeline_stage_progress` event → queue item ASR cell 由 idle → warn fill → done 綠
  - ⌘1 → ⌘2 切換 preset → pipeline-picker store sync 同 active state
  - Click 一個 queue item → workbench filename header + transcript 切換
  - Open `/`（舊 dashboard）→ 確保 0 regression

---

## 14. Final acceptance criteria（spec 嘅 11 項）

| README acceptance | Implementation strategy |
|---|---|
| 4-col 56/360/1fr/320 ratio | `grid-template-columns: 56px 360px 1fr 320px` 喺 `.console` root |
| Tokens 由 design system | 全部 `var(--*)` from `motitle-bold.css`（option A） |
| 4-segment stage bar | `StageBar.tsx` + `deriveStageStates(file, socketState, renderState?)` |
| Worker Status live update | `useWorkerStatus()` poll + socket trigger |
| ⌘1-4 hotkey | `useHotkeys({'cmd+1': ..., 'cmd+2': ..., ...})` |
| Video/Transport/Transcript stacked | Flex column inside `.con-stage` |
| Aside 3 blocks scrollable | `.con-aside` overflow-y auto，3 個 `.blk` |
| Hover / active transition 150-220ms | CSS transitions in `console.css` |
| Pulse infinite on active worker | `@keyframes pulse` + `r-dot--pulse` class |
| Existing Playwright pass | Feature flag → `/` untouched → existing specs green |

---

**End of plan. Awaiting decision on Q1 + acknowledgment to proceed (full or staged dispatch).**
