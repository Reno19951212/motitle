# V6 Qwen3 Subprocess IPC Fix — Design

**Date**: 2026-05-29
**Status**: Draft (post-validation)
**Branch**: `fix/v6-subprocess-ipc` (worktree at `../whisper-subtitle-ai-v6fix/`)
**Related**:
- Incident: [incidents/2026-05-29-v6-silent-execution-handover.md](../incidents/2026-05-29-v6-silent-execution-handover.md)
- Empirical evidence: [validation/2026-05-29-v6-ipc-deadlock-evidence.md](../validation/2026-05-29-v6-ipc-deadlock-evidence.md)

## 1. Problem statement

Qwen3 VAD subprocess (`backend/scripts/v5_prototype/qwen3_vad_subprocess.py`) writes per-region status to **stderr** (line 124 + 128) and a final JSON payload to **stdout** (line 130). Parent (`backend/engines/transcribe/qwen3_vad_engine.py:154-165`) polls `proc.poll()` in a `time.sleep(0.5)` loop and only reads `proc.stdout` / `proc.stderr` AFTER the subprocess exits (lines 168-169). When child's writes exceed macOS pipe buffer (~16 KB), child blocks in kernel `write()` syscall and never exits → parent polls forever.

Live `sample 49396` capture: 100% of 2604 samples in `_io_FileIO_write → _Py_write_impl → write (libsystem_kernel)`. All MLX worker threads idle. Inference completed, output flush wedged.

No `timeout=` kwarg anywhere → no safety net.

## 2. Goals

| # | Goal | Acceptance |
|---|------|-----------|
| G1 | Eliminate stderr/stdout pipe-buffer deadlock | Stress-test with stderr flood ≥ 1 MB completes, before-fix hangs |
| G2 | Bound worst-case wall time | `R5_QWEN3_TIMEOUT_SEC` env (default 900s); on expiry, child SIGTERM + clean error to caller |
| G3 | Preserve existing cancel semantics | `cancel_event.set()` from worker thread terminates child within ≤1s |
| G4 | Unlock per-region progress for SocketIO | Parent forwards per-region completion events to `pipeline_stage_progress` |
| G5 | Backward-compatible behavior | Existing successful V6 jobs produce identical output JSON |

Non-goals (kept for later iteration):
- Stage 3 refiner timeout (different process — Ollama HTTP)
- mlx-whisper Stage 1B timeout
- Retry-on-timeout (poison-pill cap at `R5_MAX_JOB_RETRY=3` already handles this)
- Replacing subprocess with in-process MLX call (Python 3.9 vs 3.11 venv split blocks this)

## 3. Design options considered

### Option A — Concurrent drain via `threading.Thread` (chosen)
Two daemon threads each call `proc.stdout.read()` / `proc.stderr.read()` and buffer into bytearrays. Main thread polls `cancel_event` + `proc.wait(timeout=…)`. On normal exit, join drain threads, parse stdout JSON, optionally forward stderr lines.

**Pros**: stdlib-only; ~30 LOC change; thread-safe with current `JobQueue` model; works on macOS + Linux without `selectors` portability concerns.
**Cons**: two extra OS threads per job (acceptable — ASR worker pool size = 1).

### Option B — `subprocess.communicate(timeout=…)`
Standard Python idiom. Drains both pipes via internal threads in `subprocess`.

**Pros**: minimal LOC.
**Cons**: doesn't expose **streaming** progress (only post-exit blob), so G4 not achievable without losing G2. Combining with cancel is also awkward — `communicate()` raises `TimeoutExpired` but doesn't react to external `cancel_event`.

### Option C — `asyncio.subprocess` rewrite
Native async streaming.

**Pros**: cleanest progress streaming.
**Cons**: V6 `_run_v6` is currently synchronous; adding an event loop to a sync stage call introduces a big architectural shift unrelated to the bug. Defer.

### Option D — Child-side switch from stderr → stdout JSONL streaming
Child writes one JSON line per region completion to stdout, then a `done` marker. Final structured result via separate channel (e.g. final line `{"type":"done","regions":[...]}`).

