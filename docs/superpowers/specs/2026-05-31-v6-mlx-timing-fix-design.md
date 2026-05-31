# V6 mlx 時間軸幻覺修復 — Design（D3 + D2）

**日期**：2026-05-31 ｜ **狀態**：Design — 待 user review
**前置**：[Incident](../incidents/2026-05-31-v6-cantonese-mlx-timing-misalignment.md) ｜ [Validation tracker](2026-05-31-v6-mlx-timing-validation-tracker.md)（empirical evidence，已 confirm）
**範圍**：只 V6（`pipeline_type == "v6_vad_dual_asr"`）。Profile pipeline 完全唔郁。
**Validation-First**：本設計嘅每個 hypothesis 已喺 tracker 量化驗證（cond=False clip test、detector、Qwen3 fallback）。整合 gate 仍需 re-run reproducer 先 merge。

---

## 1. 問題（一句）

V6 嘅 mlx-whisper（timing 權威）喺某啲粵語片 hallucinate「字幕由 Amara.org 社群提供」並輸出每 30 秒一格嘅 block 時間；因為 `condition_on_previous_text=True`（預設），個幻覺 **cascade** 落連續多個 30s 窗（reproducer `de603727d3f8` 頭 150s = 5 塊）。time-anchored merge 盲信呢啲 block，令字幕時間變成「30 秒塊內按字數比例」嘅假時間 → 嚴重錯位（字幕比聲音早 ~7.9s）。

## 2. 修復（兩個互補，都只郁 V6）

### D3 — 打斷 cascade（mlx 設定，V6-scoped）
喺 `backend/pipeline_runner.py::_run_v6`（~line 545，建 `ASRPrimaryStage(primary_profile, audio_path)` 之前）：
```python
# V6: mlx is the TIMING track only — content carryover (condition_on_previous_text)
# never helps and lets a head hallucination ('字幕由…提供') cascade across every
# 30s window. Force it off for the V6 mlx timing run (v3.8 cascade fix, never
# applied to asr_primary). Profile/V5 paths untouched.
primary_profile = {**primary_profile, "condition_on_previous_text": False}
```
- 實作喺 `_run_v6`（唔係改共享 `stages/v5/asr_primary_stage.py`，亦唔改個別 profile JSON）→ **嚴格 V6-scoped**，V5 / Profile / 其他 pipeline 零影響。
- `MlxWhisperEngine` 已讀 `config.get("condition_on_previous_text", True)`，所以 profile dict override 即生效。
- **Empirical（tracker D3）**：cond=True 4 段全 30s 全幻覺 → cond=False 40 段 median 2.24s，只剩頭 1 塊。修到 30s 之後成片 body。

### D2 — 殘餘失敗塊 fallback 去 VAD 時間軸（merge stage）
cond=False 之後仍可能剩頭塊（reproducer 頭 0–30s 塊）。喺 `TimeAnchoredMergeStage` 加偵測 + VAD fallback：

**(a) 傳入 VAD 區間**：`_run_v6` 嘅 `merge_overrides` 由 `{"__qwen3_chars": ...}` 加到 `{"__qwen3_chars": ..., "__vad_regions": vad_regions}`（`vad_regions` 喺 stage 0 已有，line ~502）。

**(b) 偵測器**：mlx segment `duration >= COARSE_SEC`（module 常數，預設 **20.0s**；可由 pipeline JSON `mlx_coarse_fallback_sec` override）= 不可信塊。理由：真 V6 mlx 段係 2–4s，≥20s 段幾乎必然係失敗窗。**用 duration 做主訊號（穩健，唔依賴 hardcode 幻覺 phrase）**；幻覺文字只作 log 佐證。

**(c) Fallback 重切**：`_time_anchored_merge(mlx_segs, qwen3_chars, vad_regions)` 改為——
- 可信 mlx 段（dur < COARSE_SEC）：**照舊**，一段一 slot，`chars_in = [c for c in qwen3_chars if ws <= _midpoint(c) < we]`。
- 不可信 mlx 段 `[ws, we]`：用**覆蓋 `[ws,we]` 嘅 VAD 區間**做 slots（VAD region `r` 若 `_midpoint(r) ∈ [ws,we]`，或同 `[ws,we]` 有 overlap，clip 入 `[ws,we]`）；對每個 VAD slot `[rs, re]`，收 `chars_in_slot = [c for c in chars_in(ws,we) if rs <= _midpoint(c) < re]`，emit 一段 `{start: rs, end: re, text: concat}`。
- **Empirical（tracker D2）**：detector 對 bad mlx flag 5 塊/150s、synthetic healthy 零誤報；Qwen3「今」@7.88s 證實 VAD 區間（首區間 7.80s 起）會修正頭 7.88s 誤分配。

