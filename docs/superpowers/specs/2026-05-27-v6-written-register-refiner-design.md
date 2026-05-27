# v6 賽馬廣播 (書面語) Pipeline — Design

**Date**: 2026-05-27
**Author**: brainstorming session (Reno + Claude Opus 4.7)
**Status**: Design approved, pending implementation plan
**Branch**: `feat/phase-1-frontend-design`

---

## 1. Problem / Motivation

The `[v6] 賽馬廣播 (Cantonese)` pipeline (id `4696bbaa-b988-49bd-859c-e742cb365634`) produces the best ASR quality we've observed on Cantonese broadcast content. Its refiner explicitly preserves Cantonese register markers (`嘅 / 係 / 咗 / 喺 / 唔` etc.) for an authentic spoken feel.

Users sometimes want the **same content** in 書面語 (formal written Chinese / Mandarin register) for different downstream uses — print captions, subtitling for non-Cantonese-speaking audiences, archival, etc.

## 2. Goal

Add a parallel pipeline `[v6] 賽馬廣播 (書面語)` that reuses the existing v6 Cantonese ASR + refiner machinery and appends a second register-conversion refiner. End result: subtitle text in 書面語 register, with everything else (timing, proper nouns, glossary terms) identical to the Cantonese variant.

## 3. Non-Goals

- Replacing the existing Cantonese pipeline — both options coexist; user picks via pipeline picker.
- Schema changes to `target_languages` (e.g., adding `zh_written` as a distinct lang code).
- Backend code changes — the existing `pipeline_runner` already iterates `refinements[lang]` as an ordered list and supports chained refiners on the v6 path.
- Frontend UI changes — the new pipeline appears automatically in the picker via the existing `/api/pipelines` enumeration.
- Translation / cross-lingual output (the new refiner is same-language: `zh` in, `zh` out).
- Re-running ASR for files already processed by the Cantonese variant — user must explicitly select the new pipeline for new files (or re-run on existing files via `/api/pipelines/<id>/run`).

## 4. Approach

**Chain pattern** (chosen over single-pass):
1. Stage 1-2 (VAD + qwen3-asr + mlx-whisper + TimeAnchoredMerge) — **identical** to current Cantonese pipeline.
2. Stage 3 — **existing v6 Cantonese refiner** runs first, producing polished Cantonese (`下個月有新騎師登場，就係澳洲好手`).
3. Stage 4 — **NEW 書面語 register refiner** runs second, converting register (`下個月有新騎師登場，是來自澳洲的好手`).

**Why chain over single-pass**:
- The existing Cantonese refiner already handles ASR cleanup, VAD word-boundary truncation fixes, and hallucination filtering well. Reusing it preserves all that work.
- The new refiner has **one focused job** — register conversion. Smaller prompt, less risk of breaking the proven Cantonese-side logic.
- Cost is acceptable: ~2× LLM time on the refine stage only (≈ +30-90s on a 4-min file in practice).

The pipeline runner already supports chained refiners on the v6 path:

```python
# backend/pipeline_runner.py:535
for refiner_entry in self._pipeline.get("refinements", {}).get(target_lang, []):
    refiner_profile = self._refiner_profile_manager.get(refiner_entry["refiner_profile_id"])
    # ... runs refiner on lang_segments, mutating lang_segments in place ...
```

So `refinements.zh: [refiner_A, refiner_B]` runs refiner_A then refiner_B sequentially, each operating on the previous one's output.

## 5. Components

### 5.1 New prompt template

**File**: `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`

Mirrors `zh_broadcast_hk_v6.json`'s shape (id / name / version / lang / style / system_prompt fields). The `system_prompt` is rewritten for the register-conversion job:

- **Assume input is already Cantonese-polished** (the previous refiner did ASR cleanup). This refiner does NOT re-litigate proper nouns, numbers, or punctuation — only register markers.
- Convert 粵語特徵字 → 書面語:
  - `嘅 → 的`
  - `係 → 是`
  - `咗 → 了`
  - `喺 → 在`
  - `唔 → 不`
  - `俾 → 給 / 被` (context-dependent)
  - `嘢 → 東西 / 事` (context-dependent)
  - `呢 (此處) → 這`
  - `嗰 → 那`
  - `點 (副詞) → 怎`
  - `乜 → 什麼`
  - Sentence-final particles `啦 / 㗎 / 㗎啩 / 囉` → 刪除 OR 改 `了 / 吧`
- **Preserve** proper nouns, places, racing terms (qwen3-asr context already pinned these correctly upstream).
- **Same I/O contract** as existing v6 refiner: target + neighbors input, `{action: "keep", text: "..."}` output, no markdown fence.
- **Same word-truncation handling rules** in case VAD edge-case still surfaces by stage 2 (defensive — should never fire after Cantonese refiner, but the prompt accepts the same shape, so unchanged plumbing).
- **3 in-context examples**:
  1. Normal register conversion: `就係澳洲好手 → 是來自澳洲的好手`
  2. Preserve proper noun: `袁幸堯係今日最快時間 → 袁幸堯是今日最快時間` (keep `袁幸堯` verbatim)
  3. Sentence-final particle removal: `今晚會落雨啦大家記得帶遮 → 今晚會下雨，大家記得帶傘`

