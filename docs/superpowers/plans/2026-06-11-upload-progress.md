# 上傳進度 Badge 實施計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard 上傳影片期間，檔案卡 badge 由死板「待上傳」變成實時「上傳中 N%」→「處理緊…」，並支援取消上傳。

**Architecture:** 純前端改動（`frontend/index.html` 單檔）。`startTranscription()` 嘅 `fetch()` 換成 promise 包裝嘅 `XMLHttpRequest`（`upload.onprogress` 攞真實已傳 bytes），進度寫入 `uploadedFiles['__pending__'].uploadProgress`，`stageBadgeHtml` 嘅 `'pending'` case 讀佢渲染。零後端改動。Spec：`docs/superpowers/specs/2026-06-11-upload-progress-design.md`。

**Tech Stack:** Vanilla JS（無 build step、無 JS test runner — 驗證靠手測 checklist，spec 已確認）。

**重要背景（執行者必讀）：**
- 後端 Werkzeug 全量緩衝 multipart body 先行 route — 傳輸期間 server 唔知有呢個檔案，所以進度只可以喺客戶端攞（`XMLHttpRequest.upload.onprogress`）。
- Production 冇 reverse proxy（werkzeug 直接 serve）— onprogress 數字反映真實到達 server 嘅 bytes。
- 三個上傳入口（file picker `handleFileSelect` / 拖放 `setupDropZone` / Cmd+U）全部匯流到 `setPendingFile()` → `startTranscription()` — 改一處全部受惠。
- 行號以 worktree `worktree-upload-progress` @ `4142152` 為準；同一檔案改幾處之後行號會郁，請以函數名 + 引文搜尋定位。
- 項目慣例：commit message 用 `<type>: <廣東話描述>`，無 attribution。

---

### Task 1: 前置 size check（揀檔即擋超過 5GB）

**Files:**
- Modify: `frontend/index.html` — `setPendingFile()`（~line 4398）

- [ ] **Step 1: 加常數 + 檢查**

喺 `setPendingFile` 函數定義正上方加常數，並喺函數開頭加 guard：

```js
    // 同後端 app.config['MAX_CONTENT_LENGTH']（backend/app.py:131, 5GB）保持同步
    const MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024;

    function setPendingFile(file) {
      if (file.size > MAX_UPLOAD_BYTES) {
        const gb = (file.size / 1024 / 1024 / 1024).toFixed(2);
        showToast(`檔案太大（${gb} GB），超出 5GB 上限`, 'error');
        return;
      }
      selectedFile = file;
      // …（其餘原有內容不變）
```

- [ ] **Step 2: 手動驗證**

冇 >5GB 測試檔嘅話，臨時將 `MAX_UPLOAD_BYTES` 改細（例如 `1024`）→ 揀任何影片 → 預期：紅色 toast「檔案太大…」、唔開 popup、`uploadedFiles` 冇 `__pending__`。驗完改返 `5 * 1024 * 1024 * 1024`。

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(upload): 揀檔前置 5GB size check — 唔使傳完先收 413"
```

---

### Task 2: `uploadWithProgress` XHR helper + 取消機制

**Files:**
- Modify: `frontend/index.html` — `startTranscription()` 正上方（~line 4644）

- [ ] **Step 1: 加 helper + module state**

喺 `startTranscription()` 函數定義正上方插入：

```js
    // 進行中嘅上傳 XHR — 同一時間最多一個（isProcessing 已鎖 UI）。
    // 取消上傳 = abort() → onabort → startTranscription catch 統一清理。
    let _activeUploadXhr = null;

    // fetch() 冇 upload progress API — 用 XHR 包裝做 promise。
    // resolve {status, json}（json 容忍非 JSON body，例如 werkzeug 413 HTML → null）。
    function uploadWithProgress(url, formData, onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        _activeUploadXhr = xhr;
        xhr.open('POST', url);
        xhr.upload.onprogress = (e) => {
          // lengthComputable=false → null = indeterminate（badge 顯示「上傳中…」無 %）
          onProgress(e.lengthComputable ? Math.min(100, Math.floor((e.loaded / e.total) * 100)) : null);
        };
        xhr.onload = () => {
          _activeUploadXhr = null;
          let json = null;
          try { json = JSON.parse(xhr.responseText); } catch {}
          resolve({ status: xhr.status, json });
        };
        xhr.onerror = () => {
          _activeUploadXhr = null;
          // XHR 下超 5GB cap 可能表現為中途連線錯誤而唔係乾淨 413
          reject(new Error('網絡錯誤或連線中斷 — 請檢查網絡，或確認檔案未超過 5GB 上限'));
        };
        xhr.onabort = () => {
          _activeUploadXhr = null;
          reject(Object.assign(new Error('已取消上傳'), { _aborted: true }));
        };
        xhr.send(formData);
      });
    }

    // 上傳取消：有 XHR 就 abort（清理由 onabort → catch 做）；
    // 未開始上傳（popup 階段）就直接清 pending 卡。
    function cancelUpload() {
      if (_activeUploadXhr) { _activeUploadXhr.abort(); return; }
      clearPending();
    }
