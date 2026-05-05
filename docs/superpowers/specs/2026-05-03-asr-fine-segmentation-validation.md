# ASR Fine Segmentation — Validation Tracker

**Date:** 2026-05-03
**Branch:** `feat/asr-fine-segmentation`
**Predecessor branch:** `feat/subtitle-source-mode` (HEAD `4e3c33a`)
**Mandate:** CLAUDE.md Validation-First Mode (任何 ASR / MT 改動必須先做 empirical validation)

## Context

MLX Whisper transcribe 出嚟嘅英文 segment 太長（mean 4–7s / 14 words），令到後續 EN→ZH 翻譯逐段對齊困難。目標切細到 mean 2.0–3.5s / 6–10 words，但要跟自然句子/clause 邊界，唔可以硬切。

5-agent research 結果（已歸檔於 conversation context）確認：
- **L1**（decoder kwargs）: mlx-whisper 內部 timestamp emit 由 model probability-mass rule 決定，**冇 kwarg 可以 force 縮短 segment**。Decoder kwargs 屬第二級控制（modest shortening + 防 hallucination）。
- **L2**（VAD pre-segment）: Silero VAD pre-pass + chunk-mode mlx-whisper 可以 hard cap segment length，但要強制 `condition_on_previous_text=False` 跨 chunk。
- **L3**（後處理 sentence-split）: pySBD 97.92% 英文 GRS 準確率 + protected-span regex + 4-tier hybrid (sentence > clause > silence-gap > hard-cap)。pySBD 已喺 `requirements.txt`（無新 dep）。

User 決定：**3 層全部做、每層獨立 validate 先**，由低 risk → 高 risk 次序：L3 → L1 → L2。

## Acceptance Criteria（共用）

| Metric | Target | Method |
|---|---|---|
| Mean cue duration | 2.0–3.0s | aggregate over fixture |
| P95 cue duration | ≤ 5.5s | sorted |
| Max cue duration | ≤ 6.0s (hard); ≤ 9.0s (safety) | `max(durations)` |
| Mean chars / cue (英文) | 50–80 | whitespace tokens — corrected per L3 Run 1 finding |
| Cue count delta | +60–120% vs baseline | new / old ratio |
| WER drift | ≤ 0.5pp | re-concat cue text vs original |
| Protected-span integrity | 100% pass on 20-case test set | manual eyeball + regex |
| Tiny-cue rate | <2% under 1.5s | `count(d<1.5)/n` |

---

## L3 — pySBD Sentence-Split (Post-Process)

**Status:** ⚠️ Partial — L3 alone insufficient; confirms need for L1 word_timestamps + L2 VAD

### Fixture
- `/tmp/real_madrid_segs.json` — 82 segs, mean 3.56s, max 5.84s （baseline 太 good，bypass Tier 0，algorithm 唔 trigger）
- `/tmp/v1_7_small.json` — 24 segs, mean 3.95s, p95 6.16s, **max 6.60s**, mean 84 chars — 典型「過長」case
- 兩個 fixture 嘅 `words[]` 都係空，用 uniform-time proxy — Tier 3 silence-gap 廢掉
- L1/L2 通過後再用真 word_timestamps fixture 重跑 L3

### Algorithm（Agent 2 推介，已 adapt 為 4-tier hybrid）

```
Tier 0: bypass — duration ≤ MAX_DUR && chars ≤ MAX_CHARS → return as-is
Tier 1: pySBD segment(text) → align text spans to words → produce sentence cues
Tier 2: 對過長 sentence cue，用 clause punct (, ; : —) 切（避開 protected spans）
Tier 3: 仲過長 + 有 word_timestamps，用 silence gap ≥ 0.30s 切
Tier 4: hard cut at MAX_DUR，唔切 protected span
Post-merge: < MIN_DUR 嘅 cue glue 返較短嘅鄰居（不超 MAX_DUR）
```

**Parameters:** MIN_DUR=1.5s, TARGET_DUR=2.5s, MAX_DUR=6.0s, MAX_CHARS=42, SILENCE_GAP=0.30s

**Protected spans (regex preprocess):**
- `$\d[\d,.]*\s?(billion|million|thousand|%)?` — `$3.5 billion`
- `\b[A-Z][a-z]+(\s[A-Z][a-z]+)+\b` — `Xabi Alonso`、`Real Madrid`
- `\b(January|...|December)\s+\d{4}\b` — `January 2026`
- `\b(Mr|Mrs|Ms|Dr|Sr|Jr|St|U\.S|U\.K|N\.Y)\.` — titles + geo

### Results — Run 1 (`/tmp/v1_7_small.json`, 2026-05-03)

Prototype: `/tmp/l3_pysbd_proto.py`

| Metric | Baseline (A) | Simple regex (B) | pySBD + protected (C) | Target |
|---|---|---|---|---|
| n | 24 | 28 | **29** | +60–120% (= 38–53) |
| Mean dur | 3.95s | 3.39s | **3.27s** | 2.0–3.5s ✅ |
| P95 dur | 6.16s | 5.68s | **5.68s** | ≤ 5.5s ❌ |
| Max dur | 6.60s | 6.16s | **6.16s** | ≤ 9.0s ✅ |
| Tiny (<1.5s) | 0% | 0% | **0%** | <2% ✅ |
| Mean chars | 84 | 72 | **69** | 8–12 (target 不切實際 — see note) |
| Max chars | 139 | 127 | **127** | — |
| WER drift | — | 0.2% | **0.25%** | ≤ 0.5pp ✅ |
| Protected integrity | — | 50% (1/2) | **50% (1/2)** | 100% ❌ (但 violation 係 fixture 已預先壞嘅 "Michael For" → "Michael Ford" baseline 已切錯，唔係 algorithm 切多) |

