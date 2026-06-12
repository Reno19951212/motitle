# C — lq-research Validation Tracker（總結＋交叉核數）

日期：2026-06-13 ｜ 核數者：C ｜ 對象：A1 / A2 / B1 / B2 / B3 / B4 / B5 全部 json+md
量尺：A1 error catalog（46 errors：high 36 / medium 4 / low 6；high = horse_name 24 + racing_term 10 + homophone_other 2；in_glossary high 24/36）

**核數方法**：所有主數字由 C 用獨立 script 對住 underlying JSON / transcript / diff 重算（唔係照抄各實驗自報數）。重算 script 邏輯：per-error「錯字消失 AND 正字（或 accept_also 變體）出現」、byte-identical 對 A1 corrected_text、difflib char-diff 抓 FP。説/說 字形歸一。

---

## 核數結論一覽（先講有冇報大數）

| 實驗 | 自報主數字 | C 獨立重算 | 判定 |
|---|---|---|---|
| A1 catalog 統計 | 46 (36H/4M/6L)、類型 25/13/4/4、in_glossary 25、33 段 | 完全一致 | ✅ 無誇大 |
| A2 baseline | 0/36 recovered（兩 variant）、12/48 段有候選、LLM 10 call、1 標點誤改 | 完全一致（deterministic 改 0 段 → 0 修復係恆真） | ✅ 無誇大（有一個 JSON 殘留 bug，見下） |
| B1 AUTO tier | 27/34、P=1.000、0 harmful | 重算：27 候選 → 27 TP / 0 FP；miss 名單逐項吻合（內藍米字×2、M4/M3/M2、尾指、標之星我） | ✅ 無誇大 |
| B2 V0–V5 | V5 22/31、提及 39/40、24 cue、0 regression | JSON 一致；transcript 逐 span probe 吻合（升制快車 4→0、精算部說 5→0、好有心得 5→0…殘留 M4/M3/M2/大愛當/沙田銀平屏/電流 + WKC junk ×2 全部如實申報）；V0==production（歸一後 0 mismatch）；mlx 源碼 transcribe.py:296/:534 機制 claim 屬實 | ✅ 無誇大 |
| B3 V1/V2/V3 | 0/31、7/31、12/31；V3 6 FP 含 翠紅→友愛心得 | 由 transcript 檔獨立重算：0/31、7/31、12/31 逐個一致；翠紅→友愛心得 喺 FP list 確認；V3T 1254.8s/8 段 ≈ 157s/cue 同「150–183s/cue」吻合 | ✅ 無誇大 |
| B4 組合 | 34/36 (94.4%)、29/31、34/34、1 FP、41/48 byte-identical；書面語 18/36→0/36 錯名、6/36→25/36 正名 | 全部由 b4_repaired.json / b4_refined_tracks.json 獨立重算：**逐個數字 exact match**；2 個 high miss 正係 放既碼＋山山來遲；唯一 FP 正係 seg17 面→尾；10 個書面語 example 引文逐字核實 | ✅ 無誇大 |
| B5 文獻 | mlx 冇 beam search、initial_prompt 係唯一 lever | 本地源碼核實：decoding.py raise NotImplementedError、transcribe.py 冇 carry_initial_prompt | ✅（web 部分無法本地核實，標 unverified） |

### 發現嘅小問題（全部唔影響結論方向）

1. **B1/B4 嘅「修復前 15/48 段無錯」其實係 17/48** — A1 catalog 自己 changed=False = 17（48−33 有錯段=15 係另一個定義：有 2 段只有 low-conf 無解錯誤、corrected==asr）。before 用 15、after 用 byte-identical 口徑（37/41）係兩個定義混用，將改善幅度講大咗 2 段。正確講法：**17/48 → 41/48**（B4）／**17/48 → 37/48**（B1 AUTO）。
2. **A2-baseline-run.json `recovery[0]` 有殘留 bug**：升制快車條目 `recovered:true` 同 `still_wrong:true` 並存（naive 全文 truth-presence 檢查中咗 seg43 嘅天然正確「星際快車」）。較後嘅 A2-pipeline-audit.json 已修正為 0/36，MD 跟 audit 數。headline 不受影響。
3. **B4 MD「修復 ~11s」**：timing JSON 係 0.7s（stage0/1）+ 7.3s（judge）= 8.0s。報大咗成本（保守方向，無害）。
4. **B2 MD 措辭**「V5 修復晒所有 in-glossary 馬名錯誤（…內欄位置×2…）」— 內欄位置係非 glossary 賽馬術語，唔應列喺 in-glossary 馬名清單下。馬名 claim 本身屬實（24/24 high horse rows recovered/acceptable，C 重算確認）。
5. **B4 pipeline 圖「Stage 2 (+7)」**包含咗嗰 1 個 FP（實際 = 6 真修 + 1 FP）；FP 喺正文有如實申報，但圖示易誤讀。
6. **B4 headline「34/34 = 100%」嘅 supplement 依賴要量化講明**（見 H7 caveat）：37 個 applied replacement 入面 **9 個靠 supplement 索引**（7 個 high 修復 + 1 medium + 嗰 1 個 FP），而 supplement 9 詞係由 A1 catalog 自身衍生。**淨 glossary 版 B4 估算 ≈ 27/34 (79%) high**。100% 係「假設有齊靜態賽馬術語表」嘅條件性數字。

