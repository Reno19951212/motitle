# 校對頁段落時間調整（Segment Timing Trim）— Design v2

日期：2026-06-11 ｜ 狀態：✅ 用戶已批准（v2 mockup 兩輪反饋確認）｜ Branch: `worktree-proofread-ai-rerun`
研究基礎：[2026-06-11-segment-timing-ux-research.md](2026-06-11-segment-timing-ux-research.md)（Workflow 3 研究員 + 評審；v1→v2 用戶修訂已記錄）

## 目標

校對頁俾用戶調整當前 segment 嘅 In/Out 時間點。四種互動，全部寫入同一個新 timing endpoint：

1. **拖拉把手（主力）**：時間軸當前段 region 左右各一個把手，揸住直接拖個頭／個尾；拖緊顯示浮動 timecode
2. **時間軸縮放（基建）**：`⊡全片`／`−`／`＋`／`⌖對焦本段` 控制（住喺 `.rv-b-tlh-r` 預留位），放大後橫向捲動 — 解決長片 region 得幾 px 嘅問題；「對焦本段」zoom 到當前段佔視窗 ~25%
3. **`I`/`O` 快捷鍵 + `⤓` 掣**：設 In/Out 為播放頭位置（**唯二**新快捷鍵 — 用戶明確唔要 nudge 鍵）
4. **數字時間輸入（精確後備）**：ctrl row 嘅 `#curIn`/`#curOut` 由 span 變 editable mono input（Enter/blur commit）

## 核心語義：Roll-on-contact

Cue grid 係連續無重疊（split/merge 維持），下游（SRT／libass／renderer start>=end 靜默丟棄）對重疊零防禦 → 邊界調整 model 做**共享邊界移動**：

- 段 N 嘅 In 同段 N−1 嘅 Out **相連**（butt-joined）時 → 一齊 roll，兩段各受 **0.4s 最少時長** clamp（同 split floor 一致）
- 有 **gap** 時自由移動，**clamp 喺鄰段邊界**（永不重疊、唔 roll）
- 每個操作 by construction 合法 — 無 error dialog

## 適用範圍 + 互鎖

- 只限 `active_kind == 'output_lang'`（同 split/merge/AI Rerun 一致）；非 output_lang 檔：無把手、無 zoom 限制（zoom 純顯示，全 kind 都有）、ctrl row 維持唯讀
- render／AI Rerun 進行中 → 409（雙向：timing 唔加反向鎖 — rerun 已有 timing-drift conflict check 兜底）
- **批核狀態保留** — timing-only 編輯唔 reset approval（文字冇變；雙語 render 要求全批核，reset 會逼人重審）

## 後端

**新 pure module `backend/segment_timing.py`**：
- `plan_timing_change(rows, pos, new_start=None, new_end=None, min_dur=0.4) -> (changes, clamped)`
  — `rows` 係 `[{start,end},…]` snapshot；回 `changes=[(idx, start, end),…]`（含被 roll 嘅鄰段）+ `clamped` bool；秒為單位（float）；butt-joined 用 1e-6 epsilon 判定

**新 route `PATCH /api/files/<id>/segments/<int:pos>/timing`**（`@require_file_owner`）：
- Body `{in_ms?: int, out_ms?: int}`（至少一個；絕對毫秒 — 冪等）
- 400：非 output_lang／pos 越界／參數唔係非負 int／兩個都冇
- 409：`_file_has_active_render`／`_file_has_active_rerun`
- `_registry_lock` 內：snapshot → planner → **四庫同步**（照 split cascade）：`translations[i]`＋`segments[i]`＋`content_asr_segments[i]`（唔同步嘅話 glossary-reapply 會用舊 timing 重建 grid 還原修改）＋`aligned_bilingual[i]`；status/flags 完全唔掂；`_save_registry()`
- 200 `{rows: [{idx, start, end}, …], clamped}` — 前端 reconcile（server clamp 後嘅實際值）

## 前端（proofread.html）

**縮放基建**：`#waveform` 變 viewport（`overflow-x:auto`），入面加 `#waveformInner`（`width = zoom×100%`，現有四層 — bars/regions/playhead/ticks — 搬入去，% 定位照用）。Zoom 控制喺 `.rv-b-tlh-r`；`wfZoom` state（1–64×）；zoom 改變時 debounce 重新 fetch waveform peaks（`?bins=min(4096, 480×zoom)` — endpoint 已支援 bins）；ticks 密度跟 zoom 自適應；`⌖對焦本段` zoom 到當前段佔 ~25% 並 scroll 置中

**拖拉**：`renderWaveformRegions` 為 `.cur` region（output_lang 先有）加左右 `.rv-wave-grip`；`mousedown` 喺把手、`mousemove`/`mouseup` 喺 document；拖緊：直接改該 region（同被 roll 鄰 region）嘅 left/width + ctrl row 數值 + 浮動 timecode，**唔行全量 re-render**（`renderWaveformRegions` 開頭 `if (wfDrag) return` 防 9 個 call site 殺 drag state）；`mouseup` 先 commit PATCH。click-to-seek 跳過 `.rv-wave-grip` target

**ctrl row**：`#curIn`/`#curOut` span → mono input（output_lang 先 enable）+ 兩個 `⤓` 掣；`I`/`O` keydown（跳過 input focus / isComposing）

**儲存**：`_saveTiming(pos, {in_ms?, out_ms?})` → PATCH → 用 response rows 更新 `segs[]`（`.in/.out/tsIn/tsOut/duration`）→ 重繪（regions／rail／detail／ctrl row）；失敗 → `loadSegments()` 還原 + error toast

## 唔做（YAGNI）

鍵盤 nudge（`[`/`]` 等 — 用戶明確唔要）、自動回播邊界、ASR 詞邊界 snap、tap-sync、非 output_lang 檔嘅 timing 編輯、touch 支援、undo 歷史。

## 測試

1. pytest pure planner：roll 兩方向／gap clamp 唔 roll／0.4s floor 兩段各自 clamp／單邊+雙邊改／epsilon butt 判定
2. pytest route：400 系／409 系／四庫同步（特別 content_asr_segments + aligned_bilingual string by_lang）／approval 保留／clamped flag
3. Playwright E2E（真檔）：zoom 控制循環＋對焦本段；拖 Out 把手 → segs 更新＋persist（API 覆核）＋roll 鄰段；`I`/`O`；數字輸入 commit；非 output_lang 檔冇把手
