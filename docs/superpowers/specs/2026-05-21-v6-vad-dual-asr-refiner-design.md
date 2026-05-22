# v6 VAD + Dual-ASR + Refiner Design Spec

**Date:** 2026-05-21
**Branch (not yet created):** `feat/v6-vad-dual-asr-refiner` (branch off `feat/frontend-redesign`)
**Status:** DESIGN READY — awaiting implementation

---

## 1. Problem Motivation

### Why v5-A5 is not enough for Cantonese broadcast audio

v5-A5 introduced a Refiner-as-judge model: mlx-whisper (primary) + qwen3-asr (secondary, optional) → Refiner LLM decides keep/drop/correct per segment. On the Cantonese broadcast test files (賽馬賽後特輯, 4 min), the following systematic failure modes remain:

| Failure mode | v5-A5 outcome | Root cause |
|---|---|---|
| Cascade hallucinations (3+ zero-duration identical segs at boundary) | Refiner drops 2 of 3 — but fires the LLM 3× for what should be a mechanical dedup | Whisper primary output contains hallucinations that shouldn't reach the refiner at all |
| Tail English orphan (`"vowels"` at 264.6s, 3.12s after last Chinese) | Refiner may drop if secondary confirms silence — unreliable at boundary | Structural Whisper artifact, not a content judgment |
| Entity name accuracy | Whisper mis-transcribes Cantonese names e.g. 袁幸堯, 史滕雷, HIGHLAND BLINK | Whisper large-v3 trained heavily on Mandarin; rare HK names mis-recognized |
| Cantonese particle preservation (嘅/咗/啦/喺/嘢) | Variable — refiner may over-Mandarin-ize | Whisper baseline text already Mandarin-dominant |
| Segment count mismatch (primary 90 vs refiner out ~83) | `_persist_by_lang` uses `source_segments` length as index anchor; length drop causes `by_lang[i]` index off-by-one for later segments | Structural — refiner drops collapse non-trivially with the by_lang indexing scheme |

### v6 hypothesis

Replace the "garbage-in, LLM-cleans-up" pattern with **clean ASR at source**:

1. **Silero VAD pre-segmentation** — eliminates silence / music regions before any ASR engine sees the audio. Cascade hallucinations and orphan artifacts arise when Whisper is fed long continuous audio with silence gaps. Feeding only speech regions eliminates the root cause mechanically (0.8s runtime, proven on prototype).

2. **qwen3-asr as content authority** — qwen3-asr-1.7B (MLX) run per-VAD-region achieves 100% entity name accuracy on Cantonese broadcast audio in prototype (袁幸堯, 史滕雷, HIGHLAND BLINK all correct). Text output is the sole authority — Whisper text is discarded entirely.

3. **mlx-whisper as time-grid reference only** — mlx-whisper large-v3 run on full audio produces broadcast-quality 2–3 second subtitle boundaries (proven in production). Its time boundaries are used to split qwen3's full-transcript mega-chunks into subtitle-sized segments. mlx text is ignored; only `[start, end]` is consumed.

4. **Stage 2 time-anchored merge** — pure-Python algorithm assigns qwen3 char-timestamps to mlx time slots by midpoint containment. Empty slots (mlx hallucinations) collapse into the preceding kept segment. Produces ~80 clean subtitle-sized segments in < 1s.

5. **Refiner role transformation** — with hallucination / cascade / orphan artifacts eliminated upstream, the Refiner's prompt is simplified to its primary mission: broadcast register polish. It also fixes mid-word cuts from Stage 2 (adjacent slot boundaries may split a Chinese word). No more cascade/orphan/hallucination detection rules in the prompt.

### Prototype validation summary

| Stage | Validated | Evidence file |
|---|---|---|
| Stage 0: Silero VAD | ✅ | `/tmp/v6_prototype_stage1a_v2.json` — 28 regions, 91.3% speech, 0.8s runtime |
| Stage 1A: qwen3 per region | ✅ | Same file — 28 region transcripts, 1066 char-level timestamps, 100% entity accuracy |
| Stage 1B: mlx full audio | ✅ | `backend/data/registry.json` → `aec2e8f98789.stage_outputs[0]` — 90 segs |
| Stage 2: time-anchored merge | ✅ | `/tmp/v6_stage2_result.json` — 86 raw → 84 final collapsed segs |
| Stage 3: Refiner (v6 prompt) | ⏳ | Not yet prototyped — prompt designed in this spec |

---

## 2. Architecture Diagram

