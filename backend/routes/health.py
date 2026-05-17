"""Health + readiness probes.

- ``/api/health`` — liveness check, returns server status + loaded model caches.
- ``/api/ready`` — readiness probe (DB reachable + queue workers alive).

Both endpoints are public (no auth) so that monitoring agents / load balancers
can poll them without a session cookie.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health_check():
    """Health check endpoint."""
    # Imported lazily so this blueprint stays decoupled from app.py module-load
    # ordering; ``app`` re-exports the cache dicts as module-level singletons.
    import app as _app

    return jsonify({
        'status': 'ok',
        'faster_whisper_available': _app.FASTER_WHISPER_AVAILABLE,
        'openai_models_loaded': list(_app._openai_model_cache.keys()),
        'faster_models_loaded': list(_app._faster_model_cache.keys()),
        'upload_dir': str(_app.UPLOAD_DIR),
    })


@bp.get("/api/ready")
def ready_check():
    """Readiness probe (liveness = /api/health, readiness = this).

    Returns 200 when the server can accept work: auth DB reachable and all
    job-queue worker threads alive. Returns 503 otherwise so that systemd
    or a load-balancer can hold traffic until the process is ready.
    No auth required — monitoring agents call this without a session.
    """
    auth_db_path = current_app.config["AUTH_DB_PATH"]
    job_queue = current_app.config["JOB_QUEUE"]
    try:
        from auth.users import get_connection as _get_auth_conn
        conn = _get_auth_conn(auth_db_path)
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception:
        return jsonify({"ready": False, "error": "db unavailable"}), 503
    if not all(t.is_alive() for t in job_queue._workers):
        return jsonify({"ready": False, "error": "job workers not running"}), 503
    return jsonify({"ready": True}), 200
