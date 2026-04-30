# Netflix 字幕標準研究 — EN 同 ZH 字數對應問題

**日期:** 2026-04-30
**目的:** 用 Netflix 嘅標準改寫 Phase 1 字數規則，確保 EN→ZH translate 唔再令中文超長。

---

## 📐 PART 1 — Netflix 官方標準 (verbatim)

### A. 英文 (USA) 字幕

| 項目 | 規格 |
|---|---|
| Max 每行字數 | **42 char/line** |
| Max 行數 | **2 行/cue** |
| 偏好 | **盡量單行**，超 42 char 先轉雙行 |
| Reading speed (成人節目) | **20 chars/sec** |
| Reading speed (兒童節目) | 17 chars/sec |
| Min cue duration | 20 frames @ 24fps (= 5/6 sec ≈ 833ms) |
| Max cue duration | 7 sec |
| Min gap between cues | 2 frames (any framerate) |
| 3-11 frame gap | 必須 close 到 2 frame |
| Shot change | 跨 scene cut 唔得（除非 dialogue 真係 span） |
| 換行位置 | 標點後、conjunction / preposition 之前；唔可斷 article-noun、first-last name、verb-aux |

### B. 繁體中文 / 簡體中文 字幕 (Netflix Originals)

| 項目 | 規格 |
|---|---|
| Max 每行字數 | **16 char/line (Netflix Originals)** / 23 char/line (一般非 Originals) |
| Max 行數 | **2 行/cue** |
| 偏好 | **盡量單行**，超 16 char 先轉雙行 |
| Reading speed (成人) | **9 chars/sec** |
| Reading speed (兒童) | 7 chars/sec |
| Reading speed (SDH 成人) | 11 chars/sec |
| Min/max duration / gap / shot change | 同英文 (Netflix 全部語言通用) |
| 換行 | 同英文：bottom-heavy pyramid、唔好得一兩字喺上面 |

### C. 韓文 / 日文 (參考)

| 項目 | KR | JP |
|---|---|---|
| Max 每行字數 | 16 char (Originals) | 一般約 13-15 char |
| Reading speed | 12 chars/sec | ~4-7 chars/sec (日本廣播 NHK 規範) |

---

## 🚨 PART 2 — 核心問題：EN→ZH char-count mapping 點解錯

### 你提出嘅 pain point

> 「我哋而家係根據英文嘅長短，之後直接 map 返落去中文。但係咁樣就會令到中文嘅字幕非常之長。」

### 用 Netflix 標準量化呢個 problem

**英文一行 42 char 對應應該係幾多中文？**

按 Netflix 官方限制：
- EN max = 42 char/line
- ZH max = **16 char/line (Originals) 或 23 char/line (一般)**

**Ratio:**
- 一般版本: `42 / 23 ≈ 1.83`，即係**英文 1.83 char ≈ 中文 1 char**
- Originals 版本: `42 / 16 ≈ 2.63`，即係**英文 2.63 char ≈ 中文 1 char**

### Reading speed 角度同樣印證

- EN 觀眾舒服 reading speed: **20 char/sec** (成人)
- ZH 觀眾舒服 reading speed: **9 char/sec** (成人)
- Ratio: `20 / 9 ≈ 2.22`，即**讀英文 2.22 char 嘅時間 ≈ 讀中文 1 char**

**所以 Netflix 設計嘅哲學:**
- 同樣意思，英文寫得長啲冇問題，因為觀眾讀得快
- 中文必須**更精煉**，因為讀字比英文慢
- 直接 1:1 char map = **錯**

---

## 🎯 PART 3 — 你今日系統嘅問題定位

### 系統現有設計

```python
MAX_SUBTITLE_CHARS = 28   # ZH char limit
[long] flag    >28 char
[review] flag  >40 char (hallucination)
```

### 用 Netflix 標準對照

| 你嘅 threshold | Netflix Originals (16) | Netflix 一般 (23) | TVB 內部 (約 28) |
|---|---|---|---|
| 28 字 ZH | **超 75% 嘅 spec** | 超 22% | **just match** |

**結論:** 你嘅 28 字 threshold 適合 TVB 廣播 internal，但若以 OTT 標準（Netflix）做基準，係超標 22-75%。

### 真正嘅 root cause

你嘅系統流程：
```
EN audio → Whisper (返 EN text in chunks) →
chunks 通常 ~30-50 EN char (Whisper 自然輸出長度) →
LLM translate to ZH （盡量 1:1 對應） →
得出 ~25-40 ZH char per segment
```

