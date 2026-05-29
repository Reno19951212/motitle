# V6 Qwen3 Subprocess Pipe-Deadlock — Empirical Validation

**Date**: 2026-05-29
**Validation status**: ✅ **Validated** (live system reproduction)
**Related incident**: [incidents/2026-05-29-v6-silent-execution-handover.md](../incidents/2026-05-29-v6-silent-execution-handover.md)
**CLAUDE.md regime**: Validation-First Mode — ASR engine layer changes require empirical validation before spec/plan/code.

---

## Hypothesis tested

> Qwen3 VAD subprocess (`backend/scripts/v5_prototype/qwen3_vad_subprocess.py`) blocks indefinitely because:
> - Child writes per-region progress to **stderr** (line 128) and a final big JSON blob to **stdout** (line 130)
> - Parent (`backend/engines/transcribe/qwen3_vad_engine.py:154-165`) polls `proc.poll()` in a `time.sleep(0.5)` loop, but **only drains stdout/stderr AFTER subprocess exit** (lines 168-169)
> - macOS pipe buffer is **16 KB** — once filled, the child's `write()` syscall blocks
> - Child blocks on write → parent's `poll()` never sees non-None → infinite wait
> - No `timeout=` kwarg anywhere → no safety net

## Method

1. Identified live stuck process: PID 49396, spawned at 16:20:31, parent PID 48537 (Flask backend).
2. Verified job DB row in `backend/data/app.db`:
   - `id=2f6198039fef412fb3fc85cf81c05976, type=asr, status=running`
   - `started_at=2026-05-29 16:20:29, finished_at=NULL`
   - `error_msg=NULL, attempt_count=1`
3. Confirmed process was **alive but quiescent** via `ps -o pid,stat,time`:
   - STAT `S` (sleeping)
   - CPU time `0:36.50` over **~34 min wall time** (~1.8% CPU)
4. Captured C-level stack trace using macOS `sample 49396 3`.

## Evidence

### Process state at sample time

```
PID 49396 (qwen3_vad_subprocess.py)
- STAT: S (interruptible sleep)
- CPU time:          0:36.50
- Wall time:         ~34 min since spawn (16:20:31 → 16:54:58)
- Physical footprint: 6.4 GB (peak 14.6 GB)
- Parent: PID 48537 (Flask backend)
```

The 14.6 GB peak followed by 6.4 GB resident is consistent with **MLX Qwen3-ASR model load completed, then partially freed scratch buffers**. Active inference would not show this drop pattern.

### Main thread stack (100% of 2604 samples)

```
2604 Thread_50416435   DispatchQueue_1: com.apple.main-thread  (serial)
  2604 start (dyld)
    2604 Py_BytesMain
      2604 Py_RunMain
        2604 pymain_run_file
          2604 pymain_run_file_obj
            2604 _PyRun_AnyFileObject
              2604 _PyRun_SimpleFileObject
                2604 pyrun_file
                  2604 run_mod
                    2604 run_eval_code_obj
                      2604 PyEval_EvalCode
                        2604 _PyEval_EvalFrameDefault
                          2604 _io_TextIOWrapper_write       ← Python text I/O
                            2604 _textiowrapper_writeflush
                              2604 PyObject_VectorcallMethod
                                2604 method_vectorcall_O
                                  2604 _io_BufferedWriter_write
                                    2604 _bufferedwriter_flush_unlocked
                                      2604 _bufferedwriter_raw_write
                                        2604 PyObject_VectorcallMethod
                                          2604 method_vectorcall_O
                                            2604 _io_FileIO_write
                                              2604 _Py_write_impl
                                                2604 write (libsystem_kernel.dylib)  ← kernel block
```

**Interpretation**: 100% of samples land on `write()` at the libsystem_kernel layer. This is the kernel returning `EAGAIN`-equivalent / blocking the syscall because the pipe's read side has not been drained. Classic POSIX pipe full-buffer wait.

### Worker thread states (all idle)

- `Thread_50416438` (workqueue): `__workq_kernreturn` (idle worker pool)
- `Thread_50416455` (Python GIL holder): `lock_PyThread_acquire_lock` → `__psynch_cvwait` (waiting on GIL)
- `Thread_50416461..50416466` (MLX `ThreadPool`): all in `std::condition_variable::wait` → `__psynch_cvwait` (idle)
- `Thread_50416465` (`mlx::core::scheduler::StreamThread::thread_fn`): idle

**Interpretation**: No MLX compute is in flight. Model has finished inference (or is between calls) and is sitting idle waiting for input that the main thread can't process because the main thread is wedged in `write()`.

## Verdict

✅ **Hypothesis confirmed with 100% sample coverage and no contradictory thread state.**

Diagnosis is unambiguous:
1. Qwen3 subprocess finished its actual MLX work
2. Tried to flush text output (stderr per-region log lines and/or the final stdout JSON blob)
3. Wrote past the 16 KB pipe buffer ceiling on macOS
4. Parent never drained pipes during the polling loop
5. Child has been blocked in `write()` syscall for tens of minutes

## Implications for the fix

The fix must address **two complementary failure modes** at the parent IPC boundary (`backend/engines/transcribe/qwen3_vad_engine.py:140-176`):

1. **Concurrent pipe drain** — read stdout and stderr in dedicated threads (or via `selectors`/`asyncio`) so the child's `write()` calls never block on a full buffer.
2. **Wall-clock timeout** — a `R5_QWEN3_TIMEOUT_SEC` env (default 900s) backed by `proc.wait(timeout=…)` so even a true model hang gets killed instead of dangling forever.

Cooperative cancel via `cancel_event` still works once the drain thread is in place — set the event, drain thread sees `proc.terminate()` triggered by main thread, all pipes get closed.

### Child-side improvement (optional, defense in depth)

`qwen3_vad_subprocess.py:128` writes one stderr line per region inside the hot loop. Converting this to **stdout JSON-lines streaming** (one event per region followed by a final `done` event) instead of stderr free-text would let the parent both forward progress to SocketIO in real-time *and* eliminate the stderr volume hazard.

## Out-of-scope (validated by elimination)

- ✗ **MLX inference hang** — refuted; all MLX threads idle, model load completed
- ✗ **HuggingFace cache miss / network retry** — refuted; would show network syscall stack, not write block
- ✗ **Python GIL deadlock** — refuted; all child threads coherent, no GIL contention pattern
- ✗ **Flask worker thread crash** — refuted; job DB row `error_msg=NULL`, parent process alive

## Reproducer kit

To reproduce on demand for regression testing:

1. Upload any Cantonese broadcast clip > ~3 min via V6 pipeline `[v6] 賽馬廣播 (Cantonese)`
2. After ~5 min: `ps -p <child_pid> -o time,stat` — STAT should be `S`, CPU should plateau
3. `sample <child_pid> 3` — main thread should show `_io_FileIO_write → _Py_write_impl → write` stack
4. Compare child's accumulated stderr volume via `lsof -p <child_pid>` to the macOS pipe buffer size

**After fix**: same workload completes within time budget (4-6 min) with no `S` quiescence, stderr drained continuously, and SocketIO `pipeline_stage_progress` events visible in browser DevTools Network panel.
