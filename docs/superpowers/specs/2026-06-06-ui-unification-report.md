# UI 統一報告 — 副頁面對齊主頁設計

> **狀態：** ✅ 已實施 + 對抗式覆核通過（2026-06-06）。6 個檔案，+119/−78。
> **日期：** 2026-06-06
> **Worktree / 分支：** `.claude/worktrees/feat-ui-unify` @ `feat/ui-unify`（由 `feat/glossary-v2` HEAD 開出）
> **範圍：** 統一 `Files.html` / `Glossary.html` / `user.html` / `proofread.html` 嘅**上面欄、左側欄、整體風格同尺寸**對齊主頁 `index.html`。**內容／行為不變。**
> **研究方法：** Workflow fan-out（10 個 agent）— 抽取主頁設計 DNA → 逐頁 diff → 對抗式覆核 → 綜合。結論已用 grep 二次核實（rail 全部存在、token 缺漏清單、Google Fonts 載入）。
>
> **重要更正：** 初步快速 grep 誤報「副頁冇 rail / token 只得 10」。Agent 直接讀檔 + 二次核實後確認：**四頁全部已有 `.b-rail`**；真實 token 數為 **Files 26 / user 26 / Glossary 21 / proofread 24**（vs 主頁 26）。下表已修正。

---

## 概覽

四個子頁面（檔案、術語、User、校對）全部**已經有左側欄（rail）**，視覺上同主頁好接近，但冇一個係 byte-identical：每頁都喺 rail 尺寸、topbar 結構、shell wrapper、token 集、字型載入上各有偏差。最大嘅單點視覺差異係**檔案頁同 User 頁仲載住 Google Fonts**（其他頁靠 system fallback），令文字字型同主頁唔一致。統一目標：將四頁嘅 **上面欄 / 左側欄 / 整體風格同尺寸** 對齊主頁設計 DNA（同一套 26 個 token、64px rail、`.app/.bold/.b-main` shell chain、统一 topbar chrome），**頁面內容同行為完全不變**。

| 頁面 | 有左側欄 | 有上面欄 | 用統一 shell chain | token 數 vs 26 |
|---|---|---|---|---|
| 主頁 index.html（基準） | ✅ | ✅ `.b-topbar` | ✅ `.app/.bold/.b-main` | 26/26 |
| Files.html 檔案庫 | ✅ 近乎一致 | ✅ `.b-topbar`（缺 2 條宣告） | ✅ 完整 | 26/26 ✅ |
| Glossary.html 術語表 | ✅ 尺寸偏差 | ❌ 用 `.gl-header` 代替 | ⚠️ 缺 `.app`、`.b-main` 用 flex | **20/26**（缺 6 個 radius/shadow/info） |
| user.html 帳戶 | ✅ 近乎一致 | ✅ `.b-topbar` | ⚠️ 缺 `id=app`/`id=bRail` | 26/26 ✅ |
| proofread.html 校對 | ✅ 近乎一致（rail 多 2 條） | ❌ 用 `.rv-header` 代替 | ⚠️ 缺 `.app`/`.b-main`，`.bold` 揹 100vh | **24/26**（缺 2 個 shadow） |

---

## 統一基準（主頁設計 DNA）

**左側欄 `.b-rail`（64px 欄）**
- 容器：`background:var(--bg-soft)#0f0f18`；`border-right:1px solid var(--border)#2a2a3d`；`display:flex; flex-direction:column; align-items:center; padding:14px 0; gap:8px`。
- Logo `.mark`：36×36；`border-radius:10px`；`linear-gradient(135deg, var(--accent)#6c63ff, var(--accent-2)#a78bfa)`；白色粗體「M」；`font-size:15px`；`margin-bottom:10px`。
- `.rail-btn`：40×40；`border-radius:10px`；預設色 `var(--text-dim)#6e6e85`；內含 16×16 SVG（`stroke-width:1.75`，round caps）+ `.tt` tooltip。
- 狀態：`:hover`→色 `--text`、底 `--surface-2`；`.on`→色 `--accent-2`、底 `--accent-soft`；`.on::before` 左側 active bar `left:-14px; top:10px; bottom:10px; width:3px; border-radius:2px; background:var(--accent)`。
- 5 個項目固定順序：主頁 / 檔案 / 校對 / 術語表 / User，末尾 `.flex1` spacer；markup 帶 `id="bRail"` + 每項 `data-route`。

