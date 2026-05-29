"""v3.20 T4 — concurrent-drain pattern survives stderr flood.

Invokes _drain_subprocess against the real prototype flood_child.py with
256 KB stderr payload. Asserts:
  - completes within 5s
  - stderr_bytes >= 250_000 (drain captured all of it)
  - stdout_bytes >= 40 (final JSON marker survived)
  - subprocess was reaped (rc == 0)

The whole point of this test is real OS-pipe coverage — DO NOT mock
subprocess.Popen here. The prototype validation report
(docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md)
showed the OLD pattern hangs at >= 64 KB stderr. This test forces 256 KB
to prove the NEW pattern drains it cleanly.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from engines.transcribe.qwen3_vad_engine import _drain_subprocess


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FLOOD_CHILD = (
    _REPO_ROOT / "backend" / "scripts" / "v6_prototype" / "_children" / "flood_child.py"
)


@pytest.fixture(autouse=True)
def _assert_child_exists():
    assert _FLOOD_CHILD.is_file(), (
        f"flood_child fixture missing at {_FLOOD_CHILD}. "
        "Prototype scaffolding must exist for this test."
    )


def test_drain_handles_256kb_stderr_flood_without_hang():
    """OLD pattern hangs at >= 64 KB stderr (per prototype report). NEW pattern
    must drain 256 KB cleanly in well under 5 seconds."""
    payload = {"stderr_kb": 256}
    proc = subprocess.Popen(
        [sys.executable, str(_FLOOD_CHILD)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdin.write(json.dumps(payload).encode("utf-8"))
    proc.stdin.close()

    t0 = time.time()
    stdout_bytes, stderr_bytes = _drain_subprocess(proc, timeout_sec=60)
    wall = time.time() - t0

    assert wall < 5.0, (
        f"drain took {wall:.2f}s — should be well under 5s for 256 KB stderr. "
        "Possible regression: drain threads not running concurrently with poll loop."
    )
    assert len(stderr_bytes) >= 250_000, (
        f"only drained {len(stderr_bytes)} stderr bytes — expected >= 250_000. "
        "Drain thread may have exited early or dropped bytes."
    )
    assert len(stdout_bytes) >= 40, (
        f"stdout JSON marker missing — got {len(stdout_bytes)} bytes: {stdout_bytes!r}"
    )
    parsed = json.loads(stdout_bytes)
    assert parsed.get("ok") is True
    assert parsed.get("wrote_kb") == 256
    assert proc.returncode == 0


def test_drain_forwards_stderr_lines_to_progress_callback():
    """Optional progress_callback (T7) receives each complete \\n-terminated
    stderr line. Best-effort — exceptions in the callback do not propagate."""
    payload = {"stderr_kb": 4}  # small but >1 line
    proc = subprocess.Popen(
        [sys.executable, str(_FLOOD_CHILD)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdin.write(json.dumps(payload).encode("utf-8"))
    proc.stdin.close()

    received: list = []

    def _cb(line: str) -> None:
        received.append(line)

    stdout_bytes, stderr_bytes = _drain_subprocess(
        proc, timeout_sec=30, progress_callback=_cb
    )
    assert proc.returncode == 0
    assert len(received) > 0, "progress_callback was never invoked"
    # Each forwarded line should NOT include the terminating newline.
    assert all("\n" not in line for line in received), (
        "progress_callback received lines containing embedded newlines — "
        "drain should split on \\n and strip the terminator."
    )
    # Flood child emits `[line N] XXXXX...` per stderr line.
    assert any("[line" in line for line in received), (
        f"unexpected callback content (first 3): {received[:3]}"
    )
