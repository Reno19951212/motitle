"""v3.20 T4 — wall-clock timeout fires on hung subprocess.

Invokes _drain_subprocess against slow_child.py (sleeps 30s) with
timeout_sec=2. Asserts:
  - raises RuntimeError mentioning "exceeded" / "timeout"
  - wall time is between 2s and 6s (timeout + terminate grace + overhead)
  - subprocess was reaped (proc.poll() is not None after raise)

Real subprocess — no mocks. The whole reason this fix exists is the OLD
pattern had no timeout at all (would hang forever on pipe-buffer
deadlock). T1.5 (R5_QWEN3_TIMEOUT_SEC=900) is the production safety net;
this test asserts the mechanism functions at all.
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
_SLOW_CHILD = (
    _REPO_ROOT / "backend" / "scripts" / "v6_prototype" / "_children" / "slow_child.py"
)


@pytest.fixture(autouse=True)
def _assert_child_exists():
    assert _SLOW_CHILD.is_file(), f"slow_child fixture missing at {_SLOW_CHILD}"


def test_drain_raises_runtime_error_on_wall_clock_timeout():
    payload = {"duration_sec": 30}
    proc = subprocess.Popen(
        [sys.executable, str(_SLOW_CHILD)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdin.write(json.dumps(payload).encode("utf-8"))
    proc.stdin.close()

    t0 = time.time()
    with pytest.raises(RuntimeError) as exc_info:
        _drain_subprocess(proc, timeout_sec=2)
    wall = time.time() - t0

    # Message must clearly indicate it was a timeout, not a generic failure.
    msg = str(exc_info.value).lower()
    assert "exceeded" in msg or "timeout" in msg, (
        f"RuntimeError message should mention exceeded/timeout, got: {exc_info.value!r}"
    )

    # Wall time bounds: deadline (2s) + 0.5s poll latency + 3s terminate grace
    # = ~5.5s upper. Lower bound is 2s (cannot fire before deadline).
    assert 2.0 <= wall <= 6.0, (
        f"timeout fired at wall={wall:.2f}s — expected between 2s and 6s. "
        "Either timeout mechanism is wrong or the test machine is severely loaded."
    )

    # Subprocess must be reaped — no zombie left behind.
    assert proc.poll() is not None, (
        "subprocess still running after timeout — terminate/kill cleanup failed"
    )
