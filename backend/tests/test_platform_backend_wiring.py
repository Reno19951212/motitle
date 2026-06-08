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


# ---------------------------------------------------------------------------
# Broadened cross-platform wiring (Fix #13a). Each case monkeypatches
# platform_backend.platform / .shutil and clears the R5_* env, then exercises
# the real app.* functions (full venv — these import app).
# ---------------------------------------------------------------------------

def _set_platform(monkeypatch, system, machine, cuda_present):
    """Force the detected OS/arch and whether nvidia-smi resolves on PATH."""
    monkeypatch.setattr(pb.platform, "system", lambda: system)
    monkeypatch.setattr(pb.platform, "machine", lambda: machine)
    monkeypatch.setattr(
        pb.shutil, "which",
        lambda name: "/usr/bin/nvidia-smi" if (name == "nvidia-smi" and cuda_present) else None,
    )
    for var in ("R5_ASR_BACKEND", "R5_OLLAMA_MODEL", "R5_OLLAMA_URL"):
        monkeypatch.delenv(var, raising=False)


def test_app_asr_override_cuda_on_windows_with_nvidia(monkeypatch):
    """Windows + NVIDIA (auto) -> faster-whisper on cuda."""
    _set_platform(monkeypatch, "Windows", "AMD64", cuda_present=True)
    out = app._output_lang_asr_override()
    assert out["asr"]["engine"] == "whisper"
    assert out["asr"]["device"] == "cuda"
    assert out["asr"]["compute_type"] == "float16"


def test_app_asr_override_cpu_on_linux_no_cuda(monkeypatch):
    """Linux, no nvidia-smi (auto) -> faster-whisper on cpu / int8."""
    _set_platform(monkeypatch, "Linux", "x86_64", cuda_present=False)
    out = app._output_lang_asr_override()
    assert out["asr"]["engine"] == "whisper"
    assert out["asr"]["device"] == "cpu"
    assert out["asr"]["compute_type"] == "int8"


def test_app_asr_override_force_mlx_on_linux(monkeypatch):
    """R5_ASR_BACKEND=mlx forces the mlx-whisper engine even off-darwin."""
    _set_platform(monkeypatch, "Linux", "x86_64", cuda_present=False)
    monkeypatch.setenv("R5_ASR_BACKEND", "mlx")
    out = app._output_lang_asr_override()
    assert out["asr"]["engine"] == "mlx-whisper"


def test_app_asr_override_force_whispercpp(monkeypatch):
    """R5_ASR_BACKEND=whispercpp forces the whispercpp engine."""
    _set_platform(monkeypatch, "Linux", "x86_64", cuda_present=False)
    monkeypatch.setenv("R5_ASR_BACKEND", "whispercpp")
    out = app._output_lang_asr_override()
    assert out["asr"]["engine"] == "whispercpp"


def test_app_ollama_url_override_flows_to_base_url(monkeypatch):
    """R5_OLLAMA_URL overrides the engine's _base_url end-to-end."""
    _set_platform(monkeypatch, "Linux", "x86_64", cuda_present=False)
    monkeypatch.setenv("R5_OLLAMA_URL", "http://gpu-box:9999")
    eng = app._make_ollama_llm_call_engine()
    assert eng._base_url == "http://gpu-box:9999"
