"""Tests for progress_adapter.py — Phase A tasks A1-A5."""
from progress_adapter import ProgressSnapshot


# ── Task A1: ProgressSnapshot construction ────────────────────────────────────

def test_snapshot_construction():
    snap = ProgressSnapshot(
        file_id="abc",
        job_id="job-1",
        pct=42,
        stage_label="轉錄中",
        stage_state="active",
        pipeline_kind="profile",
        updated_at=1234.0,
    )
    assert snap.file_id == "abc"
    assert snap.pct == 42
    assert snap.stage_label == "轉錄中"
    assert snap.stage_state == "active"


# ── Task A2: ProgressAdapter cache + throttled emit ───────────────────────────

def test_report_caches_snapshot():
    from progress_adapter import ProgressAdapter
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)))
    adapter.report(file_id="f1", job_id="j1", pct=50, stage_label="轉錄中",
                   stage_state="active", pipeline_kind="profile")
    snap = adapter.get_snapshot("f1")
    assert snap is not None
    assert snap.pct == 50
    assert emitted[0][0] == "pipeline_progress"
    assert emitted[0][1]["pct"] == 50


def test_throttle_collapses_rapid_reports(monkeypatch):
    """Within 500ms only the latest report goes out as pipeline_progress."""
    from progress_adapter import ProgressAdapter
    fake_time = [1000.0]
    monkeypatch.setattr("progress_adapter.time.monotonic", lambda: fake_time[0])
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)),
                              throttle_seconds=0.5)
    adapter.report(file_id="f1", job_id="j1", pct=10, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    fake_time[0] += 0.1  # 100ms later
    adapter.report(file_id="f1", job_id="j1", pct=15, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    fake_time[0] += 0.1  # 200ms later
    adapter.report(file_id="f1", job_id="j1", pct=20, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    # only the first emit happened (10); 15/20 throttled
    assert len(emitted) == 1
    assert emitted[0][1]["pct"] == 10
    # but cache always has latest
    assert adapter.get_snapshot("f1").pct == 20
    # advance past throttle window — next report goes through
    fake_time[0] += 0.5
    adapter.report(file_id="f1", job_id="j1", pct=25, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    assert len(emitted) == 2
    assert emitted[1][1]["pct"] == 25


def test_done_state_always_emits_no_throttle():
    """stage_state='done' bypasses throttle so 100% is never missed."""
    from progress_adapter import ProgressAdapter
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)),
                              throttle_seconds=10.0)
    adapter.report(file_id="f1", job_id="j1", pct=50, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    adapter.report(file_id="f1", job_id="j1", pct=100, stage_label="x",
                   stage_state="done", pipeline_kind="profile")
    assert len(emitted) == 2
    assert emitted[1][1]["stage_state"] == "done"
