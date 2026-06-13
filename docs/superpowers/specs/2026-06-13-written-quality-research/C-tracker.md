# C — 中文書面語 Refiner Validation Tracker

**建構者**：C（總結＋抽稅）·  **日期**：2026-06-13
**範圍**：W1–W6 全部 claim 交叉核數 + Validation tracker（✅Validated / ❌Rejected / ⚠️Partial）
**Stack（全部 worker 一致，production 同款）**：本地 Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3、`think:false`；ASR n/a（refine over `corrected_spoken.json` 48 段高質口語 base）。
**Ground truth**：`W1-catalog.json`（48 段書面語 error catalog）。**Baseline**：`current_written.json`。

---

## 0. 交叉核數總結（我親手重算 vs worker 報數）

| 重算項目 | worker 報數 | 我重算 | 判定 |
|---|---|---|---|
| W1 tag 分佈（name_mangled/term_misread/meaning_error/halluc/register/dropped） | 5/5/10/5/1/1，17 段有錯 | **5/5/10/5/1/1，17 段** | ✅ 完全一致 |
| W1 name_mangled 段 | [3,11,15,33,44] | **[3,11,15,33,44]** | ✅ |
| W1 term_misread 段 | [6,7,8,16,19] | **[6,7,8,16,19]** | ✅ |
| Baseline 名詞保留率 | 35/40 = 0.875 | **35/40 = 0.875** | ✅ |
| Baseline 位置術語率 | 0/5 | **0/5** | ✅ |
| W6 run1 名詞保留率 | 40/40 = 1.0 | **40/40 = 1.0** | ✅ |
| W6 run2 名詞保留率 | 39/40 = 0.975 | **39/40 = 0.975** | ✅ |
| W6 位置術語率（兩 run） | 5/5 | **5/5（兩 run）** | ✅ |
| W6 class2 judge | 6/9 | **6/9（faithful=8,16,26,30,33,42）** | ✅ |
| W6 showcase 12 段字串 | — | **逐字對齊 raw run1 output** | ✅ 無捏造 |
| W6 baseline ideal_attainment | 33/48 | **33/48（scorer 邏輯核對 OK）** | ✅（但係寬鬆 proxy，見抽稅 §T1） |
| W3 C2 verbatim 照抄段 | 8 | **9（exact match）** | ⚠️ 細微差（見 §T2） |
| W5 V2 avg 耗時 | 2.97s/call | — | ⚠️ 同 W6 0.39–0.50s 矛盾（見 §T3） |

**總評**：所有 headline 機械指標（name rate / pos rate / tag 分佈 / judge 比數 / showcase 字串）**100% 重現、無誇大**。三項細微抽稅（ideal_attainment 係寬鬆 proxy、C2 照抄段數定義差 1、W5 耗時同 W6 矛盾）已逐項記錄，**不影響主結論**。

---

## 1. Validation Tracker

### ✅ Validated