```
Audio (mp4 / mxf)
    │
    ▼  FFmpeg decode → 16kHz mono float32
    │
    ▼
[Stage 0] Silero VAD pre-segmentation
    │  Engine:   silero-vad 6.2.1 (PyTorch — already in backend/venv py3.9)
    │  Input:    full audio as torch.Tensor (16kHz)
    │  Output:   28–50 speech regions [(start_sec, end_sec)]
    │  Runtime:  ~0.8s
    │  VAD params: threshold=0.5, min_speech_duration_ms=250,
    │              max_speech_duration_s=15, min_silence_duration_ms=500,
    │              speech_pad_ms=200
    │  Purpose:  Eliminate Whisper cascade/orphan/hallucination at root
    │
    ├──────────────────────────────────────────────────┐
    │                                                  │
    ▼                                                  ▼
[Stage 1A] qwen3-asr per VAD region               [Stage 1B] mlx-whisper full audio
    │  Engine: mlx_qwen3_asr v0.3.5                   │  Engine: mlx-whisper large-v3 (existing)
    │  Subprocess: py3.11 venv at                     │  Run on:  full undivided audio
    │    backend/scripts/v5_prototype/venv_qwen/      │  Output:  ~90 segs with 2-3s boundaries
    │  Config: language="Chinese",                    │  CRITICAL: ONLY [start,end] used downstream
    │    context=<entity names>,                      │           mlx TEXT IS DISCARDED
    │    return_timestamps=True,                      │  Runtime: ~25s
    │    return_chunks=True,                          │  Purpose: provide fine-grained subtitle-
    │    post_s2hk=True (OpenCC s2hk)                │           sized time windows
    │  Output per region: full_text +                 │
    │    char-level [{start,end,text}]                │
    │  All regions: ~1066 char-timestamps total       │
    │  Runtime: ~40s for 4-min audio                  │
    │  Content authority: entity accuracy 100%        │
    │  Zero cascade / orphan artifacts                │
    │                                                  │
    └──────────────────┬───────────────────────────────┘
    NOTE: initial release executes Stage 1A → Stage 1B sequentially (~66s total).
          Parallel execution (1A ∥ 1B) is deferred to a future optimisation pass.
                       │
                       ▼
[Stage 2] Time-Anchored Merge
    │  Input A:  mlx-whisper 90 segs (time grid only — text ignored)
    │  Input B:  qwen3 char-level segments (absolute time, after region offset adjustment)
    │  Algorithm:
    │    for each mlx slot [m_start, m_end):
    │      chars = [c for c in qwen3_chars if m_start <= midpoint(c) < m_end]
    │      text = ''.join(c.text for c in chars)
    │    post-process: drop empty slots (mlx hallucinations);
    │                  extend prev kept slot's end to absorb dropped timecode
    │  Output: ~84 subtitle-sized segments with qwen3 text + mlx boundaries
    │  Runtime: < 1s (pure Python)
    │
    │  KNOWN Stage 2 artifacts passed to Stage 3 for fixing:
    │    - Mid-word cuts: mlx slot boundary cuts mid-Chinese-word
    │      (e.g. 「...時間  |  跑...」 → slot N ends with 「間」,
    │       slot N+1 starts with 「跑」 — correct word is 「時間」 at slot N)
    │    - First-character missing: when mlx boundary falls just before
    │      a qwen3 char's midpoint, first char falls to prior slot
    │
    ▼
[Stage 3] Refiner LLM
    │  Engine: qwen3.5:35b-a3b-mlx-bf16 via Ollama (or OpenRouter equivalent)
    │  Input:  Stage 2 output (~84 segs)
    │  Context: target seg + ±5s primary neighbors (no secondary — qwen3 is sole authority)
    │  Primary task: broadcast register polish
    │  NEW secondary task: fix mid-word cuts from Stage 2
    │  DROPPED from prompt: cascade / orphan / hallucination detection rules
    │                        (VAD + qwen3 have eliminated these at source)
    │  Output: {action: "keep", text: polished_text} per seg
    │  Persist: refiner output array length = translations array length
    │           (structurally fixes v5-A5 by_lang index misalignment)
    │  Runtime: ~60s for ~84 segs at ~0.7s/seg
    │
    ▼
[Stage 4] Translator (unchanged from v5-A5)
    │  When source_lang == target_lang (Cantonese → zh only): trivially skip
    │  When cross-lingual: use LLMTranslator (v5-A2 code path, unchanged)
    │
    ▼
[Persist] v5 by_lang schema (unchanged)
    │  translations[i] = {idx, start, end, source_lang, source_text, by_lang}
    │  Proofread page SubtitleOverlay: uses translations[i].start / .end directly
    │  No frontend schema changes needed
```

---

## 3. Per-Stage Detail

### Stage 0: Silero VAD

**File:** `backend/stages/v6/silero_vad_stage.py`

| Field | Value |
|---|---|
| Engine | silero-vad 6.2.1 (PyTorch); package already in `backend/venv` — imported as `from silero_vad import get_speech_timestamps, load_silero_vad` |
| Input | raw audio path (mp4 / mxf / wav) |
| Output | `[{start: float, end: float}]` — absolute seconds, speech regions only |
| VAD params | `threshold=0.5, min_speech_duration_ms=250, max_speech_duration_s=15, min_silence_duration_ms=500, speech_pad_ms=200` |
| Runtime budget | ≤ 2s for any audio ≤ 30 min |
| Quality target | ≤ 5% speech dropped (tail-pad 200ms already accounts for clipped consonants) |

**Audio loading:** FFmpeg subprocess → 16kHz mono float32 (`-f f32le`). Same pattern as `prototype_vad_qwen3.py::load_audio_via_ffmpeg`.

