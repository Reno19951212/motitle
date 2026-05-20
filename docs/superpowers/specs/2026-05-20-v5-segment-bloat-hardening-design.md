# v5 Segment Bloat Hardening — Design

**Date:** 2026-05-20
**Branch:** `feat/frontend-redesign`
**Stage:** v5-A4 hotfix
**Investigation:** 3 parallel agents (data audit + code review + prompt audit) on 2026-05-20

---

## Problem

Per-segment text in the v5 dual-ASR + Refiner-Translator pipeline can balloon
to 5–25× normal length on certain segments. Empirical worst case observed:
Winning Factor `idx=299`, 2.1-second timecode window, where:

| Stage | Char count | Output |
|---|---|---|
| `asr_primary` | 3 | `被删除` |
| `asr_secondary` (long window) | 441 | `now perhaps to the eye not deserving the kind of boom... Hot Delight had to break forty four seconds for his last eight hundred metres...` |
| `asr_verifier` | 441 | (adopted secondary verbatim into primary's 2.1s slot) |
| `refiner:zh` | 436 | (added `[HALLUC]` flag, passed text through) |

Other observed bloat patterns:
- `idx=231`: primary `ko` (2 chars) → refiner emits 234-char LLM system-prompt
  error message as segment text.
- 賽馬 `idx=39`: primary 20 chars → verifier 152 chars (legitimate long window,
  not a bug, but exhibits the same cascade behavior).

## Root Causes (5 ranked)

### R1 — Verifier replaces primary stub with secondary's long-window text
Secondary ASR (`mlx-qwen3-asr` subprocess) runs on long audio windows (10–30 s)
while primary (Whisper) produces fine-grained per-segment text. When primary is
a stub or hallucination over a short timecode (e.g. 2 s) and secondary covers a
much longer span, the verifier substitutes secondary's full-window text into
primary's short timecode slot. Length-vs-timecode contract breaks.

### R2 — No `max_tokens` cap on any v5 LLM call
`backend/engines/refiner/llm_refiner.py:51`, `translator/llm_translator.py:55`,
`verifier/llm_verifier.py:102` all call `self.llm.call(system_prompt, user)`
without passing `max_tokens`. `LLMEngine.call()` signature already supports the
kwarg (defaulting to `None`); the call sites just never set it. Ollama
`num_predict` and OpenRouter `max_tokens` end up unbounded.

### R3 — Refiner prompts lack length anchor
`prompt_templates_v5/refiner/en_newscast_default.json` has **no** length cap,
no anti-elaboration rule, no `[HALLUC]` escape hatch. The instruction
`"Fix obvious ASR errors using racing context"` invites LLM invention.
`zh_broadcast_hk_default.json` has soft `保持原段嘅字數同節奏` but no numeric
cap or anti-formulaic blacklist (v3.18 included one for v4 broadcast prompts).

### R4 — Refiner LLM leaks system-prompt meta language as segment text
When primary input is garbage (`ko`, `被删除`), the refiner LLM emits its own
system-prompt error response (e.g. `[ERROR] Input language mismatch...`) into
the segment text field instead of returning empty.

### R5 — `quality_flags` field declared but never populated
`stages/v5/{refiner,translator,verifier}_stage.py` all set
`quality_flags: List[str] = []` and never append. v4's `_TranslationPostProcessor`
that flagged `long` / `review` was deleted in v4-A5 cleanup; v5 never built
the replacement.

### R6 — Pipeline source_lang misconfiguration cascades silently
Winning Factor (an English video) was created with `source_lang=zh`. The whole
ZH ASR + refiner:zh cascade then tries to process English content with no
upstream validation. This is a user-error, but the pipeline silently accepts
it instead of warning at creation time.

---

## Goals

Restore segment text to be bounded by audio time, plus give the UI visible flags
for downstream cleanup. Specifically:

1. **Hard mechanical cap** — no single LLM call can produce more than ~600 chars
   regardless of prompt failure.
2. **Prompt-level cap** — refiner & translator prompts instruct LLM to maintain
   0.7–1.3× input length and emit empty string on hallucination tokens.
3. **Meta-language detection** — refiner output starting with
   `[ERROR]` / `[INFO]` / `[SORRY]` / `Sorry, ` / `I cannot ` falls back to
   source text instead of polluting the segment.
4. **Verifier timecode awareness** — when primary timecode window is short
   (<3 s) but secondary returns text > 2× primary's char count, prefer primary
   to keep length aligned with audio duration.
5. **`quality_flags` populated** — refiner/translator stages flag output as
   `"long"` when char count exceeds per-lang threshold; UI shows the chip.
6. **Pipeline schema warning** — pipeline create/update returns a `warnings`
   array (non-blocking) when downstream `target_languages` doesn't contain
   `asr_primary.source_lang` AND no translator is wired — a strong signal of
   misconfiguration.

## Out of Scope

- Source-lang auto-detection from audio (would need ffprobe + LID model — too
  large for hotfix; left as Phase 7 follow-up).
- Re-segmentation: actually splitting secondary's long-window output back into
  primary-aligned subsegments. This is the correct long-term fix for R1 but
  needs DTW + segment-boundary inference. For this hotfix we prefer primary on
  short windows (a coarser but mechanical guard).
- Backfilling existing registry entries with new flags. New runs only.
- Changing `LLMEngine.call()` ABC signature — already supports `max_tokens`.

## Architecture (per stage)

```
ASR primary  →  ASR secondary  →  Verifier (R1+R2 guards)  →  Refiner (R2+R3+R4 guards)  →  Translator (R2 guard)
                                       ↓                          ↓                              ↓
                                   stage_output             stage_output (flags)          stage_output (flags)
                                                                  ↓                              ↓
                                                            by_lang aggregation → file registry → /api/files/<id>/translations
```

### Engine-level changes (R2)

Three call sites in `backend/engines/{refiner,translator,verifier}/*.py`
pass concrete `max_tokens`:

| Engine | Cap | Rationale |
|---|---|---|
| Refiner | 200 | Same-lingual polish — text length ≈ input; 200 tokens ≈ 600 chars CJK |
| Translator | 300 | Cross-lingual may compress or expand; 300 tokens ≈ 900 chars |
| Verifier | 150 | One-line decision between two candidates; 150 tokens ≈ 450 chars |

`LLMEngine.call(max_tokens=N)` already supported by both OllamaLLM
(`num_predict=N`) and OpenRouterLLM (`max_tokens=N`). No ABC change.

### Refiner output filter (R4)

In `LLMRefiner.refine()`, after the label-prefix strip, before
`first_line` extraction, check if the trimmed output starts with any of:
`[ERROR]`, `[INFO]`, `[SORRY]`, `Sorry, `, `I cannot `, `As an AI`, `I'm unable`.
If so → fall back to `src` (the input) unchanged. Implementation:

```python
_META_PREFIXES = ("[ERROR]", "[INFO]", "[SORRY]", "Sorry, ", "I cannot ", "As an AI", "I'm unable", "I am unable")
if any(refined.startswith(p) for p in _META_PREFIXES):
    refined = src  # LLM refused / errored; keep input
```

### Verifier timecode-aware fallback (R1)

In `LLMVerifier.verify()`, after the LLM call returns `decision`, apply this
additional guard:

```python
PRIMARY_PREFERENCE_WINDOW_SEC = 3.0
SECONDARY_BLOAT_RATIO = 2.0
window = ps["end"] - ps["start"]
if window < PRIMARY_PREFERENCE_WINDOW_SEC and len(decision) > max(1, SECONDARY_BLOAT_RATIO * len(wt)) and wt:
    decision = wt  # Short window — trust primary's timing over secondary's content
```

`wt` is Whisper's primary text. This only triggers when:
- primary timecode window < 3s
- decision is 2× or more longer than primary
- primary is non-empty (otherwise we'd lose all content)

This does NOT re-segment — it just refuses to inject secondary's long-window
text into a short primary slot.

### Prompt-level cap (R3)

Edit both `refiner/zh_broadcast_hk_default.json` and `refiner/en_newscast_default.json`
to add explicit length rule + hallucination escape. Keep the existing
voice/register guidance; insert after rule 1.

ZH refiner addition:
```
保持長度：輸出字數須喺輸入嘅 0.7–1.3× 範圍內。唔好擴寫、唔好加任何輸入冇嘅資訊。
如果輸入含有「[HALLUC]」「[LONG]」「[ERROR]」標記，或者係明顯訓練語料碎片（例如「粟米片」「coffee shop」「豆腐花」、與賽馬／新聞無關嘅孤立詞），直接輸出空字串。
```

EN refiner addition:
```
Preserve length: output character count must stay within 0.7–1.3× of input. Do not expand, do not elaborate, do not add facts the input did not contain.
If input contains `[HALLUC]`, `[LONG]`, `[ERROR]` markers, or obvious training-corpus fragments (isolated random words with no broadcast context), output an empty string.
```

Translator templates already have explicit length rules per v5-A1 prompts —
leave them alone.

### Quality flags (R5)

Each stage's `_run_stage_v5` already accepts a `quality_flags` channel via
the registry write. Wire flag population in transform helpers:

| Stage | Flag rule |
|---|---|
| Refiner | `"long"` if output chars > 1.5× input chars |
| Refiner | `"empty_recovered"` if output is empty AND input was non-empty (LLM dropped) |
| Translator | `"long"` if output chars > 1.5× input chars OR > 80 chars hard cap |
| Verifier | `"primary_kept"` if R1 fallback fired |

Frontend already renders `flags` chips on segment rows ([SegmentRow.tsx](frontend/src/pages/Proofread/SegmentRow.tsx) v3.4 schema). No FE change needed if backend appends.

### Pipeline schema warning (R6)

In `backend/pipeline_schema_v5.py::validate_v5_pipeline`, add a non-blocking
"warnings" return channel. Currently returns `list[str]` errors only — extend
to return `(errors, warnings)` tuple where the existing call site treats
errors as fatal but logs+returns warnings to the client.

New warning rule:
```
If asr_primary.source_lang is "zh" and target_languages contains "en" but no
translators.zh_to_en defined, OR asr_primary.source_lang is "en" and
target_languages contains "zh" but no translators.en_to_zh defined → warn:
"Source language is {S} but target {T} has no translator wired — output will
be empty for that target."
```

Pipeline POST/PATCH response carries `{warnings: [...]}` next to created entity.

---

## Testing Strategy

### Unit (backend pytest)

- **Engine caps (R2)**: Each engine test asserts `llm.call` invoked with
  `max_tokens=200/300/150`. Use a `FakeLLMEngine` that records kwargs.
- **Refiner meta-prefix fallback (R4)**: Fake LLM returns `"[ERROR] ..."` → refiner output equals `src`.
- **Verifier short-window primary fallback (R1)**: Primary `(0.0, 2.0, "ko")`,
  secondary word stream covering `0.0-30.0` with 400-char text → decision = `"ko"`.
- **Verifier long-window legitimate (R1 negative)**: Primary
  `(0.0, 26.0, "下個月有...")`, secondary 152-char → decision = secondary text
  (window ≥ 3s, R1 guard skipped).
- **Prompt template lint (R3)**: Load `refiner/zh_broadcast_hk_default.json`
  and `refiner/en_newscast_default.json`, assert system_prompt contains both
  length rule and hallucination-escape clause.
- **Quality flags wiring (R5)**: After a refiner stage run with output >1.5×
  input → flags contains `"long"`.
- **Pipeline warning (R6)**: Create pipeline with `source_lang=zh` and
  `target_languages=["zh","en"]` but no `translators.zh_to_en` → response
  carries warning string.

### Integration (backend pytest)

- **R2 end-to-end**: Stub LLMEngine to return 5000-char garbage → all 3 stages
  cap output at ≤600 chars via R2 cap + downstream filters.
- **R6 warning routing**: POST `/api/pipelines` returns warnings in JSON body.

### Manual smoke (Playwright, optional)

- Re-run Winning Factor pipeline on a fresh file → no segment exceeds 200 chars.
- Dashboard live overlay shows correctly-truncated text + `long` flag chip on
  any segment that hits the cap.

### Validation

Compare 賽馬 + Winning Factor re-runs before vs after. Acceptance:

| Metric | Before (current) | Target |
|---|---|---|
| p95 segment char count (賽馬) | 128 | ≤ 60 |
| p95 segment char count (Winning Factor) | 59 | ≤ 50 |
| max segment char count | 436 | ≤ 200 |
| `[ERROR]`/`[INFO]`/`Sorry`-prefixed segments | 1+ | 0 |

Save validation snapshot pairs to `docs/superpowers/validation/v5-bloat-hardening-{before,after}.json`.

---

## Files Touched

```
backend/engines/refiner/llm_refiner.py      (R2 cap + R4 meta filter)
backend/engines/translator/llm_translator.py (R2 cap)
backend/engines/verifier/llm_verifier.py    (R2 cap + R1 timecode guard)
backend/stages/v5/refiner_stage.py          (R5 flag population)
backend/stages/v5/translator_stage.py       (R5 flag population)
backend/stages/v5/verifier_stage.py         (R5 flag population)
backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json (R3)
backend/config/prompt_templates_v5/refiner/en_newscast_default.json     (R3)
backend/pipeline_schema_v5.py               (R6 warnings channel)
backend/routes/pipelines.py                 (R6 — pass warnings through to client)
backend/tests/test_v5_bloat_hardening.py    (new — ~25 cases covering R1–R6)
docs/superpowers/validation/v5-bloat-hardening-baseline.json (validation evidence)
docs/superpowers/validation/v5-bloat-hardening-post.json     (validation evidence)
CLAUDE.md                                   (v5-A4 hotfix entry)
```

No frontend changes required — `flags` already rendered by `SegmentRow`.

## Risk

- **R1 false-positive**: A legitimate 2-second segment where Whisper truly
  missed content and secondary correctly recovered 100 chars would get
  reverted to primary's empty/stub. Tradeoff: we accept the loss because the
  alternative (silent 10×+ bloat that confuses the operator) is worse.
  Operator can re-run with adjusted timecode bounds.
- **R3 prompt change**: existing v5 pipelines pointing at the modified
  templates will pick up new behavior on next run. No re-validation script
  needed — prompt changes don't break stored pipeline JSON.
- **R5 flags**: UI already renders, but if a segment is flagged across multiple
  stages the chip may stack. Acceptable.
- **R6 warnings**: Non-blocking. If client ignores them, behavior is unchanged
  from today. Logged server-side.
