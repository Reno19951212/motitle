# Validation Tracker — 術語表近音別名 + 模糊比對（2026-07-14）

**Scope**：`en_correction.py` / `phonetic_correction.py` / `output_lang_glossary.py` — 全部喺 CLAUDE.md「Validation-First Mode」強制範圍內。

**Production stack 對齊**：ASR = mlx-whisper large-v3（未動）；候選生成 = 真實 shipped module（直接 import，零 reimplementation）；LLM judge = qwen3.5:35b-a3b。本輪**全部實驗零 LLM call**（純確定性量度），所以唔受本地 35B 長跑退化影響（見 [[local-35b-degeneration]]）。

---

## 語料（全部真嘢，read-only）

| 語料 | 來源 | 數量 |
|---|---|---|
| 英文 ASR base | `backend/data/registry.json` → `97b66062bfee`（Race-previews-Sha-Tin，851 cue）+ `f66d9705f78d`（馬會 Test Footage 1，29 cue） | **880 cue** |
| 粵語 ASR base（未糾錯） | `registry.json` → `09e0e3679f35.content_asr_segments`（source=yue, style=racing） | **48 cue** |
| 粵語控制組（已糾錯，做 FP 審計） | 另外 9 個 yue 源檔 | **3,059 cue** |
| 術語表 | `config/glossaries/db323f9d-…json`（賽馬，en→zh） | **1,354 條** |
| 行話 lexicon | `config/phonetic_lexicons/racing_terms.json` | 20 條 |

> **今日全 3 個術語表檔、1,375 條詞條，`target_aliases` 實際填咗值嘅係 0 條**（1 條有 key 但值係 `[]`）。任何別名功能唔配埋填寫閉環 = 出咗等於冇出。

---

## 結果

### ❌ A1 — 發音編碼索引（Double Metaphone / 手寫 phonetic key）做 candidate generator

**REJECTED。**

| 變體 | Candidate 總數 | 對比 baseline |
|---|---|---|
| 現有 char-Levenshtein | **171** | — |
| 手寫發音 key（d≤1） | **14,332** | **84×** |
| Double Metaphone（d≤1，pip `metaphone`） | **11,411** | **67×** |
| 發音 key + 長度閘（收噪音） | 1,422 | 8.3× |

噪音實例：`the` → `CHEAHA` ×353、`going to` → `KING ALLOY` ×20、`I think` → `LIGHTNING ACE` ×36。

**機械原因**：發音編碼**把長度訊號壓縮走咗**，而長度 band 正正係 char-Lev 免費攞到嘅剪枝力。加返長度閘去馴服噪音 → recall 反而跌到 baseline 之下。

**production 致命點**：`en_correction.MAX_JUDGE_CANDS = 200`。14,332 個 candidate 之中 **99% 會被靜默截走**，實際行為比 baseline 更差。

**新依賴判決**：`metaphone` / `jellyfish` 兩個都裝得到（非離線問題），但同零依賴嘅手寫 key **recall 完全一樣**、candidate 反而多 19% → **唔值得引入依賴**。

> 呢條 REJECT **唔依賴任何有爭議嘅指標** — candidate 爆炸同 200 上限截斷係直接量到嘅。

---

### ❌ A2 — 把別名餵入粵拼模糊索引（想連「未宣告嘅第三種聽錯」都捉埋）

**REJECTED。** Leave-one-out（宣告一個變體、隱藏其餘）：**0/5** 被救返。邊際 recall = 0。

**機械原因**（比原報告更硬嘅理由）：22 條聽錯之中 **14 條同正名嘅粵拼 fuzzy key 本身已經相同** — 別名入索引唔會新增任何**可達 span**。純加 candidate 成本，零收穫。

---

### ✅ A3 — `phonetic_correction` 由頭到尾冇讀過 `target_aliases`

