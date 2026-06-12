# B1 — 粵拼語音匹配 prototype（recall/precision 驗證）

**日期**: 2026-06-12 · **代號**: B1 · **狀態**: ✅ Validated（兩層架構）
**Proto**: `/tmp/lq-research/protos/b1_phonetic.py`（純 Python，全 clip 0.6s，無 LLM）
**量化數據**: `/tmp/lq-research/results/B1-phonetic.json`

## TL;DR

粵拼語音匹配**值得入 production，但必須行兩層架構**，唔可以一刀切自動替換：

| Tier | 規則 | Recall (high-conf 34 項) | Precision | 動作 |
|---|---|---|---|---|
| **AUTO** | L1 ∪ L2 ∪ L3(fuzzy_dist=0)，target≥3 字 | **27/34 = 79.4%** | **1.000**（27 applied，0 harmful） | 直接自動替換 |
| **AUTO + LLM** | 再加 L3(fuzzy_dist=1)，target≥3 字 | **30/34 = 88.2%**（medium 2/3） | LLM tier 原始 0.330 | 候選交 LLM 判決 |

- 對 **in-glossary 馬名錯誤（24 項）**：AUTO 救 23/24 = 95.8%，AUTO+LLM = **24/24 = 100%**。
- 淨計 glossary（無補齊術語表）：AUTO = 23/34，加埋補齊 9 個術語先去到 27/34 — **補齊馬名/術語表係效益放大器**。
- 剩餘 4 個 high-conf miss：M4/M3/M2（拉丁字 span，**無粵拼可言，結構性盲點**）+ 尾指→尾二（2 字 target 被 length gate 排除）。
- **L3 全開直接自動替換 = 災難**：precision 0.114，48 段會錯改 61 處。三級 trade-off 嘅答案好清楚：**L1/L2/L3-d0 自動替換，L3-d1 候選+LLM 判決**。

## 方法

1. **索引**：glossary.json 1352 entries → strip 「 (編號)」→ 去重得 **1290 個中文名**（0 個非 CJK 跳過）→ ToJyutping 音節序列。另加 **9 個 supplement terms**（A1 catalog `in_glossary=false`、high/medium、horse_name/racing_term 嘅 suspected_truth：內欄位置・尾四・尾三・尾二・殿後・大外檔・包尾入直路・馬位優勢・沙田銀瓶），模擬「補齊馬名/術語表」情境。兩個 index 分開 tag，所有指標分 G（淨 glossary）/ G+S（加補齊）兩組報。
2. **匹配器**：每段 text 抽連續 CJK run → sliding 2-6 字 n-gram → 粵拼 → 三級：
   - **L1 完全相同**（連聲調）
   - **L2 聲調不敏感**（toneless 相同）
   - **L3 fuzzy edit-distance ≤1**（音節級；先做懶音 normalize：n/l 聲母合流、ng/∅ 聲母脫落、韻尾 m/n/ng 合併、k/t 韻尾、eng/ing 文白異讀（平 peng4↔瓶 ping4）、鼻音節 ng/m；normalize 後容許 1 個音節 substitution 或 insert/delete）。`fuzzy_dist` 記低 normalize 後嘅實際距離（0 = 純懶音/聲調差，1 = 真係差成個音節）。
3. **跑 48 段** → 1074 個 candidates（另有 16 個 span==name 自我匹配，no-op 剔除）。
4. **對 A1 catalog 計分**：recall 對 horse_name+racing_term（high 34 項主指標、medium 3 項次級）；candidate 對住 corrected_text 判 TP / FP_wrongfix（改錯名）/ FP_corrupt（郁咗本來啱嘅字）；low-confidence 6 項按 A1 指引唔計 FP。自動替換模擬：greedy 非重疊揀 candidate 直接改字串，同 corrected_text 逐段對。

## 索引統計

- 1290 glossary 名 + 9 supplement；**toneless 粵拼 collision 喺 1290 名之內只有 1 對**（銳一/銳逸）— 詞彙表內部同音撞名唔係主要風險。
- 真正風險係 glossary 名撞**日常用語**：馬名「飈誌」(biu1 zi3) 同「標誌」完全同音 → L1 都會中（見 FP 剖析）。

## 三級 recall / precision 主表

High-conf 34 項（horse_name 24 + racing_term 10）；cumulative：

| 配置 | R@L1 | R@L1-2 | R@L1-3 | P@L1 | P@L1-2 | P@L1-3 |
|---|---|---|---|---|---|---|
| 淨 glossary | 20/34 (58.8%) | 21/34 (61.8%) | 24/34 (70.6%) | 0.952 | 0.750 | **0.097** |
| glossary+補齊 | 21/34 (61.8%) | 23/34 (67.6%) | **31/34 (91.2%)** | 0.955 | 0.767 | **0.114** |

- 淨 glossary 嘅 L3 ceiling = 24/34，因為 10 個 racing_term 根本唔喺 glossary — **覆蓋唔齊先係第一瓶頸**，匹配器對 in-glossary 錯誤 L1-3 recall 已經 100%（24/24）。
- L3 recall 勁（91.2%）但 raw precision 崩盤（0.114）— 1074 個 candidates 入面 942 個係 FP。

## Precision 按 (level × target 字數) 分層 — gating 嘅依據

| 層 | tp | fp | precision |
|---|---|---|---|
| L1 / 4字 | 21 | 0 | **1.000** |
| L1 / 2字 | 0 | 1 | 0.000（飈誌） |
| L2 / 4字 | 2 | 0 | **1.000** |
| L2 / 2字 | 0 | 6 | 0.000（全部係 標之→飈誌） |
| L3 d=0 / ≥3字 | 4 | 0 | **1.000** |
| L3 d=1 / ≥3字 | 92 | 187 | 0.330 |
| L3 d=1 / 2字 | 2 | 748 | **0.003**（雜訊海） |