**Stage shape:** `PipelineStage` ABC; `stage_type = "vad"`; `transform(segments_in, context)` ignores `segments_in` (reads audio from `context.audio_path`).

**Output format:** Each region is `{start: float, end: float}`. Stage persists via standard `_persist_stage_output`.

**Config fields (profile JSON):**
```json
{
  "vad_threshold": 0.5,
  "min_speech_duration_ms": 250,
  "max_speech_duration_s": 15,
  "min_silence_duration_ms": 500,
  "speech_pad_ms": 200
}
```

---

### Stage 1A: qwen3-asr per VAD region (content authority)

**File:** `backend/stages/v6/qwen3_per_region_stage.py`
**Engine wrapper:** `backend/engines/transcribe/qwen3_vad_engine.py`

| Field | Value |
|---|---|
| Engine | mlx-qwen3-asr v0.3.5 (Qwen/Qwen3-ASR-1.7B) — in py3.11 venv at `backend/scripts/v5_prototype/venv_qwen/` |
| Subprocess script | `backend/scripts/v5_prototype/qwen3_vad_subprocess.py` (existing, no changes needed) |
| Config | `language="Chinese"`, `context=<entity_names>`, `return_timestamps=True`, `return_chunks=True`, `post_s2hk=True` |
| Input | List of VAD regions from Stage 0 + audio path |
| Output | Flat char-level segments: `[{start: float, end: float, text: str}]` — absolute seconds after region offset adjustment |
| Runtime budget | ≤ 60s for 4-min audio (observed: ~40s) |
| Quality target | 100% entity name accuracy on HK broadcast names; 0 cascade / orphan artifacts |

**Region slicing:** Audio is decoded to float32 numpy array; each region is sliced by sample index (`start_sample = int(r.start * 16000)`), written as temp WAV via `soundfile.write`. Temp dir cleaned up after subprocess completes.

**Subprocess protocol:** Single batch call to `qwen3_vad_subprocess.py` with all regions in one JSON payload (same protocol as `prototype_vad_qwen3.py::call_qwen3_subprocess`). Returns per-region `{region_idx, region_start, region_end, full_text, chunks, segments, runtime_sec, error}`.

**Absolute-time adjustment:** Each chunk/segment `start` and `end` is `region_offset + relative_time`. OpenCC s2hk applied inside subprocess.

**Engine class shape:**
```python
class Qwen3VadEngine:
    def transcribe_regions(
        self, audio_path: str, vad_regions: List[dict],
        language: str = "Chinese", context: str = "",
        post_s2hk: bool = True
    ) -> List[dict]:
        # Returns flat list of {start, end, text} — absolute time
```

**Context (entity names) resolution:**

The `context` string passed to qwen3-asr is resolved at runtime with the following priority:

1. **Per-file override** (`file_registry[fid]["prompt_overrides"]["qwen3_context"]`) — set via PATCH `/api/files/<id>` with `{ "prompt_overrides": { "qwen3_context": "..." } }`.
2. **Pipeline default** (`pipeline["qwen3_asr"]["context"]`) — set in the pipeline JSON at creation time.
3. **Empty string** — if neither is set; qwen3 runs without domain context hints.

`_run_v6()` resolves this before instantiating `Qwen3PerRegionStage`:
```python
file_qwen3_context = (
    file_entry.get("prompt_overrides", {}).get("qwen3_context") or ""
)
pipeline_qwen3_context = self._pipeline.get("qwen3_asr", {}).get("context") or ""
resolved_context = file_qwen3_context or pipeline_qwen3_context or ""
```

---

### Stage 1B: mlx-whisper full audio (time-grid reference)

**CRITICAL DESIGN DECISION: mlx-whisper text is COMPLETELY DISCARDED.**

Only `segment["start"]` and `segment["end"]` are consumed by Stage 2. The `text` field is ignored in all downstream logic.

This is not a quality judgment about mlx-whisper; it is a structural decision: qwen3-asr is the content authority. mlx-whisper provides fine-grained subtitle boundaries that match broadcast timing requirements (~2–3s per segment) in a way that qwen3's per-region chunking does not.

**Implementation:** Reuse existing `ASRPrimaryStage` with mlx-whisper transcribe profile. No new stage class needed.

| Field | Value |
|---|---|
| Engine | mlx-whisper large-v3 (existing `MLXWhisperEngine`) |
| Input | full audio path (undivided — NOT split by VAD) |
| Output | `[{start, end, text}]` — `text` field persisted but NOT used downstream (stored for audit only) |
| Runtime budget | ≤ 30s for 4-min audio |
| Purpose | Time grid only |

**Why full audio (not VAD-split)?** mlx-whisper's segment boundaries are highest quality when it processes the full audio with its internal VAD and beam search context. Feeding VAD-split chunks degrades boundary quality.

---

### Stage 2: Time-Anchored Merge

**File:** `backend/stages/v6/time_anchored_merge_stage.py`

This stage has no LLM dependency — it is a pure-Python algorithm.

**Algorithm (from `/tmp/v6_stage2_merge.py` prototype):**

