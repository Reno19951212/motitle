"""Tests for temperature kwarg plumbing in MlxWhisperEngine + suppress_tokens."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Phase 0 — suppress_tokens for ZH-direct hallucination phrases
# ---------------------------------------------------------------------------


def _fake_zh_tokenizer():
    """Build a minimal stand-in for mlx_whisper.tokenizer.get_tokenizer.

    Maps each character to ``ord(c) % 50000`` so we get deterministic,
    realistic-looking token IDs without needing the real Whisper tokenizer.
    """
    class _Tok:
        def encode(self, phrase):
            return [ord(c) % 50000 for c in phrase]
    return _Tok()


def test_build_suppress_tokens_zh_includes_hallucination_phrases(monkeypatch):
    """language='zh' returns [-1] PLUS tokens for every hallucination phrase."""
    from asr import mlx_whisper_engine

    fake_tok = _fake_zh_tokenizer()

    class _FakeMod:
        @staticmethod
        def get_tokenizer(*, multilingual, language, task):
            assert multilingual is True
            assert language == "zh"
            assert task == "transcribe"
            return fake_tok

    monkeypatch.setitem(sys.modules, "mlx_whisper.tokenizer", _FakeMod)
    out = mlx_whisper_engine._build_suppress_tokens("zh")
    assert -1 in out
    # At least one phrase must contribute additional tokens
    assert len(out) > 1
    # And no duplicate tokens
    assert len(out) == len(set(out))


def test_build_suppress_tokens_en_returns_just_default(monkeypatch):
    """language='en' (or anything ≠ zh) returns the bare [-1] sentinel."""
    from asr import mlx_whisper_engine
    assert mlx_whisper_engine._build_suppress_tokens("en") == [-1]
    assert mlx_whisper_engine._build_suppress_tokens(None) == [-1]
    assert mlx_whisper_engine._build_suppress_tokens("") == [-1]
    assert mlx_whisper_engine._build_suppress_tokens("ja") == [-1]


def test_build_suppress_tokens_falls_back_to_default_on_tokenizer_failure(monkeypatch):
    """If get_tokenizer raises, we still return [-1] rather than crashing."""
    from asr import mlx_whisper_engine

    class _BrokenMod:
        @staticmethod
        def get_tokenizer(**kwargs):
            raise RuntimeError("tokenizer unavailable")

    monkeypatch.setitem(sys.modules, "mlx_whisper.tokenizer", _BrokenMod)
    out = mlx_whisper_engine._build_suppress_tokens("zh")
    assert out == [-1]


def test_mlx_engine_passes_suppress_tokens_to_transcribe(monkeypatch):
    """transcribe(language='zh') wires suppress_tokens kwarg through to mlx."""
    from asr import mlx_whisper_engine
    captured = {}

    def fake_transcribe(audio, **kw):
        captured.update(kw)
        return {"segments": []}

    monkeypatch.setattr(mlx_whisper_engine.mlx_whisper, "transcribe", fake_transcribe)
    monkeypatch.setattr(
        mlx_whisper_engine,
        "_build_suppress_tokens",
        lambda lang: [-1, 100, 200, 300] if lang == "zh" else [-1],
    )
    engine = mlx_whisper_engine.MlxWhisperEngine({
        "engine": "mlx-whisper", "model_size": "large-v3",
    })
    engine.transcribe("dummy.wav", language="zh")
    assert captured.get("suppress_tokens") == [-1, 100, 200, 300]


def test_mlx_engine_propagates_avg_logprob_and_compression_ratio(monkeypatch):
    """Whisper confidence metrics flow from raw output into segment dict."""
    from asr import mlx_whisper_engine

    def fake_transcribe(audio, **kw):
        return {
            "segments": [
                {
                    "start": 0.0, "end": 1.0, "text": "hi",
                    "avg_logprob": -0.42,
                    "compression_ratio": 1.7,
                },
                {
                    "start": 1.0, "end": 2.0, "text": "world",
                    # No metrics — should still produce a clean segment
                },
            ]
        }

    monkeypatch.setattr(mlx_whisper_engine.mlx_whisper, "transcribe", fake_transcribe)
    engine = mlx_whisper_engine.MlxWhisperEngine({
        "engine": "mlx-whisper", "model_size": "large-v3",
    })
    out = engine.transcribe("dummy.wav", language="en")
    assert out[0]["avg_logprob"] == pytest.approx(-0.42)
    assert out[0]["compression_ratio"] == pytest.approx(1.7)
    # Second segment lacks metrics — keys should be absent (treated as no-signal)
    assert "avg_logprob" not in out[1]
    assert "compression_ratio" not in out[1]


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
