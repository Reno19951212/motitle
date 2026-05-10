# backend/auth/admin.py
"""Admin-only user management routes (R5 Phase 3)."""
from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user

from auth.decorators import admin_required
from auth.users import (
    create_user, delete_user, set_admin, update_password,
    list_all_users, count_admins, get_user_by_id,
)
from auth.audit import log_audit


bp = Blueprint("admin", __name__)


@bp.get("/api/admin/users")
@admin_required
def list_users():
    db = current_app.config["AUTH_DB_PATH"]
    return jsonify(list_all_users(db)), 200


@bp.post("/api/admin/users")
@admin_required
def create_user_route():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    is_admin = bool(data.get("is_admin", False))
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    db = current_app.config["AUTH_DB_PATH"]
    try:
        new_id = create_user(db, username, password, is_admin=is_admin)
    except ValueError as e:
        # Username collision — message contains "exists" per Phase 1 B5 spec
        return jsonify({"error": str(e)}), 409
    log_audit(db, actor_id=current_user.id, action="user.create",
              target_kind="user", target_id=str(new_id),
              details={"username": username, "is_admin": is_admin})
    return jsonify({"id": new_id, "username": username, "is_admin": is_admin}), 201


@bp.delete("/api/admin/users/<int:user_id>")
@admin_required
def delete_user_route(user_id):
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    if target["id"] == current_user.id:
        return jsonify({"error": "cannot delete yourself"}), 403
    if target["is_admin"] and count_admins(db) <= 1:
        return jsonify({"error": "cannot delete the last admin"}), 403
    delete_user(db, target["username"])
    log_audit(db, actor_id=current_user.id, action="user.delete",
              target_kind="user", target_id=str(user_id),
              details={"username": target["username"]})
    return jsonify({"ok": True}), 200


@bp.post("/api/admin/users/<int:user_id>/reset-password")
@admin_required
def reset_password_route(user_id):
    data = request.get_json(silent=True) or {}
    new_pw = data.get("new_password") or ""
    if not new_pw:
        return jsonify({"error": "new_password required"}), 400
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    update_password(db, target["username"], new_pw)
    log_audit(db, actor_id=current_user.id, action="user.reset_password",
              target_kind="user", target_id=str(user_id))
    return jsonify({"ok": True}), 200


@bp.post("/api/admin/users/<int:user_id>/toggle-admin")
@admin_required
def toggle_admin_route(user_id):
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    new_state = not target["is_admin"]
    # Guard: demoting the last admin (whether self or not)
    if not new_state and target["is_admin"] and count_admins(db) <= 1:
        return jsonify({"error": "cannot demote the last admin"}), 403
    set_admin(db, target["username"], new_state)
    log_audit(db, actor_id=current_user.id, action="user.toggle_admin",
              target_kind="user", target_id=str(user_id),
              details={"new_state": new_state})
    return jsonify({"is_admin": new_state}), 200


@bp.get("/api/admin/audit")
@admin_required
def list_audit_route():
    from auth.audit import list_audit
    db = current_app.config["AUTH_DB_PATH"]
    limit = min(int(request.args.get("limit", 100)), 500)
    actor_id = request.args.get("actor_id")
    actor_id = int(actor_id) if actor_id else None
    return jsonify(list_audit(db, limit=limit, actor_id=actor_id)), 200
