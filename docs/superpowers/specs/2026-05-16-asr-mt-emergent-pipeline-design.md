# v4.0 ASR + MT Emergent-Translation Pipeline — Design

**Status**: Research / Vision phase. NOT implementation-ready. No POC committed.
**Branch**: `chore/asr-mt-rearchitecture-research`
**Date**: 2026-05-16
**Supersedes**: bundled-profile architecture (v3.0 — v3.18)

---

## 0. 用法說明

呢份 doc 係 **vision-level design**，唔係 implementation spec。佢嘅作用：
- Capture 大架構改革嘅核心決定（6 個 design choice + 4 個 dimension lock）
- 列出 component 嘅 shape 同 schema sketch，但唔落 method signature / API contract
- 列 migration / breaking change / out-of-scope，等將來落 implementation plan 時有 reference
- 用作 stakeholder review 嘅單一 truth source

之後想實作時，要基於呢份 doc 落 multi-stage implementation plan（每個 stage 一份 detailed spec + plan），唔係直接 jump 落 code。

---

## 1. Background + Motivation

### 1.1 現狀（v3.18 為基線）

```
audio ──→ [Whisper ASR transcribe + same-lang] ──→ source-lang transcript
                                                            ↓
                                                  [Auto MT (cross-lang translate)]
                                                            ↓
                                                  [Optional Pass 2 enrich]
                                                            ↓
                                                  target-lang subtitle
```

- Profile bundle 包含 ASR config + MT config + font config，3 個 sub-block 綁喺一個 profile entity
- MT layer 有 6 個 pipeline mode：batched / single-segment / sentence_pipeline / alignment_pipeline (`[N]` marker) / Pass 2 enrich / glossary inject
- Alignment：靠 sentence-level merge + redistribute / LLM marker injection / time-proportion fallback 三層 rescue 邏輯，將 sentence-level 翻譯切返 ASR segment-level
- Glossary：v3.15 multilingual，injection 透過 MT prompt 注入，scan + LLM apply 兩階段

### 1.2 用戶想解決嘅 problem（已 lock）

**M2 — 對齊邏輯太複雜**：6 個 pipeline mode + 3 層 alignment rescue + word-level DTW，加埋 sentence_pipeline 嘅 `MAX_MERGE_GAP_SEC` time-gap guard、`merge_short_segments` 嘅 punctuation heuristic — 全部都係為咗解決「sentence-level 翻譯點對返 ASR segment-level」呢個 bridge problem。如果每個 stage 都 per-segment 1:1，呢啲 logic 完全多餘。

**M4 — Per-language tuning 唔靈活**：依家 source language 揀完 ASR profile 後，MT prompt + glossary + alignment_mode 全部 bundled 喺同一 profile 度。想要 「英文 audio 用 prompt A」+「粵語 audio 用 prompt B」就要起兩個 profile bundle，重複維護晒 ASR + font + font subtitle 配置。

**M5 — 架構太膠**：profile schema 有 20+ knob（embedding 喺 `asr` / `translation` / `font` block 入面），人手難 audit、難文檔、難 review。6 個 MT pipeline mode 全部存活，無 default 大家用 single-segment vs alignment-markers vs sentence_pipeline 嘅明確 guideline。

### 1.3 Reality check（驗證咗嘅 evidence）

之前以為 Whisper 永遠係 same-lang transcribe — **錯**。實證（2026-05-16，[file_id `ada91d4cfef3`](backend/data/registry.json)）：

| Source audio | Profile config | Whisper output |
|---|---|---|
| 英文音訊 (`The Winning Factor`) | `task="transcribe"` + `language="en"` | `Hi and welcome to The Winning Factor.`（official，high quality） |
| **同一條** 英文音訊 | `task="transcribe"` + **`language="zh"`** | **`大家好,歡迎來到《勝利的因素》。`**（**emergent translation**，普通話 style） |

**Emergent translation behaviour**：Whisper Large-v3 + `task=transcribe` + language hint ≠ audio actual language → decoder 出 language hint 對應嘅文字（並非 hallucination noise，係 semantically correct 跨語 transcription）。

Caveat：
- OpenAI Whisper paper + official docs **唔 endorse** 呢個 behaviour
- Output 偏 **Mandarin / Simplified style**（"我是" / "我們"，唔係 "我係" / "我哋"）
- 對 noisy audio / accent / 專名 嘅 reliability 未測，存在質量 cliff 風險
- 但用戶 acceptance：File 2 嘅 emergent output 已被判斷「質量對我嚟講算係非常之好」，後續粵語 / 廣播風格 polish 交畀 MT 接手

