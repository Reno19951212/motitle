# B3 — LLM 全文上下文修復同音錯字實驗

**日期**: 2026-06-13 ｜ **Model**: Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3（production 同款，`think:false` parity）｜ **量度**: A1 catalog（high 36 項，**effective 31**——剔走 5 個 input 已係 accept_also 變體嘅 vacuous 項；medium 4 項次級）

## TL;DR

| Variant | 設計 | 修復率 (effective high) | 誤改 (text FP) | 格式穩定 | 延遲 |
|---|---|---|---|---|---|
| V1 裸修復（全文，無詞彙表） | 48 段一次過 | **0/31 (0%)** | 0 | 48/48 ✓ | 26s |
| V2 全文＋候選清單 | +19 個 jyutping 候選 | **7/31 (22.6%)** | 4（全部 register drift） | 48/48 ✓ | 10.4s |
| V2T = V2 + think=true | 全文 thinking | **DNF**：>33 分鐘未出結果，人手 kill | — | — | unviable |
| V3 逐段＋前後 2 段＋候選 | per-cue ×48（似現有 pipeline 結構） | **12/31 (38.7%)** ⭐ | 6（**含 1 個改壞正確馬名**） | 48/48 ✓，全部單行 | 32s 總（avg 0.67s/cue） |
| V3T = V3 misses + think=true | 8 段 thinking probe（cap 8192） | 量化≈V3（7/8 truncated）；**trace-verdict：13 錯修 8 全＋3 partial＋1 新幻覺** | — | 7/8 唔完成輸出 | **150–183s/cue** |
| V4 OpenRouter claude-sonnet-4.5 | ceiling 對照 | **BLOCKED**：key 對所有 frontier provider 403（賬戶級 ToS block，連 "hi" 都 403） | — | — | — |

**Verdict: ⚠️ Partial** — LLM＋候選清單修復係有真實 signal（V3 38.7%，per-cue 0.67s），但 think=False 模式有改壞正確名嘅實證風險，thinking 模式質素高好多但 latency 完全唔 production-viable。可入 production 嘅形態係「V3 結構＋硬 guardrail」，唔係 raw LLM 修復。

## 候選清單（V2/V3 用）——全自動，零 oracle

ToJyutping prefilter（聲調不敏感＋懶音 normalize：n→l、ng 脫落、-m→-n 韻尾）對 1352 個 glossary 馬名 vs 全文 n-gram 掃描，threshold ≥0.75：

- 出 **19 個候選**，**A1 嘅 6 個 truth 馬名全部入晒**（幸運有您/星際快車/錶之星河/好友心得/精算暴雪/友愛心得）＋4 個本場正確名＋**9 個 distractor**（猶有心得/摯友心得/錶之星晨/錶之翠河/錶之銀河/幸運勝利/飈誌/紫辰之星/致力之城）
- 呢條 prefilter 就係 production 可以照搬嘅件——唔使人手指定本場馬

## 核心發現

### 1. V1 證實用戶觀察：無候選詞，LLM 一個都唔修（0/31）

全文 context 已經喺面前，照樣 0 修復、0 誤改——output 幾乎逐字照抄。「佢冇思考過成句句子」喺 think=False 下完全成立：佢根本唔會主動質疑同音字。

### 2. V2（＋候選）係 all-or-nothing 嘅 name-cluster substitution

修咗 幸運有您 2/2、精算暴雪 5/5——但 星際快車 0/4、好友心得 0/5（**明明都喺候選清單**）、錶之星河 genuine 項 0/2。即係佢只做「睇到好似→換」嘅淺層配對，唔會跨段統一馬名。FP 4 個全部係 register drift（的→嘅、是→係）。

### 3. V3（per-cue＋前後文）最好量化成績，但暴露三類危險行為

12/31 (38.7%)，strict（必須出 glossary 正典名）17/36——佢仲會順手將 vacuous 嘅標之星河 canonicalize 成錶之星河。Medium 多救 1 個（seg46 繩嘅係制快車→嘅係星際快車）。**但**：

- **改壞正確名**：seg18 將正確嘅「翠紅」換成「友愛心得」（前文 seg16 有友愛心得殘響＋candidate 誘導）——廣播場景最不可接受嘅錯
- **Distractor pickup**：seg5/15 好有心得 → 揀咗 glossary distractor「**猶有心得**」而唔係 好友心得（×2）
- **錯方向亂修**：升制快車→升**製**快車（×2）、沙田銀平→沙田銀**河**、標之星我→錶之星**我**（半修）
- Register drift FP（那→嗰、很→好、的→嘅、是→係）per-cue 模式照樣有

