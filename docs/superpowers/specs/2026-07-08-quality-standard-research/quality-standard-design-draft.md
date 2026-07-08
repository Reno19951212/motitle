# 翻譯質量新標準 — 統一 rubric + benchmark harness 設計草稿（TASK D）

日期：2026-07-08 ｜ 性質：design research（證據來自 repo 現有 validation 實踐 + 對現有 registry 數據嘅純機械讀取；**本輪零新 LLM 實驗**）
Protos / 輸出：[protos/](protos/)（`scan_registry*.py`、`baseline_mechanical.py` + `baseline_mechanical_out.json` — 全部 read-only）

---

## 0. 一頁摘要

過去 3 個月嘅 validation trackers 其實已經隱性定義咗一套字幕翻譯質量維度（馬名/專名、位置術語、意思忠實、register、幻覺、口語殘留、格式穩定、詞彙表遵循、長度 cap、時間軸），但每輪 tracker 各自 ad-hoc 重新實現量度。本草稿將佢哋收斂成 **一個可重用嘅 12 維 rubric（per-cue + per-clip 兩級）**，加埋三樣新嘢：

1. **Reference-based mode** — 馬會 Test Footage 1/2 嘅**源片本身有專業燒錄中文字幕**（本輪抽 frame 實證，見 §2.1），可以 OCR 出「專業參考軌」同我哋 pipeline 輸出（registry `f66d9705f78d` / `28deab03a71c`，en→[en,zh]）做對照 — 開啟 name-match-vs-reference、judge 意思一致度、chrF 表面指標、cue 邊界對比四類新指標。
2. **Judge protocol** — 將 repo 已證實嘅 judge patterns（受限判決、3 票多數、SYSTEM 注入、A/B 位置對調、獨立第二 model、authority framing）正式化成 panel 規格 + 人手校準流程。
3. **Baseline run plan** — 以現有 8 條 racing/馬會檔立「今日質量線」；B0 機械層本輪已跑（§4.1，發現 en 軌 cap 檢查唔係 language-aware、`48c1657e7ec1` 有 1 條空 cue 等真問題）。

---

## 1. DIMENSIONS — 統一評分 rubric

### 1.1 過去 validation 實踐用過嘅維度（出處逐一列明）

