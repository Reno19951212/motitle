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
