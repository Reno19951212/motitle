# MT Output Quality Research Report

**Date**: 2026-05-15  
**Subject**: Video 1 (English horse-racing analysis) + Video 2 (Cantonese horse-racing news, ASR'd in English mode)  
**Scope**: 251 EN↔ZH segment pairs（V1: 166 + V2: 85）  
**Active config**: profile `Broadcast Production` — `mlx-whisper large-v3` + Ollama `qwen3.5:35b-a3b-mlx-bf16` + `alignment_mode: "llm-markers"` + `batch_size: 1` + `translation_passes: 2`

---

## TL;DR

| Dimension | V1 (EN source) | V2 (CN audio re-ASR'd as EN) |
|---|---|---|
| 完全空譯文 | 9 (5.4%) | 2 (2.4%) |
| 超 28 字 broadcast cap | 45 (27.1%) ⚠️ | 6 (7.1%) |
| 微型片段 (1-2 字) | 22 (13.3%) | 16 (18.8%) |
| 純標點 (only `。`) | 19 (11.4%) | 14 (16.5%) |
| Chinglish leak | 12 (7.2%) | 0 |
| 簡體中文洩漏 | 7 | 1 |
| Hallucination / Bloat | 5+ confirmed | 2+ confirmed |
| **真正可用** | ~50-55% | ~30%（受 ASR 上游 garbled English 拖累）|

**Empty rate 雖低（5.4% / 2.4%），但「非空」唔等於「正確」**：人手抽查 15 條 V1 mid-length 非 Chinglish 譯文，**6 條有明顯錯譯或 hallucination**（40% error rate）。

---

## 方法論

1. 由 server 拎 fresh post-v3.17 snapshot
2. 每個 segment 嘅 `en_text` ↔ `zh_text` 配對
3. 自動分類（empty / Chinglish / over-cap / fragment / punct-only / bloat）
4. 人手抽查每類 5 條 + 隨機 15 條 "OK" 類核對譯文準確度
5. 計算 formulaic phrase 重複頻率

數據文件：
- [v1-winning-factor-pairs.json](v1-winning-factor-pairs.json)
- [v2-jockey-news-pairs.json](v2-jockey-news-pairs.json)

---

## Video 1 質量分析（English source — 真正測試）

### 1.1 結構性問題：句子級翻譯 + Marker-split 嘅 fragment 後果

`alignment_pipeline.py` 將相鄰 ASR segments merge 成完整句子 → 一次過餵 LLM 翻譯 → 用 `[N]` marker 切返每個原 segment。問題：

- LLM 將 marker 擺喺**句末標點之後**，令邊界 segment 得返 `。` 一個字符
- 即使 marker 擺得啱，**整段 ZH 自然會堆積喺第一個或最後一個 segment**，相鄰 segment 收到 fragment

**例**：seg [7] EN: `And Blazing Wukong and Amazing Partners are coming off last start wins.`  
ZH: `。`（一個句號）

呢個係**設計層面**問題，唔係 LLM 出錯。Marker-split fundamentally 將句子重新分配到時間軸 segments，但中文句法同英文唔對等，分配位置經常 awkward。

**統計**：22 條 V1 segments（13.3%）係 tiny fragment + 19 條（11.4%）係純標點，兩者高度重疊。**~13% segments 失去語意**。

### 1.2 Chinglish 洩漏（model 跑唔出中文時 fallback 英文）

12 條 V1 segments（7.2%）有 untranslated English 詞混入中文。最嚴重例子：

| idx | EN | ZH |
|---|---|---|
| 15 | `and that's Blazing Wukong and Amazing Partners. Now Amazing Partners first of all well he's lightly raced...` | `Now 真正 Amazing 的 Partners 首先 well 他傷病纏身輕微 raced，他只 had 六次 starts...`(111 字) |
| 24 | `In Jude inside Amazing Partners in red and grey,` | `在 Jude 傷病纏身、真正大刀闊斧嘅 Amazing Partners 方面，Mr Dapper 同埋 Hi...` |
| 55 | `Now, just like Amazing Partners, not the most impressive...` | `如今，正如同《Amazing Partners》一樣，並非最引人注目嘅勝利...` |

呢個係 LLM 唔肯定點翻 proper noun 嘅時候，索性英文照搬。Profile 嘅 glossary（18 條 entry）唔覆蓋大部分賽馬名（Blazing Wukong / Amazing Partners / In Jude / Mr Dapper / Hot Delight），所以每次出現都係 LLM 自由發揮。

### 1.3 Broadcast cap 超標（27.1% segments）

45 條 V1 segments 超 28 字 broadcast 上限（v3.1 設定 cap）。最嚴重例：

| idx | 字數 | ZH |
|---|---|---|
| 3 | 37 | 本週六香港賽馬日，我將率先檢視第一場賽事，而第十場賽事的致勝關鍵，正是地圖 |
| 6 | 37 | 所以這第三集一百六十米，和《火燄悟空》與《驚奇搭檔》都將脫離最後起跑而獲勝 |
| 13 | 34 | 不過我正密切關注幾匹馬，我認為它們定能應付地圖方面看來相當棘手嘅賽事 |

呢個係 alignment_pipeline 句子級翻譯 + marker-split 副作用：當 ZH 被 redistribute 時，第一個 segment 容易吃晒 sentence 嘅大部分。

### 1.4 Hallucination / Bloat / 錯譯（最隱蔽嘅問題）

呢類 issue **自動 detector 揀唔出**，需要人手核對。隨機抽 15 條 mid-length 非 Chinglish 譯文，**6 條（40%）有問題**：

| idx | EN | ZH | 問題 |
|---|---|---|---|
| 5 | `I'm going to take a look at is race` | `，其重要性更在眾多變數中顯得尤為突出` | **完全錯譯** — 原文係「將細看一場賽事」，ZH 變咗「重要性突出」 |
| 25 | `Mr Dapper the leader and Himbuk in green` | `緊貼尾部` | **完全錯譯** — leader 譯做尾部（180°相反） |
| 33 | `grinds out the win.` | `成功帶領團隊邁向榮耀。` | **Hallucination** — 加入「團隊」、「榮耀」原文無嘅元素 |
| 51 | `here. The pace is a little better mid-race,` | `儘管賽程中段稍見好轉，但始終未能真正超越平穩之勢。` | **Hallucination** — 加入「但始終未能超越平穩」段落原文無 |
| 102 | `yellow and` | `且嚴重` | **完全錯譯** — yellow（黃色）譯做嚴重 |
| 134 | `home there on Saturday but they were hard race fit horses and he` | `；但係呢場比賽極具挑戰性` | **Partial / 偏離** — 只譯一小部分 + 加入原文無嘅「挑戰性」 |

40% 錯誤率喺人手抽查上係**嚴重 quality 問題**，遠超「empty rate 5.4%」呢個 surface metric 講嘅。

### 1.5 Formulaic phrase 過度使用（system prompt 樣板 bug）

`alignment_pipeline.build_anchor_prompt()` 嘅 default system prompt 含以下例子：

> persistent → 傷病纏身、really → 真正、radical → 大刀闊斧、light → 嚴重告急

呢啲係**示例**（example），但 LLM 將佢哋當**硬性映射規則**，導致：

| 詞語 | 喺 166 條 ZH 出現次數 | 比率 |
|---|---|---|
| 真正 | 24 | 14.5% |
| 傷病纏身 | 15 | 9.0% |
| 就此而言 | 14 | 8.4% |
| 儘管 | 13 | 7.8% |
| 大刀闊斧 | 8 | 4.8% |
| 嚴重告急 | 8 | 4.8% |

**「傷病纏身」喺英文無 persistent 字、「真正」喺英文無 really 字嘅 context 都照用**（例如 seg 24 In Jude 並非傷病馬匹）。Prompt 嘅 in-context examples 反而 leak 入 output。

### 1.6 簡體中文洩漏

7 條 V1 segments 含簡體字符。例子：`这`（zhe）、`说`（shuo）、`们`（men）。Reason：mlx model qwen3.5 中文 corpus 偏簡體；prompt 雖有「繁體中文」要求但唔夠強。可以喺後處理用 OpenCC s2hk 強制轉換（同 ASR 已實作嘅 `simplified_to_traditional` flag 一樣）。

---

## Video 2 質量分析（上游 ASR 已壞，下游 MT 譯到嘅都係 garbage）

V2 baseline 原本係 Cantonese profile（ASR 出中文），但 fresh re-run 用 active profile（`asr.language=en`），mlx-whisper 強迫將粵語 audio 轉成英文。

### 2.1 ASR 上游 garbled 例子

| idx | Audio 內容（粵語推測） | ASR 出嘅 EN |
|---|---|---|
| 1 | 賽馬節目片頭 | The following video is sponsored by |
| 2 | 香港賽馬會 | The Hong Kong-based |
| 6 | 我乜都鍾意食 | I like everything. |
| 7 | 豆腐花、粟米片 | Tofu flower, corn chips, |
| 33 | 棋手艾小麗 | the chess player Ai Xiaoli |
| 63 | 三月九日澳洲新騎師 | On March 9, Australian young chess player Stenley |

「棋手」、「dice」、「chess」呢啲詞 ASR 根本聽錯：粵語講「騎師」（jockey），英文 ASR 模型聽似 chess player + chess。賽馬詞彙無對應英文發音 → 自由發揮 hallucinate。

### 2.2 MT 將 garbled English 譯做 garbled Chinese

| idx | EN（已 garbled） | ZH |
|---|---|---|
| 33 | the chess player Ai Xiaoli officially became a father | `。`（純標點，empty effective） |
| 40 | I hope Thomas will continue to show the nature of a small fortune-teller | `我期望湯馬士能繼續展現一位小財源占卜師嘅本質，並引導其父投擲更多骰子`(34 字) |
| 63 | On March 9, Australian young chess player Stenley | `三月九日，傷病纏身嘅澳洲年輕棋手史丹利真正擊敗美國棋手米蘭...`(55 字) |

V2 嘅 MT「成功率」（69% clean）係**誤導**：clean 嘅 output 同實際粵語內容無關。

### 2.3 結論

V2 唔可以攞嚟比較 v3.17 對 MT 嘅影響 — 上游 ASR 由 Cantonese profile 變 English profile，etc. 落到 MT 嗰陣已經 garbage in。

**唯一解決**：將 V2 嘅 profile 由 active English profile 改為 Cantonese profile（重設 registry 嘅 profile_id），或者 ASR 加 language auto-detect 邏輯。

---

## 共通 root cause（適用於 V1 + V2）

### A. Alignment_pipeline 句子級翻譯 + Marker-split fundamental tradeoff

呢個係 **architecture-level 限制**：

- **目的**：保留句子級豐富 context（model 唔知道 "and" 後面有冇 main clause 而保守用「同埋」是錯誤）
- **代價**：將句子 redistribute 到時間軸 segments 必然產生 fragment + uneven distribution

**alternatives**：
- `alignment_mode: ""`（batched）— 直接 per-segment 翻譯，唔做 redistribute。Fragments 唔出現，但失去 sentence context（model 易切錯句意）
- `alignment_mode: "sentence"` — 提供 sentence context，但用 time-proportion 切，毋需 LLM marker
- 新嘅 hybrid — 短 sentence 用 single-segment，長 sentence 用 marker-split

### B. Default prompt 嘅 in-context examples 變 hard mapping

`build_anchor_prompt()` 嘅 system prompt：

```
2. 使用完整主謂結構；善用四字詞與結構連接詞（在…方面、就此而言、儘管…但）
3. 保留原文所有修飾語... persistent → 傷病纏身、really → 真正、
   radical → 大刀闊斧、light → 嚴重告急
```

呢啲示例 model 視為**強制使用詞典**。改善方向：
- 改寫成 anti-pattern（e.g.，「**不要**自動將 really 譯做真正，除非真正係 emphasis」）
- 加 negative examples
- 或者完全刪掉，靠 glossary 處理具體 brand/term 映射

### C. Glossary 覆蓋率不足

V1 涉及 ~30 個專有名詞（賽馬名）+ ~8 個騎師名 + ~5 個練馬師名。`Broadcast News` glossary 只有 18 條 entry — coverage rate 大概 20-30%。其餘 model 自由發揮 → Chinglish 或者錯譯。

### D. 字幕字數 cap 唔 enforce

`post_processor.py` 設 `[LONG]` flag（>28 字）但**唔做後處理 truncation**，只係 flag 警告。Model 受 prompt 「broadcast 允許 2 行顯示，總長約 22–35 字」教育，但 LLM 對字數限制嘅遵守度本身唔高。

### E. 簡繁中文洩漏

mlx qwen3.5 model corpus 偏簡體中文，需要 post-process forced conversion。

---

## 建議改善方向（不阻 v3.17 merge）

按優先級：

### P0 — 立即可改善（用戶層面）

1. **Profile 揀 `alignment_mode: ""`**（batched flow）
   - Pros: 消除所有 marker-split fragment + tiny chunks + uneven distribution
   - Cons: 失去 sentence context，model 翻譯短句易切錯句意，但 quality 變得**穩定可預測**
   - 試用：將 prod-default 嘅 `alignment_mode` 改 `""` 重跑同一條 video 對比
2. **加 V1 賽馬名入 glossary**（30 條 entry）
   - 直接消除 Chinglish leak + 統一專名翻譯
   - Cost: 一次性人手準備，但 broadcaster 應該本身有 master glossary

### P1 — 需要 code 改動（v3.18 範圍）

3. **改 prompt 嘅 word-list examples 為 anti-pattern**
   - 改 `persistent → 傷病纏身` 為 `「persistent」一般唔需翻成「傷病纏身」，除非賽馬真係受傷`
   - 預期改善 formulaic over-use（24 次「真正」→ 預期降 50-70%）
4. **加 post-process OpenCC s2hk forced conversion**
   - Translation engine 出 ZH 後過一次 `OpenCC('s2hk').convert()`
   - 同 v3.8 ASR `simplified_to_traditional` 機制對稱
5. **`[LONG]` flag 觸發 LLM retry truncate**
   - 翻譯結果 > 28 字嘅 segment，重新發 prompt 要求 condensed 版本
   - 已有 `_retry_missing` mechanism 可作參考

### P2 — 架構改動（v3.19+）

6. **Multi-language ASR profile auto-switch**
   - File upload 時加 ASR `language: auto` 選項，由 mlx-whisper 自動偵測
   - V2 嘅 profile linkage 問題會自動消失
7. **Hybrid alignment mode**
   - 短 sentence (≤2 segments) → single-segment 路徑
   - 長 sentence (>2 segments) → 句子級+marker-split
   - 預期降 50%+ marker artifact

---

## Concluding statement on v3.17 merge

呢份報告嘅 quality issues **全部 pre-date v3.17**。v3.17 嘅 4 個改動範圍（preset trim / Whisper schema / stub delete / migration）唔影響呢啲問題。**v3.17 仍然可以 merge**，但建議：

- v3.17 merge 同時，將 active profile `alignment_mode` 改 `""` 作為 immediate quality mitigation（P0 第 1 點）
- 開 v3.18 brainstorm 處理 P1 三個 code-level 改動（prompt anti-pattern + s2hk 後處理 + LONG retry）
- v3.19+ 諗 hybrid alignment + language auto-detect
