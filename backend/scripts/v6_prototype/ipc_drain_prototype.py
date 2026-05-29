#!/usr/bin/env python3
"""IPC Drain Prototype — V6 Qwen3 subprocess pipe-deadlock validation harness.

Reproduces production deadlock with the **old** parent IPC pattern (poll loop,
no drain), then demonstrates the **new** pattern (concurrent drain threads +
wall-clock timeout) eliminates the hang.

Per CLAUDE.md Validation-First Mode: this script must show empirical
quantitative evidence before the production code at
`backend/engines/transcribe/qwen3_vad_engine.py` is touched.

Usage:
    python ipc_drain_prototype.py --pattern=old --child=flood --stderr-kb=64
    python ipc_drain_prototype.py --pattern=new --child=flood --stderr-kb=64
    python ipc_drain_prototype.py --matrix    # runs full validation matrix

Output: single JSON line per run, easy to parse / append to report.
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_CHILDREN = {
    "flood": _SCRIPT_DIR / "_children" / "flood_child.py",
    "slow": _SCRIPT_DIR / "_children" / "slow_child.py",
}

_POLL_INTERVAL = 0.5
_TERMINATE_GRACE = 3.0


def run_with_old_pattern(child: Path, stdin_payload: dict,
                         timeout_wall: float = 120.0) -> dict:
    """Exact copy of current backend/engines/transcribe/qwen3_vad_engine.py
    poll loop (lines 142-176). Does NOT drain stdout/stderr during the wait."""
    t0 = time.time()
    proc = subprocess.Popen(
        [sys.executable, str(child)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdin.write(json.dumps(stdin_payload).encode("utf-8"))
    proc.stdin.close()

    hung = False
    while proc.poll() is None:
        if time.time() - t0 > timeout_wall:
            proc.kill()
            proc.wait()
            hung = True
            break
        time.sleep(_POLL_INTERVAL)

    if not hung:
        stdout_bytes = proc.stdout.read()
        stderr_bytes = proc.stderr.read()
    else:
        stdout_bytes = b""
        stderr_bytes = b""

    return {
        "pattern": "old",
        "hung": hung,
        "wall_sec": round(time.time() - t0, 2),
        "rc": proc.returncode,
        "stdout_bytes": len(stdout_bytes),
        "stderr_bytes": len(stderr_bytes),
    }


def run_with_new_pattern(child: Path, stdin_payload: dict,
                         timeout_wall: float = 120.0) -> dict:
    """Concurrent-drain pattern from spec §4.1. Two daemon threads each call
    proc.stdout.read() / proc.stderr.read() into bytearrays. Main thread polls
    proc.poll() + wall-clock deadline."""
    t0 = time.time()
    proc = subprocess.Popen(
        [sys.executable, str(child)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdin.write(json.dumps(stdin_payload).encode("utf-8"))
    proc.stdin.close()

    stdout_buf = bytearray()
    stderr_buf = bytearray()

    def _drain(stream, buf):
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            buf.extend(chunk)

    t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_buf),
                             daemon=True, name="stdout-drain")
    t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_buf),
                             daemon=True, name="stderr-drain")
    t_out.start()
    t_err.start()

    hung = False
    deadline = t0 + timeout_wall
    try:
        while proc.poll() is None:
            if time.time() > deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=_TERMINATE_GRACE)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                hung = True
                break
            time.sleep(_POLL_INTERVAL)
    finally:
        t_out.join(timeout=5)
        t_err.join(timeout=5)

    return {
        "pattern": "new",
        "hung": hung,
        "wall_sec": round(time.time() - t0, 2),
        "rc": proc.returncode,
        "stdout_bytes": len(stdout_buf),
        "stderr_bytes": len(stderr_buf),
    }


def run_one(pattern: str, child_name: str, stderr_kb: int = 0,
            duration_sec: int = 30, timeout_wall: float = 120.0) -> dict:
    child = _CHILDREN[child_name]
    payload = {"stderr_kb": stderr_kb, "duration_sec": duration_sec}
    runner = run_with_old_pattern if pattern == "old" else run_with_new_pattern
    result = runner(child, payload, timeout_wall=timeout_wall)
    result["child"] = child_name
    result["stderr_kb"] = stderr_kb
    result["duration_sec"] = duration_sec
    return result


def run_matrix() -> list:
    """Validation matrix per plan T2."""
    results = []
    matrix = [
        ("old", "flood", 1),
        ("old", "flood", 16),
        ("old", "flood", 64),
        ("old", "flood", 256),
        ("old", "flood", 1024),
        ("new", "flood", 1),
        ("new", "flood", 16),
        ("new", "flood", 64),
        ("new", "flood", 256),
        ("new", "flood", 1024),
        ("old", "slow", 0),
        ("new", "slow", 0),
    ]
    for pattern, child, stderr_kb in matrix:
        duration_sec = 5 if child == "slow" else 0
        timeout_wall = 30.0 if child == "slow" else 60.0
        sys.stderr.write(
            f"[matrix] running pattern={pattern} child={child} "
            f"stderr_kb={stderr_kb} duration_sec={duration_sec}...\n"
        )
        sys.stderr.flush()
        result = run_one(pattern, child, stderr_kb=stderr_kb,
                          duration_sec=duration_sec, timeout_wall=timeout_wall)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))
        sys.stdout.flush()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", choices=["old", "new"])
    parser.add_argument("--child", choices=list(_CHILDREN.keys()))
    parser.add_argument("--stderr-kb", type=int, default=0)
    parser.add_argument("--duration-sec", type=int, default=30)
    parser.add_argument("--timeout-wall", type=float, default=120.0)
    parser.add_argument("--matrix", action="store_true",
                        help="Run full validation matrix")
    args = parser.parse_args()

    if args.matrix:
        run_matrix()
        return

    if not args.pattern or not args.child:
        parser.error("Either --matrix or both --pattern and --child required")

    result = run_one(args.pattern, args.child,
                     stderr_kb=args.stderr_kb,
                     duration_sec=args.duration_sec,
                     timeout_wall=args.timeout_wall)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