### 1.4 設計目標

1. **Cross-lang translation 完全由 ASR layer 透過 emergent transcription 完成** — Whisper 直出 target-lang transcript（普通話 style），唔再喺 MT 層做 cross-lang translation
2. **MT layer 純做 same-lang transformation** — 粵語 register shift / 書面語化 / 廣播風格 / 用詞統一 / 語氣轉換
3. **Glossary 變獨立 stage** — post-MT 階段，唔再注入 MT prompt
4. **Pipeline = linear stage chain**，每個 stage per-segment 1:1，砍走所有 sentence-level alignment rescue logic
5. **Profile 拆三類** — ASR profile / MT profile / Glossary 各自獨立 entity，自由 mix-and-match
6. **MT engine 收窄到一個** — qwen3.5-35b-a3b only，OpenRouter 同 Ollama curated cloud models 全砍

---

## 2. Architecture

### 2.1 Pipeline overview

```
audio file
   │
   ▼
[ASR Stage]                    ← Whisper engine，3 mode picker (見 §3.1)
   │ per-segment transcript (target lang)
   ▼
[MT Stage 1]                   ← per-segment same-lang transformation
   │ transformed text
   ▼
[MT Stage 2]
   │
   ▼
...
   │
   ▼
[MT Stage N]
   │
   ▼
[Glossary Stage]               ← multi-select + drag-sort substitute
   │
   ▼
final subtitle output
```

特性：
- **Linear chain**，唔分支 / 唔合併
- **單一 timeline**：ASR stage 鎖定 segment 邊界，後續 stage 永遠 per-segment 1:1 transform
- **冇 alignment problem**：因為每個 stage 嘅 input / output segment count 一定相等

### 2.2 與舊架構嘅對比

| Aspect | 舊（v3.18） | 新（v4.0） |
|---|---|---|
| 翻譯方式 | MT 做 cross-lang | ASR emergent transcribe 做 cross-lang |
| MT 角色 | Cross-lang translator + polish + glossary inject | 純 same-lang polish |
| Profile shape | 1 個 profile = ASR + MT + Font bundle | 4 個 entity：ASR profile / MT profile / Glossary / Pipeline |
| MT pipeline modes | 6 (batched / single / sentence / llm-markers / Pass2 / glossary inject) | 1 (per-segment same-lang transform) |
| Alignment | sentence_pipeline + alignment_pipeline + DTW word timestamps | 砍晒 — 每 stage 1:1 |
| Glossary 路徑 | Injected into MT prompt + apply endpoint two-phase | Standalone post-MT stage |
| MT engines | Ollama qwen / OpenRouter (Claude / GPT / Gemini / etc.) | Ollama qwen3.5-35b-a3b only |

### 2.3 砍走嘅 backend modules

- `backend/translation/alignment_pipeline.py`（完全廢除）
- `backend/translation/sentence_pipeline.py`（完全廢除）
- `backend/translation/openrouter_engine.py`（完全廢除，配 D 全砍）
- `backend/asr/segment_utils.py::merge_short_segments`（保留 `split_segments`）
- `backend/translation/post_processor.py` 嘅 sentence-level retry logic（可能保留 `[LONG]` / `[NEEDS REVIEW]` flag emission，但對齊 rescue 全砍）
- `backend/translation/ollama_engine.py` 嘅 `_translate_batch` / `_enrich_batch` / Pass 2 enrich orchestration（全部由 generic same-lang prompt invocation 取代）

---

## 3. Component Breakdown

### 3.1 ASR Profile

獨立 entity，命名：`backend/config/asr_profiles/<uuid>.json`

#### 3.1.1 Schema sketch

