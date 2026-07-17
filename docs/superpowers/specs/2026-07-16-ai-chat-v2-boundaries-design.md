# AI 助手 V2 — 字幕管理能力邊界（AI Chat Window V2 Boundaries）— 設計文檔

**日期**：2026-07-16
**前置**：V1 已完成（branch `ai-chat-window`，Ready to merge — [2026-07-14-ai-chat-window-design.md](2026-07-14-ai-chat-window-design.md)）；本文檔係 V2 嘅**能力邊界設計**，喺 V1 merge 之後先實施
**狀態**：用戶 7 項產品決策已拍板（2026-07-16）；等待 spec review → 實施計劃

---

## 1. 背景與目標

V1 交付咗 AI 助手浮動聊天窗（批量取代 + 指定段落 AI 改寫），並刻意剔走一批能力（cutlist）。本設計回答一條問題：**AI 對話最終可以管理字幕到咩程度 — 邊啲開放、邊啲永遠唔畀、每樣嘅限制係乜。**

設計原則（V1 延續）：

1. **人類保留審核責任** — AI 永遠唔可以自行批核
2. **所有寫入先預覽後執行** — 破壞性操作再加一重
3. **本地 35b 退化防線** — 每個 LLM call 有界、目標檢索永遠機械、可以零 LLM 嘅就零 LLM
4. **誠實交待** — 唔可還原嘅嘢明言唔可還原，唔提供假還原

### 用戶產品決策（2026-07-16 拍板）

| # | 問題 | 決定 |
|---|------|------|
| 1 | 開放邊啲操作 | split/merge、timing、AI Rerun、render/導出、詞彙表操作、內容問答 |
| 2 | 永遠禁區 | **批核狀態**（approve/unapprove）、**跨檔操作** |
| 3 | 確認機制 | **三級**：純讀直接做／一般寫入預覽卡／破壞性雙重確認 |
| 4 | 問答餵 transcript | **檢索為主、概括為輔**（統計類零 LLM；概括類分段 summarize） |
| 5 | 詞彙表深度 | **只加詞條/加別名**（add-only，唔改唔刪） |
| 6 | render/導出 | **導出即做，render 確認後觸發**（進度卡＋可取消） |
| 7 | 批量封頂 | **細批封頂**：Rerun ≤20 段／split-merge-timing 每 turn ≤10 段，超咗引導去 UI |
| 8 | 還原語義 | **分類**：文字可還原（V1 現狀）；結構性明言唔可還原 |

---

## 2. 能力總表（The Boundary）

| 操作 | 級別 | 執行路徑 | 限制 |
|---|---|---|---|
| 內容問答 | 🟢 純讀，直接答 | 機械檢索 → bounded LLM call（統計類零 LLM） | 相關 cue 封頂先入 prompt（§4）；統計類（「出現幾多次」）server 機械答 |
| 導出 SRT/VTT/TXT | 🟢 純讀，直接俾 link | 現有 `GET /api/files/<id>/subtitle.<fmt>?source=&order=` | 無新後端；卡片俾下載 link |
| 批量取代（replace_term） | 🟡 預覽卡確認 | V1 現狀不變 | 200 項上限 |
| AI 改寫（rewrite_cue） | 🟡 預覽卡確認 | V1 現狀不變（經 `/ai-edit` 兩段式） | 每批 10 段、單次 ~20 段 |
| split / merge | 🟡 預覽卡確認 | 現有 `POST /segments/<pos>/split`、`/merge-next` | **每 turn ≤10 段**；超咗 → 「請縮窄範圍或用校對頁」；<0.4s cue 唔畀 split（現有規則） |
| timing 調整 | 🟡 預覽卡確認 | 現有 `PATCH /segments/<pos>/timing` | **每 turn ≤10 段**；roll-on-contact 語義照現有 API；卡片顯示新舊 In/Out |
| render 燒錄 | 🟡 確認後觸發 | 現有 `POST /api/render` + poll | 卡片列格式/字幕源/未批核段數 → 確認開 job → 進度卡＋取消掣（`DELETE /api/renders/<id>`） |
| AI Rerun | 🔴 雙重確認 | 現有 `POST /rerun {positions}` + poll | **每次 ≤20 段**（同現有批量 Rerun 掣一致）；警告「覆寫現有文字＋reset 批核狀態」 |
| 詞彙表加詞條/加別名 | 🔴 雙重確認 | 現有 `POST /glossaries/<id>/entries`、`POST /files/<id>/glossary-add-alias` | **add-only**；警告「影響所有用呢個表嘅檔案」；權限跟現有 API（共用表 `can_edit`／行話表 admin — chat 唔另設權限層） |