## 3. 資料流（V6 merge 後）
```
VAD regions (stage0) ─┐
qwen3 chars (stage1)  ─┼─► TimeAnchoredMergeStage._time_anchored_merge
mlx segs (stage1B)    ─┘     每 mlx 段：dur<20s → 照舊；dur≥20s → 用覆蓋嘅 VAD 區間做 slots，
                              Qwen3 字按 timestamp 落入 → 真語音邊界
                            ─► refiner ─► clause_split ─► persist（下游不變）
```

## 4. 邊界處理
| 情況 | 處理 |
|---|---|
| VAD 區間跨失敗塊邊界 | 按 `_midpoint(region) ∈ [ws,we]` 歸入；start/end clip 落 `[ws,we]` |
| 失敗塊內 Qwen3 字唔落任何 VAD slot（VAD trim 咗靜音） | 歸最近 VAD slot（唔丟字）；保持字序 |
| 失敗塊完全冇 VAD 區間覆蓋（極端） | 退回：將該塊 `[start,end]` 修正為「該塊內 Qwen3 首字.start..尾字.end」做單段（保證唔 crash + span 啱），下游 clause_split 照切 |
| `__vad_regions` 缺失（向後兼容 / 其他 caller） | detector 仍可 flag，但無 VAD 時走「極端」分支（Qwen3 span 修正）；唔 raise |

## 5. 改動檔案（高內聚、各一職）
| 檔案 | 改動 |
|---|---|
| `backend/pipeline_runner.py` | `_run_v6`：D3 cond=False override（~545）；D2 merge_overrides 加 `__vad_regions`（~555-560）|
| `backend/stages/v6/time_anchored_merge_stage.py` | D2：`_time_anchored_merge` 加 `vad_regions` 參數 + `_is_coarse()` + 失敗塊 VAD-bucket 分支；可信塊路徑不變 |
| `backend/tests/test_v6_*` | 新 unit（見 §6）|

## 6. 測試（TDD）
- **D3 unit**：`_run_v6` 建 mlx stage 時 `primary_profile["condition_on_previous_text"] is False`（patch `ASRPrimaryStage` / `create_transcribe_engine` 捕捉 config）。
- **D2 unit**（`TimeAnchoredMergeStage`，純函數，無需 mlx/audio）：
  1. 合成「1 個 coarse mlx 塊 0–30s + VAD 區間 [7.8-10.8][12.3-27.2][27.2-30] + Qwen3 字（首字 @7.88）」→ 斷言輸出係 3 段 VAD-aligned、**首段 start≈7.8s（非 0）**、字按時間正確分配。
  2. Healthy 案（全部 mlx 段 < 20s）→ 輸出同舊邏輯**逐 byte 一致**（regression guard）。
  3. 邊界：VAD 跨界 clip、字唔落 slot 歸最近、無 VAD 覆蓋 → Qwen3-span 修正、`__vad_regions` 缺失唔 crash。
- **整合（驗證 gate，Validation-First 必須）**：真 re-run reproducer `de603727d3f8` 經 V6（cond=False + D2）→ 首字幕 ~7.8s 起、頭 150s 唔再 30s 塊、detector 對「好」片（賽馬 `b1e0aa39c473`）零誤報。

## 7. 範圍 / 兼容
- 只 V6；Profile / V5 / 其他 pipeline 零改動。
- 既有已處理檔案不變（無強制 migration）；re-process 先得新行為。
- 其他 V6 pipeline（Winning Factor EN）一併受惠（cond=False + VAD fallback 對 timing track 普適正確）。
- `COARSE_SEC` 預設 20.0s，pipeline JSON 可 override；缺省即生效。

## 8. 驗收標準
1. D3：V6 mlx 跑 cond=False（unit + reproducer re-run 確認 body 無 30s 塊）。
2. D2：coarse mlx 塊被 VAD 區間取代、首字幕由真語音 start（~7.8s）起、字無丟。
3. Healthy mlx（全 <20s）行為逐 byte 不變。
4. Reproducer re-run：頭錯位消失；好片零誤報。
5. Profile / V5 regression 全綠。

## 9. 範圍外（明確）
- 改 mlx 模型本身 / word_timestamps（tracker H3.3 顯示有額外幫助，但 cond=False + VAD fallback 已足；留 deferred）。
- 全面取代 mlx 做 timing（Direction 1，更大改動，唔做）。
- Profile pipeline 嘅任何 timing 邏輯。
- 對舊檔案嘅 migration / 自動 re-process。