```jsonc
{
  "id": "asr-yue-broadcast-emergent",
  "name": "粵語廣播（emergent）",
  "description": "英文音訊 emergent 轉中文 transcript，普通話 style",
  "engine": "mlx-whisper",            // 固定 mlx-whisper / whisper（faster-whisper / openai-whisper 由 engine 內部選）
  "model_size": "large-v3",           // 鎖死 large-v3（v3.17 已收窄）
  "mode": "emergent-translate",        // ← 新 field, 3 options (見 §3.1.2)
  "language": "zh",                    // target text language (decoder 出嘅文字 lang)
  "word_timestamps": false,            // 默認 off (D9-a — 唔需要 word-level alignment)
  "initial_prompt": "以下係香港賽馬新聞...",  // 保留 v3.8 mechanism
  "condition_on_previous_text": false,  // 保留 v3.8 防 cascade
  "simplified_to_traditional": true,    // 保留 v3.8 OpenCC s2hk
  "device": "auto",
  "user_id": 5,                         // D6-a per-resource owner
  "created_at": 1715843200,
  "updated_at": 1715843200
}
```

#### 3.1.2 三 mode picker（D9-a 細化）

| `mode` value | Whisper `task` | language hint | Output |
|---|---|---|---|
| `"same-lang"` | `transcribe` | = audio actual lang | source-lang transcript（official）|
| `"emergent-translate"` | `transcribe` | ≠ audio actual lang | hint-lang transcript（**unofficial**，emergent translation） |
| `"translate-to-en"` | `translate` | (任何) | **永遠英文** transcript（official，舊式翻譯 mode） |

UI 對應：揀 `mode` 之後，`language` field semantic 自動切換 label：
- `same-lang` → "Audio language"
- `emergent-translate` → "Target text language（warning: emergent behaviour）"
- `translate-to-en` → `language` field disable，固定 EN output

#### 3.1.3 警告 UI（D9-c）

ASR profile editor 入面：
- 揀 `emergent-translate` mode 時，下方 banner：
  > ⚠️ 此 mode 利用 Whisper unofficial cross-lang transcription。Output 質量未經 OpenAI 保證，對 noisy audio / 重口音 / 專名 可能 fail。建議廣播 production 前人手 review。
- 揀 `translate-to-en` mode 時，下方 banner：
  > ℹ️ 此 mode 永遠 output 英文。如果你 audio 係英文，等同於 same-lang transcribe。

### 3.2 MT Profile

獨立 entity，命名：`backend/config/mt_profiles/<uuid>.json`

#### 3.2.1 Schema sketch

```jsonc
{
  "id": "mt-yue-register-shift",
  "name": "普通話 → 粵語書面語",
  "description": "將 ASR emergent 出嘅普通話 transcript 轉粵語書面語",
  "engine": "qwen3.5-35b-a3b",          // 鎖死，唔再 expose engine 揀
  "input_lang": "zh",                    // 接咩 lang 嘅輸入（用嚟做 routing + warning）
  "output_lang": "zh",                   // 出咩 lang（must == input_lang 因為 MT 純 same-lang）
  "system_prompt": "你係香港電視廣播嘅字幕翻譯員...",   // free-form prompt template
  "user_message_template": "請將以下普通話書面語轉粵語書面語：\n{text}",  // 接 {text} placeholder
  "batch_size": 1,                       // per-segment by default (砍 batched mode 但保留 batch_size 做 future-proof)
  "temperature": 0.1,
  "parallel_batches": 4,                 // worker concurrency
  "user_id": 5,
  "created_at": 1715843200,
  "updated_at": 1715843200
}
```

#### 3.2.2 預設 MT profile templates（factory）

新架構 ships 3 個 default MT profile 做 starter:

| Profile | Purpose | Anti-formulaic rule |
|---|---|---|
| `mt-yue-broadcast-style` | 普通話/書面 → 粵語廣播書面語 | "唔用同一連接詞模板" 之類 (沿用 v3.18 削減版) |
| `mt-broadcast-enrich` | 簡潔 → 廣播 enriched 風格 | 「保留原文所有修飾語」「2 行顯示空間 22-35 字」|
| `mt-glossary-prep` | 無 polish，純清理 markup / whitespace | 用作 glossary stage 前嘅 normalize 預處理 |

用戶可以自由建第四、第五個 MT profile，例如 `mt-formal-to-casual`、`mt-sports-broadcast`、`mt-drama-tone-adjust` 等。

#### 3.2.3 Per-stage prompt override（v3.18 C1 carry over）

File-level `prompt_overrides` 由原本 4-key flat dict 改為 per-stage map：

```jsonc
{
  "file_id": "abc123",
  "pipeline_overrides": {
    "stage_2": {                          // pipeline 嘅第二 stage（MT Stage 1）
      "system_prompt": "你嘅 custom prompt 落呢度...",
      "user_message_template": null     // null = 跟 MT profile default
    },
    "stage_3": {
      "system_prompt": null              // null = 跟 MT profile default
    }
  }
}
```

