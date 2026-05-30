# Subsystem A — 統一進度 step-diagram(Profile + V6,序列 panel + file card)

**日期**：2026-05-30 ｜ **Branch**：`fix/profile-and-v6` ｜ **狀態**：Design — 待 user review
**研究**：[2026-05-30-unified-progress-and-bilingual-research.md](../research/2026-05-30-unified-progress-and-bilingual-research.md)
**註**：Subsystem B（per-video 雙語）另 spec，A 先做。

---

## 1. 問題（研究實證）

進度顯示喺 Profile vs V6、右側序列 panel vs 左側 file card 之間唔一致 + 有 live bug：
- 🐛 **V6_STAGE_LABELS 3/5 對唔上**：`progress_adapter.py` label keys（`vad`/`asr_primary`/`asr_align`/`merge`/`refiner`）≠ `_run_v6` 真 emit 嘅 `stage_type`（`vad`/`qwen3_per_region`/`asr_primary`/`time_anchored_merge`/`refiner:zh`）→ 多數 V6 stage 顯示「Stage N」fallback，「Qwen3 識別中」label 仲黐錯去 mlx stage。
- 右側 V6 row 永遠標 '轉錄'（job.type=asr）；`/api/queue` 冇 `pipeline_kind`/`stages`。
- Profile 右側 per-stage reset（轉錄 0-100→翻譯 0-100），V6 monotonic 0-100；左側 card Profile 用 composite 3-phase、V6 **卡死 0%**（左側讀 subtitle_segment/translation_progress，V6 唔 emit）。
- `translation_status`：Profile='done' / V6='completed'（同名不同值）。

## 2. 目標 / 決策

統一**右側序列 row + 左側 file card**（兩個 surface）、**Profile + V6**（兩個 kind）嘅進度顯示，用一個 **step-diagram canonical 模型**：顯示成個 pipeline 嘅有序階段，`✓ 完成 / ● 進行中(填充) / ○ 待處理`。Frontend **零 kind branching**（v3.21 invariant）—— backend 供應階段清單 + 當前 index，frontend render generic steps。順手修 V6_STAGE_LABELS bug + normalize translation_status。

## 3. Canonical 階段模型

每個 pipeline kind 一個**有序階段清單**（backend 定義，frontend 唔知內部）：
- **Profile**：`轉錄`(transcribe) → `翻譯`(translate) → `校對`(proofread)
- **V6**：`VAD 切段`(vad) → `Qwen3 識別`(qwen3) → `mlx 對齊`(mlx) → `時間合併`(merge) → `Refiner 校對`(refiner)

每步 state 由 `stage_index` + `stage_state` + `pct` 客戶端 derive（generic，唔需要知 kind）：
- step i `< stage_index` → ✓ done
- step i `== stage_index` → ● active（fill = pct%）；若 `stage_state=='done'` 且係最後 step → ✓
- step i `> stage_index` → ○ pending
- 整條 pipeline 完成 → `stage_index = len-1, stage_state='done', pct=100` → 全 ✓

## 4. Contract 擴充（additive，backward-compat）

`ProgressSnapshot` + `pipeline_progress` event + `/api/queue` rows **新增**（現有 `pct`/`stage_label`/`stage_state`/`pipeline_kind` 保留唔改）：
- `stages: [{key: str, label: str}]` — 此 file kind 嘅完整有序階段清單
- `stage_index: int` — 當前 0-based index
- `/api/queue` 額外補返 `pipeline_kind`（cold-start 用）

加 field OK（contract invariant：加 field backward-compat，唔可刪/改名）。

## 5. Backend 設計（`backend/progress_adapter.py` 為主）

- **定義 per-kind 階段清單**（module-level）：
  ```python
  PIPELINE_STAGES = {
    "profile": [{"key":"transcribe","label":"轉錄"},{"key":"translate","label":"翻譯"},{"key":"proofread","label":"校對"}],
    "pipeline_v6": [{"key":"vad","label":"VAD 切段"},{"key":"qwen3","label":"Qwen3 識別"},{"key":"mlx","label":"mlx 對齊"},{"key":"merge","label":"時間合併"},{"key":"refiner","label":"Refiner 校對"}],
  }
  ```
