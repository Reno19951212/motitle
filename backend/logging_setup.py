"""Logging configuration for v4.0 A6 C4 — JSON output controlled by env."""
from __future__ import annotations
import contextvars
import logging
import os

from flask import Flask, g, has_request_context
from pythonjsonlogger import jsonlogger

# Module-level ContextVar for cross-context request_id propagation.
# This allows werkzeug's access logger (which fires outside the Flask request
# context, after the response is sent) to still read the request_id that was
# assigned by before_request middleware.
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(request_id: str | None) -> None:
    """Set request_id in the current execution context.

    Called by middleware on before_request (set) and teardown_request (clear).
    """
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Read request_id from the current execution context."""
    return _request_id_var.get()


class RequestIdFilter(logging.Filter):
    """Adds request_id to every log record.

    Reads from the module-level ContextVar first — this works for werkzeug's
    access logger and any background thread that inherits the context.  Falls
    back to ``flask.g`` for callers that set the field only there.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _request_id_var.get()
        if rid is None:
            try:
                if has_request_context():
                    rid = getattr(g, "request_id", None)
            except Exception:
                rid = None
        record.request_id = rid
        return True


def configure_logging(app: Flask) -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    use_json = os.environ.get("LOG_JSON", "1") != "0"

    handler = logging.StreamHandler()
    if use_json:
        handler.setFormatter(
            jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s"
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
            )
        )
    handler.addFilter(RequestIdFilter())

    # Reset root + app logger handlers to ensure we own them.
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    app.logger.handlers = [handler]
    app.logger.setLevel(level)
    app.logger.propagate = False
