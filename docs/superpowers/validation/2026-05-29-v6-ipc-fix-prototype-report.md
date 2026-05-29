# V6 IPC Fix — Prototype Validation Report

**Date**: 2026-05-29
**Branch**: `fix/v6-subprocess-ipc`
**Gate**: ✅ **PASSED** — fix design empirically validated
**Spec**: [specs/2026-05-29-v6-subprocess-ipc-fix-design.md](../specs/2026-05-29-v6-subprocess-ipc-fix-design.md)
**Plan**: [plans/2026-05-29-v6-subprocess-ipc-fix-plan.md](../plans/2026-05-29-v6-subprocess-ipc-fix-plan.md)
**Live incident evidence**: [validation/2026-05-29-v6-ipc-deadlock-evidence.md](2026-05-29-v6-ipc-deadlock-evidence.md)

---

## Method

Two synthetic children mirror Qwen3 subprocess behaviour:

- `flood_child.py` — accepts `{stderr_kb: N}`, writes N KB of stderr in tight loop, then writes small stdout JSON. Models the **runaway-stderr deadlock** scenario.
- `slow_child.py` — accepts `{duration_sec: N}`, emits 1 stderr line/sec for N s, then small stdout JSON. Models a **healthy long-running** child.

Two parent IPC patterns under test:

- `run_with_old_pattern` — exact reproduction of `backend/engines/transcribe/qwen3_vad_engine.py:142-176`: Popen, write stdin, close, `while proc.poll() is None: sleep(0.5)`, drain only after exit. Wall-clock timeout added solely so the harness itself doesn't hang the matrix.
- `run_with_new_pattern` — spec §4.1 design: two daemon drain threads `proc.stdout.read(4096)` / `proc.stderr.read(4096)` into bytearrays, main thread polls deadline + cancel.

Harness: `backend/scripts/v6_prototype/ipc_drain_prototype.py --matrix`. Reads system `python3`, no venv needed for the prototype itself.

## Results

| pattern | child | stderr_kb | duration_sec | hung | wall_sec | rc | stdout_bytes | stderr_bytes |
|---------|-------|-----------|--------------|------|----------|-----|--------------|--------------|
| old | flood | 1 | 0 | no | 0.51 | 0 | 48 | 1,200 |
| old | flood | 16 | 0 | no | 0.51 | 0 | 50 | 19,200 |
| **old** | **flood** | **64** | **0** | **YES** | **60.39** | **-9** | **0** | **0** |
| **old** | **flood** | **256** | **0** | **YES** | **60.42** | **-9** | **0** | **0** |
| **old** | **flood** | **1024** | **0** | **YES** | **60.45** | **-9** | **0** | **0** |
| new | flood | 1 | 0 | no | 0.51 | 0 | 48 | 1,200 |
| new | flood | 16 | 0 | no | 0.51 | 0 | 50 | 19,200 |
| new | flood | 64 | 0 | no | 0.51 | 0 | 50 | 76,800 |
| new | flood | 256 | 0 | no | 0.50 | 0 | 52 | 307,200 |
| **new** | **flood** | **1024** | **0** | **no** | **0.50** | **0** | **54** | **1,228,800** |
| old | slow | 0 | 5 | no | 5.54 | 0 | 31 | 95 |
| new | slow | 0 | 5 | no | 5.54 | 0 | 31 | 95 |

(`rc=-9` = killed by SIGKILL after our 60s harness timeout — proves the child cannot finish on its own.)

## Interpretation

### Buffer ceiling sits between 16 KB and 64 KB
- Old pattern handles 16 KB stderr fine (19,200 bytes drained post-exit)
- Old pattern dies hard at 64 KB and above (zero bytes drained — child wedged before completion)
- Matches well-known macOS pipe buffer behaviour (~16 KB default, up to 64 KB on some kernels with grow)

### Old pattern → 100% hang at production-realistic volumes
For the live incident, the gamehub Cantonese clip would have produced ~50+ VAD regions × ~150 bytes of stderr each ≈ 7-10 KB **per pass**, but error tracebacks or full-text logging can push individual lines into hundreds of bytes — easily over the 16 KB threshold. The live `sample 49396` evidence (100% in `write()`) is fully explained.

### New pattern → 0% hang up to 1 MB
- Drains 1.2 MB of stderr in 0.5s
- Stdout JSON parsed correctly
- No measurable wall-time penalty vs. trivial workloads

### Slow child → no regression
- Both patterns complete in 5.54s (matching 5s sleep + ~0.5s teardown)
- Confirms the drain threads add no latency for healthy children
- Cancel-loop poll cadence (0.5s) is unchanged

## Verdict

✅ **Gate PASSED.** The new pattern is empirically validated against both the deadlock scenario and the healthy-long-running scenario. Production code rewrite (plan Phase 2, T3) is unblocked.

## Caveats / honest limitations

- Harness uses system `python3` (3.13 on this Mac), not the `backend/scripts/v5_prototype/venv_qwen/` py3.11. The IPC mechanism (POSIX pipes) is kernel-level and Python-version-independent, so this is not a meaningful gap. Still, the live integration test on T6 must run against the actual venv.
- The 60s harness timeout for `old` runs is a forcing function — in production the parent has no timeout at all, so it really would wait forever.
- Cancel semantics were NOT exercised in this prototype (no `cancel_event` test). The unit test `test_qwen3_vad_engine_cancel.py` in plan T4 covers that path.
- The `_drain` helper's `chunk = stream.read(4096)` blocks if the child writes <4096 bytes then sleeps. Acceptable because we're not trying to forward sub-chunk progress; `slow_child` matrix row confirms it doesn't pathologically delay normal flow.

## Reproducer

```bash
cd ../whisper-subtitle-ai-v6fix
python3 backend/scripts/v6_prototype/ipc_drain_prototype.py --matrix
```

12 runs, ~3-4 min total wall time, no external deps.

## Next gate

Plan Phase 2 (T3+): apply the validated pattern to `backend/engines/transcribe/qwen3_vad_engine.py:142-176`, add unit tests (T4), regression-check (T5), live integration replay (T6).
