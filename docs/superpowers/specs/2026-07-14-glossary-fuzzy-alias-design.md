# Design — 術語表近音別名（宣告層）+ 模糊比對校正

**Date**: 2026-07-14
**Branch**: `feat/glossary-fuzzy-match`
**Validation**: [2026-07-14-glossary-alias-validation-tracker.md](2026-07-14-glossary-alias-validation-tracker.md)

---

## 1. 問題

術語表嘅詞條，喺 ASR 聽錯（或者拼法唔完全一致）嘅時候配對唔到：

- **英文譯音級聽錯** — `SPEEDY SMARTIE` 聽成 `Speedy Smarty`、`WOLF COMING` 聽成 `Wolff coming`、`MALPENSA` 聽成 `Malpenza`。
- **中文近音聽錯** — `好友心得` 聽成 `好有心得`、`星際快車` 聽成 `升制快車`。
- **短名結構性不可達** — `en_correction.MIN_FOLD_LEN = 6` 令任何摺疊後短於 6 字元嘅詞條（例：`Tom`、`ACE`）**永遠唔會成為模糊候選**。冇任何演算法救得返，只有人手宣告。

### 根因（實證，非推測）

`glossary_stage`（真正套用術語表嗰層）**100% exact match**：

- source-side `build_name_pattern` 只容忍**格式**變體（大小寫／空白／引號／連字符），唔容忍拼錯。
- target-side 係一句 `t in text` 純 substring。

聽錯咗嘅名**根本唔會成為 candidate**，所以 `llm_review` 個 LLM 由頭到尾見唔到佢。唯二嘅模糊層（`en_correction` / `phonetic_correction`）行喺更底層嘅 ASR base 上，而且各有窄閘。

---

## 2. 核心概念：把「宣告」同「猜測」分開

今日只有一種模式：**猜**（模糊候選 → AI 判決）。本設計加入第二種：

> **宣告（Declared）** — 用戶講明「呢個聽錯形式 ＝ 呢個正名」。系統**確定性執行、零 LLM、零判斷空間**。

兩者互補、唔互相取代：

| | 宣告 | 猜測 |
|---|---|---|
| 觸發 | 用戶填咗別名 | 模糊候選 |
| 執行 | fold-exact 改寫 | LLM accept/reject |
| Candidate 成本 | **0** | 每個都要問 AI |
| 短名（`Tom`） | ✅ 得 | ❌ 結構上不可達 |
| 未見過嘅聽錯 | ❌ 唔得 | ✅ 得 |

**已驗證**：宣告變體 → 英文 44/44、中文 25/25，**新增 candidate 0 個**，中文側 AI judge 成本反而跌 97%。

---

## 3. 資料模型（add-only）

### 3.1 Glossary entry

```jsonc
{
  "id": "…",
  "source": "SPEEDY SMARTIE",
  "target": "伶俐驫駒 (H108)",
  "target_aliases": ["伶俐飄駒"],      // 既有：譯文（中文）近音別名
  "source_variants": ["Speedy Smarty", "Speedy Smart"]   // 新增：原文（英文）近音別名
}
```

- **`source_variants`** — 新欄位。原文側近音／聽錯寫法。
- **`target_aliases`** — **已存在但半廢**：`phonetic_correction` 由頭到尾冇讀過佢（`grep alias` = 0 hit）。本設計把佢接返入糾錯層。

> 儲存層**唔使改**：`add_entry` / `update_entry` 都係 dict splat，未知 key 已經會照存。要改嘅係 **validate / CSV / API 契約 / matcher / UI** 呢 5 條線。

### 3.2 行話 lexicon（`config/phonetic_lexicons/racing_terms.json`）

今日係**扁平字串陣列**。升級成**同時食兩種 shape** 嘅 loader（backward-compatible，舊檔零改動照行）：

```jsonc
{
  "style": "racing",
  "terms": [
    "內欄位置",                                  // 舊 shape：純字串
    { "term": "殿後", "variants": ["電流", "店後"] }   // 新 shape：帶別名
  ]
}
```

**點解要做**：25 條粵語聽錯之中 **16 條（64%）嘅正名唔係術語表詞條**，而係行話（`殿後`／`尾二`／`內欄位置`）。淨做術語表 = 蓋唔到大半。

**權限**：升級成「系統行話表」，喺術語表頁出現；**管理員可改，普通用戶只讀**（全局共用，改錯影響所有片）。

---

## 4. 匹配層

### 4.1 新 pure module `backend/alias_rewrite.py`

單一 source of truth，避免今日「兩套 regex builder 互相唔同意」嘅老問題。

```
collect_declared(glossaries, lexicon, side, route)  →  [(canonical, [variants], meta)]
apply_declared(segments, rules)                     →  (new_segments, changes)
```

**語義**：fold-exact、**longest-first**、非重疊、immutable（返新 list）、零 LLM、`ImportError` fail-open。