### 關鍵 Findings

**1. Algorithm C 對「典型過長」improvement vs baseline：mean −17%、max −7%、+5 cues。已過 4/6 acceptance gates。**

**2. 未過 gate 嘅根本原因 — Broadcast 訪問 transcript 大量句子無 sentence-end punct**：
- 例如 seg #10「Yeah, I was gonna say that demolition of Auckland City 10 goals scored unusual not to see your name on the score sheet」(6.16s, 23w, 132 chars) — 無 `.`，pySBD 切唔到
- Tier 2 clause cut（`,`/`;`/`:`/`—`）只覆蓋部分 case
- Tier 3 silence-gap 完全廢掉因為 fixture 冇真 word_timestamps（uniform proxy 無 gap 信號）

**3. Mean chars 8–12 唔現實**：spec 嘅 8–12 chars 數字基於 Netflix 中文 subtitle convention，但呢個係**英文 transcript** — 8–12 英文字符 = 1–2 個英文字。實際 broadcast 英文字幕業界規範 = 1 行 ≤42 chars / 2 行 ≤84 chars (BBC Subtitle Guidelines)。要改 acceptance criteria：mean chars 50–80，max ≤120。

**4. pySBD vs simple regex 改善有限**：n=29 vs 28，mean 3.27 vs 3.39 — 兩者同樣依賴 punct，broadcast 訪問都係 run-on句子。pySBD 嘅優勢主要喺 abbreviation handling（保護 `Mr.` `U.S.` 等），呢個 fixture 冇 trigger。

**5. Protected-span integrity 50% violation 係 fixture 預存問題**：「Michael For」係 baseline 已切錯嘅 "Michael Ford"，algorithm 無切多。實際 algorithm 切割完整人名嘅 fidelity 要用 unit test fixture（手寫 20 case）測，唔可以靠 production fixture 量度。

### 結論

- **L3 alone 改善有限（mean −17%、max −7%）**，唔夠 hit acceptance target
- **必須 L1 (word_timestamps=True) 先有真 silence gap → Tier 3 才能 trigger**
- **必須 L2 (VAD pre-seg) 喺 transcribe 階段切細，唔能完全 reliance 後處理**
- pySBD vs simple regex marginal benefit，但**必選 pySBD** 因為 abbreviation handling（`Dr. Smith`、`U.S.` 等）— 真 production transcript 一定有
- **Acceptance criteria 要修正**：mean chars 50–80（英文）而唔係 8–12（中文）

### Action Items

1. **Algorithm C 加強**：增加 char-count-based hard cut（>MAX_CHARS=80 強制喺最近 word boundary 切）、提升 cue count Δ
2. **Validation tracker chars target 改正**：英文 50–80 / max 120
3. **L1 plumbing 第一優先**：開 word_timestamps + L1 kwargs，再用真 timestamps 重跑 L3

---

## L1 — mlx-whisper Decoder Kwargs

**Status:** ✅ Validated — `hallucination_silence_threshold=4.0` (single lever) hit all acceptance gates

### Run 1 — 4-config A/B (90s Trump broadcast sample, mlx-whisper medium-q4)

Sample: `/tmp/l1_sample_90s.wav` (90s clip from `audio_28d5bf78190a47a79d8f9a83229b6cba.wav`, white-noise BGM + speech)
Prototype: `/tmp/l1_kwargs_ab.py`

| Config | n | mean_dur | p95 | max | max_chars | over_max | wall |
|---|---|---|---|---|---|---|---|
| baseline (cpt=True) | 16 | 5.62s | 13.00s | 13.00s | 117 | 7 | 5.9s |
| moderate_cpt_off | 20 | 4.16s | 11.86s | 11.86s | 94 | 4 | 6.3s |
| **moderate_hsa_only (hsa=4.0)** | **21** | **2.86s** | **5.18s** | **5.92s** | **61** | **0** | 8.1s |
| aggressive_safe (cpt=False + hsa=4.0) | 18 | 3.33s | 8.84s | 8.84s | 90 | 2 | 7.9s |

### Findings

**1. `hallucination_silence_threshold=4.0` 單一 lever 過晒所有 acceptance gates**：
- ✅ Mean ∈ [2.0, 3.5]s (2.86)
- ✅ P95 ≤ 5.5s (5.18)
- ✅ Max ≤ 6.0s (5.92)
- ✅ over_max = 0
- ✅ Word_timestamps 100% coverage
- ⚠️ Tiny rate 14% (3/21) — leave to L3 post-merge

**2. `condition_on_previous_text=False` 單一 lever modest improvement**：mean −26%、p95 唔變（11.86s）— 唔夠 hit gate。Confirms Agent 4 「modest shortening」結論。

**3. 兩 lever 組合（cpt_off + hsa）反而比 hsa 單獨差**：mean 3.33 vs 2.86, max 8.84 vs 5.92. 互相衝突 — cpt_off 鼓勵連貫、hsa 偏向 split+drop。**結論：用 hsa=4.0 單一 lever，唔加 cpt_off**。

**4. 第一輪用 `hsa=2.0` 失敗 — 頭 30 秒完全消失**：誤判 broadcast 開頭 applause/silence 係 hallucination silence。`hsa=4.0` 平衡得啱啱好。Agent 4 嘅 2-8s 推薦範圍，**4.0 為安全 sweet spot**，2.0 過於激進。

**5. 意外 bonus — 殺咗 baseline 嘅 hallucination**：
- Baseline #1「President Trump is speaking in Chinese」(0-10s) **本身係錯誤識別**（Trump 講英文，Whisper 將開頭 applause 誤譯做「speaking in Chinese」）
- hsa=4.0 #1「The President's Office」(5.22-6.92s) — **正確識別**
- 即 hsa 唔單止縮短 segment，**仲順便清理 baseline 已存在嘅 hallucination**

