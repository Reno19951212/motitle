# Design — 校對頁詞彙表面板：搜尋 + 完整條目編輯 modal

**Date**: 2026-07-15
**Branch**: `feat/glossary-fuzzy-match`
**依賴**: Plan B 已落地（`source_variants` 資料模型 + PATCH/POST entries 已收該欄位）

---

## 1. 問題

校對頁面（`proofread.html`）嘅 output_lang 詞彙表面板有自己一套條目編輯 code，同 `Glossary.html` 分開，**冇跟到 Plan B**：

- **冇搜尋** — 揀咗一本詞彙表（例：賽馬 1,354 條）之後，`renderGlossaryTable` 淨係一次過列晒所有條目，冇得搜原文/譯文。
- **編輯冇近音別名** — 撳 ✎（`startEditEntry`）只 inline 改「原文 + 譯文」兩欄；PATCH body 只有 `{source, target}`。用戶喺呢度加唔到 `source_variants`（近音寫法）或 `target_aliases`（別名）。

即係 Plan B 喺 Glossary.html 加咗嘅能力，喺校對頁「填得落」流程入面缺席 —— 而校對正正係用戶發現聽錯、最想即刻補別名嘅時刻。

## 2. 方案（純前端，零後端改動）

後端 `PATCH /api/glossaries/<gid>/entries/<eid>` 同 `POST .../entries` 經 `update_entry` / `add_entry` **已經**收 `source_variants` + `target_aliases`（Plan B Task 5 驗證過），GET 亦回傳呢兩欄。所以本功能全部喺 `proofread.html` 面板 JS 完成。

### 2.1 條目搜尋
- 條目表（`#glossaryBody`）上面加搜尋框 `🔍 搜尋原文/譯文/近音…`。
- 純前端 filter `glossaryEntries`，比對 `source` / `target` / `source_variants[]` / `target_aliases[]`；拉丁大小寫不敏感。
- 即時 re-render 表格；模組變數 `_glEntryQuery` 記住查詢，`renderGlossaryTable` 尊重佢。
- 揀咗詞彙表、載入條目後先顯示（空詞彙表唔顯示）。

### 2.2 條目編輯 modal（編輯 + 新增共用）
- 新 modal DOM `#geOverlay`（跟現有 `ae-*` / `gr-*` modal 風格）。
- 觸發：✎ → `openEntryModal(eid)`（預填該條目）；「+新增」→ `openEntryModal(null)`（空白）。**兩者共用同一個編輯器。**
- 欄位：
  - 原文（`source`）input
  - 譯文（`target`）input
  - **近音寫法（原文別名）** = `source_variants` chip 列（`+加入` 用 `prompt()` / `×` 移除）
  - **別名（譯文）** = `target_aliases` chip 列（同上）
  - 取消 / 儲存
- 鍵盤：Enter 儲存、Esc 關（同 `ae-*` / `gr-*` 一致）；chip 序列化用一個 modal-local busy flag（防連撳未 re-render 就再改，仿 Glossary.html `_aliasSaveBusy`）。
- 儲存：
  - `eid` 有 → `PATCH /entries/<eid>`；`eid` 為 null → `POST /entries`。
  - body `{source, target, source_variants, target_aliases}`。
  - 成功 → 關 modal → `loadGlossaryEntries` 重載 → `renderGlossaryTable`（保留搜尋 filter）→ toast。

### 2.3 每行 badge（順手，低成本）
- 條目表原文欄後跟「·近N」（N = `source_variants` 數）小提示，令用戶一眼睇到邊啲詞條已有近音別名（對齊 Glossary.html 表格 badge）。

## 3. 取代嘅舊 code
- `startEditEntry` / `saveEditEntry`（inline 兩欄改）→ 由 modal 取代。
- `addGlossaryEntry` / `saveNewEntry` / `cancelNewEntry`（inline 加行）→ 由 modal 取代（`openEntryModal(null)`）。
- `renderGlossaryTable` 保留，但 ✎ 改 call `openEntryModal(eid)`、行 filter + badge。

## 4. 邊界處理
- **共享表權限**：賽馬表（`db323f9d`）係 shared（`user_id=None`）→ 非管理員 PATCH/POST 後端 return **403**，modal 儲存捕捉 → toast「你冇權改共享詞彙表（需管理員）」。管理員不受影響。
- 原文/譯文 trim 後為空 → 擋 + toast，唔送出。
- 儲存出錯 → toast + modal **唔關**（可重試）。
- 別名 chip 空白/重複 → 前端 trim + 去重（後端 `_normalize_entry` 亦會 strip quote；`validate_entry` 驗 `source_variants` 必須 list）。

## 5. XSS
- 所有插值（source / target / 每個 variant / 每個 alias / 詞彙表名）一律過 `escapeHtml`。
- chip 移除掣用 `data-idx`（整數）+ event delegation，唔用 inline onclick 帶字串值（避開 Plan B review 揪過嘅 inline-onclick 字串 XSS class）。

## 6. 測試
- **Playwright E2E**（延續 `scratchpad/planb_e2e.py` 模式，跑 :5011）：
  1. 揀詞彙表 → 搜尋框出現 → 打字 filter 條目表。
  2. ✎ 開 modal → 見到原文/譯文 + 近音寫法 + 別名 chip。
  3. 加一個近音寫法 → 儲存 → `GET /api/glossaries/<id>` 確認 `source_variants` persist。
  4. 「+新增」→ 同一 modal 全欄位 → 存 → 條目出現。
- **手動**：:5011 校對頁真試（含賽馬共享表 admin 情境）。
- 用丟棄式測試詞彙表做寫入驗證，唔郁真賽馬表。

## 7. 檔案
- 只改 `frontend/proofread.html`（新 modal DOM + 面板 JS，約 +130 行；移走 cramped inline 編輯邏輯 —— 淨改動接近持平）。
- **無後端改動、無新 endpoint。**

## 8. 明確唔做（YAGNI / scope）
- 唔改後端（endpoint 已足夠）。
- chip 加入唔做 modal 內 inline 打字（用 `prompt()` 對齊 Glossary.html）— 用戶已定。
- 唔掂 profile/V6 舊模式面板（`#glossarySelect` dropdown）— 本功能只針對 output_lang 面板（用戶實際用嘅）。
- 唔改掃描 modal（`glossary-review.js` 疑似聽錯一鍵 = 另一條互補路，已完成）。
