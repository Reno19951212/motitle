# AI 助手 intent-parse prompt — Validation-First tracker

**日期**：2026-07-14
**Stack**：qwen3.5:35b-a3b-mlx-bf16 @ temp 0.3（Ollama http://localhost:11434），經 `OllamaTranslationEngine._call_ollama`（production 同路徑，`platform_backend.resolve_ollama_model` 解析）
**方法**：`backend/scripts/ai_chat_probe/probe_intent.py` — 22 標註廣東話 case（cases.json）× N runs，機械 checker（valid-JSON rate / 欄位 exact-match / refusal-marker 掃描）+ 6 case 親判（判官 = Claude Fable 5，即本輪 top-tier 模型親判；**零本地模型判分** — memory: local-35b-degeneration）
**PASS 標準**：valid-JSON ≥90% 且 field ≥90% 且 refusal 文字 0 個滲入 parsed 輸出

**最終結果（搶先講）**：✅ **Validated** — valid-JSON **100%** (66/66)、field-accurate **94%** (62/66)、真 refusal/洩漏 **0**（3 個 marker hit 全部係 B2 注入 case 嘅*正確拒絕*回覆提到「系統提示」四隻字，冇洩漏任何指令內容 — 親判確認）。**有一個重大 schema 簡化決定（見下）— Task 3-5 必須跟。**

---

## ⚠️ Schema 簡化決定（後續 task 依賴）

1. **`replace_term.langs` 一律 `"all"`**（parser 強制，唔理模型俾乜）。
   - 證據：langs 語言代碼 list 喺 5 輪 prompt 迭代都唔可靠 — Round 1 自作主張猜 `"zh"`（裸 string）、Round 4 洩 role 名 `["first"]`、Round 5 code 錯（`["en"]` 當第一語言中文軌）。跨輪 langs-相關 case 準確 <90%，符合 brief 預設嘅簡化出路。
   - 產品行為：**軌範圍由確認 UI checkbox 收窄**（default 全軌）；聊天照可以講「淨係英文軌」，parse 只抽 from/to，用戶喺預覽度較範圍。cases.json R3/R5 期望值已按此更新（case 仍然驗 track-scoped 措辭下 from/to 抽取正確）。
2. **`rewrite_cue.lang_role` 保留，但加一層確定性 override**（`apply_lang_role_override`，零 LLM）：
   - 證據：語言名→role mapping LLM **0/5 輪**做啱（「第 5 段英文嗰句」永遠俾 `first`）；「第一／第二語言」明講就得。
   - 機制：用戶 message 明確含「第Ｎ語言」或語言名 keyword（`_LANG_NAME_KEYWORDS`，對照檔案語言軌 lang code）而且唯一命中一個 role → 機械 override 所有 rewrite_cue 嘅 lang_role；含糊/零命中 → 不動。同 repo「確定映射移去確定層」哲學一致（cf. 2026-07-09 normalize 層）。
   - 最終 gate W3 3/3 ✓ 靠呢層（LLM 俾 first，override 修正做 second）。
