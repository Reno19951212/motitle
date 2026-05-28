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
    from .pipelines import bp as pipelines_bp
    # v5-A3 T10 — legacy /api/asr_profiles + /api/mt_profiles blueprints
    # retired. Frontend has migrated to /api/transcribe_profiles +
    # /api/refiner_profiles (v5-A1 T26). Deprecation/Sunset headers from
    # v5-A1 served notice; removing the routes simplifies the surface area
    # before merging v5 to main.
    from .glossaries import bp as glossaries_bp
    from .languages import bp as languages_bp
    from .prompt_templates import bp as prompt_templates_bp
    from .render import bp as render_bp
    from .engines import bp as engines_bp
    from .ollama import bp as ollama_bp
    # v5-A1 T26 — 5 new profile blueprints (replacement for v4 ASR / MT profile)
    from .llm_profiles import bp as llm_profiles_bp
    from .transcribe_profiles import bp as transcribe_profiles_bp
    from .translator_profiles import bp as translator_profiles_bp
    from .refiner_profiles import bp as refiner_profiles_bp
    from .verifier_profiles import bp as verifier_profiles_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(spa_bp)
    app.register_blueprint(fonts_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(pipelines_bp)
    app.register_blueprint(glossaries_bp)
    app.register_blueprint(languages_bp)
    app.register_blueprint(prompt_templates_bp)
    app.register_blueprint(render_bp)
    app.register_blueprint(engines_bp)
    app.register_blueprint(ollama_bp)
    # v5-A1 T26
    app.register_blueprint(llm_profiles_bp)
    app.register_blueprint(transcribe_profiles_bp)
    app.register_blueprint(translator_profiles_bp)
    app.register_blueprint(refiner_profiles_bp)
    app.register_blueprint(verifier_profiles_bp)


__all__ = ["register_blueprints"]
