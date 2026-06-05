"""Task 5: verify app.py delegates to platform_backend for ASR override + Ollama engine.

TDD: tests were written before the implementation (Step 1 — RED phase).
Run from backend/ with:
  python -m pytest tests/test_platform_backend_wiring.py -v
"""

import platform_backend as pb
import app


def _force_darwin(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pb.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: None)
    monkeypatch.delenv("R5_ASR_BACKEND", raising=False)
    monkeypatch.delenv("R5_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("R5_OLLAMA_URL", raising=False)


def test_app_asr_override_matches_mlx_on_darwin(monkeypatch):
    _force_darwin(monkeypatch)
    assert app._output_lang_asr_override() == {"asr": {
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "condition_on_previous_text": False,
    }}


def test_app_ollama_engine_matches_mlx_on_darwin(monkeypatch):
    _force_darwin(monkeypatch)
    eng = app._make_ollama_llm_call_engine()
    assert eng._model == "qwen3.5:35b-a3b-mlx-bf16"
    assert eng._base_url == "http://localhost:11434"


def test_app_asr_override_cuda_on_linux_with_nvidia(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Linux")
    monkeypatch.setattr(pb.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    monkeypatch.delenv("R5_ASR_BACKEND", raising=False)
    out = app._output_lang_asr_override()
    assert out["asr"]["engine"] == "whisper"
    assert out["asr"]["device"] == "cuda"


def test_app_make_ollama_llm_call_is_callable(monkeypatch):
    _force_darwin(monkeypatch)
    fn = app._make_ollama_llm_call()
    assert callable(fn)