Resolver chain：file override → MT profile default → backend constant fallback。Backend constant 仲 ship 一份做 last-resort fallback。

### 3.3 Glossary Stage

完全 standalone post-MT stage，唔注入 MT prompt（與 v3.15 / v3.18 行為對比，呢個係 breaking change）。

#### 3.3.1 多 glossary 引用機制（B3）

```jsonc
{
  "pipeline_id": "broadcast-yue-default",
  "glossary_stage": {
    "enabled": true,
    "glossary_ids": [                     // multi-select, ordered
      "racing-terms-uuid",
      "broadcaster-names-uuid",
      "common-typos-uuid"
    ],
    "apply_order": "explicit",           // 用 array order，唔自動 alphabetical
    "apply_method": "string-match-then-llm"  // 先做 string substitute，剩餘 LLM smart replace
  }
}
```

#### 3.3.2 Drag-sort UI（D6-a）

- Proofread page 入面，glossary picker 係 reorderable list
- 拖拉 row 改 order
- UI hint：每個 glossary row 顯示 entry count + max term length
- 衝突警告：如果兩個 glossary 入面有 term 互相 substring（例如 `Mbappe` ⊂ `Mbappe Magic`），UI highlight 並提示「建議將 `Mbappe Magic` 排前」

### 3.4 Pipeline definition

新增 entity，命名：`backend/config/pipelines/<uuid>.json`

#### 3.4.1 Schema sketch

```jsonc
{
  "id": "pipeline-yue-broadcast-default",
  "name": "粵語廣播（預設）",
  "description": "英文 audio → emergent 中文 → 粵語廣播風格 + glossary",
  "asr_profile_id": "asr-yue-broadcast-emergent",
  "mt_stages": [                          // ordered, linear chain
    "mt-yue-broadcast-style",             // MT profile id
    "mt-broadcast-enrich"
  ],
  "glossary_stage": {
    "enabled": true,
    "glossary_ids": ["racing-terms-uuid"],
    "apply_order": "explicit",
    "apply_method": "string-match-then-llm"
  },
  "font_config": {                        // 仍然係 pipeline-level
    "family": "Noto Sans TC",
    "size": 35,
    "color": "#ffffff",
    "outline_color": "#000000",
    "outline_width": 2,
    "margin_bottom": 40,
    "subtitle_source": "auto",            // 暫保留 (但 enum 要 generalize 見 §6.5)
    "bilingual_order": "target_top"       // 改名以反映新概念
  },
  "user_id": 5,                           // D6-a
  "created_at": 1715843200,
  "updated_at": 1715843200
}
```

#### 3.4.2 D7-c 混合操作模式

兩個方式建 / 用 Pipeline：

1. **Pre-saved**：用戶 dashboard 揀「Broadcast 粵語預設」一個 pipeline，所有 stage 一次 commit
2. **Step-by-step**：先揀 ASR profile 跑 → proofread page 入面 add MT stage 1 → 跑 → add stage 2 → 跑 → add glossary stage → 跑 → 任何 stage 可 re-run / remove / reorder

第二個方式之下，**file 自帶一個 "ephemeral pipeline"**（即係 file 嘅 pipeline 配置由 user 喺 proofread page 一步步砌出來，可以中途 save 做 named pipeline）。

---

## 4. Pipeline Runner Flow

### 4.1 Stage execution contract

每個 stage（ASR / MT / Glossary）implement 同一 interface：

```python
class PipelineStage(ABC):
    def run(
        self,
        segments_in: List[Segment],    # per-segment input
        context: PipelineContext        # file, user, pipeline, etc.
    ) -> List[Segment]:
        """Per-segment 1:1 transform. len(segments_in) == len(segments_out)."""
```

- **Segment count invariant**：所有 stage 必須遵守 input/output 同段數
- **Timeline invariant**：所有 stage 維持 `start` / `end` 不變（ASR 鎖定，後續純改 text）
- **Word timestamps 屬可選**：只有 ASR stage word_timestamps=true 時有 `words` field，後續 stage 直接 pass-through

### 4.2 Per-stage output persistence

File registry 每 stage output 都儲存（供 proofread review + per-stage re-run）：

