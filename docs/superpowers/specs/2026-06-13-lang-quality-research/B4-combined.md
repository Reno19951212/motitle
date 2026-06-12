# B4 — 最佳組合 end-to-end pipeline（口語修復 + 書面語傳導）

**日期**: 2026-06-13 ｜ **Proto**: `/tmp/lq-research/protos/b4_pipeline.py`（repair / refine / score 三步 CLI）
**量化數據**: `/tmp/lq-research/results/B4-combined.json` ｜ **量度**: A1 catalog（high 36 主指標）
**Model**: Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3, think=False（production parity）

## TL;DR

| 指標 | 修復前 | **B4 修復後** |
|---|---|---|
| 口語 track 高置信錯誤（36 項） | 0 修復 | **34/36 = 94.4%** |
| — 扣除 5 個 vacuous 變體（31 項，B3 同口徑） | 0 | **29/31 = 93.5%**（B3 V3 raw LLM: 12/31） |
| — B1 口徑（horse+racing high 34 項） | 0 | **34/34 = 100%**（B1 AUTO 單獨: 27/34） |
| Medium（4 項） | 0 | 2/4 |
| 誤改（FP） | — | **1**（seg17 後面→後尾，refine 後語義冲走） |
| 48 段 byte-identical 對齊 A1 人手正解 | 15/48 | **41/48** |
| 書面語軌：錯名原樣殘留 | 18/36 | **0/36** |
| 書面語軌：正名出現（per-error） | 6/36 | **25/36**（餘下 gap 係 refiner 改寫跌字，唔係錯名） |
| 全程耗時（108.6s 音訊） | — | 修復 ~11s + refine ~0.6s/cue；**無 re-ASR、48-cue grid 完整保留** |

**Verdict: ✅ Promising** — 呢個組合喺單 clip 上將同音錯字問題基本清零（in-glossary 馬名 24/24、racing 術語 10/10），冇改壞任何正確馬名，並實證修復會傳導落書面語軌（0 錯名殘留 + 消除 refiner 對錯字嘅幻覺級聯）。

## 組合點揀（跟前面實驗數據）

| 來源 | 攞咗乜 | 點解 |
|---|---|---|
| **B1** | Stage 1 = AUTO tier（L1∪L2∪L3-d0、target≥3 字、greedy 替換）+ Stage 2 候選生成（L3-d1）+ M(\d)→尾X 決定性 pre-rule | AUTO tier P=1.0、27/34、零 LLM 成本；M-rule 補語音匹配結構盲點 |
| **B2** | ❌ re-ASR biased prompt **唔入主鏈** | V5 22/31 < B1 AUTO 27/34；仲要 cue grid 24 vs 48（break）、monkeypatch mlx_whisper、2-3 個新錯、5× 耗時。post-ASR 修復每項都贏。B2 留做將來源頭級補充（佢有 register 改善係 B4 冇嘅） |
| **B3** | Stage 2 結構 = per-cue + 前後文 + 候選清單；**教訓**: LLM 唔准自由改寫 | B3 V3 raw rewrite 12/31 但 6 FP 含改壞正確名（翠紅→友愛心得）— B4 將 LLM 降權做「候選 accept/reject 判決器」，災難結構性免疫 |

## Pipeline（四步）

```
48 段 ASR 口語 track
  │ Stage 0  決定性規則: M([2-9]) → 尾X                    (+3, 純 regex)
  │ Stage 1  B1 AUTO tier 粵拼自動替換 (glossary+術語表)     (+27, 純 Python 0.7s)
  │ Stage 2  L3-d1 候選 → qwen3.5 判決 (3-run majority)     (+7, 30 calls 7.3s)
  ▼
修復後口語 track（48 cue grid 不變）
  │ Stage 3  formal_refine (racing prompt) — 同 production 一致
  ▼
書面語 track（修復傳導驗證: before vs after 對照）
```

Stage 2 嘅五重 guardrail（B3 災難全部結構性擋走）：
1. **只准判決唔准改寫** — 輸出限 `{"accepts":[id...]}`，機械 apply
2. **正名保護** — 候選 span 同文中 verbatim 詞彙表名重疊一律 block（150 個候選喺呢度死咗，包括「星際快→星際快車」呢類會打爛正名嘅）
3. **near-substitution gate** — d=1 差異音節對必須 share onset/rim（電流 lau/hau ✓、尾指 zi/ji ✓、內藍米字 mai/wai ✓；頂出 ceot/hau ✗ 剔走 — LLM 曾 3/3 想 accept 呢個 FP，gate 救返）
4. **3-run majority vote** — 壓 temp 0.3 嘅 run-to-run variance（單 run 試過 accept 完又 reject 同一候選）
5. **音節對齊 tie-break** — 同名重疊 accept 揀傷害最細嘅 span（seg46 保住「係」、seg44 食埋「我」）

