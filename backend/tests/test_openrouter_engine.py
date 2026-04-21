"""Tests for OpenRouter translation engine."""
import json
import io
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ───────────────────────── Factory integration ─────────────────────────


def test_factory_creates_openrouter_engine():
    from translation import create_translation_engine
    engine = create_translation_engine({
        "engine": "openrouter",
        "api_key": "test-key",
    })
    from translation.openrouter_engine import OpenRouterTranslationEngine
    assert isinstance(engine, OpenRouterTranslationEngine)


def test_factory_unknown_engine_still_raises():
    """OpenRouter addition must not break the catch-all error."""
    from translation import create_translation_engine
    import pytest
    with pytest.raises(ValueError, match="Unknown translation engine"):
        create_translation_engine({"engine": "not-a-real-engine"})


# ───────────────────────── Config + defaults ─────────────────────────


def test_engine_uses_default_model_when_not_configured():
    from translation.openrouter_engine import (
        OpenRouterTranslationEngine, DEFAULT_OPENROUTER_MODEL,
    )
    engine = OpenRouterTranslationEngine({"api_key": "x"})
    assert engine._model == DEFAULT_OPENROUTER_MODEL


def test_engine_respects_custom_model():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({
        "api_key": "x",
        "openrouter_model": "openai/gpt-4o-mini",
    })
    assert engine._model == "openai/gpt-4o-mini"


def test_engine_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({})
    assert engine._api_key == "env-key"


def test_engine_config_key_overrides_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({"api_key": "config-key"})
    assert engine._api_key == "config-key"


# ──────────────────── _call_ollama (HTTP roundtrip) ────────────────────


def _make_fake_response(content: str) -> MagicMock:
    """Build a context-manager mock for urlopen returning a valid OpenAI body."""
    body = json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode("utf-8")
    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=None)
    resp.read = MagicMock(return_value=body)
    return resp


def test_call_openrouter_sends_bearer_auth_and_openai_body():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({
        "api_key": "sk-or-test",
        "openrouter_model": "anthropic/claude-sonnet-4.5",
    })

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _make_fake_response("你好世界")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = engine._call_ollama("sys", "user", 0.1)

    assert result == "你好世界"
    assert captured["url"].endswith("/chat/completions")
    # urllib canonicalises header keys as Title-Case
    assert captured["headers"].get("Authorization") == "Bearer sk-or-test"
    assert captured["body"]["model"] == "anthropic/claude-sonnet-4.5"
    assert captured["body"]["temperature"] == 0.1
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1]["content"] == "user"
    assert captured["body"]["stream"] is False


def test_call_openrouter_missing_api_key_raises():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    import pytest
    engine = OpenRouterTranslationEngine({})  # no key, no env
    # Ensure env doesn't leak a value
    with patch.dict(os.environ, {}, clear=True):
        engine._api_key = ""  # re-force empty after patch
        with pytest.raises(ConnectionError, match="API key missing"):
            engine._call_ollama("sys", "user", 0.1)


def test_call_openrouter_empty_choices_returns_empty_string():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({"api_key": "x"})

    def fake_urlopen(req, timeout=None):
        empty_body = json.dumps({"choices": []}).encode("utf-8")
        resp = MagicMock()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=None)
        resp.read = MagicMock(return_value=empty_body)
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        assert engine._call_ollama("s", "u", 0.1) == ""


# ───────────────────────── Metadata / schema ─────────────────────────


def test_get_info_reports_unavailable_without_key():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    # Ensure env var doesn't accidentally set a key
    with patch.dict(os.environ, {}, clear=True):
        engine = OpenRouterTranslationEngine({})
        info = engine.get_info()
    assert info["engine"] == "openrouter"
    assert info["available"] is False
    assert info["requires_api_key"] is True


def test_get_info_reports_available_with_key():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({"api_key": "sk-x"})
    assert engine.get_info()["available"] is True


def test_get_models_returns_curated_list():
    from translation.openrouter_engine import (
        OpenRouterTranslationEngine, CURATED_MODELS,
    )
    engine = OpenRouterTranslationEngine({"api_key": "sk-x"})
    models = engine.get_models()
    assert len(models) == len(CURATED_MODELS)
    for m in models:
        assert m["engine"] == "openrouter"
        assert m["available"] is True
        assert m["is_cloud"] is True
        assert "label" in m and "strengths" in m


def test_schema_includes_openrouter_specific_fields():
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({"api_key": "sk-x"})
    schema = engine.get_params_schema()
    assert schema["engine"] == "openrouter"
    # model selector uses openrouter_model, not Ollama's `model`
    assert "openrouter_model" in schema["params"]
    assert "model" not in schema["params"]
    assert "api_key" in schema["params"]
    assert schema["params"]["api_key"].get("secret") is True


def test_openrouter_model_is_free_form_not_enum():
    """Users can supply any model id — schema must not enforce an enum."""
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({"api_key": "sk-x"})
    schema = engine.get_params_schema()
    field = schema["params"]["openrouter_model"]
    assert "enum" not in field, "openrouter_model must be free-form, not enum-restricted"
    # Curated list stays available as suggestions
    assert "suggestions" in field
    assert len(field["suggestions"]) >= 3


def test_engine_accepts_arbitrary_model_id():
    """Passing a model not in CURATED_MODELS must still be accepted."""
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({
        "api_key": "sk-x",
        "openrouter_model": "some-lab/experimental-model-v2",
    })
    assert engine._model == "some-lab/experimental-model-v2"


def test_is_thinking_model_always_false():
    """OpenRouter doesn't use Ollama's `think` flag."""
    from translation.openrouter_engine import OpenRouterTranslationEngine
    engine = OpenRouterTranslationEngine({"api_key": "x"})
    assert engine._is_thinking_model() is False
