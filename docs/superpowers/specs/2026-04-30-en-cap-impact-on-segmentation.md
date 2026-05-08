# 純改 EN Segment Length Cap 對分句嘅實際影響

**問題:** 「如果我純粹改善 segment 嘅 length cap 嘅話，佢會唔會對分句都有分別？」
**答案:** **會有部分分別，但唔夠**。下面詳細拆解原因 + 應該配套改咩。

---

## 🔍 PART 1 — 你今日 split 邏輯點 work

### 你今日有兩個 split 機制

#### 機制 A — `split_segments()` (`backend/asr/segment_utils.py`)

```python
split_segments(segments, max_words=20, max_duration=10.0)
```

**參數 (來自 language_config en.json):**
- `max_words_per_segment` — 預設 **20 words**
- `max_segment_duration` — 預設 **10 sec**

**邏輯:**
1. 計每個 ASR segment 嘅 word count + duration
2. 如果超過 max → 計需要分幾多 chunks (`math.ceil`)
3. 每 chunk 大約 `target_chunk_size = word_count / num_chunks` words
4. **分嘅時候優先揾 sentence boundary** (`. ! ?`)
5. 揾到 → 喺 boundary 度切；揾唔到 → hard split @ word limit

**重點:** 呢個機制係 **word-count + duration based**，**完全冇睇 char count**

#### 機制 B — `merge_to_sentences()` (`backend/translation/sentence_pipeline.py`)

```python
merge_to_sentences(segments, max_gap_sec=1.5)
```

**邏輯:**
1. 將連續 ASR segments 用 pySBD 合併成完整句子（**先 merge 後 split**）
2. Time gap > 1.5s 強制斷句
3. 翻譯時用「整句」做 unit，唔再用 ASR fragment
4. 翻譯完之後 `redistribute_to_segments()` 按 EN word ratio 切返中文落原本 segment

**重點:** 呢個 pipeline 翻譯時用嘅係 **「sentence」單位** (可能多 ASR segment 合併)

---

## 🔬 PART 2 — 純加 EN char cap 會點？

### 假設你只係改 `split_segments()` 加 char cap

**新邏輯:**
```python
needs_word_split = word_count > max_words
needs_duration_split = duration > max_duration
needs_char_split = char_count > max_chars   # NEW
```

### 三個情境分析

#### 情境 1️⃣ — Whisper 出咗一個 80 char / 12 word / 6sec 嘅 segment

例: `"The government announced new measures to combat inflation today."` (62 char, 9 words)

| 配置 | needs_split? | 結果 |
|---|---|---|
| max_words=20, max_dur=10 (今日) | ❌ 唔分 | 1 segment, 62 char |
| max_words=20, max_dur=10, **max_chars=42** | ✅ 分 (62 > 42) | 2 segments |

**會有改善** — 純加 char cap 確實能分到。

#### 情境 2️⃣ — Whisper 出咗一個短 segment 但中文會 expand

例: `"Inflation."` (10 char, 1 word) → 中文「通貨膨脹。」(5 ZH char)

冇影響 — 本身就唔會超 cap。

#### 情境 3️⃣ — 一個 segment 入面有 sentence boundary 但 char count 中等

例: `"Yes. The government announced new tax cuts."` (44 char, 8 words, 1 sentence boundary)

| 配置 | 結果 |
|---|---|
| max_chars=42 | 分成 `"Yes."` + `"The government announced new tax cuts."` |

**會分得更好** — 因為今日嘅 logic 會喺超 word limit 時揾 sentence boundary，但 char cap 會更早觸發呢個邏輯。

---

## ⚠️ PART 3 — 純改 cap 嘅問題（dependency 喺 sentence pipeline）

### 致命問題：`merge_to_sentences()` 會 undo 你嘅分句

**Pipeline 流程:**

```
ASR (Whisper) →
split_segments() ← ⚠️ 你諗住喺呢度加 char cap
       ↓
[ASR fragment level] 假設你切到 segment ≤ 42 char ✅
       ↓
merge_to_sentences() ← ⚠️ 但呢度會將佢 merge 返做完整句!
       ↓
[Sentence level] 譯返一句完整 EN sentence (可能 80 char)
       ↓
LLM translate (1 整句 → 1 整句 ZH)
       ↓
redistribute_to_segments() ← 將 ZH 按比例切返落原 segment
       ↓
[Segment level] 每 segment ZH char count = 整句 ZH × proportion
```

**結果:**

如果原本一句完整英文係 80 char，你 split 成 2 個 40-char ASR segments：
- LLM 仍然見到完整 80 char 句去翻譯
- 譯出嚟可能 35 ZH char (整句)
- redistribute 切返 = 17 ZH + 18 ZH (per segment)
- ✅ 中文每 segment 短咗

**但係有 **3 個 catch:**

