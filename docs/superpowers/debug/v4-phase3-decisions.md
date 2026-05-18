# v4.0 Debug — Phase 3a Decisions

**Date:** 2026-05-18
**User:** Reno
**Branch close target:** **Ambitious** (per spec §11.2)

## Branch close criteria (locked)

- P0 = 100% close (N/A — 0 P0)
- P1 = 100% close (N/A — 0 P1)
- **P2 = 100% close** (all 8 → ALL → 7 fixable + 1 confirmed out-of-scope; the 7 fixable get Phase 3b tasks)
- **P3 純 bug fix bucket = 100% close** (4 entries: BUG-003, BUG-009, BUG-018; plus BUG-001 if classified as P2 vs P3 — keeping as P2)
- P3 Defer bucket → confirmed defer (no fix in this branch): 3 entries
- Confirmed out-of-scope → audit trail only: 14 entries

## Per-bug disposition

| BUG ID | Title | Severity | Disposition |
|---|---|---|---|
| BUG-001 | Test fixture media file missing | P2 | **Fix in Phase 3b** |
| BUG-002 | global-setup seed idempotency | P2 | **Fix in Phase 3b** |
| BUG-003 | Windows env syntax (cross-env) | P3 | **Fix in Phase 3b** (cheap, P3 純 bug fix) |
| BUG-004 | PromptOverridesDrawer silent no-op | P2 | **Fix in Phase 3b** |
| BUG-005 | StageRerunMenu empty dropdown | P3 | Defer (confirm) |
| BUG-006 | SocketProvider no connection state | P2 | **Fix in Phase 3b** |
| BUG-007 | Stage progress lost on refresh | P2 | **Fix in Phase 3b** |
| BUG-008 | No WebSocket event dedup | P3 | Defer (confirm) |
| BUG-009 | Proofread chunk naming | P3 | **Fix in Phase 3b** (cheap, P3 純 bug fix) |
| BUG-010 | request_id null in log lines | P2 | **Fix in Phase 3b** |
| BUG-011 | print() bypass logger | P2 | **Fix in Phase 3b** |
| BUG-012–017, 021–028 | Confirmed out-of-scope (14) | P3 | No action — audit trail |
| BUG-018 | Socket.IO emitter docs cleanup | P3 | **Fix in Phase 3b** (cheap docs cleanup) |
| BUG-019 | faster-whisper batched | P3 | Defer (confirm) |
| BUG-020 | Ollama probe timeout | P2 | **Fix in Phase 3b** |

## Track B deferred real E2E sections (DEFERRED-S1/S2/S4)

User decision: **Run inline as Phase 3b**.

| Section | Description | Phase 3b task |
|---|---|---|
| S1 | Real mlx-whisper medium ASR runs (en/zh/mixed) — 6 checklist items | **Phase 3b inline task** |
| S2 | Real Ollama qwen3.5 MT runs (batch/parallel/override/passes) — 5 checklist items | **Phase 3b inline task** |
| S4 | Real FFmpeg render (MP4 CRF/CBR/2pass + ProRes 6 profiles + XDCAM 3 bitrates) — 12 checklist items | **Phase 3b inline task** |
| S3 | OpenRouter | N/A — no API key |

These run as 3 manual-driven tasks within Phase 3b. Will require backend running + real models loaded + test media file present.

## Phase 3b scope (locked)

**14 fix tasks** + **3 deferred-real-E2E tasks** + **3 defer confirmation entries** = **17 actionable items + 3 doc-only**:

### Fix tasks (14) — sorted by recommended execution order

**Group 1: Test infra (do first, unblocks rest)**
1. BUG-001 — Add test fixture media file
2. BUG-002 — global-setup seed idempotency (getOrCreate helper)
3. BUG-003 — cross-env Windows compat

**Group 2: A6 C4 logging fixes (production-impact)**
4. BUG-010 — request_id propagation to werkzeug logger
5. BUG-011 — Replace 20+ print() with logger calls

**Group 3: A4 UX bugs**
6. BUG-004 — PromptOverridesDrawer disable Save when no pipeline_id

**Group 4: A3/A6 SocketProvider reliability**
7. BUG-006 — Add connected state + connect/disconnect handlers
8. BUG-007 — Stage progress recovery on page refresh

**Group 5: Bundle + backlog cleanup**
9. BUG-009 — Proofread chunk naming via manualChunks
10. BUG-018 — Remove dead Socket.IO emitter rows from CLAUDE.md + frontend types
11. BUG-020 — Ollama probe timeout + memoization

### Real E2E validation tasks (3)
12. Track B S1 — mlx-whisper real-audio runs
13. Track B S2 — Ollama real-MT runs
14. Track B S4 — FFmpeg real-render across 12 sub-formats

### Defer confirmation tasks (3 lightweight)
15. BUG-005 — Confirm defer entry in v4-deferred-backlog.md
16. BUG-008 — Confirm defer entry
17. BUG-019 — Confirm defer entry

## Estimated Phase 3b effort

| Task group | Tasks | Wall time |
|---|---|---|
| Group 1 (test infra) | 3 | ~30 min |
| Group 2 (A6 logging) | 2 | ~45 min |
| Group 3 (A4 UX) | 1 | ~15 min |
| Group 4 (Socket reliability) | 2 | ~60 min |
| Group 5 (cleanup) | 3 | ~45 min |
| Real E2E (S1/S2/S4) | 3 | ~3-4 hr (user-driven; backend + models loaded) |
| Defer confirmations | 3 | ~5 min |
| **Total** | **17** | **~5-6 hr** |

## Sign-off

- [x] User reviewed v4-phase2-report.md
- [x] User approved Ambitious target (P2 100% + 純 bug fix P3 100%)
- [x] User approved Real E2E inline as Phase 3b
- [ ] Plan amended (T15)
- [ ] Phase 3b execution (T16+)
