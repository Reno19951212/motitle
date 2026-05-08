# Split 機制 A + B 深度解構

**日期:** 2026-04-30
**重點:** 唔猜，全部根據實際 source code。

---

## 🧰 PART 0 — 機制定位 (1 句講晒)

| 機制 | 定位 | 何時跑 |
|---|---|---|
| **機制 A** = `split_segments()` | ASR 後處理（純切割，唔翻譯） | ASR 一返就跑 |
| **機制 B** = `merge_to_sentences()` + `redistribute_to_segments()` | 翻譯前後處理（先合再切） | 翻譯時跑（要 opt-in） |

兩個係**串行**而非平行：A 一定喺 B 之前。B 係 optional。

---

## 🅰️ PART 1 — 機制 A：`split_segments()`

### Q1.1 — 用咩模型？

**冇用任何 ML 模型。** 純 Python regex + 算術。

具體用咩:
- `re.compile(r"[.!?]")` — 偵測句末標點 (英文)
- `text.split()` — 按空白拆 word
- `math.ceil()` — 計需要分幾多 chunk

### Q1.2 — 係咪喺 ASR 入面做？

**唔係。** 喺 ASR **之後** 立即做。

確實位置 — `app.py:464-472`:

```python
raw_segments = engine.transcribe(audio_path, language=language)   # ← ASR
                                                                  # ↓ Pass to:
from asr.segment_utils import split_segments
raw_segments = split_segments(
    raw_segments,
    max_words=asr_params["max_words_per_segment"],
    max_duration=asr_params["max_segment_duration"],
)
```

但係檔案放喺 `backend/asr/segment_utils.py`，命名上歸 ASR 模組所有。**「ASR 後處理」係 ASR 模組嘅一部分**，但**唔係** Whisper engine 入面跑。

### Q1.3 — 點計 cap 出嚟？

讀 `language_config.json`：

| 語言 | max_words_per_segment | max_segment_duration |
|---|---|---|
| **English** (`en.json`) | **25** words | **40** sec |
| **Chinese** (`zh.json`) | **30** words | **8** sec |

Profile 會揀 `language_config_id` 對應邊個 config。

### Q1.4 — Split 算法精確流程

```
input: 一個 Whisper segment {start, end, text, words?}
  ↓
1. word_count = len(text.split())
   duration = end - start
  ↓
2. needs_word_split = word_count > max_words
   needs_duration_split = duration > max_duration
  ↓
3. 兩個都 false → 原段 return，唔切
  ↓
4. 任一 true → 計 num_chunks = max(
      ceil(word_count / max_words),
      ceil(duration / max_duration)
   )
  ↓
5. target_chunk_size = ceil(word_count / num_chunks)
  ↓
6. _partition_words(): 行去每個 word，達到 target 時：
   - 如果呢個 word 帶句末標點 (.!?) → 立即切 ✅
   - 唔係，但前面有句末標點 → 撤返到嗰個位切 (overshoot recovery)
   - 都冇 → hard split @ target ❌ (硬切)
  ↓
7. _assign_timings(): 按 word index 比例分 timestamp
   - 如果有 word_timestamps → partition engine_words 落 sub-segment
   - 冇 → proportional time slice
  ↓
output: 一個 list, 每段都 ≤ max_words 同 ≤ 控制範圍
```

---

## 🅱️ PART 2 — 機制 B：`sentence_pipeline`

### Q2.1 — 用咩模型？

**用 pySBD (Python Sentence Boundary Disambiguation)。** 但係**只係英文版**：

```python
# backend/translation/sentence_pipeline.py:28
_EN_SEGMENTER = pysbd.Segmenter(language="en", clean=False)
```

⚠️ **冇中文版本嘅 segmenter。** 即係話如果 ASR 出嘅係中文，呢個 pipeline 會用英文 segmenter 去切 — 會出問題（下面 Part 4 詳細講）。

### Q2.2 — 係咪喺 ASR 入面做？

**唔係。** 喺 **翻譯階段** 跑（`backend/translation/sentence_pipeline.py`）。

而且係 **opt-in** —— Profile 入面要設：
- `alignment_mode: "sentence"` 或
- `use_sentence_pipeline: true`

如果你冇 opt-in，呢個 pipeline 完全唔跑（默認 alignment_mode 係空字串 → 1-to-1 直譯）。

