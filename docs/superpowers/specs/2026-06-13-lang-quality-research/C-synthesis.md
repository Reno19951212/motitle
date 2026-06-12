# C — Synthesis：交叉核數結論 + 建議路線圖 + 未解問題

日期：2026-06-13 ｜ 前置：`C-validation-tracker.md`（逐假設判定 + 核數明細）

## 0. 一段講晒

現有 glossary stage 對同音錯字修復率 = **0/36**（A2 實跑證實，結構性：verbatim candidate gate 令 LLM 根本見唔到錯字）。最強可落地方案係 **B4 組合**（M-rule regex + 粵拼分層自動替換 + 受限 LLM 候選判決），單 clip 上口語 track 由 0 → **34/36 high（94.4%）**、只有 1 個輕微 FP、cue grid 不變、~8s 額外成本，而且修復會傳導落書面語軌（錯名殘留 18/36 → 0/36，仲消滅咗 refiner 對錯字嘅幻覺級聯）。所有數字經 C 獨立重算核實，無發現誇大；最大保留係 **N=1 clip** 同 **術語表循環性**（100% headline 係條件性 — 淨 glossary 約 79%）。

## 1. 交叉核數結果（詳見 tracker）

- **七份報告主數字全部對得上 underlying data**；C 用獨立 script 重算 B1 AUTO（27 TP/0 FP）、B3 三個 transcript（0/7/12 對 31）、B4 修復軌（34/36、1 FP、41/48）同書面語軌（18→0、6→25），全部 exact match。
- 發現 6 個小問題（tracker 有詳列），最值得記住嘅兩個：
  1. **「修復前 15/48」應為 17/48**（B1/B4 混用兩個定義）— 改善幅度被講大 2 段；
  2. **B4「34/34=100%」依賴 9 詞 supplement 術語表**，而呢 9 詞由測試 clip 自身嘅 catalog 衍生 — 淨 glossary 版估算 27/34（79%）。production 對應物（靜態賽馬術語表）合理但未喺新 clip 驗證。
- 跨實驗 denominator（36/34/31）全部 reconcile，方案排序自洽：B4 29/31 > B1 AUTO 27/34 > B2 V5 22/31 > B3 V3 12/31 > 現狀 0/36。

## 2. 建議路線圖

掛鈎位編號用 A2 嘅 H1–H6（A2-pipeline-audit.md §3）。

### P0 — 粵拼 AUTO tier + M-rule，掛 H2（base 糾正 stage）【最大效益/最快落地】

- **做乜**：新 pure module（`output_lang_phonetic_repair.py` 之類）：① regex pre-rule `M([2-9])→尾X`；② glossary（strip 編號）+ 靜態賽馬術語表 → ToJyutping 索引 → sliding n-gram 三級匹配 → **只自動替換 L1∪L2∪L3-d0、target≥3 字**（B1 AUTO tier 原樣）。純 Python、零 LLM、全 clip 0.7s。
- **掛邊度**：H2 — `_run_output_lang_bound_base`（app.py:593）base 砌好之後、clause_split/derive 之前修一次，所有輸出語言 + persist（content_asr_segments）+ glossary-reapply + 加第二語言全部自動繼承。同一函數插埋另外兩個 call site：`_produce_output_lang`（whisper-direct base）同 AI Rerun 單 cue 路（app.py:5908-5921）。
- **預期效果**：high-conf 同音錯誤 0 → **27/34（淨 glossary 23/34；連術語表 27/34）**，本 clip 0 誤傷；書面語軌錯名殘留同步大幅下降（B4 證實傳導），refiner 幻覺級聯（刪名/作賽果/作獎盃名）隨之消失。
- **風險**：真字 L1 碰撞（飈誌/標誌實證存在）— minlen≥3 gate 已擋本 clip 全部，但要 proofread 高亮 + 一鍵還原兜底；多 clip 未驗（見 P1.5）。
- **附帶 ops win（A2 觀察）**：pass track 而家 use_llm=True 係純開銷（~909s 換 0 修復 + 1 標點誤改）— 落 P0 時順手檢討。

### P1 — 受限 LLM 判決 tier（B4 Stage 2）+ 校對頁透出，掛 H2 同位 + H3/H6 同步

- **做乜**：L3-d1（≥3 字）候選交 qwen3.5 判決，**五重 guardrail 原樣 ship**：只准 accept/reject 候選、verbatim 正名保護、near-substitution onset/rim gate、3-run majority、音節對齊 tie-break。2 字候選要 3/3 全票或只標黃唔自動改。
- **預期效果**：27/34 → **34/34（horse+racing pool）**；effective 29/31；本 clip 代價 1 個輕微 FP + 30 LLM call ~7.3s。
- **同步改 H3/H6**：`scan_track`（output_lang_glossary.py:665）加 phonetic 候選 side，令校對頁同 pipeline 一致 — 自動改咗嘅高亮可還原、唔夠票嘅做建議畀人撳。
- **風險**：LLM judge run-to-run variance（seg17 FP 一 run 2/3 一 run 1/3）— 3-run vote + 2 字特別規則已係緩解；prompt 喺本 clip 迭代過 3 版，有過擬合風險。
- **明確唔做**（已 Rejected，將來 retry 要 cite 證據）：raw LLM rewrite（B3：改壞正確馬名）、thinking inline（150s+/cue）、L3 全開自動替換（P=0.114）、OpenRouter ASR（無 timestamp）。