### 跨實驗一致性（denominators 對得返）

- 36 high = 34 (horse+racing) + 2 homophone_other ✓
- 31 effective（B2/B3/B4）= 36 − 5 vacuous（標之星河×5，input 已係 accept_also 變體）✓
- B3 glossary ceiling 19/31 = A1 high in_glossary 24 − 5 vacuous ✓
- 方案排序 B4 (29/31) > B1 AUTO (27/34) > B2 V5 (22/31) > B3 V3 (12/31) > 現有 stage (0/36) 內部自洽 ✓
- B1 話 2 字 target 要 gate 走 vs B4 收返 尾指→尾二：唔係矛盾 — B4 放寬咗 gate 畀 2 字候選入 LLM tier（連 guardrail），代價正係嗰 1 個 FP（面三→尾三）— 兩邊都有如實記錄 ✓

---

## 假設逐項判定（Validation-First 格式）

### H1 — 現有 glossary stage 對同音錯字結構性救唔到 → ✅ Validated
- A2 實跑 production `glossary_stage`：deterministic **0/36**；LLM variant **0/36 + 1 標點誤改**（1508.8s，10 LLM call，2 超時）。
- 機制確證：四重 gate（routing → target verbatim `t in text` → 零候選唔叫 LLM → ≤2 字 guard）。同音錯字字面唔同 → 零候選 → LLM 一次都冇機會見到錯字段。seg44 雙重示範：有 verbatim 候選但對照表冇錯字對應條目，LLM 想救都冇權救。
- **附帶**：pass track use_llm=True 而家係純開銷（~909s LLM 換 0 修復）。

### H2 — 馬名錯誤主因係 gate 唔係 coverage → ✅ Validated
- A1：high-conf 馬名錯誤 **24/24 in_glossary=true**；本場 10 匹馬 100% 喺 glossary 有正典。
- CONTEXT.md 原假設「幸運有你/標之星河 MISSING」被推翻：glossary 正典係 幸運有**您** (E356)／**錶**之星河 (J343)，粵拼同 ASR span 完全相同（A1+B5 雙獨立發現）。
- 真 coverage 缺口只係**賽馬術語**（12 個 high in_glossary=false：內欄位置/尾二三四/大外檔/馬位優勢/沙田銀瓶…）— glossary 只收馬名。

### H3 — 粵拼語音匹配可以高 recall + 安全自動替換 → ✅ Validated（必須分層 gate）
- B1（C 獨立重算確認）：AUTO tier（L1∪L2∪L3-d0、target≥3 字）**27/34 recall、precision 1.000、0 harmful**，純 Python 0.6s 零 LLM。
- 反面同樣確證：**L3 全開自動替換 ❌**（precision 0.114，942/1074 候選係 FP）；**2 字 target ❌**（L3-d1/2字 precision 0.003）。飈誌 (biu1 zi3) 同「標誌」L1 級真字碰撞實證存在 — P=1.0 係本 clip 觀察值唔係保證。
- 匹配器對 in-glossary 錯誤 L1-3 recall 100%（24/24）— 索引層唔係瓶頸。

### H4 — ASR initial_prompt biasing 救到同音錯字 → ⚠️ Partial（機制有效，落地形態唔達標）
- 機制確證（源碼+實證雙確認，C 本地再核）：`condition_on_previous_text=False` 下 prompt 只入第一個 ~30s window（transcribe.py:296/:534）；V1–V3 修復 100% 集中 <29.4s。
- V5 一行 carry patch：**22/31、馬名提及 39/40、0 regression** — 有真實效果。
- 但對比 post-ASR 路線每項都輸：22/31 < B4 29/31；**cue grid 48→24（breaking）**；要 monkeypatch mlx_whisper；2-3 個新錯（300多米→三百零米、WKC junk）；5× 耗時 + 要兩次 ASR。
- 判定：**唔入主鏈**（B4 已採此結論）；保留做將來源頭級補充（佢有 register 改善係 post-ASR 冇嘅）。
- 附帶 ✅：**phonetic prefilter 自動搵 roster 成立** — V0 輸出 fuzzy-jyutping 對 1352 名掃描出 11 候選 = 10/10 真實出賽馬 + 1 FP（飈誌）；V3（prefilter）≥ V2（人手出馬表）。