```jsonc
{
  "file_id": "abc123",
  "pipeline_id": "pipeline-yue-broadcast-default",
  "stage_outputs": [
    {
      "stage_index": 0,
      "stage_type": "asr",
      "stage_ref": "asr-yue-broadcast-emergent",
      "status": "done",
      "ran_at": 1715843200,
      "duration_seconds": 67.3,
      "segments": [/* per-segment text + timing + optional words */]
    },
    {
      "stage_index": 1,
      "stage_type": "mt",
      "stage_ref": "mt-yue-broadcast-style",
      "status": "done",
      "ran_at": 1715843290,
      "duration_seconds": 42.1,
      "segments": [/* transformed text */]
    },
    {
      "stage_index": 2,
      "stage_type": "glossary",
      "stage_ref": "glossary-stage-inline-config",
      "status": "done",
      "ran_at": 1715843320,
      "duration_seconds": 5.2,
      "segments": [/* substituted text + applied_terms metadata */]
    }
  ],
  "current_stage_index": 2,                 // 用戶喺 proofread page 編輯緊嘅 stage
  "approval": {                              // approval 仍係 per-segment
    "approved": [true, true, false, ...],
    "approved_stage_index": 2                // approval 對應邊個 stage 嘅 output
  }
}
```

### 4.3 Re-run semantics

- **Re-run individual stage**：用戶喺 proofread page click 某 stage 嘅 "Re-run"，系統 truncate 該 stage 之後嘅 `stage_outputs`，重新跑該 stage（input 用上一個 stage 嘅 output），然後 cascade 跑後續 stage
- **Edit stage output**：用戶 PATCH 某 stage 嘅 segment text，呢個變成新嘅 `stage_outputs[i].segments`，下游 stage 自動 invalidate（mark `needs_rerun`）
- **Approval reset**：任何上游 stage 嘅 edit 或 re-run，approval 全部 reset

---

## 5. Frontend UI Shape

### 5.1 Dashboard

- 上傳 file 入口：兩個 mode 切換 tab
  - **Tab A — Quick**：揀 saved pipeline，一次 commit
  - **Tab B — Manual**：揀 ASR profile only，跑完轉 proofread page 自己砌
- File 卡顯示 pipeline name + stage progress dot（例如 ●●●○ = 3/4 stage done）

### 5.2 Proofread page 重設計

```
┌────────────────────────────────────────────────────────────────────┐
│ [Video preview]                    │  Stage chain (left rail)        │
│                                    │  ┌───────────────────────┐      │
│                                    │  │ ① ASR: yue-emergent ✅│←     │
│                                    │  │   276 seg • 67s        │      │
│                                    │  ├───────────────────────┤      │
│                                    │  │ ② MT: broadcast-style ✅      │
│                                    │  │   276 seg • 42s        │      │
│                                    │  ├───────────────────────┤      │
│                                    │  │ ③ Glossary ✅          │      │
│                                    │  │   8 terms applied      │      │
│                                    │  ├───────────────────────┤      │
│                                    │  │ + Add stage           │      │
│                                    │  └───────────────────────┘      │
├────────────────────────────────────────────────────────────────────┤
│ Editing: ③ Glossary output (final)                                  │
│                                                                      │
│ ┌──────────────────┬──────────────────────────────┬──────────┐      │
│ │ Time             │ Text (current stage)         │ Approve  │      │
│ ├──────────────────┼──────────────────────────────┼──────────┤      │
│ │ 00:00.0–00:02.1  │ 各位觀眾大家好...            │ [✓]      │      │
│ │ ...                                                                 │
│ └──────────────────┴──────────────────────────────┴──────────┘      │
│                                                                      │
│ [↺ Compare with ① ASR]  [↺ Compare with ② MT]  [⚙ Per-stage prompt override] │
└────────────────────────────────────────────────────────────────────┘
```

- 左 rail 顯示 stage chain，每 stage 可 click 切換 active editing target
- 主編輯區顯示當前 active stage 嘅 segment table
- **Compare mode**：side-by-side diff 對比兩個 stage 嘅 segment text
- **Per-stage prompt override panel**：v3.18 carry over，但 textarea 對應 active stage 嘅 MT profile prompt（唔係 v3.18 嘅 4-key flat structure）
- **Glossary picker panel**：drag-sort UI 喺 glossary stage active 時顯示
- Re-run button：每個 stage row 都有

### 5.3 Pipeline editor