**問題點:**
1. Whisper 輸出嘅 EN segment 已經接近 42 char 上限
2. LLM 翻譯時 try to preserve meaning，自然 expand 為 25-35 ZH char
3. 結果 ZH 超 16/23 字限制係**必然**，唔係偶然

**正確修正方向（如你所說）:**

> **「將英文本身嘅字句縮短，令到中文嘅字數隨之縮短，先至係正確嘅方法。」**

這個診斷係**對嘅**。要喺 ASR / segmentation 階段就確保 EN 段唔超過某個值，先可以保證 ZH 譯文喺合理範圍。

---

## 📊 PART 4 — 修訂後嘅 Phase 1 字數規則

### 新增 EN segment 上限規則

按 Netflix 標準 + 你提出嘅修正：

| Mode | EN max char/segment | ZH expected max | 點計嚟 |
|---|---|---|---|
| **Netflix Originals 嚴格** | ~28-30 EN char | 16 ZH char | 16 × 1.83 ratio |
| **Netflix 一般** | ~42 EN char (1 line) | 23 ZH char | Netflix 官方 |
| **TVB 內部 (你今日)** | ~50 EN char | 28 ZH char | 用戶現有 setting |

### 修訂後嘅 segmentation 流程

```
Whisper raw output → 
[NEW] split EN segments 喺 EN_MAX_CHAR 之前 (split at sentence boundary / pySBD) →
LLM translate → 
ZH 自然落入 16-28 範圍 →
post-process flag 邊個超 ZH_MAX_CHAR
```

### Phase 1 新增 idea

我會建議將 Phase 1 嘅 `P1.5 — Per-Language Line-Length Config` 擴大成兩個 idea：

**P1.5a — EN Segment Length Cap (新)**
- **What:** 喺 ASR / `split_segments()` 階段限制 EN segment ≤ EN_MAX_CHAR
- **Why:** 解決 root cause — 唔再令 ZH 譯出嚟必然超標
- **How:** 喺 `segment_utils.split_segments()` 加 char-count check (而唔只係 word-count + duration)。Profile 加 `en_max_chars: 42` 欄位
- **Trade-off:** 切得更細可能影響 LLM 翻譯時嘅 context (sentence pipeline 已經有 `merge_to_sentences` 處理呢個)

**P1.5b — ZH Output Length Validation (改良已有)**
- **What:** 維持 `[long]` flag 但 threshold 由 Profile 揀 (16 / 23 / 28)
- **Why:** 因應唔同 client（Netflix vs TVB）requirement 不同
- **How:** Profile 加 `zh_max_chars: 28` (default)，可調 16 / 23
- **Trade-off:** 一個 setting，多個 use case，零 breaking

**P1.5c — CPS Guard Tier (改良 P1.1)**
- **What:** CPS 同樣按 language 分 tier (EN 20 / ZH 9 / JA 4)
- **Why:** Netflix 標準明確指出唔同語言唔同
- **How:** `language_config.json` 入面 `max_cps_adult` + `max_cps_children`

---

## 🔄 PART 5 — 對 Phase 1 嘅整體修訂建議

### 原 Phase 1 (9 個)
1. CPS reading-rate guard
2. Frame-accurate snap
3. Number/date/quote invariance
4. NER cross-check
5. Per-language line-length config
6. Hash-chained audit log + `_sv` schema
7. Profile/Glossary bundle .tar.gz
8. Webhook event chain
9. Pre-render blocking gate

### 修訂後嘅 Phase 1 (10 個)

**新增第 5a 項 EN segment cap，原有 5 拆細：**

1. CPS reading-rate guard (per-language tier: EN 20 / ZH 9 / JA 4)
2. Frame-accurate snap
3. Number/date/quote invariance
4. NER cross-check
5. **EN Segment Length Cap (NEW)** — 喺 ASR 階段限制 EN char/segment
6. **ZH Output Length Validation** — Profile 揀 threshold (16/23/28)
7. Hash-chained audit log + `_sv` schema
8. Profile/Glossary bundle .tar.gz
9. Webhook event chain
10. Pre-render blocking gate

### 額外要決定嘅事

**Question for you:**

(a) **你嘅 deliverable 客戶係邊類?**
- Netflix / Disney+ / Apple TV+ → 用 16 char ZH (Originals) 或 23 char (一般)
- TVB / RTHK / OTT-only → 28 char (你今日 setting)
- 多客戶混合 → Profile 入面提供三個 preset 揀