| 維度（de-facto） | 曾用喺 | 量法（當時） |
|---|---|---|
| 馬名/專名保留（名詞被破壞） | [2026-06-13-written-quality-research/W2-audit.md](../2026-06-13-written-quality-research/W2-audit.md)（87.5%→100%）、[2026-06-13-written-refine-validation-tracker.md](../2026-06-13-written-refine-validation-tracker.md)（38/38） | string-presence 對 canonical roster（glossary target strip「 (XXX)」suffix） |
| 專名一致性（同一實體幾多種寫法） | [2026-06-03-racing-mt-prompt-optimization-tracker.md](../2026-06-03-racing-mt-prompt-optimization-tracker.md)（Amazing Partners 2 種→1 種） | 每實體 distinct surface forms 計數，1=完美 |
| 位置術語正確（尾X=倒數第N） | W2-audit（0/5→100%）、written-refine tracker（6/6） | 對 error catalog 逐項機械 string 檢查 |
| 賽馬語體濃度（術語 count） | racing MT tracker（58 vs 31 vs 4，全 282 段） | 術語詞表命中計數 |
| 意思忠實（meaning fidelity / 幻覺誤譯） | [2026-06-04-yue-written-register-asr-base-validation-tracker.md](../2026-06-04-yue-written-register-asr-base-validation-tracker.md)（意思錯誤 window 77%→33%）、written-quality C-synthesis（class2 0/9→6/9） | LLM judge：8 秒 time-window head-to-head + 有冇意思錯誤，A/B 對調 + 獨立第二 judge |
| register / 語體（書面 vs 口語） | [2026-05-31-v6-written-register-validation-tracker.md](../2026-05-31-v6-written-register-validation-tracker.md)（marker 16.63→0.13/100 字，門檻 ≤2.0） | 口語 marker 字符率（`_MARKERS` 集，見 `backend/scripts/crosslang_prototype/diag_yue_written_vs_direct.py:54`） |
| register drift（AI 編輯後語體漂移） | [2026-06-10-proofread-ai-edit-validation-tracker.md](../2026-06-10-proofread-ai-edit-validation-tracker.md)（「精簡」書面→口語 drift） | 人手逐 case 評 ✅/⚠️/❌ |
| 幻覺 / 重複 loop / 空譯 | [2026-06-02-crosslang-routing-validation-tracker.md](../2026-06-02-crosslang-routing-validation-tracker.md)（dup=7 rep=0.172、police loop、Amara.org 前奏幻覺）、racing MT tracker（空譯 0） | dup n-gram 比率、連續相同 cue、空段率、`translation/post_processor.validate_batch`（>40 字 / zh>en×3 / ≥3 連續相同） |
| 完整性（silent no-op / 長度膨脹） | v6-written-register tracker（no-op <15%、長度比 0.8–1.3×、爆 >3.5×=0） | 機械長度比 |
| 格式穩定（N 進 N 出） | written-refine tracker（48進48出）、[2026-06-02-bilingual-shared-base-validation-tracker.md](../2026-06-02-bilingual-shared-base-validation-tracker.md)（1:1 grid） | cue count 前後相等 + aligned==base |
| 長度 cap / over-cap | [2026-04-30-validation-tracker.md](../2026-04-30-validation-tracker.md)（v3.8 line-wrap 11 項）、`post_processor.py`（flag `long` >28 字/行；`clause_split` cap 24） | 機械字數 |
| 詞彙表遵循 + false-injection | [2026-06-05-glossary-v2-validation-tracker.md](../2026-06-05-glossary-v2-validation-tracker.md)（follow-rate 43/43=100%、false-injection floor 0）、[2026-07-07-en-glossary-correction-validation-tracker.md](../2026-07-07-en-glossary-correction-validation-tracker.md)（AUTO 145 rewrites 0 FP、JUDGE recall 24%） | gold-label occurrence 對照 + guard 後 floor 計數 |
| 語音同音錯字（ASR 層） | [2026-06-13-phonetic-correction-validation-tracker.md](../2026-06-13-phonetic-correction-validation-tracker.md)（34/36=94.4% 修復、AUTO 零誤改） | error catalog recovered/missed/false_positive（[2026-06-13-lang-quality-research/00-CONTEXT.md](../2026-06-13-lang-quality-research/00-CONTEXT.md) 規則） |
| 時間軸 sanity | crosslang tracker（off-by-one/對齊）、`backend/segment_timing.py`（0.4s floor、永不重疊） | 機械：單調、無 overlap、min duration |

### 1.2 收斂後 rubric（12 維，per-cue → per-clip roll-up）

**量度方法分三級**：`M` = 機械（deterministic string/數值，零成本，每 clip 必跑）；`J` = LLM judge（受限判決 panel，§3）；`H` = 人手（gold label / final arbiter — Validation-First 規定 human 係 final arbiter，見 yue-written tracker caveat 3）。