```

- [ ] **Step 2: `armOrConfirmDelete` 嘅 `_local` 分支改行 `cancelUpload()`**

現有代碼（~line 4764，**未改 Task 4 前行號**）：

```js
      // Local pending entry: just clear
      if (uploadedFiles[id]?._local) { clearPending(); return; }
```

改成：

```js
      // Local pending entry: 上傳中 abort（onabort 統一清理），未上傳就直接清
      if (uploadedFiles[id]?._local) { cancelUpload(); return; }
```

> 修復 latent bug：上傳中撳 ✕ 淨 `clearPending()` 會留低 phantom XHR 繼續上傳，完成時 `selectedFile.name` null-deref。

- [ ] **Step 3: 手動驗證（語法層面）**

重新整理 dashboard 頁，console 冇 SyntaxError；揀檔 → popup 出現 → 撳 pending 卡 ✕ → 卡即消失（未上傳階段行為同以前一致）。

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(upload): uploadWithProgress XHR helper + cancelUpload（abort 統一清理）"
```

---

### Task 3: Badge 四態渲染 + 節流進度更新

**Files:**
- Modify: `frontend/index.html` — `stageBadgeHtml()` 嘅 `'pending'` case（~line 2159）+ 新函數 `_setUploadProgress`

- [ ] **Step 1: `stageBadgeHtml` 嘅 `'pending'` case 改四態**

現有代碼：

```js
        case 'pending':
          return `<span class="badge badge--idle">待上傳</span>`;
```

改成：

```js
        case 'pending': {
          const up = f.uploadProgress;
          // undefined = 未開始上傳（popup 階段）— 行為不變
          if (up === undefined) return `<span class="badge badge--idle">待上傳</span>`;
          // null = lengthComputable false（indeterminate）
          if (up === null) return `<span class="badge badge--processing"><span class="dot" style="animation:pulse 1.3s infinite"></span> 上傳中…</span>`;
          // bytes 送晒，等 server file.save/註冊/入隊回 202 — 呢段空窗大檔好明顯
          if (up >= 100) return `<span class="badge badge--processing"><span class="dot" style="animation:pulse 1.3s infinite"></span> 處理緊…</span>`;
          return `<span class="badge badge--processing"><span class="dot" style="animation:pulse 1.3s infinite"></span> 上傳中 ${up}%</span>`;
        }
```

- [ ] **Step 2: 加 `_setUploadProgress`（節流 + 靶向 DOM 更新）**

喺 `stageBadgeHtml()` 函數之後加：

```js
    // 上傳進度寫入 + 靶向更新 badge。onprogress 發射頻率高（可達每秒幾十次），
    // 只喺整數百分比變化時先郁 DOM；只換 badge outerHTML，唔重建成個 queue list
    // （避免 hover/取消掣俾 innerHTML rebuild 打斷）。
    function _setUploadProgress(pct) {
      const p = uploadedFiles['__pending__'];
      if (!p || p.uploadProgress === pct) return;
      uploadedFiles['__pending__'] = { ...p, uploadProgress: pct };
      const host = document.querySelector('.queue-item[data-file-id="__pending__"] .qh');
      if (!host) { renderQueue(); return; }
      const badge = host.querySelector('.badge');
      if (badge) badge.outerHTML = stageBadgeHtml(uploadedFiles['__pending__']);
    }
```

> 注：pending 卡冇 `prompt_overrides`，`.qh` 入面只有一個 `.badge`，selector 唔會誤中 promptChip。

- [ ] **Step 3: 手動驗證**

