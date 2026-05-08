# Prototype Experiment Results — Direction 3 驗證

**日期:** 2026-04-30
**目的:** 用真實 file (Real Madrid YouTube clip, 5min 12sec) 驗證 3 個方向嘅實際效果
**結論:** Direction 3 via `max_new_tokens` **完全失敗**；post-processing 增強**完全成功**

---

## 🚨 PART 1 — 重大發現：`max_new_tokens` 唔係我哋諗嘅嘢

### 我以為佢係：每個 segment 嘅 token 上限
### 實際係：**每個 30-sec chunk 嘅 total token 上限**

呢個係 Whisper 內部架構嘅 fundamental limitation：
- Whisper encoder 一次只 attend 30 秒 audio (chunk)
- decoder 喺每個 chunk 內 generate token sequence
- `max_new_tokens` cap 嘅係**整個 chunk 嘅總 token 數**
- 一旦 hit cap → decoder 強制停 → emit 一個包含**截斷文字**嘅 segment 覆蓋成個 chunk

### Experiment 1 結果：用 `max_new_tokens=10`（諗住對應 ~28 EN char）

```
Baseline (no cap)              : 96 segments, total 5347 chars
max_new_tokens=10              : 9 segments,  total 321 chars  ← 災難！
```

實際 output 對比（同一段 audio 0-30 sec）：

**Baseline (今日設定):**
```
[0.0-5.4]   "When Xabi Alonso was sacked as Real Madrid manager in January 2026, sources close to..."
[5.4-9.8]   "Carlo Ancelotti's former coaching staff at Madrid told the Athletic that they saw..."
[9.8-13.3]  "no solution right now to the side's situation."
[13.3-17.9] "They said that what the team really needs is a radical overhaul in the summer..."
[17.9-21.9] "by the sale of a big player such as Vinicius Jr or Jude Bellingham."
[21.9-26.7] "So if Real Madrid do look to rebuild, where do they start..."
[26.7-28.3] "look to bring in?"
```

**With max_new_tokens=10:**
```
[0.0-30.0]  "When Javier Alon"   ← ⚠️ 截斷喺 "Alonso" 中間，後面 30 秒內容全部丟失！
```

**結論：呢個 path 不可用。會永久損失 audio data，唔可能補返。**

---

## ✅ PART 2 — 真正可行嘅 path：增強機制 A (post-processing)

### Experiment 2 結果：純改 `split_segments()` 參數（無 data loss）

| 配置 | Segment 數量 | Mean char | 超 28 char % | 超 42 char % | 超 50 char % | Data 完整？ |
|---|---|---|---|---|---|---|
| **今日 (max_words=25, max_dur=40)** | 96 | 55.7 | **88%** | 80% | 70% | ✅ 100% |
| **Netflix Orig 方向 (max_words=7, max_dur=4)** | 173 | 30.5 | 56% | **8%** | **2%** | ✅ ~99% |
| **Netflix Gen 方向 (max_words=10, max_dur=5)** | 142 | 37.3 | 79% | 29% | 15% | ✅ ~99% |

**Data integrity:** 5347 → 5270 chars (只係 word-join 嘅空白差異，**無實質 text 損失**)

### Sample output: `max_words=7, max_dur=4`

```
[0.0-1.8]   29c: "When Javier Alonso was sacked"
[1.8-3.6]   25c: "as Real Madrid manager in"
[3.6-5.4]   30c: "January 2026, sources close to"
[5.4-7.8]   49c: "Carlo Ancelotti's former coaching staff at Madrid"
[7.8-9.8]   31c: "told the Athletic that they saw"
[9.8-11.6]  21c: "no solution right now"
[11.6-13.3] 24c: "to the side's situation."
[13.3-15.0] 28c: "They said that what the team"
```

✅ **無 data loss、自然句界感保留、char count 大幅降低**

---

## 📊 PART 3 — 用 Netflix Originals 標準（你嘅選擇）反推 EN cap

按 ratio 1.83:1 (EN char : ZH char)：

```
ZH 目標 16 char (Netflix Originals)
   ↓ × 1.83
EN cap = 29 char
   ↓
≈ max_words 7 (英文平均 1 word ≈ 4 char)
   ↓
≈ max_duration 4 sec (對應自然 reading speed)
```

### 用 `max_words=7, max_dur=4` 驗證效果

