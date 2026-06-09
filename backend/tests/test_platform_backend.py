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


def test_resolve_asr_whispercpp_no_cuda_falls_back_to_cpu():
    info = {"os": "linux", "arch": "arm64", "has_cuda": False}
    out = pb.resolve_asr_override({"R5_ASR_BACKEND": "whispercpp"}, info)
    assert out["asr"]["engine"] == "whispercpp"
    assert out["asr"]["device"] == "cpu"
    assert out["asr"]["compute_type"] == "int8"


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


# ---------------------------------------------------------------------------
# Task 4: resolve_ollama_url(env)
# ---------------------------------------------------------------------------

def test_resolve_ollama_url_default():
    assert pb.resolve_ollama_url({}) == "http://localhost:11434"


def test_resolve_ollama_url_env():
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "http://10.0.0.5:11434"}) == "http://10.0.0.5:11434"


def test_resolve_ollama_url_blank_falls_back():
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "  "}) == "http://localhost:11434"


def test_resolve_ollama_url_valid_https_passes(capsys):
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "https://ollama.internal:11434"}) == "https://ollama.internal:11434"
    assert capsys.readouterr().err == ""


def test_resolve_ollama_url_invalid_scheme_falls_back(capsys):
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "htp://localhost"}) == "http://localhost:11434"
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "htp://localhost" in err


def test_resolve_ollama_url_no_scheme_falls_back(capsys):
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "localhost:11434"}) == "http://localhost:11434"
    err = capsys.readouterr().err
    assert "WARNING" in err


def test_resolve_ollama_url_blank_is_silent(capsys):
    assert pb.resolve_ollama_url({"R5_OLLAMA_URL": "   "}) == "http://localhost:11434"
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Task 5: resolve_subtitle_font_family()  (subtitle burn-in CJK fallback)
# ---------------------------------------------------------------------------

_DARWIN = {"os": "darwin", "arch": "arm64", "has_cuda": False}
_LINUX = {"os": "linux", "arch": "x86_64", "has_cuda": False}


def test_subtitle_font_darwin_maps_noto_tc_to_pingfang_tc():
    assert pb.resolve_subtitle_font_family("Noto Sans TC", _DARWIN) == "PingFang TC"


def test_subtitle_font_darwin_maps_noto_hk_to_pingfang_hk():
    assert pb.resolve_subtitle_font_family("Noto Sans HK", _DARWIN) == "PingFang HK"


def test_subtitle_font_darwin_maps_msjhenghei_to_pingfang_tc():
    assert pb.resolve_subtitle_font_family("Microsoft JhengHei", _DARWIN) == "PingFang TC"


def test_subtitle_font_darwin_maps_source_han_hk():
    assert pb.resolve_subtitle_font_family("Source Han Sans HK", _DARWIN) == "PingFang HK"


def test_subtitle_font_darwin_case_and_space_insensitive():
    assert pb.resolve_subtitle_font_family("  noto sans tc  ", _DARWIN) == "PingFang TC"


def test_subtitle_font_darwin_keeps_present_pingfang():
    # PingFang already resolves natively — must not be touched.
    assert pb.resolve_subtitle_font_family("PingFang HK", _DARWIN) == "PingFang HK"


def test_subtitle_font_darwin_keeps_unknown_uploaded_font():
    # A user-uploaded font (provided to libass via :fontsdir=) passes through.
    assert pb.resolve_subtitle_font_family("My Brand Font", _DARWIN) == "My Brand Font"


def test_subtitle_font_non_darwin_passthrough():
    # Windows/Linux ship their own Noto/Microsoft CJK fonts — never remap.
    assert pb.resolve_subtitle_font_family("Noto Sans TC", _LINUX) == "Noto Sans TC"
    assert pb.resolve_subtitle_font_family("Microsoft JhengHei", _LINUX) == "Microsoft JhengHei"


def test_subtitle_font_empty_or_none_is_safe():
    assert pb.resolve_subtitle_font_family("", _DARWIN) == ""
    assert pb.resolve_subtitle_font_family(None, _DARWIN) is None
