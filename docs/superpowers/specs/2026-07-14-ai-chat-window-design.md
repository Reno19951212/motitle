# AI 助手聊天窗口（AI Chat Window）— 設計文檔

**日期**：2026-07-14
**Branch**：`ai-chat-window`（base: dev）
**狀態**：設計已審（用戶 4 項產品決策已拍板）；等待 spec review → 實施計劃

---

## 1. 背景與目標

用戶喺**主頁（index.html）同校對頁（proofread.html）**都可以打開一個可交互嘅「AI 助手」浮動聊天窗口，用自然語言（廣東話／中文）落指令修改字幕：

- 名稱／術語修正（「把所有『晨操』改成『早操』」「全部 Luke 改做霍宏聲」）
- 翻譯意思調整（「第 3 段個馬名錯咗，應該係 Y」「呢段改更書面」）
- **重複性批量修改** — 最核心 use case：用戶唔使逐段人手改，AI 掃描 + 預覽 + 一鍵套用

必須完全融入現有 output_lang 數據模型（`translations` + `by_lang` + `{lang}_text` mirror + `aligned_bilingual` 四庫同步）、批核狀態語義、審計慣例（`glossary_changes`）同互鎖（render/rerun 409）。

### 非目標（V1 明確唔做）

- 內容問答（「點解咁譯？」）— transcript 唔入 prompt，答咗就係作嘢；禮貌引導返修改指令
- 經 chat 做 split/merge/timing/approve-all/render/rerun/檔案設定
- profile / pipeline_v6 檔案編輯（同 ai-edit 一致，output_lang only；其他 kind 出「唔支援」卡片）
- regex／模糊匹配（literal case-insensitive only，同尋找取代一致）
- 跨檔操作、對話跨 reload 持久化、streaming 逐字輸出、後台 batch job

### 用戶產品決策（2026-07-14 拍板）

| # | 問題 | 決定 |
|---|------|------|
| 1 | 主頁窗口範圍 | **完整功能**（傾偈＋預覽＋套用，同校對頁一樣） |
| 2 | 批核語義 | **預設 keep_status**（修正 ≠ 重審）＋卡片「套用後批核」toggle；已批核段預設唔剔＋badge |
| 3 | 還原 | **要 session 內還原**（undo 經同一條 server-side 衝突檢查路，連批核狀態一齊還原） |
| 4 | 問答能力 | **只做修改指令**，內容問題引導返 |

---

## 2. 架構總覽（三方案混合）

由 Workflow 研究（6 readers + 3 designers + 1 adversarial critic，2026-07-14）裁決出混合架構：**Tool-Protocol 後端脊骨 + 卡片式預覽 UX + 最細可行規模**。

```
用戶訊息（≤500 字）
    │
    ▼ POST /api/files/<id>/ai-chat/parse ── 每 turn 恰好 1 個 bounded LLM call
LLM 輸出結構化 ops JSON（replace_term / rewrite_cue / clarify / unsupported）
    │
    ▼ server 機械 expand（零 LLM：casefold Latin／exact CJK 掃描 registry snapshot，200 項上限）
proposal 卡片（窗內 checkbox 清單：#段號｜時間碼｜語言 chip｜before→after diff｜撳行跳段）
    │
    ▼ 用戶剔選 → 「套用選中 (N)」
POST /api/files/<id>/ai-chat/apply ── _registry_lock 內逐項 expected_text＋start/end 重驗
    → rerun 409（鎖內查）→ 四庫原子寫 → glossary_changes 審計 → applied/skipped/failed
```

**語義重寫（rewrite_cue）行兩段式**（critic HIGH 修正 — 保住「預覽先」防線）：
1. 生成：經**現有** `POST /ai-edit`（suggest-only，prompt 已 Validation-First 過）逐 cue 生成
2. 預覽：卡片顯示**實際生成文字**（修改前／修改後）
3. 套用：預覽過嘅文字經同一個 `/ai-chat/apply` 機械寫入（**唔會** server-side rewrite-at-apply，**唔套** >60% 字符 guard — 嗰個 guard 只適用單詞替換）

**「把所有 X 改成 Y」（主力 case）零 LLM apply** — 1 個 intent call 之後全程機械，即時。

---

## 3. 後端設計