| # | 維度 | 定義 | Per-cue 量法 | Per-clip roll-up | Scale | 級 |
|---|---|---|---|---|---|---|
| D1 | 專名準確 | glossary/roster 名喺輸出中 byte-verbatim 存在（strip「 (XXX)」；「」bracket-tolerant，見 en-glossary V6） | roster string-presence（base 命中 → 輸出必須含 canonical） | 保留率 % ＝ preserved/expected | %（gate =100%） | M |
| D2 | 專名一致性 | 同一實體全 clip 得一種寫法 | — （clip 級） | 每實體 distinct forms（1=完美）+ 有 drift 實體數 | count | M |
| D3 | 術語正確 | 領域術語（位置術語 尾X/埋邊/放頭/透出、`the map`→跑法部署 類）意思正確 | 對 per-domain error-catalog 項逐項 string check | good/bad 計數 → 正確率 % | %（racing catalog 已存在；新領域要先建 catalog） | M（catalog 建立係 H） |
| D4 | 意思忠實 | 輸出意思對 reference（源音/口語 base/專業字幕）無錯、無漏、無加料 | 8s time-window：judge 判「有/無意思錯誤」+ head-to-head（§3） | 意思錯誤 window 率 %；h2h win/tie/loss | %、W/T/L | J（+H 抽核） |
| D5 | 幻覺/加料 | 無中生有內容（含 Whisper 前奏幻覺、MT 自行補全 cut-off） | judge flag + 機械 proxy（`validate_batch`：>40字、zh>en×3、cut-off 補全 racing-prompt 規則） | 幻覺 cue 數（gate 0） | count | M+J |
| D6 | 重複/loop | dup n-gram、連續相同 cue | rep ratio、≥3 連續相同（`post_processor.validate_batch`） | dup cue 數（gate 0） | count | M |
| D7 | Register 語體 | 書面軌零口語 marker；口語軌係真口語；en/ja 軌零中文洩漏 | marker 字符率 /100 字（書面 gate ≤2.0，實踐上 ≈0；`_MARKERS` 集 `diag_yue_written_vs_direct.py:54`）；洩漏 = 非目標 script 字符率 | 全軌 marker rate | /100 字 | M |
| D8 | 完整性 | 無空譯、無 silent no-op、長度比正常 | empty check；no-op（輸入有 marker 但輸出 == 輸入）；len ratio | 空譯 0；no-op <15%；len 比 median 0.8–1.3×、>3.5× =0 | 各自 gate | M |
| D9 | 格式/結構 | N 進 N 出、aligned grid == base、JSON contract | cue count、`aligned_bilingual` 長度 == translations | 全部相等（gate） | pass/fail | M |
| D10 | 長度 cap | 行長合廣播規格 — **必須 language-aware**（本輪實證：zh cap 28 套落 en 軌會 96.6% 假陽性，§4.1） | zh/yue：>28 flag、>40 hard；en：>42（Netflix 慣例，v3.8 [2026-04-30-netflix-subtitle-research.md](../2026-04-30-netflix-subtitle-research.md) 已研究）+ 讀速 cps | over-cap 率 % | % | M |
| D11 | 詞彙表遵循 | applicable occurrence 全部 canonicalise；不 applicable 零誤套 | `output_lang_glossary.scan_track`（`backend/output_lang_glossary.py:752`，同 pipeline 共用 matching）fix/ok 計數；gold-label 對照 | follow-rate %（gate ≥85%，glossary-v2 實測 100%）；false-injection（gate 0） | % / count | M（gold 建立係 H） |
| D12 | 時間軸 | 單調、無 overlap、無 <0.4s 碎 cue、雙語 grid 對齊 | 機械 interval check（`segment_timing.py` invariants） | overlap 0、短 cue 計數 | count | M |

**Per-clip verdict**：先過 M gates（D1/D5/D6/D8/D9/D12 硬 gate + D7/D10/D11 門檻），再報 J 維度（D4 意思錯誤率 + h2h），最後 H 抽樣簽字。同 trackers 現行 ✅ Validated / ❌ Rejected / ⚠️ Partial 三態一致（CLAUDE.md Validation-First workflow 第 2 步）。

**Scale 慣例沿用 repo 現例**：% 率、good/bad 對 catalog、judge 1–5（adequacy/fluency，crosslang tracker）或 binary（有/無意思錯誤，yue-written tracker — **binary 更可靠**，1–5 喺非中文 candidate 上已知不可靠，見 crosslang tracker 已知限制）。

### 1.3 rubric 對 pipeline 軌種嘅適用矩陣

| 軌 | D1-D3 | D4 reference | D7 |
|---|---|---|---|
| yue passthrough（口語） | ✅（phonetic catalog） | 源音（人手/catalog） | marker 應高（口語真實性） |
| zh refine（書面） | ✅ | 口語 base 軌（已證可做 reference，yue-written tracker 方法） | marker ≤2.0 |
| zh MT（en→zh） | ✅ | en base 軌 + （有嘅話）專業字幕 | marker ≈0 + 粵語洩漏 0 |
| en MT / passthrough | ✅（en 大寫 canonical，en-glossary tracker） | zh↔en 對照 | 中文字符洩漏 0；**cap 用 en 閾值** |

