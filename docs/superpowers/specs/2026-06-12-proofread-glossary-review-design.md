# 校對頁 Glossary Review 重設計 — Design Spec

日期：2026-06-12
狀態：用戶已分三段批准設計；待實施計劃
前期研究：Workflow `research-proofread-glossary-flow`（4 readers + synthesis，本檔引用嘅 file:line 全部出自該研究）

---

## 1. 背景同問題

校對頁而家對 output_lang 檔嘅詞彙表互動只有「套用中…」按鈕文字 +「重新套用詞彙表」一個掣。用戶三大痛點：

1. **對應唔可見** — 唔知詞彙表啲詞點 map 落字幕。根因：`glossary_changes` 只記「有改動」嘅 case，verbatim 已正確嘅命中係 no-op 唔記錄（output_lang_glossary.py:307-309）；詞彙對照唔顯示觸發詞；覆蓋率不可見。
2. **語言表達唔清** — 同一本詞彙表對兩條語言軌係兩個唔同方向生效（refine/pass 軌 target-side canonicalize；mt 軌 source-side 命中+譯文注入 — `route_for_output` output_lang_glossary.py:184-217），UI 從未表達；`glossary_changes` 冇 lang 欄，persist 時兩軌 union 攤平（output_lang_persist.py:67-92），語言歸屬喺持久化嗰刻已丟失。
3. **冇逐個確認** — 「重新套用」係全量 re-derive 核彈：重跑成條翻譯鏈（實測 29-47s）、覆寫所有人手編輯、批核全 reset（app.py:4945-4958, output_lang_persist.py:63,81），冇 preview、冇 per-term accept/reject。

另有兩個研究發現嘅基建問題：

- 校對頁詞彙表 dropdown 係假嘅 — auto-select 舊 Profile 嘅 `translation.glossary_id`，同檔案實際嘅 `glossary_ids` 脫節（proofread.html:1593-1606；`fileInfo.glossary_ids` 全檔零引用）；「重新套用」送空 body，panel 揀乜都冇影響（proofread.html:1857）。
- 舊 C 線 scan+apply modal（proofread.html:1875-1975 + app.py:3064-3343）有「掃描→checkbox 預覽→逐項 LLM 套用」嘅好骨架，但只寫單語 `zh_text`、唔同步 `by_lang`/`aligned_bilingual`，對 output_lang 檔會 desync，所以被前端隱藏。

**方向（用戶決定）**：翻新舊 C 線骨架，搬入現時校對介面做主力互動。

## 2. 已批准嘅設計決策（六條方向題）

| # | 問題 | 決定 |
|---|---|---|
| 1 | 新 modal vs 現有「重新套用」 | **Modal 做主力**；「重新套用」保留做後備，改名「全部重新生成」+ 破壞性警告 confirm |
| 2 | AI 幾時介入 | **掃描純機械**（毫秒級，按雙軌路由+別名+guard）；**套用先逐項行 AI**；預覽顯示「⚠ AI 將判斷修改位置」 |
| 3 | 套用後批核狀態 | **保持原狀**（keep_status 語義）；已批核行喺 modal **唔 default 剔** |
| 4 | 雙軌呈現 | **一個 modal 按語言軌分區**，每軌標題寫明生效方向；軌內分「待修正／已符合」 |
| 5 | 詞彙表數據源 | **跟檔案 `glossary_ids` + panel 即場可改**（剔選+優先 badge 多選組件，同上載 popup 一致），改完寫返檔案，後續掃描/重新生成/AI Rerun 全部跟新set |
| 6 | 段落級顯示 | **「詞彙對照」一齊升級**：語言 chip + 觸發詞 + 空狀態分流 |

## 3. UI 設計

Mockup：visual companion session `.superpowers/brainstorm/25817-1781232978/content/new-glossary-review-design.html`（用戶已睇批准；舊 C 線重現喺 `old-scan-apply-modal.html`）。

### 3.1 詞彙表 panel（影片下方原位，取代假 dropdown）

- 標題「詞彙表 — 此檔案使用中（剔選即儲存）」。
- 多選清單：每行 checkbox + 名稱 + `(EN→ZH · N條)` + 優先次序數字 badge（剔選先後 = 優先，組件照搬上載 popup `_olGlossaryOrder` 嗰套互動）。清單列所有可見詞彙表；剔選狀態 = 檔案 `glossary_ids`。
- 剔/改即 `PATCH /api/files/<id>`（見 §4），toast 確認。
- 主掣「🔍 掃描詞彙表」（primary）；副掣「⟳ 全部重新生成」（ghost 樣式 + 警告色 hover），撳落出 confirm：「會由原文重新生成所有字幕，**覆寫你嘅人手修改、批核狀態全部重設**。確定？」。
- Panel 入面原有嘅詞彙表條目編輯表（加/改/刪詞條）保留不變。

### 3.2 掃描 modal