| # | Claim | 證據（重算後） | 出處 |
|---|---|---|---|
| V1 | **Root cause = 逐段零上下文 + 零 roster**，rule 6（byte-for-byte 保留馬名）救唔到，因為 model 認唔出邊段係名 | Probe A：同 cue 同 prompt，plain refine 0/4 名保留 → user 注入 roster 4/4。唯一變量 = 話佢知邊啲 string 受保護 | W2 |
| V2 | **位置術語（尾二/尾三/尾四）係 DOMAIN-KNOWLEDGE 缺失，唔係 context 缺失** → 純 prompt 加一行 gloss 即可救，逐段孤立都得 | baseline 0/5 → 加 gloss 5/5，3 次穩定（W5）；純上下文無 gloss 只 1/5（W3 C1/C3）。我重算 W6 pos 5/5 兩 run | W2/W3/W5 |
| V3 | **名詞破壞（name_mangled）：上下文 + roster 注入有效**，純後處理（粵拼 matcher）無效 | W4：phonetic matcher 對 5 個 name_mangled 段 recall 0.40（且命中嗰啲係讀音殘留型）；P2 prompt 注入 name 35→40/40 = 100%、mangled 5/5。我重算 W6 run1 name 40/40 | W4 |
| V4 | **roster 注入必須落 SYSTEM prompt，唔可以落 USER turn** | W2 實測：USER turn → 48/48 段將 context block echo 入字幕（contract break）；SYSTEM → 0 echo。W4：SYSTEM 注入 echo 0/8 | W2/W4 |
| V5 | **純 prompt 重寫（W5 V2，鐵則前置）已 ship-able 大幅提升**：name 0.857→0.968、pos 0→100%、LLM-judge wrong 0.395→0.163 | W5 3 次平均，pos 3 次全 5/5 穩定 | W5 |
| V6 | **W6 最佳組合端到端**：name 100%（run2 97.5%）、pos 100%、class2 0/9→6/9、register leak 0、48 進 48 出 | 我親手由 raw run1/run2 重算全部數字，逐項對得返 | W6 |
| V7 | **±2 cue window 救到 prompt-alone 救唔到嘅 local meaning**（米字/透出/拆名），且唔同 roster 注入衝突 | W4：P2(SYSTEM)+window(USER) 同跑 8 段，over-insert 0、echo 0、leaked-neighbour 0 | W3/W4 |
| V8 | **production 速度可行**：W6 1 call/段、無 summary call、warm avg 0.39–0.50s/段、48 段 warm < 20s，遠低於 R5_QWEN3_TIMEOUT_SEC=900s | 我重算 W6 run1：seg0 冷啟 18.1s，warm 47 段 avg 0.50s、max 1.05s | W6 |

### ❌ Rejected（有證據）

| # | Claim | 為何 reject | 出處 |
|---|---|---|---|
| R1 | **C2 全文一次過餵 refiner** | register 由 ~80% 崩到 54%，批次令 model 偷懶照抄口語碎句（W3 報 8 段，我重算 exact-match 9 段，C3/C3G 只 2–3）。格式唔爆（4/4 run 48 進 48 出），**reject 喺 register 崩塌** | W3 |
| R2 | **phonetic post-check restore（粵拼 matcher 還原被改壞嘅名）** | name_mangled 係 LLM 語義改寫（獲好評/稍顯幸運）唔係同音錯字 → recall 0.40；放寬 align 閘 → 吞句誤傷（seg4/11/16 丟正確信息）。純後處理結構性兩難 | W4 |
| R3 | **C3 two-stage 全文摘要 → 逐段 refine** | 多 1 個 summary call（+8s）+ 摘要令 garbled cue（seg46）over-confident 自創（「精算暴雪超越星際快車」）。±2 window 已得 local-context 好處而無此風險，省一個 call | W3/W6 |

### ⚠️ Partial / 未解

| # | Claim | 限制 | 出處 |
|---|---|---|---|
| P1 | **意思忠實度（class2）封頂 ~6/9** | 仍有 seg3（name-span 邊界歧義）、seg11（源頭 garbled「埋邊有啲」+「第二位」被 over-apply 尾X 邏輯）、seg46（真 garbled）解唔到。當中 seg46 係 refiner 階段結構性無解 | W3/W5/W6 |
| P2 | **「埋邊／放頭／透出／做P」lexical 術語** | W2 漏咗只 gloss 尾X；W3/W6 補返一行 gloss 後 seg26/42 修好，但 seg11「埋邊有啲」因源頭歧義仍偏 | W3/W6 |
| P3 | **真 garbled cue（seg46「財寒…暴雪咗…做P繩」）** | refiner 階段**無解**（W2/W3/W5/W6 一致結論）。garbled-guard 除咗「織繩」幻覺、修好「做P→領放」，但「財寒/暴雪咗」仍 over-interpret。要上游 ASR 糾錯 | 全部 |
| P4 | **N=1 單 clip / 單領域** | 全部結論基於同一條 108.6s 沙田銀瓶 racing clip。體育新聞 / 通用領域（generic refiner prompt + 唔同 gloss）完全未測 | 全部 |
| P5 | **LLM judge self-judge bias** | class2 / register judge 同 refine 用同一隻 model。緩解：judge 對 current_written 校準到 0/9（同 W1 人手 catalog 一致），register 用客觀 verbatim-copy 錨。但仍建議人手覆核 | W3/W6 |

