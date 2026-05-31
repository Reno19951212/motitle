# 統一左側欄（5-item rail）— Design（Task A）

**日期**：2026-05-31 ｜ **狀態**：Design — 待 user review ｜ **Branch**：`fix/profile-and-v6`
**範圍**：純前端 nav 一致化。後端零改動。**Task B（砌 User 頁）係之後獨立 cycle。**

---

## 1. 問題 / 目標
各頁（`index.html` / `proofread.html` / `Glossary.html` / `admin.html`）嘅最左側 rail 各有唔同、項目唔一致（index 仲有 Pipeline + 語言 + 服務狀態齒輪）。統一所有頁嘅 rail 為**剛好 5 個 nav item**：

| # | 標籤 | 連去 | 圖示（沿用現有 SVG 風格）|
|---|---|---|---|
| 1 | 主頁 | `index.html`（home view）| 屋 |
| 2 | 檔案 | `index.html`（files view）| 影片/列表 |
| 3 | 校對 | `proofread.html` | 鉛筆 |
| 4 | 術語表 | `Glossary.html` | 書 |
| 5 | User | `user.html`（新 placeholder）| 人像 |

## 2. 架構
專案係 vanilla HTML、無 build step、每頁各自 inline 自己嘅 rail（既有 pattern）。**唔引入 build / shared-include**（YAGNI，跟現狀）。做法：每頁寫**同一套 5-item rail markup**，只差兩點：
- **Active-state**：當前頁嘅 item 加 `class="rail-btn on"`。
- **In-page route vs cross-page link**：
  - 喺 `index.html`：主頁 / 檔案 用現有 `<button class="rail-btn" data-route="home|files">`（in-page view 切換，保留現有 data-route 邏輯）；校對 / 術語表 / User 用 `<a class="rail-btn" href="…">`。
  - 喺其他頁（proofread / Glossary / user / admin）：5 個全部 `<a class="rail-btn" href="…">`（主頁→`index.html`、檔案→`index.html`、校對→`proofread.html`、術語表→`Glossary.html`、User→`user.html`），當前頁 item active。
- rail 容器 + `.rail-btn` CSS 各頁已存在且一致，沿用。

## 3. 移除項嘅去向（功能不失）
- **Pipeline**（index rail `data-route="pipeline"`）：rail 移除。Pipeline 切換靠**頂部 pipeline strip**（已存在）。
- **語言（語言配置面板，index rail `data-route="lang"`）**：rail 移除；面板本身**保留**，trigger 搬去 **topbar 設定齒輪**（新增一個 `⚙ 設定` 按鈕喺 `.health-cluster` / topbar 右側，撳開現有 language-config 面板）。Task B 再正式搬入 User 頁設定區。
- **服務狀態 / restart 齒輪**（index rail bottom `#restartBtn`）：唔當 nav → 搬去 topbar utility 區（同 health-cluster 一齊），令 rail 純淨得返 5 個 nav。
- **管理 ⚙ adminLink**（index topbar `#adminLink href=/admin.html`，admin-only）：保留現狀（topbar，admin 先見）；Task B 會考慮吸納入 User 頁。

## 4. 新 `user.html`（Task A 只做 placeholder）
- 用同一頁面骨架（topbar + 5-item rail，User active）+ 一個中央 placeholder：「User 介面（建設中）— admin/user 管理 + 個人設定將喺 Task B 加入」。
- `login_required`：backend 已有 `GET /` / `/proofread.html` / `/Glossary.html` 靜態服務 pattern → 加 `GET /user.html` 同樣 serve（login-required）。
- Task B 先正式砌內容（admin/user 管理 + 設定，含搬入嘅語言配置）。

## 5. 改動檔案
| 檔案 | 改動 |
|---|---|
| `frontend/index.html` | rail：刪 Pipeline + 語言 + restart 齒輪 button；加 User `<a href="user.html">`。topbar：加 `⚙ 設定`（開 language 面板）+ 搬 restart/health 入 topbar utility。主頁/檔案 button 不變。 |
| `frontend/proofread.html` | rail 換成 5-item（全 `<a href>`，校對 active）|
| `frontend/Glossary.html` | rail 換成 5-item（術語表 active）|
| `frontend/admin.html` | rail 換成 5-item（User active；admin 內容不變）|
| `frontend/user.html` | **Create** — placeholder（topbar + 5-item rail + 建設中字樣）|
| `backend/app.py` | 加 `GET /user.html`（login_required，serve frontend/user.html，跟現有靜態 route pattern）|
| `frontend/tests/test_unified_sidebar.spec.js` | **Create** — Playwright |

## 6. 測試（Playwright）
對每頁（index / proofread / Glossary / user / admin）：
- rail 剛好 **5** 個 `.rail-btn` nav item，文字 = 主頁/檔案/校對/術語表/User（順序）。
- 當前頁 item 有 `.on` active class。
- 連結 href 正確（校對→proofread.html、術語表→Glossary.html、User→user.html）。
- rail **冇** Pipeline / 語言 / restart 齒輪。
- `⚙ 設定` topbar 按鈕存在且撳開 language-config 面板（語言功能仍可達）。
- `GET /user.html` 200（login 後）。

## 7. 範圍 / 兼容
- 純前端 + 一條後端靜態 route。無 backend 邏輯改動、無 API 改動。
- `login.html` 無 rail（不變）。`mockup-*.html` / `proofread.old.html` 不郁。
- 既有頂部 pipeline strip / 語言面板 / health 邏輯保留，只係 trigger 位置變。
- **Task B（User 頁正式內容）獨立 cycle**：admin/user 管理 frontend（後端已有 `/api/admin/*` + auth）+ 個人設定 + 搬入語言配置。

## 8. 驗收標準
1. 5 頁（index/proofread/Glossary/user/admin）rail 一致 = 5 item，文字/順序/active/連結正確。
2. rail 無 Pipeline / 語言 / restart。
3. 語言配置仍可由 topbar `⚙ 設定` 打開。
4. `user.html` placeholder 可達（rail User → 200）。
5. 既有 dashboard / proofread / glossary 功能零 regression。

## 9. 範圍外（明確）
- User 頁實際內容（admin/user 管理 + 設定）→ Task B。
- 語言配置正式搬入 User 設定區 → Task B（Task A 只搬 trigger 去 topbar 齒輪，唔失功能）。
- admin.html 吸納入 User 頁 → Task B。
- 任何後端 / API / auth 改動。
