"""App factory — orchestrates extension init + manager init + blueprint registration.

T5 (v4 A6 C2) lifted this out of ``app.py``. Routes remain in ``app.py`` during T5
and migrate to ``backend/routes/<group>.py`` in T6+.

Contract:
    ``create_app() -> (Flask, SocketIO)``

Behavior intent: byte-perfect reproduction of the inline boot block in the
pre-T5 ``app.py`` (config, CORS, SocketIO, auth init, admin bootstrap, job
queue with pipeline handler, manager construction, blueprint registration,
SPA error handler). The boot order matches the original line-by-line.

After ``create_app()`` returns, the singletons live on three modules:
    - ``extensions.socketio`` / ``extensions.login_manager`` / ``extensions.limiter``
    - ``managers._asr_profile_manager`` / ``_mt_profile_manager`` / ``_pipeline_manager``
      / ``_glossary_manager`` / ``_language_config_manager`` / ``_file_registry``
      / ``_registry_lock`` / ``_job_queue``
    - ``app.app`` (Flask) — kept stable so ``from app import app`` keeps working.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask
from flask_cors import CORS

import extensions
import managers


_PLACEHOLDER_SECRET = "change-me-on-first-deploy"


def create_app() -> tuple[Flask, "extensions.SocketIO"]:
    """Construct Flask app + SocketIO; init all extensions/managers/blueprints.

    Returns ``(app, socketio)`` for the caller (``app.py``) to use as the
    module-level singletons. Routes still register in ``app.py`` (T6-T11
    will migrate them to ``routes/*.py`` blueprints).
    """
    # --- Flask app + secret + cookie config (mirror app.py lines ~88-114) ---
    # ``import_name="app"`` keeps Flask's static folder lookup + logger names
    # identical to the pre-T5 boot (which did ``Flask(__name__)`` inside
    # app.py, giving import_name == "app").
    app = Flask("app")

    # --- v4.0 A6 C4: structured logging FIRST so subsequent boot lines log via JSON ---
    import logging_setup
    logging_setup.configure_logging(app)

    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key or secret_key == _PLACEHOLDER_SECRET:
        raise RuntimeError(
            "R5 Phase 5 T1.3: FLASK_SECRET_KEY env var is REQUIRED. "
            "Run ./setup-mac.sh / setup-win.ps1 / setup-linux-gb10.sh to generate one, "
            "or export FLASK_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))'). "
            f"Placeholder '{_PLACEHOLDER_SECRET}' is rejected for safety."
        )
    app.config["SECRET_KEY"] = secret_key
    # R5 Phase 5 T2.4 — CSRF/cookie hardening
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("R5_HTTPS") != "0"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024  # 5 GB

    # --- CORS — LAN-only allowlist (regex form for flask-cors 6.x) ---
    CORS(app, supports_credentials=True, origins=extensions._LAN_ORIGIN_REGEX)

    # --- v4.0 A6 C4: request_id middleware — installed before any blueprint
    # so every request gets a request_id available in `g` from before_request. ---
    import middleware
    middleware.install_request_id_middleware(app)

    # --- Extensions: SocketIO, LoginManager, Limiter ---
    socketio = extensions.init_extensions(app)

    # --- Socket.IO event handlers (v4 A6 C2 T12) ---
    # Attached AFTER init_extensions so ``extensions.socketio`` is real.
    import socket_events
    socket_events.register_socket_events()

    # --- Auth DB init + Flask-Login user_loader + auth blueprints ---
    from auth.users import init_db as _auth_init_db, get_user_by_id as _auth_get_user_by_id
    from auth.routes import bp as auth_bp, _LoginUser

    auth_db_path = os.environ.get("AUTH_DB_PATH", str(managers.DATA_DIR / "app.db"))
    app.config["AUTH_DB_PATH"] = auth_db_path
    _auth_init_db(auth_db_path)

    if extensions.login_manager is not None:
        @extensions.login_manager.user_loader
        def _load_user(uid: str):
            u = _auth_get_user_by_id(auth_db_path, int(uid))
            return _LoginUser(u) if u else None

    app.register_blueprint(auth_bp)

    # Admin blueprint + audit log init (mirrors app.py lines ~250-253)
    from auth.admin import bp as admin_bp
    from auth.audit import init_audit_log
    init_audit_log(auth_db_path)
    app.register_blueprint(admin_bp)

    # --- Optional admin bootstrap from env ---
    _bootstrap_admin_if_needed(app, auth_db_path)

    # --- Managers (ASR/MT/Pipeline/Glossary/Language) ---
    managers.init_managers()

    # Bind decorators to the fresh manager instances so ownership checks work.
    from auth.decorators import set_v4_managers
    set_v4_managers(
        managers._asr_profile_manager,
        managers._mt_profile_manager,
        managers._pipeline_manager,
    )

    # --- File registry binding (in-memory dict — disk load happens in __main__) ---
    app.config["FILE_REGISTRY"] = managers._file_registry

    # --- Job queue (must be after auth DB init + managers ready) ---
    # NOTE: workers are NOT started here. ``app.py`` defines a module-level
    # ``_pipeline_run_handler`` (so tests can ``patch("app.PipelineRunner")``)
    # and then swaps it onto the queue + calls ``start_workers()``. The
    # default closure inside ``managers.init_job_queue`` is the fallback
    # for any caller that doesn't override.
    job_queue = managers.init_job_queue(app)
    app.config["JOB_QUEUE"] = job_queue
    app.config["SOCKETIO"] = socketio

    from jobqueue.routes import bp as queue_bp
    app.register_blueprint(queue_bp)

    # --- Route blueprints (v4 A6 C2 T6+) ---
    # Health, SPA serving, and fonts endpoints moved out of app.py.
    # T7-T11 will add additional blueprints under backend/routes/.
    from routes import register_blueprints
    register_blueprints(app)

    # --- v4.0 A6 C4: ApiError + 404 + 500 handlers — registered LAST so they
    # take precedence over any blueprint-local handlers. Preserves the prior
    # /api/* + /socket.io/* JSON-404 contract that the inline _not_found used.
    import errors
    errors.register_error_handlers(app)

    return app, socketio


def _bootstrap_admin_if_needed(app: Flask, auth_db_path: str) -> None:
    """Create admin user from ``ADMIN_BOOTSTRAP_PASSWORD`` env if missing.

    Mirrors ``app.py::_bootstrap_admin_if_needed`` line-for-line.
    """
    from auth.users import get_user_by_username, create_user as _auth_create_user

    if get_user_by_username(auth_db_path, "admin") is None:
        admin_pw = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        if admin_pw:
            _auth_create_user(auth_db_path, "admin", admin_pw, is_admin=True)
            app.logger.info(
                "Bootstrapped admin user from ADMIN_BOOTSTRAP_PASSWORD env"
            )


__all__ = ["create_app"]
