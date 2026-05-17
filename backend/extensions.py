"""Singleton holders for Flask extensions.

Constructed by ``init_extensions(app)``. Imported by ``backend/bootstrap.py``
(T5 onward) so route blueprints in T6+ can reference ``extensions.socketio``
etc. instead of reaching back into ``app.py``.

Behavior intent: byte-perfect reproduction of the in-line extension wiring
that currently lives in ``backend/app.py`` (lines ~143-253). Nothing in T4
imports this module yet — pure scaffolding.
"""
from __future__ import annotations

import ipaddress
import os
from typing import Optional
from urllib.parse import urlparse

from flask import Flask
from flask_login import LoginManager
from flask_socketio import SocketIO


# ---------------------------------------------------------------------------
# Module-level singletons. Populated by ``init_extensions(app)``.
# ---------------------------------------------------------------------------
socketio: Optional[SocketIO] = None
login_manager: Optional[LoginManager] = None
# ``limiter`` is owned by ``auth.limiter`` — we re-export the same instance
# here for convenience (T6 route blueprints can do
# ``from extensions import limiter``). It is the same object as
# ``auth.limiter.limiter``; ``init_extensions`` will run ``init_app(app)``.
limiter = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# LAN-only allowlist — must stay in sync with the values in ``app.py``.
# Both forms are kept: a callable (used by Flask-SocketIO / engineio which
# treat strings as literal allow-origin) and a regex string (used by
# flask-cors 6.x which only accepts string/list/regex, not callables).
# ---------------------------------------------------------------------------
_LAN_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def _is_lan_origin(origin: str) -> bool:
    """R5 Phase 1 — allow CORS for LAN origins only.

    True if the origin's hostname is ``localhost`` or resolves to an IP in a
    private LAN range (RFC 1918 + loopback). Public IPs and unresolvable
    hostnames return False. Copy of the helper in ``app.py``; both copies
    must stay in lockstep until ``app.py`` is fully migrated and its copy
    deleted (planned in C2 T9+).
    """
    try:
        host = urlparse(origin).hostname
        if not host:
            return False
        if host == "localhost":
            return True
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _LAN_NETS)
    except (ValueError, TypeError):
        return False


_LAN_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost"
    r"|127\.\d+\.\d+\.\d+"
    r"|10\.\d+\.\d+\.\d+"
    r"|192\.168\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+"
    r")(:\d+)?$"
)


# ---------------------------------------------------------------------------
# init_extensions
# ---------------------------------------------------------------------------
def init_extensions(app: Flask) -> SocketIO:
    """Wire SocketIO, LoginManager, and Flask-Limiter onto ``app``.

    Mirrors the inline setup in ``backend/app.py`` so that callers (T5
    bootstrap) get identical behavior. Sets the module-level singletons
    ``socketio``, ``login_manager``, ``limiter`` and returns ``socketio``
    for convenience (the caller uses it for ``socketio.run(app, ...)``).

    Notes on parity with app.py:
    - SocketIO uses ``cors_allowed_origins=_is_lan_origin`` (callable, not
      regex string) because engineio treats str as a literal allow-origin.
    - SocketIO ``async_mode='threading'`` (NOT eventlet — app.py uses
      threading and switching would change worker semantics).
    - ``max_http_buffer_size=100 * 1024 * 1024`` (100 MB) to accept large
      audio uploads via SocketIO event streams.
    - LoginManager is constructed bare, then ``init_app(app)``; the
      unauthorized handler returns ``({'error': 'unauthorized'}, 401)``.
      The ``user_loader`` is NOT wired here — it depends on ``AUTH_DB_PATH``
      which is owned by bootstrap. T5 attaches the loader after calling
      ``init_extensions``.
    - ``limiter`` is the shared singleton from ``auth.limiter``;
      ``init_app(app)`` mirrors the call in app.py line ~239.
    """
    global socketio, login_manager, limiter

    socketio = SocketIO(
        app,
        cors_allowed_origins=_is_lan_origin,
        async_mode="threading",
        max_http_buffer_size=100 * 1024 * 1024,
    )

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.unauthorized_handler(lambda: ({"error": "unauthorized"}, 401))

    # Re-export and initialize the shared limiter singleton. ``auth.limiter``
    # owns the Limiter() construction; we only call init_app() here so that
    # rate-limit decorators on routes start enforcing once the app is bound.
    from auth.limiter import limiter as _shared_limiter
    _shared_limiter.init_app(app)
    limiter = _shared_limiter

    return socketio


__all__ = [
    "socketio",
    "login_manager",
    "limiter",
    "init_extensions",
    "_is_lan_origin",
    "_LAN_ORIGIN_REGEX",
    "_LAN_NETS",
]
