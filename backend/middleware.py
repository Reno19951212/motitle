"""Request middlewares for v4.0 A6 C4."""
from __future__ import annotations
import uuid
from flask import Flask, g, request


def install_request_id_middleware(app: Flask) -> None:
    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

    @app.after_request
    def _expose_request_id(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response