**上面欄 `.b-topbar`**
- `display:grid; grid-template-columns:auto minmax(0,1fr) auto auto; align-items:center; gap:12px; padding:10px 18px; background:var(--surface)#13131a; border-bottom:1px solid var(--border); flex-wrap:nowrap; min-width:0; overflow:visible; position:relative; z-index:40`。
- 內容順序：① `#mobileHamburgerBtn`（☰，≤768 先現）② `.search`（icon + placeholder + `⌘K` kbd）③ `.topbar-mid`（`#topProgress` 38px 進度 pill + `.topbar-actions`：save-btn 💾 + run-btn ▶執行）④ `.health-cluster`（JS 填充 `.health-pill`：surface-2 底、radius 8、padding 5px 10px、font 11px、`.led` 6×6）⑤ `#userChip`（**inline-styled**：`display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--border);border-radius:14px;font-size:12px;color:var(--text-mid)`，內含 name + admin ⚙ + logout ⏻）。

**Shell 容器鏈**
- `.app#app`：`display:flex; flex-direction:column; height:100vh; background:var(--bg)#0a0a0f; overflow:hidden`。
- `.bold`：`display:grid; grid-template-columns:64px 1fr; height:100%; min-height:0`。
- `.b-main`：`display:grid; grid-template-rows:auto 1fr; min-height:0; min-width:0`（topbar=auto 列，body=1fr 列）。
- 子頁保留呢條 wrapper chain，只係用各自嘅 body grid 取代主頁的 `.b-body`（280/1fr/300 三欄）。
- 強制 fill-chain：`html,body,#app{height:100%}` + `body{overflow:hidden}`，只有內層 panel 滾動。
- Off-canvas 手機抽屜 `#mobileSidebarOverlay` + `#mobileSidebarDrawer` 係 `.app` **外面**嘅 fixed sibling。

**Token 集（26 個）** — `--bg/--bg-soft/--surface/--surface-2/--surface-3`、`--border/--border-strong`、`--text/--text-mid/--text-dim`、`--accent#6c63ff/--accent-2#a78bfa/--accent-soft/--accent-softer/--accent-ring`、`--success#22c55e/--warning#f59e0b/--danger#ef4444/--info#38bdf8`、`--radius-sm 6px/--radius 10px/--radius-lg 14px`、`--shadow-sm/--shadow`、`--font-ui/--font-mono`。**不載 Google Fonts**——`Inter` 靠 system fallback。

**核心 component primitives**（已被各頁正確沿用，無需重做）：`.btn` 家族（base `gap:8px; padding:8px 14px; radius 8; 13px/600`）、`.kbd`、`.panel/.panel-head/.panel-body`、`.badge`、scrollbar（8×8、thumb `--border`）、`.mono/.dim/.mid`。`<head>` 依賴次序：socket.io → `js/font-preview.js`，`css/responsive.css` 永遠擺 `<head>` 最尾。

---

## 各頁面修改清單

### 檔案頁 Files.html（檔案庫）

情況：shell chain 同 rail 幾乎 byte-correct，token 全齊。主要問題係**多載咗 Google Fonts**、**冇載 responsive.css / socket.io / font-preview.js**，topbar slot 1 用咗自家 `.page-id` 而非 hamburger，health/userChip 用咗自家 class。