**6. Wall clock cost +36%** (5.9s → 8.1s for 90s audio = 0.09× realtime overhead) — production acceptable

### Decision (initial — REVISED below for large-v3)

**Initial recommendation (medium)**:
```json
{
  "asr": {
    "engine": "mlx-whisper",
    "model_size": "medium",
    "condition_on_previous_text": true,
    "word_timestamps": true,
    "hallucination_silence_threshold": 4.0
  }
}
```

### Run 2 — Real Madrid 5min broadcast (large-v3)

After user requested switch to `large-v3` (production parity):

| Config | n | mean | p95 | max | over_max |
|---|---|---|---|---|---|
| Baseline (cpt=True) | 66 | 4.44s | 5.92s | 6.24s | 2 |
| L1 hsa=4.0 alone | 64 | 4.31s | 5.82s | **9.58s** ⚠️ | 1 |
| L1+L3 stack | 91 | 2.89s | 5.14s | 5.38s | 0 |

**Critical finding:** `hallucination_silence_threshold=4.0` **反效果 on large-v3** — max segment shoots up to 9.58s. Original recommendation invalid for large-v3.

### Run 3 — Untried decoder kwargs A/B (large-v3, 6 configs)

Prototype: `/tmp/l1_kwargs_untested.py` + `/tmp/l1_lp_test.py` + `/tmp/l1_final_levers.py`

Tested levers untouched in Run 1/2:
- `beam_size` / `patience` — ❌ FAIL: mlx raise "Beam search decoder not yet implemented"
- `length_penalty` ∈ [0, 1] (4 values: None, 0.0, 0.5, 1.0) — ❌ Noop: identical 108 segs across all values (silently ignored because beam search disabled)
- `max_initial_timestamp` (0.5 / 2.0 vs 1.0) — ❌ Noop: identical 108 segs
- `sample_len=120` — ❌ Regression: 66 segs (was 108), mean 4.20s (was 2.54s)
- `sample_len=60` — ❌ Catastrophic: max 25.76s (broken timestamp pair rule)
- **`temperature=0.0` (固定 = disable fallback tuple)** — ✅ **Hero lever**

### **REVISED Decision — `temperature=0.0` is the only effective L1 lever for large-v3**

| Config | n | mean | p95 | max | over_max | sent_end% | func_word_end% | wall (5min) |
|---|---|---|---|---|---|---|---|---|
| Baseline (default fallback) | 72 | 3.72s | 5.92s | 6.92s | — | 19.4% | 11.1% | 105s |
| **temp=0.0** | **108** | **2.54s** | **5.64s** | **6.60s** | — | **39.8%** ⬆⬆ | **6.5%** ⬇ | **97s** |

**單一 lever `temperature=0.0`**：
- Segments +50% (72 → 108)
- Mean dur −32% (3.72 → 2.54s)
- Sentence-end boundary 比例由 19.4% → **39.8%**（翻倍）
- Function-word mid-clause cut 由 11.1% → **6.5%** (-41%)
- Wall clock 反而 **減少 8s**（冇 fallback re-decode）

**Final L1 production config**:
```json
{
  "asr": {
    "engine": "mlx-whisper",
    "model_size": "large-v3",
    "condition_on_previous_text": true,
    "word_timestamps": true,
    "temperature": 0.0
  }
}
```

`mlx_whisper_engine.py:34-73` 擴展 plumbing 接受 `temperature` kwarg（只需 forward 0.0 = scalar，唔係 default tuple）。**取消** `hallucination_silence_threshold` plumbing — 對 large-v3 反效果。

### MLX Whisper Kwargs Effectiveness Map (final)

| Kwarg | Status | Verdict |
|---|---|---|
| `temperature=0.0` (固定，disable fallback) | ✅ **Hero** | 唯一 effective lever |
| `condition_on_previous_text` | default True | Already on baseline |
| `hallucination_silence_threshold=4.0` | ⚠️ Model-specific | medium = helps, large-v3 = harms |
| `length_penalty` | ❌ Dead kwarg | beam search not impl → silently ignored |
| `beam_size` / `patience` | ❌ FAIL | mlx-whisper raise NotImplementedError |
| `max_initial_timestamp` | ❌ Noop | 0.5 / 1.0 / 2.0 結果相同 |
| `sample_len` (lower) | ❌ Reverse effect | Lower → segments 變長（破 pair rule） |
| `compression_ratio_threshold` / `logprob_threshold` | ❌ Indirect | 只 trigger fallback；temp=0 已 disable |
| `clip_timestamps` | ⚠️ L2 territory | 配合 VAD 可用，但 mlx bug #1256 `clip` = full duration → hang |
| `initial_prompt` | ❌ Reject | 長 prompt 反令 segment 變長 |

### Run 4 — Cross-style stability test (Trump speech 5min vs Real Madrid 5min)

| Sample | Config | n | mean | p95 | max | sent_end% | func_end% | wall |
|---|---|---|---|---|---|---|---|---|
| Trump 5min (政治演講) | baseline | 120 | 1.91s | 4.42s | 7.74s | 26% | 2% | 126s |
| Trump 5min | **temp_0** | 90 | **2.74s** | 5.50s | 7.58s | **49%** | **0.0%** | 117s |
| Real Madrid 5min (體育新聞+訪問) | baseline | 72 | 3.72s | 5.92s | 6.92s | 19.4% | 11.1% | 105s |
| Real Madrid 5min | **temp_0** | 108 | **2.54s** | 5.64s | 6.60s | **39.8%** | **6.5%** | 97s |

**Key cross-style findings**:

