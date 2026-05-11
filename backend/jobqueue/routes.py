"""REST routes: GET /api/queue, DELETE /api/queue/<id>."""
from flask import Blueprint, jsonify, current_app
from flask_login import login_required, current_user

from jobqueue.db import list_jobs_for_user, list_active_jobs, get_job, update_job_status
from auth.users import get_user_by_id
from auth.limiter import limiter

bp = Blueprint("queue", __name__)
_db_path = None


def set_db_path(p: str) -> None:
    global _db_path
    _db_path = p


def _annotate(jobs: list, db_path: str) -> list:
    """Add owner_username + position + eta_seconds (None for now)."""
    user_cache = {}
    out = []
    for i, j in enumerate(jobs):
        uid = j["user_id"]
        if uid not in user_cache:
            u = get_user_by_id(db_path, uid)
            user_cache[uid] = u["username"] if u else "?"
        out.append({**j,
                    "owner_username": user_cache[uid],
                    "position": i,
                    "eta_seconds": None})
    return out


@bp.get("/api/queue")
@login_required
@limiter.limit("60 per minute")
def list_queue():
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    if current_user.is_admin:
        jobs = list_active_jobs(db_path)
    else:
        all_user_jobs = list_jobs_for_user(db_path, current_user.id)
        jobs = [j for j in all_user_jobs if j["status"] in ("queued", "running")]
    return jsonify(_annotate(jobs, db_path)), 200


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
        # Synchronous DB cancel (Phase 1 C6 behavior preserved)
        update_job_status(db_path, job_id, "cancelled")
        return jsonify({"ok": True}), 200

    if job["status"] == "running":
        # R5 Phase 4: cooperative interrupt — set the cancel event,
        # worker will catch JobCancelled at next checkpoint and update status.
        from app import _job_queue
        found = _job_queue.cancel_job(job_id)
        if not found:
            # Race: job finished between our get_job check and the cancel.
            # Return 200 — the caller's request is effectively a no-op.
            return jsonify({"ok": True, "status": "completed"}), 200
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
    # Need access to _job_queue from app to call enqueue. Lazy-import to avoid
    # boot-time circular dependency.
    from app import _job_queue
    new_job_id = _job_queue.enqueue(
        user_id=job["user_id"],
        file_id=job["file_id"],
        job_type=job["type"],
    )
    return jsonify({"ok": True, "new_job_id": new_job_id}), 200