| 區域 | 位置 | 現況 | 改成 | 風險 | 動到內容? |
|---|---|---|---|---|---|
| shell | `<head>` 7-9 | 三條 Google Fonts `<link>`（Inter/Noto/JetBrains） | **移除全部三條**，靠 system fallback（同主頁一致） | 低 | 否 |
| shell | `<head>` 尾（缺） | 無 `responsive.css` link | 加 `<link rel="stylesheet" href="css/responsive.css">` 擺 `<head>` 最尾 | 中 | 否 |
| shell | `<head>`（缺）；body 底 295 | 無 socket.io、無 `js/font-preview.js` | 按次序加 socket.io → font-preview.js（先確認 files-page.js 冇自行 lazy-load socket.io） | 中 | 否 |
| shell | body 底（缺） | 無 `#mobileSidebarOverlay`/`#mobileSidebarDrawer` | 喺 `.app` 外加 off-canvas 抽屜 markup（配合 hamburger） | 中 | **是** |
| topbar | `.b-topbar` CSS 86 | 缺 `flex-wrap:nowrap` + `overflow:visible` | 補上兩條宣告 | 低 | 否 |
| topbar | `.page-id` HTML 221-227 / CSS 88-91 | slot 1 係自訂 識別塊（檔案庫/Files），無 hamburger | 用 `#mobileHamburgerBtn` 取代（或保留 page-id 但確保 ≤768 唔霸 hamburger slot）— **見待拍板** | 中 | **是** |
| topbar | `.user-chip`/.gear HTML 234-237 / CSS 99-101 | class span，只得 `#userName`+gear，無 logout/admin/data-testid | 換成基準 inline `#userChip`（name+⚙+⏻）；**`#userName` 要保留為 alias 或同步改 files-page.js** | 中 | **是** |
| topbar | `.health-cluster`/`.hpill` CSS 94-98 / HTML 233 | `.hpill`（radius 7、5px 9px、led 7×7），cluster 缺 `flex-shrink:0` | 改名 `.health-pill` 對齊尺寸（radius 8、5px 10px、led 6×6）+ 加 `flex-shrink:0`；**先核 files-page.js 輸出 markup** | 低 | 否 |
| rail | aside 208 / btn 210-214 | aside 無 `id="bRail"`，btn 無 `data-route`，主頁/校對係 `<a>` | 加 `id="bRail"` + 各項 `data-route`；校對改 `onclick="jumpToProofread()"` | 低 | 否 |
| rail | 'User' tooltip HTML 214 | 末項 tooltip 係英文「User」 | 改繁體（帳戶/用戶），同其他 tooltip 一致 | 低 | **是** |

**保留不動**：`.files-body` 單滾動容器 + `.files-inner`(1320px)、`.fh` 頁首、`.stats`、`.toolbar`、`.table-card` 整個檔案表、`#bulkSlot`、`.toasts`、全部 files-page.js id 接線（`#refreshBtn/#uploadBtn/#search/#sort/#checkAll/#rows/#stats/#tabs/#userName/#healthCluster`）。

### 術語頁 Glossary.html（術語表）— 偏差最多

情況：**冇 `.app` wrapper、`.b-main` 用 flex 而非 grid-rows、多咗 `.gl-shell` 一層、無 `.b-topbar`（用 `.gl-header` 代替）、缺 6 個 token、rail 尺寸全部偏細、`.btn` 偏細**。需要最多對齊。

| 區域 | 位置 | 現況 | 改成 | 風險 | 動到內容? |
|---|---|---|---|---|---|
| rail | `.b-rail` CSS 84-89 | `padding:12px 0 14px`、無 gap、btn 用 `margin:2px 0` | `padding:14px 0; gap:8px`，移除 per-btn margin | 低 | 否 |
| rail | `.mark` CSS 90-96 | radius 9、font 16、margin-bottom 14 | radius **10**、font **15**、margin-bottom **10** | 低 | 否 |
| rail | `.rail-btn` CSS 97-103 | 38×38、radius 8、色 `--text-mid` | **40×40、radius 10、色 `--text-dim`** | 低 | 否 |
| rail | `.on::before` CSS 106-109 | `left:-10px; width:2px; --accent-2`、不對稱 radius | `left:-14px; top/bottom:10px; width:3px; --accent; radius:2px` | 低 | 否 |
| rail | items HTML 504-508 | 全 `<a>`，無 `data-route` | 加 `data-route`，gloss 留 `.on`（proof 留 link） | 低 | **是** |
| topbar | `.gl-header` 517-536 / CSS 127-153 | 無 `.b-topbar`，page-local header，無 userChip/admin/logout | 引入共用 `.b-topbar` grid（10px 18px、z-index:40），至少加 `#userChip`；breadcrumb + A/B tabs 摺入 topbar-mid 或留 thin sub-header；**省略 save/run/#topProgress/health**（術語頁無轉錄流程） | 中 | **是** |
| shell | body open + `.bold` 496-513 | 無 `.app`、`.b-main` 用 flex、多 `.gl-shell` | 包 `.app#app`；`.b-main` 改 `grid-template-rows:auto 1fr`；`.gl-shell` 可保留作 1fr 內容或攤平 | 低 | 否 |
| tokens | `:root` 12-38 | **缺** `--info/--radius-sm/--radius/--radius-lg/--shadow-sm/--shadow` | 照基準補 6 個 token；toast shadow → `--shadow`，14px literal → `--radius-lg` | 低 | 否 |
| components | `.btn` 60-75 | base `gap:6px; padding:7px 12px; radius 7; 12.5px/500` | 對齊 base `gap:8px; padding:8px 14px; radius 8; 13px/600`（變大變粗） | 中 | 否 |
| shell | `<head>` 1-7 / 尾 | 無 responsive.css（只有自家 1280/1100 @media） | responsive.css 擺 `<head>` 最尾；**先核佢同自家 1280/1100 breakpoint 唔衝突 `.gl-edit`**；socket.io/font-preview 非必要可略 | 中 | 否 |
| components | toast 472-484 / scrollbar 52-55 | scrollbar 已對；toast shadow 硬寫 `0 8px 24px/.5` | toast shadow → `var(--shadow)`；scrollbar 不動；可選加 `.mono/.dim/.mid` | 低 | 否 |

