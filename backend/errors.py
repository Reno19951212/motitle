"""Unified ApiError + Flask error handlers for v4.0 A6 C4."""
from __future__ import annotations
from typing import Any, Optional
from flask import Flask, jsonify, request, g


class ApiError(Exception):
    """Raise from any handler; the registered error handler converts to JSON.

    Example: ``raise ApiError("pipeline_id is required", status=400)``
    """

    def __init__(
        self,
        message: str,
        status: int = 400,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(e: ApiError):
        return jsonify({"error": str(e), "details": e.details}), e.status

    @app.errorhandler(404)
    def _handle_404(e):
        # Preserve prior behavior: /api/* + /socket.io/* → JSON 404
        path = request.path or ""
        if path.startswith("/api/") or path.startswith("/socket.io/"):
            return jsonify({"error": "not found"}), 404
        return e  # default Flask HTML 404 for non-api paths

    @app.errorhandler(500)
    def _handle_500(e):
        request_id = getattr(g, "request_id", None)
        app.logger.exception("internal_error")
        return (
            jsonify({"error": "internal server error", "request_id": request_id}),
            500,
        )
