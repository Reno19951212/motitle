# 2026-05-04 — Phase 2 ZH-direct dialogue prompt A/B validation

## Result: ❌ REJECTED — does not meet acceptance gates

## Hypothesis

For ZH-direct mlx-whisper (`language="zh"` against EN audio), inject a
dialogue-styled bilingual glossary prompt as `initial_prompt` to bias proper-
noun spelling toward the canonical zh form, while preserving short-segment
broadcast cadence.

Format tested:

```
嗯，呢場波好緊湊呀！— Real Madrid (皇家馬德里), Vinicius Junior (雲尼素斯), Bellingham (比寧咸), Ancelotti (安察洛堤), Xabi Alonso (沙比阿朗素) — 沙比話：
```

(119 chars, well under 224-token Whisper context cap.)

## Acceptance gates (from Phase 2 spec)

1. max segment dur ≤ 6.0s (preserve v3.8 acceptance gate)
2. segment count within ±10% of baseline
3. ≥ 2 of 5 entities improved (canonical zh hit count higher in variant)

## Empirical run

- Stack: mlx-whisper large-v3, language="zh", word_timestamps=True,
  condition_on_previous_text=False, temperature=0.0
- Fixture: `/tmp/l1_real_madrid.wav` (Real Madrid sports interview, ~10 min)
- Direct `mlx_whisper.transcribe()` call without VAD chunking — measures
  pure prompt influence on the underlying model

| metric         | baseline (no prompt) | variant (dialogue prompt) | Δ |
| -------------- | -------------------- | ------------------------- | -- |
| segments       | 87                   | 101                       | +16.1% |
| mean dur (s)   | 2.92                 | 2.67                      | -0.25 |
| p95 dur (s)    | 5.20                 | 5.26                      | +0.06 |
| **max dur (s)** | 27.80               | **9.90**                  | -17.90 (still > 6.0s gate) |
| total chars    | 1637                 | 1665                      | +28 |

Canonical-zh hits per glossary entity:

| entity              | baseline | variant | improved? |
| ------------------- | -------- | ------- | --------- |
| Real Madrid (皇家馬德里) | 0        | 0       | no        |
| Vinicius Junior (雲尼素斯) | 0    | 0       | no        |
| Bellingham (比寧咸)   | 0        | 0       | no        |
| Ancelotti (安察洛堤)   | 0        | 0       | no        |
| Xabi Alonso (沙比阿朗素) | 0      | 2       | **yes (1/5)** |

## Verdict

- ❌ Gate 1 — max dur 9.90s > 6.0s (variant did improve from 27.80s but still fails gate)
- ❌ Gate 2 — segment count diff 16.1% > 10%
- ❌ Gate 3 — only 1/5 entities improved (need ≥ 2)

Per Validation-First mandate (CLAUDE.md), Phase 2 was NOT shipped. The
`zh_prompt_builder.py` utility was authored but not wired into the pipeline
or committed.

## Why it failed (analysis)

1. **Max-dur regression vs gate** — Without VAD pre-chunking, the raw mlx
   transcribe path is naturally subject to the 30s decoder window; even
   baseline produces 27.80s max segments. The variant's 9.90s is a real
   improvement but cannot reach 6.0s without VAD. In production this gate
   is enforced by `sentence_split.word_gap_split(safety_max_dur=6.0)` —
   not by the prompt — so the gate as written is testing the wrong axis
   for an `initial_prompt`-only change.

2. **Cadence drift (segment count Δ16.1%)** — Even with a dialogue style,
   the prompt encourages slightly more verbose Chinese output, lengthening
   total chars (1637 → 1665) and changing chunking decisions inside the
   30s window. The styled opener may itself prime longer prose despite
   the dialogue framing.

3. **Entity-correction near-zero** — The model generated 0 canonical hits
   for 4/5 entities even with the prompt present. mlx-whisper Chinese is
   trained primarily on Mandarin; HK Cantonese transliterations like
   "皇家馬德里" / "比寧咸" appear too rarely in training to be retrievable
   via `initial_prompt` alone.

## Better path forward (deferred — needs separate validation cycle)

Phase 1 (zh_aliases post-correction, shipped) directly addresses what
Phase 2 attempted to do via prompting — it deterministically rewrites
wrong-form transliterations to canonical zh AFTER ASR. Combined with the
Phase 0 suppress_tokens guard against subtitle-scrape hallucinations, the
Phase 1 layer is a higher-leverage intervention than Phase 2 prompting,
without the cadence-drift risk.

If a future iteration revisits prompting:

- Test inside `sentence_split.transcribe_fine_seg` (per-chunk path) — the
  30s-window issue is moot once VAD chunking is upstream, so the relevant
  metric becomes "max within a 25s chunk" not "global max"
- Try smaller / shorter prompt (≤ 50 chars opener only, no entity list)
  paired with Phase 1 zh_aliases to handle entity correction
- Consider `prefix` per-chunk anchor with explicit post-strip, paired
  with empirical confirmation of no empty-segment regression