```
INPUT:
  mlx_segs:       [{start, end, text}] × ~90  (text ignored)
  qwen3_chars:    [{start, end, text}] × ~1066 (absolute time)

STEP 1 — Per-mlx-slot assignment:
  for each mlx_seg m in mlx_segs:
    chars_in = [c for c in qwen3_chars if m.start <= midpoint(c) < m.end]
    slot = {start: m.start, end: m.end, text: join(c.text for c in chars_in)}

  midpoint(c) = (c.start + c.end) / 2.0 if c.end > c.start else c.start

STEP 2 — Empty slot collapse:
  Walk merged list left-to-right.
  If slot.text == "": slot is dropped; pending_end = slot.end
  Else: if pending_end exists and prior kept slot exists:
            prior_kept.end = max(prior_kept.end, pending_end)
        emit current slot; clear pending_end
  Final trailing empty slots: extend last kept slot's end.

OUTPUT: final_segs [{start, end, text}] × ~84 (estimated)
```

**Known artifacts in output (for Stage 3 to fix):**

1. **Mid-word cuts** — Chinese words occasionally split across adjacent mlx boundaries. E.g., qwen3 outputs 「比賽」 as chars [比 at 10.40–10.55] [賽 at 10.55–10.70], and an mlx boundary falls at 10.55. Result: slot N ends with 「比」, slot N+1 starts with 「賽」. Correct text: 「比賽」 belongs to whichever slot has the dominant speech energy — Stage 3 handles.

2. **First-character missing** — If an mlx slot starts at 10.55 but the qwen3 char for the first syllable has midpoint 10.52 (in the prior slot), the first char falls to the prior slot. Stage 3 handles by examining adjacent neighbor text.

**Stage shape:**
```python
class TimeAnchoredMergeStage(PipelineStage):
    stage_type = "time_anchored_merge"
    # transform(segments_in, context):
    #   reads qwen3 flat chars from context (stashed by orchestrator)
    #   reads mlx segs from segments_in
    #   returns merged list
```

**Quality target:** ≤ 5% characters lost in gaps between mlx segments. Prototype showed 0/1066 chars lost (all assigned).

---

### Stage 3: Refiner LLM (v6 simplified prompt)

**File:** `backend/stages/v6/refiner_stage.py` (or reuse `stages/v5/refiner_stage.py` with a new prompt template)
**Prompt:** `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json`

**Role transformation vs v5-A5:**

| Task | v5-A5 | v6 |
|---|---|---|
| Cascade detection | In prompt (Task 2a) | REMOVED — VAD+qwen3 eliminate at source |
| Tail orphan detection | In prompt (Task 2b) | REMOVED — VAD eliminates at source |
| Hallucination detection | In prompt (Task 2c) | REMOVED — qwen3 has no training-data leak |
| Secondary comparison | Uses `secondary` field (mlx secondary text) | REMOVED — no secondary text; qwen3 is sole authority |
| Broadcast register polish | Task 1 | PRIMARY task (promoted) |
| Mid-word cut fix | Not present | NEW task (Task 2 in v6 prompt) |

**v6 Refiner prompt requirements:**

```
System prompt structure:
1. Role: professional HK broadcast subtitle editor
2. Input JSON shape: {target: {start, end, text}, neighbors: [{...}]}
   NOTE: no "secondary" field (qwen3 is sole source; secondary is absent)
3. Tasks:
   Task 1 (PRIMARY): Polish target.text to broadcast-quality Traditional Chinese
     - Length 0.7–1.3× original char count
     - Preserve entity names (人名/地名/數字 — qwen3 already has correct entities)
     - Preserve Cantonese particles (嘅/咗/啦/喺/嘢)
     - Oral but fluent register
   Task 2 (NEW): Fix mid-word cuts from time-anchored merge
     - If target ends with a partial Chinese word AND neighbor starts with the
       completing char(s), re-attach: absorb the completing chars into target.text
     - If target starts with chars that complete a word from the previous neighbor,
       the correction should happen when the prior neighbor is processed
     - CONSERVATIVE: only fix when the word boundary issue is unambiguous
4. Output: pure JSON object, no markdown fence
   Keep format: {"action": "keep", "text": "<polished>"}
   (Drop format ONLY for: completely empty text after removing noise — e.g. pure
    punctuation segment — NOT for content judgment, which is eliminated upstream)
5. Examples: 3 keep examples (normal polish, Cantonese particle, mid-word fix)
```

**What to REMOVE from v5-A5 prompt:**
- Task 2a (cascade drop rule + cascade example)
- Task 2b (tail_orphan drop rule + tail orphan example)
- Task 2c (hallucination drop rule + hallucination example + known-bad phrases list)
- `"secondary"` field from input JSON shape description
- The "secondary is reference not authority" paragraph
- The "if Task 2 drop conditions hold, drop overrides Task 1" precedence rule
- Drop format instruction (no legitimate drop cases remain — only keep with polish)

**Refiner context:**
- `neighbors` = ±5s primary segments (same window as v5-A5)
- No secondary segments (qwen3 is sole source; there is no secondary reference)