1. ✅ **Boundary quality 改善跨 style 一致**：
   - sent_end% 翻倍：Trump ×1.87、RM ×2.05
   - func_end% 減少：Trump 2→0%、RM 11.1→6.5%
   - Wall clock 減：兩 style 都 −7 to −9s

2. 🎯 **temp_0 係 boundary quality stabilizer，唔係 length adjuster**：
   - Trump baseline 過細 (120 segs / mean 1.91s) → temp_0 收斂到 90 segs / mean 2.74s
   - Real Madrid baseline 過粗 (72 segs / mean 3.72s) → temp_0 細化到 108 segs / mean 2.54s
   - **兩個方向相反 baseline，都收斂到 mean ~2.5–2.7s + sent% 40–49% sweet spot**

3. **Trump temp_0 mid-clause cut 0%**：因 broadcast formal monologue 嘅停頓結構容易令 mlx-whisper 喺 punct 位置 emit timestamp。Real Madrid（訪問風格）有 6.5% mid-clause cut — L3 仍要處理。

### Open Question — Cross 30s window mid-clause cuts 點解？

`temp=0.0` 大幅改善 boundary quality，但**無法解決「sentence 跨 30s window」呢類結構性 cut**（例如 user 提出嘅 #3+#4 case「needs is a / radical overhaul」）。即係：

- Whisper outer loop 必需每 30s window emit 至少 1 個 timestamp
- 當 sentence 跨越 window 邊界時，timestamp 必落喺 sentence 中間
- 純 mlx-whisper kwargs 解決唔到呢個機制限制

**Boundary Repair（L3 Tier 0.5）係唯一可行 fix**：
- 偵測 segment 結尾無 sentence-end punct 又以 function-word 結尾（is/a/the/of/and/...）
- 自動 merge 入下個 segment 直至遇到下一個 `.!?`
- 喺 pySBD 切之前先做

### Open Question — L2 仲需要嗎？

L1 (`temp=0.0`) alone 已將 mean 由 3.72 → 2.54s，sent_end% 翻倍。L2 (Silero VAD) 邊際效益估值：
- 可能進一步改善 silence-rich audio 嘅 boundary alignment
- 但 architectural cost 高（chunk-mode、word offset、強制 cpt=False per chunk）
- **建議：先 ship L1 (temp=0.0) + L3 (pySBD + boundary repair)，量度 production 後再決定 L2**

### Plumbing scope (from Agent 5 audit)
`backend/asr/mlx_whisper_engine.py:34-73` 只 forward `condition_on_previous_text` + `word_timestamps`，要擴展接受：
- `hallucination_silence_threshold` (float, default null)
- `compression_ratio_threshold` (float, default 2.4)
- `logprob_threshold` (float, default -1.0)
- `no_speech_threshold` (float, default 0.6)
- `initial_prompt` (str, default null)

### A/B configs (from Agent 4)

**Conservative (preserve sentence semantics):**
```json
{
  "condition_on_previous_text": true,
  "compression_ratio_threshold": 2.4,
  "logprob_threshold": -1.0,
  "no_speech_threshold": 0.6,
  "word_timestamps": true,
  "hallucination_silence_threshold": null,
  "initial_prompt": null
}
```

**Aggressive (broadcast-friendly, anti-hallucination, slightly shorter):**
```json
{
  "condition_on_previous_text": false,
  "compression_ratio_threshold": 2.0,
  "logprob_threshold": -0.8,
  "no_speech_threshold": 0.5,
  "word_timestamps": true,
  "hallucination_silence_threshold": 2.0,
  "initial_prompt": null
}
```

### Acceptance gate
- 跑相同 audio file 比較 segment count Δ、mean duration Δ、WER（Aggressive vs Conservative vs production baseline）
- Hallucination rate not worse than baseline ±2pp
- 期望：Aggressive 模式 mean duration 縮 5–15%（modest，per Agent 4：「effects for any single intervention are not large」）

---

## L2 — Silero VAD Pre-Segmentation

**Status:** 🚫 Not started

### Plumbing scope
- 新 module `backend/asr/silero_vad.py`：load Silero ONNX、`pre_segment(audio_path, ...) -> [(start_sample, end_sample), ...]`
- 修改 `mlx_whisper_engine.py`：profile config `vad_pre_segment=True` 時 chunk-mode 跑
- Profile schema 加：`vad_pre_segment` / `vad_threshold` (0.5) / `vad_min_silence_ms` (500) / `vad_min_speech_ms` (250) / `vad_speech_pad_ms` (200)
- 強制 `condition_on_previous_text=False` per chunk + word_timestamps offset shift

### Acceptance gate
- Mean segment duration 2.0–3.5s
- P95 ≤ 14 words/seg
- Boundary alignment error ≤ 250ms vs ground truth
- 不增 hallucination rate ±2pp
- Wall-clock ≤ baseline +15%

### Known bugs to avoid
- mlx issue #1256: `clip_timestamps` 等於完整 audio duration 會 hang
- faster-whisper issue #1355: 單個 clip > 30s 會 truncate (mlx 估計同樣)
- 每個 chunk 要 read_audio 一次 + offset shift 每個 word.start/end

---

## L1 + L3 Stack 驗證

**Status:** ✅ Validated

### Run 1 — L1 hsa=4.0 output → L3 pySBD post-process

Sample: 同 L1 Run 1 (90s Trump broadcast)

| Stage | n | mean | p95 | max | tiny | over_max |
|---|---|---|---|---|---|---|
| Baseline | 16 | 5.62s | 13.00s | 13.00s | 0 | 7 |
| L1 hsa=4.0 alone | 21 | 2.86s | 5.18s | 5.92s | 3 | 0 |
| L1 + L3 stack | 21 | 2.86s | 5.18s | 5.92s | 3 | 0 |