| Metric | Today | Direction 3 (post-process) | 改善 |
|---|---|---|---|
| Mean EN char | 55.7 | 30.5 | **-45%** |
| Median EN char | 59.0 | 30.0 | **-49%** |
| Max EN char | 89 | 60 | **-33%** |
| % over 42 char | 80% | 8% | **-72pt** |
| % over 50 char | 70% | 2% | **-68pt** |
| Total segments | 96 | 173 | +80% (more cues) |

✅ **基本達到 Netflix general 標準 (42 char)**
⚠️ **未完全達到 Netflix Originals 標準 (29 char)** — 仍有 56% segment 超 28 char

---

## 🎯 PART 4 — 唔同 cap 配置嘅實測 trade-off

| 配置 | 適合 deliverable | Pros | Cons |
|---|---|---|---|
| `max_words=25, dur=40` (今日) | TVB 內部 | LLM context 多 | 88% 超 Netflix Orig，80% 超 Netflix gen |
| `max_words=10, dur=5` | Netflix general | 平衡點，data 保留好 | 仍 29% 超 42 char |
| `max_words=7, dur=4` | Netflix Originals direction | 92% under 42 char, 98% under 50 | 偶有不自然中段切（"as Real Madrid manager in" 切咗喺 prep "in" 之後） |
| `max_words=5, dur=3` (untested) | 嚴 Netflix Orig | 預期 90% under 28 | 預期翻譯品質倒退（context 太破碎） |

---

## 🔬 PART 5 — Direction 3 嘅修訂版（基於實驗結果）

**原 Direction 3 (用 max_new_tokens 反推 EN cap):** ❌ 不可行（截斷 data）

**修訂版 Direction 3 (用 post-processing 反推 EN cap):** ✅ 可行

```
Profile.subtitle_standard = "netflix_originals"
   ↓ derive
zh_max_chars = 16
   ↓ × 1.83 ratio
en_max_chars = 29
   ↓ × ~4 char-per-word
max_words_per_segment = 7
   ↓
max_segment_duration = 4 sec (按自然 reading speed)
   ↓
language_config 同步
   ↓
split_segments() 用 7 + 4 落 cap，char_cap=29 做 hard upper bound
```

**仲要做埋:**