## ⭐ 書面語 before/after 對照（直接俾用戶睇）

「書面語（修復前）」= 而家 production 行為：錯字直入 refiner。「書面語（修復後）」= B4 修復先、再 refine。

| 段 | ASR 原文 | B4 修復後口語 | 書面語（修復前 = 現狀） | 書面語（修復後） |
|---|---|---|---|---|
| 1 | 一起步的時候,**幸運有利**快 | …**幸運有您**快 | 起步時，**幸運有利**領先。 | 起步時，「**幸運有您**」領先。 |
| 2 | 見到最出紫色衫**升制快車** | …紫色衫**星際快車** | 見最外側穿紫色馬衣的**賽駒**加速領先。〔馬名完全消失〕 | 見着身披紫色賽衣的**星際快車** |
| 3 | **內藍米字標誌星河** | **內欄位置錶之星河** | **內藍米字標誌星河**〔亂碼原樣照出〕 | **內欄位置**之星河〔refiner 跌咗「錶」字 — 見 caveat〕 |
| 5 | 留守住個五、六位仲係**好有心得** | …仲係**好友心得** | 留守於第五或第六位**仍具優勢**。〔馬名消失〕 | 保持第五、六名位置，仍屬**好友心得**。 |
| 8 | **M2** 橙衫笑傲江湖，暫時**電流精算部說** | **尾二** 橙衫笑傲江湖，暫時**殿後精算暴雪** | M2 號馬身披橙衫笑傲江湖，**暫時領先**。〔殿後→領先，意思反轉 + 馬名消失〕 | 最後一場橙衫笑傲江湖，暫時**殿後精算暴雪** |
| 18 | 紅眼罩紅衫頂出去**大愛當**係翠紅 | …頂出去**大外檔**係翠紅 | 戴紅眼罩穿紅衫的「**大愛**」**勝出**，「翠紅」**得第三**。〔幻覺：無中生有賽果〕 | 戴紅眼罩、穿紅衫的馬匹從**大外檔**出發，是翠紅。 |
| 22 | **升制快車**仲有半個**馬威有勢** | **星際快車**仲有半個**馬位優勢** | **升制快車**仍具半個**馬威之勢** | **星際快車**仍保持半個**馬位優勢**。 |
| 27 | 出面位置是**精算部説** | …是**精算暴雪** | 出面位置是**精算部說** | 外檔位置是**精算暴雪** |
| 37 | 看看有沒有機會捧走**沙田銀平** | …捧走**沙田銀瓶** | 看看是否有機會奪得**沙田銀盃**〔refiner 自己作咗個獎盃名〕 | 看看是否有機會奪得**沙田銀瓶** |
| 44 | **標之星我**…捧走今屆嘅**沙田銀屏**…精算暴雪山山來遲呀跑過第二**好有心得**跑過第三**升制快車**都跑過第四 | **錶之星河**…**沙田銀瓶**…**好友心得**…**星際快車**… | **標之星**似乎可奪得本屆沙田銀瓶。無錯，精算暴雪雖來遲，但跑過第二、**好有心得**；跑過第三、**升制快車**；亦跑過第四。〔斷句令名次錯配〕 | **錶之星河**似可奪得今屆沙田銀瓶。精算暴雪山來遲，跑過第二；**好友心得**跑過第三；**星際快車**亦跑過第四。 |

**核心傳導發現**：錯字唔修，refiner 唔單止照抄錯名（seg22/27），仲會 (a) 索性刪走唔識嘅名（seg2/5/8 — 馬名喺書面語軌完全消失）、(b) 幻覺補完（seg18 無中生有「勝出/得第三」、seg37 作咗個「沙田銀盃」、seg8 殿後變「領先」）。修復後呢啲級聯全部消失 — **修復前書面語軌 18/36 錯名原樣殘留 + 多處幻覺；修復後 0 錯名殘留**。

## 殘留問題（誠實申報）