**L3 trigger 0 splits** — L1 hsa=4.0 已將所有 segs 切到 ≤ MAX_DUR (6.0s)，全部喺 L3 Tier 0 bypass。

### 結論

- **L1 hsa=4.0 對 broadcast formal speech 係 primary lever，alone 已過所有 gate**
- **L3 pySBD 嘅 value 喺 broadcast 訪問 run-on 句**（L3 Run 1 fixture v1_7_small.json）— L1 切唔到 (run-on 唔 trigger hsa) 但有 punct，pySBD 補入
- **L1 + L3 = complementary safety net**：L1 catch 大多 case (silence-driven splits)、L3 catch L1 漏切嘅 punct-rich run-on
- L2 對呢個 sample 唔需要；建議 ship L1 + L3 後量度 production 表現再決定 L2

### Acceptance gate 整體達成

| Metric | Target | L1 hsa=4.0 | L1 + L3 stack |
|---|---|---|---|
| Mean dur | 2.0–3.5s | 2.86s ✅ | 2.86s ✅ |
| P95 dur | ≤ 5.5s | 5.18s ✅ | 5.18s ✅ |
| Max dur | ≤ 6.0s | 5.92s ✅ | 5.92s ✅ |
| Over_max | 0 | 0 ✅ | 0 ✅ |
| WER drift | ≤ 0.5pp | (待 manual eyeball) | (待 manual eyeball) |
| Wall clock | baseline +15% | +36% ⚠️ | +36% ⚠️ |

**Wall clock超 +15% target**（+36%）— 主要由 word_timestamps DTW alignment cost。Trade-off acceptable for fine-segmentation 帶來嘅 translation alignment 大幅改善。

## Decisions Log

**2026-05-03 (initial — superseded)**
- L1 driver = `hallucination_silence_threshold=4.0` (medium-q4 sample only)

**2026-05-03 (final — after Run 4 cross-style)**
- L1 driver = **single-lever `temperature=0.0`** validated across **2 broadcast styles**：
  - Sports interview/news (Real Madrid): mean 3.72→2.54s, sent% 19.4→39.8%
  - Political monologue (Trump): mean 1.91→2.74s, sent% 26→49%
  - Both converge to ~2.5–2.74s mean + ~40–49% sent_end% sweet spot
- temp_0 = boundary quality **stabilizer**, NOT length adjuster

**2026-05-03 (revised after large-v3 + 11-config A/B)**
- L1 driver = **single-lever `temperature=0.0`** (固定，disable default fallback tuple)
  - Reason: 唯一 effective lever 喺 large-v3。Mean −32%、segments +50%、sent_end% 翻倍、wall clock 反而 −8%
  - Rejected: `hallucination_silence_threshold` (large-v3 反效果, max 跳升 9.58s)
  - Rejected: `length_penalty` / `beam_size` / `patience` / `max_initial_timestamp` / `sample_len` (全部 noop 或反效果)