**Pros**: cleaner contract; parent can forward each line immediately.
**Cons**: requires Option A regardless (still need concurrent drain). Treat as additive enhancement on top of A.

**Chosen**: **Option A** for the structural fix. **Option D** as an additive enhancement in the same PR if scope allows; otherwise punt to follow-up.

## 4. Detailed design (Option A)

### 4.1 Parent — `backend/engines/transcribe/qwen3_vad_engine.py`

Replace the poll loop (lines 142-176) with:

```python
import os, threading

_QWEN3_TIMEOUT_SEC = int(os.environ.get("R5_QWEN3_TIMEOUT_SEC", "900"))
_CANCEL_POLL_INTERVAL = 0.5
_TERMINATE_GRACE = 3.0

proc = subprocess.Popen(
    [str(self._venv_python), str(self._subprocess_script)],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
proc.stdin.write(stdin_bytes)
proc.stdin.close()

stdout_buf = bytearray()
stderr_buf = bytearray()
stderr_lines: list[str] = []   # for progress forwarding (G4)

def _drain(stream, buf, line_collector=None):
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        buf.extend(chunk)
        if line_collector is not None:
            # forward complete \n-terminated lines (best-effort decode)
            text = chunk.decode("utf-8", errors="replace")
            line_collector.append(text)

t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_buf),
                         daemon=True, name="qwen3-stdout-drain")
t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_buf, stderr_lines),
                         daemon=True, name="qwen3-stderr-drain")
t_out.start(); t_err.start()

deadline = time.time() + _QWEN3_TIMEOUT_SEC
try:
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try: proc.wait(timeout=_TERMINATE_GRACE)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            from jobqueue.queue import JobCancelled
            raise JobCancelled("Qwen3 subprocess cancelled by cancel_event")
        if time.time() > deadline:
            proc.terminate()
            try: proc.wait(timeout=_TERMINATE_GRACE)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            raise RuntimeError(
                f"qwen3_vad subprocess exceeded {_QWEN3_TIMEOUT_SEC}s timeout"
            )
        time.sleep(_CANCEL_POLL_INTERVAL)
finally:
    # Always join drain threads so we don't leak file descriptors
    t_out.join(timeout=5)
    t_err.join(timeout=5)

rc = proc.returncode
if rc != 0:
    raise RuntimeError(
        f"qwen3_vad subprocess failed (rc={rc}):\n"
        f"{bytes(stderr_buf).decode(errors='replace')[:500]}"
    )
return json.loads(bytes(stdout_buf))
```

### 4.2 Optional — progress forwarding hook (G4)

`_call_subprocess` gains optional `progress_callback: Callable[[str], None] | None`. The stderr drain thread invokes it on every complete `\n`-terminated line. `pipeline_runner._run_v6` passes a callback that emits `pipeline_stage_progress` SocketIO events.

Without this hook, behavior is identical to current production (stderr buffered, presented only on error).

### 4.3 No child-side changes required for fix

`qwen3_vad_subprocess.py` is **unchanged** in this iteration. The deadlock is purely on the parent side — once parent drains, child's existing stderr-per-region writes work fine. Option D (child JSONL streaming) is deferred to a follow-up; G4 is achievable from current child output by parsing the existing stderr format.

### 4.4 Cancel semantics (G3)

Unchanged behavior surface:
- Worker thread sets `cancel_event`
- Parent main loop sees flag within `_CANCEL_POLL_INTERVAL` (0.5s) → `terminate()` → grace wait → `kill()`
- Drain threads exit when stdout/stderr pipes close (immediate on `kill`)
- `JobCancelled` propagates up to `JobQueue._run_one` → marks job `status='cancelled'`

End-to-end cancel latency: ≤ 0.5s + ≤ 3s grace = **≤3.5s worst case**.

### 4.5 Timeout policy (G2)