### 4.2 三重閘（**冇呢啲閘會即刻咬人** — 壓測 5 句正常句 corrupt 咗 4 句）

| 閘 | 規則 | 防嘅嘢 |
|---|---|---|
| **長度** | 中文別名 **≥3 字**；英文別名摺疊後 **≥3 字元** | `電流`→`殿後`、`尾指`→`尾二` 呢類 2 字誤中 |
| **字界** | Latin 用 ASCII lookaround（複用 `build_name_pattern`）；中文靠 longest-first + 非重疊 | `ACE` 咬入 `RACE`、`段處` 咬入 `段處理` |
| **適用性** | 跟 `route_for_output` | 賽馬表嘅別名唔會喺非賽馬軌開火 |

### 4.2b 宣告別名 = 常用詞 deny-list 嘅逃生門

今日 `_COMMON` / `_EN_COMMON` deny-list **冇任何 per-entry 覆寫**：一隻叫 `VICTORY` 或 `ACE` 嘅馬，source-side 永遠配對唔到（deny-list 硬性擋死，防 7% 誤判嗰個實證）。

**宣告別名就係嗰個逃生門**：用戶明文填落去 = 明文承擔。所以 `alias_rewrite` **唔行 deny-list**（否則填咗都冇用）。

**但要加安全網**：術語表 UI 喺用戶填入一個屬於常用詞／常用片語嘅別名時**出警告**（唔阻止，只提示「呢個詞喺日常評述都會出現，可能會誤中」）。長度閘 + 字界閘照行。

### 4.3 掛喺邊

| 內容語言 | 掛喺 | 讀邊個欄 |
|---|---|---|
| `en` base | `en_correction` **AUTO tier 之前** | `source_variants` |
| `yue` base | `phonetic_correction` **stage 0 之前** | `target_aliases` + lexicon `variants` |

一次改 base → 所有輸出軌（口語／書面語／英／日）自動繼承（同現有糾錯層一致嘅 pattern）。

**改動記錄**：沿用既有 `glossary_changes` 契約（`{source, before, after, glossary: <TAG>, entry_id, glossary_id, lang}`），新 tag：**`宣告別名`**。校對頁「詞彙對照」即刻睇得到，**唔郁批核狀態**。

**「掃描話有 ＝ pipeline 套得中」invariant 保持**：別名改寫行喺 **base** 層，改完之後 base 入面已經係正名 → 下游 `build_name_pattern` / `scan_track` 見到嘅係 canonical，兩邊自動一致。**唔需要**把別名塞入 `build_name_pattern` 嘅 alternation（塞入反而會令 scan 同 apply 各有各套規則）。

**唔喺 scope**：`cmn` / `ja` 內容源（今日零模糊覆蓋，需要獨立 Validation-First）。en 源檔嘅**中文譯文軌**亦唔套 `target_aliases` — MT 軌只行 source-side routing，而用戶已確認中文半邊只需要處理「中文 ASR 聽錯字」（= yue 源）。

### 4.4 同場修 bug（HIGH，出功能前必修）

`output_lang_glossary.deterministic_apply:361` 係裸 `str.replace(alias, t)` — 冇字界、冇長度閘；`_filter_target_side:718` 仲會喺 canonical 逐字命中嗰條分支傳**未過濾嘅 alias list**。

**今日冇爆嘅唯一原因：全 1,375 條詞條一個別名都冇填過。** 呢個功能一出即刻咬人。修法：加返字界 regex + 長度閘（同 `wrap_matched_names` 之前以 HIGH 修 `ACE`⊂`RACE` 同一 pattern）。

### 4.5 明確唔做（有實證，見 tracker）

- ❌ **發音編碼索引**（Double Metaphone／手寫 phonetic key）— candidate 爆 **67-84×**，而 `MAX_JUDGE_CANDS=200` 會**靜默截走 99%**，實際比 baseline 更差。
- ❌ **新依賴** `metaphone` / `jellyfish` — 對零依賴手寫 key 零增益。
- ❌ **別名餵入粵拼模糊索引** — leave-one-out **0/5**，邊際 recall = 0。
- ❌ **放寬 token-count**（n±1 window）— 零 recall 增益、candidate ×2.2。

---

## 5. 閉環：別名點樣真係入到去

> **今日全 1,375 條詞條，一個別名都冇人填過。** UI 唔做好，成個功能等於冇出。呢個唔係 nice-to-have。

### 5.1 術語表頁（`Glossary.html`）

- 詞條詳情：**原文下面**加「近音寫法」chip 列（對稱現有嘅「替代寫法（別名）」）。
- **CSV 加欄** → `source,target,target_aliases,source_variants`（保持接受舊 2/3 欄 header）。1,354 條馬名唔靠 CSV 冇得填。
- 列表：加 badge 顯示邊啲詞條已有別名（今日成個 actions 欄係空嘅）。

### 5.2 校對頁一鍵回饋（**最值錢嗰環**）

