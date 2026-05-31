"""_reset_progress_for_job clears a stale snapshot and seeds the new stage (2026-05-31).

Regression for the queue-panel staleness bug: re-running a file that previously
finished a different stage made /api/queue serve the prior job's terminal
snapshot (e.g. a just-started ASR job showed "翻譯 100%").
"""
from app import _reset_progress_for_job
from progress_adapter import get_adapter, reset_adapter


def _seed_stale_translate_done(file_id):
    """Simulate the prior translate job having finished at 翻譯 100%."""
    get_adapter().report(
        file_id=file_id, job_id="old-job", pct=100,
        stage_state="active", pipeline_kind="profile", stage_index=1,
    )


def test_reset_replaces_stale_translate_with_asr_stage0():
    reset_adapter()
    _seed_stale_translate_done("fR")
    stale = get_adapter().get_snapshot("fR")
    assert stale.stage_index == 1 and stale.stage_label == "翻譯" and stale.pct == 100

    # New ASR (profile) job starts → reset to stage 0.
    _reset_progress_for_job("fR", "new-asr", "profile", 0)

    snap = get_adapter().get_snapshot("fR")
    assert snap is not None
    assert snap.stage_index == 0
    assert snap.stage_label == "轉錄"
    assert snap.pct == 0
    assert snap.stage_state == "active"
    assert snap.job_id == "new-asr"


def test_reset_to_translate_stage1_for_retranslate():
    reset_adapter()
    # Prior ASR finished at 轉錄.
    get_adapter().report(
        file_id="fT", job_id="old-asr", pct=100,
        stage_state="active", pipeline_kind="profile", stage_index=0,
    )
    _reset_progress_for_job("fT", "new-mt", "profile", 1)
    snap = get_adapter().get_snapshot("fT")
    assert snap.stage_index == 1 and snap.stage_label == "翻譯" and snap.pct == 0


def test_reset_seeds_v6_first_stage():
    reset_adapter()
    _reset_progress_for_job("fV", "v6-job", "pipeline_v6", 0)
    snap = get_adapter().get_snapshot("fV")
    assert snap.pipeline_kind == "pipeline_v6"
    assert snap.stage_index == 0
    assert snap.stage_label == "VAD 切段"


def test_reset_never_raises_on_bad_input():
    reset_adapter()
    # Should swallow any error (progress reporting must never break a job).
    _reset_progress_for_job(None, None, "profile", 0)
    _reset_progress_for_job("fX", "j", "unknown_kind", 5)  # out-of-range stage
