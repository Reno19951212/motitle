"""Phase 5 T2.4 — session cookie has SameSite=Lax (CSRF mitigation)."""
import pytest


def test_session_cookie_samesite_lax():
    import app as app_module
    assert app_module.app.config.get("SESSION_COOKIE_SAMESITE") == "Lax", \
        "T2.4 — SESSION_COOKIE_SAMESITE must be 'Lax'"


def test_session_cookie_httponly():
    """Defense-in-depth: HttpOnly should always be set (Flask default but make explicit)."""
    import app as app_module
    assert app_module.app.config.get("SESSION_COOKIE_HTTPONLY") is True


def test_session_cookie_secure_is_bool():
    """Whatever R5_HTTPS resolves to, SESSION_COOKIE_SECURE must be a bool
    (avoids falsy-but-truthy edge cases)."""
    import app as app_module
    val = app_module.app.config.get("SESSION_COOKIE_SECURE")
    assert isinstance(val, bool), f"T2.4 — SESSION_COOKIE_SECURE must be bool, got {type(val).__name__}"