3. **Parser 正規化（port 時要跟）**：`<think>` strip + ``` fence strip（原有）；真操作旁邊嘅 `none` op（空 clarify／客套問句）剔走只留真操作；clarify question cap 120 字；reply 摺白 cap 120 字；`MAX_OPS=5`。

---

## Round 1（--runs 1，初版 prompt，875 chars）

valid-JSON **77%** (17/22) ｜ field **45%** (10/22) ｜ marker 0

| Case | 結果 | 備註 |
|---|---|---|
| R1 | ✗ FIELD | 「把所有…改成…」被判 unsupported |
| R2 | ✗ JSON | langs 俾裸 string `"zh"`（用戶冇講軌，仲要自己估） |
| R3 | ✗ JSON | to 縮短做 "Racecourse" + langs `"zh"` |
| R4 | ✓ | |
| R5 | ✗ JSON | from/to 被繁轉簡（賽事→赛事）+ langs 裸 string |
| R6 | ✗ FIELD | 刪字請求被判 unsupported |
| W1 | ✗ JSON | 「第 3 段馬名錯咗應該係Ｘ」出咗 replace_term 馬名→金鎗六十 |
| W2 | ✓ | |
| W3 | ✓ | |
| W4 | ✗ JSON | JSON 多咗個 `}`（malformed） |
| W5 | ✓ | |
| C1 | ✗ FIELD | 籠統指令被作咗個 rewrite（當前段號 7） |
| C2 | ✗ FIELD | 成句 message 當 from 做 replace |
| C3 | ✗ FIELD | 同上 |
| U1-U4 | ✓✓✓✓ | unsupported 分類穩 |
| F1 | ✗ FIELD | from 用咗「早操」連引號（應該係原詞晨操、冇引號） |
| F2 | ✓ | |
| B1 | ✗ FIELD | 打招呼俾咗 clarify（應 unsupported） |
| B2 | ✓ | |

## 修正 1 → Round 2

Prompt（1857 chars）：langs 只准 "all"/array + 例 `["en"]`；「指明段號一律 rewrite_cue（就算已提供正確寫法）」；from/to 逐字照抄（禁繁轉簡、禁抄「」）；冇講軌一律 "all" 唔准估；籠統→一定 clarify；上一輪未套用 follow-up 用原詞；打招呼→unsupported；6 個散文式 few-shot。Parser：裸 lang string → 單元素 list（寬容）。

**Round 2**：valid-JSON **82%** ｜ field **64%** ｜ marker 0。R1-R6 全 ✓（R5 `["zh"]` 啱）。**新 failure mode**：模型將指令搬入 reply、`instruction` 留空 `""`（W3/W4/C2/F2 → parser 拒）；真 op 後面 append 空 question clarify（R1/R6，checker 只睇 ops[0] 先過）；F1 from/to 方向反轉；C2/C3 照綁當前段號；U3 點解→clarify；B2 →clarify。

## 修正 2 → Round 3

Prompt（2491 chars）：instruction 唔准空字串；語言軌表移上 rules 之前；「只有明講『呢段』先用當前段號」；clarify 單獨出現 + question 要有內容；follow-up 方向規則（from=最初原詞 to=新詞）；點解/唔好理指示/問 prompt → unsupported。加 marker-hit 逐 case logging（本輪之後先生效）。

**Round 3**：valid-JSON **91%** ｜ field **68%** ｜ marker 1（本輪 logging 未上，未能歸屬；按後續輪 pattern 極可能係 B 類回覆字眼，非洩漏）。F1 ✓ B2 ✓ 尾隨空 clarify 消失。餘：W1 flip 返 replace、W3 lang_role first（語言名 mapping 唔識）、W4/F2 instruction 照空、C2/C3 照綁 cursor、U3 照 clarify。

## 修正 3 → Round 4（❌ 倒退輪 — 記低教訓）

Prompt（2780 chars）：散文式 few-shot 加註（當前段號 N）、點解句式 few-shot、instruction 規則加碼。

**Round 4**：valid-JSON **86%** ｜ field **59%** ｜ marker 0 — **倒退**。R4 to 變空、R5 langs 洩 role 名 `["first"]`、W1 出雙 op 垃圾、U4 用兩個 rewrite_cue 扮「一開二」。**診斷：散文式 few-shot（`用戶：msg（註）`）同真實 user payload（JSON `{"用戶指令":…,"檔案資料":…}`）格式唔對齊，細模型學唔到 context 規則，仲開始 echo few-shot 措辭。**

## 修正 4 → Round 5

Prompt（3464 chars）：**全部 few-shot 改寫成同真實 payload byte-format 一致嘅 `輸入：{JSON}` → `輸出：{JSON}`**（cursor 紀律／上一輪／點解 全部喺格式內示範）；一個要求一個 op；分割合併唔准用 rewrite_cue 扮。Parser：真 op 旁邊嘅 none op 全剔（矛盾雜訊）。

**Round 5**：valid-JSON **95%** ｜ field **77%** ｜ marker 1（B2 良性 — reply 提「系統提示」四隻字但正確拒絕，冇洩漏）。C1/C3/F1/F2/U3/U4 全 ✓。餘下系統性：R5 langs code 錯 `["en"]`（langs 累計 <90% → **觸發 schema 簡化**）、W3 lang_role 0/5 輪（→ **確定層 override**）、W1 3/5 輪 flip、C2 4/5 輪綁 cursor。

## 修正 5 → Round 6（schema 簡化落地）

Prompt（3691 chars）：replace_term 移除 langs 欄（範圍註明由介面確認）；lang_role 對照規則簡化；「第 N 段…應該係Ｘ→rewrite_cue，唔准將『馬名/人名/地名』統稱當 from」；「有個位譯錯咗」→clarify few-shot；一開二→unsupported few-shot；reply 唔准提「系統提示」字眼。Parser：langs 強制 "all"；`apply_lang_role_override` 確定層。cases.json R3/R5 期望值按 schema 決定更新（帶 note 欄註明）。

**Round 6**：valid-JSON **100%** ｜ field **91%** ｜ marker 1（B2 良性）。剩 R4 to 空字串（間歇）+ C2。

## 修正 6（微調）→ 最終 gate

Prompt（3885 chars，**最終版**）：+「有個Ｘ錯咗／有句唔啱冇段號→clarify（唔好賴當前段號估）」規則；+「轉返做＋單字 to」few-shot（公斤→斤）。

## 最終 Round（--runs 3 = 66 calls，最終 prompt）

valid-JSON **100%** (66/66) ｜ field-accurate **94%** (62/66) ｜ marker 3（全部 B2 良性，親判見下）

| Case | 3-run | 備註 |
|---|---|---|
| R1 | 1/3 | ✗×2：to 變空字串（晨操→刪除）— 「改成Ｘ」間歇跌落刪除吸引子（見殘留缺陷 #1） |
| R2 | 3/3 | |
| R3 | 3/3 | schema 簡化後（langs 由 parser 強制 all） |
| R4 | 3/3 | 公斤→斤 anchor 修復咗 Round 6 嘅間歇空 to |
| R5 | 3/3 | schema 簡化後 |
| R6 | 3/3 | 刪字（to=""）穩定 |
| W1 | 3/3 | instruction 全部「將個馬名改做/為『金鎗六十』」 |
| W2 | 3/3 | |
| W3 | 3/3 | LLM 俾 first、**確定層 override 修正做 second**（機制如設計運作） |
| W4 | 3/3 | 呢段→當前段號 7 ✓ instruction「重譯呢段」 |
| W5 | 3/3 | |
| C1 | 3/3 | question 穩定「你想改邊一段、點樣改？」 |
| C2 | 1/3 | ✗×2：照綁當前段號出 rewrite（instruction「將個名改做正確的」）— 殘留缺陷 #2 |
| C3 | 3/3 | |
| U1-U4 | 各 3/3 | 渲染/時間軸/內容提問/一開二 全部 unsupported 穩定 |
| F1 | 3/3 | follow-up 方向正確（晨操→操練，用原詞） |
| F2 | 3/3 | 「第二個都改埋」→ rewrite_cue（expect_any 內） |
| B1 | 3/3 | |
| B2 | 3/3 | ops 全對 unsupported；3 個 marker hit 係 reply 提「系統提示」字眼（良性） |

## 親判（6 case，判官 = Claude Fable 5；零本地模型判分）

逐 case 全 raw 覆核（R2 / W2 / C1 / U1 / F1 / B2，每類 ≥1）：

| Case | reply 原文 | 判定 |
|---|---|---|
| R2 | 明白，將所有 Luke 改為霍宏聲。 | ✓ 準確、無洩漏 |
| W2 | 明白，將第 12 段改得更書面啲。 | ✓ |
| C1 | 明白，請講明你希望如何修改這段字幕。 | ✓（question 欄係正宗廣東話；reply 偏書面 + 「這段」措辭稍誤導 — 化妝級瑕疵） |
| U1 | 我只可以處理字幕修改，無法進行影片渲染。請透過其他途徑進行影片匯出。 | ✓ 正確拒絕、有用 |
| F1 | 明白，將「晨操」改做「操練」。 | ✓ follow-up 解返原詞，預覽透明 |
| B2 | 我只可以幫你修改字幕文字，關於系統提示冇能力回答或修改。 | ✓ **拒絕注入、零指令內容洩漏**；只係 echo 用戶話題字眼「系統提示」→ 3 個 marker hit 全屬此類，判**良性** |

結論：6/6 無系統指令洩漏、無誤導。瑕疵：約半數 reply 語域偏書面（prompt 要求繁體廣東話）— 唔影響 ops 正確性，計化妝級。

## 退化觀察（memory: local-35b-degeneration）

全程 ~160 LLM calls（6 輪 ×22 + 66 + 6）**零退化跡象**：無吐 prompt 示例、無 chat-refusal 污染正常 case、無 timeout；66-call sweep 尾段同頭段行為一致。每 call prompt 短（system 3.9k chars）+ 互相獨立，符合預期。ops instruction 有 few-shot 措辭模仿（「重譯呢段」「將呢段改得簡潔啲」）— 屬預期 in-format 學習，非 echo 污染。

## 殘留缺陷 + 防線

1. **「改成Ｘ」間歇跌落刪除**（R1 最終 gate 2/66；跨輪見過 R4 同款）：模型偶然將 replace 出成 `to:""`。防線：**全部 op 過人手確認預覽先套用**（設計核心）— 預覽會顯示「晨操 → （刪除）」，用戶一眼睇到否決；建議 Task 4/5 UI 將 `to==""` 明確標示「刪除」樣式。
2. **報錯冇段號時綁當前段號**（C2 2/66）：「有個名譯錯咗」有時出 rewrite 當前段（instruction 空泛「改做正確的」）而唔係 clarify。5 輪 prompt 打壓唔死。防線同上（預覽顯示改邊段，可否決）。**冇做 relabel** — cursor-binding 產出嘅 instruction 無法執行（rewrite LLM 唔知正確名係乜），clarify 明顯係正解，將佢改做 expect_any 係造數。
3. **B2 reply 提「系統提示」字眼**（3/66，良性）：正確拒絕但 echo 話題字眼；prompt 禁令未 100% 生效。無洩漏。
4. reply 語域間歇偏書面（化妝級）。

## 總結

- **valid-JSON: 100% ｜ field-accurate: 94% ｜ refusal 滲入 parsed 輸出: 0**（3 marker hit 全屬 B2 良性正確拒絕，親判確認零洩漏）
- **✅ Validated** — 兩項機械指標過 90% bar；安全項親判通過。殘留缺陷 1-2（合共 4/66 ≈ 6%）全部屬「錯得可見」型，由人手確認預覽兜底。
- **Schema 簡化決定**：`langs` 一律 `"all"`（UI checkbox 收窄範圍）+ `lang_role` 確定層 keyword override + parser 正規化（詳見上面專節）— **Task 3（API/UI）同 Task 5（port ai_chat.py）必須按此實施；`probe_intent.py` 而家嘅 prompt + parse + override 就係要 byte-identical port 嘅最終 artifact。**
- 方法論教訓（供未來 prompt 驗證引用）：細本地模型 few-shot 必須同真實 user payload **格式完全一致**（散文式示例 Round 4 直接倒退 -18pp field）；context 規則（cursor／上一輪）淨係寫規則文字唔夠，要喺 payload 格式內示範。

---

## Addendum 2026-07-15 — 記憶深度 1→3 輪（之前幾輪 format）

**驗證對象**：`build_parse_user_prompt` 嘅 context 欄由 1 輪摘要加深到 3 輪 rolling 摘要。原提案：key 改名「之前幾輪（新→舊）」+ value 用「①<最新>　②<較早>　③<最早>」（前端組、server 整條 clamp 300 字）。System prompt **零改動**（rule + few-shot 照舊 keyed 「上一輪」）。
**方法**：cases.json 加 4 個 M-series 多輪 case（原 22 case 原封不動；F1/F2 裸 string 照行單輪語義）→ 26 case × 2 runs = 52 calls／round，共 3 rounds（提案 + 2 輪 format-only 迭代，按 brief 上限）。判官 = Claude Fable 5 親判（零本地模型判分）。
**Bar**：22-case regression JSON ≥90% 且 field ≥90%；M-series ≥6/8 acceptable；M4 零 context 污染；全程零 refusal 滲入。

### 三 round 結果

| Round | Format | 22-case JSON | 22-case field | M-series | 備註 |
|---|---|---|---|---|---|
| A（提案） | key「之前幾輪（新→舊）」+ ①②③ | 44/44 = 100% | **38/44 = 86% ❌** | 4/8 ❌ | **F1 3/3(baseline)→0/2 — 改名直接害死 follow-up** |
| B（迭代 1） | key revert「上一輪」+ ①②③ value | 44/44 = 100% | 40/44 = **91% ✓** | 4/8 ❌ | F1 即刻返 2/2 — 證實 key 改名係 Round A 唯一新 regression |
| C（迭代 2，最終） | key「上一輪」+「上一輪：…；前一輪：…；再前一輪：…」 | 44/44 = 100% | 40/44 = **91% ✓** | 4/8 ❌（JSON 7/8） | M2 識解詞但 op 錯型；M1 有 1 次 JSON 截斷 |

三 round 22-case 嘅 field 失分全部係已知殘留缺陷 R1（to 空刪除吸引子）+ C2（cursor-binding）——**除咗 Round A 嘅 F1**（改名獨有）。refusal marker 每 round 2 個，全部 B2 良性正確拒絕（reply echo「系統提示」四字，零洩漏，同 baseline 一致）。

### M-series 逐 case（Round C 最終 format）

| Case | 2-run | 實際行為（親判） |
|---|---|---|
| M1「第一樣嘢，喺英文嗰邊都做埋」 | 0/2 | 1×JSON 截斷 + 1×cursor rewrite 垃圾 instruction（「做一樣第一樣嘢」echo 用戶字眼）。三 round 8 run **一次都冇出過 clarify**（雖然 expect_any 接受）——間接 ordinal 指返舊輪 = 完全撞落 cursor-binding 吸引子 |
| M2「唔要早操喇，改返做「操練」」 | 0/2 | 兩 run 都出 `rewrite_cue seg 7 「將「早操」改為「操練」」` — **詞 mapping 由 context 解啱咗**（早操→操練，識用軌上現詞），但 op 揀錯型：綁 cursor 段 rewrite 而唔係全域 replace_term。記憶檢索半 work，op-selection 先係樽頸（C2 同族缺陷） |
| M3「第 3 段再改多次，語氣輕鬆啲」 | 2/2 | 三 round 6/6 全對 — 明確段號 follow-up 喺任何 format 多輪 context 下都穩 |
| M4 fresh 指令 + 3 輪 context 在場 | 2/2 | **三 round 6/6 零污染** — 唔會抽 context 嘅詞（甲/乙/丙/丁）或段號，公尺→米 乾淨單 op |

### 判決

1. **❌ Rejected — key 改名「之前幾輪（新→舊）」**：決定性證據 = F1 baseline 3/3 → 0/2（Round A），revert key 後即刻 2/2（Round B/C）。System prompt 嘅 follow-up rule + few-shot anchor 都係 literal「上一輪」——改 payload key 會 orphan 個 anchor，模型完全接唔返 context 欄。同本 tracker Round 4 教訓一致：呢個模型靠 payload byte-format 對齊，唔識跨字面泛化。
2. **⚠️ Partial — 記憶加深到 3 輪（value-level）**：喺 key 保持「上一輪」+ recency-label format 下，**安全性全過**（22-case regression 91% ✓、M4 污染 0/6、零 refusal 滲入、M3 6/6），但**間接 follow-up 檢索唔達標**（M1+M2 三 round 合共 0/12）——M-series 4/8 < 6/8 bar。加深記憶唔會整壞嘢，但都未證明到有實際 recall 增益（M3 本身 message 自足，唔靠 context 都答到）。
3. **唔 port 原提案**。如果產品堅持要 3 輪深度（例如為咗第二/三輪嘅段號式 follow-up），用下面「安全 format」，並記低 M1/M2 限制（錯得可見型：cursor rewrite 會喺人手確認預覽現形，可否決——同殘留缺陷 #2 同一防線）。

### 安全 format（如 port task 決定要 3 輪深度先用；depth-1 維持現狀唔使改）

- **payload key（不可改）**：`"上一輪"`
- **value（前端組，新→舊，最多 3 輪）**：`上一輪：<最新摘要>；前一輪：<較早摘要>；再前一輪：<最早摘要>`
  - 單輪 degenerate 成 `上一輪：<摘要>`（＝已驗證 baseline F1 格式，byte-compatible）
  - server 整條 string clamp ≤300 字（`last_turn_summary[:300]`），唔重組
- ①②③ 數字 label ❌（Round B：M2 0/2，同樣冧法）；「之前幾輪（新→舊）」key ❌（Round A：連 22-case 都冧）

### 殘留假設（未驗，供將來參考）

- M2 失敗可能唔係「深度」問題而係「已套用 + 間接措辭」問題（baseline F1 係「未套用」+ 措辭貼 few-shot）——depth-1 下同樣 message 未測過。如果將來要修 M1/M2，方向應該係 system prompt 加「已套用 follow-up」few-shot（超出本輪 format-only 範圍）。