**Stage config:** Reuse existing `RefinerStage` class from `stages/v5/refiner_stage.py`. Pass `secondary=[]` (empty list). The `_collapse_drops` post-processor remains (handles the rare empty-text guard case), but should only fire for genuinely empty input segments.

**Output count guarantee:** Refiner output length equals translations array length (since drops are structurally eliminated, by_lang indexing is now correct). This fixes the v5-A5 by_lang index misalignment bug structurally.

**Refiner prompt three-level resolution (runtime):**

The system prompt fed to the Refiner LLM is resolved in `_run_v6()` before invoking the stage:

1. **Per-file override** — `file_registry[fid]["prompt_overrides"]["refiners.zh"]` (existing v3.18 / v5-A2 key).
2. **Pipeline-level override** — `pipeline["refiner_prompt_override"]["zh"]` (new field; set via `PATCH /api/pipelines/<id>`).
3. **Template default** — content of `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json`.

The resolved prompt is passed to `RefinerStage` / `LLMRefiner` via the existing `runtime_overrides={"refiners.zh": resolved_prompt}` mechanism (same as v5-A2 per-file overrides).

**Frontend visibility (§4.5):** The Pipelines page renders the resolved prompt for v6 pipelines with an edit textarea + Save button. The Proofread page's existing `prompt_overrides` drawer gains two new fields: `qwen3_context` and `refiners.zh` (see §4.5 for full detail).

---

### Stage 4: Translator (unchanged)

When `source_lang == target_lang` (Cantonese broadcast: source=zh, target=[zh]), the translator stage is trivially skipped — `lang_segments = list(canonical_source)`. No code change. v5-A2 `_run_v5()` path handles this already.

### Persist: v5 by_lang schema (unchanged)

`_persist_by_lang()` in `pipeline_runner.py` is unchanged. Refiner output is now length-stable (no drops), so `source_segments` and `by_lang[lang]` are the same length. The index misalignment that affected v5-A5 on drop-heavy files is structurally resolved.

---

## 4. Frontend Integration Requirements

### 4.1 Pipeline JSON registration

Create v6 pipeline JSON files in `backend/config/pipelines/` with a recognizable name prefix `[v6]`. Example:

```json
{
  "id": "<uuid>",
  "name": "[v6] 賽馬廣播 (Cantonese)",
  "pipeline_type": "v6_vad_dual_asr",
  "source_lang": "zh",
  "target_languages": ["zh"],
  "vad": {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": 15,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200
  },
  "asr_primary": {
    "transcribe_profile_id": "<mlx-whisper-profile-uuid>",
    "source_lang": "zh"
  },
  "qwen3_asr": {
    "language": "Chinese",
    "context": "袁幸堯 姚本輝 史滕雷...",
    "post_s2hk": true
  },
  "refinements": {
    "zh": [{"refiner_profile_id": "<v6-refiner-profile-uuid>"}]
  },
  "translators": {},
  "glossary_stages": {},
  "font_config": {
    "family": "Noto Sans TC",
    "color": "white",
    "outline_color": "black"
  }
}
```

The `pipeline_type: "v6_vad_dual_asr"` field causes `PipelineRunner.run()` to dispatch to `_run_v6()`. If `pipeline_type` is absent, `PipelineRunner` falls back to the v4/v5 legacy path (backward compatible).

### 4.2 Dashboard PipelinePicker

Existing `PipelinePicker` component fetches `GET /api/pipelines` and enumerates all pipelines by name. v6 pipelines appear automatically in the list because they have a `name` field. The `[v6]` prefix makes them visually distinguishable without frontend schema changes.

### 4.3 Proofread page SubtitleOverlay

The `SubtitleOverlay` component reads `translations[i].start` and `translations[i].end` to position subtitles in video time. These values come directly from Stage 2's mlx time grid — which produces accurate 2–3s boundaries matching the audio. No changes required.

The `by_lang.zh.text` field contains Stage 3 refiner output — same field path as v5. No changes required.

### 4.4 No translations schema changes

v6 emits the identical v5 translations schema (`by_lang` shape). No Proofread page or SubtitleOverlay schema changes required.

---

### 4.5 Prompt visibility and editing (NEW — in scope for v6)

Two surfaces need prompt editing UI:

#### 4.5.1 Pipelines page — refiner prompt panel

When the user views or edits a pipeline with `pipeline_type: "v6_vad_dual_asr"`, the Pipelines page renders a **Refiner Prompt** panel below the stage list:

- **Read-only display:** Shows the resolved refiner prompt template content (fetched from the template file `refiner/zh_broadcast_hk_v6.json` via the existing `GET /api/prompt_templates` endpoint).
- **Edit textarea:** User can type a custom prompt override.
- **Save button:** Calls `PATCH /api/pipelines/<id>` with body `{ "refiner_prompt_override": { "zh": "<custom_prompt_text>" } }`. When set, this pipeline-level override replaces the template content at runtime for all files using this pipeline (unless a per-file override is set).
- **Clear button:** Sends `PATCH /api/pipelines/<id>` with `{ "refiner_prompt_override": { "zh": null } }` to restore template default.
- **Scope:** Minimal viable — textarea + Save + Clear buttons. No syntax highlighting, no live preview, no multi-language selector beyond `zh`.