**CONFIRMED（代碼證據）**：`grep -n "target_aliases\|alias" backend/phonetic_correction.py` → **0 hit**。`build_index`（:150-195）只讀 `e.get("target")` + lexicon terms，並且 `if not CJK_RUN.fullmatch(name): continue` 掉走所有非純 CJK 名。

**後果**：用戶今日喺術語表填中文近音別名 → **粵拼糾錯層完全睇唔到**。（`target_aliases` 只喺 `output_lang_glossary` 嘅 target-side exact substring 用到，而嗰層行喺 refine 之後，救唔到 base。）

---

### ⚠️ A4 — 宣告別名 = 確定性 fold-exact 前置改寫（P0 主機制）

**PARTIAL — 機制 VALIDATED，數字 TAUTOLOGICAL，必須連閘一齊出。**

| 量度 | 英文側（880 cue） | 中文側（48 cue） |
|---|---|---|
| 宣告變體命中 | 44/44 | 25/25 |
| **新增 candidate** | **0** | **0** |
| LLM judge 成本 | 0 | **152 → 4（−97%）** |
| 現有 ≥3 字閘 | 未動 | 未動（`MIN_TARGET_LEN=3` / `AUTO_FUZZY_MIN_LEN=4` byte-identical） |
| 已知回歸（整個過→靖哥哥） | — | 仍然被擋 |
| 真實控制語料 FP | — | **0 / 3,059 cue** |

**誠實聲明（必須讀）**：
- 上面嘅 recall 係 **TAUTOLOGICAL** — 實驗把 ground-truth 聽錯直接宣告做別名，所以命中率必然 100%。呢個實驗**只能證明**「宣告咗嘅別名一定會被確定性執行」，**證明唔到**「別名喺實戰會提升 recall」（嗰樣完全取決於有冇人事先填）。**唔可以引用做「recall 提升 48 點」。**
- 「0 FP on 3,059 cue」係**語料偏差**嘅結果，唔係設計嘅安全性。合成壓力測試：**5 句正常句子 corrupt 咗 4 句** — `呢條電流好強`→`呢條殿後好強`、`佢隻尾指受咗傷`→`佢隻尾二受咗傷`、`段處理流程`→`段柱理流程`（`段處` 係 `段處理` 嘅 substring，冇字界）、`標誌星河`→`錶之星河`。

**⇒ 必須連三重閘一齊出**：中文別名 ≥3 字 / Latin 字界 lookaround / 跟 `route_for_output` 適用性閘。

---

### 🔴 A5 — `deterministic_apply` 字界 bug（LIVE，出功能前必修）

**CONFIRMED（代碼證據）**：
- `output_lang_glossary.deterministic_apply:361` = 裸 `new_text = new_text.replace(alias, t)` — **冇字界、冇長度閘**。
- `_filter_target_side:718` 喺「canonical 逐字命中」嘅分支，把**未過濾嘅 alias list** 傳落去（`len(alias) > 2` 嘅閘只存在於 else 分支 :732）；`_get_aliases:289` 自己亦冇長度過濾。

**今日冇爆嘅唯一原因：全世界一個別名都冇填過。** 呢個功能一出就即刻咬人。同一 class 嘅 bug 之前喺 `wrap_matched_names` 已經以 HIGH 修過（`ACE` 咬入 `RACE`）。

---

### ⚠️ A6 — 「char-Lev 其實已經捉到，樽頸喺 AI judge」

**PARTIAL — 結論方向有獨立佐證，但本輪嘅量度手法有 circular ground truth，數字不可引用。**

