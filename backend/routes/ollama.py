"""Ollama signin + status routes.

v4 A6 C2 T13a — extracted from ``app.py``.

Both endpoints are restricted to localhost via :func:`_require_localhost`
because they may spawn the interactive ``ollama signin`` flow (which would
be useless from another host anyway, since the OAuth callback opens in the
server's browser).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from auth.decorators import login_required

bp = Blueprint("ollama", __name__)


_LOCALHOST_ADDRS = frozenset({"127.0.0.1", "::1", None})


def _require_localhost():
    """Return ``(None, None)`` if the request is from localhost, else a 403.

    Guards subprocess-spawning + signin-sensitive endpoints against LAN
    exposure even if FLASK_HOST is set to ``0.0.0.0``. ``remote_addr`` is
    ``None`` when Flask is running under a test client.
    """
    if request.remote_addr not in _LOCALHOST_ADDRS:
        return (
            jsonify({"error": "restricted to localhost"}),
            403,
        )
    return None


@bp.post("/api/ollama/signin")
@login_required
def api_ollama_signin():
    """Check signin status; spawn interactive flow if not already signed in.

    First invalidates the cache and checks signin status via
    ``ollama signin`` with a 2-second timeout (see
    ``_get_ollama_signin_status``).  If already signed in, returns the
    user name immediately without spawning a new process. If not signed
    in, spawns the interactive OAuth flow non-blocking so the user can
    complete it in their browser.
    """
    forbidden = _require_localhost()
    if forbidden:
        return forbidden

    import subprocess as sp
    from translation.ollama_engine import _get_ollama_signin_status, _SIGNIN_STATUS_CACHE

    # Invalidate cache so we get a fresh check
    _SIGNIN_STATUS_CACHE["expires_at"] = 0
    status = _get_ollama_signin_status()

    if status["signed_in"]:
        return jsonify({
            "status": "already_signed_in",
            "signed_in": True,
            "user": status["user"],
            "message": f"Already signed in as '{status['user']}'",
        }), 200

    # Not signed in — spawn interactive OAuth flow
    try:
        sp.Popen(
            ["ollama", "signin"],
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
            start_new_session=True,
        )
        return jsonify({
            "status": "signin_spawned",
            "signed_in": False,
            "message": "Ollama signin launched. Complete login in browser.",
        }), 200
    except FileNotFoundError:
        return jsonify({"error": "ollama binary not found in PATH. Install Ollama first."}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to spawn ollama signin: {str(e)}"}), 500


@bp.get("/api/ollama/status")
@login_required
def api_ollama_status():
    """Return cached Ollama Cloud signin status.

    Uses the 60-second cached result from ``_get_ollama_signin_status`` to
    avoid repeated subprocess overhead on repeated calls.
    """
    forbidden = _require_localhost()
    if forbidden:
        return forbidden

    from translation.ollama_engine import _get_ollama_signin_status
    status = _get_ollama_signin_status()
    return jsonify({
        "signed_in": status["signed_in"],
        "user": status.get("user"),
    }), 200