### Q2.3 — Pipeline 三步流程

```
A. merge_to_sentences()   — ASR fragments 合併做完整 sentence
        ↓
B. engine.translate()     — LLM 譯每個 sentence
        ↓
C. redistribute_to_segments()  — 將 ZH 切返落原 ASR segment
```

#### Step A — `merge_to_sentences()`

```
input: ASR segments (已過機制 A)
  ↓
1. _split_by_time_gaps() — gap > 1.5s 強制斷句
   原因: 防止跨 speaker change / scene cut 嘅 false merge
  ↓
2. 每個 group 入面:
   - 將所有 segment text join 做 full_text
   - 紀錄 word_to_seg 映射 (邊個 word 屬邊個 segment)
   - pySBD.segment(full_text) 切句
  ↓
3. 對每個 sentence:
   - 數佢佔幾多 word
   - 用 word_to_seg 反向睇佢跨咗邊幾個 segment
   - 紀錄 seg_indices + 每段 segment 嘅 word count
  ↓
output: List[MergedSentence] = [{
    text: 完整英文句,
    seg_indices: [seg_a, seg_b, ...],
    seg_word_counts: {seg_a: 5, seg_b: 3},
    start, end
}]
```

#### Step B — LLM Translate

LLM 收到嘅係**完整 sentence**（唔再係 ASR fragment）→ 翻譯品質好啲，因為有完整 context。

#### Step C — `redistribute_to_segments()`

```
input: merged_sentences + zh_sentences + original_segments
  ↓
對每個 merged sentence:
  total_zh_chars = len(zh_text)
  total_en_words = sum(seg_word_counts.values())
  ↓
  如果整句 ZH 只屬一個 segment → 直接 assign 完
  ↓
  如果跨多個 segment:
    對每個 segment i:
      proportion = en_word_count[i] / total_en_words
      target_end = char_offset + round(total_zh_chars × proportion)
      ↓
      _find_break_point(zh_text, target_end, search_range=3):
        喺 target_end ± 3 char 內揾「。，、！？；：）」』】」嘅最近一個
        揾到 → 落嗰度切
        揾唔到 → 落 target_end
      ↓
      assign zh_text[char_offset:break_at] 落 segment i
output: List[TranslatedSegment]
```

⚠️ **3 個重要技術細節:**

1. **唔再 split 任何嘢** — 純按比例 + 標點 snap，**唔再保證每段唔超 cap**
2. `_find_break_point` 嘅 `search_range=3` 太細 — 如果 3 char 內冇標點，硬切
3. **冇 sentence pipeline 嘅情況下** (即 alignment_mode 空)，呢 3 步全部跳過 — engine.translate() 直接接收 ASR fragment 去 1-to-1 譯

---

## 🌊 PART 3 — 完整 flow diagram

### 主流程 (你今日跑緊嘅 path)