---

## 2. REFERENCE-BASED MODE — 專業參考字幕對照

### 2.1 實證：參考軌真係存在

本輪由 `backend/data/users/627/uploads/f66d9705f78d.mp4`（馬會 Test Footage _ 1，103.8s）同 `28deab03a71c.mp4`（Test Footage _ 2，59.6s）抽 frame（ffmpeg，read-only）：**兩條源片都有專業燒錄繁中字幕**（例：10s frame「牠每次上陣都全力以赴…」；20s frame「這匹2歲賽駒現時的成熟程度如何?」）。同一影片我哋 pipeline 已有 en→[en,zh] 輸出（registry 29/21 cues，racing style + 賽馬 glossary `db323f9d`）。→ OCR 呢啲燒錄字幕就係「專業參考軌」，同我哋 zh 軌直接對照。

> 注意：`backend/data/renders/*.mp4` 係**我哋自己**燒錄嘅輸出（registry 現時 13 個 entry **零** render job 記錄 — 本輪實測 `"render"` 喺 registry.json 出現 0 次，protos/scan_entry_keys.py），對 reference mode 無用（文字直接喺 registry 有）。參考軌一定係 OCR **源片**嘅 broadcaster 字幕。

### 2.2 有咗 reference 之後開得到嘅指標

| 新指標 | 做法 | 已知限制 |
|---|---|---|
| **R1 name-match vs reference** | reference 軌行同一 `scan_track` matching（canonical roster）→ 對比我哋軌：兩邊都命中 canonical？專業字幕用邊個中文名？（可反過來**審計 glossary 本身** — 專業字幕嘅譯名先係 broadcast 正名） | OCR 錯字會 miss 名 → 要先量 OCR CER floor（人手核 20-30 cue） |
| **R2 意思一致度（judge）** | 完全重用 yue-written tracker 嘅 8s time-window 協議（`diag_yue_written_vs_direct.py`）：reference 做 ground truth、我哋軌做 candidate，judge 判「意思一致/唔一致 + 邊個更準」 | 專業字幕係**濃縮意譯**（廣播字幕慣例）— 「唔一致」未必=我哋錯，judge prompt 要明示「參考係濃縮版，判斷核心意思」 |
| **R3 表面指標 chrF / BLEU** | 對齊後 cue-pair 計 chrF（character n-gram — 中文免分詞，直接可用）；BLEU 需分詞 — **jieba 切繁體已喺 v3.8 validation 被 reject**（CLAUDE.md「已 reject 嘅方案」列表），如要 BLEU 用 character-level | **只可做 trend/迴歸指標，唔可以做絕對 gate**：字幕翻譯係 condensation+paraphrase，低 chrF ≠ 錯譯（例：正確意譯 vs 直譯 chrF 反而低）。用途 = 同一 clip 改 prompt 前後 delta，或 outlier cue 篩選（chrF 極低 cue 先送 judge/人手） |
| **R4 cue 邊界對比** | reference cue 邊界 vs 我哋 cue 邊界：cue 數、cue 時長分佈、boundary offset 分佈、讀速 cps 對比 | 專業字幕分段哲學唔同（人手 spotting）；呢個係「風格差距」指標多過「錯誤」指標 |

### 2.3 時間對齊（唔同分段點對上）

Reference 同我哋嘅 cue 分段一定唔一樣（專業 spotting vs Whisper 分句）。兩層對齊，各服務唔同指標：

