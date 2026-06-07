"""Global before_request enforcement. The only Flask-aware licensing module.

Allowlisted paths work without a licence (auth + licence mgmt + health + the
licence wall + its static assets). Everything else requires evaluate().unlocked.
"""
from flask import request, jsonify, redirect, current_app

from licensing import validator

# Exact paths reachable without a licence.
ALLOWLIST_EXACT = {
    "/api/health",
    "/login", "/logout", "/api/me",
    "/login.html", "/license.html",
    "/api/license", "/api/license/activate", "/api/license/deactivate",
    "/favicon.ico",
}
# Static asset prefixes needed to render login + the licence wall.
ALLOWLIST_PREFIXES = ("/js/", "/css/")

# Page (HTML) routes that should 302 to the wall instead of returning JSON 403.
PAGE_PREFIXES_NONAPI = True  # any non-/api GET that isn't allowlisted → redirect


def _allowed(path: str) -> bool:
    if path in ALLOWLIST_EXACT:
        return True
    return any(path.startswith(p) for p in ALLOWLIST_PREFIXES)


def enforce():
    """Return None to allow the request, or a Response to short-circuit it."""
    # Test-only escape hatch: the autouse conftest fixture sets this so the
    # ~hundreds of existing API tests (which never install a licence) keep
    # running. The licensing test suites flip it off to exercise the real gate.
    # Mirrors the existing R5_AUTH_BYPASS pattern. Never set in production.
    if current_app.config.get("R5_LICENSE_BYPASS"):
        return None
    path = request.path
    if _allowed(path):
        return None
    st = validator.evaluate()
    if st.unlocked:
        return None
    if path.startswith("/api/"):
        return jsonify({"error": "licence required", "license_state": st.state}), 403
    return redirect("/license.html")


def register(app):
    app.before_request(enforce)