## 3. 永遠禁區（chat 一律唔做，引導返 UI）

| 禁區 | 理由 |
|---|---|
| **批核 approve/unapprove**（單段/批量/全部） | 審核責任必須人手。唯一例外係 V1 現狀嘅「套用後批核」toggle — 嗰個係用戶親手剔嘅套用選項，唔係 AI 決定 |
| **跨檔操作** | 一次只管當前檔案；「嗰三條片都改」→ 引導逐檔做 |
| **改/刪詞彙表條目** | 共用資源嘅修改/刪除破壞面太大；加錯咗人手刪 |
| **檔案設定**（glossary_ids、subtitle_source、mt_style 等） | 檔級配置留返 UI |
| **glossary-reapply（全部重新生成）** | 核彈級操作（清人手編輯＋reset 全部批核），連 UI 都要 confirm 警告 — chat 唔提供 |
| **用戶/權限/Beta/license 管理** | 完全出咗字幕管理範圍 |

被問到禁區操作時：`none` op ＋禮貌解釋＋（有 UI 對應功能時）指路，例如「批核請用段落表嘅批核掣」。

---

## 4. 內容問答設計（檢索為主、概括為輔）

V1 鐵律「transcript 永不入 prompt」演化為「**transcript 只經機械檢索、封頂之後先入 prompt**」。退化防線不變：每 call 有界、檢索永遠機械。

### 4.1 三類問題三條路

| 類型 | 例子 | 路徑 |
|---|---|---|
| **統計類** | 「『霍宏聲』出現咗幾多次？」「有幾多段未批核？」 | **零 LLM** — intent parse 出 `query_stats` op，server 機械數（casefold Latin／exact CJK，同 replace_term 掃描共用 matcher），直接答＋列命中段號（撳得跳段） |
| **點對點內容** | 「第 12 段講緊乜？」「邊段有提到出閘？」 | intent parse 出 `query_content` op（帶關鍵詞/段號範圍）→ server 機械檢索相關 cue（**封頂 ~20-30 段**）→ 1 個 bounded LLM call 回答 |
| **全片概括** | 「成條片大概講乜？」 | 分段 summarize：transcript 切 chunk（每 chunk 有界，例如 ~40 cue），逐 chunk bounded call → 最後一個 call 綜合。**chunk 數封頂**（例如 ≤8 個 call）；超長片 → 「條片太長，請問具體啲」 |

### 4.2 防線細節

- 檢索關鍵詞由 LLM intent parse 提供，但**揀邊啲 cue 入 prompt 永遠係 server 機械決定**（LLM 唔揀 cue — V1 原則）
- 問答回覆入對話流之前過長度閘；退化輸出（prompt echo、refusal 文本）→ 422 澄清降級（V1 `parse_ops` 同款 leniency/rejection）
- 問答係純讀 — 零寫入、零 registry 郁動
- 每 turn 嘅 LLM call 數：統計類 1（淨 intent parse）；點對點 2（parse + answer）；概括類 parse + ≤8 chunk + 1 綜合

---

## 5. 三級確認制

```
🟢 純讀（問答、導出）
    → 直接執行，答案/link 落對話流

🟡 一般寫入（取代、改寫、split/merge、timing、render 觸發）
    → 預覽卡（影響範圍 + before/after 或參數）→ 剔選/確認 → 執行
    → V1 現有 expected_text/start-end 衝突重驗照舊

🔴 破壞性（AI Rerun、詞彙表寫入）
    → 預覽卡 + 紅字警告 + 二次確認（明確撳「我明白，執行」先郁）
    → Rerun 警告：「會覆寫呢 N 段現有文字並 reset 批核狀態，無法還原」
    → 詞彙表警告：「會影響所有使用『<表名>』嘅檔案」
```

## 6. 還原語義（誠實交待）

| 操作 | 還原 |
|---|---|
| 批量取代／AI 改寫（文字） | ✅ session 內可還原（V1 現狀 — 連批核狀態、經同一條衝突檢查路） |
| split / merge / timing / Rerun / 詞彙表 / render | ❌ **唔可經對話還原** — 確認卡明確寫「此操作確認後無法經對話還原」 |

唔提供假還原：split/merge 之後 grid 段號全變，snapshot 還原要成套 grid-version 機制（工程量大、易錯）— 明言唔得好過整個半桶水。timing 技術上可以記舊值，但為咗規則簡單一致，V2 一律歸「唔可還原」類；如果日後用戶反映 timing 還原有真需求，可以單獨升級（唔改 grid 結構，風險低）。