```
┌──────────────────────────────────────────────────────────────────┐
│                    完整 Pipeline (English ASR path)               │
└──────────────────────────────────────────────────────────────────┘

[1] 🎙️ Audio File (mp4/wav)
        │
        ▼
[2] FFmpeg extract → 16kHz mono WAV
        │
        ▼
[3] Whisper Engine (faster-whisper / openai-whisper / mlx-whisper)
    │  Params (from Profile.asr):
    │    - model: small / medium / large-v3
    │    - language: "en"
    │    - max_new_tokens: optional
    │    - condition_on_previous_text
    │    - vad_filter
    │    - word_timestamps (opt-in for DTW alignment)
    │
    ▼
[4] ⚙️ Whisper raw segments
    [{start, end, text, words?}, ...]
    每段大概 30-60 EN char，duration 變化大（1-15 sec）
        │
        ▼
┌───────────────────────────────────────┐
│ 機制 A — split_segments()              │ ← 永遠跑
│ (純 regex + 算術，無 ML)                │
│                                       │
│ language_config (en.json):            │
│   max_words: 25                        │
│   max_duration: 40                     │
│                                       │
│ 唔超 → keep                            │
│ 超 → ceil split                        │
│   - 優先句末標點 (. ! ?)                │
│   - 揾唔到 → hard split                │
└───────────────────────────────────────┘
        │
        ▼
[5] 📝 Segments [{start, end, text, words?}, ...]
        │
        ▼  (registry 紀錄 + frontend show 喺 dashboard)
        │
        ▼  ⏰ 等用戶觸發 _auto_translate()
        │
        ▼
[6] _auto_translate(file_id) reads Profile.translation:
    ├─ alignment_mode == "llm-markers"  →  Path X (LLM markers, 唔係今日重點)
    ├─ alignment_mode == "sentence" 或 use_sentence_pipeline=true → 機制 B (Path Y)
    └─ default                          →  Path Z (1-to-1)

╔═══════════════════════════════════════════════════════════════╗
║   Path Z (DEFAULT) — 1-to-1 translate                          ║
║                                                                ║
║   engine.translate(asr_segments, ...)                          ║
║      ↓                                                         ║
║   逐段 ASR fragment 餵 LLM                                      ║
║      ↓                                                         ║
║   LLM 對每段獨立譯（context 限喺呢段同 batch 鄰段）              ║
║      ↓                                                         ║
║   List[{en_text, zh_text, start, end}] —————— DONE ✅          ║
╚═══════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════╗
║   Path Y (OPT-IN) — Sentence Pipeline (機制 B)                  ║
║                                                                ║
║   ┌──────────────────────────────────────────────┐             ║
║   │ Step A: merge_to_sentences()                 │             ║
║   │  - _split_by_time_gaps (>1.5s 強制斷)         │             ║
║   │  - pySBD English segmenter 切句               │             ║
║   │  - 紀錄 word→seg 映射                         │             ║
║   └──────────────────────────────────────────────┘             ║
║      ↓                                                         ║
║   完整 EN sentence list (每段可能跨 1-N 原 ASR segment)          ║
║      ↓                                                         ║
║   ┌──────────────────────────────────────────────┐             ║
║   │ Step B: engine.translate(sentence_list)      │             ║
║   │  LLM 收到完整句，譯整句 ZH                    │             ║
║   └──────────────────────────────────────────────┘             ║
║      ↓                                                         ║
║   完整 ZH sentence list                                        ║
║      ↓                                                         ║
║   ┌──────────────────────────────────────────────┐             ║
║   │ Step C: redistribute_to_segments()           │             ║
║   │  按 EN word ratio 分 ZH char                  │             ║
║   │  + ±3 char 標點 snap                          │             ║
║   └──────────────────────────────────────────────┘             ║
║      ↓                                                         ║
║   List[{en_text, zh_text, start, end}] —————— DONE ✅          ║
╚═══════════════════════════════════════════════════════════════╝
        │
        ▼
[7] 💾 Save translations to registry
        │
        ▼
[8] User proofread → approve → render
```

---

## 🌏 PART 4 — 你嘅關鍵問題：ASR 揀 EN vs ZH 會唔會分別？

**會。而且差異好大。**

### 場景 A — ASR 揀英文 (`language: "en"`)

```
Whisper 出 EN text/segments
   ↓
機制 A:
  language_config: en.json
  max_words = 25, max_duration = 40
  Sentence regex: [.!?] ← 啱用，因為英文用呢啲標點
   ↓
output: EN segments，按 . ! ? 切割合理
```

✅ **機制 A 工作正常**

```
機制 B:
  pySBD English segmenter ← 啱用
  redistribute(EN words → ZH chars) ← 假設語言 pair: 英→中
```

✅ **機制 B 工作正常 (呢個 pipeline 就係為 EN→ZH 設計)**

### 場景 B — ASR 揀中文 (`language: "zh"`)

```
Whisper 出 ZH text/segments
   ↓
機制 A:
  language_config: zh.json
  max_words = 30, max_duration = 8
  Sentence regex: [.!?]  ⚠️ 用緊英文標點 detect 中文句尾
   ↓
output: 中文 segment 不會喺 「。」「！」「？」處切！
```

❌ **機制 A 喺中文 ASR 會 hard split — 因為 regex 死板硬係 `.!?`，唔識「。！？」**

睇返 source code (`segment_utils.py:8`):
```python
_SENTENCE_END_PATTERN = re.compile(r"[.!?]")
```

中文句末用 `。！？`（全形），完全唔 match。所以中文 ASR 出嚟，所有 segment 全部 hard-split，唔識揾自然句界。