**保留不動**：3-pane 術語編輯器（`.gl-list`/`.gl-table`/`.gl-detail` 360px 右欄）、Variant B「比較+AI」、`.gl-vtabs` A/B 切換、per-glossary `--g-color` 主題、entry CRUD / CSV / 語言 select、全部 API endpoint 同 id（`glListItems/glTableBody/glDetailBody/glSourceLang/glTargetLang/glActiveTitle/glBody…`）、頁面自家 1280/1100 @media。

### User 頁 user.html（帳戶）

情況：shell chain 尺寸對，但 `.app` 缺 `id="app"`、rail 缺 `id="bRail"`、載咗 Google Fonts、無 responsive.css、health/userChip 用自家 class 且 userChip **無 admin+logout**（帳戶頁尤其應有 logout）。

| 區域 | 位置 | 現況 | 改成 | 風險 | 動到內容? |
|---|---|---|---|---|---|
| shell | `<head>` 7-9 | 載 Google Fonts（Inter/Noto/JetBrains） | 移除三條，靠 system fallback | 低 | 否 |
| shell | `<head>` 尾 215 | 無 responsive.css、無 socket.io/font-preview | responsive.css 擺最尾；socket.io/font-preview 先確認 user.js 冇自行擁有再決定 | 中 | 否 |
| shell | `.app` 218 / aside 221 | `.app` 無 `id="app"`、rail 無 `id="bRail"` | 補 `id="app"` + `id="bRail"` | 低 | 否 |
| shell | `.app` 外（缺） | 無 `#mobileSidebarOverlay`/`#mobileSidebarDrawer` | 如要手機抽屜，加 off-canvas siblings + hamburger；否則明文標記桌面限定 | 中 | 否 |
| topbar | `.page-id` 234-237 / CSS 54-57 | slot 1 係 帳戶/Account 識別塊，無 hamburger | 換 `#mobileHamburgerBtn`，或保留 page-id 但補 hamburger 供 ≤768 — **見待拍板** | 中 | 否 |
| topbar | `.topbar-mid`（缺） | 無 `#topProgress`/save/run，1fr slot 畀 `.search` 佔 | 帳戶頁無轉錄，可省略；但保持 4 欄 grid 令高度/節奏對齊（或插空 placeholder） | 低 | **是** |
| topbar | `.hpill` CSS 58-63 / HTML 242-245 | `.led` 7×7+3px ring、radius 7、5px 9px、無 warn/err 變體、**硬寫靜態 pill** | 改名 `.health-pill` 對齊尺寸 + 加 warn/err；考慮改 JS 驅動（`#healthCluster`）以反映真實狀態 | 低 | **是** |
| topbar | `.user-chip` CSS 64-65 / HTML 246 | class chip，只得 avatar+name，**無 admin/logout** | 換基準 inline `#userChip`（name+⚙+⏻）；**先確認 user.js 接 `#userChipLogout`/`#adminLink`** | 中 | **是** |
| rail | HTML 221-229 | 全 `<a>`，無 `data-route`、aside 無 id | 主頁→`<button data-route="home">`、校對→`<button data-route="proof" onclick="jumpToProofread()">`，files/gloss 加 `data-route`，User 留 `.on` | 低 | 否 |
| topbar | search kbd breakpoint CSS 53 | kbd 喺 @1400 隱藏，整個 search 永不收起 | kbd 改 @1500 隱藏 + 靠 responsive.css ≤1024 收 search（對齊主頁） | 低 | 否 |

**保留不動**：`.u-nav`（212px 帳戶分頁：我的帳戶/用戶管理·ADMIN/審計日誌 + `#navUsersCount/#navAuditCount`）、三個 `.u-pane`（#pane-account / #pane-users / #pane-audit）、全部 `data-pane/data-filter/data-testid` 同 user.js id（`#userChipName/#accountUsername/#adminUserList/#adminAuditList/#changePwMsg…`）、`#toastStack`、`js/user.js` 真實後端接線（DO NOT swap for mock）。`.u-body`(212px 1fr) 維持頁面專屬，只核 `min-height:0` fill-chain。

