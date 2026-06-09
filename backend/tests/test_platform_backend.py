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


# Target = STHeiti ("Heiti TC"/"Heiti SC"): /System/Library/Fonts/ proper, the
# only CJK family a session-less LaunchDaemon can fully load (PingFang lives in
# AssetsV2 and tofu's under a daemon; Noto/Microsoft are absent on macOS).

def test_subtitle_font_darwin_maps_noto_tc_to_heiti_tc():
    assert pb.resolve_subtitle_font_family("Noto Sans TC", _DARWIN) == "Heiti TC"


def test_subtitle_font_darwin_maps_noto_hk_to_heiti_tc():
    assert pb.resolve_subtitle_font_family("Noto Sans HK", _DARWIN) == "Heiti TC"


def test_subtitle_font_darwin_maps_noto_sc_to_heiti_sc():
    assert pb.resolve_subtitle_font_family("Noto Sans SC", _DARWIN) == "Heiti SC"


def test_subtitle_font_darwin_maps_msjhenghei_to_heiti_tc():
    assert pb.resolve_subtitle_font_family("Microsoft JhengHei", _DARWIN) == "Heiti TC"


def test_subtitle_font_darwin_maps_msyahei_to_heiti_sc():
    assert pb.resolve_subtitle_font_family("Microsoft YaHei", _DARWIN) == "Heiti SC"


def test_subtitle_font_darwin_maps_source_han_hk_to_heiti_tc():
    assert pb.resolve_subtitle_font_family("Source Han Sans HK", _DARWIN) == "Heiti TC"


def test_subtitle_font_darwin_case_and_space_insensitive():
    assert pb.resolve_subtitle_font_family("  noto sans tc  ", _DARWIN) == "Heiti TC"


def test_subtitle_font_darwin_remaps_pingfang_tc_to_heiti():
    # PingFang is "installed" but lives in on-demand AssetsV2 → a session-less
    # daemon cannot load its glyphs (tofu). Must be remapped to Heiti.
    assert pb.resolve_subtitle_font_family("PingFang TC", _DARWIN) == "Heiti TC"


def test_subtitle_font_darwin_remaps_pingfang_sc_to_heiti_sc():
    assert pb.resolve_subtitle_font_family("PingFang SC", _DARWIN) == "Heiti SC"


def test_subtitle_font_darwin_remaps_other_assetsv2_cjk_to_heiti():
    # Songti/Kaiti/STSong also live in AssetsV2 → daemon-inaccessible; rescued.
    assert pb.resolve_subtitle_font_family("Songti SC", _DARWIN) == "Heiti SC"
    assert pb.resolve_subtitle_font_family("Kaiti TC", _DARWIN) == "Heiti TC"
    assert pb.resolve_subtitle_font_family("STSong", _DARWIN) == "Heiti SC"


def test_subtitle_font_darwin_keeps_heiti_and_unknown():
    # Heiti is already daemon-safe; uploaded brand fonts (via :fontsdir=) and
    # other proper-dir fonts pass through untouched.
    assert pb.resolve_subtitle_font_family("Heiti TC", _DARWIN) == "Heiti TC"
    assert pb.resolve_subtitle_font_family("Hiragino Sans GB", _DARWIN) == "Hiragino Sans GB"
    assert pb.resolve_subtitle_font_family("My Brand Font", _DARWIN) == "My Brand Font"


def test_subtitle_font_non_darwin_passthrough():
    # Windows/Linux ship their own Noto/Microsoft CJK fonts — never remap.
    assert pb.resolve_subtitle_font_family("Noto Sans TC", _LINUX) == "Noto Sans TC"
    assert pb.resolve_subtitle_font_family("PingFang TC", _LINUX) == "PingFang TC"


def test_subtitle_font_empty_or_none_is_safe():
    assert pb.resolve_subtitle_font_family("", _DARWIN) == ""
    assert pb.resolve_subtitle_font_family(None, _DARWIN) is None


# ---------------------------------------------------------------------------
# Task 6: available_subtitle_fonts()  (font-picker source of truth)
# ---------------------------------------------------------------------------

def test_available_fonts_darwin_includes_heiti_when_file_present(monkeypatch):
    # STHeiti present in /System/Library/Fonts/ proper → Heiti TC + SC offered.
    # Hiragino Sans GB is intentionally NOT a candidate (GB/Simplified-oriented).
    monkeypatch.setattr(pb.os.path, "exists", lambda p: "STHeiti" in p)
    assert pb.available_subtitle_fonts(_DARWIN) == ["Heiti TC", "Heiti SC"]


def test_available_fonts_empty_info_falls_through_no_crash():
    # A degenerate/empty info dict must not raise; it falls through to the
    # non-darwin branch and returns the linux curated list.
    assert pb.available_subtitle_fonts({}) == list(pb._LINUX_CJK)


def test_available_fonts_darwin_excludes_when_files_missing(monkeypatch):
    monkeypatch.setattr(pb.os.path, "exists", lambda p: False)
    assert pb.available_subtitle_fonts(_DARWIN) == []


def test_available_fonts_darwin_never_offers_pingfang(monkeypatch):
    # Even with everything "present", PingFang must never appear — it lives in
    # AssetsV2 and a session-less daemon cannot load it (would tofu).
    monkeypatch.setattr(pb.os.path, "exists", lambda p: True)
    fonts = pb.available_subtitle_fonts(_DARWIN)
    assert not any("PingFang" in f for f in fonts)
    assert not any("Noto" in f for f in fonts)


def test_available_fonts_windows_curated():
    fonts = pb.available_subtitle_fonts({"os": "win32", "arch": "x86_64", "has_cuda": False})
    assert "Microsoft JhengHei" in fonts


def test_available_fonts_linux_curated():
    fonts = pb.available_subtitle_fonts(_LINUX)
    assert any("Noto Sans CJK" in f for f in fonts)
