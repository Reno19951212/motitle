# 確定性後處理正規化層（單位 + 騎師正名）Design

日期：2026-07-09
Worktree：`quality-standard`（based on dev @ a737a09d）
方向：分流 —— 將**確定性**嘅嘢由概率 MT prompt 移去確定層（用戶批准）

---

## 1. 問題

賽馬 racing.txt prompt 補強（2026-07-09 ship）之後，用戶 E2E 發現效果**散、時中時唔中**：
- 檔1「2,000's another step」→「二千**公尺**」（單位規則靠 prompt，MT 冇跟）
- 檔1「Luke had given him」→「**Luke** 已策騎他」（騎師名靠 prompt G 段名單，MT 冇改）

根因：**MT prompt 係概率性** —— 靠 LLM 每次自己決定跟唔跟規則 + temperature 隨機 + 本地 model 唔穩。對於**冇判斷成分嘅一對一映射**（公尺一定係米、Luke 一定係霍宏聲），用概率工具係錯配。

**關鍵架構發現**：詞彙表 source-side 其實**都係經 LLM**（`output_lang_glossary.py:378` 「English name in Chinese output → defer to LLM」），唔係確定。但 `apply_script`（OpenCC 繁簡）喺 MT 之後**確定性**行，係放新確定 pass 嘅現成 hook 位。

## 2. 分流原則

| 類型 | 例子 | 機制 |
|---|---|---|
| **確定映射**（本 spec） | 公尺→米、Luke/盧克→霍宏聲、Reset 保護 | **確定性後處理**（regex/表，零 LLM，每次一樣） |
| **語意判斷**（留 prompt） | work=晨操定工作、back in field=後上定後方 | racing.txt prompt（無可避免要 LLM 理解上下文） |

prompt 同確定層**互補**：prompt 減少出錯次數，確定層兜底保證 100%。

## 3. 用戶決策

| 決策 | 選擇 |
|---|---|
| 騎師名覆蓋 | **兩種都覆蓋** —— 保留英文（Luke）+ 音譯錯（盧克）→ HKJC 正名 |
| 單位生效範圍 | **所有中文輸出軌**（米係香港中文規範，通用/新聞都應統一）；騎師名只賽馬 |

## 4. 架構

新 pure module **`backend/output_lang_normalize.py`**（零 LLM、零隨機、immutable）。

```
MT (crosslang_mt) → apply_script (OpenCC 繁簡)
                  → ★ normalize_units   (所有中文軌)
                  → ★ normalize_names    (賽馬軌，style=racing gate)
                  → glossary_stage (馬名，現行)
```

放喺 **兩個 hook 位**（同 apply_script 並排，之後、glossary_stage 之前）：
- `output_lang_aligned.py` `derive_aligned_output`（bound-base/cross 主路徑）
- `app.py` `_produce_output_lang`（whisper-direct/legacy 單輸出路徑，L514 apply_script 之後）

**點解新 module 唔塞入 apply_script**：apply_script 專責 OpenCC 繁簡轉換，職責單一；單位/名稱正規化係唔同關注點 → 獨立 module 易測、易獨立撤回。

## 5. 兩個 pass

### 5.1 `normalize_units(segments) -> (segments, changes)`（所有中文軌）
純字串替換，零判斷：
- `公尺 → 米`、`公裏 → 公里`（異體統一）
- 有序表 `str.replace`；只替換單位詞，唔郁數字。
- 風險極低（「公尺」喺中文冇其他意思）。

### 5.2 `normalize_names(segments, roster) -> (segments, changes)`（賽馬軌，style gate）
騎師名對照表 → 正名替換。對照表 `config/racing_names/jockeys.json`：
```json
[{"canonical": "霍宏聲", "variants": ["Luke Ferraris", "Luke", "盧克"]}]
```
替換規則（**substring 安全係關鍵**）：
- **英文變體**：word-boundary regex `\bLuke\b`（IGNORECASE）— 防 "Lukewarm" 誤中
- **中文音譯變體**：substring，但 **≥2 字下限 + 只收唔撞常用詞嘅音譯**（「盧克」安全，唔收單字/常用詞）
- **longest-first**：先 "Luke Ferraris" 後 "Luke"，防部分替換
- already-正名 → no-op（唔記錄）
- 變體表由 Claude 從診斷 + HKJC 常見騎師組**人手策展，寧缺莫濫**（唔確定嘅音譯唔收）

### 5.3 記錄
兩 pass 替換記入 `glossary_changes`，tag「單位正規化」/「騎師正名」，格式同 glossary 一致（`{source, before, after, glossary, lang}`）；校對頁詞彙對照可見可覆核。merge 位同 phonetic/glossary 現行 pattern（glossary_stage overwrite seg glossary_changes，故正規化記錄要喺 glossary_stage 之後 merge，或 pass 內 append 到 seg 再由 glossary_stage 保留 — 實作時對齊現行 merge 邏輯）。

## 6. Validation-First

確定性 code → 主 gate 係 **unit test 全覆蓋**（唔使同退化本地 model 搏）：

**A. 單元測試（pytest，零 LLM）**
- 單位：`二千公尺→二千米`、`1600公尺→1600米`、`公裏→公里`、無單位句不變、公里保留
- 名稱：`Luke→霍宏聲`、`盧克→霍宏聲`、`Luke Ferraris→霍宏聲`(longest-first)、`Lukewarm` 不誤中(word-boundary)、非賽馬軌不郁、already-正名 no-op、≥2 字下限
- immutable、glossary_changes 記錄格式

**B. 真檔重量度（dev-side，零 LLM）**
- 攞兩檔已 re-run registry 譯文，直接 apply 兩 pass，print before/after
- 確認：檔1「二千公尺」→「二千米」、「Luke 已策騎」→「霍宏聲 已策騎」；其他句零改動

**C. E2E** — 重新處理真片，校對頁見單位/騎師確定修正 + 詞彙對照記錄

## 7. 成功標準

| 項 | 門檻 |
|---|---|
| 單元測試 | 全 pass（確定性邏輯全覆蓋） |
| 真檔 apply | 檔1 公尺→米 ✓、Luke→霍宏聲 ✓、零誤傷 |
| 誤傷 | word-boundary + 賽馬軌 gate + 策展變體 → 0 |

## 8. 錯誤處理 / 風險

- jockeys.json 缺失/壞格式 → fail-open（log + skip names pass，唔炒 job）。
- 音譯變體撞常用詞 → 靠人手策展 + ≥2 字下限；有疑問寧可漏（唔誤傷）。
- 單位 pass 對非中文軌（en）→ gate `output_lang in (yue/zh/cmn)`，唔郁英文軌。
- 同 racing.txt prompt 唔衝突：prompt 儘量譯啱，確定層兜底 —— already-米 就 no-op。

## 9. 範圍 / 明確唔做

- **IN**：單位公尺→米（所有中文軌）、騎師名確定替換（賽馬軌，英文+音譯錯變體）。
- **OUT**：語意術語（晨操/後上/初次上陣，留 prompt）；ASR 聽壞專名（上游）；馬名（現行 glossary 機制夠用）；cloud MT model（另議）。

## 10. 文檔更新（完成時）
CLAUDE.md（新 module + hook）· README（賽馬質量段落）· validation tracker · 本 design（+ plan）。