更慘嘅問題：中文冇空白分 word。`text.split()` 對中文出嚟 → 每個 segment 變成「一整 chunk」(因為冇空白)，word_count 永遠係 1，**完全唔觸發切割**。

```python
words = text.split()   # 中文無空白 → words 永遠 = ["整段中文"]
word_count = 1         # 永遠係 1
needs_word_split = 1 > 30  # = False，永遠唔切
```

❌ **機制 A 對中文 ASR 完全失效**（split 邏輯依賴英文 word boundary）

```
機制 B (假設用):
  pySBD English segmenter 食入中文 → 識唔識切？
  pySBD 對非英文輸入會 fallback 但結果不可預期
  redistribute(EN words → ZH chars) ← 但 source 已經係 ZH，pipeline 設計上錯
```

❌ **機制 B 設計上唔支援 ZH source**：成個 pipeline 假設 source = EN，target = ZH。如果 ASR 揀中文，呢個 pipeline 係 mismatch — 你唔應該用 sentence pipeline。

---

### 結論：ASR 語言對 split 機制嘅影響

| 情境 | 機制 A | 機制 B |
|---|---|---|
| ASR=EN | ✅ 正常 | ✅ 正常 |
| ASR=ZH | ❌ 完全失效（`split()` + `[.!?]` 對中文無用） | ❌ 設計上唔支援 |
| ASR=JA | ❌ 失效（同 ZH 一樣） | ❌ 失效 |
| ASR=KO | ⚠️ 部分有效（韓文有空白）但標點唔啱 | ❌ 失效 |

**呢個係今日系統嘅一個 hidden bug** —— 雖然你 99% 用 EN ASR，但 zh.json 嘅 config 形同虛設。

---

## 🌐 PART 5 — 翻譯之後，邏輯機制有冇分別？

### 翻譯之後仲有冇 split / merge？

**冇。** Pipeline 完全 stop @ `redistribute_to_segments()`。

### 但係有 post_processor

`backend/translation/post_processor.py` 係 **validation 唔係 split**：

- **唔會切**任何 segment
- **唔會 merge**任何 segment
- 只係加 `flags`：
  - `[long]` — char count > MAX_SUBTITLE_CHARS (28)
  - `[review]` — char count > 40 (hallucination heuristic)

即係話：

```
翻譯完 → ZH 已經分好 segment (來自機制 A 或機制 B 嘅 segment 結構)
   ↓
post_processor 只係 inspect 並標 flag
   ↓
flag 顯示喺 UI 提醒用戶，但 segment 結構唔變
```

### 用戶手動編輯之後

當用戶 PATCH 一個 segment 嘅 zh_text，**冇任何 re-split 邏輯**。

例：用戶將「這是政府宣布的新政策措施」改成「政府宣布新政策」，segment timing 完全不變，char count 由 12 變 7，但 timing 仍佔該 segment 嘅原 duration。

---

## 🎨 PART 6 — Visual Summary

```
┌────────────────────────────────────────────────────────────────────┐
│              Split / Merge 機制喺 Pipeline 入面嘅 6 個位             │
└────────────────────────────────────────────────────────────────────┘

階段 1: ASR 🎤
  Whisper internal 切割（按 silence + token budget）
  ⚠️ 呢個係 Whisper 本身嘅切割（你冇 control）

階段 2: ASR 後處理 ✂️ ← 機制 A
  split_segments() 加碼切細
  ✅ EN 工作正常 / ❌ ZH KR JA 失效

階段 3: 翻譯前重組 🧩 ← 機制 B Step A (opt-in)
  merge_to_sentences() 合併做完整句
  ⚠️ 只支援 EN source，pySBD English

階段 4: LLM 翻譯 🤖
  逐 segment 或逐 sentence 調用 LLM
  LLM 內部冇知道 char limit

階段 5: 翻譯後重組 ✂️ ← 機制 B Step C (opt-in)
  redistribute_to_segments() 切返 ZH 落原 segment
  ⚠️ 純 ratio + 標點 snap，唔保證 char cap

階段 6: 標 flag 📋 ← post_processor
  inspect ZH char count
  >28 → [long] / >40 → [review]
  ❌ 唔會 re-split

階段 7: 用戶手動 ✏️
  完全唔影響 segment 結構
  Just zh_text 字面變
```

---

## 🔑 PART 7 — 直接答你嘅 4 個 question

