# v4.0 Debug — Phase 2 Triage Report

**Date:** 2026-05-18
**Branch:** debug/v4-e2e-bug-hunt
**Phase 1 effort:** ~1 hour (Track A authoring + Track B scoped manual + Track C static + Track D harvest)

## Summary

| Severity | Count |
|---|---|
| P0 | **0** |
| P1 | **0** |
| P2 | **8** |
| P3 | **20** |
| **Total** | **28** |

| Plan impact | Count |
|---|---|
| 純 bug fix | 11 |
| Spec 假設錯 | 0 |
| 需開新 sub-phase | 0 |
| Defer 入 backlog | 3 |
| Confirmed out-of-scope | 14 |
| **Total** | **28** |

## Abort gate evaluation

- **P0 count: 0** vs threshold 5 (per spec §6)
- **Decision: NOT TRIGGERED** — proceed Phase 3a normally
- v4.0 ship plan stays intact; no parent-phase rewrite needed; no escalation to A7/A8 sub-phases

## Top P2 findings (preview for Phase 3a)

1. **BUG-010 [A6 C4]: `request_id` always null in log lines** — werkzeug logger fires outside Flask context, `has_request_context()` returns False. Response header set correctly, but log lines unstamped. **Implementation regression vs A6 C4 stated invariant.**
2. **BUG-011 [A6 C4]: 20+ `print()` calls in app.py bypass logger** — Under `LOG_JSON=1` they emit plain text into JSON stream, breaking log aggregator.
3. **BUG-004 [A4]: PromptOverridesDrawer Save silent no-op** — When `file.pipeline_id` is null, Save button does nothing and shows no feedback. Real UX bug found via Track A authoring.
4. **BUG-006 [A3/A6]: SocketProvider no `connected` state to UI** — Frontend cannot show disconnected banner when backend dies.
5. **BUG-007 [A3/A6]: Stage progress lost on page refresh** — In-memory WebSocket state resets, no HTTP recovery endpoint for in-progress stage %.
6. **BUG-020 [v3.14 backlog]: `/api/translation/engines` Ollama probe missing timeout + memoization** — Endpoint can hang when Ollama down (994ms outlier observed).
7. **BUG-001 [test infra]: Test fixture media file missing** — Upload-path E2E specs auto-skip.
8. **BUG-002 [test infra]: global-setup.ts seed idempotency** — Rerunning seed loses entity IDs on 409.

## Phase 1 effort by track

| Track | Method | Findings | Duration |
|---|---|---|---|
| A (Playwright) | Subagent authoring (no test execution) | 5 BUGs | ~5 min subagent + ~30 min wall |
| B (Manual matrix) | Subagent scoped to §5/6/7 (1/2/4 deferred) | 6 BUGs + 3 DEFERRED markers | ~6 min subagent |
| C (Static analysis) | Subagent surgical greps + tsc + lint | 0 BUGs (1 AUDIT pass) | ~1.5 min subagent |
| D (Known-issue harvest) | Main session inline | 17 entries (mostly out-of-scope audit) | ~10 min main |

**Out-of-scope work that was deferred from Track B (manual real-binary E2E)**:
- Section 1: Real mlx-whisper medium-model ASR runs (Cantonese/English/mixed audio) — DEFERRED-S1
- Section 2: Real Ollama qwen3.5 MT runs (batch_size/parallel/prompt_overrides/passes) — DEFERRED-S2
- Section 4: Real FFmpeg renders (12 sub-formats including MXF ProRes 6 profiles + XDCAM 3 bitrates) — DEFERRED-S4
- Section 3: OpenRouter (no API key) — N/A

These represent the **deepest E2E validation** but require dedicated human-driven session (hours). Recommend running as separate validation phase post-debug branch if user wants higher confidence before v4.0 ship.

## Recommended Phase 3a focus

User decision needed on:

1. **Branch close target** (spec §11): baseline (P0=100% + P1≥50% close) vs ambitious (P0+P1=100% + P2 budget). Since 0 P0/P1, baseline is essentially "do nothing" and ambitious is "fix all 11 純 bug fix items".

2. **A6 C4 logging fixes** (BUG-010, BUG-011): high recommendation to fix before any production deployment. These break log aggregator compatibility.

3. **Test infrastructure** (BUG-001, BUG-002, BUG-003): unlocks running E2E suite end-to-end. Cheap and self-contained.

4. **A4 UX bugs** (BUG-004, BUG-005): polish items, BUG-004 is actual usability bug.

5. **A3/A6 frontend reliability** (BUG-006, BUG-007, BUG-008, BUG-009): incremental UX hardening.

6. **Track B deferred sections**: do we want to run real ASR/MT/render E2E in a separate session? Or accept current confidence level?

## Conclusion

v4.0 surface is in **healthier shape than the spec hypothesis predicted**:
- A5 cleanup invariant clean (Track C 0 bug)
- No design-level gap requiring sub-phase
- All 28 findings are either implementation-level fix-ups, known-deferred features, or audit-trail confirmations
- No P0 / P1 → no ship blocker

Most impactful 純 bug fix candidates are the A6 C4 logging fixes (BUG-010, BUG-011) and the SocketProvider reliability gaps (BUG-006, BUG-007).