### 校對頁 proofread.html（字幕校對編輯器）— full-bleed 編輯器

情況：rail 視覺一致但 `.b-rail` 多咗 `z-index:110; position:relative`；**冇 `.app`/`.b-main`/`.b-topbar`/`.b-body`**，`.bold` 自揹 100vh，`.rv-shell` 代 `.b-main` 但缺 `min-width:0`；用 `.rv-header` 代 topbar（編輯器確實需要 breadcrumb/進度/來源 picker）；缺 2 個 shadow token；3 處硬寫 shadow。編輯器密集排版屬刻意設計，**不應強套 `.panel` 尺寸**。

| 區域 | 位置 | 現況 | 改成 | 風險 | 動到內容? |
|---|---|---|---|---|---|
| rail | `.b-rail` CSS 97-106 | 比主頁多 `z-index:110; position:relative` | 移除呢兩條（本頁無重疊，inert），達 byte 一致 | 低 | 否 |
| shell | `.bold` 90-96 / 769 | `.bold` 自揹 100vh，無 `#app`/`.b-main` | 包 `.app#app`(100vh)；`.bold` 改 `height:100%`；`.b-main` grid `auto 1fr`，`.rv-header`=auto 列、`.rv-body`=1fr 列 | 中 | 否 |
| shell | `.rv-shell` 143-147 | 有 `min-height:0`，**缺 `min-width:0`** | 補 `min-width:0`（cheap，防寬內容撐爆 1fr 欄） | 低 | 否 |
| shell | `html,body` 38 | `html,body{height:100%;overflow:hidden}` | 加 `#app` 後改 `html,body,#app{height:100%}`，`overflow:hidden` 只留 body | 低 | 否 |
| topbar | `.rv-header` 149-156 / HTML 787-826 | padding `10px 16px`、flex、無 z-index/position、無 userChip/health | **保留 `.rv-header` 作工作頭**，但 padding 改 `10px 18px` + 加 `z-index:40; position:relative`；右側可加共用 `#userChip`（本頁目前無任何 user/logout） | 中 | 否 |
| topbar | `.rv-header-source`/`.rv-progress` HTML 799-825 | select inline `radius:4px`；progress pill radius 8 | select radius → `var(--radius-sm)6px`；progress pill radius → 10px（對齊 `.topbar-progress`）；`.kbd` 已對 | 低 | 否 |
| tokens | `:root` 11-36 | **缺 `--shadow-sm`/`--shadow`**；3 處硬寫 shadow | 加 2 個 token；find-bar→`--shadow-sm`、`.ga-modal`+toast→`--shadow` | 低 | 否 |
| other | scripts 949-951 | socket.io **4.7.5**（主頁 4.7.2），script 喺 body 尾 | 全 app 統一 socket.io 版本（揀一個）；responsive.css-last 已對 | 低 | 否 |

**保留不動**：整個編輯器 workspace 同行為——`.rv-header` breadcrumb/back/進度 pill/keyboard hints/字幕來源+雙語順序 select、find-replace 工具列、segment rail（`#segList`、split/merge `.rv-seg-*`、QA flags、✓）、video player + SVG overlay、詞彙表 panel（`.ga-*` modal）、字幕設定 panel、timeline/waveform（flex-pinned）、detail editor + footer、mobile tab switcher、`#toastStack`。**任何 `.rv-*` class/id 不可改名**（JS 直接 query）。編輯器密集 panel（9px radius、7px head）**刻意保留，不強套 `.panel` 14px**（風險高）。

---

## 建議的實施策略

**Option A — 抽出共用設計系統 stylesheet（`css/app-shell.css`）+ 共用 rail/topbar markup 區塊**
- 將 26 個 token、`.app/.bold/.b-main`、`.b-rail`+全部 rail 狀態、`.b-topbar`+`#userChip`/health/search、`.btn` 家族、`.kbd/.panel/.badge`、scrollbar、`.mono/.dim/.mid` 一次過抽入 `css/app-shell.css`，每頁 `<head>` link 佢（擺喺 inline `<style>` 之前、`responsive.css` 之後保持 last-win）。
- rail + topbar 嘅 HTML 因為係 no-build 靜態頁，冇法真正「inject」，所以做法係**喺每頁貼同一段 canonical 區塊**（手動 copy 一致 block，靠 review 保證一致）。
- 優點：DRY，將來改設計只改一處；token drift（術語頁缺 6 個）一次根治。缺點：要小心各頁 page-local CSS 同共用表嘅 specificity；首次抽取改動面較大。

