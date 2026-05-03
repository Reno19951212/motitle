"""Tests for temperature kwarg plumbing in MlxWhisperEngine."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mlx_engine_forwards_temperature_when_set(monkeypatch):
    """profile temperature=0.0 → mlx_whisper.transcribe(temperature=0.0)"""
    from asr import mlx_whisper_engine
    captured = {}

    def fake_transcribe(audio, **kw):
        captured.update(kw)
        return {"segments": []}

    monkeypatch.setattr(mlx_whisper_engine.mlx_whisper, "transcribe", fake_transcribe)
    engine = mlx_whisper_engine.MlxWhisperEngine({
        "engine": "mlx-whisper", "model_size": "large-v3", "temperature": 0.0,
    })
    engine.transcribe("dummy.wav", language="en")
    assert "temperature" in captured
    assert captured["temperature"] == 0.0


def test_mlx_engine_omits_temperature_when_none(monkeypatch):
    """profile temperature=None → mlx_whisper.transcribe called without temperature kwarg."""
    from asr import mlx_whisper_engine
    captured = {}

    def fake_transcribe(audio, **kw):
        captured.update(kw)
        return {"segments": []}

    monkeypatch.setattr(mlx_whisper_engine.mlx_whisper, "transcribe", fake_transcribe)
    engine = mlx_whisper_engine.MlxWhisperEngine({
        "engine": "mlx-whisper", "model_size": "large-v3",  # no temperature
    })
    engine.transcribe("dummy.wav", language="en")
    assert "temperature" not in captured


def test_mlx_engine_schema_exposes_temperature():
    """get_params_schema includes temperature with nullable + range metadata."""
    from asr.mlx_whisper_engine import MlxWhisperEngine
    engine = MlxWhisperEngine({"engine": "mlx-whisper", "model_size": "large-v3"})
    schema = engine.get_params_schema()
    params = schema["params"]
    assert "temperature" in params
    t = params["temperature"]
    assert t.get("nullable") is True
    assert t.get("min") == 0.0
    assert t.get("max") == 1.0
    assert t.get("default") is None