1. **固定 time-window 對齊（repo 已證方法）** — 8 秒 window，兩邊各自將「cue 中點落喺 window 內」嘅文字 concat 成 window 文字（`diag_yue_written_vs_direct.py` 實作，39 windows/200 segs 規模已跑過）。**服務 R2 judge + R3 clip 級 chrF**。優點：唔使解 1:N/N:M 配對、對邊界漂移 robust；缺點：粒度粗。
2. **Interval-overlap 貪心配對** — 每條我方 cue 搵 temporal overlap 最大嘅 reference cue（IoU 或 overlap 秒數），overlap <30% 標 unmatched。**服務 R1 name-match（名喺邊條 cue 唔重要，clip 級滙總）+ R4 邊界統計**。1:N 情況（我哋一條 = 專業兩條）容許 merge 相鄰 reference cue 至 overlap 飽和。
3. 唔建議 DTW/複雜對齊 first pass — 兩層已覆蓋四類指標，複雜度換唔到準確度（Validation-First：先簡單方法出數，唔夠先升級）。

**OCR 質量前置 gate**：任何 reference 指標前，必須先出 OCR CER（人手核對 ≥20 cue 樣本）。CER 高過 ~5% 就要先修 OCR（frame 取樣頻率、字幕帶裁剪、去重），否則 R1/R3 數字係噪音。（OCR harness 屬 sibling task 範圍；本 rubric 只定 gate。）

---

## 3. JUDGE PROTOCOL — LLM 評審 panel 規格

### 3.1 Repo 已證 patterns（全部有實證出處，直接繼承）

| Pattern | 出處 | 規格 |
|---|---|---|
| **受限判決**（accept/reject only，禁自由改寫） | `backend/phonetic_correction.py:449-471`（判決 prompt 五重 guardrail）+ phonetic tracker 假設 3 | judge 輸出限純 JSON 單 verdict；「唔肯定 → reject/negative」明文 |
| **多數票** | `phonetic_correction.judge_tier`（`:551-601`）votes=3、need=2；2 字候選全票 | 3 runs 多數；高風險判決（改字）升全票 |
| **A/B 位置對調** | `diag_yue_written_vs_direct.py:109` `judge(swap=i%2)` | 對比類判決逐 window 對調 A/B 位，抵消位置偏好 |
| **獨立第二 judge model** | yue-written tracker（qwen3.6:27b 交叉重判，結果同 qwen3.5 一致先算 robust） | 關鍵結論（ship/no-ship）必須第二 model 覆核方向 |
| **self-judge bias 緩解** | written-quality C-synthesis §5（judge 同 refine 同一 model → 用 verbatim-copy 客觀錨 + baseline 校準 0/9） | candidate 生成 model == judge model 時，加客觀錨題 + 對已知 baseline 校準 |
| **authority framing** | en-glossary tracker V5（唔話俾 judge 知候選係官方馬名表 → recall 得 24%） | judge prompt 必須交代 context 權威性（「參考軌係專業廣播字幕」「候選名來自官方名冊」） |
| **judge 語言限制** | crosslang tracker 已知限制（中文 prompt judge 對 en/ja candidate 不可靠，會回 None/離譜分） | en/ja 軌意思判決要用對應語言 prompt 或只用機械 metric |
| **think:false 強制** | written-quality 00-CONTEXT（唔熄 think → 90s+/call）；phonetic tracker 假設 5（think=False 48 段 13.2s） | 所有 judge call `think:false`（production `_call_ollama` 已默認，`ollama_engine.py:818-819`；**旁路 client 自己記住**） |

### 3.2 Panel 設計（production model qwen3.5:35b-a3b local）

