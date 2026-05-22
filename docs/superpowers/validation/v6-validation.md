# v6 Operator Validation Report

**Date:** 2026-05-22
**Branch:** `feat/frontend-redesign` (HEAD `95d6f67`, merge of `feat/v6-vad-dual-asr-refiner`)
**Status:** ✅ Operator-validated, accepted to `feat/frontend-redesign`

**Spec:** [docs/superpowers/specs/2026-05-21-v6-vad-dual-asr-refiner-design.md](../specs/2026-05-21-v6-vad-dual-asr-refiner-design.md)
**Plan:** [docs/superpowers/plans/2026-05-21-v6-vad-dual-asr-refiner-plan.md](../plans/2026-05-21-v6-vad-dual-asr-refiner-plan.md)

---

## Pipeline Architecture (v6)

```
Audio (mp4 / mxf)
    │
    ▼ FFmpeg decode → 16kHz mono
    │
[Stage 0] Silero VAD pre-segmentation
    │  → N speech regions [(start, end)]  ~0.8–2.4s runtime
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
[Stage 1A] qwen3-asr per VAD region   [Stage 1B] mlx-whisper large-v3 full audio
    │  Content authority (text only)      │  Time-grid reference (timestamps only)
    │  char-level [{start, end, text}]    │  mlx TEXT IS DISCARDED
    ▼                                  ▼
[Stage 2] Time-anchored merge
    │  qwen3 chars assigned to mlx time windows by midpoint containment
    │  → subtitle-sized segments  (<1s runtime)
    ▼
[Stage 3] Refiner:zh (v6 prompt — no cascade/orphan rules, +mid-word fix polish)
    │  → broadcast-quality Cantonese Traditional output
    ▼
Persist → translations[].by_lang.zh
```

Spec reference: §2 (Architecture Diagram), §3 (Stage 0 VAD), §4 (Stages 1A/1B), §5 (Stage 2 merge), §6 (Refiner role).

---

## File 1: 賽馬娛樂新聞 — 4-min Cantonese broadcast (`823a27a9cb32`)

**Original filename:** `【#賽馬娛樂新聞】25:26 #26 新見習騎師🏇袁幸堯不日登場🔥 1080p.mp4`
**Audio duration:** ~4.4 min (last segment end 265.3s)
**Pipeline total runtime:** 126.6s (2.1×)

### Per-stage breakdown

| Stage | Type | Output segs | Duration |
|---|---|---|---|
| 0 | `vad` | 28 regions | 0.8s |
| 1 | `qwen3_per_region` | 1,066 chars | 39.2s |
| 2 | `asr_primary` (mlx) | 87 segs | 24.9s |
| 3 | `time_anchored_merge` | 83 segs | 0.016s |
| 4 | `refiner:zh` | 83 segs | 61.6s |

**Final translations:** 83

### Quality metrics

| Metric | Result |
|---|---|
| Traditional glyph ratio | 100% (0 simplified chars in 1,142 CJK) |
| Cantonese particles (嘅咗喺啦嘢唔哋咁嚟係) | 103 total |
| Cascade duplicates | 0 |
| Refiner quality flags raised | 0 |

### Entity name accuracy

| Entity | Correct form hits | Wrong form hits |
|---|---|---|
| 袁幸堯 | 3 | 0 (袁庆尧/袁幸尧: 0) |
| 史滕雷 | 3 | 0 (史腾雷: 0) |
| 美狼王 | 2 | 0 (美郎王: 0) |
| 麥道朗 | 2 | 0 |
| 艾少禮 | 2 | 1 × 艾少麗 (idx 26 — passthrough from qwen3 source, not refiner regression) |
| 推騎 | 1 | 0 (推棋: 0) |
| Highland Blink | 1 | 0 (Highland Bling: 0) |
| 寶馬香港打吡 | 1 | 0 (大悲大賽: 0) |
| 賈西迪 | 2 | 0 |
| 潘頓 | 2 | 0 (潘頓外虎: 0) |
| 肯德百利 | 2 | 0 |
| 布浩穎 | 1 | 0 |

Entity accuracy ~95%+ across 12 named entities. The single 艾少麗 variant (idx 26) originates from the qwen3 source text `出世嗰日艾少麗正正一日贏出四場頭馬` — the same segment's source_text already carries the variant spelling, indicating the qwen3 transcription itself produced one inconsistent form. The refiner preserved the source faithfully rather than hallucinating a correction.

### Known issue captured

**Issue A — mlx broken-time mega-seg:** Segment [39] spans `120.48–146.48s` (26.0s). The mlx time-grid produced a single large window that collapsed multiple qwen3 char-spans into one segment during Stage 2 merge. The refiner output for this segment is a long correctly-phrased block (`少禮之外，另外一位騎師最近亦上演贏到傻嘅神級演出…`). Content is correct; timecode boundary is the issue. Stage 1.5 mlx pre-cleanup (spec §7 deferred) would split this window before merge.

---

## File 2: 14-min Cantonese vlog (`59d9544aec52`)

**Original filename:** `YTDown_YouTube_Media_RjPHoNEei_g_001_1080p.mp4`
**Audio duration:** ~14.2 min (last segment end 849.8s)
**Pipeline total runtime:** 459.2s (0.54× realtime)

### Per-stage breakdown

| Stage | Type | Output segs | Duration |
|---|---|---|---|
| 0 | `vad` | 72 regions | 2.4s |
| 1 | `qwen3_per_region` | 4,556 chars | 175.4s |
| 2 | `asr_primary` (mlx) | 574 segs | 42.6s |
| 3 | `time_anchored_merge` | 533 segs | 0.34s |
| 4 | `refiner:zh` | 533 segs | 238.3s |

