# V6 Qwen3 Subprocess IPC Fix — Plan

**Date**: 2026-05-29
**Branch**: `fix/v6-subprocess-ipc`
**Spec**: [specs/2026-05-29-v6-subprocess-ipc-fix-design.md](../specs/2026-05-29-v6-subprocess-ipc-fix-design.md)
**Validation gate** (CLAUDE.md Validation-First Mode):
- ✅ Empirical evidence captured: [validation/2026-05-29-v6-ipc-deadlock-evidence.md](../validation/2026-05-29-v6-ipc-deadlock-evidence.md)
- ⏳ Prototype gate: T2 must pass before T3+ are allowed to merge

## Branch state at plan time
- 611f7fd (base, from `Finalize`)
- 97d789a docs: incident + evidence
- c2256fc fix(media): preload=metadata + conditional send_file (T5 — already in this branch)

---

## Phase 1 — Prototype + Validation (gate)

### T1. Build IPC drain prototype harness
- [ ] Create `backend/scripts/v6_prototype/ipc_drain_prototype.py`
- [ ] Generate two child scripts under `backend/scripts/v6_prototype/_children/`:
  - `flood_child.py` — writes N KB of stderr in tight loop then exits 0 with a tiny stdout JSON
  - `slow_child.py` — writes 1 stderr line/sec then exits 0 after 30s
- [ ] Implement `run_with_old_pattern(child, env, timeout_wall=120)` — exact copy of current `_call_subprocess` poll loop, no drain
- [ ] Implement `run_with_new_pattern(child, env, timeout_wall=120)` — drain threads + wall-clock timeout
- [ ] CLI: `python ipc_drain_prototype.py --pattern={old,new} --child={flood,slow} --stderr-kb=N`
- [ ] Report stdout JSON: `{pattern, child, stderr_kb, hung, wall_sec, stdout_bytes, stderr_bytes}`

### T2. Run validation matrix + report
- [ ] Matrix: pattern ∈ {old, new} × child ∈ {flood, slow} × stderr_kb ∈ {1, 16, 64, 256, 1024}
- [ ] Expected results table:
  | pattern | child | stderr_kb | hung | wall_sec |
  |---------|-------|-----------|------|----------|
  | old | flood | 1 | no | <1 |
  | old | flood | 16 | no | <1 |
  | old | flood | 64 | **yes** | timeout(120) |
  | old | flood | 1024 | **yes** | timeout(120) |
  | new | flood | * | no | <2 |
  | new | slow | * | no | ~30 |
- [ ] Write `docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md` with actual numbers
- [ ] **Gate**: if `new` pattern shows any hung=yes, stop and rework spec §4.1 before T3

---

## Phase 2 — Production code (post-gate)

### T3. Replace poll loop with concurrent drain
- [ ] Edit `backend/engines/transcribe/qwen3_vad_engine.py`:
  - Add module-level `_QWEN3_TIMEOUT_SEC = int(os.environ.get("R5_QWEN3_TIMEOUT_SEC", "900"))`
  - Add `_drain(stream, buf)` helper
  - Replace lines 142-176 with drain-thread version per spec §4.1
- [ ] Self-check: `python -c "import backend.engines.transcribe.qwen3_vad_engine"` imports clean
- [ ] Keep existing `tmpdir` cleanup `finally:` block intact

### T4. Unit tests
- [ ] `backend/tests/test_qwen3_vad_engine_drain.py` — stub Popen, simulate stderr flood, assert no hang, assert stdout JSON parsed correctly
- [ ] `backend/tests/test_qwen3_vad_engine_timeout.py` — stub Popen that never exits, assert `RuntimeError` raised within `_QWEN3_TIMEOUT_SEC + _TERMINATE_GRACE + 1`
- [ ] `backend/tests/test_qwen3_vad_engine_cancel.py` — set `cancel_event` after 0.5s, assert `JobCancelled` within 4s, assert subprocess reaped (`proc.poll() is not None`)
- [ ] `pytest backend/tests/test_qwen3_vad_engine_*.py -v` all green

### T5. Regression — existing tests
- [ ] `pytest backend/tests/ -k qwen3` — must remain green
- [ ] `pytest backend/tests/test_pipeline_runner.py` — must remain green
- [ ] Full `pytest backend/tests/` — accept ≤14 pre-existing failures from v3.19 baseline (11 Playwright E2E, macOS tmpdir, etc.)

