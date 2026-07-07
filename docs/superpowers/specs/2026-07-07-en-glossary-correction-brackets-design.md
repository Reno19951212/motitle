# EN 詞彙糾錯（AUTO+JUDGE）+ 名詞括號「」 — Design

日期：2026-07-07
Worktree：`glossary-en-tag`（based on dev @ 9e4d717）
狀態：**已通過 dry-run 實證**（見 [validation tracker](2026-07-07-en-glossary-correction-validation-tracker.md) + proto：[2026-07-07-en-glossary-proto/](2026-07-07-en-glossary-proto/)）

---

## 1. 問題

用戶報告（en 源檔 + en/zh 輸出 + 賽馬詞彙表 1,353 條，1,348 條全大寫）：

1. **英文字幕軌馬名寫法唔統一** — 詞彙表存全大寫 `GOLDEN SIXTY`，字幕出 `golden sixty`。研究確認根本原因：**en 軌今日完全零詞彙表處理**（en→zh 表喺 pass 軌 route None）。
2. **空白 fragile** — 源側匹配 regex 用字面單空格（`re.escape`），雙空格/換行即 miss（實證 synthetic）。大小寫**唔係**問題（源側已 IGNORECASE，實證 147/160 大小寫唔一致命中成功套用）。
3. **zh 軌馬名靠彩數** — 歷史 miss（SUPREME AGILITY→奮鬥心、BLASTED TALENT→疾風財子）係 `llm_review` 層非確定性跌單（A/B 重推實證：baseline 時中時唔中；全大寫化後全部輪次命中）。
4. **ASR 聽錯馬名要人手 workaround** — 用戶被迫加變體詞條（`Golding 60`→金鎗六十）。舊 racing 片有系統性聽錯：`SPEEDY SMARTIE` 10 種串法、`ONLY U`→"Only You"、`TAI VICTORY`→"thai victory"。
5. **想要名詞括號** — 詞彙表級 option，出字幕時馬名/騎師名用「」括住。現 pipeline 有 `strip_name_brackets` 做緊**相反方向**（統一除括號）。

## 2. 用戶決策（brainstorm 已確認）

| 決策點 | 選擇 |
|---|---|
| EN 軌馬名寫法 | **照詞彙表原樣**（全大寫就全大寫） |
| 括號範圍 | **per-glossary 三檔**：唔括（default）/ 只中文軌 / 全部軌 |
| 匹配深度 | **機械容錯 + AI 近音判決**（對稱中文語音糾錯） |
| 架構 | **方案 A：base 層糾錯**（修一次全軌繼承） |

## 3. Dry-run 實證摘要（2026-07-07，真數據）

| 驗證項 | 結果 |
|---|---|
| AUTO tier（舊 racing 片 851 句） | 180 個改寫；人手覆核誤判 10-14（~7%），**全部**係「馬名＝普通短語」詞條（ONE MORE×5/NUMBERS/WELL ENOUGH/ON THE WAY）→ 催生修訂①降級閘 |
| AUTO tier（新片 29 句） | 0 改寫 0 誤判（音頻無全大寫詞條馬名；5 條 mixed-case 已中） |
| zh 軌 A/B 重推（2 歷史 miss） | baseline 1/2 輪 miss（重現歷史）；**修正後 3/3 輪全中** |
| JUDGE 候選（兩片） | 156 原始候選（修訂③閘後 110），含大量真聽錯（SPEEDY SMARTIE 全 10 變體、ONLY U×3、TAI VICTORY、NIGHT PUROSANGUE、GLORIOUS RYDER、MALPENSA…）；噪音以單字 d2 為主 → 催生修訂③候選閘 |
| JUDGE AI 判決準確率 | qwen3.5 3 票判決（⏳ 行緊，出數即補 tracker） |
| 括號模擬（851 句） | 129 句成功括名；**1 個巧合誤括**（「關鍵所在」普通詞語境）；2 字馬名（祝願/球星/玩笑）被 >2 gate 漏 → 催生修訂②本段命中先括 |

**三個 dry-run 修訂**（已併入本 spec）：①AUTO 全常用詞降級閘 ②括號改「本段真實命中先括」 ③JUDGE 候選閘收緊。

## 4. 架構

兩個 feature，共用一條 pipeline 鏈：

```
en 源音頻 → mlx-whisper(en) → EN base
    │
    ▼ ①en_correction.correct_segments_en（新，base 修一次）
    │    AUTO：摺疊匹配 → 改寫成詞彙表原樣（零 LLM）
    │    JUDGE：近字候選 → qwen3.5 受限判決（accept/reject 多數票）
    ▼
derive per output：en=pass（軌上已係正名）/ zh=mt（MT 對正名，穩定）
    │
    ▼ ②glossary_stage（改）：\s+ matcher 修復 + 「」wrap/strip 按 glossary 分流
persist（glossary_changes 帶 tag，校對頁詞彙對照可覆核）
```

