# v4.0 Debug — Deferred Backlog

Findings marked `Defer 入 backlog` 或 `Confirmed out-of-scope` 收集處。

## Format

每條一個 H2，list source tracker BUG-NNN，原因 + future action。

## Entries (3 active defers + 14 confirmed-out-of-scope refs)

### BUG-005: StageRerunMenu renders dropdown when stage_outputs empty

- **Source**: master tracker BUG-005
- **Severity**: P3
- **Reason**: Cosmetic UX gap — the `<details>` dropdown still renders `<summary>Re-run</summary>` even when there are no stages to re-run. Clicking shows "No stages yet." text. Not data-incorrect, not functionally blocking — just misleading affordance.
- **Future action**: Conditionally hide entire `<details>` block when `stages.length === 0` in `StageRerunMenu.tsx`. Or style the summary as disabled when empty. Low priority — re-evaluate if user testing flags it as confusing.

### BUG-008: No WebSocket event sequence/dedup on reconnect

- **Source**: master tracker BUG-008
- **Severity**: P3
- **Reason**: Theoretical race condition — Socket.IO reconnect could replay old `pipeline_stage_progress` event, regressing the progress bar visually. **Socket.IO's at-most-once delivery guarantees** make this rare in practice. No observed regression in production / dev.
- **Future action**: If observed in real usage (e.g., user reports "progress bar jumps backward"), add monotonic `seq: int` to backend event payloads + frontend reducer tracks `lastSeq` per file and skips events with `seq <= lastSeq`. Until then, defer.

### BUG-019: faster-whisper BatchedInferencePipeline not tried

- **Source**: master tracker BUG-019 (originally from v3.14 Phase 6 backlog)
- **Severity**: P3
- **Reason**: `backend/asr/whisper_engine.py` uses sequential `WhisperModel().transcribe()` API. faster-whisper 4.0+ adds `BatchedInferencePipeline` claiming 30-50% speedup on large audio files. **Switching the API requires real-audio validation** because batched inference can produce subtly different segment boundaries / quality vs sequential — possibly violating Validation-First Mode invariant (per CLAUDE.md).
- **Future action**: Dedicated ASR perf optimization phase post-v4.0 ship. Must run V0-V3-style validation: capture baseline output → swap to batched → diff each metric (segment count, char distribution, hallucination rate, follow rate) → only ship if quality ≥ baseline. Defer until ASR perf becomes user-facing bottleneck.

---

## Confirmed out-of-scope entries (14 — audit trail reference only)

These were captured in Track D as known-deferred features documented in CLAUDE.md "Out-of-scope" sections. No action expected in this debug branch:

- **BUG-012** — StreamingSession class still inline in app.py (A6 C2 didn't extract it)
- **BUG-013** — Mac/Win packaging not done
- **BUG-014** — Mobile responsive layout not done
- **BUG-015** — i18n framework not introduced
- **BUG-016** — Storybook not introduced
- **BUG-017** — CI/CD GitHub Actions not configured (P2 — most production-impact among OOS, but spec §10 excludes)
- **BUG-021** — Domain context anchor (per-file subject prefix) [v3.18 Stage 3+]
- **BUG-022** — Forbidden phrases list (negative vocabulary) [v3.18 Stage 3+]
- **BUG-023** — User self-service prompt template publishing [v3.18 Stage 3+]
- **BUG-024** — Glossary stacking (multi-glossary per pipeline) [v3.18 Stage 3+]
- **BUG-025** — Per-file retry strategy config [v3.18 Stage 3+]
- **BUG-026** — A/B prompt comparison feature [v3.18 Stage 3+]
- **BUG-027** — MT-side s2hk simplified-Chinese leak post-process [v3.18 Stage 3+]
- **BUG-028** — ASR-side fragment merge Stage 1 (intentionally skipped per user direction) [Closed]

Full content for these 14 entries lives in `v4-bug-tracker-trackD-known.md`.

---

## Re-evaluation triggers

When to revisit defer / out-of-scope entries:

- **BUG-005**: User explicitly reports the empty dropdown as confusing
- **BUG-008**: Observed progress-bar regression in production
- **BUG-019**: ASR latency becomes user-visible bottleneck OR faster-whisper 5.0+ ships with breaking changes to old API
- **BUG-012 (Streaming)**: Decision to revive live-recording mode for v4.x
- **BUG-013 (packaging)**: Distribution requirement from non-developer users
- **BUG-014 (mobile)**: Demand for proofreading on tablet / phone
- **BUG-017 (CI/CD)**: Team grows beyond solo / next contributor onboards
- **BUG-021-027 (v3.18 Stage 3+)**: Translation quality findings post-v4.0 ship suggest next iteration scope