---

## 抽稅（誇大 / 定義含糊 — 踢爆）

### T1 ⚠️ `ideal_attainment 91.7–93.8%` 係寬鬆機械 proxy，唔係嚴格逐字對 ideal
W6 報「理想達成率 baseline 33/48 → W6 44–45/48」。我核 `w6_score.py`：clean 段嘅「attain」只檢查**名冇丟 + register 冇洩漏**，**唔檢查新意思偏移**。我抽查 31 個 clean 段嘅 W6 輸出：冇新 drift（名保住、register 書面），但 seg32「接近中間」→「位於中檔」（中間≠中檔，輕微語義偏）、seg23「開始上前」→「開始加速」係 paraphrase。呢啲喺 register-convert 容許範圍內、**唔係捏造**，但證明「91.7%」係寬鬆 proxy。**結論方向正確，但唔好當作「逐字 93.8% 達 ideal」嚟賣**——worker 自己 caveats 已坦白此點。**判定：方向可信，數字要降權理解。**

### T2 ⚠️ C2 verbatim 照抄段數：W3 報 8，我 exact-match 重算 9
差異源於定義：seg0「旺記舉例」、seg43「星際快車」等**短碎句本身已書面、無 marker 可轉**，喺好嘅輸出（C3/C3G）都係 byte-identical（C3=3、C3G=2），唔算「偷懶照抄」。W3 嘅「8」似乎剔走咗一個 trivial 短段。**方向絕對正確**（C2 照抄遠多過 C3/C3G），dealbreaker 成立。**判定：細微定義差，不影響 R1 reject。**

### T3 ⚠️ W5 報 V2 avg 2.97s/call vs W6 報同類 prompt warm 0.39–0.50s — 矛盾
W5 V2 prompt 同 W6 BASE 幾乎一樣（W6 = W5 V2 + 數行 gloss + window），但 W5 報 2.97s/call、W6 warm 報 0.39–0.50s。我重算 W6 run1：seg0 冷啟 18.1s、warm 47 段 avg **0.50s**、max 1.05s — **W6 數字可信**（直接由 per-seg sec 加總對得返 total 41.8s）。W5 嘅 2.97s 極可能係**量度污染**（3 變體 × 多 run 連跑、中間模型 reload / 冷啟未剔除）。**對 production 決策無影響**（兩個數都遠低於 900s budget），但**取信 W6 嘅 0.39–0.50s/段**做 production 估算基準，唔好用 W5 嘅 2.97s。**判定：W5 耗時數字不可靠，用 W6。**

### T4 ✅ name_mangled「resolved 5/5」冇雙重計數
我擔心 seg11 被「name_mangled resolved」同時又「meaning_error still_bad」雙重得益。核實：`tag_resolved` 對 name_mangled 只查名 verbatim 在場（seg11 幸運有您在場 → resolved），對 meaning_error/hallucination 用 judge（seg11 judge=false → still_bad）。**兩者邏輯分離、無互相 inflate**。seg11 正確噉同時係「名修返」+「意思仍未達 ideal」。**判定：誠實。**

### T5 ✅ W6 showcase 字串無捏造
12 個 showcase 段嘅 `improved` 字串**逐字**對得返 `w6_combined_out_run1.json` 嘅 raw output。冇美化、冇 cherry-pick 唔存在嘅輸出。**判定：誠實。**

---

## 一句總結

W1–W6 嘅**核心數字全部 reproduce、無誇大**；三項抽稅（ideal_attainment 係寬鬆 proxy、C2 照抄段定義差 1、W5 耗時數字污染）都係**邊緣量度問題，不動搖主結論**。最強 actionable evidence：**純 SYSTEM-prompt 改動（W5 V2 prompt + roster/gloss 注入）已可將 name 87.5%→100%、pos 0→100%、意思 wrong 減半，1 call/段、warm 0.4s/段**，production 完全可行。封頂位係 garbled cue（seg46）同源頭歧義（seg11），refiner 階段無解，要上游 ASR。所有結論受 **N=1 單 clip 單領域** 限制，落 production 前必須 P1.5 多 clip gating。
