"""Tests for progress_adapter.py — Phase A tasks A1-A5 + v3.22 stage-list contract."""
from progress_adapter import ProgressSnapshot


# ── Task A1: ProgressSnapshot construction ────────────────────────────────────

def test_snapshot_construction():
    snap = ProgressSnapshot(
        file_id="abc",
        job_id="job-1",
        pct=42,
        stage_label="轉錄",
        stage_state="active",
        pipeline_kind="profile",
        stages=[{"key": "transcribe", "label": "轉錄"}],
        stage_index=0,
        updated_at=1234.0,
    )
    assert snap.file_id == "abc"
    assert snap.pct == 42
    assert snap.stage_label == "轉錄"
    assert snap.stage_state == "active"
    assert snap.stage_index == 0
    assert snap.stages[0]["key"] == "transcribe"


# ── Task A2: ProgressAdapter cache + throttled emit ───────────────────────────

def test_report_caches_snapshot():
    from progress_adapter import ProgressAdapter
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)))
    adapter.report(file_id="f1", job_id="j1", pct=50,
                   stage_state="active", pipeline_kind="profile", stage_index=0)
    snap = adapter.get_snapshot("f1")
    assert snap is not None
    assert snap.pct == 50
    assert emitted[0][0] == "pipeline_progress"
    assert emitted[0][1]["pct"] == 50
    assert emitted[0][1]["stage_index"] == 0
    assert "stages" in emitted[0][1]


def test_throttle_collapses_rapid_reports(monkeypatch):
    """Within 500ms only the latest report goes out as pipeline_progress."""
    from progress_adapter import ProgressAdapter
    fake_time = [1000.0]
    monkeypatch.setattr("progress_adapter.time.monotonic", lambda: fake_time[0])
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)),
                              throttle_seconds=0.5)
    adapter.report(file_id="f1", job_id="j1", pct=10,
                   stage_state="active", pipeline_kind="profile", stage_index=0)
    fake_time[0] += 0.1  # 100ms later
    adapter.report(file_id="f1", job_id="j1", pct=15,
                   stage_state="active", pipeline_kind="profile", stage_index=0)
    fake_time[0] += 0.1  # 200ms later
    adapter.report(file_id="f1", job_id="j1", pct=20,
                   stage_state="active", pipeline_kind="profile", stage_index=0)
    # only the first emit happened (10); 15/20 throttled
    assert len(emitted) == 1
    assert emitted[0][1]["pct"] == 10
    # but cache always has latest
    assert adapter.get_snapshot("f1").pct == 20
    # advance past throttle window — next report goes through
    fake_time[0] += 0.5
    adapter.report(file_id="f1", job_id="j1", pct=25,
                   stage_state="active", pipeline_kind="profile", stage_index=0)
    assert len(emitted) == 2
    assert emitted[1][1]["pct"] == 25


def test_done_state_always_emits_no_throttle():
    """stage_state='done' bypasses throttle so 100% is never missed."""
    from progress_adapter import ProgressAdapter
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)),
                              throttle_seconds=10.0)
    adapter.report(file_id="f1", job_id="j1", pct=50,
                   stage_state="active", pipeline_kind="profile", stage_index=0)
    adapter.report(file_id="f1", job_id="j1", pct=100,
                   stage_state="done", pipeline_kind="profile", stage_index=0)
    assert len(emitted) == 2
    assert emitted[1][1]["stage_state"] == "done"


# ── Task A3: Profile shim helpers ─────────────────────────────────────────────

def test_profile_shim_subtitle_segment():
    """Translates subtitle_segment payload to pipeline_progress (stage_index=0)."""
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
    assert emitted[-1][1]["stage_label"] == "轉錄"
    assert emitted[-1][1]["stage_state"] == "active"
    assert emitted[-1][1]["pipeline_kind"] == "profile"
    assert emitted[-1][1]["stage_index"] == 0


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
    assert emitted[-1][1]["stage_label"] == "翻譯"
    assert emitted[-1][1]["stage_index"] == 1


# ── Task A4: V6 shim helper ───────────────────────────────────────────────────