### 3.1 新 pure modules（零 I/O，mirror `ai_edit.py`／`glossary_review.py` 形態）

**`backend/ai_chat.py`**（~150 行）
- 常量：`MAX_MESSAGE_CHARS=500`、`MAX_OPS=5`、`MAX_TERM_CHARS=80`、`MAX_PARSE_OUTPUT_CHARS=1200`
- `build_parse_system_prompt(lang_labels)` — 嚴格 op-schema ＋ 3-4 個廣東話 few-shot ＋「只准輸出 JSON、絕不對話」鐵則（直接針對已記錄嘅 chat-refusal 退化模式）
- `build_parse_user_prompt(message, file_meta, last_turn_summary)` — `file_meta` 只有語言標籤＋cue 數＋當前游標段號；**transcript 永不入 prompt**；`last_turn_summary` ≤300 字（前端機械生成，非 raw history）
- `parse_ops(raw) -> Optional[dict]` — 沿用 `<think>`-strip ＋ fence-strip ＋ `json.loads(strict=False)` leniency recipe；未知 op 名／超過 MAX_OPS／超長欄位一律 `None` → 422

**`backend/ai_chat_ops.py`**（~200 行，immutable — 只回新 dict）
- `validate_ops(ops, output_languages) -> Optional[err]` — langs ⊆ output_languages（防 bogus-lang 開新 by_lang 軌 bug）、seg_no 邊界、bool-is-int 拒絕
- `expand_ops(translations_snapshot, aligned_snapshot, output_languages, ops) -> proposal` — 確定性展開：
  - `replace_term`：casefold Latin／exact CJK 掃描 `by_lang[lang].text`（用 `output_lang_glossary` 共用 matching helpers，保「掃描話有＝套得中」invariant），出 `{idx, lang, kind:"mechanical", before, after, expected_text, start, end, approved}`
  - **`approved` 由 `row["status"]` 推導**（critic MED：approve-all 只掀 row.status 唔 mirror by_lang — 用 row.status 為準，OR by_lang status）
  - `after==before` 嘅行 skip（冪等）；**200 項上限** → `truncated:true`
  - `rewrite_cue`：出單項 `{idx, lang, kind:"ai_rewrite", instruction, before, expected_text, start, end}`

### 3.2 共用寫入 helper（獨立 commit）

`_write_output_lang_cue_text(entry, idx, lang, text, keep_status)` — 由 glossary-apply-item 嘅寫入 block **抽出**（critic LOW：呢段係 review-hardened 路徑，抽 helper 要獨立 commit ＋ byte-equivalence tests 先俾 chat routes 用）：
- `by_lang[lang].text` ＋ `{lang}_text` mirror（同一變量寫兩處）＋ `aligned_bilingual[idx].by_lang[lang]`（plain-string trap 注意）
- append `glossary_changes {source:"AI 助手", before, after, lang, entry_id:None}`

### 3.3 新 routes（3 條，error contract 統一用 apply-item 慣例：400 壞輸入／404 檔案／409 衝突或互鎖／422 AI 輸出不可用／502 AI 冇回應）

**`POST /api/files/<id>/ai-chat/parse`**（suggest-only，零寫入）
- Body：`{message ≤500, cursor_seg_no?, last_turn_summary? ≤300}`（`last_turn_summary` server-side 白名單驗證 — 客戶端輸入照常唔信）
- Phase 1 鎖內：400 非 output_lang／空訊息；snapshot translations＋aligned＋語言標籤
- Phase 2 鎖外：`_make_ollama_llm_call()` 1 call（Beta 模式自動轉 OpenRouter）；Exception→502；parse `None`→422（回 `reply:"唔明白你嘅指示，可以講清楚啲嗎？"` — 聊天降級做澄清而非硬錯誤）
- Phase 3：`validate_ops` → 重鎖攞 fresh snapshot → `expand_ops` → 200 `{reply, ops, proposal:{items[], truncated, summary}, rerun_active, render_active, grid_len}`

**`POST /api/files/<id>/ai-chat/expand`**（零 LLM 重掃）
- Body：`{ops}` — 對現時 registry 重新 expand。409 恢復／split 後刷新用，**唔使燒 LLM call**