**Backend support for `refiner_prompt_override`:**

`PipelineManager.update_if_owned()` accepts a `refiner_prompt_override: {lang: prompt_text | null}` patch field. The value is persisted directly in the pipeline JSON. Existing pipeline schema validator treats it as an optional dict field (no new required fields, no cross-field rules).

#### 4.5.2 Proofread page — extended prompt_overrides drawer

The existing v3.18 `prompt_overrides` drawer (opened via ⚙ Overrides in the TopBar) is extended with two new fields:

**Field 1: "qwen3 Context (詞庫)"**
- Textarea (short, ~3 rows) for per-file override of the `qwen3_context` entity names string.
- PATCH `/api/files/<id>` with `{ "prompt_overrides": { "qwen3_context": "<entity names>" } }`.
- When populated, `_run_v6()` uses this value instead of `pipeline.qwen3_asr.context`.
- Resolution priority: `file prompt_overrides.qwen3_context > pipeline.qwen3_asr.context > ""`.

**Field 2: "Refiner Prompt Override"**
- Textarea (tall, ~8 rows) for per-file override of the refiner system prompt.
- PATCH `/api/files/<id>` with `{ "prompt_overrides": { "refiners.zh": "<custom_prompt>" } }`.
- Note: key `refiners.zh` already exists in the v3.18 + v5-A2 `prompt_overrides` schema.
- Resolution priority: `file prompt_overrides.refiners.zh > pipeline.refiner_prompt_override.zh > template default`.

Both fields use the existing `prompt_override_validator.py` infrastructure. The validator adds `qwen3_context` as a known allowed key.

**Three-level resolution summary (applies to both qwen3 context and refiner prompt):**

| Priority | Source | How set |
|---|---|---|
| 1 (highest) | Per-file `prompt_overrides` | PATCH `/api/files/<id>` |
| 2 | Pipeline-level `refiner_prompt_override` | PATCH `/api/pipelines/<id>` |
| 3 (default) | Template file (`zh_broadcast_hk_v6.json`) | Static file in `config/prompt_templates_v5/refiner/` |

---

## 5. v6 Pipeline Orchestration (`_run_v6`)

**New method in `backend/pipeline_runner.py`:** `_run_v6()`

```
Dispatch condition: self._pipeline.get("pipeline_type") == "v6_vad_dual_asr"
(If pipeline_type is absent → v4/v5 legacy path, backward compatible)

Orchestration sequence:
  stage_index = 0

  --- Context resolution (before stages begin) ---
  file_entry = _file_registry[file_id]
  file_qwen3_context = file_entry.get("prompt_overrides", {}).get("qwen3_context") or ""
  pipeline_qwen3_context = self._pipeline.get("qwen3_asr", {}).get("context") or ""
  resolved_context = file_qwen3_context or pipeline_qwen3_context or ""

  [0] VAD stage
      Input: audio_path
      Output: vad_regions [{start, end}]
      Persist: stage_outputs["0"]

  stage_index = 1

  [1A] qwen3 per-region stage
      Input: audio_path + vad_regions
      qwen3 config: language, post_s2hk from pipeline.qwen3_asr
                    context = resolved_context (file override > pipeline default > "")
      Output: qwen3_chars_flat [{start, end, text}] (absolute time)
      Persist: stage_outputs["1"]
      Stash in extra_overrides: {"__qwen3_chars": qwen3_chars_flat}

  stage_index = 2

  [1B] mlx-whisper full audio (ASRPrimaryStage, existing)
      Input: audio_path
      Output: mlx_segs [{start, end, text}] (~90 segs)
      Persist: stage_outputs["2"]
      NOTE: mlx_segs.text discarded after Stage 2

  stage_index = 3

  [2] TimeAnchoredMergeStage
      Input: mlx_segs (from Stage 1B output, passed as segments_in)
      Extra context: qwen3_chars_flat (stashed in context.pipeline_overrides["__qwen3_chars"])
      Output: merged_segs [{start, end, text}] (~84 segs)
      Persist: stage_outputs["3"]

  stage_index = 4

  canonical_source = merged_segs

  --- Refiner prompt resolution ---
  file_refiner_prompt = file_entry.get("prompt_overrides", {}).get("refiners.zh") or ""
  pipeline_refiner_prompt = self._pipeline.get("refiner_prompt_override", {}).get("zh") or ""
  resolved_refiner_prompt = file_refiner_prompt or pipeline_refiner_prompt or ""
  # (empty string → RefinerStage falls back to template file content)

  [3] Refiner (per target_lang, same loop as _run_v5)
      Input: canonical_source
      Context: neighbors (±5s), no secondary (empty [])
      runtime_overrides: {"refiners.<lang>": resolved_refiner_prompt} if non-empty
      Output: refined_segs
      Persist: stage_outputs["4+"]

  [4] Translator (same as v5, skip when source==target)

  Persist by_lang → translations array (same as _run_v5)
```

**Stage index mapping:**
- 0 = VAD
- 1 = qwen3 per-region
- 2 = mlx-whisper
- 3 = time-anchored merge
- 4+ = refiner (one per target_lang chain)

