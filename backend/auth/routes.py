"""Auth blueprint: /login, /logout, /api/me."""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user

from auth.users import verify_credentials, get_user_by_id
from auth.audit import log_audit
from auth.limiter import limiter


bp = Blueprint("auth", __name__)


class _LoginUser:
    """Lightweight Flask-Login UserMixin substitute."""
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.is_admin = user_dict["is_admin"]
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return str(self.id)


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}
    # R5 Phase 5 T1.1: explicit `null` in JSON returns None from .get(),
    # bypassing the default. Coerce with `or` to avoid NoneType.strip().
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    db_path = current_app.config["AUTH_DB_PATH"]
    user = verify_credentials(db_path, username, password)
    if not user:
        log_audit(db_path, actor_id=0, action="login_failed",
                  target_kind="username", target_id=username)
        return jsonify({"error": "invalid credentials"}), 401

    login_user(_LoginUser(user))
    return jsonify({"ok": True, "user": {
        "id": user["id"],
        "username": user["username"],
        "is_admin": user["is_admin"],
    }}), 200


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True}), 200


@bp.get("/api/me")
@login_required
def me():
    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
    }), 200
