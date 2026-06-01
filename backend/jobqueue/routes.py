"""REST routes: GET /api/queue, DELETE /api/queue/<id>."""
from flask import Blueprint, jsonify, current_app
from flask_login import login_required, current_user

from jobqueue.db import (
    list_jobs_for_user,
    list_active_jobs,
    get_job,
    update_job_status,
    cancel_if_queued,
    insert_retry_job,
)
from auth.users import get_user_by_id
from auth.limiter import limiter

bp = Blueprint("queue", __name__)
_db_path = None


def set_db_path(p: str) -> None:
    global _db_path
    _db_path = p


def _annotate(jobs: list, db_path: str) -> list:
    """Add owner_username + file_name + position + eta_seconds (None for now)."""
    user_cache = {}
    registry = current_app.config.get("FILE_REGISTRY", {})
    out = []
    for i, j in enumerate(jobs):
        uid = j["user_id"]
        if uid not in user_cache:
            u = get_user_by_id(db_path, uid)
            user_cache[uid] = u["username"] if u else "?"
        file_entry = registry.get(j["file_id"]) or {}
        out.append({**j,
                    "owner_username": user_cache[uid],
                    "file_name": file_entry.get("original_name"),
                    "position": i,
                    "eta_seconds": None})
    return out


@bp.get("/api/queue")
@login_required
# Polled every 3s by every connected client (~20/min/client), shared across
# the team — 60/min was too tight for 3-5 concurrent users. SocketIO push
# also calls refreshQueue so bursty spikes are real.
@limiter.limit("240 per minute")
def list_queue():
    """Global active-queue view shared across all logged-in users.

    Returns only jobs in 'queued' or 'running' status. Completed jobs
    (done/failed/cancelled) drop off the panel as soon as the worker
    transitions out of 'running' — the file card status badges carry the
    post-completion state instead. Each row is annotated with file_name
    + owner_username + progress fields from ProgressAdapter.
    """
    # Import inside handler to avoid circular imports at module load time.
    from progress_adapter import get_adapter as _get_progress_adapter, PIPELINE_STAGES

    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    active = list_active_jobs(db_path)
    rows = _annotate(active, db_path)

    _adapter = _get_progress_adapter()
    registry = current_app.config.get("FILE_REGISTRY", {})
    for row in rows:
        fid = row.get("file_id")
        snap = _adapter.get_snapshot(fid) if fid else None
        if snap is not None:
            row["progress_pct"] = snap.pct
            row["stage_label"] = snap.stage_label
            row["stage_state"] = snap.stage_state
            row["stages"] = snap.stages
            row["stage_index"] = snap.stage_index
            row["pipeline_kind"] = snap.pipeline_kind
        else:
            # No snapshot yet — derive kind from file registry for cold-start
            fentry = (registry.get(fid) or {}) if fid else {}
            kind = fentry.get("active_kind", "profile")
            row["progress_pct"] = None
            row["stage_label"] = None
            row["stage_state"] = "idle" if row.get("status") == "queued" else None
            stages = PIPELINE_STAGES.get(kind, [])
            # output_lang: slice the canonical 2-stage list to the real language
            # count so a queued single-language job shows ONE step on cold-start
            # (mirrors ProgressAdapter.report once the first event arrives).
            if kind == "output_lang":
                _n = len(fentry.get("output_languages") or [])
                if _n:
                    stages = stages[:max(1, _n)]
            row["stages"] = stages
            row["stage_index"] = 0
            row["pipeline_kind"] = kind

    return jsonify(rows), 200


def _get_job_queue():
    """Resolve the live JobQueue instance from the running Flask app.

    `from app import _job_queue` re-imports app.py as the 'app' module, which
    creates a SECOND, separate JobQueue whose workers are NOT running. Reading
    from current_app.config keeps us on the __main__ module's instance.
    """
    q = current_app.config.get("JOB_QUEUE")
    if q is None:
        # Fall back to the legacy import path so older callers + tests that
        # set up the queue via direct attribute assignment still work.
        from app import _job_queue as q
    return q


def _broadcast_queue_changed():
    """Tell every SocketIO client to refresh /api/queue immediately."""
    sio = current_app.config.get("SOCKETIO")
    if sio is None:
        return
    try:
        sio.emit("queue_changed", {})
    except Exception:
        pass


@bp.delete("/api/queue/<job_id>")
@login_required
def cancel_job(job_id):
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    job = get_job(db_path, job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    if job["user_id"] != current_user.id and not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403

    if job["status"] == "queued":
        # R6 audit R2 — atomic UPDATE-WHERE-status='queued' closes the
        # cancel-worker race: if the worker picked up the jid between our
        # get_job() snapshot and the UPDATE, rowcount=0 and we fall through
        # to the running-cancel path so the worker actually gets the cancel
        # event. Without this, the naive UPDATE could clobber the worker's
        # status='running' transition and the job would run to completion
        # despite returning 200 to the caller.
        if cancel_if_queued(db_path, job_id):
            _broadcast_queue_changed()
            return jsonify({"ok": True}), 200
        # Fall through — the worker has just transitioned to running.
        job = {**job, "status": "running"}

    if job["status"] == "running":
        # R5 Phase 4: cooperative interrupt — set the cancel event,
        # worker will catch JobCancelled at next checkpoint and update status.
        q = _get_job_queue()
        found = q.cancel_job(job_id)
        if not found:
            # Race: job finished between our get_job check and the cancel.
            # Return 200 — the caller's request is effectively a no-op.
            return jsonify({"ok": True, "status": "completed"}), 200
        # Worker emits queue_changed on its own when it transitions to
        # 'cancelled', but emit now too so the UI flips to "cancelling"
        # without waiting for the next worker checkpoint.
        _broadcast_queue_changed()
        return jsonify({"ok": True, "status": "cancelling"}), 202

    # Other statuses (done, failed, cancelled): nothing to cancel
    return jsonify({"error": f"cannot cancel job with status '{job['status']}'"}), 409


@bp.post("/api/queue/<job_id>/retry")
@login_required
def retry_job(job_id):
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    job = get_job(db_path, job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    if job["user_id"] != current_user.id and not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    if job["status"] != "failed":
        return jsonify({"error": "can only retry failed jobs"}), 409
    # R6 audit S6 + Bug #19 — the cap check and insert must be ONE atomic
    # transaction. The old split (read attempt_count → compare → enqueue)
    # let two concurrent retries both observe count < cap and both insert,
    # bypassing the poison-pill protection from Phase 5 T1.5.
    # insert_retry_job() wraps both steps inside BEGIN IMMEDIATE (same
    # pattern as auth/admin.py _atomic_set_admin / _atomic_delete_user).
    import os as _os
    max_retry = int(_os.environ.get("R5_MAX_JOB_RETRY", "3"))
    new_job_id = insert_retry_job(
        db_path,
        user_id=job["user_id"],
        file_id=job["file_id"],
        job_type=job["type"],
        parent_job_id=job["id"],
        max_retry=max_retry,
    )
    if new_job_id is None:
        return jsonify({
            "error": f"retry cap reached ({max_retry}). Investigate the failure before re-running.",
        }), 409
    return jsonify({"ok": True, "new_job_id": new_job_id}), 200