**Socket.IO events:** Same events as v4/v5 (`pipeline_stage_start`, `pipeline_stage_progress`, `pipeline_stage_done`). No new event types.

**Cancel integration:** `_check_cancel(cancel_event)` called before each stage. Subprocess (qwen3) runs with `timeout=1800`; cancel_event checked between stages.

**Resume from stage:** Not supported in v6 initial release (same as v5). `NotImplementedError` raised if `start_from_stage != 0`.

---

## 6. v6 Refiner Prompt Spec (Full Draft)

File: `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_v6.json`

```json
{
  "id": "refiner/zh_broadcast_hk_v6",
  "lang": "zh",
  "style": "broadcast_hk_v6",
  "system_prompt": "你係專業香港廣播字幕校對員。\n\n輸入係 JSON：\n{\n  \"target\":    {\"start\": <秒>, \"end\": <秒>, \"text\": \"<待校對>\"},\n  \"neighbors\": [{\"start\":..,\"end\":..,\"text\":..}, ...]\n}\n其中 neighbors 係 target 前後 ±5 秒嘅段落（作參考上下文）。\n\n任務：\n1. 將 target.text 校對成廣播質量繁體中文（口語化但通順）：\n   - 長度 0.7–1.3× 原文字數\n   - 保留人名、地名、機構名、數字（qwen3-asr 已有 100% 正確，唔好改）\n   - 粵語特徵字（嘅/咗/啦/喺/嘢/囉/囉/㗎/㗎啩）適度保留，符合廣播口語風格\n   - 唔加外部資訊，唔添加句首連接詞\n2. 修正時間軸對齊造成嘅截斷詞問題：\n   - 若 target.text 末字同 neighbors 下一段首字合起來係一個完整詞（例：target 末尾「比」，下一段首字「賽」→「比賽」），請補全 target.text，把完整詞包入 target\n   - 若 target.text 首字係前段末字截斷詞嘅補全部分，請自然地從 target 首去掉已歸入前段嘅字，令 target 文意完整\n   - 保守原則：只有詞邊界問題明顯時才修正，唔確定就 keep 原文\n\n輸出：純 JSON object，無 markdown fence，無其他文字。\n只輸出 keep 格式：{\"action\": \"keep\", \"text\": \"<校對後文字>\"}\n\n例子 1（正常廣播校對）：\n輸入 target = {\"start\": 12.5, \"end\": 15.0, \"text\": \"佢哋话今晚会落雨啦大家记得帶遮\"}\n輸出: {\"action\": \"keep\", \"text\": \"佢哋話今晚會落雨，大家記得帶遮\"}\n\n例子 2（保留粵語特徵字）：\n輸入 target = {\"start\": 45.2, \"end\": 47.8, \"text\": \"袁幸堯係今日嘅最快時間\"}\n輸出: {\"action\": \"keep\", \"text\": \"袁幸堯係今日最快時間\"}\n\n例子 3（修正截斷詞）：\n輸入 target = {\"start\": 88.1, \"end\": 89.5, \"text\": \"美狼王以壓倒性優\"},\nnext neighbor = {\"start\": 89.5, \"end\": 91.0, \"text\": \"勢奪得冠軍\"}\n輸出: {\"action\": \"keep\", \"text\": \"美狼王以壓倒性優勢\"}\n(「優勢」被截斷為「優」+「勢」，Stage 3 把「勢」歸回 target)\n"
}
```

---

## 7. Out-of-Scope (Explicit)

The following items are explicitly excluded from v6 initial release:

1. **Stage 4 Translator rewrite** — v5-A2 `LLMTranslator` is used unchanged for cross-lingual pairs. No new translator logic for v6.

2. **Stage 5 / Persist schema rewrite** — `_persist_by_lang()` is unchanged. The by_lang misalignment bug is fixed structurally (refiner no longer drops) rather than by schema change.

3. **Issue #1 — mlx-whisper pre-cleanup** — Silero VAD eliminates the root cause. The v5-A4.1 `dedupe_cascade_repeats` / `filter_tail_english_orphan` filters on the mlx output are no longer needed in the v6 path (they remain in `segment_utils.py` for v5 backward compat; v6 stages simply don't call them).

4. **Issue #2 — mlx-whisper text** — Completely discarded in v6. No attempt to use mlx text as fallback or blend.

5. **Validation report** — Manual validation run (賽馬 file + Winning Factor file) is a post-implementation task, not part of this plan. The implementer creates a `docs/superpowers/validation/v6-validation.md` stub; operator fills after running.

6. **Full v6 Pipeline builder form** — No full create/edit form for v6 pipelines in the Pipelines page. v6 pipelines are created via direct JSON. The §4.5 refiner prompt panel is the only UI addition for v6 pipelines. A complete v6 form builder is a future follow-up.

7. **SenseVoice third ASR** — Out of scope (post-v6).

8. **qwen3-asr model upgrade** — v0.3.5 (Qwen3-ASR-1.7B) used as-is. Upgrade to larger model or Qwen3-ASR-8B is a future experiment.