Console 試：`uploadedFiles['__pending__'] = {id:'__pending__', original_name:'t.mp4', status:'pending', uploaded_at: Date.now()/1000, _local:true}; renderQueue(); _setUploadProgress(42);` → badge 變「上傳中 42%」；`_setUploadProgress(100)` → 「處理緊…」；`_setUploadProgress(null)` → 「上傳中…」。驗完 `delete uploadedFiles['__pending__']; renderQueue();`。

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(upload): pending badge 四態（待上傳/上傳中 N%/上傳中…/處理緊…）+ 節流靶向更新"
```

---

### Task 4: `startTranscription` 接線 XHR + 取消掣 + 錯誤路徑

**Files:**
- Modify: `frontend/index.html` — `startTranscription()`（~line 4645）+ `renderQueue()` 嘅卡片 actions（~line 2299）

- [ ] **Step 1: 換走 fetch 段**

`startTranscription()` 內，由 `try {` 開始到 `const data = await resp.json();` 嘅現有代碼：

```js
      try {
        const resp = await fetch(`${API_BASE}/api/transcribe`, { method: 'POST', body: formData });

        // 413 returns HTML from werkzeug — surface a specific message instead of JSON parse error
        if (resp.status === 413) {
          const mb = (selectedFile.size / 1024 / 1024).toFixed(1);
          throw new Error(`檔案太大（${mb} MB），超出後端 5GB 上限`);
        }
        // R6 audit E9 — surface 415 (wrong type) as a clear message
        if (resp.status === 415) {
          throw new Error('檔案類型不支援，請使用 MP4 / MOV / MKV / MXF / WAV / MP3 等格式');
        }
        if (!resp.ok) {
          let msg = `HTTP ${resp.status}`;
          try { const err = await resp.json(); if (err.error) msg = err.error; } catch {}
          throw new Error(msg);
        }
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
```

改成（415 死代碼分支移除 — 後端壞副檔名實際回 400 `app.py:4626`，冇任何後端代碼發 415）：

```js
      try {
        // 上傳開始 — badge 入「上傳中 0%」，full render 令「取消上傳」掣出現
        if (uploadedFiles['__pending__']) {
          uploadedFiles['__pending__'] = { ...uploadedFiles['__pending__'], uploadProgress: 0 };
          renderQueue();
        }
        const { status, json } = await uploadWithProgress(
          `${API_BASE}/api/transcribe`, formData, _setUploadProgress);

        // 413 returns HTML from werkzeug — surface a specific message instead of JSON parse error
        if (status === 413) {
          const mb = (selectedFile.size / 1024 / 1024).toFixed(1);
          throw new Error(`檔案太大（${mb} MB），超出後端 5GB 上限`);
        }
        if (status < 200 || status >= 300) {
          throw new Error((json && json.error) ? json.error : `HTTP ${status}`);
        }
        const data = json;
        if (!data) throw new Error('伺服器回應格式錯誤');
        if (data.error) throw new Error(data.error);
```

- [ ] **Step 2: catch 段識別取消（安靜清理，唔彈錯誤）**

現有 catch：

```js
      } catch (err) {
        // R6 audit E10 — clean up the pending placeholder card on upload
        // failure. Otherwise the queueList shows a phantom "pending" row
        // forever and the user has to manually delete it.
        clearPending();
        showToast(`上傳失敗: ${err.message}`, 'error');
        isProcessing = false;
      }
```

改成：

```js
      } catch (err) {
        // R6 audit E10 — clean up the pending placeholder card on upload
        // failure. Otherwise the queueList shows a phantom "pending" row
        // forever and the user has to manually delete it.
        clearPending();
        // 用戶主動取消（xhr.abort）— 安靜清理，唔彈錯誤
        if (!err._aborted) showToast(`上傳失敗: ${err.message}`, 'error');
        isProcessing = false;
      }
```

- [ ] **Step 3: 卡片加「取消上傳」掣**

`renderQueue()` 內，現有 job 取消 block（搜尋 `queueCancelBtn-`）之後、`</div>\`;` 之前加：

```js
            ${cat === 'pending' && f.uploadProgress !== undefined ? `
              <div class="q-actions" onclick="event.stopPropagation()">
                <button class="btn-secondary" data-testid="upload-cancel"
                        onclick="cancelUpload()">取消上傳</button>
              </div>
            ` : ''}
```

> 跟現有 `cancelJob` 取消掣同一個視覺模式（`q-actions` + `btn-secondary`）。只喺上傳真係開始咗（`uploadProgress !== undefined`）先出現。

- [ ] **Step 4: 手動驗證（核心流程）**

1. 開後端（`./start.sh` 或現有 dev server）、登入 dashboard。
2. DevTools → Network → throttle 揀「Fast 4G」（或 custom 細上傳速度）。
3. 揀一個 ≥50MB 影片 → 確認 popup → 撳開始。
4. 預期：badge「上傳中 0%」開始單調遞增 → 100% 後轉「處理緊…」→ 202 後卡片換新 file entry、badge「排隊中/轉錄中」、toast「文件上傳成功，開始轉錄...」。
5. 期間「取消上傳」掣一直可見；hover 唔會閃跳（badge 更新唔重建成個卡）。

- [ ] **Step 5: 手動驗證（三個錯誤路徑）**

1. **取消**：上傳中途撳「取消上傳」→ 卡即消失、冇錯誤 toast、console 冇 error；撳 pending 卡 ✕ 同效。
2. **斷線**：上傳中途 DevTools Network 揀「Offline」→ 紅 toast「上傳失敗: 網絡錯誤或連線中斷…」、pending 卡清走、`isProcessing` 解鎖（可以再揀檔）。
3. **入口一致**：file picker / 拖放 / Cmd+U 三個入口逐個試 — 行為一致。

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html
git commit -m "feat(upload): startTranscription 接線 XHR 進度 + 取消上傳掣 + abort 安靜清理（清 415 死代碼）"
```

---

### Task 5: 後端無恙確認 + 回歸手測

**Files:** 無改動 — 純驗證

- [ ] **Step 1: 後端 pytest（單檔模式 — full-suite 有已知 order-dependent 失敗，唔好信全套紅字）**

```bash
cd backend && source venv/bin/activate
pytest tests/test_api_transcribe.py -v 2>/dev/null || pytest tests/ -k "transcribe and api" -v
```

預期：PASS（零後端改動，呢步係保險）。如果 worktree 冇 venv，喺主 checkout 行（代碼一樣 — 唔好 cd 過去，用 `--rootdir` 或直接喺主 checkout 開另一個 shell）。

- [ ] **Step 2: 回歸手測**

1. 正常細檔上傳（唔 throttle）— 流程完整行通，badge 可能一閃而過直接「處理緊…」→「轉錄中」，正常。
2. 上傳成功後輸出語言、轉錄、翻譯照舊行（揀 mock/細模型 profile 快速驗）。
3. 重新處理（reprocess popup）一個已完成檔案 — 確認唔受影響（JSON-only path，冇 badge 變化）。

- [ ] **Step 3: 將手測結果記入 commit（如有修正就一齊 commit）**

```bash
git add -A
git commit -m "fix(upload): 手測回歸修正" # 如有先 commit；冇就跳過
```

---

### Task 6: 文檔更新（項目強制要求）

**Files:**
- Modify: `CLAUDE.md` — Current State 加一段
- Modify: `README.md` — 用戶說明（繁體中文）

- [ ] **Step 1: CLAUDE.md Current State 段加**

喺 `## Current State & Recent Highlights` 適當位置（最新條目區）加：

```markdown
### Upload progress badge (dashboard, NEW 2026-06-11)

- 上傳影片期間，檔案卡 badge 實時顯示「上傳中 N%」（XHR `upload.onprogress`，fetch 已換走）→ bytes 送晒後「處理緊…」（server file.save/註冊/入隊空窗）→ 202 後接返現有「排隊中/轉錄中」。`lengthComputable=false` 時顯示「上傳中…」無 %。
- 「取消上傳」掣（`q-actions` 模式）+ pending 卡 ✕ 都行 `cancelUpload()`（`xhr.abort()` → 安靜清理）；揀檔時前置 5GB size check（同 `MAX_CONTENT_LENGTH` 同步，`app.py:131`）。
- 純前端（`index.html` 單檔）：`uploadWithProgress()` helper、`uploadedFiles['__pending__'].uploadProgress` field、`stageBadgeHtml` pending case 四態、`_setUploadProgress()` 節流靶向 badge 更新。**零後端改動**；`#topProgress` 同 queue panel 上傳期間維持原狀（用戶揀咗最簡方案 — spec: docs/superpowers/specs/2026-06-11-upload-progress-design.md）。死代碼 415 分支已清（後端實際回 400）。
```

- [ ] **Step 2: README.md 用戶說明**

喺上傳相關章節（搜尋「上傳」搵啱位）加一小段（繁體中文）：

```markdown
### 上傳進度

上傳影片時，左側檔案卡會實時顯示「上傳中 N%」。大檔案去到 100% 後會見到「處理緊…」幾秒（伺服器接收緊檔案），之後自動開始轉錄。上傳期間可以撳「取消上傳」即時中止；超過 5GB 嘅檔案會喺揀檔時即時提示，唔會白等。
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: 上傳進度 badge（CLAUDE.md Current State + README 用戶說明）"
```

---

## 驗證總 checklist（完工前逐項過）

- [ ] 慢速 throttle 下進度 0%→99% 單調遞增，100% 後「處理緊…」
- [ ] 取消上傳（掣 + ✕ 兩路）安靜清理，冇 phantom XHR（Network tab 確認 request cancelled）
- [ ] 斷線顯示友好錯誤 + 清理 + UI 解鎖
- [ ] >5GB 揀檔即擋（臨時改細常數驗）
- [ ] 三個入口（picker / 拖放 / Cmd+U）一致
- [ ] 上傳成功後全 pipeline 照舊（轉錄/翻譯/badge 過渡）
- [ ] 重新處理唔受影響
- [ ] 後端 pytest 單檔 PASS
- [ ] CLAUDE.md + README.md 已更新
