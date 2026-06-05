"""Tests for platform_backend.py — Tasks 1–4.

TDD: tests were written before the implementation.
Run from backend/ with:
  python -m pytest tests/test_platform_backend.py -v
"""

import platform_backend as pb


# ---------------------------------------------------------------------------
# Task 1: detect_platform()
# ---------------------------------------------------------------------------

def test_detect_platform_darwin_arm64(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(pb.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: None)
    info = pb.detect_platform()
    assert info == {"os": "darwin", "arch": "arm64", "has_cuda": False}


def test_detect_platform_windows_cuda(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Windows")
    monkeypatch.setattr(pb.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: "C:/Windows/System32/nvidia-smi.exe" if name == "nvidia-smi" else None)
    info = pb.detect_platform()
    assert info == {"os": "win32", "arch": "x86_64", "has_cuda": True}


def test_detect_platform_linux_arm64_cuda(monkeypatch):
    monkeypatch.setattr(pb.platform, "system", lambda: "Linux")
    monkeypatch.setattr(pb.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(pb.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    info = pb.detect_platform()
    assert info == {"os": "linux", "arch": "arm64", "has_cuda": True}


# ---------------------------------------------------------------------------
# Task 2: resolve_asr_override(env, info)
# ---------------------------------------------------------------------------

def test_resolve_asr_auto_darwin_is_mlx_identical():
    info = {"os": "darwin", "arch": "arm64", "has_cuda": False}
    out = pb.resolve_asr_override({}, info)
    assert out == {"asr": {"engine": "mlx-whisper", "model_size": "large-v3", "condition_on_previous_text": False}}


def test_resolve_asr_auto_cuda_is_faster_whisper():
    info = {"os": "win32", "arch": "x86_64", "has_cuda": True}
    out = pb.resolve_asr_override({}, info)
    assert out == {"asr": {"engine": "whisper", "model_size": "large-v3", "device": "cuda", "compute_type": "float16", "condition_on_previous_text": False}}


def test_resolve_asr_auto_no_cuda_is_cpu():
    info = {"os": "linux", "arch": "x86_64", "has_cuda": False}
    out = pb.resolve_asr_override({}, info)
    assert out["asr"]["engine"] == "whisper"
    assert out["asr"]["device"] == "cpu"
    assert out["asr"]["compute_type"] == "int8"


def test_resolve_asr_env_override_forces_mlx_on_linux():
    info = {"os": "linux", "arch": "arm64", "has_cuda": True}
    out = pb.resolve_asr_override({"R5_ASR_BACKEND": "mlx"}, info)
    assert out["asr"]["engine"] == "mlx-whisper"


def test_resolve_asr_env_override_gb10_whispercpp():
    info = {"os": "linux", "arch": "arm64", "has_cuda": True}
    out = pb.resolve_asr_override({"R5_ASR_BACKEND": "whispercpp"}, info)
    assert out["asr"]["engine"] == "whispercpp"
    assert out["asr"]["device"] == "cuda"


# ---------------------------------------------------------------------------
# Task 3: resolve_ollama_model(env, info)
# ---------------------------------------------------------------------------

def test_resolve_ollama_model_darwin_is_mlx_bf16():
    info = {"os": "darwin", "arch": "arm64", "has_cuda": False}
    assert pb.resolve_ollama_model({}, info) == "qwen3.5:35b-a3b-mlx-bf16"


def test_resolve_ollama_model_non_darwin_is_gguf():
    info = {"os": "win32", "arch": "x86_64", "has_cuda": True}
    assert pb.resolve_ollama_model({}, info) == "qwen3.5:35b-a3b"


def test_resolve_ollama_model_env_override_wins():
    info = {"os": "win32", "arch": "x86_64", "has_cuda": True}
    assert pb.resolve_ollama_model({"R5_OLLAMA_MODEL": "qwen3.5:35b-a3b-q8_0"}, info) == "qwen3.5:35b-a3b-q8_0"