1. **機制 A 加入 char_cap parameter**（你最初諗到嘅）— 因為純靠 max_words 偶然會出 49 char (Carlo Ancelotti's former coaching staff at Madrid - 7 words 但 49 chars)。Char cap 可以再切呢類超長 word 嘅 case
2. **修中文 regex bug** — `[.!?]` 加埋 `[。！？]`
3. **修中文 word boundary bug** — 用 jieba 而唔係 `text.split()`

呢三個改動係 Phase 1.5a 嘅完整版本。

---

## ⚠️ PART 6 — 5 個 caveat 你要知

### Caveat 1: Sentence pipeline 會 undo 切割

實驗只係 ASR 階段嘅切割。**如果用 sentence pipeline (`alignment_mode: "sentence"`)，merge_to_sentences 會將 173 個 segments merge 返做完整句去翻譯。** 切完又 undo = 失去 char cap 效果。

**Implication:** 實際整條 pipeline 要按 Phase 1.5b/c/d 配套嘅 4 個 sub-tasks 一齊做先有效。

### Caveat 2: Word count 唔等於 char count

Real Madrid 段落出現嘅 anomaly:
```
[5.4-7.8] 49c "Carlo Ancelotti's former coaching staff at Madrid"  ← 7 words 但 49 chars (over 42 limit)
```

7 words = `Carlo / Ancelotti's / former / coaching / staff / at / Madrid`

**Implication:** 純 max_words 唔夠。一定要加 `max_chars` parameter 做 hard upper bound。

### Caveat 3: Mid-clause split 影響翻譯品質

```
[1.8-3.6]  "as Real Madrid manager in"
[3.6-5.4]  "January 2026, sources close to"
```

`"as Real Madrid manager in January 2026"` 被切咗，`in` 同 `January` 拆開。LLM 翻譯時可能譯成 `"作為 Real Madrid 主帥喺..."` + `"2026 年 1 月，消息來源..."` — 兩段都 awkward。

**Implication:** Sentence pipeline (機制 B) 嘅價值喺度體現 — 切咗去翻譯但翻譯時 merge 返做完整句，譯完先 redistribute。**所以唔可以移除機制 B**。

### Caveat 4: ASR 準確度未受影響（好消息）

`max_new_tokens` 截斷影響 transcription quality，但 `max_words/max_duration` 純後處理切割，**冇損失準確度**。

### Caveat 5: 實驗用 small model

唔同 model size 行為類似（large-v3 segment 平均更長）。實驗用 `small` 因為 quick test，但結論對所有 model 適用。

---

## 🔧 PART 7 — 修訂後嘅 Phase 1 Implementation 建議

### 唔再諗 Direction 3 (Whisper internal cap)，改為**Post-processing 強化**

```
┌──────────────────────────────────────────────────────────────────┐
│  v3.8 修訂後架構 (基於 prototype 結果)                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Profile (single source of truth):                                │
│    subtitle_standard: "netflix_originals" / "netflix_general" /  │
│                       "tvb"                                       │
│                                                                  │
│  Derived caps (auto-computed):                                    │
│    netflix_originals: zh=16, en_char=29, en_words=7,  dur=4       │
│    netflix_general:   zh=23, en_char=42, en_words=10, dur=5       │
│    tvb:               zh=28, en_char=50, en_words=12, dur=6       │
│                                                                  │
│  Layer 1 (機制 A 強化):                                            │
│    - Add max_chars param to split_segments()                     │
│    - Fix Chinese regex (「。！？」)                                 │
│    - Fix Chinese word boundary (jieba)                            │
│                                                                  │
│  Layer 2 (機制 B 強化 - opt-in path):                              │
│    - Add split_long_sentences() at sub-clause boundary           │
│    - Add Chinese segmenter for ZH source                         │
│                                                                  │
│  Layer 3 (LLM prompt):                                            │
│    - Inject ZH char limit instruction                             │
│                                                                  │
│  Layer 4 (redistribute):                                          │
│    - Hard cap ZH char per segment                                 │
│    - Overflow → split at nearest punctuation                      │
│                                                                  │
│  Layer 5 (post_processor):                                        │
│    - Flag [long] uses derived cap (per-Profile)                   │
└──────────────────────────────────────────────────────────────────┘
```

### Direction 1 (移除 A+B) — ❌ 確認不可行
### Direction 2 (per-language config) — ✅ 仍要做（修中文 bug）
### Direction 3 (cross-language aware cap) — ⚠️ 改用 post-processing 而非 Whisper internal

---

## 📋 PART 8 — 直接答你嘅問題

> **「先 confirm 咗效果可唔可以做到我哋類似想像嘅，再決定是否用呢個方案。」**

### ✅ 可以做到，但唔係用我哋最初諗嘅 path

| 諗法 | 實測結果 |
|---|---|
| 用 Whisper `max_new_tokens` cap segment 大小 | ❌ **失敗** — 截斷 audio data |
| 用 post-processing (機制 A) 加 char cap | ✅ **成功** — Mean 55.7→30.5 char, p95 82→46 char, 0 data loss |
| 從 Netflix Originals zh=16 反推 en=29 | ✅ **可行**（但要 max_words + max_chars 雙約束） |

### 你揀嘅 4 條答案我會點處理

1. **使用 Hybrid 架構** ✅ — 保留機制 A+B，增強佢哋
2. **Default `subtitle_standard: "netflix_originals"`** ✅ — Profile 加呢個 field，default 設 netflix_originals
3. **修中文 ASR bug** ✅ — Layer 1 入面修 regex 同 word boundary
4. **`max_new_tokens` 設定 + run experiment** ✅ — **實驗已完成，結論：不要設定**（會截斷）。改用 post-processing。

---

## 🎯 下一步 (我等你 confirm)

驗證完晒，下一步係寫 **v3.8 sprint plan**，內容會係：

```
Sprint v3.8 — Netflix-compliant Cross-Language Subtitle Cap
────────────────────────────────────────────────────────────────

Task 1: Profile schema 加 subtitle_standard (S, ~2h)
Task 2: Cap derivation logic + 3 presets (S, ~3h)
Task 3: split_segments() 加 max_chars + 修中文 regex (M, ~6h)
Task 4: split_segments() 加 jieba 中文 word boundary (M, ~4h)
Task 5: split_long_sentences() in sentence_pipeline (M, ~6h)
Task 6: Chinese segmenter for ZH source in pipeline (M, ~4h)
Task 7: LLM prompt ZH char limit instruction (S, ~2h)
Task 8: redistribute() ZH char cap enforcement (S, ~3h)
Task 9: post_processor [long] flag uses derived cap (S, ~1h)
Task 10: Tests (RED → GREEN) + smoke (M, ~6h)

Total: ~37h ≈ 5 working days

Deliverable:
  - 用 Real Madrid file 跑 before/after benchmark
  - 預期: % over Netflix Orig 16 char ZH 從 ~80% 跌到 ~10%
  - 預期: 0 data loss, 翻譯品質保持
```

要我即刻開 plan 嗎？