- **不可引用**：本輪算出嘅 generator recall（baseline 37/44 = 84.1%）**係循環嘅** — ground-truth 清單本身就係從 char-Lev 自己嘅 110 個 candidate 入面揀出嚟嘅真陽性。用佢去量 char-Lev 等於自己考自己，而且**結構上冇可能**畀分數任何「char-Lev 從來冇提出過」嘅聽錯（即係「純發音相似、字元距離遠」嗰一類 — 正正係要答嘅問題）。
- **獨立佐證（可引用）**：2026-07-07 tracker 嘅生產實測 — JUDGE tier 對真聽錯 **accept 8/34 = 24%**，對噪音 **reject 71/72 = 99%**。呢個係人手標註嘅評估集，唔經本輪實驗，**唔循環**。⇒ judge 過分保守係實測事實。
- **診斷（早已記錄、未實施）**：judge prompt 冇同 model 講「呢啲 candidate 係權威馬名冊上嘅名」，於是佢當普通英文詞去判。

**⇒ 未決問題（P1 要答）**：
1. 「純發音相似、字元距離遠」嗰一類聽錯，喺真數據**究竟存唔存在**？→ 要一份**獨立 ground truth**（唔經 char-Lev 生成）。
2. Judge prompt 加返 roster framing 之後，accept 率由 24% 升到幾多？噪音 reject 率有冇跌？

---

### ⚠️ A7 — 別名只覆蓋術語表詞條 → 蓋唔到 64% 嘅粵語聽錯

25 條粵語聽錯之中，**16 條嘅正名根本唔係術語表詞條**：`殿後` / `尾二` / `內欄位置` / `大外檔` / `馬位優勢` / `沙田銀瓶` 等賽馬行話（住喺 `racing_terms.json`），加上普通詞（`姍姍來遲` / `推少步`）。

**⇒ 別名機制必須同時覆蓋行話 lexicon**（已經係用戶決定）。

**Shape 注意**：`racing_terms.json` 今日係**扁平字串陣列**（`"terms": ["內欄位置", "大外檔", …]`），加 `variants` 要做 backward-compatible loader（同時食 `str` 同 `{term, variants[]}`）。

---

## 待驗（P1，未做）

| # | 假設 | 手法 |
|---|---|---|
| B1 | qwen3.5:35b-a3b 做 judge 會唔會隨 call 數退化 | 連續 200 次 judge call，量 malformed / refusal 率 **vs call index** |
| B2 | 退化 mitigation：`num_predict` 封頂 / `format:json` / 每 K 次 unload 重載 / fresh session / OpenRouter fallback | 逐個 A/B |
| B3 | Judge prompt 加 roster framing → accept 率 | 用 2026-07-07 嘅**人手標註集**（34 真 / 72 噪音，非循環）量 accept + reject |
| B4 | 「純發音相似、字元距離遠」class 存唔存在 | 建**獨立 ground truth**（唔經 char-Lev），880 cue × 1,354 名 |

---

## 已 REJECT 清單（將來重提要先 cite 呢度）

- ❌ 發音編碼索引（Double Metaphone / 手寫 key）做 candidate generator — candidate 爆 67-84×，200 上限下 99% 靜默截走
- ❌ 新依賴 `metaphone` / `jellyfish` — 對零依賴手寫 key 零增益
- ❌ 別名餵入粵拼模糊索引 — leave-one-out 0/5，邊際 recall = 0
- ❌ 放寬 token-count（n±1 window）— 本語料零 recall 增益、candidate ×2.2

**繼承自舊 tracker（仍然有效）**：2 字中文名開閘（precision 0.000 / 748 FP）、單 token 英文 d=2、裸 AUTO 無常用詞降級（7% 誤判）、phonetic matcher 事後還原被 LLM 改走嘅名（recall 0.40 兼吞句）。

---

## Artifacts

- `scratchpad/glossary_fuzzy_proto.py` — 英文側 8 變體對比（import 真 `en_correction`）
- `scratchpad/phonetic_alias_proto.py` — 中文側 Z0/Z1/Z2（import 真 `phonetic_correction`）
- 兩份都經**獨立 agent 逐行反查 + 重跑**：數字 byte-identical 重現；英文側 headline framing 被推翻（circular GT），中文側 sound=true。