### 5.2 New refiner profile

**File**: `backend/config/refiner_profiles/<new-uuid>.json`

```json
{
  "id": "<new-uuid>",
  "name": "Refiner ZH 書面語 register conversion v6",
  "lang": "zh",
  "style": "written_register_v6",
  "llm_profile_id": "9402593c-184d-4a4d-a160-ebdf55e678e8",
  "prompt_template_id": "refiner/zh_written_register_v6",
  "shared": false,
  "user_id": 627,
  "created_at": <epoch>,
  "updated_at": <epoch>
}
```

- Reuses the **same LLM profile** as the existing Cantonese refiner (`9402593c-...` is the Ollama Qwen3.5 instance) — no new LLM stack required.
- `lang: "zh"`, `style: "written_register_v6"` — distinguishes from the broadcast-hk style.
- `user_id: 627` matches the owner of the existing v6 racing pipeline so RBAC stays consistent.

### 5.3 New pipeline

**File**: `backend/config/pipelines/<new-pipeline-uuid>.json`

Cloned from `4696bbaa` with two changes: `name`, and `refinements.zh` becomes a 2-element chain:

```json
{
  "name": "[v6] 賽馬廣播 (書面語)",
  "pipeline_type": "v6_vad_dual_asr",
  "version": 6,
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
    "transcribe_profile_id": "82338761-e6ed-47eb-b153-64789ed7327e",
    "source_lang": "zh"
  },
  "qwen3_asr": {
    "language": "Chinese",
    "context": "袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 美狼王 HIGHLAND BLINK 幸運風采 沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 騎師 試騎 推騎 試閘 抽籤 排位 大熱門 頭馬 客艙 馬房 馬仔 香檳 打吡 香港 沙田 悉尼",
    "post_s2hk": true
  },
  "refinements": {
    "zh": [
      { "refiner_profile_id": "f7f72bd9-3f27-47a4-92bd-5727f336916a" },
      { "refiner_profile_id": "<new-refiner-uuid>" }
    ]
  },
  "translators": {},
  "glossary_stages": [],
  "font_config": {
    "family": "Noto Sans TC",
    "color": "white",
    "outline_color": "black"
  },
  "shared": false,
  "id": "<new-pipeline-uuid>",
  "user_id": 627,
  "created_at": <epoch>,
  "updated_at": <epoch>
}
```

The 1st refiner is the **existing** Cantonese refiner (unchanged ID). The 2nd is the new 書面語 refiner. The order is significant — Cantonese cleanup must run first.

## 6. Data Flow

```
Audio file (.mp4 / .wav)
   │
   ▼ VAD pre-segment (Silero VAD)
[(start, end), ...] speech regions
   │
   ├──▶ Stage 1A: qwen3-asr per-region transcribe
   │       → Cantonese text segments (no timing)
   │
   └──▶ Stage 1B: mlx-whisper full-audio
           → word-level timestamps grid
   │
   ▼ Stage 2: TimeAnchoredMergeStage
canonical source segments [{start, end, text}]
   │
   ▼ Stage 3a: Refiner #1 (existing Cantonese v6)
   │   prompt: zh_broadcast_hk_v6
   │   role: ASR cleanup, VAD truncation fix, preserve Cantonese register
canonical source segments (Cantonese-polished)
   │
   ▼ Stage 3b: Refiner #2 (NEW 書面語)
   │   prompt: zh_written_register_v6
   │   role: register conversion only
canonical source segments (書面語)
   │
   ▼ Stage 4: _persist_by_lang (existing v6 logic)
file_registry.translations[].by_lang["zh"].text = 書面語
```

The existing v6 pipeline runner code handles this without modification because `for refiner_entry in refinements[lang]` already iterates a list and mutates `lang_segments` each iteration.

## 7. Error Handling

| Scenario | Behaviour |
|---|---|
| Refiner #1 fails | Existing v6 path: stage marked `failed`, pipeline aborts. Same as today. |
| Refiner #2 fails | Same as Refiner #1 failure — stage marked `failed`. Refiner #1's output is preserved in `stage_outputs` for debugging. |
| Empty / drop on Refiner #2 | Existing `_collapse_drops` safety net in `RefinerStage` falls back to the previous segment's text. With chain, this means: if refiner #2 drops segment N, fall back to refiner #1's text for N. Acceptable — user sees Cantonese-polished output instead of 書面語, which is still readable. |
| Refiner #2's prompt template missing from disk | `engines/factory.py:load_prompt_template` raises `FileNotFoundError` → pipeline run fails fast. Tests cover this. |
| Refiner profile lookup returns None | `pipeline_runner.py:540` already raises `ValueError("v6: refiner profile for {lang} not found")` — same path. |
| LLM unreachable / timeout | Existing `LLMRefiner` retry / max_tokens logic applies. Same behaviour as Refiner #1 today. |