def test_v6_shim_stage_progress_uses_stage_type():
    """V6 shim derives stage index from stage_type, not from caller stage_index."""
    from progress_adapter import ProgressAdapter, report_from_v6_stage
    emitted = []
    adapter = ProgressAdapter(
        emit_fn=lambda evt, p: emitted.append((evt, p)),
        throttle_seconds=0,  # disable for test
    )
    # vad at 100% → stage_index=0, pct=100
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=99,  # caller index ignored
                         stage_type="vad",
                         stage_percent=100, total_stages=5)
    assert emitted[-1][1]["stage_index"] == 0
    assert emitted[-1][1]["stage_label"] == "VAD 切段"
    assert emitted[-1][1]["pct"] == 100

    # qwen3_per_region at 50% → stage_index=1
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=99,
                         stage_type="qwen3_per_region",
                         stage_percent=50, total_stages=5)
    assert emitted[-1][1]["stage_index"] == 1
    assert emitted[-1][1]["stage_label"] == "Qwen3 識別"

    # time_anchored_merge at 50% → stage_index=3
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=99,
                         stage_type="time_anchored_merge",
                         stage_percent=50, total_stages=5)
    assert emitted[-1][1]["stage_index"] == 3
    assert emitted[-1][1]["stage_label"] == "時間合併"

    # refiner:zh at 100% → stage_index=4, state=done
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=99,
                         stage_type="refiner:zh",
                         stage_percent=100, total_stages=5)
    assert emitted[-1][1]["stage_index"] == 4
    assert emitted[-1][1]["stage_state"] == "done"


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
    """Smoke check: calling the helper inside the emit path updates the cache."""
    from progress_adapter import get_adapter, reset_adapter, report_from_subtitle_segment
    reset_adapter()
    adapter = get_adapter()
    report_from_subtitle_segment(adapter, file_id="fid-A6", job_id="",
                                  segment_payload={"progress": 0.42})
    snap = adapter.get_snapshot("fid-A6")
    assert snap is not None
    assert snap.pct == 42
    assert snap.stage_label == "轉錄"
    assert snap.stage_index == 0
    reset_adapter()


# ── Task A7: pipeline_runner._socketio_emit bridges V6 stage ─────────────────

def test_pipeline_runner_socketio_emit_bridges_v6_stage():
    """Structural assertion: report_from_v6_stage must appear inside
    _socketio_emit function body in pipeline_runner.py."""
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


# ── v3.22 new tests: PIPELINE_STAGES shape + _v6_stage_index + shim labels ───

def test_pipeline_stages_shape():
    from progress_adapter import PIPELINE_STAGES
    assert [s["key"] for s in PIPELINE_STAGES["profile"]] == [
        "transcribe", "translate", "proofread"
    ]
    assert [s["key"] for s in PIPELINE_STAGES["pipeline_v6"]] == [
        "vad", "qwen3", "mlx", "merge", "refiner"
    ]


def test_v6_stage_type_to_index_all_five():
    from progress_adapter import _v6_stage_index
    assert _v6_stage_index("vad") == 0
    assert _v6_stage_index("qwen3_per_region") == 1
    assert _v6_stage_index("asr_primary") == 2
    assert _v6_stage_index("time_anchored_merge") == 3
    assert _v6_stage_index("refiner:zh") == 4
    assert _v6_stage_index("refiner:en") == 4


def test_v6_report_emits_label_and_index():
    from progress_adapter import ProgressAdapter, report_from_v6_stage
    ev = []
    a = ProgressAdapter(emit_fn=lambda e, p: ev.append(p), throttle_seconds=0)
    report_from_v6_stage(a, file_id="f", job_id="", stage_index=99,
                         stage_type="time_anchored_merge", stage_percent=50)
    assert ev[-1]["stage_index"] == 3
    assert ev[-1]["stage_label"] == "時間合併"
    assert ev[-1]["stages"][3]["key"] == "merge"


def test_profile_shims_stage_index():
    from progress_adapter import (ProgressAdapter, report_from_subtitle_segment,
                                  report_from_translation_progress)
    ev = []
    a = ProgressAdapter(emit_fn=lambda e, p: ev.append(p), throttle_seconds=0)
    report_from_subtitle_segment(a, file_id="f", job_id="",
                                 segment_payload={"progress": 0.5})
    assert ev[-1]["stage_index"] == 0 and ev[-1]["stage_label"] == "轉錄"
    report_from_translation_progress(a, file_id="f", job_id="",
                                     translation_payload={"percent": 40})
    assert ev[-1]["stage_index"] == 1 and ev[-1]["stage_label"] == "翻譯"
