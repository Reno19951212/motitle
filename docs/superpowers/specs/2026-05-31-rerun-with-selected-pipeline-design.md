# Re-run a completed file with the newly-selected pipeline — Design Spec

**日期**：2026-05-31 ｜ **狀態**：Approved — implement ｜ **Branch**：`fix/profile-and-v6`

## 問題
完成咗嘅片（喺檔案列表/序列）想換另一條 pipeline 再跑，但頂部 pipeline strip 嘅「執行」掣（`#runBtn`）灰咗㩒唔到；而且 re-run（`POST /api/files/<id>/transcribe`）用返**上傳時 snapshot 嘅舊 pipeline**，唔會跟你喺 strip 新揀嘅 pipeline。

## 目標
完成檔（`status==='done'`，亦涵蓋 `'error'`）選中後，喺 strip 重新揀過 pipeline，再㩒「執行」即用**新揀嘅 pipeline** 重新跑。屬 dispatch/UX wiring（邊條 pipeline 行），**唔改 ASR/MT engine 內部 → 唔涉 Validation-First**。

## Root cause（已 verify）
- `index.html::updateRunButton()`（~L4296）：只喺 `f._local`（待上傳新檔）時 enable `#runBtn`；完成檔 `_local=false` → disabled。
- `index.html::startTranscription()`：只處理 `selectedFile`（新上傳）走 `POST /api/transcribe`。完成檔 `selectedFile=null` → 乜都唔做。
- `app.py::re_transcribe_file`（`POST /api/files/<id>/transcribe`）：reset + enqueue ASR，但 `_asr_handler` 讀 `f.active_pipeline_snapshot` / `f.active_id`（上傳時 snapshot）→ 用舊 pipeline。

## 設計
**① Backend — re-run re-snapshot 當前 active**（`app.py::re_transcribe_file`）
喺 reset/enqueue 之前，將 file 嘅 `active_kind`/`active_id`/`active_pipeline_snapshot` 更新成**當前 strip 揀緊嘅 global active**：
```python
snap_kind, snap_aid = _current_active_snapshot()        # reads settings.json active_kind/active_id
_update_file(file_id, active_kind=snap_kind, active_id=snap_aid, active_pipeline_snapshot=None)
if snap_kind == "pipeline_v6":
    _snapshot_pipeline_at_upload(file_id)               # re-fills snapshot for the NEW pipeline
```
重用 upload 時嘅同一套 helper。Profile mode：`active_kind=profile`、`active_id=<profile_id>`、snapshot=None（`_asr_handler` profile 分支照行 active profile）。V6：re-snapshot 新 pipeline JSON。然後跑原有 reset（`status='transcribing'` + 清 segments/translations…）+ enqueue。**`_asr_handler` 即用新 pipeline。**

**② Frontend — enable 完成檔嘅執行掣**（`updateRunButton()`）
```js
const f = activeFileId ? uploadedFiles[activeFileId] : null;
if (f && f._local) { btn.disabled=false; btn.title='上傳並轉錄此檔案'; }
else if (f && !f._local && (f.status==='done' || f.status==='error')) {
  btn.disabled=false; btn.title='用當前 Pipeline 重新執行此檔案（會清掉現有 segments、譯文、批核狀態）';
} else { btn.disabled=true; btn.title='請先選擇或上傳檔案'; }
```

**③ Frontend — 執行掣分流**（`startTranscription()`）
頂部加 re-run 分支：
```js
if (!selectedFile && activeFileId) {
  const f = uploadedFiles[activeFileId];
  if (f && !f._local && (f.status==='done' || f.status==='error')) return rerunPipeline(activeFileId);
}
```
其餘 = 原有上傳流程不變。`rerunPipeline(id)`（已存在，L4655）有 confirm + `POST /api/files/<id>/transcribe` + toast，靠 backend ① 用新 pipeline。

## 一致性 nuance（已同 user confirm）
因為 fix 喺 backend re-run，**file card 嘅「🔄 重新執行」（同樣行 `POST /api/files/<id>/transcribe`）都會跟住用新揀嘅 pipeline**（之前用舊 snapshot）。一致 + 更直覺。

## 錯誤處理 / 兼容
- `_current_active_snapshot()` 失敗 / 無 active → 跟現有 default（profile / `active_profile`）。
- 跨 kind 切換（V6 檔 re-run 做 profile 或反之）：re-snapshot 改 `active_kind` → `_asr_handler` 按新 kind 正確路由；reset 清晒舊 segments/translations，clean run。
- mid-process（`transcribing`/`queued`）唔 enable 執行掣（只 done/error）。

## 測試
- **Backend pytest**：上傳檔 under pipeline A → set global active = pipeline B → `POST /api/files/<id>/transcribe` → 斷言 file `active_id==B` 且（V6）`active_pipeline_snapshot` 反映 B。涵蓋 profile→V6、V6→V6。
- **Frontend Playwright**：(a) 完成檔選中 → `#runBtn` 唔再 disabled + tooltip 啱；(b) `startTranscription()` 喺完成檔下打 `POST /api/files/<id>/transcribe`（route stub 斷言被 hit）；(c) 待上傳檔行原有上傳路徑（regression）。

## 範圍外
- per-file pipeline override（脫離 global active）；mid-process re-run；render-job re-run；queue panel 入面加 re-run 掣。

## Implementation 次序
見 plan `docs/superpowers/plans/2026-05-31-rerun-with-selected-pipeline-plan.md`。