- Header：`詞彙表掃描 — <表名+...>`；副題 `N 段 · M 條語言軌 · 搵到 X 處候選、Y 處已符合`。
- **按語言軌分區**（單語檔得一區）。每軌 header：語言名（用 `_outputLangLabel` 同款 label）+ 方向一句說明：
  - refine/pass 軌：「將字幕入面嘅別名統一做標準名」
  - mt 軌：「按原文（<內容語言>）命中詞條，檢查<軌語言>字幕有冇用標準譯名」
  - 詞彙表對某軌完全唔生效（route gate 唔過）→ 軌 header 顯示「<表名> 唔適用於呢條軌（原文語言唔對應）」— 教育返 mapping。
- 軌內兩個 section：
  - **待修正**（有 checkbox；default 剔，**已批核行除外**並掛「已批核」badge）：每行 `別名 → 標準名` + 詞彙表來源 tag + `#段號 時間碼`（撳得 → setCursor 跳段 + 影片 seek，跟 ⌘F 模式）+ 字幕原句（別名黃 highlight；mt 軌加埋原文行）+ hint「⚠ AI 將判斷修改位置」。
  - **已符合**（純顯示，無 checkbox，dimmed）：標準名綠 highlight。**剷走舊「強制重新套用」假功能。**
- Footer：「套用唔會改批核狀態」說明 + 取消 + 「套用選中 (N)」（實時計數；每軌 select-all 連 indeterminate）。
- **套用過程**：唔閂 modal，逐項串行（⌘F promise chain 模式），行內即時 ✓（成功）/ ✗（失敗+原因，可重試）；完成 toast 總結「已套用 X 項，Y 項失敗」。套用完成功行轉灰，「重新掃描」掣可刷新。

### 3.3 段落 detail「詞彙對照」升級

- 每行格式：`[語言chip] "觸發詞" 改前 → 改後 · 來源表名`；舊記錄冇 lang/觸發詞 → 容忍缺欄（唔出 chip）。
- 空狀態分流：檔案冇 `glossary_ids` →「未設定詞彙表」；有設但呢段冇記錄 →「此段冇命中詞條」。
- Rail 📖 chip 邏輯不變（有 `glossary_changes` 先出）。

## 4. 後端架構

全部 output_lang only（`active_kind=='output_lang'`，其他 kind 400）。