1. **Sentence pipeline 默認唔開** — 你今日嘅 `alignment_mode` 唔係 `"sentence"` 或 `"llm-markers"` 嘅話，`merge_to_sentences()` 唔會跑，咁切英文會直接影響 LLM 翻譯時嘅 context

2. **Redistribute 嘅切法係 char proportion + 標點 snap**：
   ```python
   target_end = char_offset + round(total_zh_chars * proportion)
   break_at = _find_break_point(zh_text, target_end)  # snap 落最近標點
   ```
   即係話 ZH 切點係**按 EN word 比例**而唔係按 ZH char limit。如果 ZH 譯文本身已經太長（例 50 char），切兩段每段仍然 25 char，**仍可能超 16/23 cap**

3. **冇 ZH char cap 反向約束 EN cap** — 你今日切 EN 嘅時候唔知 ZH 會幾長，cap 設 42 char EN 但 LLM 譯成 30 ZH，仍超 16 char limit

---

## 🎯 PART 4 — 結論：純改 cap 唔夠，要配套改 3 樣

### 必須配套改嘅 3 個地方

#### A. `split_segments()` 加 `max_chars` 參數 (你諗到嘅)

```python
# language_config/en.json
{
  "max_words_per_segment": 20,
  "max_segment_duration": 10.0,
  "max_chars_per_segment": 42  // NEW
}
```

效果：ASR fragment 唔再超過 42 char EN

#### B. `merge_to_sentences()` 加 length-aware split

呢個係**最重要嘅**。目前 pySBD 將 fragment merge 做完整句後，可能變 80-100 char 嘅長句，然後 LLM 譯成 30-40 ZH char，無論點 redistribute 都超標。

**新邏輯需求:**
```python
# 後處理：merged sentence 太長 → 用 sub-sentence 標點切分
# 例: ", and" / "; " / " — " 處切
LONG_SENTENCE_THRESHOLD = 60  # char
SUB_BREAKERS = [", and ", "; ", ", but ", ", or ", " — ", " — "]

def split_long_sentences(merged_sentences, threshold=60):
    """喺超長 merged sentence 嘅 sub-clause 處再切。"""
    result = []
    for sent in merged_sentences:
        if len(sent["text"]) <= threshold:
            result.append(sent)
            continue
        # try to split at sub-clause breaker
        parts = _split_at_breakers(sent["text"], SUB_BREAKERS)
        if len(parts) > 1:
            # re-distribute seg_indices proportionally
            result.extend(_split_merged(sent, parts))
        else:
            result.append(sent)  # cannot split, keep as-is
    return result
```

效果：LLM 收到嘅都係 ≤60 char EN 句，譯出嚟自然 ≤25-30 ZH char

#### C. `redistribute_to_segments()` 加 ZH char cap enforcement

目前 redistribute 純按 EN word proportion 切 ZH，唔睇 ZH 結果長度。要加：

```python
# 如果某 segment 分到嘅 ZH > zh_max_chars
# → 強制喺最近標點 split 多一個 segment
# 或者標 [long] flag 等用戶手動處理
```

---

## 📊 PART 5 — 4 種改法嘅 ROI 對比

| 改法 | 影響 | 邊際效益 | Effort |
|---|---|---|---|
| 1️⃣ **只改 split_segments() char cap** | ASR fragment 短咗 | ⚠️ 低 — 因為 sentence pipeline 會 undo | S |
| 2️⃣ + sentence pipeline 內加 sub-sentence split | LLM input 真係短咗 | ✅ **中-高** — 直接約束 ZH 長度 | M |
| 3️⃣ + redistribute ZH cap | 萬一 LLM 譯長咗都會強制切 | ✅ 高 — final guarantee | S |
| 4️⃣ 全部都改 | 完整解決 root cause | ✅ **最高** | M (combined) |

### 其他需要連帶調整嘅嘢

1. **Whisper 本身嘅 ASR 參數**：`max_new_tokens` 可以限制每個 segment 出嚟嘅 token 數（today profile 已支援呢個欄位）。但係 `max_new_tokens` 係 token 唔係 char，要 ratio 計（英文 ~1 token = 4 char，所以 42 char ≈ 10 tokens）。
   
2. **語言對嘅 ratio 要 hardcode**：英文 char count 同中文 char count 嘅 ratio 唔係 1:1 (Netflix 係 ~1.83-2.63:1)。`split_long_sentences()` threshold 應該按目標語言嘅 ZH cap 反推：
   - 目標 ZH 16 char → EN cap = 16 × 1.83 = ~29 char (Netflix Originals)
   - 目標 ZH 23 char → EN cap = 23 × 1.83 = ~42 char (Netflix 一般)
   - 目標 ZH 28 char → EN cap = 28 × 1.83 = ~51 char (TVB)

