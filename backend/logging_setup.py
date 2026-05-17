"""Logging configuration for v4.0 A6 C4 — JSON output controlled by env."""
from __future__ import annotations
import logging
import os

from flask import Flask, g, has_request_context
from pythonjsonlogger import jsonlogger


class RequestIdFilter(logging.Filter):
    """Adds request_id to every log record (None when outside request context)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = None
        if has_request_context():
            record.request_id = getattr(g, "request_id", None)
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