獨立 page (`/pipelines.html`，admin + owner 可 access)：
- 一個 pipeline 一行
- 內部 stage chain 可拖拉
- ASR profile + MT profile + Glossary 三個 dropdown 互相獨立揀
- Save / Duplicate / Delete

---

## 6. Backend Changes Summary

### 6.1 新 modules

- `backend/asr_profiles.py` — ASR Profile CRUD（owner 機制 D6-a）
- `backend/mt_profiles.py` — MT Profile CRUD
- `backend/pipelines.py` — Pipeline CRUD
- `backend/pipeline_runner.py` — Linear stage executor
- `backend/stages/asr_stage.py` — Wraps ASR engine call，emits per-segment output
- `backend/stages/mt_stage.py` — Wraps qwen3.5 call per segment
- `backend/stages/glossary_stage.py` — Standalone glossary apply（merge v3.15 scan + v3.0 apply 兩階段邏輯）

### 6.2 改 modules

- `backend/asr/__init__.py` — 加 `mode` field handling（dispatching `task` + `language` based on mode value）
- `backend/asr/whisper_engine.py` + `mlx_whisper_engine.py` — `transcribe()` 接受 `mode` parameter
- `backend/translation/__init__.py` — ABC 改為 `transform()`（強調 same-lang），唔再叫 `translate()`
- `backend/translation/ollama_engine.py` — 大幅瘦身，剩 per-segment same-lang transform
- `backend/app.py` — 新 API endpoints, 舊 `/api/transcribe` 改為 `/api/pipelines/run`, 舊 `/api/translate` 廢除（由 pipeline runner 內部處理）
- `backend/glossary.py` — 維持 v3.15 multilingual schema，但 entries 唔再注入 MT prompt
- `backend/profiles.py` — **降級為 legacy compat layer**（migration 期間提供舊 API 兼容性，最終 deprecate）

### 6.3 砍 modules

見 §2.3。

### 6.4 新 REST endpoints

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/asr_profiles` | List / Create ASR profile |
| GET / PATCH / DELETE | `/api/asr_profiles/<id>` | CRUD |
| GET / POST | `/api/mt_profiles` | List / Create MT profile |
| GET / PATCH / DELETE | `/api/mt_profiles/<id>` | CRUD |
| GET / POST | `/api/pipelines` | List / Create |
| GET / PATCH / DELETE | `/api/pipelines/<id>` | CRUD |
| POST | `/api/pipelines/<id>/run?file_id=<fid>` | Enqueue pipeline run for a file |
| POST | `/api/files/<fid>/stages/<idx>/rerun` | Re-run individual stage |
| PATCH | `/api/files/<fid>/stages/<idx>/segments/<seg>` | Edit per-stage segment text |
| POST | `/api/files/<fid>/pipeline_overrides` | Set file-level stage overrides |

### 6.5 字幕設定 (subtitle_source / bilingual_order) generalize

依家硬編碼 `{auto, en, zh, bilingual}` + `{en_top, zh_top}` 改為：

| 舊 enum | 新 enum |
|---|---|
| `subtitle_source: "en"` | `subtitle_source: "source"`（ASR stage output） |
| `subtitle_source: "zh"` | `subtitle_source: "target"`（pipeline final output） |
| `subtitle_source: "bilingual"` | `subtitle_source: "bilingual"`（不變） |
| `bilingual_order: "en_top"` | `bilingual_order: "source_top"` |
| `bilingual_order: "zh_top"` | `bilingual_order: "target_top"` |

注意：`source` / `target` 唔再對應特定 language code，而係對應 pipeline 入面嘅 stage（source = ASR output、target = pipeline final）。

### 6.6 Segment schema rename

`en_text` / `zh_text` 字段 deprecated。新 segment shape：

```jsonc
{
  "start": 0.0,
  "end": 2.1,
  "stage_outputs": {
    "asr": "大家好,歡迎來到《勝利的因素》。",
    "mt_1": "各位觀眾大家好，熱烈歡迎...",
    "mt_2": "各位觀眾大家好，熱烈歡迎蒞臨...",
    "glossary": "各位觀眾大家好，熱烈歡迎蒞臨《致勝因素》..."
  },
  "approved": true,
  "flags": []
}
```

Frontend 讀邊個 stage 嘅 text 喺 file metadata 揀緊嘅 `current_stage_index`。

---

## 7. Ownership Model (D6-a)

每類 resource 各自獨立 ownership / sharing，與 v3.11 起嘅 owner 機制一致：

| Resource | `user_id` semantics | Visibility | Edit |
|---|---|---|---|
| ASR profile | null = shared / int = owner | admin OR owner OR shared(null) | admin OR owner |
| MT profile | 同上 | 同上 | 同上 |
| Glossary | 同上 | 同上 | 同上 |
| Pipeline | 同上 | 同上 | 同上 |

**Cascade visibility check**：當用戶開 pipeline，系統 cascade 驗證每個 reference 出嚟嘅 sub-resource（ASR profile / MT profile / glossary）都係該 user 可見。否則 pipeline 顯示為 broken，UI 提示「⚠️ 此 pipeline reference 嘅 sub-resource (XXX) 你冇權限存取，請聯絡管理員」。

---

## 8. Migration Plan (E1 auto-split)

依家有 6 個 existing profile bundle。Migration script 將每個 bundle 拆三件：

```
原 profile: prod-default
  ↓
