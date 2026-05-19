"""VerifierProfile REST blueprint — v5-A1.

Endpoints (all login_required):

  GET    /api/verifier_profiles               List visible (owner OR admin OR shared)
  POST   /api/verifier_profiles               Create (current user is owner)
  GET    /api/verifier_profiles/<pid>         View single (admin OR owner OR shared)
  PATCH  /api/verifier_profiles/<pid>         Update (admin OR owner only)
  DELETE /api/verifier_profiles/<pid>         Delete (admin OR owner only)

Errors:

  400 invalid payload (validation errors — missing lang/llm_profile_id/etc.)
  403 forbidden (lookup ok but viewer not authorized OR target missing for non-admin)
  404 not found (only when viewer is admin; non-admin can't disambiguate vs forbidden)

NEW v5 entity (no legacy v4 counterpart). LLM-as-judge config for ASR
cross-validation between primary and secondary transcription outputs.
Each VerifierProfile is language-specific (must match the source audio
language).
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import app as _app
from verifier_profiles import validate_verifier_profile

bp = Blueprint("verifier_profiles", __name__)


def _is_admin() -> bool:
    return bool(getattr(current_user, "is_admin", False))


@bp.get("/api/verifier_profiles")
@login_required
def list_profiles():
    mgr = _app._verifier_profile_manager
    profiles = mgr.list_visible(user_id=current_user.id, is_admin=_is_admin())
    return jsonify({"profiles": profiles}), 200


@bp.post("/api/verifier_profiles")
@login_required
def create_profile():
    data = request.get_json(silent=True) or {}
    errors = validate_verifier_profile(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    mgr = _app._verifier_profile_manager
    try:
        pid = mgr.create(data, user_id=current_user.id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(mgr.get(pid)), 201


@bp.get("/api/verifier_profiles/<pid>")
@login_required
def get_profile(pid):
    mgr = _app._verifier_profile_manager
    if not mgr.can_view(pid, current_user.id, _is_admin()):
        # Admin gets explicit 404 if absent; non-admin always sees 403 (no info leak)
        if _is_admin() and mgr.get(pid) is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"error": "forbidden"}), 403
    return jsonify(mgr.get(pid)), 200


@bp.patch("/api/verifier_profiles/<pid>")
@login_required
def update_profile(pid):
    patch = request.get_json(silent=True) or {}
    mgr = _app._verifier_profile_manager
    try:
        result = mgr.update_if_owned(pid, current_user.id, _is_admin(), patch)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(result), 200


@bp.delete("/api/verifier_profiles/<pid>")
@login_required
def delete_profile(pid):
    mgr = _app._verifier_profile_manager
    ok = mgr.delete_if_owned(pid, current_user.id, _is_admin())
    if not ok:
        return jsonify({"error": "forbidden or missing"}), 403
    return jsonify({"deleted": pid}), 200