**`POST /api/files/<id>/ai-chat/apply`**（機械寫入 only — 任何冇 `after` 嘅 item 直接 400）
- Body：`{items:[{idx, lang, after, expected_text, start, end, status_after?}], approve?:bool}`
- **`_file_has_active_rerun` 409 檢查喺 `_registry_lock` 內**同寫入 pass 原子（critic：鎖外查有 TOCTOU）
- 鎖內逐項：`by_lang[lang].text == expected_text` **且** row start/end 冇變（淨 text 會漏 mechanical split 複製文字嘅 case）— 唔中 → 入 `failed[{idx,lang,error:"段落已被修改"}]` **唔斷批次**；`current==after` → `skipped`（冪等重交安全）；否則 `_write_output_lang_cue_text`
- 狀態規則：`status_after` 有值（`pending`|`approved`，enum 驗證）→ 直接 set row.status＋by_lang status（**undo 還原用**）；否則 `approve:true` → 批核；否則 keep_status
- Response 200 `{applied:[{idx, lang, prev_status:{row, by_lang}}], skipped[], failed[]}` — `prev_status` 俾前端存起做 undo；partial failure 係一級公民，唔係 error status
- render 進行中**允許**套用＋UI 警告「渲染進行中，本次修改唔會反映喺該渲染」（apply-item／手動 PATCH 先例）

### 3.4 唔加嘅嘢（刻意）

- **冇新 background job type** — 互鎖矩陣（render/split/merge/timing/rerun/reapply）零新增 predicate
- **冇** server-side 對話狀態 — server 完全 stateless
- **existing `/ai-edit`、`PATCH /translations`、glossary-apply-item 全部不改**

---

## 4. 前端設計

### 4.1 `frontend/js/ai-chat.js`（新，classic IIFE，~600-700 行；卡片渲染如超 800 行先拆 `ai-chat-cards.js`）

- **浮動窗**：byte-for-byte 跟 `find-replace.js` pattern — 注入自帶 `ac-*` prefix CSS、`position:fixed` 可拖頭部（clamp）、無 overlay 非阻擋、`document.body` 直屬子節點（**必須** — index.html `renderAll()` innerHTML 重建殺唔死佢）、z-index **2600**（modals 3000 之下、toasts 4000 之下）、`hidden` 屬性開關、close/reopen 保留對話
- **對外**：`window.AIChat = {open, close, isOpen}`；標題「**AI 助手**」— 全 UI 零引擎／型號／供應商名（包括錯誤文案，一律「AI 服務」）
- **聊天流**：用戶右泡、助手左泡（`escapeHtml` 全程）；輸入框 ≤500 字，Enter 送出（`e.isComposing` IME guard）
- **三種卡片**：
  1. **批量預覽卡**（replace_term）：「將『X』改成『Y』— 搵到 N 段（M 段已批核）」＋語言 chip；行 = checkbox＋#段號＋時間碼＋inline diff（match span 高亮）；**已批核行 badge＋預設唔剔**；撳行跳段；footer：「☐ 套用後批核」toggle＋「套用選中 (N)」＋「重新掃描」（打 `/expand`，零 LLM）；`truncated` → 「命中超過 200 段，請縮窄範圍」
  2. **單段建議卡**（rewrite_cue）：先打 `/ai-edit` 生成（per-card spinner「AI 修改緊第 N 段…」）→ 修改前／修改後 stacked panes → 「套用」（keep_status）／「套用並批核」／「唔要」／「↻ 再試一次」
  3. **澄清／唔支援卡**：AI 問返一條問題，或解釋「呢個檔案類型唔支援 AI 修改」＋（主頁）「去校對頁」deep-link
