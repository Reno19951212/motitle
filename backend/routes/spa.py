"""React SPA serving — root, hashed Vite assets, and React Router fallbacks.

All paths render the same ``frontend/dist/index.html``; React Router handles
client-side routing from there. NONE of these have ``@login_required`` because
``/login`` is itself a SPA route — the React app drives auth state via
``/api/me``.

The frontend dist directory is sourced from ``app._FRONTEND_DIR`` at request
time so tests can ``monkeypatch.setattr("app._FRONTEND_DIR", ...)``.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, send_from_directory

bp = Blueprint("spa", __name__)


def _frontend_dir() -> str:
    """Resolve the frontend dist root at request time (test-friendly)."""
    import app as _app
    return _app._FRONTEND_DIR


def _serve_react_index():
    """Serve the Vite-built React index.html from frontend/dist/.

    Falls back to a friendly placeholder when the dist bundle is not built —
    happens in dev environments before ``npm run build`` was ever run.
    """
    dist_index = Path(_frontend_dir()) / "dist" / "index.html"
    if dist_index.exists():
        return send_from_directory(str(dist_index.parent), "index.html")
    return (
        "<html><body>Frontend dist not built. Run "
        "<code>cd frontend && npm run build</code>.</body></html>",
        200,
    )


@bp.get("/")
def serve_index():
    """Root — serve React SPA. Auth is handled by the React app itself
    (it'll POST /login if needed). No server-side redirect."""
    return _serve_react_index()


@bp.get("/assets/<path:filename>")
def serve_assets(filename):
    """Vite-built hashed bundle assets (JS / CSS / images) from frontend/dist/assets/."""
    assets_dir = Path(_frontend_dir()) / "dist" / "assets"
    return send_from_directory(str(assets_dir), filename)


# --- React SPA routes (v4.0 A3) ----------------------------------------------
# These bare paths all render the same index.html — React Router handles
# client-side routing from there.

@bp.get("/login")
def serve_login_spa():
    return _serve_react_index()


@bp.get("/pipelines")
def serve_pipelines_spa():
    return _serve_react_index()


@bp.get("/asr_profiles")
def serve_asr_profiles_spa():
    return _serve_react_index()


@bp.get("/mt_profiles")
def serve_mt_profiles_spa():
    return _serve_react_index()


@bp.get("/glossaries")
def serve_glossaries_spa():
    return _serve_react_index()


@bp.get("/admin")
def serve_admin_spa():
    return _serve_react_index()


@bp.get("/proofread/<path:_subpath>")
def serve_proofread_spa(_subpath):
    return _serve_react_index()