掃描 modal 今日只有「待修正／已符合」。加**第三個 section「疑似聽錯」**：

- 內容 = 模糊候選（**包括俾 AI reject 咗嗰啲**）+ 確定性層 miss 咗嘅。
- 每行一個「**加為近音別名**」掣 → 直接寫入該詞條嘅 `source_variants` / `target_aliases`。

AI 今日 reject 咗 **76%** 真聽錯（accept 8/34）；有咗呢個掣，校對員一㩒就**永久修好**，下次同一條片、同一個名唔會再錯。

### 5.3 自動學（半自動 — 唔即刻生效）

AI 確認過嘅糾正 → 自動寫入「**待確認別名**」列表 → 術語表頁一㩒接受／拒絕（可全選）。

**點解唔即刻生效**：AI 一旦錯接受一次，嗰個聽錯形式就變成**永久 AUTO 改寫規則**寫入共用術語表，之後每條片、每個用戶都中招，而且冇人會發現 — 誤差唔會平均掉，會**複利累積**。半自動保留咗「錯咗睇得到、剷得走」嘅閘，同時用戶依然唔使打字。

---

## 6. 舊檔生效

今日：base 糾錯**只喺新鮮 ASR 嗰陣行**。「全部重新生成」同「AI Rerun」都係由 cached base 直接 re-derive → **加咗別名對已處理嘅檔完全冇效果**（已驗證）。

改動：兩條路都重跑 base 糾錯層。別名改寫係 text-level 兼 **idempotent**（對已糾錯 base 再行一次係 no-op），所以安全。

**⇒ 「校對時發現聽錯 → 加別名 → 重新生成 → 真係修好」呢條工作流終於行得通。** 冇呢一步，5.2 個掣㩒完等於冇㩒。

---

## 7. P1（先驗證，後實施 — 唔喺本次 scope）

模糊比對嘅**真正樽頸唔喺匹配層，喺 AI judge**：生產實測 judge 對真聽錯 **accept 只有 24%**（8/34），對噪音 reject 99%（71/72）— 即係過分保守。root cause 早已診斷（prompt 冇同 model 講「呢啲係權威馬名冊上嘅名」）但一直未實施。

P1 要先答 4 條（見 tracker「待驗」）：

1. **B1** qwen3.5:35b-a3b 做 judge 會唔會隨 call 數退化 — 連續 200 次 call 量 malformed/refusal 率 vs call index。
2. **B2** 退化 mitigation A/B — `num_predict` 封頂 / `format:json` / 每 K 次 unload 重載 / fresh session / OpenRouter fallback。
3. **B3** judge prompt 加 roster framing → accept 率（用 2026-07-07 **人手標註集**，非循環）。
4. **B4** 「純發音相似、字元距離遠」呢一 class 究竟存唔存在 — 要建**獨立 ground truth**（本輪嘅 GT 係循環嘅，答唔到）。

---

## 8. 測試

| 層 | 內容 |
|---|---|
| Unit | `alias_rewrite`：三重閘、longest-first、非重疊、字界、immutability、fail-open；lexicon loader 雙 shape 兼容 |
| Unit（回歸） | `deterministic_apply` 字界 bug 嘅回歸測試（`段處` 唔可以咬入 `段處理`） |
| Unit | `glossary.py`：`source_variants` validate + 4 欄 CSV round-trip（舊 2/3 欄 header 仍然收） |
| 整合 | `en_correction` / `phonetic_correction` 現有測試零 regression |
| Gating（真檔 dry-run） | 851-cue 英文檔 + 48-cue 粵語檔：宣告別名全中、**已知 FP class 零新增**、`整個過→靖哥哥` 仍然被擋 |
| E2E | 加別名 → 全部重新生成 → 真係修好（今日行唔通嗰條路） |

---

## 9. 檔案

**新增**
- `backend/alias_rewrite.py` — 宣告別名 pure module
- `backend/tests/test_alias_rewrite.py`

**改動**
- `backend/glossary.py` — `source_variants` validate + CSV 4 欄
- `backend/phonetic_correction.py` — lexicon loader 雙 shape；別名前置改寫 hook
- `backend/en_correction.py` — 別名前置改寫 hook
- `backend/output_lang_glossary.py` — **修 `deterministic_apply` 字界 bug** + `_filter_target_side` alias 長度閘
- `backend/app.py` — 別名 REST（待確認別名 / lexicon admin）+ 重新生成／AI Rerun 重跑 base 糾錯
- `frontend/Glossary.html` — 近音寫法 chip 列 + 系統行話表 + 待確認別名
- `frontend/js/glossary-review.js` — 掃描 modal「疑似聽錯」section + 一鍵加別名
- `config/phonetic_lexicons/racing_terms.json` — 新 shape（可選填）

**文檔**（CLAUDE.md 強制）
- `CLAUDE.md` / `README.md`（繁中）/ `docs/PRD.md`
- 本 design + tracker + implementation plan