- **Apply driver**：mechanical items 一個 `POST /apply`；ai_rewrite items 串行 promise chain（`chain=Promise.resolve()`＋per-item inflight lock — 尋找取代 idiom，永不並行單一本地 LLM）；逐行實時 ✓／✗（失敗行保持剔選可重試）；identity guard（turnSeq＋fileId snapshot）棄置過期 response；完成訊息「已套用 N 項，略過 S 項，M 項失敗」＋ resync
- **還原（undo，用戶決策 #3）**：每個 applied 行喺卡上存 `{before, applied_after, prev_status}`；「復原」（整卡或逐行）經**同一個** `/ai-chat/apply` 送 `{after: before, expected_text: applied_after, status_after: prev_status.row}` — 之後有人手改過 → 該行 ✗「已被再次修改」唔會 clobber；**批核狀態連文字一齊還原**；session-scoped（reload 失效，audit trail 仍在）
- **Staleness**：卡片 snapshot `grid_len`；`segs.length` 變（split/merge/rerun）→ 整卡灰化 banner「段落已變動 — 請撳重新掃描」，套用／還原掣 disable
- **退化狀態**：502 → 「AI 服務暫時冇回應，請再試」＋重試掣；422 → 「AI 一時冇明白，請講具體啲，例如：把所有『晨操』改成『早操』」— **raw model 輸出永不 render 入對話流**；rerun 進行中 → 套用掣 disable＋tooltip

### 4.2 Page adapter（每頁 ~15 行 inline 定義，script 載入前）

`window.AIChatPage = {hasGrid, fileId(), jump(idx), refresh(), rerunActive()}`

| | proofread.html | index.html |
|---|---|---|
| fileId | `fileId` global | `activeFileId` |
| jump | `setCursor(i, true)`（跳段＋seek） | `jumpToSegment(i)` best-effort |
| refresh | `loadSegments()` → `renderSegList()/renderDetail()` | `loadFileSegments(activeFileId)`＋`fetchFileList()` |
| rerunActive | `!!_rerunJob`（advisory；真正執法在 server 409） | 無（靠 server 409） |
| gating | output_lang rows only | `uploadedFiles[activeFileId].active_kind==='output_lang'`，否則輸入 disable＋「呢個檔案唔支援 AI 修改」 |

主頁**完整功能**（用戶決策 #1）：proposals 由 server expand 生成（主頁唔需要 raw rows），套用經 server-side 衝突檢查 — 主頁冇逐段編輯器都安全。檔案切換 mid-conversation：對話插 divider「已切換檔案：<name>」，舊卡灰化（per-card fileId snapshot）。

### 4.3 掛載

- proofread.html：`<script src="js/ai-chat.js">` 喺 glossary-review.js 之後（~:1175）；launcher「AI 助手」掣喺段落表 header（「⟳ Rerun 未批核」旁）；Esc 插入現有優先 chain（ae → ga → gr → **AIChat** → FindReplace，~:3790）；V1 唔霸單鍵 shortcut（I/O/J/K namespace 已迫）
- index.html：script 喺 queue-panel.js 之後（~:6167）；launcher 喺 `.topbar-actions`；未揀檔 → 空狀態卡「請先揀一個檔案」

---

## 5. LLM 策略（退化防線）

| 防線 | 做法 |
|---|---|
| Prompt 永遠細 | 每 turn 恰好 1 個 call；system＋user 合共 <1KB；**transcript 永不入 prompt** |
| 目標檢索永遠機械 | LLM 唔揀 cue — server 確定性字串掃描；批量 replace apply 時**零 LLM** |
| 多輪 context 有界 | 唔 replay 對話史；前端機械生成 ≤300 字 `last_turn_summary`（「上一輪：把『甲』改成『乙』，命中 12 段，已套用 10」），depth-1 |
| 語義批量分頁 | rewrite 批次每頁 **10 段** generate-and-preview、單次請求上限 **~20 段**，再大 → 「請縮窄範圍」（防長 sweep 退化 — 見 local-35b-degeneration 教訓） |
| 輸出嚴格閘 | `parse_ops` 白名單＋上限；rambling/refusal/prompt-echo → `None` → 422 澄清降級 |
| 重寫 prompt 零新增 | rewrite_cue 重用已驗證嘅 `ai_edit.py` prompt byte-identical |

---

## 6. Validation-First 計劃（先驗證後寫 code — 唯一新 prompt：intent-parse）

Tracker：`docs/superpowers/specs/2026-07-14-ai-chat-intent-validation-tracker.md`

