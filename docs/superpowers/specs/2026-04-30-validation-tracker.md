# Phase 1 — Validation-First Tracker

**模式:** 唔再寫 sprint plan。每個假設逐個驗證，confirm 之後先寫入 plan。
**日期:** 2026-04-30
**Status:** Validation in progress

---

## 📋 驗證 Checklist (按建議順序)

### ✅ V0 — 已驗證項目（前面 prototype 已 cover）

| # | 假設 | 驗證方法 | 結果 | Status |
|---|---|---|---|---|
| V0.1 | Whisper `max_new_tokens` 可以做 per-segment char cap | Real Madrid file 跑 cap=10 | ❌ 失敗 — 截斷 audio data 94% loss | Validated (rejected) |
| V0.2 | 純改 split_segments() 嘅 max_words/max_duration 可以無 data loss 切細 segment | Real Madrid file 跑 max_words=7, dur=4 | ✅ 96→173 seg, mean 55.7→30.5 char, 0 data loss | Validated (accepted) |
| V0.3 | 純 max_words 唔夠（要加 max_chars） | 觀察 7 words 49 char 嘅 case (Carlo Ancelotti's former coaching staff at Madrid) | ✅ Confirmed — 需要 char cap 做 hard upper bound | Validated |
| V0.4 | 切咗會引入 mid-clause split 影響翻譯 | 觀察「as Real Madrid manager in」/「January 2026」呢類 split | ✅ Confirmed — 所以機制 B 唔可移除 | Validated |

### 🔬 V1 — Critical Path 驗證（要做先決定 plan）

| # | 假設 | 點樣驗證 | Status |
|---|---|---|---|
| **V1.1** | EN-to-ZH char ratio 1.83:1 真係適用 | 用實際 RealMadrid 翻譯比較 EN segment char vs ZH segment char distribution | ⏳ 未做 |
| **V1.2** | 機制 B (sentence pipeline) 開住會 undo Layer 1 嘅切割 | 跑 file with `alignment_mode="sentence"`，量度 final ZH char 分佈 vs `alignment_mode=""` | ⏳ 未做 |
| **V1.3** | LLM prompt 加 ZH char limit instruction 真係有效 | 同一段英文，比較 with vs without "≤16字" instruction 嘅 ZH 輸出 | ⏳ 未做 |
| **V1.4** | redistribute() 會否 produce 超 cap 嘅 ZH segment | 用 sentence pipeline 跑 file，量度每個 redistribute 後 segment 嘅 ZH char | ⏳ 未做 |
| **V1.5** | 中文 ASR (zh.json config) 喺今日真係失效 | 揾或者整一個短中文 audio，跑 ASR + split_segments，觀察有冇切割 | ⏳ 未做 |

### 🧪 V2 — Implementation Detail 驗證（影響 plan 細節）

| # | 假設 | 點樣驗證 | Status |
|---|---|---|---|
| V2.1 | jieba 對中文 word boundary 切得乾淨 | 用 jieba 切 5-10 段中文 sample，肉眼判斷 | ⏳ 未做 |
| V2.2 | pkuseg 或其他中文 segmenter 適合 sentence-level boundary | 對比 pkuseg / jieba.cut / 純標點 split 三種方法 | ⏳ 未做 |
| V2.3 | `max_chars` 加入 split_segments() 之後唔會 break 現有 unit test | 跑 `pytest tests/test_segment_utils.py` | ⏳ 未做 |
| V2.4 | LLM (Ollama vs OpenRouter) 對 char limit instruction 嘅 follow-rate 唔同 | 同 prompt 餵 Ollama Qwen 同 OpenRouter Claude 比較 | ⏳ 未做 |
| V2.5 | `subtitle_standard` Profile field 加入後嘅 backward compat | 用舊 Profile JSON 跑 transcribe (default fallback) | ⏳ 未做 |

### 📐 V3 — Edge Case 驗證

| # | 假設 | 點樣驗證 | Status |
|---|---|---|---|
| V3.1 | 短於 833ms (Netflix min cue duration) 嘅 segment 數量 | 量度 max_words=7 後有幾多 segment 太短 | ⏳ 未做 |
| V3.2 | Whisper 出 single-word segment 嘅頻率 | 量度 RealMadrid file 後處理 word_count=1 嘅 segment % | ⏳ 未做 |
| V3.3 | 跨 1.5s 時間 gap 嘅 sentence pipeline 行為 | 揾或構造一個有長 silence 嘅 audio sample | ⏳ 未做 |
| V3.4 | sentence pipeline merge 後嘅 EN sentence 平均長度 | 用真 file 跑 merge_to_sentences，量度 sentence 長度分佈 | ⏳ 未做 |

---

## 🎯 我建議嘅驗證 sequence

按 **「最高 leverage / 最低成本」** 排序：

### 🔴 Phase 1 (Critical — 唔做唔可以決定方向) 

```
V1.1 → V1.2 → V1.4 → V1.3
```

**V1.1 (1.83 ratio 驗證) — 最重要**
- 點解：成個 cross-language cap derivation 嘅基礎假設
- 如果實際係 2.5:1 唔係 1.83:1，所有 cap 數字都要重新計
- Cost: 30 分鐘 (用現有 Real Madrid translations 直接量度)

**V1.2 (sentence pipeline 會否 undo 切割) — 第二重要**
- 點解：如果開咗 pipeline 會 undo，咁 Layer 1 等於白做，要直接落 Layer 2
- 影響整個 architecture 嘅 entry point
- Cost: 1-2 小時 (要 toggle alignment_mode 重跑翻譯)

**V1.4 (redistribute hard cap 驗證) — 第三**
- 點解：sentence pipeline 路徑入面，呢個係 final ZH cap enforcement，要量度 actual produce 幾長
- Cost: 30 分鐘 (用現有 translation 比較)

**V1.3 (LLM 跟 char limit instruction) — 第四**
- 點解：影響 Layer 3 嘅可行性
- 可能 LLM 根本唔聽 "≤16 字" 指令
- Cost: 1 小時 (寫 prompt 比較）

### 🟡 Phase 2 (Important — 影響 plan 細節)

```
V1.5 → V2.1/V2.2 (中文相關 — 如果 V1.5 confirmed bug 先做) → V3.4
```

### 🟢 Phase 3 (Nice-to-have — 開工先驗證)

```
V2.3, V2.4, V2.5, V3.1-3.3
```

---

## 🔄 工作流程

```
For each validation item:
   ↓
1. 我寫小型 prototype script
   ↓
2. 跑出量化結果
   ↓
3. 寫入呢個 doc 嘅 result column
   ↓
4. ✅ Confirmed → 加入 sprint plan
   ❌ Rejected → revise 方向
   ⚠️ Partial → 同你討論
   ↓
5. Commit 結果同 Plan update
   ↓
6. 下一個 validation
```

---

## 📊 驗證進度 Dashboard

```
V0 (前置):    ████████ 4/4 done
V1 (critical): ░░░░░░░░ 0/5 ← NEXT BATCH
V2 (detail):   ░░░░░░░░ 0/5
V3 (edge):     ░░░░░░░░ 0/4
─────────────────────────
Overall:       ████░░░░ 4/18 (22%)
```

---

## ❓ 我等你 confirm

1. **同意呢個 validation sequence 嗎？** 即 V1.1 → V1.2 → V1.4 → V1.3，仲未掂 V2/V3
2. **每個 V1 item 我跑完即 commit 同 update 呢個 doc，但唔即刻寫 plan**，要等全部 V1 done 先 review。OK 嗎？
3. **如果某個 V1 result 推翻之前嘅 finding（例如 ratio 唔係 1.83:1）**，你想:
   - (a) 即刻停低同我討論修正方向
   - (b) 我繼續所有 V1，最後一齊 review
4. **想唔想加其他 validation item？** 例如：
   - 「LLM 收到短 segment vs 長 sentence 嘅 翻譯品質差幾多」
   - 「Whisper 唔同 model size (small/medium/large) 出嚟嘅 segment 分佈」
   - 「VAD filter 開定關對 segment 切割嘅影響」

確認方向同範圍之後，我即刻開始 V1.1 (ratio 驗證)。

---

## V_R — 2026-05-01 Netflix Preset Parity Loop (5-round)

**目標：** 將 Netflix preset 做到 Broadcast Hybrid V2 嘅效果，確保 EN / ZH 都符合 Netflix Timed Text Style Guide 斷句策略。
**Stack：** mlx-whisper medium + OpenRouter Qwen3.5-35B-A3B + Hybrid V2（sentence pipeline + smart redistribute）+ smart-break v2（4e7594f）。
**Corpus：** Real Madrid 18-min file，82 EN segments, 79 non-empty ZH (avg 20.3c)。

### V_R1 — Granular max_words sweep × Netflix EN preset

| max_words | Segs | Avg c | Max c | Netflix-fit | hard-cut | title-pair split |
|---|---|---|---|---|---|---|
| 25 (現用) | 82 | 67.0 | 99 | 76.8% | 11.0% | 4 |
| 18 | 83 | 66.2 | 99 | 78.3% | 10.8% | 4 |
| 16 | 92 | 59.6 | 99 | 85.9% | 7 | 3 |
| 14 | 109 | 50.1 | 96 | 94.5% | 0.9% | 2 |
| **13** | **122** | **44.7** | **90** | **98.4%** | **0%** | **1** |
| 12 | 129 | 42.2 | 88 | 100% | 0% | 1 |
| 10 | 135 | 40.3 | 88 | 100% | 0% | 0 |

**結論：** ✅ Validated — `max_words=13` 係 sweet spot：0% hard-cut + 1 title-split + +49% segs growth。

### V_R2 — Hybrid V2 redistribute scaling

| | Segs | Cross-seg overlap | Empty | ZH avg/max |
|---|---|---|---|---|
| Baseline 82-seg | 82 | 0% | 3 | 20.3 / 37 |
| Resegmented 122-seg (max_words=13) | 122 | **0%** | **0** | **13.1 / 36** |

**結論：** ✅ Validated — Hybrid V2 redistribute 喺 finer EN 段上仍然 0% overlap，empty seg 由 3 → 0（更乾淨）。

### V_R3 + V_R3.5 — Netflix tight-cap ZH wrap

| Preset | Baseline 82-seg hc | Reseg 122-seg hc | Cap-aware redistribute (max_words=8, max_per_seg=24) |
|---|---|---|---|
| Broadcast (28/3) | 0% | 0% | 0% |
| **Netflix General (23/2)** | 3.8% | **1.6%** | 1.3% |
| Netflix Originals (16/2) | 29.1% | 18.0% | **13.3%** floor |

**結論：** ❌ Rejected for Netflix Originals — 16-char cap 對 natural broadcast ZH 翻譯太窄（中文翻譯 token density 唔夠每 16 字 1 個標點）。✅ Validated for Netflix General。

### V_R4 — Composite full-pipeline parity

| Config | EN hc | EN ts | ZH hc | Cross-seg overlap | Empty |
|---|---|---|---|---|---|
| C1 Broadcast 現用 | 0% | 0 | 0% | 0% | 3 |
| C2 Netflix 現用（無修） | 11.0% | 4 | 3.8% | 0% | 3 |
| **C3 Proposed (max_words=13 + smart-break v2 + Netflix General)** | **0%** | **1** | **1.6%** | **0%** | **0** |
| C4 Proposed × Broadcast | 0% | 0 | 0% | 0% | 0 |

**結論：** ✅ Validated — Proposed config 喺 Netflix General preset 上達到 Broadcast Hybrid V2 質素。Trade-off：+49% segments。

### V_R5 — Netflix sentence-break strategy compliance

| Language | Compliant ✅ | Neutral ○ | Bad ⚠ |
|---|---|---|---|
| EN multi-line breaks (47 total) | 31.9% (SOFT punct + connector front) | 48.9% (plain whitespace) | 19.1% (PREP front + 1 PROPER_NOUN_SPLIT) |
| ZH multi-line breaks (9 total) | 77.8% (SOFT punct + paren close) | 22.2% (mid-clause hard-cut) | 0% |

**結論：** ✅ Partial — ZH compliance 77.8% 已經 acceptable（剩低嘅 mid-clause cut 係 cap 限制下不可避免）。EN 19.1% PREP-front split 係下一輪 smart-break v3 改善方向（提升 preposition penalty）。

### 落實決策

- **Ship**: `backend/config/languages/en.json` `max_words_per_segment: 25 → 13`
- **Already shipped**: smart-break v2 (commit 4e7594f)
- **Recommend UI**: Netflix General 為標準預設、Netflix Originals 標「實驗性」
- **下一輪 candidate**: smart-break v3 提升 PREP penalty（解決 17% PREP-front split）

### 仍未驗證嘅 caveat

| 缺口 | 影響 |
|---|---|
| ~~真實 mlx-whisper re-run~~ | ✅ **2026-05-01 closed** — 跑 mlx-whisper medium 喺 51e573205941.mp4 (Real Madrid 18-min)，所有 8 項 metric 同 simulation 100% 完全一致（segments=122, avg=44.7c, max=90c, p95=82c, 2-line fit=98.4%, hard-cut=0%, title-split=1）。ASR runtime 20.3s。 |
| ~~Real Madrid 以外 corpus~~ | ✅ **2026-05-01 closed** — V_R6 cross-corpus 詳情如下 |
| ~~中文 ASR (zh.json)~~ | ✅ **2026-05-01 closed** — V1.5 詳情如下 |

---

## V_R6 — 2026-05-01 Cross-corpus EN generalization

**Stack：** mlx-whisper medium, max_words=13, smart-break v2, Netflix EN preset (cap=42, max=2, tail=4)

| Corpus | Duration | Segs | Avg c | Max c | p95 | NTF-fit (≤88c) | Hard-cut | Title-pair split |
|---|---|---|---|---|---|---|---|---|
| Real Madrid (baseline, 體育長片) | 18 min | 122 | 44.7 | 90 | 82 | **98.4%** | 0% | 1 |
| Harry Kane post-match interview | 103s | 46 | 44.3 | 72 | 65 | **100.0%** | 0% | 0 |
| FIFA WC interview (Haris Zeb) | 179s | 81 | 41.8 | 67 | 61 | **100.0%** | 0% | 1 |
| JoqF7P7d23Q (短內容/低 speech) | 142s | 15 | 29.3 | 43 | 43 | **100.0%** | 0% | 0 |

**結論：** ✅ Validated — 所有 4 個 corpus 都跑出 0% hard-cut + ≥98.4% Netflix-fit + ≤1 title-pair split。Sweet spot `max_words=13` 配置具泛化性，唔係 dataset-specific。Title-pair split 1 個 (FIFA) 為 "Auckland City, New Zealand" — 公司/地區 名前嘅 SOFT punct 斷句，非 personal name split，可接受。

---

## V1.5 — 2026-05-01 ZH ASR config validation (closed)

**Hypothesis：** `zh.json` 嘅 `max_words_per_segment` 失效，因為 split_segments 用 `text.split()` 對中文返 1 element。

**Method：** 跑 mlx-whisper medium @ language="zh" 喺 audio_28d5bf78190a47a79d8f9a83229b6cba.wav (20.8 min Chinese broadcast)，比較 max_words 30 vs 10 + max_dur 8 vs 4。

| 配置 | Output segs |
|---|---|
| Current zh.json (max_words=30, max_dur=8) | 502 |
| Aggressive max_words=10, max_dur=8 | 503 (+1) |
| Tight max_dur=4, max_words=30 | 504 (+2) |

**ZH segment 分佈（685 segs）：** avg 6.8c, median 6c, max 112c, p95 13c
- 90.0% (452/502) segments have `word_count==1` (Whisper 出 ZH 無 whitespace)
- 10.0% segments have word_count > 1 — 因為英文 code-switch ("Trump", "iPhone" 等)

**Netflix wrap 嘅效果（直接 ZH ASR 路徑）：**

| Preset | Hard-cut |
|---|---|
| Netflix Originals (16/2) | **1.2%** ✅ |
| Netflix General (23/2) | **0.4%** ✅ |
| Broadcast (28/3) | **0.3%** ✅ |

**結論：** ⚠️ **Hypothesis partially refuted**
- `max_words_per_segment` 對 ZH **partially effective** (處理 code-switch)，唔係完全失效
- `max_segment_duration` **fully effective**
- 當前 zh.json (30/8) **無需更改**：Whisper 自然 ZH segmentation 已經夠短（avg 6.8c），所有 Netflix preset 都達 production 質素
- 唯一 1.2% Netflix Originals hard-cut 來自 Whisper 偶發 hallucination（30-sec, 112-char 段）— 唔係 config 問題

**對比 EN→ZH 翻譯路徑：** Native ZH ASR (avg 6.8c, NTF-Originals hc 1.2%) **遠優於** EN→ZH translate-then-redistribute (avg 13.1c, NTF-Originals hc 18.0%)。原因：Whisper 自然段邊界對齊 speaker pause，produce 短而 punchy 嘅 cue。

### Production 建議

- 中文輸出 video（中文 ASR + 唔翻譯）：直接用 Netflix Originals preset 已 production-ready
- 英文輸出 → 中文翻譯 video：仍需 max_words=13 + smart-break v2 + Netflix General（Originals 仍受 translation density 限制）

---

## V_R7 — 2026-05-01 Smart-break v3 + max_chars constraint (closed)

**Hypothesis B：** PREP penalty −40 喺 `_wrap_en` 可消除 R5 audit 顯示嘅 19.1% PREP-front 切位（"at Madrid" / "to be"）。

**Hypothesis D：** 加 `max_chars_per_segment` 喺 `split_segments`，set `en.json: 88`（Netflix EN budget），可消除 Whisper hallucination 出嘅 90+ char 段。ZH 不適用（無空格 → splitting 反而製造冇 punct 嘅 chunk，hard-cut 變多）。

### B Results — smart-break v3 (3-corpus aggregate, 90 multi-line breaks)

| Category | v2 | v3 | Δ |
|---|---|---|---|
| HARD | 0 (0%) | 0 (0%) | 0 |
| SOFT | 23 (25.6%) | 27 (30.0%) | +4 |
| CONN_FRONT | 11 (12.2%) | 12 (13.3%) | +1 |
| WS | 32 (35.6%) | 50 (55.6%) | +18 |
| **PREP_FRONT** | **23 (25.6%)** | **0 (0.0%)** | **−23** ✅ |
| PROPER_NOUN | 1 (1.1%) | 1 (1.1%) | 0 |
| Hard-cut | 0/249 | 0/249 | 0 |
| Title-pair split | 2 | 2 | 0 |
| **Netflix-compliant** | **37.8%** | **43.3%** | **+5.5%** |
| **Bad (PREP+PN)** | **26.7%** | **1.1%** | **−96%** ✅ |

✅ Validated — PREP-front 完全消除，無 hard-cut regression。

### D Results — max_chars EN-only

**EN (Real Madrid 122 segs):**
| max_chars | Segs | Max c | NTF-fit | hc | ts |
|---|---|---|---|---|---|
| None | 122 | 90 | 98.3% | 0 | 1 |
| **88** | **124** | **88** | **100%** | **0** | **1** |
| 70 | 134 | 68 | 100% | 0 | 0 |

**ZH (audio_28d5...wav 643 segs):** ❌ ZH 加 max_chars 反而**令 hard-cut 變差**（splitting hallucinations creates chunks 冇 internal punct）：
- max_chars=None: NTF-Originals 2.02% hc
- max_chars=49: 2.33% (worse)
- max_chars=32: 2.93% (worse)

**結論：** D 只加 EN，唔加 ZH。`split_segments` 內 `needs_char_split = max_chars > 0 AND text_len > max_chars AND word_count > 1`（最後一個 condition 確保唔對中文觸發）。

### V_R7 Final acceptance — Real ASR with B + D applied

| Corpus | Segs | Max c | NTF-fit | Hard-cut | PREP-front | Title-split |
|---|---|---|---|---|---|---|
| Real Madrid | 124 | 88 | **100%** | 0 | 0 | 1 |
| Harry Kane | 46 | 72 | **100%** | 0 | 0 | 0 |
| FIFA WC | 81 | 67 | **100%** | 0 | 0 | 1 |

**Aggregate:** 251 segs, 0% hard-cut, 0 PREP-front, 1 PROPER_NOUN-split (Auckland City|New Zealand — geographic compound, acceptable).

### A — UI hint deployed

`frontend/index.html` Profile editor `subtitle_standard` selector 下方加 `#ppsPresetHint` 小貼士：
- 中文 ASR + 唔翻譯 → Netflix Originals
- 英文 → 中文翻譯 → Netflix General + max_words=13
- 廣播電視 → Broadcast 28×3
