"""Shared Flask-Limiter instance.

Initialized lazily via limiter.init_app(app) in app.py.
Tests set RATELIMIT_ENABLED=False in app config to disable enforcement.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