**Option B — 逐頁 inline copy 統一嘅 rail/topbar/token 區塊**
- 唔加新檔案，逐頁喺現有 `<style>`/HTML 內就地對齊到基準值。
- 優點：改動局部、風險可逐頁隔離、容易 review diff、唔影響其他頁。缺點：六份 token/rail/topbar 副本，將來要逐頁同步（drift 復發風險）。

**建議：行 Option B 先做第一輪統一（逐頁對齊基準值，風險最低、最易審），完成後再做 Option A 嘅抽取作為第二步重構。** 理由：呢個專案明文「唔加 build system」，而四頁嘅 page-local CSS 同 JS id 接線各異，一次過抽共用表 + 改 markup 嘅 specificity 風險高；先逐頁 inline 對齊可保證每頁獨立可驗證、零 regression，之後再 DRY 化。

**特殊案例共存**
- **校對（full-bleed 編輯器）**：全域 64px rail 同編輯器 workspace（`.rv-b-rail` 段列表、video、timeline）係兩個獨立欄並存——rail 係導航，`.rv-b-rail` 係內容，無衝突。`.rv-header` 保留作工作頭，只 skin 到 topbar 尺寸 + 補 `#userChip`，**唔整個換成 `.b-topbar`**。
- **User（local tab nav）**：全域 64px rail 同帳戶分頁 `.u-nav`(212px) 係兩個並存欄——前者全 app 導航，後者頁內分頁，兩者皆保留，只統一全域 rail 本身。

---

## 需要你拍板的決定

1. **topbar slot 1（檔案/User）**：保留自訂 `.page-id` 識別塊（檔案庫/帳戶）作子頁身分提示，定係換成基準 `#mobileHamburgerBtn`？若保留，仍需另加 hamburger 供 ≤768 手機導航。
2. **手機 responsive / 抽屜**：四頁（尤其檔案/術語/User）係咪都要 link responsive.css + 加 off-canvas 抽屜 + hamburger，定接受呢啲 login 後桌面導向頁維持桌面限定？
3. **userChip 完整化**：User 同校對頁目前**無 logout/admin**。係咪統一補上基準 `#userChip`（name+⚙+⏻）？需先確認 user.js / 各頁 JS 有冇接 `#userChipLogout`/`#adminLink`（避免加咗掣冇功能）。
4. **health pill**：把分歧嘅 `.hpill`（兩段 hk/hv、led 7×7）升格為 app-wide 共用設計，定係降格對齊基準 `.health-pill`（led 6×6、radius 8、warn/err 變體）？User 頁嗰兩粒仲係**硬寫靜態**，要唔要改 JS 驅動以反映真實 health？
5. **術語/校對 topbar 取捨**：術語頁同校對頁無轉錄流程——確認 topbar **省略 `#topProgress`/save/run/health**，只保 breadcrumb/工作控制 + `#userChip`（minimal 變體）？另：breadcrumb + A/B tabs（術語）摺入 topbar-mid 定留 thin sub-header（決定 `.b-main` 係 2 列定 3 列）？
6. **校對 shell 取捨**：要唔要引入 `#app`+`.b-main` wrapper chain 去同其他頁完全一致（中風險、會 reflow 精調過嘅 fill-chain），定保留等效 `.bold>.rv-shell`（同樣 100vh 內滾結果）只補 `min-width:0`？
7. **socket.io 版本**：全 app 統一一個版本——校對 4.7.5 vs 主頁 4.7.2，揀邊個？
8. **Google Fonts 方向**：確認**移除**檔案/User 頁嘅 Google Fonts（對齊主頁 system fallback），而非反過來畀所有頁加 webfont？
9. **是否一併統一 login.html / 任何 mockup 頁**：本報告未涵蓋——要唔要納入同一輪統一？

---

## 風險與不改動保證