**修復全部集中喺 glossary-backed 項**：12/12 recovery 都係候選清單馬名；12 個非 glossary 賽馬術語（內欄位置/尾四/尾三/尾二/大外檔/馬位優勢/沙田銀瓶/姍姍來遲…）**0 修復**。Substitution 模式嘅 hard ceiling = glossary 覆蓋率（本 catalog 61.3%）。

### 4. 「思考完會點」——thinking 真係搵到答案，但代價失控

- **V2T（全文 thinking）**：>33 分鐘冇輸出，kill。**全文 thinking 唔使諗**。
- **V3T（per-cue thinking，8 段 probe）**：7/8 連 8192 token 都唔夠收尾（uncapped 先導 run：seg3 爆 1024s）。但 thinking trace 末段嘅結論（原文引述喺 JSON `V3T_trace_verdicts`）：
  - seg2 ✓「升制 -> 星際 … So that part is fixed」——think=False 改錯嘅，諗完就啱
  - seg5 ✓「好友心得 is the fix」——**明確避開 猶有心得 distractor**
  - seg18 ✓「翠紅 is already correct according to the list」——**避開咗 think=False 嘅改壞正確名 FP**；大愛當 唔肯定就保留（Rule 3）
  - seg37 ✓「I'll go with 瓶」（仲推理咗點解唔係盃/河）——think=False 改錯做沙田銀河
  - seg44 ✓ 5 錯修 4（銀瓶/姍姍/好友/星際；標之星我只修一半）——think=False 全 miss
  - seg19 ✗ **思考都會出軌**：尾指 幻覺成騎師名「威志」——domain 知識缺口下 thinking 反而放大幻覺
  - 13 個 targeted 錯：**8 全修＋3 partial＋2 安全保留＋1 新幻覺**
- 代價：**150–183s/cue**（vs think=False 0.67s/cue，~250 倍），>8k thinking token/cue，仲未計 7/8 唔完成

**用戶兩個直覺都證實咗**：(a) 而家條 pipeline（think=False）真係冇思考過成句句子——佢做緊淺層 candidate substitution；(b) 思考完會點——大部分 miss 會修返、distractor 會避開、正確名會保護，但係用 250 倍延遲＋偶發幻覺換返嚟。

## Production 含義

1. **唔好 ship raw LLM 修復**（任何 variant）：V3 嘅 翠紅→友愛心得 一單已經足以否決——寧願唔修都唔可以改壞正確名。
2. **可行形態 = V3 結構＋機械 guardrail**：per-cue＋前後文＋jyutping 候選清單（呢部分全自動，已證），但 LLM 輸出只准用嚟「揀 candidate」，唔准自由改寫——對 diff 做 jyutping 驗證（改動 span 必須同原 span 同音/近音先接受，register drift／威志類幻覺／升製類錯向修全部會被擋）。呢個 verify 步驟係 B 組其他 agent（jyutping span-match）嘅天然結合位。
3. **Glossary 覆蓋係 hard ceiling（61.3%）**：賽馬術語要靠額外 term list 或 ASR-level（initial_prompt/biased decoding——A 組範疇）先救到。
4. **Thinking 唔好用喺 inline pipeline**；如果要用，只可以 offline／人手觸發嘅單段 rescue（150s/cue 級數）。

## 檔案

- `results/B3-llm-repair.json` — 全部量化數據＋trace verdicts＋per-error 明細
- `results/B3-transcript-V{1,2,3,3T}.txt` — 各 variant 48 段全文輸出
- `protos/b3_llm_repair.py` — prototype（run/score/report CLI）
- `protos/b3_raw_V{1,2,3,3T}.json` — raw LLM 回應＋prompt＋thinking trace 全文

## Caveats

- V2T/V4 冇量化數據（前者 latency DNF，後者 key 403）；ceiling 對照缺席，claude-sonnet 級數會點未知。
- V3T 量化表同 V3 一樣（7/8 truncated 冇 parsed 答案），thinking 結論係人手讀 trace 判定——引述原文喺 JSON，可覆核。
- FP 計法用 difflib char-diff 對 catalog span 排除；相鄰改動有機會被 merge 入 allowed span（保守低估 FP 嘅可能性低，但存在）。
- V3 seg3 嘅「recovered」係 substring 規則下嘅寬鬆計法：實際輸出「內藍米字標誌**錶之星河**」——錶之星河 係插入，殘留咗 標誌 喺前面（awkward 但有正確名）。嚴格啲計 V3 係 11+1 partial / 31。
- 單一檔案（48 段賽馬評述）單一場景；修復率數字唔應外推到其他 domain。