- Env var: `R5_QWEN3_TIMEOUT_SEC`, default `900` (15 min — comfortably above the 4-6 min healthy budget + 50% headroom for cold-cache loads)
- On timeout: same shutdown sequence as cancel, but raises `RuntimeError` (not `JobCancelled`) so `JobQueue` marks the job `status='failed'` with `error_msg` set
- The poison-pill cap (`R5_MAX_JOB_RETRY=3` from v3.13 Phase 5 T1.5) handles auto-retry suppression

### 4.6 Backward compatibility

- Successful jobs: byte-identical `stdout_buf` parsed via same `json.loads` → return value unchanged
- Failed jobs: stderr truncation point identical (`[:500]`)
- Cancel: same exception class (`JobCancelled`), same flow
- New failure mode: timeout → `RuntimeError` with explicit message — clean and observable
- No DB schema change. No registry schema change. No SocketIO contract change (unless 4.2 hook is wired)

## 5. Testing strategy

| Layer | Test |
|-------|------|
| Unit (new) | `test_qwen3_vad_engine_drain.py` — fake subprocess that floods stderr, verify no hang, verify drain bytes complete |
| Unit (new) | `test_qwen3_vad_engine_timeout.py` — fake subprocess that sleeps past timeout, verify `RuntimeError` raised within deadline + grace |
| Unit (new) | `test_qwen3_vad_engine_cancel.py` — verify `cancel_event` interrupts within ≤1s, `JobCancelled` raised, no resource leak |
| Prototype script | `backend/scripts/v6_prototype/ipc_drain_prototype.py` — reproduces production deadlock with **old** drain pattern, demonstrates fix with **new** pattern. Quantitative report (hang rate, max stderr bytes) committed to validation tracker |
| Integration | Re-run V6 on the original gamehub Cantonese file (`183e38257865`) against fix branch — should finish within 4-6 min |
| Regression | Existing `test_qwen3_vad_engine_*` tests must pass unchanged |

## 6. Risk / mitigation

| Risk | Mitigation |
|------|------------|
| Drain thread leaks if main raises before `join()` | `finally:` join with timeout |
| Thread join blocks forever if child also frozen | `t_*.join(timeout=5)` — accept a bounded leak (5s) over hang |
| `proc.stdout.read(4096)` returns very large chunk before close → memory blow | Chunked 4096; total bounded by realistic Qwen3 output (~10-100 KB final + ~1-10 KB stderr) |
| New timeout false-positives on legit long broadcasts | 900s default is 50% headroom over observed P95; env var overridable |
| Drain thread daemon=True silently drops final bytes if main returns early | We `.join()` so this can't happen on normal path |

## 7. Files touched (estimate)

- `backend/engines/transcribe/qwen3_vad_engine.py` — ~40 LOC delta (replace poll loop + add drain helpers + timeout env)
- `backend/tests/test_qwen3_vad_engine_drain.py` — new, ~80 LOC
- `backend/tests/test_qwen3_vad_engine_timeout.py` — new, ~50 LOC
- `backend/tests/test_qwen3_vad_engine_cancel.py` — new, ~60 LOC
- `backend/scripts/v6_prototype/ipc_drain_prototype.py` — new, ~120 LOC (validation harness)
- `docs/superpowers/validation/2026-05-29-v6-ipc-fix-report.md` — new, post-prototype run
- `CLAUDE.md` — version history entry (after fix lands)

No change to: child subprocess, V6 pipeline runner, SocketIO contract (unless 4.2 wired — flagged for plan).

## 8. Out-of-scope follow-ups

1. **Child-side stdout JSONL streaming** (Option D) — better long-term contract
2. **Per-stage SocketIO `pipeline_stage_progress`** for refiner — same drain pattern applies to Ollama HTTP
3. **V6 logger wiring** — separate concern (T4 in incident report); add `app.logger.info` at every stage boundary
4. **mlx-whisper Stage 1B timeout** — same risk class, different engine
5. **Real-time per-region progress UI** in proofread.html — needs the SocketIO hook from §4.2 to be wired first
