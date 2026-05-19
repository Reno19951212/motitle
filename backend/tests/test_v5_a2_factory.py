import json
import pytest
from engines.factory import build_llm_engine, load_prompt_template


def test_build_llm_engine_ollama():
    """ollama backend → OllamaLLM instance with correct base_url + model."""
    from engines.llm.ollama import OllamaLLM
    profile = {
        "backend": "ollama",
        "model": "qwen3.5:9b",
        "base_url": "http://localhost:11434",
    }
    engine = build_llm_engine(profile)
    assert isinstance(engine, OllamaLLM)
    assert engine.model == "qwen3.5:9b"
    assert engine.base_url == "http://localhost:11434"


def test_build_llm_engine_openrouter():
    from engines.llm.openrouter import OpenRouterLLM
    profile = {
        "backend": "openrouter",
        "model": "anthropic/claude-opus-4-7",
        "api_key": "sk-xxx",
    }
    engine = build_llm_engine(profile)
    assert isinstance(engine, OpenRouterLLM)
    assert engine.api_key == "sk-xxx"


def test_build_llm_engine_openrouter_missing_api_key():
    profile = {"backend": "openrouter", "model": "m"}
    with pytest.raises(ValueError, match="api_key"):
        build_llm_engine(profile)


def test_build_llm_engine_claude_not_implemented():
    with pytest.raises(NotImplementedError):
        build_llm_engine({"backend": "claude", "model": "x"})


def test_build_llm_engine_unknown_backend():
    with pytest.raises(ValueError, match="unknown LLM backend"):
        build_llm_engine({"backend": "bogus"})


def test_load_prompt_template_translator_zh_to_en():
    """Default v5-A1 template should load cleanly."""
    prompt = load_prompt_template("translator/zh_to_en_default")
    assert "Hong Kong Cantonese to English" in prompt
    assert len(prompt) > 100


def test_load_prompt_template_refiner_zh_broadcast():
    prompt = load_prompt_template("refiner/zh_broadcast_hk_default")
    assert "香港" in prompt or "粵語" in prompt


def test_load_prompt_template_missing():
    with pytest.raises(FileNotFoundError):
        load_prompt_template("translator/nonexistent")


def test_load_prompt_template_bad_id():
    with pytest.raises(ValueError, match="<category>/<name>"):
        load_prompt_template("no_slash")


def test_resolve_prompt_uses_override_when_present():
    from engines.factory import resolve_prompt
    custom = "my custom prompt text"
    out = resolve_prompt("translator/zh_to_en_default", file_override=custom)
    assert out == custom


def test_resolve_prompt_falls_back_to_template_when_override_empty():
    from engines.factory import resolve_prompt
    out = resolve_prompt("translator/zh_to_en_default", file_override="")
    assert "Cantonese" in out

    out2 = resolve_prompt("translator/zh_to_en_default", file_override=None)
    assert "Cantonese" in out2
