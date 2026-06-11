# 校對頁尋找與取代（⌘F Find & Replace Popup）— Design

日期：2026-06-11 ｜ 狀態：✅ 設計＋v2 mockup 用戶已批准 ｜ Branch: `worktree-proofread-find`
Mockup 基準：`.superpowers/brainstorm/72767-1781167108/content/popup-v2.html`（680px 放大版，用戶確認「照呢個做」）

## 目標

校對頁 `⌘F` 彈一個**非阻擋式浮動「尋找與取代」視窗**：打字即時列出全部語言欄嘅 match、撳行跳段；每行「取代／取代並批核／略過」逐句處理，另有「全部取代」批量。**成套取代現有 find bar**（用戶決定 1：唯一 ⌘F 介面）。

## 用戶決策記錄

1. **舊 find bar 成套剷走**（markup `#findBar` proofread.html:899-932 + `fb*` JS ~3599-3760 + keydown 接線）— 新 popup 係唯一 ⌘F UI；舊 bar 嘅「只搜未批核」「全部取代」功能喺新 UI 保留
2. **取代流程 = 清單式（方案 A）**：全部 match 一眼睇晒，每行自帶動作掣，唔係 Word 式逐個行進
3. **批核狀態**：每行三掣 —「**取代**」（文字改、批核狀態**保持原狀**）、「**取代並批核**」（文字改＋轉已批核）、「**略過**」；「全部取代」行「保持原狀」語義
4. **v2 視覺**（mockup 已批准）：680px 闊、雙欄輸入（尋找｜取代為）、行內 段號+timecode+語言tag、before→after 預覽、唯讀 tag、底部統計欄

## UI 規格（照 v2 mockup）

- **視窗**：680px 闊（`max-width:94vw`）、`max-height:560px`，列表區內部捲動；浮喺影片區上方置中（`position:fixed`）；**頭部可拖動**（⠿）；非阻擋（無 overlay dim — 開住照樣撳段落表／播片）；`Esc` 關、`⌘F` 開（再撳 focus 返搜尋框）；關閉後重開保留上次 查詢/取代 文字
- **輸入區**：左「尋找（全部語言欄）」右「取代為」，並排兩欄；搜尋框右端嵌計數「N 個 · M 段」（N=出現次數，M=涉及段數）
- **選項行**：「只搜未批核」checkbox ＋ 提示「撳行＝跳去嗰段＋影片預覽」＋ 右端「**全部取代 (N)**」（N=剩餘可取代行數）
- **Match 列表**：每行 = 一個 `(段, 語言欄)` 組合（同一段同欄多次出現算一行，取代時 `replaceAll`）：
  - 左：`#段號`（粗體）＋ timecode（mono）＋ 語言 tag（第一語言／第二語言／原文／譯文，跟 `_outputLangLabel` 現有命名）
  - 中：文字預覽，關鍵字紫 highlight；「取代為」非空時顯示 `舊句 → 新句`（新字綠 highlight）
  - 右：「取代」「取代並批核」「略過」三掣；**唯讀欄**（V6/profile 檔嘅原文 en 欄）冇掣、行半透明、顯示「唯讀」tag
  - 完成態：`✓ 已取代`（綠）／`✓ 已取代＋批核`（深綠），行灰化留喺列表；「已略過 · 還原」可撳還原
  - **撳行**（非掣位置）= `setCursor(idx, true)` 跳段＋影片 seek；段落表 match 行同步 highlight（沿用舊 fb 嘅 rail highlight 概念）
- **底部**：`已取代 X · 略過 Y · 剩 Z` ＋ 快捷鍵提示（`Esc` 關閉）

## 搜尋行為

- 純前端：搜 `segs[]` 記憶體（`s.en`/`s.zh` 即第一/第二語言欄文字），**唔行後端**；input 150ms debounce
- 子字串匹配；拉丁字母大小寫不敏感（`toLowerCase` 兩邊）；中文天然精確
- 「只搜未批核」= 過濾 `s.approved` 行
- 空查詢 → 清列表＋rail highlight；查詢改變 → reset 略過/完成記錄
- 適用所有檔案 kind（搜尋）；**取代掣只出現喺可編輯欄**：output_lang 兩欄都得；legacy profile 譯文(zh)欄得、原文(en)欄唯讀顯示；V6 原文欄唯讀

## 取代寫入（後端一個小改動）

- 行現有 `PATCH /api/files/<id>/translations/<idx>`，body `{text, role?, keep_status?}`：
  - **新增可選 `keep_status: true`** — 跳過 auto-approve（row `status`、`by_lang[lang].status` 都唔郁）；**唔傳 = 照舊 auto-approve**，現有 callers 零影響
  - 「取代」→ `keep_status:true`；「取代並批核」→ 唔傳（沿用 auto-approve）
  - `aligned_bilingual[idx].by_lang` 同步 PATCH 已有（2026-06-10 修），唔使加嘢
- 取代文字喺**撳掣嗰刻**由 `segs[idx]` 現值計（唔用搜尋時 snapshot — 防止期間其他編輯被覆蓋）；`replaceAll` 該欄全部出現
- 連續取代／全部取代用 promise chain **串行**（防亂序 reconcile，同 timing PATCH 一致）
- 成功後：更新 `segs[]`、重繪 rail/detail、行轉完成態；失敗 → error toast + 行保持可撳
- 「全部取代」逐行串行行「取代」（keep_status），完成 toast 總結 `成功 X／失敗 Y`

## 檔案結構

- **新檔 `frontend/js/find-replace.js`**（~300 行，classic script，照 `files-export.js` 模式）：popup markup 注入、搜尋/取代邏輯、拖動、鍵盤接線。proofread.html 嘅頂層 `let segs/cursorIdx/fileInfo/setCursor/renderSegList/...` 係 global scope，classic script 直接讀到 — proofread.html 只需 `<script src>` 一行＋剷舊 bar
- **剷除**：`#findBar` markup、`.find-bar*` CSS、`fb*` JS 全套、keydown 入面 `openFindBar` 接線（⌘F 改接新 popup）
- **後端**：`app.py` PATCH translations handler 加 `keep_status` 分支（~6 行）

## 唔做（YAGNI）

regex／whole-word 模式、復原（undo）已取代、跨檔案搜尋、取代歷史、第二語言欄逐 occurrence 部分取代（成欄 replaceAll）、行進式鍵盤模式（方案 B）。

## 測試

1. **pytest**（`tests/test_find_replace_patch.py`）：`keep_status:true` 保持 row/by_lang status＋文字有改＋mirrors 同步；唔傳 `keep_status` 照舊 auto-approve（regression）；`keep_status` + `role:'second'` 組合
2. **Playwright E2E**（真檔）：⌘F 開視窗；打字即時列 match＋計數；撳行跳段；「取代」後文字改＋狀態唔變（API 覆核）；「取代並批核」後狀態 approved；「略過／還原」；「全部取代」；V6 檔原文欄唯讀冇掣；Esc 關＋⌘F 重開保留查詢；舊 find bar 唔存在