### 4.1 新 module：`backend/en_correction.py`（pure，對稱 `phonetic_correction.py`）

**摺疊（fold）**：casefold + 空白 collapse 成單空格 + 標點變體歸一（`’‘`→`'`、`–—`→`-`、`“”`→`"`）。

**Pattern builder `build_name_pattern(source)`**：token `re.escape` 後 `'`→`['’]`、`-`→`[-–—]`，以 `\s+` join，`\b` 錨定，IGNORECASE。**同一 helper 由 `_filter_source_side`/`scan_track`/en_correction 三處共用**（放 `output_lang_glossary.py`，en_correction import），保證「掃描話有＝pipeline 套得中」invariant 不破。

**AUTO tier `stage_auto(segments, index)`**：
- 詞條 gating：`source.strip()` 非空 + `is_name_candidate`（沿用現有單字 deny-list）。
- **修訂①降級閘**：詞條**所有** token 都屬擴大常用詞表（新 `_EN_COMMON`，~top-2000 英文常用詞，module 常數）→ 唔入 AUTO，降級去 JUDGE（d0 候選）。實證：ONE MORE/ON THE WAY/NUMBERS/WELL ENOUGH/MUST GO/SO YOU WILL/I CAN/GO GO GO 全部命中呢個閘；SUPERB GUY/JUICY DRAGON 等唔受影響。
- 應用：longest-source-first `pattern.sub(source_verbatim)`（實證 ACE⊂ACE POWER 子串疊冚由 longest-first 自然處理）；span==詞彙表原樣 → no-op。
- 記錄：`{source, before(span), after, glossary, entry_id, glossary_id}` tag **`英文糾正`**。

**JUDGE tier `stage_judge(segments, index, llm_call, votes=3, cancel_check)`**：
- **修訂③候選閘**：摺疊 Levenshtein — 多 token span `1≤d≤2`；單 token **只准 d=1**；摺疊後詞條長度 ≥6；skip 同 AUTO 已應用 span 重疊；加埋降級閘落嚟嘅 d0 全常用詞候選。每檔候選上限 200（超出 log + 截斷，唔靜默）。
- 判決：受限 prompt（只准 `{"accept": true/false}`，唔確定必須 false）× votes 票多數（default 3，validation 可下調）；LLM error → 該票 None、唔夠票 fail-open skip；`cancel_check` 每候選一 call。
- 記錄 tag **`英文糾正(AI判決)`**。

**Orchestrator `correct_segments_en(segments, glossaries, llm_call, cancel_check=None, use_llm=True, votes=3)`** → `(new_segments, per_seg_changes)`；immutable（新 list，原 segments 不變）。

### 4.2 掛鈎（`app.py`，鏡像 phonetic hook 模式）

- `_run_output_lang_bound_base`：現有 yue phonetic hook 側加 `elif content_lang == "en":`（clause-split gate 之後、derive loop 之前）；`try/except ImportError` fail-open；`use_llm` 跟檔案 `glossary_llm`；changes merge 入 rows（沿用 phonetic merge 位）。
- `_produce_output_lang`（whisper-direct 單輸出路徑）：同樣 gate `content_lang == "en"`。
- **cmn/ja 源不啟用**（零驗證，同 phonetic cmn gate 先例）。

### 4.3 Matcher 修復（`output_lang_glossary.py`）

`_filter_source_side` 及 `scan_track` 改用共用 `build_name_pattern`（\s+ join + 標點變體；case 本已 IGNORECASE）。target-side（中文名）維持現狀 — 中文無大小寫/空白問題。

### 4.4 名詞括號（F2）

**數據模型**：glossary 頂層新欄 `name_brackets: "off" | "zh" | "all"`（default `"off"`）。
- `glossary.py`：`create()` 白名單加欄、`update()` merge 加欄、`validate()` 三值檢查（bad value → error）。`list_all()` 自動帶出（零改動）。CSV import/export 唔受影響（entry-level）。
- entries 照舊 `_strip_wrapping_quotes` 剝括號儲 bare term — 括號係**顯示層規則**，由 flag 控制，唔入詞條。

