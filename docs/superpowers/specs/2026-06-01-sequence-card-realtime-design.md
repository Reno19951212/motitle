# 序列 file card 實時化（階段名+% + 字幕串流）— Design Spec

**日期**：2026-06-01 ｜ **狀態**：Approved — implement ｜ **Branch**：`fix/profile-and-v6`

## 問題
工作隊列 panel 有實時進度 + 流程顯示，但左側「序列」file card 唔夠實時：card 雖然已有細粒 step-diagram（Subsystem A），但 (a) 冇似 queue panel 咁顯示**階段名 + %**，(b) **完全冇字幕文字流出**。

## 目標（user 拍板）
序列 file card 喺處理緊時：
1. 顯示 live **階段名 + %**（例：`Qwen3 識別 40%`），似 queue panel。
2. **字幕文字即時流出**（live caption）—— **V6 主力**：改 backend 令 V6 邊跑邊 emit 增量字幕；Profile ASR：用現有 `subtitle_segment` 串流。

屬 telemetry / UI（唔改 refiner / ASR / MT 輸出邏輯 —— `LLMRefiner.refine` 本身已 per-segment 回呼 text，今次只係**唔再掉佢**並 emit 出去）→ **唔涉 Validation-First**。

## 核心發現
`engines/refiner/llm_refiner.py::refine` 已經 per-segment 呼 `progress(i+1, n, text)`（L70/L118）。但 `stages/v5/refiner_stage.py::transform` 嘅 `progress_cb(idx,total,_txt)` **掉咗 `_txt`**，只 forward (idx,total) 去 stage pct。串流真實輸出 = forward 埋個 text。

## 設計

### Backend（emit only）
1. **`stages/__init__.py`** — `StageContext` 加 optional field `segment_callback: Optional[Callable[[int,int,str,str],None]] = None`（idx, total, text, lang）。
2. **`stages/v5/refiner_stage.py::transform`** — `progress_cb` 同時 forward text：
   ```python
   progress_cb = None
   if context.progress_callback is not None or context.segment_callback is not None:
       def progress_cb(idx, total, txt):
           if context.progress_callback is not None:
               context.progress_callback(idx, total)
           if context.segment_callback is not None:
               context.segment_callback(idx, total, txt, self._lang)
   return refiner.refine(segments_in, progress=progress_cb)
   ```
3. **`pipeline_runner.py`**：
   - 新 module-level `_make_segment_callback(file_id, pipeline_id)` → closure emit `_socketio_emit("pipeline_segment", {file_id, pipeline_id, idx, total, text, lang})`。
   - `_run_stage_v5` 加 param `segment_emit: bool = False`；為 True 時 `ctx.segment_callback = _make_segment_callback(self._file_id, self._pipeline["id"])`，否則 None。
   - `_run_v6` refiner 鏈：`enumerate` refinements，**只為最後一個 refiner**（`_ri == len-1`）傳 `segment_emit=True`（串最終輸出；書面語 chain 串 pass-2 書面語）。
4. 新 socketio event **`pipeline_segment`**（additive；唔改現有 `pipeline_progress`/`pipeline_stage_*` contract）。`_run_v5`（非 V6）唔郁（segment_emit 預設 False）。

### Frontend（`index.html`）
5. **階段名 + %**：card render 喺 `.card-step-diagram` 之上/旁加 `.card-stage-label`，處理緊時由 `cardProgress[id]`（已有 `stage_label`+`pct`）顯示「{stage_label} {pct}%」。`pipeline_progress` listener 已更新 `cardProgress` + diagram，順埋更新 `.card-stage-label`。
6. **字幕串流**：
   - 新 map `cardSubtitle = {}`；新 listener `socket.on('pipeline_segment', e => { cardSubtitle[e.file_id] = {text:e.text, idx:e.idx, total:e.total}; <update that card's .card-live-caption> })`。
   - 現有 `subtitle_segment` listener（Profile，無 file_id）→ 順手 `cardSubtitle[activeFileId] = {text: seg.text}` + 更新 active card 嘅 `.card-live-caption`。
   - card render 加 `.card-live-caption`（處理緊時顯示 `cardSubtitle[id].text`，截斷 1 行）。
   - 完成 / 非處理狀態 → 清 `cardSubtitle[id]`、隱藏 caption（`transcription_complete`/`pipeline_timing`/file done 時清）。

### 已知 nuance（已同 user confirm）
- 文字喺**最後 refiner stage** 先串（VAD→Qwen3→mlx→合併之後）；之前階段只有階段進度。
- 串流文字係 refiner 逐段（**clause_split 之前**）—— live preview 用，最終持久化 cue 可能再切細。
- `subtitle_segment` 無 file_id → Profile 串流只歸 active 檔（單用戶假設，沿用現狀）。

## 測試
- **Backend pytest**（`test_pipeline_segment_emit.py`）：
  1. `LLMRefiner.refine` per-segment 傳 text 去 progress（mock llm；regression guard）。
  2. `StageContext` 接受 `segment_callback`，預設 None。
  3. `RefinerStage.transform` forward 每段 text 去 `context.segment_callback`（monkeypatch `build_llm_engine`+`resolve_prompt`，mock LLM 回 canned）。
  4. `_run_stage_v5(segment_emit=True)` → stage 收到嘅 ctx.segment_callback 被呼時 emit `pipeline_segment`（含 file_id+text）；`segment_emit=False` → ctx.segment_callback is None（fake stage 記錄 ctx）。
- **Frontend Playwright**（`test_card_realtime.spec.js`）：
  1. 注入 `pipeline_segment` → 該 card 嘅 `.card-live-caption` 顯示 text。
  2. 注入 `pipeline_progress` → card 顯示 `.card-stage-label`（階段名+%）。
  3. 完成後 caption 清空 / 隱藏。

## 範圍外
- 早期串 Qwen3 原始 region 文字（user 收貨 Refiner-stage 串流）；clause_split 後精準 cue 串流；多用戶 subtitle_segment file_id（要改 backend emit room + payload）；inspector status-card 統一（另議）。

## Implementation 次序
見 plan `docs/superpowers/plans/2026-06-01-sequence-card-realtime-plan.md`。