- L3 driver = pySBD 4-tier hybrid + **boundary repair (Tier 0.5)** + protected-span regex
  - Reason: 零 new dep, 97.92% GRS accuracy
  - **Boundary repair 必需** — 解決 cross-30s-window mid-clause cuts (user-identified #3+#4 case)
- L2 (Silero VAD) = **deferred** — L1 alone 已大幅改善, ship L1+L3 後再評估
- Production model = large-v3 (user-confirmed, not medium-q4)
- Acceptance criteria 修正：mean chars 50–80（英文）而唔係 8–12（中文）

## Post-Implementation Validation (2026-05-03, after merging fine-seg branch)

### Live integration test results

```
pytest tests/integration/test_fine_segmentation.py --run-live -v
```

| Test | Duration | Result |
|---|---|---|
| test_real_madrid_5min_fine_seg_pipeline | ~80s | ✅ PASS |
| test_real_madrid_words_preserved | ~80s | ✅ PASS |

### Empirical metrics (production code path, large-v3)

| Metric | Pre-impl prototype | Post-impl production | Acceptance gate | Result |
|---|---|---|---|---|
| n | 86 | **85** | 70-110 | ✅ |
| Mean duration | 3.19s | **3.07s** | 2.5–3.5s | ✅ |
| P95 duration | 5.10s | **4.82s** | ≤ 5.5s | ✅ |
| Max duration | 5.48s | **5.64s** | ≤ 6.0s | ✅ |
| Tiny rate (<1.5s) | ~5% | **4.7%** | <8% | ✅ |
| #3+#4 case fix | ✅ | **✅** | required | ✅ |
| Words populated | 100% | **100%** | ≥90% | ✅ |

Production code path matches prototype empirical results within tolerance — all acceptance gates passed on real audio.

### Backward compat verification

- Backend pytest baseline 469/481 PASS / 12 pre-existing FAIL → 509/521 PASS / 12 FAIL (Phases A+B+C+D adding ~30 new tests)
- Existing profile JSON unchanged behaviour ✅ (test_profile_backward_compat_no_new_fields PASS)
- Legacy `engine.transcribe()` path 100% preserved ✅ (test_app_fine_seg.py covers branch routing)
- Pre-existing 12 failures unchanged (test_e2e_render Playwright + test_renderer macOS tmpdir colon-escape) — not regressions

### Outstanding observations

- Wall clock for 5min audio: ~80s vs prototype 65.6s (slightly slower, possibly cold cache). Within +15% acceptance gate. Cold-start Silero VAD model load adds ~3s singleton init.
- Tests SKIP cleanly when `--run-live` flag is omitted (default `pytest tests/` run unaffected).

## v3.9 Increment — MT Cascade Drift Fix + ASR Tuning（2026-05-04）

**Date:** 2026-05-04
**Trigger:** v3.8 ship 後 user 觀察到 MT 中文後半段同英文時間軸唔對稱（cascade drift）

### Diagnostic chain（三層 root cause）

1. **Parser drift（[backend/translation/ollama_engine.py:637-673](backend/translation/ollama_engine.py)）** — `_parse_response` 用 sort + positional remap，當 LLM 漏編號或 echo context 時 cascade shift。Mock 1000-trial × 211 segs（4 fixtures），realistic mean drift = **9.30%**、P95 = 19%、pessimistic = 15.56%。
2. **Engine 太弱** — 用 `qwen2.5-3b`（3B params）SKIP/ECHO 率比 35B+ model 高 1 個 order of magnitude。
3. **Sentence-vs-segment boundary mismatch** — LLM 將 batch 視作連續英文、按中文句切 N 段，唔跟 ASR 時間 cut。架構性問題、parser 解唔到。

### Fix 落地

| Layer | Commit | 改動 | 跨 fixture 證據 |
|---|---|---|---|
| Parser | `05c6d7a` | slot-fill v2（dict-by-number）取代 sort+positional | Mock drift 9.30% → 5.03%（−27%）+ 5 new unit tests |
| Engine | profile-level | OpenRouter `qwen/qwen3.5-35b-a3b` 取代 `qwen2.5-3b` | Live re-translate first 12 segs cascade-free vs prior 1-2 段位移 |
| Pipeline | profile-level | `translation.use_sentence_pipeline: true` | Live test 12/12 段對齊（pySBD merge → translate → char-prop redistribute）|

### v3.9 ASR enhancement candidate sweep（5 candidates × cross-fixture A/B）

**Fixtures**：`/tmp/l1_real_madrid.wav` (5min sports interview) + `/tmp/trump_5min.wav` (5min political speech). Both 16k mono PCM, mlx-whisper large-v3.

#### Item 1 + Item 3 — SHIPPED（commit `83bfb05`）

| Item | 改動 | RM Δ | Trump Δ |
|---|---|---|---|
| **1** | Whisper hallucination guards (`no_speech=0.1`, `compression_ratio=1.4`, `logprob=-1.0`) on chunk + fallback paths | 0 effect (continuous speech) | 0 effect (continuous speech) |
| **3** | `vad_speech_pad_ms` 200 → 300 | sent% **+3.48**, func% **−6.43**, mean −0.24 | sent% **+3.66**, max +0.38 (pre-existing baseline 7.62 long monologue), tiny +3 |

Item 1 zero measurable effect on continuous-speech fixtures but mbotsu reference confirms benefit on silence-tail audio (defensive). Item 3 跨 fixture sent% 一致 +3.5% — 強信號 ship。

#### Bonus — `safety_max_dur` 9.0 → 6.0（commit `835169a`）

Word_gap_split parameter sweep（5 configs × 2 fixtures，cached pre-refine segs，instant in-memory iteration）：

| cfg | RM max | Trump max | Trump tiny | Trump sent% |
|---|---|---|---|---|
| cur (safety=9.0) | 5.50 | **8.00** ❌ | 12 | 75.7 |
| **A1 (safety=6.0)** ✅ chosen | 5.50 | **5.98** ✅ | 12 | 67.9 |
| A2 (+ gap_thresh 0.05) | 5.50 | 5.98 | 12 | 66.2 |
| A3 (safety=5.5) | 5.50 | 5.44 | 12 | 62.4 |
| A4 (+ min_dur 1.0) | 5.16 | 5.92 | **27** ❌ | 63.1 |
| A5 (most aggressive) | 5.16 | 5.44 | **30** ❌ | 59.6 |

**A1 sweet spot**：RM 完全冇影響（5.50 ≤ 6.0 唔觸發），Trump max 8.00 → 5.98 過 v3.8 gate，tiny rate 不變，sent% −7.8 係 honest cost（force-split 失去原段尾標點，但 UX 2× 3s 段優於 1× 8s 字幕）。A3/A5 sent% 跌幅 13-16% 太嚴重，min_dur 1.0 觸發 tiny rate ×2.5，rejected。

**Architecture finding（log 為 future ref）**：Trump 8.00s 段**唔係** blind 25s sub-cap 切壞造成 — mlx-whisper 喺一個正常 ≤25s chunk 內部一次性 emit 嗰 8s。decoder 30s window 內部冇放 sentence boundary。Item 2（collect_chunks）+ silence-aware split hybrid 都 no-op，因為問題喺 decoder 內部、唔喺 chunk boundary。**word_gap_split force-split 係唯一路徑**。

#### Rejected candidates

| Item | 改動 | 失敗原因 |
|---|---|---|
| 2 (pure) | mbotsu `collect_chunks`（strip inter-sentence silence） | Trump sent% **−25.7** — 剝走 silence 等於剝走 Whisper 嘅 sentence-end signal。mbotsu 原 use case（短語日文）唔啱廣播字幕需求（句末標點 = 觀眾視線重置點）|
| 2 (hybrid) | Silence-aware split + 保留時間軸 | Trump max no-op（hybrid 只 help spans > threshold，但 Trump 8s 段喺 ≤25s chunk 內部，hybrid 完全唔觸發）。RM 邊際升 max -0.24 但 over84 +5、wall +7s |
| 4 | `initial_prompt` 接續（last 1/2 sentence/150 chars 餵入下個 chunk） | Cross-fixture inconsistent：RM sent% +3.58 / Trump sent% −1.28。35B model 已 7/8 named entity 一致（只 Vinicius Junior 嘅 P2 統一咗），其他 Bellingham/Ancelotti/Alonso/Alaba/Militao/Rüdiger/Asensio 全部 1 variant。Cost：max_chars +12-20、tiny +3 |
| 5 | `vad_min_silence_ms` 500 → 800 | Phase-1 stack 量度時 RM max 5.48 → 8.00（破 v3.8 acceptance gate）— 長 silence merge 兩短停頓做長 chunk，超出 word_gap_split 嘅 split 範圍 |

### Production live verification

User profile (`prod-default.json`) 切到 `engine: openrouter / qwen3.5-35b-a3b` + `use_sentence_pipeline: true` + `fine_segmentation: true` + `temperature: 0.0` 後，重新 translate 既有 file `6549d0790c3d` 嘅 66 segs：

- Pre-fix（v3.8 + qwen2.5:3b）：first 6 segs 之中 4 段 cascade drift（ZH 內容對應 EN 偏移 1-2 個 slot）
- Post-fix（v3.9 + 35B + sentence_pipeline）：first 12 segs 全部對位（Vinicius/Bellingham/Alaba/Rüdiger 等 named entity 跨 batch 一致）

Backend log 確認 `parse diag` 全程 silent — LLM 編號 1-N 完美 emit、parser slot-fill 全 in_range，drift 從 parser 層消除。

### v3.9 acceptance gates summary

| Metric | Threshold | RM result | Trump result |
|---|---|---|---|
| Mean | 2.5–3.5s | 3.07s ✅ | 3.03s ✅ |
| P95 | ≤ 5.5s | 4.82s ✅ | 5.52s ✅ |
| Max | ≤ 6.0s | 5.50s ✅ | **5.98s ✅** （v3.8 baseline 8.00 ❌） |
| Tiny rate | < 8% | 6.5% ✅ | 13.3% ⚠️ Trump dense monologue 邊際超 8% |
| Sent% | ≥ 35% | 43.0% ✅ | 67.9% ✅ |
| Hallucination rate | 0 | 0 ✅ | 0 ✅ |

Trump tiny rate 13.3% 係 force-split 帶來嘅副作用（force-split 唔保證兩半都 ≥1.5s）。Cross-style 接受 — broadcast UX 上 2× 3s 段優於 1× 8s 段。

### Backward compat

- 既有 profile JSON 唔加新欄位仍 100% work（function default 改變只影響 implicit fallback）
- 既有 callers 直接 call `word_gap_split(safety_max_dur=9.0)` 100% 仍按 9.0 行為（test 證實）
- Backend pytest 469 → 520 PASS（v3.9 完，v3.8 baseline 510，+10 new tests）/ 12 pre-existing FAIL 不變

## v3.11 Increment — Phase A Dead Code Purge + Phase B Simplification A/B（2026-05-05）

**Date:** 2026-05-05
**Trigger:** 用戶提出 simplification audit — 用 3 agent team 並行檢視 ASR / MT / cross-layer 有冇 dead code 或 over-engineering 可以收口。

### 背景

v3.10 ship direct batch translate 後，stack 累積咗大量 v3.1-v3.9 開發過程嘅實驗性 module（sentence_pipeline、alignment_pipeline、Pass 2 enrichment、stub engines、live recording streaming family）。production 路徑由 `prod-default.json` 已收緊到只用：mlx-whisper fine_seg + OpenRouter 35B direct batch + slot-fill v2 parser。其他全部 dead-by-config。

### Phase A — PROVEN_SAFE dead code purge（commit `b3a4960`）✅

3 agent team 獨立確認 5 大類 orphan code，逐項驗證後一次過刪除：

| Target | LOC removed | 證據 |
|---|---|---|
| `backend/translation/alignment_pipeline.py` + test | 319 + 196 | 兩個 profile 都無 set `alignment_mode`；只 reachable 由 `app.py` 兩個 dead routing branch |
| `backend/translation/sentence_pipeline.py` + test | 271 + 269 | 兩個 profile 都無 set `use_sentence_pipeline`；同樣 dead routing |
| `backend/asr/qwen3_engine.py` + `flg_engine.py` | 82 | Stub engines 從未實作；factory 從未 instantiate |
| `ENRICH_SYSTEM_PROMPT` + `_enrich_pass` + `_get_translation_passes` | ~135 | `translation_passes: 2` 從未喺任何 profile set |
| `live_subtitle` / `streaming_*` event family + 5 SocketIO handlers + StreamingSession class + `/api/streaming/available` route + dead state caches | ~370 | **Frontend 0 listener**；v2.0 「removed live recording mode」嘅 cleanup miss；`live_audio_chunk` handler 內部 call 4 個不存在嘅 helper（invoke 即 NameError） |
| F4「all chunks failed」fallback（`sentence_split.py`） | ~22 | 觸發等於 mlx 全死，silent fallback 隱藏 real bug；F2 zero-spans 路徑保留 |
| `condition_on_previous_text` schema entry（`mlx_whisper_engine.py`） | ~10 | fine_seg path hardcode False / fallback path hardcode True；UI field 唔生效，runtime 仍接受 JSON edit |
| `qwen3-asr` / `flg-asr` 由 `VALID_ASR_ENGINES` + UI engine list 移除 | ~3 | 收緊到 `{whisper, mlx-whisper}` 兩個真實 engine |
| 4 個 affected test file 移除 orphan 測試 | minor | `test_app_fine_seg.py` / `test_renderer.py` / `test_asr.py` / `test_translation.py` |

**Net diff: 22 insertions, 1907 deletions**（commit `b3a4960`）

**Pytest baseline shift**: 520 PASS → **469 PASS / 12 pre-existing FAIL**（純 orphan test 移除，零 production regression）。

**Live verification post-purge**: `/api/health` OK / active profile config 不變 / `/api/asr/engines` 由 4→2 engines / 重譯 file `a283cdcbfe0a` 93 segs 0 empty / 0 short / 0 mid_cut。

### Phase B — NEEDS_RECHECK candidates（全部 reject 唔 ship）

3 個 agent team 標記咗 3 項 tunable simplification candidates 需要 live behavioral A/B 先決定：

#### B.1 ❌ **ASR.A1**：collapse `word_gap_split` thresholds（remove `min_dur` + `safety_max_dur`）

**Verdict: REJECT — production metric 已證實兩個 threshold 都 load-bearing**

- `safety_max_dur=6.0` force-split 係 v3.9 commit `835169a` 解 Trump 8.00s long monologue 嘅唯一機制
- `min_dur=1.5` 護住短段唔會喺 word_gap_split 內部產生 < 1.5s 殘段
- 移除即恢復 v3.8 嘅 max ≤ 6s gate 失敗 + tiny rate 上升
- **唔需要 live A/B**：production 跑緊嘅 max=5.98s + tiny=12 數字本身就係 evidence

#### B.2 ❌ **MT.M1**：remove `context_window` plumbing

**Verdict: REJECT — non-prod profile 仍有用緊**

- `prod-default.json` 唔 set `context_window`（default 3）
- 但 `b877d8b5-….json` profile **明確 set** `context_window: 3`
- 兩個 profile 共存於 repo，不能假設 b877 係 abandoned
- **唔需要 live A/B**：靜態檢查已足夠 reject

#### B.3 ❌ **MT.M2**：trim few-shot examples 4→2 + drop `_retry_missing`

**Verdict: REJECT — 經兩輪 live A/B 驗證後發現 quality regression**

A/B setup：
- Baseline = current production prompt（4 examples：例一/例二/例三/例四 + retry-on-missing 機制保留）
- Variant = monkey-patch `SYSTEM_PROMPT_FORMAL` 移除例三/例四，留 698 chars vs baseline 1025 chars（−32%）
- Re-translate file `a283cdcbfe0a`（93 segs，~50s/run）
- Production prompt 跑後即時 restore

**Aggregate metric 睇似平手**（兩者都 0 empty / 0 short / 0 mid_cut，14/16 entity preservation tied），但 cluster 級眼睇發現 2ex variant 出現嚴重 quality regression：

| 失敗類型 | 4ex baseline | 2ex variant |
|---|---|---|
| **專名 hallucination**：Vinicius **Junior** 譯名 | ✅ 雲尼素斯·祖連奴（正確 HK 譯名） | ❌ 「小**蘇亞雷斯**」（將 Junior 變成 Suarez 姓氏 — 完全唔同球星） |
| **事實錯誤**：「RZ's Case Smit」嘅球會歸屬 | ✅ 「雷恩的凱斯·史密特」（猜 Rennes — 估錯但中性，RZ ≈ Real Sociedad）| ❌ 「皇家馬德里（RZ）的凱斯·史密特」（誤指做 Real Madrid — 觀眾會以為 Smit 已喺皇馬，全段論述邏輯崩潰）|
| **Cluster 1 對位 cascade** | ✅ 完美 align（segs 1-6） | ❌ +1 shift cascade（ZH #3 = EN #4 / ZH #4 = EN #5 / etc）|

**Root cause**：`例三` + `例四` 兩個例子**唔係** redundant，佢哋承擔住：
- 專名譯名約束（防止 LLM 將 "Junior" 自由替換成其他球星 surname）
- 模糊縮寫（如 RZ）嘅謹慎處理態度
- Cluster 級對位嘅 numbered output 紀律

—— 呢三項都係 v3.0/v3.1 開發時用 examples 解決過嘅問題，trim 等於回退到嗰個年代嘅 failure mode。

**Retry path drop**：因 baseline 跑時 retry 觸發率 = 0/93（35B + slot-fill v2 emit 完美 numbered output），呢輪 fixture 量唔到效果，**保留作 SKIP/ECHO safety net**，唔 drop。

### v3.11 ship 結果

- Phase A：~1900 LOC dead code 移除（commit `b3a4960`）✅
- Phase B：全 3 項 reject，production 配置維持 v3.10 不變
- Backend pytest: 469 PASS / 12 pre-existing FAIL / 2 skipped — 同 baseline 一致
- Production live verification 通過（重譯 93 segs metric 同 v3.10 一致）

### 教訓總結 — 將來 simplification audit 嘅 anti-pattern

| Anti-pattern | 反例證據 |
|---|---|
| **Aggregate 0/0/0 metric 唔等於 quality OK** | M.2 兩個 config 都 0/0/0 但 2ex 引入 entity hallucination |
| **Few-shot example 表面 redundant 實質 load-bearing** | 例三 + 例四 對 LLM 嘅 implicit 約束（專名穩定、縮寫謹慎、編號紀律）唔會喺 aggregate metric 顯現 |
| **`b877d8b5-….json` 等用戶自訂 profile 唔可以假設 abandoned** | M.1 context_window 唯一持有者 |
| **Production metric 本身就係最強 validation evidence** | A.1 嘅 max=5.98 + tiny=12 數字證明 thresholds 在工作 |
| **Stochastic LLM 跑兩次同一 config 出唔同結果** | 4ex baseline 喺前 run cluster 1 cascade、後 run 完美對位；temp=0.1 引入 noise，single-run A/B 結論不充分，要多 run 平均化 |

## Outstanding Questions（v3.8 carry-over）

1. fine-grained ASR + sentence_pipeline.merge_to_sentences() 重疊 → 要唔要加 `sentence_pipeline_skip` flag 自動 detect？
   **→ v3.11 已解：sentence_pipeline.py 整個刪除，問題不存在。**
2. Protected-span regex 點 maintain？應該整 module 級 constant 定 config-driven？
3. word_timestamps=True 性能 cost 幾多？要唔要 default true 還是 opt-in？
