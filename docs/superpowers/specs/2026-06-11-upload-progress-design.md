# 上傳進度 badge 設計（2026-06-11）

## 問題

Dashboard 上傳影片期間，三套狀態顯示機制全部空白：

| 機制 | 上傳期間表現 | 原因 |
|---|---|---|
| `#topProgress` 狀態卡 | 完全空白 | `langProgressRows` 讀 `f.languages`，`__pending__` placeholder 冇呢個 field（`index.html:2481`） |
| 工作隊列面板（queue-panel.js） | 唔出現 | 純 `/api/queue` 驅動，server 喺傳輸期間未有 job |
| 檔案卡 | 淨係「待上傳」badge，無進度 | `__pending__` placeholder（`index.html:4398-4413`） |

根本原因（兩層）：

1. **前端**：上傳用 `fetch()` + FormData（`startTranscription()`，`index.html:4686`）。`fetch()` 冇 upload progress API；全 codebase 冇任何 `XMLHttpRequest`。
2. **後端**：Werkzeug 將成個 multipart body 完整接收晒先至行 route code。`file_id` 喺 `app.py:4684` 先生成 — 傳輸期間 server 完全唔知有呢個檔案存在（冇 registry entry、冇 job、`/api/queue` 查唔到、`pipeline_progress` / `queue_changed` 發唔出）。

## 已確認嘅決定

1. **範圍**：淨係主影片上傳（`POST /api/transcribe`，最大 5GB）。字型上傳（≤32MB）同詞彙表 CSV 匯入唔做 — 秒級完成，YAGNI。
2. **顯示位置（用戶揀選項 C）**：淨係檔案卡 badge — 現有「待上傳」升級成「上傳中 N%」。`#topProgress` 同工作隊列面板**唔郁**（用戶知悉 topbar 狀態卡喺上傳期間會繼續空白，已確認接受）。
3. **技術路線**：客戶端 XHR — `fetch()` 換做 `XMLHttpRequest` + `upload.onprogress`。零後端改動。
4. **加項（已批准）**：pending 卡加「✕ 取消」掣（`xhr.abort()`）。

## 點解客戶端 XHR 係啱嘅路

- Production 拓撲係 werkzeug 直接 serve（`socketio.run`，`app.py:6101`），**冇 reverse proxy** — `upload.onprogress` 反映嘅係真實到達 server 嘅 bytes，唔會俾 proxy buffering 扭曲變假進度。
- 同源（`API_BASE=''`，`index.html:1789`），XHR 預設帶 session cookie，`@login_required` 照行，唔使任何 credentials 配置。
- 唔觸碰 pipeline progress contract 任何 invariant（上傳係 pre-job 階段，本身就唔屬於 `pipeline_progress` / `queue_changed` 嘅範疇）。
- **已否決嘅替代方案**：
  - *服務端 WSGI 上傳追蹤*（預申請 upload id + 包裝 input stream + socket 推送）— server-side truth，但要動 app boot 層，大改動高風險；揀咗最簡 UI（得個 badge）之下完全唔合比例。
  - *fetch + ReadableStream 上傳串流* — 需要 HTTP/2 而且 Safari 唔支援；werkzeug dev server 係 HTTP/1.1，行唔通。
  - *顯示選項 A / B*（topProgress 合成 row、queue panel 本機合成行）— 用戶揀咗 C，mockup 留底喺 `.superpowers/brainstorm/2514-1781170857/content/upload-location.html`。

## UX 流程

檔案卡 badge 生命週期：

```
揀檔案/拖放 → 確認 popup → [上傳中 0%…99%] → [處理緊…] → [排隊中/轉錄中]（現有流程接手）
```

- **上傳中 N%**：用現有 `badge--processing` 樣式（紫色 + pulsing dot），同「轉錄中 N%」「翻譯中 N%」視覺一致。
- **處理緊…**：bytes 送晒之後，server 仲要複製 spooled 臨時檔（`file.save`，`app.py:4687`）→ 註冊（`_register_file`，`app.py:4690`）→ 入隊（`app.py:4705`）先回 202。幾 GB MXF 呢段空窗用戶見得到 — 無百分比過渡狀態避免「100% 但冇反應」錯覺。`lengthComputable === false` 時都用呢個無百分比樣式（顯示「上傳中…」）。
- **✕ 取消**：pending 卡 badge 隔籬細掣，只喺上傳進行中出現。撳 → `xhr.abort()` → 安靜清理（唔彈錯誤）。
- 三個上傳入口（file picker / 拖放 `setupDropZone` / Cmd+U）全部匯流到 `setPendingFile()` → `startTranscription()` — 改一個 chokepoint 全部受惠。