asr_profile: prod-default-asr  (從原 .asr block 拆出)
mt_profile:  prod-default-mt   (從原 .translation block 拆出)
pipeline:    prod-default      (引用上面兩個 + 保留 .font block)
```

對應 mapping：
- `profile.asr.engine + .language + ...` → `asr_profile.engine + .language + ...`
- `profile.asr.mode` 自動推斷：v3.18 之前 `task` 寫死 `transcribe`，所以全部 set `mode="same-lang"`（保守，唔自動 enable emergent）
- `profile.translation.engine + .style + ...` → `mt_profile.engine + .system_prompt + ...`
- `profile.translation.alignment_mode / .translation_passes / .use_sentence_pipeline` → **drop**（新架構 single-mode）
- `profile.translation.glossary_id` → `pipeline.glossary_stage.glossary_ids = [<id>]`（single-element array）
- `profile.translation.prompt_overrides`（profile-level）→ `mt_profile.system_prompt` override
- `profile.font` → `pipeline.font_config`

File registry migration：
- Existing `file.profile_id` → `file.pipeline_id`（指向新 split pipeline）
- Existing `file.segments[].text` → `file.stage_outputs[asr][].text`
- Existing `file.translations[].zh_text` → `file.stage_outputs[mt_1][].text`
- Existing `file.translations[].flags` → 保留，attach 到對應 stage output
- Existing `file.prompt_overrides`（v3.18 file-level）→ `file.pipeline_overrides.stage_2`（assume MT 係 stage 2）

Migration script 必須 idempotent + reversible（一個 `--dry-run` flag 預覽 changes、一個 `--rollback` flag 回去）。

---

## 9. CLAUDE.md Changes (D8-a)

### 9.1 完全刪走嘅 section

- **Validation-First Mode（修改 ASR / MT 必須遵守）** — 完整 section（包括 workflow 4 步、validation tracker 路徑、之前累積 evidence 列表）
- **Verification Gates 段** 嘅 4-gate verification（保留 commit-message / docs update 嘅鼓勵，砍走 mandatory 4-gate）

### 9.2 重寫嘅 section

- **Engine Architecture**：由「ASR 同 Translation 引擎完全解耦，透過 ABC + Factory 模式」改為「Pipeline 由 3 種 stage 組成，每 stage 一個 ABC + Factory」
- **REST endpoints 表**：完全更新做 §6.4
- **Architecture / Pipeline Flow**：完全更新 diagram + module 描述

### 9.3 新增嘅 section

- **Pipeline conventions** 段：linear chain invariant、per-segment 1:1、stage interface
- **Emergent translation warning** 段：寫清楚呢個 unofficial behaviour 嘅 caveat，畀未來開發者知

### 9.4 Completed Features

- v3.18 之前嘅 entry 保留，作為 history reference
- v4.0 entry 起點：merge 之後寫一個 "v4.0 — ASR + MT Pipeline Rearchitecture" condensed summary
- 中間嘅 incremental version（v3.19 / v3.20 ...）係咪需要 — 視乎落 implementation plan 後拆嘅 phase 數

---

## 10. Risk Register

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Emergent translation 對 noisy / accented / 專名 audio fail | M | H | (1) Per-pipeline 可加 fallback：if emergent quality flag (TBD heuristic) 觸發，自動 re-run with `same-lang` mode + MT translate path; (2) UI 強制 human review approval gate before render |
| 簡體 → 繁體 + 普通話 → 粵語 雙重 polish 質量唔達標 | M | H | (1) Ship 多個 MT profile 試唔同 prompt; (2) 用戶喺 proofread page 可逐 segment 改; (3) v3.18 file-level prompt override carry over |
| 砍 alignment_pipeline + sentence_pipeline 後，individual segment 太短 / 太長 嘅 ASR boundary 處理失控 | L | M | 保留 `split_segments` + 廢除 `merge_short_segments`（後者係 sentence-level 邏輯），讓 ASR 出嘅 segment 直接 pass-through |
| Whisper emergent mode 喺某啲 mlx-whisper version 變化（model weights / token vocab 改） | L | H | Pin model version `mlx-community/whisper-large-v3-mlx`，CI 加 reference clip emergent translation snapshot test |
| Migration 失敗令現有 file 無法 access | L | H | (1) Migration script idempotent + `--dry-run` + `--rollback`; (2) Backup registry 喺 migration 前；(3) Legacy `profiles.py` 保留為 compat layer |
| Glossary stage 唔再 inject MT prompt 導致 hallucination 機會升 | M | M | Glossary stage 用 string-match 先掃，剩下 ambiguous case 再 LLM smart replace；總體比 inject-then-pray reliable |
| OpenRouter 砍走後，未來想用 cloud 模型 reach 唔到 | L | L | 砍走嘅 code 喺 git history reachable；未來想 reintroduce 加返一個 MT engine 就得 |

---

## 11. Out-of-Scope (deferred)

以下野**唔屬於** v4.0 scope：

- **Bilingual ASR output**：v4.0 ASR stage 只 output 一個 lang，唔同時出 source + target
- **Per-pipeline 多 audio input 路徑**：每個 file 一個 ASR stage
- **DAG / branching pipeline**：A2 已 reject，留 A1 linear only
- **Auto-detect source language 同 trigger ASR fallback**：用戶 explicit 揀 ASR profile
- **Real-time / streaming pipeline**：v2.0 streaming mode 已 deprecate
- **Glossary 雙向 mapping（target → source）**：v3.15 single-direction maintained
- **MT engine 多元化**：v4.0 鎖死 qwen3.5-35b，未來 reintroduce OpenRouter / Claude / GPT 為 v4.x 改動
- **Custom Whisper model fine-tune**：Large-v3 only

---

## 12. Open Questions（未答嘅嘢）

呢啲 question **唔需要喺 design 階段答**，但 implementation plan 階段必須處理：

1. **Emergent quality flag heuristic**：用咩 metric detect emergent transcription quality dropped？(e.g., Whisper avg log_prob、segment text length distribution、character set 比例) — implementation 時定 thresholds
2. **Stage parallel execution**：N MT stage chain 入面，每 stage 內部係 per-segment parallel (parallel_batches)，但 stage 之間 strict sequential。Confirm？
3. **Pipeline run cancellation granularity**：用戶 cancel pipeline 中途，已 done 嘅 stage 嘅 output 留低 vs roll back？建議留低，user 可以 selective re-run。
4. **MT profile system_prompt 模板嘅 i18n**：依家 ship 嘅 3 個 default 全部繁體中文。Future 用戶起 EN→EN polish profile 點處理？(prompt 用咩 lang 寫不影響 MT 行為，由用戶決定)
5. **File-level `pipeline_overrides`**：當 user override `stage_2.system_prompt`，呢個 override 跟 file 還是跟 (file, pipeline) pair？例如同一 file 將來用第二個 pipeline 跑，override 帶過去定 reset？建議跟 (file, pipeline_id) pair。
6. **ASR profile `mode` 同 `language` 嘅 implicit-explicit boundary**：揀 `mode="emergent-translate"` + `language="zh"` + audio 確實係中文，會 trigger same-lang transcribe 行為（emergent fallback）。UI 點處理？建議跑 audio language detection (Whisper 第一 30s) → 同 language hint 比較 → 提示用戶。
7. **Per-stage word_timestamps 需求**：v4.0 砍 alignment_pipeline 之後 word_timestamps 仲有冇 use case？(可能仲有：accurate caption positioning during render) — implementation 時 evaluate。

---

## 13. Approval Status

- [x] §1-12 vision lock，6 個 design choice + 4 個 dimension 確認
- [ ] User review 呢份 design doc
- [ ] (deferred) Implementation plan multi-phase split + 詳細 spec per phase
- [ ] (deferred) Each phase 落 implementation 前再 update vision-level doc