| 問題 | 答案 |
|---|---|
| **Q1. 用咩模型？** | **A**: 純 regex + 算術，無 ML / **B**: pySBD (英文版 only) |
| **Q2. 係咪喺 ASR 入面做？** | **A**: ASR 之後立即跑（同檔案夾但唔喺 Whisper engine）/ **B**: 翻譯階段，opt-in 先有 |
| **Q3. Flow 同計法？** | A 先 → (registry 保存) → 用戶觸發翻譯 → B opt-in 先跑 (Step A: pySBD merge → Step B: LLM → Step C: ratio split) → post_processor 標 flag → 用戶手動 |
| **Q4. Diagram?** | 見 Part 3 + Part 6 |

### EN vs ZH ASR 嘅影響

| ASR 語言 | 機制 A 影響 | 機制 B 影響 |
|---|---|---|
| **EN** | ✅ 工作正常 | ✅ 工作正常（pipeline 為 EN→ZH 設計） |
| **ZH** | ❌ 完全失效（regex 唔識中文標點 + `.split()` 對冇空白語言失效） | ❌ pySBD 唔識中文，且 pipeline 假設 source=EN |

### 翻譯後嘅機制

| 階段 | 有冇 split/merge |
|---|---|
| Translation 後 (`post_processor`) | ❌ 純 inspect 標 flag |
| 用戶 PATCH | ❌ 完全唔影響 segment 結構 |
| Render | ❌ 直接用 timing + zh_text |

---

## 💡 PART 8 — 隱藏問題清單 (你下決定前要知)

呢 5 個 issue 係今日系統嘅 hidden bug / weakness：

### Issue 1: 機制 A 對中文 ASR 完全失效
- `text.split()` 對中文無效（冇空白）
- `[.!?]` regex 唔 match 中文標點
- 用戶設 `language: zh` 不會見到 segment 切割

### Issue 2: 機制 B 對中文 ASR 設計錯誤
- `_EN_SEGMENTER` hardcode 英文
- 整個 redistribute 邏輯假設 EN word ↔ ZH char
- 用戶設 `alignment_mode: "sentence"` + `language: zh` 會出意外

### Issue 3: 機制 A 嘅切割完全唔睇 char count
- 你已知道呢個

### Issue 4: 機制 B 嘅 redistribute 唔保證 ZH char cap
- 純 ratio + 3-char 標點 snap
- 即使 EN source cap 住，ZH 結果可能仍超

### Issue 5: 翻譯後冇 re-split 機制
- post_processor 只係標 flag
- 用戶要手動切（split segment 嘅 UI 唔知有冇？）

---

## ❓ 我等你決定再諗下一步

呢份分析開咗以下幾條問題俾你思考：

1. **你最常用 ASR=英文吧？** 如果係，機制 A 對中文失效嘅問題係未來事，可以暫時放低
2. **`use_sentence_pipeline` 你今日 default 係 false？** 如果係，咁機制 B 就唔係 daily 跑，root cause 主要喺 default 1-to-1 path
3. **Whisper 出嚟嘅 segment 平均幾大？** 你可以揀一個典型 file 睇下 `len(text)` 分佈，先決定 cap 設幾多。我可以寫個 script 跑分析
4. **Sentence pipeline 嘅 redistribute 係咪你想優化嘅核心？** 因為呢個係 EN→ZH 嘅 main path

呢 4 條答完，再決定點修都唔遲。

---

## Sources (in-repo)
- [backend/asr/segment_utils.py](backend/asr/segment_utils.py) — 機制 A 實現
- [backend/translation/sentence_pipeline.py](backend/translation/sentence_pipeline.py) — 機制 B 實現
- [backend/asr/whisper_engine.py](backend/asr/whisper_engine.py) — Whisper 直接呼叫
- [backend/config/languages/en.json](backend/config/languages/en.json) — 英文 cap config
- [backend/config/languages/zh.json](backend/config/languages/zh.json) — 中文 cap config (但實際無效)
- [backend/translation/post_processor.py](backend/translation/post_processor.py) — flag 標記 (唔切)
- [backend/app.py:464-472](backend/app.py#L464) — 機制 A 觸發點
- [backend/app.py:1085-1113](backend/app.py#L1085) — 機制 B 觸發點 (alignment_mode 路由)
