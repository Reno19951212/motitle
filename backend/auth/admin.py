# backend/auth/admin.py
"""Admin-only user management routes (R5 Phase 3)."""
import sqlite3
from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user

from auth.decorators import admin_required
from auth.users import (
    create_user, delete_user, set_admin, update_password,
    list_all_users, count_admins, get_user_by_id,
)
from auth.audit import log_audit


bp = Blueprint("admin", __name__)


# R5 Phase 5 T2.7 — atomic guards.
#
# The check-then-write pattern (count_admins → UPDATE/DELETE) was vulnerable
# to a race where two admins concurrently demote / delete each other and both
# observe count_admins == 2 at check time. BEGIN IMMEDIATE acquires a write
# lock at transaction start so the second demote serializes after the first
# and observes count_admins == 1.

def _atomic_set_admin(db_path: str, user_id: int, new_admin: bool) -> None:
    """Atomic check-and-flip of is_admin.

    Raises ``ValueError`` if the operation would leave zero admins or the
    target user does not exist. Otherwise commits the change.
    """
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        target_row = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target_row is None:
            conn.execute("ROLLBACK")
            raise ValueError(f"user {user_id} not found")
        currently_admin = bool(target_row[0])

        if not new_admin and currently_admin:
            n = conn.execute(
                "SELECT COUNT(*) FROM users WHERE is_admin = 1"
            ).fetchone()[0]
            if n <= 1:
                conn.execute("ROLLBACK")
                raise ValueError("cannot demote the last admin")

        conn.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (1 if new_admin else 0, user_id),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()


def _atomic_delete_user(db_path: str, user_id: int) -> str:
    """Atomic delete with last-admin guard. Returns the deleted username
    on success, or raises ``ValueError`` (user not found / would leave
    zero admins)."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT username, is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            raise ValueError(f"user {user_id} not found")
        username, was_admin = row[0], bool(row[1])

        if was_admin:
            n = conn.execute(
                "SELECT COUNT(*) FROM users WHERE is_admin = 1"
            ).fetchone()[0]
            if n <= 1:
                conn.execute("ROLLBACK")
                raise ValueError("cannot delete the last admin")

        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("COMMIT")
        return username
    finally:
        conn.close()


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
    # R5 Phase 5 T2.7: atomic last-admin guard via BEGIN IMMEDIATE.
    try:
        username = _atomic_delete_user(db, user_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            return jsonify({"error": "not found"}), 404
        return jsonify({"error": msg}), 403
    log_audit(db, actor_id=current_user.id, action="user.delete",
              target_kind="user", target_id=str(user_id),
              details={"username": username})
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
    # R5 Phase 5 T2.7: atomic last-admin guard. Concurrent demote attempts
    # serialize on BEGIN IMMEDIATE so the second one observes count=1 and
    # rolls back instead of leaving zero admins.
    try:
        _atomic_set_admin(db, user_id, new_state)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            return jsonify({"error": "not found"}), 404
        return jsonify({"error": msg}), 403
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
