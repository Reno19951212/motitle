"""Tests for @require_asr_profile_owner / @require_mt_profile_owner /
@require_pipeline_owner — mirror of @require_file_owner."""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from auth.decorators import (
    require_asr_profile_owner,
    require_mt_profile_owner,
    require_pipeline_owner,
)


@pytest.fixture
def app():
    a = Flask(__name__)
    a.config["LOGIN_DISABLED"] = True
    a.config["R5_AUTH_BYPASS"] = False
    return a


def test_require_asr_profile_owner_403_for_non_owner(app):
    fake_user = MagicMock(id=99, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = False

    @app.route("/test/<profile_id>")
    @require_asr_profile_owner
    def view(profile_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._asr_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 403


def test_require_asr_profile_owner_200_for_owner(app):
    fake_user = MagicMock(id=99, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = True

    @app.route("/test/<profile_id>")
    @require_asr_profile_owner
    def view(profile_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._asr_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 200


def test_require_mt_profile_owner_uses_mt_manager(app):
    fake_user = MagicMock(id=1, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = False

    @app.route("/test/<profile_id>")
    @require_mt_profile_owner
    def view(profile_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._mt_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 403


def test_require_pipeline_owner_uses_pipeline_manager(app):
    fake_user = MagicMock(id=1, is_admin=False, is_authenticated=True)
    fake_mgr = MagicMock()
    fake_mgr.can_view.return_value = False

    @app.route("/test/<pipeline_id>")
    @require_pipeline_owner
    def view(pipeline_id):
        return "ok", 200

    with patch("auth.decorators.current_user", fake_user), \
         patch("auth.decorators._pipeline_manager", fake_mgr, create=True):
        client = app.test_client()
        resp = client.get("/test/some-id")
    assert resp.status_code == 403