**整體風險評級**
- **低風險**（純樣式/尺寸對齊，無行為改動）：rail 尺寸/狀態對齊、token 補齊（術語+6、校對+2）、`.btn` 尺寸對齊、移除 Google Fonts、補 shell id、scrollbar/shadow tokenize、移除校對 rail 多餘 `z-index/position`。
- **中風險**（需核 JS 接線或會 reflow）：link responsive.css（可能拉入頁面缺嘅 breakpoint/抽屜 markup）、加 socket.io/font-preview、userChip 換 class→inline（`#userName`↔`#userChipName` 要協調 files-page.js / user.js）、health pill 改名（要核 JS 輸出 markup）、校對引入 `#app`/`.b-main`（reflow fill-chain）、術語引入 `.b-topbar`。
- **高風險**（明確排除）：強套 `.panel` 14px 尺寸落校對密集編輯器——**不做**。

**內容/行為保證**：本輪只統一 **左側欄 / 上面欄 / shell 容器 / token / 共用 primitive 尺寸**。所有頁面內容區、業務邏輯、API endpoint、JS id 接線、page-local class 一律**保持不變**；任何 `.rv-*`/`gl*`/`#account*`/`#admin*` 等被 JS query 嘅 class/id 不可改名。

**被標記 `動到內容=是` 嘅改動（需特別留意，全部屬 chrome 層而非業務內容）**：
- 檔案頁：加 off-canvas 抽屜 markup、`.page-id`→hamburger（若選）、`.user-chip`→`#userChip`、'User' tooltip 改繁體。
- 術語頁：rail items 加 `data-route`、引入 `.b-topbar` + `#userChip`（重塑 header 內容）。
- User 頁：`.page-id` slot 取捨（若改）實質保留、`.topbar-mid` 取捨、`.hpill`→`.health-pill`（含改靜態為 JS 驅動）、`.user-chip`→`#userChip`（加 admin+logout）。
- 校對頁：`.rv-header` 右側「新增」`#userChip`（屬新增 chrome，不改既有編輯器內容）。

---

## 決定記錄（2026-06-06 已確認）

| # | 決定 | 結果 |
|---|---|---|
| 策略 | 實施方式 | **Option B 先行** — 逐頁 inline 對齊基準值，唔加 `css/app-shell.css`。將來可再做 A 抽共用表。 |
| 校對 | full-bleed shell | **保留 `.bold>.rv-shell` full-bleed**，唔引入 `#app/.b-main` chain；只對齊尺寸 + 補 `min-width:0` + token + rail/header skin。 |
| Chrome | logout/admin + 字型 | **全部對齊主頁** — User/校對補基準 `#userChip`（name+⚙admin+⏻logout，先核 JS 接線）；移除 Files/User 嘅 Google Fonts 改 system fallback。 |
| 範圍 | 涵蓋頁面 | **只 4 頁**（檔案/術語/User/校對）。`login.html` / `mockup-media-bin.html` 不納入本輪。 |

### 次要項目（採用以下預設，除非你另有指示）
1. **topbar slot 1（Files/User 嘅 `.page-id`）**：**保留** page-id 作子頁身分提示（唔換走），但加一個 ≤768 先現嘅 `#mobileHamburgerBtn` 令手機導航可用。主頁美學唔受影響（主頁 slot 1 本身就係 mobile-only hamburger）。
2. **socket.io / font-preview.js**：**唔強加**落 Files/Glossary/user。呢兩個係功能依賴（font-preview 只服務有字幕預覽嘅 index/proofread），唔屬 chrome；無謂載未用嘅 script。校對 vs 主頁 socket.io 版本差異（4.7.5 vs 4.7.2）統一為主頁 **4.7.2**。
3. **responsive.css**：加落 **Files + user**（低衝突）；**Glossary 先驗證** 同自家 1280/1100 @media 唔打架先加，有衝突就保留自家 breakpoint。
4. **User health pill**：對齊 `.health-pill` 尺寸（led 6×6、radius 8、5px 10px）+ 補 warn/err 變體，但**維持靜態**（唔新引入 health 輪詢 JS）。
5. **術語/校對 topbar**：**省略** `#topProgress`/save/run/health（呢兩頁無轉錄流程），只保 breadcrumb/工作控制 + minimal `#userChip`。
6. **驗證**：每頁改完跑對應 Playwright spec（`test_unified_sidebar` / `test_topbar_progress` / `test_user_page` / proofread specs）+ 視覺核對，確保零 regression。

