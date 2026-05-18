"""Request middlewares for v4.0 A6 C4."""
from __future__ import annotations
import uuid
from flask import Flask, g, request
from logging_setup import set_request_id


def install_request_id_middleware(app: Flask) -> None:
    @app.before_request
    def _assign_request_id():
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_id = rid
        # Also store in ContextVar so werkzeug's access logger (which fires
        # outside the Flask request context) can still read the request_id.
        set_request_id(rid)

    @app.after_request
    def _expose_request_id(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response

    @app.teardown_request
    def _clear_request_id(_exc):
        # Clear the ContextVar after teardown so it doesn't leak into
        # unrelated log calls in the same thread between requests.
        set_request_id(None)