**Final translations:** 533

### Quality metrics

| Metric | Result |
|---|---|
| Traditional glyph ratio | 100% (0 simplified chars in 4,517 CJK) |
| Cantonese particles (嘅咗喺啦嘢唔哋咁嚟係) | 747 total |
| Cascade duplicates | 0 |
| Short fragments (≤2 chars) | 1 (`你好` at idx 27 — valid greeting, not a fragment artifact) |
| JSON wrapper replies | 0 |
| "please provide JSON" hallucinations | 0 |
| Refiner quality flags raised | 0 |

### Path B fixes — confirmed resolved

| Fix | Commit | Status |
|---|---|---|
| B — Refiner `max_tokens=300` | `99d5360` | ✅ No truncation observed |
| C — Short-input bypass (≤5 chars skip LLM) | `99d5360` | ✅ 1 fragment passed through cleanly |
| D — Stage 2 fragment merge (≤1-char segs absorbed) | `99d5360` | ✅ 28→1 fragmentation reduction |

### JSON unwrap fix confirmed

Option C hybrid (`862558d`) — refiner output is clean polished broadcast text with no JSON wrapper artifacts in any of the 533 translations.

### Known issue captured

**Issue A (same root cause):** Segment [362] spans `512.48–537.48s` (25.0s), `'我們一齊一十幾年了'`. One occurrence per 14.2 min audio, consistent with 1 per ~5–15 min estimate from spec §7.

---

## Comparative Quality Metrics

| Metric | 賽馬 4.4 min (`823a27a9cb32`) | Winning Factor (EN) | 14-min vlog (`59d9544aec52`) |
|---|---|---|---|
| Audio duration | 4.4 min | — | 14.2 min |
| Pipeline runtime | 126.6s (0.48× realtime) | TBD | 459.2s (0.54× realtime) |
| Final segments | 83 | TBD | 533 |
| Traditional glyph ratio | 100% | TBD | 100% |
| Cantonese particles | 103 | TBD | 747 |
| Cascade duplicates | 0 | TBD | 0 |
| JSON artifacts | 0 | TBD | 0 |
| Issue A mega-seg occurrences | 1 (seg [39], 26s) | TBD | 1 (seg [362], 25s) |

*Winning Factor EN pipeline exists in config (`4696bbaa-b988-49bd-859c-e742cb365634`) but operator validation run not yet executed — marked TBD.*

---

## Known Issues and Status

**Issue A — mlx broken-time mega-seg**
⚠️ **DEFERRED** per spec §7. Observed once per ~5–15 min of audio (1 occurrence in each of the two validation files). Root cause: mlx-whisper occasionally produces a single large time window (25–26s) in its time-grid output; Stage 2 merge correctly collapses all qwen3 chars within that window into one subtitle segment. Content is correct; only the timecode boundary is suboptimal. Planned resolution: Stage 1.5 mlx pre-cleanup (v6.1 follow-up). Acceptable for initial v6 release.

**Path B fixes — ✅ resolved**
Refiner `max_tokens=300` + short-input bypass + Stage 2 fragment merge (commit `99d5360`) eliminated all fragmentation, JSON truncation, and "please provide JSON" hallucinations observed during pre-fix runs. Clean output confirmed on both validation files.

**JSON unwrap fix — ✅ resolved**
Option C hybrid unwrap (commit `862558d`) strips `{"refined_text": "..."}` wrapper while remaining backward-compatible with v5 plain-text refiner output. Zero JSON artifacts in 616 total segments validated.

---

## Out-of-Scope (acknowledged in spec §7)

- Stage 1.5 mlx pre-cleanup (Issue A) — deferred to v6.1
- Translator stage rewrite — not in v6 scope
- Persist schema rewrite — auto-resolved by refiner length stability
- Full Pipelines page builder UI for v6 (currently load-by-ID mode in frontend)
- Validation on Winning Factor EN pipeline — operator follow-up

---

## Verdict

- ✅ Architecture validated end-to-end on 2 Cantonese clips covering ~18.6 min total audio
- ✅ All 5 stages execute in correct order (`vad → qwen3_per_region → asr_primary → time_anchored_merge → refiner:zh`), persist correctly to `translations[].by_lang.zh`, no v5-A5 index-misalignment bug
- ✅ Quality wins: 100% Traditional glyph, ~95%+ entity accuracy on Cantonese broadcast proper nouns, broadcast-quality Cantonese particle preservation, zero cascade duplicates, zero JSON/hallucination artifacts
- ✅ Sub-realtime pipeline: 0.48–0.54× realtime on both files
- 🟡 1 deferred issue (Issue A, mlx mega-seg) — 1 occurrence per file, content correct, timecode suboptimal, acceptable for initial v6 release

---

## Recommended Next Steps

1. **v6.1 (high value):** Stage 1.5 mlx pre-cleanup — split mlx time-grid windows >10s before Stage 2 merge to resolve Issue A
2. **v7 (medium value):** Per-segment entity normalization pass — resolve `艾少禮` / `艾少麗` inconsistency that persists from qwen3 source output
3. **Optional:** Silero VAD param tuning (currently using spec defaults: `threshold=0.5`, `min_speech_duration_ms=250`, `speech_pad_ms=200`) — test on music-heavy clips
4. **Production deploy:** Recommended after operator runs 1–2 additional validation files (esp. Winning Factor EN pipeline to confirm cross-lingual path)
