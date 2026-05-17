"""Engine-info routes — ASR + translation engine discovery + the legacy
``/api/models`` Whisper-model list.

v4 A6 C2 T13a — extracted from ``app.py``.

These endpoints are pure metadata (no registry / no jobqueue side-effects),
which lets them live in a thin blueprint that lazy-imports the engine
factories so this module stays cheap to load.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify

from auth.decorators import login_required

bp = Blueprint("engines", __name__)


# ---------------------------------------------------------------------------
# Legacy /api/models — Whisper model availability (download/loaded state)
# ---------------------------------------------------------------------------
@bp.get("/api/models")
@login_required
def list_models():
    """List available Whisper models with download/loaded status."""
    import app as _app

    # Check which models are downloaded on disk
    cache_dir = Path.home() / ".cache" / "whisper"
    downloaded = set()
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            if f.suffix == ".pt":
                downloaded.add(f.stem)  # e.g. 'small', 'tiny'

    # Check which models are loaded in memory
    loaded_openai = set(_app._openai_model_cache.keys())
    loaded_faster = set(_app._faster_model_cache.keys())
    loaded = loaded_openai | loaded_faster

    models_info = [
        {"id": "tiny",   "name": "Tiny",   "params": "39M",   "speed": "最快", "quality": "基礎"},
        {"id": "base",   "name": "Base",   "params": "74M",   "speed": "快",   "quality": "良好"},
        {"id": "small",  "name": "Small",  "params": "244M",  "speed": "中等", "quality": "優良"},
        {"id": "medium", "name": "Medium", "params": "769M",  "speed": "慢",   "quality": "出色"},
        {"id": "large",  "name": "Large",  "params": "1550M", "speed": "最慢", "quality": "最佳"},
        {"id": "turbo",  "name": "Turbo",  "params": "809M",  "speed": "快",   "quality": "優良"},
    ]

    for m in models_info:
        mid = m["id"]
        if mid in loaded:
            m["status"] = "loaded"          # in memory, ready to use
        elif mid in downloaded:
            m["status"] = "downloaded"      # on disk, needs loading
        else:
            m["status"] = "not_downloaded"  # needs download + loading

    return jsonify({"models": models_info})


# ---------------------------------------------------------------------------
# ASR engines
# ---------------------------------------------------------------------------
@bp.get("/api/asr/engines")
@login_required
def api_list_asr_engines():
    """List available ASR engines with status."""
    from asr import create_asr_engine
    engines_info = []
    for engine_name, desc in [
        ("whisper", "Whisper (faster-whisper, CPU)"),
        ("mlx-whisper", "MLX Whisper (Metal GPU, Apple Silicon)"),
    ]:
        try:
            engine = create_asr_engine({"engine": engine_name, "model_size": "unknown"})
            info = engine.get_info()
            engines_info.append({
                "engine": engine_name,
                "available": info.get("available", False),
                "description": desc,
            })
        except Exception:
            engines_info.append({
                "engine": engine_name,
                "available": False,
                "description": desc,
            })
    return jsonify({"engines": engines_info})


@bp.get("/api/asr/engines/<name>/params")
@login_required
def api_asr_engine_params(name):
    """Get configurable parameter schema for a specific ASR engine."""
    from asr import create_asr_engine
    try:
        engine = create_asr_engine({"engine": name, "model_size": "unknown"})
        return jsonify(engine.get_params_schema())
    except ValueError:
        return jsonify({"error": f"Unknown ASR engine: {name}"}), 404


# ---------------------------------------------------------------------------
# Translation engines
# ---------------------------------------------------------------------------
@bp.get("/api/translation/engines")
@login_required
def api_list_translation_engines():
    """List available translation engines with status."""
    from translation import create_translation_engine
    from translation.ollama_engine import CLOUD_ENGINES

    engines_info = []
    for engine_name, desc in [
        ("mock", "Mock translator (development)"),
        ("qwen2.5-3b", "Qwen 2.5 3B (Ollama)"),
        ("qwen2.5-7b", "Qwen 2.5 7B (Ollama)"),
        ("qwen2.5-72b", "Qwen 2.5 72B (Ollama)"),
        ("qwen3-235b", "Qwen3 235B MoE (Ollama)"),
        ("qwen3.5-9b", "Qwen 3.5 9B (Ollama)"),
        ("qwen3.5-35b-a3b", "Qwen 3.5 35B-A3B MLX (Ollama)"),
        ("glm-4.6-cloud", "GLM-4.6 (Ollama Cloud)"),
        ("qwen3.5-397b-cloud", "Qwen 3.5 397B MoE (Ollama Cloud)"),
        ("gpt-oss-120b-cloud", "GPT-OSS 120B (Ollama Cloud)"),
        ("openrouter", "OpenRouter (Claude / GPT / Gemini / etc.)"),
    ]:
        try:
            engine = create_translation_engine({"engine": engine_name})
            info = engine.get_info()
            engines_info.append({
                "engine": engine_name,
                "available": info.get("available", False),
                "description": desc,
                "is_cloud": engine_name in CLOUD_ENGINES or engine_name == "openrouter",
                "requires_api_key": info.get("requires_api_key", False),
            })
        except Exception:
            engines_info.append({
                "engine": engine_name,
                "available": False,
                "description": desc,
                "is_cloud": engine_name in CLOUD_ENGINES or engine_name == "openrouter",
                "requires_api_key": engine_name == "openrouter",
            })
    return jsonify({"engines": engines_info})


@bp.get("/api/translation/engines/<name>/params")
@login_required
def api_translation_engine_params(name):
    """Get configurable parameter schema for a specific translation engine."""
    from translation import create_translation_engine
    try:
        engine = create_translation_engine({"engine": name})
        return jsonify(engine.get_params_schema())
    except ValueError:
        return jsonify({"error": f"Unknown translation engine: {name}"}), 404


@bp.get("/api/translation/engines/<name>/models")
@login_required
def api_translation_engine_models(name):
    """Return the model info for the specified translation engine.

    ``OllamaTranslationEngine.get_models()`` enumerates every entry in
    ENGINE_TO_MODEL, so the raw result would confuse the frontend (which
    expects one entry per engine). We filter to just the requested engine.
    """
    from translation import create_translation_engine
    try:
        engine = create_translation_engine({"engine": name})
        all_models = engine.get_models()
        matching = [m for m in all_models if m.get("engine") == name]
        # Fallback: if no match (e.g. mock engine returns a single dummy),
        # return whatever the engine provided.
        models = matching if matching else all_models
        return jsonify({"engine": name, "models": models})
    except ValueError:
        return jsonify({"error": f"Unknown translation engine: {name}"}), 404