| Endpoint | 性質 | 行為 |
|---|---|---|
| `POST /api/files/<id>/glossary-preview` | 新增，**純讀零副作用** | 機械掃描。輸入：optional body `{glossary_ids?}`（缺省用檔案嘅；**前端永遠唔送 override** — panel 改選係先 PATCH 落檔案再掃描，避免「掃描用 A 套、重新生成用 B 套」嘅狀態分歧；override 只留俾測試用）。對每條輸出語言軌行 `route_for_output` 同款路由 + 別名匹配 + 現有 guard（`_COMMON` 單字 deny、target ≤2 字 skip、(H###) suffix 剝除）。回傳 `{tracks:[{lang, mode, direction_label, applicable_glossaries, items:[{idx, start, kind: fix|ok, alias, canonical, glossary_id, glossary_name, entry_id, row_text, src_text?, approved}]}], totals}`。唔行 LLM、唔寫 registry（對比舊 scan 嘅 lazy-revert 副作用 app.py:3093-3119 — 新嘅冇）。 |
| `POST /api/files/<id>/glossary-apply-item` | 新增，逐項寫 | body `{idx, lang, alias, canonical, glossary_id, entry_id, expected_text}`。流程：鎖內驗證+snapshot → 鎖外 LLM（「只改呢個詞、其他逐字保留」prompt，`_make_ollama_llm_call()` 共用、Beta-aware）→ 重新攞鎖 + **衝突檢查**（該行該語言而家文字 != `expected_text` → 409 放棄）→ 原子寫入：`by_lang[lang].text` + `{lang}_text` mirror + `aligned_bilingual[idx].by_lang[lang]` 三位同步 → append `glossary_changes` 記錄（連 `lang` + `entry_id`）→ **status 唔郁**（keep_status 語義）。回 `{text, change}`。422 = AI 輸出唔合格（解析唔到/唔包含 canonical），唔寫入。409 = 衝突或 AI Rerun 進行中。 |
| `PATCH /api/files/<id>` | 擴展 | 接受 `glossary_ids`（驗證逐 id 存在，同上載一致 app.py:4669-4687）+ `glossary_llm`。寫入檔案 entry。 |
| `POST /api/files/<id>/glossary-reapply` | 唔變 + 補閘 | 前端改名「全部重新生成」+ confirm；後端補返漏咗嘅 render-in-progress 409（而家只擋 rerun，app.py:4967）。 |

**架構原則**：

- 掃描邏輯做成 **pure function**（新函數加喺 `output_lang_glossary.py`，例如 `scan_for_review(rows, content_segs, glossaries, output_langs, content_lang) -> tracks`），同 pipeline 嘅 `glossary_stage` 共用同一套 matching helpers — 保證「掃描話有 = pipeline 套得中」，獨立可測。
- 套用 prompt 由舊 `GLOSSARY_APPLY_SYSTEM_PROMPT`（app.py:3184-3237）改良，**落地前要過 Validation-First**（詞彙/MT 範圍強制）：仿 ai-edit 嘅 12-call 實證 — 改啱詞、其餘逐字保留、語體唔 drift（書面語軌唔可以變口語，ai-edit tracker 有實證呢個 pattern）。
- 鎖模式跟 AI 切割：LLM 喺 `_registry_lock` 外行，寫入前 re-acquire + 衝突檢查。
- 舊 scan/apply endpoints（profile/V6 用）暫時唔郁；後續可考慮加 active_kind gate（見 §8 out-of-scope）。

## 5. 數據模型（全部 add-only，無 migration）

- `glossary_changes` item 新欄：`lang`（語言軌 code）+ `entry_id`（詞彙表條目 id）。現有欄（`source`/`before`/`after`/`glossary`）不變。
  - 新 apply-item 寫嘅記錄齊欄；
  - pipeline `glossary_stage` 都同步加 `lang`（佢逐軌行，加欄好平；output_lang_persist union 照舊，但每 item 而家自帶 lang，歸屬唔再丟失）；
  - 舊記錄缺欄 → 前端容忍。
- 「已符合」**唔持久化** — preview 每次即場計，永遠最新。
- 檔案 entry：`glossary_ids`/`glossary_llm` 由 PATCH 可改（原本只有上載/重新處理先寫到）。

## 6. 必須保持嘅 invariants（研究 §5 全套）

1. 四庫 positional 對齊（translations idx 連號 / segments / content_asr_segments / aligned_bilingual）。
2. 任何寫入同步 `aligned_bilingual[idx].by_lang[lang]`；`by_lang[].text` 同 `{lang}_text` mirror 永不分歧。
3. 批核語義：本功能 keep_status；approve/unapprove 仍然係成 cue 全語言鏡像，唔引入 per-term 批核。
4. Cue start/end 永不被詞彙操作改動。
5. Registry RMW 喺 `_registry_lock` 內、LLM 鎖外。
6. `glossary_ids` 有序 first-wins；panel 編輯保序（剔選先後）。
7. `glossary_stage`/scan 保持 pure；matching 規則改動屬 Validation-First 範圍。

## 7. 錯誤處理 / edge cases

- **套用衝突**（preview 同 apply 之間段落被編輯/切割/合併/Rerun）→ expected_text 唔對 → 409 → 行內 ✗「段落已被修改」，其他項照行；modal 提供「重新掃描」。
- **AI 唔合格** → 422 → 行內 ✗ 可重試（重試 = 再 call 同一 endpoint）。
- **AI Rerun 進行中** → apply-item 409（避免同 bulk 重寫鬥）；preview 純讀照行。
- **渲染中** → apply-item 照行（同手動 PATCH 編輯一致 — render 用開波快照）；reapply 補 409。
- **單語檔** → 一個軌區；**零候選** → 顯示「全部已符合」+ 各軌統計，唔係空白。
- 詞彙表喺掃描後被刪 → apply-item 唔依賴 glossary 仲存在（改寫所需資料全部喺 body），記錄照寫。
- panel PATCH glossary_ids 含未知 id → 400 + toast。

## 8. 明確 out-of-scope（今次唔做）

- 舊 scan/apply（profile/V6 線）嘅翻新或退役 — 維持現狀。
- per-term/per-language 批核粒度。
- 「重新套用」改做輕量（只重行 glossary 層唔重跑 MT）— 留待日後；今次只改名+confirm+補閘。
- split 時 glossary_changes 按文字分配（而家清空，維持）。
- reapply rows/aligned 兩次獨立 derive 嘅 drift 統一。
- pipeline 記錄「已符合」（preview 即場計已滿足需求）。

## 9. 測試策略

1. **單元（RED 先行）**：`scan_for_review` — 雙軌路由（mt gate：glossary.source_lang==content_lang；refine/pass：target family）、別名/canonical 匹配、guard（單字 deny/≤2字/suffix）、已批核旗、「已符合」判定、glossary 唔適用軌嘅標示。
2. **Route 測試（mock LLM）**：apply-item 三位同步寫入、keep_status、glossary_changes append（lang+entry_id）、衝突 409、AI 唔合格 422、rerun 中 409、非 output_lang 400；preview 零副作用（前後 registry byte-identical）；PATCH glossary_ids 驗證。
3. **E2E（隔離 :5002 + 真 Chrome，真 LLM 細檔 — 項目慣例）**：panel 剔表→PATCH 落檔→掃描 modal 兩軌渲染→剔選→套用→段落文字+詞彙對照更新+批核狀態不變→重新掃描候選消失。
4. **Validation-First**：套用 prompt 12-call 實證（改啱詞/逐字保留/語體保持），寫 `docs/superpowers/specs/2026-06-12-glossary-apply-item-validation-tracker.md`。
5. **文檔**:CLAUDE.md（REST 表 + Current State）+ README（用戶說明）。