- **V6 stage_type → index map（修 bug）**：`vad`→0、`qwen3_per_region`→1、`asr_primary`(=mlx)→2、`time_anchored_merge`→3、`refiner:<lang>`(startswith "refiner")→4。`report_from_v6_stage` 用呢個 map 計 stage_index + 由 `PIPELINE_STAGES["pipeline_v6"][idx].label` 攞 label（取代壞咗嘅 V6_STAGE_LABELS）。
- **`ProgressAdapter.report(...)`** 接收 kind + stage_index，attach `stages = PIPELINE_STAGES[kind]` + `stage_label = stages[stage_index].label` 入 snapshot/event。
- **Profile shims**：`report_from_subtitle_segment` → stage_index 0（轉錄）；`report_from_translation_progress` → stage_index 1（翻譯）。
- **校對 step（Profile index 2）**：approval 變動時 emit。`approve` / `unapprove` / `approve-all` handler（app.py）加 additive call：`get_adapter().report(file_id, kind='profile', stage_index=2, pct=approved/total*100, stage_state='active'|'done')`。整條 done 由 approved==total 觸發（file card 仍在，序列 row 已消失，由 card 顯示）。
- **`/api/queue`**（`jobqueue/routes.py`）：每 row 加 `stages` + `stage_index` + `pipeline_kind`（由 `get_adapter().get_snapshot(file_id)`，無 snapshot 時由 `file_entry.active_kind` derive stages + index=0 idle）。
- **Normalize `translation_status`**：V6 由 'completed' 改 'done'（或 frontend/queue 一律當兩者相等 —— 採用：persist 時統一寫 'done'，保留 `translation_kind='pipeline_v6_inline'` 做區分）。

## 6. Frontend 設計（零 kind branching）

- **共用組件 `renderStepDiagram(stages, stageIndex, stageState, pct)`** → 回傳 step-diagram HTML（dots/pills + labels，`✓/●(fill)/○`）。同時畀右側 queue row 同左側 file card 用。
- **右側 `queue-panel.js`**：row 由「單一 bar + 靜態 '轉錄' label」改用 `renderStepDiagram`（讀 row 嘅 `stages`/`stage_index`/`stage_state`/`progress_pct`）；`pipeline_progress` listener patch 同樣 fields。type label 唔再硬 '轉錄'。
- **左側 file card（`index.html`）**：由 composite 3-phase pct + 卡死「轉錄中 0%」改用 `renderStepDiagram`，driven by `pipeline_progress`（為左側加 `socket.on('pipeline_progress')` → 更新該 card 嘅 step diagram）→ **V6 card 終於有進度**。移除/取代舊 composite scPercent 邏輯。
- Density：compact row 用細 dots（label 只顯示當前 active step 全名，其餘 dot + tooltip）；file card 可顯示全部 label。

## 7. Invariant 保住
- frontend render backend 畀嘅 `stages`，**零 kind 判斷**（queue-panel.js + 新組件都唔 branch on pipeline_kind）。加新 kind = backend 加 `PIPELINE_STAGES` entry + shim。
- Native events（subtitle_segment / translation_progress / pipeline_stage_*）payload 唔改。`pipeline_progress` 只加 field。`queue_changed` 維持 zero-payload。

## 8. 測試
- **pytest**：progress_adapter（PIPELINE_STAGES 結構、V6 stage_type→index map 5 個全中、Profile shim stage_index、report attach stages/label、校對 approval emit）；`/api/queue` 新 field（stages/stage_index/pipeline_kind）。
- **Playwright**：兩 kind × 兩 surface — Profile 跑（轉錄✓→翻譯●→校對○ 演進）、V6 跑（5 step 演進、label 正確唔再 "Stage N"）、cold-start reload step diagram 即現、跨 tab 同步、`pipeline_v99` forward-compat（frontend 零改 render unknown kind 嘅 stages）。

## 9. 範圍外（明確）
- Subsystem B（per-video 雙語 / 第二語言 / by_lang 重構 / resolve_segment_text language-aware）—— 另 spec。
- render-job 進度（獨立 polling，現狀不變）。
- 加權跨 stage 嘅 monotonic 單 bar（已棄用，揀咗 step-diagram）。

## 10. 風險
| 風險 | 緩解 |
|---|---|
| step diagram 喺 compact queue row 太擠 | 細 dots + 只 active step 顯全名 + tooltip；Playwright 量度唔 overflow |
| 校對 approval emit 令 file 'done' 後仍更新 | 只更新 file card（序列 row 已消失）；adapter cache 接受 post-done 更新 |
| V6 stage_index 同 stages 清單錯位 | unit test 鎖死 5 個 stage_type→index map |
| 改 translation_status 'completed'→'done' 影響既有 consumer | grep 所有讀 translation_status 嘅地方，確認當 'done' 處理；保留 translation_kind 區分 |
| 左側 card 改動撞既有 fileProgress 邏輯 | 移除 composite 3-phase 之前 grep 所有 reference；Playwright regression |

## 11. 驗收標準
1. V6 序列 row + card：5 個 step label 正確（VAD/Qwen3/mlx/時間合併/Refiner），無 "Stage N" fallback。
2. Profile 序列 row + card：轉錄→翻譯→校對 step diagram 正確演進。
3. V6 file card 唔再卡 0% —— 顯示 step 進度。
4. 兩 surface 用同一 `renderStepDiagram`，零 kind branching（grep 確認 queue-panel.js + 組件無 pipeline_kind 比較）。
5. cold-start reload step diagram 即現（/api/queue stages/stage_index）。
6. `pipeline_v99` forward-compat test 通過（unknown kind 照 render backend 畀嘅 stages）。
7. pytest + Playwright 全綠，無 regression。
