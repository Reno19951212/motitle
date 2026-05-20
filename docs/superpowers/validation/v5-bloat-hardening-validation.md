# v5 Segment Bloat Hardening — Validation Report

**Date:** 2026-05-20
**Branch:** feat/frontend-redesign
**Spec:** docs/superpowers/specs/2026-05-20-v5-segment-bloat-hardening-design.md
**Plan:** docs/superpowers/plans/2026-05-20-v5-segment-bloat-hardening-plan.md

## Test Coverage Summary

| Root cause | Tests added | Status |
|---|---|---|
| R1 verifier short-window primary preference | 4 + 1 boundary | ✅ |
| R2 mechanical max_tokens cap (3 engines) | 3 | ✅ |
| R3 refiner prompt-level length + hallucination escape | 4 | ✅ |
| R4 refiner meta-language fallback | 9 (8 parametrized + 1 negative) | ✅ |
| R5 per-segment quality_flags wiring | 6 | ✅ |
| R6 validator (errors, warnings) tuple return | 4 | ✅ |
| T7 end-to-end runaway-LLM smoke | 1 | ✅ |

Total new tests: **32** in `backend/tests/test_v5_bloat_hardening.py`. All passing.

Full backend suite: 912 pass + 21 skip + 14 known baseline failures (unchanged from pre-hotfix baseline).

## Manual Re-Run Instructions

To validate against real Whisper + Qwen3-ASR + Ollama Qwen3.5:

1. Restart backend so the prompt-template + engine changes load.
2. Re-run the v5 賽馬 pipeline (`ec2d55ba-dee7-4a32-8316-e8c2327aa2d9`) on file_id `906b5f3c3925`.
3. Re-run the v5 Winning Factor pipeline (`b49ef5d4-c325-46df-acc4-03d8d6074113`) on file_id `1490fdd1b682` — but FIRST fix the source_lang misconfig (recreate the pipeline with `asr_primary.source_lang=en`).
4. Inspect `backend/data/registry.json` for both files. Per-segment acceptance criteria (mirrors spec § Validation):

| Metric | Before | Target |
|---|---|---|
| p95 segment char count (賽馬) | 128 | ≤ 60 |
| p95 segment char count (Winning Factor) | 59 | ≤ 50 |
| max segment char count | 436 | ≤ 200 |
| `[ERROR]`/`Sorry`-prefixed segments | 1+ | 0 |

5. Save the snapshot script output (audit_bloat.py from the original investigation) to both:
   - `docs/superpowers/validation/v5-bloat-hardening-baseline.json` (pre-fix; copy from the investigation already done)
   - `docs/superpowers/validation/v5-bloat-hardening-post.json` (post-fix; new run)

6. Frontend visual check: open Dashboard → click 賽馬 row → inspector "實時字幕" panel should show no `[ERROR]` or untranslated long English passages on a ZH pipeline.

## Implementation Commit Chain

| Task | Commit | Description |
|---|---|---|
| T1 | `0084b4c` | max_tokens caps on 3 engines (R2) |
| T2 | `b41232c` | Refiner meta-language fallback (R4) |
| T3 | `c3e8155` | Verifier R1 short-window primary preference |
| T4 (initial) | `a9804de` | Refiner prompts gain length cap + hallucination escape (R3) |
| T4 (path fix) | `a0ff8cf` | Cwd-independent test file paths |
| T4 (ZH conflict) | `700b968` | Resolve ZH Rule 1 vs Rule 7 precedence |
| T5 | `c35ee99` | Per-segment quality_flags (R5) + T3 follow-up fixes |
| T6 (initial) | `25bd77e` | Validator returns (errors, warnings) (R6) |
| T6 (key bug fix) | `a8ae681` | Translator-key format fix + Test 2 rewrite |
| T6 (warnings 400) | `bb3b823` | Attach warnings to 400 body + TODO for v5 PATCH validation |
| T7 | `f1701b3` | Integration smoke (runaway LLM bounded) |
| T8 | _this commit_ | Docs |

## Out of Scope (Deferred to Future Phase)

- Source-lang auto-detection from audio (Phase 7+).
- Re-segmenting secondary's long-window output to align with primary timecodes (Phase 7+).
- v5 branch in `PipelineManager.update_if_owned` to fully validate v5 PATCH (TODO comment placed in `routes/pipelines.py`).
- Backfilling existing registry entries with new flags — new runs only.
- The `"I cannot."` (period, no trailing space) refiner meta-prefix gap (T2 code-review minor).
- Tightening refiner output check for legitimate empty when input was non-empty in the translator path (T5 code-review minor — translator does not currently emit `empty_recovered`).

## Known Limitations

The R6 translator-gap warning fires only when the hard error also fires (same condition). The 400 response body now includes the warning text alongside the error for human-readable detail. The warning is technically "redundant" but kept for future advisory-only mode (e.g., dry-run validation).

## Self-Review

After implementation:
- All 6 root causes from the spec have at least one test covering them.
- Placeholder scan: no TBDs, no `# TODO: implement` in production code — only one `TODO: add v5 branch` in `routes/pipelines.py` referring to a Phase 5 follow-up (allowed: refers to a tracked architectural debt, not a placeholder).
- Type consistency: all engine output dicts now carry `flags: list[str]`. `_persist_by_lang` reads via `segs[i].get("flags", []) or []`. Validator returns `tuple[list[str], list[str]]` consistently across all 3 production call sites + 12 test call sites + 4 new test call sites.