### P1.5 — 多 clip Validation-First 驗證【gating item，唔係可選】

- CLAUDE.md 規定 + 三個實驗自己申報 N=1。攞 3-5 段唔同賽日/馬房/講者嘅評述（最好連一段非賽馬粵語內容做 negative control，量 false-positive rate），用 A1 方法建 mini-catalog，跑 P0+P1 完整鏈。
- **過唔到就唔好 ship P1**；P0 嘅 AUTO tier 如果喺 negative control 出現 ≥3 字真字碰撞，要考慮加 confidence score 或者降做建議模式。

### P2 — 周邊補強

1. **Refiner 名詞保留**（H4 位）：書面語軌正名出現只有 25/36 — gap 全部係 refiner 改寫不穩定（跌「錶」字、將「幸運有您」拆做「幸運，有您支持」、馬名拆引號）。做法：refiner prompt 加馬名 byte-for-byte 強化 + post-refine 用 B1 matcher 做 verify pass。獨立 work item，唔 block P0/P1。
2. **賽日 roster 自動偵測**（B2 prefilter 副產品）：V0 輸出 fuzzy-jyutping 掃描自動搵出 10/10 出賽馬（+1 FP）。用嚟縮 LLM tier 候選量同（將來）ASR prompt — **注意 AUTO tier 唔需要佢**（全索引照樣 P=1.0）。HKJC racecard scrape 係更乾淨來源但有 ToS/legal caveat，要過 legal 先。
3. **B2 V5 carry-patch 留後備**：ASR 層 biasing 有 register 改善係 post-ASR 冇嘅，但 cue grid break + monkeypatch + 2 次 ASR + 新錯 2-3 個 — 只有當 P0+P1 落地後仲有殘餘錯誤先值得重開（要解決 cue 再切問題）。
4. **退役馬 backfill**（B5）：glossary 1352 = 現役名單；舊片先需要。SCMP racing stats 係可行源（已驗 static HTML），同樣有 legal caveat。

## 3. 未解問題（誠實申報）

1. **Glossary 術語覆蓋缺口點補**：12 個 high 賽馬術語錯誤唔喺 glossary。本輪 supplement 9 詞係由測試 clip 答案衍生（循環）。正路：由 HKJC 官方賽事用語/評述慣用語建一張**靜態術語表**（內欄位置/大外檔/尾二三四/殿後/馬位優勢 + 各場獎盃名），獨立於任何測試 clip，然後喺 P1.5 新 clip 上量真實覆蓋率。**獎盃名係動態的**（沙田銀瓶呢類每場唔同）— 可能要 per-meeting 配置或者 racecard 抽取。呢條未答。
2. **無出馬表時點縮候選**：B2/B3 prefilter 喺本 clip 完美（10/10+1FP），但係單 clip、單講者、錄音質素好。嘈音訊/多場混剪下 threshold 點郁未知。Fallback 設計：prefilter 信心唔夠就全索引行 AUTO tier（已證唔需要 roster），LLM tier 候選爆量時先要 roster 剪。
3. **誤改風險點守（FP containment）**：本輪防線 = minlen≥3 + fuzzy_dist 分層 + 正名保護 + onset/rim gate + 3-run vote + 2 字 3/3 規則。未答：(a) 規模化之後 P=1.0 必然會跌 — 跌到幾多先要由「自動改」降級「建議」？建議定一個 SLO（例如人手抽查 FP rate >1% 即降級）；(b) proofread UI 點呈現「機改 vs 人改」audit trail；(c) per-file kill switch。
4. **homophone_other 類救唔到**（放既碼→放嘅馬、山山來遲→姍姍來遲）：lexicon 外通用粵語同音錯字，B4 僅有嘅 2 個 high miss。通用粵語 confusion lexicon（words.hk/rime-cantonese 反向索引）係可能方向，但候選空間大好多、FP 風險高好多 — **數據唔夠，未驗證，唔好預落 roadmap 承諾**。
5. **2 字術語**（尾指→尾二、電流→殿後）：B4 靠放寬 gate + 全票規則救到，但正係唯一 FP 來源。喺更多 clip 上呢個 trade-off 企唔企得住，P1.5 先知。
6. **跨語源外推**：全部證據係 yue 源。cmn 源（pypinyin 同構方案）理論可行但零實驗；en/ja 源唔關事。唔好假設 yue 數字可以外推。
7. **B5 web claims 未驗**：HKJC/SCMP scrape 可行性係 fetch 過但未做 bulk + legal 未過；TCPGen 等訓練路線 reject 理由（stack 唔夾）成立但冇實測。

## 4. 數據夠唔夠落判斷？

- **夠**：現狀 0/36 嘅結構性診斷（A2 源碼+實跑雙證）；粵拼分層 gate 嘅 precision cliff（1074 候選嘅分層統計）；raw LLM rewrite 嘅否決（B3 + 文獻同向）；錯字→書面語傳導機制（B4 before/after 全軌對照）。呢啲可以直接指導 spec。
- **唔夠**：所有 recall/FP 絕對數字（N=1 clip）；supplement 術語表真實覆蓋率；LLM judge 喺新 clip 嘅 variance；roster prefilter 喺嘈音訊嘅表現。**P0 可以憑現有證據進入 spec/plan；P1 ship 前必須過 P1.5。**