- **判決單位**：D4 意思忠實 = 8s window（唔係 per-cue — 濃縮/合併令 per-cue 意思判決失焦，yue-written tracker 已用 window）；D5 幻覺 = per-cue binary；D11 llm_review = per-occurrence（現有 `glossary_review.py` 格局）。
- **票制**：每判決 3 votes（temp 0.3 stochastic，W2 audit 證 aggregate 穩定但單 run 搖擺）→ 多數。ship/no-ship 級結論再加獨立 model（qwen3.6:27b 或 Beta OpenRouter）方向覆核一次。
- **成本預算（要先實測，兩個歷史錨點差 50 倍）**：短 prompt + think:false ≈ **0.4–1s/call**（W6 refine 0.39-0.50s/段、phonetic judge 48 段 13.2s）；但 en-glossary V5 judge 實測 **~50s/call**（110 候選 ×3 votes = 4.7h — 長 context 判決）。→ **harness 第一步必須量 per-call 秒數**再定規模。粗算（取保守 50s/call）：29-cue clip ≈ 13 windows × 3 votes ≈ 39 calls ≈ **33 min/clip/軌**；若實測落 1s 級就係 **<1 min**。850-cue 長片只抽層化樣本（~40 windows）唔全量。
- **Judge prompt 骨架**（binary，非 1–5）：SYSTEM = 身份 + 判決規則 + authority framing（「B 係專業播出字幕，濃縮係正常，判核心意思」）+「唔肯定→有問題」+ 輸出純 JSON `{"verdict": "...", "reason": "..."}`（reason 限一句，供人手抽核用）；USER = window 時碼 + reference 文字 + candidate 文字（A/B 對調）。

### 3.3 人手校準（gold set）

Repo 已有先例：glossary-v2 嘅 **user-confirmed gold**（`docs/superpowers/validation/glossary-v2/gold_applicability_winningfactor.json`，43 occurrence）+ en-glossary V4 人手 ground truth（~35 個真聽錯）。程序：

1. 由 baseline 跑出嘅 windows 抽 **30–50 個**（層化：judge 話有錯 / 話無錯 / 唔肯定各佔），人手（用戶或母語者）標 binary gold。
2. 計 judge-human agreement；**目標 ≥85%**（同 glossary follow-rate gate 一致）。
3. <85% → 修 judge prompt（優先用 authority-framing lesson — V5 由 24% recall 起步就係 framing 問題），重驗**同一批** gold（en-glossary tracker 亦係咁重驗同一批 110 候選）。
4. Gold set 入 repo（`docs/superpowers/validation/quality-standard/`），成為之後每輪 benchmark 嘅固定校準錨 — judge prompt 任何改動都要對 gold 重跑 agreement。

---

## 4. BASELINE RUN PLAN — 用現有數據立「今日質量線」

### 4.1 B0 機械層（本輪已跑 ✅ — protos/baseline_mechanical.py，read-only）

8 條 racing/馬會檔（registry 現有 13 個 output_lang entry 中 style=racing 或馬會內容者）今日實測：

| file | 內容 | 軌 | cues | over28 | over40 | marker/100 | 空譯 | dup | overlap | glossary_changes |
|---|---|---|---|---|---|---|---|---|---|---|
| `f66d9705f78d` | 馬會 Test Footage 1（en→en,zh） | zh | 29 | 0 | 0 | 0.0 | 0 | 0 | 0 | 4 |
| | | en | 29 | **28** | 19 | 0.0 | 0 | 0 | | |
| `28deab03a71c` | 馬會 Test Footage 2（en→en,zh） | zh | 21 | 1 | 0 | 0.0 | 0 | 0 | 0 | 0 |
| | | en | 21 | **17** | 11 | 0.0 | 0 | 0 | | |
| `97b66062bfee` | 沙田賽前 previews（en→en,zh，851 cues） | zh | 851 | 39 (4.6%) | 4 | 0.02 | 0 | 0 | 0 | 159 |
| | | en | 851 | **701** | 451 | 0.0 | 0 | 0 | | |
| `09e0e3679f35` | 研究 clip 沙田銀瓶（yue 口語軌） | yue | 48 | 1 | 1 | 4.41 | 0 | 0 | 0 | 1 |
| `48c1657e7ec1` | 同片 zh 書面軌 | zh | 50 | 0 | 0 | 0.0 | **1**（idx 0, 0–1.16s 空） | 0 | 0 | 32 |
| `de5bd2b803bf` | 袁幸堯新聞（yue→zh） | zh | 49 | 0 | 0 | 0.0 | 0 | 0 | 0 | 0 |
| `fb76532ed5bc` | 賽後兩點晚（yue 口語軌，352） | yue | 352 | 3 | 0 | 2.12 | 0 | 0 | 0 | 79 |
| `ea49ef1969a9` | 3K5k4QXhzVA（yue→zh，1809） | zh | 1809 | 17 (0.9%) | 3 | 0.06 | 0 | 0 | 0 | 224 |

