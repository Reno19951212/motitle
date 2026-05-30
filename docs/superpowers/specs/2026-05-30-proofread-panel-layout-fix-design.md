# Proofread 面板錯位修復 — 移除自訂 Prompt + 校正剩餘兩 panel 比例

**日期**：2026-05-30
**範圍**：`frontend/proofread.html`（純前端 + 對應 Playwright test）
**Branch**：`finalize-debug`
**狀態**：Design — 待 user review

---

## 1. 問題（已實證）

喺 MacBook 14"（邏輯解像度 1512×982）Chrome 上面，Proofread 頁面影片預覽下方嘅三個 module 區塊出現錯位：

1. **詞彙表**（`#glossaryPanel`）
2. **字幕設定**（`#subtitleSettingsPanel`）
3. **自訂 Prompt**（`#promptPanel`）

### 實測證據（Playwright DOM 量度 @ 1512×900）

容器 `.rv-b-vid-panels`：

```
grid-template-columns: 258px 258px   (= CSS 寫嘅 1fr 1fr，2 欄)
grid-template-rows:    88px 120px    (implicit rows，因為有第 3 個 child)
height: 220px;  max-height: 360px (40vh);  overflow: visible
childCount: 3  → [glossaryPanel, subtitleSettingsPanel, promptPanel]
```

| Panel | grid 位置 | 量度尺寸 | 問題 |
|---|---|---|---|
| 詞彙表 | row 1, col 1 | 258×**88px** | 被壓扁，太矮 |
| 字幕設定 | row 1, col 2 | 258×**88px** | 被壓扁，6 項設定只見到「字型 / 大小」 |
| 自訂 Prompt | **row 2, col 1 only** | 258×120px | 孤零零佔半欄，**col 2 係空白 void** |

截圖（`frontend/diag_proofread_videocol.png` / `diag_proofread_full.png`）肉眼確認：兩個頂部 panel 被擠到只剩約 88px，自訂 Prompt 落咗第二行左半，右半留白。

## 2. 根本原因

`.rv-b-vid-panels` 係一個 **2 欄固定高度 grid**（`grid-template-columns: 1fr 1fr; height: 220px; max-height: 40vh; overflow: visible`），原本（v3.0）只為 **2 個** panel 設計。v3.18 加入 `自訂 Prompt`（`#promptPanel`）時，將佢作為第 **3** 個 grid child 直接塞入同一個容器。

Grid auto-placement 因而產生一個 implicit 第 2 行：詞彙表 + 字幕設定 迫入 row 1（各 88px），自訂 Prompt 落 row 2 col 1（120px），固定 220px 高度被瓜分 → 頂部兩 panel 被壓扁、第 3 panel 半欄孤立。

更深層：`.rv-b-prompt-panel` 係 `display:block; overflow:visible; margin-top:8px`，**設計上係一個獨立垂直堆疊嘅 panel**，從來唔係 grid cell。當佢內容變高（Profile mode 有 4 個 open textarea），喺 `overflow:visible` 容器下會**溢出 220px 框、覆蓋下方波形/時間軸**。即係呢個係結構錯配，唔係單一 viewport 嘅 off-by-few-px。

## 3. 目標 / 決策

- **完全移除** 自訂 Prompt panel（HTML + CSS + JS），proofread 頁面唔再顯示、亦唔再提供 per-file prompt override 編輯入口（user 已確認）。
- **保留** 詞彙表 + 字幕設定，並校正佢哋嘅顯示比例同尺寸，令兩者回復正常高度、唔再被壓扁。
- per-file `prompt_overrides` 嘅**資料模型同 backend API 完全唔郁** — 只係移除 proofread 嘅 UI 入口。

## 4. 設計

### 4.1 完全移除自訂 Prompt（`frontend/proofread.html`）

> 行號為撰寫時快照，實施時以 **符號 / class 名** 為錨（編輯會令行號浮動）。

**HTML** — 刪整段 `#promptPanel` block：
- 由 `<!-- 自訂 Prompt (v3.18 Stage 2) -->`（~927）到 `</div>` 收 `#promptPanel`（~983）
- 保留下一行收 `.rv-b-vid-panels` 嘅 `</div>`（~984）

**CSS** — 刪 `自訂 Prompt Panel` 整組 rule（~355–426）：
`.rv-b-prompt-panel`、`.rv-b-prompt-scope`、`.rv-b-prompt-body`、`.rv-b-prompt-row`、`.rv-b-prompt-label`、`.rv-b-prompt-select`、`.rv-b-prompt-section`、`.rv-b-prompt-section > summary`、`.rv-b-prompt-section[open] > summary`、`.rv-b-prompt-textarea`、`.rv-b-prompt-actions`