- **Production stack**：qwen3.5:35b-a3b @0.3 經真 `_make_ollama_llm_call` 路徑
- **測試矩陣**：20+ 標註廣東話 case — 批量替換／「第 N 段」（1-based 段號算術）／語義重寫／曖昧指令／out-of-scope（「幫我 render 條片」）／follow-up（帶 last_turn_summary）／**chat-refusal bait**（聊天框架最易引發嘅退化類）
- **機械 checker**：valid-JSON rate、op 欄位 exact-match（對 hand-labelled intents）、seg_no off-by-one、零 transcript 洩漏、零 raw 退化輸出
- **判分**：機械 checker 為主＋小樣本 Opus 親判（本地 judge 不可信 — 已記錄教訓）
- **合格線**：valid-JSON ≥90%＋欄位準確 ≥90%；唔達標 → **簡化 op schema**（例如放棄 scope filter／段號 arithmetic，checkbox UI 本身已覆蓋人手收窄）— schema 簡化係預期結果之一，所以 tracker 行喺凍結 schema／寫 route 之前
- 用戶 review tracker 之後先入實施

---

## 7. 測試

- `backend/tests/test_ai_chat.py` — parse_ops leniency／rejection 矩陣（含退化輸入：prompt-echo、chat-refusal 文本、`<think>` 洩漏 → 全部 `None`）、prompt snapshot
- `backend/tests/test_ai_chat_ops.py` — expand 確定性、冪等 skip、200 上限、lang 驗證、CJK/Latin matching、**approve-all 不對稱 fixture**（row.status='approved' 但 by_lang 冇 mirror → approved 必須 true）
- `backend/tests/test_ai_chat_routes.py` — 三 routes 全 error 矩陣、鎖內 rerun 409、expected_text＋timing 衝突、partial-failure response shape、`status_after` 還原語義、bool-idx 拒絕
- write-helper 抽出 commit：對 glossary-apply-item 行為嘅 byte-equivalence tests
- Playwright E2E：開窗 → 批量預覽 → 套用 → 還原（proofread）；主頁開窗＋gating
- 全部按 test-suite isolation baseline **單獨跑**驗證
- curl gates：三條新 route 嘅 happy path＋error codes

---

## 8. 風險與已知取捨

1. **intent-parse 係本地模型新領域**（JSON tool-calling 喺聊天框架下最易觸發 refusal）— Validation-First 有可能迫 schema 簡化；設計已預留降級（所有 op 都過人手確認，錯 parse 最多 422 澄清，永不寫錯嘢）
2. **大語義批量慢**：20 段 rewrite = 20 個串行本地 LLM call（每個 ~秒級）— 分頁預覽＋逐行進度＋可取消；純字串替換唔受影響
3. **reload 冇隱形突變**：所有寫入都係 request-scoped；reload 只失去對話／proposal UI（audit trail 永在）
4. **render 進行中允許套用** = 混合渲染輸出（現有 accepted 先例，警告唔封鎖）
5. **主頁整合**係前端最高風險位（兩個 poller＋innerHTML 重建）— body-mounted＋server-side scan＋apply 全走 server 衝突檢查已係最大緩解

## 9. V1 cutlist（明確剔走）

後台 batch job（`_chat_jobs`）／自由 Q&A／regex-fuzzy match／跨檔操作／timing-split-merge-render ops／對話持久化／streaming／minimize-to-pill／quick-reply chips／dashboard rail 高亮／glossary entry_id 級 provenance mapping（chat 改動記 `entry_id:None`）

## 10. 工期估算（~10-12 工作天）

| Phase | 內容 | 估時 |
|---|---|---|
| 0 | Validation-First：intent prompt probe＋tracker＋用戶 review gate | 1.5-2d |
| 1 | `_write_output_lang_cue_text` 抽出（獨立 commit＋等價測試） | 0.5-1d |
| 2 | 後端 pure modules＋3 routes＋3 test files | 2.5-3d |
| 3 | 前端 ai-chat.js（窗＋卡片＋apply driver＋undo＋雙頁整合） | 3.5-4d |
| 4 | Playwright E2E＋curl gates＋文檔（CLAUDE.md／README／PRD／plan pair） | 1-1.5d |

---

**研究出處**：Workflow run `wf_c69a9a92-2aa`（2026-07-14，6 readers＋3 designers＋1 critic，10/10 agents 成功）。Critic 全部 HIGH issue 已吸收入本設計（rewrite 兩段式、server-side 衝突檢查＋rerun 409、>60% guard 唔套用於 rewrite、glossary_changes 審計、approved 由 row.status 推導、Validation-First 先行）。