## 7. 批量封頂

| 操作 | 上限 | 超咗點做 |
|---|---|---|
| replace_term expand | 200 項（V1 現狀） | `truncated:true` → 「請縮窄範圍」 |
| rewrite_cue | 每批 10 段、單次 ~20 段（V1 現狀） | 「請縮窄範圍」 |
| split / merge / timing | **每 turn ≤10 段** | 「請縮窄範圍或用校對頁逐段做」 |
| AI Rerun | **每次 ≤20 段** | 「請縮窄範圍或用段落表嘅批量 Rerun 掣」 |
| 問答檢索 | ~20-30 cue 入 prompt；概括 ≤8 chunk call | 「請問具體啲」 |
| render | 每檔同時 1 個 job（現有互鎖） | 進度卡顯示進行中 job |

封頂數字係設計錨點，實施時容許 ± 微調（以現有 UI 對應功能嘅實測值為準），但**量級唔可以變**（10 唔可以變 100）。

## 8. 技術防線（V1 鐵律點樣演化）

| V1 鐵律 | V2 演化 |
|---|---|
| transcript 永不入 prompt | transcript **只經機械檢索、封頂之後**先入 prompt（§4） |
| 每 turn 恰好 1 個 LLM call | 每 turn LLM call 數**有界且事前可知**（parse 1 個；問答按 §4.2 上限；rewrite 照 V1 分頁） |
| LLM 唔揀 cue | 不變 — 目標檢索永遠 server 機械 |
| 所有寫入預覽先行 | 不變 ＋ 破壞性加第二重 |
| 互鎖零新增 predicate | 不變 — chat 觸發嘅 split/merge/timing/rerun/render 全行現有 API，現有 409 互鎖矩陣照生效 |
| raw model 輸出永不 render 入對話流 | 不變（問答回覆過閘先出） |

### 8.1 Intent schema 擴充（Validation-First 強制）

V1 實證 LLM intent parse 好脆弱（`langs` 5 輪 prompt 迭代都學唔識、要簡化 schema）。V2 每個新 op type 落實之前**必須**過 Validation-First intent-parse 驗證（production stack qwen3.5、機械 checker、合格線 valid-JSON ≥90% + 欄位準確 ≥90%），唔達標就簡化 schema（例如 timing 只接受「第 N 段 In/Out 移 X 秒」一種句式）。預期新 op：

`split_cue`／`merge_cue`／`adjust_timing`／`rerun_cues`／`render_video`／`export_subtitle`／`query_stats`／`query_content`／`summarize`／`glossary_add`

一次過驗全部唔現實 — 按 §9 分期，每期只驗該期嘅 op。

### 8.2 權限

Chat 唔另設權限層 — 全部行現有 API，現有 authz 照生效（詞彙表共用表 `can_edit`、行話表 admin、render/export 登入用戶）。無權 → API 403 → 卡片顯示中文錯誤。

---

## 9. 實施分期

| Phase | 內容 | 理由 |
|---|---|---|
| **A** | 導出 + 統計類問答（零 LLM）+ split/merge/timing | 低風險高價值：導出/統計零 LLM 零寫入；split/merge/timing 行現有 API + 小批量 |
| **B** | render 觸發 + AI Rerun | 觸發 job 類：要進度卡 + 取消 + 雙重確認 UI |
| **C** | LLM 問答（檢索 + 概括）+ 詞彙表 add-only | LLM 面最大（新 answer prompt 要驗）；詞彙表寫共用資源最後先開 |

每 Phase 獨立行 brainstorm 補細節（如需要）→ Validation-First → plan → 實施 → review；一個 Phase 上咗先開下一個。

## 10. 風險與已知取捨

1. **Intent parse 係最大技術風險**（V1 已實證）— 每期 Validation-First 係硬閘，預期部分 op 句式會被迫簡化
2. **概括類問答喺超長片嘅體驗**：chunk 封頂之下可能答唔晒成條片 — 接受，引導問具體啲
3. **render 進行中允許文字套用**（V1 現狀）繼續 — 混合輸出警告唔封鎖
4. **timing 唔可還原**係規則一致性換嚟嘅取捨（技術上可還原）— 留有單獨升級空間
5. **詞彙表 add-only 都仲係寫共用資源** — 雙重確認 + 現有 authz + 冪等（現有 add-alias 已存在 no-op）係三重緩解

## 11. V2 cutlist（依然剔走）

批核 ops／跨檔操作／改刪詞彙表條目／檔案設定／glossary-reapply／regex-模糊匹配／對話跨 reload 持久化／streaming／後台 chat batch job／自動執行（零確認模式）
