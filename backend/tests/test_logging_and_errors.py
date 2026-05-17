"""Smoke tests for v4.0 A6 C4: structured logging + errors + request_id."""
from __future__ import annotations
import pytest
from flask import Flask
from errors import ApiError, register_error_handlers
from middleware import install_request_id_middleware


@pytest.fixture
def smoke_app():
    """Tiny Flask app with just C4 wiring — no managers, no auth."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    install_request_id_middleware(app)
    register_error_handlers(app)

    @app.get("/echo")
    def echo():
        from flask import g, jsonify
        return jsonify({"request_id": g.request_id})

    @app.get("/raise-api-error")
    def raise_api():
        raise ApiError("bad input", status=400, details={"field": "foo"})

    return app


def test_request_id_header_set(smoke_app):
    client = smoke_app.test_client()
    r = client.get("/echo")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    body = r.get_json()
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_request_id_passthrough_from_inbound_header(smoke_app):
    client = smoke_app.test_client()
    r = client.get("/echo", headers={"X-Request-ID": "trace-abc"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["request_id"] == "trace-abc"
    assert r.headers["X-Request-ID"] == "trace-abc"


def test_api_error_handler(smoke_app):
    client = smoke_app.test_client()
    r = client.get("/raise-api-error")
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "bad input"
    assert body["details"] == {"field": "foo"}


def test_api_404_returns_json(smoke_app):
    client = smoke_app.test_client()
    r = client.get("/api/nonexistent")
    assert r.status_code == 404
    body = r.get_json()
    assert body == {"error": "not found"}