## 技術設計

全部改動喺 `frontend/index.html`，零後端改動。

1. **`uploadWithProgress(formData, onProgress)` helper**：promise 包裝嘅 XHR，resolve `{status, json}`（容忍非 JSON body，例如 werkzeug 413 HTML）。`startTranscription()` 外層 async/await 結構不變，淨係將 `fetch(...)` 行換做呢個 helper。
2. **進度 state**：`upload.onprogress` 將 `Math.floor(e.loaded / e.total * 100)` 寫入 `uploadedFiles['__pending__'].uploadProgress`。**只喺整數百分比變化時**先觸發 DOM 更新（onprogress 發射頻率高，要節流）。
3. **Badge 渲染**：`stageBadgeHtml`（`index.html:2142`）嘅 `'pending'` case 由寫死「待上傳」改成讀 `uploadProgress`：
   - `undefined` →「待上傳」（未開始，行為不變）
   - `0–99` →「上傳中 N%」（`badge--processing`）
   - `>= 100` →「處理緊…」（`badge--processing`，無 %）
   - indeterminate（`lengthComputable === false`）→「上傳中…」（`badge--processing`，無 %）
4. **`fileStatusCategory` 唔使改**（`'pending'` 分類保持）。
5. **取消機制**：module-level `_activeUploadXhr` 持有進行中嘅 XHR；取消掣 call `abort()`；上傳結束（成功/失敗/取消）清返 `null`。同一時間最多得一個上傳（`isProcessing` flag 現有行為，`index.html:4668`）。

## 錯誤處理

- **前置 size check**：喺 `setPendingFile()`（揀檔/拖放後、開確認 popup 之前）驗 `file.size` > 5GB（同後端 `MAX_CONTENT_LENGTH`，`app.py:131` 一致）→ 即時友好錯誤，唔開 popup 唔開始上傳。前端 cap 值同後端要保持同步（寫做具名常數 + 註釋指向 `app.py:131`）。
- **HTTP 413**：保留現有 special-case（werkzeug 回 HTML 唔係 JSON，`index.html:4689-4692`）— 防禦超 cap 嘅漏網情況。
- **中途斷線**（`onerror`）：XHR 下 413 可能表現為中途連線錯誤而唔係乾淨 413 — 統一顯示友好錯誤（提示網絡問題或檔案過大）+ `clearPending()` 清理。
- **取消**（`onabort`）：安靜清理，唔彈錯誤。
- **死代碼清理**：現有 415 分支（`index.html:4694`）係死代碼 — 後端壞副檔名實際回 400（`app.py:4626`），冇任何後端代碼發 415 — 一併移除。
- 唔設 XHR timeout（大檔案合法地要好耐；現有 fetch 都冇 timeout）。

## 測試

前端係 vanilla JS、冇 build step、冇 JS test runner — 冇自動化單元測試基建。驗證計劃（手測 checklist 寫入 implementation plan）：

1. DevTools network throttle 慢速上傳 — 進度由 0% 推進到 99%，數字單調遞增。
2. 大檔案真實上傳 — 100% 之後出「處理緊…」，202 回覆後 badge 轉「排隊中/轉錄中」。
3. 三個錯誤路徑：✕ 取消（安靜清理）、中途斷線（友好錯誤 + 清理）、>5GB 檔案（前置即擋）。
4. 三個入口（picker / 拖放 / Cmd+U）行為一致。
5. 後端 pytest 唔受影響（零後端改動）。

## 不做範圍（out of scope）

- 字型上傳、詞彙表 CSV 匯入嘅進度顯示。
- `#topProgress` 狀態卡同工作隊列面板嘅上傳顯示（用戶揀咗 C，知悉取捨）。
- 服務端上傳追蹤 / 斷點續傳 / 多檔並行上傳。
- 重新處理、AI Rerun 等流程 — 已確認全部 JSON-only，唔會重傳檔案，唔受影響。