兩條清晰分界線：
1. **target ≥3 字** — 2 字 target 喺任何 level 都係 FP 源（撞日常字音概率太高）；
2. **fuzzy_dist=0 vs 1** — normalize 後全同（純懶音/文白/聲調差）precision 1.0，可以同 L1/L2 一齊自動替換；真係差一個音節（d=1）就只配做 LLM 候選。

## 兩層架構（最終建議）最終數

**AUTO tier**（L1 ∪ L2 ∪ L3-d0，≥3 字，直接替換，無 LLM）：
- recall 27/34 = 79.4%（high-conf）；applied 27 個全部正確，**0 harmful、0 ambiguous**
- 48 段入面 **37 段自動替換後逐字等同 A1 corrected_text**（改前只有 15 段無錯）
- 中咗：升制快車×4→星際快車(L1)、精算部説×5→精算暴雪(L1)、標之星河×5→錶之星河(L1)、好有心得×5→好友心得(L1)、有愛心得→友愛心得(L1)、沙田銀屏→沙田銀瓶(L1,補齊)、標誌星河(L2 聲調)、馬威有勢→馬位優勢(L2,補齊)、幸運有利×2→幸運有您(L3-d0, n/l)、大愛當→大外檔(L3-d0, ng-脫落+聲調,補齊)、沙田銀平→沙田銀瓶(L3-d0, eng/ing 文白,補齊)

**LLM tier**（L3-d1，≥3 字，候選交 LLM 判決）：
- 加埋 recall 30/34 = 88.2% high + 2/3 medium；新增中：內藍米字×2→內欄位置（米 mai vs 位 wai 差成個音節）、標之星我→錶之星河（我 ngo vs 河 ho）、包尾直路→包尾入直路（漏字 insert）、制快車→星際快車（吞音節 delete）
- 工作量：**279 個候選 / 35 段**（~5.8 個/段）；原始 precision 0.330 = LLM 每睇 3 個候選有 1 個真 — 完全係 LLM 判決可消化嘅信噪比（仲可以按 score/每 span top-k 再剪）

**剩低救唔到（4 high + 1 medium）**：
- M4/M3/M2 → 尾四/尾三/尾二：ASR 出咗拉丁字，無粵拼 → **語音匹配結構性盲點**。建議加一條 deterministic pre-rule（`M([2-9])` → 尾X）喺語音匹配之前跑，呢 3 個即刻救埋。
- 尾指→尾二、電流→殿後：target 得 2 字，被 length gate 犧牲（2 字 d=1 precision 0.003，開閘要 748 FP 陪葬 — 唔值）。2 字術語要靠句法context或 LLM 全文 review，唔關語音索引事。

## 自動替換政策細節（JSON `auto_replace_policy_variants_GS`）

- minlen=2 時 L1 都會出事：seg3「標誌」→「飈誌」(L1 exact) 仲會霸住個 span，令正確嘅「標誌星河→錶之星河」(L2) 冇得改 — *longest-span-first* 可救部分，但**直接 minlen=3 gate 將成個問題消滅**（兩種 policy 都變 0 harmful）。
- 同 span 同 level 多名撞（ambiguity）喺 AUTO tier = 0 次；L3 全開先有 47-50 次 → 又一個唔好自動替換 L3 嘅理由。

## Caveats（誠實聲明）

1. **單一 clip**（108.6s、48 段、n=34 high-conf errors）。AUTO tier P=1.0 係本 clip 觀察值，唔係保證 — 「飈誌」證明 glossary 名同日常語 L1 級碰撞真實存在，換第二段評述可能出現 ≥3 字嘅碰撞。production 應保留 proofread 人工覆核 + 可一鍵還原。
2. **Supplement index 有溫和循環性**：9 個 terms 嚟自 A1 catalog 自身。production 對應物係賽日馬名 roster（賽事卡）+ 固定賽馬術語表（內欄位置/大外檔/尾二三四/殿後/馬位優勢/沙田銀瓶 全部係標準術語，靜態表可預建）— 情境合理，但實際補齊表嘅覆蓋率未驗證。
3. **ToJyutping 單讀音**：每字取 context 最佳讀音；多音字若 ASR 文同 glossary 名取唔同讀音會漏（本 clip 未見實例；「平 peng4/瓶 ping4」靠 eng/ing fuzzy 救返）。
4. **LLM 判決 tier 未實測**：本實驗只證明候選生成 recall 88-91%、volume 可控（279 個）、信噪比 1:3；LLM 判決本身嘅 accept/reject 準確度要後續實驗（建議直接用 production qwen3.5:35b-a3b 測）。
5. Low-confidence 6 項按 A1 scoring guidance 剔出 recall/FP 計算。
6. 效能：純 Python 全 clip 0.6s（1290 名索引 + 1074 候選）— production 可即時行，AUTO tier 零 LLM 成本。

## 對後續決策嘅意義

- **「自動替換 定 候選+LLM 判決」嘅答案係：兩樣都要，按 tier 分**。L1/L2/L3-d0(≥3字) 自動替換係 free win（本 clip 79.4% recall、零誤傷、零成本）；L3-d1 必須過 LLM。
- 語音匹配應該行喺 **ASR 之後、refine/MT 之前**（喺 content base 上修正，所有輸出語言受惠 — 對齊 A2 嘅 pipeline 位置結論）。
- 最大槓桿其實係**詞彙表覆蓋**：匹配器對 in-glossary 錯誤已經 100% recall，補齊賽日 roster + 術語表令整體 recall 由 70.6% → 91.2%。
