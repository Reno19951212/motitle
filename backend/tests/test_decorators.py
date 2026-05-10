"""Tests for @login_required (re-export) + @require_file_owner + @admin_required.

The decorators wrap their inner function with flask_login.login_required, which
requires a Flask request context to access request.method. We provide an app
context with LOGIN_DISABLED=True so flask_login short-circuits and our own
ownership/admin logic gets exercised.
"""
import pytest


@pytest.fixture
def app_ctx():
    """Yield a Flask request context with LOGIN_DISABLED so flask_login.login_required passes through."""
    from flask import Flask
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    with app.test_request_context("/"):
        yield app


def test_require_file_owner_allows_owner(monkeypatch, app_ctx):
    """Owner of file_id matches current_user.id → handler runs."""
    from auth.decorators import require_file_owner

    captured = {}

    @require_file_owner
    def handler(file_id):
        captured["ran"] = True
        return ("ok", 200)

    class _CU:
        is_authenticated = True
        id = 42
        is_admin = False

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    monkeypatch.setattr("auth.decorators._lookup_file_owner",
                        lambda fid: 42)

    rv = handler("abc123")
    assert rv == ("ok", 200)
    assert captured["ran"] is True


def test_require_file_owner_blocks_non_owner(monkeypatch, app_ctx):
    from auth.decorators import require_file_owner

    @require_file_owner
    def handler(file_id):
        return ("never", 200)

    class _CU:
        is_authenticated = True
        id = 42
        is_admin = False

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    monkeypatch.setattr("auth.decorators._lookup_file_owner",
                        lambda fid: 99)

    rv, code = handler("foreign-file")
    assert code == 403


def test_require_file_owner_admin_bypass(monkeypatch, app_ctx):
    """Admin can access any file."""
    from auth.decorators import require_file_owner

    @require_file_owner
    def handler(file_id):
        return ("admin-ok", 200)

    class _CU:
        is_authenticated = True
        id = 1
        is_admin = True

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    monkeypatch.setattr("auth.decorators._lookup_file_owner",
                        lambda fid: 99)

    rv, code = handler("foreign")
    assert code == 200


def test_admin_required_blocks_non_admin(monkeypatch, app_ctx):
    from auth.decorators import admin_required

    @admin_required
    def handler():
        return ("never", 200)

    class _CU:
        is_authenticated = True
        id = 5
        is_admin = False

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    rv, code = handler()
    assert code == 403


def test_admin_required_allows_admin(monkeypatch, app_ctx):
    from auth.decorators import admin_required

    @admin_required
    def handler():
        return ("ok", 200)

    class _CU:
        is_authenticated = True
        id = 1
        is_admin = True

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    assert handler() == ("ok", 200)


def test_r5_auth_bypass_short_circuits_require_file_owner():
    """R5_AUTH_BYPASS=True in app.config skips ownership check entirely (test mode)."""
    from auth.decorators import require_file_owner
    from flask import Flask
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["R5_AUTH_BYPASS"] = True

    @require_file_owner
    def handler(file_id):
        return ("bypassed", 200)

    with app.test_request_context("/"):
        assert handler("any-file-id") == ("bypassed", 200)


def test_r5_auth_bypass_short_circuits_admin_required():
    """R5_AUTH_BYPASS=True in app.config skips admin check entirely (test mode)."""
    from auth.decorators import admin_required
    from flask import Flask
    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["R5_AUTH_BYPASS"] = True

    @admin_required
    def handler():
        return ("bypassed", 200)

    with app.test_request_context("/"):
        assert handler() == ("bypassed", 200)