**B0 發現（真數據）**：
- zh 軌機械層今日已經好乾淨：over-cap ≤4.6%、marker ≈0、零 dup/overlap — **機械 gates 唔再係主戰場，D1-D4（名/術語/意思）先係**，同過去 trackers 結論一致。
- **en 軌 over28 高達 96.6%（TF1 28/29）係 cap 檢查唔 language-aware 嘅假陽性**，唔係質量問題（`post_processor.py` 嘅 28 字 cap 係 zh 語義）→ rubric D10 必須分語言閾值（en 用 42 字 + cps）。
- `48c1657e7ec1` idx0 空 cue（0–1.16s）係真缺陷樣本 — D8 gate 會捉到。
- 口語軌 marker rate 4.41（研究 clip）vs 2.12（賽後兩點晚）— 口語真實性維度喺 racing 評述類天然低過 talking-head（毛記 25.17，yue-written tracker），**per-genre baseline 唔同，gate 要對 clip 類型定**。

### 4.2 B1 — Reference-based（馬會 Test Footage 1+2，~163s 影片）

1. OCR 兩條**源片**燒錄字幕 → reference SRT（sibling OCR harness；~50 條專業 cue 估算自 cue 密度）。
2. 人手核 20-30 cue 出 OCR CER floor（gate <5%）。
3. Interval-overlap 配對 + 8s windows 對齊到我哋 zh 軌（29+21 cues）。
4. 出 R1 name-match（含 glossary 譯名 vs 專業譯名 audit）、R3 chrF、R4 邊界統計 — **全機械，零 LLM**。
5. 順手檢查其餘 YTDown racing 片（`97b66062bfee` 等）源片有無燒錄字幕，有就擴 reference set。

### 4.3 B2 — Judge 層（第一輪 LLM 開支，先小規模）

1. **先量 per-call 秒數**（§3.2 兩錨點差 50 倍）— 10 call 試跑定規模。
2. TF1+TF2 zh 軌 vs OCR reference：全部 windows（~20）× 3 votes 判意思一致 → **D4 今日數字**。
3. `48c1657e7ec1`（研究 clip zh 書面軌）vs 口語 base（`09e0e3679f35`）：重用 `diag_yue_written_vs_direct.py` 協議直接出 D4 — 呢條片 W-series 有晒 error catalog，可以驗 harness 對舊結論嘅重現性（**harness 自我校驗**：應重現 written-refine tracker 嘅位置 6/6、名詞 38/38）。
4. 30-50 window 人手 gold → judge agreement（§3.3）。

### 4.4 產出

一張「今日質量線」表（8 檔 × 12 維，M 全量 + J 抽樣 + reference 兩檔），存 `docs/superpowers/validation/quality-standard/baseline-2026-07.json` — 之後任何 ASR/MT/refiner 改動嘅 tracker 直接引呢條線做 before。

---

## 5. 誠實申報 / 開放問題

- 本輪係 design + 證據搜集：**B0 已跑（真數），B1/B2 係 plan 未跑**。
- Reference mode 目前只確認兩條馬會 Test Footage 有專業字幕（163s、50 cues 級）— 樣本細，夠做 harness 首驗，唔夠做穩定 benchmark；要問用戶攞更多帶專業字幕嘅源片。
- 專業字幕嘅濃縮/意譯風格 vs 我哋逐句 1:1 derive 係結構性差異 — R3/R4 數字第一輪會「難睇」，必須當 style-gap 報，唔好當 error gate。
- Judge 成本兩個歷史錨點（0.4s vs 50s/call）未解釋清楚差異來源（prompt 長度 + 判決複雜度嫌疑最大）— B2 第 1 步實測先。
- D3 術語 catalog 只有 racing 領域現成（W1/A1 catalog）；sportsnews/generic 要另建（H 成本）。
