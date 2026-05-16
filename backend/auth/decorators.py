"""Auth decorators on top of Flask-Login.

Re-exports @login_required for convenience. Adds @require_file_owner and
@admin_required. File ownership is looked up against the file registry.
"""
from functools import wraps
from typing import Optional

from flask import jsonify, current_app
from flask_login import current_user, login_required

# Re-export so callers do `from auth.decorators import login_required`
__all__ = ["login_required", "require_file_owner", "admin_required"]


def _auth_bypassed() -> bool:
    """True when the test harness wants ALL ownership/admin checks skipped.

    Distinct from flask_login's LOGIN_DISABLED — that one only bypasses
    @login_required, leaving our wrapper to call current_user.is_admin
    against AnonymousUserMixin (AttributeError). R5_AUTH_BYPASS short-circuits
    our wrapper entirely. Set in tests via conftest; never set in production.
    """
    try:
        return bool(current_app.config.get("R5_AUTH_BYPASS"))
    except RuntimeError:
        return False  # outside app context — production handler is decorating


def _lookup_file_owner(file_id: str) -> Optional[int]:
    """Return user_id who owns this file_id, or None if not found.

    Reads from current_app.config['FILE_REGISTRY']. The registry is attached
    to the Flask app object in app.py, so we get the running process's
    registry regardless of whether app.py is loaded as __main__ or 'app'.
    """
    reg = current_app.config.get("FILE_REGISTRY", {})
    f = reg.get(file_id)
    return f.get("user_id") if f else None


def require_file_owner(fn):
    """Block access unless current_user owns file_id (or is admin).

    The decorated handler MUST receive `file_id` as a kwarg or positional
    arg with name `file_id`.
    """
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if _auth_bypassed():
            return fn(*args, **kwargs)
        file_id = kwargs.get("file_id")
        if file_id is None and args:
            file_id = args[0]
        if file_id is None:
            return jsonify({"error": "file_id required"}), 400
        owner_id = _lookup_file_owner(file_id)
        if owner_id is None:
            return jsonify({"error": "file not found"}), 404
        if current_user.is_admin or current_user.id == owner_id:
            return fn(*args, **kwargs)
        return jsonify({"error": "forbidden"}), 403
    return wrapper


def admin_required(fn):
    """Block access unless current_user.is_admin."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if _auth_bypassed():
            return fn(*args, **kwargs)
        if not current_user.is_admin:
            return jsonify({"error": "admin only"}), 403
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# v4.0 Phase 1 — entity-specific owner decorators
# Mirror require_file_owner pattern. The manager modules are imported
# lazily at call time so this module can stay decoupled from app.py boot.
# ---------------------------------------------------------------------------

_asr_manager = None
_mt_manager = None
_pipeline_manager = None


def set_v4_managers(asr_manager, mt_manager, pipeline_manager):
    """Called from app.py boot after managers are instantiated."""
    global _asr_manager, _mt_manager, _pipeline_manager
    _asr_manager = asr_manager
    _mt_manager = mt_manager
    _pipeline_manager = pipeline_manager


def _make_owner_decorator(manager_attr_name: str, url_arg_name: str):
    """Build a decorator that checks can_view on the given manager."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import abort, jsonify  # noqa: F401 — already imported at top but kept local for clarity

            if _auth_bypassed():
                return fn(*args, **kwargs)

            if not getattr(current_user, "is_authenticated", False):
                return jsonify({"error": "authentication required"}), 401

            resource_id = kwargs.get(url_arg_name)
            mgr = globals().get(manager_attr_name)
            if mgr is None:
                return jsonify({"error": f"{manager_attr_name} not initialised"}), 500

            is_admin = bool(getattr(current_user, "is_admin", False))
            user_id = current_user.id

            if not mgr.can_view(resource_id, user_id, is_admin):
                return jsonify({"error": "not found"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


require_asr_profile_owner = _make_owner_decorator("_asr_manager", "profile_id")
require_mt_profile_owner = _make_owner_decorator("_mt_manager", "profile_id")
require_pipeline_owner = _make_owner_decorator("_pipeline_manager", "pipeline_id")
