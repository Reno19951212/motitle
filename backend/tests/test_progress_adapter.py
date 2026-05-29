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


# ── Task A3: Profile shim helpers ─────────────────────────────────────────────

def test_profile_shim_subtitle_segment():
    """Translates subtitle_segment payload to pipeline_progress."""
    from progress_adapter import ProgressAdapter, report_from_subtitle_segment
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, p: emitted.append((evt, p)))
    report_from_subtitle_segment(
        adapter,
        file_id="f1",
        job_id="j1",
        segment_payload={"progress": 0.5, "eta_seconds": 30, "total_duration": 600},
    )
    assert emitted[-1][1]["pct"] == 50
    assert emitted[-1][1]["stage_label"] == "轉錄中"
    assert emitted[-1][1]["stage_state"] == "active"
    assert emitted[-1][1]["pipeline_kind"] == "profile"


def test_profile_shim_translation_progress():
    from progress_adapter import ProgressAdapter, report_from_translation_progress
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, p: emitted.append((evt, p)))
    report_from_translation_progress(
        adapter,
        file_id="f1",
        job_id="j1",
        translation_payload={"percent": 80, "completed": 8, "total": 10},
    )
    assert emitted[-1][1]["pct"] == 80
    assert emitted[-1][1]["stage_label"] == "翻譯中"


# ── Task A4: V6 shim helper ───────────────────────────────────────────────────

def test_v6_shim_stage_progress_5_stages():
    """V6 has 5 internal stages; each stage's 0-100% maps to its slice of total."""
    from progress_adapter import ProgressAdapter, report_from_v6_stage
    emitted = []
    adapter = ProgressAdapter(
        emit_fn=lambda evt, p: emitted.append((evt, p)),
        throttle_seconds=0,  # disable for test
    )
    # Stage 0 (VAD) at 100% → pct = 20
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=0, stage_type="vad",
                         stage_percent=100, total_stages=5)
    assert emitted[-1][1]["pct"] == 20
    # Stage 2 (mlx) at 50% → pct = 40 + 10 = 50
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=2, stage_type="asr_align",
                         stage_percent=50, total_stages=5)
    assert emitted[-1][1]["pct"] == 50
    # Stage 4 (refiner) at 100% → pct = 100, done
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=4, stage_type="refiner",
                         stage_percent=100, total_stages=5)
    assert emitted[-1][1]["pct"] == 100


def test_v6_shim_uses_stage_label_map():
    from progress_adapter import report_from_v6_stage, V6_STAGE_LABELS
    assert V6_STAGE_LABELS["vad"] == "VAD 切段中"
    assert V6_STAGE_LABELS["asr_primary"] == "Qwen3 識別中"
    assert V6_STAGE_LABELS["asr_align"] == "mlx 對齊中"
    assert V6_STAGE_LABELS["merge"] == "Merge 中"
    assert V6_STAGE_LABELS["refiner"] == "Refiner 校對中"


# ── Task A5: Singleton accessor ───────────────────────────────────────────────

def test_singleton_returns_same_instance():
    from progress_adapter import get_adapter, reset_adapter
    reset_adapter()
    a = get_adapter()
    b = get_adapter()
    assert a is b
    reset_adapter()


# ── Task A6: app.py shim wiring (unit-level smoke check) ─────────────────────

def test_app_subtitle_segment_emit_triggers_adapter(monkeypatch):
    """Smoke check: calling the helper inside the emit path updates the cache.
    This is a unit-level confirmation that the shim helpers are importable
    from the same paths used by app.py."""
    from progress_adapter import get_adapter, reset_adapter, report_from_subtitle_segment
    reset_adapter()
    adapter = get_adapter()
    report_from_subtitle_segment(adapter, file_id="fid-A6", job_id="",
                                  segment_payload={"progress": 0.42})
    snap = adapter.get_snapshot("fid-A6")
    assert snap is not None
    assert snap.pct == 42
    assert snap.stage_label == "轉錄中"
    reset_adapter()


# ── Task A7: pipeline_runner._socketio_emit bridges V6 stage ─────────────────

def test_pipeline_runner_socketio_emit_bridges_v6_stage():
    """Structural assertion: report_from_v6_stage must appear inside
    _socketio_emit function body in pipeline_runner.py.
    This verifies the wiring without fragile module reload."""
    import ast
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "pipeline_runner.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_socketio_emit":
            fn_src = ast.get_source_segment(src, node)
            assert fn_src is not None, "_socketio_emit not found"
            assert "report_from_v6_stage" in fn_src, (
                "report_from_v6_stage not wired inside _socketio_emit"
            )
            return
    raise AssertionError("_socketio_emit function not found in pipeline_runner.py")
