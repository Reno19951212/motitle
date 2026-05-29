"""v3.20 T4 — cancel_event interrupts an in-flight subprocess.

Runs _drain_subprocess against slow_child.py (sleeps 30s) in a background
thread; main thread sleeps 0.5s then sets cancel_event. Asserts:
  - JobCancelled is raised inside the worker
  - wall time is <= 4s (0.5s pre-cancel + 0.5s poll latency + 3s grace)
  - subprocess was reaped (proc.poll() is not None after raise)

Real subprocess + threading — no mocks. Replaces the v3.19 Sprint 3 B-8
cancel coverage with a test that pinpoints the drain helper specifically.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from engines.transcribe.qwen3_vad_engine import _drain_subprocess
from jobqueue.queue import JobCancelled


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SLOW_CHILD = (
    _REPO_ROOT / "backend" / "scripts" / "v6_prototype" / "_children" / "slow_child.py"
)


@pytest.fixture(autouse=True)
def _assert_child_exists():
    assert _SLOW_CHILD.is_file(), f"slow_child fixture missing at {_SLOW_CHILD}"


def test_drain_raises_jobcancelled_when_cancel_event_set_mid_flight():
    payload = {"duration_sec": 30}
    proc = subprocess.Popen(
        [sys.executable, str(_SLOW_CHILD)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc.stdin.write(json.dumps(payload).encode("utf-8"))
    proc.stdin.close()

    cancel_event = threading.Event()
    captured_exc: list = []
    t0 = time.time()

    def _runner() -> None:
        try:
            _drain_subprocess(
                proc, timeout_sec=60, cancel_event=cancel_event
            )
        except BaseException as exc:  # capture JobCancelled (and anything else)
            captured_exc.append(exc)

    worker = threading.Thread(target=_runner, name="drain-runner")
    worker.start()

    # Let the subprocess actually start up + log at least one heartbeat
    time.sleep(0.5)
    cancel_event.set()

    worker.join(timeout=8)
    wall = time.time() - t0

    assert not worker.is_alive(), (
        "drain worker still running after cancel — cancel_event was not honored"
    )
    assert len(captured_exc) == 1, (
        f"expected exactly one exception, got: {captured_exc!r}"
    )
    assert isinstance(captured_exc[0], JobCancelled), (
        f"expected JobCancelled, got: {type(captured_exc[0]).__name__}: {captured_exc[0]!r}"
    )

    # Wall budget: 0.5s pre-cancel + 0.5s poll cadence + 3s terminate grace
    assert wall <= 4.0, (
        f"cancel took wall={wall:.2f}s — expected <= 4s. "
        "Cancel polling cadence (_CANCEL_POLL_INTERVAL) may be too slow."
    )

    # Subprocess must be reaped.
    assert proc.poll() is not None, (
        "subprocess still running after JobCancelled — cleanup failed"
    )
