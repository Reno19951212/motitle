"""Route blueprints registered by bootstrap.create_app().

v4 A6 C2 T6 lifted health / spa / fonts handlers out of ``app.py``. T7-T11
will add additional blueprints under this package.
"""
from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all route blueprints onto the Flask app."""
    from .health import bp as health_bp
    from .spa import bp as spa_bp
    from .fonts import bp as fonts_bp
    from .files import bp as files_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(spa_bp)
    app.register_blueprint(fonts_bp)
    app.register_blueprint(files_bp)


__all__ = ["register_blueprints"]
