"""ASR-profile routes — /api/asr_profiles* (v4.0 P1 entity).

v4 A6 C2 T9 — extracted from ``app.py``.

Helpers like ``_asr_profile_manager`` still live on ``app`` — this blueprint
imports them lazily at request time so the existing test surface
(which monkeypatches ``app._asr_profile_manager`` etc.) keeps working.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from auth.decorators import login_required, require_asr_profile_owner

bp = Blueprint("asr_profiles", __name__)


# ============================================================
# GET /api/asr_profiles — list visible ASR profiles
# ============================================================

@bp.get("/api/asr_profiles")
@login_required
def list_asr_profiles():
    import app as _app
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    profiles = _app._asr_profile_manager.list_visible(user_id, is_admin)
    return jsonify({"asr_profiles": profiles}), 200


# ============================================================
# POST /api/asr_profiles — create
# ============================================================

@bp.post("/api/asr_profiles")
@login_required
def create_asr_profile():
    import app as _app
    data = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    try:
        profile = _app._asr_profile_manager.create(data, user_id=user_id)
    except ValueError as exc:
        return jsonify({"errors": str(exc).split("; ")}), 400
    return jsonify(profile), 201


# ============================================================
# GET /api/asr_profiles/<id> — single profile
# ============================================================

@bp.get("/api/asr_profiles/<profile_id>")
@login_required
@require_asr_profile_owner
def get_asr_profile(profile_id):
    import app as _app
    profile = _app._asr_profile_manager.get(profile_id)
    if profile is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(profile), 200


# ============================================================
# PATCH /api/asr_profiles/<id> — update (owner only)
# ============================================================

@bp.patch("/api/asr_profiles/<profile_id>")
@login_required
@require_asr_profile_owner
def patch_asr_profile(profile_id):
    import app as _app
    patch = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    ok, errors = _app._asr_profile_manager.update_if_owned(
        profile_id, user_id, is_admin, patch
    )
    if not ok:
        if "permission denied" in errors:
            return jsonify({"errors": errors}), 403
        return jsonify({"errors": errors}), 400
    return jsonify(_app._asr_profile_manager.get(profile_id)), 200


# ============================================================
# DELETE /api/asr_profiles/<id> — delete (owner only)
# ============================================================

@bp.delete("/api/asr_profiles/<profile_id>")
@login_required
@require_asr_profile_owner
def delete_asr_profile(profile_id):
    import app as _app
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    if not _app._asr_profile_manager.delete_if_owned(profile_id, user_id, is_admin):
        return jsonify({"error": "forbidden"}), 403
    return "", 204


# ============================================================
# v5-A1 deprecation: signal clients to migrate to /api/transcribe_profiles
# ============================================================

@bp.after_request
def add_deprecation_header(response):
    """Mark this v4 endpoint as deprecated in favor of v5 ``/api/transcribe_profiles``.

    Removal scheduled for the v5-A3 cleanup phase.

    Sets the IETF HTTP deprecation headers:
      - ``Deprecation: true`` — clients should warn / migrate
      - ``Link: <successor>; rel="successor-version"`` — points to v5 replacement
      - ``Sunset: <date>`` — planned removal date (RFC 8594)
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/transcribe_profiles>; rel="successor-version"'
    response.headers["Sunset"] = "Wed, 31 Dec 2026 00:00:00 GMT"
    return response