### H5 — LLM 自由 rewrite（任何形態）修復同音錯字 → ❌ Rejected
- B3 V1（全文、無候選）：**0/31** — 用戶觀察「佢冇思考過成句句子」實證成立。
- B3 V3（per-cue+前後文+候選，最好 raw 形態）：12/31，但 **6 FP 含改壞正確馬名（翠紅→友愛心得）**＋distractor pickup（猶有心得×2）＋錯方向亂修（升製快車/沙田銀河）。廣播場景一單改壞正名已足以否決。
- 文獻同向（B5）：ASR-EC benchmark zero-shot LLM rewrite 令 CER 12.4%→20-34%。
- **裁決式用法除外**（見 H7 — LLM 只准 accept/reject 候選）。

### H6 — Thinking mode 修復 → ❌ Rejected（inline）／signal 存在
- V2T 全文 thinking：>33 分鐘 DNF。V3T per-cue：**150–183s/cue**（1254.8s/8 段，C 核實），7/8 段 8192 token 都唔夠收尾。
- Trace verdict（人手讀，JSON 有原文可覆核）：13 targeted 錯 8 全修 + 3 partial + 1 新幻覺（尾指→騎師名「威志」）— 質素高但偶發幻覺 + 250× 延遲。只可考慮 offline 人手觸發單段 rescue。

### H7 — 組合 pipeline（M-rule + 粵拼 AUTO + 受限 LLM 判決）基本清零 → ✅ Validated（條件性，N=1）
- B4（C 全部獨立重算 exact match）：口語 track **34/36 high (94.4%) / 29/31 effective / 34/34 horse+racing**、medium 2/4、**1 FP**（seg17 後面→後尾，2 字候選 2/3 票 borderline，傷害輕微）、41/48 byte-identical（修復前 17/48）。
- 五重 guardrail 實證有效：正名保護 block 咗 150 個候選（包括會打爛正名嘅「星際快→星際快車」）；near-substitution gate 擋走 LLM 3/3 想 accept 嘅「頂出→hau」FP。
- 成本：純 Python 0.7s + 30 judge call 7.3s，無 re-ASR，grid 不變。
- **條件**：(a) 9 詞 supplement 術語表由 A1 catalog 衍生（循環性）— 淨 glossary 估算 27/34；(b) Stage 2 prompt 喺本 clip 迭代 3 版（過擬合風險）；(c) N=1。

### H8 — 錯字會傳導落書面語軌＋修復會傳導返 → ✅ Validated
- 修復前（= 現 production 行為）：**18/36 錯名原樣殘留** + refiner 級聯災難（刪名：seg2/5/8 馬名消失；幻覺：seg18 無中生有「勝出/得第三」、seg37 自創「沙田銀盃」、seg8 殿後→「領先」意思反轉）。
- 修復後：**0/36 錯名殘留、25/36 正名出現**（C 重算 exact match）；殘餘 gap 全部係 refiner 自身改寫不穩定（跌字/拆名/意譯），唔係修復失敗 — 係獨立 work item。

### H9 — 無出馬表可以自動縮候選範圍 → ✅ Validated（N=1）
- B2 prefilter：11 候選 = 10/10 出賽馬 + 1 FP。B3 prefilter（不同 threshold）：19 候選含全部 6 個 truth 馬名。
- 注意：**B1 AUTO tier 根本唔需要 roster 縮窄**（對全 1290 名索引照樣 P=1.0）— roster 只係 LLM tier 候選量同 ASR prompt 先需要。

### H10 — 文獻方向（B5） → ⚠️ Partial（方向性參考）
- 本地可核實部分 ✅：mlx 冇 beam search、冇 carry_initial_prompt、faster-whisper hotwords 只係 prompt injection。
- 「jyutping 候選 + 受限 LLM rerank」architecture 同 B1/B4 實驗結果互相印證（PY-GEC/PMF-CEC/ASR-EC 反例）。
- HKJC racecard / SCMP backfill 等數據源 claim 屬 web research，未喺本輪實驗驗證，且有 ToS/legal caveat。

---

## 各實驗最終 verdict

| 實驗 | Verdict |
|---|---|
| A1 error catalog | ✅ 可靠量尺（46 errors，證據鏈完整可重跑） |
| A2 pipeline 審計 | ✅ Validated — 現 stage 0/36，結構性；H1-H6 hook 清單可信 |
| B1 粵拼匹配 | ✅ Validated — 兩層架構；AUTO tier production-ready 候選 |
| B2 ASR biasing | ⚠️ Partial — 機制真，落地唔達標，唔入主鏈；prefilter 副產品 ✅ |
| B3 LLM 修復 | ❌ raw rewrite Rejected；✅ 裁決式形態 + 候選清單有 signal（B4 採納） |
| B4 組合 | ✅ Promising — 本輪最強結果，待多 clip 驗證先可定案 |
| B5 文獻 | ⚠️ 方向性參考；本地可驗 claim 全中 |