**Pipeline wrap（`glossary_stage` 尾端，取代現無條件 strip）**：
- **修訂②「本段真實命中先括」**：wrap 名單 = 本 segment resolved candidates 入面 canonical 出現喺最終文字嘅名（deterministic_apply 改動+verbatim confirm+llm_review 改動），**唔係**全表盲掃。實證：解決 2 字馬名（祝願/球星/玩笑照括）+ 巧合誤括（「關鍵所在」851 句 1 例 → 0）。
- 分流：該 candidate 所屬 glossary `name_brackets=="zh"` 且輸出屬中文系 → wrap；`=="all"` → 所有 routed 軌 wrap；`=="off"` → 沿用 strip（現行為，只限該 glossary 自己嘅名）。
- **en 軌（all 檔）**：`route_for_output` 加 pass-mode 新 case — glossary source 家族==content==輸出家族 → side `source-display`（唔做替換，base 已由 F1 正名；只參與 wrap，名單=本段 F1 命中+verbatim 詞彙表原樣名）。
- Wrap 實作：冪等（已括唔再括）、longest-first；**英文名帶 ASCII word-boundary**（防 `ACE` 喺 `RACE` 入面誤括 — review HIGH 修正），中文名無需；同名多表衝突 → wrap 優先，`glossary_ids` 順序先到先得。
- 2 字中文名喺 **source-side（mt）軌**可括（candidate traceability 提供安全 — 用戶 en 源 case 全屬此類）；refine/pass 軌嘅 target-side 匹配保留原有 >2 字閘（既有匹配層限制，見 §7），1 字名一律唔括。

**逐項 AI 套用（`glossary_review.py`）**：glossary bracket on → prompt 加一條「標準寫法用「」括住」+ validate 後**機械 post-wrap 兜底**（LLM 冇括就補括，冪等）。

**下游**（研究已逐面驗證 bracket-tolerant，零改動）：scan modal（substring 照中、wrapped canonical 判 `ok`）、SRT/VTT/TXT 匯出（verbatim）、ASS render（「」非 metacharacter）、⌘F、AI Rerun/全部重新生成（re-derive 自動繼承）。

**前端（`Glossary.html`）**：活躍詞彙表 header 區加「名詞括號」select（唔括/只中文軌/全部軌）→ **第一個** `PATCH /api/glossaries/<id>` 前端 caller；跟 `can_edit` 隱藏/disable；列表項 `.gli-meta` 加「」badge。

## 5. 錯誤處理

- 兩 hook `ImportError` fail-open（log + skip，job 不死）。
- JUDGE LLM 單票 error → None；多數決唔夠 → skip 候選（fail-open）。
- `cancel_check` thread 過 AUTO（loop 頭）+ JUDGE（每候選）。
- `name_brackets` 未知值：validate 擋寫入；讀到舊檔異常值 → 當 `off`。
- PATCH glossary 未知 `name_brackets` 值 → 422（route 現有 ValueError→422 convention）。

## 6. 測試計劃

- **`tests/test_en_correction.py`**（新）：fold/pattern（雙空格、彎引號、hyphen、`\b` 邊界）、AUTO 改寫+no-op+longest-first 子串、降級閘（ONE MORE 降級/SUPERB GUY 不降）、JUDGE 閘（單 token d2 拒、多 token d2 收、長度 gate、上限 200）、判決票數/fail-open、orchestrator immutability、cancel。
- **`tests/test_output_lang_glossary.py`** 加測：`build_name_pattern` 共用、`\s+` 修復、wrap 分流（off/zh/all）、本段命中先括（2 字名括到、非命中名唔括）、冪等、同名衝突。
- **`tests/test_glossary_review_*`** 加測：bracket prompt 行 + post-wrap 兜底。
- **glossary.py**：`name_brackets` create/update/validate。
- **Validation-First gating**（實施後、merge 前）：真 module 重跑兩片 proto 對照（結果須 ≥ proto 水平：AUTO 機械誤判 0、兩歷史 miss 修復、括號誤括 0）+ 1 條 generic 片零 regression；JUDGE 判決準確率記入 tracker。
- Playwright E2E：Glossary.html toggle → 重新處理 → 校對頁見「」+ 正名 + 詞彙對照記錄。

## 7. 生效範圍 + 已知限制

- 新 derive 先生效（上傳/重新處理/AI Rerun/全部重新生成）；舊檔唔郁。
- **AI Rerun 單 cue 唔過 base 層 en_correction**（rerun 只行 derive 鏈）— 同 phonetic P2 已知 gap 一致，P2 一併處理。**全部重新生成（glossary-reapply）同理**：由 cached base re-derive，上傳後先加嘅詞條只影響 MT 注入/括號層，唔會改 base 文字。
- refine/pass 軌 target-side 匹配嘅 >2 字閘令 2 字中文名喺 yue 源檔嘅書面語軌唔會被括（en 源 mt 軌不受影響）— 既有匹配層行為，唔屬本期回歸。
- 真馬名喺普通語境（「must go with the back runners」）靠 JUDGE 語境判斷，殘餘誤差非零。
- JUDGE 運算成本：851 句片 ~110 候選；上限 200 + 票數可調控制 wall time；validation 後如準確率許可可降至 1 票。
- cmn/ja 源、EN target_aliases 匹配唔喺本期範圍。

## 8. 文檔更新（完成時）

CLAUDE.md（Current State + endpoints 無新增）、README.md（繁中用戶說明：詞彙表括號選項 + 英文糾錯行為）、PRD 狀態碼、validation tracker 補完、本 design + plan pair。