### T6. Integration — replay original incident
- [ ] User restarts backend with fix branch checked out (replaces main folder OR runs from worktree on alt port)
- [ ] Re-upload `gamehub-…赤色沙漠.mp4` via V6 `[v6] 賽馬廣播 (Cantonese)` preset
- [ ] Capture timing: VAD → Qwen3 wall time → mlx-whisper → merge → refiner → total
- [ ] Assert total ≤ 600s (1.5× healthy budget)
- [ ] Assert resulting `segments[]` non-empty, `text` populated, status reaches `done`/`completed`
- [ ] Record before/after in `docs/superpowers/validation/2026-05-29-v6-ipc-fix-report.md`

---

## Phase 3 — Observability hook (optional, in-PR if scope allows)

### T7. Per-region progress forwarding to SocketIO
- [ ] Add `progress_callback: Optional[Callable[[str], None]]` kwarg to `_call_subprocess`
- [ ] Update stderr drain to invoke callback per `\n`-terminated line
- [ ] In `backend/stages/v6/qwen3_per_region_stage.py:46` pass a callback that calls `_socketio_emit("pipeline_stage_progress", {...})`
- [ ] Frontend already listens for `pipeline_stage_progress` (from v3.19 V6 merge) — verify DevTools Network → WS frames during real run
- [ ] If scope crunch: skip T7 entirely; flag as follow-up in CLAUDE.md

---

## Phase 4 — Documentation + verification gates

### T8. CLAUDE.md version history entry
- [ ] Add `### v3.20 — V6 Qwen3 Subprocess IPC Hardening` to CLAUDE.md "Completed Features" (top of list)
- [ ] Reference spec, plan, validation report, prototype report
- [ ] Document new env var `R5_QWEN3_TIMEOUT_SEC` in CLAUDE.md "Development Commands" → "Windows CUDA runtime" section (analogous slot)
- [ ] Include the T5 frontend fix from c2256fc as part of same release ("media byte-range storm")

### T9. README.md (Traditional Chinese)
- [ ] Add troubleshooting entry: "V6 pipeline 跑超過 15 分鐘自動 timeout，可調 `R5_QWEN3_TIMEOUT_SEC`"

### T10. CLAUDE.md 4-gate verification
| Gate | How to verify | Status |
|------|---------------|--------|
| 1. 代碼質素 | `pytest backend/tests/test_qwen3_vad_engine_*.py` PASS | ⏳ |
| 2. 功能正確性 | T6 integration on real file completes | ⏳ |
| 3. 整合驗證 | Full `pytest backend/tests/` baseline maintained | ⏳ |
| 4. 文檔完整性 | T8 + T9 done | ⏳ |

---

## Phase 5 — Merge handling

### T11. Resolve `finalize-debug` divergence (user decides)
Two merge paths from `fix/v6-subprocess-ipc`:

- **Path A** — merge into `finalize-debug` (user's active branch). Risk: untracked work in user's main working dir may conflict; user must stash or commit first.
- **Path B** — merge into `Finalize` (clean base), then user manually rebases `finalize-debug` onto updated `Finalize`. Cleaner history, more user work.

Recommendation: **B** if `finalize-debug` is purely debug exploration and not destined for main; **A** if user wants the fix immediately visible in their active debug session.

### T12. Worktree cleanup
- [ ] After merge: `git worktree remove ../whisper-subtitle-ai-v6fix`
- [ ] Optional: `git branch -d fix/v6-subprocess-ipc` (only after merge confirmed)

---

## Estimated effort

| Phase | Effort | Can stop after? |
|-------|--------|----------------|
| 1 — Prototype | 1.5h | Yes — leaves user with empirically-validated fix design but no production change beyond T5 |
| 2 — Production code | 2h | Yes — full fix, no extra observability |
| 3 — SocketIO hook | 0.5h | Yes — nice-to-have |
| 4 — Docs + gates | 0.5h | Required for PR |
| 5 — Merge | 0.1h | User-driven |
| **Total** | **~4.5h** | |

This session targets Phase 1 only (per user choice). Phase 2+ is a separate decision once T2 report lands.

---

## Open questions for user

1. **Restart appetite for T6**: integration replay needs backend restart with fix-branch code. Do you want me to swap, or do you do it from another terminal?
2. **R5_QWEN3_TIMEOUT_SEC default**: 900s OK? Or your broadcast clips routinely exceed 10 min wall?
3. **T7 scope**: include SocketIO progress hook in same PR (cleaner UX, +0.5h) or defer?