9. **Windows / Linux support for Stage 1A** — mlx-qwen3-asr requires Apple Silicon (MLX). v6 pipeline is Apple Silicon only in initial release.

10. **Stage resume (start_from_stage)** — Not implemented in v6. `NotImplementedError` raised if attempted.

---

## 8. Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Silero VAD misses speech (too aggressive) | Low | Medium | `speech_pad_ms=200` adds 200ms buffer; `min_speech_duration_ms=250` avoids dropping short utterances. Prototype: 91.3% speech ratio on 賽馬 audio. |
| R2 | Silero VAD splits a phrase mid-utterance (VAD threshold too tight) | Low | Low | Split is handled: qwen3 runs per-region; Stage 2 merge re-assigns chars to mlx time grid regardless of region boundaries. |
| R3 | Stage 2 chars lost in gaps between mlx segments | Low | Medium | Prototype: 0/1066 chars lost. If chars fall between segments, they are assigned to the nearest slot in a post-process pass (absorb toward shorter gap). If still lost, Stage 3 prompt includes "if text seems truncated relative to neighbors, reconstruct from context". |
| R4 | Stage 3 Refiner mis-fixes mid-word cut (incorrect re-attachment) | Medium | Low | Prompt instructs "conservative: only fix when unambiguous". Fallback: LLM returns `action=keep, text=<original>` if uncertain. |
| R5 | qwen3 subprocess timeout for long audio | Low | High | `timeout=1800` (30 min). Observed: ~40s for 4-min audio → comfortable margin. Cancel_event checked between stages. |
| R6 | `_persist_by_lang` still uses `len(source_segments)` anchor, off-by-one if refiner silently drops | Low | Medium | With v6 prompt, drop action is structurally eliminated. `_collapse_drops` still collapses empty segs (but those were already empty going in). Monitor via test assertion: `len(refiner_out) == len(merged_segs)`. |
| R7 | mlx-whisper run on full audio produces different segment count than expected (~90) | Low | Low | Stage 2 algorithm works with any mlx seg count; empty-slot collapse handles variance. |
| R8 | py3.11 venv path differs between dev machines / CI | Medium | Medium | Hardcode default to `backend/scripts/v5_prototype/venv_qwen/`; allow override via `V6_QWEN_VENV_PYTHON` env var. |
| R9 | v6 pipeline `_run_v6()` branch causes regression in v4/v5 pipelines | Low | High | Dispatch is gated on `pipeline_type == "v6_vad_dual_asr"`; pipelines without this field fall through to v4/v5 paths unchanged. Add integration test that a v5 pipeline (no `pipeline_type` field) still dispatches to `_run_v5`. |
| R10 | Frontend prompt editing UI scope creep | Medium | Low | Keep UI minimal: textarea + Save + Clear buttons only. No syntax highlighting, no live preview, no multi-language selector beyond `zh`. Scope is bounded by §4.5. |
| R11 | Pipeline-level prompt override storage conflict with per-file override | Low | Medium | Resolution priority is explicit and tested: file `prompt_overrides.refiners.zh` > pipeline `refiner_prompt_override.zh` > template default. Same pattern applied to `qwen3_context`. Empty string is treated as "not set" (falls through to next priority level). |

---

## 9. Prototype Evidence Files

| File | Contents | Used in |
|---|---|---|
| `/tmp/v6_prototype_stage1a_v2.json` | 28 VAD regions, qwen3 1066 char timestamps, 0.8s VAD runtime | Stage 0 + 1A evidence |
| `/tmp/v6_prototype_stage1a.json` | Earlier run (v1, fewer regions) | Reference only |
| `/tmp/v6_stage2_result.json` | 90 mlx → 86 merged → 84 collapsed segs, full per-slot breakdown | Stage 2 evidence |
| `/tmp/v6_stage2_merge.py` | Stage 2 algorithm implementation | Source for `TimeAnchoredMergeStage` |
| `/tmp/v6_stage1a_vs_1b.py` | Side-by-side comparison script | Reference |
| `backend/data/registry.json` → `aec2e8f98789.stage_outputs["0"]` | mlx-whisper 90 segs (time grid) | Stage 1B evidence |
| `backend/scripts/v5_prototype/prototype_vad_qwen3.py` | Stage 0 + 1A orchestrator | Source for Stages 0+1A |
| `backend/scripts/v5_prototype/qwen3_vad_subprocess.py` | py3.11 subprocess | Reused as-is in production |

---

## 10. Dependency Versions

| Package | Version | Venv | Notes |
|---|---|---|---|
| silero-vad | 6.2.1 | `backend/venv` (py3.9) | Already installed; no new dep |
| torch | existing | `backend/venv` | Required by silero-vad |
| soundfile | existing | `backend/venv` | For WAV slicing |
| numpy | existing | `backend/venv` | For audio array ops |
| mlx-qwen3-asr | 0.3.5 | `backend/scripts/v5_prototype/venv_qwen` (py3.11) | Subprocess-isolated |
| opencc-python-reimplemented | existing | `venv_qwen` | s2hk conversion |

No new pip packages required for v6.