## 8. Testing

### 8.1 New pytest cases (`backend/tests/test_v6_written_register.py` — new file)

3 lightweight cases — no real LLM calls, just config validation:

```python
def test_zh_written_register_prompt_template_loads():
    """The new prompt template file exists and parses as valid v6 template."""
    template = load_prompt_template("refiner/zh_written_register_v6")
    assert template["lang"] == "zh"
    assert template["style"] == "written_register_v6"
    assert "system_prompt" in template
    # Spot-check the prompt mentions the register conversion mappings
    sp = template["system_prompt"]
    assert "嘅" in sp and "的" in sp  # 嘅 → 的 mapping documented
    assert "係" in sp and "是" in sp  # 係 → 是 mapping documented

def test_zh_written_register_refiner_profile_loads():
    """The new refiner profile exists and references the new template + same LLM as Cantonese variant."""
    profile = refiner_profile_manager.get("<new-refiner-uuid>")
    assert profile is not None
    assert profile["lang"] == "zh"
    assert profile["prompt_template_id"] == "refiner/zh_written_register_v6"
    # Reuses same LLM profile as the existing Cantonese refiner
    assert profile["llm_profile_id"] == "9402593c-184d-4a4d-a160-ebdf55e678e8"

def test_v6_written_pipeline_has_chained_refiners():
    """The new pipeline has the existing Cantonese refiner first, new written refiner second."""
    pipeline = pipeline_manager.get("<new-pipeline-uuid>")
    assert pipeline is not None
    assert pipeline["pipeline_type"] == "v6_vad_dual_asr"
    assert pipeline["target_languages"] == ["zh"]
    refiners = pipeline["refinements"]["zh"]
    assert len(refiners) == 2
    # Order is significant — Cantonese first, written second
    assert refiners[0]["refiner_profile_id"] == "f7f72bd9-3f27-47a4-92bd-5727f336916a"
    assert refiners[1]["refiner_profile_id"] == "<new-refiner-uuid>"
```

### 8.2 Manual smoke

After config is loaded:
1. Restart backend so the new prompt / profile / pipeline are picked up.
2. In Dashboard, switch the pipeline picker to `[v6] 賽馬廣播 (書面語)`.
3. Upload a 賽馬 video clip (or pick an already-uploaded one).
4. Click 「執行」.
5. Wait for pipeline complete (expect ~110-120s for a 4-min clip).
6. Open the Proofread page — verify segment text is in 書面語 (no 嘅/係/咗/喺 markers, proper nouns unchanged).

## 9. Acceptance Criteria

- [ ] New prompt template file exists and parses
- [ ] New refiner profile file exists and references the new template
- [ ] New pipeline file exists with the 2-element refinement chain in correct order
- [ ] 3 new pytest cases pass (existing baseline preserved)
- [ ] Backend restart loads all 3 new configs without error
- [ ] `[v6] 賽馬廣播 (書面語)` appears in the Dashboard pipeline picker
- [ ] Manual smoke: running on the sample 賽馬 video produces 書面語 output (sentence-final 嘅/係 markers absent in final segment text)
- [ ] Existing `[v6] 賽馬廣播 (Cantonese)` pipeline remains untouched and produces the same Cantonese output as before (regression check)

## 10. Out of Scope

- Backend code changes (`pipeline_runner.py` already supports refinement chains on v6 path).
- Frontend code changes (pipeline picker auto-discovers new pipelines via `/api/pipelines`).
- Schema additions (e.g., `zh_written` lang code).
- Auto-detection or A/B comparison between the two refiners' outputs.
- Migration of existing Cantonese-refined files to 書面語 (user re-runs new pipeline manually if desired).
- New LLM profile (reuses existing Ollama Qwen3.5).
- Glossary integration (the new refiner does not touch glossary terms — they're preserved verbatim).

## 11. File Inventory

**New files (4):**
- `backend/config/prompt_templates_v5/refiner/zh_written_register_v6.json`
- `backend/config/refiner_profiles/<new-refiner-uuid>.json`
- `backend/config/pipelines/<new-pipeline-uuid>.json`
- `backend/tests/test_v6_written_register.py`

**Modified files (0):**

No source code touched. This is a pure configuration + test addition.

Estimated total: ~3 JSON files (~30-80 lines each depending on prompt length) + 1 small test file (~40 lines).

## 12. Pipeline Naming Convention

`[v6] 賽馬廣播 (書面語)` — mirrors the existing naming pattern. Both pipelines appear in the picker:
- `[v6] 賽馬廣播 (Cantonese)` — existing, broadcast Cantonese register
- `[v6] 賽馬廣播 (書面語)` — new, formal written Chinese register

User picks based on intended downstream use.