**JS** — 刪「Prompt Panel (v3.18 Stage 2)」整段（~1796–1958），即 6 個 function：
`initPromptPanel()`、`showPromptPanelForFile()`、`applyPromptTemplate()`、`onPromptDirty()`、`clearPromptOverrides()`、`commitPromptOverrides()`
加 2 個 module 變量：`_promptTemplates`（~1055）、`_promptDirty`（~1056）
加 `init()` 內嘅 call site `initPromptPanel();`（~1988）

**移除後不變量（驗證項）**：
- `grep -i "prompt" proofread.html` 應只剩無關字眼（例如 native `prompt()`、`placeholder` 等），冇任何 `promptPanel` / `promptAnchor` / `promptQwen3Context` / `applyPromptTemplate` / `onPromptDirty` 等殘留 reference
- 開頁面 console 冇 `null is not an object` / `getElementById(...) is null` 類錯誤

### 4.2 校正剩餘兩 panel 比例 / 尺寸

移除第 3 child 後，`.rv-b-vid-panels` 變成 2 child / 2 欄 / 單行：

- **維持** `grid-template-columns: 1fr 1fr`（詞彙表 ‧ 字幕設定 各半）
- implicit 第 2 行消失 → 兩 panel 即刻由 88px 回復到容器全高（≈220px）→ 字幕設定 6 行（字型 / 大小 / 顏色 / 輪廓色 / 輪廓寬 / 底部邊距）唔再被切；詞彙表 table 喺自身 `overflow-y:auto` body 內 scroll
- **高度數值以實測為準**：字幕設定 6 行 + 標題 + padding 約需 ~210px。先用現有 `height: 220px; max-height: 40vh` 影 screenshot；若字幕設定仍有 scroll 或留白唔靚，微調高度（例如 220→240px）至 6 行啱啱好顯示。最終值由截圖確定，唔靠估。
- **保留** `@media (max-width: 1024px)` 單欄 stack 規則（`grid-template-columns: 1fr; height: auto; max-height: 50vh`）

### 4.3 驗證

- 重跑 / 改寫診斷 script（`frontend/diag_proofread_layout.mjs`），喺 **1512×982（MacBook 14"）** 影修復後 screenshot；另加 1–2 個闊度（例如 1280、≤1024 響應式斷點）對比
- DOM 量度確認 `.rv-b-vid-panels` 變返單行 2 欄、兩 panel 高度相等且 ≥ 內容所需
- console 零 JS error

### 4.4 測試

- **刪** `frontend/tests/test_prompt_panel.spec.js`（專測已移除嘅 panel，留住必然 fail）
- **檢查** `frontend/tests/test_v6_pipeline_strip.spec.js`：確認佢嘅 5 個 prompt-related 命中係 dashboard pipeline strip（另一組件）定有 coupling 到 proofread 已移除嘅 panel。若只 touch dashboard → 唔郁；若引用 proofread panel → 一齊修。
- 跑相關 Playwright 確認 proofread 載入、詞彙表 / 字幕設定 panel 正常。

## 5. 範圍外 / 備註（唔郁，除非另行要求）

- **Dashboard `📝 自訂` chip 保留**：`frontend/index.html` 約 2007–2009 行，當 file 有 `prompt_overrides` 時顯示 chip 並導航去 `proofread.html?file_id=...`。chip 仍代表「呢個檔案有 override」+ 導航功能；override 資料同 API 完全保留，只係 proofread 頁唔再有編輯入口。維持現狀。
- **Backend 完全唔郁**：`/api/prompt_templates`、`PATCH /api/files/<id>` 嘅 `prompt_overrides`、`/api/translate` 等全部保留，純前端移除。
- **診斷 artifact 清理**：`frontend/diag_proofread_layout.mjs`、`diag_proofread_*.png` 屬調查產物，唔 commit（驗證後刪除或留 local）。

## 6. 風險

| 風險 | 緩解 |
|---|---|
| JS 移除遺漏 reference → console error | 移除後 `grep` 全文件 + 開頁 console 檢查（4.1 不變量） |
| 字幕設定 6 行喺 220px 仍 scroll | 4.2 以截圖實測微調高度 |
| `test_v6_pipeline_strip.spec.js` 隱性 coupling | 4.4 明確檢查再決定郁唔郁 |
| 行號浮動令誤刪 | 以 class / 符號名為錨，逐段 grep 確認 |

## 7. 驗收標準

1. Proofread 頁面影片下方只剩 詞彙表 + 字幕設定 兩個 panel，並排各半、高度正常、字幕設定 6 行完整可見、詞彙表內部 scroll。
2. 自訂 Prompt panel 喺 proofread 頁面完全消失，console 零相關 JS error。
3. `frontend/proofread.html` 全文 grep 冇殘留 prompt-panel reference。
4. ≤1024px 響應式仍正常單欄 stack。
5. Playwright：`test_prompt_panel.spec.js` 已移除；其餘 proofread 相關 test 通過；`test_v6_pipeline_strip.spec.js` 通過（如需修則已修）。
6. Backend 零改動。