(b) **EN cap 設幾多?**
- 為 ZH = 16 反推: EN ≤ 28-30 char (極嚴)
- 為 ZH = 23 反推: EN ≤ 42 char (Netflix 一般 = 同 EN max line 一致)
- 為 ZH = 28 反推: EN ≤ 50 char (你今日 implicit)

(c) **Sentence pipeline 點配合?**
- 你今日有 `merge_to_sentences` (pySBD) → translate → `redistribute_to_segments`
- 新加 EN cap 應該喺 `redistribute` 之後，唔好影響 sentence-level 翻譯 quality
- 即係：merge 做完整句翻譯確保 LLM 有 context → split 返出 segment 時 enforce EN char cap

---

## 📋 PART 6 — 同其他 broadcast 標準比較

| 標準 | EN char/line | ZH char/line | EN reading speed |
|---|---|---|---|
| Netflix Originals | 42 | **16** | 20 cps |
| Netflix 一般 | 42 | **23** | 20 cps |
| Disney+ | 42 | (跟 Netflix 似) | 20 cps |
| Apple TV+ | 42 | 16 (TC/SC 嚴) | 20 cps |
| BBC | 37-39 | (TC 無公開) | 17 cps |
| TVB 內部 | 約 50 | 約 28 | 唔嚴 enforce |
| EBU R37 | 37 | (TC 無) | 17 cps |
| RTHK | 約 42 | 約 16-20 | 9 cps |

**Insight:** 你今日 28 char 標準是 TVB 寬鬆嘅 baseline。如果想 deliver 去 Netflix / Apple TV+，必須跌到 16-23。

---

## 🎯 PART 7 — 我嘅最終建議

### 修訂 Phase 1 嘅核心新規則

```json
// Profile font config 加入
{
  "subtitle_standard": "tvb" | "netflix_originals" | "netflix_general" | "custom",
  "en_max_chars": 42,        // segment max EN char (auto-set by standard)
  "zh_max_chars": 16,        // segment max ZH char (auto-set by standard)
  "max_cps": 9,              // chars/sec ZH
  "max_lines": 2,
  "min_cue_duration_ms": 833,
  "max_cue_duration_ms": 7000,
  "min_gap_frames": 2
}
```

### 三個 preset 對應三類客戶

| Preset | EN max | ZH max | Use case |
|---|---|---|---|
| `netflix_originals` | 28 | 16 | 賣 Netflix Originals 嘅 deliverable |
| `netflix_general` | 42 | 23 | 賣 Netflix 一般 / Disney+ / Apple TV+ |
| `tvb` (default) | 50 | 28 | TVB / RTHK / 香港 OTT |

### 點解呢個 design 解決你嘅 root cause

1. **EN 階段已經 cap** → LLM 翻譯時 input 已經短，output 自然短
2. **ZH 階段 enforce 對應 threshold** → catch 翻譯 expand 嘅情況
3. **CPS 跟住 language tier** → 唔再用一個 number 跨所有語言
4. **Profile 揀 preset** → 一個 Profile 對應一個 client 嘅 deliverable spec

---

## ❓ 我等你決定嘅事項

請告訴我以下幾個答案，先決定點寫 v3.8 sprint plan：

1. **你嘅主要 deliverable 客戶**係邊個? (TVB / RTHK / OTT / Netflix / 多種)
2. **你想點 default**? 用 TVB 28 字（保持向下兼容）定 Netflix 16 字（嚴格但會迫 LLM 寫短啲）?
3. **EN cap 嘅實際範圍**你想用幾多? 28 / 42 / 50 / 揸住 Profile 揀?
4. **Sentence pipeline 配合**: 你 OK 喺 split 之後 cap 嗎? 定要 cap 之後再 translate?

---

## Sources

- [Netflix English (USA) Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide)
- [Netflix Chinese (Traditional) Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215994807-Chinese-Traditional-Timed-Text-Style-Guide)
- [Netflix Chinese (Simplified) Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215986007-Chinese-Simplified-Timed-Text-Style-Guide)
- [Netflix Maximum Characters Per Line](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215274938-What-is-the-maximum-number-of-characters-per-line-allowed-in-Timed-Text-assets)
- [Netflix Subtitle Timing Guidelines](https://partnerhelp.netflixstudios.com/hc/en-us/articles/360051554394-Timed-Text-Style-Guide-Subtitle-Timing-Guidelines)
- [Netflix General Requirements](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements)