1. **2 個 high miss 係 lexicon 外嘅 homophone_other**：放既碼→放嘅馬（seg10）、山山來遲→姍姍來遲（seg44）。語音索引完全救唔到（唔喺 glossary／術語表）— 呢類要通用粵語錯字 lexicon 或 thinking-level LLM（B3 證實 150s/cue，唔 viable）。seg44 嘅 山山來遲 refine 後仲畀 refiner 搓成「暴雪山來遲」。
2. **1 個 FP**：seg17 後**面**三匹馬→後**尾**三匹馬（2 字術語候選 面三→尾三，3 票中 2；上一 run 係 1/3 — 溫度 variance 嘅 borderline case）。傷害有限（後尾係粵語詞，refine 後出「隨後三匹賽駒」，語義同基線「後方三匹賽駒」幾乎一致）。production 可以加knob：2 字候選要 3/3 全票，或者 accept 咗都喺 proofread 標黃畀人覆核。
3. **Medium 2/4**：包尾直路→包尾入直路 LLM 三 run 全 reject（「包尾+直路」表面通順）；推小步→推少步 lexicon 外。
4. **書面語傳導唔係 100%**（25/36 正名出現）：gap 全部係 **refiner 自身對短句／名詞密集句嘅改寫不穩定**（seg3 跌「錶」字、seg11 將「幸運有您」拆做「幸運，有您支持」、seg19 將「尾二」意譯做「最後一件橙色賽服」、seg33 將馬名拆引號）。呢個係 refiner 嘅獨立品質問題（錯名殘留 = 0，即 gap 唔係修復失敗）— 建議另開 work item：refiner prompt 加「馬名 byte-for-byte」強化或 post-refine 名詞校驗（B1 matcher 可以直接攞嚟做 verify pass）。
5. **單 clip N=1**：所有數字嚟自同一段 108.6s 評述。Stage 2 prompt 喺呢個 clip 上迭代過 3 版（粵拼證據、亂碼規則、詞界警告），有 clip-specific 過擬合風險 — 落 production 前要按 Validation-First 規定跑多 clip 驗證。
6. **術語表 supplement 有溫和循環性**（承 B1 caveat）：9 個術語嚟自 A1 catalog。production 對應物 = 靜態賽馬術語表 + 賽日馬名 roster，情境合理但覆蓋率未喺新 clip 驗證。
7. **耗時**：修復 stage ~11s（30 個 judge call，0.3-1.3s/call）+ refine 每 cue ~0.6s — 對 108.6s 音訊完全可接受，無 re-ASR。

## 同前面實驗嘅直接對比

| 方案 | 修復率 | FP | grid | 額外成本 |
|---|---|---|---|---|
| B1 AUTO 單獨 | 27/34 (79%) | 0 | 保留 | 零 LLM |
| B2 V5 re-ASR | 22/31 (71%) | 2-3 新錯 | **break (24 cue)** | 2× ASR + monkeypatch |
| B3 V3 raw LLM rewrite | 12/31 (39%) | 6（含改壞正確名） | 保留 | 48 call |
| **B4 組合** | **34/34 (100%) / 29/31 (94%)** | **1** | **保留** | 30 call (~11s) |

## Production 建議

1. **可以入 spec 階段**：Stage 0+1（純 Python，~1s，P=1.0 tier）係 free win，可以即刻做 glossary stage 嘅 upgrade（而家 string-match 0/46 → 粵拼 27/34）。位置：ASR 之後、derive/refine/MT 之前（content base 上修，所有輸出語言受惠 — 對齊 A2 結論）。
2. Stage 2（LLM 判決 tier）建議連五重 guardrail 一齊 ship，3-run vote 係 ~7s 成本；2 字候選 accept 加 proofread 標記。
3. 配套 work item：(a) refiner 名詞保留強化（傳導 gap 嘅另一半）；(b) 賽馬術語靜態表＋賽日 roster 機制；(c) 多 clip Validation-First 驗證。

## 檔案

- `results/B4-combined.json` — 全部量化數據 + per-error 明細 + 12 組 written examples + 五重 guardrail 配置
- `protos/b4_pipeline.py` — 完整原型（repair / refine / score CLI，可重跑）
- `protos/b4_repaired.json` — 修復後口語 track（48 段 + per-seg applied 替換記錄）
- `protos/b4_refined_tracks.json` — 書面語 before/after 兩軌全文
- `protos/b4_raw_judge.json` — 19→10 段 judge 全部 prompt + 3-run raw 回應 + 投票記錄
- `protos/b4_refine_cache.json` — 77 個 refine call cache（可重用）