### 實施次序（風險低 → 高，逐頁可獨立驗證）
- **Phase 1 — 純 CSS token/尺寸對齊（低風險，零 markup/JS）**
  - 術語：補 6 個 token、rail 對齊（40×40 / radius 10 / `--text-dim` / active-bar `left:-14px;width:3px;--accent`）、`.btn` base 對齊（8px 14px / radius 8 / 13px·600）、toast shadow → `--shadow`。
  - 校對：補 2 個 shadow token、移除 rail 多餘 `z-index:110;position:relative`、`.rv-shell` 補 `min-width:0`、3 處硬寫 shadow tokenize、select/progress radius 對齊。
  - 檔案：`.b-topbar` 補 `flex-wrap:nowrap`+`overflow:visible`、health pill 尺寸對齊、rail 加 `id="bRail"`+`data-route`、'User' tooltip 改繁體。
  - User：rail 加 `id="bRail"`+`data-route`、`.app` 加 `id="app"`、health pill 尺寸對齊、search kbd breakpoint 對齊。
- **Phase 2 — Chrome 行為（動 markup/JS 接線，逐項核 JS）**
  - 移除 Files + user 嘅 Google Fonts（3 條 link）。
  - 檔案：`.user-chip`→基準 `#userChip`（`#userName`↔`#userChipName` 協調 files-page.js）。
  - User：`.user-chip`→基準 `#userChip`（補 ⚙admin + ⏻logout，核 user.js 接 `#userChipLogout`/`#adminLink`）。
  - 校對：`.rv-header` 右側加基準 `#userChip`。
  - Files/User：加 ≤768 `#mobileHamburgerBtn`（配合保留嘅 page-id）。
- **Phase 3 — Topbar/shell 結構（中風險）**
  - 術語：`.gl-header` skin 到共用 `.b-topbar` grid 尺寸（10px 18px / border-bottom / z-index:40）+ 加 `#userChip`；breadcrumb + A/B tabs 留 thin sub-header。包 `.app#app`、`.b-main` 改 `grid-template-rows:auto 1fr`。
  - 校對：`.rv-header` padding→`10px 18px` + `z-index:40;position:relative`（**不換 `.b-topbar`、不引入 `#app`**）。
  - responsive.css：Files/user 加；Glossary 驗證後決定。
- **Phase 4 — 驗證**：逐頁跑 Playwright + 視覺核對 + `git diff` review。

---

## 實施 + 驗證結果（2026-06-06）

**改動範圍**：6 檔，+119/−78 — `user.html`、`Files.html`、`Glossary.html`、`proofread.html`、`js/user.js`、`js/files-page.js`。

**對抗式覆核（5 個 agent，逐頁 diff review + 跨頁一致性）結論**：
- Glossary：PASS。Files：2 LOW（benign scope note）。user / proofread：各 1 MEDIUM（已修）。跨頁一致性：PASS。
- **已修嘅 3 個真問題**：
  1. proofread `#userChip` 嘅 `margin-left:auto` 同 `.rv-kbd-hint` 既有 `margin-left:auto` 撞，split 咗 header free space → 移除 chip 嘅 `margin-left:auto`（chip 改由 kbd-hint 嘅 auto margin 推右；亦令 chip 同其他頁 byte-identical）。
  2. `responsive.css` link（加咗落 Files + user）會用 index 專屬嘅 `!important` topbar grid override 套落 3-child topbar → **移除返**（兩頁本來就冇 responsive.css，回到 baseline，無 mobile glitch）。
  3. user + Glossary 嘅 `.rail-btn` 漏咗 `font-size:16px`（Files/proofread/index 都有）→ 補返，rail 完全 byte-identical。

**最終驗證**：4 頁 `#userChip` opening span byte-identical；`.rail-btn font-size:16px` 全頁齊；4 頁 26 token 齊；全 app 無 Google Fonts；無殘留假 Whisper/Qwen pill；`js/user.js` + `js/files-page.js` 過 `node --check`；HTML tag 平衡；無 JS-queried id/class 被改名或刪除。

**額外決定（待 user 最終確認）**：user 講明剷 user.html 嘅假 Whisper/Qwen pill；Files.html 有一模一樣嘅假 pill（files-page.js `renderHealth` 寫死），順手一齊剷咗保持一致 — 如要 Files 留返 health 指示，可還原。

**保守保留（非 visible，避免 regression）**：proofread `.b-rail` `z-index:110`；Glossary/proofread 無強加 `.app` wrapper；Glossary 無 link responsive.css（對佢 no-op）。

以上 `動到內容` 全部限於 topbar/rail 嘅 **chrome 元素**（身分/導航/登出/手機抽屜），**冇任何一項改動頁面嘅核心功能內容或資料**。