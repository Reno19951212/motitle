"""Verify app.py wires up V6 managers + blueprints on boot."""
import pytest


def test_app_has_pipeline_manager_in_config():
    import app
    assert app.app.config.get("PIPELINE_MANAGER") is not None
    from pipelines import PipelineManager
    assert isinstance(app.app.config["PIPELINE_MANAGER"], PipelineManager)


def test_app_has_transcribe_profile_manager_in_config():
    import app
    assert app.app.config.get("TRANSCRIBE_PROFILE_MANAGER") is not None


def test_app_has_llm_profile_manager_in_config():
    import app
    assert app.app.config.get("LLM_PROFILE_MANAGER") is not None


def test_app_has_refiner_profile_manager_in_config():
    import app
    assert app.app.config.get("REFINER_PROFILE_MANAGER") is not None


def test_pipelines_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/pipelines") for r in rules), \
        "Expected at least one /api/pipelines route registered"


def test_refiner_profiles_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/refiner_profiles") for r in rules)


def test_transcribe_profiles_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/transcribe_profiles") for r in rules)


def test_llm_profiles_blueprint_registered():
    import app
    rules = [str(r) for r in app.app.url_map.iter_rules()]
    assert any(r.startswith("/api/llm_profiles") for r in rules)