3. **LLM prompt 要加 "請保持每段中文 ≤ N 字" 嘅 instruction**：純技術 split 唔夠，prompt engineering 同步收緊先有 leverage。

---

## 🧠 PART 6 — 整體分句策略修訂建議

### 由 char-only thinking → multi-stage budget control

**Stage 1: ASR 階段 (Whisper)**
- 設 `max_new_tokens` 對應目標 ZH cap × 2.5 (token-to-char ratio adjusted)
- 例：ZH 16 char target → max_new_tokens = 16 × 2.5 = 40 tokens

**Stage 2: split_segments() ASR 後處理**
- 加 `max_chars_per_segment` (你最初嘅諗法)
- 但係呢個係 **safety net**，唔係主要 control point

**Stage 3: merge_to_sentences() (sentence pipeline)**
- 用 pySBD 先 merge 做完整句（保留翻譯 context）
- **新增 sub-sentence split**：超過 EN cap 嘅 merged sentence 喺 `,`/`;`/`—` 等 sub-clause boundary 強制切（呢個係 most impactful 改動）

**Stage 4: LLM translation prompt**
- System prompt 加：「請每句中文翻譯不超過 N 字」(N 取自 profile.zh_max_chars)
- 加 few-shot 例子展示 expected length

**Stage 5: redistribute_to_segments() ZH 後處理**
- 加 ZH char cap check: 如果某 segment 分到 > zh_max_chars，喺最近標點 split 多一段
- 或 fallback 為 `[long]` flag（你今日做緊）

---

## ✅ PART 7 — 直接答你嘅問題

> **「純粹改善 segment 嘅 length cap 嘅話，佢會唔會對分句都有分別？」**

**答案：會，但分別有限。**

### 點解只係「有限」？

1. ✅ **ASR fragment 階段** — 純改 cap 確實會切多啲 segment 出嚟
2. ❌ **Sentence pipeline 階段** — `merge_to_sentences()` 會將你嘅切割合併返做完整句，等於 undo 你嘅 cap
3. ❌ **LLM translation 階段** — LLM 唔知 ZH cap 限制，譯出嚟可能仍 >16 ZH char
4. ❌ **Redistribute 階段** — 按 EN word 比例切 ZH，冇 ZH char cap enforce

### 真正要連動修改嘅 4 件事

```
┌─────────────────────────────────────────────────────────────┐
│  TODO 1: split_segments() 加 max_chars     (你已諗到)        │
│  TODO 2: split_long_sentences() (NEW)      (核心修正)        │
│  TODO 3: LLM prompt 加 "≤ N char" 提示     (約束 output)     │
│  TODO 4: redistribute_to_segments() 加 cap (final guarantee) │
└─────────────────────────────────────────────────────────────┘
```

呢 4 個一齊改先係 **完整方案**。

---

## 🎯 對 Phase 1 嘅修訂結論

我建議將原本 P1.5 (Per-Language Line-Length Config) 由**單一 idea** 拆做以下 **4 個 sub-items**:

| 編號 | Title | Effort |
|---|---|---|
| **P1.5a** | `split_segments()` 加 `max_chars_per_segment` | S (~半日) |
| **P1.5b** | `merge_to_sentences()` 加 sub-sentence split (核心) | M (~2日) |
| **P1.5c** | LLM prompt 加 ZH char limit instruction | S (~半日) |
| **P1.5d** | `redistribute_to_segments()` 加 ZH cap enforcement | S (~半日) |

**總 effort:** 3-4 個工作日（vs 原本諗住 0.5 日）

但係 4 個一齊做嘅 **payoff 高 5-10x** — 因為直接解決你提出嘅 root cause（中文字幕變長問題）。

---

## 🔄 對其他 Phase 嘅 ripple effect

呢 4 個改完，會 **連動影響** 後續 Phase：

- **Phase 2 (廣東話 leakage)** — LLM input 短咗，prompt 跌返廣東話 leak 嘅機率細
- **Phase 3 (Min-cue duration)** — segment 多咗一倍，每個 cue 短咗，可能更多 cue 跌穿 833ms 下限，要 merge 返
- **Phase 5 (diarization)** — speaker turn 同 short segment 對得 better

---

## ❓ 我等你決定嘅事

1. **同意 split into 4 sub-items?** 你 OK 將原 P1.5 拆細嗎？
2. **EN cap 設幾多?** 28 (Netflix Originals) / 42 (Netflix 一般) / 50 (TVB)？或者三個 preset 都做？
3. **Sub-sentence split 嘅 breaker list** 由我設計定你提供？(例：`,`、`;`、`but`、`and` 等)
4. **LLM prompt 修改**: 你 prefer hard limit ("不可超過 16 字") 定 soft suggestion ("盡量保持 16 字內")？

呢啲決定完，我即刻開 v3.8 sprint plan。
